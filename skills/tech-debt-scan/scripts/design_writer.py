"""Render design.md + findings.json and apply in-place ``mark_promoted`` status edits.

``render`` is the report stage of /tech-debt-scan (spec 4.11). It reads the
whole phase 2 chain out of ``--workdir`` (``inventory.json``, ``coupling.json``,
``scan-plan.json``, ``verified.json``, ``ranked.json``, ``candidates.json``,
plus the optional ``notes.json`` and ``diff.json``) and renders the single
``design.md`` the user reviews, plus ``findings.json`` into ``--workdir``
(regardless of where ``--out`` points ``design.md``): the machine-readable
twin of the same finding list, which ``evaluate.py`` prefers over
``verified.json`` because it carries the rank terms and the top-N flag.
``mark_promoted`` is stage 3 of /tech-debt-promote: it flips approved findings
to ``promoted`` in place once their bundles have been emitted.

``notes-prompt`` renders the single remediation-note agent's prompt (spec
4.11's Task 5) to ``<workdir>/prompts/notes.md``: the read-only rule, then per
top-N finding its fingerprint, family, severity, effort, proof and evidence,
then ``NOTES_CONTRACT``. The agent's reply is stored as ``notes.json`` and read
back by ``render`` (via ``notes_by_fingerprint``) into the top-N findings'
``### Remediation`` and ``### Acceptance criteria`` sections; a malformed or
absent ``notes.json`` renders ``NOTE_PLACEHOLDER`` in both instead of failing.
``--top`` narrows the prompt to fewer than ``ranked.json``'s own top N; it can
never widen past it.

Document shape (``SECTION_ORDER``): the frontmatter, the ``# Tech-debt scan``
header, ``# Top N`` with one H2 per top-N finding, then the six negative-space
H1 sections. A finding is an H2 with a fenced ```yaml anchor; every other
section is an H1, which ``design_parser`` treats as the end of a finding's
body, so no negative-space section is ever copied into a PBI.

Format invariants (the round-trip partner is design_parser.parse_design):
  - Output is LF-only. The body is built as ``"\n".join(parts)`` and written via
    ``write_bytes`` so Windows text-mode CRLF translation never corrupts it.
  - The frontmatter is emitted as literal YAML lines, never ``yaml.dump``, so
    key order and byte layout are pinned by this module rather than by PyYAML.
    An empty ``languages`` / ``families_run`` / ``families_skipped`` list is
    written as ``key: []`` on one line: a bare ``key:`` with nothing beneath it
    reads back as ``None``, which is a different document.
  - Before writing anything, ``write_design`` renders both documents in memory
    and self-checks the markdown by re-parsing it: every finding's body must
    still carry the "### Evidence" heading it was written with, and the
    document's H1 headings must be exactly ``SECTION_ORDER`` (after the fixed
    scan header), in order. Only once both hold are ``design.md`` and
    ``findings.json`` written, so format drift surfaces at write time, not
    just in tests, and a rejected render never leaves a stale file on disk.
  - Every repository-derived string (title, proof, quote, note text) passes
    through ``redaction.redact`` at the point of writing. A free-text field
    rendered outside a fenced block (proof, question, why, the rejection proof
    or trap, and the note text in Task 5) goes through ``free_text`` instead,
    which redacts and also escapes any line that would otherwise read as a
    heading and truncate the finding's body (design_parser._ends_section) or as
    a code fence and desynchronise the two fence scanners on this path. A
    finding's title goes through ``heading_text``, which redacts and collapses
    it to the one line a ``## `` heading can hold, so a title carrying an
    embedded newline cannot splice a second heading into the document.
  - An evidence quote is wrapped in a fence one backtick longer than the longest
    backtick run inside it (``_fence_for``), so a quote lifted from a Markdown or
    Ruby fixture cannot close the writer's own fence and spill into the document
    as prose. See that function for what this does *not* fix on the read side.
  - ``mark_promoted`` writes ``<path>.tmp`` then ``os.replace`` onto ``<path>``
    (atomic on POSIX + Windows) and keeps the previous content at ``<path>.bak``.
    It only touches findings currently ``approved``; an already-``promoted``
    finding is an idempotent no-op (and skips the ``.bak`` rotation when nothing
    changes).

Slug + status validation is shared with design_parser via validation.py so the
write side and read side accept the same inputs.

Direct-path invocable (no package imports): `python design_writer.py ...`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, NamedTuple

from design_parser import DesignParseError, parse_design
from inventory import write_json
from redaction import redact
from slugs import unique_slugs

SCHEMA_VERSION: Final[int] = 2

# The seven body sections of spec 4.11, in document order. "Top" is rendered as
# ``# Top <count>``; the other six are their own H1 headings verbatim.
SECTION_ORDER: Final[tuple[str, ...]] = (
    "Top",
    "Below the cut",
    "Below the cut: tier C and unverified",
    "Considered and rejected",
    "Looks bad but is fine",
    "Open questions for the maintainer",
    "Not assessed",
)

# Spec 4.11's own wording for a top-N finding the note agent did not answer for.
NOTE_PLACEHOLDER: Final[str] = "remediation note not available"
# A confirmed finding whose verdict carried no proof text still needs a body.
NO_PROOF: Final[str] = "no verifier proof"
# Rendered in place of an empty section body, so no section is a bare heading.
EMPTY_SECTION: Final[str] = "_None._"
# A finding with no evidence (a repository-level finding) has no file to name.
NO_FILE: Final[str] = "-"
# Spec 4.11's contract for the single remediation-note agent (Task 5): the JSON
# array shape ``notes.json`` must satisfy, verbatim in every rendered prompt.
NOTES_CONTRACT: Final[str] = """\
Reply with one JSON array, one object per finding, exactly these keys:

