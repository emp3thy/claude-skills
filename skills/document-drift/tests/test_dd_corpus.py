"""End-to-end checks over the three-language fixture corpus.

Each fixture under ``fixtures/corpus/<name>/`` keeps its final tree in ``files/``, its history
in ``history.yaml`` and its expectations in ``planted.json``: planted drift that must be found
with the stated outcome, and decoys that must never become an edit. Each item is its own test
case, so a single expectation can be marked xfail with evidence without hiding the others.

A decoy that relies on a doc exclusion is written so that it would be a provable edit if its
doc were scanned (ruling R53); ``test_excluded_decoys_would_be_edits_if_scanned`` proves that by
switching those exclusions off.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import dd_inventory
import dd_run
import pytest
from dd_common import EXIT_FOUND, read_json
from dd_corpus import (
    FIXTURES,
    TOKEN_KINDS,
    evaluate,
    is_edit,
    load_planted,
    outcome_for,
    prepare_fixture,
)
from dd_make_history import CORPUS_ROOT

Run = tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]  # tokens, findings, hunks
EXPECT = re.compile(r"(replace:.+|delete|unlink|human:[a-z-]+|none|excluded|no-token)")

# (fixture, item id) -> reason, for an expectation the pipeline is known to miss.
XFAIL: dict[tuple[str, str], str] = {}


def _cases() -> list[Any]:
    cases = []
    for fixture in FIXTURES:
        planted = load_planted(fixture)
        for item in planted["planted"] + planted["decoys"]:
            marks = []
            reason = XFAIL.get((fixture, item["id"]))
            if reason is not None:
                marks.append(pytest.mark.xfail(strict=True, reason=reason))
            cases.append(pytest.param(fixture, item, id=f"{fixture}-{item['id']}", marks=marks))
    return cases


def _check(fixture: str, base: Path) -> Run:
    repo = prepare_fixture(fixture, base / "repo")
    workdir = base / "wd"
    code = dd_run.main([str(repo), "--check", "--workdir", str(workdir), "--date", "2026-01-02"])
    assert code == EXIT_FOUND  # every fixture plants provable drift
    return (read_json(workdir / "tokens.json"),
            read_json(workdir / "findings.json")["findings"],
            read_json(workdir / "hunks-provable.json")["hunks"])


@pytest.fixture(scope="module")
def check_run(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Run]:
    """Replay a fixture and run ``--check`` once per module."""
    runs: dict[str, Run] = {}

    def get(fixture: str) -> Run:
        if fixture not in runs:
            runs[fixture] = _check(fixture, tmp_path_factory.mktemp(fixture))
        return runs[fixture]

    return get


@pytest.mark.parametrize("fixture", FIXTURES)
def test_replay_tree_equals_files_dir(fixture: str, tmp_path: Path) -> None:
    repo = prepare_fixture(fixture, tmp_path / fixture)
    out = subprocess.run(["git", "-C", str(repo), "-c", "core.quotePath=false", "ls-files", "-z"],
                         capture_output=True, check=True).stdout.decode("utf-8")
    tracked = sorted(p for p in out.split("\0") if p)
    files_root = CORPUS_ROOT / fixture / "files"
    final = sorted(p.relative_to(files_root).as_posix()
                   for p in files_root.rglob("*") if p.is_file())
    assert tracked == final
    for rel in tracked:
        assert (repo / rel).read_bytes() == (files_root / rel).read_bytes(), rel


@pytest.mark.parametrize(("fixture", "item"), _cases())
def test_every_planted_item_and_decoy_meets_expectation(
    fixture: str, item: dict[str, Any], check_run: Callable[[str], Run]
) -> None:
    tokens, findings, hunks = check_run(fixture)
    assert evaluate(item, tokens, findings, hunks) == item["expect"], item


def test_no_decoy_produces_an_edit(check_run: Callable[[str], Run]) -> None:
    edits = []
    for fixture in FIXTURES:
        _, findings, hunks = check_run(fixture)
        for decoy in load_planted(fixture)["decoys"]:
            got = outcome_for(decoy, findings, hunks)
            if is_edit(decoy["expect"]) or any(is_edit(o) for o in got.split(" | ")):
                edits.append((fixture, decoy["id"], decoy["expect"], got))
    assert edits == []


@pytest.mark.parametrize("fixture", [f for f in FIXTURES if any(
    d["expect"] == "excluded" for d in load_planted(f)["decoys"])])
def test_excluded_decoys_would_be_edits_if_scanned(
    fixture: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # R53: an exclusion decoy proves the exclusion only if scanning the doc would edit it
    decoys = [d for d in load_planted(fixture)["decoys"] if d["expect"] == "excluded"]
    docs = {d["doc"] for d in decoys}
    real = dd_inventory._Inventory.exclusion

    def exclusion(self: Any, rel: str) -> str | None:
        return None if rel in docs else real(self, rel)

    monkeypatch.setattr(dd_inventory._Inventory, "exclusion", exclusion)
    tokens, findings, hunks = _check(fixture, tmp_path)
    got = {d["id"]: outcome_for(d, findings, hunks) for d in decoys}
    assert got == {d["id"]: "delete" for d in decoys}
    assert docs <= set(tokens["docs"])


def test_every_token_kind_positive_in_two_fixtures() -> None:
    seen: dict[str, set[str]] = {kind: set() for kind in TOKEN_KINDS}
    for fixture in FIXTURES:
        for item in load_planted(fixture)["planted"]:
            assert item["kind"] in TOKEN_KINDS, item
            if is_edit(item["expect"]):
                seen[item["kind"]].add(fixture)
    assert all(len(fixtures) >= 2 for fixtures in seen.values()), seen


def test_planted_ids_are_unique_and_shaped() -> None:
    for fixture in FIXTURES:
        planted = load_planted(fixture)
        ids = [i["id"] for i in planted["planted"] + planted["decoys"]]
        assert len(ids) == len(set(ids)), fixture
        for item in planted["planted"]:
            assert {"id", "doc", "line", "kind", "text", "expect"} <= set(item), item
            assert item["expect"] not in ("excluded", "no-token"), item
        for item in planted["decoys"]:
            assert {"id", "doc", "line", "why", "expect"} <= set(item), item
        for item in planted["planted"] + planted["decoys"]:
            assert EXPECT.fullmatch(item["expect"]), item
