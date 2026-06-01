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

from upload.manager import UploadManager

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


class Pipeline:
    """
    Manages streaming pipelines for torrent-based media.
    Takes a TorrentSession and TorrentManager to avoid reinitializing them
    for each pipeline.
    """

    def __init__(
        self,
        torrent_session,
        torrent_manager,
        cleanup_retention_seconds=3600
    ):
        """
        Initialize the Pipeline manager.

        Args:
            torrent_session (TorrentSession): Shared torrent session
            torrent_manager (TorrentManager): Shared torrent manager
            cleanup_retention_seconds (int): How long to keep finished pipelines in registry (default: 1 hour)
        """

        self.torrent_session = (
            torrent_session
        )

        self.torrent_manager = (
            torrent_manager
        )

        self.cleanup_retention_seconds = (
            cleanup_retention_seconds
        )

        #
        # Track active pipelines by media_id
        #

        self._active_pipelines = {}

    async def _cleanup_old_pipelines(self):
        """
        Removes pipelines from registry that have been finished
        longer than cleanup_retention_seconds.
        """

        now = asyncio.get_event_loop().time()

        media_ids_to_remove = []

        for media_id, pipeline in (
            self._active_pipelines.items()
        ):

            finished_at = (
                pipeline.get(
                    "finished_at"
                )
            )

            if not finished_at:
                continue

            age = now - finished_at

            if (
                age >
                self.cleanup_retention_seconds
            ):

                media_ids_to_remove.append(
                    media_id
                )

        for media_id in media_ids_to_remove:

            self._active_pipelines.pop(
                media_id,
                None
            )

            print(
                f"[PIPELINE] "
                f"removed {media_id} "
                f"from registry"
            )

    async def _cleanup_pipeline(
        self,
        media_id
    ):
        """
        Cleans up all resources associated with a pipeline.
        Handles exceptions gracefully for each component.
        Idempotent: safe to call multiple times.
        """

        pipeline = (
            self._active_pipelines.get(
                media_id
            )
        )

        if not pipeline:
            return

        #
        # Already cleaned?
        #

        if pipeline.get("cleaned"):
            return

        pipeline["cleaned"] = True

        monitor_task = (
            pipeline.get(
                "monitor_task"
            )
        )

        producer_task = (
            pipeline.get(
                "producer_task"
            )
        )

        stream = (
            pipeline.get(
                "stream"
            )
        )

        hls = (
            pipeline.get(
                "hls"
            )
        )

        upload_manager = (
            pipeline.get(
                "upload_manager"
            )
        )

        info_hash = (
            pipeline.get(
                "info_hash"
            )
        )

        #
        # uploader
        #

        try:

            if upload_manager:

                await upload_manager.stop(
                    media_id
                )

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"uploader: {e}"
            )

        #
        # monitor task
        #

        try:

            if monitor_task:

                monitor_task.cancel()

                await monitor_task

        except asyncio.CancelledError:

            pass

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"monitor: {e}"
            )

        #
        # producer task
        #

        try:

            if producer_task:

                producer_task.cancel()

                await producer_task

        except asyncio.CancelledError:

            pass

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"producer: {e}"
            )

        #
        # hls
        #

        try:

            if hls:

                await hls.stop()

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"hls: {e}"
            )

        #
        # torrent stream
        #

        try:

            if stream:

                await stream.stop()

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"stream: {e}"
            )

        #
        # torrent release
        #

        try:

            if info_hash:

                self.torrent_manager.release_torrent(
                    info_hash
                )

        except Exception as e:

            print(
                f"[CLEANUP] "
                f"torrent: {e}"
            )

        #
        # Record finish time
        #

        pipeline["finished_at"] = (
            asyncio.get_event_loop().time()
        )

        print(
            f"[PIPELINE] "
            f"cleaned {media_id}"
        )

    async def run_pipeline(
        self,
        magnet,
        media_id
    ):
        """
        Runs the entire streaming pipeline for a given magnet and media_id.
        This is executed as a background task.
        Updates the registry entry created in start().
        """

        try:

            #
            # GET VIDEO FILE
            #

            info_hash = (
                self.torrent_manager
                .get_info_hash(magnet)
            )

            files = (
                self.torrent_manager
                .list_video_files(
                    info_hash
                )
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

            handle = (
                self.torrent_manager
                .get_handle(info_hash)
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
            # RESOLVE PLAYBACK SESSION
            #

            print(
                "\nResolving playback session...\n"
            )

            playback = (
                await resolve_playback_session(

                    media_id=media_id,

                    session_id="test_session",

                    read_stream=stream
                )
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
                media_id
            )

            upload_manager = UploadManager()

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

            await upload_manager.start(
                media_id
            )

            print(

                "\nHLS output directory:\n"

                f"/tmp/hls/{media_id}\n"
            )

            #
            # START PRODUCER
            #

            print(
                "\nStarting byte producer...\n"
            )

            producer_task = (
                asyncio.create_task(

                    byte_stream_producer(

                        stream,

                        byte_queue
                    )
                )
            )

            #
            # monitor torrent
            #

            monitor_task = asyncio.create_task(
                monitor_download(stream)
            )

            #
            # Update registry with
            # runtime resources
            #

            self._active_pipelines[media_id].update({
                "info_hash": info_hash,
                "handle": handle,
                "stream": stream,
                "hls": hls,
                "upload_manager": upload_manager,
                "producer_task": producer_task,
                "playback": playback,
                "status": "running",
                "monitor_task": monitor_task,
            })

            #
            # keep process alive
            #

            while True:

                torrent_status = (
                    handle.status()
                )

                print(

                    f"[Torrent] "

                    f"{torrent_status.progress * 100:.2f}% "

                    f"peers={torrent_status.num_peers} "

                    f"download="
                    f"{torrent_status.download_rate / 1024 / 1024:.2f} MB/s"
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

            pipeline = (
                self._active_pipelines.get(
                    media_id
                )
            )

            if pipeline:

                pipeline["status"] = "completed"

            await self._cleanup_pipeline(
                media_id
            )

        except asyncio.CancelledError:

            #
            # Safe access in case
            # stop() removed it
            #

            pipeline = (
                self._active_pipelines.get(
                    media_id
                )
            )

            if pipeline:

                pipeline["status"] = "cancelled"

            print(
                f"[PIPELINE] "
                f"{media_id} cancelled"
            )

            await self._cleanup_pipeline(
                media_id
            )

        except Exception as e:

            print(
                f"\nPipeline error for {media_id}: {e}\n"
            )

            pipeline = (
                self._active_pipelines.get(
                    media_id
                )
            )

            if pipeline:

                pipeline["status"] = "failed"

                pipeline["error"] = str(e)

            await self._cleanup_pipeline(
                media_id
            )

    async def start(self, magnet):
        """
        Starts a new streaming pipeline for the given magnet URI.
        
        Registers the pipeline immediately, then creates a background task.
        Returns immediately with the media_id.
        Runs garbage collection on old finished pipelines.
        
        Args:
            magnet (str): The magnet URI for the torrent
            
        Returns:
            str: The media_id for tracking this streaming session
        """

        #
        # Garbage collect old pipelines
        #

        await self._cleanup_old_pipelines()

        #
        # ADD MAGNET
        #

        info_hash = (
            self.torrent_manager
            .add_magnet(magnet, SAVE_PATH)
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

        await self.torrent_manager.wait_for_metadata(
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
        # GET VIDEO FILE to build media_id
        #

        files = (
            self.torrent_manager
            .list_video_files(info_hash)
        )

        if not files:

            raise Exception(
                "No video files found"
            )

        video = files[0]

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
        # REGISTER IMMEDIATELY
        # (before creating task)
        # with consistent shape
        #

        self._active_pipelines[media_id] = {
            "status": "starting",
            "magnet": magnet,
            "info_hash": info_hash,
            "created_at": (
                asyncio.get_event_loop().time()
            ),
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

        #
        # CREATE BACKGROUND TASK
        #

        task = asyncio.create_task(
            self.run_pipeline(magnet, media_id)
        )

        self._active_pipelines[
            media_id
        ]["pipeline_task"] = task

        return media_id

    async def stop(
        self,
        media_id
    ):
        """
        Stops an active streaming pipeline.
        
        Cancels the background task, cleans up resources,
        and removes from registry.
        
        Args:
            media_id (str): The media_id of the pipeline to stop
            
        Returns:
            bool: True if pipeline was stopped, False if not found
        """

        pipeline = (
            self._active_pipelines.get(
                media_id
            )
        )

        if not pipeline:
            return False

        #
        # Cancel pipeline task
        #

        task = pipeline.get(
            "pipeline_task"
        )

        if task:

            task.cancel()

            try:

                await task

            except asyncio.CancelledError:

                pass

        #
        # Cleanup resources
        # (will set status if pipeline exists)
        #

        await self._cleanup_pipeline(
            media_id
        )

        #
        # Remove from registry
        #

        self._active_pipelines.pop(
            media_id,
            None
        )

        return True

    async def status(self, media_id):
        """
        Returns detailed status information for an active streaming pipeline.
        
        Args:
            media_id (str): The media_id to query
            
        Returns:
            dict: Status dictionary containing pipeline information, or None if not found
                  Example:
                  {
                      "media_id": "...",
                      "magnet": "...",
                      "info_hash": "...",
                      "status": "running|completed|cancelled|failed|starting",
                      "progress": 45.2,
                      "download_rate": 2.34,  # MB/s
                      "num_peers": 12,
                      "downloaded_size": 450,  # MB
                      "duration": 3600,  # seconds
                      "hls_active": true,
                      "created_at": 1234567890.5,
                      "finished_at": 1234567950.5,
                      "error": null
                  }
        """

        if media_id not in self._active_pipelines:
            return None

        pipeline = (
            self._active_pipelines[media_id]
        )

        status_info = {
            "media_id": media_id,
            "magnet": pipeline["magnet"],
            "info_hash": pipeline["info_hash"],
            "status": pipeline["status"],
            "created_at": pipeline["created_at"],
            "finished_at": pipeline["finished_at"],
            "error": pipeline["error"],
        }

        #
        # Get torrent-specific stats
        #

        handle = pipeline.get("handle")

        if handle:

            try:

                torrent_status = (
                    handle.status()
                )

                status_info["progress"] = (
                    torrent_status.progress * 100
                )

                status_info["download_rate"] = (
                    torrent_status.download_rate
                    / 1024 / 1024
                )

                status_info["num_peers"] = (
                    torrent_status.num_peers
                )

            except:

                pass

        #
        # Get file size stats
        #

        stream = pipeline.get("stream")

        if stream:

            try:

                size = (
                    stream
                    .file_path
                    .stat()
                    .st_size
                )

                status_info["downloaded_size"] = (
                    size / 1024 / 1024
                )

            except:

                pass

        #
        # Get playback session info
        #

        playback = pipeline.get("playback")

        if playback:

            status_info["duration"] = (
                playback.total_duration
                if hasattr(playback, "total_duration")
                else None
            )

        #
        # Get HLS status
        #

        hls = pipeline.get("hls")

        if hls:

            status_info["hls_active"] = (
                hls.active
            )

        return status_info
    

    async def list_active(self):

        return {
            media_id: {
                "status": p["status"],
                "created_at": p["created_at"]
            }
            for media_id, p
            in self._active_pipelines.items()
        }