"""Tests for dd_readme: the citation check, the statement split and check_step (phase B spec
6.4, 6.5, 7)."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import dd_readme
from dd_common import read_json, write_json
from dd_config import DEFAULTS


def _surface(eid: str, kind: str, name: str, *, parent: str | None = None,
             hidden: bool = False) -> dict[str, Any]:
    return {"id": eid, "kind": kind, "name": name, "parent": parent,
            "summary": f"the {name} entry", "default": None, "defined_at": "src/cli.py:4",
            "user_facing": True, "hidden": hidden}


SHEETS: dict[str, Any] = {
    "sheets": {"a01": {
        "area": "a01", "dismissed": [],
        "surface": [_surface("a01-s01", "command", "sync"),
                    _surface("a01-s02", "flag", "--force", parent="sync"),
                    _surface("a01-s03", "flag", "--legacy", parent="sync", hidden=True),
                    _surface("a01-s04", "env", "APP_TOKEN")],
        "behaviours": [{"id": "a01-b01", "statement": "`sync` writes `state.db`",
                        "evidence": ["src/cli.py:12"]}]}},
    "unchecked": [], "filled": 0, "hidden_corrected": 0}


def _out(lines: list[str], *claims: tuple[int, int, list[str]]) -> dict[str, Any]:
    return {"text": "\n".join(lines) + "\n",
            "claims": [{"start_line": s, "end_line": e, "cites": list(c)} for s, e, c in claims]}


def _check(output: dict[str, Any], readme_lines: int = 300) -> tuple[list[str], dict[str, Any]]:
    return dd_readme.check(copy.deepcopy(output), copy.deepcopy(SHEETS), readme_lines)


VALID = [
    "# demo",                                  # 1
    "",                                        # 2
    "`sync` pulls the remote state",           # 3
    "and writes `state.db`.",                  # 4
    "",                                        # 5
    "## Commands",                             # 6
    "",                                        # 7
    "- `sync` pulls the remote state.",        # 8
    "  It writes `state.db`.",                 # 9
    "- `sync --force` overwrites local rows.",  # 10
    "",                                        # 11
    "| Name | Meaning |",                       # 12
    "|---|---|",                               # 13
    "| `APP_TOKEN` | the token |",             # 14
    "",                                        # 15
    "```sh",                                   # 16
    "sync --force",                            # 17
    "```",                                     # 18
]
VALID_CLAIMS = ((3, 4, ["a01-s01", "a01-b01"]), (8, 10, ["a01-s01", "a01-s02", "a01-b01"]),
                (12, 14, ["a01-s04"]), (17, 17, ["a01-s01", "a01-s02"]))


def test_valid_output_has_no_problems_and_statements_in_order() -> None:
    output = _out(VALID, *VALID_CLAIMS)
    problems, readme = _check(output)
    assert problems == []
    assert readme["text"] == output["text"]
    assert readme["claims"] == output["claims"]
    assert readme["cites_added"] == 0 and readme["cited_unnamed"] == 0
    assert [(s["id"], s["start_line"], s["end_line"], s["section"], s["kind"])
            for s in readme["statements"]] == [
        ("r-s001", 3, 4, "demo", "paragraph"),
        ("r-s002", 8, 9, "Commands", "item"),
        ("r-s003", 10, 10, "Commands", "item"),
        ("r-s004", 14, 14, "Commands", "row"),
        ("r-s005", 16, 18, "Commands", "fence")]
    first = readme["statements"][0]
    assert first["text"] == "`sync` pulls the remote state\nand writes `state.db`."
    assert first["prereject"] is None and first["claims"] == [0]
    assert readme["statements"][4]["text"] == "```sh\nsync --force\n```"
    assert readme["statements"][4]["cites"] == ["a01-s01", "a01-s02"]


def test_first_line_must_be_a_heading_and_length_capped() -> None:
    claims = (3, 4, ["a01-s01", "a01-b01"])
    problems, readme = _check(_out(["demo", "", "`sync` pulls", "it writes."], claims))
    assert problems == ["the first line is not a level-one heading",
                        "line 1 is in no claim: 'demo'"] and readme == {}
    problems, _ = _check(_out(["## demo", "", "`sync` pulls", "it writes."], claims))
    assert problems == ["the first line is not a level-one heading"]
    problems, _ = _check(_out(["# demo", "", "`sync` pulls", "it writes."], claims),
                         readme_lines=3)
    assert problems == ["the text has 4 lines, more than readme_lines 3"]
    assert _check(_out(["# demo", "", "`sync` pulls", "it writes."], claims),
                  readme_lines=4)[0] == []


def test_fence_lines_need_a_claim() -> None:
    lines = ["# demo", "", "```sh", "sync --force", "# never mind", "```"]
    problems, _ = _check(_out(lines, (4, 4, ["a01-s01"])))
    assert problems == ["line 5 is in no claim: '# never mind'"]
    assert _check(_out(lines, (4, 5, ["a01-s01"])))[0] == []


def test_overlapping_claims_are_invalid() -> None:
    lines = ["# demo", "", "- `sync` pulls.", "- `APP_TOKEN` is read."]
    problems, _ = _check(_out(lines, (3, 4, ["a01-s01"]), (4, 4, ["a01-s04"])))
    assert problems == ["line 4 is in claims 0 and 1"]


def test_unknown_cite_is_invalid() -> None:
    lines = ["# demo", "", "`sync` pulls.", "", "`APP_TOKEN` is read."]
    problems, _ = _check(_out(lines, (3, 3, []), (5, 5, ["a01-s04", "a09-s01"])))
    assert problems == ["claims[0] cites nothing",
                        "claims[1] cites a09-s01, which is not in sheets.json"]


def test_naming_an_uncited_entry_adds_the_cite() -> None:
    lines = ["# demo", "", "`sync` reads `APP_TOKEN`."]
    problems, readme = _check(_out(lines, (3, 3, ["a01-s01"])))
    assert problems == []
    assert readme["cites_added"] == 1
    assert readme["claims"][0]["cites"] == ["a01-s01", "a01-s04"]
    assert readme["statements"][0]["cites"] == ["a01-s01", "a01-s04"]


def test_cited_but_unnamed_is_counted_not_removed() -> None:
    lines = ["# demo", "", "`sync` pulls the remote state."]
    problems, readme = _check(_out(lines, (3, 3, ["a01-s01", "a01-s04", "a01-b01"])))
    assert problems == []
    assert readme["cited_unnamed"] == 1 and readme["cites_added"] == 0
    assert readme["claims"][0]["cites"] == ["a01-s01", "a01-s04", "a01-b01"]
    # the statement keeps the named surface entry and every behaviour
    assert readme["statements"][0]["cites"] == ["a01-b01", "a01-s01"]


def test_hidden_name_rejects_the_row_not_the_table() -> None:
    rows = [f"| `sync` | row {n} |" for n in range(30)]
    rows[17] = "| `--legacy` | old mode |"
    lines = ["# demo", "", "## Flags", "", "| Name | Meaning |", "|---|---|", *rows]
    problems, readme = _check(_out(lines, (5, len(lines), ["a01-s01", "a01-s03"])))
    assert problems == []
    statements = readme["statements"]
    assert len(statements) == 30 and {s["kind"] for s in statements} == {"row"}
    rejected = [s for s in statements if s["prereject"]]
    assert [(s["start_line"], s["prereject"]) for s in rejected] == [
        (24, "names hidden --legacy")]
    assert rejected[0]["cites"] == ["a01-s03"]
    assert all(s["cites"] == ["a01-s01"] for s in statements if not s["prereject"])


def test_hidden_entry_sharing_a_visible_name_rejects_where_it_is_cited() -> None:
    sheets = copy.deepcopy(SHEETS)
    sheets["sheets"]["a01"]["surface"] = [
        _surface("a01-s01", "command", "sync"),
        _surface("a01-s02", "flag", "--force", parent="pull"),
        _surface("a01-s03", "flag", "--force", parent="sync", hidden=True)]
    lines = ["# demo", "", "- `--force` forces sync", "", "- `--force` forces pull"]
    problems, readme = dd_readme.check(
        _out(lines, (3, 3, ["a01-s03"]), (5, 5, ["a01-s02"])), sheets, 300)
    assert problems == []
    assert [(s["cites"], s["prereject"]) for s in readme["statements"]] == [
        (["a01-s03"], "names hidden --force"), (["a01-s02"], None)]


def test_item_keeps_an_indented_fence_and_indented_lines_after_a_blank() -> None:
    lines = ["# demo", "",
             "- `sync` pulls the remote state:",   # 3
             "  ```sh",                             # 4
             "  sync --force  # always overwrites",  # 5
             "  ```",                               # 6
             "",                                    # 7
             "  It writes `state.db`.",             # 8
             "",                                    # 9
             "- `APP_TOKEN` is read.",              # 10
             "",                                    # 11
             "Then `sync` runs."]                   # 12
    problems, readme = _check(_out(lines, (3, 8, ["a01-s01", "a01-s02", "a01-b01"]),
                                   (10, 10, ["a01-s04"]), (12, 12, ["a01-s01"])))
    assert problems == []
    assert [(s["start_line"], s["end_line"], s["kind"], s["prereject"])
            for s in readme["statements"]] == [
        (3, 8, "item", None), (10, 10, "item", None), (12, 12, "paragraph", None)]
    # a guarantee word in the item's own prose still pre-rejects it
    lines[7] = "  It always writes `state.db`."
    _, readme = _check(_out(lines, (3, 8, ["a01-s01", "a01-s02", "a01-b01"]),
                            (10, 10, ["a01-s04"]), (12, 12, ["a01-s01"])))
    assert readme["statements"][0]["prereject"] == "guarantee word"


def test_guarantee_word_prerejects_outside_fences() -> None:
    lines = ["# demo", "", "`sync` always pulls the remote state.", "",
             "- `sync` pulls.", "", "```sh", "sync --force  # always overwrites", "```"]
    problems, readme = _check(_out(lines, (3, 3, ["a01-s01"]), (5, 5, ["a01-s01"]),
                                   (8, 8, ["a01-s02"])))
    assert problems == []
    assert [(s["kind"], s["prereject"]) for s in readme["statements"]] == [
        ("paragraph", "guarantee word"), ("item", None), ("fence", None)]


def test_statement_cites_are_the_named_surface_entries_plus_behaviours() -> None:
    lines = ["# demo", "", "- `sync` pulls the remote state.", "- `APP_TOKEN` is the token."]
    problems, readme = _check(_out(lines, (3, 4, ["a01-s01", "a01-s04", "a01-b01"])))
    assert problems == []
    assert [s["cites"] for s in readme["statements"]] == [["a01-b01", "a01-s01"],
                                                          ["a01-b01", "a01-s04"]]


def test_dollar_prefixed_env_name_counts_as_named() -> None:
    lines = ["# demo", "", "- Set `$APP_TOKEN` to the token.", "", "- `sync` uses `$APP_TOKEN`."]
    problems, readme = _check(_out(lines, (3, 3, ["a01-s04"]), (5, 5, ["a01-s01"])))
    assert problems == []
    assert readme["cited_unnamed"] == 0
    assert readme["cites_added"] == 1  # the span `$APP_TOKEN` names a01-s04
    assert readme["claims"][1]["cites"] == ["a01-s01", "a01-s04"]
    assert [s["cites"] for s in readme["statements"]] == [["a01-s04"], ["a01-s01", "a01-s04"]]


def test_table_header_and_separator_are_not_statements_and_rows_split_tables() -> None:
    lines = ["# demo", "", "| Name | Meaning |", "| :--- | ---: |", "| `sync` | pulls |", "",
             "| Variable | Meaning |", "|---|---|", "| `APP_TOKEN` | token |",
             "text after", "### Sub", "plain"]
    problems, readme = _check(_out(lines, (3, 5, ["a01-s01"]), (7, 10, ["a01-s04"]),
                                   (12, 12, ["a01-b01"])))
    assert problems == []
    assert [(s["start_line"], s["kind"], s["section"]) for s in readme["statements"]] == [
        (5, "row", "demo"), (9, "row", "demo"), (10, "paragraph", "demo"),
        (12, "paragraph", "Sub")]


# ---------------------------------------------------------------- check_step

def _workdir(tmp_path: Path, output: dict[str, Any] | None) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    workdir = root / ".document-drift"
    (workdir / "readme").mkdir(parents=True)
    write_json(workdir / "sheets.json", SHEETS)
    entry = {"id": "r001", "role": "readme", "prompt": (workdir / "p.md").as_posix(),
             "output": (workdir / "readme" / "r001.json").as_posix(), "model": "opus"}
    write_json(workdir / "plan-readme.json", [entry] if output is not None else [])
    if output is not None:
        write_json(workdir / "readme" / "r001.json", output)
    human = [{"doc": "docs/a.md", "line": 3, "kind": "unsure", "text": "x", "evidence": []},
             {"doc": "docs/z.md", "line": 1, "kind": "unsure", "text": "y", "evidence": []}]
    write_json(workdir / "edits.json", {"edits": [], "human": human})
    write_json(workdir / "plan-verify.json", [])
    return root, workdir


def test_check_step_writes_readme_json_the_create_edit_and_batches(tmp_path: Path) -> None:
    lines = ["# demo", "", "`sync` always pulls.", "", "## Flags", "",
             "- `--legacy` keeps the old mode.", "- `--force` overwrites local rows."]
    output = _out(lines, (3, 3, ["a01-s01"]), (7, 8, ["a01-s02", "a01-s03"]))
    root, workdir = _workdir(tmp_path, output)
    config = copy.deepcopy(DEFAULTS)
    readme = dd_readme.check_step(root, workdir, config, frozenset())
    assert readme is not None
    assert read_json(workdir / "readme.json") == readme
    assert len(readme["statements"]) == 3
    edits = read_json(workdir / "edits.json")
    assert edits["edits"] == [{
        "id": "r001", "doc": "README.md", "start_line": 1, "end_line": 1, "old": "", "new": "",
        "type": "create", "claim": "readme from 1 sheets", "evidence": [], "subject": None,
        "source": "readme", "status": "kept", "check": None, "human_kind": None,
        "reason": None, "statements": 3}]
    assert edits["human"] == [
        {"doc": "README.md", "line": 3, "kind": "readme-rejected",
         "text": "`sync` always pulls.", "evidence": ["guarantee word"]},
        {"doc": "README.md", "line": 7, "kind": "readme-rejected",
         "text": "- `--legacy` keeps the old mode.", "evidence": ["names hidden --legacy"]},
        {"doc": "docs/a.md", "line": 3, "kind": "unsure", "text": "x", "evidence": []},
        {"doc": "docs/z.md", "line": 1, "kind": "unsure", "text": "y", "evidence": []}]
    plan = read_json(workdir / "plan-verify.json")
    assert [(e["id"], e["statements"]) for e in plan] == [("v01", ["r-s003"])]


def test_check_step_without_a_usable_output_writes_no_readme(tmp_path: Path) -> None:
    config = copy.deepcopy(DEFAULTS)
    root, workdir = _workdir(tmp_path, None)
    assert dd_readme.check_step(root, workdir, config, frozenset()) is None
    assert read_json(workdir / "readme.json") == {"invalid": ["no writer output"]}
    assert read_json(workdir / "edits.json")["edits"] == []
    assert read_json(workdir / "plan-verify.json") == []

    bad = _out(["## demo", "", "`sync` pulls."], (3, 3, ["a01-s01"]))
    root, workdir = _workdir(tmp_path / "bad", bad)
    assert dd_readme.check_step(root, workdir, config, frozenset({"r001"})) is None
    assert read_json(workdir / "readme.json") == {
        "invalid": ["the first line is not a level-one heading"]}
    assert read_json(workdir / "edits.json")["edits"] == []
    assert read_json(workdir / "plan-verify.json") == []
