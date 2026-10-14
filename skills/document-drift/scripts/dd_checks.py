"""Script checks and verifier batches (spec 9.1, 9.2) -> edits.json and plan-verify.json.

``check`` runs the spec 9.1 checks on one edit in table order; the first failure decides:

- ``old-mismatch`` (dropped): ``old`` is not the text of lines ``start_line``..``end_line`` of
  the doc (line endings stripped, joined by ``\\n``), or the doc is not an in-scope doc. One
  repair: when both have the same number of lines and differ only in leading whitespace,
  ``old`` becomes the doc's text and each line of ``new`` gets the indentation of the doc line
  at the same index (lines past ``old``'s count take the last doc line's), replacing the
  agent's own indentation of that ``old`` line when the ``new`` line starts with it; the edit
  then carries ``repaired: true``. No repair when ``old`` is exactly the text of another range
  of the doc: the range is then misplaced (an off-by-one onto an indentation twin), not
  mis-indented.
- ``protected`` (human): a line of the range is in an honoured ``drift-ignore`` target, a
  generated region or a never-edit section. ``clear`` edits are exempt: they remove the
  skill's own notice line, and a ``drift-ignore`` over a notice is the reason to clear it.
- ``evidence`` (dropped): an entry is not ``path:line`` (or ``path:start-end``) naming a file
  tracked at HEAD and lines inside it, or a ``correct``, ``add`` or ``anchor`` edit has none.
- ``still-in-source`` (dropped): a ``remove`` edit's ``subject`` (backticks and a call's
  argument list dropped, then ``dd_defindex.norm``) is a whole word of a tracked source or
  project file, whose content is compared both as written and with ``-`` and ``.`` between
  word characters read as ``_`` (so ``cfg.retry_count`` holds ``retry_count`` and
  ``cfg_retry_count``).
- ``anchor-adds-name`` (dropped): ``old`` holds a guarantee word, or ``new``'s tokens
  (whitespace-separated, a backtick span kept whole, ``()[]{},:;`` and sentence ``.!?``
  stripped from the edges) are not ``old``'s tokens in order plus exactly one inline-code span
  and at most ``ANCHOR_EXTRA_WORDS`` other tokens, or the span's name, resolved by
  ``dd_anchors.resolve`` as a specific reference, has no definition in the file of the first
  evidence entry.
- ``guarantee`` (human ``guarantee-mismatch``): a guarantee word of ``old`` is missing from
  ``new`` (the words compared as a multiset, case-insensitive, whole words).
- ``large-deletion`` (human): a ``remove`` or ``unverified`` edit deletes more than
  ``max_delete_lines`` lines (for ``unverified``, the block's lines without its notice line,
  spec 7.3) or a heading line (a heading block of the markdown scanner).
- ``large-section`` (human): an ``add`` edit's ``new`` has more than ``max_section_lines`` lines
  beyond ``old``'s.
- ``new-reference`` (dropped): a path token of ``new`` (phase 1 extractor) that ``old`` lacks
  does not exist at HEAD relative to the doc or the root (a bare file name may also be a
  ``file`` definition), or a code-span name of ``new`` (``dd_anchors.references``) that ``old``
  lacks is neither in the definition index nor a whole word of a tracked source or project
  file. Notice-loop edits skip this check: their ``new`` is a notice line.
- ``overlap`` (human): the range overlaps an edit already kept for the same doc. ``check``
  records each kept range in ``Context.kept``, so the call order is the keep order.

Protected lines are recomputed per doc rather than read from tokens, since only lines that
carry a token have token flags: the ``drift-ignore`` targets are ``tokens.json``'s honoured
markers (``dd_unverified.ignore_regions``); generated regions and heading paths come from
``dd_extract``'s extractor over the doc text with ``inventory.json``'s ``never_edit_re``, a
line being never-edit when a heading of its heading path matches.

``run`` checks the review edits, then the gap edits, then ``notices.json``'s edits, each by id,
writes ``edits.json`` and plans the verifier batches with ``dd_dispatch.plan_verify``:
``{"edits", "questions", "refusals", "human", "unverified_blocks", "code_claims",
"unchecked_units", "unchecked_gap_docs", "not_reviewed", "unverified_batches"}``.
``not_reviewed`` holds the ranges review outputs report as not reviewed, except those of a
unit that a retry unit (``retry_of``) re-dispatched. Every edit gains ``source``
(``review``, ``gap``, ``notice``), ``status`` (``kept``, ``dropped``, ``human``), ``check``,
``human_kind`` and ``reason``; a check failure's human entry has the text ``<claim> (<reason>)``
and the edit's evidence. ``human`` holds a Human-decision entry for each question, each
check failure with a human kind and each ``target-refused`` gap refusal, sorted by doc and
line; ``refusals`` holds the other gap refusals with their target doc. Notice edits are checked
but never batched: they are not sent to a verifier (spec 7.3).
"""
from __future__ import annotations

