"""Definition index: where each name a doc may mention is defined -> defindex.json (spec 5.1).

``defindex.json`` is ``{"definitions": [Definition...], "skipped": [{"file", "reason"}]}``; the
Definition record is the shared contract in the plan. Definitions are sorted by
(file, start, end, kind, name).

- **Python** (``ast``): a ``module`` per dotted suffix of each file's path, every
  function, method and class with its exact ``lineno``..``end_lineno``, and every string literal
  that looks like a name. A literal's range is its largest enclosing node within
  ``LITERAL_NODE_LINES`` lines (walking up while the parent still fits), so a registration
  call's whole argument list is the range of each name in it. A literal is a ``reg``
  (registration) when it is a ``name=`` keyword value or an argument of a registrar call,
  otherwise a ``literal``.
- **SQL** (``.sql``): ``CREATE ... TABLE|VIEW|INDEX|TRIGGER`` objects up to the ``;`` that ends
  the statement, ignoring comments, strings and ``BEGIN``/``CASE`` ... ``END`` bodies (at most
  ``SQL_STATEMENT_LINES`` lines); one-line ``sqlcol`` columns for each ``identifier type``
  element of a table's column list (constraint clauses excluded) and for
  ``ALTER TABLE ... ADD COLUMN``.
- **JavaScript/TypeScript**: ``function``, ``class``, ``export const|let``, ``const|let x = (``
  arrows and class-body methods, ranged by brace matching over the text with strings, template
  literals and comments blanked out; quoted string literals that look like names, one line.
- **Files**: every tracked non-test file whose basename is unique among tracked files.

Owners are the normalised names of enclosing functions and classes plus, for Python, the
``name="..."`` of an enclosing call. A function or class over ``SIGNATURE_LINES`` lines gets the
signature change and reading ranges of spec 5.4 (``signature_ranges``).

``run`` reads the working tree, which preflight has checked is clean, so it is HEAD's content;
``at_commit`` reads blobs at another commit through ``History.show``.
"""
from __future__ import annotations

import argparse
import ast
import bisect
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypedDict

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_history import History
from dd_inventory import indexed_files


class Definition(TypedDict):
    name: str
    norm: str
    file: str
    start: int
    end: int
    kind: str
    owners: list[str]
    change_ranges: list[list[int]]
    reading: list[int]


RANK: dict[str, int] = {
    "module": 0, "function": 0, "class": 0, "sql": 0, "file": 0,
    "reg": 1, "sqlcol": 1,
    "literal": 2,
}
SIGNATURE_LINES = 60
LITERAL_NODE_LINES = 15
SQL_STATEMENT_LINES = 30
REGISTRARS: frozenset[str] = frozenset({
    "add_argument", "add_parser", "get", "getenv", "route", "post", "put", "patch", "delete",
    "option", "command",
})
REGISTRAR_PREFIX = "_resolve"
JS_EXTENSIONS: frozenset[str] = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

_NAME_LITERAL = re.compile(r"^[A-Za-z_][\w.\-]{2,}$")
_FLAG_LITERAL = re.compile(r"^--[\w-]+$")
_UPPER_NAME = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")
_MCP_PREFIX = re.compile(r"^mcp__.+?__(?=.)")
_ROUTE_PARAM = re.compile(r"<[^<>/]*>|\{[^{}/]*\}|(?<=/):[A-Za-z_]\w*")
_DEF_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

_SQL_OBJECT = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?(?:UNIQUE\s+)?(?:VIRTUAL\s+)?"
    r"(TABLE|VIEW|INDEX|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]]+)",
    re.IGNORECASE,
)
_SQL_COLUMN = re.compile(r"\s*[\"`\[]?(\w+)[\"`\]]?\s+[\"`\[]?\w")
_SQL_CONSTRAINTS = frozenset({"PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK", "KEY",
                              "INDEX"})
