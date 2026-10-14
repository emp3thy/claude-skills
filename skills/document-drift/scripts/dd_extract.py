"""Typed token extraction: paths, anchors, scripts, versions and tree entries -> tokens.json.

``tokens.json`` is ``{"docs": {doc: [Token...]}, "markers": [...], "skipped": [...]}``; the Token
shape is the shared contract in the plan. Tokens within a doc are ordered by (line, col).

Sources (spec section 5, phase 1):

- ``code``, ``link``, ``image`` and ``refdef`` inlines give path tokens; link, image and refdef
  targets also give anchor tokens. ``reflink``/``refimage`` usages give nothing: their span is the
  lookup label and the target is written at the definition. Autolinks are URLs.
- Fence lines give path tokens only as command arguments, and script tokens in shell fences.
  A fence with empty or ``text``/``txt`` info that looks like a directory tree gives tree tokens.
- Version floors come from the raw lines of paragraphs, list items, table rows and headings.

A token from an inline whose span crosses a line break is not ``editable``; when its text cannot
be placed on the inline's first line it keeps the whole inline span.

Beyond the shared Token shape (controller rulings R13 to R17): a path span covers exactly its
``text``; a table header row's block kind is ``table_header``; every Token has ``tree_label``
(the first ``name`` of a labelled tree, else null); anchor ``target_doc`` is repository-relative.
"""
from __future__ import annotations

import argparse
import bisect
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_md_scan import Inline, Scan, scan

KNOWN_EXTS = frozenset(
    {
        # code
        ".py", ".pyi", ".pyx", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts",
        ".go", ".rs", ".java", ".kt", ".kts", ".scala", ".groovy", ".gradle", ".rb", ".php",
        ".cs", ".fs", ".vb", ".swift", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".ino",
        ".lua", ".pl", ".pm", ".jl", ".dart", ".ex", ".exs", ".erl", ".hrl", ".clj", ".cljs",
        ".elm", ".hs", ".ml", ".mli", ".nim", ".zig", ".sol", ".vue", ".svelte", ".sql",
        ".graphql", ".gql", ".proto", ".tf", ".tfvars", ".hcl", ".nix", ".cmake", ".mk",
        ".feature", ".ipynb",
        # config and data
        ".json", ".jsonc", ".json5", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
        ".properties", ".xml", ".plist", ".lock", ".csv", ".tsv",
        # docs and assets
        ".md", ".markdown", ".mdx", ".rst", ".txt", ".adoc", ".html", ".htm", ".css", ".scss",
        ".sass", ".less", ".tex", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
        ".ico",
        # scripts
        ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".psd1", ".bat", ".cmd",
    }
)
SHELL_INFOS = frozenset({"", "bash", "sh", "shell", "console", "zsh", "powershell", "ps1", "pwsh",
                         "cmd"})
TREE_INFOS = frozenset({"", "text", "txt"})
PM_BUILTINS = frozenset({"install", "add", "remove", "init", "upgrade", "dlx", "exec", "create",
                         "why", "link", "publish", "version", "info", "run"})
SUBJECT_KINDS = frozenset({"code", "link", "image", "refdef"})
VERSION_PROSE_BLOCKS = frozenset({"paragraph", "list_item", "table_row", "heading"})
_TABLE_KINDS = frozenset({"table_row", "table_delim"})

