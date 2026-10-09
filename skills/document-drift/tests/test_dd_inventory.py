from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_common import MAX_DOC_BYTES, read_json
from dd_config import DEFAULTS
from dd_helpers import make_repo
from dd_inventory import DEFAULT_NEVER_EDIT, main, run


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    return make_repo(
        tmp_path,
        [{"date": "2026-01-01T00:00:00Z", "subject": "init", "files": files}],
    )


def _inv(tmp_path: Path, files: dict[str, str], config: dict[str, Any] | None = None) -> Any:
    repo = _repo(tmp_path, files)
    cfg = {**DEFAULTS, **(config or {})}
    return run(repo, tmp_path / "work", cfg)


def _reasons(inv: Any) -> dict[str, str]:
    return {e["path"]: e["reason"] for e in inv["excluded"]}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_superpowers_tree_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "docs/superpowers/plans/x.md": "x\n",
            "docs/superpowers/archive/y.md": "y\n",
            ".superpowers/z.md": "z\n",
            "README.md": "r\n",
        },
    )
    assert inv["docs"] == ["README.md"]
    r = _reasons(inv)
    assert r["docs/superpowers/plans/x.md"] == "path:docs/superpowers/**"
    assert r["docs/superpowers/archive/y.md"] == "path:docs/superpowers/**"
    assert r[".superpowers/z.md"] == "path:.superpowers/**"


def test_research_archive_adr_rfc_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "docs/research/a.md": "a\n",
            "a/research_notes/b.md": "b\n",
            "a/archive/c.md": "c\n",
            "a/adr/d.md": "d\n",
            "a/rfcs/e.md": "e\n",
            "a/keep.md": "k\n",
        },
    )
    assert inv["docs"] == ["a/keep.md"]
    r = _reasons(inv)
    assert r["docs/research/a.md"] == "path:docs/research/**"
    assert r["a/research_notes/b.md"] == "path:**/research_notes/**"
    assert r["a/archive/c.md"] == "path:**/archive/**"
    assert r["a/adr/d.md"] == "path:**/adr/**"
    assert r["a/rfcs/e.md"] == "path:**/rfcs/**"


def test_history_basenames_excluded(tmp_path):
    names = ["CHANGELOG.md", "HISTORY.md", "LICENSE.md", "CODE_OF_CONDUCT.md", "SECURITY.md"]
    inv = _inv(tmp_path, {**{n: "x\n" for n in names}, "README.md": "r\n"})
    assert inv["docs"] == ["README.md"]
    r = _reasons(inv)
    assert r["CHANGELOG.md"] == "basename:CHANGELOG*"
    assert r["HISTORY.md"] == "basename:HISTORY*"
    assert r["LICENSE.md"] == "basename:LICENSE*"
    assert r["CODE_OF_CONDUCT.md"] == "basename:CODE_OF_CONDUCT*"
    assert r["SECURITY.md"] == "basename:SECURITY*"


def test_claude_and_agents_md_in_scope_at_any_depth(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "CLAUDE.md": "c\n",
            "AGENTS.md": "a\n",
            "pkg/sub/CLAUDE.md": "c\n",
            "pkg/AGENTS.md": "a\n",
        },
    )
    assert inv["docs"] == ["AGENTS.md", "CLAUDE.md", "pkg/AGENTS.md", "pkg/sub/CLAUDE.md"]
    assert inv["excluded"] == []


def test_vendored_nested_library_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "package.json": '{"name": "rootproj"}\n',
            "README.md": "r\n",
            "libs/foo/LICENSE": "MIT\n",
            "libs/foo/library.json": '{"name": "foo"}\n',
            "libs/foo/README.md": "foo\n",
            "libs/foo/docs/guide.md": "g\n",
            "libs/own/LICENSE": "MIT\n",
            "libs/own/package.json": '{"name": "rootproj"}\n',
            "libs/own/README.md": "own\n",
        },
    )
    assert inv["docs"] == ["README.md", "libs/own/README.md"]
    r = _reasons(inv)
    assert r["libs/foo/README.md"] == "vendored-library:libs/foo"
    assert r["libs/foo/docs/guide.md"] == "vendored-library:libs/foo"


