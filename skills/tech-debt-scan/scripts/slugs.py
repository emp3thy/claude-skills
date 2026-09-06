"""Deterministic slugs for design findings.

A finding's slug is its identity in ``design.md``, in a PBI bundle id and in
``findings.json``. It is derived from the title so a reader can match the two,
and it always satisfies ``validation.validate_slug`` (start with a lowercase
letter, then at most 63 more of ``[a-z0-9-]``, never ending in a hyphen).

``_NON_SLUG`` strips every character outside ``[a-z0-9]``, with no
``unicodedata`` normalisation: an accented letter is a separator, not a
transliteration, so ``Ünïcode tïtle`` slugifies to ``n-code-t-tle``. That is
the pinned behaviour, chosen so the mapping is one regex a reader can check.

A leaf module: standard library only, no sibling imports.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

MAX_LENGTH: Final[int] = 64
FALLBACK: Final[str] = "finding"
_NON_SLUG: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """A validator-clean slug for ``title``; ``finding`` when nothing survives."""
    lowered = title.strip().lower()
    slug = _NON_SLUG.sub("-", lowered).strip("-")
    if not slug:
        return FALLBACK
    if not slug[0].isalpha():
        slug = f"f-{slug}"
    slug = slug[:MAX_LENGTH].rstrip("-")
    return slug or FALLBACK


def _suffixed(base: str, count: int) -> str:
    """``base`` shortened so ``-<count>`` still fits inside ``MAX_LENGTH``."""
    room = MAX_LENGTH - len(str(count)) - 1
    return f"{base[:room].rstrip('-')}-{count}"


def unique_slugs(titles: Sequence[str]) -> list[str]:
    """One slug per title, in order, with ``-2``, ``-3`` suffixes on collisions.

    The suffix counter is per base slug, and every emitted slug is also held in
    a ``taken`` set: a title that slugifies straight onto an already-emitted
    suffixed form (``"a"``, ``"a"``, ``"a-2"``) is pushed on to the next free
    suffix rather than duplicating it, which ``design_parser`` would reject.
    """
    seen: dict[str, int] = {}
    taken: set[str] = set()
    out: list[str] = []
    for title in titles:
        base = slugify(title)
        count = seen.get(base, 0) + 1
        slug = base if count == 1 else _suffixed(base, count)
        while slug in taken:
            count += 1
            slug = _suffixed(base, count)
        seen[base] = count
        taken.add(slug)
        out.append(slug)
    return out
