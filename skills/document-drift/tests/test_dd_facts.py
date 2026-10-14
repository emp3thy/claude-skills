from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_extract import extract_doc
from dd_facts import check_row, fact_tables, main, normalise, run

NEVER = re.compile(r"(?!)")


def _n(name: str, kind: str = "flag", parent: str | None = None, *,
       default: str | None = None, choices: list[str] | None = None,
       required: bool | None = None, file: str = "src/cli.py",
       line: int = 3) -> dict[str, Any]:
    return {"name": name, "kind": kind, "file": file, "line": line, "parent": parent,
            "hidden": False, "default": default, "choices": choices, "required": required}


def _one(text: str) -> dict[str, Any]:
    [table] = fact_tables(text)
    return table


def _row(table: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in table["rows"] if r["name"] == name)


FLAGS = ("## Options\n\n"
         "| Flag | Description | Default |\n"
         "|------|-------------|---------|\n"
         "| `--port` | The port | `8000` |\n"
         "| `--host` | The host | localhost |\n")


def test_fact_table_detection() -> None:
    table = _one(FLAGS)
    assert table["header_line"] == 3
    assert table["name_col"] == 0
    assert table["value_cols"] == {"Default": 2}
    assert [(r["line"], r["name"]) for r in table["rows"]] == [(5, "--port"), (6, "--host")]
    assert table["rows"][0]["cells"] == ["`--port`", "The port", "`8000`"]
    plain = "| Flag | Description |\n|---|---|\n| `--port` | The port |\n"
    assert fact_tables(plain) == []
    one_of = ("| Description | Name | One of |\n|---|---|---|\n"
              "| The mode | `--mode` | `a`, `b` |\n| The level | `--level` | `x` |\n")
    table = _one(one_of)
    assert table["name_col"] == 1 and table["value_cols"] == {"One of": 2}
    assert [r["name"] for r in table["rows"]] == ["--mode", "--level"]
    options_only = "| Options | Description |\n|---|---|\n| `--port` | The port |\n"
    assert fact_tables(options_only) == []


def test_row_with_stale_default_is_corrected() -> None:
    table = _one(FLAGS)
    names = [_n("--port", default="8080", line=12), _n("--host", default="localhost")]
    status, edit = check_row(_row(table, "--port"), table, names, [], doc="docs/cli.md")
    assert status == "corrected" and edit is not None
    assert edit == {
        "id": "", "doc": "docs/cli.md", "start_line": 5, "end_line": 5,
        "old": "| `--port` | The port | `8000` |", "new": "| `--port` | The port | `8080` |",
        "type": "fact", "source": "script", "status": "kept", "check": None,
        "human_kind": None, "reason": None, "claim": "--port Default is 8080",
        "evidence": ["src/cli.py:12"], "subject": "--port", "column": "Default",
        "old_cell": "`8000`", "new_cell": "`8080`"}
    assert check_row(_row(table, "--host"), table, names, []) == ("checked", None)
    bare = _one("| Flag | Default |\n|---|---|\n| `--port` | 8000 |\n")
    _, edit = check_row(bare["rows"][0], bare, names, [])
    assert edit is not None and edit["new"] == "| `--port` | 8080 |"
    assert edit["new_cell"] == "8080"


@pytest.mark.parametrize(("cell", "scan", "new"), [
    ("off", "false", None), ("`disabled`", "False", None), ("no", "false", None),
    ("On", "true", None), ("enabled", "True", None), ("yes", "true", None),
    ("off", "true", "on"), ("Disabled", "true", "Enabled"), ("`no`", "true", "`yes`"),
    ("`0`", "true", None), ("✗", "true", "✓"), ("Y", "false", "N")])
def test_boolean_defaults_normalise_before_comparison(cell: str, scan: str,
                                                       new: str | None) -> None:
    assert normalise("off", "Default") == "false"
    assert normalise("Enabled", "default") == "true"
    table = _one(f"| Flag | Default |\n|---|---|\n| `--debug` | {cell} |\n")
    status, edit = check_row(table["rows"][0], table, [_n("--debug", default=scan)], [])
    if new is None:
        assert (status, edit) == ("checked", None)
    else:
        assert status == "corrected" and edit is not None
        assert edit["new"] == f"| `--debug` | {new} |"


