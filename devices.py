# devices.db records each sensor's ID, key hash, and whether it can still send readings.

import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEVICE_DB_PATH = Path(os.environ.get("DEVICE_DB_PATH", "devices.db")).resolve()
DEVICE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")


@contextmanager
def database(*, initialize=False):
    # Setup can create the file. A reading requires the existing file with the registered sensors.
    path = str(DEVICE_DB_PATH) if initialize else f"{DEVICE_DB_PATH.as_uri()}?mode=rw"
    connection = sqlite3.connect(path, uri=not initialize, timeout=2)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    with database(initialize=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY NOT NULL,
                token_hash BLOB UNIQUE NOT NULL,
                active INTEGER NOT NULL CHECK (active IN (0, 1))
            )
            """
        )


def token_hash(token):
    return hashlib.sha256(token.encode("ascii")).digest()


def authenticate(authorization):
    fields = authorization.split()
    if len(fields) != 2 or fields[0].lower() != "bearer" or not TOKEN.fullmatch(fields[1]):
        return None

    # Find the active sensor whose saved hash matches the key in the request.
    with database() as connection:
        row = connection.execute(
            "SELECT device_id FROM devices WHERE token_hash = ? AND active = 1",
            (token_hash(fields[1]),),
        ).fetchone()
    return row[0] if row else None
