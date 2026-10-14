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


def test_bullet_grammar_for_script_edits() -> None:
    # phase C spec 6: a finish with an applied script edit must not fail on its bullet
    cite = _e("c001", "d.md", 9, "cite", "connect is at src/app.py:4-6", ["src/app.py:4-6"],
              "connect", "script", old_cite="src/app.py:9", new_cite="src/app.py:4")
    assert render_bullet(cite, 9) == "- d.md:9 cite connect src/app.py:9 -> src/app.py:4"
    fact = _e("f001", "d.md", 12, "fact", "--port default is 8080", ["src/cli.py:7"],
              "--port", "script", column="default", old_cell="`80`", new_cell="`8080`")
    assert render_bullet(fact, 12) == \
        "- d.md:12 fact --port default `80` -> `8080` (src/cli.py:7)"


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


def test_add_subject_listing_several_gap_names_takes_the_first_kind(tmp_path: Path) -> None:
    # live run: a gap agent put three flags that go together in one edit, its subject
    # "--tested, --passing, --failing"; the kind is the first listed name's gap
    root, work, head = _phase_a(tmp_path)
    edits = read_json(work / "edits.json")
    edits["edits"][1]["subject"] = "--tested, --passing, --failing"
    write_json(work / "edits.json", edits)
    write_json(work / "gaps.json", {"no_home": [], "gaps": [
        {"name": "--passing", "kind": "env", "target_doc": "b.md"},
        {"name": "--tested", "kind": "flag", "target_doc": "b.md"},
        {"name": "--failing", "kind": "flag", "target_doc": "b.md"}]})
    out = run(root, work, "drift/r", "r", head, "first", [])
    message = _show(root, out["commits"][1]["sha"], "%B")
    assert "- b.md:1 add flag --tested, --passing, --failing (src/x.py:2)" in message


def test_add_subject_listing_only_unknown_names_is_an_error(tmp_path: Path) -> None:
    root, work, head = _phase_a(tmp_path)
    edits = read_json(work / "edits.json")
    edits["edits"][1]["subject"] = "--nope, --nor"
    write_json(work / "edits.json", edits)
    with pytest.raises(StepError) as exc:
        run(root, work, "drift/r", "r", head, "first", [])
    assert "matches no gap" in str(exc.value)


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


# ---------------------------------------------------------------- phase B (the README)

CREATE = _e("r001", "README.md", 1, "create", "readme from 2 sheets", source="readme",
            statements=4)


def _phase_b(tmp_path: Path) -> tuple[Path, Path, str]:
    """A repository without a README whose run wrote one: a ``create`` edit applied, no other
    edit, two valid sheets, one statement removed."""
    root = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": {"src/x.py": "X = 1\n"}}])
    for key, value in (("user.name", "T"), ("user.email", "t@example.com"),
                       ("commit.gpgsign", "false")):
        _git(root, "config", key, value)
    head = _rev_parse(root)
    (root / "README.md").write_text("# x\n\n`X` is one.\n", encoding="utf-8")
    work = root / ".document-drift"
    statements = [{"id": f"r-s00{n}", "start_line": line, "end_line": line, "section": "x",
                   "kind": "item", "text": f"- `X` fact {n}\n  more", "claims": [0],
                   "cites": ["a01-s01"], "prereject": None}
                  for n, line in ((1, 3), (2, 5), (3, 7), (4, 9))]
    statements[1]["prereject"] = "guarantee word"
    _w(work,
       preflight={"head": head, "run_id": "r"},
       edits={"edits": [{**CREATE, "old": "", "new": ""}],
              "human": [{"doc": "README.md", "line": 5, "kind": "readme-rejected",
                         "text": "- `X` fact 2 (proposed line)",
                         "evidence": ["guarantee word"]}]},
       readme={"text": "", "claims": [], "statements": statements, "cites_added": 0,
               "cited_unnamed": 0},
       sheets={"sheets": {"a01": {}, "a02": {}}, "unchecked": [], "filled": 0},
       verdicts={"verdicts": {}, "unverified": [],
                 "readme": {"r-s001": {"verdict": "accept", "reason": "ok"},
                            "r-s003": {"verdict": "reject", "reason": "X is two"},
                            "r-s004": {"verdict": "unsure", "reason": "unclear"}},
                 "readme_unverified": []},
       applied={"applied": ["r001"], "reverted": [], "docs": [], "link_updates": [],
                "readme": {"lines": 3, "statements": 1, "removed": 3}},
       gaps={"no_home": [{"name": "X", "kind": "env", "file": "src/x.py", "line": 1,
                          "parent": None, "hidden": False},
                         {"name": "y-flag", "kind": "flag", "file": "src/x.py", "line": 1,
                          "parent": None, "hidden": False}], "gaps": []},
       notices={"decisions": [], "edits": []})
    return root, work, head


