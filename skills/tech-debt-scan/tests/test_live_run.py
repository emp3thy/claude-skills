"""live_run.py: argv, reply extraction, retry, the chain with a fake claude (spec 6 live policy)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from categories import SCOUT_OUTPUT_SCHEMA
from live_run import _main, claude_argv, dispatch, extract_reply, log_row, run_chain
from verify_prompts import VERDICT_SCHEMA

FAKE = '''#!/usr/bin/env python
import json, sys
from pathlib import Path

prompt = sys.argv[-1]
mode = "scout" if "read-only scout" in prompt else "verifier"
state = Path(__file__).with_suffix(".state")
if "--json-schema" not in sys.argv:
    raise SystemExit(9)
if mode == "scout":
    family = prompt.split("debt family: ")[1].split(".")[0].strip()
    findings = []
    if family == "half-finished":
        # cwd is the replayed repository, so this quote verifies against disk and the
        # candidate reaches the verifier pool -- the loop the chain test exercises.
        quote = Path("README.md").read_text(encoding="utf-8").splitlines()[0]
        findings = [{"title": "fake finding", "family": family, "debt_type": "code",
                     "type_id": None, "severity": 3, "effort": "S",
                     "signals_cited": [], "note": "fake",
                     "evidence": [{"file": "README.md", "line_start": 1,
                                   "line_end": 1, "quote": quote}]}]
    payload = {"family": family, "module": None, "findings": findings,
               "open_questions": [], "looks_bad_but_fine": [],
               "not_assessed": ["coverage numbers"]}
else:
    fps = [line.split("fingerprint: ")[1].strip()
           for line in prompt.splitlines() if line.startswith("fingerprint: ")]
    payload = [{"fingerprint": fp, "verdict": "confirm", "proof": "p", "severity": 3,
                "effort": "M", "trap_matched": None, "checked": ["x"], "opened": []}
               for fp in fps]
if not state.exists() and "FAIL_ONCE" in prompt:
    state.write_text("failed once")
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": "not json at all", "total_cost_usd": 0.01,
                      "num_turns": 1}))
    raise SystemExit(0)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "```json\\n" + json.dumps(payload) + "\\n```",
                  "total_cost_usd": 0.02, "num_turns": 2}))
'''

LOG_HEADER_TEXT = (
    "| date | fixture | model | tier_a_precision | reported_precision | decoys_tier_a "
    "| decoys_top_n | recall | scouts | verifiers | cost_usd |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)


@pytest.fixture
def fake_claude(tmp_path: Path) -> str:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    if os.name != "nt":
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    # The harness accepts a "<python> <script>" launcher so Windows needs no shebang support.
    return f"{sys.executable} {script}"


def test_claude_argv_is_a_list_with_the_isolation_flags(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("hello", encoding="utf-8")
    argv = claude_argv(prompt, model="sonnet", budget=1.0, schema=SCOUT_OUTPUT_SCHEMA,
                       claude="claude")
    assert argv[:2] == ["claude", "-p"]
    for flag in ("--setting-sources", "--strict-mcp-config", "--disable-slash-commands",
                 "--output-format", "--json-schema", "--tools", "--allowedTools", "--model",
                 "--max-budget-usd"):
        assert flag in argv
    assert argv[argv.index("--setting-sources") + 1] == "project"
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert argv[argv.index("--max-budget-usd") + 1] == "1.00"
    assert argv[-1] == "hello"
    assert "--bare" not in argv


def test_extract_reply_prefers_structured_output_then_fenced_result() -> None:
    env = {"type": "result", "subtype": "success", "is_error": False,
           "result": "```json\n[1]\n```", "structured_output": {"a": 1},
           "total_cost_usd": 0.5}
    assert extract_reply(json.dumps(env)) == ({"a": 1}, 0.5, None)
    env.pop("structured_output")
    assert extract_reply(json.dumps(env)) == ([1], 0.5, None)
    bad = {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "boom"}
    assert extract_reply(json.dumps(bad))[2] == "boom"
    assert extract_reply("not json")[2] is not None
    assert extract_reply(json.dumps({**env, "result": "plain text"}))[2] is not None


def test_dispatch_retries_once_on_invalid_payload(tmp_path: Path, fake_claude: str) -> None:
    prompt = tmp_path / "scout.md"
    prompt.write_text("You are a read-only scout for one debt family: security. FAIL_ONCE",
                      encoding="utf-8")
    out = tmp_path / "scouts" / "security.json"
    result = dispatch(prompt, out, cwd=tmp_path, model="haiku", budget=0.1,
                      schema=SCOUT_OUTPUT_SCHEMA, claude=fake_claude, timeout=60)
    assert result.status == "ok" and result.attempts == 2
    assert result.cost_usd == pytest.approx(0.03)
    assert json.loads(out.read_bytes())["family"] == "security"
    assert "previous response failed the schema" in result.last_prompt


def test_dispatch_writes_a_list_payload_for_the_verifier_contract(
    tmp_path: Path, fake_claude: str
) -> None:
    """The chain's verifier pool is empty when scouts find nothing, so cover it directly."""
    prompt = tmp_path / "verify-01.md"
    prompt.write_text(
        "You are a read-only verifier. Read and search files; change nothing.\n"
        "fingerprint: abc123\nfingerprint: def456\n",
        encoding="utf-8",
    )
    out = tmp_path / "verdicts" / "verify-01.json"
    result = dispatch(prompt, out, cwd=tmp_path, model="haiku", budget=0.1,
                      schema=VERDICT_SCHEMA, claude=fake_claude, timeout=60)
    assert result.status == "ok" and result.attempts == 1
    raw = out.read_bytes()
    assert b"\r\n" not in raw
    assert [v["fingerprint"] for v in json.loads(raw)] == ["abc123", "def456"]