_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:(?!\d)|//|www\.")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_LINE_FRAGMENT = re.compile(r"L\d+")
_CITE_FRAGMENT = re.compile(r"L(\d+)(?:-L?(\d+))?")
_CITE_SUFFIX = re.compile(r":(\d+)(?:-(\d+))?$")
_PLACEHOLDER = re.compile(r"(?i)\b(your|my)[-_]|\bexample\b|\b(foo|bar|baz|xxx|todo)\b")
_PLACEHOLDER_PARTS = ("<", ">", "{{", "${", "*")
_RATIO = re.compile(r"\d+/\d+|[A-Za-z]/[A-Za-z]")  # ruling R14: 3/5, X/Y
_CALL = re.compile(r"^\w+\(|\)$")
_CREATE = re.compile(r"(?i)\b(?:mkdir|touch|create|creates|new file)\b")
_ARG_CHARS = r"[^\s'\"`;|&<>()]"
_FENCE_ARG = re.compile(
    r"(?<![\w./\-])(?:(?:python3?|bash|sh|pwsh|node)[ \t]+(?P<arg>(?!-)" + _ARG_CHARS + r"+)"
    r"|(?P<dot>\./" + _ARG_CHARS + r"+))"
)
_PROMPT = re.compile(r"[ \t]*(?:[$>][ \t]+)?")
_SEP = re.compile(r"&&|\|\||;|\|")
_GAP = re.compile(r"[ \t]+")
_TOOL = re.compile(r"(make|npm|yarn|pnpm|just|task)[ \t]+")
_WORD = re.compile(r"[A-Za-z0-9_][\w:.\-]*(?=$|[ \t;&|)])")
# Ruling R59: the runtime word starts a word that no `.`, `-` or word character precedes, so a
# package name such as `opencv-python>=4.8` or `my.node >= 2` is not a runtime floor.
_RUNTIME = r"(?i)(?<![\w.-])(python|node(?:\.js)?|go|golang|rust)"
_VERSIONS = (
    re.compile(
        _RUNTIME + r"\s+(?:version\s+)?(?:>=\s*|≥\s*|v)?(\d+(?:\.\d+){0,2})\s*"
        r"(\+|or (?:later|newer|higher|above))"
    ),
    re.compile(_RUNTIME + r"\s*>=\s*(\d+(?:\.\d+){0,2})"),
)
_RUNTIME_NAMES = {"python": "python", "node": "node", "node.js": "node", "go": "go",
                  "golang": "go", "rust": "rust"}
# A tree glyph followed by a space and a name (box-drawing borders such as ├────┤ are not);
# its match ends where the name starts.
_GLYPH = re.compile(r"(?:├──|└──|\|--|`--)[─-]*[ \t]+(?=\S)")
_TREE_PREFIX = re.compile(r"[\s│|]*")
_BOX_CHARS = re.compile(r"[─-╿]")
_TREE_NAME_END = re.compile(r"\s+(?:#|<-|←)|\s{2,}|\t")
# A marker comment's body. Ruling R66: a body with no colon after the marker word, or with an
# empty reason after it, is a marker without a reason (reported, never honoured).
_MARKER = re.compile(
    r"drift-ignore(?P<kind>-next-line|-file)?(?:\s*:(?P<reason>.*)|\s+(?P<bare>.*))?", re.DOTALL)
# Generated-region markers (spec 8). Begin markers must open the line, so a marker quoted in
# prose or inline code does not open a region; end markers may follow content on the line.
_GENERATED = (
    (re.compile(r"\s*<!--\s*BEGIN mdsh\s*-->"), re.compile(r"<!--\s*END mdsh\s*-->")),
    (re.compile(r"\s*(?:<!--\s*)?\[\[\[cog"), re.compile(r"\[\[\[end\]\]\]")),
    (re.compile(r"\s*<!--\s*BEGIN_TF_DOCS\s*-->"), re.compile(r"<!--\s*END_TF_DOCS\s*-->")),
    (re.compile(r"\s*<!--\s*BEGIN GENERATED"), re.compile(r"<!--\s*END GENERATED")),
)
_EMBEDME = re.compile(r"\s*<!--\s*embedme\b")


