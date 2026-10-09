from __future__ import annotations

import re
from typing import Any

import pytest
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_extract import extract_doc, main, run
from dd_inventory import DEFAULT_NEVER_EDIT

NEVER = re.compile(DEFAULT_NEVER_EDIT)


Tokens = list[dict[str, Any]]


def _extract(text: str, doc: str = "README.md") -> tuple[Tokens, Tokens]:
    return extract_doc(doc, text, NEVER)


def _toks(text: str, kind: str | None = None, doc: str = "README.md") -> list[dict[str, Any]]:
    tokens, _ = _extract(text, doc)
    return [t for t in tokens if kind is None or t["kind"] == kind]


def _span(text: str, tok: dict[str, Any]) -> str:
    return str(text.split("\n")[tok["line"] - 1][tok["col"] : tok["end_col"]])


def test_inline_code_path_token():
    assert _toks("See `src/app.py` for details.\n") == [
        {
            "doc": "README.md",
            "line": 1,
            "col": 5,
            "end_col": 15,
            "kind": "path",
            "text": "src/app.py",
            "target_doc": None,
            "script_tool": None,
            "version": None,
            "context": "inline-code",
            "link": None,
            "block": {"kind": "paragraph", "line_start": 1, "line_end": 1},
            "subject": False,
            "heading_path": [],
            "never_edit": False,
            "generated": False,
            "ignored": None,
            "editable": True,
            "tree_label": None,
        }
    ]


def test_link_target_with_fragment_gives_path_and_anchor():
    text = "Read [the guide](docs/guide.md#setup).\n"
    path, anchor = _toks(text)
    link = {"col": 5, "end_col": 37, "text": "the guide"}
    assert (path["kind"], path["text"], path["context"], path["link"]) == (
        "path", "docs/guide.md", "link", link,
    )
    assert _span(text, path) == "docs/guide.md"
    assert (anchor["kind"], anchor["text"], anchor["target_doc"], anchor["link"]) == (
        "anchor", "setup", "docs/guide.md", link,
    )
    assert _span(text, anchor) == "setup"


def test_same_doc_anchor_target_doc_is_self():
    text = "# Title\n\nSee [below](#usage) and [code](src/app.py#L10).\n"
    toks = _toks(text, doc="docs/a.md")
    assert [(t["kind"], t["text"], t["target_doc"]) for t in toks] == [
        ("anchor", "usage", "docs/a.md"),
        ("path", "src/app.py", None),
    ]


def test_line_suffix_stripped_from_text_and_span():
    # ruling R13: the span covers exactly the text, never the stripped suffix
    text = "Edit `src/app.py:12`, `lib/x.go:3-9` and [code](src/app.py#L3-L9).\n"
    toks = _toks(text)
    assert [(t["kind"], t["text"], _span(text, t)) for t in toks] == [
        ("path", "src/app.py", "src/app.py"),
        ("path", "lib/x.go", "lib/x.go"),
        ("path", "src/app.py", "src/app.py"),
    ]
    fence = "```bash\npython tools/run.py:3\n```\n"
    (tok,) = _toks(fence, "path")
    assert (tok["text"], _span(fence, tok)) == ("tools/run.py", "tools/run.py")


def test_ratio_filter_drops_only_fractions_and_single_letters():
    # ruling R14
    assert [t["text"] for t in _toks("Code in `src/lib` and `app/api`.\n")] == [
        "src/lib", "app/api",
    ]
    assert _toks("Scores `3/5`, `10/12` and `X/Y`.\n") == []


@pytest.mark.parametrize(
    "text",
    [
        "Edit `<name>/x.py` now.\n",
        "Run `/pipeline` now.\n",
        "Score `3/5` now.\n",
        "Axes `X/Y` now.\n",
        "Clone `my-project/x` now.\n",
        "Run mkdir `out/` first.\n",
        "Create this file:\n`out/new.py`\n",
        "Glob `src/*.py` here.\n",
        "Use `foo/bar.py` as a sample.\n",
        "Template `${ROOT}/x.py` here.\n",
        "See [site](https://example.org/docs/a.md) and <https://x.org/a.py>.\n",
        "Dotted `os.path` and `pkg.mod.func` names.\n",
        "Spaced `src/a b.py` path.\n",
        'Annotated `@Path("/prefix")` and `--out=dist/` and `join(a/b)`.\n',
    ],
)
def test_filters_drop_placeholders_routes_ratios_and_create_paths(text):
    assert _toks(text, "path") == []


