"""The three-fixture corpus replays and matches its planted.json (spec 6)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from make_history import CORPUS_ROOT, git_output

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

EXPECTED_COMMITS = {"service-py": 16, "web-ts": 10, "mixed-decoys": 6}
EXPECTED_TAGS = {
    "service-py": ["v0.1.0", "v0.2.0"],
    "web-ts": ["v1.0.0", "v1.1.0"],
    "mixed-decoys": ["v0.1.0", "v0.2.0"],
}
EXPECTED_BRANCHES = {
    "service-py": ["hotfix/ledger-rounding", "main"],
    "web-ts": ["main", "release/1.2"],
    "mixed-decoys": ["main", "staging"],
}


def _tree(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


@pytest.fixture(params=["service-py", "web-ts", "mixed-decoys"])
def corpus(request: pytest.FixtureRequest) -> tuple[str, Path]:
    name = str(request.param)
    fixture_name = {
        "service-py": "service_py_repo",
        "web-ts": "web_ts_repo",
        "mixed-decoys": "mixed_decoys_repo",
    }[name]
    repo: Path = request.getfixturevalue(fixture_name)
    return name, repo


def test_commit_count_tags_and_branches(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    assert len(git_output(repo, "log", "--format=%H").split()) == EXPECTED_COMMITS[name]
    assert git_output(repo, "tag", "--sort=creatordate").split() == EXPECTED_TAGS[name]
    heads = git_output(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    assert heads == EXPECTED_BRANCHES[name]
    assert git_output(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"


def test_replayed_tree_equals_files_dir(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    assert _tree(repo) == _tree(CORPUS_ROOT / name / "files")


def test_planted_paths_and_lines_exist(corpus: tuple[str, Path]) -> None:
    name, repo = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    assert planted["planted"], "every fixture plants at least one item"
    assert planted["decoys"], "every fixture plants at least one decoy"
    for item in planted["planted"]:
        assert set(item) >= {"id", "family", "type_id", "path", "lines", "expect_tier"}
        if item["path"] is None:
            continue
        target = repo / item["path"]
        assert target.is_file(), item["id"]
        line_count = target.read_bytes().count(b"\n")
        start, end = item["lines"]
        assert 1 <= start <= end <= line_count, f"{item['id']}: {start}-{end} of {line_count}"
    for decoy in planted["decoys"]:
        assert set(decoy) >= {"id", "family", "path", "why"}
        assert (repo / decoy["path"]).is_file(), decoy["id"]
