"""
SQLite connection + schema init for verification.sqlite.

The DB lives at repo_root/verification.sqlite by default. Schema is idempotent
(CREATE IF NOT EXISTS) so init_schema() is safe to call every session.
"""
import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "verification.sqlite"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: str | os.PathLike | None = None) -> sqlite3.Connection:
    """Open a connection with sensible pragmas. Initializes schema on first call."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    is_new = not path.exists()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    if is_new:
        init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql. Idempotent."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def db_path() -> Path:
    return DEFAULT_DB_PATH