def test_fence_python_argument_is_path():
    text = (
        "```bash\n"
        "python scripts/run.py --flag\n"
        "./tools/setup.sh\n"
        "ls src/other.py\n"
        "node web/server.js && bash ci/check.sh\n"
        "```\n"
    )
    toks = _toks(text, "path")
    assert [(t["text"], t["line"], _span(text, t), t["context"]) for t in toks] == [
        ("scripts/run.py", 2, "scripts/run.py", "fence"),
        ("./tools/setup.sh", 3, "./tools/setup.sh", "fence"),
        ("web/server.js", 5, "web/server.js", "fence"),
        ("ci/check.sh", 5, "ci/check.sh", "fence"),
    ]
    assert toks[0]["block"] == {"kind": "fence", "line_start": 1, "line_end": 6}


def test_dot_slash_path_only_at_command_position():
    text = "```bash\ncp ./a.txt ./b.txt\n$ ./run.sh && ./ci/check.sh\n```\n"
    assert [t["text"] for t in _toks(text, "path")] == ["./run.sh", "./ci/check.sh"]


def test_generated_markers_mentioned_in_prose_open_no_region():
    text = (
        "Wrap output in `<!-- BEGIN mdsh -->` or `[[[cog`.\n"
        "\n"
        "See `src/a.py`.\n"
        "\n"
        "<!-- BEGIN GENERATED --> `src/b.py` <!-- END GENERATED -->\n"
        "\n"
        "See `src/c.py`.\n"
    )
    # the one-line region closes on its own line, so it does not run to the end of the doc
    flags = {t["text"]: t["generated"] for t in _toks(text, "path")}
    assert flags == {"src/a.py": False, "src/c.py": False}


def test_scripts_in_bash_fence_and_inline():
    text = (
        "```bash\n"
        "$ make build\n"
        "npm run lint && yarn test\n"
        "pnpm run dev\n"
        "yarn install\n"
        "just deploy\n"
        "task docs\n"
        "```\n"
        "\n"
        "Then run `yarn run e2e` or `pnpm fmt`, not `pnpm add x`.\n"
    )
    toks = _toks(text, "script")
    assert [(t["text"], t["script_tool"], t["context"]) for t in toks] == [
        ("build", "make", "fence"),
        ("lint", "npm", "fence"),
        ("test", "yarn", "fence"),
        ("dev", "pnpm", "fence"),
        ("deploy", "just", "fence"),
        ("docs", "task", "fence"),
        ("e2e", "yarn", "inline-code"),
        ("fmt", "pnpm", "inline-code"),
    ]
    assert all(_span(text, t) == t["text"] for t in toks)


def test_scripts_not_taken_from_non_shell_fence():
    assert _toks("```python\nmake build\n```\n", "script") == []


@pytest.mark.parametrize(
    ("line", "runtime", "floor"),
    [
        ("Requires Python 3.11+.", "python", "3.11"),
        ("Use Node >= 18 for the web app.", "node", "18"),
        ("This requires Go 1.22 or later.", "go", "1.22"),
        ("Needs `Node.js v20 or newer`.", "node", "20"),
        ("Built with Python 3.12.", None, None),
    ],
)
def test_version_floor_forms(line, runtime, floor):
    text = line + "\n"
    toks = _toks(text, "version")
    if runtime is None:
        assert toks == []
        return
    (tok,) = toks
    assert tok["version"] == {"runtime": runtime, "floor": floor}
    assert tok["text"] == floor
    assert _span(text, tok) == floor


def test_version_context_and_skipped_in_fences():
    text = "Python 3.11+ and `Rust 1.75+`.\n\n```\nPython 3.9+\n```\n"
    toks = _toks(text, "version")
    assert [(t["text"], t["context"], t["version"]["runtime"]) for t in toks] == [
        ("3.11", "prose", "python"),
        ("1.75", "inline-code", "rust"),
    ]


def test_tree_entries_assembled_from_indentation():
    text = (
        "```\n"
        "├── src/\n"
        "│   └── app.py\n"
        "├── ...\n"
        "├── My Notes/\n"
        "└── docs/guide.md   # the guide\n"
        "```\n"
    )
    toks = _toks(text)
    assert [t["kind"] for t in toks] == ["tree"] * 3
    assert [t["text"] for t in toks] == ["src/", "src/app.py", "docs/guide.md"]
    assert [_span(text, t) for t in toks] == ["src/", "app.py", "docs/guide.md"]
    assert {t["context"] for t in toks} == {"tree"}
    assert toks[0]["block"] == {"kind": "tree", "line_start": 1, "line_end": 7}


