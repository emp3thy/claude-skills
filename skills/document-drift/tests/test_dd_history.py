from __future__ import annotations

import subprocess
from pathlib import Path

from dd_helpers import index_commit, make_repo
from dd_history import (
    History,
    changed_files,
    diff_hunks,
    drift_base_commits,
    is_ancestor,
)

BODY = "".join(f"line number {i} of a reasonably long body\n" for i in range(30))


def _c(date: str, subject: str, **kw: object) -> dict[str, object]:
    return {"date": f"2026-01-{date}T00:00:00Z", "subject": subject, **kw}


def _rev(repo: Path, rev: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", rev], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def test_line_snapshots_point_at_line_author_commit(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "one", files={"README.md": "first\n"}),
            _c("02", "two", files={"README.md": "first\nsecond\n"}),
        ],
    )
    snaps = History(repo).line_snapshots("README.md")
    assert snaps is not None
    assert snaps[1] == _rev(repo, "HEAD~1")
    assert snaps[2] == _rev(repo, "HEAD")
    assert len(snaps[2]) == 40


def test_line_snapshots_ignore_whitespace_only_change(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "one", files={"README.md": "alpha beta\n"}),
            _c("02", "two", files={"README.md": "alpha   beta\n"}),
        ],
    )
    snaps = History(repo).line_snapshots("README.md")
    assert snaps == {1: _rev(repo, "HEAD~1")}


def test_line_snapshots_ignore_working_tree_edits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"README.md": "a\nb\n"})])
    (repo / "README.md").write_bytes(b"a\nchanged\nb\n")
    assert History(repo).line_snapshots("README.md") == {
        1: _rev(repo, "HEAD"),
        2: _rev(repo, "HEAD"),
    }


def test_line_snapshots_none_without_history(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"a.md": "x\n"})])
    assert History(repo).line_snapshots("missing.md") is None


def test_tree_at_lists_files_and_dirs(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path, [_c("01", "one", files={"a.md": "x\n", "src/pkg/m.py": "y\n", "src/n.py": "z\n"})]
    )
    h = History(repo)
    tree = h.tree_at("HEAD")
    assert tree is not None
    files, dirs = tree
    assert files == frozenset({"a.md", "src/pkg/m.py", "src/n.py"})
    assert dirs == frozenset({"src", "src/pkg"})
    assert h.head_files() == tree
    assert h.tree_at("deadbeef" * 5) is None


def test_show_returns_content_or_none(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"a.md": "x\n"})])
    h = History(repo)
    assert h.show("HEAD", "a.md") == "x\n"
    assert h.show("HEAD", "nope.md") is None


def _rename_repo(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path,
        [
            _c("01", "base", files={"old.py": BODY, "keep.py": "k\n"}),
            _c("02", "first rename", rename={"old.py": "mid.py"}),
            _c("03", "second rename", rename={"mid.py": "new.py"}),
        ],
    )


def test_final_name_follows_two_hop_chain(tmp_path: Path) -> None:
    repo = _rename_repo(tmp_path)
    h = History(repo)
    base = _rev(repo, "HEAD~2")
    names, commit = h.final_name(base, "old.py")
    assert names == frozenset({"new.py"})
    assert commit == _rev(repo, "HEAD")[:7]
    renames = h.renames_since(base)
    assert renames["old.py"] == ("mid.py", _rev(repo, "HEAD~1")[:7])
    assert renames["mid.py"] == ("new.py", _rev(repo, "HEAD")[:7])


def test_final_name_unrenamed_and_missing(tmp_path: Path) -> None:
    repo = _rename_repo(tmp_path)
    h = History(repo)
    base = _rev(repo, "HEAD~2")
    assert h.final_name(base, "keep.py") == (frozenset({"keep.py"}), None)
    assert h.final_name(base, "ghost.py") == (frozenset(), None)


def test_final_name_empty_when_deleted(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"gone.py": BODY}),
            _c("02", "delete", delete=["gone.py"]),
        ],
    )
    assert History(repo).final_name(_rev(repo, "HEAD~1"), "gone.py") == (frozenset(), None)


