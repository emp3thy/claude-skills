from __future__ import annotations

import copy
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

import dd_apply
import pytest
from dd_apply import apply_edits, main, run
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_config import DEFAULTS
from dd_extract import extract_doc
from dd_extract import run as extract_run
from dd_fixes import plan_hunks
from dd_helpers import make_repo
from dd_inventory import DEFAULT_NEVER_EDIT
from dd_inventory import run as inventory_run

NEVER = re.compile(DEFAULT_NEVER_EDIT)

Cand = dict[str, Any]

FILES = ["README.md", "src/keep.py", "src/new.py", "src/main.py"]


def _cand(text: str, match: str, cls: str = "provable-delete", *, fid: str,
          replacement: str | None = None, context: str | None = None, nth: int = 0,
          doc: str = "README.md") -> Cand:
    """A finding built on a real extracted token (the nth whose text is ``match``)."""
    tokens, _ = extract_doc(doc, text, NEVER)
    found = [t for t in tokens if t["text"] == match
             and (context is None or t["context"] == context)]
    cand: Cand = dict(found[nth])
    deleted = cls != "provable-replace"
    cand.update(
        resolved_then=match, snapshot="a" * 40, existed_then=cls != "summary-only",
        outcome="deleted" if deleted else "unique",
        replacement=None if deleted else replacement, evidence_commit="a1b2c3d",
        evidence="deleted in a1b2c3d" if deleted else "renamed in a1b2c3d",
        human_kind=None, history_unavailable=False, id=fid,
    )
    cand["class"] = cls
    return cand


def _setup(tmp_path: Path, text: str | bytes, cands: list[Cand], *,
           files: list[str] | None = None, doc: str = "README.md",
           hunks: list[Cand] | None = None) -> tuple[Path, Path, list[Cand]]:
    """Write the doc, inventory.json, findings.json and hunks-provable.json; return hunks."""
    root, workdir = tmp_path / "repo", tmp_path / "work"
    raw = text.encode() if isinstance(text, str) else text
    (root / doc).parent.mkdir(parents=True, exist_ok=True)
    (root / doc).write_bytes(raw)
    if hunks is None:
        hunks, demoted = plan_hunks(raw.decode(), cands)
        assert demoted == []
        for n, h in enumerate(hunks, 1):
            h["id"] = f"H{n:03d}"
    write_json(workdir / "inventory.json", {
        "docs": [doc], "excluded": [], "skipped": [], "files": files or FILES,
        "never_edit_re": DEFAULT_NEVER_EDIT,
    })
    write_json(workdir / "findings.json", {
        "findings": cands, "history_unavailable": True,
        "honoured": [{"doc": doc, "line": 1, "col": 0, "kind": "path", "text": "x",
                      "reason": "planned"}],
    })
    write_json(workdir / "hunks-provable.json", {"hunks": hunks})
    return root, workdir, hunks


def _findings(workdir: Path) -> dict[str, Cand]:
    return {f["id"]: f for f in read_json(workdir / "findings.json")["findings"]}


LIST_DOC = (
    "# Title\n"
    "\n"
    "- `src/gone.py` old module\n"
    "- `src/keep.py` kept\n"
    "\n"
    "See `src/old.py` here.\n"
)


def _list_cands(text: str) -> list[Cand]:
    return [
        _cand(text, "src/gone.py", fid="F001"),
        _cand(text, "src/old.py", "provable-replace", replacement="src/new.py", fid="F002"),
    ]


# -- applying ----------------------------------------------------------------------------------


