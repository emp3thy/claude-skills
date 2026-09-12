"""plan_scan.py: leads block, adaptive rule, set forms, prompt rendering (spec 2.4, 4.6)."""
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from categories import FAMILIES
from config import DEFAULTS, ConfigError
from inventory import build_all, write_json, write_outputs
from make_history import replay_fixture
from patterns import run_patterns
from plan_scan import LEAD_CAP, ScanDocs, _main, build_plan, leads_for, load_docs
from rules import run_rules

CORPUS = ("service-py", "web-ts", "mixed-decoys")
GOLDEN = Path(__file__).parent / "golden"
UPDATE_GOLDENS = os.environ.get("UPDATE_GOLDENS") == "1"


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
# service-py and mixed-decoys carry a lead for all sixteen; web-ts has no security
# pattern hit at all, so the adaptive rule drops that one scout.
_ALL_DEEP: frozenset[str] = frozenset({
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "performance", "concerns", "test-quality", "pipeline-infra",
})
EXPECTED_RUN: dict[str, set[str]] = {
    "service-py": set(_ALL_DEEP),
    "web-ts": set(_ALL_DEEP - {"security"}),
    "mixed-decoys": set(_ALL_DEEP),
}


def test_plan_shape_and_default_set(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["service-py"]
    plan, prompts = build_plan(workdir, DEFAULTS, families=None, top=None)
    assert list(plan) == ["schema_version", "set", "top", "chunked", "thresholds", "modules",
                          "modules_dropped", "entries", "families_run", "families_skipped"]
    assert plan["schema_version"] == 2 and plan["set"] == "default" and plan["top"] == 5
    assert plan["chunked"] is False and plan["thresholds"] == DEFAULTS["chunking"]
    assert plan["modules"] == [] and plan["modules_dropped"] == []
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


def test_quick_set_skips_exactly_the_ten_families_outside_it_as_not_in_set(
    tmp_path: Path,
) -> None:
    """Pins `quick`'s ``not in set`` skips (fix round 2, C1/S2/S5): ``families_skipped``
    is built from the full ``FAMILIES``, not from the selected set, so a `quick` plan's
    `design.md` is not byte-identical across a family addition -- the next one must be a
    deliberate decision, not a silent byproduct this test would catch."""
    from inventory import write_json

    write_json(tmp_path / "inventory.json", _min_inventory())
    plan, _ = build_plan(tmp_path, DEFAULTS, families="quick", top=8)
    not_in_set = {s["family"] for s in plan["families_skipped"] if s["reason"] == "not in set"}
    assert not_in_set == {
        "god-classes", "duplication", "dead-code", "migration", "doc-drift",
        "architecture", "performance", "concerns", "test-quality", "pipeline-infra",
    }


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


def test_satd_and_inventory_leads_are_capped_per_kind(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    """A TODO-heavy repository must not blow the prompt: SATD and inventory leads cap too."""
    from copy import deepcopy

    from plan_scan import KIND_CAPS, LEAD_CAP, ScanDocs, leads_for, load_docs

    _, workdir = corpus_workdirs["service-py"]
    docs = load_docs(workdir)
    inflated = ScanDocs(
        inventory=docs.inventory,
        coupling=docs.coupling,
        patterns=deepcopy(docs.patterns),
        rules=docs.rules,
    )
    inflated.patterns["satd"] = [
        {"marker": "TODO", "file": f"src/z{i}.py", "line": 1, "quote": "# TODO x",
         "ticket_ref": False, "age_days": None, "commits_since": None, "path_class": "source"}
        for i in range(80)
    ] + list(inflated.patterns["satd"])
    leads = leads_for("half-finished", inflated, DEFAULTS)
    by_kind: dict[str, int] = {}
    for lead in leads:
        by_kind[lead.kind] = by_kind.get(lead.kind, 0) + 1
    assert by_kind["satd"] == KIND_CAPS["satd"] == LEAD_CAP
    assert by_kind.get("pattern", 0) <= LEAD_CAP
    assert by_kind["hotspot"] == len(docs.inventory["hotspot_band"]), "the band is never capped"


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


class TestToolLeads:
    def _docs(self, signals: list[dict]) -> object:
        from plan_scan import ScanDocs

        return ScanDocs(
            inventory={"files": [], "hotspots": []},
            tool_signals={"schema_version": 2, "tools": {}, "signals": signals},
        )

    def _signal(self, **over) -> dict:
        base = {
            "tool": "vulture", "family": "dead-code", "kind": "unused",
            "file": "src/pay/legacy.py", "line_start": 8, "line_end": 8,
            "message": "unused function 'export_v1'", "fact": False, "extra": {},
        }
        base.update(over)
        return base

    def test_an_inference_signal_for_the_family_becomes_a_lead(self) -> None:
        from plan_scan import _tool_leads

        leads = _tool_leads(self._docs([self._signal()]), "dead-code")
        assert [(lead.kind, lead.path, lead.line) for lead in leads] == [
            ("tool", "src/pay/legacy.py", 8)
        ]

    def test_the_lead_text_names_the_tool_and_its_message(self) -> None:
        from plan_scan import _tool_leads

        text = _tool_leads(self._docs([self._signal()]), "dead-code")[0].text
        assert "vulture" in text
        assert "unused function 'export_v1'" in text

    def test_a_signal_for_another_family_is_not_a_lead_here(self) -> None:
        from plan_scan import _tool_leads

        signals = [self._signal(family="duplication", tool="jscpd", kind="clone")]
        assert _tool_leads(self._docs(signals), "dead-code") == []

    def test_a_fact_class_signal_is_never_a_lead(self) -> None:
        """Fact-class signals become candidates in merge_findings; a lead as well
        would put the same fact in front of a scout and in the candidate list."""
        from plan_scan import _tool_leads

        signals = [self._signal(tool="gitleaks", family="security", kind="secret", fact=True)]
        assert _tool_leads(self._docs(signals), "security") == []

    def test_a_signal_with_no_file_is_dropped(self) -> None:
        from plan_scan import _tool_leads

        assert _tool_leads(self._docs([self._signal(file=None)]), "dead-code") == []

    def test_a_signal_with_an_empty_file_is_dropped(self) -> None:
        from plan_scan import _tool_leads

        assert _tool_leads(self._docs([self._signal(file="")]), "dead-code") == []

    def test_a_non_dict_signal_item_is_dropped(self) -> None:
        """A malformed entry in ``signals`` (not an object) is skipped, not fatal."""
        from plan_scan import _tool_leads

        signals = ["not-a-dict", 42, self._signal()]
        leads = _tool_leads(self._docs(signals), "dead-code")
        assert [(lead.kind, lead.path, lead.line) for lead in leads] == [
            ("tool", "src/pay/legacy.py", 8)
        ]

    def test_a_non_integer_line_start_becomes_a_lineless_lead(self) -> None:
        """``line_start`` that is not an int (a string, here) is correct on inspection but
        was unpinned by any test; the lead is still built, just without a line number."""
        from plan_scan import _tool_leads

        leads = _tool_leads(self._docs([self._signal(line_start="8")]), "dead-code")
        assert [(lead.kind, lead.path, lead.line) for lead in leads] == [
            ("tool", "src/pay/legacy.py", None)
        ]

    def test_a_signal_for_an_unrecognized_family_is_never_a_lead(self) -> None:
        """A ``family`` value the skill does not know never equals any family name
        each ``_raw_leads`` branch passes in, so it is dropped safely, not by luck."""
        from plan_scan import _tool_leads

        signals = [self._signal(family="not-a-real-family")]
        assert _tool_leads(self._docs(signals), "dead-code") == []

    def test_absent_tool_signals_yield_no_leads_and_do_not_raise(self) -> None:
        from plan_scan import ScanDocs, _tool_leads

        assert _tool_leads(ScanDocs(inventory={"files": []}), "dead-code") == []

    def test_the_tool_kind_is_capped_like_pattern_and_satd(
        self, corpus_workdirs: dict[str, tuple[Path, Path]]
    ) -> None:
        """Spec 4.6 caps tool leads at 40 per family, band files first, like pattern
        and SATD (test_lead_cap_applies_to_pattern_leads_and_spares_the_other_kinds).

        This drives ``leads_for`` end to end rather than asserting the cap table
        alone: a broken ``KIND_ORDER`` (finding 1) raises ``ValueError`` here, so
        this test fails loudly against that regression instead of passing beside it.
        """
        from plan_scan import KIND_CAPS, LEAD_CAP, ScanDocs, leads_for, load_docs

        _, workdir = corpus_workdirs["service-py"]
        docs = load_docs(workdir)
        band = docs.inventory["hotspot_band"][0]
        # Decoys are named to sort *before* the real band paths (``src/pay/...``)
        # alphabetically, so band-first survival here can only come from the
        # ``path not in band`` tiebreaker in ``leads_for``, not from incidental
        # alphabetical ordering (a prior version used ``src/z*`` decoys, which
        # sorted after the band paths and passed identically with or without
        # that tiebreaker -- see task-1-rereview-1.md, Finding 2).
        signals = [
            self._signal(file=f"src/a{i:03d}.py", line_start=1) for i in range(60)
        ] + [self._signal(file=band, line_start=1)]
        inflated = ScanDocs(
            inventory=docs.inventory,
            coupling=docs.coupling,
            patterns=docs.patterns,
            rules=docs.rules,
            tool_signals={"schema_version": 2, "tools": {}, "signals": signals},
        )
        leads = leads_for("dead-code", inflated, DEFAULTS)
        tools = [lead for lead in leads if lead.kind == "tool"]
        assert len(tools) == KIND_CAPS["tool"] == LEAD_CAP
        # Band files first within the capped kind, so the cap never drops one of them.
        in_band = [lead.path in set(docs.inventory["hotspot_band"]) for lead in tools]
        assert in_band == sorted(in_band, reverse=True)
        assert band in [lead.path for lead in tools]

    def test_tool_signals_on_disk_reach_the_rendered_prompt(self, tmp_path: Path) -> None:
        """Every other ``TestToolLeads`` test hand-builds a ``ScanDocs`` and bypasses
        ``load_docs``'s read of ``tool-signals.json`` from the workdir. This test
        writes a real ``tool-signals.json`` on disk beside the other phase 1
        documents (following the ``_signals`` helper the other plan tests use), then
        builds the plan the way ``_main`` would -- exercising the disk read, the
        lead build, the cap and the sort, and the prompt render together."""
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "legacy.py").write_text("def export_v1():\n    pass\n", encoding="utf-8")
        workdir = tmp_path / "wd"
        _signals(repo, workdir)
        signal = self._signal(file="src/legacy.py", line_start=1)
        (workdir / "tool-signals.json").write_bytes(json.dumps(
            {"schema_version": 2, "tools": {}, "signals": [signal]}
        ).encode("utf-8"))
        plan, prompts = build_plan(workdir, DEFAULTS, families=["dead-code"], top=None)
        assert "dead-code" in plan["families_run"]
        text = prompts["prompts/scout-dead-code.md"]
        section = text.split("Tool signals:")[1]
        assert "src/legacy.py:1" in section
        assert "vulture: unused function 'export_v1'" in section


# --- chunking and the halved deep thresholds (task 8, spec 4.6) ------------------------


def _todo_file(marker_index: int) -> str:
    return (
        f"# TODO: revisit helper {marker_index} later\n"
        "def helper():\n"
        "    value = 1\n"
        "    return value\n"
    )


def _build_chunk_tree(root: Path) -> None:
    """Three top-level directories, twelve source files total (spec 4.6 test tree).

    Every file carries a TODO marker, so half-finished has a lead in all three
    modules. Only ``alpha`` holds a manifest (``requirements.txt``), so
    dependency-debt has a lead in exactly one module; only ``beta`` holds a
    Dockerfile, so pipeline-infra (not in the default set at all) has a lead in
    exactly one module too. No file anywhere is named uniquely across modules
    (every module repeats ``f0.py``..``f3.py``), which makes every stem shared
    and ``fan_in_approx`` ambiguous (null) everywhere, so dead-code's
    zero-fan-in-and-zero-churn lead never fires here and does not confound the
    module-scoping assertions below.
    """
    for module in ("alpha", "beta", "gamma"):
        (root / module).mkdir(parents=True)
        for i in range(4):
            (root / module / f"f{i}.py").write_text(_todo_file(i), encoding="utf-8")
    (root / "alpha" / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
    (root / "beta" / "Dockerfile").write_text(
        'FROM python:3.11\nCMD ["python", "app.py"]\n', encoding="utf-8"
    )


@pytest.fixture
def chunk_tree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_chunk_tree(repo)
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    return repo, workdir


def _build_lead_cap_tree(root: Path) -> None:
    """Three modules whose SATD-lead counts (22, 22, 5) straddle ``LEAD_CAP`` (40)
    when totalled repo-wide but not per module -- the reviewer's exact
    reproduction shape for task 8 fix round 1, finding 2."""
    for module, count in (("alpha", 22), ("beta", 22), ("gamma", 5)):
        (root / module).mkdir(parents=True)
        for i in range(count):
            (root / module / f"f{i}.py").write_text(_todo_file(i), encoding="utf-8")


@pytest.fixture
def lead_cap_tree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_lead_cap_tree(repo)
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    return repo, workdir


def _check_plan(name: str, plan: dict[str, Any], golden: Path) -> None:
    got = (json.dumps(plan, indent=2) + "\n").encode("utf-8")
    if UPDATE_GOLDENS:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(got)
    assert golden.is_file(), f"missing golden {golden}"
    assert got == golden.read_bytes(), f"{name} differs from {golden}"


def test_module_of_uses_only_the_top_level_directory() -> None:
    from plan_scan import _module_of

    assert _module_of("src/pay/refund.py") == "src"
    assert _module_of("src/pay/deep/refund.py") == "src"
    assert _module_of("README.md") is None


def test_module_of_root_sentinel_is_not_confusable_with_a_real_root_directory() -> None:
    """A genuine top-level directory named ``root`` must not collide with the
    identity ``_module_of`` returns for a true repository-root file (task 8 fix
    round 1, finding 1; reviewer-reproduced). ``None`` is not a legal directory
    name, so it cannot equal a real directory's identity the way the string
    ``"root"`` used to."""
    from plan_scan import _module_of

    assert _module_of("root/pay/refund.py") == "root"
    assert _module_of("top.py") is None
    assert _module_of("root/pay/refund.py") != _module_of("top.py")


def test_module_display_names_the_sentinel_with_a_label_no_directory_can_equal() -> None:
    """The repo-root sentinel (``None``) displays as ``"root"`` ordinarily. When
    the repository also has a genuine top-level directory literally named
    ``root``, the two would read as the same place in the rendered plan, so the
    sentinel is given ``"/"`` instead -- a label no directory can equal, because a
    path segment cannot be ``/`` (unlike the old ``"(repository root)"``, which
    was merely unlikely to collide, not incapable of it)."""
    from plan_scan import _module_display

    assert _module_display(None, set()) == "root"
    assert _module_display(None, {"root"}) == "/"
    assert "/" not in {"root", "src"}


def test_chunk_thresholds_halve_only_for_the_deep_set() -> None:
    """Spec 4.6: the halving follows from the selected set being ``deep``, not from
    argv spelling -- ``_resolve_set`` returns ``"deep"`` for both ``--families
    deep`` and a bare ``--deep`` flag (SKILL.md translates the latter before this
    script runs), and returns ``"explicit"`` even for an explicit list with the
    exact same family content as the deep set, which must not halve."""
    from plan_scan import _chunk_thresholds

    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 100, "max_loc": 1000, "max_modules": 4}
    full = {"max_files": 100, "max_loc": 1000, "max_modules": 4}
    assert _chunk_thresholds(cfg, "default") == full
    assert _chunk_thresholds(cfg, "quick") == full
    assert _chunk_thresholds(cfg, "explicit") == full
    # max_modules bounds the dispatch and does not halve: a deep scan is the run
    # that most needs the bound, not the one that should get a tighter one.
    assert _chunk_thresholds(cfg, "deep") == {"max_files": 50, "max_loc": 500, "max_modules": 4}
    # A ``chunking`` map written before ``max_modules`` existed still plans a
    # bounded scan rather than raising.
    cfg["chunking"] = {"max_files": 100, "max_loc": 1000}
    assert _chunk_thresholds(cfg, "default")["max_modules"] == (
        DEFAULTS["chunking"]["max_modules"]
    )


def test_below_both_thresholds_gives_an_unchunked_plan_with_todays_entries(
    chunk_tree: tuple[Path, Path],
) -> None:
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 1000, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is False
    assert plan["thresholds"] == dict(
        cfg["chunking"], max_modules=DEFAULTS["chunking"]["max_modules"]
    )
    entry = next(e for e in plan["entries"] if e["family"] == "half-finished")
    assert entry["module"] is None
    assert entry["prompt"] == "prompts/scout-half-finished.md"
    assert entry["output"] == "scouts/half-finished.json"
    assert entry["prompt"] in prompts


def test_above_max_files_splits_by_top_level_directory(chunk_tree: tuple[Path, Path]) -> None:
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    hf_entries = [e for e in plan["entries"] if e["family"] == "half-finished"]
    assert {e["module"] for e in hf_entries} == {"alpha", "beta", "gamma"}
    for entry in hf_entries:
        assert entry["prompt"] == f"prompts/scout-half-finished-{entry['module']}.md"
        assert entry["output"] == f"scouts/half-finished-{entry['module']}.json"
        assert entry["prompt"] in prompts
        assert f"top-level directory '{entry['module']}'" in prompts[entry["prompt"]]


def test_above_max_loc_splits_by_top_level_directory(chunk_tree: tuple[Path, Path]) -> None:
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 100000, "max_loc": 20}
    plan, _ = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    hf_modules = {e["module"] for e in plan["entries"] if e["family"] == "half-finished"}
    assert hf_modules == {"alpha", "beta", "gamma"}


