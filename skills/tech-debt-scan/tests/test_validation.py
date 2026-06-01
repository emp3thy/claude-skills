# skills/tech-debt-scan/tests/test_validation.py
from __future__ import annotations

import pytest
from validation import (
    VALID_STATUSES,
    ValidationError,
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