def test_vendored_dir_names_excluded(tmp_path):
    dirs = ["libraries", "extern", "external", "third_party", "deps", "vendor"]
    inv = _inv(tmp_path, {**{f"{d}/x/README.md": "x\n" for d in dirs}, "README.md": "r\n"})
    assert inv["docs"] == ["README.md"]
    r = _reasons(inv)
    for d in ("libraries", "extern", "external", "third_party", "deps"):
        assert r[f"{d}/x/README.md"] == f"vendored-library:{d}"
    assert r["vendor/x/README.md"] == "class:vendored"


def test_tests_class_excluded(tmp_path):
    inv = _inv(tmp_path, {"tests/fixtures/x/README.md": "x\n", "README.md": "r\n"})
    assert inv["docs"] == ["README.md"]
    assert _reasons(inv)["tests/fixtures/x/README.md"] == "class:tests"


def test_generated_class_excluded(tmp_path):
    inv = _inv(tmp_path, {"generated/api.md": "x\n", "README.md": "r\n"})
    assert _reasons(inv)["generated/api.md"] == "class:generated"


def test_gitattributes_linguist_generated_and_vendored(tmp_path):
    inv = _inv(
        tmp_path,
        {
            ".gitattributes": "docs/api/** linguist-generated\n"
            "*.ext.md linguist-vendored=true\n"
            "docs/api/keep.md -linguist-generated\n",
            "docs/api/a.md": "a\n",
            "docs/api/deep/b.md": "b\n",
            "docs/api/keep.md": "k\n",
            "docs/other.md": "o\n",
            "docs/x.ext.md": "x\n",
            "sub/y.ext.md": "y\n",
        },
    )
    r = _reasons(inv)
    assert r["docs/api/a.md"] == "gitattributes:linguist-generated"
    assert r["docs/api/deep/b.md"] == "gitattributes:linguist-generated"
    assert r["docs/x.ext.md"] == "gitattributes:linguist-vendored"
    assert r["sub/y.ext.md"] == "gitattributes:linguist-vendored"
    assert "docs/api/keep.md" in inv["docs"]
    assert "docs/other.md" in inv["docs"]


def test_gitattributes_slash_pattern_is_anchored(tmp_path):
    inv = _inv(
        tmp_path,
        {
            ".gitattributes": "api/*.md linguist-generated\n",
            "api/a.md": "a\n",
            "x/api/b.md": "b\n",
        },
    )
    assert _reasons(inv) == {"api/a.md": "gitattributes:linguist-generated"}


def test_do_not_edit_header_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "a.md": "# A\n\n<!-- DO NOT EDIT: generated -->\n",
            "b.md": "x\n\n\n\n// Code generated by foo\n",
            "c.md": "1\n2\n3\n4\n5\nDO NOT EDIT\n",
        },
    )
    assert _reasons(inv) == {"a.md": "header:do-not-edit", "b.md": "header:do-not-edit"}
    assert inv["docs"] == ["c.md"]


def test_submodule_path_excluded(tmp_path):
    repo = _repo(tmp_path, {"README.md": "r\n"})
    sha = "1" * 40
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},mods.md")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},ext/sub")
    (repo / ".gitmodules").write_text('[submodule "s"]\n\tpath = ext/sub\n\turl = x\n')
    _git(repo, "add", ".gitmodules")
    inv = run(repo, tmp_path / "work", dict(DEFAULTS))
    assert inv["docs"] == ["README.md"]
    assert _reasons(inv) == {"mods.md": "submodule:mods.md"}
    assert "ext/sub" in inv["files"]


def test_template_dirs_and_tmpl_md_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "templates/a.md": "a\n",
            "x/template/b.md": "b\n",
            "skeleton/c.md": "c\n",
            "cookiecutter-pkg/d.md": "d\n",
            "e.tmpl.md": "e\n",
            "README.md": "r\n",
        },
    )
    assert inv["docs"] == ["README.md"]
    assert set(_reasons(inv).values()) == {"template"}
    assert len(inv["excluded"]) == 5


