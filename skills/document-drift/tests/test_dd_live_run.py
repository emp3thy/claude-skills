"""The live harness's offline parts (spec 11.3): argument parsing, the evaluation-log row and the
refusal without a ``claude`` launcher. No test here calls a model; the harness itself refuses to
dispatch an agent under pytest.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import dd_live_run
import pytest
from dd_live_run import (
    HEADER,
    Call,
    append_row,
    check_log,
    main,
    parse_args,
    render_row,
    resolve_target,
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


def _cells(row: str) -> list[str]:
    assert row.startswith("| ") and row.endswith(" |\n")
    return [c.strip() for c in row[2:-3].split(" | ")]


def test_row_format(workdir: Path) -> None:
    calls = [Call("review", "u001", "sonnet", 60.0, 1000, 0.5, "ok"),
             Call("review", "u002", "sonnet", 70.0, 2000, 0.25, "ok"),
             Call("gap", "g001", "sonnet", 30.0, None, 0.1, "ok"),
             Call("verify", "v01", "opus", 40.0, 500, 1.0, "ok")]
    row = render_row(workdir, date="2026-10-13", repository="py-service", calls=calls,
                     wall_seconds=754.2, planted=(9, 11), decoys=(1, 8),
                     notes="missed p3 | p14")
    cells = _cells(row)
    header = [c.strip() for c in HEADER.strip()[2:-2].split(" | ")]
    assert len(cells) == len(header)
    got = dict(zip(header, cells, strict=True))
    assert got == {
        "date": "2026-10-13", "repository": "py-service", "head": "0123456",
        "mode": "first", "docs": "3", "affected": "3", "units": "2",
        "edits proposed": "5 (3/1/1)", "kept": "4", "verdicts": "2/1/0/1", "applied": "3",
        "human": "2", "notices placed": "1", "gaps": "2/1", "planted caught": "9/11",
        "decoys touched": "1/8", "agents": "2/1/1", "wall time": "12m34s",
        "tokens": "3500", "cost usd": "1.85", "notes": "missed p3 \\| p14",
    }


def test_row_format_without_scoring_or_tokens(workdir: Path) -> None:
    _write(workdir, "changes.json", {"mode": "later", "scope": "since abc", "review": {},
                                     "affected": {"README.md": {}}})
    calls = [Call("review", "u001", "sonnet", 5.0, None, 0.0, "ok")]
    cells = _cells(render_row(workdir, date="2026-10-13", repository="repo", calls=calls,
                              wall_seconds=5, planted=None, decoys=None, notes=""))
    assert cells[3:6] == ["later", "3", "1"]
    assert cells[14:16] == ["-", "-"]
    assert cells[18] == "-" and cells[20] == "-"


def test_row_format_missing_files(tmp_path: Path) -> None:
    cells = _cells(render_row(tmp_path, date="2026-10-13", repository="repo", calls=[],
                              wall_seconds=0, planted=None, decoys=None, notes="stopped"))
    assert cells[2] == "-" and cells[7] == "-" and cells[-1] == "stopped"


def test_append_row_into_the_section(tmp_path: Path) -> None:
    log = tmp_path / "log.md"
    sep = "|" + "---|" * (HEADER.count(" | ") + 1) + "\n"
    old = "| 2026-10-01 | a |\n"
    log.write_bytes(("# log\n\n| x |\n|---|\n\n## document-drift\n\nText.\n\n"
                     + HEADER + sep + old + "\n## later\n\n| y |\n").encode())
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
