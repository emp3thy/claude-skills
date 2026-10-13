from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_commit import collect_human, human_line, main, render_bullet, render_message, run
from dd_common import EXIT_COMMIT, StepError, read_json, write_json
from dd_helpers import make_repo

BASE = "a" * 40
GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout


# ---------------------------------------------------------------- phase A (two commits)

def _e(eid: str, doc: str, line: int, kind: str, claim: str = "c",
       evidence: list[str] | None = None, subject: str | None = None, source: str = "review",
       **extra: Any) -> dict[str, Any]:
    return {"id": eid, "doc": doc, "start_line": line, "end_line": line, "old": "o", "new": "n",
            "type": kind, "claim": claim, "evidence": evidence or [], "subject": subject,
            "source": source, "status": "kept", "check": None, "human_kind": None,
            "reason": None, **extra}


def test_bullet_grammar_for_every_edit_type() -> None:
    ev = ["src/a.py:3", "src/b.py:9"]
    assert render_bullet(_e("a", "d.md", 4, "correct", "port is 80", ev), 4) == \
        "- d.md:4 correct port is 80 (src/a.py:3, src/b.py:9)"
    assert render_bullet(_e("a", "d.md", 4, "remove", "uses old()", subject="old"), 4) == \
        "- d.md:4 remove uses old() (old not in source)"
    assert render_bullet(_e("a", "d.md", 5, "anchor", evidence=ev, subject="run"), 5) == \
        "- d.md:5 anchor run (src/a.py:3)"
    assert render_bullet(_e("a", "d.md", 6, "notice", source="notice"), 6) == \
        "- d.md:6 notice unverified block (1st notice)"
    assert render_bullet(_e("a", "d.md", 6, "escalate", source="notice"), 6) == \
        "- d.md:6 escalate unverified notice (2nd notice)"
    for reason in ("now anchored", "block changed", "drift-ignore"):
        assert render_bullet(_e("a", "d.md", 6, "clear", reason, source="notice"), 6) == \
            f"- d.md:6 clear unverified notice ({reason})"
    third = _e("a", "d.md", 6, "unverified", "3rd notice, unchanged since 2026-10-01-ab12",
               source="notice")
    assert render_bullet(third, 6) == \
        "- d.md:6 remove unverified block (3rd notice, unchanged since 2026-10-01-ab12)"
    add = _e("a", "d.md", 7, "add", "documents it", ["src/c.py:2"], "APP_X", "gap",
             gap_kind="env")
    assert render_bullet(add, 7) == "- d.md:7 add env APP_X (src/c.py:2)"


def test_message_grammar_corrections_and_additions() -> None:
    kw: dict[str, Any] = {"run_id": "2026-10-12-a3f1", "base": BASE, "scope": "since abc1234",
                          "unchecked": (2, 1, 3), "trailers": ["Signed-off-by: T <t@e.com>"]}
    corrections = render_message("corrections", ["- d.md:4 correct x (a.py:1)"], human=None, **kw)
    assert corrections == (
        "docs(drift): correct stale docs\n\n"
        "Drift-Run: 2026-10-12-a3f1\n"
        f"Drift-Base: {BASE}\n"
        "Drift-Scope: since abc1234\n"
        "Drift-Unchecked: 2 doc units, 1 gap docs, 3 verify batches\n\n"
        "- d.md:4 correct x (a.py:1)\n\n"
        "Signed-off-by: T <t@e.com>\n")
    human = [{"doc": "d.md", "line": 9, "kind": "unsure", "text": "maybe", "evidence": ["a.py:2"]}]
    additions = render_message("additions", ["- d.md:7 add env X (c.py:2)"], human=human,
                               **{**kw, "trailers": []})
    assert additions == (
        "docs(drift): document missing surface\n\n"
        "Drift-Run: 2026-10-12-a3f1\n"
        f"Drift-Base: {BASE}\n"
        "Drift-Scope: since abc1234\n"
        "Drift-Unchecked: 2 doc units, 1 gap docs, 3 verify batches\n\n"
        "- d.md:7 add env X (c.py:2)\n\n"
        "Needs a human decision:\n"
        "- d.md:9 unsure: maybe (a.py:2)\n")


