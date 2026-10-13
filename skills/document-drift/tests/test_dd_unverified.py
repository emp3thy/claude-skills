from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dd_common import read_json, write_json
from dd_extract import extract_doc
from dd_unverified import (
    block_hash,
    decide,
    ignore_regions,
    main,
    nominate,
    parse_notice,
    render_notice,
    run_start,
    run_verify,
)

RUN = "2026-10-19-b77c"
PREV = "2026-10-12-a3f1"
OLDER = "2026-10-05-0c1d"
PROSE = "The service retries three times\nand then gives up quietly."
NEVER = re.compile(r"(?!)")


def _h(block: str) -> str:
    return block_hash(block)


def _doc(*parts: str) -> str:
    return "\n".join(parts) + "\n"


def _lines(text: str) -> list[str]:
    return text.split("\n")


def _apply(text: str, edit: dict[str, Any]) -> str:
    """Replace lines start..end of an LF text by ``new`` (empty: drop the lines)."""
    lines = text.split("\n")
    assert "\n".join(lines[edit["start_line"] - 1:edit["end_line"]]) == edit["old"]
    new = edit["new"].split("\n") if edit["new"] else []
    return "\n".join(lines[:edit["start_line"] - 1] + new + lines[edit["end_line"]:])


def _ignore(doc: str, text: str) -> list[tuple[int, int]]:
    _, markers = extract_doc(doc, text, NEVER)
    return ignore_regions(markers, doc)


def test_parse_and_render_roundtrip() -> None:
    first = render_notice(1, PREV, "9c2e41d7")
    assert first == (
        "<!-- drift-unverified: 1st notice, run 2026-10-12-a3f1, block 9c2e41d7. This describes "
        "the code but names nothing in it. Name what it describes, or add drift-ignore: "
        "<reason>. -->")
    second = render_notice(2, RUN, "9c2e41d7")
    assert second == (
        "<!-- drift-unverified: 2nd notice, run 2026-10-19-b77c, block 9c2e41d7. NEEDS A HUMAN "
        "DECISION: name what this describes, add drift-ignore: <reason>, or rewrite it. The "
        "next drift run removes this block otherwise. -->")
    assert parse_notice(first) == {"stage": 1, "run": PREV, "hash": "9c2e41d7"}
    assert parse_notice(second + "\r\n") == {"stage": 2, "run": RUN, "hash": "9c2e41d7"}
    assert parse_notice("<!-- drift-unverified: 3rd notice, run x, block 9c2e41d7. y -->") is None
    assert parse_notice("<!-- drift-unverified: 1st notice, run x, block 9C2E41D7. y -->") is None
    assert parse_notice("<!-- drift-ignore: prose -->") is None


def test_block_hash_ignores_line_endings() -> None:
    assert block_hash("a  b\r\n\tc\r\n") == block_hash("a b\nc")
    assert re.fullmatch(r"[0-9a-f]{8}", block_hash("a b c"))
    assert block_hash("a b") != block_hash("a c")


def test_first_notice_unchanged_escalates() -> None:
    text = _doc("# Title", "", render_notice(1, PREV, _h(PROSE)), PROSE, "", "Tail.")
    decisions, edits, stale = decide("docs/a.md", text, [], [], RUN)
    assert stale == []
    assert decisions == [{"doc": "docs/a.md", "line": 3, "stage": 1, "run": PREV,
                          "hash": _h(PROSE), "block": [4, 5], "action": "escalate"}]
    assert edits == [{"id": "", "doc": "docs/a.md", "start_line": 3, "end_line": 3,
                      "old": render_notice(1, PREV, _h(PROSE)),
                      "new": render_notice(2, RUN, _h(PROSE)),
                      "type": "escalate", "claim": "2nd notice", "evidence": [],
                      "subject": _h(PROSE)}]