@pytest.mark.parametrize(("column", "cell", "scan", "status"), [
    ("Required", "✓", True, "checked"), ("Required", "✔", True, "checked"),
    ("Required", "y", True, "checked"), ("Required", "✗", False, "checked"),
    ("Required", "✘", False, "checked"), ("Required", "n", False, "checked"),
    ("Required", "x", False, "checked"), ("Required", "-", False, "checked"),
    ("Required", "see notes", False, "checked"), ("Required", "✓", False, "corrected"),
    ("Default", "✓", "true", "checked"), ("Default", "x", "false", "checked"),
    ("Default", "see notes", "false", "checked"),
    ("Default", "enabled by default", "false", "checked")])
def test_unknown_boolean_words_are_left_alone(column: str, cell: str, scan: Any,
                                              status: str) -> None:
    fact = {"required": scan} if column == "Required" else {"default": scan}
    table = _one(f"| Flag | {column} |\n|---|---|\n| `--debug` | {cell} |\n")
    got, edit = check_row(table["rows"][0], table, [_n("--debug", **fact)], [])
    assert got == status
    if status == "checked":
        assert edit is None
    else:
        assert edit is not None and edit["new"] == "| `--debug` | ✗ |"


@pytest.mark.parametrize("cell", ["-", "None", "`null`", "n/a", "(none)", "none", ""])
def test_no_default_spellings_are_equal(cell: str) -> None:
    assert normalise(cell, "Default") is None
    table = _one(f"| Flag | Default |\n|---|---|\n| `--name` | {cell} |\n")
    assert check_row(table["rows"][0], table, [_n("--name")], []) == ("checked", None)


def test_null_fact_never_rewrites_a_value_and_null_cell_gets_backticks() -> None:
    table = _one("| Flag | Default |\n|---|---|\n| `--a` | 5 |\n| `--b` | - |\n| `--c` |  |\n")
    names = [_n("--a"), _n("--b", default="7"), _n("--c", default="x y")]
    assert check_row(_row(table, "--a"), table, names, []) == ("checked", None)
    _, edit = check_row(_row(table, "--b"), table, names, [])
    assert edit is not None and edit["new"] == "| `--b` | `7` |"
    _, edit = check_row(_row(table, "--c"), table, names, [])
    assert edit is not None and edit["new"] == "| `--c` | `x y` |"


def test_choices_cell_compares_as_a_set() -> None:
    assert normalise(r"`b` \| `a`", "Choices") == "a, b"
    assert normalise("a, b", "Values") == "a, b"
    text = ("| Flag | Choices |\n|---|---|\n"
            r"| `--mode` | b \| a |" "\n"
            "| `--level` | a, c |\n"
            "| `--fmt` | `json`,`text` |\n"
            "| `--out` | - |\n")
    table = _one(text)
    names = [_n("--mode", choices=["a", "b"]), _n("--level", choices=["a", "b"]),
             _n("--fmt", choices=["json", "text", "yaml"]), _n("--out", choices=["x", "y"])]
    assert check_row(_row(table, "--mode"), table, names, []) == ("checked", None)
    _, edit = check_row(_row(table, "--level"), table, names, [])
    assert edit is not None and edit["new"] == "| `--level` | a, b |"
    assert edit["claim"] == "--level Choices is a, b"
    _, edit = check_row(_row(table, "--fmt"), table, names, [])
    assert edit is not None and edit["new"] == "| `--fmt` | `json`,`text`,`yaml` |"
    _, edit = check_row(_row(table, "--out"), table, names, [])
    assert edit is not None and edit["new"] == "| `--out` | `x`, `y` |"
    piped = _one("| Flag | Values |\n|---|---|\n" r"| `--mode` | `a` \| `c` |" "\n")
    _, edit = check_row(piped["rows"][0], piped, names, [])
    assert edit is not None and edit["new"] == r"| `--mode` | `a` \| `b` |"