_SQL_OPEN = re.compile(r"\s*\(")
_SQL_TOKEN = re.compile(r"\b(?:BEGIN|CASE|END)\b|;", re.IGNORECASE)
_SQL_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+([\w.\"`\[\]]+)\s+ADD\s+COLUMN\s+[\"`\[]?(\w+)", re.IGNORECASE)
_SQL_QUOTES = "\"`[]"

_JS_NAME = r"([A-Za-z_$][\w$]*)"
# (pattern over a masked line, kind, whether a newline at depth 0 ends the statement)
_JS_DEFS: tuple[tuple[re.Pattern[str], str, bool], ...] = (
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\b\s*\*?\s*"
                + _JS_NAME + r"(?=\s*[<(])"), "function", False),
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+" + _JS_NAME),
     "class", False),
    (re.compile(r"^\s*export\s+(?:const|let)\s+" + _JS_NAME), "function", True),
    (re.compile(r"^\s*(?:const|let)\s+" + _JS_NAME + r"(?=\s*(?::[^=]*)?=\s*(?:async\s*)?\()"),
     "function", True),
)
_JS_METHOD = re.compile(
    r"^\s*(?:(?:public|private|protected|static|async|readonly|override|abstract|get|set)\s+)*"
    r"\*?\s*(#?[A-Za-z_$][\w$]*)(?=\s*(?:<[^>]*>)?\s*\()")
_JS_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "function", "new", "super", "await",
    "typeof", "with", "do", "else",
})
_JS_CALLEE = re.compile(r"([A-Za-z_$][\w$]*)\s*$")
_JS_NAME_KEY = re.compile(r"\bname\s*[:=]\s*$")


def norm(name: str, *, routes: bool = False) -> str:
    """Normalise a name for comparison (shared contract): drop an ``mcp__<server>__`` prefix;
    a ``--flag`` keeps its dashes; otherwise ``-`` and ``.`` become ``_``. With ``routes``,
    route placeholders ``<x>``, ``{x}`` and ``:x`` become ``{}`` first."""
    text = _MCP_PREFIX.sub("", name, count=1)
    if routes:
        text = _ROUTE_PARAM.sub("{}", text)
    if text.startswith("--"):
        return text
    return text.replace("-", "_").replace(".", "_")


def is_specific(text: str) -> bool:
    """Spec 5.2: holds ``.``, ``/`` or ``_``, starts with ``--``, mixes case, or is an upper
    case name such as ``BETTER_MEMORY_HOME``."""
    if any(ch in text for ch in "./_") or text.startswith("--"):
        return True
    if any(ch.islower() for ch in text) and any(ch.isupper() for ch in text):
        return True
    return _UPPER_NAME.match(text) is not None


def _looks_like_name(value: str) -> bool:
    return bool(_NAME_LITERAL.match(value) or _FLAG_LITERAL.match(value))


def _is_registrar(name: str | None) -> bool:
    return name is not None and (name in REGISTRARS or name.startswith(REGISTRAR_PREFIX))


def _definition(name: str, file: str, start: int, end: int, kind: str,
                owners: Iterable[str] = (),
                change: list[tuple[int, int]] | None = None,
                reading: tuple[int, int] | None = None) -> Definition:
    own = [o for o in dict.fromkeys(owners) if o]
    return Definition(
        name=name, norm=norm(name), file=file, start=start, end=end, kind=kind, owners=own,
        change_ranges=[[s, e] for s, e in (change or [(start, end)])],
        reading=list(reading or (start, end)),
    )


# --- Python -------------------------------------------------------------------------------

