"""The live harness's offline parts (spec 11.3): argument parsing, the evaluation-log row and the
refusal without a ``claude`` launcher. No test here calls a model; the harness itself refuses to
dispatch an agent under pytest.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import dd_live_run
import pytest
from dd_live_run import (
    COLUMNS,
    HEADER,
    Call,
    append_row,
    check_log,
    live_run,
    main,
    parse_args,
    render_row,
    resolve_target,
    score,
)


def _write(workdir: Path, name: str, data: Any) -> None:
    path = workdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _edit(eid: str, source: str, status: str, kind: str, line: int) -> dict[str, Any]:
    return {"id": eid, "doc": "README.md", "start_line": line, "end_line": line, "old": "a",
            "new": "b", "type": kind, "claim": f"claim {eid}", "evidence": [],
            "subject": None, "source": source, "status": status, "check": None,
            "human_kind": None, "reason": None}


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    wd = tmp_path / ".document-drift"
    _write(wd, "preflight.json", {"head": "0123456789abcdef0123456789abcdef01234567",
                                  "run_id": "2026-01-02-3f03", "check": False})
    _write(wd, "inventory.json", {"docs": [{"path": "README.md"}, {"path": "docs/a.md"},
                                           {"path": "docs/b.md"}], "excluded": []})
    _write(wd, "changes.json", {"mode": "first", "scope": "first", "affected": {},
                                "review": {"README.md": [[1, 9]], "docs/a.md": [[1, 3]],
                                           "docs/b.md": [[1, 4]]}})
    _write(wd, "units.json", {"units": [{"id": "u001"}, {"id": "u002"}], "unchecked": []})
    edits = [_edit("u001-e01", "review", "kept", "correct", 3),
             _edit("u001-e02", "review", "kept", "remove", 5),
             _edit("u001-e03", "review", "dropped", "anchor", 7),
             _edit("g001-e01", "gap", "kept", "add", 9),
             _edit("n001", "notice", "kept", "notice", 11)]
    _write(wd, "edits.json", {"edits": edits, "human": [
        {"doc": "README.md", "line": 2, "kind": "guarantee-mismatch", "text": "never blocks",
         "evidence": []}]})
    _write(wd, "verdicts.json", {"verdicts": {
        "u001-e01": {"verdict": "accept", "reason": "ok"},
        "u001-e02": {"verdict": "reject", "reason": "wrong"},
        "g001-e01": {"verdict": "accept", "reason": "ok"}}, "unverified": ["u009-e01"]})
    _write(wd, "applied.json", {"applied": ["u001-e01", "g001-e01", "n001"], "reverted": []})
    _write(wd, "gaps.json", {"gaps": [{"name": "init", "gap_kind": "undocumented"},
                                      {"name": "X", "gap_kind": "missing-from-list"},
                                      {"name": "Y", "gap_kind": "undocumented"}]})
    return wd


def _cells(row: str) -> dict[str, str]:
    """The row's cells by column name."""
    assert row.startswith("| ") and row.endswith(" |\n")
    cells = [c.strip() for c in row[2:-3].split(" | ")]
    return dict(zip(COLUMNS, cells, strict=True))


def test_row_format(workdir: Path) -> None:
    calls = [Call("review", "u001", "sonnet", 60.0, 1000, 0.5, "ok"),
             Call("review", "u002", "sonnet", 70.0, 2000, 0.25, "ok"),
             Call("gap", "g001", "sonnet", 30.0, None, 0.1, "ok"),
             Call("verify", "v01", "opus", 40.0, 500, 1.0, "ok")]
    row = render_row(workdir, date="2026-10-13", repository="py-service", calls=calls,
                     wall_seconds=754.2, planted=(9, 11), decoys=(1, 8),
                     notes="missed p3 | p14")
    assert HEADER.startswith("| date |") and " | applied | judged acceptable | " in HEADER
    assert _cells(row) == {
        "date": "2026-10-13", "repository": "py-service", "head": "0123456",
        "mode": "first", "docs": "3", "affected": "3", "units": "2",
        "edits proposed": "5 (3/1/1)", "kept": "4", "verdicts": "2/1/0/1", "applied": "3",
        "judged acceptable": "-", "human": "2", "notices placed": "1", "gaps": "2/1",
        "planted caught": "9/11", "decoys touched": "1/8", "agents": "2/1/1",
        "wall time": "12m34s", "tokens": "3500", "cost usd": "1.85",
        "notes": "missed p3 \\| p14",
    }


