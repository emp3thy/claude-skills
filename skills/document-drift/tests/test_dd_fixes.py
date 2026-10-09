from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_extract import extract_doc
from dd_fixes import main, plan_hunks, run
from dd_inventory import DEFAULT_NEVER_EDIT

NEVER = re.compile(DEFAULT_NEVER_EDIT)

Cand = dict[str, Any]


def _cand(text: str, match: str, cls: str = "provable-delete", *, kind: str | None = None,
          context: str | None = None, replacement: str | None = None, nth: int = 0,
          doc: str = "README.md", fid: str | None = None) -> Cand:
    """A Candidate built on a real extracted token (the nth whose text is ``match``)."""
    tokens, _ = extract_doc(doc, text, NEVER)
    found = [t for t in tokens if t["text"] == match and (kind is None or t["kind"] == kind)
             and (context is None or t["context"] == context)]
    tok = found[nth]
    cand: Cand = dict(tok)
    deleted = cls == "provable-delete"
    cand.update(
        resolved_then=match, snapshot="a" * 40, existed_then=True,
        outcome="deleted" if deleted else "unique",
        replacement=None if deleted else replacement,
        evidence_commit="a1b2c3d",
        evidence="deleted in a1b2c3d" if deleted else "renamed in a1b2c3d",
        human_kind=None, history_unavailable=False,
    )
    cand["class"] = cls
    cand["id"] = fid or f"F{tok['line']:03d}"
    return cand


def _plan(text: str, *cands: Cand) -> tuple[list[Cand], list[Cand]]:
    return plan_hunks(text, list(cands))


def _demoted_kind(text: str, cand: Cand) -> str | None:
    hunks, demoted = _plan(text, cand)
    assert hunks == []
    assert [d["id"] for d in demoted] == [cand["id"]]
    assert demoted[0]["class"] == "human"
    return str(demoted[0]["human_kind"])


# -- replace ---------------------------------------------------------------------------------


def test_replace_inline_code_span_only():
    text = "See `src/app.py` and `src/app.py.bak` here.\n"
    cand = _cand(text, "src/app.py", "provable-replace", replacement="src/main.py")
    hunks, demoted = _plan(text, cand)
    assert demoted == []
    assert hunks == [{
        "id": "H001", "finding_id": cand["id"], "doc": "README.md", "line_start": 1,
        "line_end": 1, "before": ["See `src/app.py` and `src/app.py.bak` here."],
        "after": ["See `src/main.py` and `src/app.py.bak` here."], "verb": "replace",
        "token_kind": "path", "token_text": "src/app.py", "new_text": "src/main.py",
        "reason": "renamed in a1b2c3d", "also": [],
    }]


def test_replace_link_target_and_matching_label():
    text = "Read [docs/a.md](docs/a.md) and [the guide](docs/a.md).\n"
    first = _cand(text, "docs/a.md", "provable-replace", replacement="docs/b.md", fid="F001")
    second = _cand(text, "docs/a.md", "provable-replace", replacement="docs/b.md", nth=1,
                   fid="F002")
    hunks, demoted = _plan(text, first, second)
    assert demoted == []
    assert len(hunks) == 1  # same line: one hunk
    assert hunks[0]["after"] == ["Read [docs/b.md](docs/b.md) and [the guide](docs/b.md)."]
    assert hunks[0]["also"] == ["F002"]


def test_replace_version_in_prose():
    text = "Requires Python 3.9 or later.\n"
    cand = _cand(text, "3.9", "provable-replace", kind="version", replacement="3.11")
    cand["evidence"] = "manifest pyproject.toml says >=3.11"
    hunks, _ = _plan(text, cand)
    assert hunks[0]["after"] == ["Requires Python 3.11 or later."]
    assert hunks[0]["reason"] == "manifest pyproject.toml says >=3.11"


def test_replace_tree_entry_edits_own_segment():
    text = "```text\nrepo/\n├── src/\n│   └── app.py\n└── README.md\n```\n"
    cand = _cand(text, "repo/src/app.py", "provable-replace", replacement="main.py")
    hunks, _ = _plan(text, cand)
    assert hunks[0]["before"] == ["│   └── app.py"]
    assert hunks[0]["after"] == ["│   └── main.py"]


def test_replace_refdef_destination():
    text = "See [the guide][g].\n\n[g]: docs/a.md\n"
    cand = _cand(text, "docs/a.md", "provable-replace", replacement="docs/b.md")
    hunks, _ = _plan(text, cand)
    assert hunks[0]["after"] == ["[g]: docs/b.md"]


