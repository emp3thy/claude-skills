"""Areas: the indexed files split by line count into review areas -> areas.json (spec 4).

1. Every top-level directory is an area; the project files and the root's loose files form
   ``a01``.
2. An area over budget is replaced by its subdirectories plus one area for its loose files,
   recursively.
3. Loose files over budget are cut into consecutive groups in path order; a single file over
   budget is an area on its own.
4. Sibling areas (same parent directory, the root included) are merged in path order while
   the merged size stays within budget.

``areas.json`` is ``{"area_lines", "areas": [{"id", "files": [{"path", "lines"}], "lines",
"hints": [Name...]}]}``; a hint whose file is in no area goes to ``a01``.
"""
from __future__ import annotations

import argparse
import posixpath
import sys
from pathlib import Path
from typing import Any, NamedTuple

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_inventory import indexed_files, is_project_file


class _Area(NamedTuple):
    paths: list[str]
    lines: int
    parent: str


def _chunk(files: list[tuple[str, int]], budget: int, parent: str) -> list[_Area]:
    """Rule 3: consecutive whole files in path order, each group within budget."""
    areas: list[_Area] = []
    paths: list[str] = []
    size = 0
    for path, lines in sorted(files):
        if paths and size + lines > budget:
            areas.append(_Area(paths, size, parent))
            paths, size = [], 0
        paths.append(path)
        size += lines
    if paths:
        areas.append(_Area(paths, size, parent))
    return areas


def _merge(areas: list[_Area], budget: int, parent: str) -> list[_Area]:
    """Rule 4: merge adjacent areas of ``parent`` while the total stays within budget."""
    merged: list[_Area] = []
    for area in areas:
        last = merged[-1] if merged else None
        if (last is not None and last.parent == parent and area.parent == parent
                and last.lines + area.lines <= budget):
            merged[-1] = _Area(last.paths + area.paths, last.lines + area.lines, parent)
        else:
            merged.append(area)
    return merged


def _directory(files: list[tuple[str, int]], directory: str, budget: int,
               parent: str) -> list[_Area]:
    """Rule 2: ``directory``'s files as one area, or, over budget, its subareas."""
    total = sum(n for _, n in files)
    if total <= budget:
        return [_Area(sorted(p for p, _ in files), total, parent)]
    loose: list[tuple[str, int]] = []
    subdirs: dict[str, list[tuple[str, int]]] = {}
    for path, lines in files:
        head, sep, _ = posixpath.relpath(path, directory).partition("/")
        if sep:
            subdirs.setdefault(head, []).append((path, lines))
        else:
            loose.append((path, lines))
    parts = _chunk(loose, budget, directory)
    for head, sub in subdirs.items():
        parts.extend(_directory(sub, posixpath.join(directory, head), budget, directory))
    parts.sort(key=lambda a: a.paths[0])
    return _merge(parts, budget, directory)


def split(files: list[tuple[str, int]], project: set[str], area_lines: int) -> list[list[str]]:
    """Path groups in area order for ``files`` as ``(path, lines)``; ``project`` holds the
    project files, which join the root's loose files in the first group."""
    first = [(p, n) for p, n in files if p in project or "/" not in p]
    tops: dict[str, list[tuple[str, int]]] = {}
    for path, lines in files:
        if path not in project and "/" in path:
            tops.setdefault(path.split("/", 1)[0], []).append((path, lines))
    areas = _chunk(first, area_lines, "")
    for head in sorted(tops):
        areas.extend(_directory(tops[head], head, area_lines, ""))
    return [a.paths for a in _merge(areas, area_lines, "")]


def _line_count(root: Path, rel: str) -> int:
    try:
        return len((root / rel).read_bytes().decode("utf-8", "replace").splitlines())
    except OSError:
        return 0


def _load(path: Path, step: str) -> Any:
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def run(root: Path, workdir: Path, config: dict[str, Any]) -> dict[str, Any]:
    """Split the indexed files into areas and write ``areas.json``."""
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    patterns = _load(workdir / "patterns.json", "dd_patterns")
    budget = int(config["area_lines"])
    counts = {p: _line_count(root, p) for p in indexed_files(inventory)}
    project = {p for p in counts if is_project_file(p)}
    groups = split(sorted(counts.items()), project, budget)
    areas: list[dict[str, Any]] = [
        {"id": f"a{i:02d}", "files": [{"path": p, "lines": counts[p]} for p in paths],
         "lines": sum(counts[p] for p in paths), "hints": []}
        for i, paths in enumerate(groups, 1)]
    owner = {f["path"]: a for a in areas for f in a["files"]}
    for name in patterns["names"]:
        target = owner.get(name["file"]) or (areas[0] if areas else None)
        if target is not None:
            target["hints"].append(name)
    result: dict[str, Any] = {"area_lines": budget, "areas": areas}
    write_json(workdir / "areas.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Split the indexed files into review areas by line count.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--area-lines", type=int, default=5000)
    args = parser.parse_args(argv)
    try:
        run(args.repo, args.workdir, {"area_lines": args.area_lines})
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
