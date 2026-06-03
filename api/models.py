from pydantic import BaseModel


class LoginRequest(
    BaseModel
):

    key_id: str

    secret: str


class CreateAPIKeyRequest(
    BaseModel
):

    key_id: str

    role: str = "worker"


class UpdateConfigRequest(
    BaseModel
):

    config: dict


class UpdateR2Request(
    BaseModel
):

    account_id: str

    access_key_id: str

    secret_access_key: str

    bucket_name: str


class UpdateBifrostRequest(
    BaseModel
):

    url: str