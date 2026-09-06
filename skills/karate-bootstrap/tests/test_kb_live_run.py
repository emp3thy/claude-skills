"""The skill's pinned chain against real containers, once per live fixture.

``test_kb_dry_run.py`` proves the commands agree with SKILL.md; this module proves the
artefacts they produce actually work: a real image build, a real Maven run against Postgres,
Artemis, WireMock and the application, a fix-loop round that quarantines the fixture's
planted defect, and the green gate over the second run.

Subagent judgement is canned (spec 11 forbids calling a model from a test): each fixture
ships the trace, rules and generate output a real run would have produced under
``fixtures/live/<name>/expected/``. Everything else is the real script.

Opt in with ``KB_CONTAINERS=1``; CI runs it in the ``karate-live`` job, one fixture per job.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from kb_helpers import line_of
from kb_rules import slug_for
from live_recipes import RECIPES, Recipe
from test_kb_images import docker

SKILL = Path(__file__).resolve().parent.parent
TEMPLATE_README = SKILL / "templates" / "karate-tests" / "README.md.tmpl"
LINE_RE = re.compile(r"\{\{line:([^:]+):(.+?)\}\}")

pytestmark = [
    pytest.mark.containers,
    pytest.mark.skipif(os.environ.get("KB_CONTAINERS") != "1",
                       reason="set KB_CONTAINERS=1 to run containers"),
]


def run(*args: str, cwd: Path | None = None, expect_exit: int = 0) -> str:
    """A skill script, exactly as SKILL.md invokes it."""
    proc = subprocess.run([sys.executable, *args], cwd=cwd or SKILL, capture_output=True,
                          text=True)
    assert proc.returncode == expect_exit, (
        f"{' '.join(args)} exited {proc.returncode}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )
    return proc.stdout if expect_exit == 0 else proc.stdout + proc.stderr


def resolve_lines(text: str, repo: Path) -> str:
    """Replace ``{{line:<file>:<needle>}}`` with ``<file>:<n>`` located by content.

    Canned replies must not carry hard-coded line numbers: an edit to a fixture source would
    silently point ``verify-refs`` at the wrong statement.
    """
    def replace(match: re.Match[str]) -> str:
        rel, needle = match.group(1), match.group(2)
        return f"{rel}:{line_of(repo / rel, needle)}"

    return LINE_RE.sub(replace, text)


def maven(tests: Path, *args: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    """``./mvnw -B test`` in the scaffolded module, with the app image already built."""
    wrapper = tests / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    if os.name != "nt":
        wrapper.chmod(0o755)
    proc = subprocess.run([str(wrapper), "-B", "test", *args], cwd=tests,
                          capture_output=True, text=True, timeout=1800,
                          shell=(os.name == "nt"))
    if expect_success:
        assert proc.returncode == 0, proc.stdout[-8000:] + proc.stderr[-4000:]
    return proc


def quarantine(feature: Path, scenario: str) -> None:
    """Tag one scenario ``@known-defect``, the fix loop's move for an unfixable failure."""
    lines = feature.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"Scenario: {scenario}":
            indent = line[: len(line) - len(line.lstrip())]
            lines.insert(index, f"{indent}@known-defect")
            feature.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            return
    raise AssertionError(f"scenario {scenario!r} not found in {feature}")


def build_images(recipe: Recipe, repo: Path) -> tuple[str, str]:
    """The db-manager and application images this run uses; both are removed by the caller."""
    suffix = uuid.uuid4().hex[:8]
    migrations = f"kb-live-dbm-{recipe.name}-{suffix}"
    docker("build", "-t", migrations, str(repo / "db-manager"), timeout=900)
    app_image = ""
    if recipe.prebuild_app_image:
        app_image = f"kb-live-app-{recipe.name}-{suffix}"
        docker("build", "-t", app_image, str(repo), timeout=1800)
    return migrations, app_image


def assert_ledger_matches_expected(ledger: dict[str, Any], expected_path: Path) -> None:
    """Spec 11's pass criterion: every entry and exit the fixture declares is in the ledger."""
    expected = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    actual = {entry["id"]: entry for entry in ledger["entry_points"]}
    assert set(actual) == {entry["id"] for entry in expected["entry_points"]}
    for want in expected["entry_points"]:
        got = actual[want["id"]]
        assert got["kind"] == want["kind"], want["id"]
        for field in ("method", "path", "destination"):
            if field in want:
                assert got.get(field) == want[field], f"{want['id']}.{field}"
        got_exits = [{k: v for k, v in exit_.items() if k != "via"} for exit_ in got["exits"]]
        assert got_exits == want["exits"], want["id"]
        assert got["status"]["traced"] and got["status"]["stubbed"], want["id"]


