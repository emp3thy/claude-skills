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

import argparse
import contextlib
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

from config import ConfigError, load_config
from inventory import DEFAULT_IGNORE, PATH_CLASS_GLOBS, write_json
from redaction import redact
from tool_normalisers import (
    Signal,
    normalise_actionlint,
    normalise_gitleaks,
    normalise_hadolint,
    normalise_jscpd,
    normalise_knip,
    normalise_lizard,
    normalise_madge,
    normalise_osv_scanner,
    normalise_ruff,
    normalise_vulture,
)

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


SCHEMA_VERSION: Final[int] = 2

NORMALISERS: Final[dict[str, Normaliser]] = {
    "osv-scanner": normalise_osv_scanner,
    "gitleaks": normalise_gitleaks,
    "ruff": normalise_ruff,
    "vulture": normalise_vulture,
    "lizard": normalise_lizard,
    "jscpd": normalise_jscpd,
    "knip": normalise_knip,
    "madge": normalise_madge,
    "hadolint": normalise_hadolint,
    "actionlint": normalise_actionlint,
}

# Every extension lizard's own parsers accept (``lizard.languages()``), in
# rough order of how likely a repository is to hold one, because
# ``artefact_present`` stops at the first pattern that matches: the common
# case costs one glob and only a repository lizard cannot read at all pays for
# the whole list. The predicate has to name all of them because the
# invocation scans all of them -- the narrower six-extension list this
# replaced meant a repository written entirely in, say, Ruby or C was never
# offered to a tool that would have parsed it.
_LIZARD_EXTENSIONS: Final[tuple[str, ...]] = (
    "py", "ts", "js", "tsx", "jsx", "java", "go", "cs", "c", "h", "cpp", "cc", "cxx",
    "hpp", "rb", "php", "rs", "kt", "kts", "swift", "scala", "lua", "m", "mm", "pl",
    "pm", "sql", "vue", "zig", "sol", "gd", "erl", "hrl", "escript", "es", "cjs",
    "mjs", "r", "R", "st", "ttcn", "ttcnpp", "pck", "pkb", "pks", "plb", "pls",
    "f", "for", "f90", "f95", "f03", "f08", "f70", "fpp", "ftn",
)

# Glob patterns whose presence makes a tool worth running at all. Each row is
# checked against what that tool's ``argv_for`` branch actually scans; the two
# must select the same thing, or a tool is either gated out of work it would
# have done (osv-scanner's root-only lockfiles against its --recursive) or
# turned loose on work its gate never selected for (jscpd's JS/TS gate against
# an unrestricted invocation). Both were live before the whole-branch review.
ARTEFACTS: Final[dict[str, tuple[str, ...]]] = {
    # ``**/`` on every lockfile: the invocation is --recursive, and pathlib's
    # ``**`` matches the root directory too, so this is a superset of the bare
    # names it replaced. A monorepo with per-package lockfiles and none at the
    # root -- the common shape -- was skipped outright before.
    "osv-scanner": ("**/package-lock.json", "**/yarn.lock", "**/pnpm-lock.yaml",
                    "**/poetry.lock", "**/requirements.txt", "**/Pipfile.lock",
                    "**/go.sum", "**/Cargo.lock", "**/composer.lock", "**/Gemfile.lock"),
    "gitleaks": ("*",),
    "ruff": ("**/*.py",),
    "vulture": ("**/*.py",),
    "lizard": tuple(f"**/*.{extension}" for extension in _LIZARD_EXTENSIONS),
    "jscpd": ("**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"),
    "knip": ("package.json",),
    "madge": ("**/*.js", "**/*.ts", "**/*.tsx", "**/*.jsx"),
    "hadolint": ("Dockerfile", "**/Dockerfile", "**/Dockerfile.*"),
    # Root-only on purpose: GitHub reads workflows from the repository root's
    # .github/workflows and nowhere else, so a deeper match would not be a
    # workflow. The argv builder globs these same patterns for its operands.
    "actionlint": (".github/workflows/*.yml", ".github/workflows/*.yaml"),
}

