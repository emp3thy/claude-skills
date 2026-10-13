"""Run the whole skill with real Claude agents and log the run (spec 11.3). Manual only.

Usage, from the skill directory::

    python tests/dd_live_run.py <fixture name | repo path> [--state N] [--from <sha>] [--full]
        [--check] [--base <ref>] [--keep <dir>] [--budget <usd>] [--model-override <name>]
        [--workdir <dir>] [--claude <path>] [--parallel N] [--timeout S] [--log <file>]

A fixture name (one of ``dd_corpus.FIXTURES``) is replayed into a temporary directory up to its
``state1`` tag; ``--state 2`` first runs state 1 with the canned agent outputs
(``dd_corpus.run_fixture``), merges the drift branch, replays the state-2 commits, and only then
runs live. A fixture run uses the corpus date of its state (``--date``, git dates pinned) so its
run ids match the canned runs'. A path is used as the repository as it is, with its own
``.document-drift`` workdir unless ``--workdir``; a run without ``--check`` creates the drift
branch and commits in that repository, so point it at a throwaway clone.

The harness does what ``SKILL.md`` tells a session to do: ``dd_run.main`` runs ``start``,
``verify`` and ``finish`` in-process; after each stage the plan named on its stdout line is
dispatched, every entry one ``claude -p`` call (``--parallel`` at a time), the prompt
``Read the file <prompt> in full and follow it. Write only <output>.`` on stdin (never argv,
see tech-debt-scan's ``live_run.py``), the entry's model (or ``--model-override``), the tools
Read, Grep, Glob and Write, a per-call dollar budget, print mode with JSON output and the
user's settings and MCP servers left out. The working directory is the repository; a workdir
outside it is added with ``--add-dir``. The agent writes its own output file; the stage that
follows validates it, and on exit 3 the ``retry.json`` entries are dispatched once and the stage
rerun with ``--retried``. ``--from <sha>`` is ``--base <sha>`` plus a note in the row (a true
replay of history from a commit is not built).

On a fixture every ``planted.json`` item of the state is judged with ``dd_corpus.evaluate``:
an item is caught when every expectation holds; a decoy (``kind`` ``decoy`` or ``excluded``) is
touched when one does not; a ``canned_only`` item (one that encodes a canned agent's deliberate
mistake) is skipped and named in the notes. One row is appended to the table that ``HEADER``
starts in the ``## document-drift`` section of ``docs/evaluation-log.md`` (``render_row``,
``append_row``); the section and its header must already be there, and the harness never edits
them. The ``judged acceptable`` cell is rendered ``-``: the owner fills it in after judging the
run's edits. ``live-run.json`` in the workdir records every call (role, id, model, seconds,
tokens, cost, status, the agent's reply), whatever way the run ends; ``--keep`` then copies the
workdir to a directory.

Exit codes: 0 the run finished and the row was logged; 2 refused before any agent call (no
``claude`` launcher, an unknown target, a log without the section); 4 a stage exited
unexpectedly or the run crashed (the row is still logged, with the stage or the exception in
its notes). The harness refuses to dispatch an agent under pytest.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import date as Date
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
for _path in (SKILL_DIR / "scripts", TESTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import dd_run  # noqa: E402
from dd_commit import collect_human  # noqa: E402
from dd_corpus import (  # noqa: E402
    DATES,
    FIXTURES,
    evaluate,
    load_planted,
    merge_drift_branch,
    pinned_dates,
    prepare_fixture,
    run_fixture,
)
from dd_make_history import continue_fixture  # noqa: E402

LOG_PATH = SKILL_DIR.parents[1] / "docs" / "evaluation-log.md"
SECTION = "## document-drift"
COLUMNS = ("date", "repository", "head", "mode", "docs", "affected", "units", "edits proposed",
           "kept", "verdicts", "applied", "judged acceptable", "human", "notices placed", "gaps",
           "planted caught",
           "decoys touched", "agents", "wall time", "tokens", "cost usd", "notes")
HEADER = "| " + " | ".join(COLUMNS) + " |\n"
ISOLATION = ("--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands")
TOOLS = "Read,Grep,Glob,Write"
ROLES = ("review", "gap", "verify")
PLAN_LINE = re.compile(r"^(plan-docs|plan-verify|retry)\.json (.+) with (\d+) entries$")
DISPATCH = "Read the file {prompt} in full and follow it. Write only {output}."
EXIT_OK, EXIT_REFUSED, EXIT_STAGE = 0, 2, 4
CANNED_BRANCH = "docs/drift-corpus"  # run_fixture's default branch


# ---------------------------------------------------------------- the launcher

def launcher_argv(claude: str) -> list[str]:
    """Split a launcher into argv tokens; ``"<python> <script>"`` is supported (tech-debt-scan's
    ``live_run.launcher_argv``: the platform's own lexing, leftover quotes stripped)."""
    if " " not in claude:
        return [claude]
    parts = shlex.split(claude, posix=os.name != "nt")
    return [token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'"
            else token for token in parts]


def resolve_claude(claude: str) -> str | None:
    """The launcher's executable when it can be found on PATH or on disk, else None."""
    parts = launcher_argv(claude)
    head = parts[0] if parts else ""
    if not head:
        return None
    found = shutil.which(head)
    if found is not None:
        return found
    return head if Path(head).is_file() else None


def claude_argv(claude: str, *, model: str, budget: float,
                add_dir: Path | None = None) -> list[str]:
    """The list argv of one agent call; the prompt goes on stdin."""
    extra = ["--add-dir", str(add_dir)] if add_dir is not None else []
    return [*launcher_argv(claude), "-p", *ISOLATION, *extra, "--output-format", "json",
            "--tools", TOOLS, "--allowedTools", TOOLS, "--model", model,
            "--max-budget-usd", f"{budget:.2f}"]


# ---------------------------------------------------------------- one call

@dataclass
class Call:
    """One agent call and what its reply envelope reported."""
    role: str
    id: str
    model: str
    seconds: float
    tokens: int | None
    cost: float
    status: str  # ok, error, no-output
    error: str | None = None
    retry: bool = False
    reply: str = ""


def _tokens(envelope: dict[str, Any]) -> int | None:
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return None
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
            "output_tokens")
    values = [usage[k] for k in keys if isinstance(usage.get(k), int)]
    return sum(values) if values else None


