from __future__ import annotations

from pathlib import Path

from kb_check_skill import check_command, check_skill, extract_commands, help_tokens

SKILL = Path(__file__).resolve().parent.parent / "SKILL.md"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

_SIMPLE = """\
import argparse
p = argparse.ArgumentParser()
p.add_argument("path")
p.add_argument("--out")
p.parse_args()
"""

_PREFIX_FLAGS = """\
import argparse
p = argparse.ArgumentParser()
p.add_argument("path")
p.add_argument("--out-env")
p.add_argument("--out-ledger")
p.parse_args()
"""

_SUBCMD = """\
import argparse
p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("render")
r.add_argument("--prompt")
r.add_argument("--out")
p.parse_args()
"""


def _fake_script(tmp_path: Path, name: str, body: str) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / name).write_text(body, encoding="utf-8")
    return scripts


def test_extract_commands_finds_python_script_invocations_only() -> None:
    text = (
        "intro\n```bash\npython scripts/detect.py <repo> --out karate-tests/stack.json\n"
        "python scripts/flow_map.py next --phase traced --ledger karate-tests/flow-map.yaml\n```\n"
        "inline `python scripts/kb_prompt.py render --prompt trace --out x.md` too\n"
        "not a command: mvn -B test\nnor: python scripts/<name>.py --x\n"
    )
    commands = extract_commands(text)
    assert len(commands) == 3
    assert commands[2] == "python scripts/kb_prompt.py render --prompt trace --out x.md"


def test_check_passes_for_a_valid_command(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    assert check_command(scripts, "python scripts/thing.py somepath --out o.json") == []


def test_check_flags_an_unknown_flag(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/thing.py somepath --nope x")
    assert len(errors) == 1 and "--nope" in errors[0]


def test_a_flag_must_match_a_whole_help_token_not_a_prefix(tmp_path: Path) -> None:
    # --out is a substring of --out-env; only whole-token matching catches the drift
    scripts = _fake_script(tmp_path, "thing.py", _PREFIX_FLAGS)
    errors = check_command(scripts, "python scripts/thing.py somepath --out o.json")
    assert len(errors) == 1 and "--out " in errors[0]
    assert check_command(scripts, "python scripts/thing.py somepath --out-env e.json") == []


def test_help_tokens_splits_on_argparse_punctuation() -> None:
    tokens = help_tokens("usage: p [--out-env OUT_ENV] [--flag=VALUE]\n  -o, --out OUT   text\n")
    assert {"--out-env", "OUT_ENV", "--flag", "VALUE", "-o", "--out", "OUT"} <= tokens
    assert "[--out-env" not in tokens


def test_check_reports_a_missing_script(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/missing.py --out o")
    assert len(errors) == 1 and "script not found" in errors[0]


def test_subcommand_flags_are_checked_against_the_subparser(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "sub.py", _SUBCMD)
    assert check_command(scripts, "python scripts/sub.py render --prompt trace --out o.md") == []
    errors = check_command(scripts, "python scripts/sub.py render --ledger l.yaml")
    assert len(errors) == 1 and "--ledger" in errors[0] and "sub.py render" in errors[0]


def test_check_skill_collects_every_error(tmp_path: Path) -> None:
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "```bash\npython scripts/thing.py a --out o\npython scripts/thing.py a --bad 1\n"
        "python scripts/gone.py\n```\n",
        encoding="utf-8",
    )
    errors = check_skill(skill, scripts)
    assert len(errors) == 2


def test_real_skill_md_lints_clean() -> None:
    assert SKILL.is_file()
    assert check_skill(SKILL, SCRIPTS) == []
