"""Render one approved design.md finding as evidence.md, the seed for a design session.

``/tech-debt-promote`` selects a single finding and materialises it here as a
standalone document a brainstorming session reads. Everything from ``### Proof``
through ``### Acceptance criteria`` is the finding's own ``body_md``, copied
verbatim: what the verifier confirmed is what the brainstorm reads.

Two sections are added from the scan's own negative space. ``open_questions``
and ``looks_bad_but_fine`` are anchored to ``file`` and ``line_start``, never to
a fingerprint, so matching them to a finding is a heuristic: an entry matches
when its file is one of the files the finding cites, and matched entries are
ordered by distance from the finding's first cited line. Neither section is
rendered when nothing matches.

Pure: no filesystem access, no imports from the rest of the chain. Direct-path
invocable is not needed -- ``promote.py`` is the only caller.
"""
from __future__ import annotations

import re
from typing import Any, Final

# design_writer's _evidence_item renders three citation shapes (design_writer.py:662-687):
# ``- `path:start-end` `` (or ``- `path:start` `` for a one-line span), the
# whole-file ``- `path` (whole file) `` when either bound is null, and the
# repository-level ``- repository-level finding (no file or line range)``
# when there is no file at all. The first two both name a file inside
# backticks, so both match here; the third names no file and is deliberately
# left unmatched. The colon-and-digits group is optional so a whole-file
# citation still matches, with no line captured for it.
_EVIDENCE_LINE: Final[re.Pattern[str]] = re.compile(
    r"^- `([^`]+?)(?::(\d+)(?:-\d+)?)?`(?: \(whole file\))?\s*$", re.MULTILINE
)
_ABSENT: Final[str] = "-"
_QUESTIONS_HEADING: Final[str] = "### Open questions from the scan"
_RULED_OUT_HEADING: Final[str] = "### Already ruled out"


def evidence_locations(body_md: str) -> list[tuple[str, int | None]]:
    """Every ``(file, line)`` the finding's body cites, in order.

    ``line`` is ``None`` for a whole-file citation: there is no line to
    report, and ``0`` would be a lie that downstream code could mistake for a
    real anchor.
    """
    return [
        (match.group(1), int(match.group(2)) if match.group(2) is not None else None)
        for match in _EVIDENCE_LINE.finditer(body_md)
    ]


def _field(finding: dict[str, Any], key: str) -> str:
    value = finding.get(key)
    return _ABSENT if value is None or value == "" else str(value)


def _matched(
    entries: list[dict[str, Any]], files: set[str], anchor: int | None
) -> list[dict[str, Any]]:
    """``entries`` whose file the finding cites, nearest the anchor line first.

    ``sorted`` is stable, so entries equidistant from the anchor -- and every
    entry when there is no anchor -- keep their input order.
    """
    hits = [entry for entry in entries if str(entry.get("file") or "") in files]
    if anchor is None:
        return hits
    return sorted(hits, key=lambda entry: abs(int(entry.get("line_start") or 0) - anchor))


def render_evidence(
    finding: dict[str, Any],
    *,
    metadata: dict[str, Any],
    open_questions: list[dict[str, Any]],
    looks_bad_but_fine: list[dict[str, Any]],
) -> str:
    """The evidence.md text for ``finding``; LF-only, one trailing newline."""
    locations = evidence_locations(str(finding.get("body_md") or ""))
    files = {file for file, _ in locations}
    anchor = next((line for _, line in locations if line is not None), None)

    parts: list[str] = [
        f"# {finding.get('title') or ''}",
        "",
        f"Repository: {metadata.get('root') or _ABSENT}",
        f"Scan: {metadata.get('scan_date') or _ABSENT} "
        f"(preset {metadata.get('preset') or _ABSENT})",
        f"Finding: {_field(finding, 'fingerprint')} | "
        f"{finding.get('family') or finding.get('category') or _ABSENT} "
        f"| {_field(finding, 'type_id')} | {_field(finding, 'debt_type')}",
        f"Tier {_field(finding, 'tier')} | severity {_field(finding, 'severity')} "
        f"| effort {_field(finding, 'effort')} | {_field(finding, 'diff')}",
        "",
        str(finding.get("body_md") or "").strip("\n"),
    ]

    questions = _matched(open_questions, files, anchor)
    if questions:
        parts += ["", _QUESTIONS_HEADING, "", "Ask these before proposing approaches:", ""]
        parts += [
            f"- `{entry.get('file')}:{entry.get('line_start')}` - {entry.get('question')}"
            for entry in questions
        ]

    ruled_out = _matched(looks_bad_but_fine, files, anchor)
    if ruled_out:
        parts += ["", _RULED_OUT_HEADING, "", "A scout examined these and dismissed them:", ""]
        parts += [
            f"- `{entry.get('file')}:{entry.get('line_start')}` - {entry.get('why')}"
            for entry in ruled_out
        ]

    return "\n".join(parts) + "\n"
