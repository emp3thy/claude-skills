"""Run the whole scan chain with real Claude scouts and verifiers (spec 6, live policy).

Manual only, never in CI. Given a corpus fixture name (replayed into a temporary
directory through ``tests/helpers/make_history.py``) or any repository path, the
harness runs the phase 1 signal scripts, ``plan_scan.py``, one ``claude -p``
call per scout prompt, ``merge_findings.py``, ``verify_prompts.py``, one call
per verifier batch, ``apply_verdicts.py`` and ``rank.py``; when a
``planted.json`` exists it scores the result with ``evaluate.py`` and appends a
row to ``docs/evaluation-log.md``.

Every ``claude`` call is a list argv in print mode with JSON output, structured
output from the contract's JSON schema (an array contract travels wrapped in a
one-key object, because ``--json-schema`` only accepts an object at the top
level), read-only tools only, user settings and MCP servers excluded
(``--setting-sources project --strict-mcp-config
--disable-slash-commands``; ``--bare`` loses auth on this machine) and a per-call
dollar budget. A reply that fails the contract is retried once with an appended
instruction; a second failure stops the run with exit 4. Every reply is walked
through ``redaction.redact`` before it is written, because the agents read the
repository under scan and the harness is a writer like any other script.

Direct-path invocable (no package imports): `python live_run.py <fixture-or-repo>`.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from apply_verdicts import apply
from categories import SCOUT_OUTPUT_SCHEMA
from config import ConfigError, load_config
from evaluate import evaluate, render_table
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from rank import rank
from redaction import redact
from rules import SCHEMA_VERSION as RULES_SCHEMA_VERSION
from rules import run_rules
from verify_prompts import VERDICT_SCHEMA, build_verify_plan

ISOLATION: Final[tuple[str, ...]] = (
    "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
)
TOOLS: Final[str] = "Read,Grep,Glob"
# Windows caps a CreateProcess command line at 32 767 characters and the prompt is the
# positional argument; a rendered prompt with 40 leads stays well under this.
PROMPT_LIMIT: Final[int] = 30_000
RETRY_SUFFIX: Final[str] = (
    "\n\nThe previous response failed the schema; re-emit valid JSON only.\n"
)
# ``--json-schema`` wires the document straight into a tool's ``input_schema``, which
# the API rejects unless its type is ``object`` (400 tools.N.custom.input_schema.type).
# The verifier contract is an array, so it travels wrapped under this key.
WRAPPER_KEY: Final[str] = "verdicts"
LOG_HEADER: Final[str] = (
    "| date | fixture | model | churn_months | tier_a_precision | reported_precision "
    "| decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
)


@dataclass(slots=True)
class DispatchResult:
    """The outcome of one prompt: its status, how many calls it took and what it cost."""

    status: str
    attempts: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    last_prompt: str = ""


def launcher_argv(claude: str) -> list[str]:
    """Split a launcher into argv tokens; ``"<python> <script>"`` is supported.

    ``posix=True`` would eat the backslashes in a Windows path, so the platform's
    own lexing rules are used and any quotes the non-posix lexer leaves behind are
    stripped from each token.
    """
    if " " not in claude:
        return [claude]
    parts = shlex.split(claude, posix=os.name != "nt")
    return [
        token[1:-1] if len(token) > 1 and token[0] == token[-1] and token[0] in "\"'" else token
        for token in parts
    ]


def resolve_claude(claude: str) -> str | None:
    """The launcher's executable when it can be found on PATH or on disk, else ``None``."""
    parts = launcher_argv(claude)
    head = parts[0] if parts else ""
    if not head:
        return None
    found = shutil.which(head)
    if found is not None:
        return found
    return head if Path(head).is_file() else None


def prompt_text(prompt_file: Path) -> str:
    """The prompt's UTF-8 text, trimmed to ``PROMPT_LIMIT`` with a warning when oversized."""
    text = prompt_file.read_bytes().decode("utf-8")
    if len(text) > PROMPT_LIMIT:
        print(
            f"warning: {prompt_file.name} is {len(text)} chars; trimming to {PROMPT_LIMIT}",
            file=sys.stderr,
        )
        text = text[:PROMPT_LIMIT]
    return text


def wire_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """``schema`` in the shape ``--json-schema`` accepts: an object at the top level.

    The CLI hands the document to the model as a tool's ``input_schema``, and the
    API rejects anything but an object there, so an array contract (the verifier's)
    travels as a one-key object and comes back out through ``unwrap_payload``.
    """
    if schema.get("type") != "array":
        return schema
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [WRAPPER_KEY],
        "properties": {WRAPPER_KEY: schema},
    }


