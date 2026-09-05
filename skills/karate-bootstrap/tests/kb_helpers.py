"""Shared test helpers for karate-bootstrap test modules."""
from __future__ import annotations

from pathlib import Path


def line_of(path: Path, needle: str) -> int:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found in {path}")