def test_second_notice_unchanged_removes_block_and_notice() -> None:
    notice = render_notice(2, PREV, _h(PROSE))
    text = _doc("# Title", "", notice, PROSE, "", "Tail.")
    decisions, edits, stale = decide("docs/a.md", text, [], [], RUN)
    assert stale == []
    assert [d["action"] for d in decisions] == ["remove"]
    assert edits == [{"id": "", "doc": "docs/a.md", "start_line": 3, "end_line": 5,
                      "old": notice + "\n" + PROSE, "new": "", "type": "unverified",
                      "claim": f"3rd notice, unchanged since {PREV}", "evidence": [],
                      "subject": _h(PROSE)}]
    # the blank line after the block stays
    assert _apply(text, edits[0]) == _doc("# Title", "", "", "Tail.")


def test_changed_block_clears() -> None:
    notice = render_notice(1, PREV, _h(PROSE))
    text = _doc("Intro.", "", notice, "The service retries five times.", "")
    decisions, edits, _ = decide("a.md", text, [], [], RUN)
    assert [d["action"] for d in decisions] == ["clear-changed"]
    assert decisions[0]["block"] == [4, 4]
    assert edits == [{"id": "", "doc": "a.md", "start_line": 3, "end_line": 3, "old": notice,
                      "new": "", "type": "clear", "claim": "block changed", "evidence": [],
                      "subject": _h(PROSE)}]
    # whitespace-only reflow is not a change
    reflowed = _doc("Intro.", "", notice, "The service retries three times and", "then  gives "
                    "up quietly.")
    decisions, edits, _ = decide("a.md", reflowed, [], [], RUN)
    assert [d["action"] for d in decisions] == ["escalate"]


def test_anchored_block_clears() -> None:
    notice = render_notice(2, PREV, _h(PROSE))
    text = _doc(notice, PROSE, "", "Other.")
    anchor = {"doc": "a.md", "line": 3, "ref": "retry", "file": "src/r.py", "start": 1,
              "end": 9, "kind": "function", "change_ranges": [], "reading": [1, 9]}
    decisions, edits, _ = decide("a.md", text, [anchor], [], RUN)
    assert [d["action"] for d in decisions] == ["clear-anchored"]
    assert [(e["type"], e["claim"], e["old"]) for e in edits] == [("clear", "now anchored",
                                                                   notice)]
    # an anchor outside the block does not count
    elsewhere = dict(anchor, line=4)
    decisions, _, _ = decide("a.md", text, [elsewhere], [], RUN)
    assert [d["action"] for d in decisions] == ["remove"]
    # anchored wins over changed: the owner named something while rewriting the block
    changed = _doc(notice, "The `retry` helper retries three times.", "")
    decisions, edits, _ = decide("a.md", changed, [dict(anchor, line=2)], [], RUN)
    assert [d["action"] for d in decisions] == ["clear-anchored"]


def test_drift_ignore_clears() -> None:
    notice = render_notice(1, PREV, _h(PROSE))
    for text in (_doc("<!-- drift-ignore: prose -->", notice, PROSE, ""),
                 _doc(notice, "<!-- drift-ignore: prose -->", PROSE, ""),
                 _doc("<!-- drift-ignore: prose -->", "", notice, PROSE, "")):
        decisions, edits, _ = decide("a.md", text, [], _ignore("a.md", text), RUN)
        assert [d["action"] for d in decisions] == ["clear-ignore"], text
        assert [(e["type"], e["claim"], e["old"]) for e in edits] == [
            ("clear", "drift-ignore", notice)]
    # a marker without a reason is not honoured
    bare = _doc("<!-- drift-ignore -->", notice, PROSE, "")
    decisions, _, _ = decide("a.md", bare, [], _ignore("a.md", bare), RUN)
    assert [d["action"] for d in decisions] == ["escalate"]
    # a marker on an earlier block does not reach this one
    earlier = _doc("<!-- drift-ignore: other -->", "Other prose.", "", notice, PROSE, "")
    decisions, _, _ = decide("a.md", earlier, [], _ignore("a.md", earlier), RUN)
    assert [d["action"] for d in decisions] == ["escalate"]