def dispatch_entry(entry: dict[str, Any], *, claude: str, budget: float, cwd: Path,
                   add_dir: Path | None, model_override: str | None, timeout: int,
                   retry: bool) -> Call:
    """One ``claude -p`` call for plan entry ``entry``; the agent writes its own output."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        raise RuntimeError("dd_live_run never calls a model under pytest")
    model = model_override or str(entry["model"])
    text = DISPATCH.format(prompt=entry["prompt"], output=entry["output"])
    argv = claude_argv(claude, model=model, budget=budget, add_dir=add_dir)
    call = Call(str(entry["role"]), str(entry["id"]), model, 0.0, None, 0.0, "error",
                retry=retry)
    began = time.monotonic()
    try:
        proc = subprocess.run(argv, input=text, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        call.seconds = time.monotonic() - began
        call.error = str(exc)
        return call
    call.seconds = time.monotonic() - began
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        envelope = None
    if not isinstance(envelope, dict):
        call.error = (f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}")
        return call
    call.tokens = _tokens(envelope)
    call.cost = float(envelope.get("total_cost_usd") or 0.0)
    call.reply = str(envelope.get("result") or "")[:2000]
    if envelope.get("is_error") or envelope.get("subtype") != "success":
        call.error = str(envelope.get("subtype") or "error") + ": " + call.reply[:300]
        return call
    if not Path(str(entry["output"])).is_file():
        call.status, call.error = "no-output", "the agent wrote no output file"
        return call
    call.status = "ok"
    return call


def dispatch_wave(entries: Sequence[dict[str, Any]], *, sink: list[Call], parallel: int,
                  retry: bool, **kwargs: Any) -> None:
    """Every entry of a plan in parallel (at most ``parallel`` at a time). Each call is added
    to ``sink`` as it completes, so a paid call is recorded even when another one raises; the
    first exception is re-raised once the wave is over."""
    failure: BaseException | None = None
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = [pool.submit(dispatch_entry, dict(e), retry=retry, **kwargs) for e in entries]
        for future in as_completed(futures):
            try:
                call = future.result()
            except Exception as exc:
                failure = failure or exc
                continue
            sink.append(call)
            mark = " (retry)" if call.retry else ""
            tokens = "-" if call.tokens is None else str(call.tokens)
            print(f"  {call.role} {call.id}{mark}: {call.model}, {call.seconds:.0f}s, "
                  f"{tokens} tokens, ${call.cost:.2f}, {call.status}"
                  + (f" ({call.error})" if call.error else ""), flush=True)
    if failure is not None:
        raise failure


# ---------------------------------------------------------------- stages

class StageFailed(Exception):
    def __init__(self, stage: str, code: int) -> None:
        super().__init__(f"{stage} exited {code}")
        self.stage, self.code = stage, code


@dataclass
class Run:
    """The state of one live run."""
    repo: Path
    workdir: Path
    flags: list[str]
    dispatch: dict[str, Any]
    parallel: int
    calls: list[Call] = field(default_factory=list)


def _stage(run: Run, args: list[str], allowed: tuple[int, ...]) -> tuple[int, str]:
    """``dd_run.main`` in-process; its stdout is echoed and returned."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = dd_run.main([str(run.repo), *args, "--workdir", str(run.workdir)])
    out = buffer.getvalue()
    sys.stdout.write(out)
    sys.stdout.flush()
    label = " ".join(a for a in args if a != "--stage")
    if code not in allowed:
        raise StageFailed(label, code)
    return code, out


