from __future__ import annotations

from pathlib import Path

import pytest
from markers import CHEAT_SHEET, KINDS, STACKS, tokens_for

SKILL = Path(__file__).resolve().parent.parent
REFERENCE = SKILL / "reference"

STACK_HEADINGS = (
    "## Entry points",
    "## Exits: database writes",
    "## Exits: message publish",
    "## Subscriptions",
    "## Exits: outbound HTTP",
    "## Reads",
    "## Table and destination names",
    "## Config keys and roles",
    "## Readiness",
    "## Auth switches",
    "## Validation",
    "## Marker tokens verify-refs accepts",
)


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_exists_where_the_ledger_points(stack: str) -> None:
    path = SKILL / CHEAT_SHEET[stack]
    assert path == REFERENCE / f"stack-{stack}.md"
    assert path.is_file()


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_has_every_heading(stack: str) -> None:
    text = (REFERENCE / f"stack-{stack}.md").read_text(encoding="utf-8")
    for heading in STACK_HEADINGS:
        assert heading in text, f"{stack}: missing {heading}"


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_lists_every_marker_token(stack: str) -> None:
    text = (REFERENCE / f"stack-{stack}.md").read_text(encoding="utf-8")
    tokens_section = text[text.index("## Marker tokens verify-refs accepts"):]
    for kind in KINDS:
        for token in tokens_for(stack, kind):
            assert f"`{token}`" in tokens_section, f"{stack}/{kind}: token {token!r} not listed"
