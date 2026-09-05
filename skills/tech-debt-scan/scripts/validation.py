"""Shared validators for tech-debt-scan."""
from __future__ import annotations

import re
from typing import Final

VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "approved", "rejected", "accepted", "promoted"}
)

# Debt-type axis (classification, orthogonal to the scout family). Derived
# from the SATD / Alves taxonomies: code and design debt are merged into
# "code" vs "design" at the scout's discretion; the rest are the widely-agreed
# artifact buckets. v2 (spec 2.2) adds security, infrastructure,
# knowledge-process and defect; data and ml-ai are reserved for the data-ml
# follow-on and performance is deliberately absent.
VALID_DEBT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "code",
        "design",
        "architecture",
        "test",
        "documentation",
        "dependency",
        "build",
        "requirement",
        "security",
        "infrastructure",
        "knowledge-process",
        "defect",
    }
)

# Evidence tier earned after verification (spec 4.8): A corroborated, B
# confirmed only, C unverified or downgraded.
VALID_TIERS: Final[frozenset[str]] = frozenset({"A", "B", "C"})

# Optional taxonomy id TD-01 to TD-35 (spec 2.1); checked only when present.
_TYPE_ID_RE: Final[re.Pattern[str]] = re.compile(r"^TD-\d{2}$")
_TYPE_ID_MAX: Final[int] = 35

# Effort: S (< half a day), M (half a day to ~2 days), L (larger / needs a plan).
VALID_EFFORTS: Final[frozenset[str]] = frozenset({"S", "M", "L"})

# Confidence the evidence really is debt (vs. intentional or a false positive).
VALID_CONFIDENCES: Final[frozenset[str]] = frozenset({"low", "medium", "high"})

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


def validate_debt_type(value: str) -> None:
    if value not in VALID_DEBT_TYPES:
        raise ValidationError(
            f"unknown debt_type: {value!r}; expected one of {sorted(VALID_DEBT_TYPES)}"
        )


def validate_effort(value: str) -> None:
    if value not in VALID_EFFORTS:
        raise ValidationError(
            f"unknown effort: {value!r}; expected one of {sorted(VALID_EFFORTS)}"
        )


def validate_confidence(value: str) -> None:
    if value not in VALID_CONFIDENCES:
        raise ValidationError(
            f"unknown confidence: {value!r}; expected one of {sorted(VALID_CONFIDENCES)}"
        )


def validate_type_id(value: str) -> None:
    if not _TYPE_ID_RE.fullmatch(value) or not 1 <= int(value[3:]) <= _TYPE_ID_MAX:
        raise ValidationError(f"invalid type_id: {value!r}; expected TD-01 to TD-{_TYPE_ID_MAX}")


def validate_tier(value: str) -> None:
    if value not in VALID_TIERS:
        raise ValidationError(f"unknown tier: {value!r}; expected one of {sorted(VALID_TIERS)}")