def test_apply_replace_and_delete_bottom_up(tmp_path: Path):
    root, workdir, hunks = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    assert [(h["verb"], h["line_start"]) for h in hunks] == [("delete", 3), ("replace", 6)]
    result = run(root, workdir)
    assert (root / "README.md").read_bytes().decode() == (
        "# Title\n"
        "\n"
        "- `src/keep.py` kept\n"
        "\n"
        "See `src/new.py` here.\n"
    )
    applied = read_json(workdir / "applied.json")
    assert applied == result
    assert applied == {"applied": ["H001", "H002"], "reverted": [], "docs": ["README.md"]}
    assert not (root / "README.md.dd-tmp").exists()
    findings = read_json(workdir / "findings.json")
    assert findings["history_unavailable"] is True
    assert findings["honoured"][0]["reason"] == "planned"
    assert {f["id"]: f["class"] for f in findings["findings"]} == {
        "F001": "provable-delete", "F002": "provable-replace"}


def test_apply_preserves_crlf(tmp_path: Path):
    text = LIST_DOC.replace("\n", "\r\n")
    root, workdir, _ = _setup(tmp_path, text, _list_cands(text))
    run(root, workdir)
    out = (root / "README.md").read_bytes()
    assert out == (
        b"# Title\r\n"
        b"\r\n"
        b"- `src/keep.py` kept\r\n"
        b"\r\n"
        b"See `src/new.py` here.\r\n"
    )
    assert out.count(b"\n") == out.count(b"\r\n")


def test_apply_preserves_missing_trailing_newline(tmp_path: Path):
    text = LIST_DOC.rstrip("\n")
    root, workdir, _ = _setup(tmp_path, text, _list_cands(text))
    run(root, workdir)
    assert (root / "README.md").read_bytes() == (
        b"# Title\n\n- `src/keep.py` kept\n\nSee `src/new.py` here."
    )


def test_deleting_the_last_line_keeps_missing_trailing_newline(tmp_path: Path):
    text = "- `src/keep.py`\r\n- `src/gone.py`"
    root, workdir, hunks = _setup(tmp_path, text, [_cand(text, "src/gone.py", fid="F001")])
    assert hunks[0]["line_start"] == 2
    run(root, workdir)
    assert (root / "README.md").read_bytes() == b"- `src/keep.py`"


def test_mixed_endings_keep_each_line_own_ending(tmp_path: Path):
    text = "# T\r\n\r\nSee `src/old.py` here.\n- a\r\n"
    cand = _cand(text, "src/old.py", "provable-replace", replacement="src/new.py", fid="F001")
    root, workdir, _ = _setup(tmp_path, text, [cand])
    run(root, workdir)
    assert (root / "README.md").read_bytes() == b"# T\r\n\r\nSee `src/new.py` here.\n- a\r\n"


def test_before_mismatch_reverts(tmp_path: Path):
    root, workdir, _ = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    changed = LIST_DOC.replace("See `src/old.py` here.", "See `src/old.py` there.")
    (root / "README.md").write_bytes(changed.encode())
    result = run(root, workdir)
    assert result == {"applied": ["H001"],
                      "reverted": [{"hunk": "H002", "reason": "before-mismatch"}],
                      "docs": ["README.md"]}
    assert (root / "README.md").read_bytes().decode() == (
        "# Title\n\n- `src/keep.py` kept\n\nSee `src/old.py` there.\n"
    )
    found = _findings(workdir)
    assert found["F002"]["class"] == "human"
    assert found["F002"]["human_kind"] == "recheck-failed"
    assert found["F002"]["recheck_reason"] == "before-mismatch"
    assert found["F002"]["replacement"] == "src/new.py"  # other fields preserved
    assert found["F001"]["class"] == "provable-delete"
    assert "recheck_reason" not in found["F001"]


def test_failed_write_reverts_the_doc_hunks(tmp_path: Path):
    root, workdir, _ = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    (root / "README.md.dd-tmp").mkdir()  # the temporary file cannot be written
    result = run(root, workdir)
    assert result == {"applied": [], "docs": [], "reverted": [
        {"hunk": "H001", "reason": "write-failed"},
        {"hunk": "H002", "reason": "write-failed"},
    ]}
    assert (root / "README.md").read_bytes() == LIST_DOC.encode()
    assert _findings(workdir)["F001"]["recheck_reason"] == "write-failed"


