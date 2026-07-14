import asyncio
import random

import httpx

from config.singleton import (
    config
)

from upload.backends.r2 import (
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
    def __init__(self, topic, uploader, concurrency=3):
        self.topic = topic
        self.uploader = uploader
        self._sem = asyncio.Semaphore(concurrency)
        self._stop = False

    async def _do_upload(self, payload):
        # Simple retry with backoff
        max_retries = 3
        backoff = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                # uploader.upload_file is async (and now runs boto3 in a thread)
                result = await self.uploader.upload_file(
                    local_path=payload["path"],
                    object_name=f"{self.topic}/{payload['filename']}"
                )
                print("[UPLOADED]", result)
                return True
            except Exception as e:
                print(f"[UPLOAD] attempt={attempt} failed for {payload['filename']}: {e}")
                if attempt == max_retries:
                    print(f"[UPLOAD] giving up on {payload['filename']}")
                    return False
                await asyncio.sleep(backoff + random.random() * 0.5)
                backoff *= 2

    async def consume(self):
        async with httpx.AsyncClient(timeout=10.0) as client:
            while not self._stop:
                try:
                    resp = await client.post(f"{BIFROST_URL}/topics/{self.topic}/consume")
                except Exception as e:
                    print("[UPLOAD] error contacting Bifrost consume endpoint:", e)
                    # avoid tight retry loop
                    await asyncio.sleep(1)
                    continue

                # try to parse JSON safely
                try:
                    data = resp.json()
                except Exception as e:
                    print("[UPLOAD] non-JSON response from Bifrost consume:", e, "status:", resp.status_code)
                    await asyncio.sleep(1)
                    continue

                # Check if there was no message
                if not data.get("success"):
                    # No message currently — sleep a short while to avoid tight loop
                    await asyncio.sleep(0.5)
                    continue

                payload = data["message"]["payload"]
                print("[UPLOAD JOB]", payload)

                # Limit concurrency for uploads using semaphore
                async with self._sem:
                    # run upload (with retries inside _do_upload)
                    await self._do_upload(payload)


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