def test_drift_ignore_file_marker_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {"a.md": "# A\n\ntext\n<!-- drift-ignore-file: historical record -->\n", "b.md": "b\n"},
    )
    assert inv["docs"] == ["b.md"]
    assert _reasons(inv) == {"a.md": "marker:historical record"}


def test_drift_ignore_file_marker_only_as_real_comment(tmp_path):
    """Ruling R55: a doc that quotes the marker in inline code or a fence stays in scope."""
    quoted = (
        "# Markers\n\nAdd `<!-- drift-ignore-file: x -->` to skip a file.\n\n"
        "```markdown\n<!-- drift-ignore-file: y -->\n```\n\n"
        "    <!-- drift-ignore-file: indented code -->\n"
    )
    real = "# B\n\n<!-- drift-ignore-file: kept for history -->\n\ntext\n"
    inline = "# C\n\nText <!-- drift-ignore-file: inline comment --> here.\n"
    inv = _inv(tmp_path, {"a.md": quoted, "b.md": real, "c.md": inline})
    assert inv["docs"] == ["a.md"]
    assert _reasons(inv) == {"b.md": "marker:kept for history", "c.md": "marker:inline comment"}


def test_drift_ignore_file_marker_without_reason_excludes_nothing(tmp_path):
    """Ruling R66 (spec 8): no colon or an empty reason is a marker without a reason; the doc
    stays in scope and extraction reports the marker."""
    inv = _inv(tmp_path, {
        "a.md": "# A\n\n<!-- drift-ignore-file -->\n",
        "b.md": "# B\n\n<!-- drift-ignore-file:   -->\n",
        "c.md": "# C\n\n<!-- drift-ignore-file kept for history -->\n",
        "d.md": "# D\n\n<!-- drift-ignore-file: a reason -->\n",
    })
    assert inv["docs"] == ["a.md", "b.md", "c.md"]
    assert _reasons(inv) == {"d.md": "marker:a reason"}


def test_config_exclude_glob(tmp_path):
    inv = _inv(
        tmp_path,
        {"notes/a.md": "a\n", "x/DRAFT.md": "d\n", "README.md": "r\n"},
        {"exclude": ["notes/**", "DRAFT.md"]},
    )
    assert inv["docs"] == ["README.md"]
    r = _reasons(inv)
    assert r["notes/a.md"] == "config:notes/**"
    assert r["x/DRAFT.md"] == "config:DRAFT.md"


def test_first_reason_in_spec_order_wins(tmp_path):
    inv = _inv(tmp_path, {"docs/research/CHANGELOG.md": "x\n"}, {"exclude": ["**"]})
    assert _reasons(inv) == {"docs/research/CHANGELOG.md": "path:docs/research/**"}


def test_unreadable_doc_skipped_with_reason(tmp_path):
    repo = _repo(tmp_path, {"ok.md": "fine\n"})
    (repo / "bad.md").write_bytes(b"caf\xe9 \xff\xfe\n")
    (repo / "big.md").write_bytes(b"a" * (MAX_DOC_BYTES + 1))
    (repo / "bin.md").write_bytes(b"abc\x00def\n")
    _git(repo, "add", "bad.md", "big.md", "bin.md")
    inv = run(repo, tmp_path / "work", dict(DEFAULTS))
    assert inv["docs"] == ["ok.md"]
    assert inv["skipped"] == [
        {"path": "bad.md", "reason": "not-utf8"},
        {"path": "big.md", "reason": "too-large"},
        {"path": "bin.md", "reason": "binary"},
    ]


def test_files_lists_every_tracked_path_sorted_and_json_written(tmp_path):
    repo = _repo(tmp_path, {"b.py": "1\n", "a/x.txt": "1\n", "README.md": "r\n"})
    work = tmp_path / "work"
    inv = run(repo, work, dict(DEFAULTS))
    assert inv["files"] == ["README.md", "a/x.txt", "b.py"]
    on_disk = read_json(work / "inventory.json")
    assert on_disk == inv
    assert set(on_disk) == {"docs", "excluded", "skipped", "files", "never_edit_re"}


