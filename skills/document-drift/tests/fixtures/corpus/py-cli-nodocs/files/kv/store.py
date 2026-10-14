"""Items on disk, one file per key."""
from __future__ import annotations

import shutil
from pathlib import Path

KEEP_LOGS = 5


class Store:
    """Items keyed by string, kept as files under one directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def create(self, force: bool = False) -> None:
        """Make the store directory; with ``force``, delete an existing one first."""
        if force and self.root.exists():
            shutil.rmtree(self.root)
        (self.root / "items").mkdir(parents=True)

    def keys(self) -> list[str]:
        """Every stored key, sorted."""
        return sorted(p.name for p in (self.root / "items").iterdir())

    def get(self, key: str) -> bytes | None:
        """The value stored under ``key``, or None."""
        path = self.root / "items" / key
        return path.read_bytes() if path.is_file() else None

    def push(self, key: str, token: str) -> None:
        """Append ``key`` and the token's first four characters to log/sync.log."""
        log = self.root / "log" / "sync.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"{key} {token[:4]}\n")
        _rotate(log.parent)

    def migrate(self) -> None:
        """Move items of the old flat layout into items/."""
        for path in self.root.glob("*.item"):
            path.rename(self.root / "items" / path.stem)


def _rotate(folder: Path) -> None:
    """Keep the newest KEEP_LOGS files of ``folder``."""
    files = sorted(folder.iterdir(), key=lambda p: p.stat().st_mtime)
    for old in files[:-KEEP_LOGS]:
        old.unlink()
