from __future__ import annotations

from pathlib import Path
from typing import Any

from dd_common import read_json, write_json
from dd_gaps import candidates, documented, gaps, lists, run, split_by_cap


def _n(name: str, kind: str = "command", parent: str | None = None, file: str = "src/a.py",
       line: int = 1, hidden: bool = False) -> Any:
    return {"name": name, "kind": kind, "file": file, "line": line, "parent": parent,
            "hidden": hidden}


def _table(*subjects: str, heading: str = "## Commands") -> str:
    rows = "\n".join(f"| `{s}` | does it |" for s in subjects)
    return f"{heading}\n\n| Name | Description |\n|---|---|\n{rows}\n"


def test_documented_whole_word_and_flag_keeps_dashes() -> None:
    force = _n("--force", "flag")
    assert not documented(force, {"README.md": "Use force to push. The forceful option.\n"})
    assert documented(force, {"README.md": "Pass `--force` to push.\n"})
    assert documented(force, {"README.md": "usage: x [--force]\n"})
    assert not documented(force, {"README.md": "Pass `--force-all` here.\n"})
    assert not documented(_n("serve"), {"README.md": "We observe servers.\n"})
    assert documented(_n("serve"), {"README.md": "Run `serve` now.\n"})
    assert documented(_n("db migrate"), {"README.md": "Run db migrate first.\n"})
    route = _n("/users/<id>", "route")
    assert documented(route, {"README.md": "GET /users/:id returns it\n"})
    assert documented(_n("/users/{uid}", "route"), {"README.md": "GET /users/<id>\n"})
    assert not documented(route, {"README.md": "GET /accounts/:id\n"})


def test_mcp_spellings_match() -> None:
    name = _n("memory_retrieve", "tool")
    for spelling in ("memory.retrieve", "memory_retrieve", "mcp__better-memory__memory_retrieve"):
        assert documented(name, {"a.md": f"Call `{spelling}` to read.\n"}), spelling
    assert documented(_n("mcp__s__memory-retrieve", "tool"),
                      {"a.md": "```\nmemory.retrieve(query)\n```\n"})
    assert not documented(name, {"a.md": "Call `memory_retrieve_all`.\n"})


def test_param_documented_only_under_tool_heading() -> None:
    param = _n("query", "param", parent="memory_retrieve")
    elsewhere = "## Other tool\n\nTakes a query.\n\n## memory_retrieve\n\nNo word here.\n"
    assert not documented(param, {"a.md": elsewhere})
    under = "## Other\n\nx\n\n## `memory.retrieve`\n\nTakes a query.\n\n### Details\n\nmore\n"
    assert documented(param, {"a.md": under})
    after = "## memory_retrieve\n\nx\n\n## Next\n\nTakes a query.\n"
    assert not documented(param, {"a.md": after})
    nested = "## memory_retrieve\n\n### Params\n\nTakes a query.\n"
    assert documented(param, {"a.md": nested})


def test_list_needs_three_subjects_of_one_kind() -> None:
    names = [_n("alpha"), _n("beta"), _n("gamma"), _n("ENV_X", "env")]
    found = lists({"a.md": _table("alpha", "beta", "gamma")}, names)
    assert len(found) == 1
    assert found[0]["kind"] == "command"
    assert found[0]["subjects"] == ["alpha", "beta", "gamma"]
    assert found[0]["scope"] is None
    assert (found[0]["line_start"], found[0]["line_end"]) == (3, 7)
    assert lists({"a.md": _table("alpha", "beta")}, names) == []
    assert lists({"a.md": _table("alpha", "beta", "ENV_X")}, names) == []
    bullets = "- `alpha` first\n- `beta` second\n  - `gamma` nested\n- `gamma` third\n"
    got = lists({"b.md": bullets}, names)
    assert [x["subjects"] for x in got] == [["alpha", "beta", "gamma"]]
    assert (got[0]["line_start"], got[0]["line_end"]) == (1, 4)
    assert lists({"b.md": "- `alpha` first\n- `beta` second\n  - `gamma` nested\n"}, names) == []
    plain = "| a | b |\n|---|---|\n| alpha | x |\n| beta | y |\n| gamma | z |\n"
    assert len(lists({"c.md": plain}, names)) == 1


def test_flag_list_scoped_by_heading_parent() -> None:
    names = [_n("serve"), _n("build"),
             _n("--a", "flag", "serve"), _n("--b", "flag", "serve"), _n("--c", "flag", "serve"),
             _n("--d", "flag", "build")]
    scoped = _table("--a", "--b", "--c", heading="## The `build` flags")
    assert lists({"a.md": scoped}, names)[0]["scope"] == ["build"]
    unscoped = _table("--a", "--b", "--c", heading="## Options")
    assert lists({"a.md": unscoped}, names)[0]["scope"] == ["serve"]
    both = [*names, _n("--e", "flag", "build"), _n("--f", "flag", "build")]
    mixed = _table("--a", "--b", "--e", heading="## Options")
    assert lists({"a.md": mixed}, both)[0]["scope"] == ["build", "serve"]


def test_complete_intended_at_half() -> None:
    names = [_n(f"c{i}") for i in range(6)]
    table = {"a.md": _table("c0", "c1", "c2")}
    assert lists(table, names)[0]["complete"] is True
    assert lists(table, [*names, _n("c6")])[0]["complete"] is False
    hidden = [*names, _n("c6", hidden=True), _n("c7", hidden=True)]
    assert lists(table, hidden)[0]["complete"] is True


