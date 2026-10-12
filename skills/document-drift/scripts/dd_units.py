"""Review units -> units.json (spec 6.4).

Docs to review are grouped by shared anchored definitions (two docs anchored to the same
``(file, start)`` definition are reviewed together), groups are packed into units of at most
``unit_lines`` lines in path order, and a lone doc over budget is split at ``##`` headings.
``units.json`` is ``{"units": [Unit], "unchecked": [unit id]}``; at most ``caps.review`` units
are kept, README/CLAUDE/AGENTS units first.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from dd_anchors import Anchor
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_config import load_config
from dd_history import Hunk

_Key = tuple[str, int]
_Part = tuple["UnitDoc", list[Anchor]]
ROOT_DOCS = frozenset({"readme.md", "claude.md", "agents.md"})


class UnitDoc(TypedDict):
    doc: str
    ranges: list[list[int]]


class Unit(TypedDict):
    id: str
    docs: list[UnitDoc]
    anchors: list[Anchor]
    hunks: list[Hunk]
    size: int


def _lines(ranges: Iterable[Sequence[int]]) -> int:
    return sum(max(0, r[1] - r[0] + 1) for r in ranges)


def _in_ranges(line: int, ranges: Iterable[Sequence[int]]) -> bool:
    return any(r[0] <= line <= r[1] for r in ranges)


def _touches(hunk: Hunk, ranges: Iterable[Sequence[int]]) -> bool:
    """A hunk touches a range it overlaps; a pure deletion touches its ``new_start``."""
    low, high = hunk["new_start"], max(hunk["new_start"], hunk["new_end"])
    return any(low <= r[1] and r[0] <= high for r in ranges)


def _hunks_for(anchors: Iterable[Anchor], hunks: Mapping[str, list[Hunk]]) -> list[Hunk]:
    """The hunks of the anchors' files that touch the anchors' change ranges, once each."""
    found: dict[tuple[str, int, int], Hunk] = {}
    for anchor in anchors:
        for hunk in hunks.get(anchor["file"], []):
            if _touches(hunk, anchor["change_ranges"]):
                found[(hunk["file"], hunk["new_start"], hunk["new_end"])] = hunk
    return [found[key] for key in sorted(found)]


def _size(docs: Sequence[UnitDoc], anchors: Sequence[Anchor], hunks: Mapping[str, list[Hunk]],
          mode: str, affected: Mapping[str, Any]) -> int:
    """Reviewed lines plus, on a first run, each anchored definition's reading range once, or,
    on a later run, the touching hunk lines plus the reading ranges of missing definitions."""
    total = sum(_lines(d["ranges"]) for d in docs)
    reading: dict[_Key, list[int]] = {}
    if mode == "first":
        reading = {(a["file"], a["start"]): a["reading"] for a in anchors}
    else:
        total += sum(max(1, h["new_end"] - h["new_start"] + 1)
                     for h in _hunks_for(anchors, hunks))
        for d in docs:
            for miss in affected.get(d["doc"], {}).get("missing", []):
                reading[(miss["file"], miss["start"])] = miss["reading"]
    return total + sum(_lines([r]) for r in reading.values())


def _groups(docs: Sequence[str], anchors: Sequence[Anchor]) -> list[list[str]]:
    """Docs joined by shared ``(file, start)`` definitions (union-find), in path order."""
    parent = {d: d for d in docs}

    def find(d: str) -> str:
        while parent[d] != d:
            parent[d] = parent[parent[d]]
            d = parent[d]
        return d

    owner: dict[_Key, str] = {}
    for a in anchors:
        key = (a["file"], a["start"])
        if key in owner:
            parent[find(a["doc"])] = find(owner[key])
        else:
            owner[key] = a["doc"]
    grouped: dict[str, list[str]] = {}
    for d in sorted(docs):
        grouped.setdefault(find(d), []).append(d)
    return sorted(grouped.values(), key=lambda g: g[0])


def _pieces(text: str) -> list[list[int]]:
    """Line ranges of the doc cut at each ``##`` heading outside code fences; the text before
    the first heading joins the first piece. One piece when there are fewer than two."""
    lines = text.splitlines()
    heads: list[int] = []
    fence = ""
    for number, line in enumerate(lines, 1):
        marker = line.lstrip()[:3]
        if marker in ("```", "~~~"):
            fence = "" if fence == marker else (fence or marker)
        elif not fence and line.startswith("## "):
            heads.append(number)
    if len(heads) < 2:
        return [[1, len(lines)]]
    starts = [1, *heads[1:]]
    return [[s, starts[i + 1] - 1 if i + 1 < len(starts) else len(lines)]
            for i, s in enumerate(starts)]


def _clip(ranges: Sequence[Sequence[int]], piece: Sequence[int]) -> list[list[int]]:
    clipped = [[max(r[0], piece[0]), min(r[1], piece[1])] for r in ranges]
    return [r for r in clipped if r[0] <= r[1]]


def build(review: Mapping[str, Sequence[Sequence[int]]], anchors: Iterable[Anchor],
          hunks: Mapping[str, list[Hunk]], mode: str, texts: Mapping[str, str],
          unit_lines: int, affected: Mapping[str, Any] | None = None) -> list[Unit]:
    """Pack the docs of ``review`` into review units (ids ``u001``...). ``affected`` is
    ``changes.json``'s map, read on a later run for the ``missing`` definitions."""
    found = affected or {}
    mine = [a for a in anchors if a["doc"] in review]
    by_doc: dict[str, list[Anchor]] = {}
    for a in mine:
        by_doc.setdefault(a["doc"], []).append(a)

    def entry(doc: str, piece: Sequence[int] | None = None) -> _Part:
        ranges = [[r[0], r[1]] for r in review[doc]]
        doc_anchors = by_doc.get(doc, [])
        if piece is not None:
            ranges = _clip(ranges, piece)
            doc_anchors = [a for a in doc_anchors if _in_ranges(a["line"], ranges)]
        return {"doc": doc, "ranges": ranges}, doc_anchors

    def unit_of(parts: Sequence[_Part]) -> Unit:
        docs = [p[0] for p in parts]
        unit_anchors = [a for p in parts for a in p[1]]
        return {"id": "", "docs": docs, "anchors": unit_anchors,
                "hunks": _hunks_for(unit_anchors, hunks) if mode != "first" else [],
                "size": _size(docs, unit_anchors, hunks, mode, found)}

    units: list[Unit] = []
    current: list[_Part] = []
    current_size = 0

    def flush() -> None:
        nonlocal current, current_size
        if current:
            units.append(unit_of(current))
        current, current_size = [], 0

    for group in _groups(sorted(review), mine):
        parts = [entry(d) for d in group]
        size = unit_of(parts)["size"]
        if size > unit_lines:
            flush()
            if len(group) == 1 and group[0] in texts:
                for piece in _pieces(texts[group[0]]):
                    sub = entry(group[0], piece)
                    if sub[0]["ranges"]:
                        units.append(unit_of([sub]))
            else:
                units.append(unit_of(parts))
            continue
        if current and current_size + size > unit_lines:
            flush()
        current.extend(parts)
        current_size += size
    flush()
    for number, unit in enumerate(units, 1):
        unit["id"] = f"u{number:03d}"
    return units