def test_list_and_table_are_one_block() -> None:
    items = ["- first thing", "- second thing", "  continued", "- third thing"]
    lst = "\n".join(items)
    notice = render_notice(2, PREV, _h(lst))
    text = _doc("# Steps", "", notice, *items, "", "After.")
    decisions, edits, _ = decide("a.md", text, [], [], RUN)
    assert decisions[0]["block"] == [4, 7]
    assert edits[0]["old"] == notice + "\n" + lst and edits[0]["type"] == "unverified"
    # one anchored item clears the whole list
    anchor = {"doc": "a.md", "line": 6, "ref": "x", "file": "x.py", "start": 1, "end": 1,
              "kind": "function", "change_ranges": [], "reading": [1, 1]}
    decisions, _, _ = decide("a.md", text, [anchor], [], RUN)
    assert [d["action"] for d in decisions] == ["clear-anchored"]
    rows = ["| Mode | Effect |", "|---|---|", "| fast | skips checks |", "| slow | runs all |"]
    table = "\n".join(rows)
    notice = render_notice(1, PREV, _h(table))
    text = _doc(notice, *rows, "", "After.")
    decisions, edits, _ = decide("a.md", text, [], [], RUN)
    assert decisions[0]["block"] == [2, 5] and decisions[0]["action"] == "escalate"
    # nominating any row notices the whole table, hashed as decide will hash it next run
    plain = _doc("Intro.", "", *rows, "")
    [edit] = nominate([{"doc": "a.md", "start_line": 5, "end_line": 6, "why": "w"}],
                      {"a.md": plain}, [], RUN)
    assert (edit["start_line"], edit["old"]) == (3, rows[0])
    assert edit["new"] == render_notice(1, RUN, _h(table)) + "\n" + rows[0]
    applied = _apply(plain, edit)
    decisions, _, _ = decide("a.md", applied, [], [], "2026-10-26-0001")
    assert [(d["hash"], d["action"]) for d in decisions] == [(_h(table), "escalate")]


def test_remove_edit_at_end_of_doc() -> None:
    notice = render_notice(2, PREV, _h(PROSE))
    for text in ("Intro.\n\n" + notice + "\n" + PROSE + "\n",
                 "Intro.\n\n" + notice + "\n" + PROSE,
                 "Intro.\r\n\r\n" + notice + "\r\n" + PROSE.replace("\n", "\r\n") + "\r\n"):
        decisions, edits, stale = decide("a.md", text, [], [], RUN)
        assert stale == [] and [d["block"] for d in decisions] == [[4, 5]]
        assert (edits[0]["start_line"], edits[0]["end_line"]) == (3, 5)
        assert edits[0]["old"] == notice + "\n" + PROSE
        assert edits[0]["type"] == "unverified"


def test_future_notice_is_stale() -> None:
    future = render_notice(1, "2026-11-02-ffff", _h(PROSE))
    text = _doc("Intro.", "", future, PROSE, "")
    decisions, edits, stale = decide("a.md", text, [], [], RUN)
    assert (decisions, edits) == ([], [])
    assert stale == [{"doc": "a.md", "line": 3, "reason": "run newer than the current run"}]
    # the same run id is not newer
    same = _doc(render_notice(1, RUN, _h(PROSE)), PROSE)
    decisions, _, stale = decide("a.md", same, [], [], RUN)
    assert stale == [] and [d["action"] for d in decisions] == ["escalate"]


def test_same_date_notice_is_not_stale_whatever_its_suffix() -> None:
    # run ids are dated; only the date orders them, so an earlier run of the same day whose
    # hash suffix sorts after the current one's is not a future run
    later_suffix = render_notice(1, "2026-10-19-ffff", _h(PROSE))
    assert RUN < "2026-10-19-ffff"
    decisions, edits, stale = decide("a.md", _doc(later_suffix, PROSE), [], [], RUN)
    assert stale == [] and [d["action"] for d in decisions] == ["escalate"]
    assert [e["type"] for e in edits] == ["escalate"]


