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

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def service_py_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("service-py", tmp_path_factory.mktemp("service-py"))


@pytest.fixture(scope="session")
def web_ts_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("web-ts", tmp_path_factory.mktemp("web-ts"))


@pytest.fixture(scope="session")
def mixed_decoys_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("mixed-decoys", tmp_path_factory.mktemp("mixed-decoys"))
