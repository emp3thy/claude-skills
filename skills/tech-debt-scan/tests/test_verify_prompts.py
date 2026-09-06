"""verify_prompts.py: budget rule, batching, context, traps, contract (spec 4.8)."""
from __future__ import annotations

import dataclasses
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import verify_prompts
from categories import FAMILIES, FAMILY_BLOCKS, SEVERITY_RUBRIC
from config import DEFAULTS
from evidence import fingerprint, priority_terms, repo_maxima
from inventory import build_all, write_json, write_outputs
from verify_prompts import (
    FAMILY_TRAPS_HEADER,
    REPO_TRAPS_HEADER,
    VERDICT_SCHEMA,
    _main,
    _span,
    build_batches,
    build_verify_plan,
    render_verify_prompt,
    select_candidates,
)


def _cand(family: str, file: str, start: int, sev: int, *, tier: str | None = None,
          hotspot: float = 0.0, coupling: int = 0, effort: str = "M") -> dict[str, Any]:
    quote = f"line {start}"
    fp, qh = fingerprint(family, file, quote)
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code", "type_id": None,
        "title": f"{family} {file}:{start}", "severity": sev, "effort": effort, "source": "scout",
        "rule_id": None, "note": "n",
        "evidence": [{"file": file, "line_start": start, "line_end": start, "quote": quote,
                      "quote_verified": True}],
        "confirmed_by": [f"scout:{family}"], "signals_cited": [],
        "signals": {"hotspot_score": hotspot, "churn": 0, "coupling_degree": coupling,
                    "fan_in_approx": None, "path_class": "source",
                    "in_hotspot_band": hotspot > 0.5},
        "tier": tier,
    }


def test_priority_terms_reproduce_the_spec_worked_example() -> None:
    maxima = {"hotspot": 1.0, "coupling": 10, "fan_in": 10}
    weights, tract = DEFAULTS["ranking"]["weights"], DEFAULTS["ranking"]["tractability"]
    x = {"severity": 4, "effort": "M",
         "signals": {"hotspot_score": 0.8, "coupling_degree": 4, "fan_in_approx": 2}}
    terms = priority_terms(x, maxima, weights, tract, tier="A", fan_in_mode="import-lines")
    assert terms == {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
                     "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    y = {"severity": 5, "effort": "S",
         "signals": {"hotspot_score": 0, "coupling_degree": 0, "fan_in_approx": None}}
    assert priority_terms(
        y, maxima, weights, tract, tier="B", fan_in_mode="import-lines")["priority"] == 3.5
    z = {"severity": 3, "effort": "L",
         "signals": {"hotspot_score": 1.0, "coupling_degree": 10, "fan_in_approx": 5}}
    assert priority_terms(
        z, maxima, weights, tract, tier="A", fan_in_mode="import-lines")["priority"] == 4.125
    assert priority_terms(z, maxima, weights, tract, tier="A", fan_in_mode="anywhere")["F"] == 0


def test_budget_rule_floors_inclusions_cap_and_tier_a_exclusion() -> None:
    cands = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(80)]
    cands += [_cand("security", "src/s.py", 1, 1), _cand("dead-code", "src/hi.py", 1, 5),
              _cand("pipeline-infra", "Dockerfile", 1, 3, tier="A")]
    selected, unverified = select_candidates(cands, DEFAULTS, top=5)
    fps = {c["fingerprint"] for c in selected}
    assert len(selected) <= DEFAULTS["verifier"]["max_candidates"] == 72
    assert cands[80]["fingerprint"] in fps, "always_families includes security"
    assert cands[81]["fingerprint"] in fps, "always_min_severity 5"
    assert cands[82]["fingerprint"] not in fps and cands[82]["fingerprint"] not in unverified
    assert len(fps) + len(unverified) == 82
    few = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(20)]
    sel, unv = select_candidates(few, DEFAULTS, top=2)
    assert len(sel) == 20 and unv == [], "max(3N, 30) floor covers all twenty"
    top_multiple = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(40)]
    sel, unv = select_candidates(top_multiple, DEFAULTS, top=12)
    assert len(sel) == 36 and len(unv) == 4, "3N beats the 30 floor at N=12"


