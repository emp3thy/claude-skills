"""Resolution, the per-line two-snapshot test and fix classes -> candidates.json.

``candidates.json`` is ``{"candidates": [Candidate...], "history_unavailable": bool,
"honoured": [...]}``. A Candidate is a Token plus the fields in the plan's shared shape and
``history_unavailable`` (true when the token's blame or snapshot tree could not be read).
``honoured`` lists the tokens a ``drift-ignore`` marker suppressed that would otherwise have
been candidates (``doc``, ``line``, ``col``, ``kind``, ``text``, ``reason``), so the summary
can tell live markers from stale ones. Candidates are ordered by (doc, line, col).

``resolve_token`` is pure over a tree (``files``, ``dirs`` and ``read``) and serves HEAD, a
line snapshot and the in-memory re-check alike. HEAD is the tree ``git ls-tree HEAD`` lists, the
same source as the snapshot trees, so the two sides of the test are comparable.

Path tokens resolve doc-relative, then root-relative, then by suffix (tokens with ``/``) or
basename (bare names), after percent-decoding and dropping a leading ``./``. At HEAD any mode
resolves; at the snapshot only ``doc`` and ``root`` count as existed-then (ruling R26), so a
replacement is written in one of those two modes and must itself resolve at HEAD to exactly
the new path. A deleted path whose basename some HEAD path shares is a human decision (R27).
Tree entries resolve doc-relative then root-relative, with the label and then without it (a
placeholder label is always dropped); a renamed entry's replacement is its own last name
segment only, and a rename that changes a parent directory is a human decision (rulings R12,
R16, R22). Anchors whose target doc climbs above the repository never existed. An anchor is
judged by the one commit that removed its slug (a rename keeps the level and a similar section
body, R30), and a ``-N`` duplicate-suffix anchor is never provable (R24). An ``ignored`` token
never yields a candidate (R29).
"""
from __future__ import annotations

import argparse
import difflib
import functools
import posixpath
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, run_git, write_json
from dd_history import History
from dd_manifests import (
    Reader,
    at_precision,
    manifest_floor,
    same_floor,
    script_manifests,
    script_source,
)
from dd_md_scan import scan

_PLACEHOLDER_LABEL = ("<", ">", "{{", "${")
_LINKISH = re.compile(r"!?\[([^\]]*)\]\([^)]*\)|!?\[([^\]]*)\]\[[^\]]*\]")
_TAG = re.compile(r"<[^>]*>")
_OPEN_A = re.compile(r"<a\b", re.I)
_ID_ATTR = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
_NAME_ATTR = re.compile(r"""\bname\s*=\s*["']([^"']+)["']""", re.I)
_URL_SAFE = "/!$&'()*+,;=:@-._~"
_DUP_SUFFIX = re.compile(r"(.+)-(\d+)")
# Ruling R30: a one-commit heading change is a rename only when the section bodies are this
# similar (difflib ratio). An unmeasured convention, to be checked on the fixture corpus.
HEADING_BODY_SIMILARITY = 0.6
_SNAPSHOT_MODES = ("doc", "root")

Tree = tuple[frozenset[str], frozenset[str]]


# -- headings --------------------------------------------------------------------------------


def slugify_heading(text: str) -> str:
    """GitHub-style slug: lower-case, keep letters, digits, spaces, ``-``, ``_``; spaces to -."""
    kept = "".join(c for c in text.strip().lower() if c.isalnum() or c in " -_")
    return kept.replace(" ", "-")


def _plain(heading: str) -> str:
    """Heading text as rendered: link and image markup reduced to their text, tags dropped."""
    text = _LINKISH.sub(lambda m: m.group(1) if m.group(1) is not None else m.group(2), heading)
    return _TAG.sub("", text)


def heading_slugs(text: str) -> set[str]:
    """Every anchor a doc defines: heading slugs (``-1``, ``-2`` for repeats) and HTML ids."""
    return set(_slugs(text))


