"""Replay a corpus ``history.yaml`` into a fresh git repository (spec 6).

Fixtures under ``tests/fixtures/corpus/<name>/`` keep their final tree in
``files/`` and their history in ``history.yaml`` (an ordered list of commits:
author, date, subject, the files touched with their content at that point,
optional ``branch``, ``delete`` and ``tag``). Replaying at test time gives
churn, coupling, blame age, authorship, branches and tags without committing
a ``.git`` directory.

Every git call is a list argv with fixed identity and safety options
(``user.name``, ``user.email``, ``commit.gpgsign=false``,
``core.autocrlf=false``, ``core.quotePath=false``) so the replay is identical
on Windows and Linux. ``GIT_COMMITTER_DATE`` is set to the commit date so
committer dates, and therefore lightweight-tag creator dates, are fixed.

A ``files:`` value of ``"@final"`` copies the path from ``files/``; any other
string is written literally (UTF-8, LF as given). This module is covered by
ruff but not mypy (mypy's ``files`` is ``scripts/`` only).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "corpus"
FINAL = "@final"

_GIT_FIXED: tuple[str, ...] = (
    "-c", "user.name=Fixture",
    "-c", "user.email=fixture@example.com",
    "-c", "commit.gpgsign=false",
    "-c", "core.autocrlf=false",
    "-c", "core.quotePath=false",
)


class HistoryError(Exception):
    """Raised when history.yaml is malformed or a git command fails."""


def _run(
    repo: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *_GIT_FIXED, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
        timeout=120,
    )


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = _run(repo, *args, env=env)
    if proc.returncode != 0:
        raise HistoryError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def git_output(repo: Path, *args: str) -> str:
    """Run ``git <args>`` in ``repo`` and return stdout; raise HistoryError on failure."""
    return _git(repo, *args)


def _branch_exists(repo: Path, name: str) -> bool:
    return _run(repo, "rev-parse", "--verify", "-q", f"refs/heads/{name}").returncode == 0


def _current_branch(repo: Path) -> str:
    return _run(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()


def _checkout(repo: Path, name: str) -> None:
    if name == _current_branch(repo):
        return
    if _branch_exists(repo, name):
        _git(repo, "checkout", "-q", name)
    else:
        _git(repo, "checkout", "-q", "-b", name)


def _write(dest: Path, rel: str, value: Any, files_root: Path) -> None:
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "" if value is None else str(value)
    if text == FINAL:
        source = files_root / rel
        if not source.is_file():
            raise HistoryError(f"{rel}: '@final' but {source} does not exist")
        shutil.copyfile(source, target)
    else:
        target.write_bytes(text.encode("utf-8"))


def _date_string(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def replay_history(history_yaml: Path, files_root: Path, dest: Path) -> Path:
    """Create a git repository at ``dest`` by replaying ``history_yaml``.

    Returns ``dest``. HEAD ends on whichever branch the last commit named
    (``main`` when none did).
    """
    raw = yaml.safe_load(history_yaml.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("commits"), list):
        raise HistoryError(f"{history_yaml}: expected a mapping with a 'commits' list")
    dest.mkdir(parents=True, exist_ok=True)
    _git(dest, "init", "-q")
    _git(dest, "symbolic-ref", "HEAD", "refs/heads/main")
    for index, commit in enumerate(raw["commits"], start=1):
        if not isinstance(commit, dict):
            raise HistoryError(f"commit {index}: not a mapping")
        for key in ("author", "date", "subject"):
            if key not in commit:
                raise HistoryError(f"commit {index}: missing {key!r}")
        date = _date_string(commit["date"])
        branch = commit.get("branch")
        if branch is not None:
            _checkout(dest, str(branch))
        files = commit.get("files") or {}
        if not isinstance(files, dict):
            raise HistoryError(f"commit {index}: 'files' must be a mapping")
        for rel, value in files.items():
            _write(dest, str(rel), value, files_root)
        for rel in commit.get("delete") or []:
            (dest / str(rel)).unlink()
        _git(dest, "add", "-A")
        env = {**os.environ, "GIT_COMMITTER_DATE": date}
        _git(
            dest, "commit", "-q", "--allow-empty",
            "--author", str(commit["author"]), "--date", date, "-m", str(commit["subject"]),
            env=env,
        )
        tag = commit.get("tag")
        if tag is not None:
            _git(dest, "tag", str(tag), env=env)
    return dest


def replay_fixture(name: str, dest: Path) -> Path:
    """Replay ``tests/fixtures/corpus/<name>`` into ``dest`` and return ``dest``."""
    base = CORPUS_ROOT / name
    return replay_history(base / "history.yaml", base / "files", dest)
