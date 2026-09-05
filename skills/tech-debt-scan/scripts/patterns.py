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

Artefacts in ``ARTEFACT_SCAN_CLASSES`` are scanned alongside code files. A
rule's scope is matched against ``ScanFile.scope`` -- the artefact class
(``ci``, ``container``, ...) for an artefact and the path class for a code
file -- while every emitted lead and SATD entry carries ``ScanFile.path_class``,
the artefact's real path class from the inventory, so a workflow under a
fixture tree reports ``tests`` rather than ``ci`` and phase 2's merge can apply
the path-class disables to leads. Artefacts classed ``generated`` or
``vendored``, or whose inventory entry has ``skipped_large``, are not scanned,
the same three skips the code-file loop applies; scanners that skip
``path_class == "tests"`` (the credential scanner) therefore skip tests-tree
artefacts too, and ``_logger_present`` keys on ``ScanFile.scope == "source"``,
not ``path_class``, so a root-level artefact (whose real path class is also
``source``) never counts as a first-party logger import.

Leads feed scouts and corroborate the merge; counts go to report statistics,
never to a finding. Blame runs only for the SATD markers, on at most
``BLAME_FILE_CAP`` files; ``--no-blame`` skips it and leaves ``age_days`` and
``commits_since`` null (``commits_since`` comes from one ``git log
--format=%H -- <path>`` call per blamed file, the position of the blamed sha
in that list, never a per-marker ``rev-list``). Every quote is passed
through ``redaction.redact`` before it is written, whatever rule or family
it came from, so a credential-shaped value on a SATD-marker line or any
other non-security lead never reaches ``patterns.json`` unredacted, cut to
its first four characters; ``rules.py`` imports the same shared module so a
credential in a Dockerfile or workflow quote is redacted too.
``inline_disables`` per source file is written back into ``inventory.json``
in place, the only cross-script in-place edit in the pipeline (spec 9).

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
from inventory import (
    DEFAULT_COMMENT,
    LANG_COMMENT,
    MAX_SCAN_BYTES,
    NUL_SNIFF_BYTES,
    write_json,
)
from redaction import CREDENTIAL_RE, redact
from reference_graph import import_lines

SCHEMA_VERSION: Final[int] = 2
BLAME_FILE_CAP: Final[int] = 200
LEAD_PROMPT_CAP: Final[int] = 40

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
    path_class: str  # the real path class from the inventory; what leads report
    scope: str  # what ``Rule.scope`` is matched against: the artefact class, else path_class
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


def _file_commit_shas(root: Path, rel: str) -> list[str] | None:
    """Every commit sha touching ``rel``, newest first, via one ``git log`` call."""
    stdout = run_git(root, ["log", "--format=%H", "--", rel])
    if stdout is None:
        return None
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _attach_blame(root: Path, satd: list[dict[str, Any]]) -> None:
    files: list[str] = []
    for entry in satd:
        if entry["file"] not in files:
            files.append(str(entry["file"]))
    now = datetime.now(UTC)
    for rel in files[:BLAME_FILE_CAP]:
        blamed = _blame_lines(root, rel)
        if blamed is None:
            continue
        shas = _file_commit_shas(root, rel)
        for entry in satd:
            if entry["file"] != rel:
                continue
            hit = blamed.get(int(entry["line"]))
            if hit is None:
                continue
            epoch, sha = hit
            entry["age_days"] = (now - datetime.fromtimestamp(epoch, UTC)).days
            entry["commits_since"] = shas.index(sha) if shas and sha in shas else None


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


# --- error-masking --------------------------------------------------------------