def order_for_cap(units: Sequence[Unit]) -> list[Unit]:
    """README/CLAUDE/AGENTS units first, then more anchors first, then by id."""
    def root_doc(unit: Unit) -> bool:
        return any(d["doc"].rsplit("/", 1)[-1].lower() in ROOT_DOCS for d in unit["docs"])

    return sorted(units, key=lambda u: (not root_doc(u), -len(u["anchors"]), u["id"]))


def run(root: Path, workdir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Build the review units from ``changes.json`` and ``anchors.json`` (doc texts are read
    from ``root``); write ``units.json``."""
    loaded: dict[str, Any] = {}
    for name, step in (("changes", "dd_changes"), ("anchors", "dd_anchors"),
                       ("inventory", "dd_inventory")):
        path = workdir / f"{name}.json"
        if not path.is_file():
            raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
        loaded[name] = read_json(path)
    changes = loaded["changes"]
    texts: dict[str, str] = {}
    for doc in changes["review"]:
        try:
            texts[doc] = (root / doc).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    units = build(changes["review"], loaded["anchors"]["anchors"], changes["hunks"],
                  changes["mode"], texts, int(config["unit_lines"]),
                  changes.get("affected", {}))
    ordered = order_for_cap(units)
    cap = int(config["caps"]["review"])
    result = {"units": sorted(ordered[:cap], key=lambda u: u["id"]),
              "unchecked": [u["id"] for u in ordered[cap:]]}
    write_json(workdir / "units.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Group the docs to review into review units.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    config, _ = load_config(args.repo)
    try:
        run(args.repo, args.workdir, config)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
