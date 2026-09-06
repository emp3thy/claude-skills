"""Lint SKILL.md commands against the scripts they invoke.

A CI guard against doc drift: every ``python scripts/<name>.py ...`` command in SKILL.md must
name a script that exists and must only use flags the script's ``--help`` accepts. Renaming a
flag in a script but not in SKILL.md (or the reverse) fails the build instead of shipping a
stale procedure to the model that follows it.

Algorithm: regex-extract every ``python scripts/<name>.py ...`` command, confirm the script
exists, run ``python scripts/<name>.py --help`` (plus ``<subcommand> --help`` when the command
targets an argparse subparser), and require every ``--flag`` token in the command to appear
in that help text. Positional arguments and values are ignored.

Usage: python scripts/kb_check_skill.py [--skill PATH] [--scripts DIR]

Exit 0 when every command lints clean, 2 (offending commands on stderr) otherwise.
Stand-alone by design: no sibling imports, so it also works from a checkout without pyyaml.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# A full ``python scripts/<name>.py ...`` invocation up to the line end or a closing backtick.
# Script names are real lowercase module names, so prose like ``scripts/<name>.py`` is skipped.
_COMMAND_RE = re.compile(r"python\s+scripts/[a-z_][a-z0-9_]*\.py[^\n`]*")

# Argparse renders subparser choices as ``{render,mark}`` in help text.
_CHOICES_RE = re.compile(r"\{([a-z0-9,_-]+)\}")


def extract_commands(text: str) -> list[str]:
    """Every ``python scripts/*.py ...`` command string found in ``text``."""
    return [match.group(0).rstrip() for match in _COMMAND_RE.finditer(text)]


def _parse_command(command: str) -> tuple[str, list[str], list[str]]:
    tokens = command.split()
    script_rel = tokens[1]
    rest = tokens[2:]
    flags = [t for t in rest if t.startswith("--")]
    positionals = [t for t in rest if not t.startswith("-")]
    return script_rel, positionals, flags


def _run_help(script_path: Path, subcommand: list[str]) -> str:
    proc = subprocess.run(
        [sys.executable, str(script_path), *subcommand, "--help"],
        capture_output=True,
        text=True,
    )
    return proc.stdout + proc.stderr


def _subcommand_choices(help_text: str) -> set[str]:
    match = _CHOICES_RE.search(help_text)
    return set(match.group(1).split(",")) if match else set()


def check_command(scripts_dir: Path, command: str) -> list[str]:
    """Lint errors for one command (empty when it lints clean)."""
    script_rel, positionals, flags = _parse_command(command)
    script_path = scripts_dir / Path(script_rel).name
    if not script_path.exists():
        return [f"{command!r}: script not found: {script_path}"]
    help_text = _run_help(script_path, [])
    choices = _subcommand_choices(help_text)
    subcommand = next((p for p in positionals if p in choices), None)
    if subcommand is not None:
        help_text = _run_help(script_path, [subcommand])
    where = f"{script_path.name} {subcommand}".strip()
    return [
        f"{command!r}: flag {flag} not accepted by `{where} --help`"
        for flag in flags
        if flag not in help_text
    ]


def check_skill(skill_path: Path, scripts_dir: Path) -> list[str]:
    """Lint every command in ``skill_path`` against ``scripts_dir``."""
    text = skill_path.read_text(encoding="utf-8")
    errors: list[str] = []
    for command in extract_commands(text):
        errors.extend(check_command(scripts_dir, command))
    return errors


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Lint SKILL.md commands against scripts")
    parser.add_argument("--skill", type=Path, default=here.parent / "SKILL.md",
                        help="path to SKILL.md")
    parser.add_argument("--scripts", type=Path, default=here,
                        help="path to the scripts/ directory")
    args = parser.parse_args(argv)
    errors = check_skill(args.skill, args.scripts)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2
    print(f"ok: all SKILL.md commands match their scripts ({args.skill})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
