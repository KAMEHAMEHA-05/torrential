import asyncio

from pathlib import Path


HLS_ROOT = "/tmp/hls"

Path(HLS_ROOT).mkdir(
    parents=True,
    exist_ok=True
)


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
    maxsize=128
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

                chunk = (
                    await self.byte_queue.get()
                )

                #
                # shutdown sentinel
                #

                if chunk is None:
                    print(
                        "[CONSUMER] Shutdown signal received")
                    break

                self.process.stdin.write(
                    chunk
                )

                print(
                    f"[CONSUMER] "
                    f"chunk_size={len(chunk)} "
                    f"queue={self.byte_queue.qsize()}"
                )

                # await (
                #     self.process.stdin.drain()
                # )

                self.byte_queue.task_done()

        except (

            BrokenPipeError,

            ConnectionResetError
        ):

            pass

        finally:

            try:

                self.process.stdin.close()

            except:
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