def signature_ranges(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """``(change_ranges, reading)`` for a function or class (spec 5.4). Over
    ``SIGNATURE_LINES`` lines: the definition line through the docstring (or the definition
    line alone), plus each method's line for a class; otherwise the full range for both."""
    start = node.lineno
    end = node.end_lineno or start
    if end - start + 1 <= SIGNATURE_LINES:
        return [(start, end)], (start, end)
    first = node.body[0] if node.body else None
    doc_end = start
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        doc_end = first.end_lineno or start
    ranges = [(start, doc_end)]
    if isinstance(node, ast.ClassDef):
        ranges += [(m.lineno, m.lineno) for m in node.body
                   if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return ranges, (start, doc_end)


def _module_names(path: str) -> list[str]:
    """Every dotted suffix of the module path (``src.svc.storage``, ``svc.storage``,
    ``storage``), so a module answers to its import name whatever directory holds it."""
    parts = path[: -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts))]


def _call_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _name_keyword(call: ast.Call) -> ast.Constant | None:
    for kw in call.keywords:
        if (kw.arg == "name" and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)):
            return kw.value
    return None


def _py_owners(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> list[str]:
    owners: list[str] = []
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, _DEF_NODES):
            owners.append(norm(cur.name))
        elif isinstance(cur, ast.Call):
            registered = _name_keyword(cur)
            if registered is not None and registered is not node:
                owners.append(norm(str(registered.value)))
        cur = parents.get(cur)
    return owners


def _literal_range(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> tuple[int, int]:
    best = (node.lineno, node.end_lineno or node.lineno)
    cur = parents.get(node)
    while cur is not None:
        start = getattr(cur, "lineno", None)
        end = getattr(cur, "end_lineno", None)
        if isinstance(start, int) and isinstance(end, int):
            if end - start + 1 > LITERAL_NODE_LINES:
                break
            best = (start, end)
        cur = parents.get(cur)
    return best


def _py_literal_kind(node: ast.Constant, parents: dict[ast.AST, ast.AST]) -> str:
    parent = parents.get(node)
    call: ast.AST | None = None
    if isinstance(parent, ast.keyword):
        if parent.arg == "name":
            return "reg"
        call = parents.get(parent)
    elif isinstance(parent, ast.Call) and any(arg is node for arg in parent.args):
        call = parent
    if isinstance(call, ast.Call) and _is_registrar(_call_name(call.func)):
        return "reg"
    return "literal"


def _python(path: str, text: str) -> list[Definition] | None:
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError):
        return None
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    last = max(1, len(text.splitlines()))
    defs = [_definition(name, path, 1, last, "module") for name in _module_names(path)]
    for node in ast.walk(tree):
        if isinstance(node, _DEF_NODES):
            change, reading = signature_ranges(node)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            defs.append(_definition(node.name, path, node.lineno, node.end_lineno or node.lineno,
                                    kind, _py_owners(node, parents), change, reading))
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and _looks_like_name(node.value)
              and not isinstance(parents.get(node), ast.JoinedStr)):
            start, end = _literal_range(node, parents)
            defs.append(_definition(node.value, path, start, end,
                                    _py_literal_kind(node, parents), _py_owners(node, parents)))
    return defs


# --- SQL ----------------------------------------------------------------------------------