[
  {
    "fingerprint": "<as given>",
    "remediation": "<=120 words on how to pay this debt down, no code>",
    "acceptance_criteria": ["<one checkable statement>", "..."]
  }
]

Write for the engineer who will do the work: what to change and in what order, not why
the debt matters. Two to five acceptance criteria, each checkable by reading a diff or
running a test. Do not restate the finding, do not propose a schedule, do not include a
fix in code."""

# The three fixed "Not assessed" bullets; only the families line is computed.
NOT_ASSESSED_FIXED: Final[tuple[str, ...]] = (
    "- Tools: the tool probe lands in phase 4, so currency, end-of-life and "
    "vulnerability claims are not assessed",
    "- Runtime-only: coverage numbers, flake confirmation, model staleness, "
    "rollout state, deploy frequency",
    "- By design: magic literals, convention violations, and class-level metrics "
    "that need a parser",
)
# The six documents ``load_inputs`` requires; ``notes.json`` and ``diff.json``
# are optional (the note agent is Task 5's step, and diff.json lands in phase 5).
REQUIRED_DOCUMENTS: Final[tuple[str, ...]] = (
    "inventory.json",
    "coupling.json",
    "scan-plan.json",
    "verified.json",
    "ranked.json",
    "candidates.json",
)


class DesignWriteError(Exception):
    """Raised when rendering or an in-place status edit fails."""


@dataclass(slots=True)
class RenderInputs:
    """Every document ``render_design`` reads, loaded once from the workdir."""

    workdir: Path
    inventory: dict[str, Any]
    coupling: dict[str, Any]
    plan: dict[str, Any]
    verified: dict[str, Any]
    ranked: dict[str, Any]
    candidates: dict[str, Any]
    notes: list[dict[str, Any]] = field(default_factory=list)
    diff: dict[str, Any] | None = None


class Row(NamedTuple):
    """One finding paired with its rank entry and its document-unique slug."""

    rank: dict[str, Any]
    finding: dict[str, Any]
    slug: str


def load_inputs(workdir: Path) -> RenderInputs:
    """Load every render input; the six required documents must exist and be objects."""

    def required(name: str) -> dict[str, Any]:
        path = workdir / name
        if not path.is_file():
            raise DesignWriteError(f"{path} not found; run the chain first")
        loaded = json.loads(path.read_bytes())
        if not isinstance(loaded, dict):
            raise DesignWriteError(f"{path} is not a JSON object")
        return loaded

    notes_path = workdir / "notes.json"
    notes_raw = json.loads(notes_path.read_bytes()) if notes_path.is_file() else []
    notes = (
        [n for n in notes_raw if isinstance(n, dict)] if isinstance(notes_raw, list) else []
    )
    diff_path = workdir / "diff.json"
    diff_raw = json.loads(diff_path.read_bytes()) if diff_path.is_file() else None
    return RenderInputs(
        workdir=workdir,
        inventory=required("inventory.json"),
        coupling=required("coupling.json"),
        plan=required("scan-plan.json"),
        verified=required("verified.json"),
        ranked=required("ranked.json"),
        candidates=required("candidates.json"),
        notes=notes,
        diff=diff_raw if isinstance(diff_raw, dict) else None,
    )


# --- counting, ordering ---------------------------------------------------------


def _findings(inputs: RenderInputs) -> list[dict[str, Any]]:
    raw = inputs.verified.get("findings") or []
    return [f for f in raw if isinstance(f, dict)]


def _stat_sum(stats: Any, key: str) -> int:
    """Sum ``key`` across ``candidates.json``'s per-family stats blocks."""
    if not isinstance(stats, dict):
        return 0
    total = 0
    for block in stats.values():
        if isinstance(block, dict):
            value = block.get(key, 0)
            if isinstance(value, int):
                total += value
    return total


def _counts(inputs: RenderInputs) -> dict[str, int]:
    """The frontmatter ``counts`` block, in spec 4.11's pinned key order.

    ``new`` and ``resolved`` are appended only when ``diff.json`` was present;
    in phase 3 it never is, so the two keys are simply absent.
    """
    findings = _findings(inputs)
    stats = inputs.candidates.get("stats")
    counts: dict[str, int] = {
        "candidates": len(inputs.candidates.get("candidates") or []),
        "quote_failed": _stat_sum(stats, "quote_failed"),
        "verified": sum(1 for f in findings if f.get("verified")),
        "tier_a": sum(1 for f in findings if f.get("tier") == "A"),
        "tier_b": sum(1 for f in findings if f.get("tier") == "B"),
        "tier_c": sum(1 for f in findings if f.get("tier") == "C"),
        "unverified": sum(1 for f in findings if f.get("verdict") == "unverified"),
        "rejected": sum(1 for f in findings if f.get("verdict") == "reject"),
        "suppressed": _stat_sum(stats, "suppressed"),
    }
    if inputs.diff is not None:
        diff_counts = inputs.diff.get("counts")
        diff_counts = diff_counts if isinstance(diff_counts, dict) else {}
        counts["new"] = int(diff_counts.get("new", 0))
        counts["resolved"] = int(diff_counts.get("resolved", 0))
    return counts


