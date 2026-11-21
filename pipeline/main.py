import asyncio

from dataclasses import asdict
from pathlib import Path
from pprint import pprint
from typing import Optional

from torrent.session import TorrentSession
from torrent.manager import TorrentManager
from torrent.stream import TorrentReadStream

from media.cache import build_torrent_media_id
from media.resolver import resolve_playback_session

from playback.hls_stream import HLSStreamSession
from pipeline.producers import byte_stream_producer

from upload.manager import UploadManager

SAVE_PATH = "./downloads"

# how often to check whether non-HLS files have finished downloading
FILE_POLL_INTERVAL = 1.0


def _now():
    return asyncio.get_running_loop().time()


def _list_torrent_files(handle):
    """
    Every file in the torrent as {"index", "path", "size"}.
    `path` is relative to the save path.
    """

    files = handle.torrent_file().files()

    return [
        {
            "index": i,
            "path": files.file_path(i),
            "size": files.file_size(i),
        }
        for i in range(files.num_files())
    ]


async def monitor_download(stream):
    """Prints on-disk size and approximate speed once per second."""

    last_size = 0

    while True:

        try:
            size = stream.file_path.stat().st_size
        except OSError:
            await asyncio.sleep(1)
            continue

        mbps = (size - last_size) / 1024 / 1024
        last_size = size

        print(
            f"[Torrent] downloaded={size / 1024 / 1024:.2f} MB "
            f"speed={mbps:.2f} MB/s"
        )

        await asyncio.sleep(1)