@functools.lru_cache(maxsize=256)
def _headings(text: str) -> tuple[tuple[str, ...], tuple[tuple[str, int, int, int], ...]]:
    """The doc's lines and its headings as (slug, level, line_start, line_end), in order."""
    sc = scan(text)
    out: list[tuple[str, int, int, int]] = []
    counts: dict[str, int] = {}
    for block in sorted((b for b in sc.blocks if b.kind == "heading"),
                        key=lambda b: b.line_start):
        base = slugify_heading(_plain(block.text or ""))
        seen = counts.get(base, 0)
        counts[base] = seen + 1
        slug = base if seen == 0 else f"{base}-{seen}"
        out.append((slug, block.level or 1, block.line_start, block.line_end))
    return tuple(sc.lines), tuple(out)


def heading_sections(text: str) -> dict[str, tuple[int, str]]:
    """Heading slug -> (level, section body): the lines after the heading up to the next
    heading of the same or a higher level, joined and stripped."""
    lines, heads = _headings(text)
    sections: dict[str, tuple[int, str]] = {}
    for i, (slug, level, _start, end) in enumerate(heads):
        stop = len(lines)
        for _other, other_level, other_start, _other_end in heads[i + 1 :]:
            if other_level <= level:
                stop = other_start - 1
                break
        sections[slug] = (level, "\n".join(lines[end:stop]).strip())
    return sections


@functools.lru_cache(maxsize=256)
def _slugs(text: str) -> frozenset[str]:
    slugs: set[str] = {slug for slug, _level, _start, _end in _headings(text)[1]}
    for tag in _TAG.finditer(text):
        body = tag.group(0)
        slugs.update(m.group(1) for m in _ID_ATTR.finditer(body))
        if _OPEN_A.match(body):
            slugs.update(m.group(1) for m in _NAME_ATTR.finditer(body))
    return frozenset(slugs)


def _fragment(text: str) -> str:
    frag = unquote(text)
    return frag[len("user-content-"):] if frag.startswith("user-content-") else frag


def _match_slug(frag: str, slugs: set[str]) -> str | None:
    if frag in slugs:
        return frag
    lowered = {s.lower(): s for s in slugs}
    return lowered.get(frag.lower())


# -- paths -----------------------------------------------------------------------------------


def _norm(path: str) -> str | None:
    """A normalised repository path; ``""`` is the root; None when it climbs out."""
    p = posixpath.normpath(path) if path else "."
    if p == ".":
        return ""
    if p == ".." or p.startswith(("../", "/")):
        return None
    return p


def _relpath(target: str, start: str) -> str:
    t = target.split("/") if target else []
    s = start.split("/") if start else []
    i = 0
    while i < min(len(t), len(s)) and t[i] == s[i]:
        i += 1
    return "/".join([".."] * (len(s) - i) + t[i:]) or "."


@functools.lru_cache(maxsize=8)
def _by_name(files: frozenset[str], dirs: frozenset[str]) -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = defaultdict(list)
    for path in (*files, *dirs):
        index[path.rsplit("/", 1)[-1]].append(path)
    return {name: tuple(sorted(paths)) for name, paths in index.items()}


class _Form:
    """How a path token is written: prefixes and suffixes to keep in a replacement."""

    def __init__(self, text: str) -> None:
        t = unquote(text)
        self.encoded = t != text
        self.dot = t.startswith("./")
        t = t[2:] if self.dot else t
        self.absolute = t.startswith("/")
        self.trail = t.endswith("/")
        self.core = t.strip("/")


