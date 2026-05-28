import asyncio
import os

from pathlib import Path

import httpx


BIFROST_URL = (
    "http://localhost:8001"
)

WATCH_ROOT = "/tmp/hls"

TOPIC = "hls_upload"


class HLSWatcher:

    def __init__(

        self,

        root=WATCH_ROOT
    ):

        self.root = Path(root)

        self.seen = set()


    async def publish(

        self,

        payload
    ):

        async with httpx.AsyncClient() as client:

            await client.post(

                f"{BIFROST_URL}"
                f"/topics/{TOPIC}/publish",

                json={
                    "payload": payload
                }
            )


    async def scan(self):

        while True:

            for path in self.root.rglob("*"):

                if not path.is_file():
                    continue

                #
                # skip temp files
                #

                if path.suffix not in (

                    ".m4s",

                    ".m3u8",

                    ".mp4"
                ):
                    continue

                key = (
                    str(path),

                    path.stat().st_size
                )

                #
                # already uploaded
                #

                if key in self.seen:
                    continue

                self.seen.add(key)

                payload = {

                    "path": str(path),

                    "filename": path.name,

                    "size": path.stat().st_size
                }

                print(
                    "[WATCHER]",
                    payload
                )

                await self.publish(
                    payload
                )

            await asyncio.sleep(1)


async def main():

    watcher = HLSWatcher()

    await watcher.scan()


if __name__ == "__main__":

    asyncio.run(main())