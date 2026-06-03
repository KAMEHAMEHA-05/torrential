import secrets

from pathlib import Path

from config.crypto import (
    generate_master_key
)

from config.manager import (
    ConfigManager
)


ENV_PATH = Path(
    ".env"
)

CONFIG_PATH = Path(
    "config.json.enc"
)


def bootstrap():

    #
    # already initialized
    #

    if ENV_PATH.exists():

        raise RuntimeError(
            ".env already exists"
        )

    if CONFIG_PATH.exists():

        raise RuntimeError(
            "config.json.enc already exists"
        )

    #
    # generate secrets
    #

    master_key = (
        generate_master_key()
    )

    jwt_secret = (
        secrets.token_hex(
            64
        )
    )

    #
    # write env
    #

    ENV_PATH.write_text(
        (
            f"MASTER_KEY="
            f"{master_key}\n"
            f"JWT_SECRET="
            f"{jwt_secret}\n"
        )
    )

    print(
        "[BOOTSTRAP] "
        ".env created"
    )

    #
    # create config
    #

    config = ConfigManager(

        path=CONFIG_PATH,

        master_key=master_key
    )

    config.create_default()

    #
    # create first worker
    #

    worker = (
        config.create_api_key(
            key_id=(
                "primary-worker"
            ),
            role="worker"
        )
    )

    print()

    print("=" * 50)

    print(
        "\nPRIMARY WORKER\n"
    )

    print(
        f"ID:\n"
        f"{worker.id}\n"
    )

    print(
        f"SECRET:\n"
        f"{worker.secret}\n"
    )

    print("=" * 50)

    print()

    print(
        "[BOOTSTRAP] "
        "Finished"
    )


if __name__ == "__main__":

    bootstrap()