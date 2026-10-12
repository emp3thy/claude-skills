"""Shared helpers for the corpus and golden tests: replay a fixture ready for a run and read
its planted items."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from dd_make_history import CORPUS_ROOT, replay_fixture

FIXTURES: tuple[str, ...] = ("py-service", "ts-web", "go-cli")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def prepare_fixture(name: str, dest: Path) -> Path:
    """Replay ``name`` into ``dest`` with local settings that keep the working tree clean.

    The replay itself pins ``core.autocrlf=false`` per command; a later ``git status`` would
    otherwise read the machine's global setting, so it is pinned in the repository too, with
    a fixed identity for the run's own commit.
    """
    repo = replay_fixture(name, dest)
    for key, value in (("core.autocrlf", "false"), ("user.name", "Fixture"),
                       ("user.email", "fixture@example.com"), ("commit.gpgsign", "false")):
        _git(repo, "config", key, value)
    return repo


def load_planted(name: str) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(
        (CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    return data
