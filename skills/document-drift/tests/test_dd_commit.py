from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_commit import render_human, render_message, run
from dd_common import EXIT_COMMIT, StepError, read_json, write_json

BASE = "a" * 40
GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _f(fid: str, doc: str, line: int, col: int, text: str, **extra: Any) -> dict[str, Any]:
    return {"id": fid, "doc": doc, "line": line, "col": col, "text": text, "class": "provable",
            "human_kind": None, "evidence": "", **extra}


def _fixture() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings = [
        _f("F001", "docs/b.md", 3, 4, "src/old.py"),
        _f("F002", "README.md", 9, 0, "src/gone.py"),
        _f("F003", "README.md", 2, 5, "src/dead.py"),
        _f("F004", "README.md", 20, 0, "src/big.py", **{"class": "human",
           "human_kind": "large-deletion", "block": {"kind": "table_row"},
           "evidence": "deleted in 1234567"}),
        _f("F005", "README.md", 5, 0, "src/gen.py", **{"class": "human",
           "human_kind": "never-edit-section", "heading_path": ["Docs", "Changelog"]}),
        _f("F006", "README.md", 7, 0, "src/x.py", **{"class": "human",
           "human_kind": "prose-mention", "superseded_by": "H001"}),
        _f("F007", "README.md", 8, 0, "src/y.py", **{"class": "summary-only"}),
    ]
    hunks = [
        {"id": "H001", "finding_id": "F001", "doc": "docs/b.md", "line_start": 3,
         "verb": "replace", "token_text": "src/old.py", "new_text": "src/new.py",
         "reason": "renamed in a1b2c3d", "also": []},
        {"id": "H002", "finding_id": "F002", "doc": "README.md", "line_start": 9, "verb": "delete",
         "token_text": "src/gone.py", "new_text": None, "reason": "deleted in 7654321",
         "also": [{"finding_id": "F003", "verb": "unlink", "token_text": "src/dead.py",
                   "new_text": None, "reason": "removed in 1111111"}]},
    ]
    return findings, hunks


GOLDEN = (
    "docs(drift): provable fixes\n"
    "\n"
    "Drift-Run: abc123def456\n"
    f"Drift-Base: {BASE}\n"
    "Drift-Scope: all\n"
    "\n"
    "- README.md:2 unlink `src/dead.py` (removed in 1111111)\n"
    "- README.md:9 delete `src/gone.py` (deleted in 7654321)\n"
    "- docs/b.md:3 replace `src/old.py` -> `src/new.py` (renamed in a1b2c3d)\n"
    "\n"
    "Needs a human decision:\n"
    "- README.md:5 [never-edit-section] `src/gen.py` no longer exists, in a section headed "
    "'Changelog'\n"
    "  evidence: none\n"
    "- README.md:20 [large-deletion] `src/big.py` no longer exists and removing it would "
    "remove a table row\n"
    "  evidence: deleted in 1234567\n"
    "\n"
    "Co-Authored-By: Someone <s@example.com>\n"
)


def test_render_message_exact_grammar() -> None:
    findings, hunks = _fixture()
    msg = render_message(findings, hunks, ["H001", "H002"], run_id="abc123def456", base=BASE,
                         scope="all", trailers=["Co-Authored-By: Someone <s@example.com>"])
    assert msg == GOLDEN
    assert GOLDEN.count("\n") == 17
    assert "\\" not in GOLDEN


def test_human_section_omitted_when_empty() -> None:
    findings, hunks = _fixture()
    humans = [f for f in findings if f["class"] != "human"]
    msg = render_message(humans, hunks, ["H001"], run_id="r", base=BASE, scope="base:main",
                         trailers=[])
    assert "Needs a human decision" not in msg
    assert msg.endswith("(renamed in a1b2c3d)\n")
    assert "Drift-Scope: base:main" in msg
    assert render_human(humans) == ""