def test_read_only_doc_is_write_failed_and_leaves_no_temp_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, workdir, _ = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    doc = root / "README.md"
    os.chmod(doc, stat.S_IREAD)
    if sys.platform != "win32":  # replacing a read-only file only fails on Windows

        def refuse(src: object, dst: object) -> None:
            raise PermissionError(13, "read-only", str(dst))

        monkeypatch.setattr(dd_apply.os, "replace", refuse)
    try:
        result = run(root, workdir)
        assert result["applied"] == [] and result["docs"] == []
        assert result["reverted"] == [{"hunk": "H001", "reason": "write-failed"},
                                      {"hunk": "H002", "reason": "write-failed"}]
        assert doc.read_bytes() == LIST_DOC.encode()
        assert list(root.glob("*.dd-tmp")) == []
    finally:
        os.chmod(doc, stat.S_IREAD | stat.S_IWRITE)


def test_missing_doc_reverts_every_hunk_and_writes_nothing(tmp_path: Path):
    root, workdir, _ = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    (root / "README.md").unlink()
    result = run(root, workdir)
    assert result == {"applied": [], "docs": [], "reverted": [
        {"hunk": "H001", "reason": "before-mismatch"},
        {"hunk": "H002", "reason": "before-mismatch"},
    ]}
    assert not (root / "README.md").exists()


# -- re-check ----------------------------------------------------------------------------------


def test_replacement_that_does_not_resolve_is_reverted_and_marked_recheck_failed(
        tmp_path: Path):
    text = LIST_DOC
    cands = [
        _cand(text, "src/gone.py", fid="F001"),
        _cand(text, "src/old.py", "provable-replace", replacement="src/missing.py",
              fid="F002"),
    ]
    root, workdir, _ = _setup(tmp_path, text, cands)
    result = run(root, workdir)
    assert result == {"applied": ["H001"],
                      "reverted": [{"hunk": "H002", "reason": "recheck-still-unresolved"}],
                      "docs": ["README.md"]}
    assert "See `src/old.py` here." in (root / "README.md").read_text()
    found = _findings(workdir)
    assert (found["F002"]["class"], found["F002"]["human_kind"]) == ("human", "recheck-failed")
    assert found["F002"]["recheck_reason"] == "recheck-still-unresolved"


def test_whole_doc_untouched_when_every_hunk_reverts(tmp_path: Path):
    text = "See `src/old.py` here.\r\n"
    cand = _cand(text, "src/old.py", "provable-replace", replacement="src/missing.py",
                 fid="F001")
    root, workdir, _ = _setup(tmp_path, text, [cand])
    before = (root / "README.md").stat().st_mtime_ns
    result = run(root, workdir)
    assert result["applied"] == [] and result["docs"] == []
    assert (root / "README.md").read_bytes() == text.encode()
    assert (root / "README.md").stat().st_mtime_ns == before


def test_also_replacement_that_does_not_resolve_reverts_the_hunk(tmp_path: Path):
    text = "See `src/a.py` and `src/b.py`.\n"
    cands = [
        _cand(text, "src/a.py", "provable-replace", replacement="src/new.py", fid="F001"),
        _cand(text, "src/b.py", "provable-replace", replacement="src/nowhere.py", fid="F002"),
    ]
    root, workdir, hunks = _setup(tmp_path, text, cands)
    assert len(hunks) == 1 and [a["finding_id"] for a in hunks[0]["also"]] == ["F002"]
    result = run(root, workdir)
    assert result["reverted"] == [{"hunk": "H001", "reason": "recheck-still-unresolved"}]
    assert (root / "README.md").read_bytes() == text.encode()
    found = _findings(workdir)
    for fid in ("F001", "F002"):
        assert (found[fid]["class"], found[fid]["human_kind"]) == ("human", "recheck-failed")
        assert found[fid]["recheck_reason"] == "recheck-still-unresolved"


