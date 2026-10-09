"""Markdown block and inline scanner (CommonMark structure plus GFM tables).

Not a renderer: it reports where things are, with 1-based lines and 0-based character columns.
tests/test_dd_md_parity.py checks its spans against markdown-it-py on a fixed corpus.

Block pass: containers (list items, block quotes) are parsed recursively over logical lines,
``(line number, column of the text in the source line, text without the container prefix)``.
Inline pass: each paragraph, heading, list item lead paragraph and table cell is tokenized
with its lines joined by ``\\n`` and a per-character map back to ``(line, col)``, so code spans
and links can cross a line break. Link reference definitions from the whole document are
collected in the block pass and applied in the inline pass.

Conventions beyond the field names:

- A ``list_item`` block spans the whole item. Its inlines are those of the paragraph that starts
  on the marker line; later paragraphs, fences and nested items are blocks whose ``parent`` is
  the item. Blocks inside a block quote keep the quote's own ``parent``.
- Thematic breaks produce no block; ``blank`` is one block per run of blank lines.
- An inline's ``line, col .. end_line, end_col`` (end exclusive) is the code content or the link
  target as written. ``reflink`` and ``refimage`` are a link and an image whose target comes
  from a reference definition; their span is the label used for the lookup, since the target is
  not written there. Each ``refdef`` block has one ``refdef`` inline spanning its destination,
  with ``outer_*`` spanning the definition when it is on one line.
  ``cell`` is the 0-based table cell index of an inline in a ``table_row``, else None.
- ``closed`` is set on fences only: True when a closing fence line exists (``line_end`` is that
  line), False when the fence runs to its container's end. ``list_id`` is shared by the items of
  one list; a different bullet or ordered delimiter, or any block other than a blank line at the
  same level, starts a new list.
  ``outer_col`` (on ``line``) and ``outer_end_col`` (on ``end_line``) bound the whole construct,
  backticks included for code; each is None when the construct starts or ends on another line.
  Email autolinks have text ``mailto:<address>``.
"""

from __future__ import annotations

import html
import re
import string
from dataclasses import dataclass


@dataclass(frozen=True)
class Block:
    kind: str
    line_start: int
    line_end: int
    info: str | None
    level: int | None
    text: str | None
    parent: int | None
    closed: bool | None = None
    list_id: int | None = None


@dataclass(frozen=True)
class Inline:
    kind: str
    line: int
    col: int
    end_line: int
    end_col: int
    text: str
    label: str | None
    outer_col: int | None
    outer_end_col: int | None
    block: int
    cell: int | None = None


@dataclass(frozen=True)
class Comment:
    line_start: int
    line_end: int
    body: str


@dataclass(frozen=True)
class Scan:
    lines: list[str]
    blocks: list[Block]
    inlines: list[Inline]
    comments: list[Comment]


_Line = tuple[int, int, str]
_Pos = tuple[int, int]
_Src = tuple[str, list[_Pos]]  # inline text and the (line, col) of each char, plus one for its end
_Cell = tuple[_Src, int | None]  # an inline source and its table cell index

