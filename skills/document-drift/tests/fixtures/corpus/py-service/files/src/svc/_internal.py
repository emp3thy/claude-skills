"""Private helpers shared by the command line and the routes."""
from __future__ import annotations


def _helper(value: str) -> str:
    """Strip surrounding whitespace from a key before it is stored."""
    return value.strip()
