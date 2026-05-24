import asyncio

from pathlib import Path


HLS_ROOT = "/tmp/hls"


Path(HLS_ROOT).mkdir(
    parents=True,
    exist_ok=True
)


class HLSSession:

    def __init__(
        self,
        playback_session,
        input_path: str
    ):

        self.playback_session = playback_session

        self.input_path = input_path

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


    async def start(self):

        playlist = (
            self.output_dir / "master.m3u8"
        )

        segments = (
            self.output_dir / "segment_%03d.m4s"
        )

        cmd = self.build_ffmpeg_command(
            playlist,
            segments
        )

        print(" ".join(cmd))

        self.process = (
            await asyncio.create_subprocess_exec(
                *cmd,

                stdout=asyncio.subprocess.PIPE,

                stderr=asyncio.subprocess.PIPE
            )
        )

        self.active = True

        asyncio.create_task(
            self.monitor()
        )


    def build_ffmpeg_command(
        self,
        playlist,
        segments
    ):

        session = self.playback_session

        cmd = [

            "ffmpeg",

            "-i", self.input_path,

            "-preset", "ultrafast",

            "-tune", "zerolatency",

            "-g", "48",

            "-keyint_min", "48",

            "-sc_threshold", "0",
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
        # SUBTITLES
        #

        if session.burn_subtitles:

            # placeholder for future subtitle burn-in
            pass

        #
        # HLS
        #

        cmd += [

            "-f", "hls",

            "-hls_time", "4",

            "-hls_list_size", "10",

            "-hls_flags",
            "delete_segments+append_list",

            "-hls_segment_type",
            "fmp4",

            "-hls_segment_filename",
            str(segments),

            str(playlist)
        ]

        return cmd


    async def monitor(self):

        while True:

            line = (
                await self.process.stderr.readline()
            )

            if not line:
                break

            print(
                f"[FFmpeg {self.playback_session.session_id}]",
                line.decode().strip()
            )

        self.active = False