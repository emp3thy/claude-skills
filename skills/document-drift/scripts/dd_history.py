"""Git history primitives: per-line blame snapshots, trees at a commit, renames, deletions."""
from __future__ import annotations

import re
from pathlib import Path

from dd_common import run_git

_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)")
_QUIET = ("-c", "core.quotePath=false")
_EMPTY: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())


class History:
    """Read-only view of a repository's history; every result is cached per instance."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._snapshots: dict[str, dict[int, str] | None] = {}
        self._trees: dict[str, tuple[frozenset[str], frozenset[str]] | None] = {}
        self._shows: dict[tuple[str, str], str | None] = {}
        self._renames: dict[str, dict[str, tuple[str, str]]] = {}
        self._finals: dict[tuple[str, str], tuple[set[str], str | None]] = {}
        self._deletions: dict[tuple[str, str], str | None] = {}
        self._touches: dict[tuple[str, str, str], str | None] = {}

    def line_snapshots(self, doc: str) -> dict[int, str] | None:
        """Map 1-based final line number to the full sha that last changed it, at HEAD.

        Blames ``HEAD`` explicitly, so working-tree edits and autocrlf do not matter.
        None when blame fails (for example the path does not exist at HEAD).
        """
        if doc not in self._snapshots:
            out = run_git(
                self.root, [*_QUIET, "blame", "-w", "-M", "--porcelain", "HEAD", "--", doc]
            )
            result: dict[int, str] | None = None
            if out is not None:
                result = {}
                for line in out.splitlines():
                    match = _BLAME_HEADER.match(line)
                    if match:
                        result[int(match.group(2))] = match.group(1)
            self._snapshots[doc] = result
        return self._snapshots[doc]

    def tree_at(self, sha: str) -> tuple[frozenset[str], frozenset[str]] | None:
        """Return ``(files, dirs)`` at ``sha``; dirs hold every ancestor. None on failure."""
        if sha not in self._trees:
            out = run_git(self.root, [*_QUIET, "ls-tree", "-r", "--name-only", sha])
            if out is None:
                self._trees[sha] = None
            else:
                files = frozenset(line for line in out.splitlines() if line)
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

    def renames_since(self, sha: str) -> dict[str, tuple[str, str]]:
        """Old path -> (new path, 7-char commit) for renames in ``sha..HEAD``.

        ``git log`` lists newest first; the parsed commits are reversed so they apply
        oldest first, which lets a later rename of the same old path win.
        """
        if sha not in self._renames:
            out = run_git(
                self.root,
                [*_QUIET, "log", "-M", "--diff-filter=R", "--name-status",
                 "--abbrev=7", "--format=%x1e%h", f"{sha}..HEAD"],
            )
            result: dict[str, tuple[str, str]] = {}
            if out:
                records = [r for r in out.split("\x1e") if r.strip()]
                for record in reversed(records):
                    lines = record.splitlines()
                    commit = lines[0].strip()
                    for line in lines[1:]:
                        cols = line.split("\t")
                        if len(cols) == 3 and cols[0].startswith("R"):
                            result[cols[1]] = (cols[2], commit)
            self._renames[sha] = result
        return self._renames[sha]

    def final_name(self, sha: str, path: str) -> tuple[set[str], str | None]:
        """Follow ``path`` through renames after ``sha``.

        Returns the final names that exist at HEAD and the commit of the last hop
        (None when never renamed or when nothing exists at HEAD).
        """
        key = (sha, path)
        if key not in self._finals:
            renames = self.renames_since(sha)
            current, last = path, None
            seen = {path}
            while current in renames:
                nxt, commit = renames[current]
                if nxt in seen:
                    break
                seen.add(nxt)
                current, last = nxt, commit
            if current in self.head_files()[0]:
                self._finals[key] = ({current}, last)
            else:
                self._finals[key] = (set(), None)
        return self._finals[key]

    def deleting_commit(self, sha: str, path: str) -> str | None:
        """7-char commit that deleted ``path`` in ``sha..HEAD``, or None."""
        key = (sha, path)
        if key not in self._deletions:
            out = run_git(
                self.root,
                [*_QUIET, "log", "-1", "--abbrev=7", "--format=%h", "--diff-filter=D",
                 f"{sha}..HEAD", "--", path],
            )
            self._deletions[key] = (out or "").strip() or None
        return self._deletions[key]

    def last_commit_touching(self, sha: str, path: str, needle: str) -> str | None:
        """7-char newest commit in ``sha..HEAD`` whose diff changes the count of ``needle``."""
        key = (sha, path, needle)
        if key not in self._touches:
            out = run_git(
                self.root,
                [*_QUIET, "log", "-1", "--abbrev=7", "--format=%h", f"-S{needle}",
                 f"{sha}..HEAD", "--", path],
            )
            self._touches[key] = (out or "").strip() or None
        return self._touches[key]