def parse_marker(body: str) -> tuple[str, str | None] | None:
    """``(kind, reason)`` of a ``drift-ignore`` comment body, or None when it is not one.

    ``kind`` is ``drift-ignore``, ``drift-ignore-next-line`` or ``drift-ignore-file``. The
    reason is None when the marker has no colon or nothing after it (ruling R66): such a
    marker is reported as a marker without a reason and suppresses nothing.
    """
    m = _MARKER.fullmatch(body)
    if m is None:
        return None
    return "drift-ignore" + (m["kind"] or ""), (m["reason"] or "").strip() or None


def _ext(text: str) -> str:
    name = text.rstrip("/").rsplit("/", 1)[-1]
    dot = name.rfind(".")
    return name[dot:].lower() if dot > 0 else ""


def is_path(text: str, line: str, prev: str) -> bool:
    """True when ``text`` reads as a repository path (spec 5 shape and placeholder filters)."""
    if not text or any(c.isspace() for c in text) or not re.search(r"\w", text):
        return False
    if _URL.match(text) or text.startswith("~") or any(c in text for c in ':$"\'='):
        return False  # URLs, host:port, home and env-var paths, quoted or key=value text
    if _CALL.search(text):
        return False  # call syntax such as join(a/b)
    if any(p in text for p in _PLACEHOLDER_PARTS) or _PLACEHOLDER.search(text):
        return False
    if "/" not in text and _ext(text) not in KNOWN_EXTS:
        return False
    if text.startswith("/") and "/" not in text[1:]:
        return False  # URL routes and slash commands
    if _RATIO.fullmatch(text):
        return False
    return not (_CREATE.search(line) or _CREATE.search(prev))


def _split_target(raw: str) -> tuple[str, str | None, int]:
    """(path text, fragment or None, fragment start) of a reference as written.

    The path is a prefix of ``raw``, so its span is ``[0, len(path))``. A ``#L<n>`` fragment, a
    ``:<n>[-<m>]`` suffix and a ``?query`` are in neither the text nor the span (ruling R13).
    """
    frag: str | None = None
    frag_start = -1
    hash_at = raw.find("#")
    if hash_at >= 0 and _LINE_FRAGMENT.match(raw, hash_at + 1):
        path = raw[:hash_at]
    else:
        if hash_at >= 0:
            frag, frag_start, raw = raw[hash_at + 1 :], hash_at + 1, raw[:hash_at]
        query = raw.find("?")
        path = raw[:query] if query >= 0 else raw
    if m := _LINE_SUFFIX.search(path):
        path = path[: m.start()]
    return path, frag, frag_start


def _cite_of(raw: str) -> tuple[str, int, int] | None:
    """(text as written, start, end) of a ``path:N``, ``path:N-M`` or ``path#LN`` reference.

    The text runs from the start of ``raw`` to the end of the line suffix or fragment; None when
    ``raw`` carries no line (``start == end`` for a single line).
    """
    hash_at = raw.find("#")
    if hash_at >= 0:
        m = _CITE_FRAGMENT.match(raw, hash_at + 1)
        if m is None or hash_at == 0:
            return None
        first = int(m[1])
        return raw[: m.end()], first, int(m[2]) if m[2] else first
    path = raw[: raw.find("?")] if "?" in raw else raw
    m = _CITE_SUFFIX.search(path)
    if m is None or m.start() == 0:
        return None
    first = int(m[1])
    return path, first, int(m[2]) if m[2] else first


def _command_starts(s: str) -> list[int]:
    """Where commands start in a shell line: after an optional prompt and after && || ; |."""
    prompt = _PROMPT.match(s)
    starts = []
    for p in [prompt.end() if prompt else 0, *(m.end() for m in _SEP.finditer(s))]:
        while p < len(s) and s[p] in " \t":
            p += 1
        starts.append(p)
    return starts


