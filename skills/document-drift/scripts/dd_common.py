"""Shared helpers for the document-drift scripts: git access, JSON IO, exit codes."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FOUND = 1
EXIT_REFUSED = 2
EXIT_MISSING = 5
EXIT_COMMIT = 6

MAX_DOC_BYTES = 2_000_000
GIT_TIMEOUT = 120


class StepError(Exception):
    """A pipeline step failed; ``code`` is the process exit code to use."""

    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


def _git(root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_git(root: Path, args: Sequence[str]) -> str | None:
    """Run ``git -C root <args>``; return stdout, or None on any failure."""
    proc = _git(root, args)
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout


def git_ok(root: Path, args: Sequence[str]) -> bool:
    """True when ``git -C root <args>`` exits 0."""
    proc = _git(root, args)
    return proc is not None and proc.returncode == 0


def write_json(path: Path, doc: Any) -> None:
    """Write ``doc`` as UTF-8 JSON: indent 1, sorted keys, LF, trailing newline."""
    text = json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def read_json(path: Path) -> Any:
    """Read a JSON file written by ``write_json``."""
    return json.loads(path.read_text(encoding="utf-8"))