def test_also_replacements_that_resolve_are_kept(tmp_path: Path):
    text = "- [`src/app.py`](src/app.py) x\n- other\n"
    cands = [
        _cand(text, "src/app.py", "provable-replace", replacement="src/main.py",
              context="inline-code", fid="F001"),
        _cand(text, "src/app.py", "provable-replace", replacement="src/main.py",
              context="link", fid="F002"),
    ]
    root, workdir, _ = _setup(tmp_path, text, cands)
    assert run(root, workdir)["applied"] == ["H001"]
    assert (root / "README.md").read_text() == "- [`src/main.py`](src/main.py) x\n- other\n"


def test_edit_that_introduces_a_new_unresolved_token_is_reverted(tmp_path: Path):
    text = "See `src/old.py` here.\n"
    cand = _cand(text, "src/old.py", "provable-replace", replacement="src/new.py", fid="F001")
    hunk = {
        "id": "H001", "finding_id": "F001", "doc": "README.md", "line_start": 1,
        "line_end": 1, "before": ["See `src/old.py` here."],
        "after": ["See `src/new.py` and `src/bogus.py` here."], "verb": "replace",
        "token_kind": "path", "token_text": "src/old.py", "new_text": "src/new.py",
        "reason": "renamed in a1b2c3d", "also": [],
    }
    root, workdir, _ = _setup(tmp_path, text, [cand], hunks=[hunk])
    result = run(root, workdir)
    assert result["reverted"] == [{"hunk": "H001", "reason": "recheck-new-finding"}]
    assert (root / "README.md").read_text() == text
    assert _findings(workdir)["F001"]["recheck_reason"] == "recheck-new-finding"


def test_delete_that_leaves_its_own_token_firing_is_reverted(tmp_path: Path):
    text = "- `src/gone.py`\n- `src/keep.py`\n"
    cand = _cand(text, "src/gone.py", fid="F001")
    hunk = {
        "id": "H001", "finding_id": "F001", "doc": "README.md", "line_start": 2,
        "line_end": 2, "before": ["- `src/keep.py`"], "after": [], "verb": "delete",
        "token_kind": "path", "token_text": "src/gone.py", "new_text": None,
        "reason": "deleted in a1b2c3d", "also": [],
    }
    root, workdir, _ = _setup(tmp_path, text, [cand], hunks=[hunk])
    result = run(root, workdir)
    assert result["reverted"] == [{"hunk": "H001", "reason": "recheck-still-unresolved"}]
    assert (root / "README.md").read_text() == text


def test_delete_that_exposes_no_new_finding_is_kept(tmp_path: Path):
    text = (
        "Intro `src/broken.py` stays broken.\n"
        "\n"
        "- `src/gone.py` and `src/gone2.py`\n"
        "- `src/keep.py`\n"
    )
    cands = [
        _cand(text, "src/gone.py", fid="F001"),
        _cand(text, "src/gone2.py", fid="F002"),
    ]
    root, workdir, hunks = _setup(tmp_path, text, cands)
    assert [a["finding_id"] for a in hunks[0]["also"]] == ["F002"]
    result = run(root, workdir)
    assert result == {"applied": ["H001"], "reverted": [], "docs": ["README.md"]}
    assert (root / "README.md").read_text() == (
        "Intro `src/broken.py` stays broken.\n\n- `src/keep.py`\n"
    )


def test_marker_ignored_token_does_not_count_as_new(tmp_path: Path):
    text = "<!-- drift-ignore-next-line: planned -->\nSee `src/old.py` here.\n"
    cand = _cand(text, "src/old.py", "provable-replace", replacement="src/new.py", fid="F001")
    hunk = {
        "id": "H001", "finding_id": "F001", "doc": "README.md", "line_start": 2,
        "line_end": 2, "before": ["See `src/old.py` here."],
        "after": ["See `src/new.py` and `src/planned.py` here."], "verb": "replace",
        "token_kind": "path", "token_text": "src/old.py", "new_text": "src/new.py",
        "reason": "renamed in a1b2c3d", "also": [],
    }
    root, workdir, _ = _setup(tmp_path, text, [cand], hunks=[hunk])
    assert run(root, workdir)["applied"] == ["H001"]
    assert "`src/planned.py`" in (root / "README.md").read_text()


