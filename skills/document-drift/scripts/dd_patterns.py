"""Pattern scan: the user-facing names in the indexed files -> patterns.json (spec 8.1).

Each name is a ``Name`` record ``{"name", "kind", "file", "line", "parent", "hidden", "default",
"choices", "required"}`` (the last three null when the code sets none) with
``kind`` one of ``command``, ``flag``, ``env``, ``route``, ``tool``, ``param``, ``script``,
``target``. ``parent`` is a flag's command, an MCP parameter's tool, otherwise null.

- **Python** (``ast``; a file that does not parse is skipped): argparse ``add_parser("x")``
  (and its ``aliases``) as commands and every ``-``-led string of ``add_argument`` as a flag,
  whose parent is the command whose ``add_parser`` made the receiver, followed through
  assignments, argument groups and call chains; a receiver that is a function parameter has
  no parent. ``@<x>.command`` / ``@<x>.group`` functions are commands (a ``name`` given to
  the decorator wins; else the function name with ``_`` as ``-``, as click and typer do),
  and the ``-``-led strings of ``@<x>.option`` / ``@<x>.argument`` on them are flags with
  that command as parent. ``os.environ["X"]``, ``os.environ.get("X")``, ``os.getenv("X")``
  are env names (a store or ``del`` on ``os.environ`` is no read).
  ``@<x>.(get|post|put|patch|delete|route)("/x")`` are
  routes. MCP tools: ``Tool(..., name="x", ...)`` and ``@<x>.tool`` functions (their
  ``name`` or the function's); each tool's ``inputSchema`` / ``input_schema`` ``properties``
  keys (a dict literal or a module-level name bound to one) and a decorated tool's own
  parameters are ``param`` names with the tool as parent.
- **JavaScript and TypeScript** (regex): ``process.env.X``, ``process.env["X"]``,
  ``.command("x ...")``, ``.option("-x, --x <v>")`` (the first ``--`` token; a bare yargs
  name ``x`` becomes ``--x``), route calls ``<x>.(get|post|put|patch|delete)("/x"``.
- **Project files**: entry points and scripts (``dd_manifests.entry_points``) as ``script``,
  Makefile / justfile / Taskfile targets as ``target``, Dockerfile ``ENV`` keys and
  ``.env.example`` keys as ``env``.
- **Env families**: a quoted upper-case literal with an underscore anywhere in the indexed
  files is an env name when it starts with the prefix (up to and including the first ``_``)
  of an env name read directly (Python or JavaScript) in the scan.

Every pattern matches across line breaks; ``line`` is the line of the name itself. A name is
hidden when its call says ``help=argparse.SUPPRESS`` or ``hidden=True``, when its last
segment starts with ``_``, or when ``deprecated`` / ``DEPRECATED`` appears within three lines.

``patterns.json`` is ``{"names", "names_then", "skipped"}``: ``names`` for every indexed
file now; ``names_then`` for the changed indexed files as they were at the last-run commit
(null on a first run), scanned with the current env prefixes so both sides follow one rule;
``skipped`` as ``{"file", "reason"}``. Names are sorted by (file, line, kind, name).
"""
from __future__ import annotations

import argparse
import ast
import posixpath
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_history import History
from dd_inventory import indexed_files
from dd_manifests import entry_points, targets

Reader = Callable[[str], str | None]


class Name(TypedDict):
    name: str
    kind: str
    file: str
    line: int
    parent: str | None
    hidden: bool
    default: str | None
    choices: list[str] | None
    required: bool | None


class Skip(TypedDict):
    file: str
    reason: str


PY_EXTENSIONS = (".py", ".pyi")
JS_EXTENSIONS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")
ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
COMMAND_DECORATORS = frozenset({"command", "group"})
FLAG_DECORATORS = frozenset({"option", "argument"})
GROUP_METHODS = frozenset({"add_argument_group", "add_mutually_exclusive_group"})
SCHEMA_KEYWORDS = frozenset({"inputSchema", "input_schema"})
NOT_TOOL_PARAMS = frozenset({"self", "cls"})

