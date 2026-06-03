from pydantic import (
    BaseModel
)

from typing import (
    Optional
)

from typing import (
    List
)

import time


class APIKey(BaseModel):

    id: str

    secret: str

    role: str = "worker"

    enabled: bool = True

    created_at: float = (
        time.time()
    )


class AuthConfig(

    BaseModel
):

    api_keys: List[
        APIKey
    ] = []


class BifrostConfig(

    BaseModel
):

    url: str = (
        "http://localhost:8001"
    )


class R2Config(

    BaseModel
):

    account_id: str = ""

    access_key_id: str = ""

    secret_access_key: str = ""

    bucket_name: str = (
        "streamdeck-media"
    )


class AppConfig(

    BaseModel
):

    version: int = 1

    auth: AuthConfig = (
        AuthConfig()
    )

    bifrost: BifrostConfig = (
        BifrostConfig()
    )

    r2: R2Config = (
        R2Config()
    )