def _plan(out: str, workdir: Path, name: str) -> list[dict[str, Any]]:
    """The plan named on the stage's stdout line; ``[]`` when the stage named none (the phase B
    message of a run with no doc in scope)."""
    for line in out.splitlines():
        match = PLAN_LINE.match(line.strip())
        if match and match.group(1) == name:
            plan: list[dict[str, Any]] = json.loads(Path(match.group(2)).read_text("utf-8"))
            return plan
    return []


def _wave(run: Run, plan: list[dict[str, Any]], retry: bool = False) -> None:
    dispatch_wave(plan, sink=run.calls, parallel=run.parallel, retry=retry, **run.dispatch)


def _stage_with_retry(run: Run, stage: str, ok: tuple[int, ...]) -> tuple[int, str]:
    """A stage; on exit 3, its ``retry.json`` dispatched once and the stage rerun ``--retried``
    (``SKILL.md`` steps 3 and 5)."""
    code, out = _stage(run, ["--stage", stage], (*ok, 3))
    if code != 3:
        return code, out
    _wave(run, _plan(out, run.workdir, "retry"), retry=True)
    return _stage(run, ["--stage", stage, "--retried"], ok)


def drive(run: Run, check: bool, resume: str | None = None) -> None:
    """start, the review and gap wave, verify, the verifier wave, finish; with ``resume``
    (``verify`` or ``finish``) the stages before it are skipped and their waves' outputs,
    already in the workdir, are reused."""
    if resume is None:
        print(f"start: {run.repo}", flush=True)
        _, out = _stage(run, ["--stage", "start", *run.flags], (0,))
        docs_plan = _plan(out, run.workdir, "plan-docs")
        if not docs_plan:
            resume = "finish"
        else:
            _wave(run, docs_plan)
    if resume != "finish":
        print(f"verify: {run.repo}", flush=True)
        _, out = _stage_with_retry(run, "verify", (0,))
        _wave(run, _plan(out, run.workdir, "plan-verify"))
    _stage_with_retry(run, "finish", (0, 1) if check else (0,))


# ---------------------------------------------------------------- the row

def _json(workdir: Path, name: str) -> Any:
    path = workdir / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value: object) -> str:
    text = " ".join(str(value).split()) or "-"
    return text.replace("|", "\\|")


def _wall(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 60}m{total % 60:02d}s"


def _ratio(pair: tuple[int, int] | None) -> str:
    return "-" if pair is None else f"{pair[0]}/{pair[1]}"


