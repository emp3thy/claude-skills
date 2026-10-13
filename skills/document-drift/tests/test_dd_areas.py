from __future__ import annotations

from pathlib import Path

from dd_areas import run, split
from dd_common import read_json, write_json

PROJECT = {"pyproject.toml", "Makefile"}


def _split(files: dict[str, int], project: set[str] | None = None) -> list[list[str]]:
    return split(sorted(files.items()), PROJECT if project is None else project, 100)


def test_project_files_and_root_loose_files_form_a01():
    groups = _split({"pyproject.toml": 60, "Makefile": 5, "main.py": 30, "src/a.py": 90})
    assert groups == [["Makefile", "main.py", "pyproject.toml"], ["src/a.py"]]


def test_directory_within_budget_is_one_area():
    groups = _split({"src/a.py": 40, "src/b/c.py": 50, "pkg/d.py": 90})
    assert groups == [["pkg/d.py"], ["src/a.py", "src/b/c.py"]]


def test_directory_over_budget_splits_into_subdirectories_plus_loose_files():
    files = {"src/a/1.py": 80, "src/b/1.py": 90, "src/x.py": 40, "src/y.py": 40}
    assert _split(files) == [["src/a/1.py"], ["src/b/1.py"], ["src/x.py", "src/y.py"]]


def test_loose_files_over_budget_are_chunked_in_path_order():
    files = {f"src/f{i}.py": 30 for i in range(5)}
    assert _split(files) == [["src/f0.py", "src/f1.py", "src/f2.py"],
                             ["src/f3.py", "src/f4.py"]]


def test_single_file_over_budget_is_its_own_area():
    files = {"src/big.py": 300, "src/small.py": 10}
    assert _split(files) == [["src/big.py"], ["src/small.py"]]


def test_siblings_merge_in_path_order_within_budget():
    files = {"src/a/1.py": 30, "src/b/1.py": 30, "src/c/1.py": 50, "src/d/1.py": 30,
             "src/e.py": 90}
    assert _split(files) == [["src/a/1.py", "src/b/1.py"], ["src/c/1.py", "src/d/1.py"],
                             ["src/e.py"]]


def test_top_level_directories_merge_too():
    files = {"Makefile": 10, "docs/a.py": 20, "scripts/a.py": 20, "website/a.py": 20}
    assert _split(files) == [["Makefile", "docs/a.py", "scripts/a.py", "website/a.py"]]


def test_hints_follow_their_file_and_strays_go_to_a01(tmp_path: Path):
    root, work = tmp_path / "repo", tmp_path / "work"
    for rel, n in {"Makefile": 3, "src/a.py": 70, "src/b.py": 70}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x\n" * n)
    work.mkdir()
    write_json(work / "inventory.json", {
        "sources": {"source": ["src/a.py", "src/b.py"]}, "project_files": ["Makefile"]})

    def name(file: str, nm: str) -> dict[str, object]:
        return {"name": nm, "kind": "command", "file": file, "line": 1, "parent": None,
                "hidden": False}

    write_json(work / "patterns.json", {"names": [
        name("src/b.py", "b"), name("elsewhere/x.py", "stray"), name("Makefile", "m")]})
    result = run(root, work, {"area_lines": 100})
    assert result == read_json(work / "areas.json")
    assert [a["id"] for a in result["areas"]] == ["a01", "a02", "a03"]
    assert [a["lines"] for a in result["areas"]] == [3, 70, 70]
    assert [[h["name"] for h in a["hints"]] for a in result["areas"]] == [
        ["stray", "m"], [], ["b"]]
