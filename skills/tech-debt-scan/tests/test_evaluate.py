"""evaluate.py: precision, recall, decoy tiers and top-N decoys against planted.json (spec 6)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from evaluate import evaluate, hits, load_findings, render_table
from inventory import write_json
from make_history import CORPUS_ROOT


def _finding(
    family: str,
    file: str | None,
    start: int | None,
    end: int | None,
    tier: str,
    fingerprint: str,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint,
        "family": family,
        "tier": tier,
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": "q",
                      "quote_verified": True}],
    }


# A hand-written verified.json for service-py: six planted hits, two reported decoy hits,
# one unplanted finding and one tier-C decoy hit that is never "reported".
VERIFIED: list[dict[str, Any]] = [
    _finding("error-masking", "src/pay/refund.py", 31, 34, "A", "f01"),  # p1
    _finding("half-finished", "src/pay/refund.py", 35, 35, "B", "f02"),  # p2
    _finding("security", "src/pay/gateway.py", 11, 11, "B", "f03"),  # p3
    _finding("security", "tests/fixtures/seed.py", 2, 2, "C", "f04"),  # decoy d2, unreported
    _finding("duplication", "tests/fixtures/seed.py", 4, 5, "B", "f05"),  # decoy d1
    _finding("dead-code", "src/pay/__init__.py", 1, 1, "A", "f06"),  # decoy d4 at tier A
    _finding("pipeline-infra", "Dockerfile", 1, 1, "A", "f07"),  # p8
    _finding("ownership", "src/pay/refund.py", None, None, "A", "f08"),  # p7, file-level
    _finding("pipeline-infra", None, None, None, "A", "f09"),  # p19, repository-level
    _finding("security", "src/pay/gateway.py", 26, 26, "B", "f10"),  # unplanted
]
RANKED = {"schema_version": 2, "top_n": ["f01", "f06", "f07", "f08", "f09"]}


@pytest.fixture
def planted() -> dict[str, Any]:
    path = CORPUS_ROOT / "service-py" / "planted.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_hits_matches_family_file_and_overlap() -> None:
    item = {"family": "security", "path": "src/pay/gateway.py", "lines": [20, 25]}
    assert hits(_finding("security", "src/pay/gateway.py", 24, 24, "B", "x"), item)
    assert hits(_finding("security", "src/pay/gateway.py", 18, 21, "B", "x"), item)
    assert not hits(_finding("security", "src/pay/gateway.py", 26, 26, "B", "x"), item)
    assert not hits(_finding("half-finished", "src/pay/gateway.py", 24, 24, "B", "x"), item)
    assert hits(_finding("security", "src/pay/gateway.py", None, None, "B", "x"), item)
    repo_level = {"family": "pipeline-infra", "path": None, "lines": [0, 0]}
    assert hits(_finding("pipeline-infra", None, None, None, "A", "x"), repo_level)
    assert not hits(_finding("pipeline-infra", "Dockerfile", 1, 1, "A", "x"), repo_level)
    no_lines = {"family": "duplication", "path": "tests/fixtures/seed.py"}
    assert hits(_finding("duplication", "tests/fixtures/seed.py", 9, 9, "B", "x"), no_lines)


def test_evaluate_per_family_precision_recall_and_decoys(planted: dict[str, Any]) -> None:
    report = evaluate(VERIFIED, planted, set(RANKED["top_n"]), top=5)
    families = report["families"]
    assert families["error-masking"] == {
        "planted": 1, "found": 1, "recall": 1.0, "reported": 1, "precise": 1, "precision": 1.0,
        "decoy_hits": {"A": 0, "B": 0, "C": 0},
    }
    security = families["security"]
    assert (security["planted"], security["found"], security["recall"]) == (5, 1, 0.2)
    assert (security["reported"], security["precise"], security["precision"]) == (2, 1, 0.5)
    assert security["decoy_hits"] == {"A": 0, "B": 0, "C": 1}
    assert families["dead-code"]["precision"] == 0.0
    assert families["dead-code"]["decoy_hits"] == {"A": 1, "B": 0, "C": 0}
    assert families["duplication"]["planted"] == 0
    assert families["duplication"]["recall"] is None
    assert families["duplication"]["decoy_hits"]["B"] == 1
    assert (families["pipeline-infra"]["found"], families["pipeline-infra"]["planted"]) == (2, 4)
    assert families["pipeline-infra"]["precision"] == 1.0
    assert families["ownership"]["recall"] == 1.0
    assert families["test-gaps"] == {
        "planted": 1, "found": 0, "recall": 0.0, "reported": 0, "precise": 0, "precision": None,
        "decoy_hits": {"A": 0, "B": 0, "C": 0},
    }
    by_id = {item["id"]: item for item in report["planted"]}
    assert by_id["p1"] == {"id": "p1", "family": "error-masking", "found": True,
                           "tiers": ["A"], "tier_met": True}
    assert by_id["p4"]["found"] is False
    assert by_id["p19"]["found"] is True
    decoys = {item["id"]: item for item in report["decoys"]}
    assert decoys["d4"] == {"id": "d4", "family": "dead-code", "hit_tiers": ["A"],
                            "in_top_n": True}
    assert decoys["d1"]["hit_tiers"] == ["B"] and decoys["d1"]["in_top_n"] is False
    assert decoys["d2"]["hit_tiers"] == ["C"]
    assert report["decoys_in_tier_a"] == 1
    assert report["decoys_in_top_n"] == 1
    assert report["counts"] == {"reported": 9, "on_planted": 6, "on_decoys": 2, "unplanted": 1}
    assert report["top"] == 5
    assert report["schema_version"] == 2
    assert report["churn_months"] == 240  # the window service-py records


def test_tier_a_precision_counts_only_tier_a_findings(planted: dict[str, Any]) -> None:
    # The phase gate is tier A precision; the per-family "reported" figures span A and B.
    findings = [
        _finding("error-masking", "src/pay/refund.py", 31, 34, "A", "a1"),  # planted p1
        _finding("security", "src/pay/gateway.py", 26, 26, "A", "a2"),  # unplanted
        _finding("security", "src/pay/gateway.py", 11, 11, "B", "b1"),  # planted p3
    ]
    report = evaluate(findings, planted, set(), top=5)
    assert report["tier_a"] == {"reported": 2, "precise": 1, "precision": 0.5}
    keys = list(report)
    assert keys[keys.index("decoys_in_top_n") + 1] == "tier_a"
    assert keys[keys.index("tier_a") + 1] == "counts"
    assert "tier A precision: 0.50 (1/2)" in render_table(report).splitlines()


def test_churn_months_is_null_when_the_fixture_records_no_window() -> None:
    report = evaluate([], {"planted": [], "decoys": []}, set(), top=5)
    assert report["churn_months"] is None
    assert render_table(report).splitlines()[0] == "scored at churn_months (unrecorded)"


def test_tier_met_uses_the_best_hitting_tier(planted: dict[str, Any]) -> None:
    findings = [
        _finding("error-masking", "src/pay/refund.py", 31, 34, "C", "a"),
        _finding("error-masking", "src/pay/refund.py", 32, 33, "B", "b"),
    ]
    report = evaluate(findings, planted, set(), top=5)
    p1 = next(item for item in report["planted"] if item["id"] == "p1")
    assert p1["found"] is True
    assert p1["tiers"] == ["B", "C"]
    assert p1["tier_met"] is False  # expect_tier A, best tier B


def test_load_findings_prefers_findings_json_and_accepts_shapes(tmp_path: Path) -> None:
    write_json(tmp_path / "verified.json", {"candidates": VERIFIED})
    findings, source = load_findings(tmp_path)
    assert source == "verified.json" and len(findings) == 10
    write_json(tmp_path / "findings.json", {"findings": VERIFIED[:3]})
    findings, source = load_findings(tmp_path)
    assert source == "findings.json" and len(findings) == 3
    (tmp_path / "findings.json").write_bytes(json.dumps(VERIFIED[:2]).encode("utf-8"))
    findings, _ = load_findings(tmp_path)
    assert len(findings) == 2


def test_render_table_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from evaluate import _main

    workdir = tmp_path / "wd"
    write_json(workdir / "verified.json", {"candidates": VERIFIED})
    write_json(workdir / "ranked.json", RANKED)
    planted_path = CORPUS_ROOT / "service-py" / "planted.json"
    assert _main(["--planted", str(planted_path), "--workdir", str(workdir)]) == 0
    out = capsys.readouterr().out
    assert "error-masking" in out and "decoys in tier A: 1" in out and "decoys in top 5: 1" in out
    assert _main(["--planted", str(planted_path), "--workdir", str(workdir), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source"] == "verified.json"
    assert report["decoys_in_top_n"] == 1
    table = render_table(report)
    lines = table.splitlines()
    assert lines[0] == "scored at churn_months 240"
    assert lines[1].startswith("family")
    header_width = len(lines[1])
    family_rows = lines[2:-4]  # 2 header lines, one row per family, 4 tail rows
    assert len(family_rows) == len(report["families"])
    assert all(len(line) == header_width for line in family_rows)  # decoys pad as one column
    assert lines[1].endswith("decoy A/B/C")
    assert next(line for line in lines if line.startswith("dead-code")).endswith("1/0/0")


def test_cli_missing_inputs_exit_2(tmp_path: Path) -> None:
    from evaluate import _main

    planted_path = CORPUS_ROOT / "service-py" / "planted.json"
    assert _main(["--planted", str(planted_path), "--workdir", str(tmp_path)]) == 2
    write_json(tmp_path / "verified.json", {"candidates": []})
    assert _main(["--planted", str(tmp_path / "none.json"), "--workdir", str(tmp_path)]) == 2


def test_multiple_reported_findings_on_same_planted_item(
    planted: dict[str, Any],
) -> None:
    # Two reported findings both hit the same planted item: item found once, both count precision.
    findings = [
        _finding("error-masking", "src/pay/refund.py", 31, 34, "A", "f01"),
        _finding("error-masking", "src/pay/refund.py", 32, 33, "B", "f02"),
    ]
    report = evaluate(findings, planted, set(), top=5)
    p1 = next(item for item in report["planted"] if item["id"] == "p1")
    assert p1["found"] is True
    assert p1["tiers"] == ["A", "B"]
    fam = report["families"]["error-masking"]
    assert fam["found"] == 1  # planted item p1 found once
    assert fam["reported"] == 2  # two findings reported
    assert fam["precise"] == 2  # both count toward precision


def test_finding_with_multiple_evidence_items_second_matches(
    planted: dict[str, Any],
) -> None:
    # Finding with multiple evidence items: first non-matching, second matches planted item.
    finding = {
        "fingerprint": "f_test",
        "family": "error-masking",
        "tier": "A",
        "evidence": [
            {"file": "wrong/path.py", "line_start": 1, "line_end": 1,
             "quote": "q", "quote_verified": True},
            {"file": "src/pay/refund.py", "line_start": 31, "line_end": 34,
             "quote": "q", "quote_verified": True},
        ],
    }
    report = evaluate([finding], planted, set(), top=5)
    p1 = next(item for item in report["planted"] if item["id"] == "p1")
    assert p1["found"] is True
    assert "A" in p1["tiers"]
