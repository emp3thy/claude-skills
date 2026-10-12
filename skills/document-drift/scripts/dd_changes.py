"""Run mode, change set and affected docs -> changes.json (spec 6.1 to 6.3).

``changes.json`` is ``{"mode", "last_run", "last_run_source", "scope", "changed_files",
"hunks", "affected", "review"}``:

- **Last run** (``last_run``): ``--full`` makes a first run (scope ``full``); ``--base <ref>``
  makes a later run from that commit (source ``base``, scope ``base <ref>``) and refuses an
  unknown ref. Otherwise two records compete: the newest ``Drift-Base:`` commit on HEAD whose
  sha is an ancestor of HEAD (source ``commit``; an older one is taken when a newer one names
  a sha off HEAD's history, which only widens the change set), and ``last-run.json``'s
  ``head`` when it is an ancestor of HEAD (source ``record``). When both qualify the
  descendant wins; when neither descends from the other the ``Drift-Base`` sha wins, since
  that commit is shared history and the record is one machine's. Neither gives a first run
  (scope ``first``); a later run's scope is ``since <sha>``. Every sha is the full 40 hex.
- **Change set** (later run): ``changed_files`` is every path differing between the last-run
  commit and HEAD; ``hunks`` the ``git diff -U0`` hunks of the indexed files among them.
- **Affected docs** (``affected``): per doc, ``anchor_reasons`` (an anchor whose change range
  overlaps a hunk of its file; a pure deletion touches its ``new_start``), ``missing`` (a
  reference that resolved against the definition index at the last-run commit and does not
  now, as ``{"ref", "line", "file", "start", "end", "reading"}`` of the definition it had
  then), ``doc_changed`` and ``sections`` (the doc's heading sections that a hunk of the doc
  itself touches). The index at the last-run commit is the current index with the changed
  indexed files (deleted ones included) re-read at that commit.
- **Review** (``review_ranges``): on a first run every in-scope doc whole; on a later run each
  affected doc's reference blocks and changed sections, merged.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dd_anchors import Anchor, Reference, resolve
from dd_common import (
    EXIT_MISSING,
    EXIT_OK,
    EXIT_REFUSED,
    StepError,
    read_json,
    run_git,
    write_json,
)
from dd_config import load_config
from dd_defindex import Definition, at_commit, by_norm, norm
from dd_history import History, Hunk, changed_files, diff_hunks, drift_base_commits, is_ancestor
from dd_inventory import indexed_files, is_project_file, source_class
from dd_md_scan import scan

_Range = tuple[int, int]
_NOTHING: frozenset[str] = frozenset()


def _commit_sha(root: Path, ref: str) -> str | None:
    """The full sha of the commit ``ref`` names, or None."""
    out = run_git(root, ["rev-parse", "--verify", "--quiet", "--end-of-options",
                         f"{ref}^{{commit}}"])
    sha = (out or "").strip()
    return sha or None


def _record_head(workdir: Path) -> str | None:
    path = workdir / "last-run.json"
    if not path.is_file():
        return None
    try:
        record = read_json(path)
    except (OSError, ValueError):
        return None
    head = record.get("head") if isinstance(record, dict) else None
    return head if isinstance(head, str) and head else None


def last_run(root: Path, workdir: Path, base: str | None, full: bool,
             head: str = "HEAD") -> dict[str, Any]:
    """``{"mode", "sha", "source", "scope"}`` for this run (spec 6.1)."""
    if full:
        return {"mode": "first", "sha": None, "source": None, "scope": "full"}
    if base is not None:
        sha = _commit_sha(root, base)
        if sha is None:
            raise StepError(f"--base {base} is not a commit in this repository", EXIT_REFUSED)
        return {"mode": "later", "sha": sha, "source": "base", "scope": f"base {base}"}
    from_commit = None
    for _, named in drift_base_commits(root):
        sha = _commit_sha(root, named)
        if sha is not None and is_ancestor(root, sha, head):
            from_commit = sha
            break
    from_record = None
    recorded = _record_head(workdir)
    if recorded is not None:
        sha = _commit_sha(root, recorded)
        if sha is not None and is_ancestor(root, sha, head):
            from_record = sha
    if from_commit is not None and from_record is not None:
        newer_record = from_record != from_commit and is_ancestor(root, from_commit,
                                                                  from_record)
        chosen, source = (from_record, "record") if newer_record else (from_commit, "commit")
    elif from_commit is not None:
        chosen, source = from_commit, "commit"
    elif from_record is not None:
        chosen, source = from_record, "record"
    else:
        return {"mode": "first", "sha": None, "source": None, "scope": "first"}
    return {"mode": "later", "sha": chosen, "source": source, "scope": f"since {chosen}"}


def _touched(hunk: Hunk) -> _Range:
    """The new-side lines a hunk touches; a pure deletion touches ``new_start``."""
    start = max(hunk["new_start"], 1)
    return start, max(hunk["new_end"], start)


def _overlaps(a: _Range, b: _Range) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def changed_sections(text: str, hunks: Iterable[Hunk]) -> list[list[int]]:
    """The heading sections of ``text`` that ``hunks`` touch, sorted. A section runs from a
    top-level heading to the line before the next heading of the same or higher level; the
    lines before the first heading are a section, and a doc without headings is one section.
    A touched line belongs to the innermost section holding it."""
    count = len(text.splitlines())
    if count == 0:
        return []
    heads = [b for b in scan(text).blocks
             if b.kind == "heading" and b.parent is None and b.line_start <= count]
    # (segment start, segment end, its section): a segment runs to the next heading of any
    # level, so the section it belongs to is the innermost one holding its lines
    segments: list[tuple[int, int, _Range]] = []
    if not heads or heads[0].line_start > 1:
        end = heads[0].line_start - 1 if heads else count
        segments.append((1, end, (1, end)))
    for i, head in enumerate(heads):
        level = head.level or 1
        later = heads[i + 1:]
        segment_end = later[0].line_start - 1 if later else count
        section_end = next((h.line_start - 1 for h in later if (h.level or 1) <= level), count)
        segments.append((head.line_start, segment_end, (head.line_start, section_end)))
    found: set[_Range] = set()
    for hunk in hunks:
        start, end = _touched(hunk)
        touched = (min(start, count), min(end, count))
        found.update(section for s, e, section in segments if _overlaps((s, e), touched))
    return [list(section) for section in sorted(found)]


def affected(anchors: Iterable[Anchor], refs: Iterable[Reference],
             defs_then: Mapping[str, list[Definition]], hunks: Mapping[str, list[Hunk]],
             changed_docs: set[str], texts: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """The affected docs, in path order, each ``{"anchor_reasons", "missing", "doc_changed",
    "sections"}`` (spec 6.3). ``refs`` are the references that are not existing paths now
    (anchored or unanchored at HEAD): one of them that anchors against ``defs_then`` and has
    no anchor now is missing. ``hunks`` hold the changed docs' own hunks as well as code's."""
    anchors = list(anchors)
    entries: dict[str, dict[str, Any]] = {}

    def entry(doc: str) -> dict[str, Any]:
        return entries.setdefault(doc, {"anchor_reasons": [], "missing": [],
                                        "doc_changed": doc in changed_docs, "sections": []})

    for anchor in anchors:
        for hunk in hunks.get(anchor["file"], []):
            touched = _touched(hunk)
            if any(_overlaps((s, e), touched) for s, e in anchor["change_ranges"]):
                reason = {"ref": anchor["ref"], "line": anchor["line"], "file": anchor["file"],
                          "hunk": [hunk["new_start"], hunk["new_end"]]}
                reasons = entry(anchor["doc"])["anchor_reasons"]
                if reason not in reasons:
                    reasons.append(reason)
    now = {(a["doc"], a["line"], a["ref"]) for a in anchors}
    then, _ = resolve(refs, defs_then, _NOTHING, _NOTHING)
    for old in then:
        if (old["doc"], old["line"], old["ref"]) in now:
            continue
        gone = {"ref": old["ref"], "line": old["line"], "file": old["file"],
                "start": old["start"], "end": old["end"], "reading": list(old["reading"])}
        missing = entry(old["doc"])["missing"]
        if gone not in missing:
            missing.append(gone)
    for doc in sorted(changed_docs):
        sections = changed_sections(texts.get(doc, ""), hunks.get(doc, []))
        if sections:
            entry(doc)["sections"] = sections
    for found in entries.values():
        found["anchor_reasons"].sort(key=lambda r: (r["line"], r["ref"], r["file"], r["hunk"]))
        found["missing"].sort(key=lambda r: (r["line"], r["ref"], r["file"], r["start"]))
    return {doc: entries[doc] for doc in sorted(entries)}


def _merge(ranges: Iterable[Iterable[int]]) -> list[list[int]]:
    """Sorted ranges with overlapping and adjacent ones joined."""
    merged: list[list[int]] = []
    for start, end in sorted((r[0], r[1]) for r in map(list, ranges)):
        if merged and start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def review_ranges(doc: str, affected_entry: Mapping[str, Any] | None,
                  refs: Iterable[Reference], line_count: int = 0) -> list[list[int]]:
    """The line ranges of ``doc`` to review: on a first run (no entry) the whole doc of
    ``line_count`` lines; on a later run the blocks of the references named in the entry's
    ``anchor_reasons`` and ``missing`` plus its ``sections``, merged."""
    if affected_entry is None:
        return [[1, line_count]] if line_count > 0 else []
    named = {(r["line"], r["ref"])
             for r in [*affected_entry["anchor_reasons"], *affected_entry["missing"]]}
    blocks = [ref["block"] for ref in refs
              if ref["doc"] == doc and (ref["line"], ref["text"]) in named]
    return _merge([*blocks, *affected_entry["sections"]])


def _load(path: Path, step: str) -> Any:
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def _read_doc(root: Path, doc: str) -> str | None:
    try:
        return (root / doc).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _old_file_definition(path: str) -> Definition:
    """The ``file`` definition ``dd_defindex`` gives a tracked file with a unique basename."""
    name = path.rsplit("/", 1)[-1]
    return Definition(name=name, norm=norm(name), file=path, start=1, end=1, kind="file",
                      owners=[], change_ranges=[[1, 1]], reading=[1, 1])


def _defs_then(root: Path, sha: str, changed: list[str], inventory: Mapping[str, Any],
               current: list[Definition]) -> dict[str, list[Definition]]:
    """The definition index as it was at ``sha``: the current definitions of unchanged files
    plus the changed files as they were at ``sha``. A changed indexed file is re-read there;
    a changed file missing from HEAD's inventory (deleted or renamed away) is classified by
    its path, as the inventory would. Any other changed non-test file that existed at ``sha``
    keeps the ``file`` definition it had when its basename was unique in that tree, so a
    deleted config or doc named by its basename can still be reported missing."""
    tests = set(inventory["sources"].get("test", []))
    indexed = set(indexed_files(dict(inventory))) - tests
    tracked = set(inventory["files"])

    def is_test(path: str) -> bool:
        return path in tests if path in tracked else source_class(path) == "test"

    reread = [path for path in changed
              if path in indexed or (path not in tracked and not is_test(path)
                                     and (source_class(path) == "source"
                                          or is_project_file(path)))]
    tree = History(root).tree_at(sha)
    old_files = tree[0] if tree is not None else frozenset()
    names = Counter(path.rsplit("/", 1)[-1] for path in old_files)
    done = set(reread)
    file_only = [_old_file_definition(path) for path in changed
                 if path not in done and path in old_files and not is_test(path)
                 and names[path.rsplit("/", 1)[-1]] == 1]
    changed_set = set(changed)
    kept = [d for d in current if d["file"] not in changed_set]
    return by_norm([*kept, *at_commit(root, sha, reread), *file_only])


def run(root: Path, workdir: Path, config: Mapping[str, Any], base: str | None,
        full: bool) -> dict[str, Any]:
    """Decide the run mode, compute the change set and the docs to review; write
    ``changes.json``."""
    preflight = _load(workdir / "preflight.json", "dd_preflight")
    inventory = _load(workdir / "inventory.json", "dd_inventory")
    defindex = _load(workdir / "defindex.json", "dd_defindex")
    anchors_doc = _load(workdir / "anchors.json", "dd_anchors")
    mode = last_run(root, workdir, base, full, head=str(preflight["head"]))
    texts: dict[str, str] = {}
    for doc in inventory["docs"]:
        text = _read_doc(root, doc)
        if text is not None:
            texts[doc] = text
    refs: list[Reference] = anchors_doc["references"]
    anchors: list[Anchor] = anchors_doc["anchors"]
    result: dict[str, Any] = {
        "mode": mode["mode"], "last_run": mode["sha"], "last_run_source": mode["source"],
        "scope": mode["scope"], "changed_files": [], "hunks": {}, "affected": {},
        "review": {},
    }
    sha = mode["sha"]
    if sha is None:
        result["review"] = {doc: review_ranges(doc, None, refs, len(text.splitlines()))
                            for doc, text in sorted(texts.items())}
    else:
        changed = changed_files(root, sha)
        indexed = set(indexed_files(inventory))
        changed_docs = {path for path in changed if path in texts}
        code = [path for path in changed if path in indexed]
        all_hunks = diff_hunks(root, sha, [*code, *sorted(changed_docs)])
        not_path = {(a["doc"], a["line"], a["ref"])
                    for a in [*anchors, *anchors_doc["unanchored"]]}
        not_paths = [r for r in refs if (r["doc"], r["line"], r["text"]) in not_path]
        then = _defs_then(root, sha, changed, inventory, defindex["definitions"])
        found = affected(anchors, not_paths, then, all_hunks, changed_docs, texts)
        result["changed_files"] = changed
        result["hunks"] = {path: hunks for path, hunks in all_hunks.items() if path in indexed}
        result["affected"] = found
        result["review"] = {doc: review_ranges(doc, entry, refs)
                            for doc, entry in found.items()}
    write_json(workdir / "changes.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decide the run mode and find the docs the changes since the last run "
                    "affect.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--base", default=None)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    config, _ = load_config(args.repo)
    try:
        run(args.repo, args.workdir, config, args.base, args.full)
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
