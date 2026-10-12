"""Gap detection and targets: which scanned names the docs miss, and where to add them
(spec 8.2, 8.3) -> gaps.json.

A name is **documented** when it appears in any in-scope doc, fences included. Both sides are
normalised first: ``-`` and ``.`` inside word-like tokens become ``_`` (a ``--flag`` keeps its
dashes), ``mcp__<server>__`` prefixes go, and route placeholders ``<x>``, ``{x}`` and ``:x``
(after a ``/``) become ``{}``. A single-word name matches as a whole word (a flag when preceded
by the start, whitespace, a backtick, ``(``, ``[`` or ``|`` and not followed by a word
character or dash); a name with spaces matches as a whole phrase (word boundaries at both
ends). Matching is case-sensitive. An MCP ``param`` is documented only inside a section
whose heading names its tool; a section runs to the next heading of the same or higher level.

A **list** is a table (data rows) or a top-level bullet or numbered list whose items have a
subject (a row's first cell, an item's first code span) naming scanned names; it qualifies at
``LIST_MIN_SUBJECTS`` subjects of one kind. Flag and param lists are scoped to the parent the
nearest heading above names, else to the parents of the matched names; other kinds are
unscoped (``scope`` null). A list is **complete** when it holds at least ``COMPLETE_RATIO`` of
the non-hidden names of its kind in its scope.

``gaps.json`` is ``{"candidates", "lists", "gaps", "targets", "no_home", "unchecked"}``;
``targets`` holds only the ``caps.gaps`` target docs with the most gaps (ties by path) and
``unchecked`` the rest. Each gap is ``{"name", "kind", "parent", "file", "line", "gap_kind",
"target_doc", "target_line", "reason"}``: ``gap_kind`` is ``undocumented`` or
``missing-from-list``; ``reason`` is ``missing-from-list``, ``complete-list``, ``any-list``,
``most-names`` or ``no-home``. ``target_line`` is a list target's last line (insert after),
else the line of the best section's heading, or 1.

A documented name missing from complete lists gets one ``missing-from-list`` gap per such list,
each targeting that list (spec 8.2 item 2); an undocumented name gets one gap and one target.
On a later run a candidate must also lie in a changed file (``changes.json``), since
``names_then`` covers only those files.
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, TypedDict

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import norm
from dd_md_scan import Scan, scan
from dd_patterns import Name

LIST_MIN_SUBJECTS = 3
COMPLETE_RATIO = 0.5
DEFAULT_GAP_CAP = 15
SCOPED_KINDS = frozenset({"flag", "param"})
FLAG_LEAD = "`(|["
NO_HOME = "no-home"

_MCP_TEXT = re.compile(r"mcp__[\w-]+?__(?=\w)")
_PLACEHOLDER = re.compile(r"(?<=/)(?::[A-Za-z_]\w*|<[^<>/\s]*>|\{[^{}/\s]*\})")
_TOKEN = re.compile(r"(?<![\w-])-{1,2}\w[\w-]*|\w+(?:[-.]\w+)+")
_SUBJECT_SPLIT = re.compile(r"[\s,;|=]+")


class List(TypedDict):
    doc: str
    line_start: int
    line_end: int
    kind: str
    scope: list[str | None] | None
    subjects: list[str]
    complete: bool


class Gap(TypedDict):
    name: str
    kind: str
    parent: str | None
    file: str
    line: int
    gap_kind: str
    target_doc: str | None
    target_line: int | None
    reason: str


def _dashes(match: re.Match[str]) -> str:
    token = match.group(0)
    return token if token.startswith("-") else token.replace("-", "_").replace(".", "_")


def normalise_text(text: str) -> str:
    """The comparison form of doc text; line breaks and their count are kept."""
    text = _MCP_TEXT.sub("", text)
    text = _PLACEHOLDER.sub("{}", text)
    return _TOKEN.sub(_dashes, text)


def _norm_as(text: str, kind: str) -> str:
    """Normalise a name of ``kind``; a flag (``-v`` or ``--verbose``) keeps its dashes."""
    if kind == "flag" and text.startswith("-"):
        return text
    return norm(text, routes=kind == "route")


def _norm(name: Name) -> str:
    return _norm_as(name["name"], name["kind"])


def _pattern(norm_name: str, kind: str) -> re.Pattern[str]:
    body = re.escape(norm_name)
    if kind == "flag" and norm_name.startswith("-"):
        lead = "(?:^|(?<=[\\s" + re.escape(FLAG_LEAD) + "]))"
        return re.compile(lead + body + r"(?![\w-])", re.MULTILINE)
    return re.compile(r"(?<!\w)" + body + r"(?!\w)")


@dataclass(frozen=True)
class _Heading:
    line: int
    level: int
    text: str  # normalised


@dataclass
class _Doc:
    path: str
    ntext: str
    scan: Scan
    headings: list[_Heading]
    newlines: list[int]

    def line_of(self, offset: int) -> int:
        return bisect.bisect_left(self.newlines, offset) + 1


def _prepare(texts: Mapping[str, str]) -> list[_Doc]:
    docs: list[_Doc] = []
    for path in sorted(texts):
        text = texts[path]
        ntext = normalise_text(text)
        parsed = scan(text)
        headings = [_Heading(b.line_start, b.level or 1, normalise_text(b.text or ""))
                    for b in parsed.blocks if b.kind == "heading"]
        newlines = [i for i, ch in enumerate(ntext) if ch == "\n"]
        docs.append(_Doc(path, ntext, parsed, headings, newlines))
    return docs


def _names_in(heading: str, norm_name: str, kind: str) -> bool:
    return _pattern(norm_name, kind).search(heading) is not None


def _tool_sections(doc: _Doc, tool: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    last = len(doc.ntext.split("\n")) + 1
    for i, heading in enumerate(doc.headings):
        if not _names_in(heading.text, tool, "tool"):
            continue
        end = last
        for later in doc.headings[i + 1:]:
            if later.level <= heading.level:
                end = later.line - 1
                break
        spans.append((heading.line, end))
    return spans


def _match_lines(name: Name, doc: _Doc) -> list[int]:
    pattern = _pattern(_norm(name), name["kind"])
    lines = [doc.line_of(m.start()) for m in pattern.finditer(doc.ntext)]
    if name["kind"] == "param" and name["parent"]:
        spans = _tool_sections(doc, norm(name["parent"]))
        lines = [n for n in lines if any(a <= n <= b for a, b in spans)]
    return lines


def _documented(name: Name, docs: Sequence[_Doc]) -> bool:
    return any(_match_lines(name, doc) for doc in docs)


def documented(name: Name, texts: Mapping[str, str]) -> bool:
    """Whether any of the doc texts documents the name (spec 8.2)."""
    return _documented(name, _prepare(texts))


# -- lists ----------------------------------------------------------------------------------


@dataclass
class _Row:
    line: int
    subject: str
    is_code: bool


def _cell_text(line: str) -> str:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    return text.split("|", 1)[0].strip()


def _first_code(parsed: Scan, block: int, cell: int | None) -> str | None:
    for inline in parsed.inlines:
        if inline.block == block and inline.kind == "code" and inline.cell == cell:
            return inline.text
    return None


def _groups(parsed: Scan) -> list[tuple[int, int, list[_Row]]]:
    """Each table and each top-level list as ``(first line, last line, rows)``."""
    groups: list[tuple[int, int, list[_Row]]] = []
    table: list[int] = []

    def flush() -> None:
        if table and any(parsed.blocks[i].kind == "table_delim" for i in table):
            data = [i for i in table if parsed.blocks[i].kind == "table_row"][1:]
            rows: list[_Row] = []
            for i in data:
                block = parsed.blocks[i]
                code = _first_code(parsed, i, 0)
                if code is not None:
                    rows.append(_Row(block.line_start, code, True))
                else:
                    first = _cell_text(parsed.lines[block.line_start - 1])
                    if first:
                        rows.append(_Row(block.line_start, first, False))
            groups.append((parsed.blocks[table[0]].line_start,
                           parsed.blocks[table[-1]].line_end, rows))
        table.clear()

    items: dict[int, list[int]] = {}
    for i, block in enumerate(parsed.blocks):
        if block.kind in ("table_row", "table_delim"):
            if table and parsed.blocks[table[-1]].line_end + 1 != block.line_start:
                flush()
            table.append(i)
            continue
        flush()
        if block.kind == "list_item" and block.parent is None and block.list_id is not None:
            items.setdefault(block.list_id, []).append(i)
    flush()
    for members in items.values():
        rows = []
        for i in members:
            code = _first_code(parsed, i, None)
            if code is not None:
                rows.append(_Row(parsed.blocks[i].line_start, code, True))
        groups.append((parsed.blocks[members[0]].line_start,
                       max(parsed.blocks[i].line_end for i in members), rows))
    return groups


def _variants(row: _Row) -> list[str]:
    found = [row.subject]
    if row.is_code:
        found += [t for t in _SUBJECT_SPLIT.split(row.subject) if t]
    return found


def _by_norm(names: Sequence[Name]) -> dict[tuple[str, str], list[Name]]:
    index: dict[tuple[str, str], list[Name]] = {}
    for name in names:
        index.setdefault((name["kind"], _norm(name)), []).append(name)
    return index


def _match_row(row: _Row, index: Mapping[tuple[str, str], list[Name]],
               kinds: Sequence[str]) -> list[tuple[str, str]]:
    """The ``(kind, normalised subject)`` keys the row's subject matches."""
    for variant in _variants(row):
        keys = [(kind, _norm_as(variant, kind)) for kind in kinds]
        hits = [key for key in keys if key in index]
        if hits:
            return hits
    return []


