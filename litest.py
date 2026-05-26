import asyncio

from pprint import pprint

from torrent.session import TorrentSession
from torrent.manager import TorrentManager
from torrent.stream import TorrentReadStream

from media.media import analyze_stream


MAGNET = "magnet:?xt=urn:btih:94e93e866a28302adce3e0a28038c4068734d8d6"

SAVE_PATH = "./downloads"

OUTPUT = "output.mp4"


QUEUE_SIZE = 64


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

    print("Warming swarm...")

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

    print("\nSelected video:")

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

        buffer_window=32
    )

    print(
        "\nStarting stream..."
    )

    await stream.start()

    #
    # ANALYZE STREAM
    #

    print(
        "\nAnalyzing media stream...\n"
    )

    await stream.bootstrap()

    media_info = await analyze_stream(
        stream
    )

    pprint(media_info)

    #
    # RESET STREAM
    #

    await stream.seek(0)

    #
    # START FFMPEG
    #

    ffmpeg = (
        await asyncio.create_subprocess_exec(

            "ffmpeg",

            "-y",

            #
            # LOW LATENCY
            #

            "-fflags",
            "nobuffer",

            "-flags",
            "low_delay",

            "-probesize",
            "256k",

            "-analyzeduration",
            "0",

            #
            # INPUT
            #

            "-i",
            "pipe:0",

            #
            # REMUX
            #

            "-c:v",
            "copy",

            "-c:a",
            "copy",

            #
            # TIMESTAMPS
            #

            "-copyts",

            "-start_at_zero",

            #
            # FAST FRAGMENTED MP4
            #

            "-movflags",

            (
                "+frag_keyframe"
                "+separate_moof"
                "+omit_tfhd_offset"
                "+empty_moov"
            ),

            #
            # OUTPUT
            #

            OUTPUT,

            stdin=asyncio.subprocess.PIPE,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )
    )

    #
    # LOG FFMPEG
    #

    async def log_ffmpeg():

        while True:

            chunk = (
                await ffmpeg.stderr.read(
                    4096
                )
            )

            if not chunk:
                break

            print(

                "[FFmpeg]",

                chunk.decode(
                    errors="ignore"
                ),

                end=""
            )

    asyncio.create_task(
        log_ffmpeg()
    )

    #
    # PRODUCER / CONSUMER
    #

    queue = asyncio.Queue(
        maxsize=QUEUE_SIZE
    )

    #
    # PRODUCER
    #

    async def producer():

        while True:

            chunk = await stream.read()

            if not chunk:
                break

            await queue.put(
                chunk
            )

        await queue.put(None)

    #
    # CONSUMER
    #

    async def consumer():

        transported = 0

        while True:

            chunk = await queue.get()

            if chunk is None:
                break

            transported += len(
                chunk
            )

            print(
                f"Transported: {transported}"
            )

            ffmpeg.stdin.write(
                chunk
            )

            await ffmpeg.stdin.drain()

        ffmpeg.stdin.close()

    #
    # RUN PIPELINE
    #

    await asyncio.gather(

        producer(),

        consumer()
    )

    #
    # FINALIZE
    #

    await ffmpeg.wait()

    await stream.stop()

    print("\nFinished")

    print(
        f"\nOutput: {OUTPUT}"
    )


if __name__ == "__main__":

    asyncio.run(main())