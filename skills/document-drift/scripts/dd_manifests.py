"""Manifest parsing for the resolvers: script names per tool and runtime version floors.

Every function is pure over a tree: ``files`` is the set of repository paths in it and
``read(path)`` returns a file's text in that same tree (or None), so the same code answers for
HEAD, for a line snapshot and for an in-memory re-check.

Scripts (spec 6.1): ``Makefile`` targets, ``package.json`` ``scripts`` keys, ``justfile``
recipes and ``Taskfile.yml`` ``tasks`` keys, looked up in every manifest of the tool from the
doc's directory up to the root (nearest first). A manifest that cannot be parsed counts as
defining every name, so a broken manifest never turns into a deletion.

Versions: the nearest manifest value for the runtime, walking up from the doc's directory;
within a directory ``pyproject.toml`` before ``.python-version`` and ``package.json`` before
``.nvmrc``.
"""
from __future__ import annotations

import json
import posixpath
import re
import tomllib
from collections.abc import Callable
from typing import Any

import yaml

Reader = Callable[[str], str | None]

SCRIPT_MANIFESTS: dict[str, tuple[str, ...]] = {
    "make": ("Makefile", "makefile", "GNUmakefile"),
    "npm": ("package.json",),
    "yarn": ("package.json",),
    "pnpm": ("package.json",),
    "just": ("justfile", "Justfile", ".justfile"),
    "task": ("Taskfile.yml", "Taskfile.yaml", "taskfile.yml", "taskfile.yaml"),
}
VERSION_MANIFESTS: dict[str, tuple[str, ...]] = {
    "python": ("pyproject.toml", ".python-version"),
    "node": ("package.json", ".nvmrc"),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
}

# The plan's rule ``^([A-Za-z0-9_.-]+)\s*:(?!=)`` widened to several targets on one rule line
# (``all test: deps``); ``::`` rules count, ``:=`` and ``::=`` assignments do not.
_MAKE_RULE = re.compile(
    r"^([A-Za-z0-9_.\-]+(?:[ \t]+[A-Za-z0-9_.\-]+)*)[ \t]*(?:::(?!=)|:(?![=:]))", re.M
)
_MAKE_SPECIAL = re.compile(r"\.[A-Z_]+")  # .PHONY, .DEFAULT, .SUFFIXES ...
_MAKE_INCLUDE = re.compile(r"^-?s?include[ \t]+(.+)$", re.M)
_JUST_RECIPE = re.compile(r"^@?([A-Za-z0-9_-]+)(\s+[^:\n]*)?:(?!=)", re.M)
_JUST_ALIAS = re.compile(r"^alias[ \t]+([A-Za-z0-9_-]+)[ \t]*:=", re.M)
_VERSION = re.compile(r"\d+(?:\.\d+){0,2}")
_PY_CLAUSE = re.compile(r"^(>=|~=|==|\^|~)?\s*(\d+(?:\.\d+){0,2})(?:\.\*)?$")
_NODE_CLAUSE = re.compile(r"^(>=|\^|~|=)?\s*v?(\d+(?:\.\d+){0,2})(?:\.[x*])*$")
_GO_DIRECTIVE = re.compile(r"^go[ \t]+(\d+(?:\.\d+){0,2})[ \t]*$", re.M)


class _Unparsed(Exception):
    """A manifest exists but its names cannot be read."""


def ancestors(doc: str) -> list[str]:
    """The doc's directory and each parent up to the root (``""``), nearest first."""
    out: list[str] = []
    d = posixpath.dirname(doc)
    while True:
        out.append(d)
        if not d:
            return out
        d = posixpath.dirname(d)


def _join(d: str, name: str) -> str:
    return f"{d}/{name}" if d else name


def script_manifests(doc: str, tool: str, files: frozenset[str]) -> list[str]:
    """Every manifest of ``tool`` from the doc's directory up to the root, nearest first."""
    names = SCRIPT_MANIFESTS.get(tool, ())
    return [p for d in ancestors(doc) for n in names if (p := _join(d, n)) in files]


def _make_targets(path: str, text: str, files: frozenset[str], read: Reader,
                  depth: int = 0) -> set[str]:
    names: set[str] = set()
    for m in _MAKE_RULE.finditer(text):
        names.update(n for n in m.group(1).split() if not _MAKE_SPECIAL.fullmatch(n))
    if depth < 3:
        base = posixpath.dirname(path)
        for m in _MAKE_INCLUDE.finditer(text):
            for word in m.group(1).split():
                if any(c in word for c in "$*?["):
                    continue
                inc = posixpath.normpath(_join(base, word))
                body = read(inc) if inc in files else None
                if body is not None:
                    names |= _make_targets(inc, body, files, read, depth + 1)
    return names


