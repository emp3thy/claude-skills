from pathlib import Path

from dd_md_scan import Block, Comment, Inline, scan

MARKDOWN_DIR = Path(__file__).resolve().parent / "fixtures" / "markdown"


def _blocks(text: str, kind: str) -> list[Block]:
    return [b for b in scan(text).blocks if b.kind == kind]


def test_backtick_and_tilde_fences_close_only_on_same_char_and_length():
    text = "````md\n```\nnot closed\n~~~~\n````\n~~~\n```\n~~~\n```\nx\n`````\n"
    fences = _blocks(text, "fence")
    assert [(b.line_start, b.line_end, b.info) for b in fences] == [
        (1, 5, "md"),
        (6, 8, ""),
        (9, 11, ""),
    ]
    assert scan(text).inlines == []


def test_fence_indented_inside_list_item_is_a_fence():
    text = "- item\n\n  ```bash\n  make `build`\n  ```\n- next\n"
    s = scan(text)
    items = [(i, b) for i, b in enumerate(s.blocks) if b.kind == "list_item"]
    assert [(b.line_start, b.line_end, b.parent) for _, b in items] == [(1, 5, None), (6, 6, None)]
    fences = [b for b in s.blocks if b.kind == "fence"]
    assert fences == [Block("fence", 3, 5, "bash", None, None, items[0][0])]
    assert [i for i in s.inlines if i.kind == "code"] == []


def test_code_span_continuing_across_line_break():
    s = scan("Run `make\nbuild` now.\n")
    assert s.inlines == [
        Inline("code", 1, 5, 2, 5, "make build", None, 4, 6, 0),
    ]


def test_multi_backtick_span_containing_backtick():
    s = scan("Use `` a`b `` here\n")
    assert s.inlines == [Inline("code", 1, 7, 1, 10, "a`b", None, 4, 13, 0)]


def test_reference_style_link_resolves_through_refdef():
    text = (
        "See [the guide][g] and [Docs] and [g][].\n"
        "\n"
        '[g]: docs/guide.md "Guide"\n'
        "[docs]: <docs/index.md>\n"
    )
    s = scan(text)
    assert s.inlines == [
        Inline("reflink", 1, 16, 1, 17, "docs/guide.md", "the guide", 4, 18, 0),
        Inline("reflink", 1, 24, 1, 28, "docs/index.md", "Docs", 23, 29, 0),
        Inline("reflink", 1, 35, 1, 36, "docs/guide.md", "g", 34, 39, 0),
    ]
    assert [(b.line_start, b.line_end) for b in s.blocks if b.kind == "refdef"] == [(3, 3), (4, 4)]


def test_undefined_reference_is_not_a_link():
    assert scan("[text][nowhere] and [shortcut]\n").inlines == []


def test_escaped_pipe_does_not_split_table_cell():
    text = "| Flag | Meaning |\n| --- | --- |\n| `a\\|b` | either |\n"
    s = scan(text)
    assert s.inlines == [Inline("code", 3, 3, 3, 7, "a|b", None, 2, 8, 2)]


def test_table_row_blocks_have_line_numbers():
    text = "Intro\n\n| A | B |\n|---|:-:|\n| 1 | `two` |\n| [x](y.md) | 4 |\n\nAfter\n"
    s = scan(text)
    table = [(b.kind, b.line_start, b.line_end) for b in s.blocks if b.kind.startswith("table")]
    assert table == [
        ("table_row", 3, 3),
        ("table_delim", 4, 4),
        ("table_row", 5, 5),
        ("table_row", 6, 6),
    ]
    code, link = s.inlines
    assert (code.line, code.text, s.blocks[code.block].line_start) == (5, "two", 5)
    assert (link.kind, link.line, link.text, link.label) == ("link", 6, "y.md", "x")
    assert s.blocks[link.block].line_start == 6


def test_setext_heading_text_and_level():
    s = scan("Title `x`\n=====\n\nSub\n---\n")
    headings = [b for b in s.blocks if b.kind == "heading"]
    assert headings == [
        Block("heading", 1, 2, None, 1, "Title `x`", None),
        Block("heading", 4, 5, None, 2, "Sub", None),
    ]
    assert s.inlines == [Inline("code", 1, 7, 1, 8, "x", None, 6, 9, 0)]


def test_atx_heading_text_and_level():
    s = scan("### Run `make` ###\n")
    assert s.blocks == [Block("heading", 1, 1, None, 3, "Run `make`", None)]
    assert [i.text for i in s.inlines] == ["make"]


