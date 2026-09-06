"""Run already-installed external tools and write ``tool-signals.json`` (spec 4.5).

Never installs anything, never invokes external package managers and never
executes project code. Presence is ``shutil.which``, then ``<root>/node_modules/.bin``
for the three Node tools only. Each present tool runs under a per-tool timeout
and is recorded as ``ran``, ``absent``, ``failed`` or ``skipped``.

The registry is the whole contract: one row per tool giving how to invoke it,
when it is worth invoking, where its output appears, which exit codes mean
what, which normaliser reads it, and whether its signals are fact-class.
Adding a tool is a row plus a pure function in ``tool_normalisers.py``.

Nothing reads ``tool-signals.json`` until phase 4b.
"""
from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from tool_normalisers import Signal

# A normaliser takes a parsed payload and the repo root and returns signals.
Normaliser = Callable[[Any, Path], list[Signal]]

NODE_TOOLS: Final[frozenset[str]] = frozenset({"jscpd", "knip", "madge"})


@dataclass(frozen=True)
class ToolSpec:
    """One registry row: everything the runner needs to know about a tool."""

    name: str
    fact: bool
    channel: str  # "stdout" or "report_file"
    parse: str  # "json", "csv" or "lines"
    findings_exit: tuple[int, ...]  # exit codes that mean "ran, found things"
    timeout_s: int | None = None  # None means the config default
    node_bin: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


TOOLS: Final[dict[str, ToolSpec]] = {
    "osv-scanner": ToolSpec("osv-scanner", True, "stdout", "json", (1,), 300),
    "gitleaks": ToolSpec("gitleaks", True, "stdout", "json", (1,)),
    "hadolint": ToolSpec("hadolint", True, "stdout", "json", (1,)),
    "actionlint": ToolSpec("actionlint", True, "stdout", "json", (1,)),
    "ruff": ToolSpec("ruff", False, "stdout", "json", (1,)),
    "vulture": ToolSpec("vulture", False, "stdout", "lines", (3,)),
    "lizard": ToolSpec("lizard", False, "stdout", "csv", ()),
    "jscpd": ToolSpec("jscpd", False, "report_file", "json", (), None, True),
    "knip": ToolSpec("knip", False, "stdout", "json", (1,), None, True),
    "madge": ToolSpec("madge", False, "stdout", "json", (1,), None, True),
}


def find_tool(name: str, root: Path) -> str | None:
    """The executable for ``name``, or None when it is not installed.

    ``shutil.which`` first, then ``<root>/node_modules/.bin`` for the three
    Node tools. A project-local binary is a tool the repository already
    depends on; external package managers would fetch one, which spec 4.5 forbids.
    """
    found = shutil.which(name)
    if found:
        return found
    if name not in NODE_TOOLS:
        return None
    bin_dir = root / "node_modules" / ".bin"
    for suffix in ("", ".cmd", ".exe", ".ps1"):
        candidate = bin_dir / f"{name}{suffix}"
        if candidate.is_file():
            return str(candidate)
    return None
