"""Tests for dd_dispatch: plan files, prompt rendering, output validation and retries."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import dd_dispatch
import dd_units
import pytest
from dd_common import read_json, write_json
from dd_config import DEFAULTS

SHA = "0123456789abcdef0123456789abcdef01234567"
MANDATORY = ("exactly one file", "no command", "helper script")


def _config(**caps: int) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULTS)
    config["caps"].update(caps)
    return config


def _anchor(doc: str, line: int, ref: str, file: str, start: int, end: int) -> dict[str, Any]:
    return {"doc": doc, "line": line, "ref": ref, "file": file, "start": start, "end": end,
            "kind": "function", "change_ranges": [[start, end]], "reading": [start, end]}


def _hunk(file: str, start: int, end: int, text: str) -> dict[str, Any]:
    return {"file": file, "old_start": start, "old_end": end, "new_start": start,
            "new_end": end, "text": text}


def _gap(name: str, doc: str, line: int) -> dict[str, Any]:
    return {"name": name, "kind": "env", "parent": None, "file": "src/app.py", "line": 7,
            "gap_kind": "undocumented", "target_doc": doc, "target_line": line,
            "reason": "most-names"}


def _tree(tmp_path: Path, mode: str = "first") -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "README.md").write_text("# Demo\n\nRun `start`.\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text(
        "".join(f"guide line {n}\n" for n in range(1, 31)), encoding="utf-8")
    (root / "src" / "app.py").write_text("def start():\n    return 1\n", encoding="utf-8")
    workdir = root / ".document-drift"
    readme_anchor = _anchor("README.md", 3, "start", "src/app.py", 1, 2)
    guide_anchor = _anchor("docs/guide.md", 4, "start", "src/app.py", 1, 2)
    later = mode == "later"
    hunk = _hunk("src/app.py", 2, 2, "-    return 0\n+    return 1\n")
    units = {
        "units": [
            {"id": "u001", "docs": [{"doc": "README.md", "ranges": [[1, 3]]}],
             "anchors": [readme_anchor], "hunks": [hunk] if later else [], "size": 5,
             "affected_anchors": 1},
            {"id": "u002", "docs": [{"doc": "docs/guide.md", "ranges": [[1, 10], [20, 30]]}],
             "anchors": [guide_anchor], "hunks": [hunk] if later else [], "size": 23,
             "affected_anchors": 1},
        ],
        "unchecked": ["u003"],
    }
    gaps = {"candidates": [], "lists": [], "gaps": [], "no_home": [], "unchecked": ["docs/z.md"],
            "targets": {"docs/guide.md": [_gap("APP_MODE", "docs/guide.md", 12)],
                        "README.md": [_gap("APP_PORT", "README.md", 1),
                                      _gap("APP_HOST", "README.md", 1)]}}
    affected = {}
    if later:
        affected = {"README.md": {"anchor_reasons": [{"ref": "start", "line": 3,
                                                      "file": "src/app.py", "hunk": [2, 2]}],
                                  "missing": [{"ref": "stop", "line": 2, "file": "src/app.py",
                                               "start": 4, "end": 5, "reading": [4, 5]}],
                                  "doc_changed": True, "sections": [[1, 3]]}}
    changes = {"mode": mode, "last_run": SHA if later else None,
               "scope": f"since {SHA}" if later else "first", "changed_files": [],
               "hunks": {}, "affected": affected, "review": {}}
    write_json(workdir / "units.json", units)
    write_json(workdir / "gaps.json", gaps)
    write_json(workdir / "changes.json", changes)
    # a changelog exists but is out of scope, so it is not in the inventory's docs
    (root / "CHANGELOG.md").write_text("- Added `APP_PORT`.\n", encoding="utf-8")
    write_json(workdir / "inventory.json", {"docs": ["docs/guide.md", "README.md"]})
    return root, workdir


def _edit(eid: str, **over: Any) -> dict[str, Any]:
    edit: dict[str, Any] = {
        "id": eid, "doc": "docs/guide.md", "start_line": 5, "end_line": 5,
        "old": "guide line 5", "new": "guide line five", "type": "correct",
        "claim": "line 5 says 5", "evidence": ["src/app.py:1"], "subject": None}
    edit.update(over)
    return edit


def _review(unit: str = "u001", **over: Any) -> dict[str, Any]:
    review: dict[str, Any] = {
        "unit": unit, "claims_checked": 3, "code_claims": {"README.md": 3},
        "unverified_blocks": [{"doc": "README.md", "start_line": 1, "end_line": 1,
                               "why": "names nothing"}],
        "edits": [_edit(f"{unit}-e01")],
        "questions": [
            {"doc": "README.md", "line": 3, "kind": "guarantee-mismatch",
             "claim": "never fails", "code": "raises", "evidence": ["src/app.py:2"]},
            {"doc": "README.md", "line": 2, "kind": "unsure", "claim": "x",
             "question": "is it?", "evidence": []}]}
    review.update(over)
    return review


def _verdicts(batch: str, ids: list[str]) -> dict[str, Any]:
    return {"batch": batch,
            "verdicts": [{"edit": i, "verdict": "accept", "reason": "matches"} for i in ids]}


def test_render_replaces_and_rejects_unknown(tmp_path: Path) -> None:
    (tmp_path / "t.md").write_text("A {{one}} and {{two}}, {{one}} again.\n", encoding="utf-8")
    out = dd_dispatch.render("t", {"one": "1 {{two}}", "two": "2"}, directory=tmp_path)
    assert out == "A 1 {{two}} and 2, 1 {{two}} again.\n"
    with pytest.raises(KeyError):
        dd_dispatch.render("t", {"one": "1"}, directory=tmp_path)
    with pytest.raises(KeyError):
        dd_dispatch.render("t", {"one": "1", "two": "2", "three": "3"}, directory=tmp_path)
    # the shipped templates sit next to the scripts directory
    text = dd_dispatch.render("gap", {"repo": "/r", "doc": "d.md", "gaps": "- g",
                                      "docs_in_scope": "- d.md",
                                      "output": "/w/gaps/g001.json", "id": "g001"})
    assert "/w/gaps/g001.json" in text and "{{" not in text


def test_plan_docs_one_entry_per_unit_and_gap_doc_within_caps(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    assert [(e["id"], e["role"], e["model"]) for e in plan] == [
        ("u001", "review", "sonnet"), ("u002", "review", "sonnet"),
        ("g001", "gap", "sonnet"), ("g002", "gap", "sonnet")]
    assert read_json(workdir / "plan-docs.json") == plan
    by_id = {e["id"]: e for e in plan}
    assert by_id["g001"]["doc"] == "README.md" and by_id["g002"]["doc"] == "docs/guide.md"
    assert by_id["u002"]["prompt"] == (workdir / "prompts" / "review-u002.md").as_posix()
    assert by_id["u002"]["output"] == (workdir / "review" / "u002.json").as_posix()
    assert by_id["g001"]["prompt"] == (workdir / "prompts" / "gap-g001.md").as_posix()
    assert by_id["g001"]["output"] == (workdir / "gaps" / "g001.json").as_posix()
    for entry in plan:
        assert Path(entry["prompt"]).is_absolute() and Path(entry["prompt"]).is_file()
        assert Path(entry["output"]).is_absolute() and not Path(entry["output"]).exists()
    for name in ("review", "gaps", "verdicts"):
        assert (workdir / name).is_dir()
    gap_prompt = Path(by_id["g001"]["prompt"]).read_text(encoding="utf-8")
    assert "APP_PORT" in gap_prompt and "APP_HOST" in gap_prompt and "APP_MODE" not in gap_prompt
    assert "src/app.py:7" in gap_prompt and '"doc": "g001"' in gap_prompt
    # the edit example names the target doc; only the in-scope docs count as documentation
    assert '"id": "g001-e01", "doc": "README.md"' in gap_prompt
    assert "each edit's `doc` is `README.md`" in gap_prompt
    assert "\n- README.md\n- docs/guide.md\n" in gap_prompt and "CHANGELOG.md" not in gap_prompt
    assert "Changelogs, release notes, history, licences, specs and plans" in gap_prompt
    review = Path(by_id["u002"]["prompt"]).read_text(encoding="utf-8")
    assert "docs/guide.md (30 lines): lines 1-10, 20-30\n" in review
    assert f"; {dd_dispatch.NO_ANCHORS}" not in review
    assert "u003" not in review
    assert not (workdir / "prompts" / "review-u003.md").exists()


def test_review_prompt_marks_docs_with_no_anchor_in_their_lines(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    units = read_json(workdir / "units.json")
    units["units"][1]["docs"] = [{"doc": "docs/guide.md", "ranges": [[20, 30]]},
                                 {"doc": "README.md", "ranges": [[1, 3]]}]
    units["units"][1]["anchors"].append(units["units"][0]["anchors"][0])
    write_json(workdir / "units.json", units)
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    review = Path(plan[1]["prompt"]).read_text(encoding="utf-8")
    # the guide's anchor is on line 4, outside the reviewed lines; README's is on line 3
    assert f"- docs/guide.md (30 lines): lines 20-30; {dd_dispatch.NO_ANCHORS}\n" in review
    assert "- README.md (3 lines): lines 1-3\n" in review
    assert "`no anchors in these lines`" in review


def test_review_prompt_contains_anchors_and_diff_on_later_run(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path, mode="later")
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    text = Path(plan[0]["prompt"]).read_text(encoding="utf-8")
    assert "`start` (README.md line 3) -> src/app.py:1-2" in text
    assert SHA[:9] in text and SHA not in text
    assert "--- src/app.py" in text
    assert "@@ -2,1 +2,1 @@\n-    return 0\n+    return 1" in text
    assert "Your scope" in text
    # true of a --base run as well as of a run since the last check
    assert f"Since commit {SHA[:9]}, the code below changed." in text
    assert "last checked" not in text
    assert "- README.md (3 lines): lines 1-3; changed sections: 1-3" in text
    assert ("`stop` (README.md line 2) -> no longer defined; was src/app.py:4-5 at commit "
            f"{SHA[:9]}") in text
    # an anchor the changes did not touch is left out on a later run
    assert "(docs/guide.md line 4)" not in Path(plan[1]["prompt"]).read_text(encoding="utf-8")

    first_root, first_workdir = _tree(tmp_path / "first")
    first = dd_dispatch.plan_docs(first_root, first_workdir, _config())
    first_text = Path(first[0]["prompt"]).read_text(encoding="utf-8")
    assert "`start` (README.md line 3) -> src/app.py:1-2" in first_text
    assert "--- src/app.py" not in first_text and "What to check" in first_text


def test_prompts_carry_mandatory_sentences(tmp_path: Path) -> None:
    prompts: list[str] = []
    for mode in ("first", "later"):
        root, workdir = _tree(tmp_path / mode, mode=mode)
        plan = dd_dispatch.plan_docs(root, workdir, _config())
        prompts += [Path(e["prompt"]).read_text(encoding="utf-8") for e in plan]
        for entry in plan:
            assert entry["output"] in Path(entry["prompt"]).read_text(encoding="utf-8")
    verify = dd_dispatch.plan_verify(root, workdir, [[_edit("u002-e01")]], _config())
    verify_text = Path(verify[0]["prompt"]).read_text(encoding="utf-8")
    assert verify[0]["output"] in verify_text
    prompts.append(verify_text)
    assert len(prompts) == 9
    for text in prompts:
        for phrase in MANDATORY:
            assert phrase in text
        assert "{{" not in text and "Read, Grep and Glob" in text and "Write tool" in text
        assert "size in bytes" in text
    reviews = [t for t in prompts if "claims_checked" in t]
    assert len(reviews) == 4
    for text in reviews:
        for needed in ("`anchor`", "code_claims", "unverified_blocks", "drift-unverified",
                       "Preamble", "guarantee-mismatch", "`unsure`", "`must not`",
                       "is required", "relative to the repository root, with forward slashes",
                       "`doc` is the doc's path as listed above, with forward slashes"):
            assert needed in text
    gap = [t for t in prompts if '"refusals"' in t]
    assert len(gap) == 4
    for text in gap:
        for needed in ("not-user-facing", "already-documented", "target-refused",
                       "any spelling", "sorted list stays sorted", "evidence",
                       "relative to the repository root, with forward slashes"):
            assert needed in text
    for needed in ("1. ", "5. ", "other software", "minimal", "guarantee", "`anchor` edit",
                   "not merely a related one"):
        assert needed in verify_text
    # the add and remove rules narrow the five conditions, they do not replace them
    assert verify_text.count("conditions 2 to 5 still apply") == 2


def test_plan_verify_caps_batches_and_shows_doc_context(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    batches = [[_edit("u002-e01"), _edit("u002-e02", start_line=20, end_line=21,
                                         old="guide line 20\nguide line 21", new="")],
               [_edit("g001-e01", type="add")],
               [_edit("u001-e01")]]
    plan = dd_dispatch.plan_verify(root, workdir, batches, _config(verify=2))
    assert [(e["id"], e["role"], e["model"], e["edits"]) for e in plan] == [
        ("v01", "verify", "opus", ["u002-e01", "u002-e02"]),
        ("v02", "verify", "opus", ["g001-e01"])]
    assert read_json(workdir / "plan-verify.json") == plan
    assert plan[0]["output"] == (workdir / "verdicts" / "v01.json").as_posix()
    text = Path(plan[0]["prompt"]).read_text(encoding="utf-8")
    assert "u002-e01" in text and "line 5 says 5" in text and "src/app.py:1" in text
    # 10 lines either side of the edit, numbered, clipped at the doc's start and end
    assert "1: guide line 1\n" in text and "15: guide line 15\n" in text
    assert "16: guide line 16" in text  # the second edit's context starts at line 10
    assert "30: guide line 30" in text and "31:" not in text
    assert not (workdir / "prompts" / "verify-v03.md").exists()


def test_validate_review_rejects_bad_type_and_missing_old() -> None:
    assert dd_dispatch.validate_review(_review()) == []
    bad_type = _review(edits=[_edit("u001-e01", type="rewrite")])
    assert any("type" in p for p in dd_dispatch.validate_review(bad_type))
    no_old = _edit("u001-e01")
    del no_old["old"]
    assert any("old" in p for p in dd_dispatch.validate_review(_review(edits=[no_old])))
    reversed_lines = _review(edits=[_edit("u001-e01", start_line=6, end_line=5)])
    assert dd_dispatch.validate_review(reversed_lines)
    assert dd_dispatch.validate_review(_review(edits=[_edit("u001-e01", type="add")]))
    assert dd_dispatch.validate_review(_review(code_claims={"README.md": "3"}))
    assert dd_dispatch.validate_review(_review(claims_checked=-1))
    assert dd_dispatch.validate_review(_review(questions=[{"doc": "README.md", "line": 1,
                                                           "kind": "maybe", "claim": "x",
                                                           "evidence": []}]))
    unsure_without_question = _review(questions=[{"doc": "README.md", "line": 1,
                                                  "kind": "unsure", "claim": "x",
                                                  "evidence": []}])
    assert dd_dispatch.validate_review(unsure_without_question)
    assert dd_dispatch.validate_review(_review(edits=[_edit("u009-e01")]))
    assert dd_dispatch.validate_review(_review(edits=[_edit("u001-e01"), _edit("u001-e01")]))
    assert dd_dispatch.validate_review(_review(unverified_blocks=[{"doc": "README.md"}]))
    assert dd_dispatch.validate_review([]) == ["output is not a JSON object"]
    no_unit = _review()
    del no_unit["unit"]
    assert dd_dispatch.validate_review(no_unit)


def test_validate_gap_requires_add_edits_and_known_refusal_kinds() -> None:
    good = {"doc": "g001", "edits": [_edit("g001-e01", type="add", subject="APP_PORT")],
            "refusals": [{"name": "APP_HOST", "kind": "already-documented", "reason": "r"}]}
    assert dd_dispatch.validate_gap(good) == []
    assert dd_dispatch.validate_gap({**good, "edits": [_edit("g001-e01")]})
    assert dd_dispatch.validate_gap({**good, "refusals": [{"name": "X", "kind": "nope",
                                                           "reason": "r"}]})
    assert dd_dispatch.validate_gap({"doc": "g001", "edits": []})
    for wrong in ("g001", " "):
        edit = _edit("g001-e01", type="add", doc=wrong)
        assert any("target doc" in p for p in dd_dispatch.validate_gap({**good, "edits": [edit]}))
    # an edit aimed at another doc than the entry's target is a retry, not a candidate
    assert dd_dispatch.validate_gap(good, "docs/guide.md") == []
    stray = _edit("g001-e01", type="add", subject="APP_PORT", doc="README.md")
    problems = dd_dispatch.validate_gap({**good, "edits": [stray]}, "docs/guide.md")
    assert problems == ["edits[0]: doc 'README.md' is not the target doc 'docs/guide.md'"]


def test_validate_verdicts_requires_every_id_once() -> None:
    expected = ["u001-e01", "u001-e02"]
    assert dd_dispatch.validate_verdicts(_verdicts("v01", expected), expected) == []
    missing = dd_dispatch.validate_verdicts(_verdicts("v01", ["u001-e01"]), expected)
    assert any("u001-e02" in p for p in missing)
    twice = dd_dispatch.validate_verdicts(_verdicts("v01", [*expected, "u001-e01"]), expected)
    assert any("u001-e01" in p for p in twice)
    extra = dd_dispatch.validate_verdicts(_verdicts("v01", [*expected, "u009-e01"]), expected)
    assert any("u009-e01" in p for p in extra)
    bad = _verdicts("v01", expected)
    bad["verdicts"][0]["verdict"] = "maybe"
    assert dd_dispatch.validate_verdicts(bad, expected)
    assert dd_dispatch.validate_verdicts({"verdicts": []}, [])


def test_check_outputs_lists_missing_and_invalid(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    write_json(workdir / "review" / "u001.json", _review("u001"))
    (workdir / "review" / "u002.json").write_text("{not json", encoding="utf-8")
    write_json(workdir / "gaps" / "g001.json", {"doc": "g001", "edits": [], "refusals": []})
    write_json(workdir / "gaps" / "g002.json", {"doc": "g001", "edits": [], "refusals": []})
    assert dd_dispatch.check_outputs(workdir, plan, "review") == (["u001"], [plan[1]])
    # g002's output names the wrong id
    assert dd_dispatch.check_outputs(workdir, plan, "gap") == (["g001"], [plan[3]])
    # g001's edit aims at a doc other than its entry's target doc
    stray = _edit("g001-e01", type="add", subject="X",
                  doc=next(d for d in ("README.md", "docs/guide.md") if d != plan[2]["doc"]))
    write_json(workdir / "gaps" / "g001.json", {"doc": "g001", "edits": [stray],
                                                "refusals": []})
    assert dd_dispatch.check_outputs(workdir, plan, "gap") == ([], [plan[2], plan[3]])

    verify = dd_dispatch.plan_verify(root, workdir, [[_edit("u001-e01")],
                                                     [_edit("u002-e01")]], _config())
    write_json(workdir / "verdicts" / "v01.json", _verdicts("v01", ["u001-e01"]))
    assert dd_dispatch.check_outputs(workdir, verify, "verify") == (["v01"], [verify[1]])
    write_json(workdir / "verdicts" / "v02.json", _verdicts("v02", []))
    assert dd_dispatch.check_outputs(workdir, verify, "verify") == (["v01"], [verify[1]])


def test_write_retry_is_plan_format(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    _, failed = dd_dispatch.check_outputs(workdir, plan, "review")
    dd_dispatch.write_retry(workdir, failed)
    retry = json.loads((workdir / "retry.json").read_text(encoding="utf-8"))
    assert retry == plan[:2]
    for entry in retry:
        assert {"id", "role", "prompt", "output", "model"} <= set(entry)


def test_collect_verdicts_marks_unchecked_batches_unverified(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    verify = dd_dispatch.plan_verify(
        root, workdir, [[_edit("u001-e01"), _edit("u001-e02")], [_edit("u002-e01")],
                        [_edit("g001-e01", type="add")]], _config())
    good = _verdicts("v01", ["u001-e01", "u001-e02"])
    good["verdicts"][1].update(verdict="reject", reason="still wrong")
    write_json(workdir / "verdicts" / "v01.json", good)
    write_json(workdir / "verdicts" / "v02.json", _verdicts("v02", []))
    result = dd_dispatch.collect_verdicts(workdir, verify)
    assert result == {
        "verdicts": {"u001-e01": {"verdict": "accept", "reason": "matches"},
                     "u001-e02": {"verdict": "reject", "reason": "still wrong"}},
        "unverified": ["u002-e01", "g001-e01"]}
    assert read_json(workdir / "verdicts.json") == result


@pytest.mark.parametrize("name", ["units.json", "gaps.json", "changes.json", "inventory.json"])
def test_plan_docs_requires_inputs(tmp_path: Path, name: str) -> None:
    root, workdir = _tree(tmp_path)
    (workdir / name).unlink()
    with pytest.raises(dd_dispatch.StepError) as caught:
        dd_dispatch.plan_docs(root, workdir, _config())
    assert caught.value.code == dd_dispatch.EXIT_MISSING


def test_main_writes_plan(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root, workdir = _tree(tmp_path)
    assert dd_dispatch.main([str(root), "--workdir", str(workdir)]) == 0
    assert len(read_json(workdir / "plan-docs.json")) == 4
    assert "plan-docs.json" in capsys.readouterr().out


def test_validate_review_not_reviewed_is_optional_but_checked() -> None:
    assert dd_dispatch.validate_review(_review()) == []
    ok = _review(not_reviewed=[{"doc": "README.md", "start_line": 2, "end_line": 3,
                                "why": "no room"}])
    assert dd_dispatch.validate_review(ok) == []
    bad = _review(not_reviewed=[{"doc": "README.md", "start_line": 3, "end_line": 2,
                                 "why": "x"}, {"doc": "README.md"}])
    problems = dd_dispatch.validate_review(bad)
    assert any("not_reviewed[0]: start_line 3 is after end_line 2" in p for p in problems)
    assert any("not_reviewed[1] has no start_line" in p for p in problems)
    assert dd_dispatch.validate_review(_review(not_reviewed="all")) == [
        "not_reviewed is not a list"]


def test_not_reviewed_ranges_become_retry_entries(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    plan = dd_dispatch.plan_docs(root, workdir, _config())
    ranges = [{"doc": "README.md", "start_line": 2, "end_line": 3, "why": "no room"}]
    write_json(workdir / "review" / "u001.json", _review("u001", not_reviewed=ranges))
    write_json(workdir / "review" / "u002.json", _review("u002", not_reviewed=[]))
    assert dd_dispatch.not_reviewed(workdir, plan, set()) == {"u001": ranges}
    assert dd_dispatch.not_reviewed(workdir, plan, {"u001"}) == {}
    units = dd_units.retry_units(root, workdir, {"u001": ranges}, 6000)
    assert [(u["id"], u["retry_of"]) for u in units] == [("u004", "u001")]
    entries = dd_dispatch.plan_retry(root, workdir, _config(), units)
    assert [(e["id"], e["role"], e["model"]) for e in entries] == [("u004", "review", "sonnet")]
    assert read_json(workdir / "plan-docs.json") == [*plan, *entries]
    prompt = Path(entries[0]["prompt"]).read_text(encoding="utf-8")
    assert "README.md (3 lines): lines 2-3" in prompt and "u004" in prompt
    assert "docs/guide.md" not in prompt


def _hint(kind: str, name: str, parent: str | None, file: str, line: int,
          hidden: bool = False) -> dict[str, Any]:
    return {"name": name, "kind": kind, "file": file, "line": line, "parent": parent,
            "hidden": hidden}


def _write_areas(workdir: Path) -> None:
    def area(aid: str, lines: int, hints: list[dict[str, Any]]) -> dict[str, Any]:
        return {"id": aid, "files": [{"path": f"src/{aid}/m.py", "lines": lines},
                                     {"path": f"src/{aid}/n.py", "lines": 7}],
                "lines": lines + 7, "hints": hints}
    write_json(workdir / "areas.json", {"area_lines": 100, "areas": [
        area("a01", 90, [_hint("flag", "--force", "sync", "src/a01/m.py", 88),
                         _hint("env", "APP_X", None, "src/a01/m.py", 3, hidden=True)]),
        area("a02", 50, []),
        area("a03", 10, [])]})


def test_plan_sheets_one_entry_per_area_within_cap(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    _write_areas(workdir)
    config = _config(sheet_agents=2)
    docs_plan = dd_dispatch.plan_docs(root, workdir, config)
    entries = dd_dispatch.plan_sheets(root, workdir, config)
    assert [(e["id"], e["role"], e["model"]) for e in entries] == [
        ("a01", "sheet", config["models"]["sheet"]), ("a02", "sheet", config["models"]["sheet"])]
    assert entries[0]["prompt"].endswith("/prompts/sheet-a01.md")
    assert entries[0]["output"].endswith("/sheets/a01.json")
    prompt = Path(entries[0]["prompt"]).read_text(encoding="utf-8")
    assert "- src/a01/m.py (90 lines)" in prompt and "- src/a01/n.py (7 lines)" in prompt
    assert "- flag --force (parent sync) src/a01/m.py:88\n" in prompt
    assert "- env APP_X src/a01/m.py:3 hidden" in prompt
    assert "src/a03" not in Path(entries[1]["prompt"]).read_text(encoding="utf-8")
    assert read_json(workdir / "areas.json")["unplanned"] == ["a03"]
    plan = read_json(workdir / "plan-docs.json")
    assert plan == [*docs_plan, *entries]
    assert [e["role"] for e in plan] == ["review", "review", "gap", "gap", "sheet", "sheet"]


def test_sheet_prompt_has_mandatory_lines_and_no_placeholder_left(tmp_path: Path) -> None:
    root, workdir = _tree(tmp_path)
    _write_areas(workdir)
    dd_dispatch.plan_docs(root, workdir, _config())
    entries = dd_dispatch.plan_sheets(root, workdir, _config())
    assert [e["id"] for e in entries] == ["a01", "a02", "a03"]
    for entry in entries:
        text = Path(entry["prompt"]).read_text(encoding="utf-8")
        assert all(line in text for line in MANDATORY)
        assert "{{" not in text and entry["output"] in text
    assert "(none)" in Path(entries[1]["prompt"]).read_text(encoding="utf-8")
    assert read_json(workdir / "areas.json")["unplanned"] == []


def _sheet(**over: Any) -> dict[str, Any]:
    sheet: dict[str, Any] = {
        "area": "a01",
        "surface": [{"kind": "flag", "name": "--force", "parent": "sync", "summary": "x",
                     "default": None, "defined_at": "src/a.py:1", "user_facing": True,
                     "hidden": False}],
        "behaviours": [{"statement": "the `f` reads", "evidence": ["src/a.py:2"]}],
        "dismissed": [{"hint": "flag --old", "why": "internal"}]}
    sheet.update(over)
    return sheet


def test_validate_sheet_shape(tmp_path: Path) -> None:
    assert dd_dispatch.validate_sheet(_sheet()) == []
    bare = _sheet()
    del bare["dismissed"]
    assert any("no dismissed" in p for p in dd_dispatch.validate_sheet(bare))
    entry = _sheet()["surface"][0]
    del entry["defined_at"]
    problems = dd_dispatch.validate_sheet(_sheet(surface=[entry]))
    assert any("surface[0] has no defined_at" in p for p in problems)
    assert any("area is not a string" in p for p in dd_dispatch.validate_sheet(_sheet(area=3)))
    flag = _sheet()["surface"][0] | {"hidden": "no"}
    assert any("hidden is not a boolean" in p
               for p in dd_dispatch.validate_sheet(_sheet(surface=[flag])))
    assert any("evidence" in p for p in dd_dispatch.validate_sheet(
        _sheet(behaviours=[{"statement": "s"}])))
    assert dd_dispatch.validate_sheet([]) == ["output is not a JSON object"]
    # the area must be the entry's id
    root, workdir = _tree(tmp_path)
    _write_areas(workdir)
    entry_a02 = dd_dispatch.plan_sheets(root, workdir, _config())[1]
    write_json(Path(entry_a02["output"]), _sheet())
    assert dd_dispatch._problems(workdir, entry_a02) == ["area 'a01' is not 'a02'"]


def _readme_workdir(tmp_path: Path, manifest: dict[str, str] | None) -> tuple[Path, Path]:
    root = tmp_path / "my-repo"
    workdir = root / ".document-drift"
    workdir.mkdir(parents=True)
    for name, text in (manifest or {}).items():
        (root / name).write_text(text, encoding="utf-8")
    write_json(workdir / "inventory.json", {"docs": [], "project_files": sorted(manifest or {})})
    surface = [
        {"id": "a01-s01", "kind": "command", "name": "sync", "parent": None,
         "summary": "pulls the remote state", "default": None, "defined_at": "src/cli.py:4",
         "user_facing": True, "hidden": False},
        {"id": "a01-s02", "kind": "flag", "name": "--force", "parent": "sync",
         "summary": "overwrites local rows", "default": "false",
         "defined_at": "src/cli.py:7", "user_facing": True, "hidden": False},
        {"id": "a01-s03", "kind": "flag", "name": "--legacy", "parent": "sync",
         "summary": "old mode", "default": None, "defined_at": "src/cli.py:9",
         "user_facing": True, "hidden": True},
        {"id": "a01-s04", "kind": "env", "name": "APP_TOKEN", "parent": None,
         "summary": "from the pattern scan", "default": None, "defined_at": "src/cfg.py:2",
         "user_facing": True, "hidden": False, "filled": True}]
    behaviours = [{"id": "a01-b01", "statement": "`sync` writes `state.db`",
                   "evidence": ["src/cli.py:12", "src/db.py:3"]}]
    second = {"area": "a03", "dismissed": [], "behaviours": [],
              "surface": [{"id": "a03-s01", "kind": "route", "name": "/items", "parent": "GET",
                           "summary": "lists items", "default": None,
                           "defined_at": "web/app.py:5", "user_facing": True,
                           "hidden": False}]}
    write_json(workdir / "sheets.json", {
        "sheets": {"a03": second,
                   "a01": {"area": "a01", "surface": surface, "behaviours": behaviours,
                           "dismissed": []}},
        "unchecked": [{"area": "a02", "why": "invalid after retry"},
                      {"area": "a04", "why": "over the cap"}],
        "filled": 1, "hidden_corrected": 0})
    return root, workdir


def test_plan_readme_renders_sheets_and_name(tmp_path: Path) -> None:
    pyproject = '[project]\nname = "myproject"\ndescription = "Syncs a store."\n'
    root, workdir = _readme_workdir(tmp_path, {"pyproject.toml": pyproject})
    config = _config()
    plan = dd_dispatch.plan_readme(root, workdir, config)
    assert [(e["id"], e["role"], e["model"]) for e in plan] == [
        ("r001", "readme", config["models"]["readme"])]
    assert plan[0]["prompt"].endswith("/prompts/readme-r001.md")
    assert plan[0]["output"].endswith("/readme/r001.json")
    assert (workdir / "readme").is_dir()
    assert read_json(workdir / "plan-readme.json") == plan
    text = Path(plan[0]["prompt"]).read_text(encoding="utf-8")
    assert all(line in text for line in MANDATORY)
    assert "{{" not in text and plan[0]["output"] in text
    assert "`myproject`" in text and "Syncs a store." in text
    assert root.resolve().as_posix() in text
    assert f"At most {config['readme_lines']} lines" in text
    expected = (
        "- a01-s01 command `sync`: pulls the remote state; src/cli.py:4\n"
        "- a01-s02 flag `--force`, parent `sync`: overwrites local rows; default `false`; "
        "src/cli.py:7\n"
        "- a01-s04 env `APP_TOKEN`: from the pattern scan; src/cfg.py:2 (filled from the scan)\n"
        "- a01-b01: `sync` writes `state.db` (src/cli.py:12, src/db.py:3)\n"
        "- a03-s01 route `/items`, parent `GET`: lists items; web/app.py:5\n")
    assert expected in text
    assert "--legacy" not in text and "a01-s03" not in text
    assert "- a02\n- a04\n" in text
    # no manifest: the directory's name; a manifest without a description says so
    root2, workdir2 = _readme_workdir(tmp_path / "two", None)
    text2 = Path(dd_dispatch.plan_readme(root2, workdir2, config)[0]["prompt"]).read_text(
        encoding="utf-8")
    assert "`my-repo`" in text2 and "(the manifest has no description)" in text2
    root3, workdir3 = _readme_workdir(tmp_path / "three", {"package.json": '{"name": "web"}'})
    text3 = Path(dd_dispatch.plan_readme(root3, workdir3, config)[0]["prompt"]).read_text(
        encoding="utf-8")
    assert "`web`" in text3 and "(the manifest has no description)" in text3


def test_validate_readme_shape(tmp_path: Path) -> None:
    good = {"text": "# x\n\nx does `y`.\n",
            "claims": [{"start_line": 3, "end_line": 3, "cites": ["a01-b01"]}]}
    assert dd_dispatch.validate_readme(good) == []
    assert dd_dispatch.validate_readme([]) == ["output is not a JSON object"]
    assert any("text" in p for p in dd_dispatch.validate_readme({"claims": []}))
    assert any("claims is not a list" in p
               for p in dd_dispatch.validate_readme({"text": "", "claims": {}}))
    bad = {"text": "# x\n", "claims": [{"start_line": "3", "end_line": 3, "cites": "a01"},
                                       "claim"]}
    problems = dd_dispatch.validate_readme(bad)
    assert any("claims[0]: start_line" in p for p in problems)
    assert any("claims[0]: cites" in p for p in problems)
    assert any("claims[1] is not a JSON object" in p for p in problems)
    # _problems routes the role and has no id key to compare
    workdir = tmp_path / "work"
    (workdir / "readme").mkdir(parents=True)
    out = workdir / "readme" / "r001.json"
    entry: dd_dispatch.PlanEntry = {"id": "r001", "role": "readme", "model": "opus",
                                    "prompt": "p", "output": out.as_posix()}
    assert dd_dispatch._problems(workdir, entry) == [f"{out.as_posix()} is missing"]
    write_json(out, good)
    assert dd_dispatch.check_outputs(workdir, [entry], "readme") == (["r001"], [])
    write_json(out, bad)
    assert dd_dispatch.check_outputs(workdir, [entry], "readme")[0] == []