def test_create_bullet_and_additions_commit_stage_the_readme(tmp_path: Path) -> None:
    assert render_bullet({**CREATE, "sheets": 2, "removed": 3}) == (
        "- README.md:1 create readme (4 statements from 2 sheets, 3 removed)")
    root, work, head = _phase_b(tmp_path)
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["additions"]
    sha = out["commits"][0]["sha"]
    assert _files(root, sha) == ["README.md"]
    msg = _show(root, sha, "%B")
    assert msg.startswith("docs(drift): document missing surface\n")
    assert "\n- README.md:1 create readme (4 statements from 2 sheets, 3 removed)\n" in msg
    # `X` is in the written README, so only y-flag is left with no home
    assert ("Needs a human decision:\n- no-home: flag y-flag (src/x.py:1)\n"
            "- README.md:5 readme-rejected: - `X` fact 2 (proposed line) (guarantee word)\n"
            in msg)
    assert not (work / "commit-msg-corrections.txt").exists()
    assert _git(root, "status", "--porcelain", "--untracked-files=no") == ""


def test_create_edit_not_applied_makes_no_commit(tmp_path: Path) -> None:
    root, work, head = _phase_b(tmp_path)
    applied = read_json(work / "applied.json")
    write_json(work / "applied.json", {**applied, "applied": [], "readme": None})
    assert run(root, work, "drift/r", "r", head, "first", []) == {"branch": None, "commits": []}


def test_readme_rejected_and_no_home_suppressed_in_human_list(tmp_path: Path) -> None:
    root, work, _ = _phase_b(tmp_path)
    got = collect_human(work, root)
    # the written README names `X` in an inline-code span, so that no-home item is dropped;
    # `y-flag` is named nowhere in it and stays the owner's
    assert got == [
        {"doc": "", "line": 0, "kind": "no-home", "text": "flag y-flag",
         "evidence": ["src/x.py:1"]},
        {"doc": "README.md", "line": 5, "kind": "readme-rejected",
         "text": "- `X` fact 2 (proposed line)", "evidence": ["guarantee word"]},
        {"doc": "README.md", "line": 7, "kind": "readme-rejected",
         "text": "- `X` fact 3 (proposed line)", "evidence": ["X is two"]},
        {"doc": "README.md", "line": 9, "kind": "readme-rejected",
         "text": "- `X` fact 4 (proposed line)", "evidence": ["unclear"]}]
    assert human_line(got[2]) == (
        "- README.md:7 readme-rejected: - `X` fact 3 (proposed line) (X is two)")
    # a span names a no-home item by dd_defindex.norm: `y_flag` names y-flag
    (root / "README.md").write_text("# x\n\n`X` is one; see `y_flag`.\n", encoding="utf-8")
    assert [h["kind"] for h in collect_human(work, root)] == ["readme-rejected"] * 3
    # without the repository the README is the readme.json text without the statements
    # that did not stay: r-s001 (line 3, naming `X`) stays, r-s002 (line 5) does not
    readme = read_json(work / "readme.json")
    text = "# x\n\n- `X` fact 1\n\n- `X` fact 2 `y-flag`\n"
    write_json(work / "readme.json", {**readme, "text": text})
    assert [h["text"] for h in collect_human(work) if h["kind"] == "no-home"] == [
        "flag y-flag"]
    # no README written (or none wanted): the names with no home are the owner's again
    applied = read_json(work / "applied.json")
    write_json(work / "applied.json", {**applied, "readme": None})
    assert [h["kind"] for h in collect_human(work, root)] == [
        "no-home", "no-home", "readme-rejected", "readme-rejected", "readme-rejected"]


# ---------------------------------------------------------------- phase C (script edits)