def path_matches(text: str, doc: str, files: frozenset[str],
                 dirs: frozenset[str]) -> tuple[str, tuple[str, ...]] | None:
    """(mode, matching paths) of a path token; modes ``doc``, ``root``, ``suffix``, ``basename``."""
    form = _Form(text)
    if not form.core:
        return None

    def exists(p: str | None) -> bool:
        return bool(p) and (p in files or p in dirs)

    if not form.absolute:
        p = _norm(posixpath.join(posixpath.dirname(doc), form.core))
        if p is not None and exists(p):
            return "doc", (p,)
    p = _norm(form.core)
    if p is not None and exists(p):
        return "root", (p,)
    segs = form.core.split("/")
    if form.absolute or any(s in ("", ".", "..") for s in segs):
        return None
    hits = _by_name(files, dirs).get(segs[-1], ())
    if len(segs) > 1:
        found = tuple(h for h in hits if h.endswith("/" + form.core))
        return ("suffix", found) if found else None
    return ("basename", hits) if hits else None


def _tree_variants(token: dict[str, Any]) -> list[str]:
    text = str(token["text"]).strip("/")
    label = token.get("tree_label")
    if not label:
        return [text]
    if text.startswith(label + "/"):
        stripped = text[len(label) + 1 :]
    else:
        stripped = "" if text == label else text
    if any(m in label for m in _PLACEHOLDER_LABEL):
        return [stripped]
    return [text, stripped]


def tree_match(token: dict[str, Any], files: frozenset[str], dirs: frozenset[str]) -> str | None:
    """The path a tree entry names: with its label then without, doc-relative then root."""
    docdir = posixpath.dirname(token["doc"])
    for variant in _tree_variants(token):
        if not variant:
            return docdir or "."  # the label line itself names the tree's root
        for base in (docdir, ""):
            p = _norm(posixpath.join(base, variant))
            if p and (p in files or p in dirs):
                return p
    return None


def _outside(target: str) -> bool:
    return target == ".." or target.startswith("../")


def resolve_token(token: dict[str, Any], files: frozenset[str], dirs: frozenset[str],
                  read: Reader) -> str | None:
    """What the token names in the tree (path, slug, script name or floor), or None."""
    kind = token["kind"]
    doc = token["doc"]
    if kind == "path":
        found = path_matches(token["text"], doc, files, dirs)
        return found[1][0] if found else None
    if kind == "tree":
        return tree_match(token, files, dirs)
    if kind == "anchor":
        target = token.get("target_doc") or doc
        if _outside(target) or target not in files:
            return None
        text = read(target)
        return None if text is None else _match_slug(_fragment(token["text"]), heading_slugs(text))
    if kind == "script":
        tool = token.get("script_tool") or ""
        found_in = script_source(doc, tool, token["text"], files, read)
        return token["text"] if found_in is not None else None
    if kind == "version":
        version = token.get("version") or {}
        floor = version.get("floor") or token["text"]
        stated = manifest_floor(doc, version.get("runtime", ""), files, read)
        if stated is None or not same_floor(floor, stated[2]):
            return None
        return at_precision(floor, stated[2])
    return None


# -- classification --------------------------------------------------------------------------


def _ev(verb: str, commit: str | None) -> str:
    return f"{verb} in {commit}" if commit else verb


