from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, StepError, read_json, write_json
from dd_summary import render
from dd_summary import run as run_a

HEAD = "b" * 40


# ---- phase A ----------------------------------------------------------------------------

HEADINGS = ["Run", "Docs", "References and anchors", "Checkability", "Notice loop",
            "Change set", "Review units", "Claims checked", "Edits proposed", "Script checks",
            "Verdicts", "Applied", "Gaps", "Needs a human decision", "Markers", "Result"]
LATER = "A later run cannot see code changes behind these docs until they name code."


def _edit(eid: str, doc: str, line: int, typ: str, source: str = "review",
          status: str = "kept", check: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"id": eid, "doc": doc, "start_line": line, "end_line": line, "old": "o", "new": "n",
            "type": typ, "claim": "c " + eid, "evidence": ["src/a.py:1"], "subject": "thing",
            "source": source, "status": status, "check": check, "human_kind": None,
            "reason": None, **extra}


def _wd(tmp_path: Path, *, check: bool = False, mode: str = "first",
        **over: Any) -> Path:
    wd = tmp_path / "wd"
    files: dict[str, Any] = {
        "preflight.json": {"run_id": "2026-10-12-a3f1", "head": HEAD, "date": "2026-10-12",
                           "check": check, "branch": "docs/drift-x", "base": None,
                           "full": False},
        "inventory.json": {"docs": ["README.md", "docs/a.md", "docs/b.md"],
                           "excluded": [{"path": "x/1.md", "reason": "vendored"},
                                        {"path": "x/2.md", "reason": "vendored"}],
                           "skipped": [{"path": "big.md", "reason": "too-large"}]},
        "tokens.json": {"markers": [
            {"doc": "README.md", "line": 5, "kind": "drift-ignore", "reason": "r",
             "target_line_start": 6, "target_line_end": 7},
            {"doc": "README.md", "line": 9, "kind": "drift-ignore", "reason": "stale",
             "target_line_start": 10, "target_line_end": 11},
            {"doc": "docs/a.md", "line": 3, "kind": "drift-ignore", "reason": None,
             "target_line_start": 4, "target_line_end": 4}]},
        "anchors.json": {
            "references": [{"doc": "README.md", "line": 6, "text": "a"}],
            "anchors": [], "unanchored": [], "skipped": [],
            "counts": {"references": 12, "paths": 2, "anchored": 6, "ambiguous": 3,
                       "unknown": 1},
            "checkability": {
                "README.md": {"references": 8, "anchored": 6, "rate": 0.75, "status": "ok"},
                "docs/a.md": {"references": 3, "anchored": 0, "rate": 0.0,
                              "status": "unverifiable"},
                "docs/b.md": {"references": 1, "anchored": 0, "rate": 0.0,
                              "status": "unverifiable"},
                "docs/c.md": {"references": 10, "anchored": 1, "rate": 0.1,
                              "status": "weak"}}},
        "changes.json": {"mode": mode, "last_run": None if mode == "first" else HEAD,
                         "last_run_source": None if mode == "first" else "commit",
                         "scope": "first" if mode == "first" else f"since {HEAD}",
                         "changed_files": ["a.py", "b.py"],
                         "hunks": {"a.py": [{}, {}], "b.py": [{}]},
                         "review": {"docs/a.md": [[1, 9]]},
                         "affected": {"docs/a.md": {"anchor_reasons": [1, 2], "missing": [1],
                                                    "doc_changed": True}}},
        "units.json": {"units": [{"id": "u001"}, {"id": "u002"}, {"id": "u003"}],
                       "unchecked": ["u009"]},
        "gaps.json": {"candidates": [1, 2, 3, 4], "lists": [],
                      "gaps": [{"gap_kind": "undocumented", "target_doc": "docs/a.md",
                                "name": "n1", "reason": "most-names"},
                               {"gap_kind": "undocumented", "target_doc": "docs/a.md",
                                "name": "n2", "reason": "most-names"},
                               {"gap_kind": "missing-from-list", "target_doc": "README.md",
                                "name": "n3", "reason": "any-list"}],
                      "targets": [], "no_home": [], "unchecked": ["docs/z.md"]},
        "notices.json": {
            "decisions": [{"doc": "docs/a.md", "line": 20, "action": "clear-anchored",
                           "block": [21, 22]},
                          {"doc": "docs/a.md", "line": 30, "action": "clear-ignore",
                           "block": [31, 32]},
                          {"doc": "docs/a.md", "line": 40, "action": "escalate",
                           "block": [41, 42]},
                          {"doc": "docs/b.md", "line": 5, "action": "remove",
                           "block": [6, 7]}],
            "edits": [_edit("n001", "docs/a.md", 20, "clear", "notice"),
                      _edit("n002", "docs/a.md", 30, "clear", "notice"),
                      _edit("n003", "docs/a.md", 40, "escalate", "notice"),
                      _edit("n004", "docs/b.md", 5, "unverified", "notice"),
                      _edit("n005", "README.md", 12, "notice", "notice")],
            "stale": [{"doc": "docs/b.md", "line": 50, "reason": "malformed"}],
            "nominations": []},
        "plan-docs.json": [],
        "review/u001.json": {"claims_checked": 7, "code_claims": {}},
        "review/u002.json": {"claims_checked": 5, "code_claims": {}},
        "edits.json": {
            "edits": [_edit("u001-e01", "README.md", 3, "correct"),
                      _edit("u001-e02", "docs/a.md", 4, "anchor"),
                      _edit("u001-e03", "docs/c.md", 4, "anchor", status="dropped",
                            check="old-mismatch"),
                      _edit("u002-e01", "docs/a.md", 8, "remove", status="human",
                            check="large-deletion"),
                      _edit("g001-e01", "docs/a.md", 9, "add", "gap", subject="`n1`"),
                      _edit("n001", "docs/a.md", 20, "clear", "notice"),
                      _edit("n002", "docs/a.md", 30, "clear", "notice"),
                      _edit("n003", "docs/a.md", 40, "escalate", "notice"),
                      _edit("n004", "docs/b.md", 5, "unverified", "notice"),
                      _edit("n005", "README.md", 12, "notice", "notice")],
            "questions": [],
            "refusals": [{"kind": "not-user-facing", "name": "q", "reason": "r",
                          "doc": "docs/a.md"},
                         {"kind": "already-documented", "name": "w", "reason": "r",
                          "doc": "docs/a.md"},
                         {"kind": "not-user-facing", "name": "e", "reason": "r",
                          "doc": "docs/a.md"}],
            "human": [{"doc": "docs/a.md", "line": 8, "kind": "large-deletion",
                       "text": "c u002-e01 (too long)", "evidence": ["src/a.py:1"]}],
            "unverified_blocks": [], "code_claims": {"docs/a.md": 0, "docs/b.md": 4},
            "unchecked_units": ["u009", "u004"], "unchecked_gap_docs": ["docs/z.md"],
            "unverified_batches": []},
        "verdicts.json": {"verdicts": {"u001-e01": {"verdict": "accept", "reason": "ok"},
                                       "u001-e02": {"verdict": "accept", "reason": "ok"},
                                       "g001-e01": {"verdict": "reject", "reason": "no"}},
                          "unverified": ["u003-e01"]},
    }
    if not check:
        files["applied.json"] = {"applied": ["u001-e01", "u001-e02", "n001", "n003", "n005"],
                                 "reverted": [{"edit": "n002", "reason": "old-mismatch"}],
                                 "docs": ["README.md", "docs/a.md"],
                                 "link_updates": [{}, {}]}
        files["commits.json"] = {"branch": "docs/drift-x",
                                 "commits": [{"sha": "c" * 40, "kind": "corrections"},
                                             {"sha": "d" * 40, "kind": "additions"}]}
    files.update(over)
    for name, doc in files.items():
        if doc is not None:
            write_json(wd / name, doc)
    return wd


