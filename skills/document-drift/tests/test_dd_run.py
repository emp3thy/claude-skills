"""The staged driver (spec 2, 3) on a small repository with canned agent outputs.

The canned outputs under ``tests/canned/small`` quote the fixture docs below line for line;
change both together.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import dd_commit
import dd_run
import dd_summary
import dd_units
import pytest
from dd_common import EXIT_MISSING, StepError, read_json
from dd_helpers import make_repo
from dd_run import main
from dd_unverified import block_hash, render_notice

DATE = "2026-01-02"
BRANCH = f"docs/drift-{DATE}"
CANNED = Path(__file__).resolve().parent / "canned" / "small"

APP = '''import os


def connect(retries=3):
    """Open the connection, retrying on failure."""
    return retries


def main():
    host = os.environ.get("APP_HOST")
    token = os.environ.get("APP_TOKEN")
    return connect(), host, token
'''
README = """# Demo app

A small demo service.

## Usage

Call `connect` to open the connection. It retries 5 times by default.
"""
CONFIG = """# Configuration

## Environment

The service reads `APP_HOST` for the server address.
"""
FILES = {"src/app.py": APP, "README.md": README, "docs/config.md": CONFIG}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return out.stdout


def _repo(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    repo = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": FILES if files is None else files}])
    for key, value in (("user.name", "T"), ("user.email", "t@example.com"),
                       ("commit.gpgsign", "false"), ("core.autocrlf", "false")):
        _git(repo, "config", key, value)
    return repo


def _run(repo: Path, stage: str, *extra: str) -> int:
    return main([str(repo), "--stage", stage, "--date", DATE, *extra])


def _plan(repo: Path, name: str) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = read_json(repo / ".document-drift" / name)
    return plan


def _answer(repo: Path, name: str, invalid: tuple[str, ...] = ()) -> None:
    """Copy the canned output of every entry of plan ``name`` to its output path; the ids in
    ``invalid`` get the canned invalid output instead."""
    for entry in _plan(repo, name):
        out = Path(entry["output"])
        source = CANNED / ("invalid" if entry["id"] in invalid else out.parent.name) / out.name
        shutil.copyfile(source, out)


def _start_and_answer(repo: Path, *extra: str) -> None:
    assert _run(repo, "start", *extra) == 0
    _answer(repo, "plan-docs.json")


def _through_verify(repo: Path, *extra: str) -> None:
    _start_and_answer(repo, *extra)
    assert _run(repo, "verify") == 0
    _answer(repo, "plan-verify.json")


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out.strip().splitlines()[-1]


def test_start_writes_plan_and_prompts(tmp_path: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    plan = _plan(repo, "plan-docs.json")
    out = capsys.readouterr().out
    assert out == f"plan-docs.json {(workdir / 'plan-docs.json').as_posix()} with 2 entries\n"
    assert [(e["id"], e["role"]) for e in plan] == [("u001", "review"), ("g001", "gap")]
    for entry in plan:
        assert Path(entry["prompt"]).is_file()
        assert not Path(entry["output"]).exists()
    pre = read_json(workdir / "preflight.json")
    digest = hashlib.sha256(f"{head}:first:{DATE}".encode()).hexdigest()[:4]
    assert pre["run_id"] == f"{DATE}-{digest}"
    assert (pre["scope"], pre["stage"], pre["date"], pre["branch"]) == (
        "first", "start", DATE, BRANCH)
    assert (pre["base"], pre["full"], pre["check"], pre["dirty"]) == (None, False, False, {})
    for name in ("inventory.json", "tokens.json", "candidates.json", "defindex.json",
                 "anchors.json", "changes.json", "units.json", "patterns.json", "gaps.json",
                 "notices.json"):
        assert (workdir / name).is_file(), name


def test_start_clears_every_pinned_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    workdir = repo / ".document-drift"
    for stale in ("edits.json", "retry.json", "summary.md", "review/u009.json",
                  "verdicts/v09.json", "prompts/verify-v09.md", "gaps/g009.json"):
        (workdir / stale).parent.mkdir(parents=True, exist_ok=True)
        (workdir / stale).write_text("stale", encoding="utf-8")
    assert _run(repo, "start") == 0
    for stale in ("edits.json", "retry.json", "summary.md", "review/u009.json",
                  "verdicts/v09.json", "prompts/verify-v09.md", "gaps/g009.json"):
        assert not (workdir / stale).exists(), stale


def test_verify_before_start_is_refused(tmp_path: Path,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "verify") == 2
    assert "run --stage start first" in capsys.readouterr().err
    assert _run(repo, "finish") == 2


def test_finish_before_verify_is_refused(tmp_path: Path,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _start_and_answer(repo)
    assert _run(repo, "finish") == 2
    assert "plan-verify.json" in capsys.readouterr().err


@pytest.mark.parametrize("flag", [("--branch", "docs/other"), ("--check",), ("--full",),
                                  ("--base", "HEAD"), ("--date", "2026-01-03")])
def test_flag_mismatch_between_stages_is_refused(tmp_path: Path, flag: tuple[str, ...],
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _start_and_answer(repo)
    capsys.readouterr()
    assert main([str(repo), "--stage", "verify", *flag]) == 2
    assert flag[0] in capsys.readouterr().err
    assert not (repo / ".document-drift" / "edits.json").exists()
    assert _run(repo, "verify", "--branch", BRANCH) == 0  # the recorded value is accepted


def test_missing_agent_output_exits_3_and_writes_retry(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _start_and_answer(repo)
    workdir = repo / ".document-drift"
    (workdir / "review" / "u001.json").unlink()
    capsys.readouterr()
    assert _run(repo, "verify") == 3
    retry = read_json(workdir / "retry.json")
    assert [e["id"] for e in retry] == ["u001"]
    assert retry == [e for e in _plan(repo, "plan-docs.json") if e["id"] == "u001"]
    assert capsys.readouterr().out == (
        f"retry.json {(workdir / 'retry.json').as_posix()} with 1 entries\n")
    assert not (workdir / "edits.json").exists()
    assert not (workdir / "plan-verify.json").exists()


def test_invalid_agent_output_exits_3(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start") == 0
    _answer(repo, "plan-docs.json", invalid=("u001",))
    assert _run(repo, "verify") == 3
    assert [e["id"] for e in read_json(repo / ".document-drift" / "retry.json")] == ["u001"]


def test_retried_marks_unit_unchecked(tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start") == 0
    _answer(repo, "plan-docs.json", invalid=("u001",))
    assert _run(repo, "verify") == 3
    capsys.readouterr()
    assert _run(repo, "verify", "--retried") == 0
    workdir = repo / ".document-drift"
    edits = read_json(workdir / "edits.json")
    assert edits["unchecked_units"] == ["u001"]
    assert [e["id"] for e in edits["edits"]] == ["g001-e01"]
    plan = _plan(repo, "plan-verify.json")
    assert capsys.readouterr().out == (
        f"plan-verify.json {(workdir / 'plan-verify.json').as_posix()} with {len(plan)} "
        "entries\n")


def test_finish_commits_two_commits_and_records_last_run(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    _through_verify(repo)
    capsys.readouterr()
    assert _run(repo, "finish") == 0
    out = capsys.readouterr().out
    workdir = repo / ".document-drift"
    assert out == (workdir / "summary.md").read_text(encoding="utf-8")
    assert f"Branch: {BRANCH}" in out
    commits = read_json(workdir / "commits.json")
    assert commits["branch"] == BRANCH
    assert [c["kind"] for c in commits["commits"]] == ["corrections", "additions"]
    assert _git(repo, "symbolic-ref", "--short", "HEAD").strip() == BRANCH
    assert _git(repo, "rev-parse", "main").strip() == head  # the original branch is untouched
    docs = set(read_json(workdir / "inventory.json")["docs"])
    for commit in commits["commits"]:
        touched = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r",
                       commit["sha"]).split()
        assert touched and all(p.endswith(".md") and p in docs for p in touched)
        message = _git(repo, "log", "-1", "--format=%B", commit["sha"])
        assert f"Drift-Base: {head}" in message
    assert "It retries 3 times by default." in (repo / "README.md").read_text(encoding="utf-8")
    assert "APP_TOKEN" in (repo / "docs" / "config.md").read_text(encoding="utf-8")
    pre = read_json(workdir / "preflight.json")
    assert read_json(workdir / "last-run.json") == {
        "head": head, "run_id": pre["run_id"], "date": DATE, "committed": True}
    assert _git(repo, "status", "--porcelain") == ""
    assert _run(repo, "finish") == 2  # a finished run is not finished twice


def test_no_docs_stops_with_phase_b_message(tmp_path: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})
    assert _run(repo, "start") == 0
    assert capsys.readouterr().out == (
        "no markdown docs in scope; no-docs mode arrives in phase B\n")
    workdir = repo / ".document-drift"
    assert read_json(workdir / "plan-docs.json") == []
    assert not (workdir / "tokens.json").exists()
    assert _run(repo, "finish") == 0
    assert "No branch created" in capsys.readouterr().out
    assert not (workdir / "last-run.json").exists()


def test_check_mode_exits_1_without_changes_or_record(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    (repo / "notes.txt").write_text("local work\n", encoding="utf-8")  # --check allows dirt
    _through_verify(repo, "--check")
    capsys.readouterr()
    assert _run(repo, "finish") == 1
    out = capsys.readouterr().out
    assert "Planned edits:" in out and "Exit: 1 (accepted edits exist)" in out
    workdir = repo / ".document-drift"
    assert (repo / "README.md").read_text(encoding="utf-8") == README
    assert (repo / "docs" / "config.md").read_text(encoding="utf-8") == CONFIG
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    assert _git(repo, "branch", "--list", BRANCH) == ""
    assert not (workdir / "last-run.json").exists()
    assert not (workdir / "applied.json").exists()
    assert not (workdir / "commits.json").exists()


def test_check_mode_exits_0_when_every_edit_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _start_and_answer(repo, "--check")
    assert _run(repo, "verify") == 0
    for entry in _plan(repo, "plan-verify.json"):
        verdicts = read_json(CANNED / "verdicts" / Path(entry["output"]).name)
        for verdict in verdicts["verdicts"]:
            verdict["verdict"] = "reject"
        Path(entry["output"]).write_text(json.dumps(verdicts), encoding="utf-8")
    assert _run(repo, "finish") == 0


def test_finish_refuses_when_tree_changed_outside_workdir(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _through_verify(repo)
    (repo / "helper.py").write_text("print('agent helper')\n", encoding="utf-8")
    (repo / "src" / "app.py").write_text(APP + "# touched\n", encoding="utf-8")
    capsys.readouterr()
    assert _run(repo, "finish") == 2
    err = capsys.readouterr().err
    assert "helper.py" in err and "src/app.py" in err
    assert (repo / "README.md").read_text(encoding="utf-8") == README
    assert _git(repo, "branch", "--list", BRANCH) == ""


def test_check_finish_refuses_a_dirty_file_that_changed_again(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "notes.txt").write_text("local work\n", encoding="utf-8")
    _through_verify(repo, "--check")
    assert _run(repo, "finish") == 1  # unchanged dirt is fine; the finish leaves no state
    (repo / "notes.txt").write_text("changed during the run\n", encoding="utf-8")
    _through_verify(repo, "--check")
    (repo / "notes.txt").write_text("changed again\n", encoding="utf-8")
    assert _run(repo, "finish") == 2


def test_empty_plan_allows_finish_after_start(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    assert _run(repo, "start", "--base", "HEAD") == 0
    workdir = repo / ".document-drift"
    assert capsys.readouterr().out == (
        f"plan-docs.json {(workdir / 'plan-docs.json').as_posix()} with 0 entries\n")
    assert _plan(repo, "plan-docs.json") == []
    assert _run(repo, "finish") == 0
    assert "No branch created" in capsys.readouterr().out
    assert _git(repo, "symbolic-ref", "--short", "HEAD").strip() == "main"
    record = read_json(workdir / "last-run.json")
    assert (record["head"], record["committed"]) == (head, False)


def test_empty_plan_finish_still_applies_notice_edits(tmp_path: Path) -> None:
    block = "The service is fast and reliable."
    notice = render_notice(1, "2026-01-01-0000", block_hash(block))
    repo = _repo(tmp_path, {**FILES, "README.md": f"{README}\n{notice}\n{block}\n"})
    assert _run(repo, "start", "--base", "HEAD") == 0
    assert _plan(repo, "plan-docs.json") == []
    assert _run(repo, "finish") == 0
    commits = read_json(repo / ".document-drift" / "commits.json")
    assert [c["kind"] for c in commits["commits"]] == ["corrections"]
    text = (repo / "README.md").read_text(encoding="utf-8")
    assert "drift-unverified: 2nd notice" in text and block in text


def test_second_run_is_later_run_from_drift_base(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    _through_verify(repo)
    assert _run(repo, "finish") == 0
    drift_head = _git(repo, "rev-parse", "HEAD").strip()
    (repo / ".document-drift" / "last-run.json").unlink()  # only the commit names the base
    assert _run(repo, "start", "--branch", "docs/drift-second") == 0
    workdir = repo / ".document-drift"
    changes = read_json(workdir / "changes.json")
    assert (changes["mode"], changes["last_run"], changes["last_run_source"]) == (
        "later", head, "commit")
    assert changes["changed_files"] == ["README.md", "docs/config.md"]
    pre = read_json(workdir / "preflight.json")
    assert (pre["head"], pre["scope"]) == (drift_head, f"since {head}")
    digest = hashlib.sha256(f"{drift_head}:since {head}:{DATE}".encode()).hexdigest()[:4]
    assert pre["run_id"] == f"{DATE}-{digest}"
    plan = _plan(repo, "plan-docs.json")
    assert [e["role"] for e in plan] == ["review"]  # the changed sections; no new names
    assert "Since commit" in Path(plan[0]["prompt"]).read_text(encoding="utf-8")


def test_crashed_step_exits_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)

    def boom(*_args: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(dd_units, "run", boom)
    assert _run(repo, "start") == 5
    err = capsys.readouterr().err
    assert "step units crashed: RuntimeError: kaboom" in err
    assert "Traceback" in err
    assert "git status" not in err  # nothing was edited at start
    assert _run(repo, "verify") == 2  # an unfinished start is not a start


def test_step_without_its_output_exits_5(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(dd_units, "run", lambda *_args: None)
    assert _run(repo, "start") == 5
    assert "step units did not write" in capsys.readouterr().err


def test_preflight_refusal_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    (repo / "README.md").write_text("dirty\n", encoding="utf-8")
    assert _run(repo, "start") == 2
    assert "not clean" in capsys.readouterr().err


def test_unknown_base_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start", "--base", "no-such-ref") == 2
    assert "--base" in capsys.readouterr().err


HINT = "docs may already be edited and the branch may exist: check git status and git branch"


def test_commit_step_exit_5_names_the_step_and_points_to_git(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _through_verify(repo)

    def refuse(*_args: object) -> None:
        raise StepError("add edit g001-e01 names 'X', which matches no gap", EXIT_MISSING)

    monkeypatch.setattr(dd_commit, "run", refuse)
    capsys.readouterr()
    assert _run(repo, "finish") == 5
    err = capsys.readouterr().err
    assert "error: step commit: add edit g001-e01" in err and HINT in err
    assert "It retries 3 times" in (repo / "README.md").read_text(encoding="utf-8")
    assert not (repo / ".document-drift" / "last-run.json").exists()


def test_summary_crash_after_the_commits_still_finishes_the_run(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _through_verify(repo)

    def boom(*_args: object) -> None:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(dd_summary, "run", boom)
    capsys.readouterr()
    assert _run(repo, "finish") == 5
    err = capsys.readouterr().err
    assert "step summary crashed: RuntimeError: kaboom" in err and HINT in err
    workdir = repo / ".document-drift"
    assert read_json(workdir / "preflight.json")["stage"] == "finish"
    assert read_json(workdir / "last-run.json")["committed"] is True
    assert _run(repo, "finish") == 2


@pytest.mark.parametrize("stage", ["start", "finish"])
def test_crash_outside_a_step_points_to_git_only_at_finish(
        tmp_path: Path, stage: str, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    if stage == "finish":
        _through_verify(repo)

    def broken(_text: str) -> None:
        raise OSError("stdout closed")

    monkeypatch.setattr(dd_run, "_write_stdout", broken)
    capsys.readouterr()
    assert _run(repo, stage) == 5
    err = capsys.readouterr().err
    assert f"the {stage} stage crashed outside a step: OSError: stdout closed" in err
    assert (HINT in err) is (stage == "finish")


def test_refused_start_keeps_the_previous_run(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    _through_verify(repo)
    assert _run(repo, "finish") == 0
    _git(repo, "switch", "-q", "main")
    capsys.readouterr()
    assert _run(repo, "start") == 2  # the drift branch of this date exists
    assert "already exists" in capsys.readouterr().err
    workdir = repo / ".document-drift"
    for name in ("applied.json", "commits.json", "edits.json", "summary.md", "last-run.json"):
        assert (workdir / name).is_file(), name
    assert not (workdir / "preflight.json").exists()
    assert _run(repo, "verify") == 2


def test_untracked_files_hidden_by_status_config_are_compared_too(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "config", "status.showUntrackedFiles", "no")
    (repo / "notes.txt").write_text("before the run\n", encoding="utf-8")
    _through_verify(repo)  # preflight's clean check does not see notes.txt
    assert "notes.txt" in read_json(repo / ".document-drift" / "preflight.json")["dirty"]
    (repo / "helper.py").write_text("print('agent helper')\n", encoding="utf-8")
    assert _run(repo, "finish") == 2
    (repo / "helper.py").unlink()
    assert _run(repo, "finish") == 0