@pytest.mark.parametrize("recipe", list(RECIPES.values()), ids=lambda r: r.name)
def test_live_chain_goes_green(recipe: Recipe, tmp_path: Path) -> None:
    repo = tmp_path / recipe.name
    shutil.copytree(recipe.fixture, repo, ignore=shutil.ignore_patterns("expected"))
    expected = recipe.fixture / "expected"
    tests = repo / "karate-tests"
    tests.mkdir()
    ledger_path = tests / "flow-map.yaml"
    env_path = tests / "env-map.json"
    migrations_image, app_image = build_images(recipe, repo)
    try:
        # Step 0 and 1: preflight and discovery.
        run("scripts/kb_checkpoint.py", "begin", "--repo", str(repo), "--no-commit")
        run("scripts/detect.py", str(repo), "--out", str(tests / "stack.json"))
        run("scripts/discover.py", str(repo), "--stack", str(tests / "stack.json"),
            "--out-env", str(env_path), "--out-ledger", str(ledger_path))

        # Step 2: the auth switch this fixture ships.
        run("scripts/flow_map.py", "set-auth", "--ledger", str(ledger_path),
            "--mode", "disabled", "--key", recipe.auth_key, "--value", recipe.auth_off_value)

        # Step 3: one canned trace per entry, then the traced gate.
        for entry_id in recipe.entries:
            slug = slug_for(entry_id)
            reply = tests / ".prompts" / f"trace-{slug}.json"
            reply.parent.mkdir(parents=True, exist_ok=True)
            reply.write_text(
                resolve_lines((expected / "traces" / f"{slug}.json").read_text(encoding="utf-8"),
                              repo),
                encoding="utf-8")
            assert "unresolved: 0" in run("scripts/flow_map.py", "merge", str(reply),
                                          "--ledger", str(ledger_path))
        assert "phase traced: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "traced", "--ledger", str(ledger_path),
            "--repo", str(repo), "--env", str(env_path))

        # Step 4: rules, one canned rows file per validation source.
        run("scripts/kb_rules.py", "extract", str(repo), "--ledger", str(ledger_path),
            "--out-dir", str(tests))
        for number, (entry_id, source) in enumerate(recipe.rules_sources, start=1):
            slug = slug_for(entry_id)
            rows = tests / "rules" / f"{slug}-{number}.rows.csv"
            rows.parent.mkdir(parents=True, exist_ok=True)
            rows.write_text(
                resolve_lines(
                    (expected / "rules" / f"{slug}-{number}.rows.csv").read_text(encoding="utf-8"),
                    repo),
                encoding="utf-8")
            run("scripts/kb_rules.py", "add", entry_id, str(rows), "--ledger", str(ledger_path),
                "--out-dir", str(tests))
            run("scripts/kb_rules.py", "mark-scanned", entry_id, source,
                "--ledger", str(ledger_path))

        # Step 5: scaffold the module against the db-manager image built above.
        run("scripts/kb_scaffold.py", str(repo), "--ledger", str(ledger_path),
            "--env", str(env_path), "--out", str(tests),
            "--migrations-image", migrations_image)

        # Step 6: the canned generate output, then the generated gate.
        generated = expected / "generated"
        for source in sorted(generated.rglob("*")):
            if source.is_dir():
                continue
            rel = source.relative_to(generated)
            target = tests / ("src/test/resources" / rel if rel.parts[0] == "features" else rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for entry_id in recipe.entries:
            slug = slug_for(entry_id)
            args = ["scripts/flow_map.py", "mark", "--entry", entry_id, "--generated",
                    "--ledger", str(ledger_path), "--feature", f"features/{slug}.feature"]
            for flag, value in recipe.marks[entry_id]:
                args += [flag, value]
            run(*args)
        assert "phase generated: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "generated", "--ledger",
            str(ledger_path), "--repo", str(repo), "--tests-dir", str(tests))

        # Step 7: the first live run. The planted defect makes it red.
        image_args = [f"-Dapp.image={app_image}"] if app_image else []
        first = maven(tests, *image_args, expect_success=False)
        assert first.returncode != 0, "the planted defect must make the first run fail"
        report = tests / "report.json"
        run("scripts/kb_report.py", "parse", "--reports", str(tests / "target" / "karate-reports"),
            "--out", str(report), "--features", str(tests / "src" / "test" / "resources"
                                                    / "features"))
        parsed = json.loads(report.read_text(encoding="utf-8"))
        failures = [f["scenario"] for f in parsed["failed"]]
        assert recipe.planted_scenario in failures, failures

        # Step 8: one fix-loop round. The failure is a defect in the application, so the
        # scenario is quarantined and recorded; the suite documents behaviour, never fixes it.
        run("scripts/kb_iterate.py", "next", "--report", str(report), "--tests-dir", str(tests))
        run("scripts/kb_iterate.py", "log", "--log", str(tests / "iterations.jsonl"),
            "--signature", f"{recipe.planted_feature}:{recipe.planted_scenario}",
            "--hypothesis", "the application answers 500 where the scenario expects 400",
            "--change", "quarantined the scenario and recorded DEF-001",
            "--classification", "app-defect", "--unfixable")
        quarantine(tests / "src" / "test" / "resources" / recipe.planted_feature,
                   recipe.planted_scenario)
        shutil.copy2(expected / "defects.md", tests / "defects.md")

        # Step 7 again: green with the defect quarantined.
        maven(tests, *image_args)
        run("scripts/kb_report.py", "parse", "--reports", str(tests / "target" / "karate-reports"),
            "--out", str(report), "--features", str(tests / "src" / "test" / "resources"
                                                    / "features"))
        parsed = json.loads(report.read_text(encoding="utf-8"))
        assert parsed["failed"] == [], parsed["failed"]
        assert parsed["passed"] >= 4, parsed
        run("scripts/flow_map.py", "record-run", "--ledger", str(ledger_path),
            "--report", str(report))
        assert "phase green: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "green", "--ledger", str(ledger_path),
            "--repo", str(repo), "--report", str(report), "--defects", str(tests / "defects.md"))

        # Step 9: the summary the user reads.
        run("scripts/kb_report.py", "summary", "--ledger", str(ledger_path),
            "--defects", str(tests / "defects.md"), "--report", str(report),
            "--template", str(TEMPLATE_README), "--out", str(tests / "README.md"))
        readme = (tests / "README.md").read_text(encoding="utf-8")
        assert "DEF-001" in readme and "${" not in readme.replace("$${", "")

        assert_ledger_matches_expected(yaml.safe_load(ledger_path.read_text(encoding="utf-8")),
                                       expected / "expected-flow-map.yaml")
    finally:
        for tag in (migrations_image, app_image):
            if tag:
                docker("image", "rm", "-f", tag, check=False)
