# skills/tech-debt-scan/tests/test_validation.py
from __future__ import annotations

import pytest
from validation import (
    VALID_CONFIDENCES,
    VALID_DEBT_TYPES,
    VALID_EFFORTS,
    VALID_STATUSES,
    ValidationError,
    validate_confidence,
    validate_debt_type,
    validate_effort,
    validate_slug,
    validate_status,
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


@pytest.mark.parametrize("good", sorted(VALID_CONFIDENCES))
def test_validate_confidence_accepts(good: str):
    validate_confidence(good)


@pytest.mark.parametrize("bad", ["", "High", "certain", "med"])
def test_validate_confidence_rejects(bad: str):
    with pytest.raises(ValidationError, match="unknown confidence"):
        validate_confidence(bad)