def test_render_human_statements() -> None:
    fs = [
        _f("F1", "a.md", 1, 0, "p", **{"class": "human", "human_kind": "ambiguous-rename"}),
        _f("F2", "a.md", 2, 0, "p", **{"class": "human", "human_kind": "prose-mention"}),
        _f("F3", "a.md", 3, 0, "p", **{"class": "human", "human_kind": "generated-region"}),
        _f("F4", "a.md", 4, 0, "p", **{"class": "human", "human_kind": "recheck-failed",
           "recheck_reason": "before-mismatch"}),
    ]
    out = render_human(fs)
    assert "`p` was renamed or moved and no single new name is provable" in out
    assert "`p` no longer exists and is mentioned in running prose" in out
    assert "inside a generated region; regenerate it" in out
    assert "the proposed edit for `p` did not pass the re-check (before-mismatch)" in out


@pytest.mark.parametrize(("block", "unit"), [
    ("list_item", "a list item"), ("table_row", "a table row"), ("fence", "a fence line"),
    ("tree", "a tree line"), ("paragraph", "a paragraph"), ("heading", "a heading"),
])
def test_large_deletion_names_its_unit_in_words(block: str, unit: str) -> None:
    # R66: the statement says what would go, not the raw block kind
    out = render_human([_f("F1", "a.md", 1, 0, "p", **{"class": "human",
                        "human_kind": "large-deletion", "block": {"kind": block}})])
    assert f"`p` no longer exists and removing it would remove {unit}\n" in out
    assert block not in out.replace(unit, "")


def test_heading_reference_statement() -> None:
    # R62: a token in a heading is never rewritten; links to the heading would break
    out = render_human([_f("F1", "docs/api.md", 3, 3, "src/handlers.py", **{
        "class": "human", "human_kind": "heading-reference", "evidence": "renamed in a1b2c3d"})])
    assert out == (
        "Needs a human decision:\n"
        "- docs/api.md:3 [heading-reference] `src/handlers.py` is named in a heading; "
        "changing it would break links to that heading\n"
        "  evidence: renamed in a1b2c3d\n"
    )


def _hunk(hid: str, fid: str, verb: str, new_text: str | None = None,
          also: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": hid, "finding_id": fid, "doc": "a.md", "line_start": 1, "verb": verb,
            "token_text": "", "new_text": new_text, "reason": "why", "also": also or []}


@pytest.mark.parametrize(("tool", "shown"), [
    ("make", "make lint"), ("npm", "npm run lint"), ("yarn", "yarn lint"),
    ("pnpm", "pnpm lint"), ("just", "just lint"), ("task", "task lint"),
])
def test_script_findings_display_as_their_invocation(tool: str, shown: str) -> None:
    # R51: a script name alone (`lint`) does not tell the reader which command was removed
    findings = [
        _f("F1", "a.md", 1, 0, "lint", kind="script", script_tool=tool),
        _f("F2", "a.md", 2, 0, "lint", kind="script", script_tool=tool,
           **{"class": "human", "human_kind": "large-deletion", "block": {"kind": "fence"}}),
    ]
    msg = render_message(findings, [_hunk("H1", "F1", "delete")], ["H1"], run_id="r",
                         base=BASE, scope="all", trailers=[])
    assert f"- a.md:1 delete `{shown}` (why)\n" in msg
    assert (f"- a.md:2 [large-deletion] `{shown}` no longer exists and removing it would "
            "remove a fence line\n") in msg


def test_script_finding_in_an_also_entry_displays_as_its_invocation() -> None:
    findings = [_f("F1", "a.md", 1, 0, "src/x.py", kind="path"),
                _f("F2", "a.md", 1, 9, "e2e", kind="script", script_tool="npm")]
    also = [{"finding_id": "F2", "verb": "delete", "token_text": "e2e", "new_text": None,
             "reason": "removed in 1234567"}]
    msg = render_message(findings, [_hunk("H1", "F1", "delete", also=also)], ["H1"],
                         run_id="r", base=BASE, scope="all", trailers=[])
    assert "- a.md:1 delete `src/x.py` (why)\n- a.md:1 delete `npm run e2e` (removed in" in msg