def render_row(workdir: Path, *, date: str, repository: str, calls: Sequence[Call],
               wall_seconds: float, planted: tuple[int, int] | None,
               decoys: tuple[int, int] | None, notes: str) -> str:
    """One evaluation-log row (``COLUMNS``) from a run's workdir files and its calls; a cell
    whose file is missing is ``-``."""
    pre = _json(workdir, "preflight.json") or {}
    inventory = _json(workdir, "inventory.json")
    changes = _json(workdir, "changes.json")
    units = _json(workdir, "units.json")
    edits_doc = _json(workdir, "edits.json")
    verdicts_doc = _json(workdir, "verdicts.json")
    applied_doc = _json(workdir, "applied.json")
    gaps_doc = _json(workdir, "gaps.json")

    mode = affected = "-"
    if changes is not None:
        scope = str(changes.get("scope") or "")
        mode = {"first": "first", "full": "full"}.get(scope) or (
            "base" if scope.startswith("base ") else "later")
        reviewed = changes.get("review" if mode in ("first", "full") else "affected") or {}
        affected = str(len(reviewed))
    proposed = kept = human = "-"
    edits: list[dict[str, Any]] = []
    if edits_doc is not None:
        edits = list(edits_doc.get("edits", []))
        by_source = Counter(str(e.get("source")) for e in edits)
        proposed = (f"{len(edits)} ({by_source['review']}/{by_source['gap']}/"
                    f"{by_source['notice']})")
        kept = str(sum(1 for e in edits if e.get("status") == "kept"))
        human = str(len(collect_human(workdir)))
    verdicts = "-"
    if verdicts_doc is not None:
        kinds = Counter(str(v.get("verdict")) for v in verdicts_doc.get("verdicts", {}).values())
        verdicts = (f"{kinds['accept']}/{kinds['reject']}/{kinds['unsure']}/"
                    f"{len(verdicts_doc.get('unverified', []))}")
    applied = notices = "-"
    if applied_doc is not None:
        ids = set(applied_doc.get("applied", []))
        applied = str(len(ids))
        notices = str(sum(1 for e in edits
                          if e["id"] in ids and e.get("type") in ("notice", "escalate")))
    elif pre.get("check") and edits_doc is not None:
        applied = notices = "0"
    gaps = "-"
    if gaps_doc is not None:
        gap_kinds = Counter(str(g.get("gap_kind")) for g in gaps_doc.get("gaps", []))
        gaps = f"{gap_kinds['undocumented']}/{gap_kinds['missing-from-list']}"
    roles = {role: len({c.id for c in calls if c.role == role}) for role in ROLES}
    tokens = [c.tokens for c in calls if c.tokens is not None]
    head = str(pre.get("head") or "")[:7] or "-"
    cells = [
        date, repository, head, mode,
        str(len(inventory.get("docs", []))) if inventory is not None else "-",
        affected, str(len(units.get("units", []))) if units is not None else "-",
        proposed, kept, verdicts, applied, "-",  # judged acceptable: the owner fills it in
        human, notices, gaps, _ratio(planted),
        _ratio(decoys), f"{roles['review']}/{roles['gap']}/{roles['verify']}",
        _wall(wall_seconds), str(sum(tokens)) if tokens else "-",
        f"{sum(c.cost for c in calls):.2f}", notes,
    ]
    return "| " + " | ".join(_cell(c) for c in cells) + " |\n"


def _section_end(text: str) -> int:
    """The offset just after the table that ``HEADER`` starts in the ``## document-drift``
    section: past the header line and every ``|`` line directly after it. Raises ValueError
    when the section or the header is missing."""
    start = text.find(f"\n{SECTION}\n")
    if start < 0:
        raise ValueError(f"no '{SECTION}' section")
    nxt = text.find("\n## ", start + 1)
    end = len(text) if nxt < 0 else nxt + 1
    at = text.find(f"\n{HEADER}", start, end)
    if at < 0:
        raise ValueError(f"the '{SECTION}' section has no header row {HEADER.strip()!r}")
    offset = at + 1 + len(HEADER)
    while offset < end and text.startswith("|", offset):
        line_end = text.find("\n", offset)
        offset = len(text) if line_end < 0 else line_end + 1
    return offset


def _read_log(log: Path) -> tuple[str, str]:
    """The log's text with LF line ends, and the line end it uses on disk (a checkout under
    ``core.autocrlf`` has CRLF)."""
    raw = log.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" if "\r\n" in raw else "\n"


def check_log(log: Path) -> None:
    _section_end(_read_log(log)[0])


def append_row(log: Path, row: str) -> None:
    """Insert ``row`` after the last row of the document-drift table, keeping the file's line
    ends."""
    text, newline = _read_log(log)
    at = _section_end(text)
    if not text[:at].endswith("\n"):
        row = "\n" + row
    log.write_bytes((text[:at] + row + text[at:]).replace("\n", newline).encode("utf-8"))


# ---------------------------------------------------------------- scoring

DECOY_KINDS = ("decoy", "excluded")


@dataclass
class Score:
    """A fixture run judged against the state's ``planted.json`` items."""
    caught: int = 0
    planted: int = 0
    touched: int = 0
    decoys: int = 0
    missed_ids: list[str] = field(default_factory=list)
    touched_ids: list[str] = field(default_factory=list)
    canned_ids: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def notes(self) -> list[str]:
        out = []
        if self.missed_ids:
            out.append("missed " + ", ".join(self.missed_ids))
        if self.touched_ids:
            out.append("touched " + ", ".join(self.touched_ids))
        if self.canned_ids:
            out.append("canned-only: " + ", ".join(self.canned_ids))
        return out


