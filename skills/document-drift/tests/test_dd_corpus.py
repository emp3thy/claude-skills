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
    _expect_readme,
    evaluate,
    fixture_states,
    git,
    planted_items,
    run_fixture,
)
from dd_run import main

# (fixture, item id) -> why the pipeline is known to miss the expectation, with evidence.
# Leave empty unless a miss is a known limitation recorded in the ledger.
XFAIL: dict[tuple[str, str], str] = {}

CASES = [(name, item) for name in FIXTURES for item in planted_items(name)]
# the later-run tests need a second state; the retry tests need an invalid canned output, which
# one fixture carries per role (the retry path does not depend on the fixture): review outputs
# directly under state1-invalid/ (verify's retry, the unit unchecked), sheet outputs under
# state1-invalid/sheets/ (compose's retry; a sheet short only of hints is filled, not unchecked,
# so it has a test of its own)
TWO_STATES = tuple(name for name in FIXTURES if 2 in fixture_states(name))
WITH_INVALID = tuple(name for name in FIXTURES
                     if any((CANNED_ROOT / name / "state1-invalid").glob("*.json")))
WITH_INVALID_SHEETS = tuple(name for name in FIXTURES
                            if (CANNED_ROOT / name / "state1-invalid" / "sheets").is_dir())


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
            assert int(item["state"]) in fixture_states(name), f"{name} {item['id']}: no state"


def test_the_retry_path_is_exercised() -> None:
    assert WITH_INVALID, "no fixture carries an invalid canned review output"
    assert WITH_INVALID_SHEETS, "no fixture carries an invalid canned sheet output"


@pytest.mark.parametrize("name", TWO_STATES, ids=[_id(n) for n in TWO_STATES])
def test_state2_run_starts_from_the_merged_drift_base(
        name: str, runs: Callable[[str, int], Workdir]) -> None:
    # the state-1 run's Drift-Base trailer is found through the --no-ff merge, not the record
    changes = read_json(runs(name, 2).path / "changes.json")
    state1 = git(runs(name, 2).repo, "rev-parse", "state1").strip()
    assert (changes["mode"], changes["last_run_source"], changes["last_run"]) == (
        "later", "commit", state1)


@pytest.mark.parametrize("name", WITH_INVALID, ids=[_id(n) for n in WITH_INVALID])
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


@pytest.mark.parametrize("name", WITH_INVALID_SHEETS, ids=[_id(n) for n in WITH_INVALID_SHEETS])
def test_sheet_short_of_a_hint_exits_3_then_retried_fills_it(name: str, tmp_path: Path) -> None:
    # phase B spec 5.4: the retry returns the same sheet, still short only of hints; the
    # --retried compose accepts it and fills the missing hints from the pattern scan
    invalid = sorted(p.stem for p in (CANNED_ROOT / name / "state1-invalid" / "sheets").glob(
        "*.json"))
    assert invalid, f"{name} has no invalid canned sheet"
    run = run_fixture(name, 1, tmp_path, canned_invalid=True)
    assert run.exits == [("start", 0), ("compose", 3), ("compose --retried", 0), ("verify", 0),
                         ("finish", 0)]
    assert [e["id"] for e in read_json(run.path / "retry.json")] == invalid
    sheets = read_json(run.path / "sheets.json")
    assert (sheets["unchecked"], sorted(sheets["sheets"])) == ([], sorted(
        e["id"] for e in read_json(run.path / "plan-docs.json") if e["role"] == "sheet"))
    filled = [e for area in invalid for e in sheets["sheets"][area]["surface"] if e.get("filled")]
    assert len(filled) == sheets["filled"] > 0
    assert all(e["summary"] == "from the pattern scan" for e in filled)


@pytest.mark.parametrize("name", TWO_STATES, ids=[_id(n) for n in TWO_STATES])
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


def test_readme_judges_match_whole_spans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import dd_corpus

    text = "Call `Store.migrate` then `KV_TOKEN`; see `kv.cli.main`.\n"
    monkeypatch.setattr(dd_corpus, "_drift_readme", lambda _w: text)
    item: dict[str, Any] = {}
    assert _expect_readme(item, tmp_path, "absent:migrate") is None
    assert _expect_readme(item, tmp_path, "names:migrate") is None  # dotted span, last segment
    assert _expect_readme(item, tmp_path, "names:KV_TOKEN") is None
    assert _expect_readme(item, tmp_path, "names:Store") is not None
    assert _expect_readme(item, tmp_path, "names:cli.main") is not None  # dotted name, no suffix
    monkeypatch.setattr(dd_corpus, "_drift_readme", lambda _w: "Run `migrate` now.\n")
    assert _expect_readme(item, tmp_path, "absent:migrate") is not None
