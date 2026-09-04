"""Pytest path setup so scripts/ and tests/helpers imports work in tests."""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
HELPERS_DIR = _TESTS_DIR / "helpers"
# Insert in reverse so each insert(0, ...) leaves SCRIPTS_DIR ahead of
# HELPERS_DIR: a tests/helpers module must never shadow a scripts/ module.
for _dir in reversed((SCRIPTS_DIR, HELPERS_DIR)):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))
