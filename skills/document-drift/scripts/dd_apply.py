"""Apply provable hunks, re-check each one, revert any doubt -> applied.json.

``applied.json`` is ``{"applied": [hunk ids], "reverted": [{"hunk", "reason"}], "docs":
[edited doc paths]}``, all sorted. ``findings.json`` is rewritten in place: every finding of a
reverted hunk (its ``finding_id`` and every ``also`` id) becomes ``human``/``recheck-failed``
with ``recheck_reason`` set to the revert reason, and every ``human`` or ``summary-only`` finding
whose line lies inside an applied ``delete`` hunk gets ``superseded_by: <hunk id>`` (ruling
R43). Every other field and the top-level keys pass through unchanged. Line numbers are always
those of the original, pre-apply doc.

Per doc (spec 7.3): the doc is read with ``newline=""`` and split on ``\\r\\n`` or ``\\n`` like
the scanner; each line keeps its own ending, a new line takes the majority ending, and the
trailing-newline state is kept. Hunks apply bottom-up by ``line_start``. A hunk whose ``before``
lines differ from the current lines reverts (``before-mismatch``). After a hunk is applied the
edited text is re-extracted in memory and every token resolved against HEAD (the tracked files
of ``inventory.json``): the multiset of unresolved ``(kind, text)`` (a marker-ignored token
never counts) must be a subset of the previous multiset minus the hunk's own findings (ruling
R38: the ``also`` findings are its own too), and every replacement must itself resolve;
otherwise the hunk is undone with ``recheck-still-unresolved`` (an own token still fires or a
replacement does not resolve) or ``recheck-new-finding``. One hunk's failure reverts only that
hunk. The doc is written once, atomically (``<doc>.dd-tmp`` then ``os.replace``), when at least
one hunk stayed applied; a failed write reverts its hunks with ``write-failed``.
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
from pathlib import Path
from typing import Any

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_extract import extract_doc
from dd_resolve import resolve_token

BEFORE_MISMATCH = "before-mismatch"
NEW_FINDING = "recheck-new-finding"
STILL_UNRESOLVED = "recheck-still-unresolved"
WRITE_FAILED = "write-failed"
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


def _own(hunk: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Finding ids of a hunk: its ``finding_id`` and every ``also`` id (ruling R38)."""
    ids = [hunk.get("finding_id"), *(a.get("finding_id") for a in hunk.get("also") or [])]
    return [i for i in ids if isinstance(i, str) and i in by_id]


