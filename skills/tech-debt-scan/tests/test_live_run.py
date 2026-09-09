"""live_run.py: argv, reply extraction, retry, the chain with a fake claude (spec 6 live policy)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest
from categories import SCOUT_OUTPUT_SCHEMA
from design_writer import NOTE_PLACEHOLDER, DesignWriteError
from live_run import (
    NOTES_SCHEMA,
    _main,
    _write_payload,
    claude_argv,
    dispatch,
    extract_reply,
    log_row,
    run_chain,
    unwrap_payload,
    wire_schema,
)
from verify_prompts import VERDICT_SCHEMA

FAKE = '''#!/usr/bin/env python
import json, sys
from pathlib import Path

# `claude -p` reads a piped stdin as the prompt; the harness sends it that way, so
# no prompt text may appear in argv (a Windows command line caps at 32 767 chars).
prompt = sys.stdin.read()
if "remediation notes" in prompt:
    mode = "notes"
elif "read-only scout" in prompt:
    mode = "scout"
else:
    mode = "verifier"
state = Path(__file__).with_suffix(".state")
Path(__file__).with_suffix(".prompt").write_text(str(len(prompt)), encoding="utf-8")
if "--json-schema" not in sys.argv:
    raise SystemExit(9)
if any("read-only" in arg for arg in sys.argv[1:]):
    raise SystemExit(8)
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
elif mode == "notes":
    fps = [line.split("fingerprint: ")[1].strip()
           for line in prompt.splitlines() if line.startswith("fingerprint: ")]
    # NOTES_PARTIAL simulates an agent that answers for fewer findings than the
    # top N asked for, so the harness must count the notes it actually got back
    # rather than assume every top-N slot was filled. It also appends two
    # schema-valid entries for fingerprints outside ranked.json's top_n, so the
    # notes cell and design.md must come from notes_by_fingerprint's top-N
    # filter at render time, not from an unfiltered count of notes.json.
    if "NOTES_PARTIAL" in prompt:
        fps = fps[:1]
        payload = [{"fingerprint": fp, "remediation": "Extract the helper, then delete the copy.",
                    "acceptance_criteria": ["the copy is gone", "tests pass"]} for fp in fps]
        payload += [
            {"fingerprint": extra, "remediation": "Not a real finding; outside the top N.",
             "acceptance_criteria": ["a", "b"]}
            for extra in ("0000000000000000", "ffffffffffffffff")
        ]
    else:
        payload = [{"fingerprint": fp, "remediation": "Extract the helper, then delete the copy.",
                    "acceptance_criteria": ["the copy is gone", "tests pass"]} for fp in fps]
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
    "| date | fixture | model | churn_months | tier_a_precision | reported_precision "
    "| decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd | notes |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


@pytest.fixture
def fake_claude_script(tmp_path: Path) -> Path:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    if os.name != "nt":
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


@pytest.fixture
def fake_claude(fake_claude_script: Path) -> str:
    # The harness accepts a "<python> <script>" launcher so Windows needs no shebang support.
    return f"{sys.executable} {fake_claude_script}"


def test_claude_argv_is_a_list_with_the_isolation_flags_and_no_prompt() -> None:
    argv = claude_argv(model="sonnet", budget=1.0, schema=SCOUT_OUTPUT_SCHEMA, claude="claude")
    assert argv[:2] == ["claude", "-p"]
    for flag in ("--setting-sources", "--strict-mcp-config", "--disable-slash-commands",
                 "--output-format", "--json-schema", "--tools", "--allowedTools", "--model",
                 "--max-budget-usd"):
        assert flag in argv
    assert argv[argv.index("--setting-sources") + 1] == "project"
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert argv[argv.index("--max-budget-usd") + 1] == "1.00"
    # The prompt travels on stdin, so the argv ends at the budget and carries no
    # positional argument at all.
    assert argv[-2:] == ["--max-budget-usd", "1.00"]
    assert "--bare" not in argv


def test_the_array_verdict_contract_travels_as_an_object_schema(tmp_path: Path) -> None:
    """``--json-schema`` becomes a tool input_schema, which the API rejects unless it is
    an object: an array contract must be wrapped on the way out and unwrapped on the
    way back (the first live run died with 400 input_schema.type on every verifier)."""
    wired = wire_schema(VERDICT_SCHEMA)
    assert wired["type"] == "object"
    assert wired["properties"]["items"] == VERDICT_SCHEMA
    assert wire_schema(SCOUT_OUTPUT_SCHEMA) is SCOUT_OUTPUT_SCHEMA

    argv = claude_argv(model="sonnet", budget=1.0, schema=VERDICT_SCHEMA, claude="claude")
    assert json.loads(argv[argv.index("--json-schema") + 1])["type"] == "object"

    items = [{"fingerprint": "abc", "verdict": "confirm"}]
    assert unwrap_payload({"items": items}, VERDICT_SCHEMA) == items
    assert unwrap_payload(items, VERDICT_SCHEMA) == items
    assert unwrap_payload({"items": 1}, SCOUT_OUTPUT_SCHEMA) == {"items": 1}


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


def test_dispatch_sends_an_over_long_quote_heavy_prompt_whole_on_stdin(
    tmp_path: Path, fake_claude: str, fake_claude_script: Path
) -> None:
    """A prompt past the Windows command-line ceiling reaches the agent complete.

    ``CreateProcess`` caps a command line at 32 767 characters and
    ``subprocess.list2cmdline`` escapes every quote and backslash on the way
    there, so a 30 000-character quote-heavy prompt passed as the positional
    argument grew past the ceiling; the trim that kept it under would have cut
    the last candidates and the verdict contract off a verifier prompt. On stdin
    there is no ceiling and no escaping, so nothing is trimmed.
    """
    body = 'You are a read-only scout for one debt family: security.\n' + "\n".join(
        f'{i:5d} | token = "value \\ {i}"' for i in range(2000)
    )
    assert len(body) > 32_767
    prompt = tmp_path / "scout.md"
    # write_bytes, as write_plan does: write_text would turn every LF into CRLF here.
    prompt.write_bytes(body.encode("utf-8"))
    out = tmp_path / "scouts" / "security.json"
    result = dispatch(prompt, out, cwd=tmp_path, model="haiku", budget=0.1,
                      schema=SCOUT_OUTPUT_SCHEMA, claude=fake_claude, timeout=60)
    assert result.status == "ok" and result.attempts == 1, result.error
    seen = int(fake_claude_script.with_suffix(".prompt").read_text(encoding="utf-8"))
    assert seen == len(body)
    assert json.loads(out.read_bytes())["family"] == "security"


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


def test_write_payload_redacts_the_verdict_contract_and_leaves_scouts_raw(
    tmp_path: Path,
) -> None:
    """Verdicts are redacted at write; scout replies are not, or their quotes stop verifying."""
    secret = "abcdefghijkl0123"
    payload = {
        "family": "security",
        "findings": [{
            "severity": 4,
            "verified": True,
            "note": None,
            "evidence": [{"quote": f'api_key = "{secret}"', "line_start": 11}],
        }],
    }
    out = tmp_path / "scouts" / "security.json"
    _write_payload(out, payload)
    raw = out.read_bytes()
    assert b"\r\n" not in raw
    # merge_findings verifies a quote against the file and only then redacts it
    # (spec 4.7 steps 3 and 8). Redacting a hardcoded-credential quote here would
    # stop it matching the file, and the finding would be diverted as unverifiable.
    assert secret.encode() in raw
    doc = json.loads(raw)
    finding = doc["findings"][0]
    assert finding["evidence"][0]["quote"] == f'api_key = "{secret}"'
    assert finding["severity"] == 4 and finding["verified"] is True
    assert finding["note"] is None and finding["evidence"][0]["line_start"] == 11
    # The verifier contract is a bare list; nothing downstream re-verifies its prose
    # against the file, so the same credential is redacted on the way to disk.
    verdicts = tmp_path / "verdicts" / "verify-01.json"
    _write_payload(verdicts, [{"proof": f'token = "{secret}" at line 11', "checked": []}])
    written = verdicts.read_bytes()
    assert b"\r\n" not in written
    assert secret.encode() not in written
    assert json.loads(written)[0]["proof"] == 'token = "abcd***" at line 11'


def test_log_row_creates_the_header_and_appends_a_row(tmp_path: Path) -> None:
    log = tmp_path / "nested" / "log.md"
    report = {
        "families": {"security": {"reported": 4, "precise": 3, "recall": 0.5},
                     "dead-code": {"reported": 0, "precise": 0, "recall": None}},
        "decoys_in_tier_a": 1, "decoys_in_top_n": 0,
        "tier_a": {"reported": 2, "precise": 1, "precision": 0.5},
    }
    log_row(log, "service-py", "haiku", report, churn_months=240,
            scouts=6, verifiers=2, cost=0.42)
    text = log.read_text(encoding="utf-8")
    assert "\r\n" not in text
    assert text.startswith("| date | fixture | model | churn_months | tier_a_precision |")
    row = text.splitlines()[-1]
    assert row.startswith("| 20")
    # model, then churn_months right after it, then the tier A / A+B precision pair.
    assert "| haiku | 240 | 0.50 | 0.75 |" in row
    for token in ("service-py", "haiku", "security=0.50", "| 6 |", "| 2 |", "0.42"):
        assert token in row, token


def test_log_row_writes_a_dash_when_churn_months_is_none(tmp_path: Path) -> None:
    log = tmp_path / "log.md"
    report = {"families": {}, "decoys_in_tier_a": 0, "decoys_in_top_n": 0,
               "tier_a": {"reported": 0, "precise": 0, "precision": None}}
    log_row(log, "service-py", "haiku", report, churn_months=None,
            scouts=0, verifiers=0, cost=0.0)
    row = log.read_text(encoding="utf-8").splitlines()[-1]
    assert "| haiku | - | - |" in row


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
                 "evaluation.json", "design.md", "findings.json"):
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


def test_run_chain_honours_the_fixtures_churn_months_over_the_flag(
    tmp_path: Path, fake_claude: str, service_py_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """planted.json's churn_months (240) outranks a conflicting --churn-months (6)."""
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    log.write_text(LOG_HEADER_TEXT, encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
              churn_months=6, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
              skip_agents=False, planted=planted, log_path=log, fixture_name="service-py")
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    assert inventory["churn_window_months"] == 240
    err = capsys.readouterr().err
    assert "warning: --churn-months 6 ignored; service-py scores at churn_months 240" in err
    row = log.read_text(encoding="utf-8").splitlines()[-1]
    assert "| haiku | 240 |" in row


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert _main([str(tmp_path / "missing-repo"), "--skip-agents"]) == 2
    (tmp_path / "repo").mkdir()
    assert _main([str(tmp_path / "repo"), "--claude", str(tmp_path / "no-such-binary")]) == 3


