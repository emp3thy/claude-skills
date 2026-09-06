from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from flow_map import verify_refs
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


NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


@pytest.mark.parametrize("stack", STACKS)
def test_stack_sheet_states_the_verify_refs_window_symmetrically(stack: str) -> None:
    """verify_refs looks `window` lines either side of the via line, not only after it."""
    window = int(inspect.signature(verify_refs).parameters["window"].default)
    text = (REFERENCE / f"stack-{stack}.md").read_text(encoding="utf-8")
    tokens_section = text[text.index("## Marker tokens verify-refs accepts"):]
    assert f"within {NUMBER_WORDS[window]} lines before or after" in tokens_section


NOTE_HEADINGS = {
    "testcontainers-notes.md": ("## Topology", "## kb-runtime.json", "## Tokens",
                                "## Waits and timeouts", "## Logs and evidence files",
                                "## Running"),
    "karate-notes.md": ("## Runner flags", "## Tags", "## Data-driven outlines",
                        "## Calling reset.feature", "## Java helpers", "## Reports"),
    "failure-triage.md": ("## Classification order", "## 1. Infra", "## 2. Stub or seed missing",
                          "## 3. Expectation wrong", "## 4. Suspected app defect",
                          "## Quarantine procedure", "## Stop conditions"),
    "podman.md": ("## Linux", "## Windows and macOS", "## Ryuk", "## Verify"),
}


@pytest.mark.parametrize("name", sorted(NOTE_HEADINGS))
def test_note_has_every_heading(name: str) -> None:
    text = (REFERENCE / name).read_text(encoding="utf-8")
    for heading in NOTE_HEADINGS[name]:
        assert heading in text, f"{name}: missing {heading}"