def _ordered(inputs: RenderInputs) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """``(rank_entry, finding)`` pairs in ``ranked.json`` order.

    A ranked fingerprint with no verified finding is skipped. A verified
    finding with no rank entry is appended after the ranked ones with a
    synthesised entry whose ``priority`` is null; it can never be in the top N.
    """
    by_fingerprint = {str(f.get("fingerprint")): f for f in _findings(inputs)}
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    placed: set[str] = set()
    for entry in inputs.ranked.get("findings") or []:
        if not isinstance(entry, dict):
            continue
        fingerprint = str(entry.get("fingerprint"))
        finding = by_fingerprint.get(fingerprint)
        if finding is None:
            continue
        placed.add(fingerprint)
        pairs.append((entry, finding))
    for finding in _findings(inputs):
        fingerprint = str(finding.get("fingerprint"))
        if fingerprint in placed:
            continue
        pairs.append(
            (
                {
                    "fingerprint": fingerprint,
                    "rank": None,
                    "priority": None,
                    "terms": {},
                    "tier": finding.get("tier"),
                    "in_top_n": False,
                    "spread_capped": False,
                },
                finding,
            )
        )
    return pairs


def _rows(inputs: RenderInputs) -> list[Row]:
    """``_ordered`` with one document-unique slug per finding, derived from its title.

    The slugs are allocated over the whole ordered list, so a finding's slug
    does not change when another finding is added below it.

    The slug comes from ``heading_text(title)``, the same redacted string the
    document renders, never the raw one. A slug is not a display string that a
    reader can be trusted to ignore: it is the anchor's ``slug:`` key,
    ``findings.json``'s ``slug``, the PBI bundle's directory name and
    ``PBI.md``'s ``id:`` -- and the bundle directory is committed into the
    target repository. An AWS access key id is ``[A-Z0-9]{20}``, so a lowercase
    slug segment gives one back exactly by uppercasing it. Every producer
    reaching here today redacts the title before ``verified.json`` is written,
    so this moves nothing; it stops the writer from redacting the same string
    for one consumer and not the other.
    """
    pairs = _ordered(inputs)
    slugs = unique_slugs([heading_text(str(finding.get("title") or "")) for _, finding in pairs])
    return [Row(rank, finding, slug) for (rank, finding), slug in zip(pairs, slugs, strict=True)]


def _diff_for(inputs: RenderInputs, fingerprint: str) -> str:
    """``NEW`` when there is no baseline diff, else the fingerprint's diff status."""
    if inputs.diff is None:
        return "NEW"
    status = inputs.diff.get("status")
    entry = status.get(fingerprint) if isinstance(status, dict) else None
    if isinstance(entry, dict) and entry.get("diff"):
        return str(entry["diff"])
    return "NEW"


# --- rendering ------------------------------------------------------------------


def free_text(value: str) -> str:
    """Redacted free text safe to drop into the document body.

    Two line shapes are structural to the readers of this document and are
    neutralised the same way, by a leading backslash:

    - A line that begins with ``#`` would read as a heading and end the
      finding's section (design_parser._ends_section), taking Evidence and the
      note sections out of the body that bundle_writer copies into a PBI.
    - A line whose stripped text opens with a run of three or more backticks is
      a fence delimiter to both fence scanners on the write path -- ``_h1_names``
      here and design_parser's per-section scan -- each of which computes the run
      with an ``lstrip("`")`` over the stripped line. An *odd* number of such
      lines in one field leaves the two scans disagreeing (design_parser's outer
      H2 scan tracks no fences at all), ``_h1_names`` swallows every H1 that
      follows, and ``_check_headings`` aborts the whole render over one stray
      line from one agent. A backslash makes the leading-backtick run zero for
      both scanners, so the line is no longer a delimiter to either.

    Markdown renders ``\\#`` and ``\\```` as a literal ``#`` and a literal
    backtick, so an escaped line is both correct on screen and inert to the
    boundary. Only backticks are escaped: neither scanner recognises a ``~~~``
    fence, so a tilde line is not a boundary and is left as the agent wrote it.

    Every free-text field the writer places outside a fenced block (proof, and in
    Tasks 4/5 note, question, why and the remediation text) must go through this
    function rather than ``redact`` directly, so the escape cannot be forgotten
    field by field. ``write_design``'s self-check also verifies the effect of
    this function at write time, so a field that skips it fails loudly there.
    """
    redacted = redact(value)
    escaped: list[str] = []
    for line in redacted.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#") or len(stripped) - len(stripped.lstrip("`")) >= 3:
            indent = line[: len(line) - len(stripped)]
            escaped.append(f"{indent}\\{stripped}")
        else:
            escaped.append(line)
    return "\n".join(escaped)


def heading_text(value: str) -> str:
    """A finding's title, redacted and collapsed to the single line a heading is.

    The title is the one agent-supplied string the writer splices into a line it
    also owns (``## <title>``, and ``## <n>. <title>`` in the notes prompt).
    ``merge_findings._validate`` strips only leading and trailing whitespace, so
    an embedded newline reaches the writer intact, and the continuation line
    lands in the document as a line of its own: a ``# ``-shaped one becomes a
    section heading to ``design_parser``, which then finds no anchor under the
    finding's heading and aborts the whole render -- one stray line from one
    agent discarding a run's twelve scouts, its verifier batches and its note
    agent.

    A title is a single line by nature, so this collapses every whitespace run
    to one space rather than escaping each shape a continuation might take
    (``free_text``'s job, for the fields that are genuinely multi-line). After
    the collapse the ``## `` prefix guarantees the rendered line can be neither a
    heading of another level nor a fence to either scanner, whatever the title
    holds, and the heading still reads as the words the agent wrote -- where an
    escape would leave a backslash in the title that ``findings.json`` and a
    promoted ``PBI.md`` would carry as part of the name.
    """
    return " ".join(redact(value).split())


