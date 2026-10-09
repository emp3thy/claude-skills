"""Tiny repo builders for unit tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from dd_make_history import replay_commits


def make_repo(tmp_path: Path, commits: list[dict[str, Any]]) -> Path:
    """Build a git repo under ``tmp_path/repo`` from in-memory commit dicts.

    Each commit needs ``date`` (and ``subject``); ``author`` defaults to the fixture identity.
    """
    prepared = []
    for commit in commits:
        if "date" not in commit:
            raise ValueError(f"commit {commit.get('subject')!r}: 'date' is required")
        prepared.append({"author": "Fixture <fixture@example.com>", **commit})
    return replay_commits(prepared, None, tmp_path / "repo")
