from __future__ import annotations

import json

from build_synthesis_prompt import (
    SynthesisError,
    build_prompt,
    validate_synthesis_output,
)


def _raw_findings_sample() -> list[dict]:
    return [
        {
            "title": f"Finding {i}",
            "severity": (i % 5) + 1,
            "category": "god-modules" if i % 2 == 0 else "duplication",
            "evidence": [{"file": "a.py", "line": 1, "note": "n"}],
            "suggested_fix": "split X",
        }
        for i in range(20)
    ]


def _valid_item(i: int) -> dict:
    return {
        "slug": f"finding-{i}",
        "title": f"T{i}",
        "severity": 5,
        "category": "god-modules",
        "reasoning": "r",
        "evidence": [],
        "suggested_fix": "f",
        "confidence": 4,
        "change_size": "M",
        "change_risk": "low",
        "disposition": "full-repayment",
        "why_now": "high-churn hotspot",
        "scope_boundary": "only this module",
        "acceptance_criteria": "tests pass, no behaviour change",
    }


def test_build_prompt_includes_all_findings():
    prompt = build_prompt(_raw_findings_sample())
    for i in range(20):
        assert f"Finding {i}" in prompt


def test_build_prompt_specifies_schema():
    prompt = build_prompt(_raw_findings_sample())
    assert "RICE" in prompt or "confidence" in prompt.lower()
    assert '"top5"' in prompt
    assert "slug" in prompt and "severity" in prompt


def test_validate_synthesis_output_ok():
    out = json.dumps({"top5": [_valid_item(i) for i in range(5)]})
    result = validate_synthesis_output(out)
    assert len(result["top5"]) == 5


def test_validate_synthesis_output_wrong_count_raises():
    import pytest

    item = _valid_item(0)
    out = json.dumps({"top5": [item]})
    with pytest.raises(SynthesisError, match="expected 5 findings"):
        validate_synthesis_output(out)


def test_validate_synthesis_output_malformed_raises():
    import pytest

    with pytest.raises(SynthesisError, match="not valid JSON"):
        validate_synthesis_output("not json at all")


def test_validate_synthesis_output_bad_slug_raises():
    import pytest

    item = _valid_item(0)
    item["slug"] = "Bad Slug With Spaces"
    out = json.dumps({"top5": [item] * 5})
    with pytest.raises(SynthesisError, match="invalid slug"):
        validate_synthesis_output(out)


def test_validate_rejects_bad_change_size():
    import pytest

    item = _valid_item(0)
    item["change_size"] = "HUGE"
    out = json.dumps({"top5": [item] * 5})
    with pytest.raises(SynthesisError, match="change_size"):
        validate_synthesis_output(out)


def test_validate_rejects_bad_confidence():
    import pytest

    item = _valid_item(0)
    item["confidence"] = 9
    out = json.dumps({"top5": [item] * 5})
    with pytest.raises(SynthesisError, match="confidence"):
        validate_synthesis_output(out)


def test_validate_rejects_bool_confidence():
    import pytest

    item = _valid_item(0)
    item["confidence"] = True
    out = json.dumps({"top5": [item] * 5})
    with pytest.raises(SynthesisError, match="confidence"):
        validate_synthesis_output(out)


def test_validate_rejects_empty_prose_field():
    import pytest

    item = _valid_item(0)
    item["why_now"] = ""
    out = json.dumps({"top5": [item] * 5})
    with pytest.raises(SynthesisError, match="why_now"):
        validate_synthesis_output(out)


def test_churn_sort_reorders_by_hotspot():
    # Two findings: low severity in a hot file, high severity in a cold file.
    findings = [
        {
            "title": "cold-high", "severity": 5, "category": "god-modules",
            "evidence": [{"file": "cold.py", "line": 1, "note": "n"}],
            "suggested_fix": "x",
        },
        {
            "title": "hot-low", "severity": 3, "category": "god-modules",
            "evidence": [{"file": "hot.py", "line": 1, "note": "n"}],
            "suggested_fix": "x",
        },
    ]
    churn = {"cold.py": 0, "hot.py": 50}
    prompt = build_prompt(findings, churn_by_file=churn)
    # hot-low: 3 * log1p(50) ~= 11.7 ; cold-high: 5 * log1p(0) = 0 -> hot-low first
    assert prompt.index("hot-low") < prompt.index("cold-high")


def test_no_churn_falls_back_to_severity():
    findings = [
        {"title": "a", "severity": 2, "category": "god-modules",
         "evidence": [], "suggested_fix": "x"},
        {"title": "b", "severity": 5, "category": "god-modules",
         "evidence": [], "suggested_fix": "x"},
    ]
    prompt = build_prompt(findings, churn_by_file=None)
    assert prompt.index('"b"') < prompt.index('"a"')  # severity 5 before 2
