"""Pytest path setup so scripts/ and tests/helpers imports work in tests."""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
HELPERS_DIR = _TESTS_DIR / "helpers"
for _dir in (SCRIPTS_DIR, HELPERS_DIR):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
