import json
import asyncio
from pathlib import Path

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



def get_video_profile(video_stream):

    return video_stream.get("profile")


def get_video_pixel_format(video_stream):

    return video_stream.get("pix_fmt")


def get_video_channels(audio_stream):

    return audio_stream.get("channels")


def get_audio_tracks(streams):

    audio_tracks = []

    for stream in streams:

        if stream.get("codec_type") != "audio":
            continue

        audio_tracks.append({

            "codec":
                stream.get("codec_name"),

            "channels":
                get_video_channels(stream)
        })

    return audio_tracks


def get_subtitle_tracks(streams):

    subtitle_tracks = []

    for stream in streams:

        if stream.get("codec_type") != "subtitle":
            continue

        subtitle_tracks.append({

            "codec":
                stream.get("codec_name")
        })

    return subtitle_tracks


async def analyze_media(file_path: str):

    data = await run_ffprobe(file_path)

    streams = data.get("streams", [])

    video_stream = None

    for stream in streams:

        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    container = (
        data.get("format", {})
        .get("format_name", "")
        .split(",")[0]
    )

    return {

        "container": container,

        "video": {

            "codec":
                video_stream.get("codec_name")
                if video_stream else None,

            "profile":
                get_video_profile(video_stream)
                if video_stream else None,

            "pix_fmt":
                get_video_pixel_format(video_stream)
                if video_stream else None,

            "width":
                video_stream.get("width")
                if video_stream else None,

            "height":
                video_stream.get("height")
                if video_stream else None
        },

        "audio":
            get_audio_tracks(streams),

        "subtitles":
            get_subtitle_tracks(streams)
    }

if __name__ == "__main__":
    file_path = str(Path("~/Downloads/sample-2.mkv").expanduser())
    print(asyncio.run(analyze_media(file_path)))