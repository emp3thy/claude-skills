"""Orchestrate /tech-debt-promote: select one approved finding -> seed a design session.

Stage 0 (the whole command) of /tech-debt-promote. A thin glue layer over the
already-tested sub-modules:

  1. ``design_parser.parse_design`` reads the user-edited design.md.
  2. ``evidence_doc.render_evidence`` renders the evidence document for the
     one finding the user selects.
  3. ``design_writer.mark_promoted`` flips that finding ``approved -> promoted``
     in the design.md so a re-run is a no-op.

The orchestrator holds no parsing or rendering logic of its own; everything it
does is covered by the sub-modules' own tests.

Three modes; at least one is required. ``--list-approved`` prints the
approved findings (most severe first) as JSON, read-only, and cannot be
combined with --baseline. ``--select SLUG`` renders ``evidence.md`` beside
design.md for that finding and marks it promoted. ``--baseline PATH`` given
alone (neither of the above) is record-only: it records every finding's
current decision into the baseline and exits, writing no ``evidence.md`` and
marking nothing -- the spec's step 2, split out from --select's step 6 so a
review session that approves nothing still gets its rejections and
acceptances recorded. ``--baseline`` may also be combined with --select
(unchanged: the write-back then runs after the mark, capturing that
mutation).

Exit codes: 0 success; 2 no mode given, a parse error, an unknown/non-selectable
slug, an evidence-write failure, or a v1 design.md given with --baseline; 6
(EXIT_WRITE_BACK) when the baseline write-back failed -- either the
record-only run, or (after --select) once evidence.md was already written and
design.md already marked. A v2 design.md finding's ``status`` is one of
``pending``, ``approved``, ``rejected``, ``accepted`` (a deliberate deferral,
spec 4.12) or ``promoted``; only ``approved`` (or, for a re-run, ``promoted``)
findings are selectable.

With --baseline, every finding's edited status is written back to the
baseline (baseline.record): record-only reads design.md as it stands on
disk; combined with --select, the re-parsed design.md's decisions --
reflecting ``select``'s own mark-promoted mutation -- are written instead.
Either way the decisions are written together with their matching
``verified.json`` findings, and baseline.ensure_gitignore_triple then appends
the tracked-baseline gitignore triple when the baseline is ignored. A v1
design.md carries no fingerprints, so --baseline refuses it (exit 2) before
anything is written -- a baseline without fingerprints is worse than none. A
v2 document with no findings at all is not refused.

Phase 1 is single-user: do not run two promotes against the same design.md
concurrently (no file locking).

Direct-path invocable (no package imports): `python promote.py <design.md> ...`.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import baseline
from baseline import BaselineError
from design_parser import DesignParseError, parse_design
from design_writer import DesignWriteError, mark_promoted
from evidence_doc import evidence_locations, render_evidence

# Returned by _main when the baseline write-back failed: either a record-only
# run (--baseline given alone), or --select's own write-back, which runs
# after evidence.md was already written and design.md was already marked
# promoted -- both of those persist -- so exit 6 means only the baseline
# write-back failed, and the command is re-runnable (SELECTABLE includes
# "promoted" for exactly this case).
EXIT_WRITE_BACK: Final[int] = 6


def _repo_root_for_baseline(baseline_path: Path) -> Path:
    """The repository root that owns ``baseline_path``, for the gitignore triple.

    Never derived from the process's cwd. SKILL.md documents running every
    script command from the skill's own ``skills/tech-debt-scan/`` directory,
    which is generally unrelated to ``<repo>`` (the scanned repo) -- and a cwd
    inside a subdirectory of the scanned repo is a *descendant* of the repo
    root, not an ancestor of ``.tech-debt/`` (a sibling of that subdirectory).
    ``Path.cwd()`` is an ancestor of ``--baseline``'s path in neither case, so
    ``ensure_gitignore_triple``'s ``Path.relative_to`` raised an uncaught
    ``ValueError`` for both -- ``root`` must instead be derived from
    ``baseline_path`` itself, which is immune to both failure modes.

    Asks git for the repository containing ``baseline_path``'s own directory;
    falls back to ``baseline_path.parent.parent`` (SKILL.md's
    ``<repo>/.tech-debt/baseline.json`` layout) when git is absent or that
    directory is not inside a git repository.
    """
    parent = baseline_path.resolve().parent
    if shutil.which("git") is not None:
        proc = subprocess.run(
            ["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return Path(proc.stdout.strip())
    return baseline_path.resolve().parent.parent


def _read_json_object(path: Path) -> dict[str, Any]:
    """The JSON object at ``path``, or {} when it is absent or not an object."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_bytes())
    return raw if isinstance(raw, dict) else {}