_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
_ATX = re.compile(r" {0,3}(#{1,6})(?=[ \t]|$)(.*)")
_ATX_CLOSE = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")
_HR = re.compile(r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})")
_SETEXT = re.compile(r" {0,3}(=+|-+)[ \t]*")
_LIST = re.compile(r" {0,3}([-+*]|\d{1,9}[.)])(?=[ \t]|$)")
_QUOTE = re.compile(r" {0,3}> ?")
_DELIM_CELL = re.compile(r":?-+:?")
_REF_LABEL = re.compile(r" {0,3}\[(?P<label>(?:[^\\\[\]]|\\.){1,999})\]:")
_REF_DEST = re.compile(
    r"[ \t]*(?:<(?P<angle>(?:[^\\<>\n]|\\.)*)>|(?P<bare>[^\s<]\S*))"
    r"(?:[ \t]+(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)))?[ \t]*"
)
_UNESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])|&([a-z#][a-z0-9]{1,31});", re.IGNORECASE)
_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.\-]{1,31}:[^<>\x00-\x20]*)>")
_EMAIL = re.compile(
    r"<([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*)>"
)
_ATTR = (
    r"(?:\s+[a-zA-Z_:][a-zA-Z0-9:._-]*"
    r"(?:\s*=\s*(?:[^\"'=<>`\x00-\x20]+|'[^']*'|\"[^\"]*\"))?)"
)
_TAG = r"<[A-Za-z][A-Za-z0-9\-]*" + _ATTR + r"*\s*/?>|</[A-Za-z][A-Za-z0-9\-]*\s*>"
_HTML_INLINE = re.compile(
    "(?:" + _TAG + r"|<!---?>|<!--(?:[^-]|-[^-]|--[^>])*-->|<[?][\s\S]*?[?]>"
    r"|<![A-Za-z][^>]*>|<!\[CDATA\[[\s\S]*?\]\]>)"
)
_BLOCK_NAMES = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|"
    "details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h1|"
    "h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|"
    "noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|"
    "thead|title|tr|track|ul"
)
# (start, end or None for "ends before a blank line", can interrupt a paragraph)
_HTML_BLOCKS: list[tuple[re.Pattern[str], re.Pattern[str] | None, bool]] = [
    (
        re.compile(r"<(?:script|pre|style|textarea)(?=\s|>|$)", re.IGNORECASE),
        re.compile(r"</(?:script|pre|style|textarea)>", re.IGNORECASE),
        True,
    ),
    (re.compile(r"<!--"), re.compile(r"-->"), True),
    (re.compile(r"<\?"), re.compile(r"\?>"), True),
    (re.compile(r"<![A-Z]"), re.compile(r">"), True),
    (re.compile(r"<!\[CDATA\["), re.compile(r"\]\]>"), True),
    (
        re.compile(r"</?(?:" + _BLOCK_NAMES + r")(?=\s|/?>|$)", re.IGNORECASE),
        None,
        True,
    ),
    (re.compile("(?:" + _TAG + r")\s*$"), None, False),
]
_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
_PUNCT = frozenset(string.punctuation)
_MAX_NESTING = 20


def _indent(t: str) -> int:
    width = 0
    for ch in t:
        if ch == " ":
            width += 1
        elif ch == "\t":
            width += 4 - width % 4
        else:
            break
    return width


def _blank(t: str) -> bool:
    return not t.strip()


def _strip_cols(ln: _Line, n: int) -> _Line:
    """Remove up to ``n`` columns of leading whitespace."""
    no, col, t = ln
    width = k = 0
    while k < len(t) and width < n and t[k] in " \t":
        width += 1 if t[k] == " " else 4 - width % 4
        k += 1
    return no, col + k, t[k:]


def _unescape(s: str) -> str:
    return _UNESCAPE.sub(lambda m: m[1] if m[1] else html.unescape(m[0]), s)


def _norm_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).lower().upper()


def _fence_open(t: str) -> re.Match[str] | None:
    m = _FENCE.match(t)
    if m and m[1][0] == "`" and "`" in m[2]:
        return None
    return m


def _html_type(t: str, interrupting: bool) -> int | None:
    if _indent(t) >= 4:
        return None
    s = t.lstrip(" ")
    for k, (start, _, can_interrupt) in enumerate(_HTML_BLOCKS):
        if start.match(s):
            return k if can_interrupt or not interrupting else None
    return None


def _ends_lazy(t: str) -> bool:
    """A line that ends a container's lazy continuation (and a table body)."""
    return bool(
        _fence_open(t)
        or _QUOTE.match(t)
        or _HR.fullmatch(t)
        or _LIST.match(t)
        or _ATX.match(t)
        or _html_type(t, True) is not None
    )


def _track(t: str, fence: str | None, para: bool) -> tuple[str | None, bool]:
    """Follow fences and open paragraphs across a container's lines (for lazy continuation)."""
    if fence:
        c = _FENCE_CLOSE.fullmatch(t)
        if c and c[1][0] == fence[0] and len(c[1]) >= len(fence):
            return None, False
        return fence, False
    if _blank(t):
        return None, False
    if m := _fence_open(t):
        return m[1], False
    if _indent(t) >= 4:
        return None, para
    if _ATX.match(t) or _HR.fullmatch(t):
        return None, False
    return None, True