@pytest.mark.parametrize(("text", "new_text", "shown"), [
    ("src/svc/tasks/scheduler.py", "runner.py", "src/svc/tasks/runner.py"),
    ("src/components/", "widgets/", "src/widgets/"),
    ("top.py", "main.py", "main.py"),
])
def test_tree_replace_bullet_shows_full_paths(text: str, new_text: str, shown: str) -> None:
    # R51: the hunk replaces only the entry's own segment; the bullet shows both full paths
    findings = [_f("F1", "a.md", 1, 0, text, kind="tree")]
    msg = render_message(findings, [_hunk("H1", "F1", "replace", new_text)], ["H1"],
                         run_id="r", base=BASE, scope="all", trailers=[])
    assert f"- a.md:1 replace `{text}` -> `{shown}` (why)\n" in msg


def test_path_and_unknown_tool_findings_display_their_text() -> None:
    findings = [_f("F1", "a.md", 1, 0, "src/old.py", kind="path"),
                _f("F2", "a.md", 2, 0, "build", kind="script", script_tool=None)]
    hunks = [_hunk("H1", "F1", "replace", "src/new.py"), _hunk("H2", "F2", "delete")]
    msg = render_message(findings, hunks, ["H1", "H2"], run_id="r", base=BASE, scope="all",
                         trailers=[])
    assert "- a.md:1 replace `src/old.py` -> `src/new.py` (why)\n" in msg
    assert "- a.md:2 delete `build` (why)\n" in msg


def test_message_is_redacted() -> None:
    secret = "ghp_" + "A1b2C3d4E5" * 3 + "abcdef"
    findings = [_f("F1", "a.md", 1, 0, secret)]
    hunks = [{"id": "H1", "finding_id": "F1", "doc": "a.md", "line_start": 1, "verb": "delete",
              "token_text": secret, "new_text": None, "reason": "deleted in 1234567",
              "also": []}]
    msg = render_message(findings, hunks, ["H1"], run_id="r", base=BASE, scope="all",
                         trailers=[])
    assert secret not in msg
    assert "ghp_***" in msg


def _git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


def _repo(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "user.email", "t@example.com")
    (root / "README.md").write_text("see `src/gone.py` here\n", encoding="utf-8")
    (root / "other.md").write_text("untouched\n", encoding="utf-8")
    _git(root, "add", "README.md", "other.md")
    _git(root, "commit", "-q", "-m", "init")
    head = _git(root, "rev-parse", "HEAD").strip()
    workdir = root / ".document-drift"
    return root, workdir, head


def test_commit_creates_branch_from_start_and_stages_only_edited_docs(tmp_path: Path) -> None:
    root, workdir, head = _repo(tmp_path)
    (root / "README.md").write_text("see here\n", encoding="utf-8")
    (root / "other.md").write_text("edited by hand\n", encoding="utf-8")
    (root / "scratch.txt").write_text("untracked\n", encoding="utf-8")
    findings = [_f("F001", "README.md", 1, 4, "src/gone.py")]
    hunks = [{"id": "H001", "finding_id": "F001", "doc": "README.md", "line_start": 1,
              "verb": "delete", "token_text": "src/gone.py", "new_text": None,
              "reason": "deleted in 7654321", "also": []}]
    write_json(workdir / "findings.json", {"findings": findings})
    write_json(workdir / "hunks-provable.json", {"hunks": hunks})
    write_json(workdir / "applied.json", {"applied": ["H001"], "reverted": [],
                                          "docs": ["README.md"]})
    write_json(workdir / "preflight.json", {"head": head, "branch_from": "main",
                                            "branch": "drift/x", "git_version": "git"})
    out = run(root, workdir, "drift/x", "abc123def456", "all", ["T: v"])
    assert out["branch"] == "drift/x"
    assert len(out["commits"]) == 1
    assert read_json(workdir / "commits.json") == out
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "drift/x"
    assert _git(root, "rev-parse", "HEAD~1").strip() == head
    stat = _git(root, "show", "--stat", "--format=", "HEAD")
    assert "README.md" in stat and "other.md" not in stat
    assert "?? scratch.txt" in _git(root, "status", "--porcelain")
    body = _git(root, "log", "-1", "--format=%B").strip()
    assert body.startswith("docs(drift): provable fixes")
    assert f"Drift-Base: {head}" in body
    assert body.endswith("T: v")
    raw = (workdir / "commit-msg.txt").read_bytes()
    assert b"\r" not in raw