def _in_scope(name: Name, scope: Sequence[str | None] | None) -> bool:
    return scope is None or name["parent"] in scope


def _heading_before(doc: _Doc, line: int) -> _Heading | None:
    before = [h for h in doc.headings if h.line < line]
    return before[-1] if before else None


def _named_parents(heading: _Heading | None, parents: Sequence[str]) -> list[str | None]:
    if heading is None:
        return []
    return [p for p in sorted(parents) if _names_in(heading.text, norm(p), "tool")]


def _build_lists(docs: Sequence[_Doc], names: Sequence[Name]) -> list[List]:
    index = _by_norm(names)
    kinds = sorted({n["kind"] for n in names})
    found: list[List] = []
    for doc in docs:
        for first, last, rows in _groups(doc.scan):
            hits: dict[str, list[tuple[str, tuple[str, str]]]] = {}
            for row in rows:
                for key in _match_row(row, index, kinds):
                    shown = next(v for v in _variants(row)
                                 if (key[0], _norm_as(v, key[0])) == key)
                    hits.setdefault(key[0], []).append((shown, key))
            if not hits:
                continue
            kind = max(sorted(hits), key=lambda k: len(hits[k]))
            if len(hits[kind]) < LIST_MIN_SUBJECTS:
                continue
            subjects = [shown for shown, _ in hits[kind]]
            held = {key[1] for _, key in hits[kind]}
            matched = [n for key in {k for _, k in hits[kind]} for n in index[key]]
            scope: list[str | None] | None = None
            if kind in SCOPED_KINDS:
                parents = sorted({n["parent"] for n in names
                                  if n["kind"] == kind and n["parent"]})
                scope = _named_parents(_heading_before(doc, first), parents)
                if not scope:
                    scope = sorted({n["parent"] for n in matched}, key=lambda p: (p is None, p))
            pool = [n for n in names if n["kind"] == kind and not n["hidden"]
                    and _in_scope(n, scope)]
            covered = [n for n in pool if _norm(n) in held]
            complete = bool(pool) and len(covered) >= COMPLETE_RATIO * len(pool)
            found.append({"doc": doc.path, "line_start": first, "line_end": last, "kind": kind,
                          "scope": scope, "subjects": subjects, "complete": complete})
    return found