def test_required_column() -> None:
    assert normalise("Required", "Required") == "true"
    assert normalise("optional", "Required?") == "false"
    assert normalise("yes", "required") == "true"
    text = ("| Param | Required | Default |\n|---|---|---|\n"
            "| `query` | yes | - |\n| `limit` | no | `10` |\n| `scope` | optional | - |\n")
    table = _one(text)
    names = [_n("query", "param", "search", required=True),
             _n("limit", "param", "search", required=False, default="10"),
             _n("scope", "param", "search", required=True)]
    assert check_row(_row(table, "query"), table, names, []) == ("checked", None)
    assert check_row(_row(table, "limit"), table, names, []) == ("checked", None)
    status, edit = check_row(_row(table, "scope"), table, names, [])
    assert status == "corrected" and edit is not None
    assert edit["new"] == "| `scope` | required | - |"
    assert (edit["column"], edit["old_cell"], edit["new_cell"]) == (
        "Required", "optional", "required")


INIT_SYNC = [_n("--force", parent="init", default="false", line=4),
             _n("--force", parent="sync", default="true", line=9)]


def test_rows_are_scoped_by_the_heading_parent(tmp_path: Path) -> None:
    doc = ("# CLI\n\n## `init`\n\n| Flag | Default |\n|---|---|\n| `--force` | off |\n\n"
           "## sync\n\n| Flag | Default |\n|---|---|\n| `--force` | off |\n\n"
           "## Other\n\n| Flag | Default |\n|---|---|\n| `--force` | off |\n")
    first, second, third = fact_tables(doc)
    assert check_row(first["rows"][0], first, INIT_SYNC, ["init"]) == ("checked", None)
    status, edit = check_row(second["rows"][0], second, INIT_SYNC, ["sync"])
    assert status == "corrected" and edit is not None
    assert edit["new"] == "| `--force` | on |" and edit["evidence"] == ["src/cli.py:9"]
    assert check_row(third["rows"][0], third, INIT_SYNC, []) == ("skipped", None)
    root, workdir = _setup(tmp_path, {"docs/cli.md": doc}, INIT_SYNC)
    result = run(root, workdir, {})
    assert [(e["start_line"], e["new"]) for e in result["edits"] if e["type"] == "fact"] == [
        (13, "| `--force` | on |")]
    assert result["counts"]["facts"] == {"rows_checked": 2, "corrected": 1, "not_in_scan": 0}


def test_single_parent_flag_matches_without_a_heading() -> None:
    table = _one("| Flag | Default |\n|---|---|\n| `--force` | on |\n")
    status, _ = check_row(table["rows"][0], table, INIT_SYNC[:1], [])
    assert status == "corrected"


def test_unknown_name_is_a_hint_with_nearest() -> None:
    table = _one("| Flag | Default |\n|---|---|\n| `--worker` | 2 |\n| `--zzz` | 1 |\n"
                 "| `serve` | - |\n")
    names = [_n("--workers", default="2"), _n("WORKER", "env"), _n("serve", "command")]
    assert check_row(_row(table, "--worker"), table, names, []) == (
        "not-in-scan", {"line": 3, "kind": "not-in-scan",
                        "text": "not in scan: --worker; nearest --workers"})
    assert check_row(_row(table, "--zzz"), table, names, []) == (
        "not-in-scan", {"line": 4, "kind": "not-in-scan", "text": "not in scan: --zzz"})
    assert check_row(_row(table, "serve"), table, names, []) == ("skipped", None)


def test_several_matches_are_skipped() -> None:
    table = _one("| Name | Default |\n|---|---|\n| `TIMEOUT` | 5 |\n| `RETRIES` | 1 |\n")
    names = [_n("TIMEOUT", "env", default="10", file="a.py"),
             _n("TIMEOUT", "env", default="30", file="b.py"),
             _n("RETRIES", "env", default="3", file="a.py"),
             _n("RETRIES", "env", default="3", file="b.py")]
    assert check_row(_row(table, "TIMEOUT"), table, names, []) == ("skipped", None)
    status, edit = check_row(_row(table, "RETRIES"), table, names, [])
    assert status == "corrected" and edit is not None and edit["evidence"] == ["a.py:3"]


