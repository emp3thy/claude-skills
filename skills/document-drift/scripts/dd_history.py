"""Git history primitives: per-line blame snapshots, trees at a commit, renames, deletions.

HEAD's tree is listed once (``head_files``). A line snapshot's tree is never listed (ruling
R63): ``snapshot(sha)`` answers membership for the paths it is asked about with ``git cat-file
--batch-check`` (``prefetch`` asks for many in one call), and ``list_dir`` lists one directory
with ``git ls-tree -r -z --name-only <sha> -- <dir>``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from dd_common import run_git

_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)")
_QUIET = ("-c", "core.quotePath=false")
_LITERAL = "--literal-pathspecs"
_EMPTY: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())
# What a tree entry is to the resolvers: a blob (file or symlink) or a gitlink (submodule) is a
# file, as it is in an ``ls-tree -r`` listing; a tree is a directory.
_FILE_TYPES = frozenset({"blob", "commit"})
_DIR_TYPES = frozenset({"tree"})
_OBJECT_TYPES = _FILE_TYPES | _DIR_TYPES
_NL = chr(10)
_UNNAMEABLE = (_NL, chr(13), chr(0))  # characters a batch input line cannot carry


def _nul_split(out: str) -> list[str]:
    """Names from ``git ls-tree -z`` output. Without ``-z`` git C-quotes a name holding ``"``,
    ``\\``, a tab or a control character even with ``core.quotePath=false``, and the quoted
    form then fails every path comparison (final-review residual, ruling R70)."""
    return [name for name in out.split(chr(0)) if name]


class _Members:
    """``path in members``: whether the tree at ``sha`` holds ``path`` as one of ``types``."""

    def __init__(self, history: History, sha: str, types: frozenset[str]) -> None:
        self.history = history
        self.sha = sha
        self.types = types

    def __contains__(self, path: object) -> bool:
        if not isinstance(path, str) or not path:
            return False
        return self.history.object_type(self.sha, path) in self.types


class SnapshotTree:
    """The tree at one commit as ``files`` and ``dirs`` that answer ``in`` lazily."""

    def __init__(self, history: History, sha: str) -> None:
        self.sha = sha
        self.files = _Members(history, sha, _FILE_TYPES)
        self.dirs = _Members(history, sha, _DIR_TYPES)


class History:
    """Read-only view of a repository's history; every result is cached per instance."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._snapshots: dict[str, dict[int, str] | None] = {}
        self._trees: dict[str, tuple[frozenset[str], frozenset[str]] | None] = {}
        self._shows: dict[tuple[str, str], str | None] = {}
        self._renames: dict[str, dict[str, tuple[str, str]]] = {}
        self._finals: dict[tuple[str, str], tuple[frozenset[str], str | None]] = {}
        self._deletions: dict[tuple[str, str], str | None] = {}
        self._touches: dict[tuple[str, str, str], str | None] = {}
        self._types: dict[tuple[str, str], str | None] = {}
        self._failed: set[str] = set()
        self._listings: dict[tuple[str, str], frozenset[str] | None] = {}

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

    def prefetch(self, wanted: Mapping[str, Iterable[str]]) -> None:
        """Look up every ``<sha>:<path>`` not yet known in one ``git cat-file --batch-check``.

        Each sha's root (``<sha>:``) is looked up too, so ``snapshot`` can tell a readable
        commit from an unreadable one. A path git reports missing is cached as None; when the
        call itself fails, every sha in it is marked unreadable.
        """
        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for sha, paths in wanted.items():
            for path in ("", *paths):
                key = (sha, path)
                if key in self._types or key in seen or sha in self._failed:
                    continue
                if any(c in path for c in _UNNAMEABLE):
                    self._types[key] = None  # cannot be named on a batch line
                    continue
                seen.add(key)
                pairs.append(key)
        if not pairs:
            return
        out = run_git(self.root, ["cat-file", "--batch-check=%(objecttype)"],
                      stdin="".join(f"{sha}:{path}{_NL}" for sha, path in pairs))
        lines = out.split(_NL)[: len(pairs)] if out is not None else []
        if len(lines) != len(pairs):
            self._failed.update(sha for sha, _ in pairs)
            return
        for key, line in zip(pairs, lines, strict=True):
            kind = line.strip()
            self._types[key] = kind if kind in _OBJECT_TYPES else None

    def object_type(self, sha: str, path: str) -> str | None:
        """``blob``, ``tree`` or ``commit`` for ``path`` in the tree at ``sha``; None if absent."""
        key = (sha, path)
        if key not in self._types:
            self.prefetch({sha: (path,)})
        return self._types.get(key)

    def snapshot(self, sha: str) -> SnapshotTree | None:
        """The tree at ``sha`` for membership lookups; None when the commit cannot be read."""
        if self.object_type(sha, "") != "tree" or sha in self._failed:
            return None
        return SnapshotTree(self, sha)

    def list_dir(self, sha: str, directory: str) -> frozenset[str] | None:
        """Every file under ``directory`` at ``sha`` (full paths); None when git fails."""
        key = (sha, directory)
        if key not in self._listings:
            out = run_git(self.root, [_LITERAL, *_QUIET, "ls-tree", "-r", "-z", "--name-only",
                                      sha, "--", directory])
            self._listings[key] = None if out is None else frozenset(
                name for name in _nul_split(out) if name.startswith(directory + "/"))
        return self._listings[key]

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
                 "--topo-order", "--abbrev=7", "--format=%x1e%h", f"{sha}..HEAD"],
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

    def final_name(self, sha: str, path: str) -> tuple[frozenset[str], str | None]:
        """Follow ``path`` through renames after ``sha``.

        A path that exists at HEAD is returned as is with no commit (never drift). Otherwise
        returns the final names that exist at HEAD and the commit of the last hop (a chain
        that returns to an earlier name finishes there); ``(frozenset(), None)`` if gone.
        """
        key = (sha, path)
        if key not in self._finals:
            if path in self.head_files()[0]:
                self._finals[key] = (frozenset({path}), None)
                return self._finals[key]
            renames = self.renames_since(sha)
            current, last = path, None
            seen = {path}
            while current in renames:
                nxt, commit = renames[current]
                current, last = nxt, commit
                if nxt in seen:
                    break
                seen.add(nxt)
            if current in self.head_files()[0]:
                self._finals[key] = (frozenset({current}), last)
            else:
                self._finals[key] = (frozenset(), None)
        return self._finals[key]

    def deleting_commit(self, sha: str, path: str) -> str | None:
        """7-char commit that deleted ``path`` in ``sha..HEAD``, or None."""
        key = (sha, path)
        if key not in self._deletions:
            out = run_git(
                self.root,
                [_LITERAL, *_QUIET, "log", "-1", "--abbrev=7", "--format=%h", "--diff-filter=D",
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
                [_LITERAL, *_QUIET, "log", "-1", "--abbrev=7", "--format=%h", f"-S{needle}",
                 f"{sha}..HEAD", "--", path],
            )
            self._touches[key] = (out or "").strip() or None
        return self._touches[key]