def lists(texts: Mapping[str, str], names: Sequence[Name]) -> list[List]:
    """Lists in the docs that name at least ``LIST_MIN_SUBJECTS`` scanned names of one kind."""
    return _build_lists(_prepare(texts), names)


# -- candidates and gaps -----------------------------------------------------------------------


def _key(name: Name) -> tuple[str, str, str | None]:
    return (name["kind"], name["name"], name["parent"])


def candidates(names: Sequence[Name], names_then: Sequence[Name] | None,
               changed_files: Sequence[str] | None, ok: Sequence[str]) -> list[Name]:
    """Non-hidden names not matching ``undocumented_ok``. On a later run (``names_then`` not
    null) only names in a changed file whose ``(kind, name, parent)`` is absent from
    ``names_then``, which covers the changed files only (spec 6.3)."""
    changed = None if names_then is None else set(changed_files or [])
    before = None if names_then is None else {_key(n) for n in names_then}
    seen: set[tuple[str, str, str | None]] = set()
    result: list[Name] = []
    for name in names:
        key = _key(name)
        if name["hidden"] or key in seen:
            continue
        if any(fnmatchcase(text, pattern) for pattern in ok
               for text in (name["name"], norm(name["name"]), _norm(name))):
            continue
        if before is not None and (key in before or name["file"] not in (changed or set())):
            continue
        seen.add(key)
        result.append(name)
    return result


