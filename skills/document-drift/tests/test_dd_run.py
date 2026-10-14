"""The staged driver (spec 2, 3) on a small repository with canned agent outputs.

The canned outputs under ``tests/canned/small`` quote the fixture docs below line for line;
change both together.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import dd_cite
import dd_commit
import dd_run
import dd_summary
import dd_units
import pytest
from dd_common import EXIT_MISSING, StepError, read_json, write_json
from dd_config import DEFAULTS
from dd_corpus import answer
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


def _answer(repo: Path, name: str, invalid: bool = False) -> None:
    """Write the canned output of every entry of plan ``name`` to its output path; with
    ``invalid``, the entries with a canned invalid output get that instead."""
    answer(repo / ".document-drift", name, CANNED, CANNED / "invalid" if invalid else None)


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
    assert out == ("readme: no\n"
                   f"plan-docs.json {(workdir / 'plan-docs.json').as_posix()} with 2 entries\n")
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
    assert pre["readme"] is False
    assert not (workdir / "areas.json").exists()
    for name in ("inventory.json", "tokens.json", "candidates.json", "defindex.json",
                 "anchors.json", "changes.json", "units.json", "patterns.json", "gaps.json",
                 "notices.json"):
        assert (workdir / name).is_file(), name


def test_start_clears_every_pinned_output(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    workdir = repo / ".document-drift"
    stales = ("edits.json", "retry.json", "summary.md", "review/u009.json",
              "verdicts/v09.json", "prompts/verify-v09.md", "gaps/g009.json",
              "areas.json", "sheets.json", "plan-readme.json", "readme.json",
              "sheets/a09.json", "readme/r001.json")
    for stale in stales:
        (workdir / stale).parent.mkdir(parents=True, exist_ok=True)
        (workdir / stale).write_text("stale", encoding="utf-8")
    assert _run(repo, "start") == 0  # the repository has a README: no phase B file is rewritten
    for stale in stales:
        assert not (workdir / stale).exists(), stale
    assert not (workdir / "sheets").exists() and not (workdir / "readme").exists()


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
    _answer(repo, "plan-docs.json", invalid=True)
    assert _run(repo, "verify") == 3
    assert [e["id"] for e in read_json(repo / ".document-drift" / "retry.json")] == ["u001"]


def test_retried_marks_unit_unchecked(tmp_path: Path,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start") == 0
    _answer(repo, "plan-docs.json", invalid=True)
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
    repo = _repo(tmp_path, {"src/app.py": APP, ".document-drift.yaml": "readme: false\n"})
    assert _run(repo, "start") == 0
    assert capsys.readouterr().out == (
        "readme: no\nno markdown docs in scope; no-docs mode arrives in phase B\n")
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


def test_finish_refuses_when_head_moved_before_any_change(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # spec 2: exit 2 is refused before any change; a clean switch leaves the tree clean, so
    # only the HEAD comparison catches it, and it must come before apply
    repo = _repo(tmp_path)
    head = _git(repo, "rev-parse", "HEAD").strip()
    _through_verify(repo)
    _git(repo, "switch", "-q", "-c", "elsewhere")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "other work")
    moved = _git(repo, "rev-parse", "HEAD").strip()
    capsys.readouterr()
    assert _run(repo, "finish") == 2
    err = capsys.readouterr().err
    assert head in err and moved in err
    assert (repo / "README.md").read_text(encoding="utf-8") == README
    assert (repo / "docs" / "config.md").read_text(encoding="utf-8") == CONFIG
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "branch", "--list", BRANCH) == ""
    assert not (repo / ".document-drift" / "applied.json").exists()


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
        f"readme: no\nplan-docs.json {(workdir / 'plan-docs.json').as_posix()} with 0 entries\n")
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


# a citation of `connect` at line 9, where `main` now starts (connect is at lines 4-6), and a
# fact table whose one row agrees with the scan
MOVED = "The retry loop lives in `connect` (`src/app.py:9`).\n"
TABLE = "\n| Variable | Default |\n|---|---|\n| `APP_HOST` | - |\n"


def test_start_runs_cite_and_facts_and_clears_their_output(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {**FILES, "README.md": f"{README}\n{MOVED}",
                            "docs/config.md": CONFIG + TABLE})
    workdir = repo / ".document-drift"
    assert _run(repo, "start") == 0
    script = read_json(workdir / "script-edits.json")
    assert [(e["id"], e["type"], e["doc"], e["start_line"]) for e in script["edits"]] == [
        ("c001", "cite", "README.md", 9)]
    assert "(`src/app.py:4`)" in script["edits"][0]["new"]
    assert script["counts"]["citations"]["moved"] == 1
    assert script["counts"]["facts"]["rows_checked"] == 1  # dd_facts ran after dd_cite
    (workdir / "script-edits.json").write_text("stale", encoding="utf-8")
    assert _run(repo, "start") == 0  # a later start rewrites it
    assert read_json(workdir / "script-edits.json") == script
    monkeypatch.setattr(dd_cite, "run", lambda *_args: None)
    capsys.readouterr()
    assert _run(repo, "start") == 5  # start cleared it, and cite did not write it again
    assert "step cite did not write" in capsys.readouterr().err
    monkeypatch.undo()
    _through_verify(repo)
    edits = {e["id"]: e for e in read_json(workdir / "edits.json")["edits"]}
    assert (edits["c001"]["source"], edits["c001"]["status"]) == ("script", "kept")
    assert all("c001" not in p["edits"] for p in _plan(repo, "plan-verify.json"))
    assert _run(repo, "finish") == 0
    on_branch = _git(repo, "show", f"{BRANCH}:README.md")
    assert "The retry loop lives in `connect` (`src/app.py:4`)." in on_branch
    assert "It retries 3 times by default." in on_branch


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


def test_not_reviewed_ranges_are_re_dispatched_as_a_retry_unit(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    answer(workdir, "plan-docs.json", CANNED, CANNED / "not-reviewed")
    capsys.readouterr()
    assert _run(repo, "verify") == 3
    retry = read_json(workdir / "retry.json")
    assert [(e["id"], e["role"]) for e in retry] == [("u002", "review")]
    assert capsys.readouterr().out == (
        f"retry.json {(workdir / 'retry.json').as_posix()} with 1 entries\n")
    units = read_json(workdir / "units.json")["units"]
    assert [(u["id"], u.get("retry_of"), u["docs"]) for u in units][1:] == [
        ("u002", "u001", [{"doc": "docs/config.md", "ranges": [[1, 5]]}])]
    assert [e["id"] for e in _plan(repo, "plan-docs.json")] == ["u001", "g001", "u002"]
    assert "docs/config.md (5 lines): lines 1-5" in Path(retry[0]["prompt"]).read_text(
        encoding="utf-8")
    assert not (workdir / "edits.json").exists()
    answer(workdir, "retry.json", CANNED)
    assert _run(repo, "verify", "--retried") == 0
    edits = read_json(workdir / "edits.json")
    assert edits["unchecked_units"] == [] and edits["not_reviewed"] == []
    assert [e["id"] for e in edits["edits"]] == ["u001-e01", "g001-e01"]


def test_not_reviewed_after_retry_is_listed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "start", "--check") == 0
    workdir = repo / ".document-drift"
    answer(workdir, "plan-docs.json", CANNED, CANNED / "not-reviewed")
    assert _run(repo, "verify") == 3
    answer(workdir, "retry.json", CANNED, CANNED / "not-reviewed")
    assert _run(repo, "verify", "--retried") == 0
    assert read_json(workdir / "edits.json")["not_reviewed"] == [
        {"unit": "u002", "doc": "docs/config.md", "start_line": 5, "end_line": 5,
         "why": "still too much"}]
    _answer(repo, "plan-verify.json")
    assert _run(repo, "finish", "--check") == 1
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert ("checked 2, unchecked by cap 0, unchecked after retry 0, retry units 1, "
            "not reviewed 1 ranges\n- docs/config.md:5-5 (still too much)") in summary


# ---------------------------------------------------------------- phase B: README mode

def _repo_no_readme(tmp_path: Path) -> Path:
    return _repo(tmp_path, {k: v for k, v in FILES.items() if k != "README.md"})


def _sheet_entry(repo: Path) -> dict[str, Any]:
    return next(e for e in _plan(repo, "plan-docs.json") if e["role"] == "sheet")


def test_readme_trigger_is_root_markdown_only(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    config = copy.deepcopy(DEFAULTS)
    assert dd_run.readme_wanted({"docs": ["docs/README.md"]}, config)
    assert dd_run.readme_wanted({"docs": []}, config)
    assert not dd_run.readme_wanted({"docs": ["Readme.MD", "docs/guide.md"]}, config)
    assert not dd_run.readme_wanted({"docs": ["README.md"]}, config)
    assert not dd_run.readme_wanted({"docs": [], "files": ["README.md", "src/app.py"]}, config)
    assert dd_run.readme_wanted({"docs": [], "files": ["docs/README.md"]}, config)
    config["readme"] = False
    assert not dd_run.readme_wanted({"docs": ["docs/README.md"]}, config)
    repo = _repo(tmp_path, {"src/app.py": APP, "docs/README.md": CONFIG,
                            ".document-drift.yaml": "readme: false\n"})
    assert _run(repo, "start") == 0
    assert capsys.readouterr().out.startswith("readme: no\n")
    assert read_json(repo / ".document-drift" / "preflight.json")["readme"] is False


def test_start_in_readme_mode_plans_sheets_and_prints_readme_yes(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_no_readme(tmp_path)
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    plan = _plan(repo, "plan-docs.json")
    assert capsys.readouterr().out == (
        f"readme: yes\nplan-docs.json {(workdir / 'plan-docs.json').as_posix()} with "
        f"{len(plan)} entries\n")
    assert [e["role"] for e in plan][-1:] == ["sheet"] and "review" in {e["role"] for e in plan}
    sheet = _sheet_entry(repo)
    assert sheet["id"] == "a01" and sheet["output"].endswith("/sheets/a01.json")
    assert "src/app.py" in Path(sheet["prompt"]).read_text(encoding="utf-8")
    assert read_json(workdir / "preflight.json")["readme"] is True
    assert [a["id"] for a in read_json(workdir / "areas.json")["areas"]] == ["a01"]


def test_start_with_no_doc_and_readme_runs_the_full_steps(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})
    assert _run(repo, "start") == 0
    out = capsys.readouterr().out
    assert out.startswith("readme: yes\n") and "no markdown docs" not in out
    workdir = repo / ".document-drift"
    assert (workdir / "patterns.json").is_file() and (workdir / "areas.json").is_file()
    assert [(e["id"], e["role"]) for e in _plan(repo, "plan-docs.json")] == [("a01", "sheet")]
    assert read_json(workdir / "preflight.json")["stage"] == "start"


def test_compose_refuses_without_readme_and_before_start(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert _run(repo, "compose") == 2
    assert "run --stage start first" in capsys.readouterr().err
    assert _run(repo, "start") == 0
    capsys.readouterr()
    assert _run(repo, "compose") == 2
    assert ("error: nothing to compose: this run writes no README"
            in capsys.readouterr().err)
    assert not (repo / ".document-drift" / "plan-readme.json").exists()
    other = _repo_no_readme(tmp_path / "other")
    assert _run(other, "start") == 0
    capsys.readouterr()
    assert main([str(other), "--stage", "compose", "--check"]) == 2
    assert "--check" in capsys.readouterr().err
    assert not (other / ".document-drift" / "sheets.json").exists()


def test_compose_retries_a_bad_sheet_then_plans_the_writer(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_no_readme(tmp_path)
    _start_and_answer(repo)
    workdir = repo / ".document-drift"
    sheet = _sheet_entry(repo)
    Path(sheet["output"]).unlink()
    capsys.readouterr()
    assert _run(repo, "compose") == 3
    assert read_json(workdir / "retry.json") == [sheet]
    assert capsys.readouterr().out == (
        f"retry.json {(workdir / 'retry.json').as_posix()} with 1 entries\n")
    assert not (workdir / "sheets.json").exists()
    answer(workdir, "retry.json", CANNED)
    assert _run(repo, "compose", "--retried") == 0
    assert capsys.readouterr().out == (
        f"plan-readme.json {(workdir / 'plan-readme.json').as_posix()} with 1 entries\n")
    plan = _plan(repo, "plan-readme.json")
    assert [(e["id"], e["role"]) for e in plan] == [("r001", "readme")]
    prompt = Path(plan[0]["prompt"]).read_text(encoding="utf-8")
    assert "a01-s01" in prompt and "`APP_HOST`" in prompt
    sheets = read_json(workdir / "sheets.json")
    assert list(sheets["sheets"]) == ["a01"] and sheets["unchecked"] == []
    assert read_json(workdir / "preflight.json")["stage"] == "compose"


def test_compose_fills_hints_missing_after_the_retry(tmp_path: Path) -> None:
    repo = _repo_no_readme(tmp_path)
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    short = read_json(CANNED / "sheets" / "a01.json")
    short["surface"] = [e for e in short["surface"] if e["name"] != "APP_TOKEN"]
    write_json(Path(_sheet_entry(repo)["output"]), short)
    assert _run(repo, "compose") == 3
    assert [e["id"] for e in read_json(workdir / "retry.json")] == ["a01"]
    assert _run(repo, "compose", "--retried") == 0
    sheets = read_json(workdir / "sheets.json")
    assert sheets["filled"] == 1 and sheets["unchecked"] == []
    filled = [e for e in sheets["sheets"]["a01"]["surface"] if e.get("filled")]
    assert [(e["kind"], e["name"]) for e in filled] == [("env", "APP_TOKEN")]


def test_compose_with_no_valid_sheet_plans_nothing(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_no_readme(tmp_path)
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    assert _run(repo, "compose") == 3
    capsys.readouterr()
    assert _run(repo, "compose", "--retried") == 0
    assert capsys.readouterr().out == "readme: no sheet; nothing to compose\n"
    assert _plan(repo, "plan-readme.json") == []
    assert read_json(workdir / "sheets.json")["unchecked"] == [
        {"area": "a01", "why": "invalid after retry"}]
    assert read_json(workdir / "preflight.json")["stage"] == "compose"


def test_verify_refuses_before_compose_in_readme_mode(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_no_readme(tmp_path)
    _start_and_answer(repo)
    workdir = repo / ".document-drift"
    capsys.readouterr()
    assert _run(repo, "verify") == 2
    assert "error: compose has not run; run --stage compose first" in capsys.readouterr().err
    assert _run(repo, "finish") == 2
    assert "compose has not run" in capsys.readouterr().err
    assert not (workdir / "edits.json").exists()
    assert _run(repo, "compose") == 0
    assert _run(repo, "finish") == 2  # verify has not run
    capsys.readouterr()
    assert _run(repo, "verify") == 3  # the writer's output is missing
    retry = read_json(workdir / "retry.json")
    assert [(e["id"], e["role"]) for e in retry] == [("r001", "readme")]


@pytest.mark.parametrize("files", [
    {"README.md": README, ".document-drift.yaml": 'exclude: ["README.md"]\n'},
    {"README.md": f"<!-- drift-ignore-file: kept by hand -->\n{README}"}],
    ids=["config-exclude", "ignore-marker"])
def test_excluded_root_readme_does_not_trigger(tmp_path: Path, files: dict[str, str],
                                               capsys: pytest.CaptureFixture[str]) -> None:
    # spec 2: the skill may not edit an excluded README, so it writes none either
    repo = _repo(tmp_path, {"src/app.py": APP, "docs/config.md": CONFIG, **files})
    assert _run(repo, "start") == 0
    workdir = repo / ".document-drift"
    inventory = read_json(workdir / "inventory.json")
    assert "README.md" not in inventory["docs"]
    assert "README.md" in [e["path"] for e in inventory["excluded"]]
    assert capsys.readouterr().out.startswith("readme: no\n")
    assert read_json(workdir / "preflight.json")["readme"] is False
    assert not (workdir / "areas.json").exists()


def test_readme_below_the_root_still_triggers(tmp_path: Path,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP, "docs/README.md": CONFIG})
    assert _run(repo, "start") == 0
    assert capsys.readouterr().out.startswith("readme: yes\n")
    assert read_json(repo / ".document-drift" / "preflight.json")["readme"] is True


def test_verify_in_readme_mode_checks_the_writer_output_and_plans_batches(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})  # no doc at all: README mode past exit 3
    workdir = repo / ".document-drift"
    _start_and_answer(repo)
    assert _run(repo, "compose") == 0
    _answer(repo, "plan-readme.json")
    capsys.readouterr()
    assert _run(repo, "verify") == 0
    plan = _plan(repo, "plan-verify.json")
    assert capsys.readouterr().out == (
        f"plan-verify.json {(workdir / 'plan-verify.json').as_posix()} with 3 entries\n")
    assert [(e["id"], e["role"], e["statements"]) for e in plan] == [
        ("v01", "verify", ["r-s001"]), ("v02", "verify", ["r-s002", "r-s003"]),
        ("v03", "verify", ["r-s004", "r-s005"])]
    assert all(Path(e["prompt"]).is_file() for e in plan)
    readme = read_json(workdir / "readme.json")
    assert readme["cites_added"] == 1 and readme["cited_unnamed"] == 0
    assert [(s["kind"], s["section"]) for s in readme["statements"]] == [
        ("paragraph", "demo"), ("row", "Environment variables"),
        ("row", "Environment variables"), ("item", "Functions"), ("item", "Functions")]
    edits = read_json(workdir / "edits.json")
    assert [(e["id"], e["type"], e["source"], e["status"], e["statements"])
            for e in edits["edits"]] == [("r001", "create", "readme", "kept", 5)]
    assert edits["human"] == []
    assert read_json(workdir / "preflight.json")["stage"] == "verify"
    _answer(repo, "plan-verify.json")  # canned statement verdicts validate
    assert all(not dd_run.dd_dispatch._problems(workdir, e) for e in plan)


def test_invalid_writer_output_is_retried_then_no_readme(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_no_readme(tmp_path)
    workdir = repo / ".document-drift"
    _start_and_answer(repo)
    assert _run(repo, "compose") == 0
    writer = _plan(repo, "plan-readme.json")[0]
    bad = read_json(CANNED / "readme" / "r001.json")
    bad["text"] = bad["text"].replace("# demo", "## demo", 1)
    write_json(Path(writer["output"]), bad)
    capsys.readouterr()
    assert _run(repo, "verify") == 3
    assert read_json(workdir / "retry.json") == [writer]
    assert not (workdir / "readme.json").exists()
    assert _run(repo, "verify", "--retried") == 0  # the retry's output is still bad
    assert read_json(workdir / "readme.json") == {
        "invalid": ["the first line is not a level-one heading"], "attempts": 2}
    edits = read_json(workdir / "edits.json")
    assert all(e["type"] != "create" for e in edits["edits"])
    assert all("statements" not in e for e in _plan(repo, "plan-verify.json"))
    assert read_json(workdir / "preflight.json")["stage"] == "verify"


def _through_readme_verify(repo: Path, *extra: str) -> None:
    """``start`` (with ``extra``), the canned sheet, ``compose``, the canned writer output,
    ``verify`` and the canned statement verdicts (``verdicts/readme.json`` rejects r-s003)."""
    _start_and_answer(repo, *extra)
    assert _run(repo, "compose") == 0
    _answer(repo, "plan-readme.json")
    assert _run(repo, "verify") == 0
    _answer(repo, "plan-verify.json")


def test_finish_writes_the_readme_and_commits_it(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})  # no doc at all
    workdir = repo / ".document-drift"
    _through_readme_verify(repo)
    assert _run(repo, "finish") == 0
    rejected = "| `APP_TOKEN` | the token the app sends to the server |"
    assert rejected in read_json(workdir / "readme.json")["text"]
    on_branch = _git(repo, "show", f"{BRANCH}:README.md")
    assert rejected not in on_branch and "| `APP_HOST` |" in on_branch
    assert on_branch == (repo / "README.md").read_text(encoding="utf-8")
    applied = read_json(workdir / "applied.json")
    assert applied["applied"] == ["r001"]
    assert applied["readme"] == {"lines": len(on_branch.splitlines()), "statements": 4,
                                 "removed": 1}
    commits = read_json(workdir / "commits.json")
    assert commits["branch"] == BRANCH
    assert [c["kind"] for c in commits["commits"]] == ["additions"]
    sha = commits["commits"][0]["sha"]
    assert "README.md" in _git(repo, "show", "--stat", "--format=", sha)
    message = _git(repo, "log", "-1", "--format=%B", sha)
    assert "\n- README.md:1 create readme (5 statements from 1 sheets, 1 removed)\n" in message
    human = dd_commit.collect_human(workdir, repo)
    assert [(h["doc"], h["line"], h["kind"], h["evidence"]) for h in human] == [
        ("README.md", 10, "readme-rejected",
         ["main reads APP_TOKEN but nothing sends it to the server"])]
    assert "README.md:10 readme-rejected" in message
    assert _git(repo, "status", "--porcelain") == ""


def test_check_mode_lists_the_readme_and_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})
    head = _git(repo, "rev-parse", "HEAD").strip()
    workdir = repo / ".document-drift"
    _through_readme_verify(repo, "--check")
    assert _run(repo, "finish") == 1
    assert not (repo / "README.md").exists()
    assert _git(repo, "branch", "--list", BRANCH) == ""
    assert _git(repo, "rev-parse", "HEAD").strip() == head
    assert not (workdir / "applied.json").exists()
    assert not (workdir / "commits.json").exists()


def test_retry_counts_survive_a_later_stage_retry(tmp_path: Path) -> None:
    # retry.json holds only the latest exit 3: compose records the retried sheets in
    # sheets.json and verify the writer's attempts in readme.json, for the summary
    repo = _repo(tmp_path, {"src/app.py": APP})
    workdir = repo / ".document-drift"
    _start_and_answer(repo)
    Path(_sheet_entry(repo)["output"]).unlink()
    assert _run(repo, "compose") == 3
    answer(workdir, "retry.json", CANNED)
    assert _run(repo, "compose", "--retried") == 0
    assert read_json(workdir / "sheets.json")["retried"] == ["a01"]
    writer = _plan(repo, "plan-readme.json")[0]
    assert _run(repo, "verify") == 3  # no writer output yet
    assert read_json(workdir / "retry.json") == [writer]
    answer(workdir, "retry.json", CANNED)
    assert _run(repo, "verify", "--retried") == 0
    assert read_json(workdir / "readme.json")["attempts"] == 2
    _answer(repo, "plan-verify.json")
    assert _run(repo, "finish") == 0
    summary = (workdir / "summary.md").read_text(encoding="utf-8")
    assert "sheets: 1 valid, 0 unchecked, 1 retried\n" in summary
    assert "writer: 2 attempts\n" in summary


def test_first_pass_counts_one_attempt_and_no_retried_sheet(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"src/app.py": APP})
    workdir = repo / ".document-drift"
    _through_readme_verify(repo)
    assert read_json(workdir / "sheets.json")["retried"] == []
    assert read_json(workdir / "readme.json")["attempts"] == 1


@pytest.mark.parametrize("name", ["README.md", "readme.MD"])
def test_untracked_root_readme_on_disk_turns_readme_mode_off(
        tmp_path: Path, name: str, capsys: pytest.CaptureFixture[str]) -> None:
    # finish would overwrite an untracked draft README: README mode is off
    repo = _repo(tmp_path, {"src/app.py": APP, "docs/config.md": CONFIG})
    _git(repo, "config", "status.showUntrackedFiles", "no")  # preflight's clean check passes
    (repo / name).write_text("# draft\n", encoding="utf-8")
    assert dd_run.readme_wanted({"docs": [], "files": []}, copy.deepcopy(DEFAULTS), repo) is False
    assert _run(repo, "start") == 0
    assert capsys.readouterr().out.startswith("readme: no\n")
    assert read_json(repo / ".document-drift" / "preflight.json")["readme"] is False
    assert not (repo / ".document-drift" / "areas.json").exists()