def _scalar(value: Any) -> str:
    """A YAML scalar for an anchor value; ``None`` renders as ``null``."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _yaml_block(key: str, item_lines: list[str]) -> list[str]:
    """``key:`` with its items beneath it, or ``key: []`` when there are none."""
    if not item_lines:
        return [f"{key}: []"]
    return [f"{key}:", *item_lines]


def _frontmatter(inputs: RenderInputs, scan_date: str) -> list[str]:
    inv, plan = inputs.inventory, inputs.plan
    lines = [
        "---",
        "schema_version: 2",
        f"scan_date: {scan_date}",
        f"root: {inv['root']}",
        f"total_files: {inv['total_files']}",
        f"total_loc: {inv['total_loc']}",
    ]
    lines += _yaml_block("languages", [f"- {lang}" for lang in inv.get("languages") or []])
    lines.append(f"preset: {inputs.ranked.get('preset', 'balanced')}")
    lines += _yaml_block(
        "families_run", [f"- {name}" for name in plan.get("families_run") or []]
    )
    skipped: list[str] = []
    for item in plan.get("families_skipped") or []:
        skipped += [f"- family: {item['family']}", f"  reason: {item['reason']}"]
    lines += _yaml_block("families_skipped", skipped)
    lines += [
        # The tool probe lands in phase 4; both lists stay empty until then.
        "tools_run: []",
        "tools_absent: []",
        f"git_available: {str(bool(inv.get('git_available'))).lower()}",
        "counts:",
        *[f"  {key}: {value}" for key, value in _counts(inputs).items()],
        "---",
    ]
    return lines


def _header(inputs: RenderInputs, scan_date: str) -> list[str]:
    inv = inputs.inventory
    langs = ", ".join(str(lang) for lang in inv.get("languages") or [])
    scanned = (
        f"Scanned `{inv['root']}` - {inv['total_files']} files, "
        f"{inv['total_loc']} LOC across: {langs}."
    )
    lines = [
        "",
        f"# Tech-debt scan - {scan_date}",
        "",
        scanned,
        "",
        "Review each finding below. To act on one, change its `status:` from `pending` to",
        "`approved`, `rejected`, or `accepted` (add a `reason:` and an optional `until:` ISO",
        "date), then run `/tech-debt-promote`.",
    ]
    if not inv.get("git_available"):
        return [*lines, "", "No git history: churn is 0 and the interest signal is absent."]

    hotspots = [h for h in (inv.get("hotspots") or []) if isinstance(h, dict)][:5]
    if hotspots:
        summary = ", ".join(f"`{h['path']}` ({h['score']})" for h in hotspots)
        lines += ["", f"Top hotspots: {summary}."]
    pairs = [p for p in (inputs.coupling.get("pairs") or []) if isinstance(p, dict)][:5]
    if pairs:
        summary = ", ".join(
            f"`{p['a']}` <-> `{p['b']}` (shared {p['shared_commits']}, ratio {p['ratio']})"
            for p in pairs
        )
        lines += ["", f"Top coupled pairs: {summary}."]
    return lines


def _anchor(inputs: RenderInputs, row: Row) -> list[str]:
    """The finding's yaml anchor, in spec 4.11's pinned key order.

    ``category`` is always the alias of ``family``: it is a required parser key
    and ``bundle_writer.py`` reads it unconditionally.
    """
    finding = row.finding
    family = finding.get("family")
    fingerprint = str(finding.get("fingerprint"))
    values: list[tuple[str, Any]] = [
        ("status", "pending"),
        ("slug", row.slug),
        ("fingerprint", fingerprint),
        ("tier", finding.get("tier")),
        ("priority", row.rank.get("priority")),
        ("family", family),
        ("category", family),
        ("debt_type", finding.get("debt_type")),
        ("type_id", finding.get("type_id")),
        ("severity", finding.get("severity")),
        ("effort", finding.get("effort")),
        ("diff", _diff_for(inputs, fingerprint)),
    ]
    return [f"{key}: {_scalar(value)}" for key, value in values]


_BACKTICK_RUN: Final[re.Pattern[str]] = re.compile("`+")


def _fence_for(quote: str) -> str:
    """The fence marker that can hold ``quote``: one backtick longer than its longest run.

    A three-backtick fence is only safe while the quoted source has no backticks
    of its own. The inventory walks Markdown and Ruby, so a quote that itself
    contains a ```` ``` ```` line is reachable; wrapped in a plain fence it closes
    the writer's block early and every later line of the quote renders as prose,
    including any heading-shaped one. Widening the fence keeps the quote a single
    code block in the rendered document whatever it contains.

    ``design_parser`` closes a fence only on a line of backticks alone whose run
    is at least as long as the one that opened it. The wrapper this function
    returns is always one backtick longer than the quote's own longest run, so
    nothing inside the quote can ever be long enough to close it early: a quote
    carrying its own complete fenced block (a quoted docstring, a Ruby heredoc)
    round-trips through ``parse_design`` whole, anchor and all.
    """
    longest = max((len(m.group()) for m in _BACKTICK_RUN.finditer(quote)), default=0)
    return "`" * max(3, longest + 1)


def _evidence_item(item: dict[str, Any]) -> list[str]:
    """One evidence citation line, then its quote in an unlabelled fenced block.

    Three citation shapes, depending on what the item actually carries:
      - no file at all (a repository-level finding, e.g. a missing CODEOWNERS)
        names neither file nor line range;
      - a file but a null bound on either side names the file and says "whole
        file" rather than interpolating ``None`` into a range;
      - a file with both bounds gets the ordinary ``file:start-end`` citation.
    An empty quote has nothing to fence, so no fenced block is emitted for it;
    a non-empty quote keeps its adaptive fence in every shape above.
    """
    file = item.get("file")
    start = item.get("line_start")
    end = item.get("line_end")
    if not file:
        citation = "- repository-level finding (no file or line range)"
    elif start is None or end is None:
        citation = f"- `{file}` (whole file)"
    else:
        citation = f"- `{file}:{start}-{end}`"
    lines = ["", citation]
    quote = redact(str(item.get("quote") or ""))
    if quote:
        fence = _fence_for(quote)
        lines += ["", fence, *quote.split("\n"), fence]
    return lines