# One union of catch idioms with the caught variable captured from whichever
# idiom matched (spec 4.3). Go's `if err != nil {` is the catch-less form.
CATCH_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*except\b(?P<py>[^:]*):"
    r"|\bcatch\s*\((?P<brace>[^)]*)\)"
    r"|\bcatch\s*\{"
    r"|\bcatch\s+(?P<bare>[A-Za-z_]\w*)\s*(?:=>|\{|$)"
    r"|^\s*rescue\b(?P<rb>.*)$"
    r"|\bon\s+\w+\s+catch\s*\((?P<dart>[^)]*)\)"
    r"|\bif\b[^{]*?\b(?P<errvar>\w*[eE]rr\w*)\s*!=\s*nil\s*\{"
)
CARRIER_RE: Final[re.Pattern[str]] = re.compile(
    r"exc_info|\.exception\(|\bstack\w*|stackTrace|\berr\b|\bex\b|\be\)"
)
LOG_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:log|logger|logging|console|Log|fmt\.Print\w*|print|puts|warn|warning|error|info|"
    r"debug|trace|Console\.WriteLine|System\.out)\b"
)
SWALLOW_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:pass|return(?:\s+(?:None|null|nil))?;?|\.\.\.|;)$"
)
ANNOTATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnoqa\b|\bnolint\b|eslint-disable|\bpragma\b"
)
PY_CATCH_ALL_RE: Final[re.Pattern[str]] = re.compile(r"^\s*$|\bBaseException\b")
C_CATCH_ALL_RE: Final[re.Pattern[str]] = re.compile(r"\bThrowable\b|^\s*\.\.\.\s*$")
IDENT_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z_]\w*")
ASSERT_OFF_RE: Final[re.Pattern[str]] = re.compile(
    r"\bNDEBUG\b|\bpython[\d.]*\s+-OO?\b|(?<![\w-])-da\b|enableassertions\s*=\s*false"
    r"|\bassert(?:ions)?[\"']?\s*:\s*false|^\s*(?:#|//)\s*assert\b"
)


def _catch_variable(match: re.Match[str]) -> tuple[str | None, bool, bool]:
    """(caught variable, catches everything, body delimited by indentation)."""
    if match.group("py") is not None:
        spec = match.group("py")
        as_match = re.search(r"\bas\s+(\w+)", spec)
        variable = as_match.group(1) if as_match else None
        return variable, PY_CATCH_ALL_RE.search(spec) is not None, True
    if match.group("rb") is not None:
        arrow = re.search(r"=>\s*(\w+)", match.group("rb"))
        return (arrow.group(1) if arrow else None), False, True
    if match.group("brace") is not None:
        spec = match.group("brace")
        idents = IDENT_RE.findall(spec)
        return (idents[-1] if idents else None), C_CATCH_ALL_RE.search(spec) is not None, False
    if match.group("dart") is not None:
        idents = IDENT_RE.findall(match.group("dart"))
        return (idents[-1] if idents else None), False, False
    if match.group("bare") is not None:
        return match.group("bare"), False, False
    if match.group("errvar") is not None:
        return match.group("errvar"), False, False
    return None, True, False  # the `catch {` form


def _indented_body(lines: list[str], index: int) -> tuple[list[str], int]:
    """Stripped lines indented deeper than ``lines[index]``, and the last line's index."""
    start = lines[index]
    indent = len(start) - len(start.lstrip())
    body: list[str] = []
    end = index
    for j in range(index + 1, len(lines)):
        raw = lines[j]
        if not raw.strip():
            continue
        if len(raw) - len(raw.lstrip()) <= indent:
            break
        body.append(raw.strip())
        end = j
    return body, end


def _brace_body(lines: list[str], index: int, from_col: int) -> tuple[list[str], int]:
    """Stripped text chunks between the first `{` at or after ``from_col`` and its `}`."""
    depth = 0
    started = False
    chunks: list[str] = []
    current = ""
    for j in range(index, len(lines)):
        raw = lines[j]
        start = from_col if j == index else 0
        for char in raw[start:]:
            if char == "{":
                depth += 1
                if depth == 1:
                    started = True
                    continue
            elif char == "}":
                depth -= 1
                if started and depth == 0:
                    chunks.append(current)
                    return [c.strip() for c in chunks if c.strip()], j
            if started:
                current += char
        if started:
            chunks.append(current)
            current = ""
    return [c.strip() for c in chunks if c.strip()], len(lines) - 1


def _classify_body(body: list[str], variable: str | None, markers: Markers) -> str | None:
    """empty | pass | return | log-only, or None when the catch handles the error."""
    code = [b for b in body if not is_comment_line(b, markers)]
    if not code:
        return "empty"
    if all(SWALLOW_RE.match(b) for b in code):
        return "return" if any(b.startswith("return") for b in code) else "pass"
    if all(LOG_CALL_RE.search(b) for b in code):
        text = " ".join(code)
        if variable and re.search(rf"\b{re.escape(variable)}\b", text):
            return None
        if CARRIER_RE.search(text):
            return None
        return "log-only"
    return None


