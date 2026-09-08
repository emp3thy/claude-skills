"""End-to-end: canned scouts and verdicts through the whole v2 chain to a PBI bundle.

No mocking and no agent: the scout and verdict files are the corpus goldens (real
agent output from the phase 2 live runs), and every other stage is the real script
in the order SKILL.md v2 prescribes. Covers the scan side (signals to design.md),
a user edit, and the promote side (bundle, mark_promoted, idempotent re-run), plus
phase 5a's baseline sequence (scan, decide, re-scan) in
``test_scan_decide_rescan_baseline_sequence``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from apply_verdicts import apply
from baseline import _main as baseline_main
from baseline import load_baseline
from config import DEFAULTS
from design_parser import parse_design
from design_writer import load_inputs, write_design
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from promote import _main as promote_main
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


def _apply_decisions(
    design: Path, decisions: list[tuple[str, str, str | None, str | None]]
) -> None:
    """Hand-edit ``design.md``: flip each finding's ``status:`` and insert
    ``reason:`` / ``until:`` right after its ``slug:`` anchor line.

    ``decisions`` is ``(slug, status, reason, until)``; ``reason`` and ``until``
    are each omitted (``None``) rather than inserted when a finding does not
    carry one. Mirrors the substitution pattern in
    ``test_scan_to_promote_over_the_corpus``: find the ``slug: <slug>`` anchor
    line, walk back to its ``status:`` line and rewrite it, then insert any
    extra keys after the slug line -- the same place a human reviewer would
    hand-type them.
    """
    lines = design.read_bytes().decode("utf-8").splitlines()
    for slug, status, reason, until in decisions:
        anchor = next(i for i, line in enumerate(lines) if line.strip() == f"slug: {slug}")
        status_line = next(i for i in range(anchor, 0, -1) if lines[i].startswith("status:"))
        lines[status_line] = f"status: {status}"
        insert_at = anchor + 1
        if reason is not None:
            lines.insert(insert_at, f"reason: {reason}")
            insert_at += 1
        if until is not None:
            lines.insert(insert_at, f"until: {until}")
    design.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


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


# Fingerprints and slugs of the corpus's first three top-N findings (see
# tests/golden/service-py/design.md); all three cite src/pay/refund.py, which
# Ruling 3 (see the RESOLVED step below) requires -- and the spec says a
# finding sharing that file with a resolved one must keep matching by
# fingerprint and stay UNCHANGED, so reusing the same file for all three is
# exactly the case this test needs to cover, not an accident of the corpus.
_FP_REJECTED = "2e969b3499636196"
_SLUG_REJECTED = "ledger-post-failure-silently-swallowed-before-gateway-refund-fir"
_FP_ACCEPTED = "b459099b48e0a272"
_SLUG_ACCEPTED = "self-admitted-duplicate-refund-risk-left-unaddressed"
_FP_PROMOTED = "cad19db020b88f9f"
_SLUG_PROMOTED = "ownership-gaps-in-src-pay-refund-py"
# A year past SCAN_DATE, and one day past that -- the acceptance's `until` and
# the date `diff` must treat it as expired by.
_UNTIL = "2027-09-06"
_PAST_UNTIL = "2027-09-07"


def test_scan_decide_rescan_baseline_sequence(service_py_repo: Path, tmp_path: Path) -> None:
    """Phase 5a's promise as a sequence: a scan, a human decision, then three
    re-scans that exercise every classification ``baseline.diff`` can produce.

    Step 5 below deletes a file from the repository, so every step runs
    against a private copy of the session-scoped ``service_py_repo`` fixture
    (``shutil.copytree``), never the fixture path other tests share.
    """
    repo = tmp_path / "repo"
    shutil.copytree(service_py_repo, repo)
    workdir = tmp_path / "wd"

    # Step 1: scan with no baseline at all; every finding renders NEW, the
    # default `_diff_for` gives a fingerprint with no diff.json to look up.
    _scan(repo, workdir)
    design = workdir / "design.md"
    parsed = parse_design(design)
    assert parsed["findings"]
    assert all(f["diff"] == "NEW" for f in parsed["findings"])
    by_fp = {f["fingerprint"]: f for f in parsed["findings"]}
    assert by_fp[_FP_REJECTED]["slug"] == _SLUG_REJECTED
    assert by_fp[_FP_ACCEPTED]["slug"] == _SLUG_ACCEPTED
    assert by_fp[_FP_PROMOTED]["slug"] == _SLUG_PROMOTED

    # Step 2: the user rejects one finding, accepts another (deferring past an
    # expiry), and approves a third; `promote --baseline` emits the approved
    # finding's bundle, flips it to `promoted` in design.md, and records every
    # decision -- including every still-`pending` finding that carries a yaml
    # anchor -- into a fresh baseline.
    _apply_decisions(design, [
        (_SLUG_REJECTED, "rejected", "flaky pipeline, tracked in a separate ticket", None),
        (_SLUG_ACCEPTED, "accepted", "waiting for the payments rewrite", _UNTIL),
        (_SLUG_PROMOTED, "approved", None, None),
    ])
    out = tmp_path / "pbis"
    baseline_path = workdir / "baseline.json"
    assert promote_main(
        [str(design), "--out", str(out), "--baseline", str(baseline_path)]
    ) == 0

    doc = load_baseline(baseline_path)
    assert doc is not None
    assert doc["findings"][_FP_REJECTED]["status"] == "rejected"
    assert doc["findings"][_FP_REJECTED]["reason"] == \
        "flaky pipeline, tracked in a separate ticket"
    assert doc["findings"][_FP_ACCEPTED]["status"] == "accepted"
    assert doc["findings"][_FP_ACCEPTED]["until"] == _UNTIL
    assert doc["findings"][_FP_ACCEPTED]["reason"] == "waiting for the payments rewrite"
    assert doc["findings"][_FP_PROMOTED]["status"] == "promoted"
    bundle_name = doc["findings"][_FP_PROMOTED]["bundle"]
    assert bundle_name and (out / bundle_name).is_dir()

    # Ruling 25: `record` remembers every finding verified.json carried, not
    # only the ones the design document had a decision for -- so step 2's
    # baseline holds one entry per verified finding, tier-C and unverified
    # ones (no yaml anchor, no decision) included. Not hardcoded: the golden
    # corpus could change how many verified findings it carries.
    verified_step2 = json.loads((workdir / "verified.json").read_bytes())
    assert len(doc["findings"]) == len(verified_step2["findings"])

    # Step 3: diff the same verified.json against that baseline, still at the
    # scan's own date. The rejected and accepted findings are suppressed (and
    # so absent from the rendered body); every other finding is UNCHANGED --
    # the promoted one (a fingerprint match against its own `promoted`
    # entry), every other finding the document actually renders (its
    # `pending` baseline entry recorded in step 2 also matches by
    # fingerprint), and, since the fix above, the tier-C/unverified findings
    # that carry no yaml anchor and so never had a decision either: step 2's
    # fill-in recorded each of those as `pending` too, so they now match by
    # fingerprint instead of reading NEW. Nothing on disk or in verified.json
    # has changed, so `new` is zero and no entry in the raw `status` map is
    # anything but UNCHANGED.
    assert baseline_main([
        "diff", "--workdir", str(workdir), "--root", str(repo),
        "--baseline", str(baseline_path), "--today", SCAN_DATE,
    ]) == 0
    diff_doc = json.loads((workdir / "diff.json").read_bytes())
    assert {e["fingerprint"] for e in diff_doc["suppressed"]} == {_FP_REJECTED, _FP_ACCEPTED}
    assert diff_doc["counts"]["suppressed"] == 2
    assert diff_doc["counts"]["resolved"] == 0
    assert diff_doc["counts"]["expired"] == 0
    assert diff_doc["counts"]["new"] == 0
    assert _FP_REJECTED not in diff_doc["status"] and _FP_ACCEPTED not in diff_doc["status"]
    assert diff_doc["status"][_FP_PROMOTED] == {
        "diff": "UNCHANGED", "note": None, "matched": _FP_PROMOTED,
    }
    assert all(entry["diff"] == "UNCHANGED" for entry in diff_doc["status"].values())

    design2 = workdir / "design-2.md"
    write_design(load_inputs(workdir), SCAN_DATE, design2)
    parsed2 = parse_design(design2)
    fps2 = {f["fingerprint"] for f in parsed2["findings"]}
    assert _FP_REJECTED not in fps2 and _FP_ACCEPTED not in fps2
    assert _FP_PROMOTED in fps2
    promoted_row = next(f for f in parsed2["findings"] if f["fingerprint"] == _FP_PROMOTED)
    assert promoted_row["status"] == "pending"  # the document is regenerated fresh
    assert promoted_row["diff"] == "UNCHANGED"
    assert all(f["diff"] == "UNCHANGED" for f in parsed2["findings"])
    assert parsed2["metadata"]["counts"]["suppressed"] == 2
    assert parsed2["metadata"]["counts"]["resolved"] == 0
    assert parsed2["metadata"]["counts"]["new"] == 0

    # Step 4: diff again, now past the acceptance's `until`. The accepted
    # finding is no longer suppressed -- it is back in the body -- and reports
    # why: an expiry note, counted once. The rejection has no expiry and stays
    # suppressed regardless of the date.
    assert baseline_main([
        "diff", "--workdir", str(workdir), "--root", str(repo),
        "--baseline", str(baseline_path), "--today", _PAST_UNTIL,
    ]) == 0
    diff_doc = json.loads((workdir / "diff.json").read_bytes())
    assert diff_doc["status"][_FP_ACCEPTED] == {
        "diff": "UNCHANGED", "note": "acceptance expired", "matched": _FP_ACCEPTED,
    }
    assert diff_doc["counts"]["expired"] == 1
    assert {e["fingerprint"] for e in diff_doc["suppressed"]} == {_FP_REJECTED}

    design3 = workdir / "design-3.md"
    write_design(load_inputs(workdir), SCAN_DATE, design3)
    parsed3 = parse_design(design3)
    fps3 = {f["fingerprint"] for f in parsed3["findings"]}
    assert _FP_ACCEPTED in fps3  # back in the body
    assert _FP_REJECTED not in fps3  # still suppressed, and not time-limited

    # Step 5: the rejected finding's code is deleted outright. It is also
    # removed from this scan's own verified.json -- Ruling 3: a baseline entry
    # is RESOLVED only when no *current* finding matches it, and simply
    # replaying the same verified.json would still carry the same fingerprint
    # and so still match (and so still be suppressed, never RESOLVED). The
    # file is named by the finding's own primary evidence item, read before it
    # is dropped from verified.json. Back at the scan's own date (an expired
    # `until` plays no part in RESOLVED).
    verified_path = workdir / "verified.json"
    verified = json.loads(verified_path.read_bytes())
    rejected_entry = next(f for f in verified["findings"] if f["fingerprint"] == _FP_REJECTED)
    victim_file = repo / rejected_entry["evidence"][0]["file"]
    verified["findings"] = [f for f in verified["findings"] if f["fingerprint"] != _FP_REJECTED]
    verified_path.write_bytes(json.dumps(verified).encode("utf-8"))
    victim_file.unlink()

    assert baseline_main([
        "diff", "--workdir", str(workdir), "--root", str(repo),
        "--baseline", str(baseline_path), "--today", SCAN_DATE,
    ]) == 0
    diff_doc = json.loads((workdir / "diff.json").read_bytes())
    assert diff_doc["status"][_FP_REJECTED] == {
        "diff": "RESOLVED", "note": "file absent", "matched": None,
    }
    assert diff_doc["counts"]["resolved"] == 1
    # The accepted finding is suppressed again (today is back before `until`),
    # and other findings that also cite src/pay/refund.py -- the promoted one
    # among them -- still match by fingerprint and stay UNCHANGED: deleting
    # the file affects only the entry nothing currently matches.
    assert {e["fingerprint"] for e in diff_doc["suppressed"]} == {_FP_ACCEPTED}
    assert diff_doc["status"][_FP_PROMOTED] == {
        "diff": "UNCHANGED", "note": None, "matched": _FP_PROMOTED,
    }

    design4 = workdir / "design-4.md"
    write_design(load_inputs(workdir), SCAN_DATE, design4)
    parsed4 = parse_design(design4)
    assert parsed4["metadata"]["counts"]["resolved"] == 1
    fps4 = {f["fingerprint"] for f in parsed4["findings"]}
    assert _FP_REJECTED not in fps4  # gone from verified.json entirely, not just suppressed
    assert _FP_PROMOTED in fps4