def test_a_module_with_nothing_for_a_family_gets_no_entry_there(
    chunk_tree: tuple[Path, Path],
) -> None:
    """dependency-debt's only lead (the manifest) lives in ``alpha``; ``beta`` and
    ``gamma`` are real, populated modules for other families but must not get a
    dependency-debt entry of their own."""
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    plan, _ = build_plan(workdir, cfg, families="default", top=None)
    dd_modules = {e["module"] for e in plan["entries"] if e["family"] == "dependency-debt"}
    assert dd_modules == {"alpha"}
    hf_modules = {e["module"] for e in plan["entries"] if e["family"] == "half-finished"}
    # Exact equality (fix round 1, finding 3): a subset check here survives a
    # phantom-lead injection that leaks an extraneous module into the set
    # (reviewer mutation-confirmed); tightened rather than left for the sibling
    # test_above_max_files_splits_by_top_level_directory to catch alone.
    assert hf_modules == {"alpha", "beta", "gamma"}


def test_lead_cap_applies_per_module_not_once_across_the_whole_repository(
    lead_cap_tree: tuple[Path, Path],
) -> None:
    """Reviewer-reproduced (task 8 review, finding 2): with ``LEAD_CAP`` (40)
    applied repo-wide before the module split, alpha's 22 leads and beta's first
    18 (paths sort "alpha/..." before "beta/..." before "gamma/..." lexically, so
    entire modules are consumed in that order) exhausted the family's whole
    budget, leaving gamma's 5 real leads with no entry at all. Chunking exists
    for repositories too large to scan whole -- exactly the size at which a
    repo-wide cap starves a later module -- so once a plan is chunked, the cap
    must apply per module instead, and every module with real leads keeps them
    all (none of the three modules here reaches the cap on its own)."""
    _, workdir = lead_cap_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 10, "max_loc": 100000}
    plan, _ = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    hf_leads_by_module = {
        e["module"]: e["leads"] for e in plan["entries"] if e["family"] == "half-finished"
    }
    assert hf_leads_by_module == {"alpha": 22, "beta": 22, "gamma": 5}


