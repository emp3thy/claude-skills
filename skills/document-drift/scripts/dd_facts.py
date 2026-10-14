"""Fact tables: defaults, choices and required flags documented in markdown tables, checked
against the pattern scan -> script-edits.json (spec 3.2).

A **fact table** is a markdown table (a header row, its delimiter row and the data rows after
it) with at least one **value column**, whose header, lowercased, is or contains ``default``
(a default), ``required`` (required or not), or ``values``, ``choices``, ``options`` or
``one of`` (the choices), tried in that order; and a **name column**: the first other column
whose data cells mostly (more than half the rows) start with an inline code span, else the
first column (which is then no value column). A row's name is its name cell's first code span
(else the cell's text), up to the first space, ``=`` or ``,``.

A row is **checked** when its name matches, by ``dd_defindex.norm``, exactly one scanned name
of a kind with facts (``flag``, ``env``, ``param``). A ``flag`` or ``param`` match is scoped
to the parents the nearest heading above the table names (``dd_gaps.named_parents``); when
none of the matches is in that scope, or no heading names a parent, every match counts.
Matches that agree on kind, parent and all three facts are one (an env read in several
places). Several matches: the row is skipped. A row whose name matches no scanned name of
any kind is a ``not-in-scan`` hint, naming the nearest scanned name of the same family
(``flag``: ``-``-led; ``env``: upper case; other names) within edit distance 2 by ``norm``.

Cells and facts are compared through ``normalise``; a null fact never makes an edit (the scan
does not know), and neither does a boolean fact against a cell whose word the vocabulary does
not know (``see notes``, ``enabled by default``): the row is checked and the reader's
convention left alone. A mismatch rewrites only that cell in its own style (``_written``), one
``fact`` edit per row (ids ``f001``... in doc then line order). Rows on protected lines
(``drift-ignore``, never-edit sections, generated regions) are skipped and not counted.

``run`` reads ``script-edits.json`` (``dd_cite``), replaces the ``fact`` edits and
``not-in-scan`` hints of an earlier run with this run's, fills ``counts.facts``
(``rows_checked``, ``corrected``, ``not_in_scan``) and rewrites it.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from dd_checks import _protected, _read
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import norm
from dd_gaps import SCOPED_KINDS, heading_before, named_parents, prepare
from dd_md_scan import scan

DEFAULT, REQUIRED, CHOICES = "default", "required", "choices"
CHOICE_WORDS = ("values", "choices", "options", "one of")
FACT_KINDS = frozenset({"flag", "env", "param"})
NEAREST_DISTANCE = 2
NO_VALUE = frozenset({"", "-", "none", "null", "n/a", "(none)"})
BOOLEANS = ("true", "false")
# (false word, true word) pairs, in the order a cell's word is looked up when writing.
_MARKS = (("✗", "✓"), ("✘", "✔"), ("n", "y"), ("x", "✓"))
VOCAB = {DEFAULT: (("off", "on"), ("disabled", "enabled"), ("no", "yes"), ("false", "true"),
                   *_MARKS),
         REQUIRED: (("optional", "required"), ("no", "yes"), ("false", "true"), *_MARKS)}

_CODE = re.compile(r"(`+)(.+?)\1")
_TICKED = re.compile(r"^(`+)\s*([^`]*?)\s*\1$")
_QUOTED = re.compile(r"""^(["'])(.*)\1$""", re.DOTALL)
_SEP = re.compile(r"\s*(?:,|\\?\|)\s*")
_PREFIX = re.compile(r"^[ \t]*(?:>[ \t]?)*")
_NAME_END = re.compile(r"[\s=,]")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]*$")


class Row(TypedDict):
    line: int
    cells: list[str]
    name: str
    text: str  # the row's source line
    spans: list[tuple[int, int]]  # each cell's columns in ``text``, between the pipes


class Table(TypedDict):
    header_line: int
    name_col: int
    value_cols: dict[str, int]
    rows: list[Row]


def fact_of(column: str) -> str | None:
    """Which fact a column header holds (``default``, ``required``, ``choices``), or None."""
    header = column.lower()
    if DEFAULT in header:
        return DEFAULT
    if REQUIRED in header:
        return REQUIRED
    if any(word in header for word in CHOICE_WORDS):
        return CHOICES
    return None