def _script_names(tool: str, path: str, text: str, files: frozenset[str],
                  read: Reader) -> set[str]:
    if tool == "make":
        return _make_targets(path, text, files, read)
    if tool == "just":
        return {m.group(1) for m in _JUST_RECIPE.finditer(text)} | {
            m.group(1) for m in _JUST_ALIAS.finditer(text)}
    try:
        data: Any = json.loads(text) if tool in ("npm", "yarn", "pnpm") else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        raise _Unparsed(path) from exc
    key = "scripts" if tool in ("npm", "yarn", "pnpm") else "tasks"
    section = data.get(key) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return set()
    names = {str(k) for k in section}
    if tool == "task":
        for body in section.values():
            aliases = body.get("aliases") if isinstance(body, dict) else None
            if isinstance(aliases, list):
                names.update(str(a) for a in aliases)
    return names


def script_source(doc: str, tool: str, name: str, files: frozenset[str], read: Reader,
                  strict: bool = False) -> str | None:
    """The nearest manifest of ``tool`` that defines ``name``, else None.

    An unparsable manifest counts as defining every name unless ``strict``: lenient when asking
    whether a script still exists, strict when asking whether it existed at a snapshot.
    """
    for path in script_manifests(doc, tool, files):
        text = read(path)
        if text is None:
            continue
        try:
            if name in _script_names(tool, path, text, files, read):
                return path
        except _Unparsed:
            if not strict:
                return path
    return None


# -- versions --------------------------------------------------------------------------------


def _python_floor(spec: str) -> str | None:
    for clause in spec.split(","):
        m = _PY_CLAUSE.match(clause.strip())
        if m:
            return m.group(2)
    return None


def _node_floor(spec: str) -> str | None:
    if "||" in spec:
        return None
    for clause in spec.replace(",", " ").split():
        m = _NODE_CLAUSE.match(clause)
        if m:
            return m.group(2)
    return None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return ""


def _value(name: str, text: str) -> tuple[str, str] | None:
    """(raw value, floor) from one manifest file's text, or None."""
    raw: Any = None
    floor: str | None = None
    if name in ("pyproject.toml", "Cargo.toml"):
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return None
        if name == "pyproject.toml":
            raw = data.get("project", {}).get("requires-python")
            floor = _python_floor(raw) if isinstance(raw, str) else None
        else:
            raw = data.get("package", {}).get("rust-version")
            if not isinstance(raw, str):
                raw = data.get("workspace", {}).get("package", {}).get("rust-version")
            floor = raw if isinstance(raw, str) and _VERSION.fullmatch(raw) else None
    elif name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return None
        engines = data.get("engines") if isinstance(data, dict) else None
        raw = engines.get("node") if isinstance(engines, dict) else None
        floor = _node_floor(raw) if isinstance(raw, str) else None
    elif name == "go.mod":
        m = _GO_DIRECTIVE.search(text)
        raw = floor = m.group(1) if m else None
    else:  # .python-version, .nvmrc
        raw = _first_line(text)
        m = re.fullmatch(r"v?(\d+(?:\.\d+){0,2})", raw)
        floor = m.group(1) if m else None
    if isinstance(raw, str) and floor is not None:
        return raw, floor
    return None


def manifest_floor(doc: str, runtime: str, files: frozenset[str],
                   read: Reader) -> tuple[str, str, str] | None:
    """(manifest path, raw value, floor) of the nearest manifest stating the runtime floor."""
    for d in ancestors(doc):
        for name in VERSION_MANIFESTS.get(runtime, ()):
            path = _join(d, name)
            text = read(path) if path in files else None
            if text is None:
                continue
            found = _value(name, text)
            if found is not None:
                return path, found[0], found[1]
    return None


def _parts(version: str) -> list[int]:
    return [int(p) for p in version.split(".")]


def at_precision(doc_floor: str, manifest: str) -> str:
    """The manifest floor cut to as many components as the doc's floor states."""
    return ".".join(manifest.split(".")[: len(doc_floor.split("."))])


def same_floor(doc_floor: str, manifest: str) -> bool:
    """True when the floors agree at the doc's precision (missing components count as 0)."""
    a = _parts(doc_floor)
    b = _parts(at_precision(doc_floor, manifest))
    width = max(len(a), len(b))
    return a + [0] * (width - len(a)) == b + [0] * (width - len(b))
