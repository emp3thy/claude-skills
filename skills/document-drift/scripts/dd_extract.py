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
"""
from __future__ import annotations

import argparse
import bisect
import re
import sys
from pathlib import Path
from typing import Any

from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_md_scan import Block, Inline, Scan, scan

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

_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:(?!\d)|//|www\.")
_LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")
_LINE_FRAGMENT = re.compile(r"L\d+")
_PLACEHOLDER = re.compile(r"(?i)\b(your|my)[-_]|\bexample\b|\b(foo|bar|baz|xxx|todo)\b")
_PLACEHOLDER_PARTS = ("<", ">", "{{", "${", "*")
_RATIO = re.compile(r"\w{1,3}/\w{1,3}")
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
_RUNTIME = r"(?i)\b(python|node(?:\.js)?|go|golang|rust)"
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
_TREE_COMMENT = re.compile(r"\s+(?:#|<-|←)")
_DIR_NAME = re.compile(r"[ \t]*[^\s│|├└]+/[ \t]*")
_MARKER = re.compile(r"drift-ignore(?P<kind>-next-line|-file)?(?:\s*:(?P<reason>.*))?", re.DOTALL)
# Generated-region markers (spec 8). Begin markers must open the line, so a marker quoted in
# prose or inline code does not open a region; end markers may follow content on the line.
_GENERATED = (
    (re.compile(r"\s*<!--\s*BEGIN mdsh\s*-->"), re.compile(r"<!--\s*END mdsh\s*-->")),
    (re.compile(r"\s*(?:<!--\s*)?\[\[\[cog"), re.compile(r"\[\[\[end\]\]\]")),
    (re.compile(r"\s*<!--\s*BEGIN_TF_DOCS\s*-->"), re.compile(r"<!--\s*END_TF_DOCS\s*-->")),
    (re.compile(r"\s*<!--\s*BEGIN GENERATED"), re.compile(r"<!--\s*END GENERATED")),
)
_EMBEDME = re.compile(r"\s*<!--\s*embedme\b")


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
    if _RATIO.fullmatch(text) and "." not in text:
        return False
    return not (_CREATE.search(line) or _CREATE.search(prev))


def _split_target(raw: str) -> tuple[str, int, str | None, int]:
    """(path text, path span end, fragment or None, fragment start) of a reference as written.

    A ``#L<n>`` fragment and a ``:<n>[-<m>]`` suffix stay in the span but not in the text; a
    ``?query`` is in neither.
    """
    frag: str | None = None
    frag_start = -1
    hash_at = raw.find("#")
    if hash_at >= 0 and _LINE_FRAGMENT.match(raw, hash_at + 1):
        path, span_end = raw[:hash_at], len(raw)
    else:
        if hash_at >= 0:
            frag, frag_start, raw = raw[hash_at + 1 :], hash_at + 1, raw[:hash_at]
        query = raw.find("?")
        path = raw[:query] if query >= 0 else raw
        span_end = len(path)
    if m := _LINE_SUFFIX.search(path):
        path = path[: m.start()]
    return path, span_end, frag, frag_start


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


def _tree_shape(lines: list[str]) -> bool:
    hits = sum(1 for t in lines if _glyph(t) or _DIR_NAME.fullmatch(t))
    return hits >= 2


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

    def block_of(self, idx: int, kind: str | None = None) -> dict[str, Any]:
        b = self.sc.blocks[idx]
        return {"kind": kind or b.kind, "line_start": b.line_start, "line_end": b.line_end}

    def add(self, kind: str, line: int, col: int, end_col: int, text: str, context: str,
            block: dict[str, Any], source: int | None = None, **extra: Any) -> None:
        tok: dict[str, Any] = {
            "doc": self.doc, "line": line, "col": col, "end_col": end_col, "kind": kind,
            "text": text, "target_doc": None, "script_tool": None, "version": None,
            "context": context, "link": None, "block": block, "subject": False,
            "heading_path": [], "never_edit": False, "generated": False, "ignored": None,
            "editable": True,
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
        path, span_end, _, _ = _split_target(text.strip())
        if is_path(path, self.line(inl.line), self.line(inl.line - 1)):
            line, col, end_col = self.code_span(inl, lead, lead + span_end)
            self.add("path", line, col, end_col, path, "inline-code", block, idx,
                     editable=editable)
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
        path, span_end, frag, frag_start = _split_target(raw)
        has_path = is_path(path, self.line(inl.line), self.line(inl.line - 1))
        if has_path:
            self.add("path", inl.line, inl.col, inl.col + span_end, path, inl.kind, block, idx,
                     link=link, editable=editable)
        markdown_target = not path or path.lower().endswith((".md", ".markdown"))
        if (frag and markdown_target and (has_path or not path)
                and not any(p in frag for p in ("<", ">", "{", "$", "*", "#"))):
            self.add("anchor", inl.line, inl.col + frag_start, inl.col + frag_start + len(frag),
                     frag, inl.kind, block, idx, link=link, editable=editable,
                     target_doc=path or self.doc)

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
                    path, span_end, _, _ = _split_target(m[group])
                    if is_path(path, text, self.line(no - 1)):
                        start = m.start(group)
                        self.add("path", no, start, start + span_end, path, "fence", block)
                if info in SHELL_INFOS:
                    for tool, name, a, b2 in _scripts(text):
                        self.add("script", no, a, b2, name, "fence", block, script_tool=tool)

    def tree(self, idx: int, body: list[int]) -> None:
        block = self.block_of(idx, "tree")
        rows = [(no, self.line(no)) for no in body if self.line(no).strip()]
        base = min(len(t) - len(t.lstrip()) for _, t in rows)
        first = rows[0][1]
        indent = len(first) - len(first.lstrip())
        if (not _glyph(first) and re.fullmatch(r"[ \t]*(?:[^\s/]+/|\./?)[ \t]*", first)
                and all(_glyph(t) or len(t) - len(t.lstrip()) > indent for _, t in rows[1:])):
            rows = rows[1:]  # a root label, not an entry
        stack: list[tuple[int, str]] = []
        for no, t in rows:
            glyph = _glyph(t)
            if glyph:
                level_col, start = glyph.start(), glyph.end()
            else:
                prefix = _TREE_PREFIX.match(t)
                start = level_col = prefix.end() if prefix else 0
            name = _TREE_COMMENT.split(t[start:], 1)[0].rstrip()
            if not name or _BOX_CHARS.search(name):
                continue
            level = (level_col - base) // 4
            while stack and stack[-1][0] >= level:
                stack.pop()
            if name in ("...", "…"):
                continue
            path = "/".join([s for _, s in stack] + [name])
            stack.append((level, name.rstrip("/")))
            if (any(c.isspace() for c in path) or ":" in path
                    or any(p in path for p in _PLACEHOLDER_PARTS) or _PLACEHOLDER.search(path)):
                continue
            self.add("tree", no, start, start + len(name), path, "tree", block)

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
        out: list[dict[str, Any]] = []
        for c in self.sc.comments:
            m = _MARKER.fullmatch(c.body)
            if m is None or m["kind"] == "-file":
                continue
            reason = (m["reason"] or "").strip() or None
            start: int | None
            end: int | None
            if m["kind"] == "-next-line":
                start = end = c.line_end + 1 if c.line_end < self.count else None
            else:
                start, end = self.next_block(c.line_end)
            out.append({
                "doc": self.doc, "line": c.line_start, "kind": "drift-ignore" + (m["kind"] or ""),
                "reason": reason, "target_line_start": start, "target_line_end": end,
            })
        return out

    def block_after(self, line: int) -> Block | None:
        """The outermost non-blank block starting first after ``line``."""
        cands = [b for b in self.sc.blocks if b.line_start > line and b.kind != "blank"]
        return min(cands, key=lambda b: (b.line_start, -b.line_end)) if cands else None

    def next_block(self, after: int) -> tuple[int | None, int | None]:
        top = self.block_after(after)
        if top is None:
            return None, None
        end = top.line_end
        if top.kind == "list_item":  # the next block is the whole list
            end = max(b.line_end for b in self.sc.blocks if b.list_id == top.list_id)
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
                    if nxt is not None and nxt.kind == "fence":
                        regions.append((nxt.line_start, nxt.line_end))
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
                    or (b.kind == "table_row" and inl.cell == 0)):
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
