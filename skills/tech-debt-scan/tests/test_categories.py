"""categories.py: the v2 family blocks and the scout output contract (spec 4.6)."""
from __future__ import annotations

import json

import categories
from categories import (
    FAMILIES,
    FAMILY_BLOCKS,
    SCOUT_OUTPUT_SCHEMA,
    SEVERITY_RUBRIC,
    render_scout_prompt,
)
from config import FAMILY_SETS
from validation import VALID_DEBT_TYPES, validate_type_id

EXPECTED_FAMILIES = (
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "test-quality", "pipeline-infra",
)
FORBIDDEN = ("def ", ".py file", "python module", "__init__", "pip install")


def _render(family: str) -> str:
    return render_scout_prompt(
        family,
        repo_summary="root: r, 10 files, 100 LOC, languages: python, typescript; git: yes",
        leads_block="Hotspot-band files: src/a.py (0.91)\n",
        scout_cap=12,
        disabled_note="Families disabled on tests: duplication, complex-units, god-classes",
    )


# --- v1 deletion (spec 3.2) -----------------------------------------------------


def test_the_v1_scout_prompt_symbols_are_gone() -> None:
    """Spec 3.2: phase 3 deletes the v1 scout-prompt symbols outright.

    Phase 2 kept ``CATEGORY_PROMPTS``, ``CATEGORIES``, ``CORE_CATEGORIES`` and
    ``get_prompt`` beside the family blocks so SKILL.md v1 and
    ``build_synthesis_prompt.py`` kept working; both of those consumers are
    deleted by this branch, so the symbols have no reader left. ``_OUTPUT_SCHEMA``
    goes with them: it was appended to each of the eight v1 prompts and nothing
    else read it, and it still described a ``confidence`` field that this phase
    removed from ``validation.py`` -- two contradicting scout contracts in one
    module if it survived. The v2 contract is ``SCOUT_OUTPUT_SCHEMA``, which is
    a different symbol and stays.

    A v1 ``design.md`` is unaffected: its ``category`` value (``god-modules``
    and the rest) is a string in a document that ``design_parser`` reads as
    ``family``; no v1 path ever reads a scout prompt.
    """
    for name in ("CATEGORY_PROMPTS", "CATEGORIES", "CORE_CATEGORIES", "get_prompt",
                 "_OUTPUT_SCHEMA"):
        assert not hasattr(categories, name), f"{name} should have been deleted in phase 3"
    assert "suggested_fix" not in categories.SCOUT_OUTPUT_CONTRACT
    assert "confidence" not in categories.SCOUT_OUTPUT_CONTRACT


# --- v2 -------------------------------------------------------------------------


def test_fourteen_families_in_dispatch_order() -> None:
    assert FAMILIES == EXPECTED_FAMILIES
    assert set(FAMILY_BLOCKS) == set(FAMILIES)
    assert FAMILY_SETS["deep"] == FAMILIES


def test_every_block_is_complete_and_valid() -> None:
    for family, block in FAMILY_BLOCKS.items():
        assert len(block.definition) > 60, family
        assert 4 <= len(block.questions) <= 6, family
        assert block.traps, family
        assert block.type_ids, family
        for type_id in block.type_ids:
            validate_type_id(type_id)
        assert block.debt_types and set(block.debt_types) <= VALID_DEBT_TYPES, family
        assert block.verifier_questions, family


def test_rendered_prompt_has_prefix_block_leads_and_contract() -> None:
    for family in FAMILIES:
        text = _render(family)
        assert "read-only" in text.lower()
        assert "do not invent" in text.lower()
        assert '"line_start"' in text and '"line_end"' in text and '"quote"' in text
        assert '"type_id"' in text and '"signals_cited"' in text
        assert '"open_questions"' in text and '"looks_bad_but_fine"' in text
        assert '"not_assessed"' in text
        assert "suggested_fix" not in text and "confidence" not in text
        assert "an empty list is a correct answer" in text
        assert "12" in text
        assert "hotspot" in text.lower() and "Severity rubric" in text
        assert "Families disabled on tests" in text
        assert FAMILY_BLOCKS[family].definition in text
        assert "Hotspot-band files: src/a.py" in text


def test_rubric_has_no_hotspot_amplifier() -> None:
    assert "+1" not in SEVERITY_RUBRIC and "3 + hotspot" not in SEVERITY_RUBRIC
    assert SEVERITY_RUBRIC.startswith("Severity rubric")


def test_v2_prompts_avoid_language_specific_terms() -> None:
    for family in FAMILIES:
        low = _render(family).lower()
        for bad in FORBIDDEN:
            assert bad not in low, f"{family}: {bad!r}"


def test_never_assert_rules_are_present() -> None:
    text = _render("security")
    for claim in ("coverage", "CVE", "end-of-life", "deprecat", "flak", "exploitab"):
        assert claim.lower() in text.lower(), claim


def test_output_schema_is_valid_json_schema_shape() -> None:
    schema = SCOUT_OUTPUT_SCHEMA
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"family", "module", "findings", "open_questions",
                                       "looks_bad_but_fine", "not_assessed"}
    finding = schema["properties"]["findings"]["items"]
    assert set(finding["required"]) == {"title", "family", "debt_type", "severity", "effort",
                                        "signals_cited", "evidence", "note"}
    json.dumps(schema)