def _signal_lines(finding: dict[str, Any]) -> list[str]:
    signals = finding.get("signals")
    signals = signals if isinstance(signals, dict) else {}
    fan_in = signals.get("fan_in_approx")
    fan_in_text = "fan-in not computed" if fan_in is None else f"fan-in {fan_in}"
    metrics = (
        f"- hotspot score {signals.get('hotspot_score')}, churn {signals.get('churn')}, "
        f"coupling pairs {signals.get('coupling_degree')}, {fan_in_text} (approximate)"
    )
    confirmed = [str(c) for c in finding.get("confirmed_by") or []]
    return [metrics, f"- confirmed by: {', '.join(confirmed) if confirmed else 'none'}"]


def notes_by_fingerprint(inputs: RenderInputs) -> dict[str, dict[str, Any]]:
    """Valid ``notes.json`` entries for the top-N fingerprints, keyed by fingerprint.

    Kept only when the fingerprint is in ``ranked["top_n"]``, ``remediation`` is a
    non-empty string and ``acceptance_criteria`` is a list of strings; every other
    entry (an unknown fingerprint, an empty or missing remediation, a malformed
    acceptance_criteria) is dropped silently, so a malformed ``notes.json`` makes
    ``_finding_section`` fall back to ``NOTE_PLACEHOLDER`` instead of failing.
    """
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    result: dict[str, dict[str, Any]] = {}
    for note in inputs.notes:
        fingerprint = str(note.get("fingerprint"))
        if fingerprint not in top_n:
            continue
        remediation = note.get("remediation")
        if not isinstance(remediation, str) or not remediation:
            continue
        criteria = note.get("acceptance_criteria")
        if not isinstance(criteria, list) or not all(isinstance(c, str) for c in criteria):
            continue
        result[fingerprint] = {"remediation": remediation, "acceptance_criteria": criteria}
    return result


def _finding_section(
    inputs: RenderInputs,
    row: Row,
    notes: dict[str, dict[str, Any]],
    *,
    compact: bool = False,
) -> list[str]:
    """One H2 finding section. ``compact`` stops after Evidence (below the cut).

    ``notes`` is ``notes_by_fingerprint(inputs)``, computed once by the caller
    (``render_design``) and passed down rather than recomputed per finding.
    """
    finding = row.finding
    lines = [
        "",
        f"## {heading_text(str(finding.get('title') or ''))}",
        "",
        "```yaml",
        *_anchor(inputs, row),
        "```",
        "",
        "### Proof",
        "",
        free_text(str(finding.get("proof") or "")) or NO_PROOF,
        "",
        "### Evidence",
    ]
    for item in finding.get("evidence") or []:
        if isinstance(item, dict):
            lines += _evidence_item(item)
    if compact:
        return lines
    lines += ["", "### Signals", "", *_signal_lines(finding)]
    note = notes.get(str(finding.get("fingerprint")))
    if note is None:
        lines += ["", "### Remediation", "", NOTE_PLACEHOLDER]
        lines += ["", "### Acceptance criteria", "", NOTE_PLACEHOLDER]
    else:
        lines += ["", "### Remediation", "", free_text(str(note["remediation"]))]
        criteria = [f"- [ ] {free_text(str(c))}" for c in note["acceptance_criteria"]]
        lines += ["", "### Acceptance criteria", "", *criteria]
    return lines


def _top_section(
    inputs: RenderInputs, rows: list[Row], notes: dict[str, dict[str, Any]]
) -> list[str]:
    """``# Top <count>`` and one full finding section per top-N fingerprint."""
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    selected = [row for row in rows if str(row.finding.get("fingerprint")) in top_n]
    lines = ["", f"# Top {len(selected)}"]
    for row in selected:
        lines += _finding_section(inputs, row, notes)
    return lines


# --- the remediation-note prompt -------------------------------------------------


def render_notes_prompt(inputs: RenderInputs) -> str:
    """One prompt for the single remediation-note agent, over the top N only (spec 4.11).

    Its reply is ``notes.json``, which ``notes_by_fingerprint`` reads back into the
    ``### Remediation`` and ``### Acceptance criteria`` sections of the same top-N
    findings. Only the top N is shown -- a below-the-cut or rejected finding never
    reaches the note agent -- so the fingerprint set here is exactly
    ``ranked["top_n"]``, in that same priority order.
    """
    root = str(inputs.inventory.get("root") or "")
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    rows = [row for row in _rows(inputs) if str(row.finding.get("fingerprint")) in top_n]
    parts: list[str] = [
        "You are writing the remediation notes for the top tech-debt findings found "
        f"in the repository at `{root}`.",
        "You have read-only access: read and search files if you need more context; "
        "change nothing.",
    ]
    for index, row in enumerate(rows, start=1):
        finding = row.finding
        parts += [
            "",
            f"## {index}. {heading_text(str(finding.get('title') or ''))}",
            f"fingerprint: {finding.get('fingerprint')}",
            f"family: {finding.get('family')}  severity: {finding.get('severity')}  "
            f"effort: {finding.get('effort')}",
            "",
            free_text(str(finding.get("proof") or "")) or NO_PROOF,
        ]
        for item in finding.get("evidence") or []:
            if isinstance(item, dict):
                parts += _evidence_item(item)
    parts += ["", NOTES_CONTRACT]
    return "\n".join(parts) + "\n"


