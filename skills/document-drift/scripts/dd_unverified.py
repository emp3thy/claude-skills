"""The notice loop for blocks nothing can be tied to (spec 7.3) -> notices.json.

A notice is one HTML comment on its own line directly above a block (Notice line grammar in
the plan's shared contracts). On every run ``run_start`` reads each notice in the in-scope docs
and decides, in this order, from the block below it (the next non-blank block that is not a
comment-only HTML block; a list is every item sharing the first item's ``list_id``, a table the
run of ``table_row``/``table_delim`` blocks):

- ``clear-anchored``: an anchor in ``anchors.json`` lies on a line of the block;
- ``clear-changed``: the block's hash differs from the notice's;
- ``clear-ignore``: an honoured ``drift-ignore`` marker's target overlaps the notice line or
  the block (a marker directly above the notice targets the notice);
- ``escalate``: a 1st notice becomes a 2nd notice for the current run;
- ``remove``: a 2nd notice and its block are removed (an edit of type ``unverified``).

A notice whose run id sorts after the current run id, a line starting with
``<!-- drift-unverified:`` that does not match the grammar, a notice with no block below it,
and all but the lowest of several notices over one block are ``stale``: listed, left alone.
Notices inside code blocks are examples and are not read.

``run_verify`` turns the review agents' nominations into 1st notices. A nominated range is
widened to the outermost block holding its first line (a whole list or table), so its hash is
the one ``run_start`` computes on the next run. A nomination is skipped when its doc is not in
scope, no block holds the line, the block carries ``drift-ignore`` or an anchor, another
nomination already took the block, or a notice already covers it (a ``clear-changed`` block may
be noticed again: its notice goes and a new 1st notice starts, spec 7.3).

``notices.json`` is ``{"decisions": [Decision], "edits": [Edit], "stale": [{"doc", "line",
"reason"}], "nominations": [{"doc", "start_line", "end_line", "why", "skipped"}]}``; edit ids
``n001``... run over decision and nomination edits together in doc then line order.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TypedDict

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_md_scan import Block, Scan, scan

NOTICE_PREFIX = "<!-- drift-unverified:"
_NOTICE = re.compile(
    r"^<!-- drift-unverified: (1st|2nd) notice, run (\S+), block ([0-9a-f]{8})\. .* -->$")
_TEXTS = {
    1: "This describes the code but names nothing in it. Name what it describes, or add "
       "drift-ignore: <reason>.",
    2: "NEEDS A HUMAN DECISION: name what this describes, add drift-ignore: <reason>, or "
       "rewrite it. The next drift run removes this block otherwise.",
}
_ORDINALS = {1: "1st", 2: "2nd"}
_TABLE_KINDS = frozenset({"table_row", "table_delim"})
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_CLAIMS = {"clear-anchored": "now anchored", "clear-changed": "block changed",
           "clear-ignore": "drift-ignore"}

STALE_FUTURE = "run newer than the current run"
STALE_MALFORMED = "malformed"
STALE_NO_BLOCK = "no block below"
STALE_DUPLICATE = "another notice covers the block"

Range = tuple[int, int]


class Notice(TypedDict):
    stage: int
    run: str
    hash: str


def parse_notice(line: str) -> Notice | None:
    """The stage, run id and block hash of a notice line, or None when it is not one."""
    m = _NOTICE.match(line.strip())
    if m is None:
        return None
    return {"stage": 1 if m[1] == "1st" else 2, "run": m[2], "hash": m[3]}


def render_notice(stage: int, run_id: str, block: str) -> str:
    """The notice line of ``stage`` (1 or 2) for ``run_id`` and the block hash ``block``."""
    return (f"<!-- drift-unverified: {_ORDINALS[stage]} notice, run {run_id}, block {block}. "
            f"{_TEXTS[stage]} -->")


def block_hash(text: str) -> str:
    """First 8 hex digits of the SHA-256 of ``text`` with whitespace runs collapsed."""
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:8]


def ignore_regions(markers: Sequence[Mapping[str, Any]], doc: str) -> list[Range]:
    """Target line ranges of the honoured ``drift-ignore`` markers (a reason and a target) of
    ``doc`` in ``tokens.json`` ``markers``."""
    return [(m["target_line_start"], m["target_line_end"]) for m in markers
            if m["doc"] == doc and m.get("reason") and m.get("target_line_start") is not None]


def _overlaps(a: Range, b: Range) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _comment_only(sc: Scan, b: Block) -> bool:
    body = "\n".join(sc.lines[b.line_start - 1:b.line_end])
    return b.kind == "html" and not _COMMENT.sub("", body).strip()


def _widen(sc: Scan, idx: int) -> Range:
    """Lines of block ``idx`` widened to its whole list or table."""
    blocks = sc.blocks
    top = blocks[idx]
    if top.kind == "list_item":
        items = [b for b in blocks if b.kind == "list_item" and b.list_id == top.list_id]
        return min(b.line_start for b in items), max(b.line_end for b in items)
    if top.kind in _TABLE_KINDS:
        first = last = idx
        while first > 0 and blocks[first - 1].kind in _TABLE_KINDS:
            first -= 1
        while last + 1 < len(blocks) and blocks[last + 1].kind in _TABLE_KINDS:
            last += 1
        return blocks[first].line_start, blocks[last].line_end
    return top.line_start, top.line_end


def _outermost(sc: Scan, cands: list[int]) -> int | None:
    if not cands:
        return None
    return min(cands, key=lambda i: (sc.blocks[i].line_start, -sc.blocks[i].line_end, i))


def block_below(sc: Scan, line: int) -> Range | None:
    """The block a notice on ``line`` covers: the outermost block starting first after it,
    skipping blank lines and comment-only HTML, widened to its list or table."""
    idx = _outermost(sc, [i for i, b in enumerate(sc.blocks) if b.line_start > line
                          and b.kind != "blank" and not _comment_only(sc, b)])
    return None if idx is None else _widen(sc, idx)


def block_at(sc: Scan, line: int) -> Range | None:
    """The outermost non-blank block holding ``line``, widened to its list or table."""
    idx = _outermost(sc, [i for i, b in enumerate(sc.blocks)
                          if b.line_start <= line <= b.line_end and b.kind != "blank"])
    return None if idx is None else _widen(sc, idx)


def _text(sc: Scan, rng: Range) -> str:
    return "\n".join(sc.lines[rng[0] - 1:rng[1]])


def _edit(doc: str, rng: Range, old: str, new: str, kind: str, claim: str,
          subject: str) -> dict[str, Any]:
    return {"id": "", "doc": doc, "start_line": rng[0], "end_line": rng[1], "old": old,
            "new": new, "type": kind, "claim": claim, "evidence": [], "subject": subject}


def _notices(sc: Scan) -> list[int]:
    """Lines starting a comment that opens with the notice prefix (outside code blocks)."""
    return sorted({c.line_start for c in sc.comments
                   if sc.lines[c.line_start - 1].strip().startswith(NOTICE_PREFIX)})


def decide(doc: str, text: str, anchors_for_doc: Sequence[Mapping[str, Any]],
           ignore: Sequence[Range], run_id: str
           ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Decisions, edits (ids unset) and stale notices for the notices in one doc."""
    sc = scan(text)
    anchored = {int(a["line"]) for a in anchors_for_doc}
    stale: list[dict[str, Any]] = []
    found: list[tuple[int, Notice, Range]] = []
    for line in _notices(sc):
        notice = parse_notice(sc.lines[line - 1])
        block = block_below(sc, line)
        reason = (STALE_MALFORMED if notice is None
                  else STALE_FUTURE if notice["run"] > run_id
                  else STALE_NO_BLOCK if block is None else None)
        if reason is not None or notice is None or block is None:
            stale.append({"doc": doc, "line": line, "reason": reason})
            continue
        found.append((line, notice, block))
    lowest = {block: line for line, _, block in found}
    decisions: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []
    for line, notice, block in found:
        if lowest[block] != line:
            stale.append({"doc": doc, "line": line, "reason": STALE_DUPLICATE})
            continue
        own = sc.lines[line - 1]
        if any(block[0] <= n <= block[1] for n in anchored):
            action = "clear-anchored"
        elif block_hash(_text(sc, block)) != notice["hash"]:
            action = "clear-changed"
        elif any(_overlaps(r, (line, block[1])) for r in ignore):
            action = "clear-ignore"
        else:
            action = "escalate" if notice["stage"] == 1 else "remove"
        decisions.append({"doc": doc, "line": line, "stage": notice["stage"],
                          "run": notice["run"], "hash": notice["hash"], "block": list(block),
                          "action": action})
        if action in _CLAIMS:
            edits.append(_edit(doc, (line, line), own, "", "clear", _CLAIMS[action],
                               notice["hash"]))
        elif action == "escalate":
            indent = own[:len(own) - len(own.lstrip())]
            edits.append(_edit(doc, (line, line), own,
                               indent + render_notice(2, run_id, notice["hash"]),
                               "escalate", "2nd notice", notice["hash"]))
        else:
            edits.append(_edit(doc, (line, block[1]), _text(sc, (line, block[1])), "",
                               "unverified", f"3rd notice, unchanged since {notice['run']}",
                               notice["hash"]))
    stale.sort(key=lambda s: s["line"])
    return decisions, edits, stale


