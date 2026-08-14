"""Build a language-agnostic file inventory of a directory tree.

LOC is counted by tallying ``\\n`` occurrences in the opened file iterator,
never via ``Path.read_text()`` (which translates line endings on Windows), so
counts are platform-independent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_SATD_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX|WORKAROUND|KLUDGE)\b")
_IMPORT_RE = re.compile(r"^\s*(import|from|using|require|include|use)\b")

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


class InventoryError(Exception):
    """Raised when the inventory walk fails."""


@dataclass
class FileEntry:
    path: str  # relative to root, forward-slash separated
    ext: str
    loc: int
    mtime: float
    satd_count: int
    import_count: int


def _is_ignored(rel_parts: tuple[str, ...], ignore: tuple[str, ...]) -> bool:
    return any(part in ignore for part in rel_parts)


def walk_inventory(root: Path, ignore: tuple[str, ...] = DEFAULT_IGNORE) -> dict[str, object]:
    root = root.resolve()
    if not root.exists():
        raise InventoryError(f"path not found: {root}")
    if not root.is_dir():
        raise InventoryError(f"path is not a directory: {root}")

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
            loc = 0
            satd_count = 0
            import_count = 0
            with path.open(encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    loc += 1
                    satd_count += len(_SATD_RE.findall(line))
                    if _IMPORT_RE.match(line):
                        import_count += 1
        except OSError as exc:
            raise InventoryError(f"could not read {path}: {exc}") from exc
        entries.append(
            FileEntry(
                path=str(rel).replace("\\", "/"),
                ext=ext,
                loc=loc,
                mtime=path.stat().st_mtime,
                satd_count=satd_count,
                import_count=import_count,
            )
        )
        languages.add(lang)

    return {
        "root": str(root),
        "total_files": len(entries),
        "total_loc": sum(e.loc for e in entries),
        "languages": sorted(languages),
        "files": [asdict(e) for e in entries],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a file inventory for tech-debt-scan")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument("--out", default=".tech-debt/inventory.json", help="output JSON path")
    args = parser.parse_args(argv)

    try:
        inv = walk_inventory(Path(args.path))
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inv, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({inv['total_files']} files, {inv['total_loc']} LOC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
