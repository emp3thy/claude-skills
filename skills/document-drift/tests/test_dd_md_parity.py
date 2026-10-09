"""Parity of dd_md_scan spans with markdown-it-py (CommonMark plus GFM tables).

markdown-it-py is a dev-only dependency and is used nowhere but here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from dd_md_scan import Scan, scan
from markdown_it import MarkdownIt

MARKDOWN_DIR = Path(__file__).resolve().parent / "fixtures" / "markdown"

# Spans the scanner deliberately does not model, removed from both sides before comparing:
# {(fixture name, span text): one-line reason}. Keep this as small as possible.
KNOWN_DIFFERENCES: dict[tuple[str, str], str] = {}

# Ruling R2: markdown-it's commonmark preset emits link_open for <scheme:...> autolinks, so
# our autolinks count with the link-like inlines.
LINK_KINDS = ("link", "reflink", "image", "autolink")


@dataclass
class Reference:
    fence_lines: list[tuple[int, int]] = field(default_factory=list)
    code_spans: Counter[str] = field(default_factory=Counter)
    link_targets: Counter[str] = field(default_factory=Counter)


def _walk(tokens: list[Any], ref: Reference) -> None:
    for tok in tokens:
        if tok.type == "code_inline":
            ref.code_spans[tok.content] += 1
        elif tok.type == "link_open":
            ref.link_targets[tok.attrs["href"]] += 1
        elif tok.type == "image":
            ref.link_targets[tok.attrs["src"]] += 1
        if tok.children:
            _walk(tok.children, ref)


def reference_spans(text: str) -> Reference:
    md = MarkdownIt("commonmark").enable("table")
    # Compare unescaped targets as written, not percent-encoded hrefs.
    md.normalizeLink = lambda url: url  # type: ignore[method-assign]
    ref = Reference()
    tokens = md.parse(text)
    for tok in tokens:
        if tok.type == "fence":
            ref.fence_lines.append((tok.map[0] + 1, tok.map[1]))
    _walk(tokens, ref)
    return ref


def fence_lines(ours: Scan) -> list[tuple[int, int]]:
    return [(b.line_start, b.line_end) for b in ours.blocks if b.kind == "fence"]


def test_corpus_is_present():
    names = {p.name for p in MARKDOWN_DIR.glob("*.md")}
    assert {"README.md", "architecture.md", "constructs.md"} <= names
    assert len(names) == 5


@pytest.mark.parametrize("name", sorted(p.name for p in MARKDOWN_DIR.glob("*.md")))
def test_parity_with_commonmark(name):
    text = (MARKDOWN_DIR / name).read_text(encoding="utf-8")
    ours, ref = scan(text), reference_spans(text)
    known = {span for (doc, span) in KNOWN_DIFFERENCES if doc == name}
    assert fence_lines(ours) == ref.fence_lines

    def _without_known(counter: Counter[str]) -> Counter[str]:
        return Counter({k: v for k, v in counter.items() if k not in known})

    our_code = Counter(i.text for i in ours.inlines if i.kind == "code")
    assert _without_known(our_code) == _without_known(ref.code_spans)
    our_links = Counter(i.text for i in ours.inlines if i.kind in LINK_KINDS)
    assert _without_known(our_links) == _without_known(ref.link_targets)


def test_parity_reference_sees_every_construct_in_constructs_md():
    ref = reference_spans((MARKDOWN_DIR / "constructs.md").read_text(encoding="utf-8"))
    assert "a`b" in ref.code_spans
    assert "across a line break" in ref.code_spans
    assert "a|b" in ref.code_spans
    assert ref.link_targets["docs/guide.md"] == 4
    assert "mailto:ops@example.com" in ref.link_targets
    assert "docs/two-line.md" in ref.link_targets
    assert "tab.txt" in ref.code_spans
    assert len(ref.fence_lines) == 5
