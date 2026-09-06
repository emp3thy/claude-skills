"""Render subagent prompts for karate-bootstrap (design spec 5.3, 5.4, 5.6, 9).

Each prompt is a ``string.Template`` file under ``prompts/`` filled with one ledger entry,
the stack cheat sheet path, the env-map role table and the file paths the subagent must
use. The main agent never composes a prompt freehand: it renders one with this script and
passes the file path to the Agent tool.

Usage:
    python scripts/kb_prompt.py render --prompt trace|rules|generate \
        --ledger karate-tests/flow-map.yaml --entry <id> --repo <root> \
        --out karate-tests/.prompts/<name>.md [--env karate-tests/env-map.json] \
        [--tests-dir karate-tests] [--source <file>] [--focus <file:line>] [--prompts-dir DIR]

``--env`` is required for trace and generate (host keys and downstream names); ``--source``
is required for rules (the validation file the subagent reads). ``--focus`` re-renders a
trace prompt that starts at an unresolved hop.

Exit codes: 0 ok, 2 bad arguments or an unknown entry, 5 when a prompt file or input is missing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from string import Template
from typing import Any

from flow_map import find_entry, load_ledger
from kb_common import EXIT_MISSING_OUTPUT, EXIT_OK, KbError, read_json, read_text, run_cli
from kb_rules import slug_for

PROMPTS = ("trace", "rules", "generate")
SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = SKILL_DIR / "prompts"
CSV_HEADER_LINE = ("rule_id,field,mutation,value,expected_status,expected_code,"
                   "expected_message_contains,source")


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def roles_table(env_map: dict[str, Any] | None) -> str:
    if env_map is None:
        return "(no env-map given)"
    lines = ["| key | role | env var |", "|---|---|---|"]
    for key in env_map.get("keys", []):
        lines.append(f"| {key.get('key')} | {key.get('role')} | {key.get('env_var') or ''} |")
    return "\n".join(lines)


def downstream_names(env_map: dict[str, Any] | None) -> str:
    names: list[str] = []
    for key in (env_map or {}).get("keys", []):
        role = str(key.get("role", ""))
        if role.startswith("downstream:"):
            name = role.split(":", 1)[1]
            if name not in names:
                names.append(name)
    return ", ".join(names) if names else "none"


def auth_instruction(mode: str) -> str:
    if mode == "jwks":
        return ("Auth mode is jwks: the harness serves a JWKS the app trusts. Add "
                "`* header Authorization = 'Bearer ' + Jwt.token({ sub: 'test-user' })` to the "
                "Background and extend the claims map with whatever roles the handler checks.")
    if mode == "disabled":
        return ("Auth mode is disabled: the harness turns the app's auth switch off, so do not "
                "send an Authorization header and do not write 401 or 403 scenarios.")
    if mode == "blocked":
        return ("Auth mode is blocked: no token can satisfy the app. Test only the entry points "
                "the trace marked as not requiring auth; do not send an Authorization header.")
    return "Auth mode is none: the app has no auth; do not send an Authorization header."


def entry_instruction(entry: dict[str, Any]) -> str:
    if entry.get("kind") == "amq-subscribe":
        destination = entry.get("destination")
        return (f"This entry is an AMQ subscription on `{destination}`. Drive it with "
                f"`Jms.publish('{destination}', body, {{}})` and assert the exits with "
                f"`Db.awaitRow` and `Jms.await` on the destinations the trace lists. Never "
                f"`Jms.watch('{destination}')`: the harness would compete with the app for the "
                f"message on an anycast queue.")
    return (f"This entry is HTTP {entry.get('method')} {entry.get('path')}. Every scenario "
            f"starts with `Given url appBaseUrl` and `And path '{entry.get('path')}'`, sends "
            f"the request, then asserts status, body and the exits.")


def candidates_note(path: Path) -> str:
    if not path.is_file():
        return ("not present (no declarative validators were found for this entry); every row "
                "comes from your reading of the source")
    rows = [line for line in read_text(path).splitlines() if line.strip()]
    return (f"present with {max(0, len(rows) - 1)} candidate rows drawn from every declarative "
            "source of this entry; confirm or drop the ones whose source is the file you are "
            "reading and leave the rest to their own pass")


def build_context(prompt: str, ledger: dict[str, Any], entry_id: str,
                  env_map: dict[str, Any] | None, repo: Path, tests_dir: Path,
                  source: str | None, focus: str | None) -> dict[str, str]:
    if prompt not in PROMPTS:
        raise KbError(f"unknown prompt {prompt!r}; expected one of {PROMPTS}")
    if prompt in ("trace", "generate") and env_map is None:
        raise KbError(f"prompt {prompt} needs --env (host keys and downstream names)")
    if prompt == "rules" and not source:
        raise KbError("prompt rules needs --source (the validation file to read)")
    entry = find_entry(ledger, entry_id)
    stack = str(ledger.get("stack", {}).get("framework", "unknown"))
    cheat_sheet = SKILL_DIR / str(ledger.get("stack", {}).get("cheat_sheet")
                                  or f"reference/stack-{stack}.md")
    slug = slug_for(entry_id)
    handler = str(entry.get("handler") or "")
    handler_file = handler.rsplit(":", 1)[0] if handler else ""
    rules = entry.get("rules") or {}
    auth_mode = str((ledger.get("app", {}).get("auth") or {}).get("mode", "none"))
    focus_text = ""
    if focus:
        focus_text = (f"\nStart at `{focus}`: a previous trace could not follow the code there. "
                      f"Trace only from that location onward and report the rest of the path; "
                      f"keep every exit you find with its own file:line.\n")
    context = {
        "prompt_kind": prompt,
        "entry_id": entry_id,
        "slug": slug,
        "kind": str(entry.get("kind", "")),
        "handler": handler,
        "handler_path": _posix(repo / handler_file) if handler_file else "",
        "stack": stack,
        "cheat_sheet": _posix(cheat_sheet),
        "repo": _posix(repo),
        "tests_dir": _posix(tests_dir),
        "entry_json": json.dumps(entry, indent=2),
        "exits_json": json.dumps(entry.get("exits", []), indent=2),
        "reads_json": json.dumps(entry.get("reads", []), indent=2),
        "responses_json": json.dumps(entry.get("responses", []), indent=2),
        "roles": roles_table(env_map),
        "downstreams": downstream_names(env_map),
        "auth_mode": auth_mode,
        "auth_instruction": auth_instruction(auth_mode),
        "entry_instruction": entry_instruction(entry),
        "focus": focus_text,
        "source": source or "",
        "source_path": _posix(repo / source) if source else "",
        "candidates_csv": _posix(tests_dir / "rules" / f"{slug}.candidates.csv"),
        "candidates_note": candidates_note(tests_dir / "rules" / f"{slug}.candidates.csv"),
        "csv_header": CSV_HEADER_LINE,
        "rules_file": str(rules.get("file") or "none"),
        "rules_count": str(rules.get("count") or 0),
        "feature_file": f"features/{slug}.feature",
        "seed_file": f"seed/{slug}.sql",
        "example_file": f"seed/examples/{slug}.json",
        "stubs_dir": "stubs",
    }
    return context


def render(prompt: str, context: dict[str, str], prompts_dir: Path) -> str:
    path = prompts_dir / f"{prompt}.md"
    if not path.is_file():
        raise KbError(f"prompt file missing: {path}", EXIT_MISSING_OUTPUT)
    try:
        return Template(read_text(path)).substitute(context)
    except KeyError as err:
        raise KbError(f"{path}: placeholder {err.args[0]!r} has no value") from err
    except ValueError as err:
        raise KbError(f"{path}: bad placeholder syntax ({err}); write a literal $ as $$") from err


def _cmd_render(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    env_map = read_json(args.env) if args.env else None
    tests_dir: Path = args.tests_dir if args.tests_dir else args.repo / "karate-tests"
    context = build_context(args.prompt, ledger, args.entry, env_map, args.repo, tests_dir,
                            args.source, args.focus)
    text = render(args.prompt, context, args.prompts_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"rendered {args.prompt} prompt for {args.entry} -> {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a subagent prompt from prompts/<name>.md")
    sub = parser.add_subparsers(dest="command", required=True)
    rend = sub.add_parser("render", help="Fill a prompt template with one ledger entry")
    rend.add_argument("--prompt", choices=PROMPTS, required=True)
    rend.add_argument("--ledger", type=Path, required=True, help="flow-map.yaml")
    rend.add_argument("--entry", required=True, help="entry id from the ledger")
    rend.add_argument("--repo", type=Path, required=True, help="service root")
    rend.add_argument("--out", type=Path, required=True, help="prompt file to write")
    rend.add_argument("--env", type=Path, default=None, help="env-map.json (trace, generate)")
    rend.add_argument("--tests-dir", type=Path, default=None,
                      help="karate-tests directory (default <repo>/karate-tests)")
    rend.add_argument("--source", default=None, help="validation source file (rules)")
    rend.add_argument("--focus", default=None, help="file:line to start a narrower trace at")
    rend.add_argument("--prompts-dir", type=Path, default=PROMPTS_DIR,
                      help="directory holding trace.md, rules.md, generate.md")
    rend.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