def test_row_format_without_scoring_or_tokens(workdir: Path) -> None:
    _write(workdir, "changes.json", {"mode": "later", "scope": "since abc", "review": {},
                                     "affected": {"README.md": {}}})
    calls = [Call("review", "u001", "sonnet", 5.0, None, 0.0, "ok")]
    cells = _cells(render_row(workdir, date="2026-10-13", repository="repo", calls=calls,
                              wall_seconds=5, planted=None, decoys=None, notes=""))
    assert (cells["mode"], cells["docs"], cells["affected"]) == ("later", "3", "1")
    assert cells["planted caught"] == cells["decoys touched"] == "-"
    assert cells["tokens"] == cells["notes"] == cells["judged acceptable"] == "-"


def test_row_format_missing_files(tmp_path: Path) -> None:
    cells = _cells(render_row(tmp_path, date="2026-10-13", repository="repo", calls=[],
                              wall_seconds=0, planted=None, decoys=None, notes="stopped"))
    assert cells["head"] == cells["edits proposed"] == "-" and cells["notes"] == "stopped"


def _log_text(after_header: str) -> str:
    sep = "|" + "---|" * len(COLUMNS) + "\n"
    return ("# log\n\n| x |\n|---|\n\n## document-drift\n\nText.\n\n" + HEADER + sep
            + after_header + "\n## later\n\n| y |\n")


def test_append_row_into_the_section(tmp_path: Path) -> None:
    log = tmp_path / "log.md"
    old = "| 2026-10-01 | a |\n"
    log.write_bytes(_log_text(old).encode())
    append_row(log, "| new |\n")
    text = log.read_text(encoding="utf-8")
    assert old + "| new |\n\n## later" in text
    assert text.count("| new |") == 1
    log.write_bytes(text.replace("\n", "\r\n").encode())  # a CRLF checkout stays CRLF
    append_row(log, "| crlf |\n")
    raw = log.read_bytes().decode()
    assert "| new |\r\n| crlf |\r\n\r\n## later" in raw and "\r\r" not in raw
    assert raw.count("\n") == raw.count("\r\n")
    log.write_bytes(b"# log\n\n## document-drift\n\nno table\n")
    with pytest.raises(ValueError):
        check_log(log)


def test_append_row_anchors_on_the_header(tmp_path: Path) -> None:
    # another table later in the section must not receive the row
    log = tmp_path / "log.md"
    old = "| 2026-10-01 | a |\n"
    log.write_bytes(_log_text(old + "\nA note with its own table:\n\n| k | v |\n|---|---|\n")
                    .encode())
    append_row(log, "| new |\n")
    text = log.read_text(encoding="utf-8")
    assert old + "| new |\n\nA note" in text
    assert "|---|---|\n\n## later" in text


