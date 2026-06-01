from __future__ import annotations

from pathlib import Path

from skill_check import (
    check_command,
    check_skill,
    extract_commands,
)

SKILL = Path(__file__).parent.parent / "SKILL.md"
SCRIPTS = Path(__file__).parent.parent / "scripts"


def _fake_script(tmp_path: Path, name: str, body: str) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    path = scripts / name
    path.write_text(body, encoding="utf-8")
    return scripts


_SIMPLE = """\
import argparse
p = argparse.ArgumentParser()
p.add_argument("path")
p.add_argument("--out")
p.parse_args()
"""

_SUBCMD = """\
import argparse
p = argparse.ArgumentParser()
sub = p.add_subparsers(dest="cmd", required=True)
r = sub.add_parser("render")
r.add_argument("--top5")
p.parse_args()
"""


def test_extract_commands_finds_all():
    text = (
        "intro\n"
        "```bash\n"
        "python scripts/inventory.py <path> --out x.json\n"
        "python scripts/promote.py design.md --force\n"
        "```\n"
        "not a command: pytest -v\n"
    )
    cmds = extract_commands(text)
    assert len(cmds) == 2
    assert any("inventory.py" in c for c in cmds)
    assert any("promote.py" in c for c in cmds)


def test_check_passes_for_valid_command(tmp_path: Path):
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/thing.py somepath --out o.json")
    assert errors == []


def test_check_flags_unknown_flag(tmp_path: Path):
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/thing.py somepath --bogus v")
    assert len(errors) == 1
    assert "--bogus" in errors[0]


def test_check_missing_script(tmp_path: Path):
    scripts = _fake_script(tmp_path, "thing.py", _SIMPLE)
    errors = check_command(scripts, "python scripts/ghost.py --out o")
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_subcommand_flags_checked(tmp_path: Path):
    scripts = _fake_script(tmp_path, "multi.py", _SUBCMD)
    assert check_command(scripts, "python scripts/multi.py render --top5 t.json") == []
    bad = check_command(scripts, "python scripts/multi.py render --nope x")
    assert len(bad) == 1
    assert "--nope" in bad[0]


def test_real_skill_md_passes():
    errors = check_skill(SKILL, SCRIPTS)
    assert errors == [], "\n".join(errors)
