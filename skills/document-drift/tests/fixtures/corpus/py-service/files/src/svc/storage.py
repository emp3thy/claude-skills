"""Record persistence backed by SQLite."""
from __future__ import annotations

import sqlite3


def connect(path: str) -> sqlite3.Connection:
    return sqlite3.connect(path)