def _held(name: Name, found: List) -> bool:
    return _norm(name) in {_norm_as(s, name["kind"]) for s in found["subjects"]}


def _list_target(name: Name, found: Sequence[List], complete: bool) -> List | None:
    fits = [x for x in found if x["kind"] == name["kind"] and _in_scope(name, x["scope"])
            and (x["complete"] or not complete)]
    if not fits:
        return None
    return min(fits, key=lambda x: (-len(x["subjects"]), x["doc"], x["line_start"]))


def _siblings(name: Name, names: Sequence[Name]) -> list[Name]:
    if name["kind"] in SCOPED_KINDS and name["parent"] is not None:
        same = [n for n in names if n["parent"] == name["parent"]]
    else:
        same = [n for n in names if n["file"] == name["file"]]
    return [n for n in same if n["kind"] == name["kind"] and _key(n) != _key(name)]


def _best_section(name: Name, names: Sequence[Name],
                  docs: Sequence[_Doc]) -> tuple[_Doc, int] | None:
    siblings = {_key(n): n for n in _siblings(name, names)}.values()
    best: tuple[int, int, str] | None = None
    chosen: tuple[_Doc, int] | None = None
    for doc in docs:
        counts: dict[int, set[tuple[str, str, str | None]]] = {}
        total = 0
        starts = [h.line for h in doc.headings]
        for other in siblings:
            lines = _match_lines(other, doc)
            if not lines:
                continue
            total += 1
            for line in lines:
                at = bisect.bisect_right(starts, line) - 1
                counts.setdefault(starts[at] if at >= 0 else 1, set()).add(_key(other))
        if not total:
            continue
        rank = (-total, len(doc.path), doc.path)
        if best is None or rank < best:
            best = rank
            top = max(counts.items(), key=lambda kv: (len(kv[1]), -kv[0]))
            chosen = (doc, top[0])
    return chosen


def _aim(gap: Gap, doc: str, line: int, reason: str, gap_kind: str = "undocumented") -> None:
    gap["gap_kind"] = gap_kind
    gap["target_doc"] = doc
    gap["target_line"] = line
    gap["reason"] = reason


