"""The corpus harness (spec 0d): run the staged pipeline on a replayed fixture with canned agent
outputs, and judge each planted item of the fixture against the run's workdir files.

A fixture under ``tests/fixtures/corpus/<name>/`` has two states: its history's commits up to
the one tagged ``state1``, and the rest up to ``state2``. Its canned agent outputs live under
``tests/canned/<name>/``: ``state1/`` and ``state2/`` hold ``review/uNNN.json``,
``gaps/gNNN.json`` and ``verdicts/vNN.json`` named after the plan entries they answer, and
``state1-invalid/`` holds review outputs that fail validation (the retry test). Verdicts are
matched to a verify entry by edit id, so a batch that loses edits (an unchecked unit) still
gets the verdicts of the edits it holds.

``run_fixture(name, state, tmp_path)`` replays state 1 and drives ``start``, ``verify`` and
``finish``; for state 2 it then merges the drift branch into ``main`` with
``git merge --no-ff`` (deleting the merged branch), replays the state-2 commits on top with
``continue_fixture`` and drives a second, later run, so the first run's ``Drift-Base`` commit
is an ancestor of HEAD. Git author and committer dates are pinned for the whole drive, so the
drift commits, and with them every later sha and run id, are the same on every machine.

``planted.json`` is ``{"state1": [item...], "state2": [item...]}``; an item is ``{"id",
"state", "doc" and/or "name", "line", "kind", "what", "expect"}`` with ``expect`` a list of
expectations, all judged by ``evaluate`` on the run of the item's state:

- ``edit:<type>``: an applied edit of that type whose ``doc`` and ``start_line`` are the item's;
- ``human:<kind>``: a human-decision entry of that kind on the doc line (for ``no-home``, one
  whose text names the item's ``name``);
- ``gap:<gap_kind>:<target doc>``: a ``gaps.json`` gap for the item's ``name`` of that kind
  aimed at that doc;
- ``dropped:<check>``: an edit on the doc line dropped by that check;
- ``none``: no applied edit covering the doc line, no human entry on it or naming the item's
  ``name``, no gap for the ``name`` or aimed at the doc line;
- ``excluded``: the doc is in ``inventory.json`` ``excluded``;
- ``affected`` / ``not-affected``: the doc is / is not in ``changes.json`` ``affected`` (for
  any reason, its own change included); ``affected:anchor`` / ``affected:missing``: the doc's
  ``affected`` entry has an ``anchor_reasons`` / ``missing`` entry on the doc line, so the code
  change itself reached the line;
- ``not-reviewed``: no unit of ``units.json`` holds the doc;
- ``anchors``: ``anchors.json`` has an anchor on the doc line;
- ``not-about-code``: the doc's ``code_claims`` in ``edits.json`` is 0;
- ``notice:1st``: an applied 1st-notice edit over the block starting on the doc line;
  ``notice:2nd`` / ``notice:removed`` / ``notice:cleared:<anchored|changed|ignore>``: a
  ``notices.json`` decision (``escalate``, ``remove``, ``clear-<reason>``) on the block starting
  on the doc line, with its notice edit applied.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import dd_run
from dd_commit import collect_human
from dd_common import read_json
from dd_make_history import CORPUS_ROOT, continue_fixture, replay_fixture

FIXTURES: tuple[str, ...] = ("py-service",)  # the phase A fixtures; ts-web and go-cli follow
CANNED_ROOT = Path(__file__).resolve().parent / "canned"
DATES = {1: "2026-01-02", 2: "2026-01-09"}  # each state's run date (--date)
ROLE_DIRS = {"review": "review", "gap": "gaps", "verify": "verdicts"}
STATES = (1, 2)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", check=True, env=env)
    return out.stdout


def prepare_fixture(name: str, dest: Path, until_tag: str | None = "state1") -> Path:
    """Replay ``name`` (up to ``until_tag``; None for the whole history) into ``dest`` with
    local settings that keep the working tree clean.

    The replay itself pins ``core.autocrlf=false`` per command; a later ``git status`` would
    otherwise read the machine's global setting, so it is pinned in the repository too, with
    a fixed identity for the run's own commit.
    """
    repo = replay_fixture(name, dest, until_tag)
    for key, value in (("core.autocrlf", "false"), ("user.name", "Fixture"),
                       ("user.email", "fixture@example.com"), ("commit.gpgsign", "false")):
        git(repo, "config", key, value)
    return repo


def load_planted(name: str) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = json.loads(
        (CORPUS_ROOT / name / "planted.json").read_text(encoding="utf-8"))
    return data


def planted_items(name: str) -> list[dict[str, Any]]:
    """Every planted item of ``name``, state 1 first."""
    data = load_planted(name)
    return [item for state in STATES for item in data.get(f"state{state}", [])]


# ---------------------------------------------------------------- driving a run

@dataclass
class Workdir:
    """A finished run: its repository, workdir and the exit code of each stage call."""
    repo: Path
    path: Path
    branch: str
    exits: list[tuple[str, int]] = field(default_factory=list)


@contextmanager
def pinned_dates(date: str) -> Iterator[None]:
    """Pin git's author and committer dates to noon UTC of ``date`` while the block runs."""
    stamp = f"{date}T12:00:00+00:00"
    saved = {k: os.environ.get(k) for k in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
    os.environ.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _canned_verdicts(canned: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted((canned / "verdicts").glob("*.json")):
        for verdict in read_json(path)["verdicts"]:
            found[verdict["edit"]] = verdict
    return found


def answer(workdir: Path, plan_name: str, canned: Path, invalid: Path | None = None) -> None:
    """Write the canned output of every entry of plan ``plan_name``: a review or gap entry gets
    ``canned/<role dir>/<output name>`` (or ``invalid/<output name>`` when that exists); a
    verify entry gets the canned verdicts of its batch's edits, found by edit id."""
    plan: list[dict[str, Any]] = read_json(workdir / plan_name)
    verdicts: dict[str, dict[str, Any]] | None = None
    for entry in plan:
        out = Path(entry["output"])
        if entry["role"] == "verify":
            if verdicts is None:
                verdicts = _canned_verdicts(canned)
            batch = {"batch": entry["id"],
                     "verdicts": [verdicts[e] for e in entry["edits"] if e in verdicts]}
            out.write_text(json.dumps(batch, indent=1) + "\n", encoding="utf-8")
            continue
        bad = invalid / out.name if invalid is not None else None
        source = bad if bad is not None and bad.is_file() else (
            canned / ROLE_DIRS[entry["role"]] / out.name)
        if not source.is_file():
            raise FileNotFoundError(f"no canned output {source} for plan entry {entry['id']}")
        out.write_bytes(source.read_bytes())


def _stage(run: Workdir, label: str, argv: Sequence[str], expected: int) -> None:
    code = dd_run.main([str(run.repo), *argv])
    run.exits.append((label, code))
    if code != expected:
        raise AssertionError(f"{label} exited {code}, expected {expected}; exits so far "
                             f"{run.exits}")


def drive(run: Workdir, canned: Path, date: str, invalid: Path | None = None) -> None:
    """``start``, the canned review and gap outputs, ``verify`` (then ``verify --retried`` when
    ``invalid`` outputs make it exit 3), the canned verdicts and ``finish``."""
    workdir = run.path
    with pinned_dates(date):
        _stage(run, "start", ["--stage", "start", "--date", date, "--branch", run.branch], 0)
        answer(workdir, "plan-docs.json", canned, invalid)
        if invalid is not None:
            _stage(run, "verify", ["--stage", "verify"], 3)
            answer(workdir, "retry.json", canned, invalid)  # the retry fails again
            _stage(run, "verify --retried", ["--stage", "verify", "--retried"], 0)
        else:
            _stage(run, "verify", ["--stage", "verify"], 0)
        answer(workdir, "plan-verify.json", canned)
        _stage(run, "finish", ["--stage", "finish"], 0)


def merge_drift_branch(repo: Path, branch: str, date: str) -> None:
    """Merge the drift branch into ``main`` with a merge commit and delete it, as an owner
    merging the drift PR would."""
    stamp = f"{date}T18:00:00+00:00"
    env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    git(repo, "switch", "-q", "main")
    if git(repo, "branch", "--list", branch).strip():
        git(repo, "merge", "-q", "--no-ff", "-m", f"Merge branch '{branch}'", branch, env=env)
        git(repo, "branch", "-q", "-d", branch)


def run_fixture(name: str, state: int, tmp_path: Path, canned_invalid: bool = False,
                branch: str = "docs/drift-corpus") -> Workdir:
    """Run the pipeline on fixture ``name`` at ``state`` (1 or 2) under ``tmp_path``; for state
    2 the state-1 run comes first and is merged. ``canned_invalid`` answers state 1 with the
    ``state1-invalid`` review outputs where they exist."""
    if state not in STATES:
        raise ValueError(f"state must be 1 or 2, not {state!r}")
    repo = prepare_fixture(name, tmp_path / name, until_tag="state1")
    run = Workdir(repo=repo, path=repo / ".document-drift", branch=branch)
    canned = CANNED_ROOT / name
    drive(run, canned / "state1", DATES[1],
          canned / "state1-invalid" if canned_invalid else None)
    if state == 1:
        return run
    merge_drift_branch(repo, branch, DATES[1])
    continue_fixture(name, repo, after_tag="state1")
    drive(run, canned / "state2", DATES[2])
    return run


# ---------------------------------------------------------------- judging an item

def _json(workdir: Path, name: str) -> Any:
    path = workdir / name
    return read_json(path) if path.is_file() else {}


def _on_line(item: dict[str, Any], doc: str, line: int) -> bool:
    return doc == item.get("doc") and line == item.get("line")


def _applied_edits(workdir: Path) -> list[dict[str, Any]]:
    applied = set(_json(workdir, "applied.json").get("applied", []))
    return [e for e in _json(workdir, "edits.json").get("edits", []) if e["id"] in applied]


def _human(workdir: Path) -> list[dict[str, Any]]:
    return collect_human(workdir) if (workdir / "edits.json").is_file() else []


def _human_hit(item: dict[str, Any], entry: dict[str, Any]) -> bool:
    if _on_line(item, entry["doc"], int(entry["line"])):
        return True
    name = item.get("name")
    return entry["kind"] == "no-home" and bool(name) and str(entry["text"]).endswith(f" {name}")


def _expect_edit(item: dict[str, Any], workdir: Path, kind: str) -> str | None:
    if any(e["type"] == kind and _on_line(item, e["doc"], int(e["start_line"]))
           for e in _applied_edits(workdir)):
        return None
    return f"no applied {kind} edit at {item.get('doc')}:{item.get('line')}"


def _expect_human(item: dict[str, Any], workdir: Path, kind: str) -> str | None:
    if any(h["kind"] == kind and _human_hit(item, h) for h in _human(workdir)):
        return None
    return f"no {kind} human entry at {item.get('doc')}:{item.get('line')}"


def _expect_gap(item: dict[str, Any], workdir: Path, arg: str) -> str | None:
    gap_kind, _, target = arg.partition(":")
    gaps = _json(workdir, "gaps.json").get("gaps", [])
    if any(g["name"] == item.get("name") and g["gap_kind"] == gap_kind
           and g["target_doc"] == target for g in gaps):
        return None
    found = [(g["gap_kind"], g["target_doc"]) for g in gaps if g["name"] == item.get("name")]
    return f"no {gap_kind} gap for {item.get('name')} aimed at {target}; found {found}"


def _expect_dropped(item: dict[str, Any], workdir: Path, check: str) -> str | None:
    edits = _json(workdir, "edits.json").get("edits", [])
    if any(e["status"] == "dropped" and e["check"] == check
           and _on_line(item, e["doc"], int(e["start_line"])) for e in edits):
        return None
    return f"no edit at {item.get('doc')}:{item.get('line')} dropped by {check}"


def _expect_none(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    problems = []
    line = item.get("line")
    for edit in _applied_edits(workdir):
        if edit["doc"] == item.get("doc") and isinstance(line, int) and (
                int(edit["start_line"]) <= line <= int(edit["end_line"])):
            problems.append(f"applied edit {edit['id']}")
    problems += [f"human {h['kind']} entry" for h in _human(workdir) if _human_hit(item, h)]
    for gap in _json(workdir, "gaps.json").get("gaps", []):
        if (item.get("name") and gap["name"] == item["name"]) or (
                gap["target_doc"] == item.get("doc") and gap["target_line"] == line):
            problems.append(f"gap for {gap['name']}")
    return "; ".join(problems) or None


def _expect_excluded(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    excluded = [x["path"] for x in _json(workdir, "inventory.json").get("excluded", [])]
    return None if item.get("doc") in excluded else f"{item.get('doc')} is not excluded"


AFFECTED_REASONS = {"anchor": "anchor_reasons", "missing": "missing"}


def _expect_affected(item: dict[str, Any], workdir: Path, arg: str) -> str | None:
    affected = _json(workdir, "changes.json").get("affected", {})
    entry = affected.get(item.get("doc"))
    if entry is None:
        return f"{item.get('doc')} is not affected"
    if not arg:
        return None
    key = AFFECTED_REASONS.get(arg)
    if key is None:
        return f"unknown affected reason {arg!r}"
    if any(r["line"] == item.get("line") for r in entry[key]):
        return None
    return (f"{item.get('doc')} is affected, but no {key} entry is on line {item.get('line')}; "
            f"found {[(r['line'], r['ref']) for r in entry[key]]}")


def _expect_not_affected(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    if item.get("doc") in _json(workdir, "changes.json").get("affected", {}):
        return f"{item.get('doc')} is affected"
    return None


def _expect_not_reviewed(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    units = _json(workdir, "units.json").get("units", [])
    held = [u["id"] for u in units if any(d["doc"] == item.get("doc") for d in u["docs"])]
    return f"{item.get('doc')} is reviewed in {held}" if held else None


def _expect_anchors(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    anchors = _json(workdir, "anchors.json").get("anchors", [])
    if any(_on_line(item, a["doc"], int(a["line"])) for a in anchors):
        return None
    return f"no anchor at {item.get('doc')}:{item.get('line')}"


def _expect_not_about_code(item: dict[str, Any], workdir: Path, _arg: str) -> str | None:
    claims = _json(workdir, "edits.json").get("code_claims", {})
    if claims.get(item.get("doc")) == 0:
        return None
    return f"code_claims of {item.get('doc')} is {claims.get(item.get('doc'))!r}, not 0"


NOTICE_ACTIONS = {"2nd": ("escalate", "escalate"), "removed": ("remove", "unverified")}


def _expect_notice(item: dict[str, Any], workdir: Path, arg: str) -> str | None:
    applied = _applied_edits(workdir)
    if arg == "1st":
        if any(e["type"] == "notice" and _on_line(item, e["doc"], int(e["start_line"]))
               for e in applied):
            return None
        return f"no applied 1st notice over {item.get('doc')}:{item.get('line')}"
    if arg.startswith("cleared:"):
        action, edit_type = f"clear-{arg.split(':', 1)[1]}", "clear"
    elif arg in NOTICE_ACTIONS:
        action, edit_type = NOTICE_ACTIONS[arg]
    else:
        return f"unknown notice expectation {arg!r}"
    decisions = _json(workdir, "notices.json").get("decisions", [])
    hits = [d for d in decisions if d["action"] == action
            and _on_line(item, d["doc"], int(d["block"][0]))]
    if not hits:
        return f"no {action} decision on the block at {item.get('doc')}:{item.get('line')}"
    lines = {int(d["line"]) for d in hits}
    if not any(e["type"] == edit_type and e["doc"] == item.get("doc")
               and int(e["start_line"]) in lines for e in applied):
        return f"the {action} decision's {edit_type} edit was not applied"
    return None


Judge = Callable[[dict[str, Any], Path, str], str | None]
JUDGES: dict[str, Judge] = {
    "edit": _expect_edit,
    "human": _expect_human,
    "gap": _expect_gap,
    "dropped": _expect_dropped,
    "none": _expect_none,
    "excluded": _expect_excluded,
    "affected": _expect_affected,
    "not-affected": _expect_not_affected,
    "not-reviewed": _expect_not_reviewed,
    "anchors": _expect_anchors,
    "not-about-code": _expect_not_about_code,
    "notice": _expect_notice,
}


def evaluate(item: dict[str, Any], workdir: Path, state: int) -> list[str]:
    """The expectations of ``item`` that the run of ``state`` in ``workdir`` does not meet, each
    with what was found instead; empty when every expectation holds."""
    if item.get("state") != state:
        return [f"item {item.get('id')} is a state {item.get('state')} item, not state {state}"]
    problems = []
    for expectation in item["expect"]:
        head, _, arg = expectation.partition(":")
        judge = JUDGES.get(head)
        found = judge(item, workdir, arg) if judge else "unknown expectation"
        if found is not None:
            problems.append(f"{expectation}: {found}")
    return problems
