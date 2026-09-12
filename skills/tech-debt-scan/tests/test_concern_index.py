"""concern_index.py: definition-name index and cross-directory candidates (spec 2026-09-12, 4)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from concern_index import (
    STOPLIST,
    _main,
    build_concern_index,
    definition_names,
    normalise_name,
)


@pytest.mark.parametrize(
    ("language", "line", "name"),
    [
        ("python", "def compute_total(x):", "compute_total"),
        ("python", "    async def fetch_page(self):", "fetch_page"),
        ("python", "class RefundLedger:", "RefundLedger"),
        ("typescript", "export function computeTotal(x: number) {", "computeTotal"),
        ("javascript", "const computeTotal = (x) => x", "computeTotal"),
        ("typescript", "export default class Ledger {", "Ledger"),
        ("go", "func computeTotal(x int) int {", "computeTotal"),
        ("go", "func (l *Ledger) Post(x int) {", "Post"),
        ("rust", "pub fn compute_total(x: u32) -> u32 {", "compute_total"),
        ("rust", "impl Ledger {", "Ledger"),
        ("java", "public static int computeTotal(int x) {", "computeTotal"),
        ("csharp", "private async Task<int> ComputeTotal(int x)", "ComputeTotal"),
    ],
)
def test_definition_names_per_language(language: str, line: str, name: str) -> None:
    assert definition_names(language, line + "\n") == [name]


def test_unknown_language_yields_no_names() -> None:
    assert definition_names("markdown", "def looks_like_python():\n") == []


@pytest.mark.parametrize(
    ("raw", "key"),
    [("computeTotal", "compute_total"), ("compute_total", "compute_total"),
     ("ComputeTotal", "compute_total"), ("HTTPClient", "http_client")],
)
def test_normalise_name_joins_camel_and_snake(raw: str, key: str) -> None:
    assert normalise_name(raw) == key


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


def _inventory(files: dict[str, str], band: list[str]) -> dict[str, Any]:
    return {
        "root": "unused",
        "hotspot_band": band,
        "files": [
            {"path": rel, "path_class": "tests" if rel.startswith("tests/") else "source",
             "language": "python", "hotspot_score": 5.0 if rel in band else 0.0,
             "skipped_large": False}
            for rel in files
        ],
    }


def _coupling(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    return {"pairs": [{"a": a, "b": b} for a, b in pairs],
            "directories": [{"path": "src/pay", "files": 2, "loc": 10, "churn": 3,
                             "fan_in": 1, "fan_out": 1, "instability": 0.5}],
            "edges": []}


FILES = {
    "src/pay/utils.py": "def format_amount(x):\n    return x\n",
    "src/billing/format.py": "def formatAmount(x):\n    return x\n",
    "src/pay/parse.py": "def parse_csv(x):\n    return x\n",
    "src/billing/parse.py": "def parse_json(x):\n    return x\n",
    "src/pay/main.py": "def main():\n    pass\n",
    "src/billing/main.py": "def main():\n    pass\n",
    "tests/test_x.py": "def format_amount():\n    pass\n",
}


def test_candidate_needs_two_files_across_two_directories(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    doc = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    names = [c["name"] for c in doc["candidates"]]
    assert "format_amount" in names          # utils.py + format.py, two directories
    assert "parse_csv" not in names          # one file only
    assert "main" not in names               # stoplist


def test_test_files_do_not_count(tmp_path: Path) -> None:
    files = {"src/pay/a.py": "def only_here(x):\n    pass\n",
             "tests/test_a.py": "def only_here():\n    pass\n"}
    root = _repo(tmp_path, files)
    doc = build_concern_index(root, _inventory(files, []), _coupling([]))
    assert doc["candidates"] == []


def test_hotspot_touch_and_coupled_are_recorded(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    doc = build_concern_index(
        root, _inventory(FILES, ["src/pay/utils.py"]),
        _coupling([("src/pay/utils.py", "src/billing/format.py")]),
    )
    cand = next(c for c in doc["candidates"] if c["name"] == "format_amount")
    assert cand["hotspot_touch"] is True
    assert cand["coupled"] is True
    assert cand["files"] == ["src/billing/format.py", "src/pay/utils.py"]
    assert cand["directories"] == ["src/billing", "src/pay"]


def test_ranking_and_the_top_forty_cut(tmp_path: Path) -> None:
    files: dict[str, str] = {}
    for i in range(50):
        for d in ("a", "b", "c" if i < 5 else "b"):
            files[f"src/{d}/m{i}.py"] = f"def shared_{i:02d}():\n    pass\n"
    root = _repo(tmp_path, files)
    doc = build_concern_index(root, _inventory(files, []), _coupling([]))
    assert len(doc["candidates"]) == 40
    # three-directory names rank ahead of two-directory names
    assert all(len(c["directories"]) == 3 for c in doc["candidates"][:5])


def test_output_is_deterministic(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    a = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    b = build_concern_index(root, _inventory(FILES, []), _coupling([]))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_stoplist_covers_idioms_and_adapter_verbs() -> None:
    for word in ("main", "init", "new", "run", "setup", "teardown", "normalise", "parse",
                 "load", "render", "handle", "build"):
        assert word in STOPLIST


def test_cli_exits_2_without_edges(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    workdir = tmp_path / ".tech-debt"
    workdir.mkdir()
    (workdir / "inventory.json").write_text(json.dumps(_inventory(FILES, [])), encoding="utf-8")
    coupling = _coupling([])
    del coupling["edges"]
    (workdir / "coupling.json").write_text(json.dumps(coupling), encoding="utf-8")
    assert _main([str(root), "--workdir", str(workdir)]) == 2


def test_cli_writes_the_index(tmp_path: Path) -> None:
    root = _repo(tmp_path, FILES)
    workdir = tmp_path / ".tech-debt"
    workdir.mkdir()
    (workdir / "inventory.json").write_text(json.dumps(_inventory(FILES, [])), encoding="utf-8")
    (workdir / "coupling.json").write_text(json.dumps(_coupling([])), encoding="utf-8")
    assert _main([str(root), "--workdir", str(workdir)]) == 0
    doc = json.loads((workdir / "concern-index.json").read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1 and doc["stats"]["candidates"] >= 1
