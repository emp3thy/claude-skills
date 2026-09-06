from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger
from kb_common import EXIT_MISSING_OUTPUT, KbError, read_json, run_cli
from kb_iterate import group_failures
from kb_report import (
    counts_table,
    defect_titles,
    main,
    parse_reports,
    render_summary,
    summary_values,
)

FIXTURES = Path(__file__).parent / "fixtures"
REPORTS = FIXTURES / "karate-reports"
FEATURES = FIXTURES / "features-known-defect"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests" / "README.md.tmpl"
DEFECTS = (
    "# Suspected application defects\n\n"
    "## DEF-001: POST /api/shipments returns 500 for an unknown carrier\n"
    "status: pending\nslug: post-api-shipments-500-unknown-carrier\nseverity: high\n"
    "category: app-defect\nentry_point: POST /api/shipments\n"
    "scenario: features/post-api-shipments.feature:40\n"
    "evidence: |\n  response: 500\nroot_cause: ShipmentService.java:33 dereferences null\n"
    "suggested_fix: return 422\n\n"
    "## DEF-002: GET /api/shipments/{id} leaks stack trace\n"
    "status: pending\nentry_point: GET /api/shipments/{id}\n"
)


def test_parse_reports_reads_every_cucumber_json_and_counts_known_defects() -> None:
    report = parse_reports(REPORTS, FEATURES)
    assert report["passed"] == 2
    assert report["skipped"] == 1
    assert [f["scenario"] for f in report["failed"]] == ["a failing match", "outline row R2"]
    first = report["failed"][0]
    assert first == {
        "feature": "features/failing-probe.feature",
        "scenario": "a failing match",
        "outline": False,
        "tags": ["@probe"],
        "step": "* match x == { a: 2 }",
        "error": first["error"],
    }
    assert first["error"].startswith("match failed: EQUALS")
    assert first["error"].endswith("classpath:features/failing-probe.feature:6")
    assert report["failed"][1]["outline"] is True
    assert report["failed"][1]["step"] == "* match 1 == 3"


def test_parse_reports_without_features_dir_reports_zero_skipped(tmp_path: Path) -> None:
    assert parse_reports(REPORTS, tmp_path / "absent")["skipped"] == 0
    assert parse_reports(REPORTS, None)["skipped"] == 0


def test_parse_reports_without_target_dir_is_exit_5(tmp_path: Path) -> None:
    # target/ missing: mvn test never ran, so the postcondition really is absent.
    with pytest.raises(KbError) as excinfo:
        parse_reports(tmp_path / "target" / "karate-reports", None)
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT
    assert "never ran" in str(excinfo.value)


def test_parse_reports_with_no_feature_json_reports_a_startup_failure(tmp_path: Path) -> None:
    # target/ exists but Karate wrote nothing: the app never came up (spec 5.7 infra).
    target = tmp_path / "target"
    reports = target / "karate-reports"
    reports.mkdir(parents=True)
    (reports / "karate-summary-json.txt").write_text("{}", encoding="utf-8")
    (target / "app.log").write_text(
        "\n".join(f"line {n}" for n in range(1, 61)) + "\n", encoding="utf-8")
    report = parse_reports(reports, None)
    assert (report["passed"], report["skipped"]) == (0, 0)
    assert len(report["failed"]) == 1
    failure = report["failed"][0]
    assert failure["feature"] == "(startup)"
    assert failure["scenario"] == "containers and application start"
    assert failure["outline"] is False and failure["tags"] == []
    assert failure["step"] == "Containers.start"
    assert failure["error"].splitlines() == [f"line {n}" for n in range(21, 61)]  # last 40


