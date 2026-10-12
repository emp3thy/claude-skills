from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, StepError, write_json
from dd_summary import render
from dd_summary import run as run_a
from dd_summary import run_phase1 as run

HEAD = "b" * 40


def _tok(doc: str, line: int, kind: str = "path", text: str = "x") -> dict[str, Any]:
    return {"doc": doc, "line": line, "col": 0, "kind": kind, "text": text}


def _finding(fid: str, line: int, cls: str, text: str, **extra: Any) -> dict[str, Any]:
    return {"id": fid, "doc": "README.md", "line": line, "col": 2, "kind": "path", "text": text,
            "class": cls, "human_kind": None, "evidence": "", **extra}


def _marker(line: int, reason: str | None, start: int | None, end: int | None,
            doc: str = "README.md") -> dict[str, Any]:
    return {"doc": doc, "line": line, "kind": "drift-ignore", "reason": reason,
            "target_line_start": start, "target_line_end": end}


def _workdir(tmp_path: Path, *, check: bool = False, branch: str | None = "docs/drift-x",
             history_unavailable: bool = True) -> Path:
    workdir = tmp_path / "work"
    write_json(workdir / "preflight.json", {
        "head": HEAD, "branch_from": "main", "branch": "docs/drift-x", "git_version": "git",
        "run_id": "0123456789ab", "scope": "base:origin/main", "check": check,
        "date": "2026-01-02",
        "config_warnings": [".document-drift.yaml: unknown key 'bogus' ignored"],
    })
    write_json(workdir / "inventory.json", {
        "docs": ["README.md", "docs/a.md", "docs/b.md"],
        "excluded": [{"path": "docs/adr/1.md", "reason": "excluded-path:**/adr/**"},
                     {"path": "docs/adr/2.md", "reason": "excluded-path:**/adr/**"},
                     {"path": "vendor/x.md", "reason": "vendored"}],
        "skipped": [{"path": "big.md", "reason": "too-large"}],
        "files": [], "never_edit_re": "x", "scope_dropped": ["docs/c.md"],
    })
    write_json(workdir / "tokens.json", {
        "docs": {
            "README.md": [_tok("README.md", n) for n in (3, 5, 7, 9, 11, 13, 21, 22)]
            + [_tok("README.md", 30, "anchor", "#gone")],
            "docs/a.md": [_tok("docs/a.md", 1, "script", "build")],
        },
        "markers": [
            _marker(20, "kept for the migration guide", 21, 22),
            _marker(25, "stale reason", 26, 27),
            _marker(28, None, None, None),
            _marker(40, "end of file", None, None),
        ],
        "skipped": [{"doc": "docs/b.md", "reason": "not-utf8"}],
    })
    findings = [
        _finding("F001", 3, "provable-replace", "src/old.py", replacement="src/new.py"),
        _finding("F002", 5, "provable-delete", "src/gone.py"),
        _finding("F003", 7, "human", "src/maybe.py", human_kind="ambiguous-rename",
                 evidence="renamed in 1234567"),
        _finding("F004", 9, "human", "src/dropped.py", human_kind="prose-mention",
                 superseded_by="H002"),
        _finding("F005", 11, "summary-only", "src/never.py"),
    ]
    write_json(workdir / "findings.json", {
        "findings": findings, "history_unavailable": history_unavailable,
        "honoured": [{"doc": "README.md", "line": 21, "col": 0, "kind": "path", "text": "x",
                      "reason": "kept for the migration guide"}],
    })
    write_json(workdir / "hunks-provable.json", {"hunks": [
        {"id": "H001", "finding_id": "F001", "doc": "README.md"},
        {"id": "H002", "finding_id": "F002", "doc": "README.md"},
        {"id": "H003", "finding_id": "F006", "doc": "docs/a.md"},
    ]})
    if not check:
        write_json(workdir / "applied.json", {
            "applied": ["H001", "H002"],
            "reverted": [{"hunk": "H003", "reason": "recheck-new-finding"}],
            "docs": ["README.md"],
        })
        write_json(workdir / "commits.json", {
            "branch": branch, "commits": ["c" * 40] if branch else []})
    return workdir


