"""The three-fixture corpus replays and matches its planted.json (spec 6)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from make_history import CORPUS_ROOT, git_output

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

EXPECTED_COMMITS = {"service-py": 18, "web-ts": 11, "mixed-decoys": 8}
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


SOURCE_TOKEN = re.compile(
    r"^(scout:[a-z-]+|rule:([a-z]+\.[a-z0-9-]+|[a-z]+\.\*|\*)|tool:([a-z-]+|\*))$"
)


def test_every_decoy_names_its_sources(corpus: tuple[str, Path]) -> None:
    """Spec 6: decoy without sources would match any producer; corpus forbids this."""
    name, _ = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    for decoy in planted["decoys"]:
        sources = decoy.get("sources")
        assert isinstance(sources, list) and sources, f"{name} {decoy['id']} has no sources"
        for token in sources:
            assert SOURCE_TOKEN.match(token), f"{name} {decoy['id']}: {token!r}"


def test_web_ts_workflow_installs_before_it_tests(web_ts_repo: Path) -> None:
    """Spec 6: decoy d1 is a decoy only once the workflow really is well configured."""
    text = (web_ts_repo / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run: npm ci" in text
    assert text.index("run: npm ci") < text.index("nick-fields/retry@")


def test_every_fixture_has_neutral_source_files(corpus: tuple[str, Path]) -> None:
    """Spec 6: the correlation test needs source files that are neither planted nor decoys."""
    from config import DEFAULTS
    from inventory import build_all

    name, repo = corpus
    planted = json.loads((CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    taken = {p["path"] for p in planted["planted"]} | {d["path"] for d in planted["decoys"]}
    inventory, _ = build_all(repo, churn_months=240, config=DEFAULTS)
    neutral = {e["path"] for e in inventory["files"]
               if e["path_class"] == "source" and e["path"] not in taken}
    assert len(neutral) >= 1, f"{name}: {neutral}"
    assert any(e["hotspot_score"] > 0 for e in inventory["files"] if e["path"] in neutral), \
        f"{name}: every neutral file scores 0.0"