def test_max_modules_bounds_the_dispatch_and_names_what_it_dropped(
    chunk_tree: tuple[Path, Path],
) -> None:
    """Nothing else bounds a chunked plan: entries are families x modules and one
    agent is dispatched per entry, so a 40-directory monorepo -- the size chunking
    exists for -- would plan 14x40 scouts against spec 7's "14, more with
    chunking". The dropped modules are named with their lead counts, because a
    scan that quietly stops looking at part of the repository is worse than one
    that plans too many agents."""
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000, "max_modules": 2}
    plan, prompts = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    assert len(plan["modules"]) == 2
    assert {e["module"] for e in plan["entries"]} == set(plan["modules"])
    dropped = {d["module"]: d["leads"] for d in plan["modules_dropped"]}
    assert set(plan["modules"]) | set(dropped) == {"alpha", "beta", "gamma", "root"}
    assert all(count > 0 for count in dropped.values()), "a dropped module held real leads"
    assert len(prompts) == len(plan["entries"])
    again, _ = build_plan(workdir, cfg, families="default", top=None)
    assert again == plan, "the selection is deterministic for identical inputs"


def test_a_bound_that_does_not_bind_changes_nothing(chunk_tree: tuple[Path, Path]) -> None:
    """The ordinary chunked repository -- a handful of top-level directories -- plans
    exactly what it planned before the bound existed, in the same order."""
    _, workdir = chunk_tree
    loose = deepcopy(DEFAULTS)
    loose["chunking"] = {"max_files": 6, "max_loc": 100000, "max_modules": 50}
    plan, _ = build_plan(workdir, loose, families="default", top=None)
    assert plan["modules_dropped"] == []
    assert plan["modules"] == ["alpha", "beta", "gamma", "root"]


