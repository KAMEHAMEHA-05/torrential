import asyncio

from pathlib import Path


HLS_ROOT = "/tmp/hls"

Path(HLS_ROOT).mkdir(
    parents=True,
    exist_ok=True
)

STDIN_DRAIN_TIMEOUT = 5
STDIN_DRAIN_RETRIES = 3               # how many times to retry on timeout before failing
STDIN_DRAIN_BACKOFF = 0.5             # seconds, linear backoff between retries
STDIN_WRITE_SLICE = 64 * 1024


#
# global transport queue
#
# producer:
# torrent engine
#
# consumer:
# hls engine
#

GLOBAL_BYTE_QUEUE = asyncio.Queue(
    maxsize=1024
)


class HLSStreamSession:

    def __init__(
        self,
        playback_session,
        byte_queue=GLOBAL_BYTE_QUEUE
    ):

        self.playback_session = (
            playback_session
        )

        self.byte_queue = (
            byte_queue
        )

        self.output_dir = (

            Path(HLS_ROOT)

            /

            playback_session.session_id
        )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        self.process = None

        self.active = False

        self.consumer_task = None

        self.monitor_task = None


    async def start(self):

        playlist = (
            self.output_dir
            /
            "master.m3u8"
        )

        segments = (
            self.output_dir
            /
            "segment_%03d.m4s"
        )

        cmd = self.build_ffmpeg_command(

            playlist,

            segments
        )

        print(
            "\n[FFmpeg CMD]\n"
        )

        print(
            " ".join(cmd)
        )

        self.process = (

            await asyncio.create_subprocess_exec(

                *cmd,

                stdin=asyncio.subprocess.PIPE,

                stdout=asyncio.subprocess.PIPE,

                stderr=asyncio.subprocess.PIPE
            )
        )

        self.active = True

        self.consumer_task = (
            asyncio.create_task(
                self.consume_bytes()
            )
        )

        self.monitor_task = (
            asyncio.create_task(
                self.monitor()
            )
        )


    def build_ffmpeg_command(

        self,

        playlist,

        segments
    ):

        session = (
            self.playback_session
        )

        cmd = [

            "ffmpeg",

            #
            # low latency input
            #

            "-fflags",
            "+nobuffer",

            "-flags",
            "low_delay",

            "-probesize",
            "2M",

            "-analyzeduration",
            "2M",

            #
            # input stream
            #

            "-i",
            "pipe:0",

            #
            # encoding speed
            #

            "-preset",
            "ultrafast",

            "-tune",
            "zerolatency",

            #
            # GOP structure
            #

            "-g",
            "48",

            "-keyint_min",
            "48",

            "-sc_threshold",
            "0",
        ]

        #
        # VIDEO
        #

        if session.transcode_video:

            cmd += [

                "-c:v",

                session.output_video_codec,

                "-pix_fmt",

                session.output_pixel_format
            ]

        else:

            cmd += [

                "-c:v",

                "copy"
            ]

        #
        # AUDIO
        #

        if session.transcode_audio:

            cmd += [

                "-c:a",

                session.output_audio_codec
            ]

        else:

            cmd += [

                "-c:a",

                "copy"
            ]

        #
        # subtitles
        #

        if session.burn_subtitles:

            #
            # future
            #

            pass

        #
        # fragmented mp4
        #

        cmd += [

            "-movflags",

            "+frag_keyframe+empty_moov"
        ]

        #
        # HLS
        #

        cmd += [

            "-map", "0:v:0",
            "-map", "0:a:0",

            "-sn",

            "-f",

            "hls",

            "-hls_time",

            "4",

            "-hls_list_size",

            "0",

            "-hls_flags",
            "independent_segments",

            "-hls_segment_type",
            "fmp4",

            "-hls_segment_filename",

            str(segments),

            str(playlist)
        ]

        return cmd


    async def consume_bytes(self):

        try:
            while True:
                chunk = await self.byte_queue.get()

                # shutdown sentinel
                if chunk is None:
                    print("[CONSUMER] Shutdown signal received")
                    break

                try:
                    # Write the chunk in slices so the pipe buffer can drain incrementally.
                    offset = 0
                    total_len = len(chunk)

                    while offset < total_len:
                        end = min(offset + STDIN_WRITE_SLICE, total_len)
                        slice_ = chunk[offset:end]

                        try:
                            self.process.stdin.write(slice_)
                        except (BrokenPipeError, ConnectionResetError) as e:
                            print("[CONSUMER] Broken pipe on write:", e)
                            raise

                        # wait for the slice to be drained with retries
                        drained = False
                        for attempt in range(1, STDIN_DRAIN_RETRIES + 1):
                            try:
                                await asyncio.wait_for(
                                    self.process.stdin.drain(),
                                    timeout=STDIN_DRAIN_TIMEOUT
                                )
                                drained = True
                                break
                            except asyncio.TimeoutError:
                                print(
                                    f"[CONSUMER] stdin.drain() timeout (>{STDIN_DRAIN_TIMEOUT}s) "
                                    f"attempt={attempt}/{STDIN_DRAIN_RETRIES} queue={self.byte_queue.qsize()}"
                                )
                                # short backoff before retrying
                                await asyncio.sleep(STDIN_DRAIN_BACKOFF * attempt)

                        if not drained:
                            # persistent stall -- abort consumer loop (will close stdin and stop HLS)
                            print("[CONSUMER] persistent stdin.drain() failures, aborting HLS consumer")
                            raise BrokenPipeError("stdin.drain() persistent failures")

                        offset = end

                    print(
                        f"[CONSUMER] chunk_size={total_len} queue={self.byte_queue.qsize()}"
                    )

                except (BrokenPipeError, ConnectionResetError) as e:
                    print("[CONSUMER] Broken pipe/connection reset:", e)
                    break

                finally:
                    # mark task done for the queue item
                    try:
                        self.byte_queue.task_done()
                    except Exception:
                        pass

        finally:
            # best-effort close of stdin
            try:
                if self.process and self.process.stdin:
                    self.process.stdin.close()
            except Exception:
                pass

    async def monitor(self):

        while True:

            line = (
                await self.process.stderr.readline()
            )

            if not line:
                break

            print(

                f"[FFmpeg "
                f"{self.playback_session.session_id}]",

                line.decode().strip()
            )

        self.active = False


    async def stop(self):

        self.active = False

        #
        # stop consumer
        #

        await self.byte_queue.put(
            None
        )

        if self.consumer_task:

            await self.consumer_task

        if self.process:

            try:

                self.process.kill()

            except:
                pass