def test_tree_indentation_only_and_ascii_glyphs():
    indented = "```text\nsrc/\n    app.py\n    lib/\n        util.py\n    cli/\ndocs/\n```\n"
    assert [t["text"] for t in _toks(indented)] == [
        "src/", "src/app.py", "src/lib/", "src/lib/util.py", "src/cli/", "docs/",
    ]
    ascii_tree = "```\n|-- src\n|   `-- app.py <- entry\n`-- README.md\n```\n"
    assert [t["text"] for t in _toks(ascii_tree)] == ["src", "src/app.py", "README.md"]


def test_tree_root_label_kept_as_prefix_with_tree_label():
    # ruling R16: the label stays in `text`, every token of the tree carries `tree_label`
    glyphs = "```\nproject/\n├── src/\n│   └── app.py\n└── README.md\n```\n"
    toks = _toks(glyphs)
    assert [(t["text"], t["tree_label"]) for t in toks] == [
        ("project/", "project"),
        ("project/src/", "project"),
        ("project/src/app.py", "project"),
        ("project/README.md", "project"),
    ]
    assert (toks[0]["line"], _span(glyphs, toks[0])) == (2, "project/")
    src = "```\nsrc/\n├── app.py\n└── lib/\n```\n"
    assert [t["text"] for t in _toks(src)] == ["src/", "src/app.py", "src/lib/"]
    mine = "```\nmy-project/\n├── src/\n└── docs/\n```\n"
    assert [t["text"] for t in _toks(mine)] == [
        "my-project/", "my-project/src/", "my-project/docs/",
    ]
    indented = "```\nproject/\n    src/\n        app.py\n```\n"
    assert [t["text"] for t in _toks(indented)] == [
        "project/", "project/src/", "project/src/app.py",
    ]
    dot = "```\n.\n├── src/\n└── docs/\n```\n"
    assert [(t["text"], t["tree_label"]) for t in _toks(dot)] == [("src/", None), ("docs/", None)]


def test_tree_label_null_without_label_and_on_other_tokens():
    text = "`src/a.py`\n\n```\n├── src/\n└── docs/\n```\n"
    assert {t["tree_label"] for t in _toks(text)} == {None}


def test_tree_two_space_indentation():
    text = "```\nsrc/\n  app.py\ndocs/\n  guide.md\n```\n"
    assert [t["text"] for t in _toks(text)] == ["src/", "src/app.py", "docs/", "docs/guide.md"]


def test_tree_description_column_ends_the_name():
    text = (
        "```\n"
        "├── src/      source code\n"
        "│   └── app.py    entry point\n"
        "└── docs/     documentation\n"
        "```\n"
    )
    toks = _toks(text)
    assert [t["text"] for t in toks] == ["src/", "src/app.py", "docs/"]
    assert [_span(text, t) for t in toks] == ["src/", "app.py", "docs/"]


def test_unindented_name_lists_are_not_trees():
    gitignore = "```\nnode_modules/\ndist/\n.env\n```\n"
    assert _toks(gitignore, "tree") == []
    mixed = "```\ncd app/\nbuild/\nlogs/\npython scripts/run.py\n```\n"
    assert _toks(mixed, "tree") == []
    assert [t["text"] for t in _toks(mixed, "path")] == ["scripts/run.py"]


def test_plain_fence_without_tree_shape_is_not_a_tree():
    assert _toks("```\nsrc/\nhello world\n```\n", "tree") == []
    urls = "```\nhttps://a.org/\nhttps://b.org/\n```\n"
    assert _toks(urls, "tree") == []
    boxes = (
        "```\n"
        "   ┌──────────┐\n"
        "   │  server  │\n"
        "   └────▲─────┘\n"
        "├──────┬──────┤\n"
        "│ name │ size │\n"
        "└──────┴──────┘\n"
        "```\n"
    )
    assert _toks(boxes, "tree") == []