def test_provisional_ranking_normalises_coupling_over_the_pool() -> None:
    """A raw coupling_degree of 12 must not outweigh severity once C is normalised.

    Unit maxima would give the coupling-heavy candidate C=12 (uncapped), so its
    priority (2 * 7.0 * ...) beats every severity-4 candidate (4 * 1.0 * ...) and
    it gets selected. Normalised over the pool, C=1.0: 2 * (1 + 0.5 * 1) = 3.0
    loses to 4 * 1 = 4.0, so it should rank last and land in ``unverified``.
    """
    coupling_heavy = _cand("dead-code", "src/heavy.py", 1, 2, coupling=12)
    plain = [_cand("dead-code", f"src/p{i}.py", 1, 4) for i in range(34)]
    cands = [coupling_heavy] + plain
    selected, unverified = select_candidates(cands, DEFAULTS, top=5)
    fps = {c["fingerprint"] for c in selected}
    assert len(cands) == 35
    assert len(selected) == 30 and len(unverified) == 5
    assert coupling_heavy["fingerprint"] not in fps
    assert coupling_heavy["fingerprint"] in unverified


def test_batches_group_by_file_and_size() -> None:
    cands = [_cand("dead-code", "src/a.py", i, 2) for i in range(1, 8)]
    cands += [_cand("dead-code", "src/b.py", 1, 4)]
    selected, _ = select_candidates(cands, DEFAULTS, top=5)
    batches = build_batches(selected, DEFAULTS["verifier"]["batch_size"])
    assert [len(b) for b in batches] == [6, 2]
    assert {c["evidence"][0]["file"] for c in batches[0]} == {"src/a.py"}


