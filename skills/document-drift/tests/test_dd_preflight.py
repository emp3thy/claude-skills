from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from dd_common import EXIT_REFUSED, StepError, read_json
from dd_preflight import run, tree_state

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


def test_check_mode_allows_detached_head(tmp_path: Path) -> None:
    """Ruling R56: --check creates no branch, so a detached HEAD (a CI checkout) runs."""
    root, workdir = _repo(tmp_path)
    head = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "--detach")
    out = run(root, workdir, "drift fixes", True)
    assert out["branch_from"] is None
    assert out["head"] == head
    assert read_json(workdir / "preflight.json")["branch_from"] is None


def test_check_mode_still_refuses_non_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(StepError) as exc:
        run(plain, plain / ".document-drift", "drift/x", True)
    assert exc.value.code == EXIT_REFUSED


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


@pytest.mark.parametrize("check", [False, True])
def test_refuses_a_subdirectory_of_the_repository(tmp_path: Path, check: bool) -> None:
    # R61, final review C3: every path is root-relative, so <repo> must be the top level
    root, _ = _repo(tmp_path)
    sub = root / "pkg"
    sub.mkdir()
    (sub / "README.md").write_text("pkg\n", encoding="utf-8")
    _git(root, "add", "pkg/README.md")
    _git(root, "commit", "-q", "-m", "pkg")
    with pytest.raises(StepError) as exc:
        run(sub, tmp_path / "work", "drift/x", check)
    assert exc.value.code == EXIT_REFUSED
    assert "top level" in str(exc.value)
    assert _git(root, "rev-parse", "--show-toplevel") in str(exc.value)
    assert not (tmp_path / "work" / "preflight.json").exists()


@pytest.mark.parametrize("check", [False, True])
def test_refuses_a_bare_repository_and_the_git_directory(tmp_path: Path, check: bool) -> None:
    # R61: --is-inside-work-tree prints false there
    root, _ = _repo(tmp_path)
    bare = tmp_path / "bare.git"
    _git(tmp_path, "clone", "-q", "--bare", str(root), str(bare))
    for where in (bare, root / ".git"):
        with pytest.raises(StepError) as exc:
            run(where, tmp_path / "work", "drift/x", check)
        assert exc.value.code == EXIT_REFUSED
        assert "not inside a working tree" in str(exc.value)


def test_accepts_the_top_level_through_another_spelling(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    (root / "sub").mkdir()
    out = run(root / "." / "sub" / "..", workdir, "drift/x", True)
    assert out["head"] == _git(root, "rev-parse", "HEAD")


def test_records_the_run_flags(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    out = run(root, workdir, "drift/x", False, base="main", full=True, date="2026-01-02")
    assert (out["check"], out["base"], out["full"], out["date"], out["dirty"]) == (
        False, "main", True, "2026-01-02", {})
    assert read_json(workdir / "preflight.json") == out


def test_check_mode_records_the_dirty_files(tmp_path: Path) -> None:
    root, workdir = _repo(tmp_path)
    (root / "README.md").write_bytes(b"changed\n")
    (root / "notes").mkdir()
    (root / "notes" / "todo.txt").write_bytes(b"x\n")
    (workdir / "scratch.json").write_bytes(b"{}\n")
    out = run(root, workdir, "drift/x", True)
    readme, todo = (hashlib.sha256(b).hexdigest() for b in (b"changed\n", b"x\n"))
    assert out["dirty"] == {"README.md": f" M {readme}", "notes/todo.txt": f"?? {todo}"}
    (root / "notes" / "todo.txt").unlink()
    assert tree_state(root, workdir) == {"README.md": f" M {readme}"}


def test_tree_state_skips_the_workdir_even_when_not_excluded(tmp_path: Path) -> None:
    root, _ = _repo(tmp_path)
    other = root / "work"
    other.mkdir()
    (other / "plan.json").write_bytes(b"[]\n")
    assert tree_state(root, other) == {}
    assert list(tree_state(root, root / ".document-drift")) == ["work/plan.json"]
