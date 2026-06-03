# upload/session.py

import asyncio

from upload.hls_watcher import (
    HLSWatcher
)

from upload.uploader import (
    UploadWorker,
    create_uploader
)

from config.singleton import (
    config
)


class UploadSession:

    def __init__(

        self,

        media_id
    ):

        self.media_id = media_id

        self.watcher = HLSWatcher(
            media_id=media_id
        )

        self.uploader = UploadWorker(

            topic=media_id,

            uploader=create_uploader(

                "r2",

                account_id=config.config.r2.account_id,

                access_key_id=config.config.r2.access_key_id,

                secret_access_key=config.config.r2.secret_access_key,

                bucket_name=config.config.r2.bucket_name
            )
        )

        self.tasks = []


    async def start(self):

        watcher_task = (
            asyncio.create_task(
                self.watcher.scan()
            )
        )

        uploader_task = (
            asyncio.create_task(
                self.uploader.consume()
            )
        )

        self.tasks.extend(

            [

                watcher_task,

                uploader_task
            ]
        )

        print(

            f"[UPLOAD SESSION] "

            f"started {self.media_id}"
        )


    async def stop(self):

        for task in self.tasks:

            task.cancel()

        await asyncio.gather(

            *self.tasks,

            return_exceptions=True
        )

        print(

            f"[UPLOAD SESSION] "

            f"stopped {self.media_id}"
        )