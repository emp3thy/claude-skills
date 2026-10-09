"""Byte goldens for a full run (apply and commit) over each corpus fixture.

The run uses ``--date 2026-01-02 --branch docs/drift-golden``; the replay is deterministic
(fixed identities and dates, LF content), so every sha in the outputs is stable. Compared byte
for byte: ``tokens.json``, ``candidates.json``, ``findings.json`` (as rewritten by apply),
``hunks-provable.json``, the commit message (``git log -1 --format=%B``) as ``commit-msg.txt``
and every edited doc under ``docs/<doc path>``. ``UPDATE_GOLDENS=1`` rewrites the golden
directory instead of comparing; read every regenerated commit message and doc before
committing them.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import dd_run
import pytest
from dd_common import read_json
from dd_corpus import FIXTURES, prepare_fixture

GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"
JSON_OUTPUTS = ("tokens.json", "candidates.json", "findings.json", "hunks-provable.json")
BRANCH = "docs/drift-golden"


def _actual(repo: Path, workdir: Path) -> dict[str, bytes]:
    out = {name: (workdir / name).read_bytes() for name in JSON_OUTPUTS}
    out["commit-msg.txt"] = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"], capture_output=True, check=True
    ).stdout
    for doc in read_json(workdir / "applied.json")["docs"]:
        out[f"docs/{doc}"] = (repo / doc).read_bytes()
    return out


@pytest.mark.parametrize("fixture", FIXTURES)
def test_outputs_match_goldens(fixture: str, tmp_path: Path) -> None:
    repo = prepare_fixture(fixture, tmp_path / "repo")
    workdir = tmp_path / "wd"
    code = dd_run.main([str(repo), "--date", "2026-01-02", "--branch", BRANCH,
                        "--workdir", str(workdir)])
    assert code == 0
    assert read_json(workdir / "commits.json")["branch"] == BRANCH
    assert read_json(workdir / "applied.json")["reverted"] == []
    actual = _actual(repo, workdir)
    golden = GOLDEN_ROOT / fixture
    if os.environ.get("UPDATE_GOLDENS"):
        shutil.rmtree(golden, ignore_errors=True)
        for rel, data in actual.items():
            target = golden / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return
    expected = {p.relative_to(golden).as_posix(): p.read_bytes()
                for p in golden.rglob("*") if p.is_file()}
    assert sorted(actual) == sorted(expected)
    for rel in sorted(actual):
        assert actual[rel] == expected[rel], f"{fixture}: {rel} differs from its golden"