def _skip(sc: Scan, block: Range | None, decisions: Sequence[Mapping[str, Any]],
          ignore: Sequence[Range], anchored: set[int], taken: set[Range]) -> str | None:
    if block is None:
        return "no block"
    if any(_overlaps(r, block) for r in ignore):
        return "drift-ignore"
    if any(block[0] <= n <= block[1] for n in anchored):
        return "anchored"
    if block in taken:
        return "duplicate"
    renoticeable = {d["line"] for d in decisions if d["action"] == "clear-changed"}
    for d in decisions:
        if d["action"] != "clear-changed" and (
                _overlaps((d["block"][0], d["block"][1]), block)
                or block[0] <= d["line"] <= block[1]):
            return "already noticed"
    above = block[0] - 1
    if (above >= 1 and sc.lines[above - 1].strip().startswith(NOTICE_PREFIX)
            and above not in renoticeable):
        return "already noticed"
    return None


def nominate(nominations: Sequence[Mapping[str, Any]], texts: Mapping[str, str],
             existing_decisions: Sequence[Mapping[str, Any]], run_id: str, *,
             ignore: Mapping[str, Sequence[Range]] | None = None,
             anchors: Sequence[Mapping[str, Any]] = (),
             skipped: list[str | None] | None = None) -> list[dict[str, Any]]:
    """1st-notice edits (ids unset, doc then line order) for the nominated blocks; when
    ``skipped`` is given it receives, per nomination, the reason it was skipped or None."""
    scans: dict[str, Scan] = {}
    taken: dict[str, set[Range]] = {}
    edits: list[dict[str, Any]] = []
    for nom in nominations:
        doc = nom["doc"]
        reason: str | None = "not in scope"
        if doc in texts:
            sc = scans.setdefault(doc, scan(texts[doc]))
            block = block_at(sc, int(nom["start_line"]))
            reason = _skip(sc, block, [d for d in existing_decisions if d["doc"] == doc],
                           (ignore or {}).get(doc, ()),
                           {int(a["line"]) for a in anchors if a["doc"] == doc},
                           taken.setdefault(doc, set()))
            if reason is None and block is not None:
                taken[doc].add(block)
                first = sc.lines[block[0] - 1]
                digest = block_hash(_text(sc, block))
                edits.append(_edit(doc, (block[0], block[0]), first,
                                   render_notice(1, run_id, digest) + "\n" + first,
                                   "notice", "1st notice", digest))
        if skipped is not None:
            skipped.append(reason)
    return sorted(edits, key=lambda e: (e["doc"], e["start_line"]))


