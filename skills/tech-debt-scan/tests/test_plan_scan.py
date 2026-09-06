"""plan_scan.py: leads block, adaptive rule, set forms, prompt rendering (spec 2.4, 4.6)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from categories import FAMILIES
from config import DEFAULTS, ConfigError
from inventory import build_all, write_json, write_outputs
from make_history import replay_fixture
from patterns import run_patterns
from plan_scan import LEAD_CAP, ScanDocs, _main, build_plan, leads_for, load_docs
from rules import run_rules

CORPUS = ("service-py", "web-ts", "mixed-decoys")


def _signals(repo: Path, workdir: Path, *, churn_months: int = 240) -> None:
    """Run the phase 1 chain into workdir exactly as SKILL.md v2 steps 1 to 3 will."""
    inventory, coupling = build_all(repo, churn_months=churn_months, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json",
               {"schema_version": 2, "findings": findings, "leads": leads})


@pytest.fixture(scope="module")
def corpus_workdirs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Path, Path]]:
    out: dict[str, tuple[Path, Path]] = {}
    for name in CORPUS:
        repo = replay_fixture(name, tmp_path_factory.mktemp(name))
        workdir = tmp_path_factory.mktemp(f"{name}-wd")
        _signals(repo, workdir)
        out[name] = (repo, workdir)
    return out


# Filled in by the implementer from the first green run (Step 4) and checked by the
# reviewer against planted.json: every family with a planted item must be run.
# service-py and mixed-decoys carry a lead for all fourteen; web-ts has no security
# pattern hit at all, so the adaptive rule drops that one scout.
_ALL_DEEP: frozenset[str] = frozenset({
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "test-quality", "pipeline-infra",
})
EXPECTED_RUN: dict[str, set[str]] = {
    "service-py": set(_ALL_DEEP),
    "web-ts": set(_ALL_DEEP - {"security"}),
    "mixed-decoys": set(_ALL_DEEP),
}


def test_plan_shape_and_default_set(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["service-py"]
    plan, prompts = build_plan(workdir, DEFAULTS, families=None, top=None)
    assert list(plan) == ["schema_version", "set", "top", "chunked", "thresholds", "entries",
                          "families_run", "families_skipped"]
    assert plan["schema_version"] == 2 and plan["set"] == "default" and plan["top"] == 5
    assert plan["chunked"] is False and plan["thresholds"] == DEFAULTS["chunking"]
    for entry in plan["entries"]:
        assert list(entry) == ["family", "module", "prompt", "output", "leads"]
        assert entry["module"] is None
        assert entry["prompt"] == f"prompts/scout-{entry['family']}.md"
        assert entry["output"] == f"scouts/{entry['family']}.json"
        assert entry["prompt"] in prompts
    run = [e["family"] for e in plan["entries"]]
    assert run == plan["families_run"] == [f for f in FAMILIES if f in run]
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert set(run) | set(skipped) == set(FAMILIES)
    assert skipped["test-quality"] == "not in set" and skipped["pipeline-infra"] == "not in set"


@pytest.mark.parametrize("name", CORPUS)
def test_every_planted_family_is_dispatched(
    name: str, corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    _, workdir = corpus_workdirs[name]
    plan, _ = build_plan(workdir, DEFAULTS, families="deep", top=None)
    planted = json.loads((Path(__file__).parent / "fixtures" / "corpus" / name / "planted.json")
                         .read_bytes())
    scout_families = {p["family"] for p in planted["planted"]} - {"ownership"}
    assert scout_families <= set(plan["families_run"]), plan["families_skipped"]
    assert EXPECTED_RUN[name] == set(plan["families_run"])


def test_set_forms_and_explicit_list_bypass_adaptive_rule(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    _, workdir = corpus_workdirs["mixed-decoys"]
    quick, _ = build_plan(workdir, DEFAULTS, families="quick", top=3)
    assert quick["set"] == "quick" and quick["top"] == 3
    assert set(quick["families_run"]) <= {"complex-units", "error-masking", "test-gaps",
                                          "half-finished", "dependency-debt", "security"}
    deep, _ = build_plan(workdir, DEFAULTS, families="deep", top=None)
    assert deep["set"] == "deep"
    explicit, prompts = build_plan(workdir, DEFAULTS, families=["doc-drift", "duplication"],
                                   top=None)
    assert explicit["set"] == "explicit"
    assert explicit["families_run"] == ["duplication", "doc-drift"]  # FAMILIES order, not argv
    assert {s["reason"] for s in explicit["families_skipped"]} == {"not in set"}
    cfg = deepcopy(DEFAULTS)
    cfg["families"]["disabled"] = ["duplication"]
    disabled, _ = build_plan(workdir, cfg, families=["doc-drift", "duplication"], top=None)
    assert {s["family"]: s["reason"]
            for s in disabled["families_skipped"]}["duplication"] == "disabled"
    with pytest.raises(ConfigError):
        build_plan(workdir, DEFAULTS, families="nonsense", top=None)


def test_no_leads_family_is_skipped_with_reason(tmp_path: Path) -> None:
    """A family runs only when its leads block is non-empty (spec 2.4).

    ``src/b.py`` holds one indented line, so ``max_indent`` is 1 and ``loc`` is 2
    on a file with no debt in it at all. Without a floor on each family's primary
    metric the inventory lead is true of every non-empty file, and complex-units
    and god-classes would be dispatched on every repository that has any code.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("def f(value):\n    return value\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    plan, _ = build_plan(workdir, DEFAULTS, families="deep", top=None)
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert skipped.get("security") == "no leads"
    assert skipped.get("dependency-debt") == "no leads"
    assert skipped.get("complex-units") == "no leads"
    assert skipped.get("god-classes") == "no leads"


def test_lead_cap_applies_to_pattern_leads_and_spares_the_other_kinds(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    """Spec 4.6 caps pattern leads and tool signals at 40 per family, band files first.

    The hotspot band, coupled pairs, SATD markers and artefacts are separate
    items of the same sentence and carry no cap of their own (the band is already
    bounded by ``hotspot_band.max``). Capping the whole block kind-major would let
    a full band crowd every pattern lead out of a large repository's prompt.
    """
    _, workdir = corpus_workdirs["service-py"]
    docs = load_docs(workdir)
    inflated = ScanDocs(
        inventory=docs.inventory,
        coupling=docs.coupling,
        patterns=deepcopy(docs.patterns),
        rules=docs.rules,
    )
    band = docs.inventory["hotspot_band"][0]
    extra = [
        {"rule": "satd-marker", "file": f"src/z{i}.py", "line": 1, "quote": "# TODO x",
         "path_class": "source", "extra": {}}
        for i in range(60)
    ] + [{"rule": "satd-marker", "file": band, "line": 1, "quote": "# TODO band",
          "path_class": "source", "extra": {}}]
    family_leads = inflated.patterns["leads"]["half-finished"]
    inflated.patterns["leads"]["half-finished"] = extra + family_leads
    leads = leads_for("half-finished", inflated, DEFAULTS)
    patterns = [lead for lead in leads if lead.kind == "pattern"]
    assert len(patterns) == LEAD_CAP
    # Band files first within the capped kind, so the cap never drops one of them.
    in_band = [lead.path in set(docs.inventory["hotspot_band"]) for lead in patterns]
    assert in_band == sorted(in_band, reverse=True)
    assert band in [lead.path for lead in patterns]
    assert leads[0].kind == "hotspot" and leads[0].path in docs.inventory["hotspot_band"]
    assert len([lead for lead in leads if lead.kind == "hotspot"]) == len(
        docs.inventory["hotspot_band"])
    assert len([lead for lead in leads if lead.kind == "satd"]) == len(docs.patterns["satd"])


def test_path_class_disables_drop_leads_and_are_named_in_the_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "tests" / "test_a.py").write_text(
        "def test_a():\n    try:\n        pass\n    except Exception:\n        pass\n",
        encoding="utf-8")
    (repo / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    cfg = deepcopy(DEFAULTS)
    cfg["families"]["per_path_class"]["tests"] = {"disable": ["error-masking"]}
    plan, prompts = build_plan(workdir, cfg, families=["error-masking", "half-finished"], top=None)
    text = prompts["prompts/scout-error-masking.md"]
    assert "tests/test_a.py" not in text.split("Leads (deterministic signals")[1]
    assert "Families disabled on tests: error-masking" in text
    entry = next(e for e in plan["entries"] if e["family"] == "error-masking")
    assert entry["leads"] == 0


def test_a_single_family_name_is_an_explicit_one_element_list(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    """``--families security`` is a list of one, not an unknown set name (exit 2)."""
    _, workdir = corpus_workdirs["mixed-decoys"]
    plan, prompts = build_plan(workdir, DEFAULTS, families="security", top=None)
    assert plan["set"] == "explicit"
    assert plan["families_run"] == ["security"]
    assert set(prompts) == {"prompts/scout-security.md"}
    assert {s["reason"] for s in plan["families_skipped"]} == {"not in set"}
    assert _main(["--workdir", str(workdir), "--families", "security"]) == 0


def test_cli_reports_a_corrupt_signal_file_instead_of_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A signal file that is not JSON exits 2 with an ``error:`` line, like the siblings."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    (workdir / "patterns.json").write_bytes(b"{ not json")
    assert _main(["--workdir", str(workdir)]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_writes_plan_and_prompts(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["web-ts"]
    assert _main(["--workdir", str(workdir), "--families", "quick", "--top", "3"]) == 0
    plan = json.loads((workdir / "scan-plan.json").read_bytes())
    assert plan["top"] == 3
    # Phase 3 dispatches the plan and writes each scout reply to scouts/<family>.json;
    # the directory is created here so an agent's write never hits a missing parent.
    assert (workdir / "scouts").is_dir()
    for entry in plan["entries"]:
        prompt = (workdir / entry["prompt"]).read_bytes()
        assert b"\r" not in prompt and prompt.endswith(b"\n")
        text = prompt.decode("utf-8")
        assert "hotspot" in text.lower() and "Severity rubric" in text
    assert (workdir / "scan-plan.json").read_bytes().count(b"\r") == 0
    assert _main(["--workdir", str(workdir / "missing")]) == 2