def _cells(ln: _Line) -> list[_Src]:
    """Split a table row on unescaped pipes like markdown-it's escapedSplit, keeping positions."""
    no, col, t = ln
    base = col + len(t) - len(t.lstrip())
    cells: list[tuple[list[str], list[_Pos]]] = [([], [])]
    escaped = False
    for k, ch in enumerate(t.strip()):
        chars, pos = cells[-1]
        if ch == "|" and not escaped:
            cells.append(([], []))
        else:
            if ch == "|":  # escaped pipe: drop the backslash, keep the pipe
                chars.pop()
                pos.pop()
            chars.append(ch)
            pos.append((no, base + k))
        escaped = ch == "\\"
    if cells and not cells[0][0]:
        cells.pop(0)
    if cells and not cells[-1][0]:
        cells.pop()
    out: list[_Src] = []
    for chars, pos in cells:
        a, b = 0, len(chars)
        while a < b and chars[a].isspace():
            a += 1
        while b > a and chars[b - 1].isspace():
            b -= 1
        end = [(pos[b - 1][0], pos[b - 1][1] + 1)] if b > a else []
        out.append(("".join(chars[a:b]), pos[a:b] + end))
    return out


def _numbered(cells: list[_Src]) -> list[_Cell]:
    return [(c, k) for k, c in enumerate(cells) if c[0]]


def _table_cols(lls: list[_Line], i: int) -> int:
    """Column count when lines i and i+1 open a GFM table, else 0."""
    if i + 1 >= len(lls):
        return 0
    head, delim = lls[i][2], lls[i + 1][2]
    if _indent(head) >= 4 or _indent(delim) >= 4:
        return 0
    d = delim.lstrip(" \t")
    if len(d) < 2 or d[0] not in "|-:" or d[1] not in "|-: \t" or (d[0] == "-" and d[1] in " \t"):
        return 0
    if any(c not in "|-: \t" for c in d):
        return 0
    parts = d.split("|")
    aligns = 0
    for k, part in enumerate(parts):
        part = part.strip()
        if not part:
            if k in (0, len(parts) - 1):
                continue
            return 0
        if not _DELIM_CELL.fullmatch(part):
            return 0
        aligns += 1
    if "|" not in head.strip():
        return 0
    cols = len(_cells(lls[i]))
    return cols if cols and cols == aligns else 0


def _interrupts(lls: list[_Line], j: int) -> bool:
    """Whether line j starts a block that ends the paragraph before it."""
    t = lls[j][2]
    if _fence_open(t) or _ATX.match(t) or _HR.fullmatch(t) or _QUOTE.match(t):
        return True
    if _html_type(t, True) is not None:
        return True
    m = _LIST.match(t)
    if m and t[m.end() :].strip() and (m[1] in "-+*" or int(m[1][:-1]) == 1):
        return True
    return bool(_table_cols(lls, j))


def _trim(lls: list[_Line]) -> list[_Line]:
    out = list(lls)
    no, col, t = out[0]
    lead = len(t) - len(t.lstrip())
    out[0] = (no, col + lead, t[lead:])
    no, col, t = out[-1]
    out[-1] = (no, col, t.rstrip())
    return out


def _src(lls: list[_Line]) -> _Src:
    chars: list[str] = []
    pos: list[_Pos] = []
    end: _Pos = (lls[0][0], lls[0][1])
    for k, (no, col, t) in enumerate(lls):
        if k:
            chars.append("\n")
            pos.append(end)
        chars.append(t)
        pos.extend((no, col + c) for c in range(len(t)))
        end = (no, col + len(t))
    pos.append(end)
    return "".join(chars), pos