def unwrap_payload(payload: Any, schema: dict[str, Any]) -> Any:
    """The array back out of its wrapper; a reply that is already an array passes through."""
    if schema.get("type") == "array" and isinstance(payload, dict) and WRAPPER_KEY in payload:
        return payload[WRAPPER_KEY]
    return payload


def _argv(
    text: str, *, model: str, budget: float, schema: dict[str, Any], claude: str
) -> list[str]:
    return [
        *launcher_argv(claude), "-p", *ISOLATION,
        "--output-format", "json", "--json-schema", json.dumps(wire_schema(schema)),
        "--tools", TOOLS, "--allowedTools", TOOLS,
        "--model", model, "--max-budget-usd", f"{budget:.2f}",
        text,
    ]


def claude_argv(
    prompt_file: Path, *, model: str, budget: float, schema: dict[str, Any], claude: str
) -> list[str]:
    """The list argv for one read-only ``claude -p`` call over ``prompt_file``."""
    return _argv(
        prompt_text(prompt_file), model=model, budget=budget, schema=schema, claude=claude
    )


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def extract_reply(stdout: str) -> tuple[Any, float, str | None]:
    """(payload, cost, error): the agent's JSON reply from a ``claude -p`` envelope."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return None, 0.0, f"envelope is not JSON: {stdout[:200]}"
    if not isinstance(envelope, dict):
        return None, 0.0, "envelope is not an object"
    cost = float(envelope.get("total_cost_usd") or 0.0)
    if envelope.get("is_error") or envelope.get("subtype") != "success":
        return None, cost, str(envelope.get("result") or envelope.get("subtype") or "error")
    if envelope.get("structured_output") is not None:
        return envelope["structured_output"], cost, None
    try:
        return json.loads(_strip_fences(str(envelope.get("result", "")))), cost, None
    except json.JSONDecodeError:
        return None, cost, "result is not JSON"


def _valid(payload: Any, schema: dict[str, Any]) -> bool:
    """A structural check of the payload against the contract the call was given."""
    if schema.get("type") == "array":
        return isinstance(payload, list)
    return (
        isinstance(payload, dict)
        and all(key in payload for key in schema.get("required", []))
        and isinstance(payload.get("findings"), list)
    )


def redact_payload(payload: Any) -> Any:
    """``payload`` with every string value redacted, dicts and lists walked in place.

    Keys are structural and are left alone; numbers, booleans and null pass
    through untouched. An agent reads the repository under scan, so anything it
    hands back can quote a credential, and the harness writes that reply to disk.
    """
    if isinstance(payload, str):
        return redact(payload)
    if isinstance(payload, dict):
        return {key: redact_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload


def _write_payload(output_file: Path, payload: Any) -> None:
    """LF-only JSON for either payload shape (``write_json`` only takes a document)."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    safe = redact_payload(payload)
    if isinstance(safe, dict):
        write_json(output_file, safe)
    else:
        output_file.write_bytes((json.dumps(safe, indent=2) + "\n").encode("utf-8"))


