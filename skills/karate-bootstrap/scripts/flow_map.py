"""The flow-map ledger: karate-bootstrap's only memory across phases.

Subcommands:
    next        --phase traced|generated --ledger PATH
                prints JSON {id, kind, handler, cheat_sheet} for the next pending entry,
                or {"done": true}
    merge       ENTRY_JSON --ledger PATH
                merges one trace subagent result into its entry
    mark        --entry ID (--generated|--tested|--passing|--failing) --ledger PATH
    validate    --phase traced|generated|green --ledger PATH --repo ROOT
                [--env PATH] [--tests-dir PATH] [--report PATH] [--defects PATH]
                exit 0 when the phase gate passes, 2 with the gap list otherwise
    verify-refs --ledger PATH --repo ROOT
                exit 2 when any exit ``via`` does not point at a matching marker

Status flags: traced (trace merged, no unresolved), stubbed (features, stubs
and seeds generated), tested (included in a run), passing (green in the last
run).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

from kb_common import (
    EXIT_OK,
    LEDGER_VERSION,
    KbError,
    read_json,
    read_yaml,
    require_file,
    run_cli,
    write_yaml,
)

# Task 8 adds EXIT_VALIDATION and read_text to the kb_common import and
# ``from markers import tokens_for``.

STATUS_FLAGS = ("traced", "stubbed", "tested", "passing")
EXIT_KINDS = ("db-write", "amq-publish", "http-out")
READ_KINDS = ("db-read", "http-in")
MERGE_FIELDS = ("request", "responses", "reads", "exits", "exits_none_reason", "auth", "type")
VIA_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)$")

_REQUIRED_EXIT_FIELDS = {
    "db-write": ("table", "op"),
    "amq-publish": ("destination",),
    "http-out": ("host_key", "method", "path"),
}


def load_ledger(path: Path) -> dict[str, Any]:
    ledger: dict[str, Any] = read_yaml(require_file(path, "flow-map.yaml"))
    if ledger.get("version") != LEDGER_VERSION:
        raise KbError(f"{path}: unsupported ledger version {ledger.get('version')!r}")
    ledger.setdefault("entry_points", [])
    ledger.setdefault("unresolved", [])
    return ledger


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_yaml(path, ledger)


def find_entry(ledger: dict[str, Any], entry_id: str) -> dict[str, Any]:
    for entry in ledger["entry_points"]:
        if entry.get("id") == entry_id:
            return cast(dict[str, Any], entry)
    raise KbError(f"unknown entry {entry_id!r}")


def _pending(entry: dict[str, Any], phase: str) -> bool:
    status = entry.get("status", {})
    if phase == "traced":
        return not status.get("traced", False)
    if phase == "generated":
        return bool(status.get("traced")) and not status.get("stubbed", False)
    raise KbError(f"unknown phase {phase!r}; expected traced or generated")


def next_entry(ledger: dict[str, Any], phase: str) -> dict[str, Any] | None:
    for entry in ledger["entry_points"]:
        if _pending(entry, phase):
            return {
                "id": entry["id"],
                "kind": entry.get("kind"),
                "handler": entry.get("handler"),
                "cheat_sheet": ledger.get("stack", {}).get("cheat_sheet"),
            }
    return None


def _check_via(owner: str, item: dict[str, Any]) -> None:
    via = item.get("via")
    if not isinstance(via, str) or not VIA_RE.match(via):
        raise KbError(f"{owner}: every exit needs 'via' as file:line, got {via!r}")


def _validate_exits(entry_id: str, exits: list[dict[str, Any]]) -> None:
    for item in exits:
        kind = item.get("kind")
        if kind not in EXIT_KINDS:
            raise KbError(f"{entry_id}: exit kind {kind!r} not one of {EXIT_KINDS}")
        missing = [f for f in _REQUIRED_EXIT_FIELDS[kind] if f not in item]
        if missing:
            raise KbError(f"{entry_id}: {kind} exit missing {missing}")
        _check_via(entry_id, item)
        if kind == "amq-publish":
            item.setdefault("type", "queue")


def merge_entry(ledger: dict[str, Any], traced: dict[str, Any]) -> int:
    entry_id = str(traced.get("id", ""))
    entry = find_entry(ledger, entry_id)
    exits = list(traced.get("exits", []))
    _validate_exits(entry_id, exits)
    for field in MERGE_FIELDS:
        if field in traced:
            entry[field] = traced[field]
    entry["exits"] = exits
    incoming_sources = traced.get("rules", {}).get("sources", [])
    rules = entry.setdefault("rules", {"file": None, "count": 0, "sources": []})
    known = {s["file"] for s in rules["sources"]}
    for source in incoming_sources:
        if source["file"] not in known:
            scanned = bool(source.get("scanned"))
            rules["sources"].append({"file": source["file"], "scanned": scanned})
            known.add(source["file"])
    unresolved = [
        {"entry": entry_id, "at": u["at"], "reason": u.get("reason", "")}
        for u in traced.get("unresolved", [])
    ]
    ledger["unresolved"] = [u for u in ledger["unresolved"] if u.get("entry") != entry_id]
    ledger["unresolved"].extend(unresolved)
    complete = bool(exits) or bool(entry.get("exits_none_reason"))
    entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
    entry["status"]["traced"] = not unresolved and complete
    return len(unresolved)


def mark_entry(ledger: dict[str, Any], entry_id: str, flag: str, value: bool = True) -> None:
    if flag not in STATUS_FLAGS:
        raise KbError(f"unknown status flag {flag!r}; expected one of {STATUS_FLAGS}")
    entry = find_entry(ledger, entry_id)
    entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
    entry["status"][flag] = value


def _cmd_next(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    pending = next_entry(ledger, args.phase)
    print(json.dumps(pending if pending is not None else {"done": True}))
    return EXIT_OK


def _cmd_merge(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    traced = read_json(require_file(args.entry_json, "trace result"))
    count = merge_entry(ledger, traced)
    save_ledger(args.ledger, ledger)
    print(f"merged {traced['id']}; unresolved: {count}")
    return EXIT_OK


def _cmd_mark(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    if args.generated:
        mark_entry(ledger, args.entry, "stubbed")
    if args.tested:
        mark_entry(ledger, args.entry, "tested")
    if args.passing:
        mark_entry(ledger, args.entry, "passing")
    if args.failing:
        mark_entry(ledger, args.entry, "passing", False)
    save_ledger(args.ledger, ledger)
    print(f"marked {args.entry}: {find_entry(ledger, args.entry)['status']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate on the karate-bootstrap flow-map ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="Print the next pending entry for a phase")
    nxt.add_argument("--phase", choices=("traced", "generated"), required=True)
    nxt.add_argument("--ledger", type=Path, required=True)
    nxt.set_defaults(func=_cmd_next)

    merge = sub.add_parser("merge", help="Merge a trace subagent result into the ledger")
    merge.add_argument("entry_json", type=Path)
    merge.add_argument("--ledger", type=Path, required=True)
    merge.set_defaults(func=_cmd_merge)

    mark = sub.add_parser("mark", help="Flip status flags on one entry")
    mark.add_argument("--entry", required=True)
    mark.add_argument("--ledger", type=Path, required=True)
    mark.add_argument("--generated", action="store_true")
    mark.add_argument("--tested", action="store_true")
    mark.add_argument("--passing", action="store_true")
    mark.add_argument("--failing", action="store_true")
    mark.set_defaults(func=_cmd_mark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
