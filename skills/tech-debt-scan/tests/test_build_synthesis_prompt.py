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
    import pytest

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
