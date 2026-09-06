# skills/tech-debt-scan/tests/test_validation.py
from __future__ import annotations

import pytest
from validation import (
    VALID_DEBT_TYPES,
    VALID_EFFORTS,
    VALID_STATUSES,
    VALID_TIERS,
    ValidationError,
    validate_debt_type,
    validate_effort,
    validate_slug,
    validate_status,
    validate_tier,
    validate_type_id,
)


@pytest.mark.parametrize("good", ["a", "abc", "split-loop-py", "x1-y2-z3", "double--dash-ok"])
def test_validate_slug_accepts(good: str):
    validate_slug(good)  # no raise


@pytest.mark.parametrize(
    "bad",
    ["", "A", "1-good", "with space", "ends-", "x" * 65, "snake_case_no"],
)
def test_validate_slug_rejects(bad: str):
    with pytest.raises(ValidationError):
        validate_slug(bad)


@pytest.mark.parametrize("good", list(VALID_STATUSES))
def test_validate_status_accepts(good: str):
    validate_status(good)


def test_validate_status_rejects_empty_via_is_not_none():
    # per [[26d0a5a7-truthiness-vs-none]]: empty must reach validator, not be
    # short-circuited by falsy check upstream
    with pytest.raises(ValidationError, match="unknown status"):
        validate_status("")


@pytest.mark.parametrize("bad", ["pending ", "APPROVED", "yes", "no"])
def test_validate_status_rejects_bad(bad: str):
    with pytest.raises(ValidationError):
        validate_status(bad)


@pytest.mark.parametrize("good", sorted(VALID_DEBT_TYPES))
def test_validate_debt_type_accepts(good: str):
    validate_debt_type(good)


@pytest.mark.parametrize("bad", ["", "Code", "perf", "tests"])
def test_validate_debt_type_rejects(bad: str):
    with pytest.raises(ValidationError, match="unknown debt_type"):
        validate_debt_type(bad)


@pytest.mark.parametrize("good", sorted(VALID_EFFORTS))
def test_validate_effort_accepts(good: str):
    validate_effort(good)


@pytest.mark.parametrize("bad", ["", "s", "XL", "small"])
def test_validate_effort_rejects(bad: str):
    with pytest.raises(ValidationError, match="unknown effort"):
        validate_effort(bad)


def test_accepted_is_a_valid_status() -> None:
    assert "accepted" in VALID_STATUSES
    validate_status("accepted")


@pytest.mark.parametrize("good", ["security", "infrastructure", "knowledge-process", "defect"])
def test_new_debt_types_accepted(good: str) -> None:
    assert good in VALID_DEBT_TYPES
    validate_debt_type(good)


@pytest.mark.parametrize("reserved", ["data", "ml-ai", "performance"])
def test_reserved_debt_types_still_rejected(reserved: str) -> None:
    with pytest.raises(ValidationError, match="unknown debt_type"):
        validate_debt_type(reserved)


@pytest.mark.parametrize("good", ["TD-01", "TD-13", "TD-35"])
def test_validate_type_id_accepts(good: str) -> None:
    validate_type_id(good)


@pytest.mark.parametrize("bad", ["", "TD-00", "TD-36", "TD-1", "td-01", "TD-013", "TD-13 "])
def test_validate_type_id_rejects(bad: str) -> None:
    with pytest.raises(ValidationError, match="invalid type_id"):
        validate_type_id(bad)


@pytest.mark.parametrize("good", sorted(VALID_TIERS))
def test_validate_tier_accepts(good: str) -> None:
    validate_tier(good)


@pytest.mark.parametrize("bad", ["", "a", "D", "AA", "A "])
def test_validate_tier_rejects(bad: str) -> None:
    with pytest.raises(ValidationError, match="unknown tier"):
        validate_tier(bad)
