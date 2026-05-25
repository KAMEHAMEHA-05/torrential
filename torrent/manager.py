from pathlib import Path
import libtorrent as lt

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm"
}


class TorrentManager:

    def __init__(self, torrent_session):

        self.session = torrent_session

        self.handles = {}


    def add_magnet(
        self,
        magnet_uri,
        save_path
    ):

        params = {

            "save_path": save_path,

            "storage_mode":
                lt.storage_mode_t.storage_mode_sparse
        }

        handle = (
            self.session.session.add_torrent({
                "url": magnet_uri,
                **params
            })
        )

        handle.set_sequential_download(
            True
        )

        info_hash = str(
            handle.info_hash()
        )

        self.handles[
            info_hash
        ] = handle

        return info_hash


    def get_handle(self, info_hash):

        handle = self.handles.get(
            info_hash
        )

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