def dispatch(
    prompt_file: Path,
    output_file: Path,
    *,
    cwd: Path,
    model: str,
    budget: float,
    schema: dict[str, Any],
    claude: str,
    timeout: int,
) -> DispatchResult:
    """One agent call, retried once with an appended instruction when the reply is invalid."""
    result = DispatchResult(status="failed")
    text = prompt_text(prompt_file)
    for attempt in (1, 2):
        result.attempts = attempt
        result.last_prompt = text
        argv = _argv(text, model=model, budget=budget, schema=schema, claude=claude)
        try:
            proc = subprocess.run(
                argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            result.error = str(exc)
            return result
        payload, cost, error = extract_reply(proc.stdout)
        payload = unwrap_payload(payload, schema)
        result.cost_usd += cost
        if error is None and _valid(payload, schema):
            _write_payload(output_file, payload)
            result.status = "ok"
            result.error = None
            return result
        result.error = error or "payload failed the contract"
        if proc.returncode != 0:
            # The envelope carries no exit status, so keep the CLI's own complaint: a
            # manual run needs to tell "bad reply" from "the CLI refused to start".
            stderr = (proc.stderr or "").strip()[:200]
            result.error = f"{result.error} (exit {proc.returncode}: {stderr})"
        text = text + RETRY_SUFFIX
    return result


def _ratio_cell(value: float | None) -> str:
    """A ratio as two decimals, or ``-`` when there was nothing to divide."""
    return "-" if value is None else f"{value:.2f}"


def log_row(
    log_path: Path,
    fixture: str,
    model: str,
    report: dict[str, Any],
    *,
    churn_months: int | None,
    scouts: int,
    verifiers: int,
    cost: float,
) -> None:
    """Append one evaluation row (LF-only), creating the table header when absent."""
    families = report.get("families") or {}
    # tier_a_precision is the release bar and counts tier A findings alone; the
    # per-family reported and precise counts span tiers A and B, so their ratio is
    # logged beside it as reported_precision rather than in its place.
    tier_a = report.get("tier_a") or {}
    reported = sum(int(stats.get("reported", 0)) for stats in families.values())
    precise = sum(int(stats.get("precise", 0)) for stats in families.values())
    recall = " ".join(
        f"{name}={stats['recall']:.2f}"
        for name, stats in sorted(families.items())
        if stats.get("recall") is not None
    )
    row = (
        f"| {datetime.now(UTC).date().isoformat()} | {fixture} | {model} "
        f"| {churn_months if churn_months is not None else '-'} "
        f"| {_ratio_cell(tier_a.get('precision'))} "
        f"| {_ratio_cell(precise / reported if reported else None)} "
        f"| {report.get('decoys_in_tier_a', 0)} | {report.get('decoys_in_top_n', 0)} "
        f"| {recall or '-'} | {scouts} | {verifiers} | {cost:.2f} |\n"
    )
    if not log_path.is_file():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(LOG_HEADER.encode("utf-8"))
    log_path.write_bytes(log_path.read_bytes() + row.encode("utf-8"))


def _signals(
    repo: Path, workdir: Path, config: dict[str, Any], churn_months: int | None
) -> None:
    """inventory.json, coupling.json, patterns.json and rule-findings.json under ``workdir``."""
    inventory, coupling = build_all(repo, churn_months=churn_months, config=config)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, config)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(str(entry["path"]), 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, config)
    write_json(
        workdir / "rule-findings.json",
        {"schema_version": RULES_SCHEMA_VERSION, "findings": findings, "leads": leads},
    )


def _needs_call(output: Path, *, skip_agents: bool, label: str) -> bool:
    """True when the agent must be called; raises when ``--skip-agents`` has no cached reply."""
    if not skip_agents:
        return True
    if output.is_file():
        return False
    raise RuntimeError(f"--skip-agents but {output} is missing ({label})")


def run_chain(
    repo: Path,
    workdir: Path,
    *,
    families: str | None,
    top: int | None,
    preset: str | None,
    churn_months: int | None,
    model: str,
    budget: float,
    claude: str,
    timeout: int,
    skip_agents: bool,
    planted: Path | None = None,
    log_path: Path | None = None,
    fixture_name: str = "",
) -> dict[str, Any]:
    """Signals, scouts, merge, verifiers, tiers, ranking and (with planted.json) scoring."""
    repo = repo.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    config = load_config(repo)
    planted_doc = json.loads(planted.read_bytes()) if planted and planted.is_file() else None
    planted_churn = None
    if planted_doc and isinstance(planted_doc.get("churn_months"), int):
        planted_churn = int(planted_doc["churn_months"])
    # The fixture's scoring window always wins: a conflicting --churn-months would
    # otherwise silently score the run against a table built at a different window.
    if planted_churn is not None:
        if churn_months is not None and churn_months != planted_churn:
            print(
                f"warning: --churn-months {churn_months} ignored; "
                f"{fixture_name or repo.name} scores at churn_months {planted_churn}",
                file=sys.stderr,
            )
        churn_months = planted_churn
    _signals(repo, workdir, config, churn_months)

    plan, prompts = build_plan(workdir, config, families=families, top=top)
    write_plan(workdir, plan, prompts)
    cost = 0.0
    scout_calls = 0
    for entry in plan["entries"]:
        output = workdir / str(entry["output"])
        if not _needs_call(output, skip_agents=skip_agents, label=str(entry["family"])):
            continue
        res = dispatch(
            workdir / str(entry["prompt"]), output, cwd=repo, model=model, budget=budget,
            schema=SCOUT_OUTPUT_SCHEMA, claude=claude, timeout=timeout,
        )
        cost += res.cost_usd
        scout_calls += 1
        if res.status != "ok":
            raise RuntimeError(f"scout {entry['family']} failed: {res.error}")

    write_json(workdir / "candidates.json", merge(workdir, repo, config))
    top_n = int(top if top is not None else plan["top"])
    vplan, vprompts = build_verify_plan(workdir, repo, config, top_n)
    for rel, text in vprompts.items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    write_json(workdir / "verify-plan.json", vplan)

    verifier_calls = 0
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for batch in vplan["batches"]:
        output = workdir / str(batch["output"])
        if _needs_call(output, skip_agents=skip_agents, label=str(batch["prompt"])):
            res = dispatch(
                workdir / str(batch["prompt"]), output, cwd=repo, model=model, budget=budget,
                schema=VERDICT_SCHEMA, claude=claude, timeout=timeout,
            )
            cost += res.cost_usd
            verifier_calls += 1
            if res.status != "ok":
                raise RuntimeError(f"verifier {batch['prompt']} failed: {res.error}")
        verdicts[str(batch["output"])] = json.loads(output.read_bytes())

    candidates = json.loads((workdir / "candidates.json").read_bytes())["candidates"]
    verified = apply(candidates, vplan, verdicts)
    write_json(workdir / "verified.json", verified)
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    chosen_preset = preset or str(config["ranking"]["preset"])
    ranked = rank(verified, inventory, config, preset=chosen_preset, top=top_n)
    write_json(workdir / "ranked.json", ranked)

    summary: dict[str, Any] = {
        "scout_calls": scout_calls, "verifier_calls": verifier_calls,
        "cost_usd": cost, "top_n": ranked["top_n"],
    }
    if planted_doc is not None:
        report = evaluate(verified["findings"], planted_doc, set(ranked["top_n"]), top=top_n)
        write_json(workdir / "evaluation.json", report)
        print(render_table(report))
        summary["report"] = report
        if log_path is not None:
            log_row(
                log_path, fixture_name or repo.name, model, report,
                churn_months=churn_months,
                scouts=scout_calls, verifiers=verifier_calls, cost=cost,
            )
    print(
        f"agent calls: {scout_calls} scouts, {verifier_calls} verifier batches; cost ${cost:.2f}"
    )
    return summary