def _mask_sql(text: str) -> list[str]:
    """The lines of ``text`` with ``--`` and ``/* */`` comments and ``'...'`` strings blanked
    (same length), so a ``;`` or a keyword inside them is not seen."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif text[i] == "'":
            j = i + 1
            while j < n and (text[j] != "'" or text.startswith("''", j)):
                j += 2 if text[j] == "'" else 1
            j = min(n, j + 1)
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != "\n":
                out[k] = " "
        i = j
    lines = "".join(out).split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def _sql_statement_end(lines: list[str], start: int) -> int:
    """The line of the ``;`` ending the statement that starts on ``start``, outside any
    ``BEGIN``/``CASE`` ... ``END`` block; at most ``SQL_STATEMENT_LINES`` lines."""
    cap = min(len(lines), start + SQL_STATEMENT_LINES - 1)
    depth = 0
    for number in range(start, cap + 1):
        for token in _SQL_TOKEN.finditer(lines[number - 1]):
            word = token.group(0).upper()
            if word in ("BEGIN", "CASE"):
                depth += 1
            elif word == "END":
                depth = max(0, depth - 1)
            elif depth == 0:
                return number
    return cap


def _sql_columns(lines: list[str], start: int, end: int, offset: int) -> list[tuple[str, int]]:
    """``(column, line)`` for each ``identifier type`` element of the parenthesised list that
    follows a ``CREATE TABLE`` name ending at ``offset`` on line ``start``."""
    text = "\n".join(lines[start - 1 : end])
    opening = _SQL_OPEN.match(text, offset)
    if opening is None:
        return []
    elements: list[tuple[int, int]] = []
    depth, begin = 0, opening.end()
    for i in range(opening.end() - 1, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                elements.append((begin, i))
                break
        elif text[i] == "," and depth == 1:
            elements.append((begin, i))
            begin = i + 1
    else:  # the list runs past the statement cap
        elements.append((begin, len(text)))
    columns: list[tuple[str, int]] = []
    for a, b in elements:
        column = _SQL_COLUMN.match(text[a:b])
        if column and column.group(1).upper() not in _SQL_CONSTRAINTS:
            columns.append((column.group(1), start + text.count("\n", 0, a + column.start(1))))
    return columns


def _sql(path: str, text: str) -> list[Definition]:
    lines = _mask_sql(text)
    defs: list[Definition] = []
    for number, line in enumerate(lines, 1):
        created = _SQL_OBJECT.match(line)
        if created:
            name = created.group(2).strip(_SQL_QUOTES)
            end = _sql_statement_end(lines, number)
            defs.append(_definition(name, path, number, end, "sql"))
            if created.group(1).upper() == "TABLE":
                defs += [_definition(column, path, at, at, "sqlcol", [norm(name)])
                         for column, at in _sql_columns(lines, number, end, created.end())]
        added = _SQL_ADD_COLUMN.search(line)
        if added:
            owner = norm(added.group(1).strip(_SQL_QUOTES))
            defs.append(_definition(added.group(2), path, number, number, "sqlcol", [owner]))
    return defs


# --- JavaScript and TypeScript ------------------------------------------------------------

def _mask_js(text: str) -> tuple[str, list[tuple[int, str]]]:
    """Blank out comments, quoted strings and template literal text (newlines kept, ``${...}``
    expressions kept as code); return the masked text and each closed quoted string as
    ``(offset, value)``. Quoted strings end at a line break, so a stray quote (JSX text such as
    ``Don't``) hides one line at most."""
    out = list(text)
    strings: list[tuple[int, str]] = []
    braces: list[int] = []  # open-brace depth inside each enclosing ${...}
    in_template = False
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = text[i]
        if in_template:
            if ch == "\\":
                blank(i, i + 2)
                i += 2
            elif ch == "`":
                blank(i, i + 1)
                in_template = False
                i += 1
            elif text.startswith("${", i):
                blank(i, i + 2)
                braces.append(0)
                in_template = False
                i += 2
            else:
                blank(i, i + 1)
                i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif ch in "'\"":
            j = i + 1
            while j < n and text[j] not in (ch, "\n"):
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == ch:
                strings.append((i, text[i + 1 : j]))
                j += 1
        elif ch == "`":
            in_template = True
            j = i + 1
        else:
            if ch == "{" and braces:
                braces[-1] += 1
            elif ch == "}" and braces:
                if braces[-1] == 0:
                    braces.pop()
                    in_template = True
                    blank(i, i + 1)
                else:
                    braces[-1] -= 1
            i += 1
            continue
        blank(i, j)
        i = j
    return "".join(out), strings


class _JsFile:
    def __init__(self, text: str) -> None:
        self.masked, self.strings = _mask_js(text)
        self.starts = [0] + [i + 1 for i, ch in enumerate(self.masked) if ch == "\n"]
        self.pairs: dict[int, int] = {}
        self.depths: list[int] = []  # brace depth at the start of each line
        stack: list[int] = []
        line = 0
        for i, ch in enumerate(self.masked):
            while line < len(self.starts) and self.starts[line] == i:
                self.depths.append(len(stack))
                line += 1
            if ch == "{":
                stack.append(i)
            elif ch == "}" and stack:
                self.pairs[stack.pop()] = i
        while len(self.depths) < len(self.starts):
            self.depths.append(len(stack))

    def line_of(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)

    def depth_after(self, offset: int) -> int:
        """Brace depth just after the character at ``offset``."""
        line_start = self.starts[self.line_of(offset) - 1]
        span = self.masked[line_start : offset + 1]
        return self.depths[self.line_of(offset) - 1] + span.count("{") - span.count("}")

    def lines(self) -> list[str]:
        return self.masked.split("\n")

    def body(self, pos: int, start: int, newline_ends: bool) -> tuple[int, int | None]:
        """From ``pos``, the first ``{`` outside parentheses and brackets opens the body;
        return ``(end line, body open offset)``. A ``;`` (or, when ``newline_ends``, a line
        break) at depth 0 first ends a body-less statement on its line; a ``}`` at depth 0
        (the enclosing block closing) leaves the definition on its own line."""
        depth = 0
        for i in range(pos, len(self.masked)):
            ch = self.masked[i]
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
                if depth < 0:
                    return start, None
            elif depth == 0:
                if ch == "{":
                    close = self.pairs.get(i)
                    end = self.line_of(close) if close is not None else len(self.starts)
                    return end, i
                if ch == ";" or (ch == "\n" and newline_ends):
                    return self.line_of(i), None
                if ch == "}":
                    return start, None
        return start, None


def _js_registration(js: _JsFile, offset: int) -> bool:
    line_start = js.starts[js.line_of(offset) - 1]
    prefix = js.masked[line_start:offset]
    if _JS_NAME_KEY.search(prefix):
        return True
    depth = 0
    for k in range(len(prefix) - 1, -1, -1):
        if prefix[k] == ")":
            depth += 1
        elif prefix[k] == "(":
            if depth == 0:
                callee = _JS_CALLEE.search(prefix[:k])
                return _is_registrar(callee.group(1) if callee else None)
            depth -= 1
    return False


def _js(path: str, text: str) -> list[Definition]:
    js = _JsFile(text)
    lines = js.lines()
    found: list[tuple[str, str, int, int]] = []  # name, kind, start, end
    classes: list[tuple[int, int]] = []  # body open/close offsets
    for number, line in enumerate(lines, 1):
        for pattern, kind, newline_ends in _JS_DEFS:
            match = pattern.match(line)
            if match:
                pos = js.starts[number - 1] + match.end()
                end, opened = js.body(pos, number, newline_ends)
                found.append((match.group(1), kind, number, end))
                if kind == "class" and opened is not None and opened in js.pairs:
                    classes.append((opened, js.pairs[opened]))
                break
    for opened, closed in classes:
        body_depth = js.depth_after(opened)
        for number in range(js.line_of(opened) + 1, js.line_of(closed) + 1):
            if js.depths[number - 1] != body_depth or js.starts[number - 1] >= closed:
                continue
            match = _JS_METHOD.match(lines[number - 1])
            if match and match.group(1) not in _JS_KEYWORDS:
                end, _ = js.body(js.starts[number - 1] + match.end(), number, False)
                found.append((match.group(1), "function", number, end))

    def owners(start: int, end: int) -> list[str]:
        holders = [(s, e, name) for name, _, s, e in found
                   if s <= start and end <= e and (s, e) != (start, end)]
        return [norm(name) for _, _, name in sorted(holders, key=lambda h: h[1] - h[0])]

    defs = [_definition(name, path, s, e, kind, owners(s, e)) for name, kind, s, e in found]
    for offset, value in js.strings:
        if _looks_like_name(value):
            number = js.line_of(offset)
            kind = "reg" if _js_registration(js, offset) else "literal"
            defs.append(_definition(value, path, number, number, kind, owners(number, number)))
    return defs


# --- Index --------------------------------------------------------------------------------

def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _extension(path: str) -> str:
    name = _basename(path)
    return "." + name.rpartition(".")[2].lower() if "." in name else ""


def _parse(path: str, text: str) -> list[Definition] | None:
    """Language definitions for one file; None when the file does not parse."""
    ext = _extension(path)
    if ext == ".py":
        return _python(path, text)
    if ext == ".sql":
        return _sql(path, text)
    if ext in JS_EXTENSIONS:
        return _js(path, text)
    return []


def _file_definition(path: str) -> Definition:
    return _definition(_basename(path), path, 1, 1, "file")


def _ordered(defs: Iterable[Definition]) -> list[Definition]:
    unique = {(d["file"], d["start"], d["end"], d["kind"], d["name"], tuple(d["owners"]),
               tuple(map(tuple, d["change_ranges"])), tuple(d["reading"])): d for d in defs}
    return [unique[key] for key in sorted(unique)]


def _index(files: Iterable[str], read: Callable[[str], str | None],
           unique_basenames: set[str]) -> tuple[list[Definition], list[dict[str, str]]]:
    defs: list[Definition] = []
    skipped: list[dict[str, str]] = []
    for path in files:
        text = read(path)
        if text is None:
            skipped.append({"file": path, "reason": "unreadable"})
            continue
        parsed = _parse(path, text)
        if parsed is None:
            skipped.append({"file": path, "reason": "syntax-error"})
        else:
            defs.extend(parsed)
        if _basename(path) in unique_basenames:
            defs.append(_file_definition(path))
    return _ordered(defs), sorted(skipped, key=lambda s: s["file"])


def build(files: list[str], read: Callable[[str], str | None],
          unique_basenames: set[str]) -> list[Definition]:
    """Definitions of ``files`` (content from ``read``, None for a missing file), with a
    ``file`` definition for each whose basename is in ``unique_basenames``; sorted."""
    return _index(files, read, unique_basenames)[0]


def by_norm(definitions: Iterable[Definition]) -> dict[str, list[Definition]]:
    """Group definitions by their normalised name, keeping their order."""
    groups: dict[str, list[Definition]] = {}
    for definition in definitions:
        groups.setdefault(definition["norm"], []).append(definition)
    return groups


def _unique_basenames(paths: Iterable[str]) -> set[str]:
    counts = Counter(_basename(path) for path in paths)
    return {name for name, count in counts.items() if count == 1}


def at_commit(root: Path, sha: str, files: list[str]) -> list[Definition]:
    """``build`` for ``files`` as they were at ``sha``; basenames are unique in that tree."""
    history = History(root)
    tree = history.tree_at(sha)
    unique = _unique_basenames(tree[0]) if tree is not None else set()
    return build(files, lambda path: history.show(sha, path), unique)


def _read_worktree(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Index ``indexed_files`` from ``workdir/inventory.json`` plus a ``file`` definition for
    every tracked non-test file with a unique basename; write ``defindex.json``."""
    inv_path = workdir / "inventory.json"
    if not inv_path.is_file():
        raise StepError(f"missing {inv_path}; run dd_inventory first", EXIT_MISSING)
    inventory = read_json(inv_path)
    tracked: list[str] = inventory["files"]
    tests = set(inventory["sources"].get("test", []))
    unique = _unique_basenames(tracked)
    indexed = [path for path in indexed_files(inventory) if path not in tests]
    defs, skipped = _index(indexed, lambda path: _read_worktree(root, path), unique)
    done = set(indexed)
    defs += [_file_definition(path) for path in tracked
             if path not in done and path not in tests and _basename(path) in unique]
    result: dict[str, Any] = {"definitions": _ordered(defs), "skipped": skipped}
    write_json(workdir / "defindex.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index where names are defined in the code.")
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
