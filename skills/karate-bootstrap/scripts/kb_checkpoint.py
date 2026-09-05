"""Git checkpoints for karate-bootstrap (design spec section 9).

``begin`` makes sure the run lands on a feature branch: on the repo's default branch it
creates (or checks out) ``karate-bootstrap``; on any other branch, such as a ralph-managed
``ralph/<PBI-id>`` branch, it changes nothing. ``commit`` stages ``karate-tests/`` only and
commits with a phase-tagged message. Both print JSON. Both are no-ops with ``--no-commit``.
The skill never pushes.

Usage:
    python scripts/kb_checkpoint.py begin --repo <repo> [--branch karate-bootstrap] [--no-commit]
    python scripts/kb_checkpoint.py commit --repo <repo> --phase N --message "..." \
        [--tests-dir karate-tests] [--no-commit]

Exit codes: 0 ok (including nothing to commit), 2 when the repo is not a git work tree or
a git command fails.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from kb_common import EXIT_OK, KbError, run_cli

DEFAULT_BRANCH_NAME = "karate-bootstrap"
DEFAULT_TESTS_DIR = "karate-tests"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise KbError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc


def is_repo(repo: Path) -> bool:
    if not repo.is_dir():
        return False
    proc = _git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _require_repo(repo: Path) -> None:
    if not is_repo(repo):
        raise KbError(f"{repo} is not a git work tree")


def current_branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current").stdout.strip()


def _branch_exists(repo: Path, name: str) -> bool:
    proc = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def default_branch(repo: Path) -> str:
    """origin/HEAD when a remote is configured, else main or master, else the current branch."""
    proc = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    ref = proc.stdout.strip()
    if proc.returncode == 0 and ref.startswith("origin/"):
        return ref[len("origin/"):]
    for name in ("main", "master"):
        if _branch_exists(repo, name):
            return name
    return current_branch(repo)


def begin(repo: Path, branch: str = DEFAULT_BRANCH_NAME) -> dict[str, Any]:
    _require_repo(repo)
    current = current_branch(repo)
    if current != default_branch(repo):
        return {"branch": current, "created": False, "switched": False}
    exists = _branch_exists(repo, branch)
    if exists:
        _git(repo, "checkout", "-q", branch)
    else:
        _git(repo, "checkout", "-q", "-b", branch)
    return {"branch": branch, "created": not exists, "switched": True}


def commit(repo: Path, phase: int, message: str,
           tests_dir: str = DEFAULT_TESTS_DIR) -> dict[str, Any]:
    _require_repo(repo)
    _git(repo, "add", "--", tests_dir)
    staged = _git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return {"committed": False, "sha": None, "files": []}
    _git(repo, "commit", "-q", "-m", f"test(karate-bootstrap): phase {phase}: {message}")
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"committed": True, "sha": sha, "files": staged.splitlines()}


def _cmd_begin(args: argparse.Namespace) -> int:
    if args.no_commit:
        print(json.dumps({"skipped": "no-commit"}))
        return EXIT_OK
    print(json.dumps(begin(args.repo, args.branch)))
    return EXIT_OK


def _cmd_commit(args: argparse.Namespace) -> int:
    if args.no_commit:
        print(json.dumps({"skipped": "no-commit"}))
        return EXIT_OK
    print(json.dumps(commit(args.repo, args.phase, args.message, args.tests_dir)))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git checkpoints for karate-bootstrap runs")
    sub = parser.add_subparsers(dest="command", required=True)

    begin_p = sub.add_parser(
        "begin", help="Create or check out the feature branch when on the default branch"
    )
    begin_p.add_argument("--repo", type=Path, required=True)
    begin_p.add_argument("--branch", default=DEFAULT_BRANCH_NAME)
    begin_p.add_argument("--no-commit", action="store_true", help="never touch git")
    begin_p.set_defaults(func=_cmd_begin)

    commit_p = sub.add_parser("commit", help="Stage karate-tests/ and commit a phase checkpoint")
    commit_p.add_argument("--repo", type=Path, required=True)
    commit_p.add_argument("--phase", type=int, required=True)
    commit_p.add_argument("--message", required=True)
    commit_p.add_argument("--tests-dir", default=DEFAULT_TESTS_DIR,
                          help="directory to stage, relative to the repo")
    commit_p.add_argument("--no-commit", action="store_true", help="never touch git")
    commit_p.set_defaults(func=_cmd_commit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
