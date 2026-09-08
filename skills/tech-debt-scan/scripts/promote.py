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

Exit codes: 0 success, 2 parse / mark-promoted error, or a v1 design.md given
with --baseline; 4 bundle-write failure after at least one success; 6
(EXIT_WRITE_BACK) when --baseline was given and the write-back to the
baseline failed after bundles were already emitted. A v2 design.md finding's
``status`` is one of ``pending``, ``approved``, ``rejected``, ``accepted`` (a
deliberate deferral, spec 4.12) or ``promoted``; only ``approved`` findings
are emitted here, and every other status is only tallied.

With --baseline, every finding's edited status is written back to the
baseline (baseline.record) after bundles are emitted: each finding emitted
this run is recorded ``promoted`` with its bundle directory (PromoteResult
.emitted), and a finding whose design.md already read ``promoted`` before
this run has its existing bundle directory looked up on disk under out_root
(PromoteResult.already_promoted) so a decision recorded before --baseline
existed does not make record() raise. baseline.ensure_gitignore_triple then
appends the tracked-baseline gitignore triple when the baseline is ignored.
A v1 design.md carries no fingerprints, so --baseline refuses it (exit 2)
before anything is emitted -- a baseline without fingerprints is worse than
none. A v2 document with no findings at all is not refused: nothing is
emitted and nothing is recorded, exit 0.

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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import baseline
from baseline import BaselineError
from bundle_writer import BundleWriteError, write_bundle
from design_parser import DesignParseError, parse_design
from design_writer import DesignWriteError, mark_promoted

# Returned by _main when --baseline was given and baseline.record raised
# after bundles were already written this run: the bundles on disk and the
# design.md mark-promoted mutation from run_promote both persist -- only the
# write-back to the baseline itself failed, so a write-back failure is never
# mistaken for a promote failure (which returns 2 or 4).
EXIT_WRITE_BACK: Final[int] = 6


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
    # Fingerprint -> bundle directory, for findings emitted (and marked
    # promoted) this run. Keyed by fingerprint rather than derived from
    # emitted_paths so a --baseline write-back never has to re-derive a
    # fingerprint by parsing a slug back out of a directory name.
    emitted: dict[str, Path] = field(default_factory=dict)
    # Fingerprint -> bundle directory, for findings whose design.md status
    # already read "promoted" going into this run (a prior run emitted them),
    # confirmed to still exist on disk under out_root. Lets a --baseline
    # write-back record a bundle for a finding promoted before --baseline
    # existed, which has no entry in `emitted` and no prior baseline history.
    already_promoted: dict[str, Path] = field(default_factory=dict)


def _existing_bundle_dir(out_root: Path, slug: str) -> Path | None:
    """The bundle directory already on disk for ``slug``, at any date, if any.

    A finding already marked ``promoted`` in design.md was bundled on some
    earlier run, possibly on a different date than this run's ``date``, so
    the lookup globs on the slug alone rather than reconstructing today's
    ``chore-<slug>-<date>`` id. When two dated directories exist for the same
    slug (an earlier promote, then a later regeneration that left the old
    directory on disk), the newest by name wins -- the ``YYYY-MM-DD`` date
    suffix sorts lexically, so the last name in sorted order is the most
    recent. ``_write_back`` layers a further preference on top of this
    pick: the baseline's own previously recorded bundle beats it whenever
    that directory still exists (Ruling 2).
    """
    if not out_root.is_dir():
        return None
    matches = sorted(p for p in out_root.glob(f"chore-{slug}-*") if p.is_dir())
    return matches[-1] if matches else None


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
        fingerprint: str | None = finding.get("fingerprint")
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
            if fingerprint:
                result.emitted[fingerprint] = path
            promoted_slugs.append(finding["slug"])
        elif status == "promoted":
            result.already_promoted_count += 1
            if fingerprint:
                existing = _existing_bundle_dir(out_root, finding["slug"])
                if existing is not None:
                    result.already_promoted[fingerprint] = existing
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


