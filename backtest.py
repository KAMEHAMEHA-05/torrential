from pathlib import Path

import asyncio

from media.media import analyze_media

from playback.strategies import determine_strategy

from playback.hls import HLSSession


async def main():

    input_path = str(
        Path(
            "~/Downloads/sample-avi-files-sample_1920x1080.avi"
        ).expanduser()
    )

    media_info = await analyze_media(
        input_path
    )

    playback_session = await determine_strategy(
        media_info,
        "test-session-id2"
    )

    print(playback_session)

    hls_session = HLSSession(
        playback_session=playback_session,
        input_path=input_path
    )

    await hls_session.start()

    print("\nHLS session started.\n")

    print(
        "Playlist:",
        hls_session.output_dir / "master.m3u8"
    )

    #
    # Keep process alive
    #

    while hls_session.active:

        await asyncio.sleep(1)


asyncio.run(main())