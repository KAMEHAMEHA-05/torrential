from dataclasses import asdict

from media.cache import cache

from media.media import (
    analyze_media,
    analyze_stream
)

from playback.strategies import (
    determine_strategy,
    PlaybackSession
)


async def resolve_playback_session(

    *,
    media_id,
    session_id,

    file_path=None,
    read_stream=None
):

    #
    # cache hit
    #

    cached = cache.get(
        media_id
    )

    if cached:

        media_info = (
            cached["media_info"]
        )

        strategy = (
            cached["strategy"]
        )

        #
        # strategy cache hit
        #

        if strategy:

            playback = PlaybackSession(
                **strategy
            )

            #
            # session_id changes
            #

            playback.session_id = (
                session_id
            )

            return playback

    #
    # analyze
    #

    if file_path:

        media_info = (
            await analyze_media(
                file_path
            )
        )

    else:

        media_info = (
            await analyze_stream(
                read_stream
            )
        )

    #
    # determine playback strategy
    #

    playback = (
        await determine_strategy(

            media_info,

            session_id
        )
    )

    #
    # persist
    #

    cache.set(

        media_id,

        media_info,

        asdict(playback)
    )

    return playback