def _replay(name: str, dest: Path) -> Path:
    """Replay a corpus fixture through the test helper (mypy covers scripts/ only)."""
    helper = Path(__file__).resolve().parent.parent / "tests" / "helpers" / "make_history.py"
    subprocess.run([sys.executable, str(helper), name, str(dest)], check=True, timeout=300)
    return dest


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the scan chain with real Claude agents (manual, never CI)"
    )
    parser.add_argument(
        "target", help="corpus fixture name (service-py, web-ts, mixed-decoys) or a repo path"
    )
    parser.add_argument("--workdir", default=None, help="scan workdir (default: <repo>/.tech-debt)")
    parser.add_argument(
        "--families", default=None, help="default, quick, deep or a comma-separated list"
    )
    parser.add_argument("--top", type=int, default=None, help="findings to report")
    parser.add_argument("--preset", default=None, help="ranking preset (default: config)")
    parser.add_argument("--churn-months", type=int, default=None, help="git history window")
    parser.add_argument("--model", default="sonnet", help="claude model alias")
    parser.add_argument("--max-budget-usd", type=float, default=1.0, help="per agent call")
    parser.add_argument("--claude", default=None, help="claude executable (default: on PATH)")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per agent call")
    parser.add_argument(
        "--log", default=None, help="evaluation log to append to (default: docs/evaluation-log.md)"
    )
    parser.add_argument(
        "--skip-agents", action="store_true", help="reuse existing scout and verdict files"
    )
    args = parser.parse_args(argv)

    corpus = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "corpus"
    planted: Path | None = None
    fixture_name = ""
    # Only a bare name is a fixture: ``corpus / "C:\\repo"`` yields the absolute path on
    # Windows, so an absolute repo path would otherwise be mistaken for a corpus fixture.
    bare = args.target == Path(args.target).name
    if bare and (corpus / args.target).is_dir():
        fixture_name = args.target
        planted = corpus / args.target / "planted.json"
        repo = _replay(args.target, Path(tempfile.mkdtemp(prefix=f"live-{args.target}-")))
    else:
        repo = Path(args.target)
        if not repo.is_dir():
            print(f"error: {repo} is not a directory or a corpus fixture", file=sys.stderr)
            return 2
        candidate = repo / "planted.json"
        planted = candidate if candidate.is_file() else None

    claude = args.claude or shutil.which("claude") or ""
    if not args.skip_agents and resolve_claude(claude) is None:
        print(
            "error: claude executable not found; install Claude Code or pass --claude",
            file=sys.stderr,
        )
        return 3
    workdir = Path(args.workdir) if args.workdir else repo / ".tech-debt"
    default_log = Path(__file__).resolve().parents[3] / "docs" / "evaluation-log.md"
    log = Path(args.log) if args.log else default_log
    try:
        run_chain(
            repo, workdir, families=args.families, top=args.top, preset=args.preset,
            churn_months=args.churn_months, model=args.model, budget=args.max_budget_usd,
            claude=claude, timeout=args.timeout, skip_agents=args.skip_agents,
            planted=planted, log_path=log, fixture_name=fixture_name,
        )
    except (ConfigError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    print(f"workdir: {workdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
