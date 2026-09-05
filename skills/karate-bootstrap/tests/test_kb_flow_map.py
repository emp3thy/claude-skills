from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import (
    find_entry,
    load_ledger,
    main,
    mark_entry,
    merge_entry,
    next_entry,
    save_ledger,
    validate,
    verify_refs,
)
from kb_common import EXIT_MISSING_OUTPUT, EXIT_VALIDATION, KbError, read_json
from kb_helpers import line_of

FIXTURES = Path(__file__).parent / "fixtures"
SPRING = FIXTURES / "spring-mini"
SERVICE = "src/main/java/com/acme/shipments/ShipmentService.java"
LISTENER = "src/main/java/com/acme/shipments/ShipmentEventsListener.java"


@pytest.fixture()
def spring_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger_path = tmp_path / "flow-map.yaml"
    assert detect_main([str(SPRING), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(SPRING), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger_path)]) == 0
    return ledger_path, load_ledger(ledger_path)


def post_trace() -> dict[str, Any]:
    return {
        "id": "POST /api/shipments",
        "auth": "required",
        "request": {"content_type": "application/json",
                    "schema_ref": "src/main/java/com/acme/shipments/ShipmentRequest.java",
                    "example": "seed/examples/post-api-shipments.json"},
        "responses": [
            {"status": 201, "when": "happy"},
            {"status": 400, "when": "validation", "rules": True},
            {"status": 400, "when": "weight over 1000kg",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'weight exceeds')}"},
        ],
        "reads": [
            {"kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET",
             "path": "/rates/{countryCode}"},
        ],
        "exits": [
            {"kind": "db-write", "table": "shipments", "op": "insert",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'repository.save')}"},
            {"kind": "amq-publish", "destination": "shipment.created", "type": "queue",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'convertAndSend')}"},
            {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET",
             "path": "/rates/{countryCode}",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'getForObject')}"},
        ],
        "rules": {"sources": [{"file": "src/main/java/com/acme/shipments/ShipmentRequest.java",
                               "scanned": False}]},
        "unresolved": [],
    }