class _Scanner:
    def __init__(self) -> None:
        self.blocks: list[Block] = []
        self.sources: dict[int, list[_Cell]] = {}
        self.defs: dict[int, Inline] = {}  # refdef block index -> its destination inline
        self.refs: dict[str, str] = {}
        self.comments: list[Comment] = []
        self.inlines: list[Inline] = []
        self.lists = 0

    def add(
        self,
        kind: str,
        first: _Line,
        last: _Line,
        parent: int | None,
        *,
        info: str | None = None,
        level: int | None = None,
        text: str | None = None,
        src: list[_Cell] | None = None,
        closed: bool | None = None,
        list_id: int | None = None,
    ) -> int:
        block = Block(kind, first[0], last[0], info, level, text, parent, closed, list_id)
        self.blocks.append(block)
        if src:
            self.sources[len(self.blocks) - 1] = src
        return len(self.blocks) - 1

    def parse(self, lls: list[_Line], parent: int | None, lead: int | None = None) -> None:
        i, n = 0, len(lls)
        lst: tuple[int, str] | None = None  # (list id, marker kind) of the list in progress
        while i < n:
            t = lls[i][2]
            prev, lst = lst, None  # any block but a blank line or a list item ends a list
            if _blank(t):
                j = i
                while j < n and _blank(lls[j][2]):
                    j += 1
                self.add("blank", lls[i], lls[j - 1], parent)
                i, lst = j, prev
            elif _indent(t) >= 4:
                j = last = i
                while j < n and (_blank(lls[j][2]) or _indent(lls[j][2]) >= 4):
                    last = j if not _blank(lls[j][2]) else last
                    j += 1
                self.add("indented_code", lls[i], lls[last], parent)
                i = last + 1
            elif cols := _table_cols(lls, i):
                i = self.table(lls, i, cols, parent)
            elif _fence_open(t):
                i = self.fence(lls, i, parent)
            elif _QUOTE.match(t):
                i = self.quote(lls, i, parent)
            elif _HR.fullmatch(t):
                i += 1
            elif m := _LIST.match(t):
                marker = m[1] if m[1] in "-+*" else m[1][-1]
                if prev is not None and prev[1] == marker:
                    lst = prev
                else:
                    lst, self.lists = (self.lists, marker), self.lists + 1
                i = self.item(lls, i, parent, lst[0])
            elif used := self.refdef(lls, i, parent):
                i += used
            elif (k := _html_type(t, False)) is not None:
                i = self.html(lls, i, k, parent)
            elif m := _ATX.match(t):
                raw = m[2]
                text = _ATX_CLOSE.sub("", raw).strip()
                start = m.start(2) + len(raw) - len(raw.lstrip())
                src: list[_Cell] = [(_src([(lls[i][0], lls[i][1] + start, text)]), None)]
                self.add("heading", lls[i], lls[i], parent, level=len(m[1]), text=text,
                         src=src if text else None)
                i += 1
            else:
                i = self.paragraph(lls, i, parent, lead if i == 0 else None)

    def refdef(self, lls: list[_Line], i: int, parent: int | None) -> int:
        """Lines used by a link reference definition at i (destination on this or the next line)."""
        no, col, t = first = lls[i]
        label = _REF_LABEL.match(t)
        if label is None or not _norm_label(label["label"]):
            return 0
        dest, used = _REF_DEST.fullmatch(t, label.end()), 1
        if dest is None and _blank(t[label.end() :]) and i + 1 < len(lls):
            (no, col, t), used = lls[i + 1], 2
            dest = _REF_DEST.fullmatch(t)
        if dest is None:
            return 0
        group = "angle" if dest["angle"] is not None else "bare"
        target = _unescape(dest[group])
        self.refs.setdefault(_norm_label(label["label"]), target)
        idx = self.add("refdef", first, lls[i + used - 1], parent)
        outer_col = outer_end_col = None
        if used == 1:
            outer_col = col + len(t) - len(t.lstrip())
            outer_end_col = col + len(t.rstrip())
        self.defs[idx] = Inline(
            "refdef", no, col + dest.start(group), no, col + dest.end(group), target,
            label["label"], outer_col, outer_end_col, idx,
        )
        return used

    def paragraph(self, lls: list[_Line], i: int, parent: int | None, lead: int | None) -> int:
        j = i + 1
        while j < len(lls):
            t = lls[j][2]
            if _blank(t):
                break
            if _indent(t) < 4:
                if m := _SETEXT.fullmatch(t):
                    body = _trim(lls[i:j])
                    text = " ".join(ln[2].strip() for ln in body)
                    level = 1 if m[1][0] == "=" else 2
                    self.add("heading", lls[i], lls[j], parent, level=level, text=text,
                             src=[(_src(body), None)])
                    return j + 1
                if _interrupts(lls, j):
                    break
            j += 1
        src: list[_Cell] = [(_src(_trim(lls[i:j])), None)]
        if lead is not None:
            self.sources[lead] = src
        else:
            self.add("paragraph", lls[i], lls[j - 1], parent, src=src)
        return j

    def fence(self, lls: list[_Line], i: int, parent: int | None) -> int:
        m = _fence_open(lls[i][2])
        assert m is not None
        marker, j = m[1], i + 1
        while j < len(lls):
            c = _FENCE_CLOSE.fullmatch(lls[j][2])
            if c and c[1][0] == marker[0] and len(c[1]) >= len(marker):
                break
            j += 1
        last = min(j, len(lls) - 1)
        self.add("fence", lls[i], lls[last], parent, info=m[2].strip(), closed=j < len(lls))
        return last + 1

    def html(self, lls: list[_Line], i: int, k: int, parent: int | None) -> int:
        end_re, j, n = _HTML_BLOCKS[k][1], i, len(lls)
        if end_re is None:
            while j + 1 < n and not _blank(lls[j + 1][2]):
                j += 1
        else:
            while j < n - 1 and not end_re.search(lls[j][2]):
                j += 1
        body = "\n".join(ln[2] for ln in lls[i : j + 1])
        for m in _COMMENT.finditer(body):
            first = lls[i + body.count("\n", 0, m.start())][0]
            last = lls[i + body.count("\n", 0, m.end())][0]
            self.comments.append(Comment(first, last, m[1].strip()))
        self.add("html", lls[i], lls[j], parent)
        return j + 1

    def table(self, lls: list[_Line], i: int, cols: int, parent: int | None) -> int:
        self.add("table_row", lls[i], lls[i], parent, src=_numbered(_cells(lls[i])))
        self.add("table_delim", lls[i + 1], lls[i + 1], parent)
        j = i + 2
        while j < len(lls):
            t = lls[j][2]
            if _blank(t) or _indent(t) >= 4 or _ends_lazy(t):
                break
            self.add("table_row", lls[j], lls[j], parent, src=_numbered(_cells(lls[j])[:cols]))
            j += 1
        return j

    def quote(self, lls: list[_Line], i: int, parent: int | None) -> int:
        inner: list[_Line] = []
        fence: str | None = None
        para = False
        j = i
        while j < len(lls):
            no, col, t = lls[j]
            if m := _QUOTE.match(t):
                ln = (no, col + m.end(), t[m.end() :])
            elif _blank(t) or fence or not para or _ends_lazy(t):
                break
            else:
                ln = _strip_cols(lls[j], len(t))
            inner.append(ln)
            fence, para = _track(ln[2], fence, para)
            j += 1
        self.add("blockquote", lls[i], lls[j - 1], parent)
        self.parse(inner, parent)
        return j

    def item(self, lls: list[_Line], i: int, parent: int | None, list_id: int) -> int:
        no, col, t = lls[i]
        m = _LIST.match(t)
        assert m is not None
        after = m.end()
        k = width = after
        while k < len(t) and t[k] in " \t":
            width += 1 if t[k] == " " else 4 - width % 4
            k += 1
        if k == len(t):
            width, first = after + 1, (no, col + len(t), "")
        elif width - after > 4:  # the content is indented code one column after the marker
            width, first = after + 1, (no, col + after + 1, t[after + 1 :])
        else:
            first = (no, col + k, t[k:])
        inner = [first]
        fence, para = _track(first[2], None, False)
        j, pending = i + 1, 0
        while j < len(lls):
            tj = lls[j][2]
            if _blank(tj):
                if not first[2] and j == i + 1:
                    break  # an item may begin with at most one blank line
                pending += 1
            elif _indent(tj) >= width:
                for ln in lls[j - pending : j + 1]:
                    inner.append(_strip_cols(ln, width))
                    fence, para = _track(inner[-1][2], fence, para)
                pending = 0
            elif pending or fence or not para or _ends_lazy(tj):
                break
            else:
                inner.append(_strip_cols(lls[j], len(tj)))
            j += 1
        if fence and pending:  # an unclosed fence runs over the blank lines to the item's end
            inner.extend(_strip_cols(ln, width) for ln in lls[j - pending : j])
            pending = 0
        idx = self.add("list_item", lls[i], inner[-1], parent, list_id=list_id)
        self.parse(inner[1:] if not first[2] else inner, idx, lead=idx)
        return j - pending


