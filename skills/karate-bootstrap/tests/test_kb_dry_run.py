"""Every pinned SKILL.md command, in order, on each fixture repo, with canned subagent replies.

No mocking and no containers: the trace, rules and generate subagents are replaced by the
JSON, CSV and feature text a real run would have produced; everything else is the real
script wired exactly as SKILL.md prescribes, run through subprocess so the CLI surface is
exercised too. Git steps run against a throwaway repository.

The third case is the monorepo path: the same spring fixture copied under
``services/shipments`` and driven with ``--service-dir services/shipments`` and
``--tests-dir services/shipments/karate-tests``, the flags SKILL.md pins for a run with a
service sub-directory.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import yaml
from kb_common import read_json
from kb_helpers import line_of
from kb_rules import slug_for

SKILL = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
REPORTS = FIXTURES / "karate-reports"
IMAGE = "registry.example/db-manager:1"


def run(*args: str, cwd: Path | None = None, expect_exit: int = 0) -> str:
    proc = subprocess.run([sys.executable, *args], cwd=cwd or SKILL, capture_output=True,
                          text=True)
    assert proc.returncode == expect_exit, f"{' '.join(args)}\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout if expect_exit == 0 else proc.stdout + proc.stderr


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def spring_traces(repo: Path) -> dict[str, dict[str, Any]]:
    service = "src/main/java/com/acme/shipments/ShipmentService.java"
    listener = "src/main/java/com/acme/shipments/ShipmentEventsListener.java"
    request = "src/main/java/com/acme/shipments/ShipmentRequest.java"
    return {
        "POST /api/shipments": {
            "id": "POST /api/shipments", "auth": "required",
            "request": {"content_type": "application/json", "schema_ref": request,
                        "example": "seed/examples/post-api-shipments.json"},
            "responses": [{"status": 201, "when": "happy"},
                          {"status": 400, "when": "validation", "rules": True}],
            "reads": [{"kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET",
                       "path": "/rates/{countryCode}"}],
            "exits": [
                {"kind": "db-write", "table": "shipments", "op": "insert",
                 "via": f"{service}:{line_of(repo / service, 'repository.save')}"},
                {"kind": "amq-publish", "destination": "shipment.created", "type": "queue",
                 "via": f"{service}:{line_of(repo / service, 'convertAndSend')}"},
                {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET",
                 "path": "/rates/{countryCode}",
                 "via": f"{service}:{line_of(repo / service, 'getForObject')}"},
            ],
            "rules": {"sources": [{"file": request, "scanned": False}]},
            "unresolved": [],
        },
        "GET /api/shipments/{id}": {
            "id": "GET /api/shipments/{id}", "exits": [], "exits_none_reason": "read-only lookup",
            "unresolved": [], "responses": [{"status": 200, "when": "found"},
                                            {"status": 404, "when": "missing"}],
        },
        "amq shipment.requested": {
            "id": "amq shipment.requested", "unresolved": [],
            "exits": [{"kind": "db-write", "table": "shipments", "op": "insert",
                       "via": f"{listener}:{line_of(repo / listener, 'repository.save')}"}],
        },
    }


def dotnet_traces(repo: Path) -> dict[str, dict[str, Any]]:
    service = "Services/DealService.cs"
    consumer = "Messaging/DealRequestedConsumer.cs"
    validator = "Validators/DealRequestValidator.cs"
    return {
        "POST /api/deals": {
            "id": "POST /api/deals", "auth": "required",
            "request": {"content_type": "application/json", "schema_ref": "Data/Deal.cs",
                        "example": "seed/examples/post-api-deals.json"},
            "responses": [{"status": 201, "when": "happy"},
                          {"status": 400, "when": "validation", "rules": True}],
            "reads": [{"kind": "http-in", "host_key": "Pricing__BaseUrl", "method": "GET",
                       "path": "/prices/{product}"}],
            "exits": [
                {"kind": "db-write", "table": "deals", "op": "insert",
                 "via": f"{service}:{line_of(repo / service, 'SaveChangesAsync')}"},
                {"kind": "amq-publish", "destination": "deal.created", "type": "queue",
                 "via": f"{service}:{line_of(repo / service, '_producer.Send(')}"},
                {"kind": "http-out", "host_key": "Pricing__BaseUrl", "method": "GET",
                 "path": "/prices/{product}",
                 "via": f"{service}:{line_of(repo / service, 'GetFromJsonAsync')}"},
            ],
            "rules": {"sources": [{"file": validator, "scanned": False}]},
            "unresolved": [],
        },
        "GET /api/deals/{id}": {
            "id": "GET /api/deals/{id}", "exits": [], "exits_none_reason": "read-only lookup",
            "unresolved": [], "responses": [{"status": 200, "when": "found"},
                                            {"status": 404, "when": "missing"}],
        },
        "amq deal.requested": {
            "id": "amq deal.requested", "unresolved": [],
            "exits": [{"kind": "db-write", "table": "deals", "op": "update",
                       "via": f"{consumer}:{line_of(repo / consumer, '_db.SaveChanges()')}"}],
        },
    }


def feature_text(table: str, destination: str, downstream_path: str) -> str:
    return (
        f"@smoke\nFeature: canned\n\nBackground:\n  * def uid = java.util.UUID.randomUUID() + ''\n"
        f"  * call read('classpath:common/reset.feature') {{ watch: ['{destination}'] }}\n\n"
        f"Scenario: happy\n  * def row = Db.row('{table}', {{ reference: uid }})\n"
        f"  * def msg = Jms.await('{destination}', 5000, {{ id: uid }})\n"
        f"  * Stubs.verify('GET', '{downstream_path}', 1)\n"
    )


class Case(NamedTuple):
    """One dry-run case: which fixture, its canned traces, and the SKILL.md flag values."""

    fixture: str
    traces_for: Callable[[Path], dict[str, dict[str, Any]]]
    post_id: str
    table: str
    destination: str
    downstream_path: str
    auth_key: str
    service_dir: str | None


CASES: dict[str, Case] = {
    "spring-mini": Case("spring-mini", spring_traces, "POST /api/shipments", "shipments",
                        "shipment.created", "/pricing/rates/GB", "APP_SECURITY_ENABLED", None),
    "dotnet-mini": Case("dotnet-mini", dotnet_traces, "POST /api/deals", "deals", "deal.created",
                        "/pricing/prices/BRENT", "Auth__Enabled", None),
    "spring-mini-monorepo": Case("spring-mini", spring_traces, "POST /api/shipments", "shipments",
                                 "shipment.created", "/pricing/rates/GB", "APP_SECURITY_ENABLED",
                                 "services/shipments"),
}


@pytest.mark.parametrize("case_name", sorted(CASES))
def test_pinned_command_chain_runs_green(tmp_path: Path, case_name: str) -> None:
    case = CASES[case_name]
    post_id, table = case.post_id, case.table
    destination, downstream_path, auth_key = case.destination, case.downstream_path, case.auth_key
    repo = tmp_path / "repo"
    # <root> is always <repo-path>; the service sub-directory travels as --service-dir.
    root = repo / case.service_dir if case.service_dir else repo
    sub = ["--service-dir", case.service_dir] if case.service_dir else []
    # kb_checkpoint.py commit stages relative to <repo-path>, so --tests-dir carries <sub>.
    tests_dir_flag = (["--tests-dir", f"{case.service_dir}/karate-tests"]
                      if case.service_dir else [])
    root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURES / case.fixture, root)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "kb@example.com")
    git(repo, "config", "user.name", "kb")
    git(repo, "add", "--", ".")
    git(repo, "commit", "-q", "-m", "fixture")
    tests = root / "karate-tests"
    tests.mkdir()
    ledger, env, stack = tests / "flow-map.yaml", tests / "env-map.json", tests / "stack.json"
    prompts = tests / ".prompts"
    traces = case.traces_for(root)
    post_slug = slug_for(post_id)

    # Step 0 and 1
    assert "karate-bootstrap" in run("scripts/kb_checkpoint.py", "begin", "--repo", str(repo))
    assert git(repo, "branch", "--show-current") == "karate-bootstrap"
    run("scripts/detect.py", str(repo), *sub, "--out", str(stack), "--skip-toolchain")
    run("scripts/discover.py", str(repo), *sub, "--stack", str(stack), "--out-env", str(env),
        "--out-ledger", str(ledger))
    seeded = yaml.safe_load(ledger.read_text(encoding="utf-8"))
    assert {e["id"] for e in seeded["entry_points"]} == set(traces)

    # Step 2: re-confirm the auth switch discover.py already guessed, and reject an
    # add-entry for an id the discover regexes already seeded
    auth_out = run("scripts/flow_map.py", "set-auth", "--ledger", str(ledger), "--mode",
                   "disabled", "--key", auth_key, "--value", "false")
    assert '"mode": "disabled"' in auth_out
    assert f'"key": "{auth_key}"' in auth_out
    assert '"confirmed": true' in auth_out
    dup = run("scripts/flow_map.py", "add-entry", "--ledger", str(ledger), "--id", post_id,
             "--kind", "http", "--handler", "src/Duplicate.txt:1", "--method", "POST",
             "--path", "/duplicate", expect_exit=2)
    assert f"{post_id}: already in the ledger" in dup
    unchanged = yaml.safe_load(ledger.read_text(encoding="utf-8"))
    assert {e["id"] for e in unchanged["entry_points"]} == set(traces)

    # Step 3: trace loop with rendered prompts and canned replies
    while True:
        pending = json.loads(run("scripts/flow_map.py", "next", "--phase", "traced",
                                 "--ledger", str(ledger)))
        if pending.get("done"):
            break
        prompt = prompts / "trace.md"
        run("scripts/kb_prompt.py", "render", "--prompt", "trace", "--ledger", str(ledger),
            "--env", str(env), "--entry", pending["id"], "--repo", str(repo), *sub,
            "--out", str(prompt))
        rendered = prompt.read_text(encoding="utf-8")
        assert pending["id"] in rendered
        # the handler path in the prompt resolves under the service root, not the repo root
        assert (root / str(pending["handler"]).rsplit(":", 1)[0]).resolve().as_posix() in rendered
        reply = prompts / "trace.json"
        reply.write_text(json.dumps(traces[pending["id"]]), encoding="utf-8")
        assert "unresolved: 0" in run("scripts/flow_map.py", "merge", str(reply),
                                      "--ledger", str(ledger))
    # Step 3, the --focus variant SKILL.md pins for an unresolved hop
    focus_prompt = prompts / f"trace-{post_slug}-2.md"
    focus_at = str(traces[post_id]["exits"][0]["via"])
    run("scripts/kb_prompt.py", "render", "--prompt", "trace", "--ledger", str(ledger),
        "--env", str(env), "--entry", post_id, "--repo", str(repo), *sub,
        "--focus", focus_at, "--out", str(focus_prompt))
    focus_text = focus_prompt.read_text(encoding="utf-8")
    assert f"Start at `{focus_at}`" in focus_text
    assert "Return the complete entry" in focus_text
    assert "so the merge keeps them" in focus_text

    assert "phase traced: pass" in run("scripts/flow_map.py", "validate", "--phase", "traced",
                                       "--ledger", str(ledger), "--repo", str(repo), *sub,
                                       "--env", str(env))

    # Step 4: rules, candidates confirmed verbatim
    run("scripts/kb_rules.py", "extract", str(repo), *sub, "--ledger", str(ledger),
        "--out-dir", str(tests))
    source = traces[post_id]["rules"]["sources"][0]["file"]
    run("scripts/kb_prompt.py", "render", "--prompt", "rules", "--ledger", str(ledger),
        "--entry", post_id, "--source", source, "--repo", str(repo), *sub,
        "--tests-dir", str(tests), "--out", str(prompts / "rules.md"))
    candidates = tests / "rules" / f"{post_slug}.candidates.csv"
    rows = tests / "rules" / f"{post_slug}.rows.csv"
    rows.write_text(candidates.read_text(encoding="utf-8"), encoding="utf-8")
    assert f"{post_id}:" in run("scripts/kb_rules.py", "add", post_id, str(rows),
                                "--ledger", str(ledger), "--out-dir", str(tests))
    run("scripts/kb_rules.py", "mark-scanned", post_id, source, "--ledger", str(ledger))

    # Step 5: scaffold and checkpoint
    run("scripts/kb_scaffold.py", str(repo), *sub, "--ledger", str(ledger), "--env", str(env),
        "--out", str(tests), "--migrations-image", IMAGE)
    runtime = read_json(tests / "src/test/resources/kb-runtime.json")
    assert runtime["migrations"]["image"] == IMAGE and runtime["amq"]["queues"]
    assert '"committed": true' in run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo),
                                      *tests_dir_flag, "--phase", "5", "--message", "scaffold")

    # Step 6: generate loop with a canned feature, stub and seed per entry
    features = tests / "src/test/resources/features"
    (tests / "stubs/pricing").mkdir(parents=True)
    (tests / "stubs/pricing/default.json").write_text('{"mappings":[]}', encoding="utf-8")
    (tests / "seed/examples").mkdir(parents=True)
    (tests / "seed/examples" / f"{post_slug}.json").write_text("{}", encoding="utf-8")
    (tests / "seed" / f"{post_slug}.sql").write_text("-- nothing to seed\n", encoding="utf-8")
    while True:
        pending = json.loads(run("scripts/flow_map.py", "next", "--phase", "generated",
                                 "--ledger", str(ledger)))
        if pending.get("done"):
            break
        run("scripts/kb_prompt.py", "render", "--prompt", "generate", "--ledger", str(ledger),
            "--env", str(env), "--entry", pending["id"], "--repo", str(repo), *sub,
            "--tests-dir", str(tests), "--out", str(prompts / "generate.md"))
        (features / f"{post_slug}.feature").write_text(
            feature_text(table, destination, downstream_path), encoding="utf-8")
        run("scripts/flow_map.py", "mark", "--entry", pending["id"], "--generated",
            "--feature", f"features/{post_slug}.feature", "--stub", "stubs/pricing/default.json",
            "--seed", f"seed/{post_slug}.sql", "--ledger", str(ledger))
    assert "phase generated: pass" in run("scripts/flow_map.py", "validate", "--phase",
                                          "generated", "--ledger", str(ledger),
                                          "--repo", str(repo), *sub, "--tests-dir", str(tests))
    run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo), *tests_dir_flag,
        "--phase", "6", "--message", "generate")

    # Step 7: a captured green run stands in for mvn test
    reports = tests / "target/karate-reports"
    reports.mkdir(parents=True)
    shutil.copy2(REPORTS / "features.harness-smoke.json", reports / "features.harness-smoke.json")
    report = tests / "target/report.json"
    run("scripts/kb_report.py", "parse", "--reports", str(reports), "--out", str(report))
    assert "failing: 0" in run("scripts/flow_map.py", "record-run", "--ledger", str(ledger),
                               "--report", str(report))
    assert "phase green: pass" in run("scripts/flow_map.py", "validate", "--phase", "green",
                                      "--ledger", str(ledger), "--repo", str(repo), *sub,
                                      "--report", str(report),
                                      "--defects", str(tests / "defects.md"))
    assert run("scripts/kb_iterate.py", "check-stop", "--log", str(tests / ".iterations.log"),
               "--report", str(report), "--max-iterations", "15").strip() == "done"

    # Step 8: the pinned loop commands on a green report; `next` has nothing left to hand out
    assert json.loads(run("scripts/kb_iterate.py", "next", "--report", str(report),
                          "--tests-dir", str(tests))) == {"done": True}
    iterations = tests / ".iterations.log"
    signature = f"features/{post_slug}.feature|happy|* match status == N|"
    assert "iteration 1 logged" in run(
        "scripts/kb_iterate.py", "log", "--log", str(iterations), "--signature", signature,
        "--hypothesis", "the stub returns 404 because the path is wrong",
        "--change", "point the pricing stub at the traced path", "--classification",
        "stub-or-seed")
    logged = [json.loads(line) for line in iterations.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    assert len(logged) == 1
    assert logged[0]["iteration"] == 1
    assert logged[0]["signature"] == signature
    assert logged[0]["classification"] == "stub-or-seed"
    assert logged[0]["unfixable"] is False

    # Step 8: record an observed-behaviour override (no failure to iterate on here, but the
    # command is pinned and runs with no containers)
    override_item = {"scenario": "happy", "field": "status", "old": "201", "new": "200",
                     "reason": "observed 200 not 201 on a clean run"}
    override_out = run("scripts/flow_map.py", "override", "--ledger", str(ledger), "--entry",
                       post_id, "--scenario", override_item["scenario"], "--field",
                       override_item["field"], "--old", override_item["old"], "--new",
                       override_item["new"], "--reason", override_item["reason"])
    assert f"override on {post_id}:" in override_out
    overridden = yaml.safe_load(ledger.read_text(encoding="utf-8"))
    post_entry = next(e for e in overridden["entry_points"] if e["id"] == post_id)
    assert post_entry["observed_overrides"] == [override_item]

    # Step 9: report and final checkpoint
    run("scripts/kb_report.py", "summary", "--ledger", str(ledger), "--defects",
        str(tests / "defects.md"), "--report", str(report), "--template",
        str(SKILL / "templates/karate-tests/README.md.tmpl"), "--out", str(tests / "README.md"))
    readme = (tests / "README.md").read_text(encoding="utf-8")
    assert f"# Karate tests for {root.name}" in readme
    assert "| Entry points | 3 |" in readme and "$" not in readme.replace("${XDG_RUNTIME_DIR}", "")
    run("scripts/kb_checkpoint.py", "commit", "--repo", str(repo), *tests_dir_flag,
        "--phase", "9", "--message", "report")
    assert git(repo, "status", "--short") == ""
    assert not any(".prompts" in line for line in git(repo, "ls-files").splitlines())
    staged = git(repo, "ls-files").splitlines()
    prefix = f"{case.service_dir}/karate-tests/" if case.service_dir else "karate-tests/"
    assert any(line.startswith(prefix) for line in staged)
