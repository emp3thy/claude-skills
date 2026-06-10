from __future__ import annotations

from categories import CATEGORIES, CORE_CATEGORIES, get_prompt

EXPECTED = {
    "god-modules",
    "duplication",
    "dead-code",
    "test-gaps",
    "doc-drift",
    "half-finished",
    "dependency-debt",
    "architecture",
}


def test_eight_categories():
    assert set(CATEGORIES) == EXPECTED


def test_core_categories_are_a_subset():
    assert set(CORE_CATEGORIES) <= set(CATEGORIES)
    assert len(CORE_CATEGORIES) >= 3


def test_each_prompt_non_empty():
    for cat in EXPECTED:
        prompt = get_prompt(cat)
        assert len(prompt) > 200, f"{cat} prompt too short"


def test_unknown_category_raises():
    import pytest

    with pytest.raises(KeyError):
        get_prompt("not-a-category")


def test_prompts_avoid_python_specific_terms():
    """Prompts must read as language-agnostic."""
    forbidden = {"def ", "import ", ".py file", "Python module"}
    for cat in EXPECTED:
        text = get_prompt(cat).lower()
        for bad in forbidden:
            assert bad.lower() not in text, f"{cat}: {bad!r} leaks Python-specific phrasing"


def test_each_prompt_specifies_json_schema():
    """Each prompt must instruct the scout to emit the ScoutFinding JSON schema."""
    for cat in EXPECTED:
        text = get_prompt(cat)
        assert '"title"' in text
        assert '"severity"' in text
        assert '"category"' in text
        assert '"debt_type"' in text
        assert '"effort"' in text
        assert '"confidence"' in text
        assert '"evidence"' in text
        assert '"suggested_fix"' in text


def test_each_prompt_carries_hotspot_guidance_and_rubric():
    for cat in EXPECTED:
        text = get_prompt(cat)
        assert "hotspot" in text.lower(), f"{cat}: missing hotspot guidance"
        assert "Severity rubric" in text, f"{cat}: missing severity rubric"
