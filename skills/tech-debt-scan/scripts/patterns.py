"""Regex lead miner and SATD table for the scout families (spec 4.3).

One rule table keyed by family. Each ``Rule`` row has ``family``, ``rule``,
a compiled regex, a path-class scope and a blame flag; ``kind`` names the
scanner that applies it (a plain line match, or one of the multi-line
scanners for catch bodies, commented-out runs, call arguments, per-file
counts and assertion-free tests). Every regex is a union of idioms across
languages; the only language-aware input is ``LANG_COMMENT`` from the
inventory's extension map, which says which comment markers to strip. No
function here branches on a language name (spec 0(d)); a grep test enforces
it.

Leads feed scouts and corroborate the merge; counts go to report statistics,
never to a finding. Blame runs only for the SATD markers, on at most
``BLAME_FILE_CAP`` files; ``--no-blame`` skips it and leaves ``age_days`` and
``commits_since`` null. Credential values are redacted to their first four
characters before anything is written. ``inline_disables`` per source file
is written back into ``inventory.json`` in place, the only cross-script
in-place edit in the pipeline (spec 9).

``python scripts/patterns.py <repo> --workdir .tech-debt [--no-blame]``
reads ``<workdir>/inventory.json`` and writes ``<workdir>/patterns.json``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from config import ConfigError, load_config
from git_history import run_git
from inventory import DEFAULT_COMMENT, LANG_COMMENT, write_json
from reference_graph import import_lines

SCHEMA_VERSION: Final[int] = 2
BLAME_FILE_CAP: Final[int] = 200
LEAD_PROMPT_CAP: Final[int] = 40
MAX_SCAN_BYTES: Final[int] = 2_000_000

Markers = tuple[tuple[str, ...], tuple[tuple[str, str], ...]]

FAMILIES: Final[tuple[str, ...]] = (
    "half-finished", "error-masking", "dead-code", "security", "test-quality", "pipeline-infra",
)

SOURCE: Final[frozenset[str]] = frozenset({"source"})
SOURCE_TESTS: Final[frozenset[str]] = frozenset({"source", "tests"})
SOURCE_CI_CONFIG: Final[frozenset[str]] = frozenset({"source", "ci", "config"})
TESTS: Final[frozenset[str]] = frozenset({"tests"})
ARTEFACT_SCAN_CLASSES: Final[tuple[str, ...]] = (
    "ci", "config", "build", "manifest", "container", "iac", "sql", "runtime_version",
    "governance",
)
ALL_TEXT: Final[frozenset[str]] = frozenset({"source", "tests", "docs", *ARTEFACT_SCAN_CLASSES})

# Self-admitted debt markers: the 62-entry union used for the satd group,
# matched case-insensitively inside comment text only.
SATD_MARKERS: Final[tuple[str, ...]] = (
    "todo", "fixme", "xxx", "hack", "hacky", "kludge", "kluge", "workaround", "work around",
    "temporary", "temp fix", "quick fix", "quick and dirty", "band-aid", "bandaid", "stopgap",
    "stop-gap", "not implemented", "unimplemented", "needs work", "needs refactor",
    "refactor this", "refactor me", "clean up later", "cleanup later", "remove this", "remove me",
    "get rid of", "rewrite this", "should be rewritten", "should be refactored", "should be fixed",
    "must be fixed", "to be fixed", "fix later", "fix me later", "revisit", "for now", "someday",
    "eventually", "ugly", "nasty", "broken", "known bug", "known issue", "known problem",
    "this is wrong", "this is bad", "this isn't right", "doesn't work", "does not work",
    "won't work", "not sure why", "no idea why", "not tested", "untested", "unsafe", "dangerous",
    "deprecated", "obsolete", "legacy", "smell",
)
SATD_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:" + "|".join(re.escape(m).replace(r"\ ", r"\s+") for m in SATD_MARKERS) + r")\b",
    re.IGNORECASE,
)
TICKET_RE: Final[re.Pattern[str]] = re.compile(
    r"#\d+|\b[A-Z][A-Z0-9]+-\d+\b|https?://\S+/issues/\d+"
)
AGE_BANDS: Final[tuple[str, ...]] = ("<30d", "30-180d", "180-365d", ">365d", "unknown")


@dataclass(frozen=True)
class Rule:
    family: str
    rule: str
    regex: re.Pattern[str]
    scope: frozenset[str]
    blame: bool = False
    kind: str = "line"
    exclude: re.Pattern[str] | None = None


@dataclass(slots=True)
class Lead:
    rule: str
    file: str
    line: int
    quote: str
    path_class: str
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "file": self.file,
            "line": self.line,
            "quote": self.quote,
            "path_class": self.path_class,
            "extra": self.extra,
        }


@dataclass(slots=True)
class ScanFile:
    path: str
    path_class: str
    language: str
    text: str
    lines: list[str]
    markers: Markers


@dataclass(slots=True)
class ScanContext:
    fan_in: dict[str, int | None]
    logger_present: bool


Handler = Callable[[ScanFile, Rule, ScanContext], list[Lead]]


# --- comment handling -----------------------------------------------------------


def comment_text(line: str, markers: Markers) -> str | None:
    """The comment part of ``line`` (text after the first comment marker), or None."""
    stripped = line.strip()
    positions: list[tuple[int, int]] = []  # (index of marker, marker length)
    for marker in markers[0]:
        idx = line.find(marker)
        if idx != -1:
            positions.append((idx, len(marker)))
    for open_marker, close_marker in markers[1]:
        idx = line.find(open_marker)
        if idx != -1:
            positions.append((idx, len(open_marker)))
        elif open_marker == "/*" and stripped.startswith("*"):
            positions.append((line.find("*"), 1))  # a line inside a block comment
        elif stripped.endswith(close_marker):
            positions.append((0, 0))  # the closing line of a block comment
    if not positions:
        return None
    idx, length = min(positions)
    text = line[idx + length :]
    for _open_marker, close_marker in markers[1]:
        text = text.replace(close_marker, "")
    return text.strip()


def is_comment_line(line: str, markers: Markers) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(stripped.startswith(m) for m in markers[0]):
        return True
    for open_marker, close_marker in markers[1]:
        if stripped.startswith(open_marker) or stripped.endswith(close_marker):
            return True
        if open_marker == "/*" and stripped.startswith("*"):
            return True
    return False


def strip_markers(line: str, markers: Markers) -> str:
    stripped = line.strip()
    for marker in markers[0]:
        if stripped.startswith(marker):
            return stripped[len(marker) :].strip()
    for open_marker, close_marker in markers[1]:
        if stripped.startswith(open_marker):
            stripped = stripped[len(open_marker) :]
        if stripped.endswith(close_marker):
            stripped = stripped[: -len(close_marker)]
        if open_marker == "/*" and stripped.lstrip().startswith("*"):
            stripped = stripped.lstrip().lstrip("*")
    return stripped.strip()


# --- scanners -------------------------------------------------------------------


def _scan_lines(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        if rule.regex.search(line) and not (rule.exclude and rule.exclude.search(line)):
            leads.append(Lead(rule.rule, sf.path, lineno, line.strip(), sf.path_class))
    return leads


def _scan_satd(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        comment = comment_text(line, sf.markers)
        if comment is None:
            continue
        match = rule.regex.search(comment)
        if match is None:
            continue
        marker = re.sub(r"\s+", " ", match.group(0).lower())
        leads.append(
            Lead(
                rule.rule, sf.path, lineno, line.strip(), sf.path_class,
                {"marker": marker, "ticket_ref": TICKET_RE.search(comment) is not None},
            )
        )
    return leads


# --- blame ----------------------------------------------------------------------


def _blame_lines(root: Path, rel: str) -> dict[int, tuple[int, str]] | None:
    """Map final line number -> (author epoch seconds, commit sha) via blame -w."""
    stdout = run_git(
        root, ["-c", "core.quotePath=false", "blame", "-w", "--line-porcelain", "--", rel]
    )
    if stdout is None:
        return None
    out: dict[int, tuple[int, str]] = {}
    sha = ""
    line_no = 0
    for raw in stdout.splitlines():
        if re.match(r"^[0-9a-f]{40} \d+ \d+", raw):
            parts = raw.split()
            sha, line_no = parts[0], int(parts[2])
        elif raw.startswith("author-time "):
            out[line_no] = (int(raw[12:].strip()), sha)
    return out


def _commits_since(
    root: Path, sha: str, rel: str, cache: dict[tuple[str, str], int | None]
) -> int | None:
    key = (sha, rel)
    if key not in cache:
        stdout = run_git(root, ["rev-list", "--count", f"{sha}..HEAD", "--", rel])
        cache[key] = int(stdout.strip()) if stdout and stdout.strip().isdigit() else None
    return cache[key]


def _attach_blame(root: Path, satd: list[dict[str, Any]]) -> None:
    files: list[str] = []
    for entry in satd:
        if entry["file"] not in files:
            files.append(str(entry["file"]))
    now = datetime.now(UTC)
    cache: dict[tuple[str, str], int | None] = {}
    for rel in files[:BLAME_FILE_CAP]:
        blamed = _blame_lines(root, rel)
        if blamed is None:
            continue
        for entry in satd:
            if entry["file"] != rel:
                continue
            hit = blamed.get(int(entry["line"]))
            if hit is None:
                continue
            epoch, sha = hit
            entry["age_days"] = (now - datetime.fromtimestamp(epoch, UTC)).days
            entry["commits_since"] = _commits_since(root, sha, rel, cache)


def _age_band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age < 30:
        return "<30d"
    if age < 180:
        return "30-180d"
    if age < 365:
        return "180-365d"
    return ">365d"


# --- rule table -----------------------------------------------------------------

RULES: Final[tuple[Rule, ...]] = (
    Rule("half-finished", "satd-marker", SATD_RE, ALL_TEXT, blame=True, kind="satd"),
)

_HANDLERS: Final[dict[str, Handler]] = {
    "line": _scan_lines,
    "satd": _scan_satd,
}


# --- driver ---------------------------------------------------------------------


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:1024]:
        return None
    return data.decode("utf-8", errors="replace")


def _scan_files(root: Path, inventory: dict[str, Any]) -> list[ScanFile]:
    files: list[ScanFile] = []
    for entry in inventory["files"]:
        path_class = str(entry["path_class"])
        if path_class in ("generated", "vendored"):
            continue
        text = _read_text(root / str(entry["path"]))
        if text is None:
            continue
        language = str(entry.get("language") or "")
        markers = LANG_COMMENT.get(language, DEFAULT_COMMENT)
        files.append(
            ScanFile(str(entry["path"]), path_class, language, text, text.splitlines(), markers)
        )
    artefacts = inventory.get("artefacts") or {}
    for cls in ARTEFACT_SCAN_CLASSES:
        for artefact in artefacts.get(cls, []):
            text = _read_text(root / str(artefact["path"]))
            if text is None:
                continue
            files.append(
                ScanFile(str(artefact["path"]), cls, "", text, text.splitlines(), DEFAULT_COMMENT)
            )
    return files


LOGGER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:log|logging|structlog|loguru|winston|pino|bunyan|log4js|loglevel|serilog|nlog|"
    r"log4net|logrus|zap|zerolog|slog|log4j|slf4j|logback|tracing)\b"
)


def _logger_present(files: Sequence[ScanFile]) -> bool:
    for sf in files:
        if sf.path_class == "source" and any(
            LOGGER_RE.search(line) for line in import_lines(sf.text)
        ):
            return True
    return False


def _satd_entry(lead: Lead) -> dict[str, Any]:
    return {
        "marker": lead.extra["marker"],
        "file": lead.file,
        "line": lead.line,
        "quote": lead.quote,
        "ticket_ref": lead.extra["ticket_ref"],
        "age_days": None,
        "commits_since": None,
        "path_class": lead.path_class,
    }


def _stats(satd: list[dict[str, Any]], leads: dict[str, list[Lead]]) -> dict[str, Any]:
    bands: Counter[str] = Counter(_age_band(s["age_days"]) for s in satd)
    without = sum(1 for s in satd if not s["ticket_ref"])
    return {
        "markers_by_age_band": {band: bands[band] for band in AGE_BANDS},
        "markers_without_ticket_share": round(without / len(satd), 3) if satd else 0.0,
        "leads_per_family": {family: len(items) for family, items in leads.items()},
    }


def run_patterns(
    root: Path, inventory: dict[str, Any], config: dict[str, Any], *, blame: bool = True
) -> tuple[dict[str, Any], dict[str, int]]:
    """Return (patterns document, inline-disable counts per source path)."""
    root = root.resolve()
    files = _scan_files(root, inventory)
    ctx = ScanContext(
        fan_in={str(e["path"]): e.get("fan_in_approx") for e in inventory["files"]},
        logger_present=_logger_present(files),
    )
    leads: dict[str, list[Lead]] = {family: [] for family in FAMILIES}
    satd: list[dict[str, Any]] = []
    inline: dict[str, int] = {}
    for sf in files:
        for rule in RULES:
            if sf.path_class not in rule.scope:
                continue
            found = _HANDLERS[rule.kind](sf, rule, ctx)
            if rule.kind == "satd":
                satd.extend(_satd_entry(lead) for lead in found)
            else:
                leads[rule.family].extend(found)
        if sf.path_class == "source":
            inline[sf.path] = 0
    if blame:
        _attach_blame(root, satd)
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "leads": {family: [lead.as_dict() for lead in items] for family, items in leads.items()},
        "satd": satd,
        "stats": _stats(satd, leads),
    }
    return document, inline


def capped_leads(
    leads: Sequence[dict[str, Any]], band: Sequence[str], limit: int = LEAD_PROMPT_CAP
) -> list[dict[str, Any]]:
    """The first ``limit`` leads with hotspot-band files first (spec 4.3 prompt cap)."""
    in_band = set(band)
    first = [lead for lead in leads if lead["file"] in in_band]
    rest = [lead for lead in leads if lead["file"] not in in_band]
    return [*first, *rest][:limit]


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mine regex leads and SATD markers")
    parser.add_argument("path", help="repo root to scan")
    parser.add_argument(
        "--workdir",
        default=".tech-debt",
        help="directory holding inventory.json (default .tech-debt)",
    )
    parser.add_argument("--no-blame", action="store_true", help="skip git blame for SATD ages")
    args = parser.parse_args(argv)
    root = Path(args.path)
    workdir = Path(args.workdir)
    inventory_path = workdir / "inventory.json"
    if not inventory_path.is_file():
        print(f"error: {inventory_path} not found; run inventory.py first", file=sys.stderr)
        return 2
    try:
        inventory = json.loads(inventory_path.read_bytes())
        cfg = load_config(root)
        document, inline = run_patterns(root, inventory, cfg, blame=not args.no_blame)
    except (OSError, ValueError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(str(entry["path"]), 0)
    patterns_path = workdir / "patterns.json"
    write_json(patterns_path, document)
    write_json(inventory_path, inventory)
    counts = ", ".join(f"{f} {n}" for f, n in document["stats"]["leads_per_family"].items())
    print(f"wrote {patterns_path} ({len(document['satd'])} SATD markers; leads: {counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
