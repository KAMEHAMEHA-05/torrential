import os

import jwt

from datetime import (
    datetime,
    timedelta,
    timezone
)


def create_access_token(

    key_id,

    role,

    expires_minutes=20
):

    now = datetime.now(
        timezone.utc
    )

    payload = {

        "sub": key_id,

        "role": role,

        "iat": now,

        "exp": (
            now
            + timedelta(
                minutes=expires_minutes
            )
        )
    }

    return jwt.encode(

        payload,

        os.getenv(
            "JWT_SECRET"
        ),

        algorithm="HS256"
    )