def test_summary_lists_human_findings_and_stale_markers(tmp_path: Path) -> None:
    workdir = _workdir(tmp_path)
    text = run(workdir)
    assert (workdir / "summary.md").read_bytes() == text.encode("utf-8")
    assert "\r" not in text and text.endswith("\n")
    lines = text.splitlines()
    assert lines[0] == "Run: 0123456789ab"
    assert "Scope: base:origin/main" in lines
    assert f"Base: {HEAD}" in lines
    assert "Docs scanned: 2" in lines
    assert "Docs out of scope: 1" in lines
    assert "  - docs/c.md" in lines
    assert "Docs excluded: 3" in lines
    assert "- excluded-path:**/adr/** (2)" in lines
    assert "  - docs/adr/2.md" in lines
    assert "- vendored (1)" in lines
    assert "Docs skipped: 2" in lines
    assert "- not-utf8 (1)" in lines and "  - docs/b.md" in lines
    assert "- too-large (1)" in lines and "  - big.md" in lines
    assert ("Tokens: 10 (path 8, anchor 1, script 1, version 0, tree 0); resolved 4; "
            "suppressed by a marker 1") in lines
    assert ("Candidates: 5 (provable-replace 1, provable-delete 1, human 2, "
            "summary-only 1)") in lines
    assert "Hunks: 3 provable; applied 2; reverted 1" in lines
    assert "- H003 reverted: recheck-new-finding" in lines
    # the human section comes from render_human: superseded findings are not listed
    assert "Needs a human decision:" in lines
    assert any(line.startswith("- README.md:7 [ambiguous-rename]") for line in lines)
    assert "src/dropped.py" not in text
    assert "Markers without a reason:" in lines
    assert "- README.md:28 drift-ignore" in lines
    stale = lines.index("Stale markers (their block holds no suppressed reference):")
    assert lines[stale + 1:stale + 3] == [
        "- README.md:25 drift-ignore: stale reason",
        "- README.md:40 drift-ignore: end of file",
    ]
    assert "kept for the migration guide" not in text
    assert any(line.startswith("History unavailable:") for line in lines)
    assert "Config warnings:" in lines
    assert "- .document-drift.yaml: unknown key 'bogus' ignored" in lines
    assert lines[-2:] == ["Branch: docs/drift-x", f"Commits: {'c' * 40}"]


def test_summary_no_branch_and_no_history_line(tmp_path: Path) -> None:
    text = run(_workdir(tmp_path, branch=None, history_unavailable=False))
    assert text.splitlines()[-1] == "No branch created."
    assert "History unavailable" not in text
    assert "Branch:" not in text


def _planned(workdir: Path, third: str = "F005") -> None:
    write_json(workdir / "hunks-provable.json", {"hunks": [
        {"id": "H001", "finding_id": "F001", "doc": "README.md", "verb": "replace",
         "new_text": "src/new.py", "reason": "renamed in 1234567", "also": []},
        {"id": "H002", "finding_id": "F002", "doc": "README.md", "verb": "delete",
         "new_text": None, "reason": "deleted in 89abcde",
         "also": [{"finding_id": third, "verb": "delete", "token_text": "src/never.py",
                   "new_text": None, "reason": "deleted in 89abcde"}]},
    ]})


def test_summary_check_mode(tmp_path: Path) -> None:
    workdir = _workdir(tmp_path, check=True)
    _planned(workdir)
    text = run(workdir)
    lines = text.splitlines()
    assert "Hunks: 2 provable; check mode: no edits made" in lines
    assert lines[-1] == "No branch created."
    # R66: check mode lists every planned edit in the commit-bullet grammar
    at = lines.index("Planned edits:")
    assert lines[at + 1 : at + 5] == [
        "- README.md:3 replace `src/old.py` -> `src/new.py` (renamed in 1234567)",
        "- README.md:5 delete `src/gone.py` (deleted in 89abcde)",
        "- README.md:11 delete `src/never.py` (deleted in 89abcde)",
        "",
    ]


def test_summary_without_check_has_no_planned_section(tmp_path: Path) -> None:
    assert "Planned edits:" not in run(_workdir(tmp_path))


def test_summary_check_mode_hunk_without_finding_is_exit_5(tmp_path: Path) -> None:
    workdir = _workdir(tmp_path, check=True)
    _planned(workdir, third="F999")
    with pytest.raises(StepError) as exc:
        run(workdir)
    assert exc.value.code == EXIT_MISSING


def test_summary_redacts_repository_strings(tmp_path: Path) -> None:
    workdir = _workdir(tmp_path)
    secret = 'password = "hunter2hunter2"'
    write_json(workdir / "tokens.json", {"docs": {}, "markers": [
        _marker(1, secret, None, None)], "skipped": []})
    text = run(workdir)
    assert "hunter2hunter2" not in text


def test_summary_missing_input_is_exit_5(tmp_path: Path) -> None:
    workdir = _workdir(tmp_path)
    (workdir / "findings.json").unlink()
    with pytest.raises(StepError) as exc:
        run(workdir)
    assert exc.value.code == EXIT_MISSING


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
                         "changed_files": ["a.py", "b.py"], "hunks": [{}, {}, {}],
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


def test_phase_a_redacts_repository_strings(tmp_path: Path) -> None:
    secret = "ghp_" + "a" * 36
    inv = {"docs": [f"{secret}.md"], "excluded": [], "skipped": []}
    assert secret not in render(_wd(tmp_path, **{"inventory.json": inv}))