def _setup(tmp_path: Path, docs: Mapping[str, str], names: Iterable[dict[str, Any]],
           never: str = NEVER.pattern, script: bool = True) -> tuple[Path, Path]:
    root, workdir = tmp_path / "repo", tmp_path / "work"
    root.mkdir(parents=True)
    for doc, text in docs.items():
        (root / doc).parent.mkdir(parents=True, exist_ok=True)
        (root / doc).write_bytes(text.encode("utf-8"))
    write_json(workdir / "inventory.json", {"docs": sorted(docs), "files": sorted(docs),
                                            "excluded": [], "skipped": [],
                                            "never_edit_re": never})
    tokens: dict[str, Any] = {}
    markers: list[Any] = []
    for doc, text in docs.items():
        tokens[doc], doc_markers = extract_doc(doc, text, re.compile(never))
        markers += doc_markers
    write_json(workdir / "tokens.json", {"docs": tokens, "markers": markers, "skipped": []})
    write_json(workdir / "patterns.json", {"names": list(names), "names_then": None,
                                           "skipped": []})
    if script:
        write_json(workdir / "script-edits.json", {
            "edits": [{"id": "c001", "doc": "docs/a.md", "type": "cite"}],
            "hints": {"docs/a.md": [{"line": 1, "kind": "cite-unresolved", "text": "x"}]},
            "counts": {"citations": {"checked": 1},
                       "facts": {"rows_checked": 0, "corrected": 0, "not_in_scan": 0}}})
    return root, workdir


def test_run_appends_to_script_edits(tmp_path: Path) -> None:
    a = ("| Flag | Default |\n|---|---|\n| `--port` | 8000 |\n| `--host` | x |\n"
         "| `--gone` | 1 |\n\n<!-- drift-ignore: pinned -->\n| Flag | Default |\n|---|---|\n"
         "| `--port` | 1 |\n")
    b = "# B\n\n| Flag | Default |\n|---|---|\n| `--host` | y |\n"
    names = [_n("--port", default="8080"), _n("--host", default="x")]
    root, workdir = _setup(tmp_path, {"docs/a.md": a, "docs/b.md": b}, names)
    result = run(root, workdir, {})
    assert read_json(workdir / "script-edits.json") == result
    fact = [e for e in result["edits"] if e["type"] == "fact"]
    assert [(e["id"], e["doc"], e["start_line"]) for e in fact] == [
        ("f001", "docs/a.md", 3), ("f002", "docs/b.md", 5)]
    assert result["edits"][0]["id"] == "c001"
    assert result["hints"] == {"docs/a.md": [
        {"line": 1, "kind": "cite-unresolved", "text": "x"},
        {"line": 5, "kind": "not-in-scan", "text": "not in scan: --gone"}]}
    assert result["counts"] == {"citations": {"checked": 1},
                                "facts": {"rows_checked": 3, "corrected": 2, "not_in_scan": 1}}
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_OK
    assert read_json(workdir / "script-edits.json") == result  # a rerun replaces, not appends


def test_never_edit_section_is_skipped(tmp_path: Path) -> None:
    doc = ("# Changelog\n\n| Flag | Default |\n|---|---|\n| `--port` | 1 |\n")
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, [_n("--port", default="2")],
                           never="(?i)changelog")
    result = run(root, workdir, {})
    assert [e for e in result["edits"] if e["type"] == "fact"] == []
    assert result["counts"]["facts"] == {"rows_checked": 0, "corrected": 0, "not_in_scan": 0}


@pytest.mark.parametrize(("name", "step"), [("patterns.json", "dd_patterns"),
                                            ("script-edits.json", "dd_cite")])
def test_missing_inputs_raise(tmp_path: Path, name: str, step: str) -> None:
    root, workdir = _setup(tmp_path, {"docs/a.md": "x\n"}, [])
    (workdir / name).unlink()
    with pytest.raises(StepError) as info:
        run(root, workdir, {})
    assert info.value.code == EXIT_MISSING and step in str(info.value)
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_MISSING


