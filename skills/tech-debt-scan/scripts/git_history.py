"""One pass over git history for inventory.py (spec 4.2).

``git_log_pass`` runs a single ``git log --name-only`` with a record separator
format and returns every commit in the churn window, newest first, with its
author name and email, ISO date, subject and touched paths (root-relative,
forward-slash). ``derive_file_history`` folds those commits into per-file
facts for the paths present at HEAD, so a file deleted in history never
becomes a lead. ``repo_authors``, ``list_branches``, ``list_tags``,
``mailmap_present`` and ``blame_top_share`` give the repo-wide ``git`` block
and the hotspot-band line share.

Failure posture (spec 3.3): every git call is a list argv with a 120-second
timeout; a missing binary, a non-repository, a timeout or a non-zero exit
returns ``None`` and the caller emits the no-git shape. Output is decoded as
UTF-8 with replacement (``core.quotePath=false`` keeps non-ASCII paths raw).

Authors are keyed by email; names matching ``bot_authors`` (case-insensitive
substring) are dropped from authorship counts. Commits touching more than the
coupling ``bulk_threshold`` are excluded from churn, authorship and coupling
and counted in ``bulk_commits_excluded``; ``commits_in_window`` counts every
commit. Git emits newest first, so the first date seen per file or author is
its last touch.

``change_coupling`` mines the same commit list for co-change pairs among
source-class files (spec 4.2): a pair is emitted when the files were touched
together in at least ``min_shared`` non-bulk commits and
``shared / mean(commits_a, commits_b) >= min_ratio``, giving both the ordered
pair list and each file's coupling degree (count of pairs it appears in).
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GIT_TIMEOUT = 120
LOG_FORMAT = "%x1e%H%x09%aN%x09%aE%x09%aI%x09%s"
REF_FORMAT = (
    "%(refname)%09%(refname:short)%09%(symref)%09%(committerdate:iso-strict)%09%(objectname)"
)
TAG_FORMAT = "%(refname:short)%09%(creatordate:iso-strict)"

BUGFIX_RE = re.compile(r"fix|bug|hotfix|regress", re.IGNORECASE)
MIGRATION_RE = re.compile(r"migrat|legacy|deprecat|port(ed|ing)|codemod|upgrade", re.IGNORECASE)
FLAKY_RE = re.compile(r"flak", re.IGNORECASE)


@dataclass(slots=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    date: str
    subject: str
    files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileHistory:
    churn: int = 0
    last_touched: str | None = None
    authors: int = 0
    top_author: str | None = None
    top_author_share: float | None = None
    bugfix_share: float = 0.0
    migration_commits: int = 0
    flaky_commits: int = 0
    untested_change_share: float | None = None


def run_git(root: Path, args: Sequence[str]) -> str | None:
    """Run ``git -C root <args>``; return stdout, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def parse_log(stdout: str) -> list[Commit]:
    """Parse the LOG_FORMAT output: one 0x1e record per commit."""
    commits: list[Commit] = []
    for chunk in stdout.split("\x1e"):
        if not chunk.strip():
            continue
        header, _, body = chunk.partition("\n")
        parts = header.split("\t", 4)  # subjects may contain tabs
        if len(parts) < 5:
            continue
        sha, name, email, date, subject = parts
        files = [line.strip() for line in body.splitlines() if line.strip()]
        commits.append(Commit(sha, name, email, date, subject, files))
    return commits


def git_log_pass(root: Path, months: int) -> list[Commit] | None:
    """Every commit in the window touching ``root``, newest first; None without git."""
    stdout = run_git(
        root,
        [
            "-c", "core.quotePath=false", "log", f"--since={months} months ago",
            "--name-only", "--relative", f"--format={LOG_FORMAT}", "--", ".",
        ],
    )
    if stdout is None:
        return None
    return parse_log(stdout)


def is_bot(name: str, bot_authors: Sequence[str]) -> bool:
    lowered = name.lower()
    return any(str(bot).lower() in lowered for bot in bot_authors)


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def derive_file_history(
    commits: Sequence[Commit],
    present: set[str],
    *,
    is_test: Callable[[str], bool],
    bot_authors: Sequence[str],
    bulk_threshold: int,
) -> tuple[dict[str, FileHistory], int]:
    """Per-file history for the paths present at HEAD; also the bulk commit count."""
    histories: dict[str, FileHistory] = {path: FileHistory() for path in present}
    authors: dict[str, Counter[str]] = {path: Counter() for path in present}
    bugfix: Counter[str] = Counter()
    untested: Counter[str] = Counter()
    bulk_excluded = 0
    for commit in commits:
        if len(commit.files) > bulk_threshold:
            bulk_excluded += 1
            continue
        human = not is_bot(commit.author_name, bot_authors)
        has_test = any(is_test(path) for path in commit.files)
        is_fix = BUGFIX_RE.search(commit.subject) is not None
        is_migration = MIGRATION_RE.search(commit.subject) is not None
        is_flaky = FLAKY_RE.search(commit.subject) is not None
        for path in commit.files:
            history = histories.get(path)
            if history is None:
                continue  # deleted before HEAD: never a lead
            history.churn += 1
            if history.last_touched is None:
                history.last_touched = commit.date
            if human:
                authors[path][commit.author_email] += 1
            if is_fix:
                bugfix[path] += 1
            if is_migration:
                history.migration_commits += 1
            if is_flaky:
                history.flaky_commits += 1
            if not has_test:
                untested[path] += 1
    for path, history in histories.items():
        counter = authors[path]
        history.authors = len(counter)
        if counter:
            email, count = counter.most_common(1)[0]
            history.top_author = email
            history.top_author_share = _share(count, sum(counter.values()))
        history.bugfix_share = _share(bugfix[path], history.churn) or 0.0
        history.untested_change_share = _share(untested[path], history.churn)
    return histories, bulk_excluded