def _own_keys(hunk: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> Counter[Key]:
    keys: Counter[Key] = Counter()
    keys[(hunk["token_kind"], hunk["token_text"])] += 1
    for also in hunk.get("also") or []:
        f = by_id.get(also.get("finding_id") or "")
        kind = f["kind"] if f else hunk["token_kind"]
        keys[(kind, also["token_text"])] += 1
    return keys


def _replacements(hunk: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[Key]:
    """``(kind, new text)`` of every replacement the hunk writes."""
    out: list[Key] = []
    if hunk.get("verb") == "replace" and hunk.get("new_text"):
        out.append((hunk["token_kind"], hunk["new_text"]))
    for also in hunk.get("also") or []:
        if also.get("verb") == "replace" and also.get("new_text"):
            f = by_id.get(also.get("finding_id") or "")
            out.append((f["kind"] if f else hunk["token_kind"], also["new_text"]))
    return out


def _names(token: dict[str, Any], key: Key) -> bool:
    kind, new = key
    text = str(token["text"])
    return token["kind"] == kind and (text == new or kind == "tree" and text.endswith("/" + new))


def _verdict(hunk: dict[str, Any], by_id: dict[str, dict[str, Any]], prev: Counter[Key],
             tokens: list[tuple[dict[str, Any], str | None]]) -> str | None:
    """None when the edited text passes the re-check, else the revert reason."""
    own = _own_keys(hunk, by_id)
    excess = _Checker.unresolved(tokens) - (prev - own)
    if any(key in own for key in excess):
        return STILL_UNRESOLVED
    first = hunk["line_start"]
    last = first + len(hunk["after"]) - 1
    for key in _replacements(hunk, by_id):
        mine = [r for t, r in tokens if first <= t["line"] <= last and _names(t, key)]
        if not mine or any(r is None for r in mine):
            return STILL_UNRESOLVED
    return NEW_FINDING if excess else None


def _apply_doc(root: Path, doc: str, hunks: list[dict[str, Any]], checker: _Checker,
               by_id: dict[str, dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    """Settle one doc's hunks; return (applied ids, {reverted id: reason})."""
    reverted: dict[str, str] = {}
    try:
        with (root / doc).open(encoding="utf-8", newline="") as fh:
            original = fh.read()
    except (OSError, UnicodeDecodeError, ValueError):
        return [], {h["id"]: BEFORE_MISMATCH for h in hunks}
    cur = _Text(original)
    prev = _Checker.unresolved(checker.tokens(doc, original))
    applied: list[str] = []
    for hunk in sorted(hunks, key=lambda h: (h["line_start"], h["line_end"]), reverse=True):
        start, end = hunk["line_start"], hunk["line_end"]
        if not 1 <= start <= end or cur.contents(start, end) != list(hunk["before"]):
            reverted[hunk["id"]] = BEFORE_MISMATCH
            continue
        lines = cur.replaced(start, end, list(hunk["after"]))
        text = _Text.join(lines)
        tokens = checker.tokens(doc, text)
        reason = _verdict(hunk, by_id, prev, tokens)
        if reason is not None:
            reverted[hunk["id"]] = reason
            continue
        cur.lines = lines
        prev = _Checker.unresolved(tokens)
        applied.append(hunk["id"])
    if applied:
        text = _Text.join(cur.lines)
        try:
            _write_atomic(root / doc, text)
        except OSError:
            reverted.update({hid: WRITE_FAILED for hid in applied})
            return [], reverted
        checker.settled[doc] = text
    return applied, reverted


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


def _settle_findings(findings: list[dict[str, Any]], hunks: list[dict[str, Any]],
                     applied: set[str], reverted: dict[str, str],
                     by_id: dict[str, dict[str, Any]]) -> None:
    for hunk in hunks:
        reason = reverted.get(hunk["id"])
        if reason is None:
            continue
        for fid in _own(hunk, by_id):
            by_id[fid].update({"class": "human", "human_kind": "recheck-failed",
                               "recheck_reason": reason})
    deletes = [h for h in hunks if h["id"] in applied and h["verb"] == "delete"]
    for f in findings:
        f.pop("superseded_by", None)
        if f.get("class") not in ("human", "summary-only"):
            continue
        for h in deletes:
            if h["doc"] == f.get("doc") and h["line_start"] <= f.get("line", 0) <= h["line_end"]:
                f["superseded_by"] = h["id"]
                break


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Apply every provable hunk with its re-check; write ``applied.json``, update findings."""
    for name in ("inventory.json", "findings.json", "hunks-provable.json"):
        if not (workdir / name).is_file():
            raise StepError(f"missing {workdir / name}; run the earlier steps first", EXIT_MISSING)
    inventory = read_json(workdir / "inventory.json")
    findings_doc = read_json(workdir / "findings.json")
    hunks: list[dict[str, Any]] = read_json(workdir / "hunks-provable.json")["hunks"]
    findings: list[dict[str, Any]] = findings_doc["findings"]
    by_id = {f["id"]: f for f in findings if isinstance(f.get("id"), str)}
    checker = _Checker(root, inventory.get("files", []), re.compile(inventory["never_edit_re"]))
    applied: list[str] = []
    reverted: dict[str, str] = {}
    docs: list[str] = []
    for doc in sorted({h["doc"] for h in hunks}):
        done, undone = _apply_doc(root, doc, [h for h in hunks if h["doc"] == doc], checker,
                                  by_id)
        applied.extend(done)
        reverted.update(undone)
        if done:
            docs.append(doc)
    _settle_findings(findings, hunks, set(applied), reverted, by_id)
    write_json(workdir / "findings.json", findings_doc)
    result = {
        "applied": sorted(applied),
        "reverted": [{"hunk": hid, "reason": reverted[hid]} for hid in sorted(reverted)],
        "docs": sorted(docs),
    }
    write_json(workdir / "applied.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply provable hunks with re-check.")
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
