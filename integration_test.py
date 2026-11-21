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

import time


# MAGNET = (
#     "magnet:?xt=urn:btih:94e93e866a28302adce3e0a28038c4068734d8d6"
# )

# MAGNET = (
#     "magnet:?xt=urn:btih:0f67fd75f3759d1eac7c03349031be0a3d4666c8&dn=Torrentio%0A1080p"
# )

MAGNET = (
    r"magnet:?xt=urn:btih:b0d4d04b968c29d8d8d3266e60a21c618eec675c&dn=Torrentio%0A1080p&tr=tracker%3Audp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.stealth.si%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.torrent.eu.org%3A451%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.demonii.com%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fopen.tracker.cl%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Fexodus.desync.com%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.qu.ax%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.ducks.party%3A1984%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.bittor.pw%3A1337%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.tryhackx.org%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.corpscorp.online%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.nyaa.vc%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker-udp.gbitt.info%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Fexplodie.org%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.gmi.gd%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.dler.org%3A6969%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker2.dler.org%3A80%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.dler.com%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.renfei.net%3A8080%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.peerfect.org%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Fnyaa.tracker.wf%3A7777%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Fanidex.moe%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ftracker.anirena.com%3A80%2Fannounce&tr=tracker%3Audp%3A%2F%2Ftracker.uw0.xyz%3A6969%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Fshare.camoe.cn%3A8080%2Fannounce&tr=tracker%3Ahttp%3A%2F%2Ft.nyaatracker.com%3A80%2Fannounce&tr=b0d4d04b968c29d8d8d3266e60a21c618eec675c")

async def diagnose(manager, info_hash, session, duration=60):
    handle = manager.get_handle(info_hash)
    start = time.time()
    while time.time() - start < duration:
        if not handle or not handle.is_valid():
            print("Handle not valid yet")
        else:
            st = handle.status()
            print("STATUS:", {
                "has_metadata": st.has_metadata,
                "progress": st.progress,
                "peers": st.num_peers,
                "download_rate": st.download_rate,
                "up_rate": st.upload_rate,
            })
            # peer info may be expensive; iterate if available
            try:
                peers = handle.get_peer_info()
                print("Peers count from API:", len(peers))
                for p in peers[:10]:
                    # p.ip, p.client, p.flags exist in libtorrent
                    print(" peer:", getattr(p, "ip", None), getattr(p, "client", None), getattr(p, "flags", None))
            except Exception as e:
                print("peer info read error:", e)

        # pull alerts from the session (session is TorrentSession.session)
        try:
            alerts = session.session.pop_alerts()
            for a in alerts:
                print("ALERT:", type(a).__name__, str(a))
        except Exception:
            pass

        await asyncio.sleep(1)

async def main():
    print("MAIN STARTED")

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

    