def _section(text: str, name: str) -> list[str]:
    lines = text.split("\n")
    start = lines.index(name)
    end = next((i for i in range(start + 1, len(lines)) if lines[i] in HEADINGS), len(lines))
    return [x for x in lines[start + 1:end] if x]


def test_summary_sections_in_order(tmp_path: Path) -> None:
    text = render(_wd(tmp_path))
    lines = text.split("\n")
    wanted = [h for h in HEADINGS if h != "Change set"]
    positions = [lines.index(h) for h in wanted]
    assert positions == sorted(positions)
    assert "Change set" not in lines
    assert "Run id: 2026-10-12-a3f1" in text
    assert "Mode: first" in text
    assert text.endswith("\n") and "\r" not in text
    assert run_a(tmp_path / "wd") == text
    assert (tmp_path / "wd" / "summary.md").read_bytes() == text.encode("utf-8")
    later_text = render(_wd(tmp_path / "l", mode="later"))
    later = later_text.split("\n")
    assert later.index("Notice loop") < later.index("Change set") < later.index("Review units")
    body = _section(later_text, "Change set")
    assert "changed files 2, hunks 3" in body
    assert "- docs/a.md: anchors 2, missing 1, doc changed" in body


def test_checkability_lists_unverifiable_and_weak_docs(tmp_path: Path) -> None:
    body = _section(render(_wd(tmp_path)), "Checkability")
    assert "README.md: 8 refs, 6 anchored (75%)" in body
    assert "docs/c.md: 10 refs, 1 anchored (10%)" in body
    assert "Unverifiable (no anchor):" in body
    assert "  not about the code (0 code claims):" in body
    assert "    - docs/a.md (1 anchor edit applied)" in body
    assert "  describes the code but names nothing:" in body
    assert "    - docs/b.md" in body
    weak = body[body.index("Weakly anchored:"):]
    assert weak[1] == "  - docs/c.md"
    assert body[-1] == LATER
    later = render(_wd(tmp_path / "l", mode="later"))
    assert "not about the code" not in later
    assert LATER in later


