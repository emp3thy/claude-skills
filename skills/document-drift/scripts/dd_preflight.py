"""Preflight: refuse early when a run could not end in a clean commit (spec 7.1).

Every mode refuses a path that is not a git repository and a repository with no commits (there
is nothing to scan). Outside ``--check`` it also refuses a detached HEAD, an invalid branch
name, a dirty tree, an existing branch and a missing author identity; ``--check`` creates no
branch, so it runs from a detached HEAD too and ``branch_from`` is then null (ruling R56).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from dd_common import EXIT_OK, EXIT_REFUSED, StepError, git_ok, run_git, write_json


def _exclude_workdir(root: Path, workdir: Path) -> None:
    """Append the workdir's repository-relative path to info/exclude once."""
    raw = run_git(root, ["rev-parse", "--git-path", "info/exclude"])
    if raw is None:
        return
    exclude = Path(raw.strip())
    if not exclude.is_absolute():
        exclude = root / exclude
    try:
        rel = workdir.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return
    if rel in ("", "."):
        return
    entry = rel.rstrip("/") + "/"
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if entry in existing.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with exclude.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{entry}\n")


def run(root: Path, workdir: Path, branch: str, check: bool) -> dict[str, Any]:
    """Run the refusal checks; write and return ``preflight.json``."""
    if run_git(root, ["rev-parse", "--is-inside-work-tree"]) is None:
        raise StepError(f"{root} is not a git repository", EXIT_REFUSED)
    head_out = run_git(root, ["rev-parse", "HEAD"])
    if head_out is None:
        raise StepError("the repository has no commits yet", EXIT_REFUSED)
    branch_from = (run_git(root, ["symbolic-ref", "--short", "-q", "HEAD"]) or "").strip()
    if not check:  # ruling R56: check mode creates no branch, so these do not apply
        if not branch_from:
            raise StepError("HEAD is detached; check out a branch first", EXIT_REFUSED)
        if not git_ok(root, ["check-ref-format", "--branch", branch]):
            raise StepError(
                f"branch name {branch!r} is not valid; choose another with --branch",
                EXIT_REFUSED)
    _exclude_workdir(root, workdir)  # before the status check, so the workdir is not dirty
    if not check:
        status = run_git(root, ["status", "--porcelain"])
        if status is None or status.strip():
            raise StepError("the working tree is not clean; commit or stash first", EXIT_REFUSED)
        if git_ok(root, ["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"]):
            raise StepError(
                f"branch {branch} already exists; choose another with --branch", EXIT_REFUSED)
        if run_git(root, ["var", "GIT_AUTHOR_IDENT"]) is None:
            raise StepError(
                "no git author identity; set user.name and user.email", EXIT_REFUSED)
    version = (run_git(root, ["--version"]) or "").strip()
    result: dict[str, Any] = {
        "head": head_out.strip(),
        "branch_from": branch_from or None,
        "branch": branch,
        "git_version": version,
    }
    write_json(workdir / "preflight.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight refusal checks.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        run(args.repo, args.workdir, args.branch, args.check)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
