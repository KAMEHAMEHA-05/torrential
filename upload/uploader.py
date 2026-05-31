import asyncio
import os

import httpx

from dotenv import load_dotenv

from backends.r2 import (
    R2Uploader
)

load_dotenv()


BIFROST_URL = (
    "http://localhost:8001"
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

    worker = UploadWorker(

        topic=media_id,

        uploader=uploader
    )

    await worker.consume()


if __name__ == "__main__":

    asyncio.run(main())