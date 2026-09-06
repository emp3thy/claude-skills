"""The flow-map ledger: karate-bootstrap's only memory across phases.

Subcommands:
    next        --phase traced|generated --ledger PATH
                prints JSON {id, kind, handler, cheat_sheet} for the next pending entry,
                or {"done": true}
    merge       ENTRY_JSON --ledger PATH
                merges one trace subagent result into its entry
    mark        --entry ID (--generated|--tested|--passing|--failing)
                [--feature F]... [--stub S]... [--seed X]... --ledger PATH
                flips status flags and records generated files on the entry
    add-entry   --ledger PATH --id ID --kind http|amq-subscribe --handler file:line
                [--method M --path P] [--destination D --type queue|topic]
                seeds an entry the discover regexes missed (spec 5.2)
    record-run  --ledger PATH --report PATH
                sets tested and passing on every entry with features from report.json
    override    --ledger PATH --entry ID --scenario S --field F --old O --new N --reason R
                appends an observed-behaviour override (spec 5.7, classification 3)
    set-auth    --ledger PATH --mode disabled|jwks|none|blocked [--key K --value V]
                [--issuer-keys A,B]
                records the confirmed auth mode on app.auth (spec 5.2)
    validate    --phase traced|generated|green --ledger PATH --repo ROOT
                [--service-dir SUB] [--env PATH] [--tests-dir PATH] [--report PATH]
                [--defects PATH]
                exit 0 when the phase gate passes, 2 with the gap list otherwise
    verify-refs --ledger PATH --repo ROOT [--service-dir SUB]
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
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from kb_common import (
    EXIT_OK,
    EXIT_VALIDATION,
    LEDGER_VERSION,
    KbError,
    read_json,
    read_text,
    read_yaml,
    require_file,
    run_cli,
    write_yaml,
)
from kb_features import PARALLEL_FALSE_TAG, unsafe_parallel_scenarios
from markers import tokens_for

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

AUTH_MODES = ("disabled", "jwks", "none", "blocked")
ENTRY_KINDS = ("http", "amq-subscribe")


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


def new_entry(base: dict[str, Any]) -> dict[str, Any]:
    """An untraced entry: ``base`` (id, kind, handler and the kind's own fields) plus the
    bookkeeping fields every phase expects. discover.seed_ledger and add_entry both use it."""
    item: dict[str, Any] = dict(base)
    item.update({
        "auth": "unknown",
        "request": None,
        "responses": [],
        "reads": [],
        "exits": [],
        "rules": {"file": None, "count": 0, "sources": []},
        "features": [],
        "stubs": [],
        "seeds": [],
        "observed_overrides": [],
        "status": dict.fromkeys(STATUS_FLAGS, False),
    })
    return item


def add_entry(ledger: dict[str, Any], entry_id: str, kind: str, handler: str,
              method: str | None = None, path: str | None = None,
              destination: str | None = None, dest_type: str = "queue") -> dict[str, Any]:
    """Seed an entry point the discover regexes missed (spec 5.2)."""
    if kind not in ENTRY_KINDS:
        raise KbError(f"{entry_id}: unknown entry kind {kind!r}; expected one of {ENTRY_KINDS}")
    if any(e.get("id") == entry_id for e in ledger["entry_points"]):
        raise KbError(f"{entry_id}: already in the ledger")
    clean_handler = handler.replace("\\", "/")
    if not VIA_RE.match(clean_handler):
        raise KbError(f"{entry_id}: handler must be file:line, got {handler!r}")
    base: dict[str, Any] = {"id": entry_id, "kind": kind}
    if kind == "http":
        if not method or not path:
            raise KbError(f"{entry_id}: http entries need --method and --path")
        base.update({"method": method.upper(), "path": path})
    else:
        if not destination:
            raise KbError(f"{entry_id}: amq-subscribe entries need --destination")
        base.update({"destination": destination, "type": dest_type})
    base["handler"] = clean_handler
    entry = new_entry(base)
    ledger["entry_points"].append(entry)
    return entry


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


def _validate_reads(entry_id: str, reads: list[dict[str, Any]]) -> None:
    for item in reads:
        kind = item.get("kind")
        if kind not in READ_KINDS:
            raise KbError(f"{entry_id}: read kind {kind!r} not one of {READ_KINDS}")


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
    for item in exits:
        via = item.get("via")
        if isinstance(via, str):
            item["via"] = via.replace("\\", "/")  # a Windows trace still points at a posix path
    _validate_exits(entry_id, exits)
    _validate_reads(entry_id, list(traced.get("reads", [])))
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


RESOURCES_PREFIX = "src/test/resources/"


def record_files(ledger: dict[str, Any], entry_id: str, features: Iterable[str] = (),
                 stubs: Iterable[str] = (), seeds: Iterable[str] = ()) -> dict[str, Any]:
    """Append generated file paths (posix, de-duplicated) to the entry's lists.

    Features are stored relative to ``src/test/resources`` (the classpath root the gate and
    the report parser use); a path given from the tests root is trimmed to that form. Stubs
    and seeds stay relative to the tests root.
    """
    entry = find_entry(ledger, entry_id)
    for key, items in (("features", features), ("stubs", stubs), ("seeds", seeds)):
        existing: list[str] = entry.setdefault(key, [])
        for item in items:
            clean = str(item).replace("\\", "/")
            if key == "features" and clean.startswith(RESOURCES_PREFIX):
                clean = clean[len(RESOURCES_PREFIX):]
            if clean not in existing:
                existing.append(clean)
    return entry


def record_run(ledger: dict[str, Any], report: dict[str, Any]) -> dict[str, int]:
    """After a full run: every entry with features is tested; passing unless one of its
    features appears in the report's failed list (spec 5.7)."""
    failed_features = {str(item.get("feature", "")) for item in report.get("failed", [])}
    counts = {"tested": 0, "passing": 0, "failing": 0}
    for entry in ledger["entry_points"]:
        features = [str(f) for f in entry.get("features", [])]
        if not features:
            continue
        status = entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
        status["tested"] = True
        status["passing"] = not (set(features) & failed_features)
        counts["tested"] += 1
        counts["passing" if status["passing"] else "failing"] += 1
    return counts


def add_override(ledger: dict[str, Any], entry_id: str, scenario: str, field: str,
                 old: str, new: str, reason: str) -> dict[str, Any]:
    """Record that a generated expectation was replaced by observed behaviour."""
    entry = find_entry(ledger, entry_id)
    item = {"scenario": scenario, "field": field, "old": old, "new": new, "reason": reason}
    entry.setdefault("observed_overrides", []).append(item)
    return item


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
    record_files(ledger, args.entry, args.feature or [], args.stub or [], args.seed or [])
    save_ledger(args.ledger, ledger)
    print(f"marked {args.entry}: {find_entry(ledger, args.entry)['status']}")
    return EXIT_OK


def set_auth(ledger: dict[str, Any], mode: str, key: str | None = None,
             value: str | None = None, issuer_keys: list[str] | None = None) -> dict[str, Any]:
    """Record the confirmed auth mode on ``app.auth`` (spec 5.2)."""
    if mode not in AUTH_MODES:
        raise KbError(f"unknown auth mode {mode!r}; expected one of {AUTH_MODES}")
    auth: dict[str, Any]
    if mode == "disabled":
        if not key or value is None:
            raise KbError("auth mode disabled needs --key and --value")
        auth = {"mode": "disabled", "key": key, "value": value, "confirmed": True}
    elif mode == "jwks":
        if not issuer_keys:
            raise KbError("auth mode jwks needs --issuer-keys")
        auth = {"mode": "jwks", "keys": sorted(set(issuer_keys))}
    else:
        auth = {"mode": mode}
    ledger.setdefault("app", {})["auth"] = auth
    return auth


def _cmd_set_auth(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    keys = None
    if args.issuer_keys:
        keys = [k.strip() for k in args.issuer_keys.split(",") if k.strip()]
    auth = set_auth(ledger, args.mode, args.key, args.value, keys)
    save_ledger(args.ledger, ledger)
    print(f"app.auth: {json.dumps(auth)}")
    return EXIT_OK


def _cmd_add_entry(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    entry = add_entry(ledger, args.id, args.kind, args.handler, args.method, args.path,
                      args.destination, args.type)
    save_ledger(args.ledger, ledger)
    print(f"added {entry['id']} ({entry['kind']}) at {entry['handler']}")
    return EXIT_OK


def _cmd_record_run(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    report = read_json(require_file(args.report, "report.json"))
    counts = record_run(ledger, report)
    save_ledger(args.ledger, ledger)
    print(f"recorded run: tested: {counts['tested']}  passing: {counts['passing']}  "
          f"failing: {counts['failing']}")
    return EXIT_OK


def _cmd_override(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    item = add_override(ledger, args.entry, args.scenario, args.field, args.old, args.new,
                        args.reason)
    save_ledger(args.ledger, ledger)
    print(f"override on {args.entry}: {json.dumps(item)}")
    return EXIT_OK


# --- verify-refs -----------------------------------------------------------------------


def _split_via(via: str) -> tuple[str, int]:
    match = VIA_RE.match(via)
    if not match:
        raise KbError(f"malformed via {via!r}")
    return match.group("file"), int(match.group("line"))


def verify_refs(ledger: dict[str, Any], repo_root: Path, window: int = 3) -> list[str]:
    stack = str(ledger.get("stack", {}).get("framework"))
    gaps: list[str] = []
    for entry in ledger["entry_points"]:
        bad = False
        for item in entry.get("exits", []):
            kind = str(item.get("kind"))
            file_rel, line_no = _split_via(str(item.get("via")))
            path = repo_root / file_rel
            if not path.is_file():
                gaps.append(f"{entry['id']}: {kind} via {file_rel}:{line_no} does not exist")
                bad = True
                continue
            lines = read_text(path).splitlines()
            if not 1 <= line_no <= len(lines):
                gaps.append(f"{entry['id']}: {kind} via {file_rel}:{line_no} is past end of file")
                bad = True
                continue
            lo, hi = max(0, line_no - 1 - window), min(len(lines), line_no + window)
            snippet = "\n".join(lines[lo:hi])
            if not any(token in snippet for token in tokens_for(stack, kind)):
                gaps.append(
                    f"{entry['id']}: {kind} via {file_rel}:{line_no} has no {kind} marker "
                    f"within {window} lines"
                )
                bad = True
        if bad:
            entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))["traced"] = False
    return gaps


# --- validate ----------------------------------------------------------------------------


def _validate_traced(ledger: dict[str, Any], env_map: dict[str, Any] | None) -> list[str]:
    gaps: list[str] = []
    known_keys = {k["key"] for k in (env_map or {}).get("keys", [])} | {
        str(k.get("env_var")) for k in (env_map or {}).get("keys", []) if k.get("env_var")
    }
    for entry in ledger["entry_points"]:
        if not entry.get("status", {}).get("traced"):
            gaps.append(f"{entry['id']}: not traced")
        elif not entry.get("exits") and not entry.get("exits_none_reason"):
            gaps.append(f"{entry['id']}: no exits and no exits_none_reason")
        if env_map is not None:
            for item in list(entry.get("exits", [])) + list(entry.get("reads", [])):
                host_key = item.get("host_key")
                if host_key and host_key not in known_keys:
                    gaps.append(f"{entry['id']}: host_key {host_key!r} not in env-map")
    for item in ledger.get("unresolved", []):
        gaps.append(
            f"{item.get('entry')}: unresolved hop at {item.get('at')}: {item.get('reason')}"
        )
    auth = ledger.get("app", {}).get("auth") or {}
    if auth.get("mode") == "disabled" and auth.get("confirmed") is False:
        gaps.append(
            f"app.auth: switch {auth.get('key')} is unconfirmed; "
            "confirm or set the real value"
        )
    return gaps


def _csv_rows(path: Path) -> int:
    lines = [line for line in read_text(path).splitlines() if line.strip()]
    return max(0, len(lines) - 1)


def _validate_generated(ledger: dict[str, Any], tests_dir: Path | None) -> list[str]:
    if tests_dir is None:
        raise KbError("--tests-dir is required for the generated phase")
    resources = tests_dir / "src" / "test" / "resources"
    gaps: list[str] = []
    for entry in ledger["entry_points"]:
        eid = entry["id"]
        if not entry.get("status", {}).get("stubbed"):
            gaps.append(f"{eid}: not generated")
        features = entry.get("features", [])
        if not features:
            gaps.append(f"{eid}: no feature file")
            continue
        texts: list[str] = []
        for feature in features:
            path = resources / feature
            if not path.is_file():
                gaps.append(f"{eid}: feature {feature} does not exist")
                continue
            feature_text = read_text(path)
            texts.append(feature_text)
            for name in unsafe_parallel_scenarios(feature_text):
                gaps.append(
                    f"{eid}: {feature} scenario {name!r} uses exclusive state "
                    f"without {PARALLEL_FALSE_TAG}"
                )
        text = "\n".join(texts)
        for item in entry.get("exits", []):
            kind = item["kind"]
            if kind == "db-write" and not ("Db." in text and str(item["table"]) in text):
                gaps.append(f"{eid}: db-write on {item['table']} has no Db. assertion")
            if kind == "amq-publish" and not ("Jms." in text and str(item["destination"]) in text):
                gaps.append(f"{eid}: amq-publish to {item['destination']} has no Jms. assertion")
            if kind == "http-out":
                if "Stubs.verify" not in text:
                    gaps.append(
                        f"{eid}: http-out {item['method']} {item['path']} has no Stubs.verify"
                    )
                if not entry.get("stubs"):
                    gaps.append(f"{eid}: http-out exit but no stub files")
        for stub in entry.get("stubs", []):
            if not (tests_dir / stub).is_file():
                gaps.append(f"{eid}: stub {stub} does not exist")
        needs_rules = any(r.get("rules") for r in entry.get("responses", []))
        rules = entry.get("rules", {})
        if needs_rules:
            if not rules.get("file"):
                gaps.append(f"{eid}: validation responses but no rules file")
            else:
                rules_path = tests_dir / str(rules["file"])
                if not rules_path.is_file():
                    gaps.append(f"{eid}: rules file {rules['file']} does not exist")
                else:
                    rows = _csv_rows(rules_path)
                    if rows != int(rules.get("count", 0)):
                        gaps.append(
                            f"{eid}: rules count {rules.get('count')} differs from {rows} CSV rows"
                        )
            for source in rules.get("sources", []):
                if not source.get("scanned"):
                    gaps.append(f"{eid}: rules source {source['file']} not scanned")
    return gaps


_DEFECT_ENTRY_RE = re.compile(r"^entry_point:\s*(.+?)\s*$", re.MULTILINE)


def _validate_green(ledger: dict[str, Any], report: dict[str, Any] | None,
                    defects_text: str | None) -> list[str]:
    if report is None:
        raise KbError("--report is required for the green phase")
    gaps: list[str] = []
    quarantined_entries = set(_DEFECT_ENTRY_RE.findall(defects_text or ""))
    for failed in report.get("failed", []):
        feature = str(failed.get("feature", ""))
        label = f"{feature}: {failed.get('scenario')!r}"
        if "@known-defect" not in failed.get("tags", []):
            gaps.append(f"{label} failed and is not quarantined with @known-defect")
            continue
        owners = {
            str(entry["id"])
            for entry in ledger["entry_points"]
            if feature in entry.get("features", [])
        }
        if not owners:
            gaps.append(f"{label} is quarantined but no ledger entry owns {feature}")
        elif not owners & quarantined_entries:
            gaps.append(
                f"{label} is quarantined but defects.md has no entry for "
                f"{', '.join(sorted(owners))}"
            )
    for entry in ledger["entry_points"]:
        status = entry.get("status", {})
        if not status.get("passing") and entry["id"] not in quarantined_entries:
            gaps.append(f"{entry['id']}: not passing and not listed in defects.md")
    return gaps


def validate(ledger: dict[str, Any], phase: str, repo_root: Path,
             env_map: dict[str, Any] | None, tests_dir: Path | None,
             report: dict[str, Any] | None, defects_text: str | None) -> list[str]:
    if phase == "traced":
        return _validate_traced(ledger, env_map) + verify_refs(ledger, repo_root)
    if phase == "generated":
        return _validate_generated(ledger, tests_dir)
    if phase == "green":
        return _validate_green(ledger, report, defects_text)
    raise KbError(f"unknown phase {phase!r}")


def _repo_root(args: argparse.Namespace) -> Path:
    root: Path = args.repo / args.service_dir if args.service_dir else args.repo
    return root


def _cmd_validate(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    env_map = read_json(args.env) if args.env else None
    report = read_json(args.report) if args.report else None
    defects_text = read_text(args.defects) if args.defects and args.defects.is_file() else None
    gaps = validate(ledger, args.phase, _repo_root(args), env_map, args.tests_dir, report,
                    defects_text)
    save_ledger(args.ledger, ledger)  # verify-refs may have reset traced flags
    if gaps:
        print("\n".join(gaps))
        print(f"{len(gaps)} gap(s) in phase {args.phase}")
        return EXIT_VALIDATION
    print(f"phase {args.phase}: pass")
    return EXIT_OK


def _cmd_verify_refs(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    gaps = verify_refs(ledger, _repo_root(args))
    save_ledger(args.ledger, ledger)
    if gaps:
        print("\n".join(gaps))
        return EXIT_VALIDATION
    print("verify-refs: pass")
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
    mark.add_argument("--feature", action="append", help="feature path to record (repeatable)")
    mark.add_argument("--stub", action="append", help="stub path to record (repeatable)")
    mark.add_argument("--seed", action="append", help="seed path to record (repeatable)")
    mark.set_defaults(func=_cmd_mark)

    auth = sub.add_parser("set-auth", help="Record the confirmed auth mode on app.auth")
    auth.add_argument("--ledger", type=Path, required=True)
    auth.add_argument("--mode", choices=AUTH_MODES, required=True)
    auth.add_argument("--key", default=None, help="switch env var (mode disabled)")
    auth.add_argument("--value", default=None, help="switch value that turns auth off")
    auth.add_argument("--issuer-keys", default=None,
                      help="comma-separated issuer or JWKS env vars (mode jwks)")
    auth.set_defaults(func=_cmd_set_auth)

    add = sub.add_parser("add-entry", help="Seed an entry point the discover regexes missed")
    add.add_argument("--ledger", type=Path, required=True)
    add.add_argument("--id", required=True, help='entry id, e.g. "PUT /api/deals/{id}"')
    add.add_argument("--kind", choices=ENTRY_KINDS, required=True)
    add.add_argument("--handler", required=True, help="file:line of the handler")
    add.add_argument("--method", default=None, help="HTTP method (kind http)")
    add.add_argument("--path", default=None, help="route path (kind http)")
    add.add_argument("--destination", default=None, help="queue or topic name (kind amq-subscribe)")
    add.add_argument("--type", choices=("queue", "topic"), default="queue")
    add.set_defaults(func=_cmd_add_entry)

    run = sub.add_parser("record-run", help="Set tested and passing per entry from report.json")
    run.add_argument("--ledger", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.set_defaults(func=_cmd_record_run)

    over = sub.add_parser("override", help="Append an observed-behaviour override to an entry")
    over.add_argument("--ledger", type=Path, required=True)
    over.add_argument("--entry", required=True)
    over.add_argument("--scenario", required=True)
    over.add_argument("--field", required=True)
    over.add_argument("--old", required=True)
    over.add_argument("--new", required=True)
    over.add_argument("--reason", required=True)
    over.set_defaults(func=_cmd_override)

    val = sub.add_parser("validate", help="Run a phase gate")
    val.add_argument("--phase", choices=("traced", "generated", "green"), required=True)
    val.add_argument("--ledger", type=Path, required=True)
    val.add_argument("--repo", type=Path, required=True, help="service root")
    val.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    val.add_argument("--env", type=Path, default=None, help="env-map.json (traced phase)")
    val.add_argument("--tests-dir", type=Path, default=None, help="karate-tests dir (generated)")
    val.add_argument("--report", type=Path, default=None, help="parsed report JSON (green)")
    val.add_argument("--defects", type=Path, default=None, help="defects.md (green)")
    val.set_defaults(func=_cmd_validate)

    refs = sub.add_parser("verify-refs", help="Check every exit via points at a marker")
    refs.add_argument("--ledger", type=Path, required=True)
    refs.add_argument("--repo", type=Path, required=True)
    refs.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    refs.set_defaults(func=_cmd_verify_refs)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
