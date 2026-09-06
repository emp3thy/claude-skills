"""Phases 6 and 7 of karate-bootstrap: parse Karate reports, render the README.

``parse`` reads Karate's cucumber JSON (one ``<packageQualifiedName>.json`` per feature under
``target/karate-reports``) into the report contract the green gate and kb_iterate.py consume:
``{"passed", "skipped", "failed": [{"feature", "scenario", "outline", "tags", "step", "error"}]}``.
``skipped`` counts ``@known-defect`` scenarios in the features directory, because the runner's
tag filter removes them before any report is written.

A run that started Maven but produced no feature JSON (the app or the db-manager never came
up) still gets a report: one synthetic ``(startup)`` failure carrying the tail of
``target/app.log`` or ``target/db-manager.log``, so the fix loop can classify it as infra
instead of the run dying on a missing postcondition. Exit 5 is kept for the one case that
really is a missing output: ``target/`` itself does not exist, so Maven never ran.

``summary`` fills ``README.md.tmpl`` from the ledger, defects.md and the report, and prints the
counts table.

Usage:
    python scripts/kb_report.py parse --reports karate-tests/target/karate-reports \
        --out karate-tests/target/report.json [--features karate-tests/src/test/resources/features]
    python scripts/kb_report.py summary --ledger karate-tests/flow-map.yaml \
        --defects karate-tests/defects.md --report karate-tests/target/report.json \
        --template <skill>/templates/karate-tests/README.md.tmpl --out karate-tests/README.md

Exit codes: 0 ok, 5 when target/ is missing (Maven never ran) or an input is missing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from string import Template
from typing import Any

from flow_map import load_ledger
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_OK,
    KbError,
    read_json,
    read_text,
    require_file,
    run_cli,
    write_json,
)
from kb_features import known_defect_scenario_count

_DEFECT_HEADING_RE = re.compile(r"^## (DEF-\d+:.*?)\s*$", re.MULTILINE)


# --- parse ------------------------------------------------------------------------------


def cucumber_files(reports_dir: Path) -> list[Path]:
    """Karate writes ``<packageQualifiedName>.json`` per feature; the summary is a ``.txt``."""
    return sorted(p for p in reports_dir.glob("*.json") if p.is_file())


def _failed_entry(uri: str, element: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    result = step.get("result", {})
    return {
        "feature": uri,
        "scenario": str(element.get("name", "")),
        "outline": element.get("keyword") == "Scenario Outline",
        "tags": [str(t["name"]) for t in element.get("tags", []) if "name" in t],
        "step": f"{str(step.get('keyword', '*')).strip()} {step.get('name', '')}".strip(),
        "error": str(result.get("error_message", "")),
    }


STARTUP_LOG_NAMES = ("app.log", "db-manager.log")
STARTUP_LOG_TAIL_LINES = 40
NO_REPORTS_ERROR = "no karate reports were produced"


def startup_log_tail(target_dir: Path, lines: int = STARTUP_LOG_TAIL_LINES) -> str:
    """The tail of the container log the harness wrote under ``target/`` (Containers.java).

    ``app.log`` first, then ``db-manager.log``; a fixed message when neither exists.
    """
    for name in STARTUP_LOG_NAMES:
        path = target_dir / name
        if path.is_file():
            tail = "\n".join(read_text(path).splitlines()[-lines:])
            if tail.strip():
                return tail
    return NO_REPORTS_ERROR


def startup_failure_report(target_dir: Path) -> dict[str, Any]:
    """The report for a run that produced no feature JSON: one synthetic infra failure.

    The fix loop needs a report.json to exist even when nothing ran, so Step 8 can classify
    the startup failure instead of the run aborting on a missing postcondition (spec 5.7).
    """
    return {
        "passed": 0,
        "skipped": 0,
        "failed": [{
            "feature": "(startup)",
            "scenario": "containers and application start",
            "outline": False,
            "tags": [],
            "step": "Containers.start",
            "error": startup_log_tail(target_dir),
        }],
    }


def parse_reports(reports_dir: Path, features_dir: Path | None) -> dict[str, Any]:
    files = cucumber_files(reports_dir)
    if not files:
        target = reports_dir.parent
        if not target.is_dir():
            raise KbError(f"{target} does not exist; mvn test never ran", EXIT_MISSING_OUTPUT)
        return startup_failure_report(target)
    passed = 0
    failed: list[dict[str, Any]] = []
    for path in files:
        data = json.loads(read_text(path))
        if not isinstance(data, list):
            continue
        for feature in data:
            uri = str(feature.get("uri") or feature.get("name") or path.stem)
            for element in feature.get("elements", []):
                if element.get("type") != "scenario":
                    continue
                failing = next(
                    (s for s in element.get("steps", [])
                     if s.get("result", {}).get("status") == "failed"),
                    None,
                )
                if failing is None:
                    passed += 1
                else:
                    failed.append(_failed_entry(uri, element, failing))
    skipped = 0
    if features_dir is not None and features_dir.is_dir():
        skipped = sum(known_defect_scenario_count(read_text(f))
                      for f in sorted(features_dir.rglob("*.feature")))
    return {"passed": passed, "skipped": skipped, "failed": failed}


def default_features_dir(reports_dir: Path) -> Path | None:
    """The module's features directory when reports live at ``<module>/target/karate-reports``."""
    module = reports_dir.resolve().parent.parent
    candidate = module / "src" / "test" / "resources" / "features"
    return candidate if candidate.is_dir() else None


