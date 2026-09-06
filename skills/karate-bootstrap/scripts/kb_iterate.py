"""Phase 6 of karate-bootstrap: bookkeeping for the fix loop (design spec 5.7).

``next`` groups the failures in report.json by signature and prints the largest group with
its evidence bundle. ``log`` appends one iteration record (hypothesis, change, classification)
to a JSONL log; it is written before the change is made. ``check-stop`` applies the stop
conditions and prints ``done`` (no failures), ``continue``, or ``stop:<reason>`` with exit 6.

Usage:
    python scripts/kb_iterate.py next --report karate-tests/target/report.json \
        --tests-dir karate-tests
    python scripts/kb_iterate.py log --log karate-tests/.iterations.log --signature <sig> \
        --hypothesis "..." --change "..." \
        --classification infra|stub-or-seed|expectation|app-defect [--unfixable]
    python scripts/kb_iterate.py check-stop --log karate-tests/.iterations.log \
        --report karate-tests/target/report.json --max-iterations 15

Signature: feature | scenario (collapsed to <outline> for Scenario Outline rows) | first failing
step | error class (first error line with numbers, quoted strings and URLs normalised).

Exit codes: 0 continue or done, 2 bad input, 5 missing report, 6 stop condition met.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kb_common import (
    EXIT_OK,
    EXIT_STOPPED,
    KbError,
    read_json,
    read_text,
    require_file,
    run_cli,
)

CLASSIFICATIONS = ("infra", "stub-or-seed", "expectation", "app-defect")
REPEAT_LIMIT = 3
LOG_TAIL_LINES = 80

_URL_RE = re.compile(r"https?://\S+")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_NUMBER_RE = re.compile(r"\d+")


# --- signatures --------------------------------------------------------------------------


def error_class(error: str) -> str:
    """First non-empty error line with URLs, quoted strings and numbers normalised."""
    first = next((line.strip() for line in error.splitlines() if line.strip()), "")
    first = _URL_RE.sub("URL", first)
    first = _QUOTED_RE.sub("'?'", first)
    return _NUMBER_RE.sub("N", first)[:160]


def signature(failure: dict[str, Any]) -> str:
    scenario = "<outline>" if failure.get("outline") else str(failure.get("scenario", ""))
    return "|".join([str(failure.get("feature", "")), scenario, str(failure.get("step", "")),
                     error_class(str(failure.get("error", "")))])


def group_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Failure groups, largest first; ties keep first-seen order (sorted is stable)."""
    groups: dict[str, dict[str, Any]] = {}
    for failure in report.get("failed", []):
        sig = signature(failure)
        group = groups.setdefault(sig, {
            "signature": sig,
            "count": 0,
            "feature": failure.get("feature"),
            "scenario": failure.get("scenario"),
            "outline": bool(failure.get("outline")),
            "step": failure.get("step"),
            "error_class": error_class(str(failure.get("error", ""))),
            "error": failure.get("error", ""),
            "tags": list(failure.get("tags", [])),
        })
        group["count"] += 1
    return sorted(groups.values(), key=lambda g: -int(g["count"]))


# --- evidence ----------------------------------------------------------------------------


def _tail(path: Path, lines: int = LOG_TAIL_LINES) -> str | None:
    if not path.is_file():
        return None
    return "\n".join(read_text(path).splitlines()[-lines:])


def evidence(tests_dir: Path) -> dict[str, Any]:
    """Evidence bundle from the files Containers.java and Stubs.unmatched() write under target/."""
    target = tests_dir / "target"
    unmatched_path = target / "stubs-unmatched.json"
    unmatched: Any = None
    if unmatched_path.is_file():
        try:
            unmatched = json.loads(read_text(unmatched_path))
        except json.JSONDecodeError:
            unmatched = read_text(unmatched_path)
    return {
        "app_log_tail": _tail(target / "app.log"),
        "db_manager_log_tail": _tail(target / "db-manager.log"),
        "stubs_unmatched": unmatched,
    }


# --- iteration log -----------------------------------------------------------------------


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in read_text(path).splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def append_log(path: Path, record: dict[str, Any]) -> int:
    """Append one iteration; returns its 1-based number."""
    if record.get("classification") not in CLASSIFICATIONS:
        raise KbError(
            f"unknown classification {record.get('classification')!r}; "
            f"expected one of {CLASSIFICATIONS}"
        )
    records = read_log(path)
    number = len(records) + 1
    full = {"iteration": number, "at": datetime.now(UTC).isoformat(timespec="seconds"), **record}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(full) + "\n")
    return number


def check_stop(records: list[dict[str, Any]], report: dict[str, Any], max_iterations: int) -> str:
    if not report.get("failed"):
        return "done"
    if len(records) >= max_iterations:
        return f"stop:iteration-cap {max_iterations}"
    if records and records[-1].get("unfixable"):
        return "stop:infra-unfixable"
    recent = records[-REPEAT_LIMIT:]
    if len(recent) == REPEAT_LIMIT and len({str(r.get("signature")) for r in recent}) == 1:
        return f"stop:repeated-signature {recent[-1].get('signature')}"
    return "continue"


# --- CLI ---------------------------------------------------------------------------------


def _cmd_next(args: argparse.Namespace) -> int:
    report = read_json(require_file(args.report, "report.json"))
    groups = group_failures(report)
    if not groups:
        print(json.dumps({"done": True}))
        return EXIT_OK
    top = dict(groups[0])
    top["groups"] = len(groups)
    top["evidence"] = evidence(args.tests_dir)
    print(json.dumps(top, indent=2))
    return EXIT_OK


def _cmd_log(args: argparse.Namespace) -> int:
    number = append_log(args.log, {
        "signature": args.signature,
        "hypothesis": args.hypothesis,
        "change": args.change,
        "classification": args.classification,
        "unfixable": bool(args.unfixable),
    })
    print(f"iteration {number} logged -> {args.log}")
    return EXIT_OK


def _cmd_check_stop(args: argparse.Namespace) -> int:
    report = read_json(require_file(args.report, "report.json"))
    verdict = check_stop(read_log(args.log), report, args.max_iterations)
    print(verdict)
    return EXIT_STOPPED if verdict.startswith("stop:") else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fix-loop bookkeeping for karate-bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="Print the largest failure group with its evidence")
    nxt.add_argument("--report", type=Path, required=True,
                     help="report.json from kb_report.py parse")
    nxt.add_argument("--tests-dir", type=Path, required=True, help="karate-tests directory")
    nxt.set_defaults(func=_cmd_next)

    log = sub.add_parser("log", help="Record one iteration before making the change")
    log.add_argument("--log", type=Path, required=True, help=".iterations.log (JSONL)")
    log.add_argument("--signature", required=True)
    log.add_argument("--hypothesis", required=True)
    log.add_argument("--change", required=True)
    log.add_argument("--classification", choices=CLASSIFICATIONS, required=True)
    log.add_argument("--unfixable", action="store_true",
                     help="infra failure not fixable from karate-tests/; check-stop stops")
    log.set_defaults(func=_cmd_log)

    stop = sub.add_parser("check-stop", help="Apply the stop conditions")
    stop.add_argument("--log", type=Path, required=True)
    stop.add_argument("--report", type=Path, required=True)
    stop.add_argument("--max-iterations", type=int, default=15)
    stop.set_defaults(func=_cmd_check_stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