RUFF_SELECT: Final[str] = "E722,BLE001,S110,S112,C901,PLR0911,PLR0912,PLR0913,PLR0915,F401,UP035"
MADGE_EXTENSIONS: Final[str] = "js,jsx,ts,tsx"
JSCPD_MIN_TOKENS: Final[str] = "50"
# jscpd's own names for the four formats its ARTEFACTS row gates on. Without
# this it parses every format it knows -- markdown, JSON, diffs, Python -- and
# on a copy of this repository 3,022 of 3,267 signals came from jscpd with 12
# of them from the language that justified running it at all.
JSCPD_FORMATS: Final[str] = "javascript,typescript,jsx,tsx"


def _ignore_globs() -> tuple[str, ...]:
    """The trees a scan must not descend into, as ignore globs.

    Translated from ``inventory.py``'s own classification rather than a second
    list invented here, so the probe and the inventory cannot disagree about
    what is vendored: ``DEFAULT_IGNORE`` is the set of directory names the
    inventory walk never enters (``node_modules``, ``.venv``, ``dist``,
    ``.git``, the caches), and ``PATH_CLASS_GLOBS`` holds the ``vendored`` and
    ``generated`` path classes that ``patterns.py`` already refuses to scan.
    The inventory's globs are anchored (``vendor/*``, ``*/vendor/*``); the
    equivalent here is unanchored, because a tool is told to ignore a name
    wherever it appears.
    """
    globs = {f"**/{name}/**" for name in DEFAULT_IGNORE}
    for path_class in ("vendored", "generated"):
        for pattern in PATH_CLASS_GLOBS[path_class]:
            stripped = pattern.removeprefix("*/")
            if stripped.endswith("/*"):
                globs.add(f"**/{stripped[:-2]}/**")
            else:
                globs.add(f"**/{stripped}")
    return tuple(sorted(globs))


def artefact_present(spec: ToolSpec, root: Path) -> bool:
    """True when the repository holds something ``spec``'s tool could read."""
    for pattern in ARTEFACTS[spec.name]:
        if pattern == "*":
            return True
        if next(root.glob(pattern), None) is not None:
            return True
    return False


# Tools whose argv is a list of files found by globbing, rather than the
# target directory itself. ``artefact_present`` only asks "does *something*
# match one of this tool's patterns" -- it says nothing about whether the
# specific glob an argv builder happens to use would find that same thing.
# Both members build their operand list from exactly the same ARTEFACTS
# patterns their predicate reads, via ``_glob_operands`` below, so the two can
# no longer disagree. hadolint given no file operand reads a Dockerfile from
# inherited stdin and hangs until the timeout; actionlint given none walks up
# from its cwd looking for a .git directory and errors out when there is none,
# which is every corpus fixture. ``probe`` additionally refuses to run any
# tool in this set when the expansion comes back empty, as a second,
# structural line of defence against the same class of bug reappearing (a
# future pattern added to one side and not the other, or a new tool built the
# same way).
GLOB_OPERAND_TOOLS: Final[frozenset[str]] = frozenset({"hadolint", "actionlint"})


def _glob_operands(spec: ToolSpec, root: Path) -> list[str]:
    """Every path under ``root`` matching one of ``spec``'s ARTEFACTS patterns."""
    found: set[str] = set()
    for pattern in ARTEFACTS[spec.name]:
        if pattern == "*":
            continue
        found.update(str(path) for path in root.glob(pattern))
    return sorted(found)