def _spans(line: str) -> list[tuple[int, int]]:
    """The column ranges of a table line's cells, between unescaped ``|``; a block quote
    prefix and an empty edge segment outside the outer pipes are no cell."""
    match = _PREFIX.match(line)
    start = match.end() if match else 0
    pipes = [i for i in range(start, len(line))
             if line[i] == "|" and (i == 0 or line[i - 1] != "\\")]
    bounds = [start - 1, *pipes, len(line)]
    cells = [(bounds[i] + 1, bounds[i + 1]) for i in range(len(bounds) - 1)]
    return [c for n, c in enumerate(cells)
            if line[c[0]:c[1]].strip() or n not in (0, len(cells) - 1)]


def _row_name(cell: str) -> str:
    match = _CODE.search(cell)
    text = match.group(2).strip() if match else cell.strip().strip("*").strip()
    return _NAME_END.split(text, maxsplit=1)[0]


def _is_code(cell: str) -> bool:
    return cell.startswith("`")


def fact_tables(text: str) -> list[Table]:
    """The fact tables of a markdown text (module docstring), in order."""
    parsed = scan(text)
    blocks = parsed.blocks
    tables: list[Table] = []
    for i, block in enumerate(blocks[:-1]):
        if block.kind != "table_row" or blocks[i + 1].kind != "table_delim":
            continue
        lines = [block.line_start]
        last = blocks[i + 1].line_start
        for later in blocks[i + 2:]:
            if later.kind != "table_row" or later.line_start != last + 1:
                break
            lines.append(later.line_start)
            last = later.line_start
        source = [parsed.lines[n - 1] for n in lines]
        spans = [_spans(line) for line in source]
        cells = [[line[a:b].strip() for a, b in row] for line, row in zip(source, spans,
                                                                           strict=True)]
        header, data = cells[0], cells[1:]
        values = {n for n, column in enumerate(header) if fact_of(column)}
        code = [n for n in range(len(header)) if n not in values
                and 2 * sum(1 for row in data if n < len(row) and _is_code(row[n])) > len(data)]
        name_col = code[0] if code else 0
        value_cols = {header[n]: n for n in sorted(values) if n != name_col}
        if not value_cols:
            continue
        rows: list[Row] = []
        for number, line, row, row_spans in zip(lines[1:], source[1:], data, spans[1:],
                                                strict=True):
            name = _row_name(row[name_col]) if name_col < len(row) else ""
            if name:
                rows.append(Row(line=number, cells=row, name=name, text=line,
                                spans=row_spans))
        tables.append(Table(header_line=lines[0], name_col=name_col, value_cols=value_cols,
                            rows=rows))
    return tables


def _unwrap(cell: str) -> tuple[str, str, str]:
    """``(backticks, quote, inner text)`` of a cell's stripped text."""
    text, ticks, quote = cell.strip(), "", ""
    match = _TICKED.match(text)
    if match:
        ticks, text = match.group(1), match.group(2)
    match = _QUOTED.match(text)
    if match:
        quote, text = match.group(1), match.group(2).strip()
    return ticks, quote, text


def _separators(cell: str) -> list[tuple[int, int]]:
    """The item separators (``,``, ``|`` or ``\\|`` with their spacing) outside code spans."""
    code = [(m.start(), m.end()) for m in _CODE.finditer(cell)]
    return [(m.start(), m.end()) for m in _SEP.finditer(cell)
            if not any(a <= m.start() < b for a, b in code)]


def _items(cell: str) -> list[str]:
    bounds = [(0, 0), *_separators(cell), (len(cell), len(cell))]
    found = [_unwrap(cell[bounds[i][1]:bounds[i + 1][0]])[2] for i in range(len(bounds) - 1)]
    return [item for item in found if item]


def normalise(cell: str, column: str) -> str | None:
    """The comparison form of a cell (or a scanned value) under ``column``'s header: backticks
    and surrounding quotes stripped; an empty cell, ``-``, ``None``, ``null``, ``n/a`` and
    ``(none)`` (any case) are None. A ``default`` column's boolean words (``off``,
    ``disabled``, ``no``, ``false`` / ``on``, ``enabled``, ``yes``, ``true``) and a
    ``required`` column's (``no``, ``false``, ``optional`` / ``yes``, ``true``,
    ``required``) become ``"false"`` / ``"true"``, and so do the marks of both (``✗``,
    ``✘``, ``n``, ``x`` / ``✓``, ``✔``, ``y``; a required column's ``-`` is
    ``"false"``); a choices cell is its distinct items (split on ``,`` or ``|`` outside
    backticks) sorted and joined by ``, ``."""
    fact = fact_of(column)
    _, _, text = _unwrap(cell)
    if fact == REQUIRED and text == "-":
        return "false"
    if text.lower() in NO_VALUE:
        return None
    if fact == CHOICES:
        items = sorted(set(_items(cell)))
        return ", ".join(items) if items else None
    if fact in VOCAB:
        for false, true in VOCAB[fact]:
            if text.lower() == false:
                return "false"
            if text.lower() == true:
                return "true"
    return text


