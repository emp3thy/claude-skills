"""Run already-installed external tools and write ``tool-signals.json`` (spec 4.5).

Never installs anything, never invokes ``npx`` and never executes project
code. Presence is ``shutil.which``, then ``<root>/node_modules/.bin``
for the three Node tools only. Each present tool runs under a per-tool timeout
and is recorded as ``ran``, ``absent``, ``failed`` or ``skipped``.

The registry is the whole contract: one row per tool giving how to invoke it,
when it is worth invoking, where its output appears, which exit codes mean
what, which normaliser reads it, and whether its signals are fact-class.
Adding a tool is a row plus a pure function in ``tool_normalisers.py``.

Nothing reads ``tool-signals.json`` until phase 4b.
"""
from __future__ import annotations

import contextlib
import csv
import json
import shutil
import subprocess
import tempfile
import time
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
    depends on; ``npx`` would fetch a package to run it, which spec 4.5 forbids.
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


STDERR_CHARS: Final[int] = 200
REPORT_FILENAME: Final[str] = "jscpd-report.json"


@dataclass(frozen=True)
class ToolResult:
    """What one attempted tool run produced."""

    status: str  # "ran", "absent", "failed" or "skipped"
    payload: Any = None
    reason: str = ""
    duration_s: float = 0.0


def _parse(spec: ToolSpec, text: str) -> Any:
    """The tool's raw output as its declared shape, or ValueError."""
    if spec.parse == "json":
        return json.loads(text)
    if spec.parse == "lines":
        return [line for line in text.splitlines() if line.strip()]
    if spec.parse == "csv":
        return [row for row in csv.reader(text.splitlines()) if row]
    raise ValueError(f"unknown parse mode {spec.parse!r}")


def _rejected_exit_reason(returncode: int, stderr: str) -> str:
    """A failure reason that unambiguously names a rejected exit code.

    The ``exit N`` prefix is always added, rather than checking whether
    ``stderr`` happens to already contain the number as a substring: stderr
    text with a coincidentally matching digit (a line number, a byte count)
    must never suppress the prefix.
    """
    if stderr:
        return f"exit {returncode}: {stderr}"[:STDERR_CHARS]
    return f"exit {returncode}"


def run_tool(spec: ToolSpec, argv: list[str], root: Path, timeout_s: int) -> ToolResult:
    """Run one tool and classify the attempt.

    ``argv`` already carries the executable as its first element; the caller
    builds it (see ``argv_for``).

    ``ran`` means the process exited with a code the spec's table allows and
    its output parsed. Anything else is ``failed``, carrying the first
    ``STDERR_CHARS`` characters of stderr, because unparseable output is the
    failure signal for every tool in the first cut.

    A ``report_file`` tool writes its result into a directory this function
    creates and removes; its stdout is progress and promotional text and is
    never parsed. For that channel the report decides and the exit code is
    only commentary: a present, parseable report is ``ran`` whatever the exit
    code, because the temporary directory is created fresh for each run, so a
    present report can only have been written by this run. The exit code is
    consulted only when the report is absent or unparseable, and then the
    same rules as the stdout channel apply.
    """
    started = time.monotonic()
    report_dir: tempfile.TemporaryDirectory[str] | None = None
    full_argv = list(argv)
    if spec.channel == "report_file":
        report_dir = tempfile.TemporaryDirectory(dir=root, ignore_cleanup_errors=True)
        full_argv.append(report_dir.name)
    try:
        try:
            completed = subprocess.run(  # noqa: S603 - argv is built from the registry
                full_argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                cwd=root,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult("failed", reason=f"timed out after {timeout_s}s",
                              duration_s=time.monotonic() - started)
        except OSError as exc:
            return ToolResult("failed", reason=str(exc)[:STDERR_CHARS],
                              duration_s=time.monotonic() - started)

        duration = time.monotonic() - started
        stderr = (completed.stderr or "").strip()[:STDERR_CHARS]

        if spec.channel == "report_file":
            assert report_dir is not None
            report = Path(report_dir.name) / REPORT_FILENAME
            if report.is_file():
                try:
                    payload = _parse(spec, report.read_text(encoding="utf-8", errors="replace"))
                except (ValueError, csv.Error):
                    pass
                else:
                    return ToolResult("ran", payload=payload, duration_s=duration)

            if completed.returncode != 0 and completed.returncode not in spec.findings_exit:
                reason = _rejected_exit_reason(completed.returncode, stderr)
                return ToolResult("failed", reason=reason, duration_s=duration)
            if not report.is_file():
                return ToolResult("failed", reason=f"no {REPORT_FILENAME} report written",
                                  duration_s=duration)
            return ToolResult("failed", reason=stderr or "unparseable output",
                              duration_s=duration)

        if completed.returncode != 0 and completed.returncode not in spec.findings_exit:
            reason = _rejected_exit_reason(completed.returncode, stderr)
            return ToolResult("failed", reason=reason, duration_s=duration)

        try:
            payload = _parse(spec, completed.stdout or "")
        except (ValueError, csv.Error):
            return ToolResult("failed", reason=stderr or "unparseable output",
                              duration_s=duration)
        return ToolResult("ran", payload=payload, duration_s=duration)
    finally:
        if report_dir is not None:
            with contextlib.suppress(OSError):
                report_dir.cleanup()