def _cite(eid: str, doc: str, line: int) -> dict[str, Any]:
    return _e(eid, doc, line, "cite", "x is at src/x.py:4", ["src/x.py:4"], "x", "script",
              old_cite="src/x.py:9", new_cite="src/x.py:4")


def _fact(eid: str, doc: str, line: int) -> dict[str, Any]:
    return _e(eid, doc, line, "fact", "--port default is 8080", ["src/cli.py:7"], "--port",
              "script", column="default", old_cell="`80`", new_cell="`8080`")


def _phase_c(tmp_path: Path, script: list[dict[str, Any]],
             applied: list[str] | None = None) -> tuple[Path, Path, str]:
    """``_phase_a`` plus the applied ``script`` edits (``c.md`` rewritten when one names it);
    ``applied`` replaces the applied agent edits (default: both of ``_phase_a``)."""
    root, work, head = _phase_a(tmp_path)
    if any(e["doc"] == "c.md" for e in script):
        (root / "c.md").write_text("keep (src/x.py:4)\n", encoding="utf-8")
    edits = read_json(work / "edits.json")
    write_json(work / "edits.json", {**edits, "edits": [*edits["edits"], *script]})
    agent = ["g001-e01", "u001-e01"] if applied is None else applied
    docs = sorted({"g001-e01": "b.md", "u001-e01": "a.md"}[a] for a in agent)
    write_json(work / "applied.json", {
        "applied": [*agent, *(e["id"] for e in script)], "reverted": [],
        "docs": sorted({*docs, *(e["doc"] for e in script)}), "link_updates": []})
    return root, work, head


def test_citations_commit_after_additions_with_bullets(tmp_path: Path) -> None:
    root, work, head = _phase_c(tmp_path, [_fact("f001", "c.md", 1), _cite("c001", "c.md", 1)])
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections", "additions", "citations"]
    assert read_json(work / "commits.json") == out
    first, second, third = (c["sha"] for c in out["commits"])
    assert _files(root, first) == ["a.md"] and _files(root, second) == ["b.md"]
    assert _files(root, third) == ["c.md"]
    assert _show(root, third, "%P").strip() == second
    msg = _show(root, third, "%B")
    assert msg.startswith("docs(drift): correct citations and facts\n\nDrift-Run: r\n")
    assert ("\n- c.md:1 cite x src/x.py:9 -> src/x.py:4\n"
            "- c.md:1 fact --port default `80` -> `8080` (src/cli.py:7)\n") in msg
    assert "cite" not in _show(root, first, "%B") and "fact" not in _show(root, first, "%B")
    written = (work / "commit-msg-citations.txt").read_text(encoding="utf-8")
    assert written.strip() == msg.strip()
    assert _git(root, "status", "--porcelain", "--untracked-files=no") == ""


def test_citations_commit_allow_empty_when_docs_already_staged(tmp_path: Path) -> None:
    root, work, head = _phase_c(tmp_path, [_cite("c001", "a.md", 1), _fact("f001", "b.md", 1)])
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections", "additions", "citations"]
    third = out["commits"][2]["sha"]
    assert _files(root, third) == []  # a.md and b.md rode in the earlier commits
    assert _show(root, third, "%P").strip() == out["commits"][1]["sha"]
    msg = _show(root, third, "%B")
    assert "\n- a.md:1 cite x src/x.py:9 -> src/x.py:4\n" in msg
    assert "\n- b.md:1 fact --port default `80` -> `8080` (src/cli.py:7)\n" in msg


def test_human_list_on_last_commit_made(tmp_path: Path) -> None:
    root, work, head = _phase_c(tmp_path, [_cite("c001", "c.md", 1)], applied=["u001-e01"])
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections", "citations"]
    first, last = (_show(root, c["sha"], "%B") for c in out["commits"])
    assert "Needs a human decision" not in first
    assert last.strip().endswith("Needs a human decision:\n- c.md:1 unsure: q")
    assert not (work / "commit-msg-additions.txt").exists()
    # with no script edit applied the human list stays on the last agent commit
    root, work, head = _phase_c(tmp_path / "b", [])
    out = run(root, work, "drift/r", "r", head, "first", [])
    assert [c["kind"] for c in out["commits"]] == ["corrections", "additions"]
    assert "Needs a human decision" in _show(root, out["commits"][1]["sha"], "%B")
