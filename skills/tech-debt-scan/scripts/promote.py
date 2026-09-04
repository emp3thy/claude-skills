"""Orchestrate /tech-debt-promote: parse -> emit bundles -> mark promoted.

Stage 0 (the whole command) of /tech-debt-promote. A thin glue layer over the
already-tested sub-modules:

  1. ``design_parser.parse_design`` reads the user-edited design.md.
  2. ``bundle_writer.write_bundle`` materialises one PBI bundle per *approved*
     finding under ``out_root``.
  3. ``design_writer.mark_promoted`` flips those findings ``approved -> promoted``
     in the design.md so a re-run is a no-op.

The orchestrator holds no parsing or rendering logic of its own; everything it
does is covered by the sub-modules' own tests. It only decides *which* findings
to act on and tallies the outcome.

Counters are kept separate (per [[852f5ae9]]): ``emitted_count`` (bundles
written this run), ``already_promoted_count`` (findings already ``promoted`` on
disk, i.e. a prior run handled them), ``rejected_count``, ``accepted_count``
(deliberate deferrals, spec 4.12; never reported as pending) and
``pending_count``. "No-op because already promoted" is never conflated with
"no-op because nothing was approved".

Roll-forward on partial failure: if N of M approved findings have their bundles
written and bundle N+1 fails, the N succeeded bundles persist and the design.md
is marked ``promoted`` for those N only; the rest stay ``approved`` for a later
run. Exit code 4 signals the partial failure.

Exit codes: 0 success, 2 parse / mark-promoted error, 4 bundle-write failure
after at least one success.

Phase 1 is single-user: do not run two promotes against the same design.md
concurrently (no file locking).

Direct-path invocable (no package imports): `python promote.py <design.md> ...`.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from bundle_writer import BundleWriteError, write_bundle
from design_parser import DesignParseError, parse_design
from design_writer import DesignWriteError, mark_promoted


@dataclass(slots=True)
class PromoteResult:
    emitted_count: int = 0
    already_promoted_count: int = 0
    rejected_count: int = 0
    accepted_count: int = 0
    pending_count: int = 0
    dry_run_skipped: bool = False
    exit_code: int = 0
    emitted_paths: list[Path] = field(default_factory=list)


def run_promote(
    design_path: Path,
    *,
    out_root: Path,
    force: bool = False,
    date: str | None = None,
) -> PromoteResult:
    """Parse ``design_path``, emit a bundle per approved finding, mark promoted.

    Returns a PromoteResult tallying the outcome. Never raises for an expected
    failure mode (parse error, bundle-write error) — those surface as a non-zero
    ``exit_code`` with a message on stderr.
    """
    scan_date = datetime.now(UTC).strftime("%Y-%m-%d") if date is None else date

    try:
        parsed = parse_design(design_path)
    except DesignParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return PromoteResult(exit_code=2)

    result = PromoteResult()
    promoted_slugs: list[str] = []

    for finding in parsed["findings"]:
        status = finding["status"]
        if status == "approved":
            try:
                path = write_bundle(
                    finding,
                    out_root=out_root,
                    source_design=str(design_path),
                    date=scan_date,
                    force=force,
                )
            except BundleWriteError as exc:
                # A pre-existing bundle means a prior run already emitted it;
                # treat as already-promoted rather than a hard failure.
                if "already exists" in str(exc):
                    result.already_promoted_count += 1
                    continue
                print(f"error: {exc}", file=sys.stderr)
                result.exit_code = 4
                break
            result.emitted_paths.append(path)
            result.emitted_count += 1
            promoted_slugs.append(finding["slug"])
        elif status == "promoted":
            result.already_promoted_count += 1
        elif status == "rejected":
            result.rejected_count += 1
        elif status == "accepted":
            result.accepted_count += 1
        else:  # pending
            result.pending_count += 1

    if promoted_slugs:
        try:
            mark_promoted(design_path, slugs=promoted_slugs)
        except DesignWriteError as exc:
            print(f"error: {exc}", file=sys.stderr)
            result.exit_code = 2

    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert approved tech-debt findings into ralph PBI bundles"
    )
    parser.add_argument("design", type=Path, help="path to the edited design.md")
    parser.add_argument(
        "--out", type=Path, default=Path("./tech-debt-pbis"), help="bundle output dir"
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing bundles")
    args = parser.parse_args(argv)

    result = run_promote(args.design, out_root=args.out, force=args.force)
    print(
        f"emitted: {result.emitted_count}, "
        f"already-promoted: {result.already_promoted_count}, "
        f"rejected: {result.rejected_count}, "
        f"accepted: {result.accepted_count}, "
        f"pending: {result.pending_count}"
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(_main())