def test_a_family_left_with_no_scanned_module_is_skipped_not_reported_as_run(
    chunk_tree: tuple[Path, Path],
) -> None:
    """doc-drift's leads all sit in modules the bound drops here. Leaving it in
    ``families_run`` would have ``design.md`` claim a family ran that dispatched no
    agent at all; ``merge_findings`` would never see an entry for it either."""
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000, "max_modules": 2}
    plan, _ = build_plan(workdir, cfg, families="default", top=None)
    assert "doc-drift" not in plan["families_run"]
    assert not [e for e in plan["entries"] if e["family"] == "doc-drift"]
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert skipped["doc-drift"] == "no leads in the scanned modules"
    assert [s["family"] for s in plan["families_skipped"]] == [
        f for f in FAMILIES if f in skipped
    ], "families_skipped stays in FAMILIES order"


def test_select_modules_ranks_by_hotspot_band_then_leads_then_name() -> None:
    """The hotspot band is the scan's own statement of where debt concentrates, so
    it decides first; lead count breaks a tie and the plan order breaks that."""
    from plan_scan import Lead, ScanDocs, _select_modules

    def leads(*paths: str) -> list[Lead]:
        return [Lead(kind="satd", path=p, line=1, text="t") for p in paths]

    family_leads = {
        "half-finished": leads("banded/a.py", "big/a.py", "big/b.py", "big/c.py",
                               "small/a.py", "tiny/a.py"),
    }
    docs = ScanDocs(inventory={"files": [], "hotspot_band": ["banded/a.py"]})
    kept, dropped = _select_modules(family_leads, docs, 2)
    # banded holds the only band file; big wins the rest on lead count; the
    # survivors come back in plan order, not rank order.
    assert kept == ["banded", "big"]
    assert dropped == ["small", "tiny"]
    assert _select_modules(family_leads, docs, 4) == (
        ["banded", "big", "small", "tiny"], []
    )


