from pathlib import Path

import boto3
import asyncio


class R2Uploader:

    def __init__(

        self,

        account_id,

        access_key_id,

        secret_access_key,

        bucket_name
    ):

        endpoint = (

            f"https://{account_id}"
            f".r2.cloudflarestorage.com"
        )

        self.bucket_name = bucket_name

        self.client = boto3.client(

            service_name="s3",

            endpoint_url=endpoint,

            aws_access_key_id=(
                access_key_id
            ),

            aws_secret_access_key=(
                secret_access_key
            ),

            region_name="auto"
        )


    async def upload_file(self, local_path, object_name=None):
        path = Path(local_path)
        if object_name is None:
            object_name = path.name

        # Run the blocking boto3 call in a thread so it doesn't block the event loop
        def _upload():
            self.client.upload_file(
                Filename=str(path),
                Bucket=self.bucket_name,
                Key=object_name
            )

        await asyncio.to_thread(_upload)

        return {
            "success": True,
            "bucket": self.bucket_name,
            "object": object_name
        }