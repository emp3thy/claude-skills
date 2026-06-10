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


def test_entries_carry_complexity_and_churn_fields():
    result = walk_inventory(FIXTURES / "python-repo")
    for entry in result["files"]:
        assert "complexity" in entry and entry["complexity"] >= 0
        assert "max_indent" in entry and entry["max_indent"] >= 0
        assert "churn" in entry and entry["churn"] >= 0
    # the fixtures contain indented code, so at least one file has complexity
    assert any(e["complexity"] > 0 for e in result["files"])


def test_inventory_carries_hotspot_summary_keys():
    result = walk_inventory(FIXTURES / "python-repo")
    assert "git_available" in result
    assert "churn_window_months" in result
    assert isinstance(result["hotspots"], list)
    for hotspot in result["hotspots"]:
        assert set(hotspot) == {"path", "churn", "complexity", "loc", "score"}
        assert 0 < hotspot["score"] <= 100


def test_non_git_dir_has_zero_churn(tmp_path: Path):
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    result = walk_inventory(tmp_path)
    assert result["git_available"] is False
    assert result["hotspots"] == []
    assert all(e["churn"] == 0 for e in result["files"])


def test_indentation_complexity_counts_units(tmp_path: Path):
    # two lines at depth 1, one at depth 2 -> total 4 units, max 2
    (tmp_path / "x.py").write_text(
        "def f():\n    a = 1\n    if a:\n        return a\n", encoding="utf-8"
    )
    result = walk_inventory(tmp_path)
    entry = result["files"][0]
    assert entry["complexity"] == 4
    assert entry["max_indent"] == 2