def _fact(name: Mapping[str, Any], column: str) -> str | list[str] | None:
    """The scanned value of ``column``'s fact for a name: a string, a choices list, or None."""
    fact = fact_of(column)
    if fact == CHOICES:
        choices = name.get("choices")
        return [str(c) for c in choices] if choices else None
    if fact == REQUIRED:
        required = name.get("required")
        return None if required is None else ("true" if required else "false")
    default = name.get("default")
    return None if default is None else str(default)


def _shown(value: str | list[str], column: str) -> str:
    """A scanned value as written in a claim: choices joined by ``, ``, booleans normalised."""
    if isinstance(value, list):
        return ", ".join(value)
    norm_value = normalise(value, column)
    return norm_value if norm_value in BOOLEANS else value


def _case_like(old: str, word: str) -> str:
    if len(old) > 1 and old.isupper():
        return word.upper()
    return word.capitalize() if old[:1].isupper() else word


def _written(old: str, value: str | list[str], column: str) -> str:
    """The new text of a cell holding ``old`` (stripped) for the scanned ``value``: a cell
    meaning no value becomes the value in backticks (each choice in backticks, joined by
    ``, ``); a choices cell keeps its first separator with its spacing and writes each item
    in backticks when its first item had them; otherwise the old backticks and quotes are
    kept, and a boolean is written in the old cell's vocabulary (its case kept) when the old
    cell was a boolean word of the column, else as ``true`` or ``false``."""
    fact = fact_of(column)
    empty = normalise(old, column) is None
    if isinstance(value, list):
        seps = _separators(old)
        sep = old[seps[0][0]:seps[0][1]] if seps and not empty else ", "
        ticked = empty or old.lstrip().startswith("`")
        return sep.join(f"`{item}`" if ticked else item for item in value)
    word = _shown(value, column)
    ticks, quote, inner = _unwrap(old)
    if word in BOOLEANS and fact in VOCAB:
        pair = next((p for p in VOCAB[fact] if inner.lower() in p), None)
        if pair is not None:
            word = _case_like(inner, pair[word == "true"])
    if empty:
        return f"`{word}`"
    return f"{ticks}{quote}{word}{quote}{ticks}"


def _replace(line: str, span: tuple[int, int], new: str) -> str:
    a, b = span
    cell = line[a:b]
    if not cell.strip():
        return f"{line[:a]} {new} {line[b:]}"
    lead = len(cell) - len(cell.lstrip())
    trail = len(cell.rstrip())
    return line[:a + lead] + new + line[a + trail:]


