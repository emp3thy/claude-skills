from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from dd_common import EXIT_REFUSED, StepError, read_json
from dd_preflight import run

GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run([*GIT, "-C", str(repo), *args], capture_output=True, text=True,
                         check=True)
    return out.stdout.strip()


def _repo(tmp_path: Path, identity: bool = True) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "core.autocrlf", "false")
    if identity:
        _git(root, "config", "user.name", "T")
        _git(root, "config", "user.email", "t@example.com")
    (root / "README.md").write_text("hi\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "init")
    workdir = root / ".document-drift"
    workdir.mkdir()
    return root, workdir


def test_refuses_not_a_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(StepError) as exc:
        run(plain, tmp_path / "work", "drift/x", False)
    assert exc.value.code == EXIT_REFUSED


def test_success_writes_preflight(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    out = run(root, workdir, "drift/x", False)
    assert out["head"] == _git(root, "rev-parse", "HEAD")
    assert out["branch_from"] == "main"
    assert out["branch"] == "drift/x"
    assert read_json(workdir / "preflight.json") == out
    assert out["git_version"].startswith("git version")


def test_refuses_dirty_tree(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", False)
    assert exc.value.code == EXIT_REFUSED
    assert "\n" not in str(exc.value)


def test_refuses_detached_head(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    _git(root, "checkout", "-q", "--detach")
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", False)
    assert exc.value.code == EXIT_REFUSED
    assert "detached" in str(exc.value)


def test_refuses_existing_branch(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    _git(root, "branch", "drift/x")
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", False)
    assert exc.value.code == EXIT_REFUSED
    assert "--branch" in str(exc.value)


def test_refuses_missing_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, workdir = _repo(tmp_path, identity=False)
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                 "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift/x", False)
    assert exc.value.code == EXIT_REFUSED
    assert "identity" in str(exc.value)
    out = run(root, workdir, "drift/x", True)
    assert out["branch"] == "drift/x"


def test_check_mode_allows_dirty_tree(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    _git(root, "branch", "drift/x")
    out = run(root, workdir, "drift/x", True)
    assert out["branch_from"] == "main"


def test_check_mode_still_refuses_detached(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    _git(root, "checkout", "-q", "--detach")
    with pytest.raises(StepError):
        run(root, workdir, "drift/x", True)


def test_workdir_added_to_info_exclude_once(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    run(root, workdir, "drift/x", False)
    run(root, workdir, "drift/x", False)
    exclude = (root / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert exclude.splitlines().count(".document-drift/") == 1


def test_refuses_invalid_branch_name(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    with pytest.raises(StepError) as exc:
        run(root, workdir, "drift fixes", False)
    assert exc.value.code == EXIT_REFUSED
    assert "drift fixes" in str(exc.value)