def _write_back(design_path: Path, baseline_path: Path, today: str) -> str:
    """Record every decision in ``design_path`` into the baseline; return the outcome.

    Re-parses ``design_path`` so the decisions reflect ``select``'s own
    mark-promoted mutation, and reads the matching ``verified.json`` and
    ``ranked.json`` (preset defaults to "balanced" when ranked.json or its
    preset key is absent) from the design's own directory.

    Raises BaselineError, DesignParseError, ValueError or OSError on any
    failure -- the caller turns each into EXIT_WRITE_BACK. ``root`` for the
    gitignore triple is derived from ``baseline_path`` itself, never from the
    process's cwd.
    """
    decisions = parse_design(design_path)["findings"]
    verified = _read_json_object(design_path.parent / "verified.json")
    findings = verified.get("findings") or []
    ranked = _read_json_object(design_path.parent / "ranked.json")
    preset = str(ranked.get("preset") or "balanced")

    baseline.record(
        baseline_path,
        decisions=decisions,
        findings=findings,
        today=today,
        preset=preset,
    )
    return baseline.ensure_gitignore_triple(_repo_root_for_baseline(baseline_path), baseline_path)


def _run_write_back(design_path: Path, baseline_path: Path) -> int:
    """Run the baseline write-back and print its outcome; return the exit code.

    Shared by the record-only mode (--baseline given alone) and --select's
    own post-mark write-back (--select combined with --baseline) -- both call
    _write_back the same way and report the same three outcomes.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        outcome = _write_back(design_path, baseline_path, today)
    except (BaselineError, DesignParseError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_WRITE_BACK
    print(f"wrote {baseline_path}")
    if outcome == "appended":
        print("appended the gitignore triple")
    elif outcome == "still-ignored":
        print(
            "appended the gitignore triple, but the baseline is still ignored; "
            "an ancestor directory is ignored and must be un-ignored by hand"
        )
    return 0


# design.md statuses `--select` accepts. `promoted` is included so a failed
# baseline write, or a second design session on the same finding, can be
# re-run; `--list-approved` still offers only `approved`, so a re-run is
# always deliberate rather than suggested.
SELECTABLE: Final[frozenset[str]] = frozenset({"approved", "promoted"})


class SelectionError(Exception):
    """Raised when the requested slug is unknown or not selectable."""


def _severity(finding: dict[str, Any]) -> int:
    try:
        return int(finding["severity"])
    except (KeyError, TypeError, ValueError):
        return 0


def _priority(finding: dict[str, Any]) -> float:
    try:
        return float(finding.get("priority") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def list_approved(design_path: Path) -> list[dict[str, Any]]:
    """The `approved` findings in ``design_path``, most severe first.

    Ordered by severity then priority, both descending, so the row the user is
    most likely to pick is first. Read-only: nothing is written and no status
    changes.
    """
    findings = parse_design(design_path)["findings"]
    approved = [f for f in findings if f.get("status") == "approved"]
    approved.sort(key=lambda f: (-_severity(f), -_priority(f)))
    rows: list[dict[str, Any]] = []
    for finding in approved:
        locations = evidence_locations(str(finding.get("body_md") or ""))
        rows.append({
            "slug": finding["slug"],
            "title": finding["title"],
            "family": finding.get("family") or finding["category"],
            "severity": _severity(finding),
            "effort": finding.get("effort"),
            "primary_file": locations[0][0] if locations else None,
            "fingerprint": finding.get("fingerprint"),
        })
    return rows


def select(design_path: Path, slug: str) -> Path:
    """Write ``evidence.md`` for ``slug`` and mark it promoted; return the path.

    Writes beside ``design_path`` (the workdir), overwriting any previous
    evidence document: it seeds one design session and is always re-derivable.
    The design.md mark happens after the write, so a failed render never
    consumes the finding. If the write succeeds but ``mark_promoted`` then
    raises (e.g. a permission error), the finding's status is left
    ``approved`` -- a retry re-renders and re-attempts the mark cleanly -- and
    the failure is re-raised as SelectionError naming the evidence path
    already on disk, so the caller is never told the mark failed without
    knowing evidence.md exists.
    """
    parsed = parse_design(design_path)
    finding = next((f for f in parsed["findings"] if f.get("slug") == slug), None)
    if finding is None:
        raise SelectionError(f"unknown slug: {slug}")
    status = str(finding.get("status", ""))
    if status not in SELECTABLE:
        raise SelectionError(f"{slug} is {status}, not approved")

    candidates = _read_json_object(design_path.parent / "candidates.json")
    text = render_evidence(
        finding,
        metadata=parsed["metadata"],
        open_questions=candidates.get("open_questions") or [],
        looks_bad_but_fine=candidates.get("looks_bad_but_fine") or [],
    )
    out_path = design_path.parent / "evidence.md"
    out_path.write_bytes(text.encode("utf-8"))

    if status == "approved":
        try:
            mark_promoted(design_path, slugs=[slug])
        except DesignWriteError as exc:
            raise SelectionError(
                f"wrote {out_path} but could not mark {slug!r} promoted: {exc}"
            ) from exc
    return out_path


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select one approved tech-debt finding and seed a design session"
    )
    parser.add_argument("design", type=Path, help="path to the edited design.md")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--list-approved", action="store_true",
        help="print the approved findings as JSON and exit",
    )
    group.add_argument("--select", metavar="SLUG", help="write evidence.md for this finding")
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help=(
            "record every finding's decision into this baseline. Given alone "
            "(no --list-approved or --select), records every decision and "
            "exits without writing evidence.md or marking anything; combined "
            "with --select, records after the mark"
        ),
    )
    args = parser.parse_args(argv)

    if not args.list_approved and args.select is None and args.baseline is None:
        parser.error(
            "choose one of --list-approved, --select SLUG, or --baseline PATH "
            "(given alone, to record every decision without selecting)"
        )
    if args.list_approved and args.baseline is not None:
        parser.error("--list-approved is read-only; it cannot be combined with --baseline")

    try:
        parsed = parse_design(args.design)
    except DesignParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_approved:
        try:
            rows = list_approved(args.design)
        except DesignParseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(rows, indent=2))
        return 0

    # A v1 design.md carries no fingerprints; refuse before anything is written,
    # since a baseline without fingerprints is worse than none. A document with
    # no findings answers the same way and is not a v1 document.
    if args.baseline is not None and parsed["findings"] and not any(
        f.get("fingerprint") for f in parsed["findings"]
    ):
        print(
            f"error: {args.design} has no fingerprints (a v1 design.md); "
            "refusing to write a baseline without them",
            file=sys.stderr,
        )
        return 2

    if args.select is None:
        # --baseline given alone: the checks above guarantee it is set here.
        # Record every finding's current decision and exit -- nothing is
        # selected, so evidence.md is not written and no finding's status
        # changes.
        return _run_write_back(args.design, args.baseline)

    try:
        written = select(args.design, args.select)
    except (DesignParseError, SelectionError, DesignWriteError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {written}")

    if args.baseline is not None:
        return _run_write_back(args.design, args.baseline)

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
