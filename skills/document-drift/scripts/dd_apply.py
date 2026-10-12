"""Apply the accepted agent edits with a re-scan, revert any doubt -> applied.json (spec 9.3).

``apply_edits`` applies every ``edits.json`` edit whose status is ``kept`` and whose
``verdicts.json`` verdict is ``accept``, plus every kept notice-loop edit (``source ==
"notice"``, no verdict needed); a missing ``verdicts.json`` means no verdicts.

Per doc (spec 7.3): the doc is read with ``newline=""`` and split on ``\\r\\n`` or ``\\n`` like
the scanner (``_Text``); each line keeps its own ending, a new line takes the majority ending,
and the trailing-newline state is kept. Edits apply bottom-up by ``(start_line, end_line)``: an
edit applies when lines ``start_line..end_line`` (endings stripped, joined by ``\\n``) equal
``old``, else it reverts with ``old-mismatch``; ``new == ""`` removes the lines, otherwise
``new.split("\\n")`` (each line's trailing ``\\r`` dropped) replaces them. After each edit the
doc text is re-extracted in memory and resolved against HEAD (the tracked files of
``inventory.json``, ``_Checker``; a doc already edited in this run is read as edited): the
multiset of unresolved ``(kind, text)`` for kinds ``path`` and ``anchor`` (a marker-ignored
token never counts) must be a subset of the multiset before the edit, otherwise the edit
reverts with ``recheck-failed``. Both multisets are taken on the text with the heading-link
rewrites known so far applied (the renames of earlier docs and of this doc's applied edits,
including the edit under test), so a heading edit is not reverted for the links that
``update_heading_links`` rewrites in the same run. ``update_heading_links`` then rewrites the
links to renamed headings in the in-memory texts (a link names a slug as the resolver reads
it: percent-decoded, ``user-content-`` dropped, case-insensitive), and every changed doc is
written once, atomically (``<doc>.dd-tmp`` then ``os.replace``); a failed write reverts that
doc's edits with ``write-failed`` and drops its link updates. One edit's failure reverts only
that edit. ``applied.json`` is ``{"applied": [ids], "reverted": [{"edit", "reason"}], "docs":
[written docs], "link_updates": [{"doc", "line", "old", "new", "edit"}]}``, all sorted. Line
numbers are always those of the original, pre-apply doc.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import stat
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_extract import extract_doc
from dd_md_scan import scan
from dd_resolve import _fragment, _match_slug, _plain, resolve_token, slugify_heading

WRITE_FAILED = "write-failed"
OLD_MISMATCH = "old-mismatch"
RECHECK_FAILED = "recheck-failed"
RECHECKED_KINDS = frozenset({"path", "anchor"})
_SPLIT = re.compile(r"(\r?\n)")

Line = tuple[str, str]  # (content, ending); ending is "" only on a last line without newline
Key = tuple[str, str]  # (kind, text)


class _Text:
    """A doc as lines with their own endings, the majority ending and the trailing state."""

    def __init__(self, text: str) -> None:
        parts = _SPLIT.split(text)
        contents, endings = parts[0::2], [*parts[1::2], ""]
        if len(contents) > 1 and contents[-1] == "":
            contents, endings = contents[:-1], endings[:-1]
        elif contents == [""]:
            contents, endings = [], []
        self.lines: list[Line] = list(zip(contents, endings, strict=True))
        crlf = sum(1 for e in endings if e == "\r\n")
        self.ending = "\r\n" if crlf > sum(1 for e in endings if e == "\n") else "\n"
        self.trailing = text.endswith("\n")

    def contents(self, start: int, end: int) -> list[str]:
        return [c for c, _ in self.lines[start - 1 : end]]

    def replaced(self, start: int, end: int, after: list[str]) -> list[Line]:
        """The lines with ``start..end`` replaced by ``after`` (endings kept per position)."""
        old = self.lines[start - 1 : end]
        new = [(a, old[i][1] if i < len(old) and old[i][1] else self.ending)
               for i, a in enumerate(after)]
        lines = [*self.lines[: start - 1], *new, *self.lines[end:]]
        if lines:
            last, ending = lines[-1]
            lines[-1] = (last, (ending or self.ending) if self.trailing else "")
        return lines

    @staticmethod
    def join(lines: list[Line]) -> str:
        return "".join(c + e for c, e in lines)


class _Checker:
    """Unresolved-token multisets of a doc's text, resolved against HEAD."""

    def __init__(self, root: Path, files: list[str], never_edit_re: re.Pattern[str]) -> None:
        self.root = root
        self.files = frozenset(files)
        dirs: set[str] = set()
        for path in self.files:
            parts = path.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        self.dirs = frozenset(dirs)
        self.never = never_edit_re
        self.settled: dict[str, str] = {}  # docs already edited in this run
        self._cache: dict[str, str | None] = {}

    def _disk(self, path: str) -> str | None:
        if path not in self._cache:
            try:
                with (self.root / path).open(encoding="utf-8", newline="") as fh:
                    self._cache[path] = fh.read()
            except (OSError, UnicodeDecodeError, ValueError):
                self._cache[path] = None
        return self._cache[path]

    def tokens(self, doc: str, text: str) -> list[tuple[dict[str, Any], str | None]]:
        """Every token of ``text`` with what it resolves to at HEAD (or None)."""

        def read(path: str) -> str | None:
            if path == doc:
                return text
            return self.settled[path] if path in self.settled else self._disk(path)

        found, _ = extract_doc(doc, text, self.never)
        return [(t, resolve_token(t, self.files, self.dirs, read)) for t in found]

    @staticmethod
    def unresolved(tokens: list[tuple[dict[str, Any], str | None]]) -> Counter[Key]:
        """Unresolved ``(kind, text)``; a marker-ignored token never counts."""
        return Counter((t["kind"], t["text"]) for t, r in tokens
                       if r is None and not t.get("ignored"))


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".dd-tmp")
    try:
        tmp.write_bytes(text.encode("utf-8"))
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except OSError:
        with contextlib.suppress(OSError):
            if tmp.is_file():  # never a directory the user happens to have at that name
                os.chmod(tmp, stat.S_IREAD | stat.S_IWRITE)  # copymode may have made it read-only
                tmp.unlink()
        raise


