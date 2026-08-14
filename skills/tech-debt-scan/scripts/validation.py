"""Shared validators for tech-debt-scan."""
from __future__ import annotations

import re
from typing import Final

VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "approved", "rejected", "promoted"}
)

# Slug: starts with a lowercase letter, then 0-63 more of [a-z0-9-] (max 64
# chars total), must not end with a hyphen. The leading-letter + length-1
# allowance are fixed by test_validation.py (accepts "a", rejects "1-good"),
# which the original plan regex `^[a-z0-9][a-z0-9-]{1,63}$` contradicted.
_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class ValidationError(ValueError):
    """Raised when a value fails one of the shared validators."""


def validate_slug(value: str) -> None:
    if not _SLUG_RE.fullmatch(value):
        raise ValidationError(f"invalid slug: {value!r}")
    if value.endswith("-"):
        raise ValidationError(f"slug must not end with hyphen: {value!r}")


def validate_status(value: str) -> None:
    if value not in VALID_STATUSES:
        raise ValidationError(
            f"unknown status: {value!r}; expected one of {sorted(VALID_STATUSES)}"
        )


VALID_CHANGE_SIZES: Final[frozenset[str]] = frozenset({"S", "M", "L", "XL"})
VALID_CHANGE_RISKS: Final[frozenset[str]] = frozenset({"low", "med", "high"})
VALID_DISPOSITIONS: Final[frozenset[str]] = frozenset(
    {"full-repayment", "debt-conversion", "interest-only"}
)


def validate_change_size(value: str) -> None:
    if value not in VALID_CHANGE_SIZES:
        raise ValidationError(
            f"unknown change_size: {value!r}; expected one of {sorted(VALID_CHANGE_SIZES)}"
        )


def validate_change_risk(value: str) -> None:
    if value not in VALID_CHANGE_RISKS:
        raise ValidationError(
            f"unknown change_risk: {value!r}; expected one of {sorted(VALID_CHANGE_RISKS)}"
        )


def validate_disposition(value: str) -> None:
    if value not in VALID_DISPOSITIONS:
        raise ValidationError(
            f"unknown disposition: {value!r}; expected one of {sorted(VALID_DISPOSITIONS)}"
        )