_DEPRECATED = re.compile(r"\b(?:deprecated|DEPRECATED)\b")
_ENV_LITERAL = re.compile(r"[A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9]")
_SEGMENT_SPLIT = re.compile(r"[./:]")
_Q = "[\"'`]"
_JS_ENV_DOT = re.compile(r"\bprocess\s*\.\s*env\s*\.\s*([A-Za-z_$][\w$]*)")
_JS_ENV_INDEX = re.compile(rf"\bprocess\s*\.\s*env\s*\[\s*({_Q})([^\"'`]+)\1\s*\]")
_JS_COMMAND = re.compile(rf"\.\s*command\(\s*({_Q})([^\"'`]+)\1")
_JS_OPTION = re.compile(rf"\.\s*option\(\s*({_Q})([^\"'`]+)\1")
_JS_ROUTE = re.compile(
    rf"\b[A-Za-z_$][\w$]*\s*\.\s*(?:get|post|put|patch|delete)\(\s*({_Q})(/[^\"'`]*)\1")
_QUOTED_ENV = re.compile(rf"({_Q})([A-Z][A-Z0-9]*_[A-Z0-9_]*[A-Z0-9])\1")
_FLAG_TOKEN = re.compile(r"-{0,2}[A-Za-z0-9][\w-]*")
_DOCKER_ENV = re.compile(r"^[ \t]*(?i:env)[ \t]+((?:[^\n]*\\\n)*[^\n]*)", re.M)
_DOCKER_PAIR = re.compile(r"(?:^|(?<=\s))([A-Za-z_][A-Za-z0-9_]*)=")
_DOCKER_LEGACY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)[ \t]")
_DOTENV_KEY = re.compile(r"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=", re.M)


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _key_line(text: str, name: str) -> int:
    """The line where ``name`` is defined as a key (``name:``, ``"name":``, ``name =``),
    else the first line holding it as a token, else 1."""
    n = re.escape(name)
    key = re.compile(rf"(?:[\"']{n}[\"']|(?:^|(?<=\s)){n})[ \t]*[:=]", re.M)
    m = key.search(text) or re.search(rf"(?<![\w.-]){n}(?![\w.-])", text)
    return _line_at(text, m.start()) if m else 1


def _underscored(name: str) -> bool:
    """Whether the last segment of ``name`` (dashes stripped) starts with ``_``."""
    segments = [s for s in _SEGMENT_SPLIT.split(name.lstrip("-")) if s]
    return bool(segments) and segments[-1].startswith("_")


@dataclass
class _File:
    """The names found in one file, with the text lines that hidden detection reads."""

    path: str
    lines: list[str]
    names: list[Name] = field(default_factory=list)
    direct_env: set[str] = field(default_factory=set)
    literals: list[tuple[str, int]] = field(default_factory=list)

    def add(self, name: str, kind: str, line: int, parent: str | None = None,
            hidden: bool = False, default: str | None = None,
            choices: list[str] | None = None, required: bool | None = None) -> None:
        near = self.lines[max(line - 4, 0): line + 3]
        hidden = hidden or _underscored(name) or any(_DEPRECATED.search(t) for t in near)
        self.names.append(Name(name=name, kind=kind, file=self.path, line=line,
                               parent=parent, hidden=hidden, default=default,
                               choices=choices, required=required))

    def env(self, name: str, line: int, default: str | None = None) -> None:
        self.direct_env.add(name)
        self.add(name, "env", line, default=default)


@dataclass
class ScanResult:
    names: list[Name]
    skipped: list[Skip]
    prefixes: set[str]


# -- Python ----------------------------------------------------------------------------------

_Scope = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda
_Bindings = dict[str, str | None]