def _scripts(s: str) -> list[tuple[str, str, int, int]]:
    """(tool, name, start, end) of each script invocation at a command position of ``s``."""
    found: list[tuple[str, str, int, int]] = []
    for p in _command_starts(s):
        tool = _TOOL.match(s, p)
        if tool is None:
            continue
        name, words = tool[1], []
        w = _WORD.match(s, tool.end())
        while w is not None:
            words.append(w)
            if name != "make":
                break
            nxt = _GAP.match(s, w.end())
            w = _WORD.match(s, nxt.end()) if nxt else None
        if not words:
            continue
        first = words[0]
        if name in ("npm", "yarn", "pnpm"):
            if first[0] == "run":
                gap = _GAP.match(s, first.end())
                target = _WORD.match(s, gap.end()) if gap else None
                words = [target] if target else []
            elif name == "npm" or first[0] in PM_BUILTINS:
                words = []
        found.extend((name, w[0], w.start(), w.end()) for w in words)
    return found


def _glyph(t: str) -> re.Match[str] | None:
    """The tree glyph of an entry line, when only tree rails and spaces precede it."""
    m = _GLYPH.search(t)
    return m if m and _TREE_PREFIX.fullmatch(t, 0, m.start()) else None


_TreeEntry = tuple[int, int, bool, str]  # (column, name start, has glyph, name)


def _tree_entry(t: str) -> _TreeEntry | None:
    """A tree line's entry, or None for a line of rails only.

    The column is the glyph's for a glyph line and the name's otherwise. The name ends at a
    ``#``/``<-``/``←`` comment or at a run of two or more spaces (a description column).
    """
    glyph = _glyph(t)
    if glyph:
        col, start = glyph.start(), glyph.end()
    else:
        prefix = _TREE_PREFIX.match(t)
        col = start = prefix.end() if prefix else 0
    name = _TREE_NAME_END.split(t[start:], 1)[0].rstrip()
    return (col, start, glyph is not None, name) if name else None


def _unit(cols: list[int], base: int) -> int:
    """The smallest positive step between distinct indentation columns (4 when none)."""
    levels = sorted({base, *cols})
    steps = [b - a for a, b in zip(levels, levels[1:], strict=False) if b > a]
    return min(steps) if steps else 4


def _tree_shape(lines: list[str]) -> bool:
    """Ruling R16: two glyph lines, or an indented list of single names with two ``name/``."""
    if sum(1 for t in lines if _glyph(t)) >= 2:
        return True
    entries = [_tree_entry(t) for t in lines]
    names: list[_TreeEntry] = [e for e in entries if e is not None]
    if len(names) != len(lines) or any(any(c.isspace() for c in e[3]) for e in names):
        return False
    if sum(1 for e in names if e[3].endswith("/")) < 2:
        return False
    return any(
        e[3].endswith("/") and later[0] > e[0]
        for i, e in enumerate(names)
        for later in names[i + 1 :]
    )


