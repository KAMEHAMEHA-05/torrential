# upload/manager.py

from upload.session import (
    UploadSession
)


class UploadManager:

    def __init__(self):

        self.sessions = {}


    async def start(

        self,

        media_id
    ):

        if media_id in self.sessions:

            return

        session = UploadSession(
            media_id
        )

        await session.start()

        self.sessions[
            media_id
        ] = session


    async def stop(

        self,

        media_id
    ):

        session = self.sessions.get(
            media_id
        )

        if not session:
            return

        await session.stop()

        del self.sessions[
            media_id
        ]