def _dotted(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class _Lit(NamedTuple):
    """A string literal and its line."""

    value: str
    lineno: int


def _str(node: ast.expr | None) -> _Lit | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _Lit(node.value, node.lineno)
    return None


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _const_text(node: ast.expr | None) -> str | None:
    """The text of a constant (``true``/``false`` for booleans); None for null or any
    other expression."""
    if not isinstance(node, ast.Constant) or node.value is None:
        return None
    if isinstance(node.value, bool):
        return "true" if node.value else "false"
    if isinstance(node.value, (str, int, float)):
        return str(node.value)
    return None


def _const_list(node: ast.expr | None) -> list[str] | None:
    """A list or tuple of constants as text; None for anything else."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    items = [_const_text(e) for e in node.elts]
    return None if any(i is None for i in items) else [i for i in items if i is not None]


def _bool(node: ast.expr | None) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


class _Facts(NamedTuple):
    default: str | None = None
    choices: list[str] | None = None
    required: bool | None = None


def _call_facts(call: ast.Call) -> _Facts:
    """``default`` / ``choices`` / ``required`` of an argparse or click option call."""
    default = _const_text(_keyword(call, "default"))
    action = _const_text(_keyword(call, "action"))
    if _keyword(call, "default") is None and action in ("store_true", "store_false"):
        default = "false" if action == "store_true" else "true"
    choices = _const_list(_keyword(call, "choices"))
    kind = _keyword(call, "type")
    if choices is None and isinstance(kind, ast.Call) and (
            _dotted(kind.func) or "").rsplit(".", 1)[-1] == "Choice" and kind.args:
        choices = _const_list(kind.args[0])
    return _Facts(default, choices, _bool(_keyword(call, "required")))


def _call_hides(call: ast.Call) -> bool:
    """``help=argparse.SUPPRESS`` (or a bare ``SUPPRESS``) or ``hidden=True`` in the call."""
    help_value = _keyword(call, "help")
    hidden = _keyword(call, "hidden")
    suppress = help_value is not None and (_dotted(help_value) or "").endswith("SUPPRESS")
    return suppress or (isinstance(hidden, ast.Constant) and hidden.value is True)


def _attr(node: ast.expr) -> str | None:
    """The method name of ``x.method`` or of a call to it."""
    func = node.func if isinstance(node, ast.Call) else node
    return func.attr if isinstance(func, ast.Attribute) else None


def _scopes(tree: ast.Module) -> Iterator[_Scope]:
    yield tree
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            yield node


def _own_nodes(scope: _Scope) -> Iterator[ast.AST]:
    """The nodes of ``scope`` outside its nested functions, classes and lambdas (decorators
    and defaults of a nested definition belong to it too, and are skipped)."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                 ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _params(scope: _Scope) -> set[str]:
    if isinstance(scope, (ast.Module, ast.ClassDef)):
        return set()
    a = scope.args
    every = [*a.posonlyargs, *a.args, *a.kwonlyargs, *filter(None, (a.vararg, a.kwarg))]
    return {arg.arg for arg in every}


def _parser_command(node: ast.expr, local: _Bindings, outer: _Bindings,
                    params: set[str]) -> str | None:
    """The command whose ``add_parser`` made the parser ``node`` evaluates to, or None."""
    if isinstance(node, ast.Call):
        method = _attr(node)
        if method == "add_parser":
            first = _str(node.args[0]) if node.args else None
            return first.value if first else None
        if method in GROUP_METHODS and isinstance(node.func, ast.Attribute):
            return _parser_command(node.func.value, local, outer, params)
        return None
    key = _dotted(node)
    if key is None:
        return None
    if key in local:
        return local[key]
    if key.split(".", 1)[0] in params:
        return None
    return outer.get(key)


def _argparse(scope: _Scope, out: _File, outer: _Bindings) -> _Bindings:
    """Commands and flags of argparse calls in ``scope``; returns the scope's bindings."""
    params = _params(scope)
    local: _Bindings = {}
    nodes = sorted((n for n in _own_nodes(scope)
                    if isinstance(n, (ast.Assign, ast.AnnAssign, ast.Call))),
                   key=lambda n: (n.lineno, n.col_offset))
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            found = (_parser_command(value, local, outer, params)
                     if value is not None else None)
            targets_ = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets_:
                key = _dotted(target)
                if key is not None:
                    local[key] = found
            continue
        method = _attr(node)
        if method == "add_parser":
            first = _str(node.args[0]) if node.args else None
            aliases = _keyword(node, "aliases")
            names = [first] if first else []
            if isinstance(aliases, (ast.List, ast.Tuple)):
                names.extend(c for c in map(_str, aliases.elts) if c)
            for const in names:
                out.add(const.value, "command", const.lineno, hidden=_call_hides(node))
        elif method == "add_argument" and isinstance(node.func, ast.Attribute):
            parent = _parser_command(node.func.value, local, outer, params)
            for const in filter(None, map(_str, node.args)):
                if const.value.startswith("-"):
                    out.add(const.value, "flag", const.lineno, parent, _call_hides(node),
                            *_call_facts(node))
    return local


def _named(call: ast.Call | None) -> _Lit | None:
    """A decorator call's ``name=`` or first positional string."""
    if call is None:
        return None
    return _str(_keyword(call, "name")) or (_str(call.args[0]) if call.args else None)


def _schema_params(schema: ast.expr | None, tool: str, out: _File,
                   dicts: dict[str, ast.Dict]) -> None:
    if isinstance(schema, ast.Name):
        schema = dicts.get(schema.id)
    if not isinstance(schema, ast.Dict):
        return
    items = list(zip(schema.keys, schema.values, strict=True))
    required: list[str] | None = None
    for key, value in items:
        const = _str(key)
        if const is not None and const.value == "required":
            required = _const_list(value)
    for key, value in items:
        const = _str(key)
        if const is None or const.value != "properties":
            continue
        if isinstance(value, ast.Name):
            value = dicts.get(value.id, value)
        if isinstance(value, ast.Dict):
            for pkey, spec in zip(value.keys, value.values, strict=True):
                prop = _str(pkey)
                if prop is None:
                    continue
                default: str | None = None
                choices: list[str] | None = None
                if isinstance(spec, ast.Dict):
                    for k, v in zip(spec.keys, spec.values, strict=True):
                        name = _str(k)
                        if name and name.value == "default":
                            default = _const_text(v)
                        elif name and name.value == "enum":
                            choices = _const_list(v)
                out.add(prop.value, "param", prop.lineno, tool, False, default, choices,
                        None if required is None else prop.value in required)


def _decorated(fn: ast.FunctionDef | ast.AsyncFunctionDef, out: _File,
               dicts: dict[str, ast.Dict]) -> None:
    command: str | None = None
    flags: list[tuple[_Lit, bool, _Facts]] = []
    for dec in fn.decorator_list:
        call = dec if isinstance(dec, ast.Call) else None
        method = _attr(dec)
        hides = call is not None and _call_hides(call)
        named = _named(call)
        if method in COMMAND_DECORATORS and command is None:
            # click (7.0+) and typer expose a function-named command with dashes
            command = named.value if named else fn.name.replace("_", "-")
            hides = hides or (named is None and _underscored(fn.name))
            out.add(command, "command", named.lineno if named else fn.lineno, hidden=hides)
        elif method in FLAG_DECORATORS and call is not None:
            flags.extend((c, hides, _call_facts(call)) for c in map(_str, call.args)
                         if c and c.value.startswith("-"))
        elif method in ROUTE_METHODS | {"route"} and call is not None and call.args:
            path = _str(call.args[0])
            if path and path.value.startswith("/"):
                out.add(path.value, "route", path.lineno, hidden=hides)
        elif method == "tool":
            tool = named.value if named else fn.name
            out.add(tool, "tool", named.lineno if named else fn.lineno, hidden=hides)
            a = fn.args
            for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]:
                annotation = _dotted(arg.annotation) if arg.annotation else None
                if arg.arg in NOT_TOOL_PARAMS or (annotation or "").endswith("Context"):
                    continue
                out.add(arg.arg, "param", arg.lineno, tool)
            if call is not None:
                for keyword in SCHEMA_KEYWORDS:
                    _schema_params(_keyword(call, keyword), tool, out, dicts)
    for const, hides, facts in flags:
        out.add(const.value, "flag", const.lineno, command, hides, *facts)