class Resolver:
    """Classifies tokens against HEAD and their line snapshots."""

    def __init__(self, root: Path, history: History) -> None:
        self.root = root
        self.history = history
        self.files, self.dirs = history.head_files()
        self.history_unavailable = False
        self.honoured: list[dict[str, Any]] = []

    def _read_head(self, path: str) -> str | None:
        return self.history.show("HEAD", path)

    def classify(self, token: dict[str, Any]) -> dict[str, Any] | None:
        """A Candidate for a token that does not resolve at HEAD (or a version mismatch)."""
        kind = token["kind"]
        if kind == "version":
            return self._version(token)
        if kind not in ("path", "anchor", "script", "tree"):
            return None
        if kind == "anchor":
            target = token.get("target_doc") or token["doc"]
            if _outside(target):
                return self._route(token, evidence="anchor target is outside the repository")
            if target not in self.files:
                return None  # the unresolved path part is the path token's finding
        if kind == "script" and not script_manifests(
            token["doc"], token.get("script_tool") or "", self.files
        ):
            return None  # no manifest of the tool: not checkable, not a finding
        if resolve_token(token, self.files, self.dirs, self._read_head) is not None:
            return None
        snaps = self.history.line_snapshots(token["doc"])
        sha = snaps.get(token["line"]) if snaps else None
        tree = self.history.tree_at(sha) if sha else None
        if sha is None or tree is None:
            return self._route(token, snapshot=sha, history_unavailable=True,
                               evidence="history unavailable")
        files, dirs = tree
        read: Reader = functools.partial(self.history.show, sha)
        then = resolve_token(token, files, dirs, read)
        if then is not None and kind == "script":
            # strict at the snapshot: an open manifest proves only the names it shows
            then = script_source(token["doc"], token.get("script_tool") or "", token["text"],
                                 files, read, strict=True)
        if then is not None and kind == "path":
            # R26: a suffix or basename match at the snapshot is a guess, not proof
            found = path_matches(token["text"], token["doc"], files, dirs)
            if found is None or found[0] not in _SNAPSHOT_MODES:
                then = None
        if then is None:
            return self._route(token, snapshot=sha, evidence=f"not present at {sha[:7]}")
        if kind == "anchor":
            fields = self._anchor(token, sha)
        elif kind == "script":
            fields = {"resolved_then": then, "outcome": "deleted"}
            commit = self.history.last_commit_touching(sha, then, token["text"])
            fields.update(evidence_commit=commit, evidence=_ev("removed", commit))
        else:
            fields = self._path(token, sha, (files, dirs))
        return self._route(token, snapshot=sha, existed_then=True, **fields)

    def _route(self, token: dict[str, Any], **fields: Any) -> dict[str, Any] | None:
        cand = dict(token)
        cand.update(resolved_then=None, snapshot=None, existed_then=False, outcome=None,
                    replacement=None, evidence_commit=None, evidence="", human_kind=None,
                    history_unavailable=False)
        cand.update(fields)
        human: str | None = None
        if token.get("ignored"):  # R29: never a candidate of any class
            self.honoured.append({"doc": token["doc"], "line": token["line"], "col": token["col"],
                                  "kind": token["kind"], "text": token["text"],
                                  "reason": token["ignored"]})
            return None
        if cand["history_unavailable"]:
            self.history_unavailable = True
        if not cand["existed_then"]:
            cand["class"] = "summary-only"
            return cand
        if token.get("generated"):
            human = "generated-region"
        elif token.get("never_edit"):
            human = "never-edit-section"
        elif not token.get("editable", True):
            human = "prose-mention"
        elif cand["outcome"] == "ambiguous":
            human = "ambiguous-rename"
        if human is not None:
            cand.update({"class": "human", "human_kind": human})
        elif cand["outcome"] in ("unique", "version-mismatch"):
            cand["class"] = "provable-replace"
        else:
            cand["class"] = "provable-delete"
        if cand["outcome"] != "unique" and cand["outcome"] != "version-mismatch":
            cand["replacement"] = None
        return cand

    # -- versions ----------------------------------------------------------------------------

    def _version(self, token: dict[str, Any]) -> dict[str, Any] | None:
        version = token.get("version") or {}
        stated = manifest_floor(token["doc"], version.get("runtime", ""), self.files,
                                self._read_head)
        if stated is None:
            return None
        path, raw, floor = stated
        doc_floor = version.get("floor") or token["text"]
        if same_floor(doc_floor, floor):
            return None
        return self._route(token, existed_then=True, resolved_then=path,
                           outcome="version-mismatch",
                           replacement=at_precision(doc_floor, floor),
                           evidence=f"manifest {path} says {raw}")

    # -- anchors -----------------------------------------------------------------------------

    def _anchor(self, token: dict[str, Any], sha: str) -> dict[str, Any]:
        """Ruling R24: judge the anchor by the one commit that removed its slug."""
        target = token.get("target_doc") or token["doc"]
        frag = _fragment(token["text"])
        then = heading_slugs(self.history.show(sha, target) or "")
        slug = _match_slug(frag, then) or frag
        now = heading_slugs(self._read_head(target) or "")
        found = self._heading_commit(sha, target, frag)
        commit = found[0][:7] if found else None
        fields: dict[str, Any] = {"resolved_then": target, "evidence_commit": commit,
                                  "outcome": "ambiguous",
                                  "evidence": _ev("headings changed", commit)}
        dup = _DUP_SUFFIX.fullmatch(slug)
        if found is None or (dup is not None and (dup.group(1) in then or dup.group(1) in now)):
            return fields  # a -N anchor names a position among repeats: never provable
        removed, added = found[1], found[2]
        if _match_slug(frag, removed) is None:
            return fields  # R32: that commit did not remove this anchor against its parent
        if not added:  # R34: however many subsections went with it
            fields.update(outcome="deleted", evidence=_ev("heading removed", commit))
        elif len(removed) == 1 and len(added) == 1:
            new = next(iter(added))
            if new in now and self._same_section(target, found[0], next(iter(removed)), new):
                fields.update(outcome="unique", replacement=new,
                              evidence=_ev("heading renamed", commit))
        return fields

    def _same_section(self, target: str, commit: str, old: str, new: str) -> bool:
        """Ruling R30: the renamed heading keeps its level and a similar section body."""
        before = heading_sections(self.history.show(f"{commit}^", target) or "").get(old)
        after = heading_sections(self.history.show(commit, target) or "").get(new)
        if before is None or after is None or before[0] != after[0]:
            return False  # an HTML id, not a heading, or the level changed
        if not before[1] or not after[1]:
            return False  # R33: two empty bodies would compare as identical
        ratio = difflib.SequenceMatcher(None, before[1], after[1]).ratio()
        return ratio >= HEADING_BODY_SIMILARITY

    def _heading_commit(self, sha: str, target: str,
                        frag: str) -> tuple[str, set[str], set[str]] | None:
        """The last commit (in topological order) that removed the anchor against its own first
        parent, with the slugs that commit removed and added there.

        Each commit is judged against its first parent, never against the previously listed
        commit, so a merge whose first parent already lacked the anchor is not the remover
        (ruling R32).
        """
        out = run_git(self.root, ["--literal-pathspecs", "log", "--topo-order", "--reverse",
                                  "--format=%H", f"{sha}..HEAD", "--", target])
        found: tuple[str, set[str], set[str]] | None = None
        for commit in (out or "").split():
            after = heading_slugs(self.history.show(commit, target) or "")
            if _match_slug(frag, after) is not None:
                continue
            before = heading_slugs(self.history.show(f"{commit}^", target) or "")
            if _match_slug(frag, before) is not None:
                found = (commit, before - after, after - before)
        return found

    # -- paths and tree entries --------------------------------------------------------------

    def _path(self, token: dict[str, Any], sha: str, tree: Tree) -> dict[str, Any]:
        files, dirs = tree
        mode = "tree"
        if token["kind"] == "tree":
            old = tree_match(token, files, dirs) or ""
        else:
            found = path_matches(token["text"], token["doc"], files, dirs)
            assert found is not None  # the caller checked a doc or root match then (R26)
            mode, old = found[0], found[1][0]
        news, commit = self._moved(sha, old, files)
        fields: dict[str, Any] = {"resolved_then": old, "evidence_commit": commit}
        if not news:
            gone = self.history.deleting_commit(sha, old)
            fields.update(outcome="deleted", evidence_commit=gone, evidence=_ev("deleted", gone))
            # R27: a same-named path at HEAD may be the file moved and rewritten
            same = _by_name(self.files, self.dirs).get(old.rsplit("/", 1)[-1], ())
            if same:
                fields.update(outcome="ambiguous",
                              evidence=_ev("deleted", gone) + "; HEAD has " + ", ".join(same))
            return fields
        if len(news) == 1:
            replacement = self._rewrite(token, mode, old, next(iter(news)))
            if replacement is not None:
                fields.update(outcome="unique", replacement=replacement,
                              evidence=_ev("renamed", commit))
                return fields
        names = ", ".join(sorted(n for n in news if n)) or "several paths"
        fields.update(outcome="ambiguous", evidence=_ev("renamed", commit) + f" to {names}")
        return fields

    def _moved(self, sha: str, old: str, files: frozenset[str]) -> tuple[set[str], str | None]:
        """Final names of a snapshot path; a directory's from the final names of its files."""
        if old in files:
            finals, commit = self.history.final_name(sha, old)
            return set(finals), commit
        prefixes: set[str] = set()
        commits: Counter[str] = Counter()
        for child in sorted(p for p in files if p.startswith(old + "/")):
            rel = child[len(old) + 1 :]
            finals, commit = self.history.final_name(sha, child)
            for new in finals:
                if new.endswith("/" + rel):
                    prefixes.add(new[: -len(rel) - 1])
                elif "/" not in rel:
                    prefixes.add(posixpath.dirname(new))
                else:
                    prefixes.add("")  # layout changed below the directory: never unique
            if commit and finals:
                commits[commit] += 1
        best = min(commits, key=lambda c: (-commits[c], c)) if commits else None
        return prefixes, best

    def _rewrite(self, token: dict[str, Any], mode: str, old: str, new: str) -> str | None:
        """The token's new text in its own mode, when it resolves at HEAD to exactly ``new``."""
        if not new or (new not in self.files and new not in self.dirs):
            return None
        text = str(token["text"])
        if mode == "tree":
            if posixpath.dirname(new) != posixpath.dirname(old):
                return None  # a parent changed: the edit would have to touch another line
            trail = "/" if text.endswith("/") else ""
            own = text.rstrip("/").rsplit("/", 1)[-1] + trail
            replacement = new.rsplit("/", 1)[-1] + trail
            moved = dict(token, text=text[: len(text) - len(own)] + replacement)
            ok = tree_match(moved, self.files, self.dirs) == new
            return replacement if ok else None
        form = _Form(text)
        body = _relpath(new, posixpath.dirname(token["doc"])) if mode == "doc" else new
        out = ("/" if form.absolute else "") + body + ("/" if form.trail else "")
        if form.dot and not out.startswith(("../", "/")):
            out = "./" + out
        if form.encoded:
            out = quote(out, safe=_URL_SAFE)
        found = path_matches(out, token["doc"], self.files, self.dirs)
        return out if found is not None and found[1] == (new,) and out != text else None


def run(root: Path, workdir: Path, history: History | None = None) -> dict[str, Any]:
    """Classify every token in ``workdir/tokens.json``; write ``candidates.json``."""
    for name in ("inventory.json", "tokens.json"):
        if not (workdir / name).is_file():
            raise StepError(f"missing {workdir / name}; run the earlier steps first", EXIT_MISSING)
    tokens = read_json(workdir / "tokens.json")
    resolver = Resolver(root, history or History(root))
    candidates: list[dict[str, Any]] = []
    for doc in sorted(tokens["docs"]):
        for token in tokens["docs"][doc]:
            cand = resolver.classify(token)
            if cand is not None:
                candidates.append(cand)
    candidates.sort(key=lambda c: (c["doc"], c["line"], c["col"], c["end_col"], c["kind"]))
    result = {
        "candidates": candidates,
        "history_unavailable": resolver.history_unavailable,
        "honoured": sorted(resolver.honoured, key=lambda h: (h["doc"], h["line"], h["col"])),
    }
    write_json(workdir / "candidates.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve tokens and classify the unresolved.")
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
