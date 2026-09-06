from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from kb_common import EXIT_STOPPED, KbError, run_cli
from kb_iterate import (
    CLASSIFICATIONS,
    REPEAT_LIMIT,
    append_log,
    check_stop,
    error_class,
    evidence,
    group_failures,
    main,
    read_log,
    signature,
)

ERROR = ("match failed: EQUALS\n  $ | not equal | match failed for name: 'a' (MAP:MAP)\n"
         "  {\"a\":1}\n  {\"a\":2}\n\nclasspath:features/failing-probe.feature:6")


def _failure(scenario: str, outline: bool = False, error: str = ERROR,
             step: str = "* match x == { a: 2 }",
             feature: str = "features/f.feature") -> dict[str, Any]:
    return {"feature": feature, "scenario": scenario, "outline": outline, "tags": ["@rules"],
            "step": step, "error": error}


def test_error_class_normalises_numbers_quotes_and_urls() -> None:
    assert error_class(ERROR) == "match failed: EQUALS"
    assert error_class("status code was: 500, expected: 201, response: http://app:8080/api/x") == (
        "status code was: N, expected: N, response: URL"
    )
    assert error_class("no row in deals matching {external_id='EXT-42'} within 5000ms") == (
        "no row in deals matching {external_id='?'} within Nms"
    )
    assert error_class("") == ""


def test_signature_collapses_outline_rows_but_not_plain_scenarios() -> None:
    plain_a = signature(_failure("a"))
    plain_b = signature(_failure("b"))
    assert plain_a != plain_b
    assert signature(_failure("rule R001 on x", outline=True)) == signature(
        _failure("rule R002 on y", outline=True)
    )
    assert signature(_failure("a")) == (
        "features/f.feature|a|* match x == { a: 2 }|match failed: EQUALS"
    )


def test_group_failures_orders_by_count_then_first_seen() -> None:
    report = {"passed": 1, "skipped": 0, "failed": [
        _failure("only once"),
        _failure("rule R001", outline=True),
        _failure("rule R002", outline=True),
        _failure("rule R003", outline=True),
        _failure("other", error="status code was: 500"),
    ]}
    groups = group_failures(report)
    assert [g["count"] for g in groups] == [3, 1, 1]
    assert groups[0]["scenario"] == "rule R001"
    assert groups[0]["error_class"] == "match failed: EQUALS"
    assert groups[1]["scenario"] == "only once"
    assert groups[2]["error_class"] == "status code was: N"


def test_evidence_reads_logs_and_unmatched_when_present(tmp_path: Path) -> None:
    assert evidence(tmp_path) == {"app_log_tail": None, "db_manager_log_tail": None,
                                  "stubs_unmatched": None}
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.log").write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    (target / "db-manager.log").write_text("migrated", encoding="utf-8")
    (target / "stubs-unmatched.json").write_text(
        json.dumps({"unmatched": {"requests": [{"url": "/pricing/rates/GB"}]}, "nearMisses": {}}),
        encoding="utf-8")
    bundle = evidence(tmp_path)
    assert bundle["app_log_tail"].splitlines()[0] == "line 20"
    assert bundle["app_log_tail"].splitlines()[-1] == "line 99"
    assert bundle["db_manager_log_tail"] == "migrated"
    assert bundle["stubs_unmatched"]["unmatched"]["requests"][0]["url"] == "/pricing/rates/GB"


def test_log_appends_numbered_records(tmp_path: Path) -> None:
    log = tmp_path / ".iterations.log"
    assert read_log(log) == []
    assert append_log(log, {"signature": "s1", "hypothesis": "h", "change": "c",
                            "classification": "infra", "unfixable": False}) == 1
    assert append_log(log, {"signature": "s2", "hypothesis": "h", "change": "c",
                            "classification": "expectation", "unfixable": False}) == 2
    records = read_log(log)
    assert [r["iteration"] for r in records] == [1, 2]
    assert records[0]["signature"] == "s1" and "at" in records[0]
    with pytest.raises(KbError):
        append_log(log, {"signature": "s3", "classification": "nope"})


def test_check_stop_rules() -> None:
    failing = {"passed": 1, "skipped": 0, "failed": [_failure("a")]}
    green = {"passed": 2, "skipped": 0, "failed": []}
    rec = [{"iteration": i, "signature": s, "classification": "expectation", "unfixable": False}
           for i, s in enumerate(["s1", "s2", "s3"], start=1)]
    assert check_stop([], failing, 15) == "continue"
    assert check_stop(rec, failing, 15) == "continue"
    assert check_stop(rec, green, 15) == "done"
    assert check_stop(rec, failing, 3) == "stop:iteration-cap 3"
    same = [dict(r, signature="same") for r in rec]
    assert REPEAT_LIMIT == 3
    assert check_stop(same, failing, 15) == "stop:repeated-signature same"
    assert check_stop(same[:2], failing, 15) == "continue"
    stuck = rec + [{"iteration": 4, "signature": "s4", "classification": "infra",
                    "unfixable": True}]
    assert check_stop(stuck, failing, 15) == "stop:infra-unfixable"
    assert set(CLASSIFICATIONS) == {"infra", "stub-or-seed", "expectation", "app-defect"}


def test_cli_next_log_check_stop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tests_dir = tmp_path / "karate-tests"
    (tests_dir / "target").mkdir(parents=True)
    (tests_dir / "target" / "app.log").write_text("boom", encoding="utf-8")
    report = tests_dir / "target" / "report.json"
    report.write_text(json.dumps({"passed": 0, "skipped": 0, "failed": [
        _failure("rule R001", outline=True), _failure("rule R002", outline=True),
    ]}), encoding="utf-8")
    assert run_cli(main, ["next", "--report", str(report), "--tests-dir", str(tests_dir)]) == 0
    top = json.loads(capsys.readouterr().out)
    assert top["count"] == 2 and top["groups"] == 1
    assert top["evidence"]["app_log_tail"] == "boom"
    log = tests_dir / ".iterations.log"
    for _ in range(3):
        assert run_cli(main, ["log", "--log", str(log), "--signature", top["signature"],
                              "--hypothesis", "mutation value off by one", "--change", "rules csv",
                              "--classification", "expectation"]) == 0
    capsys.readouterr()
    assert run_cli(main, ["check-stop", "--log", str(log), "--report", str(report),
                          "--max-iterations", "15"]) == EXIT_STOPPED
    assert capsys.readouterr().out.startswith("stop:repeated-signature")
    report.write_text(json.dumps({"passed": 5, "skipped": 0, "failed": []}), encoding="utf-8")
    assert run_cli(main, ["check-stop", "--log", str(log), "--report", str(report),
                          "--max-iterations", "15"]) == 0
    assert capsys.readouterr().out.strip() == "done"
    assert run_cli(main, ["next", "--report", str(report), "--tests-dir", str(tests_dir)]) == 0
    assert json.loads(capsys.readouterr().out) == {"done": True}
    with pytest.raises(SystemExit) as excinfo:  # argparse rejects a value outside choices
        main(["log", "--log", str(log), "--signature", "x", "--hypothesis", "h",
              "--change", "c", "--classification", "bogus"])
    assert excinfo.value.code == 2
