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

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from config import ConfigError, load_config
from evidence import find_quote
from inventory import write_json

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
            line if isinstance(line, int) and not isinstance(line, bool) else None)


def _until_is_malformed(entry: dict[str, Any]) -> bool:
    """True when `until` is present but not a parseable ISO date."""
    until = entry.get("until")
    if until is None:
        return False
    if isinstance(until, str):
        try:
            date.fromisoformat(until)
            return False
        except ValueError:
            return True
    return True


def _expired(entry: dict[str, Any], today: str) -> bool:
    """True when `until` has passed, or is present but malformed.

    A missing `until` (None) means "no expiry" and is never expired. A
    malformed `until` fails safe -- treated as expired so the finding
    returns and `classify` can say why, rather than suppressing silently
    forever.
    """
    until = entry.get("until")
    if until is None:
        return False
    if isinstance(until, str):
        try:
            return date.fromisoformat(until) < date.fromisoformat(today)
        except ValueError:
            pass
    return True


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
    """The fingerprint of a baseline entry this finding is an edit of, if any.

    Requires an integer line on both sides. A finding whose primary evidence
    has no ``line_start`` (an osv-scanner advisory, spec 4.6, always has
    none), or a baseline entry whose recorded ``line_start`` is not an
    integer, can never match here: the heuristic exists for code that moved
    or was retitled near its old location, and a manifest-level fact has no
    "near" to check. Such findings fall through to fingerprint matching, or
    NEW, instead of matching on title overlap alone at any distance.
    """
    if not isinstance(line, int):
        return None
    wanted = title_tokens(str(finding.get("title", "")))
    family = finding.get("family")
    best: tuple[int, str] | None = None
    for fp, entry in baseline["findings"].items():
        if entry.get("family") != family or entry.get("file") != file:
            continue
        base_line = entry.get("line_start")
        if not isinstance(base_line, int) or abs(base_line - line) > EDIT_WINDOW:
            continue
        base_tokens = title_tokens(str(entry.get("title", "")))
        shared = len(wanted & base_tokens)
        if base_tokens and shared * 2 >= len(base_tokens):
            distance = abs(base_line - line)
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
            note = "until is not a date" if _until_is_malformed(entry) else "acceptance expired"
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


def _resolved(entry: dict[str, Any], root: Path) -> tuple[bool, str | None]:
    """Whether an unmatched baseline entry's debt is gone, and why.

    Spec 4.10's baseline schema lists ``quote_hash`` only, but a hash cannot be
    searched for; ``record`` (Task 3) writes an optional ``quote`` alongside it
    so RESOLVED has text to look for. Resolving means the code that carried
    the debt is gone, not that we simply cannot look: an entry with no usable
    quote is resolved only when its file is absent or is now a directory;
    otherwise it stays open, with ``note`` saying why, so a suppressed entry
    never loses its suppression just because a scan failed to reproduce its
    fingerprint.
    """
    file = entry.get("file")
    if not isinstance(file, str):
        return True, "file unknown"
    path = root / file
    if path.is_dir():
        return True, "file is a directory"
    if not path.is_file():
        return True, "file absent"
    quote = entry.get("quote")
    if not isinstance(quote, str) or not quote:
        return False, "quote unavailable"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return True, "file unreadable"
    line = entry.get("line_start") if isinstance(entry.get("line_start"), int) else None
    return find_quote(lines, quote, line, line) is None, None


def diff(
    verified: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> dict[str, Any]:
    """The ``diff.json`` document of spec 4.10.

    Every current finding is classified against the baseline; every baseline
    entry no finding matched is checked on disk and marked RESOLVED when its
    quote or its file is gone. A suppressed finding (``rejected`` or an
    unexpired ``accepted``) is listed under ``suppressed`` instead of statused,
    so it never appears twice. An expired acceptance is counted under
    ``expired`` whether its ``until`` passed cleanly or was malformed --
    ``classify`` returns the finding either way, for the same underlying
    reason, so both notes (``acceptance expired`` and ``until is not a date``)
    count there.
    """
    status: dict[str, dict[str, Any]] = {}
    suppressed: list[dict[str, Any]] = []
    counts = {"new": 0, "unchanged": 0, "moved": 0, "edited": 0,
              "resolved": 0, "suppressed": 0, "expired": 0}
    matched: set[str] = set()
    for finding in verified.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        fp = str(finding.get("fingerprint", ""))
        out = classify(finding, baseline, root, today)
        if out.matched:
            matched.add(out.matched)
        if out.suppressed_as:
            entry = baseline["findings"][out.matched] if baseline and out.matched else {}
            suppressed.append({"fingerprint": fp, "status": out.suppressed_as,
                               "reason": entry.get("reason") or ""})
            counts["suppressed"] += 1
            continue
        status[fp] = {"diff": out.diff, "note": out.note, "matched": out.matched}
        if out.note in ("acceptance expired", "until is not a date"):
            counts["expired"] += 1
        counts[{"NEW": "new", "UNCHANGED": "unchanged", "UNCHANGED (moved)": "moved",
                "UNCHANGED (edited)": "edited"}[out.diff]] += 1
    if baseline is not None:
        for fp, entry in baseline["findings"].items():
            if fp in matched:
                continue
            gone, note = _resolved(entry, root)
            if gone:
                status[fp] = {"diff": "RESOLVED", "note": note, "matched": None}
                counts["resolved"] += 1
    return {"schema_version": SCHEMA_VERSION, "baseline_found": baseline is not None,
            "status": status, "suppressed": suppressed, "counts": counts}


def _run_diff(args: argparse.Namespace) -> int:
    root = Path(args.root)
    workdir = Path(args.workdir)
    verified_path = workdir / "verified.json"
    if not verified_path.is_file():
        print(f"error: {verified_path} not found; run the chain first", file=sys.stderr)
        return 2
    try:
        verified = json.loads(verified_path.read_bytes())
        if not isinstance(verified, dict):
            raise ValueError(f"{verified_path} is not a JSON object")
        baseline_path = (
            Path(args.baseline) if args.baseline
            else root / str(load_config(root)["baseline"])
        )
        baseline = load_baseline(baseline_path)
    except (BaselineError, ConfigError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    today = args.today or date.today().isoformat()
    doc = diff(verified, baseline, root, today)
    write_json(workdir / "diff.json", doc)
    print(f"wrote {workdir / 'diff.json'}; counts: {doc['counts']}")
    return 0


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="The baseline: classify verified findings, diff, and record (spec 4.10)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_diff = sub.add_parser("diff", help="classify verified.json against the baseline")
    p_diff.add_argument("--workdir", default=".tech-debt", help="directory holding verified.json")
    p_diff.add_argument("--root", default=".", help="repository root the baseline is relative to")
    p_diff.add_argument(
        "--baseline", default=None,
        help="baseline path (default: config's baseline, resolved against --root)",
    )
    p_diff.add_argument("--today", default=None, help="ISO date (default: today)")

    args = parser.parse_args(argv)
    if args.cmd == "diff":
        return _run_diff(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