def test_checkability_all_anchored_has_no_closing_sentence(tmp_path: Path) -> None:
    ok = {"README.md": {"references": 8, "anchored": 6, "rate": 0.75, "status": "ok"}}
    anchors = {"references": [], "anchors": [], "unanchored": [], "skipped": [],
               "counts": {"references": 8, "paths": 0, "anchored": 6, "ambiguous": 2,
                          "unknown": 0}, "checkability": ok}
    text = render(_wd(tmp_path, **{"anchors.json": anchors}))
    assert LATER not in text
    assert "Unverifiable" not in text


def test_notice_loop_counts(tmp_path: Path) -> None:
    body = _section(render(_wd(tmp_path)), "Notice loop")
    assert ("placed 1, escalated 1, cleared 1 (now anchored 1, block changed 0, "
            "drift-ignore 0), removed 0, stale 1") in body
    check = _section(render(_wd(tmp_path / "c", check=True)), "Notice loop")
    assert ("placed 1, escalated 1, cleared 2 (now anchored 1, block changed 0, "
            "drift-ignore 1), removed 1, stale 1") in check


def test_check_mode_lists_planned_edits_as_bullets(tmp_path: Path) -> None:
    body = _section(render(_wd(tmp_path, check=True)), "Result")
    assert "No branch created" in body
    planned = body[body.index("Planned edits:") + 1:]
    assert planned[:2] == ["- README.md:3 correct c u001-e01 (src/a.py:1)",
                           "- README.md:12 notice unverified block (1st notice)"]
    assert "- docs/a.md:4 anchor thing (src/a.py:1)" in planned
    assert not any("u001-e03" in x or "add n1" in x for x in planned)
    assert "Exit: 1 (accepted edits exist)" in body
    empty = {"verdicts": {}, "unverified": []}
    edits = _wd(tmp_path / "n", check=True, **{"verdicts.json": empty})
    notices = {"decisions": [], "edits": [], "stale": [], "nominations": []}
    write_json(edits / "notices.json", notices)
    doc = {"edits": [], "questions": [], "refusals": [], "human": [],
           "unverified_blocks": [], "code_claims": {}, "unchecked_units": [],
           "unchecked_gap_docs": [], "unverified_batches": []}
    write_json(edits / "edits.json", doc)
    assert "Exit: 0" in _section(render(edits), "Result")