def test_malformed_notice_is_stale() -> None:
    good = render_notice(1, PREV, _h(PROSE))
    text = _doc("<!-- drift-unverified: 1st notice, run x, block zz. hand made -->", "Para one.",
                "", "<!-- drift-unverified: 1st notice -->", "Para two.", "",
                "<!-- drift-unverified: 2nd notice, run " + OLDER + ", block 9c2e41d7. split",
                "over two lines -->", "Para three.", "",
                "```", good, PROSE, "```", "",
                good, "")
    decisions, edits, stale = decide("a.md", text, [], [], RUN)
    assert stale == [{"doc": "a.md", "line": 1, "reason": "malformed"},
                     {"doc": "a.md", "line": 4, "reason": "malformed"},
                     {"doc": "a.md", "line": 7, "reason": "malformed"},
                     {"doc": "a.md", "line": 17, "reason": "no block below"}]
    # a notice inside a fence is an example, not a notice
    assert (decisions, edits) == ([], [])
    # of two notices over one block, the lower one is read and the upper one is stale
    stacked = _doc(render_notice(1, OLDER, _h(PROSE)), good, PROSE)
    decisions, edits, stale = decide("a.md", stacked, [], [], RUN)
    assert [(d["line"], d["action"]) for d in decisions] == [(2, "escalate")]
    assert stale == [{"doc": "a.md", "line": 1, "reason": "another notice covers the block"}]


def test_nomination_skips_noticed_and_ignored_blocks() -> None:
    noticed = "Already noticed prose."
    changed = "Rewritten prose."
    text = _doc("# T", "", render_notice(1, PREV, _h(noticed)), noticed, "",
                "<!-- drift-ignore: history -->", "Ignored prose.", "",
                "Fresh prose", "over two lines.", "",
                render_notice(1, PREV, "00000000"), changed, "",
                "Anchored `retry` prose.", "",
                "<!-- drift-unverified: hand made -->", "Prose under a stale notice.", "")
    decisions, _, _ = decide("a.md", text, [], _ignore("a.md", text), RUN)
    assert [d["action"] for d in decisions] == ["escalate", "clear-changed"]
    anchor = {"doc": "a.md", "line": 15, "ref": "retry", "file": "r.py", "start": 1, "end": 2,
              "kind": "function", "change_ranges": [], "reading": [1, 2]}
    noms = [{"doc": "a.md", "start_line": n, "end_line": n, "why": "w"}
            for n in (4, 7, 10, 9, 13, 15, 18, 2)]
    noms.append({"doc": "other.md", "start_line": 1, "end_line": 1, "why": "w"})
    edits = nominate(noms, {"a.md": text}, decisions, RUN,
                     ignore={"a.md": _ignore("a.md", text)}, anchors=[anchor])
    assert [(e["start_line"], e["type"], e["claim"], e["subject"]) for e in edits] == [
        (9, "notice", "1st notice", _h("Fresh prose\nover two lines.")),
        (13, "notice", "1st notice", _h(changed))]
    assert edits[0]["old"] == "Fresh prose"
    assert edits[0]["new"] == render_notice(1, RUN, _h("Fresh prose over two lines.")) + \
        "\nFresh prose"
    assert edits[0]["end_line"] == 9


def test_nomination_on_a_comment_line_resolves_to_the_block_below() -> None:
    later = "2026-10-26-0001"
    # (a) a plain comment line: the notice goes above the prose, hashed as decide hashes it
    text = _doc("Intro.", "", "<!-- see below -->", "Some prose.")
    [edit] = nominate([{"doc": "a.md", "start_line": 3, "end_line": 4, "why": "w"}],
                      {"a.md": text}, [], RUN)
    assert (edit["start_line"], edit["old"], edit["subject"]) == (4, "Some prose.",
                                                                  _h("Some prose."))
    decisions, _, _ = decide("a.md", _apply(text, edit), [], [], later)
    assert [(d["hash"], d["action"]) for d in decisions] == [(_h("Some prose."), "escalate")]
    # (b) the line of a notice being cleared as changed: the new notice does not overlap it
    text = _doc("Intro.", "", render_notice(1, PREV, "00000000"), "Some prose.")
    decisions, clears, _ = decide("a.md", text, [], [], RUN)
    assert [(e["start_line"], e["type"]) for e in clears] == [(3, "clear")]
    [edit] = nominate([{"doc": "a.md", "start_line": 3, "end_line": 4, "why": "w"}],
                      {"a.md": text}, decisions, RUN)
    assert (edit["start_line"], edit["end_line"], edit["old"]) == (4, 4, "Some prose.")
    applied = _apply(_apply(text, edit), clears[0])
    assert applied == _doc("Intro.", "", render_notice(1, RUN, _h("Some prose.")), "Some prose.")
    decisions, _, _ = decide("a.md", applied, [], [], later)
    assert [d["action"] for d in decisions] == ["escalate"]