def test_prompt_renders_context_coupling_questions_traps_and_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    body = "\n".join(f"line {i}" for i in range(1, 101)) + "\n"
    # Module stems of four or more characters: a one-character stem is below
    # ``fan_in.min_stem_length`` and the graph would have no edges to render.
    (repo / "src" / "payments.py").write_text(body, encoding="utf-8")
    (repo / "src" / "caller.py").write_text(
        'token = "abcdefghijkl0123"\nfrom payments import x\n', encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    coupling["pairs"] = [{"a": "src/payments.py", "b": "src/caller.py", "shared_commits": 4,
                          "ratio": 0.8, "cross_directory": False}]
    cfg = deepcopy(DEFAULTS)
    cfg["traps"] = [
        {"family": "dead-code", "path_glob": "src/*.py", "note": "entry points live here"},
        {"family": "security", "path_glob": "src/*.py", "note": "never shown"},
    ]
    cand = _cand("dead-code", "src/payments.py", 50, 3)
    cand["evidence"].append({"file": "src/caller.py", "line_start": 1, "line_end": 1,
                             "quote": 'token = "abcdefghijkl0123"', "quote_verified": True})
    text = render_verify_prompt(
        [cand], root=repo, inventory=inventory, coupling=coupling, config=cfg)
    assert cand["fingerprint"] in text
    assert "    20 | line 20" in text and "    80 | line 80" in text and "    19 | " not in text
    assert ">    50 | line 50" in text
    assert "src/caller.py" in text and "shared=4" in text
    assert "Which dynamic-reference patterns were checked" in text
    assert "entry points live here" in text and "never shown" not in text
    assert "up to three further files" in text
    assert "abcdefghijkl0123" not in text and "abcd***" in text
    assert SEVERITY_RUBRIC not in text
    assert '"verdict"' in text and '"trap_matched"' in text and '"opened"' in text
    assert "approximate referrers: src/caller.py" in text


def test_span_clamps_at_file_boundaries(tmp_path: Path) -> None:
    """Context never runs off either end of the file, and an empty file renders a header only."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "five.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 6)) + "\n", encoding="utf-8")
    (repo / "src" / "empty.py").write_text("", encoding="utf-8")

    at_start = _span(repo, {"file": "src/five.py", "line_start": 1, "line_end": 1}, 2)
    assert at_start.splitlines() == [
        "src/five.py:1-1", ">     1 | line 1", "      2 | line 2", "      3 | line 3"]

    at_end = _span(repo, {"file": "src/five.py", "line_start": 5, "line_end": 5}, 2)
    assert at_end.splitlines() == [
        "src/five.py:5-5", "      3 | line 3", "      4 | line 4", ">     5 | line 5"]

    whole = _span(repo, {"file": "src/five.py", "line_start": 1, "line_end": 5}, 30)
    assert whole.splitlines()[1] == ">     1 | line 1"
    assert whole.splitlines()[-1] == ">     5 | line 5"

    empty = _span(repo, {"file": "src/empty.py", "line_start": 1, "line_end": 1}, 2)
    assert empty.splitlines() == ["src/empty.py:1-1"]


def test_the_reference_graph_never_reads_guarded_or_out_of_graph_files(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The referrer graph honours the size guard and reads only source and tests files.

    ``build_reference_graph`` uses source files as targets and source or tests
    files as referrers, so every other class is read for nothing; a file the
    inventory marked ``skipped_large`` was never read by the inventory and must
    not be read here either. This call passes no ``edges``, so it builds the
    graph itself, which is the path a single-prompt caller takes.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "docs").mkdir(parents=True)
    (repo / "src" / "payments.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 6)) + "\n", encoding="utf-8")
    (repo / "src" / "caller.py").write_text("from payments import x\n", encoding="utf-8")
    (repo / "src" / "huge.py").write_text("from payments import y\n", encoding="utf-8")
    (repo / "docs" / "guide.md").write_text("from payments import z\n", encoding="utf-8")
    inventory = {
        "files": [
            {"path": "src/payments.py", "path_class": "source", "language": "python",
             "loc": 5, "churn": 0, "skipped_large": False},
            {"path": "src/caller.py", "path_class": "source", "language": "python",
             "loc": 1, "churn": 0, "skipped_large": False},
            {"path": "src/huge.py", "path_class": "source", "language": "python",
             "loc": 0, "churn": 0, "skipped_large": True},
            {"path": "docs/guide.md", "path_class": "docs", "language": "markdown",
             "loc": 1, "churn": 0, "skipped_large": False},
        ]
    }
    reads: list[str] = []
    original = Path.read_bytes

    def _record(self: Path) -> bytes:
        reads.append(self.as_posix())
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", _record)
    cand = _cand("dead-code", "src/payments.py", 1, 3)
    text = render_verify_prompt(
        [cand], root=repo, inventory=inventory, coupling={}, config=DEFAULTS)

    assert not [p for p in reads if p.endswith("src/huge.py")], "the size guard was bypassed"
    assert not [p for p in reads if p.endswith("docs/guide.md")], "a docs file was read"
    assert [p for p in reads if p.endswith("src/caller.py")], "the referrer was not read"
    assert "approximate referrers: src/caller.py" in text


def test_a_reference_graph_failure_leaves_the_prompt_intact(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("line 1\n", encoding="utf-8")
    cand = _cand("dead-code", "src/a.py", 1, 3)
    text = render_verify_prompt([cand], root=repo, inventory={"files": [{"no_path_key": True}]},
                                coupling={}, config=DEFAULTS)
    assert "approximate referrers: not computed" in text
    assert cand["fingerprint"] in text and '"verdict"' in text
    assert "change-coupled files: none" in text


def test_verify_plan_and_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 20)) + "\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    workdir = tmp_path / "wd"
    write_outputs(inventory, coupling, workdir)
    cands = [_cand("dead-code", "src/a.py", i, 2) for i in range(1, 9)]
    cands.append(_cand("pipeline-infra", "src/a.py", 9, 3, tier="A"))
    write_json(workdir / "candidates.json",
               {"schema_version": 2, "candidates": cands, "open_questions": [],
                "looks_bad_but_fine": [], "stats": {}})
    plan, prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
    assert list(plan) == ["schema_version", "top", "batch_size", "selected", "unverified",
                          "batches"]
    assert plan["selected"] == [c["fingerprint"] for b in plan["batches"]
                                for c in [{"fingerprint": f} for f in b["fingerprints"]]]
    assert [b["prompt"] for b in plan["batches"]] == ["prompts/verify-01.md",
                                                      "prompts/verify-02.md"]
    assert [b["output"] for b in plan["batches"]] == ["verdicts/verify-01.json",
                                                      "verdicts/verify-02.json"]
    assert set(prompts) == {"prompts/verify-01.md", "prompts/verify-02.md"}
    assert cands[-1]["fingerprint"] not in plan["selected"]
    assert _main(["--workdir", str(workdir), "--top", "5"]) == 0
    raw = (workdir / "prompts" / "verify-01.md").read_bytes()
    assert b"\r" not in raw
    assert json.loads((workdir / "verify-plan.json").read_bytes())["top"] == 5
    # Phase 3 writes each batch's reply to the plan's `output` path under verdicts/;
    # the directory is created here so an agent's write never hits a missing parent.
    assert (workdir / "verdicts").is_dir()
    assert _main(["--workdir", str(tmp_path / "none")]) == 2


def test_the_reference_graph_is_built_once_per_plan(tmp_path: Path, monkeypatch: Any) -> None:
    """One stem graph per plan, not one per batch.

    ``_reference_edges`` reads every source and tests file in the inventory, so
    building it inside ``render_verify_prompt`` re-read the whole repository once
    for each batch (12 times at ``max_candidates``).
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "payments.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 20)) + "\n", encoding="utf-8")
    (repo / "src" / "caller.py").write_text("from payments import x\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    workdir = tmp_path / "wd"
    write_outputs(inventory, coupling, workdir)
    cands = [_cand("dead-code", "src/payments.py", i, 2) for i in range(1, 9)]
    write_json(workdir / "candidates.json",
               {"schema_version": 2, "candidates": cands, "open_questions": [],
                "looks_bad_but_fine": [], "stats": {}})

    builds: list[int] = []
    original = verify_prompts.build_reference_graph

    def _record(files: Any, config: Any) -> Any:
        builds.append(len(files))
        return original(files, config)

    monkeypatch.setattr(verify_prompts, "build_reference_graph", _record)
    plan, prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)

    assert len(plan["batches"]) == 2
    assert len(builds) == 1, f"the graph was built {len(builds)} times"
    assert all("approximate referrers: src/caller.py" in text for text in prompts.values())


def test_cli_reports_a_malformed_candidates_document_instead_of_a_traceback(
    tmp_path: Path, capsys: Any
) -> None:
    """Bad JSON and a document without ``candidates`` both exit 2 with an ``error:`` line."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("line 1\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    workdir = tmp_path / "wd"
    write_outputs(inventory, coupling, workdir)

    (workdir / "candidates.json").write_bytes(b"{ not json")
    assert _main(["--workdir", str(workdir)]) == 2
    assert "error:" in capsys.readouterr().err

    write_json(workdir / "candidates.json", {"schema_version": 2})
    assert _main(["--workdir", str(workdir)]) == 2
    assert "error:" in capsys.readouterr().err

    (workdir / "inventory.json").write_bytes(b"[]")
    assert _main(["--workdir", str(workdir)]) == 2
    assert "error:" in capsys.readouterr().err


def test_verdict_schema_shape() -> None:
    item = VERDICT_SCHEMA["items"]
    assert VERDICT_SCHEMA["type"] == "array"
    assert set(item["required"]) == {"fingerprint", "verdict", "proof", "severity", "effort",
                                     "trap_matched", "checked", "opened"}
    assert item["properties"]["verdict"]["enum"] == ["confirm", "downgrade", "reject", "refer"]
    assert repo_maxima({"files": []}) == {"hotspot": 0.0, "coupling": 0, "fan_in": 0}


def test_prompt_carries_the_family_traps_before_the_repository_traps(tmp_path: Path) -> None:
    """The family block's own traps reach the verifier, ahead of the repository's."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "payments.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 21)) + "\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    cfg = deepcopy(DEFAULTS)
    cfg["traps"] = [
        {"family": "error-masking", "path_glob": "src/*.py", "note": "the repository's own trap"},
    ]
    text = render_verify_prompt(
        [_cand("error-masking", "src/payments.py", 5, 3)],
        root=repo, inventory=inventory, coupling=coupling, config=cfg,
    )
    assert FAMILY_TRAPS_HEADER in text
    assert (
        "A catch at a process or request boundary that reports and continues is correct." in text
    )
    assert "A retry loop that re-raises after the last attempt is not masking." in text
    assert text.index(FAMILY_TRAPS_HEADER) < text.index(REPO_TRAPS_HEADER)


