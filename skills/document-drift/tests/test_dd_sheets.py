from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import dd_dispatch
import dd_sheets
from dd_common import read_json, write_json
from dd_helpers import make_repo

CLI = ["import argparse", "", "def main():", "    p = argparse.ArgumentParser()",
       "    p.add_argument('--force', help='overwrite')",
       *[f"    x{n} = {n}" for n in range(9)],
       "def sync():", "    pass", *[f"y{n} = {n}" for n in range(12)]]
FILES = {"src/app/cli.py": "\n".join(CLI) + "\n",
         "src/app/config.py": "import os\nTOKEN = os.environ['APP_TOKEN']\n",
         "scripts/setup.sh": "#!/bin/sh\necho setup\n"}
SYNC_LINE = CLI.index("def sync():") + 1
HINTS_A01 = [
    {"name": "sync", "kind": "command", "file": "src/app/cli.py", "line": SYNC_LINE,
     "parent": None, "hidden": False},
    {"name": "--force", "kind": "flag", "file": "src/app/cli.py", "line": 5,
     "parent": "sync", "hidden": False}]
HINTS_A02 = [{"name": "APP_TOKEN", "kind": "env", "file": "src/app/config.py", "line": 2,
              "parent": None, "hidden": False}]


def _area(aid: str, paths: list[str], hints: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": aid, "files": [{"path": p, "lines": 5} for p in paths], "lines": 5,
            "hints": hints}


AREA1 = _area("a01", ["src/app/cli.py"], HINTS_A01)
AREA2 = _area("a02", ["src/app/config.py", "scripts/setup.sh"], HINTS_A02)


def _repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": FILES}])


def _surface(kind: str, name: str, at: str, parent: str | None = None,
             hidden: bool = False) -> dict[str, Any]:
    return {"kind": kind, "name": name, "parent": parent, "summary": "does it",
            "default": None, "defined_at": at, "user_facing": True, "hidden": hidden}


def _sheet(**over: Any) -> dict[str, Any]:
    sheet: dict[str, Any] = {
        "area": "a01",
        "surface": [_surface("command", "sync", f"src/app/cli.py:{SYNC_LINE}"),
                    _surface("flag", "--force", "src/app/cli.py:5", "sync")],
        "behaviours": [{"statement": "the `main` function parses the flags",
                        "evidence": ["src/app/cli.py:3"]}],
        "dismissed": []}
    sheet.update(over)
    return sheet


def _check(tmp_path: Path, sheet: Any, area: dict[str, Any] = AREA1) -> list[str]:
    root = _repo(tmp_path)
    return dd_sheets.validate(sheet, area, root, set(FILES))


def test_valid_sheet_has_no_problems(tmp_path: Path) -> None:
    assert _check(tmp_path, _sheet()) == []


def test_defined_at_outside_the_area_is_invalid(tmp_path: Path) -> None:
    sheet = _sheet()
    sheet["surface"][0]["defined_at"] = "src/app/config.py:2"
    problems = _check(tmp_path, sheet)
    assert any("outside the area" in p for p in problems)


def test_defined_at_line_outside_the_file_is_invalid(tmp_path: Path) -> None:
    sheet = _sheet()
    sheet["surface"][0]["defined_at"] = "src/app/cli.py:999"
    assert any("outside src/app/cli.py" in p for p in _check(tmp_path, sheet))
    sheet["surface"][0]["defined_at"] = "src/app/cli.py"
    assert any("not path:line" in p for p in _check(tmp_path, sheet))


