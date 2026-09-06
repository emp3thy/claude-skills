"""slugs.py: deterministic, validator-clean slugs from finding titles."""
from __future__ import annotations

import pytest
from slugs import slugify, unique_slugs
from validation import ValidationError, validate_slug


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Refund failure swallowed by a bare except", "refund-failure-swallowed-by-a-bare-except"),
        ("  Mixed CASE and  spaces  ", "mixed-case-and-spaces"),
        ("punctuation: it's a (test) -- really!", "punctuation-it-s-a-test-really"),
        ("123 leading digits", "f-123-leading-digits"),
        ("", "finding"),
        ("---", "finding"),
        ("Ünïcode tïtle", "n-code-t-tle"),
    ],
)
def test_slugify_is_deterministic_and_valid(title: str, expected: str) -> None:
    assert slugify(title) == expected
    validate_slug(slugify(title))


def test_slugify_truncates_to_the_validator_limit() -> None:
    slug = slugify("word " * 40)
    assert len(slug) <= 64 and not slug.endswith("-")
    validate_slug(slug)


def test_unique_slugs_deduplicates_in_order() -> None:
    assert unique_slugs(["Same title", "Same title", "Other", "Same title"]) == [
        "same-title", "same-title-2", "other", "same-title-3",
    ]
    for slug in unique_slugs(["x" * 70, "x" * 70]):
        validate_slug(slug)


def test_unique_slugs_rejects_nothing_the_validator_would() -> None:
    titles = ["", "---", "9", "A" * 200, "réfund"]
    for slug in unique_slugs(titles):
        try:
            validate_slug(slug)
        except ValidationError as exc:  # pragma: no cover - the assert carries the message
            raise AssertionError(f"{slug!r}: {exc}") from exc
