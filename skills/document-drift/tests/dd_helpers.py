"""Tiny repo builders for unit tests."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from dd_make_history import replay_commits

_IDENTITY = ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
             "-c", "commit.gpgsign=false")


def _git(repo: Path, *args: str, stdin: bytes | None = None,
         env: Mapping[str, str] | None = None) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *_IDENTITY, *args], input=stdin,
                          capture_output=True, check=True, env=env)
    return proc.stdout.decode("utf-8").strip()


def index_commit(repo: Path, date: str, subject: str, add: Mapping[str, str] | None = None,
                 remove: Sequence[str] = ()) -> None:
    """Commit straight from the index with git plumbing, never touching the working tree.

    Lets a test record tree entries whose names the host file system cannot hold (a ``"`` or
    a tab on Windows): each ``add`` path gets a blob holding its text, and each ``remove``
    path leaves the index. ``core.protectNTFS`` is off for those calls only, since these
    entries never reach the disk; with it on, git silently skips such a path. The index is
    checked afterwards so a skipped path fails loudly. ``date`` is the full ISO date used for
    author and committer.
    """
    for path, text in (add or {}).items():
        blob = _git(repo, "hash-object", "-w", "--stdin", stdin=text.encode("utf-8"))
        _git(repo, "-c", "core.protectNTFS=false", "update-index", "--add", "--cacheinfo",
             f"100644,{blob},{path}")
    for path in remove:
        _git(repo, "-c", "core.protectNTFS=false", "update-index", "--force-remove", "--", path)
    listed = _git(repo, "ls-files", "-z", "--cached").split(chr(0))
    missing = [p for p in (add or {}) if p not in listed]
    stuck = [p for p in remove if p in listed]
    if missing or stuck:
        raise AssertionError(f"index_commit: not added {missing}, not removed {stuck}")
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    _git(repo, "commit", "-q", "-m", subject, env=env)


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