@pytest.mark.parametrize(("cell", "default", "new"), [
    ("`30` seconds", "30", None), ("`8080` (dev)", "8080", None),
    ("`8000` (dev)", "8080", "`8080` (dev)"), ("about 30 seconds", "60", None),
    ("`None` (unset)", "5", "`5` (unset)"), ("see `config.py`", "5", None)])
def test_cell_text_around_the_value_is_kept(cell: str, default: str, new: str | None) -> None:
    table = _one(f"| Flag | Default |\n|---|---|\n| `--timeout` | {cell} |\n")
    status, edit = check_row(table["rows"][0], table, [_n("--timeout", default=default)], [])
    assert status == ("checked" if new is None else "corrected")
    assert (edit["new"] if edit else None) == (
        None if new is None else f"| `--timeout` | {new} |")


def test_pipes_are_unescaped_to_compare_and_escaped_to_write() -> None:
    table = _one("| Flag | Default |\n|---|---|\n| `--sep` | `\\|` |\n| `--join` | `,` |\n")
    assert [len(r["cells"]) for r in table["rows"]] == [2, 2]
    names = [_n("--sep", default="|"), _n("--join", default="|")]
    assert check_row(_row(table, "--sep"), table, names, []) == ("checked", None)
    _, edit = check_row(_row(table, "--join"), table, names, [])
    assert edit is not None and edit["new"] == "| `--join` | `\\|` |"
    choices = _one("| Flag | Choices |\n|---|---|\n| `--sep` | `\\|`, `,` |\n")
    assert check_row(choices["rows"][0], choices,
                     [_n("--sep", choices=["|", ","])], []) == ("checked", None)
    _, edit = check_row(choices["rows"][0], choices, [_n("--sep", choices=["|", ";"])], [])
    assert edit is not None and edit["new"] == "| `--sep` | `\\|`, `;` |"


def test_heading_scope_never_borrows_another_commands_flag() -> None:
    table = _one("| Flag | Default |\n|---|---|\n| `--force` | off |\n")
    sync_only = [INIT_SYNC[1]]
    assert check_row(table["rows"][0], table, sync_only, ["init"]) == ("skipped", None)
    global_flag = [*sync_only, _n("--force", default="true", line=20)]
    status, edit = check_row(table["rows"][0], table, global_flag, ["init"])
    assert status == "corrected" and edit is not None
    assert edit["evidence"] == ["src/cli.py:20"] and edit["new"] == "| `--force` | on |"


@pytest.mark.parametrize(("flag", "cell", "default", "new"), [
    ("--axis", "`x`", "y", "`y`"), ("--color", "`auto`", "off", "`off`"),
    ("--color", "`off`", "off", None), ("--mode", "on", "True", None)])
def test_boolean_words_apply_only_to_boolean_defaults(flag: str, cell: str, default: str,
                                                      new: str | None) -> None:
    table = _one(f"| Flag | Default |\n|---|---|\n| `{flag}` | {cell} |\n")
    status, edit = check_row(table["rows"][0], table, [_n(flag, default=default)], [])
    assert status == ("checked" if new is None else "corrected")
    if new is not None:
        assert edit is not None and edit["new"] == f"| `{flag}` | {new} |"
        assert edit["claim"] == f"{flag} Default is {default}"


@pytest.mark.parametrize(("cell", "default", "new"), [
    ("-", "false", None), ("", "False", None), ("`null`", "false", None),
    ("n/a", "false", None), ("none", "false", None),
    ("-", "8080", "`8080`"), ("", "auto", "`auto`"), ("-", "true", "`true`")])
def test_no_value_cell_against_boolean_false_is_left_alone(cell: str, default: str,
                                                          new: str | None) -> None:
    table = _one(f"| Flag | Default |\n|---|---|\n| `--x` | {cell} |\n")
    status, edit = check_row(table["rows"][0], table, [_n("--x", default=default)], [])
    assert status == ("checked" if new is None else "corrected")
    if new is not None:
        assert edit is not None and edit["new"] == f"| `--x` | {new} |"