def test_no_hunks_no_branch(tmp_path: Path) -> None:
    root, workdir, head = _repo(tmp_path)
    write_json(workdir / "findings.json", {"findings": []})
    write_json(workdir / "hunks-provable.json", {"hunks": []})
    write_json(workdir / "applied.json", {"applied": [], "reverted": [], "docs": []})
    write_json(workdir / "preflight.json", {"head": head, "branch_from": "main",
                                            "branch": "drift/x", "git_version": "git"})
    out = run(root, workdir, "drift/x", "r", "all", [])
    assert out == {"branch": None, "commits": []}
    assert read_json(workdir / "commits.json") == {"branch": None, "commits": []}
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def _prep(root: Path, workdir: Path, head: str, doc: str, applied: bool = True,
          finding_ids: tuple[str, ...] = ("F001",)) -> None:
    findings = [_f(fid, doc, 1, 4, "src/gone.py") for fid in finding_ids]
    hunks = [{"id": "H001", "finding_id": "F001", "doc": doc, "line_start": 1,
              "verb": "delete", "token_text": "src/gone.py", "new_text": None,
              "reason": "deleted in 7654321",
              "also": [{"finding_id": "F009", "verb": "delete", "token_text": "x",
                        "new_text": None, "reason": "deleted in 7654321"}]
              if "F009" not in finding_ids and len(finding_ids) > 1 else []}]
    write_json(workdir / "findings.json", {"findings": findings})
    write_json(workdir / "hunks-provable.json", {"hunks": hunks})
    write_json(workdir / "applied.json", {"applied": ["H001"], "reverted": [], "docs": [doc]})
    write_json(workdir / "preflight.json", {"head": head, "branch_from": "main",
                                            "branch": "drift/x", "git_version": "git"})


def test_bracket_named_doc_is_staged_literally(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "config", "user.name", "T")
    _git(root, "config", "user.email", "t@example.com")
    for name in ("[a].md", "a.md", "b.md"):
        (root / "docs" / name).write_text("see `src/gone.py` here\n", encoding="utf-8")
    _git(root, "add", "docs")
    _git(root, "commit", "-q", "-m", "init")
    head = _git(root, "rev-parse", "HEAD").strip()
    (root / "docs" / "[a].md").write_text("see here\n", encoding="utf-8")
    (root / "docs" / "a.md").write_text("hand edit\n", encoding="utf-8")
    workdir = root / ".document-drift"
    _prep(root, workdir, head, "docs/[a].md")
    run(root, workdir, "drift/x", "r", "all", [])
    files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
    assert files == ["docs/[a].md"]
    assert _git(root, "status", "--porcelain", "--untracked-files=no").strip() == "M docs/a.md"


def test_head_moved_creates_no_branch(tmp_path: Path) -> None:
    root, workdir, head = _repo(tmp_path)
    (root / "README.md").write_text("see here\n", encoding="utf-8")
    _prep(root, workdir, "b" * 40, "README.md")
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", "r", "all", [])
    assert exc.value.code == EXIT_COMMIT
    assert "HEAD moved" in str(exc.value)
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert _git(root, "branch", "--list", "drift/x").strip() == ""


def test_missing_finding_is_an_error(tmp_path: Path) -> None:
    root, workdir, head = _repo(tmp_path)
    (root / "README.md").write_text("see here\n", encoding="utf-8")
    _prep(root, workdir, head, "README.md", finding_ids=("F001", "F002"))
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", "r", "all", [])
    assert exc.value.code == EXIT_COMMIT
    assert "F009" in str(exc.value)
    assert _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def test_failure_after_switch_names_the_branch(tmp_path: Path) -> None:
    root, workdir, head = _repo(tmp_path)
    (root / "README.md").write_text("see here\n", encoding="utf-8")
    _prep(root, workdir, head, "README.md")
    write_json(workdir / "applied.json", {"applied": ["H001"], "reverted": [],
                                          "docs": ["missing.md"]})
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", "r", "all", [])
    assert exc.value.code == EXIT_COMMIT
    assert "you are on branch drift/x" in str(exc.value)