def _is_environ(node: ast.expr) -> bool:
    return _dotted(node) in ("os.environ", "environ")


def _python_call(call: ast.Call, out: _File, dicts: dict[str, ast.Dict]) -> None:
    func = call.func
    first = _str(call.args[0]) if call.args else None
    getenv = _dotted(func) in ("os.getenv", "getenv")
    environ_get = isinstance(func, ast.Attribute) and func.attr == "get" and _is_environ(
        func.value)
    if first and (getenv or environ_get):
        fallback = _const_text(call.args[1]) if len(call.args) > 1 else None
        out.env(first.value, first.lineno, fallback)
    if (_dotted(func) or "").rsplit(".", 1)[-1] == "Tool":
        name = _str(_keyword(call, "name"))
        if name:
            out.add(name.value, "tool", name.lineno)
            for keyword in SCHEMA_KEYWORDS:
                _schema_params(_keyword(call, keyword), name.value, out, dicts)


def _scan_python(text: str, out: _File) -> bool:
    """Python names of ``text`` into ``out``; False when the file does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    dicts: dict[str, ast.Dict] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Dict):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    dicts[target.id] = stmt.value
    module: _Bindings = {}
    for scope in _scopes(tree):
        bound = _argparse(scope, out, module)
        if scope is tree:
            module = bound
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _decorated(node, out, dicts)
        elif isinstance(node, ast.Call):
            _python_call(node, out, dicts)
        elif (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
              and _is_environ(node.value)):
            key = _str(node.slice)
            if key:
                out.env(key.value, key.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and _ENV_LITERAL.fullmatch(node.value):
            out.literals.append((node.value, node.lineno))
    return True


# -- JavaScript, TypeScript and project files ------------------------------------------------


def _js_flag(spec: str) -> str | None:
    """The flag an ``.option()`` string declares: its first ``--`` token, else its first
    ``-`` token, else a bare yargs name as ``--name`` (``-n`` for one character)."""
    tokens = [t for t in re.split(r"[\s,|]+", spec) if t and t[0] not in "<["]
    token = next((t for t in tokens if t.startswith("--")), None) or next(
        (t for t in tokens if t.startswith("-")), None)
    if token is None and tokens:
        token = ("-" if len(tokens[0]) == 1 else "--") + tokens[0]
    return token if token and _FLAG_TOKEN.fullmatch(token) else None


def _scan_js(text: str, out: _File) -> None:
    for m in _JS_ENV_DOT.finditer(text):
        out.env(m.group(1), _line_at(text, m.start(1)))
    for m in _JS_ENV_INDEX.finditer(text):
        out.env(m.group(2), _line_at(text, m.start(2)))
    for m in _JS_COMMAND.finditer(text):
        word = m.group(2).split()[0] if m.group(2).split() else ""
        if word and word[0] not in "$<[":
            out.add(word, "command", _line_at(text, m.start(2)))
    for m in _JS_OPTION.finditer(text):
        flag = _js_flag(m.group(2))
        if flag:
            out.add(flag, "flag", _line_at(text, m.start(2)))
    for m in _JS_ROUTE.finditer(text):
        out.add(m.group(2), "route", _line_at(text, m.start(2)))


def _scan_project(path: str, text: str, out: _File) -> None:
    base = posixpath.basename(path)
    for name in entry_points(path, text):
        out.add(name, "script", _key_line(text, name))
    for name in targets(path, text):
        out.add(name, "target", _key_line(text, name))
    if fnmatchcase(base, "Dockerfile*") or base.lower().endswith(".dockerfile"):
        for m in _DOCKER_ENV.finditer(text):
            body = m.group(1)
            keys = list(_DOCKER_PAIR.finditer(body))
            first = body.split(None, 1)[0] if body.split() else ""
            if "=" not in first:
                legacy = _DOCKER_LEGACY.match(body)
                keys = [legacy] if legacy else []
            for key in keys:
                out.add(key.group(1), "env", _line_at(text, m.start(1) + key.start(1)))
    if base == ".env.example":
        for m in _DOTENV_KEY.finditer(text):
            out.add(m.group(1), "env", _line_at(text, m.start(1)))


# -- scan ------------------------------------------------------------------------------------


def _prefix(name: str) -> str | None:
    cut = name.find("_")
    return name[: cut + 1] if cut > 0 else None


def scan_files(files: Iterable[str], read: Reader,
               prefixes: Iterable[str] = ()) -> ScanResult:
    """Scan ``files`` (read through ``read``) for user-facing names. Env families use the
    prefixes of the env names read directly in these files plus ``prefixes``."""
    scanned: list[_File] = []
    skipped: list[Skip] = []
    for path in files:
        text = read(path)
        if text is None:
            skipped.append(Skip(file=path, reason="unreadable"))
            continue
        out = _File(path, text.splitlines())
        if path.endswith(PY_EXTENSIONS):
            if not _scan_python(text, out):
                skipped.append(Skip(file=path, reason="syntax error"))
                continue
        else:
            if path.endswith(JS_EXTENSIONS):
                _scan_js(text, out)
            else:
                _scan_project(path, text, out)
            out.literals.extend((m.group(2), _line_at(text, m.start(2)))
                                for m in _QUOTED_ENV.finditer(text))
        scanned.append(out)
    family = set(prefixes)
    family.update(p for f in scanned for v in f.direct_env if (p := _prefix(v)))
    for f in scanned:
        for value, line in f.literals:
            if any(value.startswith(p) and value != p for p in family):
                f.add(value, "env", line)
    unique: dict[tuple[str, int, str, str, str], Name] = {}
    for f in scanned:
        for n in f.names:
            key = (n["file"], n["line"], n["kind"], n["name"], n["parent"] or "")
            held = unique.get(key)
            # a family literal re-finds a direct read: keep the record that has the facts
            if held is None or not (held["default"] or held["choices"]) or n["default"]:
                unique[key] = n
    names = [unique[key] for key in sorted(unique)]
    return ScanResult(names=names, skipped=sorted(skipped, key=lambda s: s["file"]),
                      prefixes=family)


def scan(files: Iterable[str], read: Reader, prefixes: Iterable[str] = ()) -> list[Name]:
    """The user-facing names in ``files``, sorted by (file, line, kind, name)."""
    return scan_files(files, read, prefixes).names


def _load(path: Path, step: str) -> Any:
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Scan the indexed files now and the changed ones at the last-run commit (from
    ``changes.json``); write ``patterns.json``."""
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    changes = _load(workdir / "changes.json", "dd_changes")
    files = indexed_files(inventory)

    def read_now(path: str) -> str | None:
        try:
            return (root / path).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    now = scan_files(files, read_now)
    names_then: list[Name] | None = None
    sha = changes.get("last_run")
    if isinstance(sha, str) and sha:
        history = History(root)
        indexed = set(files)
        changed = [p for p in changes.get("changed_files", []) if p in indexed]
        names_then = scan_files(changed, lambda p: history.show(sha, p), now.prefixes).names
    result: dict[str, Any] = {"names": now.names, "names_then": names_then,
                              "skipped": now.skipped}
    write_json(workdir / "patterns.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan the indexed files for user-facing names (commands, flags, env "
                    "vars, routes, MCP tools, scripts, targets).")
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
