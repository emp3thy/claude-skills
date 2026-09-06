"""Render design.md and apply in-place ``mark_promoted`` status edits.

``render`` is the report stage of /tech-debt-scan (spec 4.11). It reads the
whole phase 2 chain out of ``--workdir`` (``inventory.json``, ``coupling.json``,
``scan-plan.json``, ``verified.json``, ``ranked.json``, ``candidates.json``,
plus the optional ``notes.json`` and ``diff.json``) and renders the single
``design.md`` the user reviews. ``mark_promoted`` is stage 3 of
/tech-debt-promote: it flips approved findings to ``promoted`` in place once
their bundles have been emitted.

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
  - After writing, ``write_design`` re-parses its own output as a self-check so
    format drift surfaces at write time, not just in tests.
  - Every repository-derived string (title, proof, quote, note text) passes
    through ``redaction.redact`` at the point of writing. A free-text field
    rendered outside a fenced block (proof; note, question, why and the
    remediation text in Tasks 4/5) goes through ``free_text`` instead, which
    redacts and also escapes any line that would otherwise read as a heading
    and truncate the finding's body (design_parser._ends_section).
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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, NamedTuple

from design_parser import DesignParseError, parse_design
from redaction import redact
from slugs import unique_slugs

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
    """
    pairs = _ordered(inputs)
    slugs = unique_slugs([str(finding.get("title") or "") for _, finding in pairs])
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

    A line that begins with ``#`` would read as a heading and end the finding's
    section (design_parser._ends_section), taking Evidence and the note sections
    out of the body that bundle_writer copies into a PBI. Markdown renders ``\\#``
    as a literal ``#``, and the parser's predicates no longer match, so an escaped
    line is both correct on screen and inert to the boundary.

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
        if stripped.startswith("#"):
            indent = line[: len(line) - len(stripped)]
            escaped.append(f"{indent}\\{stripped}")
        else:
            escaped.append(line)
    return "\n".join(escaped)


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


def _evidence_item(item: dict[str, Any]) -> list[str]:
    """One ``- `file:start-end`` line then its quote in an unlabelled fenced block."""
    start = item.get("line_start")
    end = item.get("line_end")
    end = start if end is None else end
    quote = redact(str(item.get("quote") or ""))
    return [
        "",
        f"- `{item.get('file', '')}:{start}-{end}`",
        "",
        "```",
        *quote.split("\n"),
        "```",
    ]


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


def _finding_section(inputs: RenderInputs, row: Row, *, compact: bool = False) -> list[str]:
    """One H2 finding section. ``compact`` stops after Evidence (below the cut)."""
    finding = row.finding
    lines = [
        "",
        f"## {redact(str(finding.get('title') or ''))}",
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
    lines += ["", "### Remediation", "", NOTE_PLACEHOLDER]
    lines += ["", "### Acceptance criteria", "", NOTE_PLACEHOLDER]
    return lines


def _top_section(inputs: RenderInputs, rows: list[Row]) -> list[str]:
    """``# Top <count>`` and one full finding section per top-N fingerprint."""
    top_n = {str(fp) for fp in inputs.ranked.get("top_n") or []}
    selected = [row for row in rows if str(row.finding.get("fingerprint")) in top_n]
    lines = ["", f"# Top {len(selected)}"]
    for row in selected:
        lines += _finding_section(inputs, row)
    return lines


def render_design(inputs: RenderInputs, scan_date: str) -> str:
    """Render the whole ``design.md`` as an LF-only string ending in one newline."""
    rows = _rows(inputs)
    parts: list[str] = []
    parts += _frontmatter(inputs, scan_date)
    parts += _header(inputs, scan_date)
    parts += _top_section(inputs, rows)
    # Tasks 4 and 5 of the phase 3 plan fill these bodies; the headings are
    # emitted from the first commit so the document shape and the parser's H1
    # section boundary are exercised.
    for name in SECTION_ORDER[1:]:
        parts += ["", f"# {name}"]
    return "\n".join(parts) + "\n"


def write_design(inputs: RenderInputs, scan_date: str, out_path: Path) -> None:
    """Write ``design.md`` to ``out_path``, then re-parse it as a self-check."""
    text = render_design(inputs, scan_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(text.encode("utf-8"))

    # Self-check: the document must parse back through the read side cleanly, and
    # every finding's body must still carry the "### Evidence" heading that was
    # written for it. A free-text field that skips ``free_text`` and leaves a
    # heading-shaped line unescaped would otherwise truncate the section
    # (design_parser._ends_section reads it as a new H1) and vanish silently
    # instead of failing loudly here.
    try:
        parsed = parse_design(out_path)
    except DesignParseError as exc:
        raise DesignWriteError(f"self-check failed: {exc}") from exc

    for finding in parsed["findings"]:
        if "### Evidence" not in finding["body_md"]:
            raise DesignWriteError(
                f"self-check failed: finding {finding['slug']!r} lost its body "
                "past an unescaped heading-shaped line"
            )


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
        else:
            mark_promoted(Path(args.design), slugs=args.slug)
            print(f"promoted {len(args.slug)} finding(s) in {args.design}")
    except (DesignWriteError, DesignParseError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