class _Extractor:
    def __init__(self, doc: str, text: str, never_edit_re: re.Pattern[str]) -> None:
        self.doc = doc
        self.never = never_edit_re
        self.sc: Scan = scan(text)
        self.lines = self.sc.lines
        self.count = len(self.lines) - 1 if self.lines and self.lines[-1] == "" else len(self.lines)
        self.tokens: list[dict[str, Any]] = []
        self.sources: list[int | None] = []  # inline index behind each token, for `subject`

    # -- helpers ---------------------------------------------------------------------------

    def line(self, no: int) -> str:
        return self.lines[no - 1] if 1 <= no <= len(self.lines) else ""

    def is_header(self, idx: int) -> bool:
        """A table header row: a ``table_row`` followed by the ``table_delim`` line."""
        blocks = self.sc.blocks
        return (blocks[idx].kind == "table_row" and idx + 1 < len(blocks)
                and blocks[idx + 1].kind == "table_delim")

    def block_of(self, idx: int, kind: str | None = None) -> dict[str, Any]:
        b = self.sc.blocks[idx]
        kind = kind or ("table_header" if self.is_header(idx) else b.kind)
        return {"kind": kind, "line_start": b.line_start, "line_end": b.line_end}

    def add(self, kind: str, line: int, col: int, end_col: int, text: str, context: str,
            block: dict[str, Any], source: int | None = None, **extra: Any) -> None:
        tok: dict[str, Any] = {
            "doc": self.doc, "line": line, "col": col, "end_col": end_col, "kind": kind,
            "text": text, "target_doc": None, "script_tool": None, "version": None,
            "context": context, "link": None, "block": block, "subject": False,
            "heading_path": [], "never_edit": False, "generated": False, "ignored": None,
            "editable": True, "tree_label": None,
        }
        tok.update(extra)
        self.tokens.append(tok)
        self.sources.append(source)

    # -- inlines -----------------------------------------------------------------------------

    def inlines(self) -> None:
        for idx, inl in enumerate(self.sc.inlines):
            if inl.kind == "code":
                self.code(idx, inl)
            elif inl.kind in ("link", "image", "refdef"):
                self.target(idx, inl)

    def code_span(self, inl: Inline, a: int, b: int) -> tuple[int, int, int]:
        if inl.line == inl.end_line or b <= len(self.line(inl.line)) - inl.col:
            return inl.line, inl.col + a, inl.col + b
        return inl.line, inl.col, inl.end_col

    def code(self, idx: int, inl: Inline) -> None:
        block = self.block_of(inl.block)
        editable = inl.line == inl.end_line
        text = inl.text
        lead = len(text) - len(text.lstrip())
        path, _, _ = _split_target(text.strip())
        if is_path(path, self.line(inl.line), self.line(inl.line - 1)):
            line, col, end_col = self.code_span(inl, lead, lead + len(path))
            self.add("path", line, col, end_col, path, "inline-code", block, idx,
                     editable=editable)
            if cite := _cite_of(text.strip()):
                line, col, end_col = self.code_span(inl, lead, lead + len(cite[0]))
                self.add("cite", line, col, end_col, cite[0], "inline-code", block, idx,
                         editable=editable, path=path, start=cite[1], end=cite[2])
        for tool, name, a, b in _scripts(text):
            line, col, end_col = self.code_span(inl, a, b)
            self.add("script", line, col, end_col, name, "inline-code", block, idx,
                     script_tool=tool, editable=editable)

    def target(self, idx: int, inl: Inline) -> None:
        raw = self.line(inl.line)[inl.col : inl.end_col] if inl.line == inl.end_line else inl.text
        if not raw or _URL.match(raw):
            return
        link = None
        if inl.kind == "link" and inl.outer_col is not None and inl.outer_end_col is not None:
            link = {"col": inl.outer_col, "end_col": inl.outer_end_col, "text": inl.label}
        block = self.block_of(inl.block)
        editable = inl.line == inl.end_line
        path, frag, frag_start = _split_target(raw)
        has_path = is_path(path, self.line(inl.line), self.line(inl.line - 1))
        if has_path:
            self.add("path", inl.line, inl.col, inl.col + len(path), path, inl.kind, block, idx,
                     link=link, editable=editable)
            if cite := _cite_of(raw):
                self.add("cite", inl.line, inl.col, inl.col + len(cite[0]), cite[0], inl.kind,
                         block, idx, link=link, editable=editable, path=path, start=cite[1],
                         end=cite[2])
        markdown_target = not path or path.lower().endswith((".md", ".markdown"))
        if (frag and markdown_target and (has_path or not path)
                and not any(p in frag for p in ("<", ">", "{", "$", "*", "#"))):
            self.add("anchor", inl.line, inl.col + frag_start, inl.col + frag_start + len(frag),
                     frag, inl.kind, block, idx, link=link, editable=editable,
                     target_doc=self.repo_path(path) if path else self.doc)

    def repo_path(self, path: str) -> str:
        """A link path part as a repository-relative path (ruling R17)."""
        base = "" if path.startswith("/") else posixpath.dirname(self.doc)
        return posixpath.normpath(posixpath.join(base, path.lstrip("/")))

    # -- fences ------------------------------------------------------------------------------

    def fences(self) -> None:
        for idx, b in enumerate(self.sc.blocks):
            if b.kind != "fence":
                continue
            last = b.line_end - 1 if b.closed else b.line_end
            body = list(range(b.line_start + 1, last + 1))
            words = (b.info or "").split()
            info = words[0].lower() if words else ""
            rows = [self.line(no) for no in body if self.line(no).strip()]
            if info in TREE_INFOS and _tree_shape(rows):
                self.tree(idx, body)
                continue
            block = self.block_of(idx)
            for no in body:
                text = self.line(no)
                starts = _command_starts(text)
                for m in _FENCE_ARG.finditer(text):
                    group = "arg" if m["arg"] is not None else "dot"
                    if group == "dot" and m.start(group) not in starts:
                        continue  # ./x counts only when it is the command being run
                    path, _, _ = _split_target(m[group])
                    if is_path(path, text, self.line(no - 1)):
                        start = m.start(group)
                        self.add("path", no, start, start + len(path), path, "fence", block)
                if info in SHELL_INFOS:
                    for tool, name, a, b2 in _scripts(text):
                        self.add("script", no, a, b2, name, "fence", block, script_tool=tool)

    def tree(self, idx: int, body: list[int]) -> None:
        """Tree tokens of a fence (ruling R16).

        Levels count indentation units: for glyph lines the step between glyph columns, for
        plain lines the smallest positive indentation step. A name with no glyph is the parent
        of glyph lines at its own level. A first ``name/`` line whose following lines are all
        its descendants stays in every path and is reported as ``tree_label``; a first ``.`` or
        ``./`` line is the repository root and is dropped.
        """
        block = self.block_of(idx, "tree")
        entries = [(no, e) for no in body if (e := _tree_entry(self.line(no))) is not None]
        if entries and not entries[0][1][2] and entries[0][1][3] in (".", "./"):
            entries = entries[1:]
        if not entries:
            return
        base = min(e[0] for _, e in entries)
        unit_glyph = _unit([e[0] for _, e in entries if e[2]], base)
        unit_plain = _unit([e[0] for _, e in entries if not e[2]], base)
        label: str | None = None
        col0, _, glyph0, name0 = entries[0][1]
        if (not glyph0 and name0.endswith("/") and not any(c.isspace() for c in name0)
                and len(entries) > 1
                and all((e[2] and e[0] >= col0) or e[0] > col0 for _, e in entries[1:])):
            label = name0.rstrip("/")
        stack: list[tuple[tuple[int, int], str]] = []
        for no, (col, start, glyph, name) in entries:
            if _BOX_CHARS.search(name):
                continue
            key = ((col - base) // (unit_glyph if glyph else unit_plain), int(glyph))
            while stack and stack[-1][0] >= key:
                stack.pop()
            if name in ("...", "…"):
                continue
            path = "/".join([s for _, s in stack] + [name])
            stack.append((key, name.rstrip("/")))
            # placeholder filters apply below the label: `my-project/` is a common label
            own = path[len(label) + 1 :] if label is not None else path
            if (any(c.isspace() for c in path) or ":" in path
                    or any(p in own for p in _PLACEHOLDER_PARTS) or _PLACEHOLDER.search(own)):
                continue
            self.add("tree", no, start, start + len(name), path, "tree", block, tree_label=label)

    # -- versions ----------------------------------------------------------------------------

    def innermost(self) -> dict[int, int]:
        best: dict[int, int] = {}
        for idx, b in enumerate(self.sc.blocks):
            for no in range(b.line_start, b.line_end + 1):
                cur = best.get(no)
                if cur is None:
                    best[no] = idx
                    continue
                c = self.sc.blocks[cur]
                if b.line_end - b.line_start <= c.line_end - c.line_start:
                    best[no] = idx
        return best

    def versions(self) -> None:
        codes = [i for i in self.sc.inlines if i.kind == "code" and i.line == i.end_line]
        for no, idx in sorted(self.innermost().items()):
            if self.sc.blocks[idx].kind not in VERSION_PROSE_BLOCKS:
                continue
            text, seen = self.line(no), set()
            for pattern in _VERSIONS:
                for m in pattern.finditer(text):
                    a, b = m.span(2)
                    if (a, b) in seen:
                        continue
                    seen.add((a, b))
                    in_code = any(c.line == no and c.col <= a < c.end_col for c in codes)
                    runtime = _RUNTIME_NAMES[m[1].lower()]
                    self.add("version", no, a, b, m[2], "inline-code" if in_code else "prose",
                             self.block_of(idx), version={"runtime": runtime, "floor": m[2]})

    # -- flags -------------------------------------------------------------------------------

    def markers(self) -> list[dict[str, Any]]:
        """Block and line markers, and a file marker without a reason (ruling R66: it does not
        exclude the doc, so it is reported here; one with a reason never reaches extraction)."""
        out: list[dict[str, Any]] = []
        for c in self.sc.comments:
            parsed = parse_marker(c.body)
            if parsed is None:
                continue
            kind, reason = parsed
            start: int | None = None
            end: int | None = None
            if kind == "drift-ignore-file":
                if reason is not None:
                    continue
            elif kind == "drift-ignore-next-line":
                start = end = c.line_end + 1 if c.line_end < self.count else None
            else:
                start, end = self.next_block(c.line_end)
            out.append({
                "doc": self.doc, "line": c.line_start, "kind": kind,
                "reason": reason, "target_line_start": start, "target_line_end": end,
            })
        return out

    def block_after(self, line: int) -> int | None:
        """Index of the outermost non-blank block starting first after ``line``."""
        blocks = self.sc.blocks
        cands = [i for i, b in enumerate(blocks) if b.line_start > line and b.kind != "blank"]
        if not cands:
            return None
        return min(cands, key=lambda i: (blocks[i].line_start, -blocks[i].line_end, i))

    def next_block(self, after: int) -> tuple[int | None, int | None]:
        """Lines a ``drift-ignore`` covers: the next block, a whole list or a whole table."""
        blocks = self.sc.blocks
        idx = self.block_after(after)
        if idx is None:
            return None, None
        top = blocks[idx]
        end = top.line_end
        if top.kind == "list_item":
            end = max(b.line_end for b in blocks if b.list_id == top.list_id)
        elif top.kind in _TABLE_KINDS:
            while idx + 1 < len(blocks) and blocks[idx + 1].kind in _TABLE_KINDS:
                idx += 1
            end = blocks[idx].line_end
        return top.line_start, end

    def generated(self) -> list[tuple[int, int]]:
        code: set[int] = set()
        for b in self.sc.blocks:
            if b.kind in ("fence", "indented_code"):
                code.update(range(b.line_start, b.line_end + 1))
        regions: list[tuple[int, int]] = []
        open_at: tuple[int, re.Pattern[str]] | None = None
        for no in range(1, self.count + 1):
            if no in code:
                continue
            t = self.line(no)
            if open_at is not None:
                if open_at[1].search(t):
                    regions.append((open_at[0], no))
                    open_at = None
                continue
            for begin, end in _GENERATED:
                if m := begin.match(t):
                    if end.search(t, m.end()):
                        regions.append((no, no))
                    else:
                        open_at = (no, end)
                    break
            else:
                if _EMBEDME.match(t):  # embedme covers the fenced block that follows
                    nxt = self.block_after(no)
                    if nxt is not None and self.sc.blocks[nxt].kind == "fence":
                        regions.append((self.sc.blocks[nxt].line_start,
                                        self.sc.blocks[nxt].line_end))
        if open_at is not None:
            regions.append((open_at[0], self.count))
        return regions

    def heading_paths(self) -> tuple[list[int], list[list[str]]]:
        starts: list[int] = []
        paths: list[list[str]] = []
        stack: list[tuple[int, str]] = []
        for b in sorted((b for b in self.sc.blocks if b.kind == "heading"),
                        key=lambda b: b.line_start):
            level = b.level or 1
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, b.text or ""))
            starts.append(b.line_start)
            paths.append([t for _, t in stack])
        return starts, paths

    def subjects(self) -> None:
        firsts: dict[int, int] = {}  # block index -> its first subject-bearing inline
        for idx, inl in enumerate(self.sc.inlines):
            b = self.sc.blocks[inl.block]
            if inl.kind not in SUBJECT_KINDS:
                continue
            if not ((b.kind == "list_item" and inl.line == b.line_start)
                    or (b.kind == "table_row" and inl.cell == 0
                        and not self.is_header(inl.block))):
                continue
            key = (inl.line, inl.outer_col if inl.outer_col is not None else inl.col)
            cur = firsts.get(inl.block)
            if cur is None:
                firsts[inl.block] = idx
            else:
                c = self.sc.inlines[cur]
                if key < (c.line, c.outer_col if c.outer_col is not None else c.col):
                    firsts[inl.block] = idx
        chosen = set(firsts.values())
        done: set[int] = set()
        order = sorted(range(len(self.tokens)),
                       key=lambda k: (self.tokens[k]["line"], self.tokens[k]["col"]))
        for k in order:
            src = self.sources[k]
            if src is not None and src in chosen and src not in done:
                self.tokens[k]["subject"] = True
                done.add(src)

    def run(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self.inlines()
        self.fences()
        self.versions()
        self.subjects()
        markers = self.markers()
        honoured = [m for m in markers if m["reason"] and m["target_line_start"] is not None]
        regions = self.generated()
        starts, paths = self.heading_paths()
        for tok in self.tokens:
            line = tok["line"]
            pos = bisect.bisect_right(starts, line)
            tok["heading_path"] = list(paths[pos - 1]) if pos else []
            tok["never_edit"] = any(self.never.search(h) for h in tok["heading_path"])
            tok["generated"] = any(a <= line <= b for a, b in regions)
            for m in honoured:
                if m["target_line_start"] <= line <= m["target_line_end"]:
                    tok["ignored"] = m["reason"]
                    break
        tokens = sorted(self.tokens, key=lambda t: (t["line"], t["col"], t["end_col"], t["kind"]))
        return tokens, markers


def extract_doc(
    doc: str, text: str, never_edit_re: re.Pattern[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Tokens of one doc, ordered by (line, col), and its drift-ignore markers."""
    return _Extractor(doc, text, never_edit_re).run()


def run(root: Path, workdir: Path) -> dict[str, Any]:
    """Extract tokens from every doc in ``workdir/inventory.json``; write ``tokens.json``."""
    inv_path = workdir / "inventory.json"
    if not inv_path.is_file():
        raise StepError(f"missing {inv_path}; run dd_inventory first", EXIT_MISSING)
    inventory = read_json(inv_path)
    never = re.compile(inventory["never_edit_re"])
    docs: dict[str, list[dict[str, Any]]] = {}
    markers: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for doc in inventory["docs"]:
        try:
            text = (root / doc).read_bytes().decode("utf-8")
        except OSError:
            skipped.append({"doc": doc, "reason": "unreadable"})
            continue
        except UnicodeDecodeError:
            skipped.append({"doc": doc, "reason": "not-utf8"})
            continue
        docs[doc], doc_markers = extract_doc(doc, text, never)
        markers.extend(doc_markers)
    result = {"docs": docs, "markers": markers, "skipped": skipped}
    write_json(workdir / "tokens.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract typed tokens from the docs in scope.")
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
