"""Findings and provable hunks -> findings.json, hunks-provable.json.

``findings.json`` is ``{"findings": [...], "history_unavailable": bool, "honoured": [...]}``:
every candidate of every class with an ``id`` (``F001``...) in (doc, line, col) order; the two
other keys pass through from ``candidates.json`` unchanged. ``hunks-provable.json`` is
``{"hunks": [Hunk...]}``. A Hunk's ``verb``, ``token_kind``, ``token_text`` and ``new_text``
describe its first finding (``finding_id``); every other finding folded into it is an ``also``
entry ``{"finding_id", "verb", "token_text", "new_text", "reason"}`` (ruling R42). In a
``delete`` hunk every ``also`` entry is a ``delete`` (the lines take the token with them).

Deletion units (spec 7.1 as amended), tried in order; the first rule that applies decides:

1. the subject of a list item with no nested item and at least one sibling: the item's lines
   (and the blank lines up to its next sibling);
2. the subject of a table body row, when the table keeps another body row: the row;
3. a script or fence path on a single-command line of a shell fence that is a command list and
   keeps another command line: the line;
4. a tree entry with no deeper entry directly beneath it: the line;
5. a link target (not an image): the whole ``[label](target)`` becomes ``label`` (``unlink``);
6. anything else: ``human``/``prose-mention``.

A rule that applies but whose unit is unsafe gives ``human``/``large-deletion``; so does a
reference definition (removing it breaks every usage), any delete inside a block quote (R40),
an edit overlapping an earlier hunk's lines without matching them, and every delete of a list,
table body, fence or tree whose planned deletes together would remove all of its items, body
rows, command lines or entries (R39). Edits with the same line range merge into the first one's
hunk. A demoted finding whose token sits inside lines another hunk deletes joins that hunk.
A span that no longer holds the token's text is ``human``/``recheck-failed``. A replacement in a
link, image or refdef destination is percent-encoded (R41).

Final-review rulings: a replace whose token sits in a heading is ``human``/``heading-reference``
(R62: the heading's slug may be a link target in another doc, which apply does not re-check).
Every hunk's ``reason``, and every ``also`` reason, either names a 7-hex commit after `` in ``
or starts with ``manifest ``; anything else is a planning bug and exits 5 (R64).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_extract import SHELL_INFOS, _tree_entry
from dd_md_scan import Block, scan

PROVABLE = ("provable-replace", "provable-delete")
_TABLE_KINDS = frozenset({"table_row", "table_delim"})
_DESTINATIONS = frozenset({"link", "image", "refdef"})
_PROMPT = re.compile(r"^\$(?:[ \t]+|$)")
_SEPARATORS = ("&", "|", ";")  # `&` covers `&&` and a background job, `|` covers `||`
_CONTINUED = ("\\", "`", "^")
_COMPOUND = re.compile(
    r"^(?:if|then|else|elif|fi|for|while|until|do|done|case|esac|function|select)(?:\s|;|$)"
)
_ORDERED = re.compile(r"^[ \t>]*\d{1,9}[.)]")
_ENCODE = {" ": "%20", "(": "%28", ")": "%29", "<": "%3C", ">": "%3E"}
_PROOF = re.compile(r" in [0-9a-f]{7}(?![0-9a-f])")  # R64: "renamed in a1b2c3d" and the like

Cand = dict[str, Any]
Span = tuple[int, int, str]  # [col, end_col) on line_start and its new text
Unit = tuple[str, int]  # (unit kind, id) of a line deletion, for ruling R39


@dataclass
class _Edit:
    line_start: int
    line_end: int
    verb: str
    spans: list[Span] = field(default_factory=list)  # empty for a line deletion
    new_text: str | None = None
    unit: Unit | None = None  # the list, table, fence or tree a line deletion belongs to
    total: int = 0  # how many members (items, body rows, commands, entries) the unit has


@dataclass
class _Also:
    pos: int
    verb: str
    new_text: str | None


@dataclass
class _Hunk:
    pos: int
    edit: _Edit
    also: list[_Also] = field(default_factory=list)

    def merge(self, pos: int, edit: _Edit) -> bool:
        """Fold ``edit`` into this hunk when both have the same lines and do not conflict."""
        mine = self.edit
        if (mine.line_start, mine.line_end) != (edit.line_start, edit.line_end):
            return False
        if mine.verb == "delete":
            self.also.append(_Also(pos, "delete", None))  # the lines take every edit along
            return True
        if edit.verb == "delete":
            return False
        fresh = [s for s in edit.spans if s not in mine.spans]
        if any(a < y and x < b for a, b, _ in fresh for x, y, _ in mine.spans):
            return False
        mine.spans.extend(fresh)
        self.also.append(_Also(pos, edit.verb, edit.new_text))
        return True


def _encode(text: str, angle: bool) -> str:
    """Ruling R41: a destination escapes what would end or break it."""
    chars = "<>" if angle else "".join(_ENCODE)
    return "".join(_ENCODE[ch] if ch in chars else ch for ch in text)


class _Doc:
    """The current text of one doc with its scanner blocks."""

    def __init__(self, text: str) -> None:
        sc = scan(text)
        self.lines = sc.lines
        self.blocks = sc.blocks

    def line(self, no: int) -> str:
        return self.lines[no - 1] if 1 <= no <= len(self.lines) else ""

    def find(self, kind: str, start: int, end: int | None = None) -> int | None:
        """Index of the one block of ``kind`` spanning ``start..end``, or None."""
        found = [i for i, b in enumerate(self.blocks) if b.kind == kind and b.line_start == start
                 and (end is None or b.line_end == end)]
        return found[0] if len(found) == 1 else None

    def quoted(self, start: int, end: int) -> bool:
        """True when a block quote encloses lines ``start..end`` (blocks in a quote keep the
        quote's own parent, so enclosure is judged by lines)."""
        return any(b.kind == "blockquote" and b.line_start <= start and end <= b.line_end
                   for b in self.blocks)

    # -- rules -------------------------------------------------------------------------------

    def edit(self, c: Cand) -> _Edit | str:
        """The edit for a provable candidate, or the ``human_kind`` it is demoted to."""
        if not c.get("editable", True):
            return "prose-mention"
        line = self.line(c["line"])
        span = line[c["col"] : c["end_col"]] if c["end_col"] <= len(line) else ""
        text = str(c["text"])
        if not span or not (text.endswith(span) if c["kind"] == "tree" else span == text):
            return "recheck-failed"  # the doc no longer holds the token where it was found
        if c["class"] == "provable-replace":
            return self.replace(c, line)
        found = self.delete(c)
        if isinstance(found, _Edit) and self.quoted(found.line_start, found.line_end):
            return "large-deletion"  # ruling R40
        return found

    def replace(self, c: Cand, line: str) -> _Edit | str:
        if (c.get("block") or {}).get("kind") == "heading":
            return "heading-reference"  # R62: the heading's slug is a link target elsewhere
        new = c.get("replacement")
        if not new:
            return "recheck-failed"
        written = str(new)
        if c["context"] in _DESTINATIONS:
            start = c["col"]
            while start > 0 and line[start - 1] not in "(< \t":
                start -= 1
            written = _encode(written, angle=line[start - 1 : start] == "<")
        spans: list[Span] = [(c["col"], c["end_col"], written)]
        link = c.get("link")
        if c["context"] == "link" and link and link.get("text") == c["text"]:
            a = link["col"] + 1
            b = a + len(c["text"])
            if line[a - 1 : a] == "[" and line[a:b] == c["text"] and line[b : b + 1] == "]":
                spans.append((a, b, str(new)))  # the label is text, not a destination
        return _Edit(c["line"], c["line"], "replace", spans, written)

    def delete(self, c: Cand) -> _Edit | str:
        if c["context"] == "refdef":
            return "large-deletion"  # ruling R11: every usage of the definition would break
        if c["context"] == "image":
            return "prose-mention"
        block = c["block"]
        if c.get("subject") and block["kind"] == "list_item":
            return self.list_item(block)
        if c.get("subject") and block["kind"] == "table_row":
            return self.table_row(c["line"])
        if c["context"] == "fence" and c["kind"] in ("script", "path"):
            return self.fence_line(c["line"], block)
        if c["kind"] == "tree":
            return self.tree_line(c, block)
        if c["context"] == "link":
            return self.unlink(c)
        return "prose-mention"

    def list_item(self, block: dict[str, Any]) -> _Edit | str:
        idx = self.find("list_item", block["line_start"], block["line_end"])
        if idx is None:
            return "large-deletion"
        item = self.blocks[idx]
        siblings = [b for b in self.blocks if b.kind == "list_item"
                    and b.list_id == item.list_id and b is not item]
        if item.list_id is None or not siblings:
            return "large-deletion"
        if any(b.parent == idx and b.kind in ("list_item", "refdef") for b in self.blocks):
            return "large-deletion"
        before = [b for b in siblings if b.line_start < item.line_start]
        prev = self.line(item.line_start - 1)
        if not before and prev.strip() and _ORDERED.match(self.line(item.line_start)):
            return "large-deletion"  # a later number cannot interrupt the text above
        end = item.line_end
        after = [b.line_start for b in siblings if b.line_start > item.line_end]
        if after and all(not self.line(n).strip() for n in range(end + 1, min(after))):
            end = min(after) - 1
        return _Edit(item.line_start, end, "delete", unit=("list", item.list_id),
                     total=len(siblings) + 1)

    def table_row(self, line: int) -> _Edit | str:
        idx = self.find("table_row", line, line)
        if idx is None:
            return "large-deletion"
        first = last = idx
        parent = self.blocks[idx].parent
        while first > 0 and self._same_table(self.blocks[first - 1], parent, first):
            first -= 1
        while last + 1 < len(self.blocks) and self._same_table(self.blocks[last + 1], parent,
                                                                last):
            last += 1
        table = self.blocks[first : last + 1]
        if len(table) < 2 or table[1].kind != "table_delim" or idx <= first + 1:
            return "large-deletion"  # the header row is never deleted
        body = [b for b in table[2:] if b.kind == "table_row"]
        if len(body) < 2:
            return "large-deletion"
        return _Edit(line, line, "delete", unit=("table", first), total=len(body))

    def _same_table(self, b: Block, parent: int | None, neighbour: int) -> bool:
        near = self.blocks[neighbour]
        adjacent = b.line_end + 1 == near.line_start or near.line_end + 1 == b.line_start
        return b.kind in _TABLE_KINDS and b.parent == parent and adjacent

    def _fence(self, block: dict[str, Any]) -> tuple[Block, list[int]] | None:
        idx = self.find("fence", block["line_start"], block["line_end"])
        if idx is None:
            return None
        fence = self.blocks[idx]
        last = fence.line_end - 1 if fence.closed else fence.line_end
        return fence, list(range(fence.line_start + 1, last + 1))

    def fence_line(self, line: int, block: dict[str, Any]) -> _Edit | str:
        found = self._fence(block)
        if found is None:
            return "large-deletion"
        fence, body = found
        words = (fence.info or "").split()
        if (words[0].lower() if words else "") not in SHELL_INFOS or line not in body:
            return "large-deletion"
        rows = [self.line(n).strip() for n in body if self.line(n).strip()]
        commands = [r for r in rows if not _PROMPT.sub("", r, count=1).startswith("#")]
        if len(commands) < 2 or not _command_list(rows):
            return "large-deletion"  # a fence left with only comments says nothing
        command = _PROMPT.sub("", self.line(line).strip(), count=1)
        if not command or command.startswith("#") or any(s in command for s in _SEPARATORS):
            return "large-deletion"
        return _Edit(line, line, "delete", unit=("fence", fence.line_start),
                     total=len(commands))

    def tree_line(self, c: Cand, block: dict[str, Any]) -> _Edit | str:
        found = self._fence(block)
        line = c["line"]
        if found is None or line not in found[1]:
            return "large-deletion"
        fence, body = found
        entry = _tree_entry(self.line(line))
        if entry is None or entry[1] != c["col"]:
            return "large-deletion"
        if sum(1 for n in body if self.line(n).strip()) < 2:
            return "large-deletion"
        for n in body[body.index(line) + 1 :]:
            below = _tree_entry(self.line(n))
            if below is None:
                continue  # a blank or rails-only line
            deeper = below[0] > entry[0] or (below[0] == entry[0] and below[2] and not entry[2])
            if deeper:
                return "large-deletion"
            break
        return _Edit(line, line, "delete", unit=("tree", fence.line_start),
                     total=self._tree_entries(body))

    def _tree_entries(self, body: list[int]) -> int:
        """Entries of a tree, less a first root or label line every other entry sits under."""
        entries = [e for n in body if (e := _tree_entry(self.line(n))) is not None]
        if entries and not entries[0][2] and all(
            (e[2] and e[0] >= entries[0][0]) or e[0] > entries[0][0] for e in entries[1:]
        ):
            return len(entries) - 1
        return len(entries)

    def unlink(self, c: Cand) -> _Edit | str:
        link = c.get("link")
        if not link or not link.get("text"):
            return "prose-mention"  # a wrapped link, or an empty label would leave nothing
        line = self.line(c["line"])
        a, e, label = link["col"], link["end_col"], str(link["text"])
        b = a + 1 + len(label)
        if (line[a : a + 1] != "[" or line[a + 1 : b] != label or line[b : b + 1] != "]"
                or line[e - 1 : e] != ")" or not a <= c["col"] < c["end_col"] <= e):
            return "prose-mention"
        return _Edit(c["line"], c["line"], "unlink", [(a, e, label)])


def _command_list(rows: list[str]) -> bool:
    """True when every non-empty fence line is a command on its own (no output, no blocks)."""
    prompted = [bool(_PROMPT.match(r)) for r in rows]
    if any(prompted) and not all(prompted):
        return False  # commands mixed with their output
    for row in rows:
        cmd = _PROMPT.sub("", row, count=1)
        if (cmd.endswith(_CONTINUED) or "<<" in cmd or _COMPOUND.match(cmd)
                or cmd.startswith(("{", "}", "(", ")")) or cmd.endswith(("{", "("))):
            return False
    return True


def _demote(c: Cand, kind: str) -> Cand:
    out = dict(c)
    out.update({"class": "human", "human_kind": kind})
    return out


def _order(c: Cand) -> tuple[Any, ...]:
    return (c["doc"], c["line"], c["col"], c["end_col"], c["kind"])


def _build(edits: list[_Edit | str], excluded: set[int]) -> tuple[list[_Hunk], dict[int, str]]:
    """Hunks from the edits in document order; the overlapping ones demoted."""
    hunks: list[_Hunk] = []
    demoted: dict[int, str] = {}
    for pos, edit in enumerate(edits):
        if isinstance(edit, str) or pos in excluded:
            continue
        hit = [h for h in hunks
               if h.edit.line_start <= edit.line_end and edit.line_start <= h.edit.line_end]
        if not hit:
            hunks.append(_Hunk(pos, edit))
        elif not (len(hit) == 1 and hit[0].merge(pos, edit)):
            demoted[pos] = "large-deletion"
    return hunks, demoted


def _emptied(hunks: list[_Hunk]) -> set[int]:
    """Ruling R39: findings of every delete in a unit whose deletes would remove all of it."""
    members: dict[Unit, set[int]] = defaultdict(set)
    totals: dict[Unit, int] = {}
    for h in hunks:
        if h.edit.unit is not None:
            members[h.edit.unit].add(h.edit.line_start)
            totals[h.edit.unit] = h.edit.total
    full = {u for u, lines in members.items() if len(lines) >= totals[u]}
    return {p for h in hunks if h.edit.unit in full for p in [h.pos, *(a.pos for a in h.also)]}


def plan_hunks(doc_text: str, candidates: list[Cand]) -> tuple[list[Cand], list[Cand]]:
    """Hunks for the provable candidates of one doc, and the candidates demoted to human.

    Hunks are numbered ``H001``... in document order; ``run`` renumbers them across docs.
    """
    doc = _Doc(doc_text)
    cands = sorted((c for c in candidates if c.get("class") in PROVABLE), key=_order)
    edits = [doc.edit(c) for c in cands]
    excluded: set[int] = set()
    while True:  # each round can only exclude more, so this ends
        hunks, demoted = _build(edits, excluded)
        emptied = _emptied(hunks)
        if not emptied:
            break
        excluded |= emptied
    demoted.update(dict.fromkeys(excluded, "large-deletion"))
    for pos, edit in enumerate(edits):
        if not isinstance(edit, str):
            continue
        line = cands[pos]["line"]
        home = next((h for h in hunks if h.edit.verb == "delete"
                     and h.edit.line_start <= line <= h.edit.line_end), None)
        if home is not None and edit != "recheck-failed":
            home.also.append(_Also(pos, "delete", None))  # the lines take it along
        else:
            demoted[pos] = edit
    out = [_hunk_record(doc, h, n, cands) for n, h in enumerate(hunks, 1)]
    return out, [_demote(cands[pos], demoted[pos]) for pos in sorted(demoted)]


def _hunk_record(doc: _Doc, h: _Hunk, n: int, cands: list[Cand]) -> Cand:
    e, c = h.edit, cands[h.pos]
    before = [doc.line(no) for no in range(e.line_start, e.line_end + 1)]
    after: list[str] = []
    if e.verb != "delete":
        text = before[0]
        for a, b, new in sorted(e.spans, reverse=True):
            text = text[:a] + new + text[b:]
        after = [text]
    also = [{"finding_id": cands[a.pos].get("id"), "verb": a.verb,
             "token_text": cands[a.pos]["text"], "new_text": a.new_text,
             "reason": cands[a.pos].get("evidence", "")}
            for a in sorted(h.also, key=lambda a: a.pos)]
    return {
        "id": f"H{n:03d}", "finding_id": c.get("id"), "doc": c["doc"],
        "line_start": e.line_start, "line_end": e.line_end, "before": before, "after": after,
        "verb": e.verb, "token_kind": c["kind"], "token_text": c["text"],
        "new_text": e.new_text if e.verb == "replace" else None,
        "reason": c.get("evidence", ""), "also": also,
    }


def _check_reasons(hunk: Cand) -> None:
    """Ruling R64: every provable edit names the commit (or the manifest) that proves it."""
    for reason in [hunk.get("reason"), *(a.get("reason") for a in hunk.get("also") or [])]:
        text = str(reason or "")
        if not (_PROOF.search(text) or text.startswith("manifest ")):
            raise StepError(f"hunk {hunk['id']} in {hunk['doc']} has no proving commit or "
                            f"manifest in its reason {text!r}", EXIT_MISSING)


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Number every candidate and plan the provable hunks; write both outputs.

    Returns ``{"findings": <findings.json content>, "hunks": [Hunk...]}``.
    """
    path = workdir / "candidates.json"
    if not path.is_file():
        raise StepError(f"missing {path}; run dd_resolve first", EXIT_MISSING)
    data = read_json(path)
    findings: list[Cand] = []
    for n, c in enumerate(sorted(data["candidates"], key=_order), 1):
        findings.append(dict(c, id=f"F{n:03d}"))
    by_id = {f["id"]: k for k, f in enumerate(findings)}
    hunks: list[Cand] = []
    for doc in sorted({f["doc"] for f in findings if f.get("class") in PROVABLE}):
        mine = [f for f in findings if f["doc"] == doc]
        try:
            with (root / doc).open(encoding="utf-8", newline="") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            doc_hunks: list[Cand] = []
            demoted = [_demote(f, "recheck-failed") for f in mine if f.get("class") in PROVABLE]
        else:
            doc_hunks, demoted = plan_hunks(text, mine)
        for d in demoted:
            findings[by_id[d["id"]]] = d
        hunks.extend(doc_hunks)
    for n, h in enumerate(hunks, 1):
        h["id"] = f"H{n:03d}"
        _check_reasons(h)
    findings_doc = {
        "findings": findings,
        "history_unavailable": bool(data.get("history_unavailable", False)),
        "honoured": data.get("honoured", []),
    }
    write_json(workdir / "findings.json", findings_doc)
    write_json(workdir / "hunks-provable.json", {"hunks": hunks})
    return {"findings": findings_doc, "hunks": hunks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Number findings and plan provable hunks.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run(args.repo, args.workdir)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
