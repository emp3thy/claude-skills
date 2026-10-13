"""SQLite storage for the key-value service."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def open_store(path: str, create: bool = False, force: bool = False) -> sqlite3.Connection:
    """Open the database file at ``path``; with ``create``, apply the schema first."""
    target = Path(path)
    if force and target.exists():
        target.unlink()
    conn = sqlite3.connect(target, check_same_thread=False)
    if create:
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


class Store:
    """Items keyed by string, each with an optional expiry time."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    def put(self, key: str, value: bytes, ttl: int | None = None) -> None:
        """Save ``value`` under ``key``; with ``ttl`` it expires after that many seconds."""
        expires = None if ttl is None else int(time.time()) + ttl
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO items (key, value, expires_at) VALUES (?, ?, ?)",
                (key, value, expires),
            )
            self._conn.commit()

    def get(self, key: str) -> bytes | None:
        """The value saved under ``key``, or None when it is missing or expired."""
        row = self._conn.execute(
            "SELECT value, expires_at FROM items WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        value, expires = row
        if expires is not None and expires <= time.time():
            return None
        return bytes(value)

    def keys(self) -> list[str]:
        """Every stored key, expired ones included, in key order."""
        rows = self._conn.execute("SELECT key FROM items ORDER BY key").fetchall()
        return [str(row[0]) for row in rows]

    def count(self) -> int:
        """How many items are stored."""
        (total,) = self._conn.execute("SELECT COUNT(*) FROM items").fetchone()
        return int(total)

    def expires_at(self, key: str) -> int | None:
        """The expiry time of ``key`` in seconds since the epoch, or None."""
        row = self._conn.execute(
            "SELECT expires_at FROM items WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None or row[0] is None else int(row[0])

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key) is not None

    def purge(self) -> int:
        """Delete every expired item; return how many went."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM items WHERE expires_at IS NOT NULL AND expires_at < ?",
                (int(time.time()),),
            )
            self._conn.commit()
        return cursor.rowcount

    def close(self) -> None:
        """Close the connection; the store is unusable afterwards."""
        self._conn.close()
