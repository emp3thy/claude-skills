from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

import dd_apply
import pytest
from dd_apply import main, run
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_extract import extract_doc
from dd_fixes import plan_hunks
from dd_inventory import DEFAULT_NEVER_EDIT

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
