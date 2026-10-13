"""The README writer's output at ``verify``: the citation check, the statements and their
verifier batches (phase B spec 6.4, 6.5, 7).

- ``structural_problems(output, sheets, readme_lines)`` is spec 6.4's invalid rule, run by
  ``dd_dispatch._problems`` so a structurally bad output takes the exit-3 retry: the first line
  is not a level-one heading; ``text`` has more than ``readme_lines`` lines; a line outside
  headings, blank lines and fence markers is in no claim or in two; a claim cites nothing or
  an id not in ``sheets.json``. Claim ranges are read within the text's lines.
- ``check(output, sheets, readme_lines)`` returns those problems, or none and the
  ``readme.json`` content ``{"text", "claims", "statements", "cites_added",
  "cited_unnamed"}``. Repairs: a claim whose lines name a surface entry in an inline-code span
  without citing it gets the id appended (``cites_added``; a span naming several entries of
  one name, a flag of two commands, adds them all unless the claim cites one); a cited surface
  entry none of the claim's lines name is counted (``cited_unnamed``) and kept.
- Statements (spec 6.5), ids ``r-s001``... in README order: a list item (a line ``- ``,
  ``* ``, ``+ `` or ``1. `` at indentation 0, plus the lines under it that start with
  whitespace, blank lines between them and a fence whose opening marker is indented, to its
  closing marker, included), a table row (a line starting with ``|``, not a table's first
  row, the header, nor its second when that is a ``|---|`` separator), a paragraph
  (consecutive other non-blank lines), a fence (from its opening marker to its closing one,
  or the text's end). Headings, blank lines, table headers and separators are not
  statements. Each carries ``start_line``,
  ``end_line``, ``section`` (the nearest heading above it, ``""`` before the first), ``kind``
  (``item``, ``row``, ``paragraph``, ``fence``), ``text``, ``claims`` (the indexes of the
  claims its lines lie in), ``cites`` (those claims' surface entries its own lines name, plus
  all their behaviours, sorted) and ``prereject``: ``names hidden <name>`` when a span of its
  lines resolves to surface entries that are all hidden, or to a hidden one its claims cited
  as the writer gave them (before the repair), else ``guarantee word`` when its lines outside
  fences hold one outside their inline-code spans (``dd_checks._guarantees``), else null.
- Naming is spec 6.4's loose match: the entry's name without a ``$`` prefix equals a span
  (also without ``$`` and a trailing ``()``) by ``dd_defindex.norm``, or occurs in the lines
  as text.
- ``check_step(root, workdir, config, failed)``: with an empty ``plan-readme.json`` or a
  writer output that failed validation (its entry in ``failed``) it writes ``readme.json`` as
  ``{"invalid": [...]}`` (``no writer output`` when there is no output at all) and returns
  None. Otherwise it writes ``readme.json``, appends the README's ``create`` edit to
  ``edits.json``'s ``edits`` and a ``readme-rejected`` Human-decision item per pre-rejected
  statement to its ``human`` (kept sorted), and appends the statement batches to
  ``plan-verify.json`` (``dd_dispatch.plan_verify_readme``).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import dd_dispatch
from dd_checks import _guarantees
from dd_common import read_json, write_json
from dd_defindex import norm

README = "README.md"
NO_OUTPUT = "no writer output"

_LINE_SPLIT = re.compile(r"\r?\n")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ITEM = re.compile(r"^([-*+]|\d+\.)\s")
_SEPARATOR = re.compile(r"\|[\s:|-]*-[\s:|-]*")
_SPAN = re.compile(r"`([^`\n]+)`")

Entry = Mapping[str, Any]


def _lines(text: str) -> list[str]:
    lines = _LINE_SPLIT.split(text)
    return lines[:-1] if lines and lines[-1] == "" else lines


def _fence_tags(lines: Sequence[str]) -> list[str]:
    """Per line: ``marker`` (a fence's opening or closing line), ``code`` (inside a fence) or
    ``""``. A fence closes at a line of its own character, at least as long, and nothing else;
    an unclosed fence runs to the end."""
    tags = [""] * len(lines)
    i = 0
    while i < len(lines):
        opening = _FENCE.match(lines[i])
        if opening is None:
            i += 1
            continue
        tags[i] = "marker"
        fence = opening.group(1)
        closing = re.compile(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$")
        i += 1
        while i < len(lines) and not closing.match(lines[i]):
            tags[i] = "code"
            i += 1
        if i < len(lines):
            tags[i] = "marker"
            i += 1
    return tags


def _heading(line: str) -> re.Match[str] | None:
    return _HEADING.match(line)


def _needs_claim(line: str, tag: str) -> bool:
    if not line.strip() or tag == "marker":
        return False
    return tag == "code" or _heading(line) is None


# ---------------------------------------------------------------- names

def _keys(name: str) -> set[str]:
    bare = name.strip().lstrip("$")
    if bare.endswith("()"):
        bare = bare[:-2]
    return {norm(bare), norm(bare, routes=True)} if bare else set()


class _Index:
    """The ids of ``sheets.json`` and its surface entries by name key."""

    def __init__(self, sheets: Mapping[str, Any]) -> None:
        self.ids: dict[str, Entry] = {}
        self.by_key: dict[str, list[Entry]] = {}
        for aid in sorted(sheets.get("sheets", {})):
            sheet = sheets["sheets"][aid]
            for entry in sheet.get("surface", []):
                self.ids[str(entry["id"])] = entry
                for key in _keys(str(entry["name"])):
                    self.by_key.setdefault(key, []).append(entry)
            for behaviour in sheet.get("behaviours", []):
                self.ids[str(behaviour["id"])] = behaviour

    def spans(self, text: str) -> list[list[Entry]]:
        """Per inline-code span of ``text`` that names surface entries, in order, those
        entries (each once)."""
        out: list[list[Entry]] = []
        for span in _SPAN.findall(text):
            found: dict[str, Entry] = {}
            for key in sorted(_keys(span)):
                for entry in self.by_key.get(key, []):
                    found.setdefault(str(entry["id"]), entry)
            if found:
                out.append(list(found.values()))
        return out


def _span_keys(text: str) -> set[str]:
    return {key for span in _SPAN.findall(text) for key in _keys(span)}


def _named(entry: Entry, text: str, keys: set[str]) -> bool:
    bare = str(entry["name"]).strip().lstrip("$")
    return bool(_keys(bare) & keys) or (bool(bare) and bare in text)


def _is_surface(entry: Entry | None) -> bool:
    return entry is not None and "name" in entry


# ---------------------------------------------------------------- the check

def _claim_lines(claim: Mapping[str, Any], count: int) -> range:
    return range(max(1, int(claim["start_line"])), min(count, int(claim["end_line"])) + 1)


def structural_problems(output: Mapping[str, Any], sheets: Mapping[str, Any],
                        readme_lines: int) -> list[str]:
    """Spec 6.4's invalid rule on a well-formed writer output; empty when none applies."""
    lines = _lines(str(output["text"]))
    problems: list[str] = []
    first = _heading(lines[0]) if lines else None
    if first is None or len(first.group(1)) != 1:
        problems.append("the first line is not a level-one heading")
    if len(lines) > readme_lines:
        problems.append(f"the text has {len(lines)} lines, more than readme_lines "
                        f"{readme_lines}")
    owners: dict[int, list[int]] = {}
    for n, claim in enumerate(output["claims"]):
        for covered in _claim_lines(claim, len(lines)):
            owners.setdefault(covered, []).append(n)
    for number, (line, tag) in enumerate(zip(lines, _fence_tags(lines), strict=True), 1):
        if not _needs_claim(line, tag):
            continue
        own = owners.get(number, [])
        if not own:
            problems.append(f"line {number} is in no claim: {line[:60]!r}")
        elif len(own) > 1:
            problems.append(f"line {number} is in claims "
                            f"{', '.join(str(o) for o in own[:-1])} and {own[-1]}")
    ids = _Index(sheets).ids
    for n, claim in enumerate(output["claims"]):
        if not claim["cites"]:
            problems.append(f"claims[{n}] cites nothing")
        problems += [f"claims[{n}] cites {cid}, which is not in sheets.json"
                     for cid in claim["cites"] if cid not in ids]
    return problems


def _repair(claims: list[dict[str, Any]], lines: Sequence[str],
            index: _Index) -> tuple[int, int]:
    """Add the surface entries a claim's spans name to its cites; count the cited surface
    entries its lines do not name. Returns ``(cites_added, cited_unnamed)``."""
    added = unnamed = 0
    for claim in claims:
        text = "\n".join(lines[n - 1] for n in _claim_lines(claim, len(lines)))
        cites: list[str] = claim["cites"]
        for entries in index.spans(text):
            if any(str(e["id"]) in cites for e in entries):
                continue
            cites += [str(e["id"]) for e in entries]
            added += len(entries)
        keys = _span_keys(text)
        unnamed += sum(1 for cid in cites if _is_surface(index.ids.get(cid))
                       and not _named(index.ids[cid], text, keys))
    return added, unnamed


def _fence_end(tags: Sequence[str], start: int) -> int:
    """The index of the last line of the fence opening at ``start``: its closing marker, or
    the last line of an unclosed fence."""
    end = start + 1
    while end < len(tags) and tags[end] == "code":
        end += 1
    return end if end < len(tags) and tags[end] == "marker" else end - 1


def _indented(line: str) -> bool:
    return bool(line.strip()) and line[0] in " \t"


def _indented_next(lines: Sequence[str], start: int) -> bool:
    """The first non-blank line from ``start`` on starts with whitespace."""
    j = start
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and _indented(lines[j])


def _blocks(lines: Sequence[str], tags: Sequence[str]) -> list[dict[str, Any]]:
    """The statements of spec 6.5 as ``{"start_line", "end_line", "section", "kind"}``. An
    open item takes every indented line under it, blank lines between them and a fence
    whose opening marker is indented (to its closing marker) included."""
    out: list[dict[str, Any]] = []
    section = ""
    current: dict[str, Any] | None = None  # the open item or paragraph
    table_row = -1  # the index of a line within its table, -1 outside one
    i = 0
    while i < len(lines):
        line, number = lines[i], i + 1
        in_item = current is not None and current["kind"] == "item"
        if in_item and current is not None and _indented(line):
            last = _fence_end(tags, i) if tags[i] == "marker" else i
            current["end_line"] = last + 1
            i = last + 1
            continue
        if tags[i] == "marker":  # a fence opens: it runs to its closing marker
            last = _fence_end(tags, i)
            out.append({"start_line": number, "end_line": last + 1, "section": section,
                        "kind": "fence"})
            current, table_row, i = None, -1, last + 1
            continue
        i += 1
        if not line.strip():
            if not (in_item and _indented_next(lines, i)):  # an item goes on when indented
                current, table_row = None, -1
            continue
        heading = _heading(line)
        if heading is not None:
            section = (heading.group(2) or "").strip()
            current, table_row = None, -1
            continue
        if line.startswith("|"):
            current = None
            table_row += 1
            if table_row == 0 or (table_row == 1 and _SEPARATOR.fullmatch(line.strip())):
                continue
            out.append({"start_line": number, "end_line": number, "section": section,
                        "kind": "row"})
            continue
        table_row = -1
        if _ITEM.match(line):
            current = {"start_line": number, "end_line": number, "section": section,
                       "kind": "item"}
            out.append(current)
        elif current is not None and (current["kind"] == "paragraph" or line[0] in " \t"):
            current["end_line"] = number
        else:
            current = {"start_line": number, "end_line": number, "section": section,
                       "kind": "paragraph"}
            out.append(current)
    return out


def _prereject(text: str, prose: str, explicit: set[str], index: _Index) -> str | None:
    """``names hidden <name>`` when a span resolves to entries that are all hidden, or to a
    hidden entry the statement's claims cited themselves (before the repair); else
    ``guarantee word`` when ``prose`` (the lines outside fences, spans dropped) holds one."""
    for entries in index.spans(text):
        hidden = [e for e in entries if e.get("hidden")]
        cited = [e for e in hidden if str(e["id"]) in explicit]
        if cited or (hidden and len(hidden) == len(entries)):
            return f"names hidden {(cited or hidden)[0]['name']}"
    if _guarantees(_SPAN.sub("", prose)):
        return "guarantee word"
    return None


def _statements(lines: Sequence[str], claims: Sequence[Mapping[str, Any]],
                explicit: Sequence[set[str]], index: _Index) -> list[dict[str, Any]]:
    """The statements with their cites and pre-rejections; ``explicit`` holds each claim's
    cites as the writer gave them."""
    tags = _fence_tags(lines)
    statements = []
    for number, block in enumerate(_blocks(lines, tags), 1):
        start, end = int(block["start_line"]), int(block["end_line"])
        text = "\n".join(lines[start - 1:end])
        prose = "\n".join(lines[n - 1] for n in range(start, end + 1) if not tags[n - 1])
        keys = _span_keys(text)
        within = [n for n, claim in enumerate(claims)
                  if int(claim["start_line"]) <= end and int(claim["end_line"]) >= start]
        cites = {cid for n in within for cid in claims[n]["cites"]
                 if not _is_surface(index.ids.get(cid)) or _named(index.ids[cid], text, keys)}
        written = {cid for n in within for cid in explicit[n]}
        statements.append({"id": f"r-s{number:03d}", **block, "text": text, "claims": within,
                           "cites": sorted(cites),
                           "prereject": _prereject(text, prose, written, index)})
    return statements


def check(output: Mapping[str, Any], sheets: Mapping[str, Any],
          readme_lines: int) -> tuple[list[str], dict[str, Any]]:
    """The invalid problems of a well-formed writer output, or none and the ``readme.json``
    content: claims repaired, statements split, cites and pre-rejections set."""
    problems = structural_problems(output, sheets, readme_lines)
    if problems:
        return problems, {}
    index = _Index(sheets)
    text = str(output["text"])
    lines = _lines(text)
    claims = [{**claim, "cites": [str(c) for c in claim["cites"]]}
              for claim in output["claims"]]
    explicit = [set(claim["cites"]) for claim in claims]  # before the repair adds any
    added, unnamed = _repair(claims, lines, index)
    return [], {"text": text, "claims": claims,
                "statements": _statements(lines, claims, explicit, index),
                "cites_added": added, "cited_unnamed": unnamed}


# ---------------------------------------------------------------- the verify step

def _create_edit(sheets: Mapping[str, Any], statements: Sequence[Any]) -> dict[str, Any]:
    return {"id": "r001", "doc": README, "start_line": 1, "end_line": 1, "old": "", "new": "",
            "type": "create", "claim": f"readme from {len(sheets.get('sheets', {}))} sheets",
            "evidence": [], "subject": None, "source": "readme", "status": "kept",
            "check": None, "human_kind": None, "reason": None, "statements": len(statements)}


def _rejected(statements: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"doc": README, "line": int(s["start_line"]), "kind": "readme-rejected",
             "text": str(s["text"]).split("\n", 1)[0], "evidence": [str(s["prereject"])]}
            for s in statements if s.get("prereject")]