def repo_authors(
    commits: Sequence[Commit], bot_authors: Sequence[str], bulk_threshold: int
) -> list[dict[str, Any]]:
    """Human authors with commit counts and last active date, most commits first."""
    counts: Counter[str] = Counter()
    names: dict[str, str] = {}
    last_active: dict[str, str] = {}
    for commit in commits:
        if len(commit.files) > bulk_threshold or is_bot(commit.author_name, bot_authors):
            continue
        counts[commit.author_email] += 1
        names.setdefault(commit.author_email, commit.author_name)
        last_active.setdefault(commit.author_email, commit.date)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"email": email, "name": names[email], "commits": count, "last_active": last_active[email]}
        for email, count in ordered
    ]


def parse_branch_refs(stdout: str) -> list[dict[str, Any]]:
    """Parse REF_FORMAT lines, skipping symbolic refs such as origin/HEAD."""
    refs: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        refname, short, symref, date, sha = parts
        if symref:
            continue
        refs.append({"name": short, "ref": refname, "last_commit": date, "sha": sha})
    return refs


def _merged_refnames(root: Path) -> frozenset[str] | None:
    """Full refnames merged into HEAD, via one bounded ``for-each-ref --merged`` pass.

    None when the call fails (a non-repository, no HEAD/unborn branch gives
    exit 128, a timeout, or a missing binary), so every branch gets
    ``merged: None`` rather than a wrong guess.
    """
    stdout = run_git(
        root,
        ["for-each-ref", "--format=%(refname)", "--merged=HEAD", "refs/heads", "refs/remotes"],
    )
    if stdout is None:
        return None
    return frozenset(line.strip() for line in stdout.splitlines() if line.strip())


def list_branches(root: Path) -> list[dict[str, Any]] | None:
    stdout = run_git(root, ["for-each-ref", f"--format={REF_FORMAT}", "refs/heads", "refs/remotes"])
    if stdout is None:
        return None
    merged = _merged_refnames(root)
    branches: list[dict[str, Any]] = []
    for ref in parse_branch_refs(stdout):
        ref.pop("sha", None)
        ref["merged"] = None if merged is None else str(ref["ref"]) in merged
        branches.append(ref)
    return branches


def list_tags(root: Path) -> list[dict[str, Any]] | None:
    stdout = run_git(root, ["tag", "--sort=creatordate", f"--format={TAG_FORMAT}"])
    if stdout is None:
        return None
    tags: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        name, _, date = line.partition("\t")
        if name:
            tags.append({"name": name, "date": date})
    return tags


def mailmap_present(root: Path) -> bool:
    top = run_git(root, ["rev-parse", "--show-toplevel"])
    if top is None:
        return False
    return (Path(top.strip()) / ".mailmap").is_file()


def blame_top_share(
    root: Path, rel: str, bot_authors: Sequence[str]
) -> tuple[float | None, str | None]:
    """(share of lines by the top human author, that author's email) via blame -w."""
    stdout = run_git(
        root, ["-c", "core.quotePath=false", "blame", "-w", "--line-porcelain", "--", rel]
    )
    if stdout is None:
        return None, None
    counter: Counter[str] = Counter()
    name = ""
    for line in stdout.splitlines():
        if line.startswith("author "):
            name = line[7:]
        elif line.startswith("author-mail ") and not is_bot(name, bot_authors):
            counter[line[12:].strip().strip("<>")] += 1
    if not counter:
        return None, None
    email, count = counter.most_common(1)[0]
    return round(count / sum(counter.values()), 3), email


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def change_coupling(
    commits: Sequence[Commit],
    present_source: set[str],
    *,
    min_shared: int,
    min_ratio: float,
    bulk_threshold: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Co-change pairs of source-class files (spec 4.2) and per-file degree.

    Bulk commits (more than ``bulk_threshold`` files) are skipped. A pair is
    emitted when ``shared >= min_shared`` and
    ``shared / mean(commits_a, commits_b) >= min_ratio``.
    """
    per_file: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    for commit in commits:
        if len(commit.files) > bulk_threshold:
            continue
        files = sorted({path for path in commit.files if path in present_source})
        for path in files:
            per_file[path] += 1
        for index, first in enumerate(files):
            for second in files[index + 1 :]:
                pair_counts[(first, second)] += 1
    pairs: list[dict[str, Any]] = []
    degree: dict[str, int] = {}
    for (first, second), shared in pair_counts.items():
        if shared < min_shared:
            continue
        mean = (per_file[first] + per_file[second]) / 2
        ratio = shared / mean if mean else 0.0
        if ratio < min_ratio:
            continue
        pairs.append(
            {
                "a": first,
                "b": second,
                "shared_commits": shared,
                "ratio": round(ratio, 3),
                "cross_directory": _dirname(first) != _dirname(second),
            }
        )
        degree[first] = degree.get(first, 0) + 1
        degree[second] = degree.get(second, 0) + 1
    pairs.sort(key=lambda p: (-int(p["shared_commits"]), -float(p["ratio"]), p["a"], p["b"]))
    return pairs, dict(sorted(degree.items()))