def test_lines_cut_to_160_and_redacted() -> None:
    secret = "ghp_" + "A1b2C3d4E5" * 3 + "abcdef"
    long_claim = secret + " " + "x" * 400
    human = [{"doc": "d.md", "line": 1, "kind": "unsure", "text": long_claim + "\nsecond",
              "evidence": ["a.py:1"]}]
    bullet = render_bullet(_e("a", "d.md", 1, "correct", long_claim, ["a.py:1"]), 1)
    sub = f"  - d.md:1 link #{secret} -> #{'y' * 300}"
    msg = render_message("corrections", [bullet, sub], run_id="r", base=BASE, scope="full",
                         unchecked=(0, 0, 0), human=human, trailers=[])
    assert secret not in msg
    assert "ghp_***" in msg
    assert all(len(line) <= 160 for line in msg.split("\n"))
    assert "second" not in msg
    assert "\n  - d.md:1 link #ghp_***" in msg
    assert msg.count("\n- d.md:1 ") == 2
    assert "\nNeeds a human decision:\n- d.md:1 unsure: ghp_***" in msg


def _w(workdir: Path, **files: Any) -> None:
    for name, data in files.items():
        write_json(workdir / f"{name}.json", data)


def _rev_parse(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def test_collect_human_kinds_and_order(tmp_path: Path) -> None:
    root = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": {"n.md": "<!-- note -->\nFirst line of block\nmore\n"}}])
    work = tmp_path / "work"
    e1 = _e("u1-e01", "z.md", 5, "correct", "claim one", ["a.py:1"])
    e2 = _e("u1-e02", "y.md", 2, "correct", "claim two", ["b.py:2"])
    e3 = _e("u1-e03", "x.md", 8, "correct", "claim three", ["c.py:3"])
    _w(work,
       preflight={"head": _rev_parse(root), "run_id": "r"},
       edits={"edits": [e1, e2, e3],
              "human": [{"doc": "m.md", "line": 4, "kind": "guarantee-mismatch", "text": "g",
                         "evidence": ["g.py:1"]}]},
       verdicts={"verdicts": {"u1-e01": {"verdict": "reject", "reason": "not so"},
                              "u1-e02": {"verdict": "unsure", "reason": "hmm"},
                              "u1-e03": {"verdict": "accept", "reason": "ok"}}, "unverified": []},
       applied={"applied": ["u1-e03"],
                "reverted": [{"edit": "u1-e03", "reason": "recheck-failed"},
                             {"edit": "u1-e01", "reason": "old-mismatch"}],
                "docs": [], "link_updates": []},
       gaps={"no_home": [{"name": "X_Y", "kind": "env", "file": "src/c.py", "line": 7,
                          "parent": None, "hidden": False}]},
       notices={"decisions": [{"doc": "n.md", "line": 1, "action": "escalate", "block": [2, 3]},
                              {"doc": "n.md", "line": 9, "action": "remove", "block": [10, 10]}],
                "edits": []})
    got = collect_human(work, root)
    assert [(h["doc"], h["line"], h["kind"]) for h in got] == [
        ("", 0, "no-home"), ("m.md", 4, "guarantee-mismatch"), ("n.md", 1, "unverified"),
        ("x.md", 8, "recheck-failed"), ("y.md", 2, "verify-rejected"),
        ("z.md", 5, "verify-rejected")]
    by_kind = {(h["doc"], h["kind"]): h for h in got}
    assert by_kind[("z.md", "verify-rejected")]["text"] == "claim one: not so"
    assert by_kind[("z.md", "verify-rejected")]["evidence"] == ["a.py:1"]
    assert by_kind[("x.md", "recheck-failed")]["text"] == "claim three"
    assert by_kind[("", "no-home")] == {"doc": "", "line": 0, "kind": "no-home",
                                        "text": "env X_Y", "evidence": ["src/c.py:7"]}
    # a no-home item has no doc, so its line has no doc:line
    assert human_line(by_kind[("", "no-home")]) == "- no-home: env X_Y (src/c.py:7)"
    assert human_line(by_kind[("m.md", "guarantee-mismatch")]) == (
        "- m.md:4 guarantee-mismatch: g (g.py:1)")
    assert by_kind[("n.md", "unverified")]["text"] == "First line of block"


def _phase_a(tmp_path: Path) -> tuple[Path, Path, str]:
    root = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": {"a.md": "old a\n", "b.md": "old b\n",
                                           "c.md": "keep\n"}}])
    _git(root, "config", "user.name", "T")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "commit.gpgsign", "false")
    head = _rev_parse(root)
    (root / "a.md").write_text("new a\n", encoding="utf-8")
    (root / "b.md").write_text("old b\nadded\n", encoding="utf-8")
    work = root / ".document-drift"
    edits = [_e("u001-e01", "a.md", 1, "correct", "a is new", ["src/x.py:1"]),
             _e("g001-e01", "b.md", 1, "add", "adds it", ["src/x.py:2"], "APP_X", "gap"),
             _e("u001-e02", "c.md", 1, "remove", "dropped", subject="gone")]
    _w(work,
       preflight={"head": head, "run_id": "r"}, changes={"scope": "first"},
       edits={"edits": edits,
              "human": [{"doc": "c.md", "line": 1, "kind": "unsure", "text": "q",
                         "evidence": []}],
              "unchecked_units": ["u9"], "unchecked_gap_docs": [], "unverified_batches": [["v"]]},
       verdicts={"verdicts": {}, "unverified": []},
       applied={"applied": ["g001-e01", "u001-e01"], "reverted": [],
                "docs": ["a.md", "b.md"], "link_updates": []},
       gaps={"no_home": [], "gaps": [{"name": "APP_X", "kind": "env", "target_doc": "b.md"}]},
       notices={"decisions": [], "edits": []})
    return root, work, head


