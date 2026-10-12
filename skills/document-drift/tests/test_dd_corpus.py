"""The corpus fixtures end to end (spec 0d): each fixture state runs the staged pipeline with
canned agent outputs, and each planted item is judged against that run's workdir files.

The runs are shared across the planted-item cases (one run per fixture and state); the tests
that change a repository make their own run.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from dd_common import read_json
from dd_corpus import (
    CANNED_ROOT,
    DATES,
    FIXTURES,
    Workdir,
    evaluate,
    git,
    planted_items,
    run_fixture,
)
from dd_run import main

# (fixture, item id) -> why the pipeline is known to miss the expectation, with evidence.
# Leave empty unless a miss is a known limitation recorded in the ledger.
XFAIL: dict[tuple[str, str], str] = {}

CASES = [(name, item) for name in FIXTURES for item in planted_items(name)]


def _id(name: str) -> str:
    return name.replace("-", "_")


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str, int], Workdir]:
    cache: dict[tuple[str, int], Workdir] = {}

    def get(name: str, state: int) -> Workdir:
        if (name, state) not in cache:
            cache[(name, state)] = run_fixture(
                name, state, tmp_path_factory.mktemp(f"{_id(name)}-state{state}"))
        return cache[(name, state)]

    return get


@pytest.mark.parametrize(("name", "item"), CASES,
                         ids=[f"{_id(name)}-{item['id']}" for name, item in CASES])
def test_planted_item(name: str, item: dict[str, Any], runs: Callable[[str, int], Workdir],
                      request: pytest.FixtureRequest) -> None:
    if (name, item["id"]) in XFAIL:
        request.applymarker(pytest.mark.xfail(reason=XFAIL[(name, item["id"])], strict=True))
    run = runs(name, int(item["state"]))
    problems = evaluate(item, run.path, int(item["state"]))
    assert not problems, f"{item['id']} ({item['what']}): " + "; ".join(problems)


def test_every_item_has_an_expectation() -> None:
    for name in FIXTURES:
        items = planted_items(name)
        ids = [item["id"] for item in items]
        assert len(ids) == len(set(ids)), f"{name}: repeated item ids"
        for item in items:
            assert item["expect"], f"{name} {item['id']} expects nothing"
            assert item.get("doc") or item.get("name"), f"{name} {item['id']} has no place"


@pytest.mark.parametrize("name", FIXTURES, ids=[_id(n) for n in FIXTURES])
def test_invalid_output_exits_3_then_retried_marks_unchecked(name: str,
                                                             tmp_path: Path) -> None:
    invalid = sorted(p.stem for p in (CANNED_ROOT / name / "state1-invalid").glob("*.json"))
    assert invalid, f"{name} has no invalid canned output"
    run = run_fixture(name, 1, tmp_path, canned_invalid=True)
    assert run.exits == [("start", 0), ("verify", 3), ("verify --retried", 0), ("finish", 0)]
    assert [e["id"] for e in read_json(run.path / "retry.json")] == invalid
    edits = read_json(run.path / "edits.json")
    assert [u for u in edits["unchecked_units"] if u in invalid] == invalid
    assert not [e for e in edits["edits"] if e["id"].split("-")[0] in invalid]


@pytest.mark.parametrize("name", FIXTURES, ids=[_id(n) for n in FIXTURES])
def test_no_agent_dispatched_when_nothing_changed(name: str, tmp_path: Path) -> None:
    run = run_fixture(name, 2, tmp_path)
    # the state-2 run started from main's HEAD; back on main nothing changed since then
    git(run.repo, "switch", "-q", "main")
    assert read_json(run.path / "last-run.json")["head"] == git(
        run.repo, "rev-parse", "HEAD").strip()
    assert main([str(run.repo), "--stage", "start", "--date", DATES[2],
                 "--branch", "docs/drift-again"]) == 0
    changes = read_json(run.path / "changes.json")
    assert (changes["mode"], changes["changed_files"], changes["affected"]) == ("later", [], {})
    assert read_json(run.path / "plan-docs.json") == []
    assert main([str(run.repo), "--stage", "finish"]) == 0