# --- summary ----------------------------------------------------------------------------


def defect_titles(defects_text: str) -> list[str]:
    return _DEFECT_HEADING_RE.findall(defects_text)


def summary_values(ledger: dict[str, Any], defects_text: str,
                   report: dict[str, Any]) -> dict[str, str]:
    entries: list[dict[str, Any]] = ledger["entry_points"]
    exits = [e for entry in entries for e in entry.get("exits", [])]
    app = ledger["app"]
    readiness = app.get("readiness") or {}
    auth = app.get("auth") or {}
    migrations = app.get("migrations") or {}
    overrides = [
        f"- {entry['id']}: {json.dumps(item, sort_keys=True)}"
        for entry in entries for item in entry.get("observed_overrides", [])
    ]
    notes: list[str] = []
    if readiness.get("source") == "fallback":
        notes.append("- readiness: no manifest probe; the harness waits for the container port")
    if auth.get("mode") == "blocked":
        notes.append("- auth: blocked (no switch, no configurable issuer); 401/403 not exercised")
    if auth.get("mode") == "disabled" and auth.get("confirmed") is False:
        notes.append(f"- auth: switch {auth.get('key')} was never confirmed")
    if migrations.get("also_on_boot"):
        notes.append("- migrations: the app also migrates on boot; the db-manager image runs first")
    failing = len(report.get("failed", []))
    scenarios = int(report.get("passed", 0)) + int(report.get("skipped", 0)) + failing

    def count(kind: str) -> str:
        return str(sum(1 for e in exits if e.get("kind") == kind))

    return {
        "repo": str(ledger["repo"]),
        "stack": f"{ledger['stack'].get('framework')} ({ledger['stack'].get('language')})",
        "entry_points": str(len(entries)),
        "exits_db": count("db-write"),
        "exits_amq": count("amq-publish"),
        "exits_http": count("http-out"),
        "scenarios": str(scenarios),
        "rules_rows": str(sum(int((entry.get("rules") or {}).get("count") or 0)
                              for entry in entries)),
        "passing": str(report.get("passed", 0)),
        "failing": str(failing),
        "quarantined": str(report.get("skipped", 0)),
        "auth_mode": str(auth.get("mode", "none")),
        "migrations_image": str(migrations.get("image") or "not set"),
        "readiness": str(readiness.get("path") or f"port {app.get('port')} (fallback)"),
        "overrides": "\n".join(overrides) or "- none",
        "defects": "\n".join(f"- {title}" for title in defect_titles(defects_text)) or "- none",
        "notes": "\n".join(notes) or "- none",
    }


def render_summary(template_text: str, values: dict[str, str]) -> str:
    return Template(template_text).safe_substitute(values)


def counts_table(values: dict[str, str]) -> str:
    rows = (
        ("Entry points", values["entry_points"]),
        ("DB write exits", values["exits_db"]),
        ("AMQ publish exits", values["exits_amq"]),
        ("Outbound HTTP exits", values["exits_http"]),
        ("Scenarios", values["scenarios"]),
        ("Validation rule rows", values["rules_rows"]),
        ("Passing", values["passing"]),
        ("Failing", values["failing"]),
        ("Quarantined", values["quarantined"]),
    )
    return "\n".join(f"{label:<22} {value:>6}" for label, value in rows)


# --- CLI --------------------------------------------------------------------------------


def _cmd_parse(args: argparse.Namespace) -> int:
    features = args.features if args.features is not None else default_features_dir(args.reports)
    report = parse_reports(args.reports, features)
    write_json(args.out, report)
    print(f"passed: {report['passed']}  skipped: {report['skipped']}  "
          f"failed: {len(report['failed'])} -> {args.out}")
    return EXIT_OK


def _cmd_summary(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    defects_text = read_text(args.defects) if args.defects.is_file() else ""
    report = read_json(require_file(args.report, "report.json"))
    template_text = read_text(require_file(args.template, "README.md.tmpl"))
    values = summary_values(ledger, defects_text, report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_summary(template_text, values), encoding="utf-8")
    print(counts_table(values))
    print(f"README -> {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Karate reports and render the README")
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="Cucumber JSON -> report.json")
    parse.add_argument("--reports", type=Path, required=True, help="target/karate-reports")
    parse.add_argument("--out", type=Path, required=True, help="report.json to write")
    parse.add_argument("--features", type=Path, default=None,
                       help="features dir for the @known-defect count (default: module layout)")
    parse.set_defaults(func=_cmd_parse)

    summary = sub.add_parser("summary", help="Render README.md from the ledger, defects and report")
    summary.add_argument("--ledger", type=Path, required=True)
    summary.add_argument("--defects", type=Path, required=True)
    summary.add_argument("--report", type=Path, required=True)
    summary.add_argument("--template", type=Path, required=True, help="README.md.tmpl")
    summary.add_argument("--out", type=Path, required=True)
    summary.set_defaults(func=_cmd_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
