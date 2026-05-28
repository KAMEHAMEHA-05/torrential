import json
import sqlite3
import time
from dataclasses import asdict

import hashlib
from pathlib import Path


STRATEGY_VERSION = 1


class MediaCache:

    def __init__(
        self,
        db_path="data/media_cache.db"
    ):

        db_path = Path(db_path)

        db_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media_cache (

                media_id TEXT PRIMARY KEY,

                media_info TEXT NOT NULL,

                strategy TEXT NOT NULL,

                strategy_version INTEGER NOT NULL,

                updated_at INTEGER NOT NULL
            )
            """
        )

        self.conn.commit()


    def get(
        self,
        media_id
    ):

        cursor = self.conn.execute(
            """
            SELECT
                media_info,
                strategy,
                strategy_version

            FROM media_cache

            WHERE media_id = ?
            """,
            (media_id,)
        )

        row = cursor.fetchone()

        if not row:
            return None

        media_info = json.loads(
            row[0]
        )

        strategy = json.loads(
            row[1]
        )

        version = row[2]

        #
        # invalidate old strategies
        #

        if version != STRATEGY_VERSION:
            return {
                "media_info": media_info,
                "strategy": None
            }

        return {
            "media_info": media_info,
            "strategy": strategy
        }


    def set(
        self,
        media_id,
        media_info,
        strategy
    ):

        self.conn.execute(
            """
            INSERT OR REPLACE INTO media_cache (

                media_id,
                media_info,
                strategy,
                strategy_version,
                updated_at

            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                media_id,

                json.dumps(media_info),

                json.dumps(strategy),

                STRATEGY_VERSION,

                int(time.time())
            )
        )

        self.conn.commit()


def build_local_media_id(
    path,
    size
):

    key = (
        f"local:"
        f"{Path(path).name}:"
        f"{size}"
    )

    return hashlib.sha1(
        key.encode()
    ).hexdigest()


def build_torrent_media_id(
    info_hash,
    file_index,
    size
):

    key = (
        f"torrent:"
        f"{info_hash}:"
        f"{file_index}:"
        f"{size}"
    )

    return hashlib.sha1(
        key.encode()
    ).hexdigest()


cache = MediaCache()