def distance(a: str, b: str) -> int:
    """The Levenshtein edit distance between two strings."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _family(text: str, kind: str | None = None) -> str:
    if kind is not None:
        return kind if kind in ("flag", "env") else "name"
    if text.startswith("-"):
        return "flag"
    return "env" if _ENV.match(text) else "name"


def _norm_of(name: Mapping[str, Any]) -> str:
    return norm(str(name["name"]), routes=name["kind"] == "route")


def _not_in_scan(row: Row, names: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    key, family = norm(row["name"]), _family(row["name"])
    near = sorted({(distance(key, _norm_of(n)), str(n["name"])) for n in names
                   if _family(str(n["name"]), str(n["kind"])) == family})
    text = f"not in scan: {row['name']}"
    if near and near[0][0] <= NEAREST_DISTANCE:
        text += f"; nearest {near[0][1]}"
    return {"line": row["line"], "kind": "not-in-scan", "text": text}


def _identity(name: Mapping[str, Any]) -> tuple[Any, ...]:
    choices = name.get("choices")
    return (name["kind"], name.get("parent"), name.get("default"),
            tuple(choices) if choices is not None else None, name.get("required"))


def _matches(key: str, names: Sequence[Mapping[str, Any]],
             parent: Sequence[str | None]) -> list[Mapping[str, Any]]:
    found = [n for n in names if n["kind"] in FACT_KINDS and _norm_of(n) == key]
    scoped = [n for n in found if n["kind"] in SCOPED_KINDS and n.get("parent") in parent]
    if scoped:
        found = scoped
    distinct: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for name in sorted(found, key=lambda n: (str(n["file"]), int(n["line"]))):
        distinct.setdefault(_identity(name), name)
    return list(distinct.values())


def check_row(row: Row, table: Table, names: Sequence[Mapping[str, Any]],
              parent: Sequence[str | None], *,
              doc: str = "") -> tuple[str, dict[str, Any] | None]:
    """Check one row of a fact table against the scanned names; ``parent`` holds the parents
    the nearest heading above the table names (module docstring).

    Returns ``("checked", None)``, ``("corrected", edit)``, ``("not-in-scan", hint)`` or
    ``("skipped", None)``."""
    key = norm(row["name"])
    if not any(_norm_of(n) == key for n in names):
        return "not-in-scan", _not_in_scan(row, names)
    matches = _matches(key, names, parent)
    if len(matches) != 1:
        return "skipped", None
    [match] = matches
    new = row["text"]
    changed: list[tuple[str, str, str, str]] = []
    for column, index in sorted(table["value_cols"].items(), key=lambda c: -c[1]):
        if index >= len(row["cells"]):
            continue
        value = _fact(match, column)
        if value is None:
            continue
        old = row["cells"][index]
        want = normalise(", ".join(value) if isinstance(value, list) else value, column)
        have = normalise(old, column)
        if have == want or (want in BOOLEANS and have is not None and have not in BOOLEANS):
            continue  # an unknown boolean word is the reader's convention: left alone
        cell = _written(old, value, column)
        new = _replace(new, row["spans"][index], cell)
        changed.insert(0, (column, old, cell, _shown(value, column)))
    if not changed:
        return "checked", None
    name = str(match["name"])
    return "corrected", {
        "id": "", "doc": doc, "start_line": row["line"], "end_line": row["line"],
        "old": row["text"], "new": new, "type": "fact", "source": "script",
        "status": "kept", "check": None, "human_kind": None, "reason": None,
        "claim": "; ".join(f"{name} {column} is {shown}" for column, _, _, shown in changed),
        "evidence": [f"{match['file']}:{match['line']}"], "subject": name,
        "column": "; ".join(c[0] for c in changed),
        "old_cell": "; ".join(c[1] for c in changed),
        "new_cell": "; ".join(c[2] for c in changed),
    }


def _load(workdir: Path, name: str, step: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def run(root: Path, workdir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Check the fact tables of the in-scope docs (``inventory.json``) against
    ``patterns.json``; add the ``fact`` edits, the ``not-in-scan`` hints and the facts counts
    to ``script-edits.json``. ``config`` is unused (the step's signature)."""
    patterns = _load(workdir, "patterns.json", "dd_patterns")
    script = _load(workdir, "script-edits.json", "dd_cite")
    inventory = _load(workdir, "inventory.json", "dd_inventory")
    tokens = _load(workdir, "tokens.json", "dd_extract")
    names: list[dict[str, Any]] = list(patterns["names"])
    parents = sorted({str(n["parent"]) for n in names
                      if n["kind"] in SCOPED_KINDS and n.get("parent")})
    never = re.compile(inventory["never_edit_re"])
    markers = tokens.get("markers", [])
    counts = {"rows_checked": 0, "corrected": 0, "not_in_scan": 0}
    edits: list[dict[str, Any]] = [e for e in script.get("edits", []) if e.get("type") != "fact"]
    hints: dict[str, list[dict[str, Any]]] = {}
    for doc, found in script.get("hints", {}).items():
        kept = [h for h in found if h.get("kind") != "not-in-scan"]
        if kept:
            hints[doc] = kept
    facts: list[dict[str, Any]] = []
    for doc in sorted(inventory.get("docs", [])):
        text = _read(root, doc)
        tables = fact_tables(text) if text is not None else []
        if text is None or not tables:
            continue
        protected, _ = _protected(doc, text, markers, never)
        [prepared] = prepare({doc: text})
        for table in tables:
            scope = named_parents(heading_before(prepared, table["header_line"]), parents)
            for row in table["rows"]:
                if row["line"] in protected:
                    continue
                status, record = check_row(row, table, names, scope, doc=doc)
                if status in ("checked", "corrected"):
                    counts["rows_checked"] += 1
                if status == "corrected" and record is not None:
                    counts["corrected"] += 1
                    facts.append(record)
                elif status == "not-in-scan" and record is not None:
                    counts["not_in_scan"] += 1
                    hints.setdefault(doc, []).append(record)
    for n, edit in enumerate(facts, 1):
        edit["id"] = f"f{n:03d}"
    result = {**script, "edits": edits + facts, "hints": hints,
              "counts": {**script.get("counts", {}), "facts": counts}}
    write_json(workdir / "script-edits.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the docs' default, choices and required tables against the scan.")
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
