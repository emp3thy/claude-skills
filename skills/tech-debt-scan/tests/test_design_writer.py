"""design_writer.py v2: render design.md and findings.json from the ranked chain (spec 4.11)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from design_parser import parse_design
from design_writer import DesignWriteError, load_inputs, render_design, write_design
from inventory import write_json

SCAN_DATE = "2026-09-06"
GOLDEN = Path(__file__).parent / "golden"

TOP_FP = "0123456789abcdef"
CUT_FP = "fedcba9876543210"
TIER_C_FP = "aaaabbbbccccdddd"


def _inventory() -> dict[str, Any]:
    return {
        "schema_version": 2, "root": "/abs/path/to/repo", "total_files": 100,
        "total_loc": 12000, "languages": ["python"], "git_available": True,
        "hotspots": [
            {"path": "src/pay/refund.py", "churn": 4, "complexity": 20, "loc": 100, "score": 80.0},
            {"path": "src/pay/gateway.py", "churn": 2, "complexity": 9, "loc": 40, "score": 45.0},
        ],
        "hotspot_band": ["src/pay/refund.py"],
        "files": [
            {"path": "src/pay/refund.py", "path_class": "source", "hotspot_score": 80.0,
             "churn": 4, "coupling_degree": 1, "fan_in_approx": 2, "fan_in_mode": "import-lines"},
            {"path": "src/pay/gateway.py", "path_class": "source", "hotspot_score": 45.0,
             "churn": 2, "coupling_degree": 1, "fan_in_approx": 0, "fan_in_mode": "import-lines"},
        ],
    }


def _coupling() -> dict[str, Any]:
    return {"schema_version": 2, "pairs": [
        {"a": "src/pay/refund.py", "b": "src/pay/gateway.py", "shared_commits": 4,
         "ratio": 0.8, "cross_directory": False}
    ], "degree": {}, "cycles": [], "directories": [], "unstable_edges": []}


def _plan() -> dict[str, Any]:
    return {
        "schema_version": 2, "set": "default", "top": 5, "chunked": False, "thresholds": {},
        "entries": [], "families_run": ["error-masking", "security"],
        "families_skipped": [{"family": "duplication", "reason": "no leads"}],
    }


def _finding(
    fingerprint: str, family: str, title: str, file: str, start: int, end: int, quote: str,
    *, tier: str | None, verdict: str, severity: int = 4, effort: str = "M",
    debt_type: str = "defect", type_id: str | None = "TD-13", proof: str = "",
    confirmed: list[str] | None = None, signals: dict[str, Any] | None = None,
    trap: str | None = None, verified: bool = True,
) -> dict[str, Any]:
    return {
        "fingerprint": fingerprint, "quote_hash": "0" * 40, "family": family,
        "debt_type": debt_type, "type_id": type_id, "title": title, "severity": severity,
        "effort": effort, "source": "scout", "rule_id": None, "note": "n",
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote,
                      "quote_verified": True}],
        "confirmed_by": confirmed if confirmed is not None else [f"scout:{family}"],
        "signals_cited": [],
        "signals": signals if signals is not None else {
            "hotspot_score": 80.0, "churn": 4, "coupling_degree": 1, "fan_in_approx": 2,
            "path_class": "source", "in_hotspot_band": True},
        "tier": tier, "verdict": verdict, "proof": proof, "checked": [], "opened": [],
        "trap_matched": trap, "verified": verified,
    }


def _verified() -> dict[str, Any]:
    return {"schema_version": 2, "findings": [
        _finding(TOP_FP, "error-masking", "Refund failure swallowed by a bare except",
                 "src/pay/refund.py", 120, 123, "    except Exception:\n        pass",
                 tier="A", verdict="confirm",
                 proof="The catch at lines 120 to 123 returns on any failure and logs nothing.",
                 confirmed=["hotspot", "pattern:swallowed-catch", "scout:error-masking"]),
        _finding(CUT_FP, "security", "Hard-coded credential in the gateway client",
                 "src/pay/gateway.py", 11, 11, 'token = "sk_l***"',
                 tier="B", verdict="confirm", severity=5, effort="S",
                 debt_type="security", type_id="TD-03",
                 proof="A credential-shaped literal sits in source, not in configuration.",
                 confirmed=["scout:security"],
                 signals={"hotspot_score": 45.0, "churn": 2, "coupling_degree": 1,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
        _finding(TIER_C_FP, "dead-code", "Unused helper in the ledger module",
                 "src/pay/ledger.py", 40, 41, "def unused_helper():\n    return None",
                 tier="C", verdict="unverified", severity=2, effort="S",
                 debt_type="code", type_id="TD-09", verified=False,
                 signals={"hotspot_score": 0.0, "churn": 0, "coupling_degree": 0,
                          "fan_in_approx": 0, "path_class": "source", "in_hotspot_band": False}),
    ], "stats": {"selected": 2, "verdicts": 2, "unknown_fingerprint": 0, "missing_verdict": 1,
                 "tier_a": 1, "tier_b": 1, "tier_c": 1, "rejected": 0}}


def _ranked() -> dict[str, Any]:
    terms = {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
             "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    return {
        "schema_version": 2, "formula_version": 1, "preset": "balanced", "top": 5,
        "weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
        "tractability": {"S": 1.0, "M": 0.75, "L": 0.5},
        "top_n": [TOP_FP],
        "findings": [
            {"fingerprint": TOP_FP, "rank": 1, "priority": 6.3, "terms": terms, "tier": "A",
             "in_top_n": True, "spread_capped": False},
            {"fingerprint": CUT_FP, "rank": 2, "priority": 3.5, "terms": dict(terms, priority=3.5),
             "tier": "B", "in_top_n": False, "spread_capped": False},
            {"fingerprint": TIER_C_FP, "rank": 3, "priority": 0.7,
             "terms": dict(terms, priority=0.7), "tier": "C", "in_top_n": False,
             "spread_capped": False},
        ],
    }


def _candidates() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "candidates": [
            {"fingerprint": TOP_FP}, {"fingerprint": CUT_FP}, {"fingerprint": TIER_C_FP},
        ],
        "open_questions": [
            {"file": "src/pay/refund.py", "line_start": 51,
             "question": "Is audit_trail() wired into a production caller?", "reason": None},
            {"file": "src/pay/ledger.py", "line_start": 12,
             "question": "Ledger rounding drifts on partial refunds", "reason": "quote not found"},
        ],
        "looks_bad_but_fine": [
            {"file": "src/pay/gateway.py", "line_start": 19,
             "why": "One multi-line call, not nested branching."},
        ],
        "stats": {"error-masking": {"raw": 2, "dropped": 0, "quote_failed": 1, "clustered": 0,
                                    "suppressed": 0, "disabled": 0}},
    }


def _write_workdir(workdir: Path, **overrides: Any) -> Path:
    docs = {
        "inventory.json": _inventory(), "coupling.json": _coupling(), "scan-plan.json": _plan(),
        "verified.json": _verified(), "ranked.json": _ranked(), "candidates.json": _candidates(),
    }
    docs.update(overrides)
    for name, doc in docs.items():
        if doc is not None:
            write_json(workdir / name, doc)
    return workdir


def _inputs(tmp_path: Path, **overrides: Any) -> Any:
    return load_inputs(_write_workdir(tmp_path / "wd", **overrides))


# --- frontmatter, header, top N -------------------------------------------------


def test_render_matches_the_worked_example(tmp_path: Path) -> None:
    """The exact bytes of the plan's Step 0 example (Tasks 4 and 5 fill the empty sections)."""
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    expected = (GOLDEN / "design-worked-example.md").read_bytes().decode("utf-8")
    assert text == expected