def test_no_branch_line(tmp_path: Path) -> None:
    wd = _wd(tmp_path, **{"commits.json": {"branch": None, "commits": []}})
    assert _section(render(wd), "Result") == ["No branch created"]
    full = _section(render(_wd(tmp_path / "f")), "Result")
    assert full == ["Branch: docs/drift-x", f"Commits: {'c' * 40} (corrections)",
                    f"Commits: {'d' * 40} (additions)"]


def test_summary_counts_checks_verdicts_applied_gaps_markers(tmp_path: Path) -> None:
    text = render(_wd(tmp_path))
    checks = _section(text, "Script checks")
    assert "- large-deletion: 1" in checks and "- old-mismatch: 1" in checks
    assert "kept 8" in checks
    assert "accept 2, reject 1, unsure 0, unverified 1" in _section(text, "Verdicts")
    applied = _section(text, "Applied")
    assert "applied 5, reverted 1, link updates 2" in applied
    assert "- docs/a.md" in applied
    assert "claims checked: 12" in _section(text, "Claims checked")
    review = "\n".join(_section(text, "Review units"))
    assert "checked 2" in review and "unchecked by cap 1" in review
    assert "unchecked after retry 1" in review
    gaps = "\n".join(_section(text, "Gaps"))
    assert "candidates 4" in gaps and "undocumented 2" in gaps
    assert "missing-from-list 1" in gaps
    assert "- docs/a.md: 2" in gaps and "not-user-facing 2" in gaps
    assert "already-documented 1" in gaps and "- docs/z.md" in gaps
    markers = _section(text, "Markers")
    assert "- docs/a.md:3" in markers and "- README.md:9" in markers
    assert "- README.md:5" not in markers
    assert "- docs/b.md:50 malformed" in markers
    human = "\n".join(_section(text, "Needs a human decision"))
    assert "docs/a.md:8 large-deletion" in human


def test_early_stop_says_not_run(tmp_path: Path) -> None:
    wd = _wd(tmp_path)
    for name in ("edits.json", "verdicts.json", "applied.json", "commits.json",
                 "review/u001.json", "review/u002.json"):
        (wd / name).unlink()
    text = render(wd)
    assert "not run" in _section(text, "Verdicts")[0]
    assert "not run" in _section(text, "Applied")[0]
    assert "not run" in _section(text, "Edits proposed")[0]
    assert "no review output" in "\n".join(_section(text, "Claims checked"))
    assert "not reviewed" in "\n".join(_section(text, "Checkability"))


def test_stale_markers_not_run_without_anchors(tmp_path: Path) -> None:
    wd = _wd(tmp_path)
    (wd / "anchors.json").unlink()
    markers = _section(render(wd), "Markers")
    assert "stale markers: not run" in markers
    assert "- README.md:9" not in markers


def test_nothing_to_review_is_stated(tmp_path: Path) -> None:
    empty = {"mode": "later", "last_run": HEAD, "last_run_source": "commit",
             "scope": f"since {HEAD}", "changed_files": [], "hunks": {}, "affected": {},
             "review": {}}
    wd = _wd(tmp_path, **{"changes.json": empty})
    gaps = {"candidates": [], "lists": [], "gaps": [], "targets": [], "no_home": [],
            "unchecked": []}
    write_json(wd / "gaps.json", gaps)
    both = "No doc was affected and no gap candidate exists; no agent was dispatched."
    assert both in _section(render(wd), "Review units")
    write_json(wd / "gaps.json", {**gaps, "targets": ["docs/a.md"]})
    only = "No doc was affected; no review agent was dispatched."
    assert only in _section(render(wd), "Review units")
    assert both not in render(wd)
    assert only not in render(_wd(tmp_path / "f"))


def test_phase_a_redacts_repository_strings(tmp_path: Path) -> None:
    secret = "ghp_" + "a" * 36
    inv = {"docs": [f"{secret}.md"], "excluded": [], "skipped": []}
    assert secret not in render(_wd(tmp_path, **{"inventory.json": inv}))