def test_families_run_lists_a_chunked_family_once_not_once_per_module(
    chunk_tree: tuple[Path, Path],
) -> None:
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    plan, _ = build_plan(workdir, cfg, families="default", top=None)
    assert plan["families_run"].count("half-finished") == 1
    assert len([e for e in plan["entries"] if e["family"] == "half-finished"]) == 3


def test_deep_set_halves_thresholds_so_a_repo_between_them_chunks_only_under_deep(
    chunk_tree: tuple[Path, Path],
) -> None:
    """12 source files sit strictly between the halved (10) and full (20) values,
    so this is the one test where the halving decides ``chunked`` itself rather
    than only the recorded ``thresholds`` number."""
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 20, "max_loc": 100000}
    default_plan, _ = build_plan(workdir, cfg, families="default", top=None)
    deep_plan, _ = build_plan(workdir, cfg, families="deep", top=None)
    assert default_plan["chunked"] is False
    modules = DEFAULTS["chunking"]["max_modules"]
    assert default_plan["thresholds"] == {"max_files": 20, "max_loc": 100000,
                                          "max_modules": modules}
    assert deep_plan["chunked"] is True
    assert deep_plan["thresholds"] == {"max_files": 10, "max_loc": 50000,
                                       "max_modules": modules}


def test_explicit_family_with_no_leads_stays_a_single_whole_repo_entry_when_chunked(
    chunk_tree: tuple[Path, Path],
) -> None:
    """Chunking splits a family's leads by module; a family with none at all
    (dispatched anyway because it was named explicitly) has nothing to split, so
    it keeps the unchunked whole-repo shape instead of inventing an entry -- or
    inventing none at all -- for every module."""
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families=["security"], top=None)
    assert plan["chunked"] is True
    assert plan["entries"] == [
        {"family": "security", "module": None, "prompt": "prompts/scout-security.md",
         "output": "scouts/security.json", "leads": 0}
    ]
    assert "prompts/scout-security.md" in prompts


