"""Tests for dd_units: linking, packing, splitting, sizing, cap order and run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import dd_units
from dd_anchors import Anchor
from dd_common import read_json, write_json
from dd_history import Hunk


def anchor(doc: str, line: int, file: str = "src/a.py", start: int = 1, end: int = 10,
           reading: tuple[int, int] = (1, 10), change: tuple[int, int] = (1, 10)) -> Anchor:
    return {"doc": doc, "line": line, "ref": "x", "file": file, "start": start, "end": end,
            "kind": "function", "change_ranges": [list(change)], "reading": list(reading)}


def hunk(file: str, start: int, end: int) -> Hunk:
    return {"file": file, "old_start": start, "old_end": end, "new_start": start,
            "new_end": end, "text": ""}


def whole(*docs: str, n: int = 10) -> dict[str, list[list[int]]]:
    return {d: [[1, n]] for d in docs}


def test_docs_sharing_a_definition_are_linked() -> None:
    anchors = [anchor("a.md", 1, start=5), anchor("c.md", 2, start=5),
               anchor("b.md", 1, file="src/b.py", start=1)]
    # budget 25 would pack a and b together; the link a-c (20 lines + 10 reading) wins
    units = dd_units.build(whole("a.md", "b.md", "c.md"), anchors, {}, "first", {}, 35)
    docs = [[d["doc"] for d in u["docs"]] for u in units]
    assert docs == [["a.md", "c.md"], ["b.md"]]


def test_packing_respects_unit_lines() -> None:
    units = dd_units.build(whole("a.md", "b.md", "c.md"), [], {}, "first", {}, 25)
    assert [[d["doc"] for d in u["docs"]] for u in units] == [["a.md", "b.md"], ["c.md"]]
    assert [u["size"] for u in units] == [20, 10]


def test_large_doc_split_at_second_level_headings() -> None:
    text = "# T\nintro\n## A\na1\na2\n```\n## not a heading\n```\n## B\nb1\nb2\n"
    n = len(text.splitlines())
    anchors = [anchor("big.md", 4), anchor("big.md", 11, file="src/b.py")]
    units = dd_units.build({"big.md": [[1, n]]}, anchors, {}, "first", {"big.md": text}, 5)
    assert [u["docs"][0]["ranges"] for u in units] == [[[1, 8]], [[9, 11]]]
    assert [len(u["anchors"]) for u in units] == [1, 1]
    assert [u["id"] for u in units] == ["u001", "u002"]


def test_large_doc_without_headings_stays_one_unit() -> None:
    text = "one\ntwo\nthree\n"
    units = dd_units.build({"a.md": [[1, 3]]}, [], {}, "first", {"a.md": text}, 2)
    assert len(units) == 1


def test_first_run_size_counts_reading_ranges_once() -> None:
    anchors = [anchor("a.md", 1, start=5, reading=(1, 7)),
               anchor("a.md", 2, start=5, reading=(1, 7)),
               anchor("a.md", 3, file="src/b.py", reading=(1, 3))]
    units = dd_units.build(whole("a.md"), anchors, {}, "first", {}, 1000)
    assert units[0]["size"] == 10 + 7 + 3
    assert units[0]["hunks"] == []


def test_later_run_size_counts_hunks() -> None:
    anchors = [anchor("a.md", 1, change=(3, 4)), anchor("a.md", 2, change=(3, 4))]
    hunks = {"src/a.py": [hunk("src/a.py", 3, 6), hunk("src/a.py", 50, 60)]}
    affected = {"a.md": {"missing": [{"ref": "m", "line": 5, "file": "src/gone.py",
                                      "start": 1, "end": 9, "reading": [1, 9]}]}}
    units = dd_units.build(whole("a.md"), anchors, hunks, "later", {}, 1000, affected)
    assert units[0]["size"] == 10 + 4 + 9
    assert units[0]["hunks"] == [hunks["src/a.py"][0]]


def make_unit(uid: str, doc: str, anchors: int) -> dd_units.Unit:
    return {"id": uid, "docs": [{"doc": doc, "ranges": [[1, 1]]}],
            "anchors": [anchor(doc, i) for i in range(anchors)], "hunks": [], "size": 1}


def test_cap_order_puts_readme_first() -> None:
    units = [make_unit("u001", "a.md", 5), make_unit("u002", "docs/readme.md", 0),
             make_unit("u003", "b.md", 9), make_unit("u004", "b2.md", 9)]
    assert [u["id"] for u in dd_units.order_for_cap(units)] == [
        "u002", "u003", "u004", "u001"]


def test_ids_follow_path_order() -> None:
    units = dd_units.build(whole("z.md", "a.md", "m.md"), [], {}, "first", {}, 10)
    assert [(u["id"], u["docs"][0]["doc"]) for u in units] == [
        ("u001", "a.md"), ("u002", "m.md"), ("u003", "z.md")]


def test_run_writes_units_with_cap(tmp_path: Path) -> None:
    root, work = tmp_path / "repo", tmp_path / "work"
    (root / "docs").mkdir(parents=True)
    for name in ("README.md", "docs/a.md", "docs/b.md"):
        (root / name).write_text("l1\nl2\n", encoding="utf-8")
    write_json(work / "changes.json", {
        "mode": "first", "hunks": {}, "affected": {},
        "review": {"README.md": [[1, 2]], "docs/a.md": [[1, 2]], "docs/b.md": [[1, 2]]}})
    write_json(work / "anchors.json", {"anchors": [anchor("docs/b.md", 1, reading=(1, 0))]})
    write_json(work / "inventory.json", {"docs": ["README.md", "docs/a.md", "docs/b.md"]})
    config: dict[str, Any] = {"unit_lines": 2, "caps": {"review": 2}}
    result = dd_units.run(root, work, config)
    assert [u["id"] for u in result["units"]] == ["u001", "u003"]
    assert result["unchecked"] == ["u002"]
    assert read_json(work / "units.json") == result
