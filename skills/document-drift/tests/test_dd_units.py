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


def test_over_budget_linked_group_is_packed_doc_by_doc() -> None:
    # a, b and c share one definition: linked, 60 doc lines + 10 reading = 70 > 55
    anchors = [anchor(d, 1, start=5) for d in ("a.md", "b.md", "c.md")]
    units = dd_units.build(whole("a.md", "b.md", "c.md", n=20), anchors, {}, "first", {}, 55)
    assert [[d["doc"] for d in u["docs"]] for u in units] == [["a.md", "b.md"], ["c.md"]]
    assert [u["size"] for u in units] == [50, 30]
    # a doc of the group that is over budget on its own is still split at headings
    text = chr(10).join(["# T", *["x"] * 30, "## A", *["y"] * 14, "## B", *["z"] * 15]) + chr(10)
    n = len(text.splitlines())
    review = {"a.md": [[1, n]], "b.md": [[1, 20]]}
    anchors = [anchor("a.md", 2, start=5), anchor("b.md", 1, start=5)]
    units = dd_units.build(review, anchors, {}, "first", {"a.md": text}, 55)
    assert [(u["docs"][0]["doc"], u["docs"][0]["ranges"]) for u in units] == [
        ("a.md", [[1, 46]]), ("a.md", [[47, 62]]), ("b.md", [[1, 20]])]


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
            "anchors": [anchor(doc, i) for i in range(anchors)], "hunks": [], "size": 1,
            "affected_anchors": anchors}


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


def test_cap_order_counts_affected_anchors_on_later_run() -> None:
    anchors = [anchor("a.md", i, start=i) for i in range(1, 6)]
    anchors += [anchor("b.md", i, file="src/b.py", start=i) for i in range(1, 3)]
    affected = {
        "a.md": {"anchor_reasons": [{"ref": "x", "line": 1, "file": "src/a.py", "hunk": 0}],
                 "missing": []},
        "b.md": {"anchor_reasons": [{"ref": "x", "line": 1, "file": "src/b.py", "hunk": 0}],
                 "missing": [{"ref": "x", "line": 2, "file": "src/b.py", "start": 2,
                              "end": 3, "reading": [2, 3]}]}}
    units = dd_units.build(whole("a.md", "b.md"), anchors, {}, "later", {}, 10, affected)
    assert [(u["id"], len(u["anchors"]), u["affected_anchors"]) for u in units] == [
        ("u001", 5, 1), ("u002", 2, 2)]
    assert [u["id"] for u in dd_units.order_for_cap(units)] == ["u002", "u001"]
    first = dd_units.build(whole("a.md", "b.md"), anchors, {}, "first", {}, 10)
    assert [u["affected_anchors"] for u in first] == [5, 2]


def test_split_piece_anchors_follow_the_piece_not_the_ranges() -> None:
    text = "# T\n## A\na1\na2\n## B\nb1\nb2\n"
    anchors = [anchor("d.md", 3), anchor("d.md", 4, file="src/b.py"),
               anchor("d.md", 7, file="src/c.py")]
    # reviewed range covers only line 3 of piece A (lines 1-4) and line 7 of piece B (5-7)
    review = {"d.md": [[3, 3], [7, 7]]}
    units = dd_units.build(review, anchors, {}, "first", {"d.md": text}, 1)
    assert [u["docs"][0]["ranges"] for u in units] == [[[3, 3]], [[7, 7]]]
    assert [[a["line"] for a in u["anchors"]] for u in units] == [[3, 4], [7]]


def test_retry_units_clip_to_the_unit_pack_and_continue_numbering(tmp_path: Path) -> None:
    root, workdir = tmp_path / "repo", tmp_path / "wd"
    root.mkdir()
    (root / "a.md").write_text("".join(f"a{n}\n" for n in range(1, 21)), encoding="utf-8")
    kept = anchor("a.md", 3, start=5)
    gone = anchor("a.md", 2, file="src/b.py", start=1)
    write_json(workdir / "units.json", {
        "units": [{"id": "u001", "docs": [{"doc": "a.md", "ranges": [[1, 20]]},
                                          {"doc": "b.md", "ranges": [[1, 20]]}],
                   "anchors": [kept, gone], "hunks": [], "size": 60, "affected_anchors": 0}],
        "unchecked": ["u002"]})
    write_json(workdir / "changes.json", {"mode": "first", "hunks": {}, "affected": {}})
    pending = {"u001": [{"doc": "a.md", "start_line": 3, "end_line": 30, "why": "w"},
                        {"doc": "a.md", "start_line": 8, "end_line": 12, "why": "w"},
                        {"doc": "c.md", "start_line": 1, "end_line": 2, "why": "w"}],
               "u009": [{"doc": "a.md", "start_line": 1, "end_line": 2, "why": "w"}]}
    new = dd_units.retry_units(root, workdir, pending, 6000)
    assert [(u["id"], u["retry_of"], u["docs"]) for u in new] == [
        ("u003", "u001", [{"doc": "a.md", "ranges": [[3, 20]]}])]
    assert new[0]["anchors"] == [kept]
    stored = read_json(workdir / "units.json")
    assert [u["id"] for u in stored["units"]] == ["u001", "u003"]
    assert stored["unchecked"] == ["u002"]
    assert dd_units.retry_units(root, workdir, {"u001": []}, 6000) == []
