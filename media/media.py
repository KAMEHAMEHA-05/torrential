import json
import asyncio
from pathlib import Path
from media.parser import parse_media_info

SUPPORTED_VIDEO_CODECS = [
    "h264"
]

SUPPORTED_AUDIO_CODECS = [
    "aac"
]

SUPPORTED_CONTAINERS = [
    "mp4",
    "mov"
]

PROBE_SIZE = "10M"

ANALYZE_DURATION = "20M"

async def run_ffprobe(file_path: str):

    process = await asyncio.create_subprocess_exec(
        "ffprobe",

        "-v", "quiet",

        "-print_format", "json",

        "-show_streams",

        "-show_format",

        file_path,

        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(
            f"ffprobe failed: {stderr.decode()}"
        )

    return json.loads(stdout.decode())



# def get_video_profile(video_stream):

#     return video_stream.get("profile")


# def get_video_pixel_format(video_stream):

#     return video_stream.get("pix_fmt")


# def get_video_channels(audio_stream):

#     return audio_stream.get("channels")


# def get_audio_tracks(streams):

#     audio_tracks = []

#     for stream in streams:

#         if stream.get("codec_type") != "audio":
#             continue

#         audio_tracks.append({

#             "codec":
#                 stream.get("codec_name"),

#             "channels":
#                 get_video_channels(stream)
#         })

#     return audio_tracks


# def get_subtitle_tracks(streams):

#     subtitle_tracks = []

#     for stream in streams:

#         if stream.get("codec_type") != "subtitle":
#             continue

#         subtitle_tracks.append({

#             "codec":
#                 stream.get("codec_name")
#         })

#     return subtitle_tracks


async def analyze_media(
    file_path: str
):

    raw_data = await run_ffprobe(
        file_path
    )

    return parse_media_info(
        raw_data
    )


async def analyze_stream(
    read_stream
):

    process = (
        await asyncio.create_subprocess_exec(

            "ffprobe",

            "-v", "quiet",

            "-print_format", "json",

            "-show_streams",

            "-show_format",

            "-probesize", "2M",

            "-analyzeduration", "2M",

            "-i", "pipe:0",

            stdout=asyncio.subprocess.PIPE,

            stdin=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )
    )

    try:

        initial_data = (
            await read_stream.read_for_analysis(
                max_bytes=(
                    4 * 1024 * 1024
                )
            )
        )

        process.stdin.write(
            initial_data
        )

        try:

            await process.stdin.drain()

        except (
            BrokenPipeError,
            ConnectionResetError
        ):

            pass

    finally:

        try:
            process.stdin.close()

        except:
            pass

    stdout, stderr = (
        await process.communicate()
    )

    if process.returncode != 0:

        raise Exception(
            stderr.decode()
        )

    raw_data = json.loads(
        stdout.decode()
    )

    return parse_media_info(
        raw_data
    )

if __name__ == "__main__":
    file_path = str(Path("~/Downloads/sample-2.mkv").expanduser())
    print(asyncio.run(analyze_media(file_path)))