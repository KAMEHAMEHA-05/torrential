def parse_frame_rate(rate):

    if not rate:
        return None

    try:

        num, den = rate.split("/")

        num = float(num)
        den = float(den)

        if den == 0:
            return None

        return num / den

    except:
        return None


def get_audio_tracks(streams):

    result = []

    for stream in streams:

        if stream.get("codec_type") != "audio":
            continue

        result.append({

            "codec":
                stream.get("codec_name"),

            "channels":
                stream.get("channels"),

            "language":
                (
                    stream
                    .get("tags", {})
                    .get("language")
                ),

            "title":
                (
                    stream
                    .get("tags", {})
                    .get("title")
                )
        })

    return result


def get_subtitle_tracks(streams):

    result = []

    for stream in streams:

        if stream.get("codec_type") != "subtitle":
            continue

        result.append({

            "codec":
                stream.get("codec_name"),

            "language":
                (
                    stream
                    .get("tags", {})
                    .get("language")
                ),

            "title":
                (
                    stream
                    .get("tags", {})
                    .get("title")
                )
        })

    return result


def parse_media_info(data):

    streams = data.get(
        "streams",
        []
    )

    video_stream = None

    for stream in streams:

        if (
            stream.get("codec_type")
            ==
            "video"
        ):

            video_stream = stream
            break

    format_names = (

        data
        .get("format", {})
        .get("format_name", "")
        .split(",")
    )

    container = (
        format_names[0].strip()
        if format_names
        else None
    )

    return {

        "container":
            container,

        "duration":

            float(
                data
                .get("format", {})
                .get("duration", 0)
            ),

        "video": {

            "codec":
                (
                    video_stream
                    .get("codec_name")
                    if video_stream
                    else None
                ),

            "profile":
                (
                    video_stream
                    .get("profile")
                    if video_stream
                    else None
                ),

            "pix_fmt":
                (
                    video_stream
                    .get("pix_fmt")
                    if video_stream
                    else None
                ),

            "width":
                (
                    video_stream
                    .get("width")
                    if video_stream
                    else None
                ),

            "height":
                (
                    video_stream
                    .get("height")
                    if video_stream
                    else None
                ),

            "fps":
                (
                    parse_frame_rate(
                        video_stream.get(
                            "r_frame_rate"
                        )
                    )
                    if video_stream
                    else None
                )
        },

        "audio":
            get_audio_tracks(streams),

        "subtitles":
            get_subtitle_tracks(streams)
    }