def test_untracked_file_is_invalid(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    problems = dd_sheets.validate(_sheet(), AREA1, root, set())
    assert any("not tracked" in p for p in problems)


def test_name_must_be_at_its_place(tmp_path: Path) -> None:
    far = _sheet()
    far["surface"][0]["defined_at"] = "src/app/cli.py:5"
    assert any("'sync' is not within" in p for p in _check(tmp_path, far))
    module = _sheet(surface=[_surface("entry", "python -m app.cli", "src/app/cli.py:1")],
                    dismissed=[{"hint": "command sync", "why": "x"},
                               {"hint": "flag --force", "why": "x"}])
    assert _check(tmp_path, module) == []
    script = _sheet(area="a02", surface=[
        _surface("script", "scripts/setup.sh", "scripts/setup.sh:1"),
        _surface("env", "APP_TOKEN", "src/app/config.py:2")], behaviours=[])
    assert _check(tmp_path, script, AREA2) == []


def test_route_duplicates_are_keyed_by_method(tmp_path: Path) -> None:
    area = _area("a01", ["src/app/cli.py"], [])
    # the name must be near its line: `/argparse` sits next to line 1
    routes = [_surface("route", "/argparse", "src/app/cli.py:1", "GET"),
              _surface("route", "/argparse", "src/app/cli.py:1", "POST")]
    assert _check(tmp_path, _sheet(surface=routes, behaviours=[]), area) == []
    routes[1]["parent"] = "GET"
    assert any("duplicate" in p for p in
               _check(tmp_path, _sheet(surface=routes, behaviours=[]), area))


def test_behaviour_needs_a_span_and_no_guarantee_word(tmp_path: Path) -> None:
    def problems(statement: str, evidence: list[str] | None = None) -> list[str]:
        return _check(tmp_path, _sheet(behaviours=[{
            "statement": statement,
            "evidence": ["src/app/cli.py:3"] if evidence is None else evidence}]))
    assert problems("the `main` function parses") == []
    assert any("no inline-code span" in p for p in problems("main parses"))
    assert any("guarantee word" in p for p in problems("`main` always parses"))
    assert any("several lines" in p for p in problems("`main`\nparses"))
    assert any("no evidence" in p for p in problems("`main` parses", []))
    assert any("outside the area" in p for p in problems("`main` parses", ["x.py:1"]))


def test_every_hint_is_an_entry_or_dismissed(tmp_path: Path) -> None:
    sheet = _sheet(area="a02", surface=[], behaviours=[])
    problems = _check(tmp_path, sheet, AREA2)
    assert len(problems) == 1
    assert "env APP_TOKEN" in problems[0]
    root = tmp_path / "repo"  # after the retry the missing hints are filled, not a problem
    assert dd_sheets.validate(sheet, AREA2, root, set(FILES), require_hints=False) == []
    sheet["dismissed"] = [{"hint": "env APP_TOKEN", "why": "internal"}]
    assert _check(tmp_path, sheet, AREA2) == []


def test_fill_adds_missing_hints_from_the_scan() -> None:
    area = _area("a02", ["src/app/config.py"], [{**HINTS_A02[0], "hidden": True}])
    sheet = _sheet(area="a02", surface=[], behaviours=[])
    assert dd_sheets.fill(sheet, area) == 1
    entry = sheet["surface"][0]
    assert entry == {"kind": "env", "name": "APP_TOKEN", "parent": None,
                     "summary": "from the pattern scan", "default": None,
                     "defined_at": "src/app/config.py:2", "user_facing": True,
                     "hidden": True, "filled": True}
    assert dd_sheets.fill(sheet, area) == 0


def test_hidden_takes_the_hints_value() -> None:
    sheet = _sheet()
    sheet["surface"][1]["hidden"] = True
    assert dd_sheets.correct_hidden(sheet, AREA1) == 1
    assert sheet["surface"][1]["hidden"] is False
    assert dd_sheets.correct_hidden(sheet, AREA1) == 0


def test_run_writes_sheets_json_with_ids_and_unchecked(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    workdir = tmp_path / "work"
    (workdir / "sheets").mkdir(parents=True)
    area3 = _area("a03", ["scripts/setup.sh"], [])
    write_json(workdir / "areas.json", {"area_lines": 100, "areas": [AREA1, AREA2, area3],
                                        "unplanned": ["a03"]})
    write_json(workdir / "inventory.json", {"files": sorted(FILES)})
    plan = [{"id": a, "role": "sheet", "model": "m", "prompt": f"p{a}",
             "output": (workdir / "sheets" / f"{a}.json").as_posix()} for a in ("a01", "a02")]
    write_json(workdir / "plan-docs.json", plan)
    write_json(workdir / "sheets" / "a01.json", _sheet())
    write_json(workdir / "sheets" / "a02.json", _sheet(area="a02", surface=[], behaviours=[]))
    result = dd_sheets.run(root, workdir, {}, frozenset({"a02"}))
    assert read_json(workdir / "sheets.json") == result
    assert result["unchecked"] == [{"area": "a02", "why": "invalid after retry"},
                                   {"area": "a03", "why": "over the cap"}]
    assert [e["id"] for e in result["sheets"]["a01"]["surface"]] == ["a01-s01", "a01-s02"]
    assert result["sheets"]["a01"]["behaviours"][0]["id"] == "a01-b01"
    assert (result["filled"], result["hidden_corrected"]) == (0, 0)
    (workdir / "sheets" / "a02.json").unlink()
    again = dd_sheets.run(root, workdir, {}, frozenset())
    assert again["unchecked"][0] == {"area": "a02", "why": "no output"}


def test_check_outputs_runs_the_content_rules_only_with_a_root(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    workdir = tmp_path / "work"
    (workdir / "sheets").mkdir(parents=True)
    write_json(workdir / "areas.json", {"area_lines": 100, "areas": [copy.deepcopy(AREA1)]})
    write_json(workdir / "inventory.json", {"files": sorted(FILES)})
    far = _sheet()
    far["surface"][0]["defined_at"] = "src/app/cli.py:5"
    out = workdir / "sheets" / "a01.json"
    write_json(out, far)
    plan: list[dd_dispatch.PlanEntry] = [
        {"id": "a01", "role": "sheet", "model": "m", "prompt": "p", "output": out.as_posix()}]
    assert dd_dispatch.check_outputs(workdir, plan, "sheet") == (["a01"], [])
    valid, failed = dd_dispatch.check_outputs(workdir, plan, "sheet", root=root)
    assert valid == [] and [e["id"] for e in failed] == ["a01"]