def test_edit_ids_in_doc_then_line_order(tmp_path: Path) -> None:
    root, work = tmp_path / "repo", tmp_path / "work"
    a1, a2, b1 = "First block.", "Third block.", "Only block."
    texts = {
        "docs/b.md": _doc(render_notice(1, PREV, _h(b1)), b1),
        "README.md": _doc(render_notice(2, PREV, _h(a1)), a1, "", "Second block.", "",
                          render_notice(1, PREV, "11111111"), a2, "",
                          render_notice(1, "2027-01-01-0000", _h(a2)), a2),
    }
    for doc, text in texts.items():
        (root / doc).parent.mkdir(parents=True, exist_ok=True)
        (root / doc).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    write_json(work / "inventory.json", {"docs": ["README.md", "docs/b.md"]})
    write_json(work / "anchors.json", {"anchors": []})
    write_json(work / "tokens.json", {"docs": {}, "markers": []})
    result = run_start(root, work, RUN)
    assert read_json(work / "notices.json") == result
    assert [(e["id"], e["doc"], e["start_line"], e["type"]) for e in result["edits"]] == [
        ("n001", "README.md", 1, "unverified"), ("n002", "README.md", 6, "clear"),
        ("n003", "docs/b.md", 1, "escalate")]
    assert result["stale"] == [{"doc": "README.md", "line": 9,
                                "reason": "run newer than the current run"}]
    assert result["nominations"] == []
    noms = [{"doc": "docs/b.md", "start_line": 2, "end_line": 2, "why": "noticed"},
            {"doc": "README.md", "start_line": 4, "end_line": 4, "why": "prose"}]
    for _ in range(2):  # a repeated verify replaces the nominations, never doubles them
        result = run_verify(root, work, noms, RUN)
    assert read_json(work / "notices.json") == result
    assert [(e["id"], e["doc"], e["start_line"], e["type"]) for e in result["edits"]] == [
        ("n001", "README.md", 1, "unverified"), ("n002", "README.md", 4, "notice"),
        ("n003", "README.md", 6, "clear"), ("n004", "docs/b.md", 1, "escalate")]
    assert [n["skipped"] for n in result["nominations"]] == ["already noticed", None]
    assert len(result["decisions"]) == 3


def test_main_reads_run_id_from_preflight(tmp_path: Path) -> None:
    root, work = tmp_path / "repo", tmp_path / "work"
    root.mkdir()
    (root / "a.md").write_text(_doc(render_notice(1, PREV, _h(PROSE)), PROSE), encoding="utf-8")
    write_json(work / "inventory.json", {"docs": ["a.md"]})
    write_json(work / "anchors.json", {"anchors": []})
    write_json(work / "tokens.json", {"docs": {}, "markers": []})
    write_json(work / "preflight.json", {"run_id": RUN})
    assert main([str(root), "--workdir", str(work)]) == 0
    assert read_json(work / "notices.json")["edits"][0]["new"] == render_notice(2, RUN, _h(PROSE))
    noms = tmp_path / "noms.json"
    write_json(noms, [])
    assert main([str(root), "--workdir", str(work), "--nominations", str(noms)]) == 0
    assert main([str(root), "--workdir", str(tmp_path / "empty")]) == 5