def gaps(names: Sequence[Name], texts: Mapping[str, str], found: Sequence[List],
         names_then: Sequence[Name] | None, ok: Sequence[str],
         changed_files: Sequence[str] | None = None) -> list[Gap]:
    """The gaps among the candidates, each with its target (spec 8.2, 8.3)."""
    docs = _prepare(texts)
    result: list[Gap] = []
    for name in candidates(names, names_then, changed_files, ok):
        base: Gap = {"name": name["name"], "kind": name["kind"], "parent": name["parent"],
                     "file": name["file"], "line": name["line"], "gap_kind": "undocumented",
                     "target_doc": None, "target_line": None, "reason": NO_HOME}
        if _documented(name, docs):
            missing = [x for x in found if x["complete"] and x["kind"] == name["kind"]
                       and _in_scope(name, x["scope"]) and not _held(name, x)]
            if not missing:
                continue
            for target in sorted(missing, key=lambda x: (x["doc"], x["line_start"])):
                each = base.copy()
                _aim(each, target["doc"], target["line_end"], "missing-from-list",
                     "missing-from-list")
                result.append(each)
            continue
        else:
            listed = _list_target(name, found, True)
            reason = "complete-list"
            if listed is None:
                listed, reason = _list_target(name, found, False), "any-list"
            if listed is not None:
                _aim(base, listed["doc"], listed["line_end"], reason)
            else:
                section = _best_section(name, names, docs)
                if section is not None:
                    _aim(base, section[0].path, section[1], "most-names")
        result.append(base)
    return result


def split_by_cap(found: Sequence[Gap], cap: int) -> tuple[dict[str, list[Gap]], list[str]]:
    """Group gaps by target doc; keep the ``cap`` docs with the most gaps (ties by path) and
    list the others as unchecked."""
    by_doc: dict[str, list[Gap]] = {}
    for gap in found:
        if gap["target_doc"] is not None:
            by_doc.setdefault(gap["target_doc"], []).append(gap)
    order = sorted(by_doc, key=lambda d: (-len(by_doc[d]), d))
    return ({d: by_doc[d] for d in sorted(order[:cap])}, sorted(order[cap:], key=lambda d: (
        -len(by_doc[d]), d)))


def run(root: Path, workdir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Read ``patterns.json`` and ``inventory.json``; write ``gaps.json``."""
    for step, filename in (("dd_patterns", "patterns.json"), ("dd_inventory", "inventory.json")):
        if not (workdir / filename).is_file():
            raise StepError(f"{filename} is missing; run {step} first", EXIT_MISSING)
    patterns = read_json(workdir / "patterns.json")
    inventory = read_json(workdir / "inventory.json")
    if not (workdir / "changes.json").is_file():
        raise StepError("changes.json is missing; run dd_changes first", EXIT_MISSING)
    changed_files: list[str] = list(read_json(workdir / "changes.json").get("changed_files", []))
    names: list[Name] = patterns["names"]
    names_then: list[Name] | None = patterns.get("names_then")
    texts: dict[str, str] = {}
    for path in inventory.get("docs", []):
        try:
            texts[path] = (root / path).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    ok: list[str] = list(config.get("undocumented_ok", []))
    cap = int(config.get("caps", {}).get("gaps", DEFAULT_GAP_CAP))
    found_lists = lists(texts, names)
    found = gaps(names, texts, found_lists, names_then, ok, changed_files)
    targets, unchecked = split_by_cap(found, cap)
    lookup = {_key(n): n for n in names}
    result: dict[str, Any] = {
        "candidates": candidates(names, names_then, changed_files, ok),
        "lists": found_lists,
        "gaps": found,
        "targets": targets,
        "no_home": [lookup[(g["kind"], g["name"], g["parent"])] for g in found
                    if g["target_doc"] is None],
        "unchecked": unchecked,
    }
    write_json(workdir / "gaps.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find user-facing names the docs miss and pick a target doc for each.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from dd_config import load_config
        config, _ = load_config(args.repo)
        run(args.repo, args.workdir, config)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
