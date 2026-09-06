from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger, merge_entry
from kb_common import EXIT_OK, KbError, read_json, run_cli
from kb_features import parse_feature, unsafe_parallel_scenarios
from kb_prompt import PROMPTS, PROMPTS_DIR, build_context, main, render
from kb_rules import add_rows

FIXTURES = Path(__file__).parent / "fixtures"
SPRING = FIXTURES / "spring-mini"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
REQUEST = "src/main/java/com/acme/shipments/ShipmentRequest.java"
_PLACEHOLDER_RE = re.compile(r"\$[a-z_]")


@pytest.fixture()
def analysed(tmp_path: Path) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(SPRING), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(SPRING), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return ledger, env, load_ledger(ledger), read_json(env)


def _block(text: str, heading: str, fence: str) -> str:
    """The first fenced block of the given language after a heading line."""
    start = text.index(heading)
    open_tag = f"```{fence}\n"
    begin = text.index(open_tag, start) + len(open_tag)
    end = text.index("\n```", begin)
    return text[begin:end]


def test_prompt_files_exist_and_gitignore_hides_rendered_prompts() -> None:
    assert PROMPTS == ("trace", "rules", "generate")
    for name in PROMPTS:
        assert (PROMPTS_DIR / f"{name}.md").is_file()
    assert ".prompts/" in (TEMPLATE / ".gitignore").read_text(encoding="utf-8")


def test_trace_context_and_render(analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]],
                                  tmp_path: Path) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert context["slug"] == "post-api-shipments"
    assert context["cheat_sheet"].endswith("reference/stack-spring.md")
    assert Path(context["cheat_sheet"]).is_file()
    assert context["handler_path"].endswith("ShipmentController.java")
    assert "| PRICING_BASE_URL | downstream:pricing | PRICING_BASE_URL |" in context["roles"]
    assert context["downstreams"] == "pricing"
    assert context["auth_mode"] == "disabled"
    assert context["focus"] == ""
    text = render("trace", context, PROMPTS_DIR)
    assert "POST /api/shipments" in text
    assert "12 hops" in text and "unresolved" in text and "no code fence" in text
    assert _PLACEHOLDER_RE.search(text) is None