def test_final_name_rename_then_delete(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"a.py": BODY}),
            _c("02", "rename", rename={"a.py": "b.py"}),
            _c("03", "delete", delete=["b.py"]),
        ],
    )
    assert History(repo).final_name(_rev(repo, "HEAD~2"), "a.py") == (frozenset(), None)


def test_final_name_survives_rename_cycle(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"a.py": BODY}),
            _c("02", "to b", rename={"a.py": "b.py"}),
            _c("03", "back to a", rename={"b.py": "a.py"}),
        ],
    )
    assert History(repo).final_name(_rev(repo, "HEAD~2"), "a.py") == (frozenset({"a.py"}), None)


def test_final_name_path_recreated_after_rename(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"old.py": BODY}),
            _c("02", "rename", rename={"old.py": "new.py"}),
            _c("03", "recreate", files={"old.py": "fresh\n"}),
        ],
    )
    assert History(repo).final_name(_rev(repo, "HEAD~2"), "old.py") == (frozenset({"old.py"}), None)


def test_deleting_commit_literal_pathspec(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"docs/a[1].md": "x\n", "docs/a1.md": "y\n"}),
            _c("02", "delete other", delete=["docs/a1.md"]),
            _c("03", "delete bracket", delete=["docs/a[1].md"]),
        ],
    )
    h = History(repo)
    assert h.deleting_commit(_rev(repo, "HEAD~2"), "docs/a[1].md") == _rev(repo, "HEAD")[:7]


def test_deleting_commit(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"gone.py": BODY, "stay.py": "s\n"}),
            _c("02", "delete", delete=["gone.py"]),
        ],
    )
    h = History(repo)
    base = _rev(repo, "HEAD~1")
    assert h.deleting_commit(base, "gone.py") == _rev(repo, "HEAD")[:7]
    assert h.deleting_commit(base, "stay.py") is None


def test_last_commit_touching_finds_removed_make_target(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"Makefile": "build:\n\techo b\n\nlint:\n\techo l\n"}),
            _c("02", "unrelated", files={"Makefile": "build:\n\techo b2\n\nlint:\n\techo l\n"}),
            _c("03", "drop lint", files={"Makefile": "build:\n\techo b2\n"}),
        ],
    )
    h = History(repo)
    base = _rev(repo, "HEAD~2")
    assert h.last_commit_touching(base, "Makefile", "lint:") == _rev(repo, "HEAD")[:7]
    assert h.last_commit_touching(base, "Makefile", "zzz") is None


def test_results_are_cached(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"a.md": "x\n"})])
    h = History(repo)
    assert h.line_snapshots("a.md") is h.line_snapshots("a.md")
    assert h.tree_at("HEAD") is h.tree_at("HEAD")


# Names git C-quotes in plain listings even with core.quotePath=false. Windows cannot hold
# them on disk, so the tests record them with plumbing (dd_helpers.index_commit).
QUOTED = ('legacy/q"x.py', "legacy/tab\there.py")


def _quoted_repo(tmp_path: Path) -> Path:
    repo = make_repo(tmp_path, [_c("01", "one", files={"legacy/a.py": "a = 1\n"})])
    index_commit(repo, "2026-01-02T00:00:00Z", "quoted names",
                 add={name: f"# {name}\n" for name in QUOTED})
    return repo


def test_list_dir_keeps_names_git_would_quote(tmp_path: Path) -> None:
    # final-review residual R70: an `ls-tree` listing without -z C-quotes these names, and a
    # prefix filter then drops them, so a partly deleted directory looked wholly moved
    repo = _quoted_repo(tmp_path)
    assert History(repo).list_dir(_rev(repo, "HEAD"), "legacy") == frozenset(
        {"legacy/a.py", *QUOTED})


def test_tree_at_keeps_names_git_would_quote(tmp_path: Path) -> None:
    repo = _quoted_repo(tmp_path)
    tree = History(repo).tree_at("HEAD")
    assert tree is not None
    files, dirs = tree
    assert {"legacy/a.py", *QUOTED} <= files
    assert "legacy" in dirs