# --- the negative-space sections ------------------------------------------------


def _section(name: str, body: list[str]) -> list[str]:
    """``# <name>``, a blank line, then ``body`` -- or ``_None._`` when it is empty."""
    return ["", f"# {name}", "", *(body or [EMPTY_SECTION])]


def _primary_file(finding: dict[str, Any]) -> str:
    """The file of the first evidence item, or ``-`` for a repository-level finding."""
    for item in finding.get("evidence") or []:
        if isinstance(item, dict) and item.get("file"):
            return str(item["file"])
    return NO_FILE


def _primary_location(finding: dict[str, Any]) -> str:
    """``file:line`` of the first evidence item; the bare file when it carries no line."""
    for item in finding.get("evidence") or []:
        if isinstance(item, dict) and item.get("file"):
            start = item.get("line_start")
            return f"{item['file']}" if start is None else f"{item['file']}:{start}"
    return NO_FILE


def _below_the_cut(
    inputs: RenderInputs, rows: list[Row], name: str, notes: dict[str, dict[str, Any]]
) -> list[str]:
    """``# Below the cut``: a compact H2 per tier A/B finding outside the top N.

    The anchor is the same as a top-N finding's, so the user can approve one of
    these straight from the document; only the Signals and note sections are
    dropped, because those are the expensive parts the note agent fills in.
    Built here rather than through ``_section`` because ``_finding_section``
    supplies its own leading blank line. ``notes`` is unused in ``compact``
    mode (there is no Remediation/Acceptance criteria to fill in here) but is
    threaded through anyway to keep ``_finding_section``'s signature uniform.
    """
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    selected = [
        row
        for row in rows
        if row.finding.get("tier") in ("A", "B")
        and str(row.finding.get("fingerprint")) not in top_n
    ]
    if not selected:
        return _section(name, [])
    lines = ["", f"# {name}"]
    for row in selected:
        lines += _finding_section(inputs, row, notes, compact=True)
    return lines


def _tier_c_table(rows: list[Row]) -> list[str]:
    """One table row per tier C or unverified finding; a reject belongs elsewhere."""
    selected = [
        row
        for row in rows
        if row.finding.get("verdict") != "reject"
        and (row.finding.get("tier") == "C" or row.finding.get("verdict") == "unverified")
    ]
    if not selected:
        return []
    lines = ["| slug | family | file | reason |", "| --- | --- | --- | --- |"]
    for row in selected:
        finding = row.finding
        lines.append(
            f"| {row.slug} | {finding.get('family')} | {_primary_file(finding)} "
            f"| {finding.get('verdict')} |"
        )
    return lines


def _considered_and_rejected(rows: list[Row]) -> list[str]:
    """One bullet per ``reject``; a matched trap replaces the verifier's proof."""
    lines: list[str] = []
    for row in rows:
        finding = row.finding
        if finding.get("verdict") != "reject":
            continue
        detail = finding.get("trap_matched") or finding.get("proof") or NO_PROOF
        # The title goes through heading_text, not free_text: it is rendered inside
        # a bullet this function owns, so a newline in it breaks the bullet in half
        # rather than adding a line of prose. Collapsing keeps the bullet one line;
        # the escape free_text would add is then unreachable, since nothing the
        # title holds can start a line.
        title = heading_text(str(finding.get("title") or ""))
        lines.append(
            f"- **{title}** - `{_primary_file(finding)}` - {free_text(str(detail))}"
        )
    return lines


def _looks_bad_but_fine(inputs: RenderInputs, rows: list[Row]) -> list[str]:
    """The scouts' own "looks bad but is fine" entries, then the trap rejections.

    A trap-matched rejection is the verifier reaching the same conclusion the
    scouts reach in ``looks_bad_but_fine``, so it is listed in both places: here
    for the reader who wants the whole "not a bug" list, and under "Considered
    and rejected" for the reader auditing what the scan threw away.
    """
    lines: list[str] = []
    for entry in inputs.candidates.get("looks_bad_but_fine") or []:
        if not isinstance(entry, dict):
            continue
        why = free_text(str(entry.get("why") or ""))
        lines.append(f"- `{entry.get('file', '')}:{entry.get('line_start')}` - {why}")
    for row in rows:
        finding = row.finding
        if finding.get("verdict") != "reject" or not finding.get("trap_matched"):
            continue
        trap = free_text(str(finding["trap_matched"]))
        lines.append(f"- `{_primary_location(finding)}` - {trap}")
    return lines


def _open_questions(inputs: RenderInputs) -> list[str]:
    """``candidates.json``'s open questions; a quote failure says so up front."""
    lines: list[str] = []
    for entry in inputs.candidates.get("open_questions") or []:
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question") or "")
        if entry.get("reason") == "quote not found":
            question = f"quote not found: {question}"
        lines.append(
            f"- `{entry.get('file', '')}:{entry.get('line_start')}` - {free_text(question)}"
        )
    return lines


def _not_assessed(inputs: RenderInputs) -> list[str]:
    """The families the plan skipped, then the three standing limits of a v2 scan."""
    skipped = [
        f"{item['family']} ({item['reason']})"
        for item in inputs.plan.get("families_skipped") or []
    ]
    families = ", ".join(skipped) if skipped else "none"
    return [f"- Families not run: {families}", *NOT_ASSESSED_FIXED]


# --- the two documents ----------------------------------------------------------


