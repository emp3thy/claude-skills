"""The detect, verify, rank chain over the corpus with canned scouts and verdicts (spec 6, 11).

Scout and verdict files are the first live run's output (plus the hand edits the
phase 2 plan names); every deterministic stage is compared byte for byte to its
golden. Regenerate the deterministic goldens with UPDATE_GOLDENS=1 after an
intentional change; never regenerate the scouts or verdicts by hand.

Two clocks are pinned so the goldens stay stable: ``run_patterns`` runs with
``blame=False`` (SATD ages are wall-clock) and ``run_rules`` runs at ``RULES_NOW``.
The rule quotes for ``release.stale-env-branch`` and ``ownership.former-contributor``
spell an age in days, and the fingerprint hashes that quote, so an unpinned clock
would give the same debt a new fingerprint every day.

One finding per fixture (``PIN_TITLE``) is hand-added with a quote that is not in
the file, so the diversion path is exercised on every run. The live scouts of
their own accord produced a few more unverifiable quotes; those are named in
``LIVE_QUOTE_MISSES`` rather than edited out, so the test still states the exact
set of quotes that must fail.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from apply_verdicts import apply
from config import DEFAULTS
from evaluate import evaluate
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from rank import rank
from rules import run_rules
from verify_prompts import build_verify_plan

GOLDEN = Path(__file__).parent / "golden"
CORPUS = Path(__file__).parent / "fixtures" / "corpus"
FIXTURES = ("service-py", "web-ts", "mixed-decoys")
UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"
# The first live run's date: keeping it fixed keeps the day counts, and so the
# fingerprints, that rules.py derives from "now" identical on every later run.
RULES_NOW = datetime(2026, 9, 5, tzinfo=UTC)
# The hand-added finding whose quote is not in the file; the merge must divert it.
PIN_TITLE = "invented quote (golden pin)"
# Live scout findings that cite a quote ``find_quote`` cannot rejoin: each spans
# more lines than the six-line fallback window and its cited range is off by a
# line or two, so the quote is lost. Kept exactly as the run emitted them, because
# this is the evidence gate working on real output rather than fixture damage.
# ``diverted`` findings lose every quote and land in ``open_questions``; ``partial``
# findings keep another verified quote and stay as candidates.
LIVE_QUOTE_MISSES: dict[str, dict[str, frozenset[str]]] = {
    "service-py": {
        "diverted": frozenset({"README has no CONTRIBUTING section or file for the repo"}),
        "partial": frozenset({
            "Legacy export bypasses the ledger, writing refund data to a second store",
            "README Run instructions reference a CLI that refund.py does not implement",
        }),
    },
    "web-ts": {
        "diverted": frozenset({
            "Duplicated fetch-wrapper logic between client.ts and client-admin.ts",
        }),
        "partial": frozenset(),
    },
    "mixed-decoys": {
        "diverted": frozenset(),
        "partial": frozenset({
            "Deprecated but still-called httpc.Fetch path has no test",
            "Deprecated httpc.Fetch still called instead of FetchWithTimeout",
            "Fetch has no timeout and can hang forever on health check",
            "Payments kill switch has no test verifying it changes behaviour",
        }),
    },
}

Chain = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]


def _canon(doc: dict[str, Any], root: str) -> bytes:
    """The document as the golden holds it, with the temporary repository root masked.

    Both spellings are masked: the plain path and the JSON-escaped one a Windows
    root turns into (``C:\\repo`` is written ``C:\\\\repo`` inside a JSON string).
    """
    text = json.dumps(doc, indent=2) + "\n"
    text = text.replace(root.replace("\\", "\\\\"), "<root>").replace(root, "<root>")
    return text.encode("utf-8")


def _check(name: str, doc: dict[str, Any], golden: Path, root: str) -> None:
    got = _canon(doc, root)
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(got)
    assert golden.is_file(), f"missing golden {golden}"
    assert got == golden.read_bytes(), f"{name} differs from {golden}"


def _chain(name: str, repo: Path, tmp_path: Path) -> Chain:
    workdir = tmp_path / "wd"
    planted = json.loads((CORPUS / name / "planted.json").read_bytes())
    inventory, coupling = build_all(
        repo, churn_months=int(planted["churn_months"]), config=DEFAULTS
    )
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS, now=RULES_NOW)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": 2, "findings": findings, "leads": leads},
    )
    plan, prompts = build_plan(workdir, DEFAULTS, families="deep", top=5)
    write_plan(workdir, plan, prompts)
    golden = GOLDEN / name
    for entry in plan["entries"]:
        src = golden / entry["output"]
        assert src.is_file(), f"golden scout missing for {entry['family']} on {name}"
        dest = workdir / entry["output"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dest)
    for extra in sorted((golden / "scouts").glob("*.json")):
        assert extra.name in {Path(e["output"]).name for e in plan["entries"]}, (
            f"golden scout {extra.name} is not in the plan for {name}"
        )
    root = str(repo.resolve())
    candidates = merge(workdir, repo, DEFAULTS)
    write_json(workdir / "candidates.json", candidates)
    _check("candidates", candidates, golden / "candidates.json", root)
    vplan, _ = build_verify_plan(workdir, repo, DEFAULTS, 5)
    _check("verify-plan", vplan, golden / "verify-plan.json", root)
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for batch in vplan["batches"]:
        src = golden / batch["output"]
        assert src.is_file(), f"golden verdict missing: {src}"
        verdicts[batch["output"]] = json.loads(src.read_bytes())
    verified = apply(candidates["candidates"], vplan, verdicts)
    _check("verified", verified, golden / "verified.json", root)
    ranked = rank(verified, inventory, DEFAULTS, preset="balanced", top=5)
    _check("ranked", ranked, golden / "ranked.json", root)
    return candidates, verified, ranked


@pytest.mark.parametrize("name", FIXTURES)
def test_chain_matches_goldens_and_meets_the_corpus_bar(
    name: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    candidates, verified, ranked = _chain(name, repo, tmp_path)
    planted = json.loads((CORPUS / name / "planted.json").read_bytes())
    report = evaluate(verified["findings"], planted, set(ranked["top_n"]), top=5)
    assert report["decoys_in_tier_a"] == 0, report["decoys"]
    assert report["decoys_in_top_n"] == 0, report["decoys"]
    assert report["counts"]["on_planted"] > 0
    diverted = sorted(
        q["question"] for q in candidates["open_questions"] if q["reason"] == "quote not found"
    )
    assert diverted == sorted({PIN_TITLE, *LIVE_QUOTE_MISSES[name]["diverted"]}), diverted
    assert any(f["verdict"] == "reject" and f["trap_matched"] for f in verified["findings"])
    top_n = set(ranked["top_n"])
    assert all(
        f["tier"] in ("A", "B") for f in verified["findings"] if f["fingerprint"] in top_n
    )


@pytest.mark.parametrize("name", FIXTURES)
def test_every_golden_quote_except_the_pin_verifies(
    name: str, request: pytest.FixtureRequest
) -> None:
    """Only the pin and the named live misses fail ``find_quote`` against the fixture."""
    from evidence import find_quote

    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    diverted: set[str] = set()
    partial: set[str] = set()
    for scout in sorted((GOLDEN / name / "scouts").glob("*.json")):
        for finding in json.loads(scout.read_bytes())["findings"]:
            found = []
            for ev in finding["evidence"]:
                path = repo / ev["file"]
                raw = path.read_bytes() if path.is_file() else b""
                lines = raw.decode("utf-8", "replace").splitlines()
                hit = find_quote(lines, ev["quote"], ev.get("line_start"), ev.get("line_end"))
                found.append(hit is not None)
            if not any(found):
                diverted.add(finding["title"])
            elif not all(found):
                partial.add(finding["title"])
    expected = LIVE_QUOTE_MISSES[name]
    assert diverted == {PIN_TITLE, *expected["diverted"]}, sorted(diverted)
    assert partial == set(expected["partial"]), sorted(partial)