def number(edits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort edits by doc then line and give them ids ``n001``, ``n002``, ..."""
    ordered = sorted(edits, key=lambda e: (e["doc"], e["start_line"], e["end_line"]))
    return [dict(e, id=f"n{k:03d}") for k, e in enumerate(ordered, 1)]


def _load(path: Path, step: str) -> Any:
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def _texts(root: Path, docs: Sequence[str]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for doc in docs:
        try:
            texts[doc] = (root / doc).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return texts


def run_start(root: Path, workdir: Path, run_id: str) -> dict[str, Any]:
    """Decide on every notice in the in-scope docs; write ``notices.json``."""
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    anchors = _load(workdir / "anchors.json", "dd_anchors")["anchors"]
    markers = _load(workdir / "tokens.json", "dd_extract")["markers"]
    decisions: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for doc, text in sorted(_texts(root, inventory["docs"]).items()):
        d, e, s = decide(doc, text, [a for a in anchors if a["doc"] == doc],
                         ignore_regions(markers, doc), run_id)
        decisions += d
        edits += e
        stale += s
    result: dict[str, Any] = {"decisions": decisions, "edits": number(edits), "stale": stale,
                              "nominations": []}
    write_json(workdir / "notices.json", result)
    return result


def run_verify(root: Path, workdir: Path, nominations: Sequence[Mapping[str, Any]],
               run_id: str) -> dict[str, Any]:
    """Add 1st-notice edits for ``nominations`` to ``notices.json`` and renumber its edits.
    Earlier nomination edits are replaced, so a repeated call gives the same file."""
    result: dict[str, Any] = _load(workdir / "notices.json", "dd_unverified run_start")
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    anchors = _load(workdir / "anchors.json", "dd_anchors")["anchors"]
    markers = _load(workdir / "tokens.json", "dd_extract")["markers"]
    wanted = sorted({str(n["doc"]) for n in nominations} & set(inventory["docs"]))
    texts = _texts(root, wanted)
    skipped: list[str | None] = []
    new = nominate(nominations, texts, result["decisions"], run_id,
                   ignore={doc: ignore_regions(markers, doc) for doc in texts},
                   anchors=anchors, skipped=skipped)
    kept = [e for e in result["edits"] if e["type"] != "notice"]
    result["edits"] = number(kept + new)
    result["nominations"] = [
        {"doc": n["doc"], "start_line": n["start_line"], "end_line": n["end_line"],
         "why": n.get("why", ""), "skipped": why}
        for n, why in zip(nominations, skipped, strict=True)]
    write_json(workdir / "notices.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide on drift-unverified notices, or add nominated ones.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--run-id", help="the current run id (default: preflight.json)")
    parser.add_argument("--nominations", type=Path,
                        help="JSON list of nominations to add (verify stage)")
    args = parser.parse_args(argv)
    try:
        run_id = args.run_id or _load(args.workdir / "preflight.json", "dd_preflight")["run_id"]
        if args.nominations is None:
            run_start(args.repo, args.workdir, run_id)
        else:
            run_verify(args.repo, args.workdir, read_json(args.nominations), run_id)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