def test_summary_without_preflight_is_exit_5(tmp_path: Path) -> None:
    workdir = _wd(tmp_path)
    (workdir / "preflight.json").unlink()
    with pytest.raises(StepError) as exc:
        run_a(workdir)
    assert exc.value.code == EXIT_MISSING


def test_review_units_lists_retry_units_and_not_reviewed_ranges(tmp_path: Path) -> None:
    body = _section(render(_wd(tmp_path)), "Review units")
    assert body == ["checked 2, unchecked by cap 1, unchecked after retry 1, retry units 0, "
                    "not reviewed 0 ranges"]
    wd = _wd(tmp_path / "r", **{
        "units.json": {"units": [{"id": "u001"}, {"id": "u002", "retry_of": "u001"}],
                       "unchecked": []}})
    edits = read_json(wd / "edits.json")
    edits["unchecked_units"] = []
    edits["not_reviewed"] = [{"unit": "u002", "doc": "docs/a.md", "start_line": 4,
                              "end_line": 9, "why": "too long"}]
    write_json(wd / "edits.json", edits)
    assert _section(render(wd), "Review units") == [
        "checked 2, unchecked by cap 0, unchecked after retry 0, retry units 1, "
        "not reviewed 1 ranges", "- docs/a.md:4-9 (too long)"]


# ---- the README section (phase B spec 10) -----------------------------------------------

def _readme_wd(tmp_path: Path, **over: Any) -> Path:
    stmts = [{"id": f"s{i:03d}", "start_line": i, "text": f"text {i}",
              "prereject": "hidden" if i == 6 else None} for i in range(1, 9)]
    files: dict[str, Any] = {
        "areas.json": {"area_lines": 4000, "unplanned": [], "areas": [
            {"id": "a01", "lines": 300, "hints": ["x", "y", "z"]},
            {"id": "a02", "lines": 120, "hints": ["w"]},
            {"id": "a03", "lines": 80, "hints": []}]},
        "sheets.json": {"sheets": {"a01": {}, "a02": {}},
                        "unchecked": [{"area": "a03", "why": "no output"}],
                        "filled": 1, "hidden_corrected": 0, "retried": ["a02", "a03"]},
        # a later stage's retry overwrites retry.json: the summary reads sheets.json and
        # readme.json instead
        "retry.json": [{"role": "verify", "id": "v01"}],
        "plan-readme.json": [{"id": "r001", "role": "readme"}],
        "readme.json": {"statements": stmts, "attempts": 2},
        "verdicts.json": {"verdicts": {}, "unverified": [],
                          "readme": {"s001": {"verdict": "accept"}, "s002": {"verdict": "accept"},
                                     "s003": {"verdict": "accept"}, "s004": {"verdict": "reject"},
                                     "s005": {"verdict": "unsure"}},
                          "readme_unverified": ["s007"]},
        "applied.json": {"applied": [], "reverted": [], "docs": [], "link_updates": [],
                         "readme": {"lines": 42, "statements": 3, "removed": 5}},
    }
    files.update(over)
    wd = _wd(tmp_path)
    pre = read_json(wd / "preflight.json")
    write_json(wd / "preflight.json", {**pre, "readme": True,
                                       **({"check": True} if over.get("check") else {})})
    files.pop("check", None)
    for name, doc in files.items():
        if doc is None:
            (wd / name).unlink(missing_ok=True)
        else:
            write_json(wd / name, doc)
    return wd


def test_readme_section_counts(tmp_path: Path) -> None:
    text = render(_readme_wd(tmp_path))
    lines = text.split("\n")
    assert lines.index("Gaps") < lines.index("README") < lines.index("Needs a human decision")
    assert _section(text, "README") == [
        "areas: 3 (500 lines, area_lines 4000)",
        "sheets: 2 valid, 1 unchecked (a03: no output), 2 retried",
        "hints: 3 accounted for, 1 filled from the scan",
        "writer: 2 attempts",
        "statements: 8 proposed, 3 accepted, 2 rejected, 1 unsure, 1 unverified",
        "written: README.md, 42 lines"]
    result = _section(text, "Result")
    assert result[-1] == "README: README.md (42 lines)"
    assert result[-2].startswith("Commits: ")


