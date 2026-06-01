from __future__ import annotations

from categories import CATEGORIES, get_prompt

EXPECTED = {"god-modules", "duplication", "dead-code", "test-gaps", "doc-drift", "half-finished"}


def test_six_categories():
    assert set(CATEGORIES) == EXPECTED


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
        assert '"evidence"' in text
        assert '"suggested_fix"' in text
