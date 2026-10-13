"""Git history primitives: trees and files at a commit, the last-run search and diff hunks.

``History`` lists a commit's tree once (``tree_at``; ``head_files`` for HEAD) and reads files at
a commit (``show``), caching both. ``drift_base_commits``, ``is_ancestor``, ``changed_files``
and ``diff_hunks`` serve the last-run search and the change set (spec 6.1, 6.2).
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict

from dd_common import git_ok, run_git

_QUIET = ("-c", "core.quotePath=false")
_LITERAL = "--literal-pathspecs"
_EMPTY: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())
_DRIFT_BASE = re.compile(r"^Drift-Base:\s*([0-9a-f]{7,40})", re.MULTILINE)
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_NL = chr(10)


class Hunk(TypedDict):
    """One ``git diff -U0`` hunk; a zero count gives ``end = start - 1``."""

    file: str
    old_start: int
    old_end: int
    new_start: int
    new_end: int
    text: str


def _nul_split(out: str) -> list[str]:
    """Names from ``git ls-tree -z`` output. Without ``-z`` git C-quotes a name holding ``"``,
    ``\\``, a tab or a control character even with ``core.quotePath=false``, and the quoted
    form then fails every path comparison (final-review residual, ruling R70)."""
    return [name for name in out.split(chr(0)) if name]


class History:
    """Read-only view of a repository's history; every result is cached per instance."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._trees: dict[str, tuple[frozenset[str], frozenset[str]] | None] = {}
        self._shows: dict[tuple[str, str], str | None] = {}

    def tree_at(self, sha: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """Return ``(files, dirs)`` at ``sha``; dirs hold every ancestor. None on failure."""
        if sha not in self._trees:
            out = run_git(self.root, [*_QUIET, "ls-tree", "-r", "-z", "--name-only", sha])
            if out is None:
                self._trees[sha] = None
            else:
                files = frozenset(_nul_split(out))
                dirs: set[str] = set()
                for path in files:
                    parts = path.split("/")[:-1]
                    for i in range(1, len(parts) + 1):
                        dirs.add("/".join(parts[:i]))
                self._trees[sha] = (files, frozenset(dirs))
        return self._trees[sha]

    def head_files(self) -> tuple[frozenset[str], frozenset[str]]:
        """``tree_at("HEAD")``; two empty sets when HEAD does not exist (empty repository)."""
        return self.tree_at("HEAD") or _EMPTY

    def show(self, sha: str, path: str) -> str | None:
        """File content at ``sha``, or None when the path does not exist there."""
        key = (sha, path)
        if key not in self._shows:
            self._shows[key] = run_git(self.root, ["show", f"{sha}:{path}"])
        return self._shows[key]


def drift_base_commits(root: Path) -> list[tuple[str, str]]:
    """``(commit, Drift-Base sha)`` for every commit on HEAD carrying a ``Drift-Base:`` line in
    its message, newest first. Empty when git fails."""
    out = run_git(root, ["log", "--format=%H%x00%B%x00", "--grep=^Drift-Base:", "HEAD"])
    found: list[tuple[str, str]] = []
    if not out:
        return found
    fields = out.split(chr(0))
    for i in range(0, len(fields) - 1, 2):
        match = _DRIFT_BASE.search(fields[i + 1])
        if match:
            found.append((fields[i].strip(), match.group(1)))
    return found


def is_ancestor(root: Path, a: str, b: str) -> bool:
    """Whether commit ``a`` is an ancestor of (or equal to) ``b``; False when git fails."""
    return git_ok(root, ["merge-base", "--is-ancestor", a, b])


def changed_files(root: Path, sha: str) -> list[str]:
    """Sorted paths that differ between ``sha`` and HEAD, renames shown as delete plus add."""
    out = run_git(root, [*_QUIET, "diff", "--name-only", "--no-renames", "-z", sha, "HEAD"])
    return sorted(_nul_split(out)) if out else []


def diff_hunks(root: Path, sha: str, files: Iterable[str]) -> dict[str, list[Hunk]]:
    """Hunks of ``git diff -U0 sha HEAD`` for the given ``files``; a file without hunks has no
    key. Empty when git fails."""
    wanted = list(files)
    if not wanted:
        return {}
    out = run_git(root, [_LITERAL, *_QUIET, "diff", "-U0", "--no-renames", "--no-color",
                         sha, "HEAD", "--", *wanted])
    result: dict[str, list[Hunk]] = {}
    if not out:
        return result
    current: str | None = None
    hunk: Hunk | None = None
    body: list[str] = []

    def close() -> None:
        if hunk is not None:
            hunk["text"] = "".join(body)
        body.clear()

    for line in out.splitlines(keepends=True):
        if hunk is None and line.startswith("+++ "):
            name = line[4:].rstrip(_NL).removesuffix(chr(9))  # git tab-ends names with spaces
            current = name[2:] if name.startswith("b/") else None
            continue
        if line.startswith("diff --git "):
            close()
            hunk = None
            current = None
            continue
        match = _HUNK_HEADER.match(line)
        if match and current in wanted:
            close()
            old_n = 1 if match.group(2) is None else int(match.group(2))
            new_n = 1 if match.group(4) is None else int(match.group(4))
            old_start, new_start = int(match.group(1)), int(match.group(3))
            hunk = {"file": current or "", "old_start": old_start,
                    "old_end": old_start + old_n - 1, "new_start": new_start,
                    "new_end": new_start + new_n - 1, "text": ""}
            result.setdefault(hunk["file"], []).append(hunk)
        elif hunk is not None:
            body.append(line)
    close()
    return result