def test_subject_flag_list_and_table():
    text = (
        "- `src/a.py` and `src/b.py`\n"
        "- see [guide](docs/guide.md) and `src/c.py`\n"
        "- plain `--flag` then `src/d.py`\n"
        "- intro text\n"
        "  `src/h.py` continued\n"
        "\n"
        "| File | Notes |\n"
        "|------|-------|\n"
        "| `src/e.py` | uses `src/f.py` |\n"
        "| text | `src/g.py` |\n"
    )
    subjects = {t["text"]: t["subject"] for t in _toks(text, "path")}
    assert subjects == {
        "src/a.py": True,
        "src/b.py": False,
        "docs/guide.md": True,
        "src/c.py": False,
        "src/d.py": False,
        "src/h.py": False,
        "src/e.py": True,
        "src/f.py": False,
        "src/g.py": False,
    }
    blocks = {t["text"]: t["block"] for t in _toks(text, "path")}
    assert blocks["src/h.py"] == {"kind": "list_item", "line_start": 4, "line_end": 5}
    assert blocks["src/e.py"] == {"kind": "table_row", "line_start": 9, "line_end": 9}


def test_table_header_row_kind_and_never_subject():
    # ruling R15
    text = "| `src/h.py` | Notes |\n|---|---|\n| `src/b.py` | body |\n"
    head, body = _toks(text)
    assert (head["text"], head["block"]["kind"], head["subject"]) == (
        "src/h.py", "table_header", False,
    )
    assert (body["text"], body["block"]["kind"], body["subject"]) == ("src/b.py", "table_row", True)


def test_drift_ignore_before_table_covers_the_table():
    text = (
        "<!-- drift-ignore: legacy table -->\n"
        "| File | Notes |\n"
        "|------|-------|\n"
        "| `src/a.py` | x |\n"
        "| `src/b.py` | y |\n"
        "\n"
        "`src/c.py`\n"
    )
    tokens, markers = _extract(text)
    assert {t["text"]: t["ignored"] for t in tokens} == {
        "src/a.py": "legacy table", "src/b.py": "legacy table", "src/c.py": None,
    }
    assert (markers[0]["target_line_start"], markers[0]["target_line_end"]) == (2, 5)


def test_anchor_target_doc_is_repository_relative():
    # ruling R17
    text = "[a](../guide/x.md#f) [b](sub/y.md#g) [c](/docs/root.md#h) [d](#i)\n"
    toks = _toks(text, "anchor", doc="docs/a.md")
    assert [(t["text"], t["target_doc"]) for t in toks] == [
        ("f", "guide/x.md"),
        ("g", "docs/sub/y.md"),
        ("h", "docs/root.md"),
        ("i", "docs/a.md"),
    ]


def test_never_edit_from_ancestor_heading():
    text = (
        "# Project\n\n## History\n\n### Details\n\nSee `src/old.py`.\n\n"
        "## Usage\n\nSee `src/new.py`.\n"
    )
    old, new = _toks(text)
    assert (old["heading_path"], old["never_edit"]) == (["Project", "History", "Details"], True)
    assert (new["heading_path"], new["never_edit"]) == (["Project", "Usage"], False)


def test_generated_region_flag():
    text = (
        "<!-- BEGIN mdsh -->\n"
        "See `src/a.py`.\n"
        "<!-- END mdsh -->\n"
        "\n"
        "See `src/b.py`.\n"
        "\n"
        "<!-- embedme src/c.py -->\n"
        "```bash\n"
        "python src/c.py\n"
        "```\n"
        "\n"
        "<!-- [[[cog import x ]]] -->\n"
        "`src/d.py`\n"
        "<!-- [[[end]]] -->\n"
        "\n"
        "<!-- BEGIN_TF_DOCS -->\n"
        "`src/e.py`\n"
        "<!-- END_TF_DOCS -->\n"
        "\n"
        "<!-- BEGIN GENERATED: table -->\n"
        "`src/f.py`\n"
        "<!-- END GENERATED -->\n"
        "\n"
        "`src/g.py`\n"
    )
    flags = {t["text"]: t["generated"] for t in _toks(text, "path")}
    assert flags == {
        "src/a.py": True,
        "src/b.py": False,
        "src/c.py": True,
        "src/d.py": True,
        "src/e.py": True,
        "src/f.py": True,
        "src/g.py": False,
    }


