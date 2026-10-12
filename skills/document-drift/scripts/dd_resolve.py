"""Resolution of path and anchor tokens against HEAD -> candidates.json.

``candidates.json`` is ``{"candidates": [Candidate...]}``: one Candidate per ``path`` and
``anchor`` token of ``tokens.json``, the token plus ``resolved`` (bool) and ``resolved_to``
(the path or slug it names at HEAD, or null), ordered by (doc, line, col, end_col, kind). A
path absent from HEAD but present on disk (untracked or ignored, such as a once-tracked
runtime artefact) counts as resolved, with ``resolved_to`` null (ruling R66).

``resolve_token`` is pure over a tree (``files``, ``dirs`` and ``read``) and serves the HEAD
resolution and the in-memory re-check of ``dd_apply`` alike; it also resolves ``script``,
``version`` and ``tree`` tokens. Path tokens resolve doc-relative, then root-relative, then by
suffix (tokens with ``/``) or basename (bare names), after percent-decoding and dropping a
leading ``./``. Tree entries resolve doc-relative then root-relative, with the label and then
without it (a placeholder label is always dropped). An anchor resolves when its target doc is
in the tree and defines the slug (``heading_slugs``); a target doc above the repository never
resolves. An open script manifest counts as defining every name (ruling R25).
"""
from __future__ import annotations

import argparse
import functools
import posixpath
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_history import History
from dd_manifests import (
    Paths,
    Reader,
    at_precision,
    manifest_floor,
    same_floor,
    script_source,
)
from dd_md_scan import scan

_PLACEHOLDER_LABEL = ("<", ">", "{{", "${")
_LINKISH = re.compile(r"!?\[([^\]]*)\]\([^)]*\)|!?\[([^\]]*)\]\[[^\]]*\]")
_TAG = re.compile(r"<[^>]*>")
_OPEN_A = re.compile(r"<a\b", re.I)
_ID_ATTR = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
_NAME_ATTR = re.compile(r"""\bname\s*=\s*["']([^"']+)["']""", re.I)


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


@functools.lru_cache(maxsize=8)
def _by_name(files: frozenset[str], dirs: frozenset[str]) -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = defaultdict(list)
    for path in (*files, *dirs):
        index[path.rsplit("/", 1)[-1]].append(path)
    return {name: tuple(sorted(paths)) for name, paths in index.items()}


class _Form:
    """A path token read as a path: percent-decoded, a leading ``./`` dropped, whether it is
    absolute, and its ``core`` without leading or trailing ``/``."""

    def __init__(self, text: str) -> None:
        t = unquote(text)
        t = t[2:] if t.startswith("./") else t
        self.absolute = t.startswith("/")
        self.core = t.strip("/")


def _strict_paths(text: str, doc: str) -> list[str]:
    """The doc-relative then the root-relative reading of a path token, existing or not."""
    form = _Form(text)
    if not form.core:
        return []
    out: list[str] = []
    if not form.absolute:
        p = _norm(posixpath.join(posixpath.dirname(doc), form.core))
        if p:
            out.append(p)
    p = _norm(form.core)
    if p:
        out.append(p)
    return out


def path_matches(text: str, doc: str, files: Paths, dirs: Paths,
                 loose: bool = True) -> tuple[str, tuple[str, ...]] | None:
    """(mode, matching paths) of a path token; modes ``doc``, ``root``, ``suffix``, ``basename``.

    ``loose=False`` tries only ``doc`` and ``root``; suffix and basename matching needs a
    listed tree (frozensets) and is skipped otherwise.
    """
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
    if not loose or not isinstance(files, frozenset) or not isinstance(dirs, frozenset):
        return None
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


def tree_match(token: dict[str, Any], files: Paths, dirs: Paths) -> str | None:
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


def resolve_token(token: dict[str, Any], files: Paths, dirs: Paths,
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


# -- resolution at HEAD ----------------------------------------------------------------------

CHECKED_KINDS = ("path", "anchor")


class Resolver:
    """Resolves path and anchor tokens against HEAD's tree."""

    def __init__(self, root: Path, history: History | None = None) -> None:
        self.root = root
        self.history = history or History(root)
        self.files, self.dirs = self.history.head_files()

    def _read_head(self, path: str) -> str | None:
        return self.history.show("HEAD", path)

    def _on_disk(self, token: dict[str, Any]) -> bool:
        """Ruling R66: a path absent from HEAD but present in the working tree (untracked or
        ignored, such as a once-tracked runtime artefact) counts as resolved."""
        if token["kind"] != "path":
            return False
        for p in _strict_paths(str(token["text"]), token["doc"]):
            try:
                where = self.root / p
                if where.is_file() or (where.is_dir() and any(
                        x.is_file() for x in where.rglob("*"))):
                    return True  # an empty directory is a leftover of a move, not a path
            except (OSError, ValueError):
                continue
        return False

    def candidate(self, token: dict[str, Any]) -> dict[str, Any] | None:
        """The token with ``resolved`` and ``resolved_to``; None for a kind not checked."""
        if token["kind"] not in CHECKED_KINDS:
            return None
        found = resolve_token(token, self.files, self.dirs, self._read_head)
        return dict(token, resolved=found is not None or self._on_disk(token),
                    resolved_to=found)


def run(root: Path, workdir: Path, history: History | None = None) -> dict[str, Any]:
    """Resolve every path and anchor token of ``workdir/tokens.json``; write
    ``candidates.json``."""
    for name in ("inventory.json", "tokens.json"):
        if not (workdir / name).is_file():
            raise StepError(f"missing {workdir / name}; run the earlier steps first", EXIT_MISSING)
    tokens = read_json(workdir / "tokens.json")
    resolver = Resolver(root, history)
    candidates = [c for doc in sorted(tokens["docs"]) for t in tokens["docs"][doc]
                  if (c := resolver.candidate(t)) is not None]
    candidates.sort(key=lambda c: (c["doc"], c["line"], c["col"], c["end_col"], c["kind"]))
    result = {"candidates": candidates}
    write_json(workdir / "candidates.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve path and anchor tokens against HEAD.")
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
