import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone


def init_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                original_url TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                click_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                request_hash TEXT NOT NULL,
                code TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


@dataclass(frozen=True)
class LinkRow:
    id: int
    code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None
    click_count: int


class CodeTakenError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(f"code already in use: {code}")


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _row_to_link(row: sqlite3.Row) -> LinkRow:
    return LinkRow(
        id=row["id"],
        code=row["code"],
        original_url=row["original_url"],
        created_at=_parse_dt(row["created_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        click_count=row["click_count"],
    )


def get_link_by_code(conn: sqlite3.Connection, code: str) -> LinkRow | None:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT id, code, original_url, created_at, expires_at, click_count "
        "FROM links WHERE code = ?",
        (code,),
    )
    row = cur.fetchone()
    return _row_to_link(row) if row else None


@dataclass(frozen=True)
class IdempotencyRow:
    key: str
    request_hash: str
    code: str


def get_idempotency_record(conn: sqlite3.Connection, key: str) -> IdempotencyRow | None:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT key, request_hash, code FROM idempotency_keys WHERE key = ?",
        (key,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return IdempotencyRow(key=row["key"], request_hash=row["request_hash"], code=row["code"])


def create_link(
    conn: sqlite3.Connection,
    lock: threading.Lock,
    *,
    code: str,
    original_url: str,
    created_at: datetime,
    expires_at: datetime | None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> LinkRow:
    with lock:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO links (code, original_url, created_at, expires_at, click_count) "
                    "VALUES (?, ?, ?, ?, 0)",
                    (
                        code,
                        original_url,
                        created_at.isoformat(),
                        expires_at.isoformat() if expires_at else None,
                    ),
                )
                if idempotency_key is not None:
                    conn.execute(
                        "INSERT INTO idempotency_keys (key, request_hash, code, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (idempotency_key, request_hash, code, created_at.isoformat()),
                    )
        except sqlite3.IntegrityError as exc:
            raise CodeTakenError(code) from exc

    link = get_link_by_code(conn, code)
    assert link is not None
    return link


def increment_click(conn: sqlite3.Connection, lock: threading.Lock, code: str) -> None:
    with lock:
        with conn:
            conn.execute("UPDATE links SET click_count = click_count + 1 WHERE code = ?", (code,))


def list_links(
    conn: sqlite3.Connection,
    *,
    active_only: bool,
    now: datetime,
    limit: int,
    offset: int,
) -> list[LinkRow]:
    conn.row_factory = sqlite3.Row
    if active_only:
        cur = conn.execute(
            "SELECT id, code, original_url, created_at, expires_at, click_count "
            "FROM links WHERE expires_at IS NULL OR expires_at > ? "
            "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (now.astimezone(timezone.utc).isoformat(), limit, offset),
        )
    else:
        cur = conn.execute(
            "SELECT id, code, original_url, created_at, expires_at, click_count "
            "FROM links ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    return [_row_to_link(row) for row in cur.fetchall()]