def test_score_skips_canned_only_and_finds_decoys_by_kind(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    items = [{"id": "p1", "kind": "flag-name"}, {"id": "p2", "kind": "count"},
             {"id": "dx", "kind": "count"},  # a d-prefixed id that is not a decoy
             {"id": "q1", "kind": "decoy"}, {"id": "q2", "kind": "excluded"},
             {"id": "p14", "kind": "wrong-correction", "canned_only": True},
             {"id": "d7", "kind": "decoy", "canned_only": True}]
    unmet = {"p2", "q2", "p14", "d7"}
    monkeypatch.setattr(dd_live_run, "load_planted", lambda name: {"state1": items})
    monkeypatch.setattr(dd_live_run, "evaluate",
                        lambda item, wd, state: ["unmet"] if item["id"] in unmet else [])
    result = score("any", 1, tmp_path)
    assert (result.caught, result.planted, result.touched, result.decoys) == (2, 3, 1, 2)
    assert result.notes() == ["missed p2", "touched q2", "canned-only: p14, d7"]


def test_crash_still_records_calls_and_logs_a_row(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    log = tmp_path / "log.md"
    log.write_bytes(_log_text("").encode())

    def crash(run: Any, check: bool, resume: str | None = None) -> None:
        run.workdir.mkdir(parents=True)
        run.calls.append(Call("review", "u001", "sonnet", 3.0, 10, 0.25, "ok"))
        raise RuntimeError("boom")

    monkeypatch.setattr(dd_live_run, "drive", crash)
    args = parse_args([str(repo)])
    assert live_run(args, "claude", None, repo, log) == 4
    record = json.loads((repo / ".document-drift" / "live-run.json").read_text("utf-8"))
    assert [c["id"] for c in record["calls"]] == ["u001"]
    rows = [ln for ln in log.read_text("utf-8").splitlines() if ln.startswith("| 20")]
    assert len(rows) == 1
    cells = _cells(rows[0] + "\n")
    assert cells["cost usd"] == "0.25" and "crashed: RuntimeError: boom" in cells["notes"]


def test_resume_reuses_the_recorded_calls(monkeypatch: pytest.MonkeyPatch,
                                          tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    workdir = repo / ".document-drift"
    workdir.mkdir(parents=True)
    log = tmp_path / "log.md"
    log.write_bytes(_log_text("").encode())
    earlier = Call("review", "u001", "sonnet", 3.0, 10, 0.25, "ok")
    workdir.joinpath("live-run.json").write_text(json.dumps(
        {"repo": str(repo), "calls": [asdict(earlier)], "row": ""}), encoding="utf-8")
    seen: list[tuple[Any, ...]] = []

    def resumed(run: Any, check: bool, resume: str | None = None) -> None:
        seen.append((resume, [c.id for c in run.calls]))
        run.calls.append(Call("verify", "v01", "opus", 2.0, 5, 0.5, "ok"))

    monkeypatch.setattr(dd_live_run, "drive", resumed)
    assert live_run(parse_args([str(repo), "--resume", "verify"]), "claude", None, repo,
                    log) == 0
    assert seen == [("verify", ["u001"])]
    rows = [ln for ln in log.read_text("utf-8").splitlines() if ln.startswith("| 20")]
    cells = _cells(rows[0] + "\n")
    assert cells["cost usd"] == "0.75"
    assert "resumed at verify with 1 earlier calls" in cells["notes"]
    # nothing to resume
    assert live_run(parse_args([str(tmp_path / "other"), "--resume", "finish"]), "claude",
                    None, tmp_path / "other", log) == 2


def test_fixture_name_or_path(tmp_path: Path) -> None:
    args = parse_args(["py-service", "--state", "2", "--budget", "1.5", "--keep", "k",
                       "--model-override", "haiku", "--check"])
    assert (args.target, args.state, args.budget, args.keep, args.model_override,
            args.check) == ("py-service", 2, 1.5, "k", "haiku", True)
    assert resolve_target("py-service") == ("py-service", None)
    assert resolve_target(str(tmp_path)) == (None, tmp_path)
    with pytest.raises(ValueError):
        resolve_target(str(tmp_path / "missing"))
    args = parse_args([str(tmp_path), "--from", "abc123", "--full", "--parallel", "2"])
    assert (args.from_sha, args.full, args.parallel, args.state) == ("abc123", True, 2, 1)


def test_refuses_bad_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dd_live_run, "resolve_claude", lambda claude: "claude")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the harness went past its argument checks")

    monkeypatch.setattr(dd_live_run, "live_run", boom)
    assert main([str(tmp_path / "missing")]) == 2
    assert main([str(tmp_path), "--state", "2"]) == 2
    assert main(["py-service", "--from", "abc", "--base", "main"]) == 2
    assert main(["py-service", "--log", str(tmp_path / "no-log.md")]) == 2


def test_refuses_without_claude(monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(dd_live_run, "resolve_claude", lambda claude: None)

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the harness went past the launcher check")

    monkeypatch.setattr(dd_live_run, "prepare_fixture", boom)
    monkeypatch.setattr(dd_live_run, "live_run", boom)
    assert main(["py-service"]) == 2
    assert "claude" in capsys.readouterr().err


def _fake_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, readme: bool,
              docs: int = 1) -> tuple[Any, list[str], list[list[str]]]:
    """A Run whose stages and waves are faked: the stage order and the ids dispatched."""
    workdir = tmp_path / "wd"
    workdir.mkdir(parents=True, exist_ok=True)
    _write(workdir, "preflight.json", {"readme": readme})
    for name in ("docs", "readme", "verify"):
        _write(workdir, f"plan-{name}.json",
               [{"id": f"{name}-1", "role": name, "model": "m", "prompt": "p", "output": "o"}]
               if name != "docs" or docs else [])
    stages: list[str] = []
    waves: list[list[str]] = []

    def stage(run: Any, args: list[str], allowed: tuple[int, ...]) -> tuple[int, str]:
        name = args[args.index("--stage") + 1]
        stages.append(name)
        lines = {"start": f"readme: {'yes' if readme else 'no'}\n"
                          f"plan-docs.json {workdir / 'plan-docs.json'} with {docs} entries\n",
                 "compose": f"plan-readme.json {workdir / 'plan-readme.json'} with 1 entries\n",
                 "verify": f"plan-verify.json {workdir / 'plan-verify.json'} with 1 entries\n",
                 "finish": ""}
        return 0, lines[name]

    def wave(entries: Any, **kwargs: Any) -> None:
        waves.append([e["id"] for e in entries])

    monkeypatch.setattr(dd_live_run, "_stage", stage)
    monkeypatch.setattr(dd_live_run, "dispatch_wave", wave)
    run = dd_live_run.Run(tmp_path, workdir, [], {}, 1)
    return run, stages, waves


def test_drive_runs_compose_and_the_writer_wave_in_readme_mode(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run, stages, waves = _fake_run(monkeypatch, tmp_path, True)
    dd_live_run.drive(run, False)
    assert stages == ["start", "compose", "verify", "finish"]
    assert waves == [["docs-1"], ["readme-1"], ["verify-1"]]


def test_drive_skips_compose_without_readme(monkeypatch: pytest.MonkeyPatch,
                                            tmp_path: Path) -> None:
    run, stages, waves = _fake_run(monkeypatch, tmp_path, False)
    dd_live_run.drive(run, False)
    assert stages == ["start", "verify", "finish"]
    assert waves == [["docs-1"], ["verify-1"]]


def test_resume_compose_reuses_the_sheet_wave(monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:
    run, stages, waves = _fake_run(monkeypatch, tmp_path, True)
    dd_live_run.drive(run, False, "compose")
    assert stages == ["compose", "verify", "finish"]
    assert waves == [["readme-1"], ["verify-1"]]
    assert parse_args(["x", "--resume", "compose"]).resume == "compose"


def test_row_counts_sheet_and_readme_calls(workdir: Path) -> None:
    base = [Call("review", "u001", "sonnet", 1.0, 1, 0.0, "ok"),
            Call("verify", "v01", "opus", 1.0, 1, 0.0, "ok")]

    def cells(calls: list[Call]) -> dict[str, str]:
        return _cells(render_row(workdir, date="2026-10-13", repository="r", calls=calls,
                                 wall_seconds=1, planted=None, decoys=None, notes="x"))

    assert cells(base)["agents"] == "1/0/1"
    assert cells(base)["notes"] == "x"
    _write(workdir, "applied.json", {"applied": [], "reverted": [],
                                     "readme": {"lines": 42, "statements": 5, "removed": 0}})
    more = [*base, Call("sheet", "a01", "sonnet", 1.0, 1, 0.0, "ok"),
            Call("sheet", "a02", "sonnet", 1.0, 1, 0.0, "ok"),
            Call("readme", "r01", "opus", 1.0, 1, 0.0, "ok")]
    got = cells(more)
    assert got["agents"] == "1/0/1/2/1"
    assert got["notes"] == "x; readme: 42 lines"


def test_drive_runs_compose_even_with_an_empty_docs_plan_in_readme_mode(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run, stages, waves = _fake_run(monkeypatch, tmp_path, True, docs=0)
    dd_live_run.drive(run, False)
    assert stages == ["start", "compose", "verify", "finish"]
    assert waves == [["readme-1"], ["verify-1"]]
    run, stages, waves = _fake_run(monkeypatch, tmp_path / "b", False, docs=0)
    dd_live_run.drive(run, False)
    assert stages == ["start", "finish"] and waves == []