def test_log_row_creates_the_header_and_appends_a_row(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "log.md"
    report = {
        "families": {"security": {"reported": 4, "precise": 3, "recall": 0.5},
                     "dead-code": {"reported": 0, "precise": 0, "recall": None}},
        "decoys_in_tier_a": 1, "decoys_in_top_n": 0,
        "tier_a": {"reported": 2, "precise": 1, "precision": 0.5},
    }
    log_row(log, "service-py", "haiku", report, scouts=6, verifiers=2, cost=0.42)
    text = log.read_text(encoding="utf-8")
    assert "\r\n" not in text
    assert text.startswith("| date | fixture | model | tier_a_precision | reported_precision |")
    row = text.splitlines()[-1]
    assert row.startswith("| 20")
    # tier A precision (0.50) is the bar; the A+B reported precision (0.75) sits beside it.
    assert "| 0.50 | 0.75 |" in row
    for token in ("service-py", "haiku", "security=0.50", "| 6 |", "| 2 |", "0.42"):
        assert token in row, token


def test_run_chain_over_a_corpus_fixture_with_the_fake(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    log.write_text(LOG_HEADER_TEXT, encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    summary = run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
                        churn_months=240, model="haiku", budget=0.1, claude=fake_claude,
                        timeout=60, skip_agents=False, planted=planted, log_path=log,
                        fixture_name="service-py")
    for name in ("inventory.json", "patterns.json", "rule-findings.json", "scan-plan.json",
                 "candidates.json", "verify-plan.json", "verified.json", "ranked.json",
                 "evaluation.json"):
        assert (workdir / name).is_file(), name
    plan = json.loads((workdir / "scan-plan.json").read_bytes())
    for entry in plan["entries"]:
        assert (workdir / entry["output"]).is_file()
    assert summary["scout_calls"] == len(plan["entries"]) and summary["cost_usd"] > 0
    assert summary["verifier_calls"] >= 1
    verified = json.loads((workdir / "verified.json").read_bytes())
    assert [f for f in verified["findings"]
            if f["verdict"] == "confirm" and f["tier"] in ("A", "B")]
    assert json.loads((workdir / "ranked.json").read_bytes())["top_n"]
    rows = log.read_text(encoding="utf-8").splitlines()
    assert rows[-1].startswith("| 20") and "service-py" in rows[-1] and "haiku" in rows[-1]


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert _main([str(tmp_path / "missing-repo"), "--skip-agents"]) == 2
    (tmp_path / "repo").mkdir()
    assert _main([str(tmp_path / "repo"), "--claude", str(tmp_path / "no-such-binary")]) == 3
