from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger, main, mark_entry, merge_entry, next_entry, save_ledger
from kb_common import EXIT_MISSING_OUTPUT, KbError
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
