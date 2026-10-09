from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import dd_fixes
import dd_resolve
import pytest
from dd_common import read_json
from dd_helpers import make_repo
from dd_run import main

BODY = "print('a long enough body for rename detection, {}')\n"
README = "# Project\n\n- `src/old.py` the entry point\n- `src/util.py` helpers\n"


def _c(day: str, subject: str, **kw: object) -> dict[str, object]:
    return {"date": f"2026-01-{day}T00:00:00Z", "subject": subject, **kw}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return out.stdout


def _identity(repo: Path) -> Path:
    _git(repo, "config", "user.name", "T")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.autocrlf", "false")
    return repo


def _rename_repo(tmp_path: Path) -> Path:
    return _identity(make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": README,
            "src/old.py": BODY.format("old"),
            "src/util.py": BODY.format("util"),
        }),
        _c("02", "rename", rename={"src/old.py": "src/new.py"}),
    ]))


def _run_id(head: str, scope: str, date: str) -> str:
    return hashlib.sha256(f"{head}:{scope}:{date}".encode()).hexdigest()[:12]


def _main(repo: Path, *extra: str) -> int:
    return main([str(repo), "--date", "2026-01-02", *extra])


def test_run_end_to_end_small_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _main(repo) == 0
    out = capsys.readouterr().out
    workdir = repo / ".document-drift"
    commits = read_json(workdir / "commits.json")
    assert commits["branch"] == "docs/drift-2026-01-02"
    assert len(commits["commits"]) == 1
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "docs/drift-2026-01-02"
    assert _git(repo, "rev-parse", "HEAD~1").strip() == head
    assert (repo / "README.md").read_text(encoding="utf-8") == README.replace("old.py", "new.py")
    sha7 = _git(repo, "rev-parse", "main").strip()[:7]
    body = _git(repo, "log", "-1", "--format=%B")
    run_id = _run_id(head, "all", "2026-01-02")
    assert body == (
        "docs(drift): provable fixes\n\n"
        f"Drift-Run: {run_id}\nDrift-Base: {head}\nDrift-Scope: all\n\n"
        f"- README.md:3 replace `src/old.py` -> `src/new.py` (renamed in {sha7})\n\n"
    )
    assert _git(repo, "status", "--porcelain") == ""
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert out == summary
    assert f"Run: {run_id}" in summary
    assert "Branch: docs/drift-2026-01-02" in summary
    assert commits["commits"][0] in summary
    assert "applied 1" in summary


def test_check_mode_exits_1_and_edits_nothing(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _main(repo, "--check") == 1
    workdir = repo / ".document-drift"
    assert (repo / "README.md").read_text(encoding="utf-8") == README
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    assert _git(repo, "branch", "--list").split() == ["*", "main"]
    assert len(read_json(workdir / "hunks-provable.json")["hunks"]) == 1
    assert not (workdir / "applied.json").exists()
    assert not (workdir / "commits.json").exists()
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert "check mode: no edits made" in summary
    assert "No branch created." in summary
    assert capsys.readouterr().out == summary


def test_check_mode_exits_0_when_no_hunks(tmp_path: Path) -> None:
    repo = _identity(make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "See `src/app.py`.\n", "src/app.py": "x = 1\n"})]))
    assert _main(repo, "--check") == 0


def test_stale_outputs_are_removed_first(tmp_path: Path) -> None:
    repo = _rename_repo(tmp_path)
    workdir = tmp_path / "work"
    workdir.mkdir()
    for name in ("applied.json", "commits.json", "commit-msg.txt"):
        (workdir / name).write_text("stale\n", encoding="utf-8")
    assert _main(repo, "--check", "--workdir", str(workdir)) == 1
    assert not (workdir / "applied.json").exists()
    assert not (workdir / "commits.json").exists()
    assert not (workdir / "commit-msg.txt").exists()


