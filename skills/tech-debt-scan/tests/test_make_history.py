"""Smoke test for the history.yaml replay helper (spec section 6)."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from make_history import HistoryError, git_output, replay_history

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

HISTORY = """\
commits:
  - author: "Ada Lovelace <ada@example.com>"
    date: "2024-09-10T10:00:00+00:00"
    subject: "feat: initial"
    files:
      src/app.py: |
        x = 1
      src/old.py: |
        z = 3
      README.md: "@final"
    tag: v0.1.0
  - author: "Grace Hopper <grace@example.com>"
    date: "2025-03-01T09:00:00+00:00"
    subject: "fix: rounding\\twith tab"
    branch: hotfix/rounding
    files:
      src/app.py: |
        x = 3
  - author: "Grace Hopper <grace@example.com>"
    date: "2025-04-01T09:00:00+00:00"
    subject: "fix: rounding"
    branch: main
    files:
      src/app.py: "@final"
    delete: [src/old.py]
"""


def _write_history(tmp_path: Path) -> tuple[Path, Path]:
    files_root = tmp_path / "files"
    (files_root / "src").mkdir(parents=True)
    (files_root / "src" / "app.py").write_bytes(b"x = 2\n")
    (files_root / "README.md").write_bytes(b"# demo\n")
    history = tmp_path / "history.yaml"
    history.write_text(HISTORY, encoding="utf-8")
    return history, files_root


def test_scripts_dir_precedes_helpers_dir_on_syspath() -> None:
    """conftest.py must put scripts/ ahead of tests/helpers so a helper never shadows
    a module of the same name under scripts/ (spec 3.3)."""
    tests_dir = Path(__file__).resolve().parent
    scripts_dir = str(tests_dir.parent / "scripts")
    helpers_dir = str(tests_dir / "helpers")
    assert sys.path.index(scripts_dir) < sys.path.index(helpers_dir)


def test_replay_authors_dates_and_subjects_on_main(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    log = git_output(repo, "log", "--reverse", "--format=%aN|%aI|%s").splitlines()
    assert len(log) == 2  # the hotfix commit is on its own branch, not on main
    assert log[0].startswith("Ada Lovelace|2024-09-10T10:00:00")
    assert log[0].endswith("|feat: initial")
    assert log[1].startswith("Grace Hopper|2025-04-01T09:00:00")
    committer = git_output(repo, "log", "-1", "--format=%cI").strip()
    assert committer.startswith("2025-04-01T09:00:00")


def test_replay_final_tree_branch_tag_and_delete(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    assert (repo / "src" / "app.py").read_bytes() == b"x = 2\n"
    assert (repo / "README.md").read_bytes() == b"# demo\n"
    assert not (repo / "src" / "old.py").exists()
    assert git_output(repo, "tag").split() == ["v0.1.0"]
    heads = git_output(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
    assert heads == ["hotfix/rounding", "main"]
    assert git_output(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"
    subject = git_output(repo, "log", "-1", "--format=%s", "hotfix/rounding").rstrip("\n")
    assert subject == "fix: rounding\twith tab"


def test_malformed_history_raises(tmp_path: Path) -> None:
    history = tmp_path / "history.yaml"
    history.write_text("commits:\n  - author: x\n", encoding="utf-8")
    with pytest.raises(HistoryError, match="missing 'date'"):
        replay_history(history, tmp_path, tmp_path / "repo")


def test_git_output_raises_on_failure(tmp_path: Path) -> None:
    history, files_root = _write_history(tmp_path)
    repo = replay_history(history, files_root, tmp_path / "repo")
    with pytest.raises(HistoryError, match="rev-parse"):
        git_output(repo, "rev-parse", "--verify", "refs/heads/does-not-exist")
