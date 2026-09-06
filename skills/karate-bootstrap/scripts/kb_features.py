"""Grep-level Gherkin structure shared by flow_map.py and kb_report.py.

``parse_feature`` splits a feature file into its feature-level tags and its
``Background``, ``Scenario`` and ``Scenario Outline`` blocks. It is deliberately
not a Gherkin parser: the generated gate and the report only need tags, names
and body text (spec 5.6, "grep-level checks by design").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

PARALLEL_FALSE_TAG: Final[str] = "@parallel=false"
KNOWN_DEFECT_TAG: Final[str] = "@known-defect"

# Helpers and reset.feature arguments that mutate shared state. A scenario using
# any of them must carry @parallel=false (spec 5.6, isolation by data).
EXCLUSIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"Stubs\.reset\(|Stubs\.load\(|Db\.truncate\(|\btruncate:|\bstubs:"
)

_TAG_LINE_RE = re.compile(r"^\s*@\S")
_FEATURE_RE = re.compile(r"^\s*Feature:")
_BLOCK_RE = re.compile(r"^\s*(Background|Scenario Outline|Scenario):\s*(.*?)\s*$")


@dataclass
class Block:
    kind: str  # "Background", "Scenario" or "Scenario Outline"
    name: str
    tags: set[str]
    body: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.body)


@dataclass
class ParsedFeature:
    tags: set[str]
    blocks: list[Block]

    def scenarios(self) -> list[Block]:
        return [b for b in self.blocks if b.kind != "Background"]

    def background_text(self) -> str:
        return "\n".join(b.text() for b in self.blocks if b.kind == "Background")

    def effective_tags(self, block: Block) -> set[str]:
        return self.tags | block.tags


def parse_feature(text: str) -> ParsedFeature:
    feature_tags: set[str] = set()
    pending: set[str] = set()
    blocks: list[Block] = []
    current: Block | None = None
    for line in text.splitlines():
        if _TAG_LINE_RE.match(line):
            pending |= set(line.split())
            continue
        if _FEATURE_RE.match(line):
            feature_tags, pending = pending, set()
            continue
        match = _BLOCK_RE.match(line)
        if match:
            current = Block(match.group(1), match.group(2), pending)
            pending = set()
            blocks.append(current)
            continue
        if current is not None:
            current.body.append(line)
    return ParsedFeature(feature_tags, blocks)


def unsafe_parallel_scenarios(text: str) -> list[str]:
    """Names of scenarios that touch exclusive state without ``@parallel=false``.

    An unsafe Background taints every scenario in the feature unless the feature
    itself carries the tag.
    """
    parsed = parse_feature(text)
    background_unsafe = bool(EXCLUSIVE_RE.search(parsed.background_text()))
    return [
        block.name or block.kind
        for block in parsed.scenarios()
        if PARALLEL_FALSE_TAG not in parsed.effective_tags(block)
        and (background_unsafe or EXCLUSIVE_RE.search(block.text()))
    ]


def known_defect_scenario_count(text: str) -> int:
    """Scenarios (outlines count once, not per example row) quarantined with ``@known-defect``."""
    parsed = parse_feature(text)
    return sum(1 for b in parsed.scenarios() if KNOWN_DEFECT_TAG in parsed.effective_tags(b))
