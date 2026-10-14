"""Byte goldens for a full run over each corpus fixture and state (success criterion 6).

``run_fixture`` drives start (in README mode compose), verify and finish with the canned agent
outputs; state 1 runs on 2026-01-02 and state 2 on the harness's pinned later date, on branch
``docs/drift-golden``. Compared byte for byte against ``golden/<fixture>/state<N>/``: the
stage outputs, the commit messages and every doc the run edited (under ``docs/<doc path>``);
a README-mode run (phase B) adds its own outputs, the summary and the README it wrote
(``docs/README.md``), and a run that made the citations commit (phase C) adds
``script-edits.json``, that commit's message and the summary. Absolute paths in the outputs
are rewritten to ``<workdir>``. A file a run does not produce is recorded by its absence from
the golden directory.
``UPDATE_GOLDENS=1`` rewrites the golden directories instead of comparing; read every
regenerated commit message and doc before committing them.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from dd_common import read_json
from dd_corpus import FIXTURES, fixture_states, run_fixture

GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"
BRANCH = "docs/drift-golden"
OUTPUTS = (
    "defindex.json", "anchors.json", "changes.json", "units.json", "patterns.json",
    "gaps.json", "notices.json", "edits.json", "plan-docs.json", "plan-verify.json",
    "applied.json", "commit-msg-corrections.txt", "commit-msg-additions.txt",
)
# compared only in README mode, so the phase A goldens stay as they were
README_OUTPUTS = ("areas.json", "sheets.json", "plan-readme.json", "readme.json", "summary.md")
# compared only when the run made the citations commit (phase C), so the earlier goldens stay
SCRIPT_OUTPUTS = ("script-edits.json", "commit-msg-citations.txt", "summary.md")
PAIRS = [(name, state) for name in FIXTURES for state in fixture_states(name)]


def _actual(repo: Path, workdir: Path) -> dict[str, bytes]:
    """The compared files of a run by golden-relative name; absent files are left out."""
    native = str(workdir)
    posix = workdir.as_posix()
    out: dict[str, bytes] = {}
    readme = bool(read_json(workdir / "preflight.json").get("readme"))
    script = (workdir / "commit-msg-citations.txt").is_file()
    names = OUTPUTS + (README_OUTPUTS if readme else ()) + (SCRIPT_OUTPUTS if script else ())
    for name in dict.fromkeys(names):
        path = workdir / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        for form in sorted({native, posix}, key=len, reverse=True):
            data = data.replace(form.encode("utf-8"), b"<workdir>")
        out[name] = data
    applied = workdir / "applied.json"
    if applied.is_file():
        record = read_json(applied)
        for doc in record["docs"]:
            out[f"docs/{doc}"] = (repo / doc).read_bytes()
        if record.get("readme"):
            out["docs/README.md"] = (repo / "README.md").read_bytes()
    return out


@pytest.mark.parametrize(("name", "state"), PAIRS,
                         ids=[f"{n.replace('-', '_')}-state{s}" for n, s in PAIRS])
def test_outputs_match_goldens(name: str, state: int, tmp_path: Path) -> None:
    run = run_fixture(name, state, tmp_path, branch=BRANCH)
    assert [code for _, code in run.exits[-3:]] == [0, 0, 0]
    actual = _actual(run.repo, run.path)
    golden = GOLDEN_ROOT / name / f"state{state}"
    if os.environ.get("UPDATE_GOLDENS"):
        shutil.rmtree(golden, ignore_errors=True)
        for rel, data in actual.items():
            target = golden / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        golden.mkdir(parents=True, exist_ok=True)
        return
    expected = {p.relative_to(golden).as_posix(): p.read_bytes()
                for p in golden.rglob("*") if p.is_file()}
    for rel in sorted(set(actual) | set(expected)):
        assert rel in expected, f"{name} state {state}: {rel} is produced but has no golden"
        assert rel in actual, f"{name} state {state}: {rel} has a golden but was not produced"
        assert actual[rel] == expected[rel], f"{name} state {state}: {rel} differs from its golden"
