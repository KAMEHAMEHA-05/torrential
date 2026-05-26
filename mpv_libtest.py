import asyncio
import subprocess

from pprint import pprint

from torrent.session import TorrentSession
from torrent.manager import TorrentManager
from torrent.stream import TorrentReadStream

from media.media import analyze_stream


MAGNET = (
    "magnet:?xt=urn:btih:"
    "94e93e866a28302adce3e0a28038c4068734d8d6"
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
    # OPTIONAL:
    # analyze media
    #

    print(
        "\nAnalyzing media...\n"
    )

    media_info = await analyze_stream(
        stream
    )

    pprint(media_info)

    #
    # reset stream state
    #

    await stream.seek(0)

    #
    # monitor download speed
    #

    asyncio.create_task(

        monitor_download(
            stream
        )
    )

    #
    # wait for enough buffer
    #

    await wait_for_playable(
        stream
    )

    #
    # START MPV
    #

    print(
        "\nLaunching mpv...\n"
    )

    mpv = subprocess.Popen([

        "mpv",

        "--cache=yes",

        "--cache-secs=30",

        "--demuxer-max-bytes=512M",

        "--demuxer-readahead-secs=60",

        "--force-seekable=yes",

        "--hr-seek=yes",

        "--really-quiet",

        str(stream.file_path)
    ])

    #
    # keep torrent alive
    #

    while True:

        status = handle.status()

        #
        # print progress
        #

        print(

            f"[Torrent] "

            f"{status.progress * 100:.2f}% "

            f"peers={status.num_peers} "

            f"download="
            f"{status.download_rate / 1024 / 1024:.2f} MB/s"
        )

        #
        # exit if mpv closes
        #

        if mpv.poll() is not None:

            print(
                "\nmpv exited\n"
            )

            break

        await asyncio.sleep(2)

    #
    # cleanup
    #

    await stream.stop()

    print(
        "\nFinished"
    )


if __name__ == "__main__":

    asyncio.run(main())