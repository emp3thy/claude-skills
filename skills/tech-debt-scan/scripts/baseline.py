"""The baseline: what the last scan found, and what a human decided (spec 4.10).

``diff`` classifies every current finding against the committed baseline --
UNCHANGED, UNCHANGED (moved), UNCHANGED (edited), NEW -- and every baseline
entry no current finding matched as RESOLVED, writing ``diff.json`` for
``design_writer`` to render. ``record`` is called in process by ``promote.py``
and writes each finding's status, reason, expiry and bundle back, so a
``rejected`` finding stops recurring and an ``accepted`` one returns when its
expiry passes.

Three classifications are exact and one is a heuristic. A fingerprint match
is UNCHANGED, or UNCHANGED (moved) when the baseline recorded a different
line -- the fingerprint carries no line, so a quote that moved keeps it. An
edited match is the heuristic: same family and file, within ``EDIT_WINDOW``
lines, a title sharing at least half the baseline title's tokens. It can be
wrong in both directions, so a suppression that rests on it is noted.

The baseline lives inside the ignored workdir and is re-included by three
``.gitignore`` lines appended once by ``record``; see ``ensure_gitignore_triple``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 2
STATUSES: Final[tuple[str, ...]] = ("pending", "approved", "rejected", "accepted", "promoted")
SUPPRESSING: Final[frozenset[str]] = frozenset({"rejected", "accepted"})
EDIT_WINDOW: Final[int] = 40
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class BaselineError(Exception):
    """A baseline that cannot be read or written."""


@dataclass(frozen=True)
class Classification:
    diff: str  # NEW | UNCHANGED | UNCHANGED (moved) | UNCHANGED (edited)
    matched: str | None  # baseline fingerprint, if any
    note: str | None
    suppressed_as: str | None  # "rejected" | "accepted" | None


def load_baseline(path: Path) -> dict[str, Any] | None:
    """The baseline document, or None when the file does not exist."""
    import json

    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise BaselineError(f"{path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        raise BaselineError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("findings"), dict):
        raise BaselineError(f"{path}: findings must be an object")
    return doc


def title_tokens(title: str) -> set[str]:
    """Lower-cased tokens split on non-alphanumerics; stop-words are kept (spec 4.10)."""
    return {t for t in _TOKEN.split(title.lower()) if t}


def _primary(finding: dict[str, Any]) -> tuple[str | None, int | None]:
    evidence = finding.get("evidence") or []
    if not evidence or not isinstance(evidence[0], dict):
        return None, None
    file = evidence[0].get("file")
    line = evidence[0].get("line_start")
    return (file if isinstance(file, str) else None,
            line if isinstance(line, int) else None)


def _expired(entry: dict[str, Any], today: str) -> bool:
    until = entry.get("until")
    if not isinstance(until, str):
        return False
    try:
        return date.fromisoformat(until) < date.fromisoformat(today)
    except ValueError:
        return False


def _suppressed_as(entry: dict[str, Any], today: str) -> str | None:
    status = entry.get("status")
    if status == "rejected":
        return "rejected"
    if status == "accepted" and not _expired(entry, today):
        return "accepted"
    return None


def _edited_match(
    finding: dict[str, Any], baseline: dict[str, Any], file: str, line: int | None
) -> str | None:
    """The fingerprint of a baseline entry this finding is an edit of, if any."""
    wanted = title_tokens(str(finding.get("title", "")))
    family = finding.get("family")
    best: tuple[int, str] | None = None
    for fp, entry in baseline["findings"].items():
        if entry.get("family") != family or entry.get("file") != file:
            continue
        base_line = entry.get("line_start")
        if line is not None and isinstance(base_line, int) and abs(base_line - line) > EDIT_WINDOW:
            continue
        base_tokens = title_tokens(str(entry.get("title", "")))
        shared = len(wanted & base_tokens)
        if base_tokens and shared * 2 >= len(base_tokens):
            distance = abs((base_line or 0) - (line or 0))
            if best is None or distance < best[0]:
                best = (distance, fp)
    return best[1] if best else None


def classify(
    finding: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> Classification:
    """One current finding against the baseline (spec 4.10)."""
    if baseline is None:
        return Classification("NEW", None, None, None)
    fp = str(finding.get("fingerprint", ""))
    file, line = _primary(finding)
    entry = baseline["findings"].get(fp)
    if entry is not None:
        suppressed = _suppressed_as(entry, today)
        note = None
        if entry.get("status") == "accepted" and suppressed is None:
            note = "acceptance expired"
        moved = isinstance(line, int) and isinstance(entry.get("line_start"), int) \
            and entry["line_start"] != line
        return Classification("UNCHANGED (moved)" if moved else "UNCHANGED", fp, note, suppressed)
    if file is not None:
        edited = _edited_match(finding, baseline, file, line)
        if edited is not None:
            entry = baseline["findings"][edited]
            suppressed = _suppressed_as(entry, today)
            note = "suppressed by edited match" if suppressed else None
            return Classification("UNCHANGED (edited)", edited, note, suppressed)
    return Classification("NEW", None, None, None)