def test_drift_base_commits_newest_first(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "base", files={"a.md": "x\n"}),
            _c("02", "fix one\n\nDrift-Base: 0123456789abcdef", files={"a.md": "y\n"}),
            _c("03", "unrelated", files={"a.md": "z\n"}),
            _c("04", "fix two\n\nDrift-Base: fedcba9876543210", files={"a.md": "w\n"}),
        ],
    )
    assert drift_base_commits(repo) == [
        (_rev(repo, "HEAD"), "fedcba9876543210"),
        (_rev(repo, "HEAD~2"), "0123456789abcdef"),
    ]


def test_drift_base_found_in_squash_message(tmp_path: Path) -> None:
    squash = (
        "Squashed PR\n\n* docs: fix\n\n"
        "  details\nDrift-Base: abcdef1234567\n\n* more work\n"
    )
    repo = make_repo(tmp_path, [_c("01", squash, files={"a.md": "x\n"})])
    assert drift_base_commits(repo) == [(_rev(repo, "HEAD"), "abcdef1234567")]


def test_drift_base_commits_empty_without_trailer(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "plain", files={"a.md": "x\n"})])
    assert drift_base_commits(repo) == []
    assert drift_base_commits(tmp_path / "missing") == []


def test_is_ancestor(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [_c("01", "one", files={"a.md": "x\n"}), _c("02", "two", files={"a.md": "y\n"})],
    )
    first, last = _rev(repo, "HEAD~1"), _rev(repo, "HEAD")
    assert is_ancestor(repo, first, last)
    assert not is_ancestor(repo, last, first)
    assert not is_ancestor(repo, "0" * 40, last)


def test_changed_files_sorted(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "one", files={"b.md": "x\n", "a.md": "x\n", "keep.md": "k\n"}),
            _c("02", "two", files={"c.md": "new\n", "a.md": "y\n"}),
        ],
    )
    assert changed_files(repo, _rev(repo, "HEAD~1")) == ["a.md", "c.md"]
    assert changed_files(repo, "0" * 40) == []


def test_diff_hunks_ranges_and_pure_deletion(tmp_path: Path) -> None:
    old = "".join(f"l{i}\n" for i in range(1, 9))
    new = "l1\nl2\nl3\nl4\nl5\nl8\n"
    repo = make_repo(
        tmp_path,
        [_c("01", "one", files={"d.md": old}), _c("02", "two", files={"d.md": new})],
    )
    [hunk] = diff_hunks(repo, _rev(repo, "HEAD~1"), ["d.md"])["d.md"]
    assert hunk["file"] == "d.md"
    assert (hunk["old_start"], hunk["old_end"]) == (6, 7)
    assert (hunk["new_start"], hunk["new_end"]) == (5, 4)
    assert hunk["text"] == "-l6\n-l7\n"


def test_diff_hunks_insertion_and_replacement(tmp_path: Path) -> None:
    old = "".join(f"l{i}\n" for i in range(1, 9))
    new = "l1\nl2\nX\nl4\nl5\nl6\nl7\nl8\nnew\n"
    repo = make_repo(
        tmp_path,
        [_c("01", "one", files={"d.md": old}), _c("02", "two", files={"d.md": new})],
    )
    replaced, added = diff_hunks(repo, _rev(repo, "HEAD~1"), ["d.md"])["d.md"]
    assert (replaced["old_start"], replaced["old_end"]) == (3, 3)
    assert (replaced["new_start"], replaced["new_end"]) == (3, 3)
    assert replaced["text"] == "-l3\n+X\n"
    assert (added["old_start"], added["old_end"]) == (8, 7)
    assert (added["new_start"], added["new_end"]) == (9, 9)
    assert added["text"] == "+new\n"


def test_diff_hunks_only_requested_files(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        [
            _c("01", "one", files={"a.md": "x\n", "b.md": "x\n", "c d.md": "x\n"}),
            _c("02", "two", files={"a.md": "y\n", "b.md": "y\n", "c d.md": "y\n"}),
        ],
    )
    base = _rev(repo, "HEAD~1")
    hunks = diff_hunks(repo, base, ["b.md", "c d.md", "untouched.md"])
    assert sorted(hunks) == ["b.md", "c d.md"]
    assert hunks["b.md"][0]["file"] == "b.md"
    assert diff_hunks(repo, base, []) == {}
    assert diff_hunks(repo, "0" * 40, ["b.md"]) == {}