def test_missing_from_list_targets_that_list() -> None:
    names = [_n("c0"), _n("c1"), _n("c2"), _n("c3")]
    texts = {"docs/cli.md": _table("c0", "c1", "c2"), "README.md": "c3 is mentioned here.\n"}
    found = gaps(names, texts, lists(texts, names), None, [])
    assert [(g["name"], g["gap_kind"], g["target_doc"], g["reason"]) for g in found] == [
        ("c3", "missing-from-list", "docs/cli.md", "missing-from-list")]
    assert found[0]["target_line"] == 7


def test_undocumented_targets_doc_with_most_same_kind_names() -> None:
    names = [_n("e1", "env", file="src/x.py"), _n("e2", "env", file="src/x.py"),
             _n("e3", "env", file="src/x.py"), _n("e4", "env", file="src/y.py"),
             _n("e9", "env", file="src/x.py")]
    texts = {"docs/a.md": "# A\n\nstuff\n\n## Env\n\nSet e1 and e2 first.\n",
             "docs/b.md": "# B\n\nSet e1.\n", "z.md": "e4 only\n"}
    found = gaps(names, texts, lists(texts, names), None, [])
    assert [(g["name"], g["target_doc"], g["target_line"], g["reason"]) for g in found
            if g["name"] == "e9"] == [("e9", "docs/a.md", 5, "most-names")]
    tie = gaps(names, {"docs/long.md": "e1\n", "a.md": "e2\n"}, [], None, [])
    assert {g["name"]: g["target_doc"] for g in tie}["e9"] == "a.md"


def test_undocumented_prefers_complete_then_any_list() -> None:
    names = [_n(f"c{i}") for i in range(6)] + [_n("c10"), _n("c11")]
    texts = {"z.md": _table("c0", "c1", "c2", "c3"), "b.md": _table("c4", "c5", "c10")}
    found = lists(texts, names)
    assert {x["doc"]: x["complete"] for x in found} == {"z.md": True, "b.md": False}
    got = gaps(names, texts, found, None, [])
    assert [(g["name"], g["target_doc"], g["reason"]) for g in got if g["name"] == "c11"] == [
        ("c11", "z.md", "complete-list")]
    assert {g["name"] for g in got if g["gap_kind"] == "missing-from-list"} == {"c4", "c5", "c10"}
    wide = [*names, *(_n(f"d{i}") for i in range(4))]
    got2 = gaps(wide, texts, lists(texts, wide), None, [])
    undocumented = [g for g in got2 if g["gap_kind"] == "undocumented"]
    assert {g["reason"] for g in undocumented} == {"any-list"}
    assert {g["target_doc"] for g in undocumented} == {"z.md"}


def test_no_home_when_nothing_fits() -> None:
    names = [_n("only", "script", file="pkg/m.py")]
    found = gaps(names, {"a.md": "nothing\n"}, [], None, [])
    assert found[0]["target_doc"] is None
    assert found[0]["target_line"] is None
    assert found[0]["reason"] == "no-home"
    assert found[0]["gap_kind"] == "undocumented"


def test_hidden_and_undocumented_ok_never_gaps() -> None:
    names = [_n("secret", hidden=True), _n("MY_DEBUG", "env"), _n("my-tool"), _n("shown")]
    got = candidates(names, None, ["MY_*", "my_tool"])
    assert [n["name"] for n in got] == ["shown"]
    found = gaps(names, {"a.md": "x\n"}, [], None, ["MY_*", "my_tool"])
    assert [g["name"] for g in found] == ["shown"]


def test_later_run_candidates_are_new_names_only() -> None:
    now = [_n("old"), _n("new"), _n("--f", "flag", "old"), _n("--f", "flag", "new")]
    then = [_n("old"), _n("--f", "flag", "old")]
    got = candidates(now, then, [])
    assert [(n["name"], n["parent"]) for n in got] == [("new", None), ("--f", "new")]
    assert len(candidates(now, None, [])) == 4


def test_gap_cap_order() -> None:
    def g(doc: str | None) -> Any:
        return {"name": "n", "target_doc": doc}
    found = [g("c.md"), g("a.md"), g("a.md"), g("b.md"), g("b.md"), g("d.md"), g(None)]
    targets, unchecked = split_by_cap(found, 2)
    assert list(targets) == ["a.md", "b.md"]
    assert unchecked == ["c.md", "d.md"]
    assert len(targets["a.md"]) == 2


def test_run_writes_gaps_json(tmp_path: Path) -> None:
    root, work = tmp_path / "repo", tmp_path / "work"
    (root / "docs").mkdir(parents=True)
    work.mkdir()
    (root / "docs" / "cli.md").write_text(_table("c0", "c1", "c2"), encoding="utf-8")
    names = [_n("c0"), _n("c1"), _n("c2"), _n("c3"), _n("zz", hidden=True)]
    write_json(work / "patterns.json", {"names": names, "names_then": None, "skipped": []})
    write_json(work / "inventory.json", {"docs": ["docs/cli.md", "docs/gone.md"]})
    config = {"undocumented_ok": [], "caps": {"review": 40, "gaps": 15, "verify": 25}}
    result = run(root, work, config)
    assert read_json(work / "gaps.json") == result
    assert set(result) == {"candidates", "lists", "gaps", "targets", "no_home", "unchecked"}
    assert [x["name"] for x in result["candidates"]] == ["c0", "c1", "c2", "c3"]
    assert list(result["targets"]) == ["docs/cli.md"]
    assert result["targets"]["docs/cli.md"][0]["name"] == "c3"
    assert result["no_home"] == [] and result["unchecked"] == []