def render_design(inputs: RenderInputs, scan_date: str) -> str:
    """Render the whole ``design.md`` as an LF-only string ending in one newline."""
    rows = _rows(inputs)
    # Computed once here rather than once per top-N/below-the-cut finding inside
    # _finding_section, which recomputed the same top-N notes dict on every call.
    notes = notes_by_fingerprint(inputs)
    # SECTION_ORDER is the single source of the six H1 names; unpacking it here
    # means a section added to that tuple fails loudly instead of going unwritten.
    below, tier_c, rejected, fine, questions, not_assessed = SECTION_ORDER[1:]
    parts: list[str] = []
    parts += _frontmatter(inputs, scan_date)
    parts += _header(inputs, scan_date)
    parts += _top_section(inputs, rows, notes)
    parts += _below_the_cut(inputs, rows, below, notes)
    parts += _section(tier_c, _tier_c_table(rows))
    parts += _section(rejected, _considered_and_rejected(rows))
    parts += _section(fine, _looks_bad_but_fine(inputs, rows))
    parts += _section(questions, _open_questions(inputs))
    parts += _section(not_assessed, _not_assessed(inputs))
    return "\n".join(parts) + "\n"


def _json_evidence(finding: dict[str, Any]) -> list[dict[str, Any]]:
    """The finding's evidence items with the quotes redacted, keys otherwise untouched."""
    items: list[dict[str, Any]] = []
    for item in finding.get("evidence") or []:
        if isinstance(item, dict):
            items.append({**item, "quote": redact(str(item.get("quote") or ""))})
    return items


def render_findings_json(inputs: RenderInputs) -> dict[str, Any]:
    """The machine-readable twin of ``design.md``: one entry per finding, same order.

    ``evaluate.py`` prefers this over ``verified.json`` because it joins the
    verdict to the rank (``priority``, ``terms``, ``in_top_n``, ``spread_capped``)
    and to the document (``slug``, ``diff``). Every repository-derived string is
    redacted exactly as it is in the markdown, so a secret cannot leak through
    the machine file after being scrubbed from the human one.
    """
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    findings: list[dict[str, Any]] = []
    for row in _rows(inputs):
        finding = row.finding
        fingerprint = str(finding.get("fingerprint"))
        findings.append(
            {
                "fingerprint": fingerprint,
                "slug": row.slug,
                "title": heading_text(str(finding.get("title") or "")),
                "family": finding.get("family"),
                "debt_type": finding.get("debt_type"),
                "type_id": finding.get("type_id"),
                "severity": finding.get("severity"),
                "effort": finding.get("effort"),
                "evidence": _json_evidence(finding),
                "signals": finding.get("signals") or {},
                "confirmed_by": list(finding.get("confirmed_by") or []),
                "tier": finding.get("tier"),
                "verdict": finding.get("verdict"),
                "proof": redact(str(finding.get("proof") or "")),
                "priority": row.rank.get("priority"),
                "terms": row.rank.get("terms") or {},
                "in_top_n": fingerprint in top_n,
                "spread_capped": bool(row.rank.get("spread_capped")),
                "diff": _diff_for(inputs, fingerprint),
            }
        )
    return {"schema_version": SCHEMA_VERSION, "findings": findings}


_TOP_HEADING: Final[re.Pattern[str]] = re.compile(r"^Top \d+$")


def _h1_names(text: str) -> list[str]:
    """The ``# `` heading names in ``text``, in document order.

    Mirrors design_parser's own length-aware fence rule (a line opens a fence
    at 3+ leading backticks, recording that run's length; only a
    backticks-alone line with an equal or longer run closes it), so a
    heading-shaped line inside a quote's own nested fence is never mistaken
    for a real section heading. The frontmatter block is skipped outright,
    since design_parser's own scan never looks inside it either.
    """
    lines = text.split("\n")
    start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                start = idx + 1
                break
    names: list[str] = []
    in_fence = False
    fence_len = 0
    for line in lines[start:]:
        stripped = line.strip()
        run = len(stripped) - len(stripped.lstrip("`"))
        if in_fence:
            if run == len(stripped) and run >= fence_len:
                in_fence = False
                fence_len = 0
            continue
        if run >= 3:
            in_fence = True
            fence_len = run
            continue
        if line.startswith("# "):
            names.append(line[2:].strip())
    return names


def _check_headings(text: str) -> None:
    """The document's H1 headings, after the scan header, must be exactly SECTION_ORDER.

    ``render_design`` always emits exactly one H1 header
    (``# Tech-debt scan - <date>``) before the seven body sections, so it is
    dropped before comparing the rest. ``parse_design`` never returns the
    prose between H1 sections at all -- it only tracks H2 finding sections --
    so a heading-shaped line spliced into a negative-space field by a
    free-text call site that skipped ``free_text`` is invisible to the rest of
    the self-check; this is the only thing that catches it.
    """
    names = _h1_names(text)
    actual = ["Top" if _TOP_HEADING.match(name) else name for name in names[1:]]
    expected = list(SECTION_ORDER)
    if actual == expected:
        return
    unexpected = next((name for name in actual if name not in expected), None)
    if unexpected is None:
        unexpected = next((a for a, e in zip(actual, expected, strict=False) if a != e), None)
    if unexpected is None:
        unexpected = actual[len(expected)] if len(actual) > len(expected) else "<missing section>"
    raise DesignWriteError(
        f"self-check failed: unexpected heading {unexpected!r} among the document's "
        f"H1 sections; expected {expected!r} in order, found {actual!r}"
    )


