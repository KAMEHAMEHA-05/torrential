import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException
from config.manager import ConfigManager
from api.dependencies import verify_jwt
from api.auth import create_access_token
from api.models import*

load_dotenv()

app = FastAPI(
    title="Torrential"
)

config = ConfigManager(

    path="config.json.enc",

    master_key=os.getenv(
        "MASTER_KEY"
    )
)

config.load()

@app.post(
    "/auth/login"
)
async def login(

    request: LoginRequest
):

    key = (
        config.verify_api_key(

            request.key_id,

            request.secret
        )
    )

    if not key:

        raise HTTPException(

            401,

            "Invalid credentials"
        )

    token = create_access_token(

        key_id=key.id,

        role=key.role
    )

    return {

        "access_token":
            token,

        "token_type":
            "bearer",

        "expires_in":
            1200
    }


@app.get(
    "/admin/config"
)
async def get_config(

    _ = Depends(
        verify_jwt
    )
):

    return config.get_config()

@app.put(
    "/admin/config"
)
async def update_config(

    request:
    UpdateConfigRequest,

    _ = Depends(
        verify_jwt
    )
):

    config.config = type(
        config.config
    )(
        **request.config
    )

    config.save()

    return {

        "success": True
    }

@app.get(
    "/admin/apikeys"
)
async def list_apikeys(

    _ = Depends(
        verify_jwt
    )
):

    return config.list_api_keys()

@app.post(
    "/admin/apikeys"
)
async def create_apikey(

    request:
    CreateAPIKeyRequest,

    _ = Depends(
        verify_jwt
    )
):

    key = (
        config.create_api_key(

            key_id=
            request.key_id,

            role=
            request.role
        )
    )

    return key.model_dump()

@app.patch(
    "/admin/apikeys/{key_id}/enable"
)
async def enable_key(

    key_id: str,

    _ = Depends(
        verify_jwt
    )
):

    return {

        "success":

        config.enable_api_key(
            key_id
        )
    }

@app.patch(
    "/admin/apikeys/{key_id}/disable"
)
async def disable_key(

    key_id: str,

    _ = Depends(
        verify_jwt
    )
):

    return {

        "success":

        config.disable_api_key(
            key_id
        )
    }

@app.delete(
    "/admin/apikeys/{key_id}"
)
async def delete_key(

    key_id: str,

    _ = Depends(
        verify_jwt
    )
):

    config.delete_api_key(
        key_id
    )

    return {

        "success": True
    }

@app.get(
    "/health"
)
async def health():

    return {

        "status": "healthy"
    }

@app.put(
    "/admin/config/r2"
)
async def update_r2(

    request: UpdateR2Request,

    _ = Depends(
        verify_jwt
    )
):

    config.update_r2(

        account_id=
        request.account_id,

        access_key_id=
        request.access_key_id,

        secret_access_key=
        request.secret_access_key,

        bucket_name=
        request.bucket_name
    )

    return {

        "success": True,

        "r2": (

            config
            .config
            .r2
            .model_dump()
        )
    }

@app.get(
    "/admin/config/r2"
)
async def get_r2(

    _ = Depends(
        verify_jwt
    )
):

    return (

        config
        .config
        .r2
        .model_dump()
    )

@app.put(
    "/admin/config/bifrost"
)
async def update_bifrost(

    request: UpdateBifrostRequest,

    _ = Depends(
        verify_jwt
    )
):

    config.update_bifrost(
        request.url
    )

    return {

        "success": True,

        "bifrost": (

            config
            .config
            .bifrost
            .model_dump()
        )
    }

@app.get(
    "/admin/config/bifrost"
)
async def get_bifrost(

    _ = Depends(
        verify_jwt
    )
):

    return (

        config
        .config
        .bifrost
        .model_dump()
    )