def score(name: str, state: int, workdir: Path) -> Score:
    """Judge every item of the state: a planted item is caught when every expectation holds, a
    decoy (``kind`` in ``DECOY_KINDS``) touched when one does not; a ``canned_only`` item is
    skipped and named."""
    result = Score()
    for item in load_planted(name).get(f"state{state}", []):
        iid = str(item["id"])
        if item.get("canned_only"):
            result.canned_ids.append(iid)
            continue
        problems = evaluate(item, workdir, state)
        if item.get("kind") in DECOY_KINDS:
            result.decoys += 1
            if problems:
                result.touched += 1
                result.touched_ids.append(iid)
                result.lines.append(f"touched {iid}: {'; '.join(problems)}")
        else:
            result.planted += 1
            if problems:
                result.missed_ids.append(iid)
                result.lines.append(f"missed {iid}: {'; '.join(problems)}")
            else:
                result.caught += 1
    return result


# ---------------------------------------------------------------- main

def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run document-drift with real Claude agents and log the run (manual only)")
    parser.add_argument("target", help=f"a corpus fixture ({', '.join(FIXTURES)}) or a repo path")
    parser.add_argument("--state", type=int, choices=(1, 2), default=1,
                        help="fixture state to run live (2 runs state 1 canned first)")
    parser.add_argument("--from", dest="from_sha", default=None,
                        help="last-run commit to compare against (passed as --base)")
    parser.add_argument("--base", default=None, help="passed to start")
    parser.add_argument("--full", action="store_true", help="passed to start")
    parser.add_argument("--check", action="store_true", help="passed to start")
    parser.add_argument("--keep", default=None, help="copy the workdir to this directory")
    parser.add_argument("--resume", choices=("verify", "finish"), default=None,
                        help="continue the run in the workdir from this stage, reusing the "
                             "agent outputs already there; its live-run.json's calls count")
    parser.add_argument("--budget", type=float, default=2.0, help="dollars per agent call")
    parser.add_argument("--model-override", default=None,
                        help="run every agent on this model instead of the plan's")
    parser.add_argument("--workdir", default=None, help="default: <repo>/.document-drift")
    parser.add_argument("--claude", default=None, help="claude launcher (default: on PATH)")
    parser.add_argument("--parallel", type=int, default=4, help="agent calls at a time")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds per agent call")
    parser.add_argument("--log", default=None, help=f"default: {LOG_PATH}")
    return parser.parse_args(argv)


def resolve_target(target: str) -> tuple[str | None, Path | None]:
    """(fixture name, None) for a bare fixture name, else (None, repository path); raises
    ValueError for neither."""
    if target in FIXTURES and target == Path(target).name:
        return target, None
    path = Path(target)
    if not path.is_dir():
        raise ValueError(f"{target} is neither a corpus fixture ({', '.join(FIXTURES)}) "
                         "nor a directory")
    return None, path


@contextlib.contextmanager
def _maybe_pinned(date: str | None) -> Iterator[None]:
    if date is None:
        yield
    else:
        with pinned_dates(date):
            yield


def _prepare(name: str, state: int) -> Path:
    """Replay fixture ``name`` to a temporary directory, ready for a live run at ``state``."""
    tmp = Path(tempfile.mkdtemp(prefix=f"dd-live-{name}-"))
    if state == 1:
        return prepare_fixture(name, tmp / name, until_tag="state1")
    repo = run_fixture(name, 1, tmp).repo
    merge_drift_branch(repo, CANNED_BRANCH, DATES[1])
    continue_fixture(name, repo, after_tag="state1")
    return repo


def _write_record(workdir: Path, repo: Path, calls: Sequence[Call], row: str = "") -> None:
    """``live-run.json``: every call made so far (and the row, once rendered)."""
    if not workdir.is_dir():
        return  # start never ran far enough to dispatch anything
    record = {"repo": str(repo), "calls": [asdict(c) for c in calls], "row": row}
    (workdir / "live-run.json").write_bytes(
        (json.dumps(record, indent=1) + "\n").encode("utf-8"))


