"""Citation checks: every ``path:line`` citation against the definition index and the pattern
scan -> script-edits.json (spec 2).

A citation is a ``cite`` token of ``tokens.json``. Its **subject** is a name on the same doc
line (``subject_of``): the candidates are the contents of inline code spans, without a trailing
``()``, and the bare words (``[A-Za-z_][\\w.]*``, a trailing ``.`` dropped) outside them that
are specific (``dd_defindex.is_specific``: ``EpisodeService``, ``store.save``) or written as a
call (``observe()``), so a plain word such as ``line`` never claims a citation. The line's
citations are masked out first, so no citation text is ever a candidate. The candidates are
those before the citation ending within ``BEFORE_WINDOW`` characters of it, nearest first (in
a table row only those in the citation's own cell, plus the row's name cell, its first cell, at
any distance), then those starting within ``AFTER_WINDOW`` characters after it, nearest
first. A candidate whose span in the cited file covers the citation wins (the doc cites that
definition, whatever name is nearer); otherwise the first candidate resolving in the cited
file is the subject; failing that, the first resolving elsewhere (a use site).

A candidate resolves (``resolve_name``) to definitions of rank 0 (``module``, ``function``,
``class``, ``sql``, ``file``) by its whole normalised name or, for ``Owner.member``, by the member
with the owner among the definition's owners, and to the scan's names by ``norm`` (the route
form for routes, with a leading HTTP method dropped), each a one-line span at its
``file:line``; definitions in the cited file win, then scanned names there, then definitions
and scanned names elsewhere. A ``file`` or ``module`` definition of the cited file itself
never resolves: a citation naming its own file says nothing about the line. A definition is
**in the cited file** when its file is the cited path or ends with ``/`` and the cited path.

``check`` gives spec 2.2's case: ``current``, ``moved`` (with the rewritten citation text),
``several definitions, one covers``, ``ambiguous``, ``use site`` or ``unresolved``. A citation
on a heading line is never rewritten (``unresolved``, hinted ``(heading)``), and a path that
names several tracked files (not resolved to one relative to the doc or the root) is
``ambiguous``: the subject never picks the file. A moved
``N`` becomes the definition's start; ``N-M`` (or ``#LN-LM``) its start and end, written once
when they are equal.

``script-edits.json`` is ``{"edits": [...], "hints": {doc: [{"line", "kind", "text"}]},
"counts": {"citations": {...}, "facts": {...}}}`` (plan, Shared contracts). Each doc line with
moved citations gets one ``cite`` edit holding all of them (ids ``c001``... in doc then line
order); citations under ``drift-ignore``, in never-edit sections or generated regions, and
non-editable ones are skipped and not counted. The ``facts`` counts are written as zero for
``dd_facts`` to fill.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from dd_checks import _protected, _read, _split
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import RANK, Definition, by_norm, is_specific, norm
from dd_resolve import path_matches

BEFORE_WINDOW = 120
TABLE_BLOCKS = frozenset({"table_row", "table_header"})
AFTER_WINDOW = 60
SELF_KINDS = frozenset({"file", "module"})
CURRENT, MOVED, ONE_COVERS = "current", "moved", "several definitions, one covers"
AMBIGUOUS, USE_SITE, UNRESOLVED = "ambiguous", "use site", "unresolved"
_COUNT_KEY = {CURRENT: "current", ONE_COVERS: "current", MOVED: "moved",
              AMBIGUOUS: "ambiguous", USE_SITE: "use_site", UNRESOLVED: "unresolved"}
_HINT_KIND = {AMBIGUOUS: "cite-ambiguous", USE_SITE: "cite-use-site",
              UNRESOLVED: "cite-unresolved"}

_CODE = re.compile(r"(`+)(.+?)\1")
_WORD = re.compile(r"(?<![\w.])[A-Za-z_][\w.]*")
_METHOD = re.compile(r"(?i)^(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+")
_CITE = re.compile(
    r"^(?P<path>.+?)(?:#L(?P<fs>\d+)(?:-(?P<fl>L?)(?P<fe>\d+))?|:(?P<s>\d+)(?:-(?P<e>\d+))?)$")

Span = tuple[str, int, int]
Cite = tuple[str, int, int]
Names = Mapping[str, list[dict[str, Any]]]


class Subject(TypedDict):
    text: str
    file: str
    start: int
    end: int
    kind: str  # "definition" | "scanned"
    count: int  # spans in the cited file
    spans: list[Span]  # the spans in the cited file


def _clean(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]
    return path


def in_cited(file: str, cited: str, exact: bool = False) -> bool:
    """True when ``file`` is the cited path or (unless ``exact``: the path resolved to one
    file relative to the doc or the root) ends with ``/`` and it (segments aligned)."""
    return file == cited or (not exact and file.endswith("/" + cited))


def parse_cite(text: str) -> Cite | None:
    """``(path, start, end)`` of a citation as written (``a.py:3``, ``a.py:3-9``,
    ``a.py#L3-L9``), the path without a leading ``./``; None when it is not one."""
    m = _CITE.match(text)
    if m is None:
        return None
    start = int(m["fs"] or m["s"])
    last = m["fe"] or m["e"]
    return _clean(m["path"]), start, int(last) if last else start


def rewrite(text: str, start: int, end: int, *, single: bool) -> str:
    """The citation ``text`` pointing at ``start`` (``single``) or ``start``-``end``, in its
    written form (``:N``, ``:N-M``, ``#LN``, ``#LN-LM`` or ``#LN-M``)."""
    m = _CITE.match(text)
    if m is None:
        return text
    one = single or start == end
    if m["fs"] is not None:
        head = text[: m.start("fs") - 2]
        return f"{head}#L{start}" if one else f"{head}#L{start}-{m['fl'] or ''}{end}"
    head = text[: m.start("s") - 1]
    return f"{head}:{start}" if one else f"{head}:{start}-{end}"


def index_names(names: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """The scan's names grouped by ``norm`` (the route form for routes)."""
    index: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        key = norm(str(name["name"]), routes=name["kind"] == "route")
        index.setdefault(key, []).append(dict(name))
    return index


def resolve_name(text: str, defs: Mapping[str, list[Definition]], names: Names,
                 cited: str, exact: bool = False) -> tuple[str, list[Span]] | None:
    """``(kind, spans)`` a candidate name resolves to, or None (module docstring).

    Rank-0 definitions match by the whole name, else ``Owner.member`` by the member with the
    owner among the definition's owners; the scan's names by ``norm``. The first non-empty of
    these wins: definitions in the cited file, scanned names in the cited file, definitions
    elsewhere, scanned names elsewhere. Spans are sorted and distinct."""
    found = [d for d in defs.get(norm(text), []) if RANK.get(d["kind"]) == 0]
    if not found and "." in text:
        owner, member = text.rsplit(".", 1)
        owner_norm = norm(owner.rsplit(".", 1)[-1])
        found = [d for d in defs.get(norm(member), [])
                 if RANK.get(d["kind"]) == 0 and owner_norm in d["owners"]]
    found = [d for d in found
             if not (d["kind"] in SELF_KINDS and in_cited(d["file"], cited, exact))]
    scanned = [r for r in names.get(norm(text), []) if r["kind"] != "route"]
    route = norm(_METHOD.sub("", text, count=1), routes=True)
    scanned += [r for r in names.get(route, []) if r["kind"] == "route"]
    def_spans = sorted({(str(d["file"]), int(d["start"]), int(d["end"])) for d in found})
    name_spans = sorted({(str(r["file"]), int(r["line"]), int(r["line"])) for r in scanned})
    for kind, spans, here in (("definition", def_spans, True), ("scanned", name_spans, True),
                              ("definition", def_spans, False),
                              ("scanned", name_spans, False)):
        chosen = [s for s in spans if in_cited(s[0], cited, exact)] if here else spans
        if chosen:
            return kind, chosen
    return None


def _strip_call(text: str) -> str:
    return text[:-2] if text.endswith("()") else text


def _cells(line: str) -> list[tuple[int, int]]:
    """The column ranges of a table row's cells, between unescaped ``|`` (an empty edge
    segment outside the outer pipes is no cell)."""
    pipes = [i for i, ch in enumerate(line) if ch == "|" and (i == 0 or line[i - 1] != "\\")]
    bounds = [-1, *pipes, len(line)]
    cells = [(bounds[i] + 1, bounds[i + 1]) for i in range(len(bounds) - 1)]
    return [c for n, c in enumerate(cells)
            if line[c[0]:c[1]].strip() or n not in (0, len(cells) - 1)]


def _candidates(line: str, col: int, end_col: int, table: bool) -> list[str]:
    """The candidate names of a masked line in trial order (module docstring): before the
    citation within ``BEFORE_WINDOW`` characters, nearest first (in a table row only in its
    own cell, plus the row's name cell at any distance), then within ``AFTER_WINDOW`` after
    it."""
    found: list[tuple[int, int, str]] = []
    code: list[tuple[int, int]] = []
    for m in _CODE.finditer(line):
        code.append((m.start(), m.end()))
        text = _strip_call(m.group(2).strip())
        if text:
            found.append((m.start(), m.end(), text))
    for m in _WORD.finditer(line):
        if any(a <= m.start() < b for a, b in code):
            continue
        text = m.group(0).rstrip(".")
        called = text == m.group(0) and line.startswith("(", m.end())
        if text and (called or is_specific(text)):
            found.append((m.start(), m.end(), text))
    cells = _cells(line) if table else []
    own = [c for c in cells if c[0] <= col < c[1]][:1]

    def near(c: tuple[int, int, str]) -> bool:
        if any(a <= c[0] and c[1] <= b for a, b in cells[:1]) and cells[:1] != own:
            return True  # the row's name cell, at any distance
        in_own = any(a <= c[0] and c[1] <= b for a, b in own) if table else True
        return in_own and col - c[1] <= BEFORE_WINDOW
    before = sorted((c for c in found if c[1] <= col and near(c)), key=lambda c: (-c[1], c[0]))
    after = sorted((c for c in found if c[0] >= end_col and c[0] - end_col <= AFTER_WINDOW),
                   key=lambda c: (c[0], -c[1]))
    return [c[2] for c in before + after]


def _mask(line: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(line)
    for a, b in spans:
        chars[a:b] = " " * len(chars[a:b])
    return "".join(chars)


def _covers(span: Span, start: int, end: int) -> bool:
    return span[1] <= start and end <= span[2]


def subject_of(line: str, col: int, end_col: int, defs: Mapping[str, list[Definition]],
               names: Names, *, cite: Cite | None = None,
               others: Sequence[tuple[int, int]] = (),
               table: bool | None = None, exact: bool = False) -> Subject | None:
    """The subject of the citation at ``line[col:end_col]``, or None when no candidate
    resolves (module docstring). ``cite`` overrides ``(path, start, end)`` parsed from the
    citation text (the caller's repository form of the path); ``others`` are the line's other
    citation spans, masked like this one; ``table`` says the line is a table row (by default,
    when it starts with ``|``); ``exact`` that the path resolved to one file relative to the
    doc or the root, so only that file is the cited file (``in_cited``).

    The first candidate with a span in the cited file covering the citation wins, with that
    span; else the first candidate with spans in the cited file, with its first span; else
    (a use site) the first candidate resolving elsewhere. ``count`` is the winner's number of
    spans in the cited file, ``spans`` those spans."""
    parsed = cite or parse_cite(line[col:end_col])
    if parsed is None:
        return None
    path, start, end = parsed
    if table is None:
        table = line.lstrip().startswith("|")
    masked = _mask(line, [(col, end_col), *others])
    nearest: Subject | None = None
    elsewhere: Subject | None = None
    for text in _candidates(masked, col, end_col, table):
        resolved = resolve_name(text, defs, names, path, exact)
        if resolved is None:
            continue
        kind, spans = resolved
        if not in_cited(spans[0][0], path, exact):
            elsewhere = elsewhere or Subject(text=text, file=spans[0][0], start=spans[0][1],
                                             end=spans[0][2], kind=kind, count=0, spans=[])
            continue
        covering = [s for s in spans if _covers(s, start, end)]
        pick = (covering or spans)[0]
        subject = Subject(text=text, file=pick[0], start=pick[1], end=pick[2], kind=kind,
                          count=len(spans), spans=spans)
        if covering:
            return subject
        nearest = nearest or subject
    return nearest or elsewhere


def cited_files(path: str, files: Iterable[str], exact: bool = False) -> list[str]:
    """The tracked files a cited path names."""
    return [f for f in files if in_cited(f, path, exact)]


def _heading(token: Mapping[str, Any]) -> bool:
    return bool((token.get("block") or {}).get("kind") == "heading")


def check(token: Mapping[str, Any], subject: Subject | None, files: Collection[str],
          file_lengths: Mapping[str, int], *,
          exact: bool = False) -> tuple[str, dict[str, str] | None]:
    """Spec 2.2's case of a citation token and, for ``moved``, ``{"old_cite", "new_cite"}``.
    ``files`` are the tracked paths, ``file_lengths`` the line counts of the cited ones,
    ``exact`` as for ``subject_of``.

    A citation on a heading line is ``unresolved`` (a rewrite would change the heading's
    slug), and so is one with no subject. A path naming several tracked files is
    ``ambiguous``: the subject never picks the file. Otherwise a subject span covering the
    citation makes it current (``several definitions, one covers`` when exactly one of
    several does); else one span is ``moved``, several ``ambiguous``."""
    path, start, end = _clean(str(token["path"])), int(token["start"]), int(token["end"])
    if _heading(token) or start < 1 or end < start:
        return UNRESOLVED, None
    tracked = cited_files(path, files, exact)
    if not tracked or all(end > file_lengths.get(f, 0) for f in tracked) or subject is None:
        return UNRESOLVED, None
    if len(tracked) > 1:
        return AMBIGUOUS, None
    if subject["count"] == 0:
        return USE_SITE, None
    covering = [s for s in subject["spans"] if _covers(s, start, end)]
    if covering:
        return (ONE_COVERS if subject["count"] > 1 and len(covering) == 1 else CURRENT), None
    if subject["count"] == 1:
        old = str(token["text"])
        return MOVED, {"old_cite": old, "new_cite": rewrite(
            old, subject["start"], subject["end"], single=start == end)}
    return AMBIGUOUS, None


def _numbers(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _hint(case: str, token: Mapping[str, Any], subject: Subject | None) -> dict[str, Any]:
    cited = f"{token['path']}:{_numbers(int(token['start']), int(token['end']))}"
    if case == AMBIGUOUS and subject is not None:
        text = f"cite ambiguous: {subject['text']} {cited}"
    elif case == USE_SITE and subject is not None:
        text = (f"cite use-site: {subject['text']} is defined in "
                f"{subject['file']}:{subject['start']}-{subject['end']}")
    else:
        text = f"cite unresolved: {cited}" + (" (heading)" if _heading(token) else "")
    return {"line": int(token["line"]), "kind": _HINT_KIND[case], "text": text}


def _skipped(token: Mapping[str, Any], line: str, protected: Mapping[int, str]) -> bool:
    col, end_col = int(token["col"]), int(token["end_col"])
    return bool(token.get("ignored") or token.get("never_edit") or token.get("generated")
                or not token.get("editable", True) or int(token["line"]) in protected
                or line[col:end_col] != token["text"])


def _repo_path(path: str, doc: str, files: frozenset[str]) -> tuple[str, bool]:
    """``(path, exact)``: the cited path in repository form and True when it names one file
    relative to the doc or the root, else the path as written without a leading ``./`` and
    False (it then names every tracked file it is a suffix of)."""
    match = path_matches(path, doc, files, frozenset(), loose=False)
    if match is not None and len(match[1]) == 1:
        return match[1][0], True
    return _clean(path), False


def _edit(doc: str, number: int, line: str,
          moved: list[tuple[dict[str, Any], Subject, dict[str, str]]]) -> dict[str, Any]:
    new = line
    for token, _, rewritten in sorted(moved, key=lambda m: -int(m[0]["col"])):
        new = new[: int(token["col"])] + rewritten["new_cite"] + new[int(token["end_col"]):]
    first = moved[0][1]
    return {
        "id": "", "doc": doc, "start_line": number, "end_line": number, "old": line,
        "new": new, "type": "cite", "source": "script", "status": "kept", "check": None,
        "human_kind": None, "reason": None,
        "claim": f"{first['text']} is at {first['file']}:{first['start']}-{first['end']}",
        "evidence": [f"{s['file']}:{s['start']}-{s['end']}" for _, s, _ in moved],
        "subject": first["text"],
        "old_cite": ", ".join(r["old_cite"] for _, _, r in moved),
        "new_cite": ", ".join(r["new_cite"] for _, _, r in moved),
    }


def _load(workdir: Path, name: str, step: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Check every citation of the in-scope docs in ``workdir/tokens.json``; write
    ``script-edits.json`` with the ``cite`` edits, the hints and the counts."""
    tokens = _load(workdir, "tokens.json", "dd_extract")
    defindex = _load(workdir, "defindex.json", "dd_defindex")
    patterns = _load(workdir, "patterns.json", "dd_patterns")
    inventory = _load(workdir, "inventory.json", "dd_inventory")
    defs = by_norm(defindex["definitions"])
    names = index_names(patterns["names"])
    files = frozenset(str(f) for f in inventory["files"])
    never = re.compile(inventory["never_edit_re"])
    markers = tokens.get("markers", [])
    counts = dict.fromkeys(("checked", "current", "moved", "ambiguous", "use_site",
                            "unresolved"), 0)
    edits: list[dict[str, Any]] = []
    hints: dict[str, list[dict[str, Any]]] = {}
    lengths: dict[str, int] = {}
    for doc in sorted(tokens["docs"]):
        cites = [t for t in tokens["docs"][doc] if t["kind"] == "cite"]
        text = _read(root, doc) if cites else None
        if text is None:
            continue
        lines = _split(text)
        protected, _ = _protected(doc, text, markers, never)
        by_line: dict[int, list[dict[str, Any]]] = {}
        for token in cites:
            by_line.setdefault(int(token["line"]), []).append(token)
        for number in sorted(by_line):
            line = lines[number - 1] if number <= len(lines) else ""
            row = sorted(by_line[number], key=lambda t: int(t["col"]))
            spans = [(int(t["col"]), int(t["end_col"])) for t in row]
            moved: list[tuple[dict[str, Any], Subject, dict[str, str]]] = []
            for i, token in enumerate(row):
                if _skipped(token, line, protected):
                    continue
                path, exact = _repo_path(str(token["path"]), doc, files)
                for file in cited_files(path, files, exact):
                    if file not in lengths:
                        source = _read(root, file)
                        lengths[file] = 0 if source is None else len(_split(source))
                subject = subject_of(line, *spans[i], defs, names,
                                     cite=(path, int(token["start"]), int(token["end"])),
                                     others=spans[:i] + spans[i + 1:],
                                     table=(token.get("block") or {}).get("kind")
                                     in TABLE_BLOCKS, exact=exact)
                case, rewritten = check({**token, "path": path}, subject, files, lengths,
                                        exact=exact)
                counts["checked"] += 1
                counts[_COUNT_KEY[case]] += 1
                if case == MOVED and subject is not None and rewritten is not None:
                    moved.append((token, subject, rewritten))
                elif case in _HINT_KIND:
                    hints.setdefault(doc, []).append(_hint(case, token, subject))
            if moved:
                edits.append(_edit(doc, number, line, moved))
    for n, edit in enumerate(edits, 1):
        edit["id"] = f"c{n:03d}"
    result = {"edits": edits, "hints": hints,
              "counts": {"citations": counts,
                         "facts": {"rows_checked": 0, "corrected": 0, "not_in_scan": 0}}}
    write_json(workdir / "script-edits.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the docs' path:line citations against the definition index.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run(args.repo, args.workdir)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
