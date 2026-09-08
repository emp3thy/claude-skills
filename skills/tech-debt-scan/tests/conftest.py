"""Pytest path setup so scripts/ and tests/helpers imports work in tests."""
from __future__ import annotations

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = _TESTS_DIR.parent / "scripts"
HELPERS_DIR = _TESTS_DIR / "helpers"
# Insert in reverse so each insert(0, ...) leaves SCRIPTS_DIR ahead of
# HELPERS_DIR: a tests/helpers module must never shadow a scripts/ module.
for _dir in reversed((SCRIPTS_DIR, HELPERS_DIR)):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def service_py_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("service-py", tmp_path_factory.mktemp("service-py"))


@pytest.fixture(scope="session")
def web_ts_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("web-ts", tmp_path_factory.mktemp("web-ts"))


@pytest.fixture(scope="session")
def mixed_decoys_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from make_history import replay_fixture

    return replay_fixture("mixed-decoys", tmp_path_factory.mktemp("mixed-decoys"))


@pytest.fixture()
def v2_design_workdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """A v2 design.md plus its verified.json/findings.json/ranked.json, in one dir.

    Copied from the ``service-py`` golden corpus (every finding carries a
    fingerprint). One finding's ``status`` is flipped from ``pending`` to
    ``approved`` so a promote run has something to emit.

    The process cwd is set to the workdir, which is where these tests put
    their baselines and bundle directories, so relative paths and anything
    the code under test writes beside the cwd stay inside the test's own
    temporary tree rather than the pytest run's working directory. Nothing
    in promote.py derives a repository root from the cwd any more (ruling 19
    replaced that ``Path.cwd()`` call with a root derived from
    ``--baseline``'s own path), so the chdir no longer stands in for a repo
    root; ``test_root_is_derived_from_baseline_not_cwd`` is the one test
    that overrides it, chdir-ing to an unrelated sibling directory precisely
    to prove the cwd plays no part in that derivation.
    """
    golden = Path(__file__).parent / "golden" / "service-py"
    workdir = tmp_path
    design = workdir / "design.md"
    design.write_bytes((golden / "design.md").read_bytes())
    for name in ("verified.json", "findings.json", "ranked.json"):
        (workdir / name).write_bytes((golden / name).read_bytes())
    text = design.read_text(encoding="utf-8").replace("status: pending", "status: approved", 1)
    design.write_text(text, encoding="utf-8")
    monkeypatch.chdir(workdir)
    return design, workdir
