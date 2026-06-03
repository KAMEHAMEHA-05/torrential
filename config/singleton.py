import os

from dotenv import load_dotenv

from config.manager import (
    ConfigManager
)

load_dotenv()


config = ConfigManager(

    path="config.json.enc",

    master_key=os.getenv(
        "MASTER_KEY"
    )
)

config.load()