def test_never_edit_re_default_and_extended(tmp_path):
    inv = _inv(tmp_path, {"README.md": "r\n"})
    assert inv["never_edit_re"] == DEFAULT_NEVER_EDIT
    inv = _inv(tmp_path / "b", {"README.md": "r\n"}, {"never_edit_heading": "(?i)faq"})
    # Python 3.11+ rejects a global flag group inside the combined pattern, so each part's
    # leading (?i) becomes a scoped (?i:...) group; the result still compiles and matches both.
    body = DEFAULT_NEVER_EDIT.removeprefix("(?i)")
    assert inv["never_edit_re"] == f"(?:(?i:{body}))|(?:(?i:faq))"
    compiled = re.compile(inv["never_edit_re"])
    assert compiled.search("FAQ") and compiled.search("Why we did it")
    inv = _inv(tmp_path / "c", {"README.md": "r\n"}, {"never_edit_heading": "faq"})
    compiled = re.compile(inv["never_edit_re"])
    assert compiled.search("faq") and not compiled.search("FAQ") and compiled.search("HISTORY")


def test_main_writes_inventory_and_prints_config_warnings(tmp_path, capsys):
    repo = _repo(tmp_path, {"README.md": "r\n", ".document-drift.yaml": "bogus: 1\n"})
    work = tmp_path / "work"
    assert main([str(repo), "--workdir", str(work)]) == 0
    assert "bogus" in capsys.readouterr().err
    assert read_json(work / "inventory.json")["docs"] == ["README.md"]


def test_main_not_a_repo_refuses(tmp_path):
    (tmp_path / "plain").mkdir()
    assert main([str(tmp_path / "plain"), "--workdir", str(tmp_path / "w")]) == 2


@pytest.mark.parametrize("name", ["README.MD", "notes.Md"])
def test_md_extension_case_insensitive(tmp_path, name):
    assert _inv(tmp_path, {name: "x\n"})["docs"] == [name]


@pytest.mark.parametrize("pattern", ["docs/legacy", "docs/legacy/"])
def test_config_exclude_directory_pattern_covers_contents(tmp_path, pattern):
    inv = _inv(
        tmp_path,
        {"docs/legacy/a.md": "a\n", "docs/legacy/deep/b.md": "b\n", "docs/new.md": "n\n"},
        {"exclude": [pattern]},
    )
    assert inv["docs"] == ["docs/new.md"]
    assert set(_reasons(inv)) == {"docs/legacy/a.md", "docs/legacy/deep/b.md"}


def test_basename_case_insensitive_only_on_conventional_stem(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "changelog.md": "x\n",
            "Security.md": "x\n",
            "release-notes.md": "x\n",
            "LICENSE-MIT.md": "x\n",
            "CHANGELOG-v2.md": "x\n",
            "license-faq.md": "x\n",
            "notice-board.md": "x\n",
            "history-of-the-project.md": "x\n",
            "docs/authorship.md": "x\n",
        },
    )
    assert inv["docs"] == [
        "docs/authorship.md", "history-of-the-project.md", "license-faq.md", "notice-board.md",
    ]
    r = _reasons(inv)
    assert r["changelog.md"] == "basename:CHANGELOG*"
    assert r["Security.md"] == "basename:SECURITY*"
    assert r["release-notes.md"] == "basename:RELEASE-NOTES"
    assert r["LICENSE-MIT.md"] == "basename:LICENSE*"
    assert r["CHANGELOG-v2.md"] == "basename:CHANGELOG*"


def test_walk_ignore_dirs_excluded(tmp_path):
    inv = _inv(
        tmp_path,
        {
            "node_modules/x/README.md": "x\n",
            "dist/README.md": "x\n",
            "build/notes.md": "x\n",
            "tools/build/README.md": "x\n",
            "tools/build/package.json": "{}\n",
            "venv/a.md": "x\n",
            "dist.md": "x\n",
        },
    )
    assert inv["docs"] == ["dist.md", "tools/build/README.md"]
    r = _reasons(inv)
    assert r["node_modules/x/README.md"] == "ignored-dir:node_modules"
    assert r["dist/README.md"] == "ignored-dir:dist"
    assert r["build/notes.md"] == "ignored-dir:build"
    assert r["venv/a.md"] == "ignored-dir:venv"