def test_html_comment_is_a_comment_not_a_paragraph():
    s = scan("<!-- document-drift: ignore\n  next line -->\nText `a`.\n")
    assert s.comments == [Comment(1, 2, "document-drift: ignore\n  next line")]
    assert [(b.kind, b.line_start, b.line_end) for b in s.blocks] == [
        ("html", 1, 2),
        ("paragraph", 3, 3),
    ]
    assert [i.text for i in s.inlines] == ["a"]


def test_inline_html_comment_is_a_comment():
    s = scan("Text <!-- marker --> more\n")
    assert s.comments == [Comment(1, 1, "marker")]


def test_nested_list_item_parent_index():
    s = scan("- a `x`\n  - b\n    - c\n- d\n")
    assert [(b.kind, b.line_start, b.line_end, b.parent) for b in s.blocks] == [
        ("list_item", 1, 3, None),
        ("list_item", 2, 3, 0),
        ("list_item", 3, 3, 1),
        ("list_item", 4, 4, None),
    ]
    assert [(i.text, i.block) for i in s.inlines] == [("x", 0)]


def test_image_inline_kind():
    s = scan("![logo `x`](img/logo.png) and [![b](badge.svg)](https://ci)\n")
    assert s.inlines[0] == Inline(
        "image", 1, 12, 1, 24, "img/logo.png", "logo `x`", 0, 25, 0
    )
    assert [(i.kind, i.text) for i in s.inlines] == [
        ("image", "img/logo.png"),
        ("code", "x"),
        ("link", "https://ci"),
        ("image", "badge.svg"),
    ]


def test_autolinks():
    s = scan("See <https://x.io/a> or <me@x.io>.\n")
    spans = [(i.kind, i.text, i.col, i.end_col, i.outer_col, i.outer_end_col) for i in s.inlines]
    assert spans == [
        ("autolink", "https://x.io/a", 5, 19, 4, 20),
        ("autolink", "mailto:me@x.io", 25, 32, 24, 33),
    ]


def test_link_target_is_unescaped_and_label_kept():
    s = scan("[`a`](<docs/my file.md> \"t\") [b](x\\_y.md)\n")
    links = [i for i in s.inlines if i.kind == "link"]
    assert [(i.text, i.label, i.col, i.end_col) for i in links] == [
        ("docs/my file.md", "`a`", 7, 22),
        ("x_y.md", "b", 33, 40),
    ]


def test_inline_code_inside_fence_is_not_an_inline():
    s = scan("```\nuse `x`\n```\n    indented `y`\n")
    assert [b.kind for b in s.blocks] == ["fence", "indented_code"]
    assert s.inlines == []


def test_blockquote_contents_are_scanned():
    s = scan("> quoted `q.py`\n> more\n")
    assert s.blocks[0].kind == "blockquote"
    assert [(i.text, i.line, i.col) for i in s.inlines] == [("q.py", 1, 10)]


def test_crlf_input_gives_same_scan_as_lf():
    text = (MARKDOWN_DIR / "constructs.md").read_text(encoding="utf-8")
    lf = text.replace("\r\n", "\n")
    crlf = lf.replace("\n", "\r\n")
    assert scan(crlf) == scan(lf)
    assert not any("\r" in line for line in scan(crlf).lines)


def test_lines_are_split_without_endings():
    assert scan("a\r\nb\nc").lines == ["a", "b", "c"]


def test_reference_image_is_a_reflink_spanning_its_label():
    s = scan("[![CI][ci-img]][ci]\n\n[ci-img]: badge.svg\n[ci]:\n  https://ci.example\n")
    assert [(i.kind, i.text, i.col, i.end_col) for i in s.inlines] == [
        ("reflink", "https://ci.example", 16, 18),
        ("reflink", "badge.svg", 7, 13),
    ]
    assert [(b.line_start, b.line_end) for b in s.blocks if b.kind == "refdef"] == [(3, 3), (4, 5)]


def test_outer_span_is_none_when_label_wraps_lines():
    (link,) = scan("[two\nlines](t.md)\n").inlines
    assert (link.line, link.col, link.outer_col, link.outer_end_col) == (2, 7, None, 12)


def test_tab_after_list_marker():
    s = scan("*\t`opt` (bool)\n\n\tIf set to `true`.\n")
    assert [b.kind for b in s.blocks] == ["list_item", "blank", "paragraph"]
    assert [(i.text, i.line, i.col, s.blocks[i.block].kind) for i in s.inlines] == [
        ("opt", 1, 3, "list_item"),
        ("true", 3, 12, "paragraph"),
    ]


def test_unclosed_fence_in_list_item_runs_over_blank_lines():
    s = scan("- a\n  ```\n  x\n\nafter\n")
    fence = next(b for b in s.blocks if b.kind == "fence")
    assert (fence.line_start, fence.line_end) == (2, 4)
