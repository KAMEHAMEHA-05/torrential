import asyncio

from pathlib import Path

from torrent.priorities import (
    update_priorities,
    apply_deadlines
)


BOOTSTRAP_WINDOW = 16

BOOTSTRAP_CHUNK_SIZE = 128 * 1024

STARTUP_WINDOW = 48

STREAM_CHUNK_SIZE = 1024 * 1024
STARTUP_CHUNK_SIZE = 512 * 1024
STEADY_CHUNK_SIZE = 512 * 1024


MIN_PLAYABLE_PIECES = 4
PLAYABLE_FRACTION = 0.125  
PIECE_WAIT_TIMEOUT = 60  
PIECE_WAIT_LOG_INTERVAL = 5  


class TorrentReadStream:

    def __init__(
        self,
        handle,
        torrent_file,
        save_path,
        buffer_window=128
    ):

        self.handle = handle

        self.torrent_file = torrent_file

        self.save_path = Path(save_path)

        self.buffer_window = buffer_window

        self.torrent_info = (
            handle.get_torrent_info()
        )

        self.piece_length = (
            self.torrent_info.piece_length()
        )

        self.total_pieces = (
            self.torrent_info.num_pieces()
        )

        self.file_path = (
            self.save_path
            /
            torrent_file["path"]
        )

        self.file_size = (
            torrent_file["size"]
        )

        self.file_offset = (
            torrent_file["offset"]
        )

        self.piece_end = (
            torrent_file["piece_end"]
        )

        self.current_offset = 0

        self.running = False

        self.file = None

        self.active_pieces = set()

        self.startup_complete = False

        self.scheduler_task = None

        self.bootstrap_complete = False


    async def start(self):

        self.running = True
        self.prioritize_file()

        await self.wait_for_file()

        self.file = open(

            self.file_path,

            "rb"
        )

        # self.scheduler_task = (
        #     asyncio.create_task(
        #         self.scheduler_loop()
        #     )
        # )


    def prioritize_file(self):

        files = self.torrent_info.files()

        for i in range(files.num_files()):

            if i == self.torrent_file["index"]:

                self.handle.file_priority(
                    i,
                    7
                )

            else:

                self.handle.file_priority(
                    i,
                    0
                )


    async def stop(self):

        self.running = False

        if self.file:
            self.file.close()

        if self.scheduler_task:
            self.scheduler_task.cancel()


    async def wait_for_file(self):

        while not self.file_path.exists():

            await asyncio.sleep(0.1)


    def current_piece(self):

        absolute_offset = (
            self.file_offset
            +
            self.current_offset
        )

        return (
            absolute_offset
            //
            self.piece_length
        )


    async def ensure_buffer(self):

        current_piece = (
            self.current_piece()
        )

        new_window = (
            self.build_piece_window(
                current_piece
            )
        )

        #
        # bootstrap:
        # first piece ONLY
        #

        if not self.bootstrap_complete:

            target_ready = 1

        #
        # startup:
        # tiny playable buffer
        #

        elif not self.startup_complete:

            target_ready = 2

        #
        # steady-state:
        # require only a small playable prefix rather than the entire window
        #

        else:

            # Adaptive target: at least MIN_PLAYABLE_PIECES, or PLAYABLE_FRACTION of the window
            computed = int(len(new_window) * PLAYABLE_FRACTION)
            target_ready = min(
                len(new_window),
                max(MIN_PLAYABLE_PIECES, computed)
            )

        # Wait loop with logging and overall timeout to avoid blocking forever
        loop_start = asyncio.get_event_loop().time()
        last_log = loop_start

        while True:

            ready = 0

            for piece in new_window:

                if self.handle.have_piece(
                    piece
                ):

                    ready += 1

            if ready >= target_ready:
                break

            now = asyncio.get_event_loop().time()

            # periodic progress log so operator can see what's missing
            if now - last_log >= PIECE_WAIT_LOG_INTERVAL:
                print(
                    f"[ensure_buffer] current_piece={current_piece} "
                    f"ready={ready}/{len(new_window)} "
                    f"target={target_ready}"
                )
                last_log = now

            # global timeout: if nothing sufficient has arrived in PIECE_WAIT_TIMEOUT seconds,
            # proceed with a fallback rather than block forever
            if now - loop_start > PIECE_WAIT_TIMEOUT:
                print(
                    f"[ensure_buffer] timeout after {PIECE_WAIT_TIMEOUT}s: "
                    f"ready={ready}/{len(new_window)}. Proceeding with fallback."
                )

                # fallback behavior:
                # - if at least one piece ready, proceed (allows streaming to continue)
                # - otherwise sleep briefly and keep trying (swarm may be initializing)
                if ready >= 1:
                    break
                else:
                    await asyncio.sleep(0.05)
                    continue

            await asyncio.sleep(0.005)

        #
        # bootstrap complete
        #

        if not self.bootstrap_complete:

            self.bootstrap_complete = True

        #
        # startup complete
        #

        elif not self.startup_complete:

            self.startup_complete = True

    async def read(self):

        # ensure window/pieces are prioritized
        await self.ensure_buffer()

        # determine read size depending on mode
        if not self.bootstrap_complete:
            read_size = BOOTSTRAP_CHUNK_SIZE
        elif not self.startup_complete:
            read_size = STARTUP_CHUNK_SIZE
        else:
            read_size = STEADY_CHUNK_SIZE

        # Wait until at least one byte is available, but avoid busy loop
        # file.seek/current_offset are relative to file start here
        while True:
            try:
                total_size = self.file_path.stat().st_size
            except Exception:
                total_size = 0

            available = total_size - self.current_offset

            if available > 0:
                break

            # If the torrent completed and file hasn't grown, treat as EOF
            # Otherwise sleep briefly and retry
            await asyncio.sleep(0.01)

        # don't read more than available bytes
        to_read = min(read_size, max(1, available))

        # read only the bytes present
        self.file.seek(self.current_offset)
        chunk = self.file.read(to_read)

        if not chunk:
            # treat as EOF if nothing could be read
            return b""

        self.current_offset += len(chunk)

        return chunk

    async def seek(self, byte_offset):

        #
        # move cursor
        #

        self.current_offset = byte_offset

        #
        # rebuild priorities
        # around seek target
        #

        current_piece = (
            self.current_piece()
        )

        #
        # AGGRESSIVE seek burst
        #

        self.burst_prioritize()

        #
        # rolling seek window
        #

        priorities = (
            self.build_piece_window(
                current_piece
            )
        )

        #
        # reprioritize swarm
        #

        update_priorities(

            self.handle,

            self.active_pieces,

            priorities
        )

        #
        # aggressive deadlines
        #

        apply_deadlines(

            self.handle,

            priorities,

            current_piece,

            startup=True
        )

        self.active_pieces = (
            priorities
        )

        #
        # wait until target region
        # becomes playable
        #

        await self.ensure_buffer()


    async def read_for_analysis(

        self,

        max_bytes=(
            4 * 1024 * 1024
        )
    ):

        current_piece = (
            self.current_piece()
        )

        startup_window = set(

            range(
                current_piece,
                min(
                    current_piece + 4,
                    self.piece_end
                )
            )
        )

        update_priorities(

            self.handle,

            self.active_pieces,

            startup_window
        )

        apply_deadlines(

            self.handle,

            startup_window,

            current_piece
        )

        self.active_pieces = (
            startup_window
        )

        #
        # only wait for first piece
        #

        while True:

            if self.file_path.exists():

                try:

                    size = self.file_path.stat().st_size

                    needed = (
                        self.current_offset
                        +
                        (512 * 1024)
                    )

                    if size >= needed:
                        break

                except:
                    pass

            await asyncio.sleep(0.005)

        self.file.seek(
            self.current_offset
        )

        chunk = self.file.read(
            max_bytes
        )

        self.current_offset += len(
            chunk
        )

        return chunk
    

    def build_piece_window(

        self,

        current_piece
    ):

        #
        # bootstrap mode
        #

        if not self.bootstrap_complete:

            buffer_window = (
                BOOTSTRAP_WINDOW
            )

        #
        # startup mode
        #

        elif not self.startup_complete:

            buffer_window = (
                STARTUP_WINDOW
            )

        #
        # steady-state
        #

        else:

            buffer_window = (
                self.buffer_window
            )

        stop = min(

            current_piece
            +
            buffer_window,

            self.piece_end
        )

        return set(

            range(
                current_piece,
                stop
            )
        )
    

    async def scheduler_loop(self):

        while self.running:

            current_piece = (
                self.current_piece()
            )

            new_window = (
                self.build_piece_window(
                    current_piece
                )
            )

            update_priorities(

                self.handle,

                self.active_pieces,

                new_window
            )

            apply_deadlines(

                self.handle,

                new_window,

                current_piece,

                startup=(
                    not self.startup_complete
                )
            )

            self.active_pieces = (
                new_window
            )

            if not self.startup_complete:

                await asyncio.sleep(0.005)

            else:

                await asyncio.sleep(0.05)

    # async def bootstrap(self):

    #     self.burst_prioritize()

    #     current_piece = (
    #         self.current_piece()
    #     )

    #     bootstrap_window = set(

    #         range(

    #             current_piece,

    #             min(
    #                 current_piece
    #                 +
    #                 BOOTSTRAP_WINDOW,

    #                 self.piece_end
    #             )
    #         )
    #     )

    #     #
    #     # ultra aggressive startup
    #     #

    #     update_priorities(

    #         self.handle,

    #         self.active_pieces,

    #         bootstrap_window
    #     )

    #     apply_deadlines(

    #         self.handle,

    #         bootstrap_window,

    #         current_piece,

    #         startup=True
    #     )

    #     self.active_pieces = (
    #         bootstrap_window
    #     )

    #     #
    #     # wait until first piece arrives
    #     #

    #     while not self.handle.have_piece(
    #         current_piece
    #     ):

    #         await asyncio.sleep(
    #             0.005
    #         )

    async def bootstrap(self):

        self.burst_prioritize()

        current_piece = (
            self.current_piece()
        )

        print(
            "BOOTSTRAP current_piece:",
            current_piece
        )

        print(
            "BOOTSTRAP have_piece:",
            self.handle.have_piece(
                current_piece
            )
        )

        while not self.handle.have_piece(
            current_piece
        ):

            print(
                "waiting on",
                current_piece
            )

            await asyncio.sleep(1)

        print(
            "BOOTSTRAP COMPLETE"
        )
    
    def burst_prioritize(self):

        current_piece = self.current_piece()

        #
        # HUGE startup fanout
        #

        burst_window = set(

            range(

                current_piece,

                min(
                    current_piece + 128,
                    self.piece_end
                )
            )
        )

        #
        # descending priorities
        #

        for i, piece in enumerate(burst_window):

            #
            # immediate playback region
            #

            if i < 8:

                priority = 7

            #
            # near future
            #

            elif i < 32:

                priority = 6

            #
            # future buffer
            #

            elif i < 64:

                priority = 5

            #
            # deep prefetch
            #

            else:

                priority = 3

            self.handle.piece_priority(
                piece,
                priority
            )

            #
            # AGGRESSIVE deadlines
            #

            self.handle.set_piece_deadline(

                piece,

                i * 10
            )


    async def wait_for_bytes(

        self,

        start_offset,

        minimum_bytes=(
            4 * 1024 * 1024
        )
    ):

        target = (
            start_offset
            +
            minimum_bytes
        )

        while True:

            if self.file_path.exists():

                try:

                    size = (
                        self.file_path
                        .stat()
                        .st_size
                    )

                    if size >= target:
                        return

                except:
                    pass

            await asyncio.sleep(
                0.01
            )


    async def wait_for_bytes(

        self,

        start_offset,

        minimum_bytes=(
            4 * 1024 * 1024
        )
    ):

        target = (
            start_offset
            +
            minimum_bytes
        )

        while True:

            if self.file_path.exists():

                try:

                    size = (
                        self.file_path
                        .stat()
                        .st_size
                    )

                    if size >= target:
                        return

                except:
                    pass

            await asyncio.sleep(
                0.01
            )