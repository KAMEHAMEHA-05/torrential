import asyncio
import os

import httpx

from config.singleton import (
    config
)

from backends.r2 import (
    R2Uploader
)


BIFROST_URL = (
    config.config.bifrost.url
)


def create_uploader(

    backend,

    **kwargs
):

    if backend == "r2":

        return R2Uploader(
            **kwargs
        )

    raise ValueError(

        f"Unsupported backend: "
        f"{backend}"
    )


class UploadWorker:

    def __init__(

        self,

        topic,

        uploader
    ):

        self.topic = topic

        self.uploader = uploader


    async def consume(self):

        async with httpx.AsyncClient(

            timeout=None
        ) as client:

            while True:

                response = await client.post(

                    f"{BIFROST_URL}"
                    f"/topics/{self.topic}/consume"
                )

                data = response.json()

                if not data.get(
                    "success"
                ):
                    continue

                payload = (

                    data[
                        "message"
                    ][
                        "payload"
                    ]
                )

                print(

                    "[UPLOAD JOB]",

                    payload
                )

                result = await (

                    self.uploader.upload_file(

                        local_path=
                        payload["path"],

                        object_name=(

                            f"{self.topic}/"

                            f"{payload['filename']}"
                        )
                    )
                )

                print(

                    "[UPLOADED]",

                    result
                )


async def main():

    media_id = (
        input(
            "Media ID: "
        ).strip()
    )

    uploader = create_uploader(

        "r2",

        account_id=config.config.r2.account_id,

        access_key_id=config.config.r2.access_key_id,

        secret_access_key=config.config.r2.secret_access_key,

        bucket_name=config.config.r2.bucket_name
    )

    worker = UploadWorker(

        topic=media_id,

        uploader=uploader
    )

    await worker.consume()


if __name__ == "__main__":

    asyncio.run(main())