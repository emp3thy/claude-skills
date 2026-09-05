from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from kb_checkpoint import begin, commit, current_branch, default_branch, is_repo, main
from kb_common import EXIT_VALIDATION, KbError, run_cli


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _repo(tmp_path: Path, default: str = "main") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", default)
    _git(repo, "config", "user.email", "kb@example.com")
    _git(repo, "config", "user.name", "kb")
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    _git(repo, "add", "--", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_is_repo_and_branches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert is_repo(repo) is True
    assert is_repo(tmp_path) is False
    assert current_branch(repo) == "main"
    assert default_branch(repo) == "main"
    master = _repo(tmp_path / "m", default="master")
    assert default_branch(master) == "master"


def test_begin_creates_the_branch_on_the_default_branch_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": True,
                                               "switched": True}
    assert current_branch(repo) == "karate-bootstrap"
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": False,
                                               "switched": False}
    _git(repo, "checkout", "-q", "main")
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": False,
                                               "switched": True}
    _git(repo, "checkout", "-q", "-b", "ralph/PBI-42")
    assert begin(repo, "ralph/PBI-42") == {"branch": "ralph/PBI-42", "created": False,
                                               "switched": False}


def test_commit_stages_only_the_tests_dir(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "pom.xml").write_text("<project/>", encoding="utf-8")
    (repo / "unrelated.txt").write_text("x", encoding="utf-8")
    result = commit(repo, 4, "scaffold the Karate module", "karate-tests")
    assert result["committed"] is True
    assert result["files"] == ["karate-tests/pom.xml"]
    assert len(result["sha"]) >= 7
    assert _git(repo, "log", "-1", "--pretty=%s") == (
        "test(karate-bootstrap): phase 4: scaffold the Karate module"
    )
    assert _git(repo, "status", "--short") == "?? unrelated.txt"
    assert commit(repo, 5, "nothing new", "karate-tests") == {"committed": False, "sha": None,
                                                              "files": []}


def test_commit_and_begin_reject_a_non_repo(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        begin(tmp_path, "karate-bootstrap")
    assert excinfo.value.exit_code == EXIT_VALIDATION
    with pytest.raises(KbError):
        commit(tmp_path, 1, "x", "karate-tests")


def test_cli_and_no_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert run_cli(main, ["begin", "--repo", str(repo)]) == 0
    assert '"branch": "karate-bootstrap"' in capsys.readouterr().out
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "flow-map.yaml").write_text("version: 1\n", encoding="utf-8")
    assert run_cli(main, ["commit", "--repo", str(repo), "--phase", "2",
                          "--message", "ledger traced"]) == 0
    assert '"committed": true' in capsys.readouterr().out
    assert run_cli(main, ["commit", "--repo", str(tmp_path), "--phase", "3", "--message", "x",
                          "--no-commit"]) == 0
    assert "no-commit" in capsys.readouterr().out
    assert run_cli(main, ["begin", "--repo", str(tmp_path)]) == EXIT_VALIDATION