def test_trace_example_output_merges_into_the_ledger(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    text = render("trace", context, PROMPTS_DIR)
    example = json.loads(_block(text, "## Example output", "json"))
    assert example["id"] == "POST /api/shipments"
    assert merge_entry(ledger, example) == 0
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is True
    assert {e["kind"] for e in entry["exits"]} == {"db-write", "amq-publish", "http-out"}


def test_focus_adds_a_start_at_paragraph(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    context = build_context("trace", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None,
                            "src/main/java/com/acme/shipments/ShipmentService.java:30")
    assert "Start at" in context["focus"] and "ShipmentService.java:30" in context["focus"]
    assert "ShipmentService.java:30" in render("trace", context, PROMPTS_DIR)


def test_rules_context_needs_a_source_and_its_example_rows_load(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    tests_dir = tmp_path / "karate-tests"
    with pytest.raises(KbError, match="--source"):
        build_context("rules", ledger, "POST /api/shipments", env_map, SPRING, tests_dir,
                      None, None)
    context = build_context("rules", ledger, "POST /api/shipments", None, SPRING, tests_dir,
                            REQUEST, None)
    assert context["source"] == REQUEST
    assert context["source_path"].endswith(REQUEST)
    assert context["candidates_csv"].endswith("rules/post-api-shipments.candidates.csv")
    assert "not present" in context["candidates_note"]
    assert "rows_csv" not in context
    text = render("rules", context, PROMPTS_DIR)
    assert "rule_id,field,mutation,value,expected_status,expected_code," in text
    assert _PLACEHOLDER_RE.search(text) is None
    assert "before:<field>" in text
    reply = json.loads(_block(text, "## Reply", "json"))
    assert reply["csv"].startswith("rule_id,field,mutation,value,")
    assert set(reply) == {"csv", "rows", "dropped_candidates", "notes"}
    rows = tmp_path / "rows.csv"
    rows.write_text(_block(text, "## Example rows file", "csv") + "\n", encoding="utf-8")
    assert add_rows(tests_dir, ledger, "POST /api/shipments", rows) >= 3
    assert find_entry(ledger, "POST /api/shipments")["rules"]["file"] == (
        "rules/post-api-shipments.csv"
    )


def test_rules_candidates_note_counts_existing_rows(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, _ = analysed
    tests_dir = tmp_path / "karate-tests"
    candidates = tests_dir / "rules" / "post-api-shipments.candidates.csv"
    candidates.parent.mkdir(parents=True)
    candidates.write_text(
        "rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source\n"
        ",reference,missing,,400,,,x:1\n,reference,empty,,400,,,x:1\n", encoding="utf-8")
    context = build_context("rules", ledger, "POST /api/shipments", None, SPRING, tests_dir,
                            REQUEST, None)
    assert "2 candidate rows" in context["candidates_note"]


def test_generate_context_and_example_feature_is_parallel_safe(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    find_entry(ledger, "POST /api/shipments")["rules"].update(
        {"file": "rules/post-api-shipments.csv", "count": 9})
    context = build_context("generate", ledger, "POST /api/shipments", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert context["feature_file"] == "features/post-api-shipments.feature"
    assert context["seed_file"] == "seed/post-api-shipments.sql"
    assert context["example_file"] == "seed/examples/post-api-shipments.json"
    assert context["rules_file"] == "rules/post-api-shipments.csv" and context["rules_count"] == "9"
    assert "do not send an Authorization header" in context["auth_instruction"]
    assert "Given url appBaseUrl" in context["entry_instruction"]
    text = render("generate", context, PROMPTS_DIR)
    assert "@parallel=false" in text and "Jms.await(" in text and "Stubs.verify(" in text
    assert _PLACEHOLDER_RE.search(text) is None
    assert "## Cross-field rules" in text
    assert "karate.filter(" in text and "cross_field" in text
    feature = _block(text, "## Feature shape", "gherkin")
    assert "checkError(response, '<expected_code>'" in feature
    parsed = parse_feature(feature)
    assert len(parsed.scenarios()) >= 3
    assert unsafe_parallel_scenarios(feature) == []
    cross_field_scenario = _block(text, "## Cross-field rules", "gherkin")
    assert unsafe_parallel_scenarios(cross_field_scenario) == []
    summary = json.loads(_block(text, "## Reply", "json"))
    assert set(summary) >= {"features", "stubs", "seeds"}


def test_generate_context_for_amq_and_jwks(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
) -> None:
    _, _, ledger, env_map = analysed
    ledger["app"]["auth"] = {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}
    context = build_context("generate", ledger, "amq shipment.requested", env_map, SPRING,
                            tmp_path / "karate-tests", None, None)
    assert "Jwt.token(" in context["auth_instruction"]
    assert "Jms.publish('shipment.requested'" in context["entry_instruction"]
    assert "Never `Jms.watch('shipment.requested')`" in context["entry_instruction"]


def test_render_reports_a_missing_placeholder(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "trace.md").write_text("Entry $entry_id needs $nope", encoding="utf-8")
    with pytest.raises(KbError, match="nope"):
        render("trace", {"entry_id": "x"}, prompts)


def test_cli_render_writes_the_prompt_file(
    analysed: tuple[Path, Path, dict[str, Any], dict[str, Any]], tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ledger_path, env_path, _, _ = analysed
    out = tmp_path / "karate-tests" / ".prompts" / "trace-post-api-shipments.md"
    assert run_cli(main, ["render", "--prompt", "trace", "--ledger", str(ledger_path),
                          "--env", str(env_path), "--entry", "POST /api/shipments",
                          "--repo", str(SPRING), "--out", str(out)]) == EXIT_OK
    assert out.is_file() and "POST /api/shipments" in out.read_text(encoding="utf-8")
    assert str(out) in capsys.readouterr().out
    assert run_cli(main, ["render", "--prompt", "trace", "--ledger", str(ledger_path),
                          "--entry", "POST /api/shipments", "--repo", str(SPRING),
                          "--out", str(out)]) == 2
    assert run_cli(main, ["render", "--prompt", "generate", "--ledger", str(ledger_path),
                          "--env", str(env_path), "--entry", "nope", "--repo", str(SPRING),
                          "--out", str(out)]) == 2
