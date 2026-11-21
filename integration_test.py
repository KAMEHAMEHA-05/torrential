import argparse
import asyncio
import time
from pathlib import Path

from torrent.session import TorrentSession
from torrent.manager import TorrentManager

from pipeline.main import Pipeline, SAVE_PATH

TERMINAL = ("completed", "failed", "cancelled")

# how much of a (non-HLS) video must be on disk before mpv opens it
MPV_START_BYTES = 64 * 1024 * 1024


def parse_args():

    p = argparse.ArgumentParser(
        description="Stream / download a torrent, optionally HLS + upload + mpv"
    )

    p.add_argument("magnet", help="magnet URI (quote it in your shell)")

    p.add_argument(
        "--hls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="HLS one video from the torrent (default: on; use --no-hls)",
    )

    p.add_argument(
        "--upload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="upload outputs (default: on; --no-upload just saves to --save-path)",
    )

    p.add_argument(
        "--video-id",
        type=int,
        default=None,
        help="file index of the video to use (default: largest video)",
    )

    p.add_argument(
        "--save-path",
        default=SAVE_PATH,
        help=f"where files are saved (default: {SAVE_PATH})",
    )

    p.add_argument(
        "--mpv",
        action="store_true",
        help="play the video in mpv while it is downloading (video torrents only)",
    )

    return p.parse_args()


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
            try:
                peers = handle.get_peer_info()
                print("Peers count from API:", len(peers))
                for p in peers[:10]:
                    print(" peer:", getattr(p, "ip", None), getattr(p, "client", None), getattr(p, "flags", None))
            except Exception as e:
                print("peer info read error:", e)

        try:
            alerts = session.session.pop_alerts()
            for a in alerts:
                print("ALERT:", type(a).__name__, str(a))
        except Exception:
            pass

        await asyncio.sleep(1)


#
# mpv helpers
#

async def wait_for_hls_playlist(pipeline, media_id, hls_dir):
    """
    Wait until ffmpeg has written a playlist with at least one segment.
    Returns the path to open (master playlist if there is one), or None if
    the pipeline ended first.
    """

    hls_dir = Path(hls_dir)

    while True:

        status = await pipeline.status(media_id)

        if not status or status["status"] in TERMINAL:
            return None

        playlists = []

        if hls_dir.exists():
            for pl in hls_dir.rglob("*.m3u8"):
                try:
                    playlists.append((pl, pl.read_text(errors="ignore")))
                except OSError:
                    pass

        if any("#EXTINF" in text for _, text in playlists):

            for pl, text in playlists:
                if "#EXT-X-STREAM-INF" in text:
                    return pl

            return next(pl for pl, text in playlists if "#EXTINF" in text)

        await asyncio.sleep(0.5)


async def wait_for_video_bytes(pipeline, media_id):
    """
    Wait until the start of the (non-HLS) video is on disk.
    Returns the file path, or None if the pipeline ended first.
    """

    while True:

        status = await pipeline.status(media_id)

        if not status:
            return None

        path = status.get("video_path")
        size = status.get("video_size", 0)
        got = status.get("video_downloaded", 0)

        if path and Path(path).exists() and got >= min(MPV_START_BYTES, size):
            return path

        if status["status"] in TERMINAL:
            return None

        await asyncio.sleep(1)


async def play_in_mpv(pipeline, media_id, state):
    """Background task: open mpv once there is something to play."""

    status = await pipeline.status(media_id)

    if status.get("hls_dir"):
        print("[MPV] waiting for HLS playlist...")
        target = await wait_for_hls_playlist(
            pipeline, media_id, status["hls_dir"]
        )

    else:
        print("[MPV] waiting for enough of the video to download...")
        target = await wait_for_video_bytes(pipeline, media_id)

    if target is None:
        print("[MPV] pipeline ended before playback could start")
        return

    print(f"[MPV] playing {target}")

    try:
        proc = await asyncio.create_subprocess_exec("mpv", str(target))
    except FileNotFoundError:
        print("[MPV] mpv not found on PATH, skipping playback")
        return

    state["proc"] = proc

    await proc.wait()

    print("[MPV] mpv exited (pipeline keeps running)")


async def main(args):
    print("MAIN STARTED")

    torrent_session = TorrentSession()

    await torrent_session.start()

    torrent_manager = TorrentManager(torrent_session)

    pipeline = Pipeline(torrent_session, torrent_manager)

    media_id = None
    mpv_task = None
    mpv_state = {}

    try:

        media_id = await pipeline.start(
            args.magnet,
            hls=args.hls,
            upload=args.upload,
            video_id=args.video_id,
            save_path=args.save_path,
            sequential=args.mpv,
        )

        print(f"\nMEDIA ID:\n{media_id}\n")

        #
        # mpv: only if asked for AND the torrent has a video
        #

        if args.mpv:

            status = await pipeline.status(media_id)

            if status and (status.get("hls_dir") or status.get("video_path")):
                mpv_task = asyncio.create_task(
                    play_in_mpv(pipeline, media_id, mpv_state)
                )
            else:
                print("[MPV] no video in this torrent, skipping playback")

        #
        # monitor status
        #

        while True:

            status = await pipeline.status(media_id)

            print("\nSTATUS:\n")
            print(status)

            if not status:
                break

            if status["status"] in TERMINAL:

                if status["status"] == "failed":
                    print(f"\nPipeline failed: {status['error']}")

                break

            await asyncio.sleep(5)

    finally:

        if mpv_task:
            mpv_task.cancel()
            try:
                await mpv_task
            except asyncio.CancelledError:
                pass

        proc = mpv_state.get("proc")

        if proc and proc.returncode is None:
            proc.terminate()

        if media_id:
            await pipeline.stop(media_id)

        await torrent_session.stop()


if __name__ == "__main__":

    print("Entering Asyncio Event Loop")
    asyncio.run(main(parse_args()))