# upload/session.py

import asyncio

from upload.hls_watcher import (
    HLSWatcher
)

from upload.uploader import (
    UploadWorker,
    create_uploader
)

import os

from dotenv import load_dotenv

load_dotenv()


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

                account_id=os.getenv(
                    "R2_ACCOUNT_ID"
                ),

                access_key_id=os.getenv(
                    "R2_ACCESS_KEY_ID"
                ),

                secret_access_key=os.getenv(
                    "R2_SECRET_ACCESS_KEY"
                ),

                bucket_name=os.getenv(
                    "R2_BUCKET_NAME",
                    "streamdeck-media"
                )
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