def live_run(args: argparse.Namespace, claude: str, fixture: str | None,
             path: Path | None, log: Path) -> int:
    """Prepare the repository, drive the stages, score, log the row, keep the workdir."""
    repo = (_prepare(fixture, args.state) if fixture is not None else path)
    assert repo is not None
    repo = repo.resolve()
    workdir = (Path(args.workdir) if args.workdir else repo / ".document-drift").resolve()
    base = args.from_sha or args.base
    flags = [*(["--base", base] if base else []), *(["--full"] if args.full else []),
             *(["--check"] if args.check else [])]
    date = DATES[args.state] if fixture is not None else None
    if date is not None:
        flags += ["--date", date]
    inside = workdir == repo or repo in workdir.parents
    run = Run(repo, workdir, flags, parallel=args.parallel, dispatch={
        "claude": claude, "budget": args.budget, "cwd": repo,
        "add_dir": None if inside else workdir, "model_override": args.model_override,
        "timeout": args.timeout})
    notes: list[str] = []
    if args.resume:
        record = workdir / "live-run.json"
        if not record.is_file():
            print(f"error: nothing to resume: {record} is missing", file=sys.stderr)
            return EXIT_REFUSED
        run.calls.extend(Call(**c) for c in json.loads(record.read_text("utf-8"))["calls"])
        notes.append(f"resumed at {args.resume} with {len(run.calls)} earlier calls; "
                     "wall time from the resume")
    if args.from_sha:
        notes.append(f"from {args.from_sha[:7]} (as --base)")
    if args.check:
        notes.append("--check run: nothing applied")
    if fixture is not None and args.state == 2:
        notes.append("state 1 canned")
    if args.model_override:
        notes.append(f"models overridden: {args.model_override}")
    code = EXIT_OK
    began = time.monotonic()
    try:
        with _maybe_pinned(date):
            drive(run, args.check, args.resume)
    except StageFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        notes.append(f"stopped: {exc}")
        code = EXIT_STAGE
    except Exception as exc:  # the paid calls so far are still recorded and logged
        traceback.print_exc(file=sys.stderr)
        notes.append(f"crashed: {type(exc).__name__}: {exc}")
        code = EXIT_STAGE
    finally:  # also on KeyboardInterrupt: never lose the record of a paid call
        _write_record(workdir, repo, run.calls)
    wall = time.monotonic() - began
    failed = Counter((c.id, c.status) for c in run.calls if c.status != "ok")
    if failed:
        notes.append("failed calls " + ", ".join(
            f"{eid} {status}" + (f" x{n}" if n > 1 else "")
            for (eid, status), n in failed.items()))
    retries = sum(1 for c in run.calls if c.retry)
    if retries:
        notes.append(f"{retries} retried")
    planted = decoys = None
    if fixture is not None and workdir.is_dir():
        try:
            result = score(fixture, args.state, workdir)
        except Exception as exc:  # a crashed run can leave files evaluate cannot read
            notes.append(f"not scored: {type(exc).__name__}: {exc}")
        else:
            planted = (result.caught, result.planted)
            decoys = (result.touched, result.decoys)
            for line in result.lines:
                print(line)
            notes += result.notes()
    repository = (f"{fixture} (state {args.state})" if fixture is not None else repo.name)
    row = render_row(workdir, date=Date.today().isoformat(), repository=repository,
                     calls=run.calls, wall_seconds=wall, planted=planted, decoys=decoys,
                     notes="; ".join(notes))
    _write_record(workdir, repo, run.calls, row)
    append_row(log, row)
    print(row, end="")
    if args.keep and workdir.is_dir():
        shutil.copytree(workdir, Path(args.keep), dirs_exist_ok=True)
        print(f"workdir copied to {args.keep}")
    print(f"repository: {repo}\nworkdir: {workdir}")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    # The stage summaries may hold characters the console code page cannot encode.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    claude = args.claude or shutil.which("claude") or ""
    if resolve_claude(claude) is None:
        print("error: no claude launcher found; install Claude Code or pass --claude",
              file=sys.stderr)
        return EXIT_REFUSED
    if args.from_sha and args.base:
        print("error: give --from or --base, not both", file=sys.stderr)
        return EXIT_REFUSED
    log = Path(args.log) if args.log else LOG_PATH
    try:
        fixture, path = resolve_target(args.target)
        if fixture is None and args.state != 1:
            raise ValueError("--state applies to a corpus fixture only")
        check_log(log)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    return live_run(args, claude, fixture, path, log)


if __name__ == "__main__":
    sys.exit(main())