def test_every_family_renders_its_own_trap_list(tmp_path: Path) -> None:
    """Every one of the fourteen families carries its block's traps into the prompt."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "payments.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 21)) + "\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    for family in FAMILIES:
        text = render_verify_prompt(
            [_cand(family, "src/payments.py", 5, 3)],
            root=repo, inventory=inventory, coupling=coupling, config=DEFAULTS,
        )
        assert FAMILY_TRAPS_HEADER in text, family
        for trap in FAMILY_BLOCKS[family].traps:
            assert trap in text, (family, trap)


def test_credential_shaped_family_trap_is_redacted_in_the_prompt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A family block's own trap text is redacted, same as every other prompt line (spec 4.3/4.4).

    None of the fourteen real family blocks' traps happen to contain a
    credential-shaped string, so ``test_every_family_renders_its_own_trap_list``
    stays green even if the ``redact(`` call were deleted from the family-traps
    line in ``render_verify_prompt``. This monkeypatches one block's traps
    with a credential-shaped string so the redaction itself is pinned, not
    merely applied.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "payments.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 21)) + "\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    secret_trap = 'ignore token = "abcdefghijkl0123" in fixtures'
    replaced = dataclasses.replace(FAMILY_BLOCKS["error-masking"], traps=(secret_trap,))
    monkeypatch.setitem(FAMILY_BLOCKS, "error-masking", replaced)

    text = render_verify_prompt(
        [_cand("error-masking", "src/payments.py", 5, 3)],
        root=repo, inventory=inventory, coupling=coupling, config=DEFAULTS,
    )

    assert "abcdefghijkl0123" not in text
    assert FAMILY_TRAPS_HEADER in text
    lines = text.splitlines()
    trap_line = lines[lines.index(FAMILY_TRAPS_HEADER) + 1]
    assert trap_line == '  - ignore token = "abcd***" in fixtures'
