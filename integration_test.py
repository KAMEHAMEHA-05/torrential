import asyncio

from torrent.session import (
    TorrentSession
)

from torrent.manager import (
    TorrentManager
)

from pipeline.main import (
    Pipeline
)


# MAGNET = (
#     "magnet:?xt=urn:btih:94e93e866a28302adce3e0a28038c4068734d8d6"
# )

MAGNET = (
    "magnet:?xt=urn:btih:0f67fd75f3759d1eac7c03349031be0a3d4666c8&dn=Torrentio%0A1080p"
)


async def main():
    print("MAIN STARTED")
    #
    # shared torrent engine
    #

    torrent_session = (
        TorrentSession()
    )

    await torrent_session.start()

    torrent_manager = (
        TorrentManager(
            torrent_session
        )
    )

    pipeline = Pipeline(

        torrent_session,

        torrent_manager
    )

    try:

        #
        # start stream
        #

        media_id = await (
            pipeline.start(
                MAGNET
            )
        )

        print(
            f"\nMEDIA ID:"
            f"\n{media_id}\n"
        )

        #
        # monitor status
        #

        while True:

            status = await (
                pipeline.status(
                    media_id
                )
            )

            print(
                "\nSTATUS:\n"
            )

            print(status)

            if not status:
                break

            if status[
                "status"
            ] in (

                "completed",

                "failed",

                "cancelled"
            ):
                break

            await asyncio.sleep(5)

    finally:

        #
        # stop pipeline if alive
        #

        await pipeline.stop(
            media_id
        )

        await torrent_session.stop()


if __name__ == "__main__":

    print("Entering Asyncio Event Loop")
    asyncio.run(main())