def test_startup_failure_falls_back_to_db_manager_log_then_a_fixed_message(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    (target / "karate-reports").mkdir(parents=True)
    assert parse_reports(target / "karate-reports", None)["failed"][0]["error"] == (
        "no karate reports were produced")
    (target / "db-manager.log").write_text("migration failed: relation exists\n", encoding="utf-8")
    assert "relation exists" in parse_reports(target / "karate-reports", None)["failed"][0]["error"]
    (target / "app.log").write_text("app refused to bind :8080\n", encoding="utf-8")
    assert "refused to bind" in parse_reports(target / "karate-reports", None)["failed"][0]["error"]


def test_startup_failure_groups_as_one_infra_iteration(tmp_path: Path) -> None:
    """The synthetic failure is a normal report entry, so kb_iterate.py next groups it."""
    target = tmp_path / "target"
    (target / "karate-reports").mkdir(parents=True)
    (target / "app.log").write_text("Caused by: java.net.ConnectException\n", encoding="utf-8")
    report = parse_reports(target / "karate-reports", None)
    groups = group_failures(report)
    assert len(groups) == 1 and groups[0]["count"] == 1
    assert groups[0]["feature"] == "(startup)"


def _spring_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = FIXTURES / "spring-mini"
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return ledger, load_ledger(ledger)


def test_defect_titles_reads_headings() -> None:
    assert defect_titles(DEFECTS) == [
        "DEF-001: POST /api/shipments returns 500 for an unknown carrier",
        "DEF-002: GET /api/shipments/{id} leaks stack trace",
    ]
    assert defect_titles("") == []


def test_summary_values_and_render(tmp_path: Path) -> None:
    _, ledger = _spring_ledger(tmp_path)
    post = find_entry(ledger, "POST /api/shipments")
    post["exits"] = [
        {"kind": "db-write", "table": "shipments", "op": "insert", "via": "x:1"},
        {"kind": "amq-publish", "destination": "shipment.created", "type": "queue", "via": "x:2"},
        {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET", "path": "/rates/{c}",
         "via": "x:3"},
    ]
    post["rules"].update({"file": "rules/post-api-shipments.csv", "count": 12})
    post["observed_overrides"] = [{"scenario": "happy", "field": "status", "old": 201, "new": 200}]
    ledger["app"]["migrations"]["image"] = "registry.example/db-manager:1"
    failure = {"feature": "f", "scenario": "s", "outline": False, "tags": [], "step": "x",
               "error": "e"}
    report = {"passed": 9, "skipped": 1, "failed": [failure]}
    values = summary_values(ledger, DEFECTS, report)
    assert values["repo"] == "spring-mini"
    assert values["stack"] == "spring (java)"
    assert values["entry_points"] == "3"
    assert (values["exits_db"], values["exits_amq"], values["exits_http"]) == ("1", "1", "1")
    assert values["scenarios"] == "11"
    assert values["rules_rows"] == "12"
    assert (values["passing"], values["failing"], values["quarantined"]) == ("9", "1", "1")
    assert values["auth_mode"] == "disabled"
    assert values["migrations_image"] == "registry.example/db-manager:1"
    assert values["readiness"] == "/actuator/health/readiness"
    assert "POST /api/shipments" in values["overrides"] and '"old": 201' in values["overrides"]
    assert values["defects"].splitlines() == [
        "- DEF-001: POST /api/shipments returns 500 for an unknown carrier",
        "- DEF-002: GET /api/shipments/{id} leaks stack trace",
    ]
    assert values["notes"] == "- none"
    readme = render_summary(TEMPLATE.read_text(encoding="utf-8"), values)
    assert "# Karate tests for spring-mini" in readme
    assert "| Entry points | 3 |" in readme
    assert "- DEF-001:" in readme
    assert "$" not in readme.replace("${XDG_RUNTIME_DIR}", "")
    table = counts_table(values)
    assert "Entry points" in table and "Quarantined" in table


def test_summary_values_notes_fallbacks(tmp_path: Path) -> None:
    _, ledger = _spring_ledger(tmp_path)
    ledger["app"]["readiness"] = {"path": None, "port": 8080, "source": "fallback"}
    ledger["app"]["auth"] = {"mode": "blocked"}
    ledger["app"]["migrations"]["also_on_boot"] = True
    values = summary_values(ledger, "", {"passed": 0, "skipped": 0, "failed": []})
    assert values["readiness"] == "port 8080 (fallback)"
    assert values["defects"] == "- none"
    assert values["overrides"] == "- none"
    notes = values["notes"].splitlines()
    assert any("readiness" in n for n in notes)
    assert any("blocked" in n for n in notes)
    assert any("boot" in n for n in notes)


def test_cli_parse_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "report.json"
    assert run_cli(main, ["parse", "--reports", str(REPORTS), "--out", str(out),
                          "--features", str(FEATURES)]) == 0
    report = read_json(out)
    assert (report["passed"], report["skipped"], len(report["failed"])) == (2, 1, 2)
    assert "passed: 2" in capsys.readouterr().out
    ledger_path, _ = _spring_ledger(tmp_path)
    defects = tmp_path / "defects.md"
    defects.write_text(DEFECTS, encoding="utf-8")
    readme = tmp_path / "README.md"
    assert run_cli(main, ["summary", "--ledger", str(ledger_path), "--defects", str(defects),
                          "--report", str(out), "--template", str(TEMPLATE),
                          "--out", str(readme)]) == 0
    text = readme.read_text(encoding="utf-8")
    assert "# Karate tests for spring-mini" in text and "- DEF-002:" in text
    assert "Entry points" in capsys.readouterr().out
    absent = tmp_path / "never-ran" / "target" / "karate-reports"
    assert run_cli(main, ["parse", "--reports", str(absent), "--out", str(out)]) == 5
    # target/ present but empty: exit 0 with the synthetic startup failure written out
    (tmp_path / "ran" / "target" / "karate-reports").mkdir(parents=True)
    startup_out = tmp_path / "ran" / "target" / "report.json"
    assert run_cli(main, ["parse", "--reports", str(tmp_path / "ran/target/karate-reports"),
                          "--out", str(startup_out)]) == 0
    assert read_json(startup_out)["failed"][0]["feature"] == "(startup)"
    assert "failed: 1" in capsys.readouterr().out


def test_parse_default_features_dir_is_the_module_layout(tmp_path: Path) -> None:
    module = tmp_path / "karate-tests"
    reports = module / "target" / "karate-reports"
    reports.mkdir(parents=True)
    for name in ("features.failing-probe.json", "features.harness-smoke.json"):
        (reports / name).write_text((REPORTS / name).read_text(encoding="utf-8"), encoding="utf-8")
    features = module / "src/test/resources/features"
    features.mkdir(parents=True)
    (features / "x.feature").write_text((FEATURES / "failing-probe.feature").read_text("utf-8"),
                                        encoding="utf-8")
    out = module / "target" / "report.json"
    assert run_cli(main, ["parse", "--reports", str(reports), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["skipped"] == 1
