# pipeline.py

import asyncio

from media.cache import MediaCache
from torrent.manager import TorrentManager
from  import resolve_playback_session
from playback.hls_stream import HLSStreamSession
from .producers import byte_stream_producer


class TorrentialPipeline:

    def __init__(

        self,

        torrent_manager,

        media_cache
    ):

        self.torrent_manager = (
            torrent_manager
        )

        self.media_cache = (
            media_cache
        )

        self.sessions = {}


    async def start_stream(

        self,

        magnet
    ):

        #
        # create media id immediately
        #

        media_id = (
            self.media_cache.create_media(
                magnet
            )
        )

        #
        # spawn background task
        #

        asyncio.create_task(

            self._run_stream(

                media_id,

                magnet
            )
        )

        return media_id


    async def _run_stream(

        self,

        media_id,

        magnet
    ):

        try:

            #
            # add torrent
            #

            info_hash = (
                self.torrent_manager.add_magnet(

                    magnet_uri=magnet,

                    save_path="./downloads"
                )
            )

            #
            # metadata
            #

            await self.torrent_manager.wait_metadata(
                info_hash
            )

            #
            # select video
            #

            video = (
                self.torrent_manager
                .largest_video_file(
                    info_hash
                )
            )

            #
            # create byte stream
            #

            stream = (
                self.torrent_manager
                .create_stream(
                    info_hash,
                    video["index"]
                )
            )

            #
            # playback session
            #

            playback = (
                resolve_playback_session(
                    stream
                )
            )

            #
            # hls
            #

            hls = HLSStreamSession(
                playback
            )

            await hls.start()

            #
            # producer
            #

            asyncio.create_task(

                byte_stream_producer(

                    stream,

                    hls.byte_queue
                )
            )

            self.sessions[
                media_id
            ] = {

                "state":
                    "streaming",

                "playlist":
                    playback.playlist_url,

                "hls":
                    hls
            }

        except Exception as e:

            self.sessions[
                media_id
            ] = {

                "state":
                    "failed",

                "error":
                    str(e)
            }