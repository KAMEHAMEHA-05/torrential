from cryptography.fernet import (
    Fernet
)


def generate_master_key():

    return (
        Fernet
        .generate_key()
        .decode()
    )


def create_fernet(

    key
):

    return Fernet(
        key.encode()
    )