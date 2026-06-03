import json

from pathlib import Path

from config.crypto import (
    create_fernet
)

from config.models import (
    AppConfig
)

from config.models import (
    APIKey
)

import secrets


class ConfigManager:

    def __init__(

        self,

        path,

        master_key
    ):

        self.path = Path(
            path
        )

        self.fernet = (
            create_fernet(
                master_key
            )
        )

        self.config = (
            AppConfig()
        )


    def create_default(self):

        self.save()


    def load(self):

        if not self.path.exists():

            self.create_default()

            return

        encrypted = (
            self.path.read_bytes()
        )

        decrypted = (
            self.fernet.decrypt(
                encrypted
            )
        )

        data = json.loads(
            decrypted.decode()
        )

        self.config = (
            AppConfig(
                **data
            )
        )


    def save(self):

        data = (
            self.config
            .model_dump()
        )

        encrypted = (
            self.fernet.encrypt(
                json.dumps(
                    data,
                    indent=4
                ).encode()
            )
        )

        self.path.write_bytes(
            encrypted
        )


    def get_config(self):

        return (
            self.config
            .model_dump()
        )
    
    def create_api_key(

        self,

        key_id,

        role="worker"
    ):

        secret = (
            secrets.token_hex(
                32
            )
        )

        api_key = APIKey(

            id=key_id,

            secret=secret,

            role=role
        )

        self.config.auth.api_keys.append(
            api_key
        )

        self.save()

        return api_key

    def list_api_keys(self):

        return [

            key.model_dump()

            for key

            in self.config.auth.api_keys
        ]
    
    def get_api_key(

        self,

        key_id
    ):

        for key in (

            self.config
            .auth
            .api_keys
        ):

            if key.id == key_id:

                return key

        return None
    
    def disable_api_key(

        self,

        key_id
    ):

        key = self.get_api_key(
            key_id
        )

        if not key:
            return False

        key.enabled = False

        self.save()

        return True
    
    def enable_api_key(

        self,

        key_id
    ):

        key = self.get_api_key(
            key_id
        )

        if not key:
            return False

        key.enabled = True

        self.save()

        return True
    
    def delete_api_key(

        self,

        key_id
    ):

        self.config.auth.api_keys = [

            key

            for key

            in self.config
            .auth
            .api_keys

            if key.id != key_id
        ]

        self.save()

    def verify_api_key(

        self,

        key_id,

        secret
    ):

        key = self.get_api_key(
            key_id
        )

        if not key:
            return None

        if not key.enabled:
            return None

        if key.secret != secret:
            return None

        return key
    
    def update_bifrost(

        self,

        url
    ):

        self.config.bifrost.url = url

        self.save()

    def update_r2(

        self,

        account_id,

        access_key_id,

        secret_access_key,

        bucket_name
    ):

        self.config.r2.account_id = (
            account_id
        )

        self.config.r2.access_key_id = (
            access_key_id
        )

        self.config.r2.secret_access_key = (
            secret_access_key
        )

        self.config.r2.bucket_name = (
            bucket_name
        )

        self.save()

        