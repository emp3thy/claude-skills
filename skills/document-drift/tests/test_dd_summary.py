from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, StepError, write_json
from dd_summary import run

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


def test_summary_check_mode(tmp_path: Path) -> None:
    text = run(_workdir(tmp_path, check=True))
    lines = text.splitlines()
    assert "Hunks: 3 provable; check mode: no edits made" in lines
    assert lines[-1] == "No branch created."


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
