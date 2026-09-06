"""End-to-end: canned scouts and verdicts through the whole v2 chain to a PBI bundle.

No mocking and no agent: the scout and verdict files are the corpus goldens (real
agent output from the phase 2 live runs), and every other stage is the real script
in the order SKILL.md v2 prescribes. Covers the scan side (signals to design.md),
a user edit, and the promote side (bundle, mark_promoted, idempotent re-run).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from apply_verdicts import apply
from config import DEFAULTS
from design_parser import parse_design
from design_writer import load_inputs, write_design
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from promote import run_promote
from rank import rank
from rules import run_rules
from verify_prompts import build_verify_plan

GOLDEN = Path(__file__).parent / "golden" / "service-py"
CORPUS = Path(__file__).parent / "fixtures" / "corpus" / "service-py"
SCAN_DATE = "2026-09-06"
PROMOTE_DATE = "2026-09-06"


def _copy_golden(relative: str, workdir: Path) -> None:
    """Drop one canned agent reply into the workdir, creating its directory first.

    The scout and verdict outputs are nested (``scouts/`` and ``verdicts/``), and
    only ``scouts/`` is created for us by ``write_plan``; a bare ``shutil.copy``
    of a verdict fails on the missing parent.
    """
    destination = workdir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(GOLDEN / relative, destination)


def _scan(repo: Path, workdir: Path) -> None:
    planted = json.loads((CORPUS / "planted.json").read_bytes())
    inventory, coupling = build_all(repo, churn_months=int(planted["churn_months"]),
                                    config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json",
               {"schema_version": 2, "findings": findings, "leads": leads})
    plan, prompts = build_plan(workdir, DEFAULTS, families="deep", top=5)
    write_plan(workdir, plan, prompts)
    for entry in plan["entries"]:
        _copy_golden(entry["output"], workdir)
    write_json(workdir / "candidates.json", merge(workdir, repo, DEFAULTS))
    vplan, _ = build_verify_plan(workdir, repo, DEFAULTS, 5)
    write_json(workdir / "verify-plan.json", vplan)
    verdicts = {}
    for batch in vplan["batches"]:
        _copy_golden(batch["output"], workdir)
        verdicts[batch["output"]] = json.loads((workdir / batch["output"]).read_bytes())
    candidates = json.loads((workdir / "candidates.json").read_bytes())["candidates"]
    verified = apply(candidates, vplan, verdicts)
    write_json(workdir / "verified.json", verified)
    write_json(workdir / "ranked.json",
               rank(verified, inventory, DEFAULTS, preset="balanced", top=5))
    shutil.copy(GOLDEN / "notes.json", workdir / "notes.json")
    write_design(load_inputs(workdir), SCAN_DATE, workdir / "design.md")


def test_scan_to_promote_over_the_corpus(service_py_repo: Path, tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    _scan(service_py_repo, workdir)
    design = workdir / "design.md"
    parsed = parse_design(design)
    assert parsed["metadata"]["schema_version"] == 2
    assert (workdir / "findings.json").is_file()

    # The user approves the first finding and accepts the second.
    text = design.read_bytes().decode("utf-8")
    first, second = parsed["findings"][0]["slug"], parsed["findings"][1]["slug"]
    lines = text.splitlines()
    for slug, status in ((first, "approved"), (second, "accepted")):
        anchor = next(i for i, line in enumerate(lines) if line.strip() == f"slug: {slug}")
        status_line = next(i for i in range(anchor, 0, -1) if lines[i].startswith("status:"))
        lines[status_line] = f"status: {status}"
    if second:
        anchor = next(i for i, line in enumerate(lines) if line.strip() == f"slug: {second}")
        lines.insert(anchor + 1, "reason: waiting for the payments rewrite")
    design.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))

    out = tmp_path / "pbis"
    result = run_promote(design, out_root=out, date=PROMOTE_DATE)
    assert result.exit_code == 0
    assert result.emitted_count == 1 and result.accepted_count == 1
    bundle = out / f"chore-{first}-{PROMOTE_DATE}"
    pbi = (bundle / "PBI.md").read_text(encoding="utf-8")
    assert "type: feature" in pbi and "status: inbox" in pbi and "target_repo:" in pbi
    assert "fingerprint: " in pbi and "tier: " in pbi
    assert (bundle / "PLAN.md").is_file() and (bundle / "HISTORY.md").is_file()

    # A second promote is a no-op: the finding is now `promoted`.
    again = run_promote(design, out_root=out, date=PROMOTE_DATE)
    assert again.emitted_count == 0 and again.already_promoted_count == 1
    assert again.accepted_count == 1 and again.exit_code == 0


def test_a_v1_design_still_promotes(tmp_path: Path) -> None:
    """Spec 8: the v1 document keeps working after the cut-over.

    The bundle is asserted by content rather than against
    ``golden/bundle/chore-finding-0-2026-05-31``: that golden belongs to
    ``test_bundle_writer.test_v1_finding_still_writes_the_v1_golden_bytes``,
    which builds a different synthetic finding (body ``- foo`` / ``bar``) and
    passes a literal ``source_design`` of ``d.md``. Promoting the real
    ``design-v1.md`` writes the v1 body through and stamps ``source_design``
    with this run's own absolute temp path, so no byte comparison against a
    checked-in bundle can hold for it. What matters here is the v1 shape: the
    v1 anchor's four keys survive, the v2 anchor keys are absent rather than
    invented, and the whole v1 body is copied across.
    """
    design = tmp_path / "design.md"
    shutil.copy(Path(__file__).parent / "golden" / "design-v1.md", design)
    text = design.read_bytes().decode("utf-8").replace("status: pending", "status: approved", 1)
    design.write_bytes(text.encode("utf-8"))
    result = run_promote(design, out_root=tmp_path / "out", date="2026-05-31")
    assert result.exit_code == 0 and result.emitted_count == 1
    bundle = tmp_path / "out" / "chore-finding-0-2026-05-31"
    assert (bundle / "PLAN.md").is_file() and (bundle / "HISTORY.md").is_file()
    pbi = (bundle / "PBI.md").read_text(encoding="utf-8")
    assert "id: chore-finding-0-2026-05-31" in pbi
    assert "severity: critical" in pbi and "category: god-modules" in pbi
    assert "fingerprint:" not in pbi and "tier:" not in pbi, "v1 has no v2 anchor keys"
    for section in ("# Finding 0 title", "### Reasoning", "reasoning 0",
                    "### Evidence", "### Suggested fix", "fix 0"):
        assert section in pbi, section
    plan = (bundle / "PLAN.md").read_text(encoding="utf-8")
    assert "- [ ] 1. Address the tech-debt finding described in PBI.md." in plan
    assert "status: promoted" in design.read_text(encoding="utf-8")