# -- superseded findings (ruling R43) ----------------------------------------------------------


def test_human_and_summary_findings_inside_applied_delete_are_superseded(tmp_path: Path):
    text = (
        "- `src/gone.py` see `lib/never.py`\n"
        "- `src/keep.py`\n"
        "\n"
        "Later `lib/other.py` and `src/vague.py`.\n"
    )
    inside = _cand(text, "lib/never.py", "summary-only", fid="F002")
    outside = _cand(text, "lib/other.py", "summary-only", fid="F003")
    human = _cand(text, "src/vague.py", "human", fid="F004")
    human["human_kind"] = "ambiguous-rename"
    cands = [_cand(text, "src/gone.py", fid="F001"), inside, outside, human]
    root, workdir, hunks = _setup(tmp_path, text, cands)
    assert [(h["id"], h["verb"]) for h in hunks] == [("H001", "delete")]
    run(root, workdir)
    found = _findings(workdir)
    assert found["F002"]["superseded_by"] == "H001"
    assert "superseded_by" not in found["F003"]
    assert "superseded_by" not in found["F004"]
    assert "superseded_by" not in found["F001"]


def test_no_superseded_by_when_the_delete_is_reverted(tmp_path: Path):
    text = "- `src/gone.py` see `lib/never.py`\n- `src/keep.py`\n"
    inside = _cand(text, "lib/never.py", "summary-only", fid="F002")
    root, workdir, _ = _setup(tmp_path, text, [_cand(text, "src/gone.py", fid="F001"), inside])
    (root / "README.md").write_bytes(b"- `src/gone.py` see it\n- `src/keep.py`\n")
    assert run(root, workdir)["reverted"] == [{"hunk": "H001", "reason": "before-mismatch"}]
    assert "superseded_by" not in _findings(workdir)["F002"]


# -- main --------------------------------------------------------------------------------------


def test_main_missing_inputs_exits_missing(tmp_path: Path):
    assert main([str(tmp_path), "--workdir", str(tmp_path / "work")]) == EXIT_MISSING


def test_main_ok(tmp_path: Path):
    root, workdir, _ = _setup(tmp_path, LIST_DOC, _list_cands(LIST_DOC))
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_OK
    assert read_json(workdir / "applied.json")["applied"] == ["H001", "H002"]


# -- agent edits (spec 9.3) --------------------------------------------------------------------

APP = "def main():\n    return 0\n"
DOC = (
    "# Project\n"                                # 1
    "\n"                                         # 2
    "See `src/app.py` for the entry point.\n"    # 3
    "\n"                                         # 4
    "## Setup\n"                                 # 5
    "\n"                                         # 6
    "Run the old setup step.\n"                  # 7
    "Remove this stale line.\n"                  # 8
    "\n"                                         # 9
    "Back to [the setup](#setup).\n"             # 10
)


def _edit_repo(tmp_path: Path, docs: dict[str, str]) -> tuple[Path, Path]:
    """A one-commit repo holding ``docs`` and ``src/app.py``, with inventory and tokens."""
    root = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": {"src/app.py": APP, **docs}}])
    work = tmp_path / "work"
    inventory_run(root, work, copy.deepcopy(DEFAULTS))
    extract_run(root, work)
    return root, work


def _lines(text: str, start: int, end: int) -> str:
    return "\n".join(text.replace("\r\n", "\n").split("\n")[start - 1:end])


def _agent_edit(eid: str, text: str, start: int, end: int | None = None, new: str = "x", *,
                doc: str = "README.md", source: str = "review", status: str = "kept",
                kind: str = "correct", old: str | None = None) -> dict[str, Any]:
    end = start if end is None else end
    return {"id": eid, "doc": doc, "start_line": start, "end_line": end,
            "old": _lines(text, start, end) if old is None else old, "new": new, "type": kind,
            "claim": f"claim {eid}", "evidence": ["src/app.py:1"], "subject": None,
            "source": source, "status": status, "check": None, "human_kind": None,
            "reason": None}


