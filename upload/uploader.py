import asyncio

import httpx


BIFROST_URL = (
    "http://localhost:8001"
)

TOPIC = "hls_upload"


class UploadWorker:

    async def consume(self):

        async with httpx.AsyncClient(
            timeout=None
        ) as client:

            while True:

                response = await client.post(

                    f"{BIFROST_URL}"
                    f"/topics/{TOPIC}/consume"
                )

                data = response.json()

                message = data[
                    "message"
                ]

                payload = message[
                    "payload"
                ]

                print(
                    "[UPLOAD JOB]",
                    payload
                )

                #
                # future:
                # upload to R2
                #


async def main():

    worker = UploadWorker()

    await worker.consume()


if __name__ == "__main__":

    asyncio.run(main())