class _InlineParser:
    def __init__(self, sc: _Scanner, src: _Src, block: int, cell: int | None) -> None:
        self.sc, self.block, self.cell = sc, block, cell
        self.s, self.pos = src
        self.cache: dict[tuple[int, int], int] = {}
        self.depth = 0

    def run(self, p: int, end: int) -> None:
        while p < end:
            p = self.token(p, end, True)

    def token(self, p: int, end: int, emit: bool) -> int:
        """Consume one token at p; when not emitting this is markdown-it's skipToken."""
        if not emit and (p, end) in self.cache:
            return self.cache[(p, end)]
        if self.depth >= _MAX_NESTING:  # markdown-it's maxNesting: stop looking for structure
            return end if not emit else p + 1
        s, ch, nxt = self.s, self.s[p], p + 1
        if ch == "\\":
            nxt = p + 2 if p + 1 < end and (s[p + 1] in _PUNCT or s[p + 1] == "\n") else p + 1
        elif ch == "`":
            nxt = self.code(p, end, emit)
        elif ch == "[" or (ch == "!" and p + 1 < end and s[p + 1] == "["):
            self.depth += 1
            nxt = self.link(p, end, emit, image=ch == "!") or p + 1
            self.depth -= 1
        elif ch == "<":
            nxt = self.angle(p, end, emit)
        if not emit:
            self.cache[(p, end)] = nxt
        return nxt

    def emit(
        self, kind: str, a: int, b: int, text: str, label: str | None, oa: int, ob: int
    ) -> None:
        line, col = self.pos[a]
        if b > a and self.s[b - 1] != "\n":
            end_line, end_col = self.pos[b - 1][0], self.pos[b - 1][1] + 1
        else:
            end_line, end_col = self.pos[b]
        (o_line, o_col), (oe_line, oe_col) = self.pos[oa], self.pos[ob - 1]
        outer_col = o_col if o_line == line else None
        outer_end_col = oe_col + 1 if oe_line == end_line else None
        self.sc.inlines.append(
            Inline(kind, line, col, end_line, end_col, text, label, outer_col, outer_end_col,
                   self.block, self.cell)
        )

    def code(self, p: int, end: int, emit: bool) -> int:
        s, q = self.s, p
        while q < end and s[q] == "`":
            q += 1
        k = q
        while True:
            a = s.find("`", k, end)
            if a < 0:
                return q  # no closer of the same length: the run is literal text
            b = a
            while b < end and s[b] == "`":
                b += 1
            if b - a == q - p:
                break
            k = b
        if emit:
            text, lo, hi = s[q:a].replace("\n", " "), q, a
            if text.startswith(" ") and text.endswith(" ") and text.strip():
                text, lo, hi = text[1:-1], lo + 1, hi - 1
            self.emit("code", lo, hi, text, None, p, b)
        return b

    def angle(self, p: int, end: int, emit: bool) -> int:
        s = self.s
        if m := _AUTOLINK.match(s, p, end):
            if emit:
                self.emit("autolink", p + 1, m.end() - 1, m[1], m[1], p, m.end())
            return m.end()
        if m := _EMAIL.match(s, p, end):
            if emit:
                self.emit("autolink", p + 1, m.end() - 1, "mailto:" + m[1], m[1], p, m.end())
            return m.end()
        if m := _HTML_INLINE.match(s, p, end):
            if emit and (c := _COMMENT.fullmatch(m[0])):
                first, last = self.pos[p][0], self.pos[m.end() - 1][0]
                self.sc.comments.append(Comment(first, last, c[1].strip()))
            return m.end()
        return p + 1

    def label_end(self, p: int, end: int, no_nested: bool) -> int:
        """Index of the ']' closing the '[' at p (markdown-it parseLinkLabel), or -1."""
        k, level = p + 1, 1
        while k < end:
            c = self.s[k]
            if c == "]":
                level -= 1
                if level == 0:
                    return k
            nk = self.token(k, end, False)
            if c == "[":
                if nk == k + 1:
                    level += 1
                elif no_nested:
                    return -1
            k = nk
        return -1

    def link(self, p: int, end: int, emit: bool, image: bool) -> int:
        """End of the link or image starting at p, or 0 when there is none."""
        s = self.s
        ls = p + 2 if image else p + 1
        le = self.label_end(ls - 1, end, not image)
        if le < 0:
            return 0
        target: tuple[str, int, int] | None = None
        q = le + 1
        if q < end and s[q] == "(":
            k = _skip_ws(s, q + 1, end)
            if k >= end:
                return 0
            dest = _destination(s, k, end)
            text, a, b = ("", k, k) if dest is None else dest[:3]
            if dest is not None:
                k = _skip_ws(s, dest[3], end)
                title_end = _title_end(s, k, end)
                if title_end is not None and k != dest[3]:
                    k = _skip_ws(s, title_end, end)
            if k < end and s[k] == ")":
                target, q = (text, a, b), k + 1
        kind = "image" if image else "link"
        if target is None:
            q, label, la, lb = le + 1, "", ls, le
            if q < end and s[q] == "[":
                le2 = self.label_end(q, end, False)
                if le2 >= 0:
                    label, la, lb, q = s[q + 1 : le2], q + 1, le2, le2 + 1
            if not label:
                label, la, lb = s[ls:le], ls, le
            resolved = self.sc.refs.get(_norm_label(label))
            if resolved is None:
                return 0
            target, kind = (resolved, la, lb), "refimage" if image else "reflink"
        if emit:
            self.emit(kind, target[1], target[2], target[0], s[ls:le], p, q)
            self.run(ls, le)
        return q