def _scan_catches(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for index, line in enumerate(sf.lines):
        match = rule.regex.search(line)
        if match is None:
            continue
        variable, catch_all, indented = _catch_variable(match)
        if indented:
            body, end = _indented_body(sf.lines, index)
        else:
            brace = line.find("{", match.start())
            if brace != -1:
                body, end = _brace_body(sf.lines, index, brace)
            elif index + 1 < len(sf.lines):
                body, end = _brace_body(sf.lines, index + 1, 0)
            else:
                body, end = [], index
        kind = _classify_body(body, variable, sf.markers)
        if kind is None:
            continue
        tail = line[match.end() :]
        annotated = bool(ANNOTATION_RE.search(line)) or "#" in tail or "//" in tail
        leads.append(
            Lead(
                rule.rule, sf.path, index + 1, line.strip(), sf.path_class,
                {
                    "variable": variable,
                    "body": kind,
                    "catch_all": catch_all,
                    "annotated": annotated,
                    "line_end": end + 1,
                },
            )
        )
    return leads


# --- dead-code ------------------------------------------------------------------

STATEMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "if", "for", "while", "return", "def", "function", "class", "var", "let", "const", "int",
    "string", "public", "private", "static", "fn", "func", "import", "using", "switch", "case",
    "try", "catch", "elif", "else", "foreach",
)
CODE_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:" + "|".join(STATEMENT_KEYWORDS) + r")\b|^[A-Za-z_][\w.]*\s*(?:=[^=]|\()|[;{]$"
)
LEGACY_TOKENS: Final[frozenset[str]] = frozenset({"old", "bak", "v1", "legacy"})
DEF_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|function|func|class|fn|struct|interface|type|"
    r"public|private|protected|internal|static|const|let|var)\b"
)
DEPRECATION_RE: Final[re.Pattern[str]] = re.compile(
    r"@deprecated\b|\[Obsolete\]|@Deprecated\b|DeprecationWarning|#\[deprecated\]"
    r"|^\s*(?://|#|\*|///)\s*Deprecated:|@available\(\*,\s*deprecated"
)
FLAG_SDK_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:bool)?[vV]ariation\(|\bisEnabled\(|\bIsEnabled\(|\bis_active\(|\bgetFeatureFlag\("
    r"|\bgetBooleanValue\(|\bFEATURE_[A-Z0-9_]+\b"
)


def _balanced(text: str) -> bool:
    return all(text.count(o) == text.count(c) for o, c in (("(", ")"), ("[", "]"), ("{", "}")))


def _scan_commented_code(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    run: list[tuple[int, str]] = []

    def flush() -> None:
        if len(run) < 3:
            return
        bodies = [body for _, body in run]
        code_like = sum(1 for body in bodies if rule.regex.match(body))
        if code_like * 2 > len(bodies) and _balanced("\n".join(bodies)):
            first = run[0][0]
            leads.append(
                Lead(
                    rule.rule, sf.path, first, sf.lines[first - 1].strip(), sf.path_class,
                    {"line_end": run[-1][0], "code_like": code_like, "total": len(bodies)},
                )
            )

    for lineno, line in enumerate(sf.lines, start=1):
        if is_comment_line(line, sf.markers):
            run.append((lineno, strip_markers(line, sf.markers)))
        else:
            flush()
            run.clear()
    flush()
    return leads


def _identifier_words(identifier: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier)
    return [word.lower() for word in re.split(r"[_\s-]+", spaced) if word]


def _scan_legacy_names(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    path_words = [w for part in re.split(r"[/._-]+", sf.path) for w in _identifier_words(part)]
    hit = next((w for w in path_words if w in LEGACY_TOKENS), None)
    if hit and sf.lines:
        leads.append(
            Lead(
                rule.rule, sf.path, 1, sf.lines[0].strip(), sf.path_class,
                {"where": "path", "token": hit},
            )
        )
    for lineno, line in enumerate(sf.lines, start=1):
        if not rule.regex.match(line):
            continue
        for ident in IDENT_RE.findall(line):
            token = next((w for w in _identifier_words(ident) if w in LEGACY_TOKENS), None)
            if token:
                leads.append(
                    Lead(
                        rule.rule, sf.path, lineno, line.strip(), sf.path_class,
                        {"where": "symbol", "token": token},
                    )
                )
                break
    return leads


def _scan_deprecation(sf: ScanFile, rule: Rule, ctx: ScanContext) -> list[Lead]:
    leads = _scan_lines(sf, rule, ctx)
    for lead in leads:
        lead.extra = {"callers_approx": ctx.fan_in.get(sf.path)}
    return leads


# --- half-finished: stubs, skips, no-timeout ---------------------------------------

STUB_RE: Final[re.Pattern[str]] = re.compile(
    r"NotImplementedError|NotImplementedException|\bnot implemented\b|unimplemented!"
    r"|panic\(\"not implemented|throw new Error\(\"not implemented|\bTODO\(\)",
    re.IGNORECASE,
)
SKIP_RE: Final[re.Pattern[str]] = re.compile(
    r"\bxfail\b|expectedFailure|@pytest\.mark\.skip|@Ignore\b|@Disabled\b|\bit\.skip\("
    r"|\btest\.skip\(|\[Ignore\]|\bt\.Skip\("
)
# (label, client-call idiom, the timeout argument that idiom must carry)
TIMEOUT_TABLE: Final[tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...]] = (
    (
        "requests/httpx",
        re.compile(r"\b(?:requests|httpx)\.(?:get|post|put|delete|patch|head|request)\("),
        re.compile(r"\btimeout\s*="),
    ),
    ("fetch", re.compile(r"\bfetch\("), re.compile(r"\bsignal\b|\btimeout\b")),
    ("axios", re.compile(r"\baxios(?:\.\w+)?\("), re.compile(r"\btimeout\b|\bsignal\b")),
    ("HttpClient", re.compile(r"new\s+HttpClient\("), re.compile(r"\bTimeout\b")),
    ("net/http", re.compile(r"\bhttp\.(?:Get|Post|Head|PostForm)\("), re.compile(r"\bTimeout\b")),
    ("http.Client", re.compile(r"&http\.Client\{"), re.compile(r"\bTimeout\b")),
    ("Net::HTTP", re.compile(r"Net::HTTP"), re.compile(r"read_timeout")),
    ("urlopen", re.compile(r"\burlopen\("), re.compile(r"\btimeout\b")),
    ("curl", re.compile(r"(?<![\w.])curl\b"), re.compile(r"--max-time|(?<!\w)-m\s+\d")),
)
NO_TIMEOUT_RE: Final[re.Pattern[str]] = re.compile(
    "|".join(call.pattern for _label, call, _timeout in TIMEOUT_TABLE)
)
# The bracket a call idiom opens (its regex's own literal trailing token), used to join a
# multi-line call's own arguments without following into an unrelated enclosing block; an
# idiom with no trailing bracket (a bare token such as `curl` or `Net::HTTP`) is never joined.
_BRACKET_CLOSE: Final[dict[str, str]] = {"(": ")", "{": "}"}
_CALL_OPENER: Final[dict[str, str | None]] = {
    label: (
        "(" if call.pattern.endswith(r"\(") else "{" if call.pattern.endswith(r"\{") else None
    )
    for label, call, _timeout in TIMEOUT_TABLE
}
MAX_CALL_SPAN_LINES: Final[int] = 20


def _call_span(lines: list[str], index: int, opener: str) -> str:
    """``lines[index]`` joined forward while its own ``opener`` bracket stays unbalanced."""
    closer = _BRACKET_CLOSE[opener]
    depth = lines[index].count(opener) - lines[index].count(closer)
    chunks = [lines[index]]
    end = index
    while depth > 0 and end + 1 < len(lines) and end - index < MAX_CALL_SPAN_LINES:
        end += 1
        chunks.append(lines[end])
        depth += lines[end].count(opener) - lines[end].count(closer)
    return " ".join(chunks)


def _scan_no_timeout(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for index, line in enumerate(sf.lines):
        if is_comment_line(line, sf.markers):
            continue
        for label, call_re, timeout_re in TIMEOUT_TABLE:
            if not call_re.search(line):
                continue
            opener = _CALL_OPENER[label]
            span = _call_span(sf.lines, index, opener) if opener is not None else line
            if not timeout_re.search(span):
                leads.append(
                    Lead(
                        rule.rule, sf.path, index + 1, line.strip(), sf.path_class,
                        {"client": label},
                    )
                )
            break
    return leads


# --- security -------------------------------------------------------------------

PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"fake|dummy|example|placeholder|changeme|your_|xxx", re.IGNORECASE
)
PLACEHOLDER_PREFIXES: Final[tuple[str, ...]] = ("$", "${", "{{", "<", "%")
SQL_CALL_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:execute|query|Query|ExecuteSqlRaw|Raw|createStatement|executeQuery|Exec)\s*\("
    r"(?P<arg>[^\n]*)"
)
SQL_BUILT_RE: Final[re.Pattern[str]] = re.compile(
    r"\+\s*\w|\w\s*\+|\bf[\"']|\$\{|String\.format|\$\"|[\"']\s*%\s*[\w(]|\.format\("
)
DYNAMIC_EVAL_RE: Final[re.Pattern[str]] = re.compile(
    r"\beval\(|\bexec\(|shell\s*=\s*True|shell:\s*true|child_process\.exec\(|Runtime\.exec\("
    r"|Process\.Start\(|exec\.Command\(|\bsystem\("
)
TLS_OFF_RE: Final[re.Pattern[str]] = re.compile(
    r"verify\s*=\s*False|rejectUnauthorized:\s*false|InsecureSkipVerify:\s*true"
    r"|ServerCertificateValidationCallback|VERIFY_NONE|(?<!\w)--insecure\b"
)
WEAK_HASH_RE: Final[re.Pattern[str]] = re.compile(
    r"\bmd5\(|\bsha1\(|MD5\.Create|getInstance\(\"MD5\"\)|createHash\(['\"]md5['\"]\)"
    r"|Digest::MD5|\bmd5\.(?:Sum|New)\(|\bsha1\.(?:Sum|New)\("
)
CORS_RE: Final[re.Pattern[str]] = re.compile(r"Access-Control-Allow-Origin[\"']?\s*[:,]\s*[\"']?\*")
SEC_SUPPRESS_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnosec\b|eslint-disable[^\n]*security|nolint:gosec"
    r"|pragma\s+warning\s+disable[^\n]*\bCA\d+"
)


def _scan_credentials(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    if sf.path_class == "tests":
        return []
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        match = rule.regex.search(line)
        if match is None:
            continue
        value = match.group("value")
        if value.startswith(PLACEHOLDER_PREFIXES) or PLACEHOLDER_RE.search(value):
            continue
        leads.append(
            Lead(
                rule.rule, sf.path, lineno, redact(line.strip()), sf.path_class,
                {"redacted": True},
            )
        )
    return leads


def _scan_string_sql(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    for lineno, line in enumerate(sf.lines, start=1):
        match = rule.regex.search(line)
        if match is not None and SQL_BUILT_RE.search(match.group("arg")):
            leads.append(Lead(rule.rule, sf.path, lineno, line.strip(), sf.path_class))
    return leads


# --- test-quality ---------------------------------------------------------------

SLEEP_RE: Final[re.Pattern[str]] = re.compile(r"\bsleep\(|Thread\.Sleep|setTimeout\(|time\.Sleep\(")
RETRY_RE: Final[re.Pattern[str]] = re.compile(
    r"@retry\b|\bflaky\b|\breruns\b|\bretries\s*[=:(]|jest\.retryTimes|\[Retry\]|@Repeat\b"
)
WALLCLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnow\(\)|Date\.now\(|DateTime\.(?:Now|UtcNow)|time\.Now\(|Time\.now|new Date\(\)"
)
RANDOM_RE: Final[re.Pattern[str]] = re.compile(
    r"\brandom\.\w+\(|Math\.random\(|\brand\.\w+\(|new Random\(\)"
)
SEEDED_RE: Final[re.Pattern[str]] = re.compile(r"seed", re.IGNORECASE)
TRY_IN_TEST_RE: Final[re.Pattern[str]] = re.compile(r"^\s*try\s*[:{]?\s*$|\bcatch\s*\(")
CONDITIONAL_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:if|elif|else if|switch)\b")
NUMERIC_ASSERT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:assert\w*|expect|Assert\.\w+|require\.\w+|should)\b[^\n]*?"
    r"(?<![\w.])(?:\d{2,}|\d+\.\d+)\b"
)
TEST_FN_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:async\s+)?def\s+test_\w+|^\s*func\s+Test\w+\(|^\s*(?:it|test)(?:\.only|\.skip)?\s*\("
    r"|^\s*@Test\b|^\s*\[(?:Fact|Test)\]"
)
TEST_NAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:def|func)\s+(\w+)|(?:it|test)(?:\.\w+)?\s*\(\s*[\"'`]([^\"'`]*)"
)
ASSERT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bassert\w*\b|\bexpect\(|\bAssert\.|\brequire\."
    r"|\bt\.(?:Error|Errorf|Fatal|Fatalf|Fail|FailNow)\b"
    r"|\bshould\b|\.toBe|\.toEqual|pytest\.raises|\.Should\("
)


def _scan_assert_free(sf: ScanFile, rule: Rule, _ctx: ScanContext) -> list[Lead]:
    leads: list[Lead] = []
    lines = sf.lines
    starts = [i for i, line in enumerate(lines) if rule.regex.match(line)]
    for start in starts:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            line = lines[j]
            top_level = bool(line.strip()) and not line[0].isspace() and not line.startswith("}")
            if rule.regex.match(line) or top_level:
                end = j
                break
        if ASSERT_RE.search("\n".join(lines[start:end])):
            continue
        name_match = TEST_NAME_RE.search(lines[start])
        name = lines[start].strip()[:60]
        if name_match is not None:
            name = name_match.group(1) or name_match.group(2) or name
        leads.append(
            Lead(rule.rule, sf.path, start + 1, lines[start].strip(), sf.path_class, {"test": name})
        )
    return leads


# --- pipeline-infra: stdout writes; lint: inline disables --------------------------

STDOUT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bprint\(|console\.log\(|System\.out\.println\(|fmt\.Print(?:ln|f)?\(|^\s*puts\s|^\s*echo\s"
    r"|Console\.WriteLine\(|\bprintf\("
)
CLI_SEGMENTS: Final[frozenset[str]] = frozenset({"cli", "cmd", "bin", "scripts", "tools"})
ENTRY_RE: Final[re.Pattern[str]] = re.compile(
    r"if __name__ == [\"']__main__[\"']|func main\(\)|static void Main|fn main\(\)|process\.argv"
)
INLINE_DISABLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\bnoqa\b|eslint-disable|pragma\s+warning\s+disable|SuppressWarnings|\bnolint\b"
    r"|rubocop:disable|#\[allow\(|\bnosec\b"
)


def _scan_stdout(sf: ScanFile, rule: Rule, ctx: ScanContext) -> list[Lead]:
    if not ctx.logger_present:
        return []
    if CLI_SEGMENTS & set(sf.path.split("/")[:-1]) or ENTRY_RE.search(sf.text):
        return []
    hits = [(i, line) for i, line in enumerate(sf.lines, start=1) if rule.regex.search(line)]
    if not hits:
        return []
    first, line = hits[0]
    return [Lead(rule.rule, sf.path, first, line.strip(), sf.path_class, {"count": len(hits)})]


# --- rule table -----------------------------------------------------------------

RULES: Final[tuple[Rule, ...]] = (
    # satd group (half-finished)
    Rule("half-finished", "satd-marker", SATD_RE, ALL_TEXT, blame=True, kind="satd"),
    Rule("half-finished", "stub", STUB_RE, SOURCE_TESTS),
    Rule("half-finished", "skip-marker", SKIP_RE, SOURCE_TESTS),
    # requirement group (half-finished)
    Rule("half-finished", "no-timeout", NO_TIMEOUT_RE, SOURCE, kind="no-timeout"),
    # error-masking
    Rule("error-masking", "swallowed-catch", CATCH_RE, SOURCE, kind="catch"),
    Rule("error-masking", "assertions-disabled", ASSERT_OFF_RE, SOURCE_CI_CONFIG),
    # dead-code
    Rule("dead-code", "commented-out-code", CODE_LINE_RE, SOURCE, kind="commented-code"),
    Rule("dead-code", "legacy-name", DEF_LINE_RE, SOURCE, kind="legacy-name"),
    Rule("dead-code", "deprecation", DEPRECATION_RE, SOURCE, kind="deprecation"),
    Rule("dead-code", "flag-sdk", FLAG_SDK_RE, SOURCE),
    # security
    Rule("security", "credential", CREDENTIAL_RE, SOURCE_CI_CONFIG, kind="credential"),
    Rule("security", "string-sql", SQL_CALL_RE, SOURCE, kind="string-sql"),
    Rule("security", "dynamic-eval", DYNAMIC_EVAL_RE, SOURCE_CI_CONFIG),
    Rule("security", "tls-disabled", TLS_OFF_RE, SOURCE_CI_CONFIG),
    Rule("security", "weak-hash", WEAK_HASH_RE, SOURCE),
    Rule("security", "permissive-cors", CORS_RE, SOURCE_CI_CONFIG),
    Rule("security", "security-suppression", SEC_SUPPRESS_RE, SOURCE_CI_CONFIG),
    # test-quality
    Rule("test-quality", "sleep", SLEEP_RE, TESTS),
    Rule("test-quality", "retry-marker", RETRY_RE, TESTS),
    Rule("test-quality", "wall-clock", WALLCLOCK_RE, TESTS),
    Rule("test-quality", "unseeded-random", RANDOM_RE, TESTS, exclude=SEEDED_RE),
    Rule("test-quality", "try-in-test", TRY_IN_TEST_RE, TESTS),
    Rule("test-quality", "conditional-in-test", CONDITIONAL_RE, TESTS),
    Rule("test-quality", "numeric-assert", NUMERIC_ASSERT_RE, TESTS),
    Rule("test-quality", "assert-free", TEST_FN_RE, TESTS, kind="assert-free"),
    # observability (pipeline-infra)
    Rule("pipeline-infra", "stdout-write", STDOUT_RE, SOURCE, kind="stdout"),
    # lint (signal only; counted into inventory.files[].inline_disables)
    Rule("lint", "inline-disable", INLINE_DISABLE_RE, SOURCE, kind="inline-disable"),
)

_HANDLERS: Final[dict[str, Handler]] = {
    "line": _scan_lines,
    "satd": _scan_satd,
    "catch": _scan_catches,
    "commented-code": _scan_commented_code,
    "legacy-name": _scan_legacy_names,
    "deprecation": _scan_deprecation,
    "no-timeout": _scan_no_timeout,
    "credential": _scan_credentials,
    "string-sql": _scan_string_sql,
    "assert-free": _scan_assert_free,
    "stdout": _scan_stdout,
    "inline-disable": _scan_lines,
}


# --- driver ---------------------------------------------------------------------


def _read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:NUL_SNIFF_BYTES]:
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
            ScanFile(
                str(entry["path"]), path_class, path_class, language, text,
                text.splitlines(), markers,
            )
        )
    artefacts = inventory.get("artefacts") or {}
    for cls in ARTEFACT_SCAN_CLASSES:
        for artefact in artefacts.get(cls, []):
            path_class = str(artefact["path_class"])
            if path_class in ("generated", "vendored") or artefact.get("skipped_large"):
                continue
            text = _read_text(root / str(artefact["path"]))
            if text is None:
                continue
            files.append(
                ScanFile(
                    str(artefact["path"]), path_class, cls, "", text,
                    text.splitlines(), DEFAULT_COMMENT,
                )
            )
    return files


LOGGER_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:log|logging|structlog|loguru|winston|pino|bunyan|log4js|loglevel|serilog|nlog|"
    r"log4net|logrus|zap|zerolog|slog|log4j|slf4j|logback|tracing)\b"
)


def _logger_present(files: Sequence[ScanFile]) -> bool:
    for sf in files:
        if sf.scope == "source" and any(
            LOGGER_RE.search(line) for line in import_lines(sf.text)
        ):
            return True
    return False


def _satd_entry(lead: Lead) -> dict[str, Any]:
    return {
        "marker": lead.extra["marker"],
        "file": lead.file,
        "line": lead.line,
        "quote": redact(lead.quote),
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
            if sf.scope not in rule.scope:
                continue
            found = _HANDLERS[rule.kind](sf, rule, ctx)
            if rule.kind == "satd":
                satd.extend(_satd_entry(lead) for lead in found)
            elif rule.kind == "inline-disable":
                inline[sf.path] = len(found)
            else:
                for lead in found:
                    lead.quote = redact(lead.quote)
                leads[rule.family].extend(found)
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
