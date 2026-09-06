"""End-to-end walk through the full scan -> review -> promote flow.

No mocking: the Agent dispatch step (Claude running the six scouts) is simply
skipped and replaced by canned golden JSON, exactly as a real run would have
produced. Everything else is the real helper scripts wired in the order
SKILL.md prescribes, so this test is pure deterministic file IO.

Covered:
  - the scan-side contract (raw-findings.json -> build_prompt -> top5.json
    validates against the strict synthesis schema);
  - render design.md, a user editing status, then promote;
  - the multi-bundle path (two approved findings, slug-list mark_promoted);
  - idempotent re-run via collision detection;
  - the invalid-status -> exit 2 error path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# The v1 synthesis path this file drives (build_synthesis_prompt.py and
# design_writer.render_design_md) is replaced by the v2 chain in phase 3.
# render_design_md no longer exists, so the module cannot even be imported;
# the skip therefore sits above the imports and covers every test here.
# Task 8 of the phase 3 plan rewrites this file and removes the skip.
pytest.skip(
    "v1 synthesis path; rewritten in Task 8 of the phase 3 plan",
    allow_module_level=True,
)

from build_synthesis_prompt import build_prompt, validate_synthesis_output  # noqa: E402
from design_writer import render_design_md  # noqa: E402
from inventory import walk_inventory  # noqa: E402
from promote import run_promote  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"
SCAN_DATE = "2026-05-31"


def _load_top5_text() -> str:
    return (GOLDEN / "top5.json").read_text(encoding="utf-8")


def test_golden_top5_conforms_to_synthesis_schema():
    """Self-validating fixture: the hand-authored top5 must pass Task 4's
    validator, so drift in either the schema or the golden fails fast."""
    result = validate_synthesis_output(_load_top5_text())
    assert len(result["top5"]) == 5


def test_scan_side_contract_raw_findings_to_top5():
    """raw-findings.json feeds build_prompt, and the synthesis reply
    (top5.json) validates -- the read end of the scan stage."""
    raw = json.loads((GOLDEN / "raw-findings.json").read_text(encoding="utf-8"))
    assert isinstance(raw, list) and len(raw) == 30
    prompt = build_prompt(raw)
    assert '"top5"' in prompt and "slug" in prompt
    validate_synthesis_output(_load_top5_text())  # no raise


@pytest.mark.parametrize("fixture", ["multi-lang-repo", "python-repo"])
def test_e2e_scan_then_promote(tmp_path: Path, fixture: str):
    # --- Step 1: inventory (real walk over a fixture repo) ---
    inv = walk_inventory(FIXTURES / fixture)
    assert inv["total_files"] > 0

    # --- Steps 2-4: scout dispatch + persistence + synthesis are skipped;
    #     a real run hands the golden top5 straight from the synthesis model.
    top5 = json.loads(_load_top5_text())

    # --- Step 5: render design.md ---
    design_path = tmp_path / "design.md"
    render_design_md(top5=top5, inventory=inv, scan_date=SCAN_DATE, out_path=design_path)

    # --- User edits status: pending -> approved for the first finding ---
    text = design_path.read_text(encoding="utf-8")
    design_path.write_text(text.replace("status: pending", "status: approved", 1), encoding="utf-8")

    # --- Promote ---
    out_root = tmp_path / "tech-debt-pbis"
    result = run_promote(design_path, out_root=out_root, date=SCAN_DATE)
    assert result.exit_code == 0
    assert result.emitted_count == 1
    pbi = out_root / "chore-finding-0-2026-05-31" / "PBI.md"
    assert pbi.exists()
    pbi_text = pbi.read_text(encoding="utf-8")
    assert "type: feature" in pbi_text
    assert "target_repo:" in pbi_text
    # design.md mutated to promoted for the emitted finding only
    assert "status: promoted" in design_path.read_text(encoding="utf-8")

    # --- Idempotent re-run: collision detected, nothing new emitted ---
    result2 = run_promote(design_path, out_root=out_root, date=SCAN_DATE)
    assert result2.exit_code == 0
    assert result2.emitted_count == 0
    assert result2.already_promoted_count == 1


def test_e2e_two_approved_emits_two_bundles(tmp_path: Path):
    """Exercises the multi-bundle path + mark_promoted over a slug list."""
    inv = walk_inventory(FIXTURES / "multi-lang-repo")
    top5 = json.loads(_load_top5_text())
    design_path = tmp_path / "design.md"
    render_design_md(top5=top5, inventory=inv, scan_date=SCAN_DATE, out_path=design_path)

    text = design_path.read_text(encoding="utf-8")
    design_path.write_text(text.replace("status: pending", "status: approved", 2), encoding="utf-8")

    out_root = tmp_path / "tech-debt-pbis"
    result = run_promote(design_path, out_root=out_root, date=SCAN_DATE)
    assert result.exit_code == 0
    assert result.emitted_count == 2
    assert (out_root / "chore-finding-0-2026-05-31").is_dir()
    assert (out_root / "chore-finding-1-2026-05-31").is_dir()
    assert design_path.read_text(encoding="utf-8").count("status: promoted") == 2


def test_e2e_invalid_status_exits_2(tmp_path: Path):
    inv = walk_inventory(FIXTURES / "multi-lang-repo")
    top5 = json.loads(_load_top5_text())
    design_path = tmp_path / "design.md"
    render_design_md(top5=top5, inventory=inv, scan_date=SCAN_DATE, out_path=design_path)

    text = design_path.read_text(encoding="utf-8")
    design_path.write_text(text.replace("status: pending", "status: yes", 1), encoding="utf-8")

    result = run_promote(design_path, out_root=tmp_path / "out", date=SCAN_DATE)
    assert result.exit_code == 2
