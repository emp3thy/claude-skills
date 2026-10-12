"""References, anchors and checkability -> anchors.json (spec 5.2 to 5.5).

``anchors.json`` is ``{"references": [Reference...], "anchors": [Anchor...],
"unanchored": [{"doc", "line", "ref", "reason"}], "checkability": {doc: {...}},
"counts": {"references", "paths", "anchored", "ambiguous", "unknown"},
"skipped": [{"doc", "reason"}]}``; the Reference and Anchor records are the shared contract in
the plan.

- **References**: every inline code span outside code blocks, and every HTML ``<code>`` span on
  a line outside code blocks (not inside a code span), whose first token looks like a name
  (``first_token``). Its ``block`` is the scanner block holding it (an HTML span takes the
  smallest block holding its line), its ``heading`` the nearest heading above that block, and
  its ``context`` the normalised specific references of its block plus the specific names of
  that heading (its code spans, else the dotted names in its text), less its own name.
- **Resolution** (``resolve``): a reference that is an existing path needs no anchor and is
  listed with reason ``path``; a specific one takes its definitions of the best rank present
  (a dotted name with none falls back to its last segment), ambiguous over
  ``SPECIFIC_LIMIT``; a bare one takes the definitions whose owners meet its context, ambiguous
  with none or over ``BARE_LIMIT``; a name with no definition at all is ``unknown``. Every
  reference without an anchor is in ``unanchored`` with its reason, so ``counts`` add up:
  ``references = paths + anchored + ambiguous + unknown``. Each chosen definition is an anchor.
- **Checkability** (``checkability``): per doc, the references, the anchored references, their
  rate, and the paragraphs, list items and table rows (``blocks``) with the ones holding no
  reference (``blocks_noref``). ``unverifiable`` with no anchored reference, ``weak`` under
  ``min_anchor_ratio`` or under ``MIN_ANCHORS`` anchored references, else ``ok``.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, TypedDict

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_config import load_config
from dd_defindex import RANK, Definition, by_norm, is_specific, norm
from dd_history import History
from dd_md_scan import Block, Scan, scan
from dd_resolve import path_matches


class Reference(TypedDict):
    doc: str
    line: int
    text: str
    norm: str
    specific: bool
    block: list[int]
    heading: str | None
    context: list[str]


class Anchor(TypedDict):
    doc: str
    line: int
    ref: str
    file: str
    start: int
    end: int
    kind: str
    change_ranges: list[list[int]]
    reading: list[int]


SPECIFIC_LIMIT = 10
BARE_LIMIT = 3
MIN_ANCHORS = 3
COUNTED_BLOCKS: frozenset[str] = frozenset({"paragraph", "list_item", "table_row"})
CODE_BLOCKS: frozenset[str] = frozenset({"fence", "indented_code"})

_NAME = re.compile(r"^[A-Za-z_][\w.\-]{2,}$")
_FLAG = re.compile(r"^--[\w-]+$")
_HTML_CODE = re.compile(r"<code(?:\s[^>]*)?>(.*?)</code\s*>", re.IGNORECASE)
_DOTTED = re.compile(r"(?<![\w.])[A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)+")
_SURROUNDING = "()[]{},:;"

_Range = tuple[int, int]


def first_token(span: str) -> str | None:
    """The name a code span refers to: its first whitespace-separated piece without
    surrounding ``()[]{},:;`` or a call's argument list (``save(path)`` is ``save``); None
    unless it looks like a name (``^[A-Za-z_][\\w.\\-]{2,}$``), a ``--flag`` or holds a ``/``."""
    pieces = span.split()
    if not pieces:
        return None
    token = pieces[0].strip(_SURROUNDING)
    if "(" in token:
        token = token[: token.index("(")].strip(_SURROUNDING)
    if _NAME.match(token) or _FLAG.match(token) or (token and "/" in token):
        return token
    return None


def _code_lines(blocks: Iterable[Block]) -> set[int]:
    return {line for b in blocks if b.kind in CODE_BLOCKS
            for line in range(b.line_start, b.line_end + 1)}


def _span_cover(sc: Scan) -> dict[int, list[_Range]]:
    """Per line, the column ranges covered by code spans, backticks included."""
    cover: dict[int, list[_Range]] = {}
    for inline in sc.inlines:
        if inline.kind != "code":
            continue
        for line in range(inline.line, inline.end_line + 1):
            start = inline.outer_col if line == inline.line and inline.outer_col is not None \
                else 0
            end = inline.outer_end_col \
                if line == inline.end_line and inline.outer_end_col is not None \
                else len(sc.lines[line - 1])
            cover.setdefault(line, []).append((start, end))
    return cover


def _block_at(blocks: list[Block], line: int) -> _Range:
    """The line range of the smallest non-blank block holding ``line`` (the later one on a
    tie); the line itself when no block holds it."""
    holding = [(b.line_end - b.line_start, -i) for i, b in enumerate(blocks)
               if b.kind != "blank" and b.line_start <= line <= b.line_end]
    if not holding:
        return line, line
    block = blocks[-min(holding)[1]]
    return block.line_start, block.line_end


def _spans(sc: Scan) -> list[tuple[int, int, str, _Range]]:
    """``(line, col, token, block range)`` of every reference span, in document order."""
    code = _code_lines(sc.blocks)
    found: list[tuple[int, int, str, _Range]] = []
    for inline in sc.inlines:
        token = first_token(inline.text) if inline.kind == "code" else None
        if token is not None:
            b = sc.blocks[inline.block]
            found.append((inline.line, inline.col, token, (b.line_start, b.line_end)))
    cover = _span_cover(sc)
    for number, text in enumerate(sc.lines, 1):
        if number in code:
            continue
        for match in _HTML_CODE.finditer(text):
            if any(a <= match.start() < b for a, b in cover.get(number, [])):
                continue
            token = first_token(html.unescape(match.group(1)))
            if token is not None:
                found.append((number, match.start(), token, _block_at(sc.blocks, number)))
    return sorted(found)


def references(doc: str, text: str) -> list[Reference]:
    """The references of one doc, in document order (spec 5.2)."""
    sc = scan(text)
    spans = _spans(sc)
    by_block: dict[_Range, list[str]] = {}
    for _, _, token, block in spans:
        if is_specific(token):
            by_block.setdefault(block, []).append(norm(token))
    headings = [b for b in sc.blocks if b.kind == "heading"]

    def heading_of(block: _Range) -> Block | None:
        above = [h for h in headings if h.line_end < block[0]]
        return above[-1] if above else None

    def heading_names(h: Block) -> list[str]:
        named = by_block.get((h.line_start, h.line_end))
        if named:
            return named
        return [norm(name) for name in _DOTTED.findall(h.text or "")]

    refs: list[Reference] = []
    for line, _, token, block in spans:
        own = norm(token)
        heading = heading_of(block)
        names = by_block.get(block, []) + (heading_names(heading) if heading else [])
        refs.append(Reference(
            doc=doc, line=line, text=token, norm=own, specific=is_specific(token),
            block=[block[0], block[1]], heading=heading.text if heading else None,
            context=[n for n in dict.fromkeys(names) if n != own],
        ))
    return refs


def _choose(ref: Reference, defs: Mapping[str, list[Definition]]) -> tuple[
        list[Definition], str | None]:
    """The definitions a reference anchors to, or ``([], reason)``."""
    candidates = defs.get(ref["norm"], [])
    if ref["specific"]:
        if not candidates and "." in ref["text"]:
            candidates = defs.get(norm(ref["text"].rsplit(".", 1)[1]), [])
        if not candidates:
            return [], "unknown"
        best = min(RANK[d["kind"]] for d in candidates)
        chosen = [d for d in candidates if RANK[d["kind"]] == best]
        return ([], "ambiguous") if len(chosen) > SPECIFIC_LIMIT else (chosen, None)
    if not candidates:
        return [], "unknown"
    context = set(ref["context"])
    chosen = [d for d in candidates if context.intersection(d["owners"])]
    return ([], "ambiguous") if not chosen or len(chosen) > BARE_LIMIT else (chosen, None)


def resolve(refs: Iterable[Reference], defs: Mapping[str, list[Definition]],
            files: frozenset[str], dirs: frozenset[str],
            ) -> tuple[list[Anchor], list[dict[str, Any]]]:
    """``(anchors, unanchored)`` for ``refs`` against ``defs`` (``by_norm`` groups) and the
    tracked ``files`` and ``dirs`` (spec 5.3). A token holding ``/`` is matched as a path
    loosely (by suffix and basename too), any other only relative to the doc or the root."""
    anchors: list[Anchor] = []
    unanchored: list[dict[str, Any]] = []
    for ref in refs:
        text = ref["text"]
        chosen: list[Definition] = []
        reason: str | None = "path"
        if not path_matches(text, ref["doc"], files, dirs, loose="/" in text):
            chosen, reason = _choose(ref, defs)
        if reason is not None:
            unanchored.append({"doc": ref["doc"], "line": ref["line"], "ref": text,
                               "reason": reason})
        anchors += [Anchor(doc=ref["doc"], line=ref["line"], ref=text, file=d["file"],
                           start=d["start"], end=d["end"], kind=d["kind"],
                           change_ranges=[list(r) for r in d["change_ranges"]],
                           reading=list(d["reading"]))
                    for d in chosen]
    return anchors, unanchored


def checkability(docs: list[str], texts: Mapping[str, str], refs: Iterable[Reference],
                 anchors: Iterable[Anchor], config: Mapping[str, Any],
                 ) -> dict[str, dict[str, Any]]:
    """Per doc: ``references``, ``anchored`` (references with an anchor), ``rate``,
    ``blocks``, ``blocks_noref`` and ``status`` (spec 5.5)."""
    ratio = float(config.get("min_anchor_ratio", 0.25))
    anchored_keys = {(a["doc"], a["line"], a["ref"]) for a in anchors}
    per_doc: dict[str, list[Reference]] = {doc: [] for doc in docs}
    for ref in refs:
        per_doc.setdefault(ref["doc"], []).append(ref)
    result: dict[str, dict[str, Any]] = {}
    for doc in docs:
        doc_refs = per_doc[doc]
        total = len(doc_refs)
        anchored = sum((r["doc"], r["line"], r["text"]) in anchored_keys for r in doc_refs)
        rate = anchored / total if total else 0.0
        held = {(r["block"][0], r["block"][1]) for r in doc_refs}
        blocks = [(b.line_start, b.line_end) for b in scan(texts.get(doc, "")).blocks
                  if b.kind in COUNTED_BLOCKS]
        if anchored == 0:
            status = "unverifiable"
        elif rate < ratio or anchored < MIN_ANCHORS:
            status = "weak"
        else:
            status = "ok"
        result[doc] = {"references": total, "anchored": anchored, "rate": round(rate, 4),
                       "blocks": len(blocks),
                       "blocks_noref": sum(block not in held for block in blocks),
                       "status": status}
    return result


def _read_doc(root: Path, doc: str) -> str | None:
    try:
        return (root / doc).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _load(path: Path, step: str) -> Any:
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def run(root: Path, workdir: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve the references of every in-scope doc in ``workdir/inventory.json`` against
    ``workdir/defindex.json`` and HEAD's tracked paths; write ``anchors.json``."""
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    defindex = _load(workdir / "defindex.json", "dd_defindex")
    texts: dict[str, str] = {}
    skipped: list[dict[str, str]] = []
    for doc in inventory["docs"]:
        text = _read_doc(root, doc)
        if text is None:
            skipped.append({"doc": doc, "reason": "unreadable"})
        else:
            texts[doc] = text
    docs = [doc for doc in inventory["docs"] if doc in texts]
    refs = [ref for doc in docs for ref in references(doc, texts[doc])]
    files, dirs = History(root).head_files()
    anchors, unanchored = resolve(refs, by_norm(defindex["definitions"]), files, dirs)
    reasons = [u["reason"] for u in unanchored]
    result: dict[str, Any] = {
        "references": refs,
        "anchors": anchors,
        "unanchored": unanchored,
        "checkability": checkability(docs, texts, refs, anchors, config),
        "counts": {"references": len(refs), "paths": reasons.count("path"),
                   "anchored": len(refs) - len(unanchored),
                   "ambiguous": reasons.count("ambiguous"),
                   "unknown": reasons.count("unknown")},
        "skipped": skipped,
    }
    write_json(workdir / "anchors.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve doc references to code definitions and measure checkability.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    config, _ = load_config(args.repo)
    try:
        run(args.repo, args.workdir, config)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