import argparse
import posixpath
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dd_anchors import Reference, first_token, references, resolve
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import Definition, by_norm, norm
from dd_dispatch import DEFAULT_VERIFY_CAP, plan_verify
from dd_extract import _Extractor, extract_doc
from dd_history import History
from dd_inventory import indexed_files
from dd_resolve import path_matches
from dd_unverified import ignore_regions

MAX_DELETE_LINES = 15
MAX_SECTION_LINES = 40
BATCH_SIZE = 10
ANCHOR_EXTRA_WORDS = 3

SOURCES = ("review", "gap", "notice")
NOTICE_TYPES = frozenset({"notice", "escalate", "clear", "unverified"})
EVIDENCE_REQUIRED = frozenset({"correct", "add", "anchor"})
DELETION_TYPES = frozenset({"remove", "unverified"})
HUMAN_KINDS = {"protected": "protected", "guarantee": "guarantee-mismatch",
               "large-deletion": "large-deletion", "large-section": "large-section",
               "overlap": "overlap"}
KEPT_REFUSALS = ("not-user-facing", "already-documented")

_GUARANTEE = re.compile(
    r"(?<!\w)(must\s+not|must|shall|guarantees|guarantee|always|never|is\s+required)(?!\w)",
    re.IGNORECASE)
_EVIDENCE = re.compile(r"^(?P<path>.+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_LINE_SPLIT = re.compile(r"\r?\n")
_INNER = re.compile(r"(?<=\w)[-.](?=\w)")
# words, and flags with their leading dashes: `--foo-bar` holds both `foo_bar` and `--foo_bar`
_WORDS = (re.compile(r"\w+"), re.compile(r"(?<![\w-])-+\w+"))
_TOKEN = re.compile(r"(?:[^\s`]*`[^`]*`)+[^\s`]*|\S+")
_SPAN = re.compile(r"`([^`]+)`")
_EDGES = "()[]{},:;.!?"
_NEVER = re.compile(r"(?!)")

Range = tuple[int, int]


@dataclass
class Context:
    """What the checks read: per doc its lines and protected lines (line -> region kind), the
    definition index by norm, HEAD's files and dirs, the tracked source and project files'
    normalised words and texts, and the config. ``kept`` collects the kept ranges per doc."""
    root: Path
    texts: dict[str, list[str]]
    protected: dict[str, dict[int, str]]
    headings: dict[str, set[int]]
    defs: dict[str, list[Definition]]
    files: frozenset[str]
    dirs: frozenset[str]
    source_words: frozenset[str]
    source_texts: list[str]
    config: Mapping[str, Any]
    kept: dict[str, list[Range]] = field(default_factory=dict)
    line_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------- context

def _split(text: str) -> list[str]:
    lines = _LINE_SPLIT.split(text)
    return lines[:-1] if lines and lines[-1] == "" else lines


def _read(root: Path, path: str) -> str | None:
    try:
        return (root / path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _protected(doc: str, text: str, markers: Sequence[Mapping[str, Any]],
               never: re.Pattern[str]) -> tuple[dict[int, str], set[int]]:
    """Protected lines of one doc (line -> region kind) and its heading lines."""
    extractor = _Extractor(doc, text, never)
    lines: dict[int, str] = {}
    starts, paths = extractor.heading_paths()
    bounds = [*starts[1:], extractor.count + 1] if starts else []
    for start, end, path in zip(starts, bounds, paths, strict=True):
        if any(never.search(h) for h in path):
            lines.update(dict.fromkeys(range(start, end), "never-edit section"))
    for a, b in extractor.generated():
        lines.update(dict.fromkeys(range(a, b + 1), "generated region"))
    for a, b in ignore_regions(markers, doc):
        lines.update(dict.fromkeys(range(a, b + 1), "drift-ignore region"))
    headings = {n for b in extractor.sc.blocks if b.kind == "heading"
                for n in range(b.line_start, b.line_end + 1)}
    return lines, headings


def _normalise(text: str) -> str:
    return _INNER.sub("_", text)


def _load(workdir: Path, name: str, step: str) -> Any:
    path = workdir / name
    if not path.is_file():
        raise StepError(f"missing {path}; run {step} first", EXIT_MISSING)
    return read_json(path)


def context(root: Path, workdir: Path, config: Mapping[str, Any],
            docs: Iterable[str] | None = None) -> Context:
    """The check context for ``docs`` (default: every in-scope doc); a doc outside
    ``inventory.json``'s docs, or unreadable, has no text, so its edits fail ``old-mismatch``."""
    inventory = _load(workdir, "inventory.json", "dd_inventory")
    markers = _load(workdir, "tokens.json", "dd_extract")["markers"]
    defindex = _load(workdir, "defindex.json", "dd_defindex")
    in_scope = set(inventory["docs"])
    never = re.compile(inventory["never_edit_re"])
    texts: dict[str, list[str]] = {}
    protected: dict[str, dict[int, str]] = {}
    headings: dict[str, set[int]] = {}
    for doc in sorted(in_scope if docs is None else in_scope.intersection(docs)):
        text = _read(root, doc)
        if text is None:
            continue
        texts[doc] = _split(text)
        protected[doc], headings[doc] = _protected(doc, text, markers, never)
    raw = [t for t in (_read(root, p) for p in indexed_files(inventory)) if t is not None]
    # raw and normalised: `cfg.retry_count` holds `retry_count` as well as `cfg_retry_count`
    source_texts = raw + [_normalise(t) for t in raw]
    words = frozenset(w for t in source_texts for pattern in _WORDS for w in pattern.findall(t))
    files, dirs = History(root).head_files()
    return Context(root=root, texts=texts, protected=protected, headings=headings,
                   defs=by_norm(defindex["definitions"]), files=files, dirs=dirs,
                   source_words=words, source_texts=source_texts, config=config)


def _in_source(name: str, ctx: Context) -> bool:
    """``name`` (normalised) is a whole word of a tracked source or project file."""
    target = _normalise(norm(name))
    if not target:
        return False
    if re.fullmatch(r"-*\w+", target):
        return target in ctx.source_words
    pattern = re.compile(r"(?<!\w)" + re.escape(target) + r"(?!\w)")
    return any(pattern.search(t) for t in ctx.source_texts)


def _defined(name: str, ctx: Context) -> bool:
    """``name`` is in the definition index, directly or as ``Owner.member`` (spec 5.3)."""
    if norm(name) in ctx.defs:
        return True
    if "." in name and "/" not in name:
        head, tail = name.split(".", 1)[0], name.rsplit(".", 1)[1]
        return norm(head) in ctx.defs and norm(tail) in ctx.defs
    return False


def _setting(ctx: Context, key: str, default: int) -> int:
    return int(ctx.config.get(key, default))


# ---------------------------------------------------------------- checks

def _guarantees(text: str) -> Counter[str]:
    return Counter(" ".join(m.lower().split()) for m in _GUARANTEE.findall(text))


def _indent(line: str) -> str:
    return line[:len(line) - len(line.lstrip())]


def _old_mismatch(edit: dict[str, Any], ctx: Context) -> str | None:
    lines = ctx.texts.get(edit["doc"])
    if lines is None:
        return f"{edit['doc']} is not an in-scope doc that can be read"
    start, end = int(edit["start_line"]), int(edit["end_line"])
    if start < 1 or end < start or end > len(lines):
        return f"lines {start}-{end} are outside the doc ({len(lines)} lines)"
    doc_lines = lines[start - 1:end]
    if edit["old"] == "\n".join(doc_lines):
        return None
    old_lines = edit["old"].split("\n")
    if len(old_lines) != len(doc_lines) or any(
            a.lstrip() != b.lstrip() for a, b in zip(old_lines, doc_lines, strict=True)):
        return f"old is not the text of lines {start}-{end}"
    size = len(old_lines)
    for other in range(1, len(lines) - size + 2):
        if lines[other - 1] == old_lines[0] and lines[other - 1:other - 1 + size] == old_lines:
            return (f"old is the text of lines {other}-{other + size - 1}, not of lines "
                    f"{start}-{end}")
    new_lines = edit["new"].split("\n") if edit["new"] else []
    out = []
    for i, line in enumerate(new_lines):
        k = min(i, len(doc_lines) - 1)
        own = _indent(old_lines[k])
        body = line[len(own):] if own and line.startswith(own) else line
        out.append(_indent(doc_lines[k]) + body if line.strip() else line)
    edit["old"] = "\n".join(doc_lines)
    edit["new"] = "\n".join(out)
    edit["repaired"] = True
    return None


def _protected_check(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] == "clear":
        return None
    marks = ctx.protected.get(edit["doc"], {})
    for line in range(int(edit["start_line"]), int(edit["end_line"]) + 1):
        if line in marks:
            return f"line {line} is in a {marks[line]}"
    return None


def _file_lines(path: str, ctx: Context) -> int:
    if path not in ctx.line_counts:
        text = _read(ctx.root, path)
        ctx.line_counts[path] = 0 if text is None else len(_split(text))
    return ctx.line_counts[path]


def _evidence(edit: dict[str, Any], ctx: Context) -> str | None:
    evidence = edit.get("evidence") or []
    if not evidence and edit["type"] in EVIDENCE_REQUIRED:
        return f"a {edit['type']} edit needs evidence"
    for entry in evidence:
        m = _EVIDENCE.match(entry)
        if m is None:
            return f"evidence {entry!r} is not path:line"
        path, start = m["path"], int(m["start"])
        end = int(m["end"]) if m["end"] else start
        if path not in ctx.files:
            return f"evidence {entry!r} names a file not tracked at HEAD"
        count = _file_lines(path, ctx)
        if not 1 <= start <= end <= count:
            return f"evidence {entry!r} is outside the file ({count} lines)"
    return None


def _subject_name(subject: str) -> str:
    text = subject.strip().strip("`").strip()
    return first_token(text) or text


def _still_in_source(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] != "remove" or not edit.get("subject"):
        return None
    name = _subject_name(str(edit["subject"]))
    if _in_source(name, ctx):
        return f"{name} is still in the source"
    return None


def _tokens(text: str) -> list[str]:
    out = [t.strip(_EDGES) for t in _TOKEN.findall(text)]
    return [t for t in out if t]


def _extras(old: list[str], new: list[str]) -> list[str] | None:
    """The tokens of ``new`` left once ``old``'s tokens are matched in order, or None when
    ``old`` is not a subsequence of ``new``."""
    extras: list[str] = []
    i = 0
    for token in new:
        if i < len(old) and token == old[i]:
            i += 1
        else:
            extras.append(token)
    return extras if i == len(old) else None


def _wrapped(old: list[str], new: list[str]) -> str | None:
    """The one token of ``old`` that ``new`` wraps in backticks and changes nothing else, or
    None."""
    if len(old) != len(new):
        return None
    changed = [(o, n) for o, n in zip(old, new, strict=True) if o != n]
    if len(changed) == 1 and changed[0][1] == f"`{changed[0][0]}`":
        return changed[0][1]
    return None


def _evidence_file(edit: Mapping[str, Any]) -> str | None:
    evidence = edit.get("evidence") or []
    if not evidence:
        return None
    m = _EVIDENCE.match(evidence[0])
    return m["path"] if m else None


def _anchor_adds_name(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] != "anchor":
        return None
    if _guarantees(edit["old"]):
        return "old holds a guarantee word"
    old_tokens, new_tokens = _tokens(edit["old"]), _tokens(edit["new"])
    extras = _extras(old_tokens, new_tokens)
    if extras is None:
        wrapped = _wrapped(old_tokens, new_tokens)
        if wrapped is None:
            return "new does not keep old's words in order"
        extras = [wrapped]
    spans = [t for t in extras if _SPAN.fullmatch(t)]
    if len(spans) != 1:
        return f"new adds {len(spans)} inline-code spans, not one"
    if len(extras) - 1 > ANCHOR_EXTRA_WORDS:
        return f"new adds {len(extras) - 1} words besides the name"
    name = first_token(spans[0][1:-1])
    file = _evidence_file(edit)
    if name is None or file is None:
        return "the added span names nothing"
    start, end = int(edit["start_line"]), int(edit["end_line"])
    ref = Reference(doc=edit["doc"], line=start, text=name, norm=norm(name), specific=True,
                    block=[start, end], heading=None, context=[])
    anchors, _ = resolve([ref], ctx.defs, ctx.files, ctx.dirs)
    if not any(a["file"] == file for a in anchors):
        return f"{name} does not resolve to a definition in {file}"
    return None


def _guarantee(edit: dict[str, Any], ctx: Context) -> str | None:
    lost = _guarantees(edit["old"]) - _guarantees(edit["new"])
    if lost:
        return f"new drops the guarantee word {sorted(lost)[0]!r}"
    return None


def _large_deletion(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] not in DELETION_TYPES:
        return None
    start, end = int(edit["start_line"]), int(edit["end_line"])
    limit = _setting(ctx, "max_delete_lines", MAX_DELETE_LINES)
    # an unverified removal's range starts at its notice line; spec 7.3 measures the block
    lines = end - start + 1 - (1 if edit["type"] == "unverified" else 0)
    if lines > limit:
        return f"deletes {lines} lines (more than {limit})"
    heads = ctx.headings.get(edit["doc"], set())
    for line in range(start, end + 1):
        if line in heads:
            return f"deletes the heading on line {line}"
    return None


def _large_section(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] != "add":
        return None
    added = len(edit["new"].split("\n")) - len(edit["old"].split("\n"))
    limit = _setting(ctx, "max_section_lines", MAX_SECTION_LINES)
    if added > limit:
        return f"adds {added} lines (more than {limit})"
    return None


def _paths(doc: str, text: str) -> set[str]:
    tokens, _ = extract_doc(doc, text, _NEVER)
    return {t["text"] for t in tokens if t["kind"] == "path"}


def _new_reference(edit: dict[str, Any], ctx: Context) -> str | None:
    if edit["type"] in NOTICE_TYPES:
        return None
    doc = edit["doc"]
    new_paths = _paths(doc, edit["new"]) - _paths(doc, edit["old"])
    for path in sorted(new_paths):
        found = path_matches(path, doc, ctx.files, ctx.dirs, loose=False)
        if not found and not ("/" not in path and norm(posixpath.basename(path)) in ctx.defs):
            return f"path {path} does not exist at HEAD"
    old_names = {r["text"] for r in references(doc, edit["old"])}
    for ref in references(doc, edit["new"]):
        name = ref["text"]
        if name in old_names or name in new_paths:
            continue
        if _defined(name, ctx) or _in_source(name, ctx):
            continue
        if "/" in name and path_matches(name, doc, ctx.files, ctx.dirs, loose=True):
            continue
        return f"{name} is neither defined nor in the source"
    return None


def _overlap(edit: dict[str, Any], ctx: Context) -> str | None:
    start, end = int(edit["start_line"]), int(edit["end_line"])
    for a, b in ctx.kept.get(edit["doc"], []):
        if start <= b and a <= end:
            return f"lines {start}-{end} overlap a kept edit on lines {a}-{b}"
    return None


CHECKS: tuple[tuple[str, Callable[[dict[str, Any], Context], str | None]], ...] = (
    ("old-mismatch", _old_mismatch),
    ("protected", _protected_check),
    ("evidence", _evidence),
    ("still-in-source", _still_in_source),
    ("anchor-adds-name", _anchor_adds_name),
    ("guarantee", _guarantee),
    ("large-deletion", _large_deletion),
    ("large-section", _large_section),
    ("new-reference", _new_reference),
    ("overlap", _overlap),
)


def _check(edit: dict[str, Any], ctx: Context) -> tuple[str, str | None, str | None, str | None]:
    for name, fn in CHECKS:
        reason = fn(edit, ctx)
        if reason is not None:
            kind = HUMAN_KINDS.get(name)
            return ("human" if kind else "dropped"), name, kind, reason
    ctx.kept.setdefault(edit["doc"], []).append(
        (int(edit["start_line"]), int(edit["end_line"])))
    return "kept", None, None, None


def check(edit: dict[str, Any], ctx: Context) -> tuple[str, str | None, str | None]:
    """``(status, failing check, human kind)`` of ``edit`` (spec 9.1, first failure decides).
    The whitespace repair rewrites ``edit`` in place; a kept edit's range joins ``ctx.kept``."""
    status, name, kind, _ = _check(edit, ctx)
    return status, name, kind


# ---------------------------------------------------------------- batches

def batches(kept_edits: Iterable[Mapping[str, Any]],
            size: int = BATCH_SIZE) -> list[list[Mapping[str, Any]]]:
    """Kept review and gap edits grouped by the file of their first evidence entry (an edit
    with no evidence by its doc), groups by key, edits by id, at most ``size`` per batch."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for edit in kept_edits:
        if edit.get("status") != "kept" or edit.get("source") not in ("review", "gap"):
            continue
        key = _evidence_file(edit) or str(edit["doc"])
        groups.setdefault(key, []).append(edit)
    out: list[list[Mapping[str, Any]]] = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda e: str(e["id"]))
        out += [group[i:i + size] for i in range(0, len(group), size)]
    return out


# ---------------------------------------------------------------- run

def _human(doc: str, line: int, kind: str, text: str, evidence: Sequence[str]) -> dict[str, Any]:
    return {"doc": doc, "line": line, "kind": kind, "text": text, "evidence": list(evidence)}


def _target_line(gaps: Mapping[str, Any], doc: str, name: str) -> int:
    for gap in gaps.get("targets", {}).get(doc, []):
        if gap.get("name") == name:
            return int(gap["target_line"])
    return 1


def _outputs(plan: Sequence[Mapping[str, Any]], failed: frozenset[str] | set[str]
             ) -> tuple[list[tuple[Mapping[str, Any], Any]], list[str]]:
    """``(entry, output)`` of each review and gap entry with a usable output, and the ids of
    the entries without one."""
    usable: list[tuple[Mapping[str, Any], Any]] = []
    missing: list[str] = []
    for entry in plan:
        if entry["role"] not in ("review", "gap"):
            continue
        path = Path(entry["output"])
        if entry["id"] in failed or not path.is_file():
            missing.append(str(entry["id"]))
            continue
        usable.append((entry, read_json(path)))
    return usable, missing


def run(root: Path, workdir: Path, config: Mapping[str, Any],
        failed: frozenset[str] | set[str] = frozenset()) -> dict[str, Any]:
    """Check every review, gap and notice edit; write ``edits.json`` and ``plan-verify.json``.
    ``failed`` holds the ids of plan entries whose output failed validation after retry."""
    plan = _load(workdir, "plan-docs.json", "dd_dispatch")
    units = _load(workdir, "units.json", "dd_units")
    gaps = _load(workdir, "gaps.json", "dd_gaps")
    notices = _load(workdir, "notices.json", "dd_unverified")
    usable, missing = _outputs(plan, failed)
    roles = {str(e["id"]): e for e in plan}
    unchecked_units = sorted({*units.get("unchecked", []),
                              *(i for i in missing if roles[i]["role"] == "review")})
    unchecked_gap_docs = sorted({*gaps.get("unchecked", []),
                                 *(str(roles[i]["doc"]) for i in missing
                                   if roles[i]["role"] == "gap")})
    found: dict[str, list[dict[str, Any]]] = {s: [] for s in SOURCES}
    questions: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []
    human: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    claims: dict[str, int] = {}
    for entry, out in sorted(usable, key=lambda pair: str(pair[0]["id"])):
        if entry["role"] == "review":
            found["review"] += [dict(e) for e in out["edits"]]
            questions += out["questions"]
            blocks += out["unverified_blocks"]
            for doc, count in out["code_claims"].items():
                claims[doc] = claims.get(doc, 0) + int(count)
            continue
        doc = str(entry["doc"])
        found["gap"] += [dict(e) for e in out["edits"]]
        for refusal in out["refusals"]:
            if refusal["kind"] in KEPT_REFUSALS:
                refusals.append({**refusal, "doc": doc})
            else:
                human.append(_human(doc, _target_line(gaps, doc, refusal["name"]),
                                    "target-refused", refusal["name"], [refusal["reason"]]))
    found["notice"] = [dict(e) for e in notices.get("edits", [])]
    for q in questions:
        extra = q.get("code") or q.get("question") or ""
        human.append(_human(q["doc"], int(q["line"]), q["kind"], q["claim"],
                            q["evidence"] or ([extra] if extra else [])))
    ctx = context(root, workdir, config,
                  {str(e["doc"]) for edits in found.values() for e in edits})
    checked: list[dict[str, Any]] = []
    for source in SOURCES:
        for edit in sorted(found[source], key=lambda e: str(e["id"])):
            status, name, kind, reason = _check(edit, ctx)
            edit.update(source=source, status=status, check=name, human_kind=kind,
                        reason=reason)
            checked.append(edit)
            if kind is not None and reason is not None:
                human.append(_human(edit["doc"], int(edit["start_line"]), kind,
                                    f"{edit['claim']} ({reason})", edit.get("evidence") or []))
    retried = {str(u["retry_of"]) for u in units["units"] if u.get("retry_of")}
    not_reviewed = sorted(
        ({"unit": str(entry["id"]), "doc": str(r["doc"]), "start_line": int(r["start_line"]),
          "end_line": int(r["end_line"]), "why": str(r["why"])}
         for entry, output in usable if entry["role"] == "review"
         and str(entry["id"]) not in retried
         for r in output.get("not_reviewed") or []),
        key=lambda r: (r["doc"], r["start_line"], r["end_line"], r["unit"]))
    planned = batches(checked)
    cap = int(config.get("caps", {}).get("verify", DEFAULT_VERIFY_CAP))
    result: dict[str, Any] = {
        "edits": checked,
        "questions": questions,
        "refusals": refusals,
        "human": sorted(human, key=lambda h: (h["doc"], h["line"], h["kind"], h["text"])),
        "unverified_blocks": blocks,
        "code_claims": claims,
        "unchecked_units": unchecked_units,
        "unchecked_gap_docs": unchecked_gap_docs,
        "not_reviewed": not_reviewed,
        "unverified_batches": [[str(e["id"]) for e in b] for b in planned[cap:]],
    }
    write_json(workdir / "edits.json", result)
    plan_verify(root, workdir, planned, config)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the script checks on the proposed edits; write edits.json and the "
                    "verifier plan.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--failed", action="append", default=[],
                        help="id of a plan entry whose output failed validation (repeatable)")
    args = parser.parse_args(argv)
    try:
        from dd_config import load_config
        config, _ = load_config(args.repo)
        result = run(args.repo, args.workdir, config, set(args.failed))
    except StepError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    kept = sum(e["status"] == "kept" for e in result["edits"])
    print(f"{(args.workdir / 'edits.json').as_posix()}: {len(result['edits'])} edits, "
          f"{kept} kept")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
