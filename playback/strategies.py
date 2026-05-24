from dataclasses import dataclass, field
from typing import Optional


DIRECT_PLAY = "direct_play"
REMUX = "remux"
TRANSCODE_AUDIO = "transcode_audio"
TRANSCODE_VIDEO = "transcode_video"
FULL_TRANSCODE = "full_transcode"


SUPPORTED_CONTAINERS = [
    "mp4",
    "mov"
]
SUPPORTED_VIDEO_CODECS = [
    "h264"
]
SUPPORTED_AUDIO_CODECS = [
    "aac"
]
SUPPORTED_PIXEL_FORMATS = [
    "yuv420p"
]
SUPPORTED_H264_PROFILES = [
    "Constrained Baseline",
    "Baseline",
    "Main",
    "High"
]
SUPPORTED_SUBTITLE_CODECS = [
    "subrip",
    "webvtt",
    None
]


@dataclass
class PlaybackSession:

    strategy: str
    playlist_url: str
    session_id: str
    media_info: dict
    remux: bool = False
    transcode_video: bool = False
    transcode_audio: bool = False
    burn_subtitles: bool = False
    output_container: str = "mp4"
    output_video_codec: str = "h264"
    output_audio_codec: str = "aac"
    output_pixel_format: str = "yuv420p"


def get_primary_audio_track(media_info):

    audio_tracks = media_info.get("audio", [])

    if not audio_tracks:
        return None

    return audio_tracks[0]


def get_primary_subtitle_track(media_info):

    subtitle_tracks = media_info.get("subtitles", [])

    if not subtitle_tracks:
        return None

    return subtitle_tracks[0]


def is_container_supported(media_info):

    return (
        media_info["container"]
        in
        SUPPORTED_CONTAINERS
    )


def is_video_supported(media_info):

    video = media_info["video"]

    return (

        video["codec"]
        in
        SUPPORTED_VIDEO_CODECS

        and

        video["pix_fmt"]
        in
        SUPPORTED_PIXEL_FORMATS

        and

        video["profile"]
        in
        SUPPORTED_H264_PROFILES
    )


def is_audio_supported(media_info):

    audio = get_primary_audio_track(media_info)

    if not audio:
        return True

    return (
        audio["codec"]
        in
        SUPPORTED_AUDIO_CODECS
    )


def are_subtitles_supported(media_info):

    subtitle = get_primary_subtitle_track(media_info)

    if not subtitle:
        return True

    return (
        subtitle["codec"]
        in
        SUPPORTED_SUBTITLE_CODECS
    )


async def try_direct_play(
    media_info: dict,
    session_id: str
) -> Optional[PlaybackSession]:

    if (

        is_container_supported(media_info)

        and

        is_video_supported(media_info)

        and

        is_audio_supported(media_info)

        and

        are_subtitles_supported(media_info)
    ):

        return PlaybackSession(

            strategy=DIRECT_PLAY,

            playlist_url=(
                f"/media/{session_id}/original"
            ),

            session_id=session_id,

            media_info=media_info
        )

    return None


async def try_remux(
    media_info: dict,
    session_id: str
) -> Optional[PlaybackSession]:

    if (

        not is_container_supported(media_info)

        and

        is_video_supported(media_info)

        and

        is_audio_supported(media_info)

        and

        are_subtitles_supported(media_info)
    ):

        return PlaybackSession(

            strategy=REMUX,

            playlist_url=(
                f"/media/{session_id}/remux/master.m3u8"
            ),

            session_id=session_id,

            media_info=media_info,

            remux=True
        )

    return None


async def try_audio_transcode(
    media_info: dict,
    session_id: str
) -> Optional[PlaybackSession]:

    if (

        is_video_supported(media_info)

        and

        not is_audio_supported(media_info)
    ):

        return PlaybackSession(

            strategy=TRANSCODE_AUDIO,

            playlist_url=(
                f"/media/{session_id}/audio/master.m3u8"
            ),

            session_id=session_id,

            media_info=media_info,

            remux=True,

            transcode_audio=True
        )

    return None


async def try_video_transcode(
    media_info: dict,
    session_id: str
) -> Optional[PlaybackSession]:

    if (

        not is_video_supported(media_info)

        and

        is_audio_supported(media_info)
    ):

        return PlaybackSession(

            strategy=TRANSCODE_VIDEO,

            playlist_url=(
                f"/media/{session_id}/video/master.m3u8"
            ),

            session_id=session_id,

            media_info=media_info,

            remux=True,

            transcode_video=True
        )

    return None


async def try_full_transcode(
    media_info: dict,
    session_id: str
) -> PlaybackSession:

    subtitle_supported = (
        are_subtitles_supported(media_info)
    )

    return PlaybackSession(

        strategy=FULL_TRANSCODE,

        playlist_url=(
            f"/media/{session_id}/transcode/master.m3u8"
        ),

        session_id=session_id,

        media_info=media_info,

        remux=True,

        transcode_video=True,

        transcode_audio=True,

        burn_subtitles=(
            not subtitle_supported
        )
    )


async def determine_strategy(
    media_info: dict,
    session_id: str
):

    return (

        await try_direct_play(
            media_info,
            session_id
        )

        or

        await try_remux(
            media_info,
            session_id
        )

        or

        await try_audio_transcode(
            media_info,
            session_id
        )

        or

        await try_video_transcode(
            media_info,
            session_id
        )

        or

        await try_full_transcode(
            media_info,
            session_id
        )
    )