def test_readme_section_reasons_for_none(tmp_path: Path) -> None:
    count = iter(range(100))

    def written(**over: Any) -> str:
        wd = _readme_wd(tmp_path / f"c{next(count)}", **over)
        body = _section(render(wd), "README")
        return body[-1]

    none = {"applied.json": {"applied": [], "reverted": [], "docs": [], "link_updates": [],
                             "readme": None}}
    assert written(**none, **{"sheets.json": {"sheets": {}, "unchecked": [], "filled": 0,
                                               "hidden_corrected": 0}}
                   ) == "written: none (no valid sheet)"
    assert written(**none, **{"readme.json": None}) == "written: none (no writer output)"
    assert written(**none, **{"readme.json": {"invalid": ["no writer output"]}}
                   ) == "written: none (no writer output)"
    secret = "ghp_" + "a" * 36
    assert written(**none, **{"readme.json": {"invalid": [f"line 3 is in no claim: {secret}",
                                                          "second"], "attempts": 2}}
                   ) == "written: none (invalid writer output: line 3 is in no claim: ghp_***)"
    assert written(**none, **{"verdicts.json": {"verdicts": {}, "unverified": [], "readme": {},
                                                "readme_unverified": []}}
                   ) == "written: none (no accepted statement)"
    wd = _readme_wd(tmp_path / "chk", **none)
    pre = read_json(wd / "preflight.json")
    write_json(wd / "preflight.json", {**pre, "check": True})
    assert _section(render(wd), "README")[-1] == "written: none (check mode)"
    empty = _readme_wd(tmp_path / "e", **{"plan-readme.json": [], "retry.json": None,
                                         "sheets.json": None, "areas.json": None,
                                         "readme.json": {"invalid": ["no writer output"],
                                                         "attempts": 0}, **none})
    body = _section(render(empty), "README")
    assert body[:4] == ["areas: 0 (0 lines, area_lines 0)",
                        "sheets: 0 valid, 0 unchecked, 0 retried",
                        "hints: 0 accounted for, 0 filled from the scan", "writer: 0 attempts"]


def test_readme_section_absent_without_readme(tmp_path: Path) -> None:
    assert "README" not in render(_wd(tmp_path)).split("\n")


def test_check_mode_plans_the_readme_create_bullet(tmp_path: Path) -> None:
    wd = _readme_wd(tmp_path, check=True)
    create = {**_edit("r001", "README.md", 1, "create", "readme", claim="readme from 2 sheets"),
              "statements": 8}
    edits = read_json(wd / "edits.json")
    write_json(wd / "edits.json", {**edits, "edits": [create]})
    write_json(wd / "verdicts.json", {"verdicts": {}, "unverified": [],
                                      "readme": {"s001": {"verdict": "accept"}},
                                      "readme_unverified": []})
    write_json(wd / "notices.json", {"decisions": [], "edits": [], "stale": [],
                                     "nominations": []})
    body = _section(render(wd), "Result")
    assert body[body.index("Planned edits:") + 1:] == [
        "- README.md:1 create readme (8 statements from 2 sheets, 7 removed)",
        "Exit: 1 (accepted edits exist)"]
    write_json(wd / "verdicts.json", {"verdicts": {}, "unverified": [], "readme": {},
                                      "readme_unverified": []})
    assert _section(render(wd), "Result")[-1] == "Exit: 0"


def test_edits_proposed_counts_the_readme_in_readme_mode_only(tmp_path: Path) -> None:
    wd = _readme_wd(tmp_path)
    assert _section(render(wd), "Edits proposed")[-1] == "readme: 0"
    create = {**_edit("r001", "README.md", 1, "create", "readme"), "statements": 8}
    edits = read_json(wd / "edits.json")
    write_json(wd / "edits.json", {**edits, "edits": [*edits["edits"], create]})
    body = _section(render(wd), "Edits proposed")
    assert body[-1] == "readme: 1" and body[0].startswith("review: ")
    assert all(not line.startswith("readme") for line in
               _section(render(_wd(tmp_path / "a")), "Edits proposed"))
