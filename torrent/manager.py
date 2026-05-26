from pathlib import Path
import libtorrent as lt
import json

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm"
}

class TorrentContext:

    def __init__(
        self,
        info_hash,
        handle
    ):

        self.info_hash = info_hash

        self.handle = handle

        self.viewer_count = 0

class TorrentManager:

    def __init__(self, torrent_session):

        self.session = torrent_session

        self.handles = {}
        self.torrents = {}

    def add_magnet(
        self,
        magnet_uri,
        save_path
    ):

        temp = lt.parse_magnet_uri(
            magnet_uri
        )

        info_hash = str(
            temp.info_hash
        )

        #
        # already active
        #

        existing = self.torrents.get(
            info_hash
        )

        if existing:

            existing.viewer_count += 1

            print(

                "Reusing torrent:",

                info_hash,

                "viewers:",

                existing.viewer_count
            )

            return info_hash

        params = {

            "save_path": save_path,

            "storage_mode":
                lt.storage_mode_t.storage_mode_sparse
        }

        #
        # load fastresume
        #

        resume_file = (

            Path("./session/resume")
            /
            f"{info_hash}.fastresume"
        )

        if resume_file.exists():

            try:

                with open(
                    resume_file,
                    "rb"
                ) as f:

                    params[
                        "resume_data"
                    ] = f.read()

                print(
                    "Loaded fastresume"
                )

            except Exception as e:

                print(
                    "Failed loading resume:",
                    e
                )

        handle = (
            self.session.session.add_torrent({

                "url": magnet_uri,

                **params
            })
        )

        context = TorrentContext(

            info_hash,

            handle
        )

        context.viewer_count = 1

        self.torrents[
            info_hash
        ] = context

        return info_hash


    def get_handle(self, info_hash):

        context = self.torrents.get(
            info_hash
        )

        if not context:
            return None

        handle = context.handle

        if not handle:
            return None

        if not handle.is_valid():
            return None

        return handle


    async def wait_for_metadata(
        self,
        info_hash
    ):

        import asyncio

        handle = self.get_handle(
            info_hash
        )

        while True:

            if handle.status().has_metadata:
                return

            await asyncio.sleep(1)


    def list_video_files(
        self,
        info_hash
    ):

        handle = self.get_handle(
            info_hash
        )

        ti = handle.get_torrent_info()

        files = ti.files()

        result = []

        for i in range(files.num_files()):

            f = files.at(i)

            path = Path(f.path)

            if (
                path.suffix.lower()
                not in VIDEO_EXTENSIONS
            ):
                continue

            piece_start = (
                f.offset
                //
                ti.piece_length()
            )

            piece_end = (
                (f.offset + f.size - 1)
                //
                ti.piece_length()
            )

            result.append({

                "index": i,

                "path": f.path,

                "size": f.size,

                "offset": f.offset,

                "piece_start": piece_start,

                "piece_end": piece_end
            })

        return result
    
    def release_torrent(
        self,
        info_hash
    ):

        context = self.torrents.get(
            info_hash
        )

        if not context:
            return

        context.viewer_count -= 1

        print(

            "Released torrent:",

            info_hash,

            "viewers:",

            context.viewer_count
        )

        #
        # keep warm for now
        #