def _show(root: Path, rev: str, fmt: str) -> str:
    return subprocess.run(["git", "-C", str(root), "show", "-s", f"--format={fmt}", rev],
                          capture_output=True, text=True, check=True).stdout


def _files(root: Path, rev: str) -> list[str]:
    return subprocess.run(["git", "-C", str(root), "show", "--name-only", "--format=", rev],
                          capture_output=True, text=True, check=True).stdout.split()


def test_human_block_on_last_commit_only(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert out["branch"] == "drift/r"
    assert [c["kind"] for c in out["commits"]] == ["corrections", "additions"]
    assert read_json(work / "commits.json") == out
    first, second = out["commits"][0]["sha"], out["commits"][1]["sha"]
    msg1, msg2 = _show(root, first, "%B"), _show(root, second, "%B")
    assert msg1.startswith("docs(drift): correct stale docs\n\nDrift-Run: r\n")
    assert "Needs a human decision" not in msg1
    assert "- a.md:1 correct a is new (src/x.py:1)" in msg1
    assert msg2.startswith("docs(drift): document missing surface\n")
    assert "- b.md:1 add env APP_X (src/x.py:2)" in msg2
    assert msg2.strip().endswith("Needs a human decision:\n- c.md:1 unsure: q")
    assert "Drift-Unchecked: 1 doc units, 0 gap docs, 1 verify batches" in msg1
    assert "Drift-Scope: first" in msg1
    assert _show(root, first, "%P").strip() == head
    assert _files(root, first) == ["a.md"]
    assert _files(root, second) == ["b.md"]
    written = (work / "commit-msg-corrections.txt").read_text(encoding="utf-8")
    assert written.strip() == msg1.strip()
    assert (work / "commit-msg-additions.txt").is_file()


def test_single_commit_carries_the_human_block(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    applied = read_json(work / "applied.json")
    write_json(work / "applied.json", {**applied, "applied": ["u001-e01"], "docs": ["a.md"]})
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections"]
    assert "Needs a human decision" in _show(root, out["commits"][0]["sha"], "%B")
    assert not (work / "commit-msg-additions.txt").exists()


def test_doc_with_both_kinds_lands_in_corrections_commit(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    add = _e("g001-e02", "a.md", 1, "add", "adds", ["src/x.py:2"], "APP_Y", "gap")
    edits = read_json(work / "edits.json")
    write_json(work / "edits.json", {**edits, "edits": [*edits["edits"], add]})
    gaps = read_json(work / "gaps.json")
    write_json(work / "gaps.json", {**gaps, "gaps": [*gaps["gaps"], {
        "name": "APP_Y", "kind": "flag", "target_doc": "a.md"}]})
    link = {"doc": "a.md", "line": 1, "old": "x", "new": "y", "edit": "u001-e01"}
    write_json(work / "applied.json", {"applied": ["g001-e02", "u001-e01"], "reverted": [],
                                       "docs": ["a.md"], "link_updates": [link]})
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections", "additions"]
    msg1 = _show(root, out["commits"][0]["sha"], "%B")
    assert "- a.md:1 correct a is new (src/x.py:1)\n  - a.md:1 link #x -> #y\n" in msg1
    assert _files(root, out["commits"][0]["sha"]) == ["a.md"]
    assert "- a.md:1 add flag APP_Y (src/x.py:2)" in _show(root, out["commits"][1]["sha"], "%B")


def test_no_commit_without_edits_and_no_branch(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    write_json(work / "applied.json", {"applied": [], "reverted": [], "docs": [],
                                       "link_updates": []})
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert out == {"branch": None, "commits": []}
    assert read_json(work / "commits.json") == out
    listed = subprocess.run(["git", "-C", str(root), "branch", "--list", "drift/r"],
                            capture_output=True, text=True, check=True).stdout
    assert listed.strip() == ""


def test_phase_a_head_moved_creates_no_branch(tmp_path: Path) -> None:
    root, work, _ = _phase_a(tmp_path)
    with pytest.raises(StepError) as exc:
        run(root, work, "drift/r", "r", "b" * 40, "first", [])
    assert exc.value.code == EXIT_COMMIT
    listed = subprocess.run(["git", "-C", str(root), "branch", "--list", "drift/r"],
                            capture_output=True, text=True, check=True).stdout
    assert listed.strip() == ""


def test_add_edit_matching_no_gap_is_an_error(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    gaps = read_json(work / "gaps.json")
    write_json(work / "gaps.json", {**gaps, "gaps": []})
    with pytest.raises(StepError) as exc:
        run(root, work, "drift/r", "r", head, "first", [])
    assert "g001-e01" in str(exc.value)


def test_add_subject_in_backticks_matches_the_normalised_gap_name(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    edits = read_json(work / "edits.json")
    edits["edits"][1]["subject"] = " `app-x` "
    write_json(work / "edits.json", edits)
    write_json(work / "gaps.json", {"no_home": [], "gaps": [
        {"name": "app.x", "kind": "env", "target_doc": "b.md"}]})
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert "- b.md:1 add env `app-x`" not in _show(root, out["commits"][1]["sha"], "%B")
    assert "- b.md:1 add env app-x (src/x.py:2)" in _show(root, out["commits"][1]["sha"], "%B")


def test_failed_second_commit_keeps_the_first_in_commits_json(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    hook = root / ".git" / "hooks" / "commit-msg"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text('#!/bin/sh\ngrep -q "missing surface" "$1" && exit 1\nexit 0\n',
                    encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    with pytest.raises(StepError) as exc:
        run(root, work, "drift/r", "r", head, "first", [])
    assert exc.value.code == EXIT_COMMIT
    saved = read_json(work / "commits.json")
    assert saved["branch"] == "drift/r"
    assert [c["kind"] for c in saved["commits"]] == ["corrections"]


def test_bracket_named_doc_is_staged_literally(tmp_path: Path) -> None:
    root = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": {"docs/[a].md": "old\n", "docs/a.md": "old\n"}}])
    for key, value in (("user.name", "T"), ("user.email", "t@example.com"),
                       ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    head = _rev_parse(root)
    (root / "docs" / "[a].md").write_text("new\n", encoding="utf-8")
    (root / "docs" / "a.md").write_text("hand edit\n", encoding="utf-8")
    work = root / ".document-drift"
    _w(work, preflight={"head": head, "run_id": "r"},
       edits={"edits": [_e("u001-e01", "docs/[a].md", 1, "correct", "new", ["src/x.py:1"])]},
       applied={"applied": ["u001-e01"], "reverted": [], "docs": ["docs/[a].md"],
                "link_updates": []})
    run(root, work, "drift/r", "r", head, "first", [])
    assert _files(root, "HEAD") == ["docs/[a].md"]
    assert _git(root, "status", "--porcelain", "--untracked-files=no").strip() == "M docs/a.md"


def test_main_commits_from_the_preflight_head(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    assert main([str(root), "--workdir", str(work), "--branch", "drift/m", "--run-id", "r",
                 "--scope", "first"]) == 0
    commits = read_json(work / "commits.json")["commits"]
    assert f"Drift-Base: {head}" in _show(root, commits[0]["sha"], "%B")