# -- agent edits (spec 9.3) --------------------------------------------------------------------

Renames = dict[str, dict[str, str | None]]  # target doc -> {old slug: new slug, None: left}
Heading = tuple[int, str, bool]  # (line, slug as linked, its base slug repeats in the doc)
# (line, target doc, renamed slug, link text as written, its rewrite or None)
Found = tuple[int, str, str, str, str | None]


def _read_doc(root: Path, doc: str) -> str | None:
    try:
        with (root / doc).open(encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def _headings(text: str) -> list[Heading]:
    """Every heading of ``text`` in order: its line, its slug (``-N`` for repeats, numbered as
    ``dd_resolve.heading_slugs`` numbers them) and whether its base slug repeats in the doc."""
    blocks = sorted((b for b in scan(text).blocks if b.kind == "heading"),
                    key=lambda b: b.line_start)
    bases = [slugify_heading(_plain(b.text or "")) for b in blocks]
    counts = Counter(bases)
    seen: Counter[str] = Counter()
    out: list[Heading] = []
    for block, base in zip(blocks, bases, strict=True):
        n = seen[base]
        seen[base] += 1
        out.append((block.line_start, base if n == 0 else f"{base}-{n}", counts[base] > 1))
    return out


def _heading_changes(before: str, start: int, end: int, after: str, new_start: int,
                     count: int) -> list[tuple[str, str | None]]:
    """``(old slug, new slug)`` per heading of ``before``'s lines ``start..end`` whose
    counterpart (same position) among ``after``'s lines ``new_start..new_start + count - 1``
    has another slug. The new slug is None when either heading's base slug repeats in its doc
    (the ``-N`` suffixes are left to the owner). Nothing when the edit adds or drops a heading.
    """
    old = [h for h in _headings(before) if start <= h[0] <= end]
    new = [h for h in _headings(after) if new_start <= h[0] < new_start + count]
    if len(old) != len(new):
        return []
    return [(o_slug, None if o_dup or n_dup else n_slug)
            for (_, o_slug, o_dup), (_, n_slug, n_dup) in zip(old, new, strict=True)
            if o_slug != n_slug]


def _rewrite_links(doc: str, text: str, tokens: list[dict[str, Any]],
                   renames: Renames) -> tuple[str, list[Found]]:
    """``text`` with every anchor token that names a renamed heading rewritten to the new slug,
    and a ``Found`` per such token. A token names a slug as the resolver reads it
    (``dd_resolve._match_slug`` of ``_fragment``: percent-decoded, ``user-content-`` dropped,
    case-insensitive fallback); the rewrite is the new slug, keeping a ``user-content-`` prefix.
    The rewrite is None, and the token kept, when the rename is left to the owner or the token
    cannot be rewritten in place (never-edit, generated or marker-ignored, spanning lines, or
    its span not holding its text)."""
    cur = _Text(text)
    found: list[Found] = []
    for tok in sorted(tokens, key=lambda t: (t["line"], t["col"]), reverse=True):
        target = tok.get("target_doc") or doc
        if tok["kind"] != "anchor" or target not in renames:
            continue
        slug = _match_slug(_fragment(tok["text"]), set(renames[target]))
        if slug is None:
            continue
        new_slug = renames[target][slug]
        prefix = "user-content-" if _fragment(tok["text"]) != unquote(tok["text"]) else ""
        new = None if new_slug is None else prefix + new_slug
        line, col, end = int(tok["line"]), int(tok["col"]), int(tok["end_col"])
        content, ending = cur.lines[line - 1] if 1 <= line <= len(cur.lines) else ("", "")
        if (tok.get("never_edit") or tok.get("generated") or tok.get("ignored")
                or not tok.get("editable", True) or content[col:end] != tok["text"]):
            new = None
        if new is not None:
            cur.lines[line - 1] = (content[:col] + new + content[end:], ending)
        found.append((line, target, slug, tok["text"], new))
    found.sort(key=lambda f: (f[0], f[1], f[3]))
    if all(f[4] is None for f in found):
        return text, found
    return _Text.join(cur.lines), found


def _unresolved(checker: _Checker, doc: str, text: str, renames: Renames) -> Counter[Key]:
    """Unresolved ``(kind, text)`` path and anchor tokens of ``text`` once the heading-link
    rewrites of ``renames`` are applied to it."""
    tokens = checker.tokens(doc, text)
    projected, _ = _rewrite_links(doc, text, [t for t, _ in tokens], renames)
    if projected != text:
        tokens = checker.tokens(doc, projected)
    return Counter({key: n for key, n in _Checker.unresolved(tokens).items()
                    if key[0] in RECHECKED_KINDS})


def _settle_doc(doc: str, original: str, edits: list[dict[str, Any]], checker: _Checker,
                renames: Renames) -> tuple[str, list[str], dict[str, str]]:
    """Apply one doc's edits bottom-up with the spec 9.3 re-scan; return (edited text, applied
    ids, {reverted id: reason}). ``renames`` gains this doc's applied heading renames."""
    cur = _Text(original)
    text = original
    prev = _unresolved(checker, doc, text, renames)
    applied: list[str] = []
    reverted: dict[str, str] = {}
    for edit in sorted(edits, key=lambda e: (int(e["start_line"]), int(e["end_line"])),
                       reverse=True):
        start, end = int(edit["start_line"]), int(edit["end_line"])
        if (not 1 <= start <= end <= len(cur.lines)
                or "\n".join(cur.contents(start, end)) != edit["old"]):
            reverted[edit["id"]] = OLD_MISMATCH
            continue
        # a "\r\n" inside an agent's ``new`` must not leave a stray "\r" before the line ending
        after = [a.removesuffix("\r") for a in edit["new"].split("\n")] if edit["new"] else []
        lines = cur.replaced(start, end, after)
        new_text = _Text.join(lines)
        own = dict(renames.get(doc, {}))
        own.update(_heading_changes(text, start, end, new_text, start, len(after)))
        now = _unresolved(checker, doc, new_text, {**renames, doc: own})
        if now - prev:
            reverted[edit["id"]] = RECHECK_FAILED
            continue
        cur.lines, text, prev = lines, new_text, now
        renames[doc] = own
        applied.append(edit["id"])
    return text, applied, reverted


def _head_line(line: int, spans: list[tuple[int, int, int]]) -> int:
    """The line at the starting HEAD of ``line`` in the edited text; ``spans`` are the applied
    edits' ``(start_line, end_line, new line count)``, ascending. A line inside an edit's new
    lines maps to that edit's ``start_line``."""
    offset = 0
    for start, end, count in spans:
        first = start + offset
        if line < first:
            break
        if line < first + count:
            return start
        offset += count - (end - start + 1)
    return line - offset


def update_heading_links(root: Path, workdir: Path, applied_edits: Iterable[str],
                         texts: dict[str, str]) -> list[dict[str, Any]]:
    """Rewrite, in ``texts``, the links to headings that the applied edits renamed (spec 9.3).

    ``texts`` maps each edited doc to its edited, not yet written text; a doc's pre-apply text
    is read from disk, so this runs before the edited docs are written (``apply_edits`` then
    writes every doc of ``texts`` once, atomically). For each applied edit (``edits.json``
    records) whose range held a heading whose counterpart in ``new`` has another slug
    (``slugify_heading`` of the heading text), every anchor token of an in-scope doc
    (``inventory.json``'s docs) that targets the edited doc with the old slug as its text is
    rewritten to the new slug. An edited doc's tokens are re-extracted from its text; any other
    doc's come from ``tokens.json``. A doc changed only for links is added to ``texts``.
    Returns ``{"doc", "line", "old", "new", "edit"}`` per such token, sorted by doc and line
    (``line`` is the line at the starting HEAD, mapped back through the applied edits);
    ``new`` is None, and the link left as it is, for a repeated heading (``-N`` suffixes are
    left to the owner) or a token that cannot be rewritten in place.
    """
    ids = set(applied_edits)
    edits = [e for e in read_json(workdir / "edits.json")["edits"] if e["id"] in ids]
    renames: Renames = {}
    owner: dict[tuple[str, str], str] = {}
    spans: dict[str, list[tuple[int, int, int]]] = {}
    for doc in sorted({e["doc"] for e in edits}):
        original, final = _read_doc(root, doc), texts.get(doc)
        if original is None or final is None:
            continue
        offset = 0  # line shift from the applied edits above, in the final text
        for edit in sorted((e for e in edits if e["doc"] == doc),
                           key=lambda e: int(e["start_line"])):
            start, end = int(edit["start_line"]), int(edit["end_line"])
            count = len(edit["new"].split("\n")) if edit["new"] else 0
            for old, new in _heading_changes(original, start, end, final, start + offset,
                                             count):
                renames.setdefault(doc, {})[old] = new
                owner[(doc, old)] = edit["id"]
            offset += count - (end - start + 1)
            spans.setdefault(doc, []).append((start, end, count))
    if not renames:
        return []
    inventory = read_json(workdir / "inventory.json")
    never = re.compile(inventory["never_edit_re"])
    stored: dict[str, list[dict[str, Any]]] = read_json(workdir / "tokens.json")["docs"]
    updates: list[dict[str, Any]] = []
    for doc in sorted(set(inventory["docs"]) | set(texts)):
        text: str | None
        if doc in texts:
            text = texts[doc]
            tokens = extract_doc(doc, text, never)[0]
        else:
            tokens = stored.get(doc) or []
            if not any(t["kind"] == "anchor" and (t.get("target_doc") or doc) in renames
                       for t in tokens):
                continue
            text = _read_doc(root, doc)
            if text is None:
                continue
        new_text, found = _rewrite_links(doc, text, tokens, renames)
        updates.extend({"doc": doc, "line": _head_line(line, spans.get(doc, [])), "old": old,
                        "new": new, "edit": owner[(target, slug)]}
                       for line, target, slug, old, new in found)
        if new_text != text:
            texts[doc] = new_text
    return updates


def selected_edits(edits: Iterable[Mapping[str, Any]],
                   verdicts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The edits a run applies: kept and accepted by their verdict, or kept notice-loop edits
    (no verdict needed). ``verdicts`` is ``verdicts.json``'s ``verdicts`` mapping."""
    accepted = {eid for eid, v in verdicts.items() if v.get("verdict") == "accept"}
    return [dict(e) for e in edits
            if e.get("status") == "kept" and (e.get("source") == "notice" or e["id"] in accepted)]


def apply_edits(root: Path, workdir: Path) -> dict[str, Any]:
    """Apply the accepted agent edits and the kept notice edits; write ``applied.json``."""
    for name in ("inventory.json", "tokens.json", "edits.json"):
        if not (workdir / name).is_file():
            raise StepError(f"missing {workdir / name}; run the earlier steps first", EXIT_MISSING)
    inventory = read_json(workdir / "inventory.json")
    verdicts_path = workdir / "verdicts.json"
    verdicts = read_json(verdicts_path)["verdicts"] if verdicts_path.is_file() else {}
    edits = selected_edits(read_json(workdir / "edits.json")["edits"], verdicts)
    checker = _Checker(root, inventory.get("files", []), re.compile(inventory["never_edit_re"]))
    renames: Renames = {}
    texts: dict[str, str] = {}
    applied: dict[str, str] = {}  # edit id -> doc
    reverted: dict[str, str] = {}
    for doc in sorted({e["doc"] for e in edits}):
        mine = [e for e in edits if e["doc"] == doc]
        original = _read_doc(root, doc)
        if original is None:
            reverted.update({e["id"]: OLD_MISMATCH for e in mine})
            continue
        text, done, undone = _settle_doc(doc, original, mine, checker, renames)
        reverted.update(undone)
        if done:
            applied.update({eid: doc for eid in done})
            texts[doc] = text
            checker.settled[doc] = text
    link_updates = update_heading_links(root, workdir, list(applied), texts)
    docs: list[str] = []
    for doc in sorted(texts):
        try:
            _write_atomic(root / doc, texts[doc])
        except OSError:
            for eid in [i for i, d in applied.items() if d == doc]:
                del applied[eid]
                reverted[eid] = WRITE_FAILED
            link_updates = [u for u in link_updates if u["doc"] != doc]
            continue
        docs.append(doc)
    result = {
        "applied": sorted(applied),
        "reverted": [{"edit": eid, "reason": reverted[eid]} for eid in sorted(reverted)],
        "docs": docs,
        "link_updates": sorted(link_updates, key=lambda u: (u["doc"], u["line"], u["old"])),
    }
    write_json(workdir / "applied.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply the accepted edits of edits.json with the re-scan (spec 9.3).")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        apply_edits(args.repo, args.workdir)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