def _read_json_object(path: Path) -> dict[str, Any]:
    """The JSON object at ``path``, or {} when it is absent or not an object."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_bytes())
    return raw if isinstance(raw, dict) else {}


def _write_back(
    design_path: Path,
    baseline_path: Path,
    result: PromoteResult,
    today: str,
    *,
    out_root: Path,
) -> str:
    """Record every decision in ``design_path`` into the baseline; return the outcome.

    Re-parses ``design_path`` so the decisions reflect run_promote's own
    mark-promoted mutation, reads the matching ``verified.json`` and
    ``ranked.json`` (Ruling 1: preset defaults to "balanced" when ranked.json
    or its preset key is absent) from the design's own directory, and maps
    ``already_promoted`` and ``emitted`` bundle directories (by name, not
    path) into baseline.record's ``bundles`` argument (Ruling 2 and Ruling 3).
    An ``already_promoted`` fingerprint prefers the bundle the *previous*
    baseline already recorded for it over the fresh (possibly ambiguous, see
    ``_existing_bundle_dir``) glob pick, whenever that directory still exists
    on disk under ``out_root`` (Ruling 2); an ``emitted`` fingerprint always
    uses this run's own fresh bundle, since a bundle just written has no
    ambiguity to resolve.

    Raises BaselineError, DesignParseError (the re-parse can fail on a
    document edited between the two parses), ValueError (includes
    json.JSONDecodeError, e.g. a malformed verified.json/ranked.json) or
    OSError on any failure -- the caller (_main) turns each into
    EXIT_WRITE_BACK. ``root`` for the
    gitignore triple is derived from ``baseline_path`` itself
    (``_repo_root_for_baseline``), never from the process's cwd.
    """
    decisions = parse_design(design_path)["findings"]
    verified = _read_json_object(design_path.parent / "verified.json")
    findings = verified.get("findings") or []
    ranked = _read_json_object(design_path.parent / "ranked.json")
    preset = str(ranked.get("preset") or "balanced")

    prior = baseline.load_baseline(baseline_path)
    prior_findings: dict[str, Any] = prior["findings"] if prior else {}

    bundles: dict[str, str] = {}
    for fp, path in result.already_promoted.items():
        prior_bundle = prior_findings.get(fp, {}).get("bundle")
        if prior_bundle and (out_root / prior_bundle).is_dir():
            bundles[fp] = prior_bundle
        else:
            bundles[fp] = path.name
    for fp, path in result.emitted.items():
        bundles[fp] = path.name

    baseline.record(
        baseline_path,
        decisions=decisions,
        findings=findings,
        bundles=bundles,
        today=today,
        preset=preset,
    )
    return baseline.ensure_gitignore_triple(_repo_root_for_baseline(baseline_path), baseline_path)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert approved tech-debt findings into ralph PBI bundles"
    )
    parser.add_argument("design", type=Path, help="path to the edited design.md")
    parser.add_argument(
        "--out", type=Path, default=Path("./tech-debt-pbis"), help="bundle output dir"
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing bundles")
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help="write every finding's decision back into this baseline after promoting",
    )
    args = parser.parse_args(argv)

    # A v1 design.md carries no fingerprints; refuse before run_promote emits
    # anything, since a baseline without fingerprints is worse than none. A
    # document with no findings at all answers that question the same way and
    # is not a v1 document: a scan that found nothing promotes normally,
    # emitting and recording nothing.
    if args.baseline is not None:
        try:
            precheck = parse_design(args.design)
        except DesignParseError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if precheck["findings"] and not any(f.get("fingerprint") for f in precheck["findings"]):
            print(
                f"error: {args.design} has no fingerprints (a v1 design.md); "
                "refusing to write a baseline without them",
                file=sys.stderr,
            )
            return 2

    # Computed once here (rather than left to run_promote's own default) so
    # the write-back's `today` -- the bundle directory's date and the
    # baseline's last_seen -- always agree with what run_promote actually used.
    scan_date = datetime.now(UTC).strftime("%Y-%m-%d")
    result = run_promote(args.design, out_root=args.out, force=args.force, date=scan_date)
    print(
        f"emitted: {result.emitted_count}, "
        f"already-promoted: {result.already_promoted_count}, "
        f"rejected: {result.rejected_count}, "
        f"accepted: {result.accepted_count}, "
        f"pending: {result.pending_count}"
    )

    if args.baseline is not None and result.exit_code == 0:
        try:
            outcome = _write_back(
                args.design, args.baseline, result, scan_date, out_root=args.out
            )
        except (BaselineError, DesignParseError, ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_WRITE_BACK
        print(f"wrote {args.baseline}")
        if outcome == "appended":
            print("appended the gitignore triple")
        elif outcome == "still-ignored":
            print(
                "appended the gitignore triple, but the baseline is still ignored; "
                "an ancestor directory is ignored and must be un-ignored by hand"
            )

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(_main())
