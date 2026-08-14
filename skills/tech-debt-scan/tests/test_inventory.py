from __future__ import annotations

from pathlib import Path

from inventory import walk_inventory

FIXTURES = Path(__file__).parent / "fixtures"


def test_python_repo_inventory():
    result = walk_inventory(FIXTURES / "python-repo")
    assert result["total_files"] == 3
    assert result["total_loc"] > 0
    assert "python" in result["languages"]
    # __pycache__ and .venv files must be ignored
    for entry in result["files"]:
        assert "__pycache__" not in entry["path"]
        assert ".venv" not in entry["path"]


def test_csharp_repo_inventory():
    result = walk_inventory(FIXTURES / "csharp-repo")
    assert result["total_files"] == 2
    assert "csharp" in result["languages"]
    for entry in result["files"]:
        assert "/bin/" not in entry["path"] and "/obj/" not in entry["path"]


def test_react_repo_inventory():
    result = walk_inventory(FIXTURES / "react-repo")
    assert result["total_files"] == 4  # 3 tsx + 1 ts
    assert "typescript" in result["languages"]
    for entry in result["files"]:
        assert "node_modules" not in entry["path"]


def test_multi_lang_repo_inventory():
    result = walk_inventory(FIXTURES / "multi-lang-repo")
    assert len(result["languages"]) >= 2


def test_missing_path_raises():
    import pytest
    from inventory import InventoryError

    with pytest.raises(InventoryError, match="path not found"):
        walk_inventory(FIXTURES / "does-not-exist")


def test_empty_dir_returns_zero(tmp_path: Path):
    result = walk_inventory(tmp_path)
    assert result["total_files"] == 0
    assert result["files"] == []


def test_satd_and_import_counts():
    result = walk_inventory(FIXTURES / "satd-repo")
    entry = next(e for e in result["files"] if e["path"] == "dirty.py")
    assert entry["satd_count"] == 2      # TODO + FIXME
    assert entry["import_count"] == 2    # import os + from sys import argv


def test_counts_present_on_every_entry():
    result = walk_inventory(FIXTURES / "python-repo")
    for entry in result["files"]:
        assert "satd_count" in entry
        assert "import_count" in entry


def test_git_churn_none_when_no_git(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    entry = next(e for e in result["files"] if e["path"] == "a.py")
    assert entry["git_churn"] is None  # no .git -> degrade, do not abort


def test_git_churn_counts_commits(tmp_path: Path):
    import subprocess

    def _git(*args: str):
        subprocess.run(
            ["git", *args], cwd=tmp_path, check=True,
            capture_output=True, text=True,
        )

    _git("init")
    _git("config", "user.email", "t@e.st")
    _git("config", "user.name", "t")
    (tmp_path / "hot.py").write_text("v = 1\n", encoding="utf-8")
    _git("add", "hot.py")
    _git("commit", "-m", "one")
    (tmp_path / "hot.py").write_text("v = 2\n", encoding="utf-8")
    _git("commit", "-am", "two")

    result = walk_inventory(tmp_path)
    entry = next(e for e in result["files"] if e["path"] == "hot.py")
    assert entry["git_churn"] == 2  # touched by two commits
