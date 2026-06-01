"""Lint SKILL.md commands against the scripts they invoke.

A CI guard against doc drift (per [[98056ebc-docs-in-sync]]): every
``python scripts/<name>.py ...`` command in SKILL.md must name a script that
exists and must only use flags the script's ``--help`` actually accepts. When a
flag is renamed or removed in a script but not in SKILL.md (or vice versa), this
fails the build instead of letting the stale doc ship.

Algorithm: regex-extract every ``python scripts/<name>.py ...`` line, then for
each command confirm the script exists, run ``python scripts/<name>.py --help``
(plus ``<subcommand> --help`` when the command targets an argparse subparser),
and assert every ``--flag`` token in the command appears in that help text.
Positional arguments and value tokens are ignored — only ``--flag`` names are
checked.

Exit 0 if every command lints clean, 2 (with the offending commands printed) if
any flag or script is unknown.

Direct-path invocable (no package imports): `python skill_check.py`.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Matches a full ``python scripts/<name>.py ...`` invocation up to the line end
# or a closing backtick (so inline-code commands are caught too). The script name
# is restricted to real lowercase module names so prose placeholders like
# ``scripts/<name>.py`` are not mistaken for runnable commands.
_COMMAND_RE = re.compile(r"python\s+scripts/[a-z_][a-z0-9_]*\.py[^\n`]*")

# Argparse renders subparser choices as ``{render,mark-promoted}`` in help text.
_CHOICES_RE = re.compile(r"\{([a-z0-9,_-]+)\}")


def extract_commands(text: str) -> list[str]:
    """Return every ``python scripts/*.py ...`` command string found in ``text``."""
    return [m.group(0).rstrip() for m in _COMMAND_RE.finditer(text)]


def _parse_command(command: str) -> tuple[str, list[str], list[str]]:
    """Split a command into (script-rel-path, positional tokens, --flags)."""
    tokens = command.split()
    script_rel = tokens[1]  # tokens[0] == "python"
    rest = tokens[2:]
    flags = [t for t in rest if t.startswith("--")]
    positionals = [t for t in rest if not t.startswith("-")]
    return script_rel, positionals, flags


def _run_help(script_path: Path, subcommand: list[str]) -> str:
    """Capture ``python <script> [subcommand] --help`` output (stdout + stderr)."""
    proc = subprocess.run(
        [sys.executable, str(script_path), *subcommand, "--help"],
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr


def _subcommand_choices(help_text: str) -> set[str]:
    """Extract the set of subparser names from a ``{a,b,c}`` group, if present."""
    match = _CHOICES_RE.search(help_text)
    if match is None:
        return set()
    return set(match.group(1).split(","))


def check_command(scripts_dir: Path, command: str) -> list[str]:
    """Return a list of lint errors for one command (empty when it lints clean)."""
    script_rel, positionals, flags = _parse_command(command)
    name = Path(script_rel).name
    script_path = scripts_dir / name
    if not script_path.exists():
        return [f"{command!r}: script not found: {script_path}"]

    help_text = _run_help(script_path, [])
    choices = _subcommand_choices(help_text)
    subcommand = next((p for p in positionals if p in choices), None)
    if subcommand is not None:
        help_text = _run_help(script_path, [subcommand])

    where = f"{name} {subcommand}".strip()
    errors: list[str] = []
    for flag in flags:
        if flag not in help_text:
            errors.append(f"{command!r}: flag {flag} not accepted by `{where} --help`")
    return errors


def check_skill(skill_path: Path, scripts_dir: Path) -> list[str]:
    """Lint every command in ``skill_path`` against ``scripts_dir``."""
    text = skill_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for command in extract_commands(text):
        errors.extend(check_command(scripts_dir, command))
    return errors


def _main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Lint SKILL.md commands against scripts")
    parser.add_argument(
        "--skill", type=Path, default=here.parent / "SKILL.md", help="path to SKILL.md"
    )
    parser.add_argument(
        "--scripts", type=Path, default=here, help="path to the scripts/ directory"
    )
    args = parser.parse_args(argv)

    errors = check_skill(args.skill, args.scripts)
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 2
    print(f"ok: all SKILL.md commands match their scripts ({args.skill})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
