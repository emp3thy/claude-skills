from __future__ import annotations

import json

import pytest
from build_synthesis_prompt import (
    HOTSPOT_BOOST,
    SynthesisError,
    build_prompt,
    priority_score,
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


def test_build_prompt_includes_all_findings():
    prompt = build_prompt(_raw_findings_sample())
    for i in range(20):
        assert f"Finding {i}" in prompt


def test_build_prompt_specifies_schema():
    prompt = build_prompt(_raw_findings_sample())
    assert "impact" in prompt and "tractability" in prompt
    assert '"top5"' in prompt
    assert "slug" in prompt and "severity" in prompt


def test_validate_synthesis_output_ok():
    out = json.dumps(
        {
            "top5": [
                {
                    "slug": f"finding-{i}",
                    "title": f"T{i}",
                    "severity": 5,
                    "category": "god-modules",
                    "reasoning": "r",
                    "evidence": [],
                    "suggested_fix": "f",
                }
                for i in range(5)
            ]
        }
    )
    result = validate_synthesis_output(out)
    assert len(result["top5"]) == 5


def test_validate_synthesis_output_wrong_count_raises():
    import pytest

    out = json.dumps(
        {
            "top5": [
                {
                    "slug": "a",
                    "title": "t",
                    "severity": 1,
                    "category": "god-modules",
                    "reasoning": "r",
                    "evidence": [],
                    "suggested_fix": "f",
                }
            ]
        }
    )
    with pytest.raises(SynthesisError, match="expected 5 findings"):
        validate_synthesis_output(out)


def test_validate_synthesis_output_malformed_raises():
    import pytest

    with pytest.raises(SynthesisError, match="not valid JSON"):
        validate_synthesis_output("not json at all")


def test_validate_synthesis_output_bad_slug_raises():
    out = json.dumps(
        {
            "top5": [
                {
                    "slug": "Bad Slug With Spaces",
                    "title": "t",
                    "severity": 1,
                    "category": "god-modules",
                    "reasoning": "r",
                    "evidence": [],
                    "suggested_fix": "f",
                }
            ]
            * 5
        }
    )
    with pytest.raises(SynthesisError, match="invalid slug"):
        validate_synthesis_output(out)


def _finding(severity=3, effort=None, confidence=None, file="a.py") -> dict:
    f = {
        "title": "t",
        "severity": severity,
        "category": "god-modules",
        "evidence": [{"file": file, "line": 1, "note": "n"}],
        "suggested_fix": "f",
    }
    if effort is not None:
        f["effort"] = effort
    if confidence is not None:
        f["confidence"] = confidence
    return f


def test_priority_score_prefers_small_effort():
    small = priority_score(_finding(severity=4, effort="S"), set())
    large = priority_score(_finding(severity=4, effort="L"), set())
    assert small > large


def test_priority_score_discounts_low_confidence():
    high = priority_score(_finding(severity=4, confidence="high"), set())
    low = priority_score(_finding(severity=4, confidence="low"), set())
    assert high > low


def test_priority_score_boosts_hotspot_evidence():
    base = priority_score(_finding(file="cold.py"), {"hot.py"})
    hot = priority_score(_finding(file="hot.py"), {"hot.py"})
    assert hot == pytest.approx(base * HOTSPOT_BOOST)


def test_build_prompt_renders_hotspot_block_from_inventory():
    inventory = {
        "hotspots": [
            {"path": "hot.py", "churn": 9, "complexity": 120, "loc": 400, "score": 88.5}
        ]
    }
    prompt = build_prompt(_raw_findings_sample(), inventory=inventory)
    assert "hot.py" in prompt
    assert "hotspot" in prompt.lower()


def test_build_prompt_respects_top_n():
    prompt = build_prompt(_raw_findings_sample(), top_n=3)
    assert "exactly 3 findings" in prompt


def test_validate_synthesis_output_custom_expected_count():
    items = [
        {
            "slug": f"finding-{i}",
            "title": "t",
            "severity": 3,
            "category": "god-modules",
            "reasoning": "r",
            "evidence": [],
            "suggested_fix": "f",
        }
        for i in range(3)
    ]
    result = validate_synthesis_output(json.dumps({"top5": items}), expected_count=3)
    assert len(result["top5"]) == 3


def test_validate_synthesis_output_rejects_bad_effort():
    items = [
        {
            "slug": f"finding-{i}",
            "title": "t",
            "severity": 3,
            "category": "god-modules",
            "effort": "XL",
            "reasoning": "r",
            "evidence": [],
            "suggested_fix": "f",
        }
        for i in range(5)
    ]
    with pytest.raises(SynthesisError, match="unknown effort"):
        validate_synthesis_output(json.dumps({"top5": items}))


def test_validate_synthesis_output_accepts_classification_fields():
    items = [
        {
            "slug": f"finding-{i}",
            "title": "t",
            "severity": 3,
            "category": "architecture",
            "debt_type": "architecture",
            "effort": "L",
            "confidence": "medium",
            "reasoning": "r",
            "evidence": [],
            "suggested_fix": "f",
        }
        for i in range(5)
    ]
    validate_synthesis_output(json.dumps({"top5": items}))  # no raise
