import asyncio

from dataclasses import asdict
from pprint import pprint

from torrent.session import TorrentSession
from torrent.manager import TorrentManager
from torrent.stream import TorrentReadStream

from media.cache import build_torrent_media_id
from media.resolver import resolve_playback_session

from playback.hls_stream import HLSStreamSession
from pipeline.producers import byte_stream_producer

MAGNET = (
    "magnet:?xt=urn:btih:323b224fb72bd287887058408f02102958d03ac6"
)

SAVE_PATH = "./downloads"

#
# how much data we want before playback
#

START_THRESHOLD = (
    64 * 1024 * 1024
)

#
# how often to check
#

CHECK_INTERVAL = 0.25


async def wait_for_playable(
    stream
):

    print(
        "\nWaiting for playable buffer...\n"
    )

    while True:

        if not stream.file_path.exists():

            await asyncio.sleep(
                CHECK_INTERVAL
            )

            continue

        try:

            size = (
                stream.file_path
                .stat()
                .st_size
            )

        except:

            await asyncio.sleep(
                CHECK_INTERVAL
            )

            continue

        downloaded_mb = (
            size / 1024 / 1024
        )

        print(
            f"Buffered: "
            f"{downloaded_mb:.2f} MB"
        )

        if size >= START_THRESHOLD:

            print(
                "\nEnough buffer "
                "for playback\n"
            )

            return

        await asyncio.sleep(
            CHECK_INTERVAL
        )


async def monitor_download(
    stream
):

    last_size = 0

    while True:

        try:

            size = (
                stream.file_path
                .stat()
                .st_size
            )

        except:

            await asyncio.sleep(1)

            continue

        delta = size - last_size

        last_size = size

        mbps = (
            delta / 1024 / 1024
        )

        total_mb = (
            size / 1024 / 1024
        )

        print(

            f"[Torrent] "

            f"downloaded="
            f"{total_mb:.2f} MB "

            f"speed="
            f"{mbps:.2f} MB/s"
        )

        await asyncio.sleep(1)


async def main():

    #
    # TORRENT ENGINE
    #

    torrent_session = TorrentSession()

    await torrent_session.start()

    manager = TorrentManager(
        torrent_session
    )

    info_hash = manager.add_magnet(
        MAGNET,
        SAVE_PATH
    )

    print(
        f"Added torrent: {info_hash}"
    )

    #
    # WAIT FOR METADATA
    #

    print(
        "Waiting for metadata..."
    )

    await manager.wait_for_metadata(
        info_hash
    )

    print(
        "Metadata ready"
    )

    #
    # WARM SWARM
    #

    print(
        "Warming swarm..."
    )

    await asyncio.sleep(3)

    #
    # GET VIDEO FILE
    #

    files = manager.list_video_files(
        info_hash
    )

    if not files:

        raise Exception(
            "No video files found"
        )

    video = files[0]

    print(
        "\nSelected video:\n"
    )

    pprint(video)

    #
    # CREATE STREAM
    #

    handle = manager.get_handle(
        info_hash
    )

    stream = TorrentReadStream(

        handle=handle,

        torrent_file=video,

        save_path=SAVE_PATH,

        buffer_window=256
    )

    print(
        "\nStarting stream..."
    )

    await stream.start()

    #
    # AGGRESSIVE BOOTSTRAP
    #

    await stream.bootstrap()

    #
    # BUILD MEDIA ID
    #

    media_id = build_torrent_media_id(

        info_hash=info_hash,

        file_index=video["index"],

        size=video["size"]
    )

    print(
        f"\nMedia ID: {media_id}\n"
    )

    #
    # RESOLVE PLAYBACK SESSION
    #

    print(
        "\nResolving playback session...\n"
    )

    playback = await resolve_playback_session(

        media_id=media_id,

        session_id="test_session",

        read_stream=stream
    )

    #
    # PRINT RESULT
    #

    print(
        "\nPlayback Session:\n"
    )

    pprint(
        asdict(playback)
    )

    #
    # reset stream state
    #

    await stream.seek(0)

    #
    # session queue
    #

    byte_queue = asyncio.Queue(
        maxsize=128
    )

    #
    # use torrent hash as session id
    #

    playback.session_id = (
        info_hash
    )

    #
    # START HLS ENGINE
    #

    print(
        "\nStarting HLS engine...\n"
    )

    hls = HLSStreamSession(

        playback_session=playback,

        byte_queue=byte_queue
    )

    await hls.start()

    print(

        "\nHLS output directory:\n"

        f"/tmp/hls/{info_hash}\n"
    )

    #
    # START PRODUCER
    #

    print(
        "\nStarting byte producer...\n"
    )

    producer_task = asyncio.create_task(

        byte_stream_producer(

            stream,

            byte_queue
        )
    )

    #
    # monitor torrent
    #

    asyncio.create_task(

        monitor_download(
            stream
        )
    )

    #
    # keep process alive
    #

    while True:

        status = handle.status()

        print(

            f"[Torrent] "

            f"{status.progress * 100:.2f}% "

            f"peers={status.num_peers} "

            f"download="
            f"{status.download_rate / 1024 / 1024:.2f} MB/s"
        )

        #
        # ffmpeg exited
        #

        if not hls.active:

            print(
                "\nHLS session ended\n"
            )

            break

        await asyncio.sleep(2)

    #
    # cleanup
    #

    await hls.stop()

    await stream.stop()

    producer_task.cancel()

    print(
        "\nFinished"
    )

    manager.release_torrent(
        info_hash
    )


if __name__ == "__main__":

    asyncio.run(main())