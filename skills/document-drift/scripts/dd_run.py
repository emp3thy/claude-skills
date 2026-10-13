"""The staged driver (spec 2, 3; phase B spec 2, 3): ``start``, ``compose``, ``verify`` and
``finish``.

Usage: ``python scripts/dd_run.py <repo> --stage <start|compose|verify|finish> [--retried]
[--base REF] [--full] [--branch NAME] [--check] [--workdir DIR] [--date YYYY-MM-DD]``.

The workdir defaults to ``<repo>/.document-drift`` and the date to today; the branch defaults
to the config ``branch`` with ``{date}`` replaced by the date. ``start`` records ``base``,
``full``, ``branch``, ``check`` and ``date`` in ``preflight.json`` (``dd_preflight``) and, once
``dd_changes`` has decided the scope, ``run_id`` and ``scope``; the run id is ``<date>-`` plus
the first 4 hex characters of ``sha256("<head>:<scope>:<date>")``. Each stage records its own
name as ``stage`` when it completes. ``compose``, ``verify`` and ``finish`` take every flag
they are not given from that record and refuse (exit 2) one that differs from it, or a stage
run out of order: ``compose`` needs a completed ``start`` (or a ``compose``, which it
repeats), ``verify`` a completed ``start`` (in README mode a ``compose``) or a ``verify``,
which it repeats, ``finish`` a completed ``verify``, or (outside README mode) a ``start`` whose
``plan-docs.json`` is empty.

README mode (phase B spec 2): ``start`` records ``readme`` in ``preflight.json``, true when the
config's ``readme`` is on and no tracked file at the root is ``README.md`` (matched
case-insensitively; an excluded or ignored one counts too), and prints ``readme: yes`` or
``readme: no`` before anything else.

- ``start`` deletes ``preflight.json`` (a refused start leaves no started run), runs preflight
  and, once it passes, deletes every other pinned output (files and the ``review/``,
  ``gaps/``, ``verdicts/``, ``prompts/``, ``sheets/`` and ``readme/`` directories;
  ``last-run.json`` is kept), so a refused start keeps the previous run's files. Then it
  runs inventory, extract, resolve, defindex, anchors, changes, units, patterns, gaps, the
  notice decisions and the dispatch plan, in README mode the areas (``areas.json``) and the
  sheet entries appended to the plan, and prints ``plan-docs.json <path> with <n> entries``.
  Outside README mode, with no in-scope doc it stops after the inventory, writes an empty
  ``plan-docs.json`` and prints the phase B message.
- ``compose`` (README mode only; otherwise it refuses with exit 2) validates the sheet
  outputs with the same exit-3 retry as ``verify``; on the ``--retried`` rerun a sheet short
  only of hints is accepted, and ``dd_sheets`` fills them. It writes ``sheets.json`` and,
  with at least one valid sheet, the writer's ``plan-readme.json`` (printing its line), else
  an empty ``plan-readme.json`` and ``readme: no sheet; nothing to compose``.
- ``verify`` validates the review and gap outputs (in README mode the writer's output too,
  in the same ``retry.json``); without ``--retried`` a missing or invalid output writes
  ``retry.json``, prints ``retry.json <path> with <n> entries`` and exits 3, changing
  nothing else; with it those entries are unchecked. Without ``--retried`` the ranges
  a valid review output reports as ``not_reviewed`` become retry units (``dd_units.retry_units``
  appends them to ``units.json``, ``dd_dispatch.plan_retry`` to ``plan-docs.json``) listed in
  the same ``retry.json``; with it those ranges are listed in ``edits.json`` as not reviewed.
  Then it adds the review agents' ``unverified_blocks`` as notice nominations, runs the script
  checks (``edits.json``, ``plan-verify.json``) and prints ``plan-verify.json <path> with <n>
  entries``.
- ``finish`` validates the verifier outputs the same way, writes ``verdicts.json`` and refuses
  (exit 2) when HEAD is no longer the preflight HEAD (naming both shas; a clean branch switch
  leaves the tree clean) or a file outside the workdir changed since preflight (naming them,
  ``dd_preflight.tree_state``), before anything is applied. Under ``--check`` it writes the
  summary and exits 1 when an edit would apply (kept and accepted, or a kept notice edit),
  else 0; nothing is applied, committed or recorded. Otherwise it applies the edits (with the
  heading-link updates), makes the commits, writes ``last-run.json`` (``head``, ``run_id``,
  ``date``, ``committed``), records the stage as finished and writes the summary, and exits 0.
  After a ``start`` with an empty plan it first runs the script checks, so the notice edits
  ``start`` decided still apply; after a ``start`` that found no doc (outside README mode) it
  only writes the summary.

Each stage prints one line (``start`` the readme line first), or for ``finish`` the summary.
Exit codes: a ``StepError`` exits with its own code and message, except that a step's own
exit 5 is reworded to name the step; a step that does not write its output exits 5 naming the
step and the file; any other exception in a step prints its traceback and exits 5 naming the
step. In apply, commit and the summary after them every exit-5 message adds that docs may
already be edited and the branch may exist, and points to ``git status`` and ``git branch``
(spec 3.3). Ruling R65: an exception anywhere else in a stage also prints its traceback and
exits 5 (with the same pointer at ``finish``).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import shutil
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dd_anchors
import dd_apply
import dd_areas
import dd_changes
import dd_checks
import dd_commit
import dd_defindex
import dd_dispatch
import dd_extract
import dd_gaps
import dd_inventory
import dd_patterns
import dd_preflight
import dd_resolve
import dd_sheets
import dd_summary
import dd_units
import dd_unverified
from dd_common import (
    EXIT_FOUND,
    EXIT_MISSING,
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_RETRY,
    StepError,
    read_json,
    run_git,
    write_json,
)
from dd_config import load_config

STAGES = ("start", "compose", "verify", "finish")
FLAGS = ("base", "full", "branch", "check", "date")
OUTPUTS = (
    "preflight.json", "inventory.json", "tokens.json", "candidates.json", "defindex.json",
    "anchors.json", "changes.json", "units.json", "patterns.json", "gaps.json", "notices.json",
    "plan-docs.json", "retry.json", "edits.json", "plan-verify.json", "verdicts.json",
    "applied.json", "commits.json", "commit-msg-corrections.txt", "commit-msg-additions.txt",
    "summary.md", "areas.json", "sheets.json", "plan-readme.json", "readme.json",
)
OUTPUT_DIRS = ("review", "gaps", "verdicts", "prompts", "sheets", "readme")
NO_DOCS = "no markdown docs in scope; no-docs mode arrives in phase B"
COMPOSE_FIRST = "compose has not run; run --stage compose first"
VERIFY_FIRST = "verify has not run (plan-verify.json is missing); run --stage verify first"
HINT = "; docs may already be edited and the branch may exist: check git status and git branch"


def _date(value: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(f"{value!r} is not a YYYY-MM-DD date")
    return value


def run_id_for(head: str, scope: str, date: str) -> str:
    """``<date>-`` plus the first 4 hex characters of ``sha256("<head>:<scope>:<date>")``."""
    return f"{date}-{hashlib.sha256(f'{head}:{scope}:{date}'.encode()).hexdigest()[:4]}"


def _step(name: str, workdir: Path, outputs: tuple[str, ...], call: Callable[[], Any], *,
          edits_at_risk: bool = False) -> Any:
    """Run one step. A crash, a missing output or the step's own exit-5 StepError becomes an
    exit 5 naming the step (spec 3.3); ``edits_at_risk`` (apply, commit and the summary after
    them) adds where to look, since docs may already be edited. Any other StepError passes
    through with its own code."""
    hint = HINT if edits_at_risk else ""
    try:
        result = call()
    except StepError as exc:
        if exc.code != EXIT_MISSING:
            raise
        raise StepError(f"step {name}: {exc}{hint}", EXIT_MISSING) from exc
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        raise StepError(f"step {name} crashed: {type(exc).__name__}: {exc}{hint}",
                        EXIT_MISSING) from exc
    for out in outputs:
        if not (workdir / out).is_file():
            raise StepError(f"step {name} did not write {workdir / out}{hint}", EXIT_MISSING)
    return result


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(encoding, "replace").decode(encoding))
    sys.stdout.flush()


def _say_plan(workdir: Path, name: str, count: int) -> None:
    _write_stdout(f"{name} {(workdir / name).absolute().as_posix()} with {count} entries\n")


def _clear(workdir: Path, keep: tuple[str, ...] = ()) -> None:
    """Delete every pinned output of an earlier run but ``keep``, so no stale file is read
    again."""
    for name in OUTPUTS:
        if name not in keep:
            (workdir / name).unlink(missing_ok=True)
    for name in OUTPUT_DIRS:
        path = workdir / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _record(workdir: Path, **fields: Any) -> dict[str, Any]:
    """Add ``fields`` to ``preflight.json``; return the whole record."""
    pre: dict[str, Any] = read_json(workdir / "preflight.json")
    pre.update(fields)
    write_json(workdir / "preflight.json", pre)
    return pre


def _no_docs(workdir: Path) -> bool:
    return not read_json(workdir / "inventory.json")["docs"]


def readme_wanted(inventory: dict[str, Any], config: dict[str, Any]) -> bool:
    """Phase B spec 2: the config's ``readme`` is on and no tracked file at the root is
    ``README.md``, matched case-insensitively. An excluded or ``drift-ignore-file`` README
    counts too: the skill may not edit it, so it writes none either; a README elsewhere does
    not count."""
    paths = {*inventory.get("files", []), *inventory["docs"]}
    return bool(config["readme"]) and not any(
        str(path).lower() == "readme.md" for path in paths)


def stage_start(root: Path, workdir: Path, *, base: str | None, full: bool,
                branch: str | None, check: bool, date: str) -> int:
    """Run the ``start`` steps; write ``plan-docs.json`` and print its line."""
    (workdir / "preflight.json").unlink(missing_ok=True)  # a refused start is no started run
    config, warnings = load_config(root)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    branch_name = branch or str(config["branch"]).replace("{date}", date)
    pre = _step("preflight", workdir, ("preflight.json",),
                lambda: dd_preflight.run(root, workdir, branch_name, check, base=base,
                                         full=full, date=date))
    _clear(workdir, keep=("preflight.json",))  # only now: a refused start keeps the last run
    head = str(pre["head"])
    _step("inventory", workdir, ("inventory.json",),
          lambda: dd_inventory.run(root, workdir, config))
    readme = readme_wanted(read_json(workdir / "inventory.json"), config)
    _record(workdir, readme=readme)
    _write_stdout(f"readme: {'yes' if readme else 'no'}\n")
    if not readme and _no_docs(workdir):  # README mode runs every step, docs or not
        mode = _step("changes", workdir, (),
                     lambda: dd_changes.last_run(root, workdir, base, full, head=head))
        scope = str(mode["scope"])
        write_json(workdir / "plan-docs.json", [])
        _record(workdir, run_id=run_id_for(head, scope, date), scope=scope, stage="start")
        _write_stdout(NO_DOCS + "\n")
        return EXIT_OK
    _step("extract", workdir, ("tokens.json",), lambda: dd_extract.run(root, workdir))
    _step("resolve", workdir, ("candidates.json",), lambda: dd_resolve.run(root, workdir))
    _step("defindex", workdir, ("defindex.json",), lambda: dd_defindex.run(root, workdir))
    _step("anchors", workdir, ("anchors.json",), lambda: dd_anchors.run(root, workdir, config))
    changes = _step("changes", workdir, ("changes.json",),
                    lambda: dd_changes.run(root, workdir, config, base, full))
    scope = str(changes["scope"])
    run_id = run_id_for(head, scope, date)
    _record(workdir, run_id=run_id, scope=scope)
    _step("units", workdir, ("units.json",), lambda: dd_units.run(root, workdir, config))
    _step("patterns", workdir, ("patterns.json",), lambda: dd_patterns.run(root, workdir))
    _step("gaps", workdir, ("gaps.json",), lambda: dd_gaps.run(root, workdir, config))
    _step("notices", workdir, ("notices.json",),
          lambda: dd_unverified.run_start(root, workdir, run_id))
    plan = _step("dispatch", workdir, ("plan-docs.json",),
                 lambda: dd_dispatch.plan_docs(root, workdir, config))
    if readme:
        _step("areas", workdir, ("areas.json",), lambda: dd_areas.run(root, workdir, config))
        plan = plan + _step("sheets", workdir, ("plan-docs.json",),
                            lambda: dd_dispatch.plan_sheets(root, workdir, config))
    _record(workdir, stage="start")
    _say_plan(workdir, "plan-docs.json", len(plan))
    return EXIT_OK


def _resume(workdir: Path, given: dict[str, Any]) -> dict[str, Any]:
    """``preflight.json`` of a started run whose recorded flags agree with ``given`` (a flag
    that was not given is None and takes the recorded value)."""
    path = workdir / "preflight.json"
    if not path.is_file():
        raise StepError(f"no run in {workdir}; run --stage start first", EXIT_REFUSED)
    pre: dict[str, Any] = read_json(path)
    for flag in FLAGS:
        value = given.get(flag)
        if value is not None and value != pre.get(flag):
            raise StepError(
                f"--{flag} {value!r} differs from {pre.get(flag)!r}, which start recorded; "
                "give every stage the flags given to start", EXIT_REFUSED)
    if pre.get("stage") == "finish":
        raise StepError("this run is finished; run --stage start for a new one", EXIT_REFUSED)
    if pre.get("stage") not in ("start", "compose", "verify"):
        raise StepError("start did not complete; run --stage start first", EXIT_REFUSED)
    return pre


def _failed(workdir: Path, plan: list[dd_dispatch.PlanEntry], roles: tuple[str, ...], *,
            root: Path | None = None,
            require_hints: bool = True) -> list[dd_dispatch.PlanEntry]:
    """The ``roles`` entries of ``plan`` whose output failed validation; ``root`` and
    ``require_hints`` go to the sheet validator."""
    failed: list[dd_dispatch.PlanEntry] = []
    for role in roles:
        failed += dd_dispatch.check_outputs(workdir, plan, role, root=root,
                                            require_hints=require_hints)[1]
    return failed


def _retry(workdir: Path, entries: list[dd_dispatch.PlanEntry]) -> int:
    dd_dispatch.write_retry(workdir, entries)
    _say_plan(workdir, "retry.json", len(entries))
    return EXIT_RETRY


def _outputs_or_retry(workdir: Path, plan: list[dd_dispatch.PlanEntry],
                      roles: tuple[str, ...], retried: bool, *, root: Path | None = None,
                      require_hints: bool = True) -> frozenset[str] | None:
    """The ids of the ``roles`` entries whose output failed validation; None after writing
    ``retry.json`` when any failed and this is not the ``--retried`` rerun."""
    failed = _failed(workdir, plan, roles, root=root, require_hints=require_hints)
    if failed and not retried:
        _retry(workdir, failed)
        return None
    return frozenset(e["id"] for e in failed)


def stage_compose(root: Path, workdir: Path, *, retried: bool,
                  given: dict[str, Any]) -> int:
    """Validate the sheet outputs, write ``sheets.json`` and the writer's ``plan-readme.json``
    (phase B spec 3, 5.4)."""
    pre = _resume(workdir, given)
    if not pre.get("readme"):
        raise StepError("nothing to compose: this run writes no README", EXIT_REFUSED)
    if pre["stage"] not in ("start", "compose"):
        raise StepError("verify has run, and compose comes before it; run --stage start for a "
                        "new run", EXIT_REFUSED)
    for name, step in (("plan-docs.json", "dispatch"), ("areas.json", "areas")):
        if not (workdir / name).is_file():
            raise StepError(f"step {step} of start did not write {workdir / name}",
                            EXIT_MISSING)
    config, _ = load_config(root)
    plan: list[dd_dispatch.PlanEntry] = read_json(workdir / "plan-docs.json")
    # spec 5.4: a sheet short of hints is retried once; after the retry the script fills them
    found = _outputs_or_retry(workdir, plan, ("sheet",), retried, root=root,
                              require_hints=not retried)
    if found is None:
        return EXIT_RETRY
    failed: frozenset[str] = found
    sheets = _step("sheets", workdir, ("sheets.json",),
                   lambda: dd_sheets.run(root, workdir, config, failed))
    if sheets["sheets"]:
        writer = _step("readme", workdir, ("plan-readme.json",),
                       lambda: dd_dispatch.plan_readme(root, workdir, config))
        _record(workdir, stage="compose")
        _say_plan(workdir, "plan-readme.json", len(writer))
    else:
        write_json(workdir / "plan-readme.json", [])
        _record(workdir, stage="compose")
        _write_stdout("readme: no sheet; nothing to compose\n")
    return EXIT_OK


def stage_verify(root: Path, workdir: Path, *, retried: bool,
                 given: dict[str, Any]) -> int:
    """Validate the review and gap outputs (and in README mode the writer's), run the script
    checks, write ``plan-verify.json``."""
    pre = _resume(workdir, given)
    readme = bool(pre.get("readme"))
    if readme and pre["stage"] == "start":
        raise StepError(COMPOSE_FIRST, EXIT_REFUSED)
    if not (workdir / "plan-docs.json").is_file():
        raise StepError("plan-docs.json is missing; run --stage start first", EXIT_REFUSED)
    if not readme and _no_docs(workdir):
        raise StepError("start found no doc in scope; run --stage finish", EXIT_REFUSED)
    if readme and not (workdir / "plan-readme.json").is_file():
        raise StepError("plan-readme.json is missing; run --stage compose first", EXIT_REFUSED)
    config, _ = load_config(root)
    plan: list[dd_dispatch.PlanEntry] = read_json(workdir / "plan-docs.json")
    writer: list[dd_dispatch.PlanEntry] = (read_json(workdir / "plan-readme.json")
                                           if readme else [])
    bad = _failed(workdir, plan, ("review", "gap")) + _failed(workdir, writer, ("readme",))
    failed = frozenset(e["id"] for e in bad)
    if not retried:
        retry = list(bad)
        pending = dd_dispatch.not_reviewed(workdir, plan, failed)
        if pending:
            units = _step("units", workdir, ("units.json",),
                          lambda: dd_units.retry_units(root, workdir, pending,
                                                       int(config["unit_lines"])))
            retry += _step("dispatch", workdir, ("plan-docs.json",),
                           lambda: dd_dispatch.plan_retry(root, workdir, config, units))
        if retry:
            return _retry(workdir, retry)
    nominations: list[dict[str, Any]] = []
    for entry in plan:
        if entry["role"] == "review" and entry["id"] not in failed:
            nominations += read_json(Path(entry["output"]))["unverified_blocks"]
    run_id = str(pre["run_id"])
    _step("notices", workdir, ("notices.json",),
          lambda: dd_unverified.run_verify(root, workdir, nominations, run_id))
    _step("checks", workdir, ("edits.json", "plan-verify.json"),
          lambda: dd_checks.run(root, workdir, config, failed))
    _record(workdir, stage="verify")
    _say_plan(workdir, "plan-verify.json", len(read_json(workdir / "plan-verify.json")))
    return EXIT_OK


def _tree_check(root: Path, workdir: Path, pre: dict[str, Any]) -> None:
    """Refuse when HEAD moved or a file outside the workdir changed since preflight. A clean
    branch switch leaves the tree clean, so HEAD is compared on its own, before any edit is
    applied (``dd_commit`` checks it again before it creates the branch)."""
    head = (run_git(root, ["rev-parse", "HEAD"]) or "").strip()
    if head != str(pre["head"]):
        raise StepError(f"HEAD moved during the run: start saw {pre['head']}, now it is "
                        f"{head or 'unknown'}; nothing was applied", EXIT_REFUSED)
    then: dict[str, str] = pre.get("dirty") or {}
    now = dd_preflight.tree_state(root, workdir)
    changed = sorted(p for p in {*then, *now} if then.get(p) != now.get(p))
    if changed:
        raise StepError("files outside the workdir changed during the run: "
                        f"{', '.join(changed)}; nothing was applied", EXIT_REFUSED)


def _would_apply(workdir: Path) -> bool:
    """An edit that a run without ``--check`` would apply: kept and accepted, or a kept notice
    edit (no verdict needed)."""
    return bool(dd_apply.selected_edits(read_json(workdir / "edits.json")["edits"],
                                        read_json(workdir / "verdicts.json")["verdicts"]))


def _summary(root: Path, workdir: Path, edits_at_risk: bool = False) -> str:
    return str(_step("summary", workdir, ("summary.md",), lambda: dd_summary.run(workdir, root),
                     edits_at_risk=edits_at_risk))


def stage_finish(root: Path, workdir: Path, *, retried: bool,
                 given: dict[str, Any]) -> int:
    """Collect the verdicts, check the tree, then apply, commit and record (or, under
    ``--check``, only report); print the summary."""
    pre = _resume(workdir, given)
    readme = bool(pre.get("readme"))
    if readme and pre["stage"] == "start":
        raise StepError(COMPOSE_FIRST, EXIT_REFUSED)
    empty_plan = ((workdir / "plan-docs.json").is_file()
                  and read_json(workdir / "plan-docs.json") == [])
    if (pre["stage"] == "start" and not empty_plan) or pre["stage"] == "compose":
        raise StepError(VERIFY_FIRST, EXIT_REFUSED)
    if pre["stage"] == "verify" and not (workdir / "plan-verify.json").is_file():
        raise StepError("plan-verify.json is missing; run --stage verify first", EXIT_REFUSED)
    if not readme and _no_docs(workdir):
        text = _summary(root, workdir)
        _record(workdir, stage="finish")
        _write_stdout(text)
        return EXIT_OK
    config, _ = load_config(root)
    if pre["stage"] == "start":  # nothing was dispatched: the notice edits still need checks
        _step("checks", workdir, ("edits.json", "plan-verify.json"),
              lambda: dd_checks.run(root, workdir, config))
    plan: list[dd_dispatch.PlanEntry] = read_json(workdir / "plan-verify.json")
    if _outputs_or_retry(workdir, plan, ("verify",), retried) is None:
        return EXIT_RETRY
    _step("verdicts", workdir, ("verdicts.json",),
          lambda: dd_dispatch.collect_verdicts(workdir, plan))
    _tree_check(root, workdir, pre)
    if pre["check"]:
        text = _summary(root, workdir)
        _record(workdir, stage="finish")
        _write_stdout(text)
        return EXIT_FOUND if _would_apply(workdir) else EXIT_OK
    _step("apply", workdir, ("applied.json",), lambda: dd_apply.apply_edits(root, workdir),
          edits_at_risk=True)
    trailers = [str(t) for t in config.get("commit_trailers", [])]
    head, run_id = str(pre["head"]), str(pre["run_id"])
    commits = _step("commit", workdir, ("commits.json",),
                    lambda: dd_commit.run(root, workdir, str(pre["branch"]), run_id, head,
                                          str(pre["scope"]), trailers),
                    edits_at_risk=True)
    write_json(workdir / "last-run.json", {"head": head, "run_id": run_id, "date": pre["date"],
                                           "committed": bool(commits["commits"])})
    _record(workdir, stage="finish")  # the run is done; a failing summary does not undo that
    text = _summary(root, workdir, edits_at_risk=True)
    _write_stdout(text)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find documentation drift in stages; commit the accepted fixes on a branch.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--retried", action="store_true",
                        help="rerun of a stage that exited 3, after re-dispatching retry.json")
    parser.add_argument("--base", help="compare against REF instead of the last drift run")
    parser.add_argument("--full", action="store_true", default=None,
                        help="a first run regardless of any previous run")
    parser.add_argument("--branch", help="branch to create (default: config branch)")
    parser.add_argument("--check", action="store_true", default=None,
                        help="verify only; exit 1 from finish when an accepted edit exists")
    parser.add_argument("--workdir", type=Path, help="default: <repo>/.document-drift")
    parser.add_argument("--date", type=_date, default=None, help="YYYY-MM-DD (default today)")
    args = parser.parse_args(argv)
    root: Path = args.repo
    workdir: Path = args.workdir or root / ".document-drift"
    given = {flag: getattr(args, flag) for flag in FLAGS}
    try:
        if args.stage == "start":
            return stage_start(root, workdir, base=args.base, full=bool(args.full),
                               branch=args.branch, check=bool(args.check),
                               date=args.date or dt.date.today().isoformat())
        if args.stage == "compose":
            return stage_compose(root, workdir, retried=args.retried, given=given)
        if args.stage == "verify":
            return stage_verify(root, workdir, retried=args.retried, given=given)
        return stage_finish(root, workdir, retried=args.retried, given=given)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except Exception as exc:  # ruling R65: never exit 1 (reserved for --check) on a crash
        traceback.print_exc(file=sys.stderr)
        hint = HINT if args.stage == "finish" else ""
        print(f"error: the {args.stage} stage crashed outside a step: "
              f"{type(exc).__name__}: {exc}{hint}", file=sys.stderr)
        return EXIT_MISSING


if __name__ == "__main__":
    sys.exit(main())