def _inputs(work: Path, edits: list[dict[str, Any]], verdicts: dict[str, str],
            unverified: tuple[str, ...] = ()) -> None:
    write_json(work / "edits.json", {"edits": edits, "human": [], "questions": []})
    write_json(work / "verdicts.json", {
        "verdicts": {eid: {"verdict": v, "reason": f"because {v}"} for eid, v in verdicts.items()},
        "unverified": list(unverified)})


def _doc(root: Path, doc: str = "README.md") -> str:
    return (root / doc).read_bytes().decode("utf-8")


def test_apply_accepted_edits_bottom_up(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    edits = [
        # the upper edit grows by a line: applied first, it would shift the lower one
        _agent_edit("u001-e01", DOC, 3, new="See `src/app.py` for the entry point.\n"
                    "It returns the exit code."),
        _agent_edit("u001-e02", DOC, 7, 8, new="Run `src/app.py` once."),
        _agent_edit("g001-e01", DOC, 1, new="# The project", source="gap", kind="add"),
    ]
    _inputs(work, edits, {"u001-e01": "accept", "u001-e02": "accept", "g001-e01": "accept"})
    result = apply_edits(root, work)
    assert _doc(root) == (
        "# The project\n"
        "\n"
        "See `src/app.py` for the entry point.\n"
        "It returns the exit code.\n"
        "\n"
        "## Setup\n"
        "\n"
        "Run `src/app.py` once.\n"
        "\n"
        "Back to [the setup](#setup).\n"
    )
    assert result == read_json(work / "applied.json")
    assert result == {"applied": ["g001-e01", "u001-e01", "u001-e02"], "reverted": [],
                      "docs": ["README.md"], "link_updates": []}


def test_empty_new_removes_the_lines(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 8, 9, new="", kind="remove")],
            {"u001-e01": "accept"})
    assert apply_edits(root, work)["applied"] == ["u001-e01"]
    assert _doc(root) == DOC.replace("Remove this stale line.\n\n", "")