class Pipeline:
    """
    Manages pipelines for torrent-based media.

    Per torrent, `start()` takes three options:

      hls       - HLS-transcode ONE video from the torrent while it downloads.
                  The other files (non-videos, and any other videos) are
                  downloaded normally. If the torrent has no video, this is
                  ignored.
      upload    - upload the output. HLS segments are uploaded as they appear,
                  plain files are uploaded once they finish downloading.
                  If False, everything is just saved under save_path.
      video_id  - file index of the video to HLS (and to report as the
                  playable video in status()). Defaults to the largest.

    Resulting modes:

      hls=True,  upload=True   stream video -> HLS -> upload; other files -> upload
      hls=True,  upload=False  stream video -> HLS (left in /tmp/hls/<id>);
                               other files saved
      hls=False, upload=True   download everything fully, upload each file
      hls=False, upload=False  download everything to save_path, nothing else

    Registry key (the returned id):
      - HLS runs use the video's media_id (so /tmp/hls/<id> stays the same)
      - non-HLS runs use the torrent's info_hash
    """

    def __init__(
        self,
        torrent_session,
        torrent_manager,
        cleanup_retention_seconds=3600,
    ):
        self.torrent_session = torrent_session
        self.torrent_manager = torrent_manager
        self.cleanup_retention_seconds = cleanup_retention_seconds

        self._active_pipelines = {}

    # ------------------------------------------------------------------
    # registry housekeeping
    # ------------------------------------------------------------------

    async def _cleanup_old_pipelines(self):
        """Drop finished pipelines older than cleanup_retention_seconds."""

        now = _now()

        expired = [
            pid
            for pid, p in self._active_pipelines.items()
            if p.get("finished_at")
            and now - p["finished_at"] > self.cleanup_retention_seconds
        ]

        for pid in expired:
            self._active_pipelines.pop(pid, None)
            print(f"[PIPELINE] removed {pid} from registry")

    async def _cleanup_pipeline(self, pipeline_id):
        """
        Releases every resource a pipeline holds. Each step is isolated so
        one failure doesn't block the rest. Idempotent.
        """

        pipeline = self._active_pipelines.get(pipeline_id)

        if not pipeline or pipeline.get("cleaned"):
            return

        pipeline["cleaned"] = True

        async def stop_task(name):
            task = pipeline.get(name)
            if not task:
                return
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[CLEANUP] {name}: {e}")

        # uploader
        try:
            if pipeline.get("upload_manager"):
                await pipeline["upload_manager"].stop(pipeline_id)
        except Exception as e:
            print(f"[CLEANUP] uploader: {e}")

        await stop_task("monitor_task")
        await stop_task("producer_task")

        # hls
        try:
            if pipeline.get("hls"):
                await pipeline["hls"].stop()
        except Exception as e:
            print(f"[CLEANUP] hls: {e}")

        # torrent stream
        try:
            if pipeline.get("stream"):
                await pipeline["stream"].stop()
        except Exception as e:
            print(f"[CLEANUP] stream: {e}")

        # torrent release
        try:
            if pipeline.get("info_hash"):
                self.torrent_manager.release_torrent(pipeline["info_hash"])
        except Exception as e:
            print(f"[CLEANUP] torrent: {e}")

        pipeline["finished_at"] = _now()

        print(f"[PIPELINE] cleaned {pipeline_id}")

    # ------------------------------------------------------------------
    # planning
    # ------------------------------------------------------------------

    def _build_plan(self, info_hash, handle, hls, video_id):
        """
        Decide what gets HLS'd and what is handled as a plain file.

        Returns (hls_video | None, plain_files, target_video | None).

        target_video is the video picked by video_id (or the largest); it is
        what a player should play, whether or not it is HLS'd.
        """

        all_files = _list_torrent_files(handle)

        videos = self.torrent_manager.list_video_files(info_hash)
        videos_by_index = {v["index"]: v for v in videos}

        # the video we care about: explicit video_id, else the largest
        target_video = None

        if video_id is not None:

            if video_id not in videos_by_index:
                raise ValueError(
                    f"video_id {video_id} is not a video file in this "
                    f"torrent (video indexes: {sorted(videos_by_index)})"
                )

            target_video = videos_by_index[video_id]

        elif videos:
            target_video = max(videos, key=lambda v: v["size"])

        # only HLS it if asked to
        hls_video = target_video if hls else None

        plain_files = [
            f for f in all_files
            if hls_video is None or f["index"] != hls_video["index"]
        ]

        return hls_video, plain_files, target_video

    @staticmethod
    def _apply_priorities(handle, hls_video, plain_files):
        """
        While streaming, the HLS video gets top priority so the rest of the
        torrent doesn't compete with it for bandwidth.
        """

        if not hls_video:
            return

        for f in plain_files:
            handle.file_priority(f["index"], 1)

        handle.file_priority(hls_video["index"], 7)

    # ------------------------------------------------------------------
    # the two jobs a pipeline can run
    # ------------------------------------------------------------------

    async def _run_hls(self, pipeline_id, handle, video):
        """Stream one video through ffmpeg -> HLS (optionally uploading)."""

        pipeline = self._active_pipelines[pipeline_id]
        upload_manager = pipeline["upload_manager"]

        print("\nSelected video:\n")
        pprint(video)

        stream = TorrentReadStream(
            handle=handle,
            torrent_file=video,
            save_path=pipeline["save_path"],
            buffer_window=256,
        )
        pipeline["stream"] = stream

        print("\nStarting stream...")
        await stream.start()
        await stream.bootstrap()

        print("\nResolving playback session...\n")
        playback = await resolve_playback_session(
            media_id=pipeline_id,
            session_id="test_session",
            read_stream=stream,
        )
        pipeline["playback"] = playback

        print("\nPlayback Session:\n")
        pprint(asdict(playback))

        # probing consumed some bytes, start from the top again
        await stream.seek(0)

        byte_queue = asyncio.Queue(maxsize=1024)

        # torrent media id doubles as session id
        playback.session_id = pipeline_id

        print("\nStarting HLS engine...\n")
        hls = HLSStreamSession(
            playback_session=playback,
            byte_queue=byte_queue,
        )
        pipeline["hls"] = hls
        await hls.start()

        if upload_manager:
            # watches the HLS output dir and ships segments
            await upload_manager.start(pipeline_id)

        print(f"\nHLS output directory:\n/tmp/hls/{pipeline_id}\n")

        print("\nStarting byte producer...\n")
        pipeline["producer_task"] = asyncio.create_task(
            byte_stream_producer(stream, byte_queue)
        )
        pipeline["monitor_task"] = asyncio.create_task(
            monitor_download(stream)
        )

        while hls.active:

            s = handle.status()

            print(
                f"[Torrent] {s.progress * 100:.2f}% "
                f"peers={s.num_peers} "
                f"download={s.download_rate / 1024 / 1024:.2f} MB/s"
            )

            await asyncio.sleep(2)

        print("\nHLS session ended\n")

    async def _run_files(self, pipeline_id, handle, files):
        """
        Wait for plain files to finish downloading, uploading each one as
        it completes (if upload is on). Files stay in save_path either way.
        """

        pipeline = self._active_pipelines[pipeline_id]
        upload_manager = pipeline["upload_manager"]
        save_path = Path(pipeline["save_path"])

        pending = {f["index"]: f for f in files}

        while pending:

            progress = handle.file_progress()

            for index in list(pending):

                f = pending[index]

                if progress[index] < f["size"]:
                    continue

                del pending[index]

                local_path = save_path / f["path"]

                print(f"[FILES] complete: {f['path']}")

                if upload_manager:
                    await upload_manager.upload_file(
                        pipeline_id,
                        local_path,
                        f["path"],
                    )
                    print(f"[FILES] uploaded: {f['path']}")

                pipeline["files_done"] += 1

            if pending:
                await asyncio.sleep(FILE_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # orchestration
    # ------------------------------------------------------------------

    async def run_pipeline(self, pipeline_id):
        """
        Background task: runs the HLS job and/or the plain-files job
        concurrently, then cleans up.
        """

        try:

            pipeline = self._active_pipelines[pipeline_id]

            handle = self.torrent_manager.get_handle(pipeline["info_hash"])
            pipeline["handle"] = handle

            hls_video = pipeline["hls_video"]
            plain_files = pipeline["plain_files"]

            self._apply_priorities(handle, hls_video, plain_files)

            play_video = pipeline["play_video"]

            if pipeline["sequential"] and not hls_video and play_video:
                handle.set_sequential_download(True)

                for f in plain_files:
                    prio = 7 if f["index"] == play_video["index"] else 1
                    handle.file_priority(f["index"], prio)

            if pipeline["upload"]:
                pipeline["upload_manager"] = UploadManager()

            jobs = []

            if hls_video:
                jobs.append(self._run_hls(pipeline_id, handle, hls_video))

            if plain_files:
                jobs.append(self._run_files(pipeline_id, handle, plain_files))

            pipeline["status"] = "running"

            tasks = [asyncio.create_task(j) for j in jobs]

            try:
                # first failure wins; otherwise wait for every job
                done, _ = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_EXCEPTION,
                )
                for t in done:
                    t.result()

            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            pipeline["status"] = "completed"

            await self._cleanup_pipeline(pipeline_id)

        except asyncio.CancelledError:

            pipeline = self._active_pipelines.get(pipeline_id)

            if pipeline:
                pipeline["status"] = "cancelled"

            print(f"[PIPELINE] {pipeline_id} cancelled")

            await self._cleanup_pipeline(pipeline_id)

        except Exception as e:

            print(f"\nPipeline error for {pipeline_id}: {e}\n")

            pipeline = self._active_pipelines.get(pipeline_id)

            if pipeline:
                pipeline["status"] = "failed"
                pipeline["error"] = str(e)

            await self._cleanup_pipeline(pipeline_id)

    async def start(
        self,
        magnet: str,
        hls: bool = True,
        upload: bool = True,
        video_id: Optional[int] = None,
        save_path: str = SAVE_PATH,
        sequential: bool = False,
    ):
        """
        Start a pipeline for a magnet. Returns the pipeline id immediately
        (after metadata is fetched).

        Args:
            magnet:    magnet URI
            hls:       HLS one video from the torrent (see class docstring)
            upload:    upload outputs; if False, just save under save_path
            video_id:  file index of the video to HLS (default: largest video)
            save_path: where the torrent's files are saved
            sequential: only used when NOT doing HLS: download in order and
                       prioritise the target video so it can be played from
                       disk while it downloads (e.g. mpv)

        Raises:
            ValueError: bad video_id / no video files for a given video_id
        """

        await self._cleanup_old_pipelines()

        info_hash = self.torrent_manager.add_magnet(magnet, save_path)
        print(f"Added torrent: {info_hash}")

        print("Waiting for metadata...")
        await self.torrent_manager.wait_for_metadata(info_hash)
        print("Metadata ready")

        handle = self.torrent_manager.get_handle(info_hash)

        try:
            hls_video, plain_files, target_video = self._build_plan(
                info_hash, handle, hls, video_id
            )
        except Exception:
            # don't leave a torrent running for a request we're rejecting
            self.torrent_manager.release_torrent(info_hash)
            raise

        if hls_video:
            pipeline_id = build_torrent_media_id(
                info_hash=info_hash,
                file_index=hls_video["index"],
                size=hls_video["size"],
            )
        else:
            pipeline_id = info_hash

        print(f"\nPipeline ID: {pipeline_id}\n")

        # same job already running -> hand back the existing one
        existing = self._active_pipelines.get(pipeline_id)

        if existing and existing["status"] in ("starting", "running"):
            return pipeline_id

        if hls_video:
            print("Warming swarm...")
            await asyncio.sleep(3)

        # register before the task exists, with a consistent shape
        self._active_pipelines[pipeline_id] = {
            "status": "starting",
            "mode": "hls" if hls_video else "direct",
            "magnet": magnet,
            "info_hash": info_hash,
            "save_path": save_path,
            "upload": upload,
            "hls_video": hls_video,
            "plain_files": plain_files,
            "play_video": target_video,
            "sequential": sequential,
            "files_total": len(plain_files),
            "files_done": 0,
            "created_at": _now(),
            "cleaned": False,
            "error": None,
            "finished_at": None,
            "pipeline_task": None,
            "handle": None,
            "stream": None,
            "hls": None,
            "upload_manager": None,
            "producer_task": None,
            "monitor_task": None,
            "playback": None,
        }

        self._active_pipelines[pipeline_id]["pipeline_task"] = (
            asyncio.create_task(self.run_pipeline(pipeline_id))
        )

        return pipeline_id

    async def stop(self, pipeline_id):
        """
        Cancel a pipeline, clean up, and remove it from the registry.
        Returns True if stopped, False if not found.
        """

        pipeline = self._active_pipelines.get(pipeline_id)

        if not pipeline:
            return False

        task = pipeline.get("pipeline_task")

        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._cleanup_pipeline(pipeline_id)

        self._active_pipelines.pop(pipeline_id, None)

        return True

    async def status(self, pipeline_id):
        """Status dict for a pipeline, or None if not found."""

        pipeline = self._active_pipelines.get(pipeline_id)

        if not pipeline:
            return None

        info = {
            "media_id": pipeline_id,
            "mode": pipeline["mode"],
            "magnet": pipeline["magnet"],
            "info_hash": pipeline["info_hash"],
            "status": pipeline["status"],
            "upload": pipeline["upload"],
            "save_path": pipeline["save_path"],
            "hls_file_index": (
                pipeline["hls_video"]["index"]
                if pipeline["hls_video"] else None
            ),
            "files_total": pipeline["files_total"],
            "files_done": pipeline["files_done"],
            "created_at": pipeline["created_at"],
            "finished_at": pipeline["finished_at"],
            "error": pipeline["error"],
        }

        handle = pipeline.get("handle")

        if handle:
            try:
                s = handle.status()
                info["progress"] = s.progress * 100
                info["download_rate"] = s.download_rate / 1024 / 1024
                info["num_peers"] = s.num_peers
            except Exception:
                pass

        stream = pipeline.get("stream")

        if stream:
            try:
                info["downloaded_size"] = (
                    stream.file_path.stat().st_size / 1024 / 1024
                )
            except OSError:
                pass

        if pipeline["hls_video"]:
            info["hls_dir"] = f"/tmp/hls/{pipeline_id}"

        video = pipeline["play_video"]

        if video:
            info["video_path"] = str(
                Path(pipeline["save_path"]) / video["path"]
            )
            info["video_size"] = video["size"]

            if handle:
                try:
                    info["video_downloaded"] = (
                        handle.file_progress()[video["index"]]
                    )
                except Exception:
                    pass

        playback = pipeline.get("playback")

        if playback:
            info["duration"] = getattr(playback, "total_duration", None)

        hls = pipeline.get("hls")

        if hls:
            info["hls_active"] = hls.active

        return info

    async def list_active(self):

        return {
            pid: {
                "status": p["status"],
                "mode": p["mode"],
                "created_at": p["created_at"],
            }
            for pid, p in self._active_pipelines.items()
        }