def test_document_parses_and_carries_one_top_finding(tmp_path: Path) -> None:
    out = tmp_path / "design.md"
    write_design(_inputs(tmp_path), SCAN_DATE, out)
    raw = out.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    parsed = parse_design(out)
    assert parsed["metadata"]["schema_version"] == 2
    assert parsed["metadata"]["counts"]["tier_a"] == 1
    assert [f["slug"] for f in parsed["findings"]] == [
        "refund-failure-swallowed-by-a-bare-except"
    ]
    finding = parsed["findings"][0]
    assert finding["category"] == finding["family"] == "error-masking"
    assert finding["tier"] == "A" and finding["diff"] == "NEW" and finding["priority"] == "6.3"
    assert "Considered and rejected" not in finding["body_md"]


def test_git_absent_omits_the_hotspot_and_coupling_summary(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory["git_available"] = False
    inventory["hotspots"] = []
    inventory["hotspot_band"] = []
    text = render_design(_inputs(tmp_path, **{"inventory.json": inventory,
                                              "coupling.json": {"schema_version": 2, "pairs": []}}),
                         SCAN_DATE)
    assert "Top hotspots:" not in text and "Top coupled pairs:" not in text
    assert "git_available: false" in text
    assert "No git history: churn is 0 and the interest signal is absent." in text


def test_counts_come_from_the_documents(tmp_path: Path) -> None:
    text = render_design(_inputs(tmp_path), SCAN_DATE)
    for line in ("  candidates: 3", "  quote_failed: 1", "  verified: 2", "  tier_a: 1",
                 "  tier_b: 1", "  tier_c: 1", "  unverified: 1", "  rejected: 0",
                 "  suppressed: 0"):
        assert line in text, line
    assert "  new:" not in text and "  resolved:" not in text, "no diff.json in phase 3"


def test_every_written_string_is_redacted(tmp_path: Path) -> None:
    secret = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"
    verified = _verified()
    verified["findings"][0]["proof"] = f'the literal token = "{secret}" sits here'
    verified["findings"][0]["evidence"][0]["quote"] = f'token = "{secret}"'
    text = render_design(_inputs(tmp_path, **{"verified.json": verified}), SCAN_DATE)
    assert secret not in text and "sk_l***" in text


def test_missing_input_document_is_an_error(tmp_path: Path) -> None:
    workdir = _write_workdir(tmp_path / "wd")
    (workdir / "ranked.json").unlink()
    with pytest.raises((DesignWriteError, FileNotFoundError)):
        load_inputs(workdir)