def argv_for(spec: ToolSpec, executable: str, root: Path, *, network: bool) -> list[str]:
    """The exact command line for one tool.

    **Every builder names its target with an absolute path.** ``run_tool``
    also sets ``cwd=root``, so a *relative* operand would be re-resolved
    against that new cwd and become ``<root>/<root>`` -- a directory that does
    not exist, which ruff and lizard report as an ordinary empty result and
    which therefore reads as a clean repository. ``probe`` resolves ``root``
    before anything here sees it, so the operand and the cwd can only ever
    name the same directory. The alternative convention -- pass ``.`` and let
    the cwd decide -- would work equally well but is more fragile: a tool that
    ignores cwd, or a builder that forgets the operand, fails silently under
    it, whereas a wrong absolute path fails loudly. The two tools that once
    passed no operand at all (knip, actionlint) now name their target too, so
    no builder depends on cwd for *what* it scans.

    madge is given ``--extensions`` explicitly: without it madge returns an
    empty graph and exits 0 on a TypeScript tree, which reads as "no cycles"
    and would never fail a test (spec 4.5). ruff runs ``--isolated`` so the
    scanned repository's own configuration cannot silence the rules we ask
    for, and ``--no-cache`` so a probe run never writes a ``.ruff_cache``
    directory into the repository being scanned.
    """
    target = str(root)
    if spec.name == "ruff":
        return [executable, "check", "--isolated", "--no-cache", "--output-format", "json",
                "--select", RUFF_SELECT, target]
    if spec.name == "vulture":
        return [executable, target]
    if spec.name == "lizard":
        return [executable, "--csv", target]
    if spec.name == "madge":
        return [executable, "--extensions", MADGE_EXTENSIONS, "--circular", "--json", target]
    if spec.name == "jscpd":
        # --format restricts jscpd to the same four languages its ARTEFACTS row
        # gates on, and --ignore keeps it out of the vendored and generated
        # trees inventory.py already classifies. Ends with a bare --output on
        # purpose: run_tool appends the report directory it created, which is
        # the report_file channel's contract.
        return [executable, "--reporters", "json", "--min-tokens", JSCPD_MIN_TOKENS,
                "--format", JSCPD_FORMATS, "--ignore", ",".join(_ignore_globs()),
                target, "--output"]
    if spec.name == "knip":
        return [executable, "--reporter", "json", "--directory", target]
    if spec.name == "gitleaks":
        return [executable, "detect", "--no-git", "--report-format", "json",
                "--report-path", "-", "--source", target]
    if spec.name == "hadolint":
        return [executable, "--format", "json", *_glob_operands(spec, root)]
    if spec.name == "actionlint":
        # Given no file operand actionlint walks up from its cwd looking for a
        # .git directory to establish the project root and errors out when
        # there is none -- which is every corpus fixture and every scratch
        # copy. Passing the workflow files its own ARTEFACTS row globs makes
        # the predicate and the invocation select the same files and removes
        # the dependency on cwd semantics, the shape hadolint already uses.
        return [executable, "-format", "{{json .}}", "-no-color",
                *_glob_operands(spec, root)]
    if spec.name == "osv-scanner":
        argv = [executable, "--format", "json", "--recursive", target]
        if not network:
            argv.insert(1, "--offline")
        return argv
    raise ValueError(f"no argv builder for {spec.name!r}")


