"""Build a language-agnostic file inventory of a directory tree.

LOC is counted by tallying ``\\n`` occurrences in the opened file iterator,
never via ``Path.read_text()`` (which translates line endings on Windows), so
counts are platform-independent.

Beyond the raw file walk, the inventory now carries the two signals behind
hotspot analysis (Tornhill, "Your Code as a Crime Scene"):

  - ``complexity``: an indentation-based complexity proxy (total logical
    indent units across the file, tab = one unit, 4 spaces = one unit). It is
    language-agnostic and correlates well with cyclomatic complexity without
    needing a parser per language.
  - ``churn``: how many commits touched the file inside the churn window
    (default 12 months), mined from ``git log``. Zero when git is unavailable
    or the tree is not a repository (``git_available`` records which).

``hotspots`` ranks files by normalised churn x complexity (0-100). Hotspots
are where debt accrues the highest interest: complex code the team keeps
having to change. Scouts and the synthesis step use this list to prioritise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".md": "markdown",
}

DEFAULT_IGNORE: tuple[str, ...] = (
    "node_modules",
    "bin",
    "obj",
    "target",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".git",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tech-debt",
)

# One logical indent unit = one tab or this many spaces.
_INDENT_SPACES = 4

DEFAULT_CHURN_MONTHS = 12

# How many files the hotspots summary carries (the full per-file data stays in
# ``files`` regardless).
HOTSPOT_LIMIT = 20


class InventoryError(Exception):
    """Raised when the inventory walk fails."""


@dataclass
class FileEntry:
    path: str  # relative to root, forward-slash separated
    ext: str
    loc: int
    mtime: float
    complexity: int  # total logical indent units (indentation complexity proxy)
    max_indent: int  # deepest logical indent level seen
    churn: int  # commits touching the file inside the churn window (0 if no git)


def _is_ignored(rel_parts: tuple[str, ...], ignore: tuple[str, ...]) -> bool:
    return any(part in ignore for part in rel_parts)


def _line_metrics(handle: Iterable[str]) -> tuple[int, int, int]:
    """Return (loc, indent_total, max_indent) for an open text file."""
    loc = 0
    indent_total = 0
    max_indent = 0
    for line in handle:
        loc += 1
        stripped = line.lstrip(" \t")
        if not stripped or stripped in ("\n", "\r\n"):
            continue  # blank lines carry no complexity signal
        ws = line[: len(line) - len(stripped)]
        units = (ws.count("\t") * _INDENT_SPACES + ws.count(" ")) // _INDENT_SPACES
        indent_total += units
        if units > max_indent:
            max_indent = units
    return loc, indent_total, max_indent


def _git_churn(root: Path, months: int) -> dict[str, int] | None:
    """Mine per-file commit counts from git history inside the window.

    Returns None when git is missing, the tree is not a repository, or the
    command fails for any other reason — churn is best-effort, never fatal.
    Paths in the result are relative to ``root`` (forward-slash), matching
    FileEntry.path, even when ``root`` is a subdirectory of the repository.
    """
    cmd = [
        "git",
        "-C",
        str(root),
        "log",
        f"--since={months} months ago",
        "--name-only",
        "--relative",
        "--pretty=format:",
        "--",
        ".",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    counts: dict[str, int] = {}
    for raw in proc.stdout.splitlines():
        path = raw.strip()
        if path:
            counts[path] = counts.get(path, 0) + 1
    return counts


def _build_hotspots(entries: list[FileEntry]) -> list[dict[str, object]]:
    """Rank files by normalised churn x complexity (score 0-100, top N only)."""
    max_churn = max((e.churn for e in entries), default=0)
    max_cx = max((e.complexity for e in entries), default=0)
    if max_churn == 0 or max_cx == 0:
        return []
    scored: list[tuple[float, dict[str, object]]] = []
    for e in entries:
        score = round((e.churn / max_churn) * (e.complexity / max_cx) * 100, 1)
        if score > 0:
            scored.append(
                (
                    score,
                    {
                        "path": e.path,
                        "churn": e.churn,
                        "complexity": e.complexity,
                        "loc": e.loc,
                        "score": score,
                    },
                )
            )
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [hotspot for _, hotspot in scored[:HOTSPOT_LIMIT]]


def walk_inventory(
    root: Path,
    ignore: tuple[str, ...] = DEFAULT_IGNORE,
    churn_months: int = DEFAULT_CHURN_MONTHS,
) -> dict[str, object]:
    root = root.resolve()
    if not root.exists():
        raise InventoryError(f"path not found: {root}")
    if not root.is_dir():
        raise InventoryError(f"path is not a directory: {root}")

    churn = _git_churn(root, churn_months)
    git_available = churn is not None
    churn_map = churn or {}

    entries: list[FileEntry] = []
    languages: set[str] = set()

    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _is_ignored(rel.parts, ignore):
            continue
        ext = path.suffix.lower()
        lang = EXT_TO_LANG.get(ext)
        if lang is None:
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                loc, indent_total, max_indent = _line_metrics(handle)
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        rel_str = str(rel).replace("\\", "/")
        entries.append(
            FileEntry(
                path=rel_str,
                ext=ext,
                loc=loc,
                mtime=path.stat().st_mtime,
                complexity=indent_total,
                max_indent=max_indent,
                churn=churn_map.get(rel_str, 0),
            )
        )
        languages.add(lang)

    return {
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "git_available": git_available,
        "churn_window_months": churn_months,
        "hotspots": _build_hotspots(entries),
        "files": [asdict(e) for e in entries],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a file inventory for tech-debt-scan")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument("--out", default=".tech-debt/inventory.json", help="output JSON path")
    parser.add_argument(
        "--churn-months",
        type=int,
        default=DEFAULT_CHURN_MONTHS,
        help="git-history window (months) for per-file churn counts",
    )
    args = parser.parse_args(argv)

    try:
        inv = walk_inventory(Path(args.path), churn_months=args.churn_months)
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    hot = len(cast("list[dict[str, object]]", inv["hotspots"]))
    git_note = "git churn on" if inv["git_available"] else "no git history"
    print(
        f"wrote {out_path} ({inv['total_files']} files, {inv['total_loc']} LOC, "
        f"{hot} hotspots, {git_note})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
