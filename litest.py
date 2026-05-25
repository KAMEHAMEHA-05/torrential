import asyncio

from torrent.session import TorrentSession
from torrent.manager import TorrentManager
from torrent.stream import TorrentReadStream


MAGNET = "magnet:?xt=urn:btih:a56d60701384fd01b2efcbf6fa0606db330db66f&dn=Origem%20S01%202022%20WEB-DL%201080p%20x264%20DUAL%202.0&xl=18517830969"

SAVE_PATH = "./downloads"

OUTPUT = "output.mp4"


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

    print(f"Added torrent: {info_hash}")

    #
    # WAIT FOR METADATA
    #

    print("Waiting for metadata...")

    await manager.wait_for_metadata(
        info_hash
    )

    print("Metadata ready")

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
    print(video)

    #
    # CREATE TRANSPORT STREAM
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

    print("\nStarting stream...")

    await stream.start()

    #
    # START FFMPEG
    #

    ffmpeg = (
        await asyncio.create_subprocess_exec(

            "ffmpeg",

            "-y",

            "-i", "pipe:0",

            "-c:v", "libx264",

            "-c:a", "aac",

            "-movflags",
            "frag_keyframe+empty_moov",

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

            chunk = await ffmpeg.stderr.read(4096)

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
    # PIPE STREAM → FFMPEG
    #

    total = 0

    while True:

        chunk = await stream.read()

        if not chunk:
            break

        total += len(chunk)

        print(
            f"Transported: {total}"
        )

        ffmpeg.stdin.write(chunk)

        await ffmpeg.stdin.drain()

    #
    # FINALIZE
    #

    ffmpeg.stdin.close()

    await ffmpeg.wait()

    await stream.stop()

    print("\nFinished")

    print(f"\nOutput: {OUTPUT}")


if __name__ == "__main__":

    asyncio.run(main())