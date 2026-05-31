import asyncio
from pathlib import Path

import httpx


BIFROST_URL = (
    "http://localhost:8001"
)

WATCH_ROOT = "/tmp/hls"


class HLSWatcher:

    def __init__(

        self,

        media_id,

        root=WATCH_ROOT
    ):

        self.media_id = media_id

        self.topic = media_id

        self.root = (
            Path(root)
            / media_id
        )

        self.seen = set()


    async def publish(

        self,

        payload
    ):

        async with httpx.AsyncClient() as client:

            await client.post(

                f"{BIFROST_URL}"
                f"/topics/{self.topic}/publish",

                json={
                    "payload": payload
                }
            )


    async def scan(self):

        while True:

            if not self.root.exists():

                await asyncio.sleep(1)

                continue

            for path in self.root.rglob("*"):

                if not path.is_file():
                    continue

                #
                # only upload HLS files
                #

                if path.suffix not in (

                    ".m4s",

                    ".m3u8",

                    ".mp4",

                    ".vtt"
                ):
                    continue

                key = (

                    str(path),

                    path.stat().st_size
                )

                #
                # already seen
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

    media_id = (
        input(
            "Media ID: "
        ).strip()
    )

    async with httpx.AsyncClient() as client:

        await client.post(

            f"{BIFROST_URL}"
            f"/topics/create",

            json={

                "name": media_id,

                "maxsize": 0
            }
        )

    watcher = HLSWatcher(
        media_id=media_id
    )

    await watcher.scan()


if __name__ == "__main__":

    asyncio.run(main())