def test_load_ledger_missing_is_exit_5(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        load_ledger(tmp_path / "nope.yaml")
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT


def test_load_ledger_rejects_wrong_version(tmp_path: Path) -> None:
    path = tmp_path / "flow-map.yaml"
    path.write_text("version: 99\nentry_points: []\nunresolved: []\n", encoding="utf-8")
    with pytest.raises(KbError, match="version"):
        load_ledger(path)


def test_next_entry_walks_untraced_then_ungenerated(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    first = next_entry(ledger, "traced")
    assert first is not None
    assert first["id"] == "POST /api/shipments"
    assert first["cheat_sheet"] == "reference/stack-spring.md"
    assert first["handler"].startswith("src/main/java/com/acme/shipments/ShipmentController.java:")
    assert next_entry(ledger, "generated") is None  # nothing traced yet
    for entry in ledger["entry_points"]:
        entry["status"]["traced"] = True
    assert next_entry(ledger, "traced") is None
    assert next_entry(ledger, "generated") is not None


def test_merge_entry_sets_traced_and_replaces_fields(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    path, ledger = spring_ledger
    assert merge_entry(ledger, post_trace()) == 0
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is True
    assert [e["kind"] for e in entry["exits"]] == ["db-write", "amq-publish", "http-out"]
    assert entry["rules"]["sources"][0]["file"].endswith("ShipmentRequest.java")
    assert entry["rules"]["count"] == 0  # untouched by merge
    save_ledger(path, ledger)
    assert load_ledger(path)["entry_points"][0]["status"]["traced"] is True


def test_merge_entry_with_unresolved_stays_untraced(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["unresolved"] = [{"at": f"{SERVICE}:31", "reason": "Shipment.from is a static factory"}]
    assert merge_entry(ledger, traced) == 1
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is False
    assert ledger["unresolved"] == [{"entry": "POST /api/shipments", "at": f"{SERVICE}:31",
                                     "reason": "Shipment.from is a static factory"}]
    # a re-trace that resolves it clears only this entry's unresolved items
    assert merge_entry(ledger, post_trace()) == 0
    assert ledger["unresolved"] == []


def test_merge_entry_requires_exits_or_reason(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = {"id": "GET /api/shipments/{id}", "exits": [], "reads": [
        {"kind": "db-read", "table": "shipments", "via": f"{SERVICE}:37"}], "unresolved": []}
    assert merge_entry(ledger, traced) == 0
    assert find_entry(ledger, "GET /api/shipments/{id}")["status"]["traced"] is False
    traced["exits_none_reason"] = "read-only lookup"
    merge_entry(ledger, traced)
    assert find_entry(ledger, "GET /api/shipments/{id}")["status"]["traced"] is True


def test_merge_entry_validates_exit_shape(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"] = [{"kind": "db-write", "table": "shipments", "op": "insert"}]  # no via
    with pytest.raises(KbError, match="via"):
        merge_entry(ledger, traced)
    traced["exits"] = [{"kind": "db-write", "table": "shipments", "via": f"{SERVICE}:32"}]
    with pytest.raises(KbError, match="missing"):
        merge_entry(ledger, traced)
    traced["exits"] = [{"kind": "teleport", "via": f"{SERVICE}:32"}]
    with pytest.raises(KbError, match="kind"):
        merge_entry(ledger, traced)


def test_merge_entry_unknown_id(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    with pytest.raises(KbError, match="unknown entry"):
        merge_entry(ledger, {"id": "DELETE /nope", "exits": [], "unresolved": []})


def test_mark_entry(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    mark_entry(ledger, "POST /api/shipments", "stubbed")
    assert find_entry(ledger, "POST /api/shipments")["status"]["stubbed"] is True
    with pytest.raises(KbError, match="flag"):
        mark_entry(ledger, "POST /api/shipments", "verified")


def test_cli_next_merge_mark(spring_ledger: tuple[Path, dict[str, Any]],
                             tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path, _ = spring_ledger
    assert main(["next", "--phase", "traced", "--ledger", str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["id"] == "POST /api/shipments"
    trace_file = tmp_path / "entry.json"
    trace_file.write_text(json.dumps(post_trace()), encoding="utf-8")
    assert main(["merge", str(trace_file), "--ledger", str(path)]) == 0
    assert "unresolved: 0" in capsys.readouterr().out
    mark_result = main(
        ["mark", "--entry", "POST /api/shipments", "--generated", "--ledger", str(path)]
    )
    assert mark_result == 0
    reloaded = load_ledger(path)
    assert reloaded["entry_points"][0]["status"] == {"traced": True, "stubbed": True,
                                                     "tested": False, "passing": False}


def _trace_all(ledger: dict[str, Any]) -> None:
    merge_entry(ledger, post_trace())
    merge_entry(ledger, {"id": "GET /api/shipments/{id}", "exits": [],
                         "exits_none_reason": "read-only lookup", "unresolved": [],
                         "responses": [{"status": 200, "when": "found"},
                                       {"status": 404, "when": "missing"}]})
    merge_entry(ledger, {
        "id": "amq shipment.requested", "unresolved": [],
        "exits": [{"kind": "db-write", "table": "shipments", "op": "insert",
                   "via": f"{LISTENER}:{line_of(SPRING / LISTENER, 'repository.save')}"}],
    })


def test_verify_refs_passes_for_real_lines(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    assert verify_refs(ledger, SPRING) == []


def test_verify_refs_flags_wrong_line_and_resets_traced(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"][0]["via"] = f"{SERVICE}:1"  # package line, no write marker nearby
    merge_entry(ledger, traced)
    gaps = verify_refs(ledger, SPRING)
    assert len(gaps) == 1 and "db-write" in gaps[0] and f"{SERVICE}:1" in gaps[0]
    assert find_entry(ledger, "POST /api/shipments")["status"]["traced"] is False


def test_verify_refs_flags_missing_file(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"][0]["via"] = "src/main/java/Nope.java:3"
    merge_entry(ledger, traced)
    gaps = verify_refs(ledger, SPRING)
    assert gaps and "does not exist" in gaps[0]


def test_validate_traced_lists_gaps_then_passes(spring_ledger: tuple[Path, dict[str, Any]],
                                                tmp_path: Path) -> None:
    path, ledger = spring_ledger
    env_map = read_json(path.parent / "env-map.json")
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert len(gaps) == 3 and all("not traced" in g for g in gaps)
    _trace_all(ledger)
    assert validate(ledger, "traced", SPRING, env_map, None, None, None) == []


def test_validate_traced_flags_unknown_host_key_and_unscanned_rules(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    path, ledger = spring_ledger
    env_map = read_json(path.parent / "env-map.json")
    _trace_all(ledger)
    entry = find_entry(ledger, "POST /api/shipments")
    entry["exits"][2]["host_key"] = "NOT_A_KEY"
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert any("NOT_A_KEY" in g for g in gaps)
    entry["exits"][2]["host_key"] = "PRICING_BASE_URL"
    entry["rules"]["sources"][0]["scanned"] = False
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert gaps == []  # scanned is a Phase 3 concern, checked in the generated gate


def _fake_generated(tmp_path: Path, ledger: dict[str, Any], feature_text: str) -> Path:
    tests_dir = tmp_path / "karate-tests"
    features = tests_dir / "src/test/resources/features"
    features.mkdir(parents=True)
    (features / "post-api-shipments.feature").write_text(feature_text, encoding="utf-8")
    (tests_dir / "stubs/post-api-shipments").mkdir(parents=True)
    (tests_dir / "stubs/post-api-shipments/pricing.json").write_text("[]", encoding="utf-8")
    (tests_dir / "rules").mkdir()
    (tests_dir / "rules/post-api-shipments.csv").write_text(
        "rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source\n"
        "R001,reference,missing,,400,VALIDATION,,x:1\n",
        encoding="utf-8",
    )
    entry = find_entry(ledger, "POST /api/shipments")
    entry["features"] = ["features/post-api-shipments.feature"]
    entry["stubs"] = ["stubs/post-api-shipments/pricing.json"]
    entry["rules"].update({"file": "rules/post-api-shipments.csv", "count": 1})
    entry["rules"]["sources"][0]["scanned"] = True
    entry["status"]["stubbed"] = True
    for other in ("GET /api/shipments/{id}", "amq shipment.requested"):
        o = find_entry(ledger, other)
        o["features"] = ["features/post-api-shipments.feature"]
        o["status"]["stubbed"] = True
    return tests_dir


GOOD_FEATURE = """Feature: POST /api/shipments
Scenario: happy
  * def row = Db.row('shipments', { reference: 'x' })
  * def msg = Jms.await('shipment.created', 5000)
  * Stubs.verify('GET', '/rates/GB', 1)
"""


def test_validate_generated_passes_with_markers(spring_ledger: tuple[Path, dict[str, Any]],
                                                tmp_path: Path) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, GOOD_FEATURE)
    assert validate(ledger, "generated", SPRING, None, tests_dir, None, None) == []


def test_validate_generated_flags_missing_assertions_and_count(
    spring_ledger: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, "Feature: POST /api/shipments\nScenario: x\n")
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert any("Db." in g and "shipments" in g for g in gaps)
    assert any("Jms." in g and "shipment.created" in g for g in gaps)
    assert any("Stubs.verify" in g for g in gaps)
    find_entry(ledger, "POST /api/shipments")["rules"]["count"] = 5
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert any("rules" in g and "5" in g and "1" in g for g in gaps)


def test_validate_green(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    find_entry(ledger, "POST /api/shipments")["features"] = ["features/post-api-shipments.feature"]
    for entry in ledger["entry_points"]:
        entry["status"].update({"stubbed": True, "tested": True, "passing": True})
    report = {"passed": 10, "skipped": 1, "failed": []}
    assert validate(ledger, "green", SPRING, None, None, report, "") == []
    report["failed"] = [{"feature": "features/post-api-shipments.feature",
                         "scenario": "over weight", "tags": ["@error"], "step": "status 400",
                         "error": "expected 400 got 500"}]
    gaps = validate(ledger, "green", SPRING, None, None, report, "")
    assert gaps == ["features/post-api-shipments.feature: 'over weight' failed and is not "
                    "quarantined with @known-defect"]
    report["failed"][0]["tags"] = ["@error", "@known-defect"]
    gaps = validate(ledger, "green", SPRING, None, None, report, "")
    assert gaps and "defects.md" in gaps[0]
    defects = "## DEF-001: over weight 500\nstatus: pending\nentry_point: POST /api/shipments\n"
    find_entry(ledger, "POST /api/shipments")["status"]["passing"] = False
    assert validate(ledger, "green", SPRING, None, None, report, defects) == []


def test_validate_green_requires_the_owning_entry_in_defects(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    for entry in ledger["entry_points"]:
        entry["features"] = [f"features/{slug}.feature" for slug in [entry["id"].lower()
                             .replace(" ", "-").replace("/", "-").replace("{", "")
                             .replace("}", "")]]
        entry["status"].update({"stubbed": True, "tested": True, "passing": True})
    post = find_entry(ledger, "POST /api/shipments")
    post["features"] = ["features/post-api-shipments.feature"]
    post["status"]["passing"] = False
    report = {"passed": 5, "skipped": 0, "failed": [{
        "feature": "features/post-api-shipments.feature", "scenario": "over weight",
        "tags": ["@error", "@known-defect"], "step": "status 400", "error": "500"}]}
    unrelated = "## DEF-001: x\nstatus: pending\nentry_point: GET /api/shipments/{id}\n"
    gaps = validate(ledger, "green", SPRING, None, None, report, unrelated)
    assert any("defects.md has no entry for POST /api/shipments" in g for g in gaps)
    assert any("POST /api/shipments: not passing" in g for g in gaps)
    matching = "## DEF-001: x\nstatus: pending\nentry_point: POST /api/shipments\n"
    assert validate(ledger, "green", SPRING, None, None, report, matching) == []


def test_validate_green_flags_unowned_feature(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    for entry in ledger["entry_points"]:
        entry["status"].update({"stubbed": True, "tested": True, "passing": True})
    report = {"passed": 1, "skipped": 0, "failed": [{
        "feature": "features/orphan.feature", "scenario": "x", "tags": ["@known-defect"],
        "step": "s", "error": "e"}]}
    defects_text = "entry_point: POST /api/shipments\n"
    gaps = validate(ledger, "green", SPRING, None, None, report, defects_text)
    assert gaps == ["features/orphan.feature: 'x' is quarantined but no ledger entry owns "
                    "features/orphan.feature"]


def test_validate_green_flags_not_passing_without_defect(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    for entry in ledger["entry_points"]:
        entry["status"].update({"stubbed": True, "tested": True, "passing": True})
    find_entry(ledger, "amq shipment.requested")["status"]["passing"] = False
    report = {"passed": 9, "skipped": 0, "failed": []}
    gaps = validate(ledger, "green", SPRING, None, None, report, "")
    assert gaps == ["amq shipment.requested: not passing and not listed in defects.md"]


def test_validate_generated_flags_unscanned_source(spring_ledger: tuple[Path, dict[str, Any]],
                                                   tmp_path: Path) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, GOOD_FEATURE)
    find_entry(ledger, "POST /api/shipments")["rules"]["sources"][0]["scanned"] = False
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert gaps == ["POST /api/shipments: rules source "
                    "src/main/java/com/acme/shipments/ShipmentRequest.java not scanned"]


def test_cli_validate_and_verify_refs_exit_codes(spring_ledger: tuple[Path, dict[str, Any]],
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    path, ledger = spring_ledger
    env = path.parent / "env-map.json"
    assert main(["validate", "--phase", "traced", "--ledger", str(path), "--repo", str(SPRING),
                 "--env", str(env)]) == EXIT_VALIDATION
    assert "not traced" in capsys.readouterr().out
    _trace_all(ledger)
    save_ledger(path, ledger)
    assert main(["validate", "--phase", "traced", "--ledger", str(path), "--repo", str(SPRING),
                 "--env", str(env)]) == 0
    assert main(["verify-refs", "--ledger", str(path), "--repo", str(SPRING)]) == 0