def _self_check(text: str) -> None:
    """Parse the rendered markdown back through design_parser before anything is written.

    ``parse_design`` only reads from a path, so ``text`` is spooled to a
    throwaway temp file for the duration of the check; nothing under
    ``out_path`` or the workdir is touched here. Two things must hold: every
    finding's body still carries the "### Evidence" heading that was written
    for it (a free-text field that skips ``free_text`` and leaves a
    heading-shaped line unescaped would otherwise truncate the section --
    design_parser._ends_section reads it as a new H1 -- and vanish silently
    instead of failing loudly here); and the document's H1 headings are
    exactly SECTION_ORDER, in order, after the scan header (see
    ``_check_headings`` for why this second check exists).
    """
    fd, tmp_name = tempfile.mkstemp(suffix=".md")
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        tmp_path.write_bytes(text.encode("utf-8"))
        try:
            parsed = parse_design(tmp_path)
        except DesignParseError as exc:
            raise DesignWriteError(f"self-check failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    for finding in parsed["findings"]:
        if "### Evidence" not in finding["body_md"]:
            raise DesignWriteError(
                f"self-check failed: finding {finding['slug']!r} lost its body "
                "past an unescaped heading-shaped line"
            )
    _check_headings(text)


def write_design(inputs: RenderInputs, scan_date: str, out_path: Path) -> None:
    """Render design.md + findings.json in memory, self-check, then write both.

    ``findings.json`` always lands in ``inputs.workdir`` -- never beside
    ``out_path`` -- because ``evaluate.load_findings`` only looks in the
    workdir it is given; a ``--out`` pointed elsewhere must not hide it from
    that lookup. Both documents are rendered and the markdown is self-checked
    before anything touches disk, so a rejected render leaves neither a stale
    ``design.md`` nor a stale ``findings.json`` behind for a later
    ``evaluate.py`` run to prefer over ``verified.json``.
    """
    text = render_design(inputs, scan_date)
    findings_doc = render_findings_json(inputs)
    _self_check(text)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(text.encode("utf-8"))
    write_json(inputs.workdir / "findings.json", findings_doc)


def _status_line_index(lines: list[str], anchor_lineno: int) -> int | None:
    """Return the 0-based index of the ``status:`` line inside the anchor.

    ``anchor_lineno`` is the 1-based line of the opening ```yaml fence (as
    reported by parse_design). The status key may sit anywhere inside the fence.
    """
    open_idx = anchor_lineno - 1
    i = open_idx + 1
    while i < len(lines) and lines[i].strip() != "```":
        if lines[i].lstrip().startswith("status:"):
            return i
        i += 1
    return None


def mark_promoted(path: Path, slugs: list[str]) -> None:
    """Flip each ``slug`` from ``approved`` to ``promoted`` in place.

    Raises DesignWriteError for an unknown slug or a finding that is not
    currently ``approved``. Already-``promoted`` findings are a no-op. When no
    finding actually changes, the file (and its ``.bak``) is left untouched.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DesignWriteError(f"could not read {path}: {exc}") from exc

    parsed = parse_design(path)
    by_slug = {f["slug"]: f for f in parsed["findings"]}

    for slug in slugs:
        if slug not in by_slug:
            raise DesignWriteError(f"unknown slug: {slug!r}")

    to_change: list[str] = []
    for slug in slugs:
        status = by_slug[slug]["status"]
        if status == "promoted":
            continue  # idempotent no-op
        if status != "approved":
            raise DesignWriteError(
                f"finding {slug!r} is not approved (status: {status!r})"
            )
        to_change.append(slug)

    if not to_change:
        return  # nothing to do; do not rotate .bak

    lines = text.splitlines()
    for slug in to_change:
        idx = _status_line_index(lines, by_slug[slug]["line"])
        if idx is None:
            raise DesignWriteError(f"could not locate status line for {slug!r}")
        lines[idx] = "status: promoted"

    new_text = "\n".join(lines) + "\n"

    bak_path = Path(str(path) + ".bak")
    bak_path.write_bytes(text.encode("utf-8"))

    tmp_path = Path(str(path) + ".tmp")
    tmp_path.write_bytes(new_text.encode("utf-8"))
    os.replace(tmp_path, path)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or edit a design.md")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_render = sub.add_parser("render", help="render a design.md from the chain outputs")
    p_render.add_argument(
        "--workdir", default=".tech-debt", help="directory holding the chain outputs"
    )
    p_render.add_argument("--scan-date", required=True, help="ISO scan date")
    p_render.add_argument("--out", help="output design.md path (default <workdir>/design.md)")

    p_notes = sub.add_parser(
        "notes-prompt", help="render the remediation-note agent's prompt"
    )
    p_notes.add_argument(
        "--workdir", default=".tech-debt", help="directory holding the chain outputs"
    )
    p_notes.add_argument(
        "--top", type=int, default=None,
        help="narrow the top N below ranked.json's own top (never widens it)",
    )

    p_mark = sub.add_parser("mark-promoted", help="flip approved findings to promoted")
    p_mark.add_argument("design", help="path to design.md")
    p_mark.add_argument("--slug", action="append", default=[], help="slug to promote")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "render":
            workdir = Path(args.workdir)
            out_path = Path(args.out) if args.out else workdir / "design.md"
            write_design(load_inputs(workdir), args.scan_date, out_path)
            print(f"wrote {out_path}")
            print(f"wrote {workdir / 'findings.json'}")
        elif args.cmd == "notes-prompt":
            workdir = Path(args.workdir)
            inputs = load_inputs(workdir)
            if args.top is not None:
                top_n = list(inputs.ranked.get("top_n") or [])
                inputs.ranked["top_n"] = top_n[: max(0, min(args.top, len(top_n)))]
            text = render_notes_prompt(inputs)
            out_path = workdir / "prompts" / "notes.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(text.encode("utf-8"))
            print(f"wrote {out_path}")
        else:
            mark_promoted(Path(args.design), slugs=args.slug)
            print(f"promoted {len(args.slug)} finding(s) in {args.design}")
    except (DesignWriteError, DesignParseError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
