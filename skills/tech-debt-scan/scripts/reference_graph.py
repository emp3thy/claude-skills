"""Approximate file reference graph by identifier stems (spec 4.2).

Each source file is a target whose stem is its basename before the first dot,
lower-cased. Every source and tests file is a referrer: its identifier tokens
(``TOKEN_RE``, which keeps hyphenated module names whole) are intersected with
an inverted stem index, one set operation per file.

Two modes. ``import-lines`` (the default) only looks at import-like logical
lines: a line matching ``IMPORT_LINE_RE`` or containing ``require(``,
``import(``, ``from "`` or ``from '``; lines are joined while a bracket is
open or the line ends in a backslash or a comma, so multi-line imports and
Go ``import (`` blocks count. ``anywhere`` matches tokens over the whole file
and is the labelled lower-confidence fallback; under ``mode: auto`` it applies
to every file of a language that matched no import-like line anywhere in the
repository, and the targets it reaches are marked ``fan_in_mode: anywhere``.

Ambiguity is mechanical: a target with a stem shorter than
``min_stem_length``, a stem shared by two or more targets, a package or index
name, a test-harness name, or a stoplist name gets ``fan_in_approx`` None.
Package files are never mapped to their directory name and the stoplist is
never extended with domain vocabulary.

Cycles are Tarjan SCCs of size 2 to 5 over import-lines edges only, emitted
as capped leads for the architecture scout, never as findings. Directory
aggregates and unstable edges use edges between source files.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

IMPORT_LINE_RE = re.compile(
    r"^\s*(import|from|using|use|require|include|#include|load|open|extern crate|"
    r"require_relative|@import|@use)\b"
)
IMPORT_CALL_RE = re.compile(r"require\(|import\(|from \"|from '")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
MAX_CONTINUATION = 200
MIN_CYCLE = 2
MAX_CYCLE = 5
_OPEN = "([{"
_CLOSE = ")]}"


@dataclass(slots=True)
class GraphFile:
    path: str
    language: str
    path_class: str
    text: str
    loc: int = 0
    churn: int = 0


@dataclass(slots=True)
class GraphResult:
    fan_in: dict[str, int | None] = field(default_factory=dict)
    fan_out: dict[str, int] = field(default_factory=dict)
    mode: dict[str, str] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    ambiguous: dict[str, str] = field(default_factory=dict)
    cycles: list[dict[str, Any]] = field(default_factory=list)
    directories: list[dict[str, Any]] = field(default_factory=list)
    unstable_edges: list[dict[str, Any]] = field(default_factory=list)


def file_stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.split(".", 1)[0].lower()


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _unclosed(text: str) -> bool:
    depth = 0
    for char in text:
        if char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth -= 1
    return depth > 0


def _continues(buffer: str) -> bool:
    stripped = buffer.rstrip()
    return bool(stripped) and (stripped.endswith(("\\", ",")) or _unclosed(stripped))


def numbered_logical_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    """(1-based start line, joined text): continuations joined by a single space."""
    out: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    joined = 0
    for index, raw in enumerate(lines, start=1):
        if buffer:
            buffer = buffer + " " + raw.strip()
            joined += 1
        else:
            buffer = raw
            start = index
            joined = 0
        if _continues(buffer) and joined < MAX_CONTINUATION:
            continue
        out.append((start, buffer))
        buffer = ""
    if buffer:
        out.append((start, buffer))
    return out


def logical_lines(text: str) -> list[str]:
    """Physical lines with continuations joined by a single space."""
    return [line for _, line in numbered_logical_lines(text.splitlines())]


def is_import_line(line: str) -> bool:
    return bool(IMPORT_LINE_RE.match(line) or IMPORT_CALL_RE.search(line))


def import_lines(text: str) -> list[str]:
    return [line for line in logical_lines(text) if is_import_line(line)]


def identifier_tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def tarjan_scc(adjacency: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components (iterative Tarjan), each sorted, in finish order."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0
    for root in sorted(adjacency):
        if root in index_of:
            continue
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(sorted(adjacency.get(root, ()))))]
        while work:
            node, children = work[-1]
            descended = False
            for child in children:
                if child not in adjacency:
                    continue
                if child not in index_of:
                    index_of[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(adjacency.get(child, ())))))
                    descended = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index_of[child])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                component: list[str] = []
                while True:
                    top = stack.pop()
                    on_stack.discard(top)
                    component.append(top)
                    if top == node:
                        break
                result.append(sorted(component))
    return result


def _round(value: float) -> float:
    return round(value, 3)


def build_reference_graph(files: Sequence[GraphFile], fan_in_cfg: dict[str, Any]) -> GraphResult:
    """Fan-in, fan-out, modes, cycles and directory aggregates for ``files``."""
    mode_cfg = str(fan_in_cfg.get("mode", "auto"))
    min_len = int(fan_in_cfg.get("min_stem_length", 4))
    ambiguous_cfg = fan_in_cfg.get("ambiguous") or {}
    shared_stem = bool(ambiguous_cfg.get("shared_stem", True))
    package_files = {str(n) for n in ambiguous_cfg.get("package_files") or []}
    harness_files = {str(n) for n in ambiguous_cfg.get("harness_files") or []}
    stoplist = {str(n) for n in fan_in_cfg.get("stoplist") or []}

    targets = [f for f in files if f.path_class == "source"]
    referrers = [f for f in files if f.path_class in ("source", "tests")]
    stem_of = {f.path: file_stem(f.path) for f in targets}
    stem_count = Counter(stem_of.values())

    result = GraphResult()
    index: dict[str, str] = {}
    for path, stem in stem_of.items():
        if len(stem) < min_len:
            result.ambiguous[path] = "short-stem"
        elif shared_stem and stem_count[stem] > 1:
            result.ambiguous[path] = "shared-stem"
        elif stem in package_files:
            result.ambiguous[path] = "package-file"
        elif stem in harness_files:
            result.ambiguous[path] = "harness-file"
        elif stem in stoplist:
            result.ambiguous[path] = "stoplist"
        else:
            index[stem] = path
    result.fan_in = {p: (None if p in result.ambiguous else 0) for p in stem_of}
    result.fan_out = {p: 0 for p in stem_of}
    result.mode = dict.fromkeys(stem_of, "import-lines")

    lines_of = {f.path: import_lines(f.text) for f in referrers}
    lang_has_imports: set[str] = {f.language for f in referrers if lines_of[f.path]}

    def mode_for(referrer: GraphFile) -> str:
        if mode_cfg == "import-lines":
            return "import-lines"
        if mode_cfg == "anywhere":
            return "anywhere"
        return "import-lines" if referrer.language in lang_has_imports else "anywhere"

    strict_edges: list[tuple[str, str]] = []
    stems = set(index)
    for referrer in referrers:
        mode = mode_for(referrer)
        if mode == "import-lines":
            tokens = identifier_tokens("\n".join(lines_of[referrer.path]))
        else:
            tokens = identifier_tokens(referrer.text)
        for stem in sorted(tokens & stems):
            target = index[stem]
            if target == referrer.path:
                continue
            result.edges.append((referrer.path, target))
            current = result.fan_in[target]
            result.fan_in[target] = (current or 0) + 1
            if referrer.path in result.fan_out:
                result.fan_out[referrer.path] += 1
            if mode == "anywhere":
                result.mode[target] = "anywhere"
            else:
                strict_edges.append((referrer.path, target))

    adjacency: dict[str, set[str]] = {p: set() for p in index.values()}
    for source, target in strict_edges:
        if source in adjacency:
            adjacency[source].add(target)
    for component in tarjan_scc(adjacency):
        if MIN_CYCLE <= len(component) <= MAX_CYCLE:
            result.cycles.append(
                {"members": component, "approximate": True, "source": "import-lines",
                 "lead_only": True}
            )
    result.cycles.sort(key=lambda c: c["members"])

    dir_files: Counter[str] = Counter()
    dir_loc: Counter[str] = Counter()
    dir_churn: Counter[str] = Counter()
    for target_file in targets:
        directory = _dirname(target_file.path)
        dir_files[directory] += 1
        dir_loc[directory] += target_file.loc
        dir_churn[directory] += target_file.churn
    dir_in: Counter[str] = Counter()
    dir_out: Counter[str] = Counter()
    dir_edges: set[tuple[str, str]] = set()
    for source, target in result.edges:
        if source not in stem_of:
            continue  # tests-class referrers do not shape directory structure
        from_dir, to_dir = _dirname(source), _dirname(target)
        if from_dir == to_dir:
            continue
        dir_out[from_dir] += 1
        dir_in[to_dir] += 1
        dir_edges.add((from_dir, to_dir))
    instability: dict[str, float] = {}
    for directory in sorted(dir_files):
        total = dir_in[directory] + dir_out[directory]
        instability[directory] = _round(dir_out[directory] / total) if total else 0.0
        result.directories.append(
            {
                "path": directory,
                "files": dir_files[directory],
                "loc": dir_loc[directory],
                "churn": dir_churn[directory],
                "fan_in": dir_in[directory],
                "fan_out": dir_out[directory],
                "instability": instability[directory],
            }
        )
    for from_dir, to_dir in sorted(dir_edges):
        if instability[from_dir] < 0.3 and instability[to_dir] > 0.7:
            result.unstable_edges.append(
                {
                    "from": from_dir,
                    "to": to_dir,
                    "from_instability": instability[from_dir],
                    "to_instability": instability[to_dir],
                }
            )
    return result