def test_missing_output_exits_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)

    def skip(root: Path, workdir: Path) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(dd_fixes, "run", skip)
    assert _main(repo) == 5
    err = capsys.readouterr().err
    assert "findings.json" in err
    assert (repo / "README.md").read_text(encoding="utf-8") == README


def test_crashed_step_exits_5_with_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)

    def boom(root: Path, workdir: Path, history: object = None) -> dict[str, Any]:
        raise ValueError("kaput")

    monkeypatch.setattr(dd_resolve, "run", boom)
    assert _main(repo) == 5
    err = capsys.readouterr().err
    assert "Traceback" in err and "ValueError: kaput" in err
    assert "resolve" in err


def test_refusal_exit_2_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)
    (repo / "README.md").write_text("edited\n", encoding="utf-8")
    assert _main(repo) == 2
    err = capsys.readouterr().err
    assert "working tree is not clean" in err
    assert not (repo / ".document-drift" / "summary.md").exists()


def test_branch_option_and_config_branch(tmp_path: Path) -> None:
    repo = _identity(make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": README,
            ".document-drift.yaml": "branch: fix/docs-{date}\nbogus: 1\n",
            "src/old.py": BODY.format("old"),
            "src/util.py": BODY.format("util"),
        }),
        _c("02", "rename", rename={"src/old.py": "src/new.py"}),
    ]))
    assert _main(repo) == 0
    workdir = repo / ".document-drift"
    assert read_json(workdir / "commits.json")["branch"] == "fix/docs-2026-01-02"
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert "unknown key 'bogus' ignored" in summary


def test_base_scope_drops_unrelated_docs(tmp_path: Path) -> None:
    repo = _identity(make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": README,
            "docs/other.md": "# Other\n\n- `lib/gone.py` old\n- `lib/x.py` kept\n",
            "docs/dir.md": "Code lives in `src/`.\n",
            "src/old.py": BODY.format("old"),
            "src/util.py": BODY.format("util"),
            "lib/gone.py": BODY.format("gone"),
            "lib/x.py": BODY.format("x"),
        }),
        _c("02", "delete gone", delete=["lib/gone.py"], tag="base"),
        _c("03", "rename", rename={"src/old.py": "src/new.py"}),
    ]))
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _main(repo, "--base", "base") == 0
    workdir = repo / ".document-drift"
    inventory = read_json(workdir / "inventory.json")
    assert inventory["scope_dropped"] == ["docs/other.md"]
    assert inventory["docs"] == ["README.md", "docs/dir.md"]
    assert "docs/other.md" not in read_json(workdir / "tokens.json")["docs"]
    cands = read_json(workdir / "candidates.json")["candidates"]
    assert [c["doc"] for c in cands] == ["README.md"]
    body = _git(repo, "log", "-1", "--format=%B")
    assert "Drift-Scope: base:base\n" in body
    assert f"Drift-Run: {_run_id(head, 'base:base', '2026-01-02')}\n" in body
    assert "lib/gone.py" in (repo / "docs/other.md").read_text(encoding="utf-8")
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert "Scope: base:base" in summary
    assert "docs/other.md" in summary


def test_base_invalid_ref_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)
    assert _main(repo, "--base", "no-such-ref") == 2
    assert "no-such-ref" in capsys.readouterr().err
    assert (repo / "README.md").read_text(encoding="utf-8") == README


def test_second_run_on_drift_branch_makes_no_commit(tmp_path: Path,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    repo = _rename_repo(tmp_path)
    assert _main(repo) == 0
    first = _git(repo, "rev-parse", "HEAD").strip()
    capsys.readouterr()
    assert _main(repo, "--branch", "docs/drift-again") == 0
    workdir = repo / ".document-drift"
    assert read_json(workdir / "commits.json") == {"branch": None, "commits": []}
    assert _git(repo, "rev-parse", "HEAD").strip() == first
    assert "docs/drift-again" not in _git(repo, "branch", "--list")
    out = capsys.readouterr().out
    assert "No branch created." in out
    assert re.search(r"^Run: [0-9a-f]{12}$", out, re.M)
