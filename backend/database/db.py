"""SQLite database access — raw sql, no ORM."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA_PATH: Path = Path(__file__).parent / "schema.sql"


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    """Read schema.sql and create all tables. Idempotent — uses IF NOT EXISTS."""
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
        logger.info("Database initialized at %s", db_path)
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        raise
    finally:
        conn.close()
