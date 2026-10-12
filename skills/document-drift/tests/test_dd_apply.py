from __future__ import annotations

import copy
import os
import stat
import sys
from pathlib import Path
from typing import Any

import dd_apply
import pytest
from dd_apply import apply_edits, main
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_config import DEFAULTS
from dd_extract import run as extract_run
from dd_helpers import make_repo
from dd_inventory import run as inventory_run

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
    # the link is on line 11 of the edited doc and on line 10 at the starting HEAD
    assert result["link_updates"] == [{"doc": "README.md", "line": 10, "old": "setup",
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


def test_main_applies_the_edits(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    assert main([str(root), "--workdir", str(work)]) == EXIT_MISSING
    _inputs(work, [_agent_edit("u001-e01", DOC, 8, new="Keep this line.")],
            {"u001-e01": "accept"})
    assert main([str(root), "--workdir", str(work)]) == EXIT_OK
    assert read_json(work / "applied.json")["applied"] == ["u001-e01"]


def test_heading_links_match_as_the_resolver_reads_them(tmp_path: Path):
    readme = DOC.replace("(#setup)", "(#Setup)")
    guide = ("# Guide\n\n"
             "See [one](../README.md#Setup), [two](../README.md#user-content-setup)\n"
             "and [three](../README.md#set%75p).\n")
    root, work = _edit_repo(tmp_path, {"README.md": readme, "docs/guide.md": guide})
    _inputs(work, [_agent_edit("u001-e01", readme, 5, new="## Installation")],
            {"u001-e01": "accept"})
    result = apply_edits(root, work)
    assert result["applied"] == ["u001-e01"] and result["reverted"] == []
    assert _doc(root).endswith("Back to [the setup](#installation).\n")
    assert _doc(root, "docs/guide.md") == (
        "# Guide\n\n"
        "See [one](../README.md#installation), "
        "[two](../README.md#user-content-installation)\n"
        "and [three](../README.md#installation).\n")
    assert result["link_updates"] == [
        {"doc": "README.md", "line": 10, "old": "Setup", "new": "installation",
         "edit": "u001-e01"},
        {"doc": "docs/guide.md", "line": 3, "old": "Setup", "new": "installation",
         "edit": "u001-e01"},
        {"doc": "docs/guide.md", "line": 3, "old": "user-content-setup",
         "new": "user-content-installation", "edit": "u001-e01"},
        {"doc": "docs/guide.md", "line": 4, "old": "set%75p", "new": "installation",
         "edit": "u001-e01"},
    ]


def test_crlf_inside_new_leaves_no_stray_carriage_return(tmp_path: Path):
    text = DOC.replace("\n", "\r\n")
    root, work = _edit_repo(tmp_path, {"README.md": text})
    _inputs(work, [_agent_edit("u001-e01", text, 7, new="First step.\r\nSecond step.\r")],
            {"u001-e01": "accept"})
    assert apply_edits(root, work)["applied"] == ["u001-e01"]
    out = (root / "README.md").read_bytes()
    assert b"First step.\r\nSecond step.\r\nRemove this stale line.\r\n" in out
    assert b"\r\r" not in out
    assert out.count(b"\n") == out.count(b"\r\n")


def test_removing_the_last_lines_keeps_missing_trailing_newline(tmp_path: Path):
    text = DOC.rstrip("\n")
    root, work = _edit_repo(tmp_path, {"README.md": text})
    _inputs(work, [_agent_edit("u001-e01", text, 9, 10, new="", kind="remove")],
            {"u001-e01": "accept"})
    assert apply_edits(root, work)["applied"] == ["u001-e01"]
    assert _doc(root) == text.split("\n\nBack to")[0]
    assert _doc(root).endswith("Remove this stale line.")


def test_apply_edits_keeps_each_line_own_ending(tmp_path: Path):
    text = "# T\r\n\r\nSee `src/app.py` here.\n- a\r\n"
    root, work = _edit_repo(tmp_path, {"README.md": text})
    _inputs(work, [_agent_edit("u001-e01", text, 3, new="See `src/app.py` there.")],
            {"u001-e01": "accept"})
    assert apply_edits(root, work)["applied"] == ["u001-e01"]
    assert (root / "README.md").read_bytes() == b"# T\r\n\r\nSee `src/app.py` there.\n- a\r\n"


def test_read_only_doc_is_write_failed_and_leaves_no_temp_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 8, new="Keep this line.")],
            {"u001-e01": "accept"})
    doc = root / "README.md"
    os.chmod(doc, stat.S_IREAD)
    if sys.platform != "win32":  # replacing a read-only file only fails on Windows

        def refuse(src: object, dst: object) -> None:
            raise PermissionError(13, "read-only", str(dst))

        monkeypatch.setattr(dd_apply.os, "replace", refuse)
    try:
        result = apply_edits(root, work)
        assert result["applied"] == [] and result["docs"] == []
        assert result["reverted"] == [{"edit": "u001-e01", "reason": "write-failed"}]
        assert doc.read_bytes() == DOC.encode()
        assert list(root.glob("*.dd-tmp")) == []
    finally:
        os.chmod(doc, stat.S_IREAD | stat.S_IWRITE)


def test_missing_doc_reverts_its_edits_and_writes_nothing(tmp_path: Path):
    root, work = _edit_repo(tmp_path, {"README.md": DOC})
    _inputs(work, [_agent_edit("u001-e01", DOC, 8, new="Keep this line.")],
            {"u001-e01": "accept"})
    (root / "README.md").unlink()
    assert apply_edits(root, work) == {
        "applied": [], "reverted": [{"edit": "u001-e01", "reason": "old-mismatch"}],
        "docs": [], "link_updates": []}
    assert not (root / "README.md").exists()
