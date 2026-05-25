import asyncio

from pathlib import Path

from torrent.priorities import (
    set_stream_priorities
)


STREAM_CHUNK_SIZE = 1024 * 1024


class TorrentReadStream:

    def __init__(
        self,
        handle,
        torrent_file,
        save_path,
        buffer_window=32
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


    async def start(self):

        self.running = True

        self.prioritize_file()

        await self.wait_for_file()

        self.file = open(
            self.file_path,
            "rb"
        )


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

        set_stream_priorities(
            self.handle,

            current_piece,

            self.piece_end,

            self.buffer_window
        )

        target_piece = min(
            current_piece
            +
            self.buffer_window,

            self.piece_end
        )

        while True:

            ready = True

            for piece in range(
                current_piece,
                target_piece
            ):

                if not self.handle.have_piece(piece):

                    ready = False
                    break

            if ready:
                return

            await asyncio.sleep(0.05)


    async def read(self):

        if not self.running:
            return b""

        remaining = (
            self.file_size
            -
            self.current_offset
        )

        if remaining <= 0:
            return b""

        await self.ensure_buffer()

        read_size = min(
            STREAM_CHUNK_SIZE,
            remaining
        )

        self.file.seek(
            self.current_offset
        )

        chunk = self.file.read(
            read_size
        )

        if not chunk:
            return b""

        self.current_offset += len(chunk)

        return chunk


    async def seek(self, byte_offset):

        self.current_offset = byte_offset

        await self.ensure_buffer()