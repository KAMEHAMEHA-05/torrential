import os

import jwt

from fastapi import (

    Header,

    HTTPException
)


async def verify_jwt(

    authorization: str = Header(
        default=""
    )
):

    if not authorization.startswith(
        "Bearer "
    ):

        raise HTTPException(
            401,
            "Missing token"
        )

    token = (
        authorization.replace(
            "Bearer ",
            ""
        )
    )

    try:

        payload = jwt.decode(

            token,

            os.getenv(
                "JWT_SECRET"
            ),

            algorithms=[
                "HS256"
            ]
        )

        return payload

    except jwt.InvalidTokenError:

        raise HTTPException(

            401,

            "Invalid token"
        )