def _redact_value(value: Any) -> Any:
    """``value`` with every string it holds redacted, recursing into dicts and lists.

    Tool-supplied text is not confined to ``message``: ``extra`` carries rule
    ids, symbol names and cycle-member paths straight from the tool, and a
    string nested inside a list or dict within ``extra`` (a cycle's member
    list, a set of duplicate locations) is just as capable of holding a
    credential-shaped token as ``message`` is. Dictionary *keys* are redacted
    as well as values: nothing today keys ``extra`` by tool-supplied text, but
    a normaliser that keyed a map by symbol name or rule id would otherwise
    reintroduce the leak one level down, silently. Non-string, non-container
    values (``None``, ``int``, ``bool``) pass through untouched.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {
            (redact(key) if isinstance(key, str) else key): _redact_value(inner)
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(inner) for inner in value]
    return value


def redact_document(document: dict[str, Any]) -> dict[str, Any]:
    """The whole ``tool-signals.json`` document with every string redacted.

    Applied to the document rather than to the ``signals`` array alone, so a
    field added later cannot miss redaction by construction. The array was not
    the only place tool-supplied text reaches the file: ``tools[<name>]
    ["reason"]`` carries up to ``STDERR_CHARS`` characters of a failing tool's
    raw stderr, and a tool that fails while reading a file routinely prints
    the offending source line -- vulture 2.16 does exactly that on a syntax
    error, so a credential on that line reached the document verbatim. Every
    other value in the document (``schema_version``, ``status``, ``version``,
    ``duration_s``) is a number or drawn from a closed set, so redacting the
    whole thing costs nothing and removes the class of defect rather than one
    instance of it.
    """
    return cast(dict[str, Any], _redact_value(document))


def probe(root: Path, config: dict[str, Any], *, skip_all: bool = False) -> dict[str, Any]:
    """Run every allowed, present tool and return the ``tool-signals.json`` document.

    ``root`` is resolved here as well as in ``_main``, because every argv
    builder passes it as an absolute operand while ``run_tool`` passes it as
    the child's cwd: a relative root would be re-resolved against that cwd and
    silently become ``<root>/<root>``. Resolving once, at the top of the only
    function both paths flow through, is what makes those two uses agree for
    every caller rather than only for the CLI.
    """
    root = root.resolve()
    tools_config = config.get("tools") or {}
    deny = set(tools_config.get("deny") or [])
    network = bool(tools_config.get("network", True))
    default_timeout = int(tools_config.get("timeout_s", 120))
    tools: dict[str, Any] = {}
    signals: list[Any] = []

    for name, spec in TOOLS.items():
        if skip_all:
            tools[name] = _entry("skipped", reason="--skip-all")
            continue
        if name in deny:
            tools[name] = _entry("skipped", reason="deny list")
            continue
        if not artefact_present(spec, root):
            tools[name] = _entry("skipped", reason="no matching artefact")
            continue
        if name in GLOB_OPERAND_TOOLS and not _glob_operands(spec, root):
            # Belt-and-braces: artefact_present and _glob_operands already
            # read the same ARTEFACTS patterns, so this is unreachable today,
            # but it makes an empty-operand invocation structurally
            # impossible even if that alignment is ever broken again.
            tools[name] = _entry("skipped", reason="no matching artefact")
            continue
        executable = find_tool(name, root)
        if executable is None:
            tools[name] = _entry("absent")
            continue
        if name == "osv-scanner" and not network:
            db_dir = os.environ.get("OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY")
            if not (db_dir and Path(db_dir).is_dir()):
                tools[name] = _entry("skipped", reason="no local database")
                continue
        timeout = spec.timeout_s or default_timeout
        result = run_tool(spec, argv_for(spec, executable, root, network=network),
                          root, timeout)
        tools[name] = _entry(result.status, reason=result.reason, duration_s=result.duration_s)
        if result.status == "ran":
            tool_signals = NORMALISERS[name](result.payload, root)
            tool_signals.sort(key=_signal_sort_key)
            signals.extend(tool_signals)

    return redact_document({
        "schema_version": SCHEMA_VERSION,
        "tools": tools,
        "signals": signals,
    })


def _signal_sort_key(sig: Any) -> tuple[str, int, str, str, str]:
    """A total order for one tool's own signals.

    Some tools do not guarantee their own JSON emits findings in a stable
    order across runs (knip's file-scan ordering was observed to differ
    between an isolated run and one under a full test-suite's system load).
    Sorting within each tool's contribution keeps ``tool-signals.json``
    byte-identical across regenerations regardless of that. The across-tool
    order is already deterministic: it follows ``TOOLS`` registry order.

    The first four elements are the human-meaningful ordering (file, line,
    kind, message); the last is a canonical JSON dump of the whole signal,
    included so the key is total rather than merely usually-distinguishing.
    Two signals that agree on file, line_start, kind and message are the
    normal shape of one source block reported as duplicated with several
    other regions -- jscpd's own ``other_line_start``/``other_line_end`` in
    ``extra`` is exactly what tells them apart, and without it in the key a
    stable sort falls back to silently preserving the tool's own emission
    order for that tied pair, which is the non-determinism this function
    exists to remove.
    """
    file_ = sig.get("file") or ""
    line_start = sig.get("line_start")
    row = line_start if isinstance(line_start, int) else -1
    canonical = json.dumps(sig, sort_keys=True, default=str)
    return (file_, row, sig.get("kind") or "", sig.get("message") or "", canonical)


def _entry(status: str, *, reason: str = "", duration_s: float = 0.0) -> dict[str, Any]:
    return {"status": status, "version": "", "duration_s": round(duration_s, 3),
            "reason": reason}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run installed external tools")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument("--workdir", default=".tech-debt",
                        help="directory to write tool-signals.json into (default .tech-debt)")
    parser.add_argument("--skip-all", action="store_true",
                        help="run nothing; write every tool skipped")
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    try:
        document = probe(root, load_config(root), skip_all=args.skip_all)
    except (OSError, ValueError, ConfigError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    out_path = Path(args.workdir) / "tool-signals.json"
    write_json(out_path, document)
    ran = sum(1 for entry in document["tools"].values() if entry["status"] == "ran")
    print(f"wrote {out_path} ({ran} tools ran, {len(document['signals'])} signals)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
