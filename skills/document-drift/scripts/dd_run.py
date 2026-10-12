"""The chain: preflight, inventory, extract, resolve, fixes, apply, commit, summary.

Usage: ``python scripts/dd_run.py <repo> [--base REF] [--branch NAME] [--workdir DIR]
[--date YYYY-MM-DD] [--check]``.

The workdir defaults to ``<repo>/.document-drift`` and the date to today. The branch defaults
to the config ``branch`` with ``{date}`` replaced by the date. The run id is the first 12 hex
characters of ``sha256("<head>:<scope>:<date>")`` where scope is ``all`` or ``base:<ref>``.
Before the first step every output file the run may produce is deleted from the workdir, so a
stale file can neither satisfy a check nor be read again (ruling R45). After preflight the run
fields (``run_id``, ``scope``, ``check``, ``date``, ``config_warnings``) are added to
``preflight.json`` for the summary.

``--base REF`` keeps a doc when it is itself in ``git diff --name-only --no-renames
REF...HEAD`` or one of its ``path`` or ``tree`` tokens (ruling R66) resolves, at HEAD or at its
snapshot (``resolved_then``), to a changed path or a directory holding one. ``--no-renames``
lists both sides of a rename, so a doc naming the old path stays in scope. The filter runs after
resolve: the other docs' tokens, markers, candidates and honoured entries are dropped and the
docs are recorded in ``inventory.json`` as ``scope_dropped`` (sorted; empty without ``--base``).

``--check`` stops after fixes (no apply, no commit), writes the summary and exits 1 when
``hunks-provable.json`` holds any hunk, else 0. Exit codes: a ``StepError`` exits with its own
code and message; a step that does not write its output exits 5 naming the file; any other
exception prints its traceback and exits 5 naming the step. Ruling R65: an exception anywhere
else in the chain (clearing the old outputs, rewriting ``preflight.json`` or ``inventory.json``,
writing to stdout, reading the final hunks) also prints its traceback and exits 5.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dd_apply
import dd_commit
import dd_extract
import dd_fixes
import dd_inventory
import dd_preflight
import dd_resolve
import dd_summary
from dd_common import (
    EXIT_FOUND,
    EXIT_MISSING,
    EXIT_OK,
    EXIT_REFUSED,
    StepError,
    read_json,
    run_git,
    write_json,
)
from dd_config import load_config
from dd_history import History
from dd_resolve import path_matches, tree_match

OUTPUTS = (
    "preflight.json", "inventory.json", "tokens.json", "candidates.json", "findings.json",
    "hunks-provable.json", "applied.json", "commits.json", "summary.md", "commit-msg.txt",
)


def _date(value: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(f"{value!r} is not a YYYY-MM-DD date")
    return value


def run_id_for(head: str, scope: str, date: str) -> str:
    """First 12 hex characters of ``sha256("<head>:<scope>:<date>")``."""
    return hashlib.sha256(f"{head}:{scope}:{date}".encode()).hexdigest()[:12]


def _step(name: str, workdir: Path, outputs: tuple[str, ...], call: Callable[[], Any]) -> Any:
    """Run one step; StepError passes through, a crash or a missing output becomes exit 5."""
    try:
        result = call()
    except StepError:
        raise
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        raise StepError(f"step {name} crashed: {type(exc).__name__}: {exc}",
                        EXIT_MISSING) from exc
    for out in outputs:
        if not (workdir / out).is_file():
            raise StepError(f"step {name} did not write {workdir / out}", EXIT_MISSING)
    return result


def changed_paths(root: Path, ref: str) -> set[str]:
    """Paths changed in ``ref...HEAD``, both sides of a rename; an unknown ref is refused."""
    verify = ["rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"]
    if ref.startswith("-") or run_git(root, verify) is None:
        raise StepError(f"--base {ref!r} is not a commit in this repository", EXIT_REFUSED)
    out = run_git(root, ["-c", "core.quotePath=false", "diff", "--name-only", "--no-renames",
                         f"{ref}...HEAD", "--"])
    if out is None:
        raise StepError(f"git diff {ref}...HEAD failed; check --base", EXIT_REFUSED)
    return {line for line in out.splitlines() if line}


def apply_base_scope(root: Path, workdir: Path, changed: set[str]) -> list[str]:
    """Drop the docs out of ``--base`` scope from tokens, candidates and the inventory."""
    inventory = read_json(workdir / "inventory.json")
    tokens = read_json(workdir / "tokens.json")
    cands = read_json(workdir / "candidates.json")
    touched = set(changed)
    for path in changed:
        parts = path.split("/")
        touched.update("/".join(parts[:n]) for n in range(1, len(parts)))
    files, dirs = History(root).head_files()

    def in_scope(doc: str) -> bool:
        if doc in changed:
            return True
        for tok in tokens["docs"].get(doc, []):
            if tok.get("kind") == "path":
                found = path_matches(str(tok["text"]), doc, files, dirs)
                if found is not None and any(p in touched for p in found[1]):
                    return True
            elif tok.get("kind") == "tree" and tree_match(tok, files, dirs) in touched:
                return True  # ruling R66: tree entries name paths too
        return any(c["doc"] == doc and c.get("kind") in ("path", "tree")
                   and c.get("resolved_then") in touched for c in cands["candidates"])

    dropped = sorted(doc for doc in inventory["docs"] if not in_scope(doc))
    gone = set(dropped)
    inventory["docs"] = [d for d in inventory["docs"] if d not in gone]
    inventory["scope_dropped"] = dropped
    tokens["docs"] = {d: t for d, t in tokens["docs"].items() if d not in gone}
    tokens["markers"] = [m for m in tokens.get("markers", []) if m.get("doc") not in gone]
    tokens["skipped"] = [s for s in tokens.get("skipped", []) if s.get("doc") not in gone]
    cands["candidates"] = [c for c in cands["candidates"] if c["doc"] not in gone]
    cands["honoured"] = [h for h in cands.get("honoured", []) if h.get("doc") not in gone]
    cands["history_unavailable"] = any(c.get("history_unavailable")
                                       for c in cands["candidates"])
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "tokens.json", tokens)
    write_json(workdir / "candidates.json", cands)
    return dropped


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.write(text.encode(encoding, "replace").decode(encoding))
    sys.stdout.flush()


def chain(root: Path, workdir: Path, *, base: str | None, branch: str | None, date: str,
          check: bool) -> int:
    """Run every step in order; return the exit code. StepError propagates."""
    config, warnings = load_config(root)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    branch_name = branch or str(config["branch"]).replace("{date}", date)
    scope = "all" if base is None else f"base:{base}"
    for name in OUTPUTS:
        (workdir / name).unlink(missing_ok=True)

    pre = _step("preflight", workdir, ("preflight.json",),
                lambda: dd_preflight.run(root, workdir, branch_name, check))
    run_id = run_id_for(str(pre["head"]), scope, date)
    pre_doc = read_json(workdir / "preflight.json")
    pre_doc.update(run_id=run_id, scope=scope, check=check, date=date,
                   config_warnings=list(warnings))
    write_json(workdir / "preflight.json", pre_doc)
    changed = changed_paths(root, base) if base is not None else None

    _step("inventory", workdir, ("inventory.json",),
          lambda: dd_inventory.run(root, workdir, config))
    _step("extract", workdir, ("tokens.json",), lambda: dd_extract.run(root, workdir))
    _step("resolve", workdir, ("candidates.json",), lambda: dd_resolve.run(root, workdir))
    if changed is not None:
        _step("scope", workdir, ("inventory.json",),
              lambda: apply_base_scope(root, workdir, changed))
    else:
        inventory = read_json(workdir / "inventory.json")
        inventory["scope_dropped"] = []
        write_json(workdir / "inventory.json", inventory)
    _step("fixes", workdir, ("findings.json", "hunks-provable.json"),
          lambda: dd_fixes.run(root, workdir))
    if not check:
        _step("apply", workdir, ("applied.json",), lambda: dd_apply.run(root, workdir))
        trailers = [str(t) for t in config.get("commit_trailers", [])]
        _step("commit", workdir, ("commits.json",),
              lambda: dd_commit.run_hunks(root, workdir, branch_name, run_id, scope, trailers))
    text = _step("summary", workdir, ("summary.md",), lambda: dd_summary.run(workdir))
    _write_stdout(str(text))
    if check and read_json(workdir / "hunks-provable.json")["hunks"]:
        return EXIT_FOUND
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find documentation drift and commit the provable fixes on a branch.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--base", help="only docs touched by REF...HEAD (by path or reference)")
    parser.add_argument("--branch", help="branch to create (default: config branch)")
    parser.add_argument("--workdir", type=Path, help="default: <repo>/.document-drift")
    parser.add_argument("--date", type=_date, default=None, help="YYYY-MM-DD (default today)")
    parser.add_argument("--check", action="store_true",
                        help="report only; exit 1 when a provable edit exists")
    args = parser.parse_args(argv)
    root: Path = args.repo
    workdir: Path = args.workdir or root / ".document-drift"
    date: str = args.date or dt.date.today().isoformat()
    try:
        return chain(root, workdir, base=args.base, branch=args.branch, date=date,
                     check=args.check)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except Exception as exc:  # ruling R65: never exit 1 (reserved for --check) on a crash
        traceback.print_exc(file=sys.stderr)
        print(f"error: the run crashed outside a step: {type(exc).__name__}: {exc}; "
              "check git status and git branch", file=sys.stderr)
        return EXIT_MISSING


if __name__ == "__main__":
    sys.exit(main())
