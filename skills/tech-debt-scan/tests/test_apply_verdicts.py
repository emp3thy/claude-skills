"""apply_verdicts.py: verdict join, tier table, family caps (spec 4.8, 2.3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from apply_verdicts import _main, apply, earned_tier, family_cap
from evidence import fingerprint
from inventory import write_json


def _cand(family: str, sev: int = 3, *, confirmed: list[str] | None = None, tier: str | None = None,
          type_id: str | None = None, churn: int = 1, fan_in: int | None = 1) -> dict[str, Any]:
    fp, qh = fingerprint(family, "src/a.py", f"q {family} {sev} {confirmed}")
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code",
        "type_id": type_id,
        "title": "t", "severity": sev, "effort": "M", "source": "rule" if tier == "A" else "scout",
        "rule_id": None, "note": "",
        "evidence": [{"file": "src/a.py", "line_start": 1, "line_end": 1, "quote": "q",
                     "quote_verified": True}],
        "confirmed_by": confirmed if confirmed is not None else [f"scout:{family}"],
        "signals_cited": [],
        "signals": {"hotspot_score": 0.0, "churn": churn, "coupling_degree": 0,
                    "fan_in_approx": fan_in,
                    "path_class": "source", "in_hotspot_band": False},
        "tier": tier,
    }


def _verdict(cand: dict[str, Any], verdict: str, **extra: Any) -> dict[str, Any]:
    v: dict[str, Any] = {"fingerprint": cand["fingerprint"], "verdict": verdict, "proof": "p",
                         "severity": cand["severity"], "effort": cand["effort"],
                         "trap_matched": None, "checked": ["x"], "opened": []}
    v.update(extra)
    return v


def _plan(*cands: dict[str, Any]) -> dict[str, Any]:
    fps = [c["fingerprint"] for c in cands]
    return {"schema_version": 2, "top": 5, "batch_size": 6, "selected": fps, "unverified": [],
            "batches": [{"prompt": "prompts/verify-01.md", "output": "verdicts/verify-01.json",
                         "fingerprints": fps}]}


@pytest.mark.parametrize(
    ("verdict", "confirmed", "tier"),
    [
        ("confirm", ["scout:error-masking", "pattern:swallowed-catch"], "A"),
        ("confirm", ["scout:error-masking", "scout:dead-code"], "A"),
        ("confirm", ["scout:error-masking", "hotspot"], "A"),
        ("confirm", ["scout:error-masking"], "B"),
        ("downgrade", ["scout:error-masking", "pattern:x"], "C"),
        ("refer", ["scout:error-masking", "pattern:x"], "C"),
        ("reject", ["scout:error-masking", "pattern:x"], None),
    ],
)
def test_tier_table(verdict: str, confirmed: list[str], tier: str | None) -> None:
    cand = _cand("error-masking", confirmed=confirmed)
    assert earned_tier(cand, _verdict(cand, verdict)) == tier


def test_family_caps() -> None:
    assert family_cap(_cand("duplication", confirmed=["scout:duplication", "pattern:x"])) == "B"
    assert family_cap(_cand("duplication", confirmed=["scout:duplication", "coupling"])) is None
    assert family_cap(_cand("dead-code", churn=1, fan_in=1)) == "C"
    assert family_cap(_cand("dead-code", churn=0, fan_in=0)) == "B"
    assert family_cap(_cand("dead-code", confirmed=["scout:dead-code", "tool:knip"])) is None
    assert family_cap(_cand("god-classes", type_id="TD-20")) == "B"
    assert family_cap(_cand("god-classes", type_id="TD-11")) is None
    assert family_cap(_cand("architecture", type_id="TD-10")) == "C"
    assert family_cap(_cand("architecture", type_id="TD-07")) == "B"
    assert family_cap(_cand("architecture", type_id="TD-07",
                            confirmed=["scout:architecture", "coupling"])) is None
    assert family_cap(_cand("test-gaps")) == "B"
    assert family_cap(_cand("test-gaps",
                            confirmed=["scout:test-gaps", "signal:no-mapped-tests"])) is None
    assert family_cap(_cand("security")) == "B"
    assert family_cap(_cand("doc-drift")) == "B"
    assert family_cap(_cand("error-masking")) is None
    assert family_cap(_cand("complex-units")) is None


def test_apply_joins_overrides_and_counts() -> None:
    a = _cand("error-masking", 4, confirmed=["scout:error-masking", "pattern:x"])
    b = _cand("duplication", 3, confirmed=["scout:duplication", "pattern:y"])
    c = _cand("dead-code", 2)
    d = _cand("pipeline-infra", 3, tier="A")
    e = _cand("test-quality", 5, confirmed=["scout:test-quality", "satd"])
    plan = _plan(a, b, c, e)
    verdicts = {"verdicts/verify-01.json": [
        _verdict(a, "confirm", severity=2, effort="S"),
        _verdict(b, "confirm"),
        _verdict(e, "confirm"),
        {"fingerprint": "unknown000000000", "verdict": "confirm", "proof": "", "severity": 1,
         "effort": "S", "trap_matched": None, "checked": [], "opened": []},
    ]}
    doc = apply([a, b, c, d, e], plan, verdicts)
    assert list(doc) == ["schema_version", "findings", "stats"]
    by_fp = {f["fingerprint"]: f for f in doc["findings"]}
    assert by_fp[a["fingerprint"]]["tier"] == "A"
    assert by_fp[a["fingerprint"]]["severity"] == 2 and by_fp[a["fingerprint"]]["effort"] == "S"
    assert by_fp[b["fingerprint"]]["tier"] == "B", "duplication capped without tool or coupling"
    assert (by_fp[c["fingerprint"]]["tier"] == "C"
            and by_fp[c["fingerprint"]]["verdict"] == "unverified")
    assert by_fp[c["fingerprint"]]["verified"] is False
    assert by_fp[d["fingerprint"]]["tier"] == "A" and by_fp[d["fingerprint"]]["verified"] is True
    assert by_fp[e["fingerprint"]]["severity"] == 3, "test-quality severity capped at 3"
    assert by_fp[e["fingerprint"]]["tier"] == "B", "test-quality capped at B without a tool"
    finding = by_fp[a["fingerprint"]]
    assert list(finding)[-6:] == [
        "verdict", "proof", "checked", "opened", "trap_matched", "verified"]
    assert doc["stats"] == {"selected": 4, "verdicts": 3, "unknown_fingerprint": 1,
                            "missing_verdict": 1,
                            "tier_a": 2, "tier_b": 2, "tier_c": 1, "rejected": 0}


def test_reject_and_trap_are_kept(tmp_path: Path) -> None:
    a = _cand("dead-code", confirmed=["scout:dead-code", "pattern:x"])
    plan = _plan(a)
    doc = apply([a], plan, {"verdicts/verify-01.json": [
        _verdict(a, "reject", trap_matched="entry points live here")]})
    f = doc["findings"][0]
    assert (f["tier"] is None and f["verdict"] == "reject"
            and f["trap_matched"] == "entry points live here")
    assert doc["stats"]["rejected"] == 1


def test_verifier_text_is_redacted_before_it_reaches_a_finding() -> None:
    """The verifier reads the repository, so its prose is a credential path too (spec 4.3)."""
    secret = "abcdefghijkl0123"
    a = _cand("security", confirmed=["scout:security", "pattern:x"])
    doc = apply([a], _plan(a), {"verdicts/verify-01.json": [_verdict(
        a, "confirm",
        proof=f'src/a.py:11 hardcodes token = "{secret}" at module level',
        checked=[f'token = "{secret}" is not in a test fixture'],
        opened=[f'src/a.py -> token = "{secret}"'],
        trap_matched=f'trap: token = "{secret}" is the documented sample',
    )]})
    finding = doc["findings"][0]
    assert "abcd***" in finding["proof"]
    assert secret not in json.dumps(finding), "no verifier field may carry the raw value"
    assert all("abcd***" in text for text in (*finding["checked"], *finding["opened"]))
    assert "abcd***" in finding["trap_matched"]


def test_cli_reads_verdict_files(tmp_path: Path) -> None:
    a = _cand("error-masking", confirmed=["scout:error-masking", "satd"])
    workdir = tmp_path / "wd"
    write_json(workdir / "candidates.json", {"schema_version": 2, "candidates": [a],
                                             "open_questions": [], "looks_bad_but_fine": [],
                                             "stats": {}})
    write_json(workdir / "verify-plan.json", _plan(a))
    (workdir / "verdicts").mkdir()
    (workdir / "verdicts" / "verify-01.json").write_text(
        json.dumps([_verdict(a, "confirm")]), encoding="utf-8")
    assert _main(["--workdir", str(workdir)]) == 0
    doc = json.loads((workdir / "verified.json").read_bytes())
    assert doc["findings"][0]["tier"] == "A"
    assert (workdir / "verified.json").read_bytes().count(b"\r") == 0
    assert _main(["--workdir", str(tmp_path / "none")]) == 2


@pytest.mark.parametrize(
    ("bad_file", "bad_content"),
    [
        ("candidates.json", "[]"),
        ("verify-plan.json", "[]"),
        ("candidates.json", '{"candidates": null}'),
    ],
    ids=["candidates-is-list", "plan-is-list", "candidates-field-null"],
)
def test_cli_exits_2_on_wrongly_shaped_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    bad_file: str,
    bad_content: str,
) -> None:
    a = _cand("error-masking", confirmed=["scout:error-masking", "satd"])
    workdir = tmp_path / "wd"
    write_json(workdir / "candidates.json", {"schema_version": 2, "candidates": [a],
                                             "open_questions": [], "looks_bad_but_fine": [],
                                             "stats": {}})
    write_json(workdir / "verify-plan.json", _plan(a))
    (workdir / bad_file).write_text(bad_content, encoding="utf-8")
    assert _main(["--workdir", str(workdir)]) == 2
    assert capsys.readouterr().err.startswith("error:")
