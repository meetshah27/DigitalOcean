import logging
import sqlite3
from pathlib import Path

from app.config import settings

logger = logging.getLogger("app.db")

_connection: sqlite3.Connection | None = None


def init_db() -> None:
    global _connection
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _connection = sqlite3.connect(str(db_path), check_same_thread=False)
    _connection.execute("PRAGMA journal_mode=WAL;")
    _connection.execute("PRAGMA busy_timeout=5000;")
    logger.info("db_initialized", extra={"extra_fields": {"db_path": str(db_path)}})


def close_db() -> None:
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None
        logger.info("db_closed")


def is_ready() -> bool:
    if _connection is None:
        return False
    try:
        _connection.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def get_connection() -> sqlite3.Connection:
    if _connection is None:
        raise RuntimeError("Database not initialized")
    return _connection