def test_tool_leads_land_in_the_right_module_when_chunked(chunk_tree: tuple[Path, Path]) -> None:
    """A tool signal is just another lead with a path; splitting by module must
    route it into that path's module's prompt and no one else's (task 8's
    interface note on ``ScanDocs.tool_signals``). ``security`` has no other lead
    source in this fixture (no pattern hit), so the one entry it gets can only
    have come from the tool signal itself."""
    _, workdir = chunk_tree
    signal = {
        "tool": "gitleaks", "family": "security", "kind": "secret",
        "file": "beta/f0.py", "line_start": 1, "line_end": 1,
        "message": "hardcoded credential", "fact": False, "extra": {},
    }
    (workdir / "tool-signals.json").write_bytes(json.dumps(
        {"schema_version": 2, "tools": {}, "signals": [signal]}
    ).encode("utf-8"))
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families=["security"], top=None)
    sec_entries = [e for e in plan["entries"] if e["family"] == "security"]
    assert {e["module"] for e in sec_entries} == {"beta"}
    text = prompts[sec_entries[0]["prompt"]]
    assert "beta/f0.py:1" in text
    assert "gitleaks: hardcoded credential" in text


def test_a_real_root_directory_and_true_repo_root_files_get_separate_module_entries(
    tmp_path: Path,
) -> None:
    """Reviewer-reproduced (task 8 review, finding 1): a repository with a genuine
    top-level directory named ``root`` must not have its leads silently merged
    with true repository-root files under one mislabeled entry. These are two
    different physical scopes and must get two entries, each scoped to only its
    own leads -- unlike the slug-collision case below, this collision happens one
    level upstream of ``unique_slugs``, at module *identity*, so a fix there alone
    could not have caught it."""
    repo = tmp_path / "repo"
    (repo / "root").mkdir(parents=True)
    for i in range(4):
        (repo / "root" / f"f{i}.py").write_text(_todo_file(i), encoding="utf-8")
    (repo / "top.py").write_text(_todo_file(9), encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 2, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    hf_entries = [e for e in plan["entries"] if e["family"] == "half-finished"]
    assert len(hf_entries) == 2, hf_entries
    prompt_paths = {e["prompt"] for e in hf_entries}
    assert len(prompt_paths) == 2, "the two scopes must not share one prompt file"
    root_dir_entry = next(e for e in hf_entries if "root/f0.py" in prompts[e["prompt"]])
    sentinel_entry = next(e for e in hf_entries if e is not root_dir_entry)
    assert "top.py:1" in prompts[sentinel_entry["prompt"]]
    assert "top.py" not in prompts[root_dir_entry["prompt"]]
    for i in range(4):
        assert f"root/f{i}.py" in prompts[root_dir_entry["prompt"]]
        assert f"root/f{i}.py" not in prompts[sentinel_entry["prompt"]]


def test_every_prompt_path_in_a_chunked_plan_is_unique(tmp_path: Path) -> None:
    """Two top-level directories that collide after slugging (``foo_bar`` and
    ``foo-bar`` both slugify to ``foo-bar``) must not overwrite each other's
    prompt: a real collision would make two entries share one ``prompt``/
    ``output`` path, so the plan would dispatch one agent twice and silently
    lose the other module's scout."""
    repo = tmp_path / "repo"
    for module in ("foo_bar", "foo-bar"):
        (repo / module).mkdir(parents=True)
        (repo / module / "a.py").write_text(_todo_file(0), encoding="utf-8")
        (repo / module / "b.py").write_text(_todo_file(1), encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 2, "max_loc": 100000}
    plan, prompts = build_plan(workdir, cfg, families="default", top=None)
    assert plan["chunked"] is True
    hf_entries = [e for e in plan["entries"] if e["family"] == "half-finished"]
    assert {e["module"] for e in hf_entries} == {"foo_bar", "foo-bar"}
    prompt_paths = [e["prompt"] for e in plan["entries"]]
    output_paths = [e["output"] for e in plan["entries"]]
    assert len(prompt_paths) == len(set(prompt_paths)), prompt_paths
    assert len(output_paths) == len(set(output_paths)), output_paths
    assert set(prompts) == set(prompt_paths)
    tokens = {
        e["prompt"].removeprefix("prompts/scout-half-finished-").removesuffix(".md")
        for e in hf_entries
    }
    assert len(tokens) == 2, "the two colliding module names must get distinct tokens"


def test_chunked_plan_goldens_at_full_and_halved_thresholds(
    chunk_tree: tuple[Path, Path],
) -> None:
    """Step 4: one config and one synthetic tree, read at the default (full) and
    deep (halved) thresholds. The tree is sized to exceed both max_files values
    at once, so both plans chunk; what differs between the two goldens is the
    recorded ``thresholds``, family coverage (pipeline-infra is not in the
    default set, so its one lead -- the Dockerfile in ``beta`` -- only reaches an
    entry in the deep/halved plan), and nothing else.
    """
    _, workdir = chunk_tree
    cfg = deepcopy(DEFAULTS)
    cfg["chunking"] = {"max_files": 6, "max_loc": 100000}
    full, _ = build_plan(workdir, cfg, families="default", top=5)
    halved, _ = build_plan(workdir, cfg, families="deep", top=5)
    _check_plan("chunked-plan-full", full, GOLDEN / "chunked-plan-full.json")
    _check_plan("chunked-plan-halved", halved, GOLDEN / "chunked-plan-halved.json")
    assert full["chunked"] is True and halved["chunked"] is True
    assert full["thresholds"] != halved["thresholds"]
    assert set(full["families_run"]) < set(halved["families_run"])


def _docs_with(inventory: dict[str, Any], **extra: dict[str, Any]) -> ScanDocs:
    return ScanDocs(inventory=inventory, **extra)


def _min_inventory() -> dict[str, Any]:
    return {"root": "r", "total_files": 2, "total_loc": 20, "languages": ["python"],
            "git_available": True, "hotspot_band": ["src/hot.py"],
            "files": [{"path": "src/hot.py", "path_class": "source", "hotspot_score": 9.0,
                       "max_indent": 5, "fan_in_approx": 1, "churn": 3},
                      {"path": "src/cold.py", "path_class": "source", "hotspot_score": 0.0,
                       "max_indent": 1, "fan_in_approx": 1, "churn": 0}],
            "boundary_tooling": []}


def test_join_leads_render_under_their_own_headings() -> None:
    coupling = {"pairs": [
        {"a": "src/a.py", "b": "lib/b.py", "shared_commits": 4, "ratio": 0.5,
         "cross_directory": True, "has_edge": False, "edge_direction": None,
         "lead_kind": "modularity-violation"},
        {"a": "src/dep.py", "b": "src/hub.py", "shared_commits": 6, "ratio": 0.6,
         "cross_directory": False, "has_edge": True, "edge_direction": "a->b",
         "lead_kind": "unstable-interface"},
        {"a": "src/x.py", "b": "src/y.py", "shared_commits": 3, "ratio": 0.3,
         "cross_directory": True, "has_edge": True, "edge_direction": "both",
         "lead_kind": None},
        {"a": "src/p.py", "b": "src/q.py", "shared_commits": 2, "ratio": 0.2,
         "cross_directory": False, "has_edge": True, "edge_direction": "both",
         "lead_kind": None},
    ], "cycles": [], "unstable_edges": [], "directories": [], "edges": []}
    leads = leads_for("architecture", _docs_with(_min_inventory(), coupling=coupling), DEFAULTS)
    kinds = {lead.kind for lead in leads}
    assert {"violation", "interface", "coupling"} <= kinds
    assert not any(lead.path == "src/p.py" for lead in leads)
    from plan_scan import render_leads
    text = render_leads(leads)
    assert "Co-change with no import edge (modularity violation):" in text
    assert "Co-change into a high-fan-in file (unstable interface):" in text
    assert "src/a.py <-> lib/b.py" in text and "no edge" in text
    assert "src/dep.py -> src/hub.py" in text


def test_performance_leads_come_from_patterns_tools_and_deep_band_files() -> None:
    patterns = {"leads": {"performance": [
        {"file": "src/cold.py", "line": 4, "rule": "io-in-loop", "quote": "open(p)",
         "path_class": "source", "extra": {"loop_line": 3}}]}, "satd": []}
    signals = {"signals": [{"tool": "ruff", "family": "performance", "kind": "perf-smell",
                            "file": "src/cold.py", "line_start": 9, "message": "PERF401",
                            "fact": False}]}
    docs = _docs_with(_min_inventory(), patterns=patterns, tool_signals=signals)
    leads = leads_for("performance", docs, DEFAULTS)
    kinds = [(lead.kind, lead.path) for lead in leads]
    assert ("hotspot", "src/hot.py") in kinds
    assert ("inventory", "src/hot.py") in kinds        # max_indent 5 on a band file
    assert ("inventory", "src/cold.py") not in kinds   # off band
    assert ("pattern", "src/cold.py") in kinds
    assert ("tool", "src/cold.py") in kinds


def test_concerns_leads_are_candidates_band_pairs_and_structure_never_files() -> None:
    index = {"candidates": [{"name": "format_amount", "tokens": ["format_amount", "formatAmount"],
                             "files": ["src/a.py", "lib/b.py"], "directories": ["lib", "src"],
                             "hotspot_touch": True, "hotspot_share": 0.5, "coupled": False}],
             "directories": [], "stats": {}}
    patterns = {"leads": {"performance": [
        {"file": "src/cold.py", "line": 4, "rule": "io-in-loop", "quote": "open(p)",
         "path_class": "source", "extra": {}}]}, "satd": []}
    docs = _docs_with(_min_inventory(), concern_index=index, patterns=patterns)
    leads = leads_for("concerns", docs, DEFAULTS)
    assert any(lead.kind == "candidate" and "format_amount" in lead.text for lead in leads)
    assert all(lead.kind != "pattern" and lead.kind != "tool" for lead in leads)


def test_concerns_leads_include_directory_aggregates() -> None:
    """Spec 2026-09-12 section 4: "the scout receives the directory aggregates
    [...]". Before fix round 2 (I2), ``concern-index.json``'s ``directories``
    was computed, persisted and never read by anything."""
    index = {"candidates": [], "directories": [
        {"path": "src/billing", "files": 3, "loc": 11, "churn": 3, "fan_in": 1,
         "fan_out": 2, "instability": 0.5},
        {"path": "", "files": 1, "loc": 4, "churn": 1, "fan_in": 0, "fan_out": 0,
         "instability": 0.0},
    ], "stats": {}}
    docs = _docs_with(_min_inventory(), concern_index=index)
    leads = leads_for("concerns", docs, DEFAULTS)
    directory_leads = {lead.path: lead.text for lead in leads if lead.kind == "directory"}
    assert directory_leads["src/billing"] == "files=3 loc=11 churn=3 instability=0.5"
    assert directory_leads["(root)"] == "files=1 loc=4 churn=1 instability=0.0"


def test_concerns_prompt_carries_the_read_budget(tmp_path: Path) -> None:
    from inventory import write_json
    write_json(tmp_path / "inventory.json", _min_inventory())
    write_json(tmp_path / "coupling.json", {"pairs": [], "cycles": [], "unstable_edges": [],
                                             "directories": [], "edges": []})
    write_json(tmp_path / "concern-index.json", {"candidates": [
        {"name": "n", "tokens": ["n"], "files": ["src/a.py", "lib/b.py"],
         "directories": ["lib", "src"], "hotspot_touch": False, "hotspot_share": 0.0,
         "coupled": False}], "directories": [], "stats": {}})
    plan, prompts = build_plan(tmp_path, DEFAULTS, families=["concerns"], top=8)
    text = prompts["prompts/scout-concerns.md"]
    assert "at most 60 files" in text and "at most 10" in text and '"files_read"' in text
    assert plan["entries"][0]["output"] == "scouts/concerns.json"


def test_concerns_and_performance_skip_with_no_leads(tmp_path: Path) -> None:
    from inventory import write_json
    inv = _min_inventory()
    inv["hotspot_band"] = []
    inv["files"][0]["max_indent"] = 1
    write_json(tmp_path / "inventory.json", inv)
    plan, _ = build_plan(tmp_path, DEFAULTS, families="default", top=8)
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert skipped.get("concerns") == "no leads" and skipped.get("performance") == "no leads"


def test_concerns_gets_one_entry_on_a_chunked_plan(tmp_path: Path) -> None:
    from copy import deepcopy

    from inventory import write_json

    inv = _min_inventory()
    inv["files"] = [{"path": f"{d}/f{i}.py", "path_class": "source", "hotspot_score": 1.0,
                     "max_indent": 1, "fan_in_approx": 1, "churn": 1}
                    for d in ("alpha", "beta") for i in range(3)]
    inv["hotspot_band"] = ["alpha/f0.py", "beta/f0.py"]
    write_json(tmp_path / "inventory.json", inv)
    write_json(tmp_path / "coupling.json", {"pairs": [], "cycles": [], "unstable_edges": [],
                                             "directories": [], "edges": []})
    write_json(tmp_path / "concern-index.json", {"candidates": [
        {"name": "n", "tokens": ["n"], "files": ["alpha/f1.py", "beta/f1.py"],
         "directories": ["alpha", "beta"], "hotspot_touch": False, "hotspot_share": 0.0,
         "coupled": False}], "directories": [], "stats": {}})
    config = deepcopy(DEFAULTS)
    config["chunking"]["max_files"] = 2
    plan, prompts = build_plan(tmp_path, config, families=["concerns", "complex-units"], top=8)
    assert plan["chunked"] is True
    concerns = [e for e in plan["entries"] if e["family"] == "concerns"]
    assert len(concerns) == 1 and concerns[0]["module"] is None
    assert "prompts/scout-concerns.md" in prompts