def test_old_mismatch_reverts_only_that_edit(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    edits = [_agent_edit("u001-e01", DOC, 7, new="Run it.", old="Run the new setup step."),
             _agent_edit("u001-e02", DOC, 8, new="Keep this line.")]
    _inputs(work, edits, {"u001-e01": "accept", "u001-e02": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e02"]
    assert result["reverted"] == [{"edit": "u001-e01", "reason": "old-mismatch"}]
    assert _doc(root) == DOC.replace("Remove this stale line.", "Keep this line.")


def test_rejected_and_unverified_edits_not_applied(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    edits = [
        _agent_edit("u001-e01", DOC, 1, new="# Rejected"),
        _agent_edit("u001-e02", DOC, 3, new="Unsure line."),
        _agent_edit("u001-e03", DOC, 7, new="Unverified line."),
        _agent_edit("u001-e04", DOC, 8, new="Dropped line.", status="dropped"),
        _agent_edit("u001-e05", DOC, 9, new="Human line.", status="human"),
        _agent_edit("g001-e01", DOC, 10, new="Back to [the setup](#setup), accepted.",
                    source="gap"),
    ]
    _inputs(work, edits, {"u001-e01": "reject", "u001-e02": "unsure", "u001-e04": "accept",
                          "u001-e05": "accept", "g001-e01": "accept"}, unverified=("u001-e03",))
    result = apply_edits(root, work)
    assert result["applied"] == ["g001-e01"]
    assert result["reverted"] == []
    assert _doc(root) == DOC.replace("(#setup).", "(#setup), accepted.")


def test_notice_edits_apply_without_verdict(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    notice = ("<!-- drift-unverified: 1st notice, run 2026-10-12-a3f1, block 0123abcd. "
              "This describes the code but names nothing in it. -->")
    edits = [
        _agent_edit("n001", DOC, 7, new=notice + "\nRun the old setup step.", source="notice",
                    kind="notice"),
        _agent_edit("n002", DOC, 8, new="", source="notice", kind="unverified",
                    status="dropped"),
        _agent_edit("u001-e01", DOC, 3, new="No verdict, not applied."),
    ]
    _inputs(work, edits, {})
    result = apply_edits(root, work)
    assert result["applied"] == ["n001"]
    assert _doc(root) == DOC.replace("Run the old", notice + "\nRun the old")


def test_apply_edits_keeps_crlf(tmp_path: Path):
    text = DOC.replace("\n", "\r\n")
    root, work = _edit_repo(tmp_path, {"README.md": text})
    edits = [
        _agent_edit("u001-e01", text, 3, new="See `src/app.py` for the entry point.\n"
                    "It returns the exit code."),
        _agent_edit("u001-e02", text, 7, 9, new="", kind="remove"),
    ]
    _inputs(work, edits, {"u001-e01": "accept", "u001-e02": "accept"})
    assert apply_edits(root, work)["applied"] == ["u001-e01", "u001-e02"]
    out = (root / "README.md").read_bytes()
    assert out == (
        b"# Project\r\n"
        b"\r\n"
        b"See `src/app.py` for the entry point.\r\n"
        b"It returns the exit code.\r\n"
        b"\r\n"
        b"## Setup\r\n"
        b"\r\n"
        b"Back to [the setup](#setup).\r\n"
    )
    assert out.count(b"\n") == out.count(b"\r\n")


def test_recheck_reverts_edit_that_breaks_a_path(tmp_path: Path):
    text = DOC + "Old notes live in `src/gone.py`.\n"  # line 11: unresolved before any edit
    root, work = _edit_repo(tmp_path, {"README.md": text})
    edits = [
        _agent_edit("u001-e01", text, 3, new="See `src/missing.py` for the entry point."),
        _agent_edit("u001-e02", text, 10, new="Back to [the setup](#nowhere)."),
        _agent_edit("u001-e03", text, 11, new="Old notes live in `src/also-gone.py`."),
        _agent_edit("u001-e04", text, 8, new="Run `src/app.py` to start."),
    ]
    _inputs(work, edits, {e["id"]: "accept" for e in edits})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e04"]
    assert result["reverted"] == [{"edit": "u001-e01", "reason": "recheck-failed"},
                                  {"edit": "u001-e02", "reason": "recheck-failed"},
                                  {"edit": "u001-e03", "reason": "recheck-failed"}]
    assert _doc(root) == text.replace("Remove this stale line.", "Run `src/app.py` to start.")


def test_whole_doc_untouched_when_every_edit_reverts(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 3, new="See `src/missing.py`.")],
            {"u001-e01": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == [] and result["docs"] == []
    assert _doc(root) == DOC
    assert not (root / "README.md.dd-tmp").exists()


GUIDE_DOC = (
    "# Guide\n"
    "\n"
    "Read [setup](../README.md#setup) first.\n"
    "Then [the project](../README.md#project) and [local](#guide).\n"
    "Also [setup again](../README.md#setup).\n"
)
OTHER_DOC = "# Other\n\n## Setup\n\nSee [setup](#setup) here.\n"


def test_heading_edit_updates_links_in_other_docs(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC, "docs/guide.md": GUIDE_DOC,
                                       "docs/other.md": OTHER_DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 5, new="## Installation")],
            {"u001-e01": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01"] and result["reverted"] == []
    assert _doc(root) == DOC.replace("## Setup", "## Installation").replace(
        "(#setup)", "(#installation)")
    assert _doc(root, "docs/guide.md") == GUIDE_DOC.replace("#setup", "#installation")
    assert _doc(root, "docs/other.md") == OTHER_DOC  # its own Setup heading, not README's
    assert result["docs"] == ["README.md", "docs/guide.md"]
    assert result["link_updates"] == [
        {"doc": "README.md", "line": 10, "old": "setup", "new": "installation",
         "edit": "u001-e01"},
        {"doc": "docs/guide.md", "line": 3, "old": "setup", "new": "installation",
         "edit": "u001-e01"},
        {"doc": "docs/guide.md", "line": 5, "old": "setup", "new": "installation",
         "edit": "u001-e01"},
    ]


def test_heading_link_lines_follow_the_edited_doc(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    edits = [_agent_edit("u001-e01", DOC, 5, new="## Installation"),
             _agent_edit("u001-e02", DOC, 3, new="One.\nTwo.")]
    _inputs(work, edits, {"u001-e01": "accept", "u001-e02": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01", "u001-e02"]
    assert result["link_updates"] == [{"doc": "README.md", "line": 11, "old": "setup",
                                       "new": "installation", "edit": "u001-e01"}]
    assert _doc(root).endswith("Back to [the setup](#installation).\n")


def test_duplicate_heading_slug_links_are_left_to_the_owner(tmp_path: Path):
    readme = "# Project\n\n## Usage\n\nOne.\n\n## Usage\n\nTwo.\n"
    guide = "# Guide\n\nSee [usage](../README.md#usage-1).\n"
    root, work = _edit_repo(tmp_path, {"README.md": readme, "docs/guide.md": guide})
    _inputs(work, [_agent_edit("u001-e01", readme, 7, new="## Advanced usage")],
            {"u001-e01": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01"]
    assert result["link_updates"] == [{"doc": "docs/guide.md", "line": 3, "old": "usage-1",
                                       "new": None, "edit": "u001-e01"}]
    assert result["docs"] == ["README.md"]
    assert _doc(root, "docs/guide.md") == guide


def test_doc_written_once_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, work = _edit_repo(tmp_path, {"README.md": DOC, "docs/guide.md": GUIDE_DOC})
    edits = [_agent_edit("u001-e01", DOC, 5, new="## Installation"),
             _agent_edit("u001-e02", DOC, 8, new="Keep this line."),
             _agent_edit("u001-e03", DOC, 1, new="# The project")]
    _inputs(work, edits, {e["id"]: "accept" for e in edits})
    writes: list[str] = []
    real = dd_apply._write_atomic

    def spy(path: Path, text: str) -> None:
        writes.append(path.relative_to(root).as_posix())
        real(path, text)

    monkeypatch.setattr(dd_apply, "_write_atomic", spy)
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01", "u001-e02", "u001-e03"]
    assert sorted(writes) == ["README.md", "docs/guide.md"]
    guide = _doc(root, "docs/guide.md")
    assert "(../README.md#the-project)" in guide and "(../README.md#installation)" in guide
    assert "(#installation)" in _doc(root)
    assert not list(root.rglob("*.dd-tmp"))


def test_failed_write_drops_that_doc_and_its_link_updates(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch):
    root, work = _edit_repo(tmp_path, {"README.md": DOC, "docs/guide.md": GUIDE_DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 5, new="## Installation")],
            {"u001-e01": "accept"})
    real = dd_apply._write_atomic

    def failing(path: Path, text: str) -> None:
        if path.name == "guide.md":
            raise OSError("disk full")
        real(path, text)

    monkeypatch.setattr(dd_apply, "_write_atomic", failing)
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01"]
    assert result["docs"] == ["README.md"]
    assert [u["doc"] for u in result["link_updates"]] == ["README.md"]
    assert _doc(root, "docs/guide.md") == GUIDE_DOC


def test_main_edits_path(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    assert main([str(root), "--workdir", str(work), "--edits"]) == EXIT_MISSING
    _inputs(work, [_agent_edit("u001-e01", DOC, 8, new="Keep this line.")],
            {"u001-e01": "accept"})
    assert main([str(root), "--workdir", str(work), "--edits"]) == EXIT_OK
    assert read_json(work / "applied.json")["applied"] == ["u001-e01"]