def _invalid(workdir: Path, problems: list[str]) -> None:
    write_json(workdir / "readme.json", {"invalid": problems})


def check_step(root: Path, workdir: Path, config: Mapping[str, Any],
               failed: frozenset[str]) -> dict[str, Any] | None:
    """Check the writer's output and plan its statements' verifier batches; None when there
    is no README to propose."""
    plan: list[dd_dispatch.PlanEntry] = dd_dispatch._require(workdir, "plan-readme.json",
                                                             "compose")
    readme_lines = int(config["readme_lines"])
    if not plan or not Path(plan[0]["output"]).is_file():
        _invalid(workdir, [NO_OUTPUT])
        return None
    entry = plan[0]
    if entry["id"] in failed:
        _invalid(workdir, dd_dispatch._problems(workdir, entry, readme_lines=readme_lines)
                 or ["invalid writer output"])
        return None
    sheets = dd_dispatch._require(workdir, "sheets.json", "compose")
    problems, readme = check(read_json(Path(entry["output"])), sheets, readme_lines)
    if problems:
        _invalid(workdir, problems)
        return None
    write_json(workdir / "readme.json", readme)
    edits = dd_dispatch._require(workdir, "edits.json", "dd_checks")
    edits["edits"].append(_create_edit(sheets, readme["statements"]))
    edits["human"] = sorted([*edits["human"], *_rejected(readme["statements"])],
                            key=lambda h: (h["doc"], h["line"], h["kind"], h["text"]))
    write_json(workdir / "edits.json", edits)
    dd_dispatch.plan_verify_readme(root, workdir, readme["statements"], config)
    return readme