def test_drift_ignore_next_block_and_next_line():
    text = (
        "<!-- drift-ignore: kept for history -->\n"
        "- `src/a.py`\n"
        "- `src/b.py`\n"
        "\n"
        "<!-- drift-ignore-next-line: example output -->\n"
        "`src/c.py` here\n"
        "`src/d.py` there\n"
        "\n"
        "`src/e.py`\n"
    )
    tokens, markers = _extract(text)
    assert {t["text"]: t["ignored"] for t in tokens} == {
        "src/a.py": "kept for history",
        "src/b.py": "kept for history",
        "src/c.py": "example output",
        "src/d.py": None,
        "src/e.py": None,
    }
    assert markers == [
        {
            "doc": "README.md", "line": 1, "kind": "drift-ignore", "reason": "kept for history",
            "target_line_start": 2, "target_line_end": 3,
        },
        {
            "doc": "README.md", "line": 5, "kind": "drift-ignore-next-line",
            "reason": "example output", "target_line_start": 6, "target_line_end": 6,
        },
    ]


def test_marker_without_reason_reported_not_honoured():
    text = (
        "<!-- drift-ignore -->\n"
        "`src/a.py`\n"
        "\n"
        "<!-- drift-ignore-next-line:   -->\n"
        "`src/b.py`\n"
        "\n"
        "<!-- drift-ignore-file: whole file -->\n"
    )
    tokens, markers = _extract(text)
    assert [t["ignored"] for t in tokens] == [None, None]
    assert [(m["kind"], m["reason"], m["target_line_start"]) for m in markers] == [
        ("drift-ignore", None, 2),
        ("drift-ignore-next-line", None, 5),
    ]


def test_multiline_code_span_not_editable():
    text = "Run `npm run\nbuild` now, see `\nsrc/app.py` and `src/ok.py`.\n"
    toks = _toks(text)
    by_text = {t["text"]: t for t in toks}
    assert by_text["build"]["kind"] == "script"
    assert by_text["build"]["editable"] is False
    assert by_text["src/app.py"]["editable"] is False
    assert by_text["src/ok.py"]["editable"] is True


def test_refdef_gives_tokens_reflink_and_autolink_do_not():
    text = "See [the guide][g] and ![logo](img/logo.png).\n\n[g]: docs/guide.md#sec\n"
    toks = _toks(text)
    assert [(t["kind"], t["text"], t["context"], t["line"], t["link"]) for t in toks] == [
        ("path", "img/logo.png", "image", 1, None),
        ("path", "docs/guide.md", "refdef", 3, None),
        ("anchor", "sec", "refdef", 3, None),
    ]
    assert toks[1]["block"] == {"kind": "refdef", "line_start": 3, "line_end": 3}


def test_tokens_ordered_by_line_and_col():
    text = "`b/x.py` [a](a/y.md)\n\n```bash\nmake t\n```\n"
    toks = _toks(text)
    keys = [(t["line"], t["col"]) for t in toks]
    assert keys == sorted(keys)
    assert len(toks) == 3


def test_run_writes_tokens_json_and_skips_unreadable(tmp_path):
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("See `src/app.py`.\r\n", encoding="utf-8", newline="")
    (root / "docs" / "bad.md").write_bytes(b"\xff\xfe bad")
    workdir = tmp_path / "work"
    write_json(
        workdir / "inventory.json",
        {
            "docs": ["README.md", "docs/bad.md", "docs/gone.md"],
            "files": [],
            "never_edit_re": DEFAULT_NEVER_EDIT,
            "excluded": [],
            "skipped": [],
        },
    )
    result = run(root, workdir)
    assert result == read_json(workdir / "tokens.json")
    assert list(result["docs"]) == ["README.md"]
    assert [t["text"] for t in result["docs"]["README.md"]] == ["src/app.py"]
    assert result["markers"] == []
    assert result["skipped"] == [
        {"doc": "docs/bad.md", "reason": "not-utf8"},
        {"doc": "docs/gone.md", "reason": "unreadable"},
    ]
    assert (workdir / "tokens.json").read_bytes().endswith(b"}\n")


def test_main_exit_codes(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    workdir = tmp_path / "work"
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_MISSING
    write_json(
        workdir / "inventory.json",
        {"docs": [], "files": [], "never_edit_re": DEFAULT_NEVER_EDIT},
    )
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_OK
    assert read_json(workdir / "tokens.json") == {"docs": {}, "markers": [], "skipped": []}


def test_crlf_and_lf_give_same_tokens():
    lf = "# T\n\n- `src/a.py`\n\n```bash\nmake x\n```\n"
    assert _toks(lf) == _toks(lf.replace("\n", "\r\n"))