def test_notes_schema_is_an_array_of_bounded_notes() -> None:
    assert NOTES_SCHEMA["type"] == "array"
    item = NOTES_SCHEMA["items"]
    assert item["required"] == ["fingerprint", "remediation", "acceptance_criteria"]
    assert item["properties"]["acceptance_criteria"]["minItems"] == 2
    assert item["properties"]["acceptance_criteria"]["maxItems"] == 5
    assert item["additionalProperties"] is False


def test_run_chain_renders_the_design_with_notes_from_the_agent(
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
    for name in ("prompts/notes.md", "notes.json", "design.md", "findings.json"):
        assert (workdir / name).is_file(), name
    assert summary["notes_calls"] == 1
    design = (workdir / "design.md").read_text(encoding="utf-8")
    top = design.split("# Top ")[1].split("\n# Below the cut")[0]
    assert "remediation note not available" not in top
    assert "Extract the helper" in top
    row = log.read_text(encoding="utf-8").splitlines()[-1]
    top_n = json.loads((workdir / "ranked.json").read_bytes())["top_n"]
    assert row.endswith(f"| {len(top_n)}/{len(top_n)} |")
    report = json.loads((workdir / "evaluation.json").read_bytes())
    assert report["source"] == "findings.json"


def test_run_chain_refuses_to_score_when_a_baseline_or_diff_is_in_the_workdir(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "diff.json").write_text("{}", encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    with pytest.raises(RuntimeError, match="baseline"):
        run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
                  churn_months=240, model="haiku", budget=0.1, claude=fake_claude,
                  timeout=60, skip_agents=False, planted=planted, log_path=None,
                  fixture_name="service-py")


def test_run_chain_keeps_the_run_documents_under_keep(
    tmp_path: Path, fake_claude: str, service_py_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # a foreign cwd: keep must not resolve against it
    workdir = tmp_path / "wd"
    keep = tmp_path / "runs" / "2026-04-15-test"
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
              churn_months=240, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
              skip_agents=False, planted=planted, log_path=None, fixture_name="service-py",
              keep=keep)
    for name in ("evaluation.json", "design.md", "notes.json", "findings.json"):
        assert (keep / "service-py" / name).is_file(), name


def test_log_row_appends_the_notes_column_last(tmp_path: Path) -> None:
    log = tmp_path / "log.md"
    report = {"families": {}, "decoys_in_tier_a": 0, "decoys_in_top_n": 0,
              "tier_a": {"reported": 0, "precise": 0, "precision": None}}
    log_row(log, "service-py", "haiku", report, churn_months=None,
            scouts=0, verifiers=0, cost=0.0, notes="3/5")
    text = log.read_text(encoding="utf-8")
    assert text.splitlines()[0].endswith("| cost_usd | notes |")
    assert text.splitlines()[-1].endswith("| 0.00 | 3/5 |")


def test_run_chain_counts_notes_exactly_not_by_placeholder_arithmetic(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    """The notes cell must reflect ``notes.json`` itself, not a placeholder count
    inferred from ``design.md``. The fake answers for only the first fingerprint
    when the prompt carries ``NOTES_PARTIAL`` -- planted in the repo copy's
    README first line, which the fake's own half-finished scout finding quotes
    into evidence, so the marker reaches the notes prompt -- and the harness
    must report a genuinely partial cell, not one inferred as full.

    Edits a private copy of the session-scoped ``service_py_repo`` fixture
    (``shutil.copytree``), never the fixture path other tests share.
    """
    repo = tmp_path / "repo"
    shutil.copytree(service_py_repo, repo)
    readme = repo / "README.md"
    readme.write_text("NOTES_PARTIAL " + readme.read_text(encoding="utf-8"), encoding="utf-8")
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    log.write_text(LOG_HEADER_TEXT, encoding="utf-8")
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    # top=8 (not the usual 3): the fake's half-finished finding -- the only one
    # whose evidence quotes README.md, so it is the only carrier of the marker --
    # is tier B and ranks below nine tier-A rule findings on this fixture, so a
    # small top would never pull it (or the marker) into the notes prompt at all.
    run_chain(repo, workdir, families="quick", top=8, preset="balanced",
              churn_months=240, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
              skip_agents=False, planted=planted, log_path=log, fixture_name="service-py")
    top_n = json.loads((workdir / "ranked.json").read_bytes())["top_n"]
    n = len(top_n)
    assert n > 1, "need two or more top-N findings for a partial fill to be visible"
    row = log.read_text(encoding="utf-8").splitlines()[-1]
    assert row.endswith(f"| 1/{n} |")
    design = (workdir / "design.md").read_text(encoding="utf-8")
    top = design.split("# Top ")[1].split("\n# Below the cut")[0]
    assert top.count(NOTE_PLACEHOLDER) == 2 * (n - 1)
    # The fake's NOTES_PARTIAL reply also carries two schema-valid entries for
    # fingerprints outside ranked.json's top_n; notes.json keeps all three (the
    # raw reply), so the "1/{n}" cell above proves notes_by_fingerprint's top-N
    # filter, not a smaller reply.
    assert len(json.loads((workdir / "notes.json").read_bytes())) == 3


def test_main_exits_2_when_the_design_render_self_check_fails(
    tmp_path: Path, fake_claude: str, service_py_repo: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise DesignWriteError("boom")

    monkeypatch.setattr("live_run.write_design", boom)
    workdir = tmp_path / "wd"
    rc = _main([
        str(service_py_repo), "--workdir", str(workdir), "--families", "quick", "--top", "3",
        "--preset", "balanced", "--churn-months", "240", "--model", "haiku",
        "--max-budget-usd", "0.1", "--claude", fake_claude, "--timeout", "60",
    ])
    assert rc == 2
    assert "error: boom" in capsys.readouterr().err


def test_run_chain_probes_tools_when_requested(
    tmp_path: Path, fake_claude: str, service_py_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from config import load_config

    calls: list[tuple[Path, dict]] = []

    def stub_probe(root: Path, config: dict) -> dict:
        calls.append((root, config))
        return {"schema_version": 2, "tools": {}, "signals": []}

    monkeypatch.setattr("live_run.probe", stub_probe)
    workdir = tmp_path / "wd"
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
              churn_months=240, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
              skip_agents=False, planted=planted, log_path=None, fixture_name="service-py",
              tools=True)
    doc = json.loads((workdir / "tool-signals.json").read_bytes())
    assert doc == {"schema_version": 2, "tools": {}, "signals": []}
    assert calls == [(service_py_repo.resolve(), load_config(service_py_repo))]


def test_main_planted_flag_overrides_the_repo_and_fixture_lookup(
    tmp_path: Path, fake_claude: str, service_py_repo: Path
) -> None:
    """``--planted`` scores a plain repository against any fixture's planted file,
    without a ``planted.json`` ever being added to the repo tree."""
    assert not (service_py_repo / "planted.json").is_file()
    planted = Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json"
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    rc = _main([
        str(service_py_repo), "--workdir", str(workdir), "--families", "quick", "--top", "3",
        "--preset", "balanced", "--churn-months", "240", "--model", "haiku",
        "--max-budget-usd", "0.1", "--claude", fake_claude, "--timeout", "60",
        "--log", str(log), "--planted", str(planted),
    ])
    assert rc == 0
    assert (workdir / "evaluation.json").is_file()
    rows = log.read_text(encoding="utf-8").splitlines()
    # ``target`` was a bare repo path, not a corpus fixture name, so fixture_name
    # stays "" and log_row falls back to the repo's own directory name -- proof
    # the fixture-lookup branch played no part in resolving --planted.
    assert rows[-1].startswith("| 20") and service_py_repo.name in rows[-1]
    assert not (service_py_repo / "planted.json").is_file()


def test_main_planted_flag_with_a_missing_path_exits_2_before_anything_runs(
    tmp_path: Path, fake_claude: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A ``--planted`` path that is not a file must fail fast: before ``resolve_claude``
    and before any fixture replay, so a bad path costs nothing, not even a workdir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    missing = tmp_path / "missing.json"
    assert not missing.is_file()
    workdir = tmp_path / "wd"
    rc = _main([str(repo), "--planted", str(missing), "--claude", fake_claude,
                "--workdir", str(workdir)])
    assert rc == 2
    assert f"error: --planted {missing} is not a file" in capsys.readouterr().err
    assert not workdir.exists()
