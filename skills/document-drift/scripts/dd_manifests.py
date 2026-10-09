"""Manifest parsing for the resolvers: script names per tool and runtime version floors.

Every function is pure over a tree: ``files`` is the set of repository paths in it and
``read(path)`` returns a file's text in that same tree (or None), so the same code answers for
HEAD, for a line snapshot and for an in-memory re-check.

Scripts (spec 6.1): ``Makefile`` targets, ``package.json`` ``scripts`` keys, ``justfile``
recipes and ``Taskfile.yml`` ``tasks`` keys, looked up in every manifest of the tool from the
doc's directory up to the root (nearest first). A manifest is *open* when it can define names
this parser cannot see (ruling R25): it does not parse, a Makefile has an include it cannot
follow (glob, variable, missing file), a pattern rule (``%``) or a variable target
(``$(VAR):``), a justfile has ``import`` or ``mod``, a Taskfile has ``includes:``. An open
manifest defines every name when asking whether a script still exists (lenient, HEAD) and only
its visible names when asking whether it existed at a snapshot (strict).

Versions: only declared floors count (ruling R28): ``pyproject.toml``
``[project].requires-python``, ``package.json`` ``engines.node``, the ``go.mod`` ``go``
directive and ``Cargo.toml`` ``[package].rust-version``, from the nearest manifest walking up
from the doc's directory. Pin files (``.python-version``, ``.nvmrc``, ``.tool-versions``) state
what one machine runs, not what the project supports, and are never read. Floors compare at the
lower of the two precisions (ruling R29).
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
    "python": ("pyproject.toml",),
    "node": ("package.json",),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
}

# The plan's rule ``^([A-Za-z0-9_.-]+)\s*:(?!=)`` widened to several targets on one rule line
# (``all test: deps``); ``::`` rules count, ``:=`` and ``::=`` assignments do not.
_MAKE_RULE = re.compile(
    r"^([A-Za-z0-9_.\-]+(?:[ \t]+[A-Za-z0-9_.\-]+)*)[ \t]*(?:::(?!=)|:(?![=:]))", re.M
)
# A rule line whose targets hold ``%`` (pattern rule) or ``$`` (variable target).
_MAKE_OPEN_RULE = re.compile(r"^[^\t#:=\n]*[%$][^:=\n]*:(?!=)", re.M)
_MAKE_SPECIAL = re.compile(r"\.[A-Z_]+")  # .PHONY, .DEFAULT, .SUFFIXES ...
_MAKE_INCLUDE = re.compile(r"^-?s?include[ \t]+(.+)$", re.M)
_JUST_RECIPE = re.compile(r"^@?([A-Za-z0-9_-]+)(\s+[^:\n]*)?:(?!=)", re.M)
_JUST_ALIAS = re.compile(r"^alias[ \t]+([A-Za-z0-9_-]+)[ \t]*:=", re.M)
_JUST_OPEN = re.compile(r"^(?:import|mod)\??[ \t]", re.M)
_VERSION = re.compile(r"\d+(?:\.\d+){0,2}")
_PY_CLAUSE = re.compile(r"^(>=|~=|==|\^|~)?\s*(\d+(?:\.\d+){0,2})(?:\.\*)?$")
_NODE_CLAUSE = re.compile(r"^(>=|\^|~|=)?\s*v?(\d+(?:\.\d+){0,2})(?:\.[x*])*$")
_GO_DIRECTIVE = re.compile(r"^go[ \t]+(\d+(?:\.\d+){0,2})[ \t]*$", re.M)

Names = tuple[set[str], bool]  # (visible names, open)


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
                  depth: int = 0) -> Names:
    names: set[str] = set()
    for m in _MAKE_RULE.finditer(text):
        names.update(n for n in m.group(1).split() if not _MAKE_SPECIAL.fullmatch(n))
    is_open = _MAKE_OPEN_RULE.search(text) is not None
    base = posixpath.dirname(path)
    for m in _MAKE_INCLUDE.finditer(text):
        for word in m.group(1).split():
            inc = posixpath.normpath(_join(base, word))
            followable = depth < 3 and not any(c in word for c in "$*?[") and inc in files
            body = read(inc) if followable else None
            if body is None:
                is_open = True
                continue
            sub, sub_open = _make_targets(inc, body, files, read, depth + 1)
            names |= sub
            is_open = is_open or sub_open
    return names, is_open


def _script_names(tool: str, path: str, text: str, files: frozenset[str],
                  read: Reader) -> Names:
    if tool == "make":
        return _make_targets(path, text, files, read)
    if tool == "just":
        names = {m.group(1) for m in _JUST_RECIPE.finditer(text)}
        names |= {m.group(1) for m in _JUST_ALIAS.finditer(text)}
        return names, _JUST_OPEN.search(text) is not None
    try:
        data: Any = json.loads(text) if tool in ("npm", "yarn", "pnpm") else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError):
        return set(), True
    key = "scripts" if tool in ("npm", "yarn", "pnpm") else "tasks"
    section = data.get(key) if isinstance(data, dict) else None
    is_open = tool == "task" and isinstance(data, dict) and "includes" in data
    if not isinstance(section, dict):
        return set(), is_open
    found = {str(k) for k in section}
    if tool == "task":
        for body in section.values():
            aliases = body.get("aliases") if isinstance(body, dict) else None
            if isinstance(aliases, list):
                found.update(str(a) for a in aliases)
    return found, is_open


def script_source(doc: str, tool: str, name: str, files: frozenset[str], read: Reader,
                  strict: bool = False) -> str | None:
    """The nearest manifest of ``tool`` that defines ``name``, else None.

    An open manifest counts as defining every name unless ``strict``: lenient when asking
    whether a script still exists, strict when asking whether it existed at a snapshot.
    """
    for path in script_manifests(doc, tool, files):
        text = read(path)
        if text is None:
            continue
        names, is_open = _script_names(tool, path, text, files, read)
        if name in names or (is_open and not strict):
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
    if isinstance(raw, str) and floor is not None:
        return raw, floor
    return None


def manifest_floor(doc: str, runtime: str, files: frozenset[str],
                   read: Reader) -> tuple[str, str, str] | None:
    """(manifest path, raw value, floor) of the nearest manifest declaring the runtime floor."""
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


def at_precision(doc_floor: str, manifest: str) -> str:
    """The manifest floor cut to as many components as the doc's floor states."""
    return ".".join(manifest.split(".")[: len(doc_floor.split("."))])


def same_floor(doc_floor: str, manifest: str) -> bool:
    """True when the floors agree at the lower of the two precisions (ruling R29)."""
    a = doc_floor.split(".")
    b = manifest.split(".")
    width = min(len(a), len(b))
    return [int(p) for p in a[:width]] == [int(p) for p in b[:width]]