def _skip_ws(s: str, k: int, end: int) -> int:
    while k < end and s[k] in " \t\n":
        k += 1
    return k


def _destination(s: str, k: int, end: int) -> tuple[str, int, int, int] | None:
    """(unescaped target, start, end, next index) like markdown-it parseLinkDestination."""
    if s[k] == "<":
        j = k + 1
        while j < end:
            if s[j] in "\n<":
                return None
            if s[j] == ">":
                return _unescape(s[k + 1 : j]), k + 1, j, j + 1
            j += 2 if s[j] == "\\" and j + 1 < end else 1
        return None
    j, level = k, 0
    while j < end:
        c = s[j]
        if c == " " or ord(c) < 0x20 or c == "\x7f":
            break
        if c == "\\" and j + 1 < end:
            if s[j + 1] == " ":
                break
            j += 2
            continue
        if c == "(":
            level += 1
            if level > 32:
                return None
        elif c == ")":
            if level == 0:
                break
            level -= 1
        j += 1
    if j == k or level:
        return None
    return _unescape(s[k:j]), k, j, j


def _title_end(s: str, k: int, end: int) -> int | None:
    if k >= end or s[k] not in "\"'(":
        return None
    close = ")" if s[k] == "(" else s[k]
    j = k + 1
    while j < end:
        if s[j] == close:
            return j + 1
        if s[j] == "(" and close == ")":
            return None
        j += 2 if s[j] == "\\" and j + 1 < end else 1
    return None


def scan(text: str) -> Scan:
    """Scan markdown text; CRLF and LF input give identical results.

    ``lines`` is ``text`` split on ``\\r\\n`` or ``\\n``, so text ending in a newline has a final
    empty element (``"\\n".join(lines)`` restores the LF text); no block covers that element.
    """
    lines = re.split(r"\r?\n", text)
    count = len(lines) - 1 if lines[-1] == "" else len(lines)
    sc = _Scanner()
    sc.parse([(k + 1, 0, lines[k]) for k in range(count)], None)
    for idx in sorted(set(sc.sources) | set(sc.defs)):
        if idx in sc.defs:
            sc.inlines.append(sc.defs[idx])
        for src, cell in sc.sources.get(idx, []):
            _InlineParser(sc, src, idx, cell).run(0, len(src[0]))
    comments = sorted(sc.comments, key=lambda c: (c.line_start, c.line_end))
    return Scan(lines, sc.blocks, sc.inlines, comments)