def test_replace_span_mismatch_is_recheck_failed():
    text = "See `src/app.py` here.\n"
    cand = _cand(text, "src/app.py", "provable-replace", replacement="src/main.py")
    assert _demoted_kind("See `src/xyz.py` here.\n", cand) == "recheck-failed"


# -- list items ------------------------------------------------------------------------------


def test_delete_subject_list_item_with_continuation_lines():
    text = ("Files:\n\n- `src/a.py` does a\n- `src/b.py` does b\n  and more b\n"
            "  and even more\n- `src/c.py` does c\n\nEnd.\n")
    cand = _cand(text, "src/b.py")
    hunks, demoted = _plan(text, cand)
    assert demoted == []
    assert len(hunks) == 1
    h = hunks[0]
    assert (h["line_start"], h["line_end"], h["verb"]) == (4, 6, "delete")
    assert h["before"] == ["- `src/b.py` does b", "  and more b", "  and even more"]
    assert h["after"] == []
    assert h["new_text"] is None
    assert h["reason"] == "deleted in a1b2c3d"


def test_delete_loose_list_item_takes_blank_lines_up_to_next_sibling():
    text = "- `src/a.py`\n\n- `src/b.py`\n\n- `src/c.py`\n"
    hunks, _ = _plan(text, _cand(text, "src/b.py"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (3, 4)
    assert hunks[0]["before"] == ["- `src/b.py`", ""]


def test_delete_last_list_item_keeps_following_blank_line():
    text = "- `src/a.py`\n- `src/b.py`\n\nEnd.\n"
    hunks, _ = _plan(text, _cand(text, "src/b.py"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (2, 2)


def test_only_list_item_is_large_deletion():
    text = "Intro.\n\n- `src/a.py` does a\n\nEnd.\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "large-deletion"


def test_list_item_with_children_is_large_deletion():
    text = "- `src/a.py` does a\n  - nested\n  - other\n- `src/b.py`\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "large-deletion"


def test_nested_item_with_sibling_is_deleted():
    text = "- top\n  - `src/a.py`\n  - `src/b.py`\n- next\n"
    hunks, _ = _plan(text, _cand(text, "src/a.py"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (2, 2)


def test_first_ordered_item_after_paragraph_is_large_deletion():
    # `2.` cannot interrupt a paragraph: deleting item 1 would fold the list into the text
    text = "Steps:\n1. `src/a.py`\n2. `src/b.py`\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "large-deletion"


def test_non_subject_inline_mention_is_prose_mention():
    text = "Run `src/a.py` first.\n\n- see `src/b.py` and `src/c.py`\n- other\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "prose-mention"
    assert _demoted_kind(text, _cand(text, "src/c.py")) == "prose-mention"


def test_mention_inside_deleted_item_joins_the_hunk():
    text = "- `src/a.py` and `src/x.py`\n- `src/b.py`\n"
    subject = _cand(text, "src/a.py", fid="F001")
    other = _cand(text, "src/x.py", fid="F002")
    hunks, demoted = _plan(text, subject, other)
    assert demoted == []
    assert [(h["finding_id"], h["also"]) for h in hunks] == [("F001", ["F002"])]


def test_link_label_code_and_subject_link_in_one_item():
    text = "- [`src/app.py`](src/app.py) x\n- other\n"
    code = _cand(text, "src/app.py", context="inline-code", fid="F001")
    link = _cand(text, "src/app.py", context="link", fid="F002")
    hunks, demoted = _plan(text, code, link)
    assert demoted == []
    assert [(h["finding_id"], h["verb"], h["also"]) for h in hunks] == [
        ("F002", "delete", ["F001"])
    ]


# -- tables ----------------------------------------------------------------------------------


def test_delete_table_row_subject():
    text = "| File | Use |\n|---|---|\n| `src/a.py` | a |\n| `src/b.py` | b |\n"
    hunks, _ = _plan(text, _cand(text, "src/a.py"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (3, 3)
    assert hunks[0]["before"] == ["| `src/a.py` | a |"]
    assert hunks[0]["after"] == []


def test_last_table_data_row_is_large_deletion():
    text = "| File | Use |\n|---|---|\n| `src/a.py` | a |\n\nEnd.\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "large-deletion"


def test_header_row_token_is_never_deleted():
    text = "| `src/a.py` | Use |\n|---|---|\n| x | a |\n| y | b |\n"
    assert _demoted_kind(text, _cand(text, "src/a.py")) == "prose-mention"


# -- fences ----------------------------------------------------------------------------------


def test_delete_single_command_fence_line():
    text = "```bash\n$ make build\n$ make test\n```\n"
    hunks, _ = _plan(text, _cand(text, "build", kind="script"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (2, 2)
    assert hunks[0]["before"] == ["$ make build"]
    assert hunks[0]["verb"] == "delete"


def test_delete_fence_path_command_line():
    text = "```sh\npython scripts/run.py --x\nmake test\n```\n"
    hunks, _ = _plan(text, _cand(text, "scripts/run.py"))
    assert hunks[0]["before"] == ["python scripts/run.py --x"]


def test_compound_command_line_is_large_deletion():
    text = "```bash\nmake build && make test\nmake lint\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"
    text = "```bash\nmake build | tee log\nmake lint\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"


def test_only_command_in_fence_is_large_deletion():
    text = "```bash\nmake build\n\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"


def test_command_beside_only_comments_is_large_deletion():
    text = "```bash\n# build the docs\nmake build\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"


def test_continued_command_is_large_deletion():
    text = "```bash\nmake build \\\n  V=1\nmake test\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"


def test_command_with_output_lines_is_large_deletion():
    text = "```console\n$ make build\nbuilding...\n$ make test\n```\n"
    assert _demoted_kind(text, _cand(text, "build", kind="script")) == "large-deletion"


def test_non_shell_fence_line_is_large_deletion():
    text = "```python\nimport os\npython scripts/run.py\n```\n"
    cands = [t for t in extract_doc("README.md", text, NEVER)[0] if t["kind"] == "path"]
    if cands:  # the extractor may skip non-shell fences entirely
        assert _demoted_kind(text, _cand(text, "scripts/run.py")) == "large-deletion"


# -- trees -----------------------------------------------------------------------------------

TREE = "```text\nrepo/\n├── src/\n│   ├── app.py\n│   └── util.py\n└── README.md\n```\n"


def test_delete_tree_leaf_line():
    hunks, _ = _plan(TREE, _cand(TREE, "repo/src/app.py"))
    assert (hunks[0]["line_start"], hunks[0]["line_end"]) == (4, 4)
    assert hunks[0]["before"] == ["│   ├── app.py"]
    hunks, _ = _plan(TREE, _cand(TREE, "repo/README.md"))
    assert hunks[0]["before"] == ["└── README.md"]


def test_tree_parent_is_large_deletion():
    assert _demoted_kind(TREE, _cand(TREE, "repo/src/")) == "large-deletion"


# -- links, images, refdefs ------------------------------------------------------------------


def test_unlink_keeps_label():
    text = "Read [the guide](docs/guide.md) today.\n"
    hunks, _ = _plan(text, _cand(text, "docs/guide.md"))
    assert hunks[0]["verb"] == "unlink"
    assert hunks[0]["after"] == ["Read the guide today."]
    assert hunks[0]["new_text"] is None


def test_unlink_anchor_link():
    text = "See [setup](#setup) below.\n\n# Usage\n"
    tokens, _ = extract_doc("README.md", text, NEVER)
    assert any(t["kind"] == "anchor" for t in tokens)
    hunks, _ = _plan(text, _cand(text, "setup", kind="anchor"))
    assert hunks[0]["after"] == ["See setup below."]


def test_wrapped_link_is_prose_mention():
    text = "Read [the guide](docs/guide.md) today.\n"
    cand = _cand(text, "docs/guide.md")
    cand["link"] = None
    assert _demoted_kind(text, cand) == "prose-mention"


def test_image_is_prose_mention():
    text = "Logo: ![logo](img/logo.png)\n\n- ![logo](img/logo.png)\n- other\n"
    assert _demoted_kind(text, _cand(text, "img/logo.png")) == "prose-mention"
    assert _demoted_kind(text, _cand(text, "img/logo.png", nth=1)) == "prose-mention"


def test_refdef_delete_is_large_deletion():
    text = "See [the guide][g].\n\n[g]: docs/a.md\n"
    assert _demoted_kind(text, _cand(text, "docs/a.md")) == "large-deletion"


# -- merging ---------------------------------------------------------------------------------


def test_same_range_hunks_merge():
    text = "- [`src/app.py`](src/app.py) x\n- other\n"
    code = _cand(text, "src/app.py", "provable-replace", context="inline-code",
                 replacement="src/main.py", fid="F001")
    link = _cand(text, "src/app.py", "provable-replace", context="link",
                 replacement="src/main.py", fid="F002")
    hunks, demoted = _plan(text, code, link)
    assert demoted == []
    assert len(hunks) == 1
    assert hunks[0]["finding_id"] == "F001"
    assert hunks[0]["also"] == ["F002"]
    assert hunks[0]["after"] == ["- [`src/main.py`](src/main.py) x"]


def test_overlapping_different_range_is_large_deletion():
    text = "- `src/a.py` does a\n  see `src/old.py`\n- `src/b.py`\n"
    item = _cand(text, "src/a.py", fid="F001")
    inner = _cand(text, "src/old.py", "provable-replace", replacement="src/new.py",
                  fid="F002")
    hunks, demoted = _plan(text, item, inner)
    assert [h["finding_id"] for h in hunks] == ["F001"]
    assert [(d["id"], d["human_kind"]) for d in demoted] == [("F002", "large-deletion")]


def test_crlf_doc_gives_same_lines():
    text = "- `src/a.py`\r\n- `src/b.py`\r\n"
    hunks, _ = _plan(text, _cand(text.replace("\r\n", "\n"), "src/a.py"))
    assert hunks[0]["before"] == ["- `src/a.py`"]


def test_non_provable_candidates_are_ignored():
    text = "See `src/a.py`.\n"
    cand = _cand(text, "src/a.py")
    cand.update({"class": "human", "human_kind": "ambiguous-rename"})
    assert _plan(text, cand) == ([], [])


# -- run -------------------------------------------------------------------------------------


def test_findings_ordered_and_numbered(tmp_path: Path):
    root, workdir = tmp_path / "repo", tmp_path / "work"
    (root / "docs").mkdir(parents=True)
    readme = "- `src/a.py`\n- `src/b.py`\n\nRun `src/c.py`.\n"
    guide = "See `old.py` now.\r\n"
    (root / "README.md").write_bytes(readme.encode())
    (root / "docs" / "guide.md").write_bytes(guide.encode())
    c_mention = _cand(readme, "src/c.py")
    a_item = _cand(readme, "src/a.py")
    g_replace = _cand(guide.replace("\r\n", "\n"), "old.py", "provable-replace",
                      replacement="new.py", doc="docs/guide.md")
    summary = dict(a_item, line=2, col=2, end_col=12, text="src/b.py")
    summary.update({"class": "summary-only", "existed_then": False})
    honoured = [{"doc": "README.md", "line": 9, "col": 0, "kind": "path", "text": "x.py",
                 "reason": "planned"}]
    cands = [c_mention, summary, g_replace, a_item]
    for c in cands:
        del c["id"]
    write_json(workdir / "candidates.json",
               {"candidates": cands, "history_unavailable": True, "honoured": honoured})
    result = run(root, workdir)
    findings = read_json(workdir / "findings.json")
    assert findings == result["findings"]
    assert findings["history_unavailable"] is True
    assert findings["honoured"] == honoured
    got = [(f["id"], f["doc"], f["line"], f["class"], f["human_kind"])
           for f in findings["findings"]]
    assert got == [
        ("F001", "README.md", 1, "provable-delete", None),
        ("F002", "README.md", 2, "summary-only", None),
        ("F003", "README.md", 4, "human", "prose-mention"),
        ("F004", "docs/guide.md", 1, "provable-replace", None),
    ]
    hunks = read_json(workdir / "hunks-provable.json")["hunks"]
    assert [(h["id"], h["finding_id"], h["doc"], h["verb"]) for h in hunks] == [
        ("H001", "F001", "README.md", "delete"),
        ("H002", "F004", "docs/guide.md", "replace"),
    ]
    assert hunks[1]["before"] == ["See `old.py` now."]
    assert hunks[1]["after"] == ["See `new.py` now."]


def test_main_missing_candidates_exits_missing(tmp_path: Path):
    assert main([str(tmp_path), "--workdir", str(tmp_path / "work")]) == EXIT_MISSING


def test_main_ok(tmp_path: Path):
    write_json(tmp_path / "work" / "candidates.json",
               {"candidates": [], "history_unavailable": False, "honoured": []})
    assert main([str(tmp_path), "--workdir", str(tmp_path / "work")]) == EXIT_OK
    assert read_json(tmp_path / "work" / "hunks-provable.json") == {"hunks": []}


@pytest.mark.parametrize("info", ["", "sh", "PowerShell", "console"])
def test_shell_infos_allow_line_delete(info: str):
    text = f"```{info}\nmake build\nmake test\n```\n"
    hunks, _ = _plan(text, _cand(text, "build", kind="script"))
    assert hunks[0]["before"] == ["make build"]
