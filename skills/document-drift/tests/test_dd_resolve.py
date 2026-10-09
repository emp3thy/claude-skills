from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_extract import extract_doc
from dd_helpers import make_repo
from dd_history import History
from dd_inventory import DEFAULT_NEVER_EDIT
from dd_manifests import script_source
from dd_resolve import Resolver, heading_slugs, main, resolve_token, run, slugify_heading

NEVER = re.compile(DEFAULT_NEVER_EDIT)


def _c(day: str, subject: str, **kw: object) -> dict[str, object]:
    return {"date": f"2026-01-{day}T00:00:00Z", "subject": subject, **kw}


def _sha7(repo: Path, rev: str = "HEAD") -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", rev], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()[:7]


def _tokens(repo: Path, doc: str) -> list[dict[str, Any]]:
    text = (repo / doc).read_bytes().decode("utf-8")
    tokens, _ = extract_doc(doc, text, NEVER)
    return tokens


def _cands(repo: Path, doc: str = "README.md") -> list[dict[str, Any]]:
    resolver = Resolver(repo, History(repo))
    return [c for t in _tokens(repo, doc) if (c := resolver.classify(t)) is not None]


def _one(repo: Path, doc: str = "README.md") -> dict[str, Any]:
    cands = _cands(repo, doc)
    assert len(cands) == 1, cands
    return cands[0]


def _shape(c: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return c["class"], c["outcome"], c["replacement"], c["human_kind"]


def _tok(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "doc": "README.md", "line": 1, "col": 0, "end_col": 1, "kind": "path", "text": "x",
        "target_doc": None, "script_tool": None, "version": None, "context": "inline-code",
        "link": None, "block": {"kind": "paragraph", "line_start": 1, "line_end": 1},
        "subject": False, "heading_path": [], "never_edit": False, "generated": False,
        "ignored": None, "editable": True, "tree_label": None,
    }
    base.update(kw)
    return base


def _reader(texts: dict[str, str]) -> Any:
    return texts.get


# -- paths -----------------------------------------------------------------------------------


def test_present_path_gives_no_candidate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "See `src/app.py`, [the app](src/app.py) and `src/`.\n",
        "src/app.py": "x = 1\n",
    })])
    assert len(_tokens(repo, "README.md")) == 3
    assert _cands(repo) == []


def test_renamed_file_doc_relative_mode_replacement(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "pkg/README.md": "Run `old.py` here.\n\nAlso [./old.py](./old.py).\n",
            "pkg/old.py": "print('a long enough body for rename detection')\n",
        }),
        _c("02", "rename", rename={"pkg/old.py": "pkg/new.py"}),
    ])
    sha = _sha7(repo)
    cands = _cands(repo, "pkg/README.md")
    assert [_shape(c) for c in cands] == [
        ("provable-replace", "unique", "new.py", None),
        ("provable-replace", "unique", "./new.py", None),
    ]
    first = cands[0]
    assert first["existed_then"] is True
    assert first["resolved_then"] == "pkg/old.py"
    assert first["evidence_commit"] == sha
    assert first["evidence"] == f"renamed in {sha}"
    assert first["text"] == "old.py" and first["doc"] == "pkg/README.md"
    assert len(first["snapshot"]) == 40


def test_renamed_file_doc_relative_mode_moves_to_other_dir(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "pkg/README.md": "Run `old.py` here.\n",
            "pkg/old.py": "print('a long enough body for rename detection')\n",
        }),
        _c("02", "rename", rename={"pkg/old.py": "lib/new.py"}),
    ])
    assert _shape(_one(repo, "pkg/README.md")) == ("provable-replace", "unique", "../lib/new.py",
                                                   None)


def test_renamed_file_root_mode_replacement(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "docs/guide.md": "Entry point: `src/old.py`.\n",
            "src/old.py": "print('a long enough body for rename detection')\n",
        }),
        _c("02", "rename", rename={"src/old.py": "src/main.py"}),
    ])
    cand = _one(repo, "docs/guide.md")
    assert _shape(cand) == ("provable-replace", "unique", "src/main.py", None)
    assert cand["resolved_then"] == "src/old.py"


def test_resolve_suffix_and_basename() -> None:
    files = frozenset({"README.md", "services/api/handlers.py", "services/api/app.py"})
    dirs = frozenset({"services", "services/api"})
    read = _reader({})
    doc = "docs/guide.md"
    assert resolve_token(_tok(doc=doc, text="api/handlers.py"), files, dirs, read) == (
        "services/api/handlers.py")
    assert resolve_token(_tok(doc=doc, text="app.py"), files, dirs, read) == "services/api/app.py"
    assert resolve_token(_tok(doc=doc, text="api/"), files, dirs, read) == "services/api"
    assert resolve_token(_tok(doc=doc, text="api/missing.py"), files, dirs, read) is None
    assert resolve_token(_tok(doc=doc, text="../api/handlers.py"), files, dirs, read) is None


def test_suffix_only_match_at_snapshot_is_never_existed(tmp_path: Path) -> None:
    # R26: at the snapshot only doc and root modes count as existed-then
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "docs/guide.md": "Handlers live in `api/handlers.py`.\n",
            "services/api/handlers.py": "print('a long enough body for rename detection')\n",
        }),
        _c("02", "rename", rename={"services/api/handlers.py": "services/api/routes.py"}),
    ])
    cand = _one(repo, "docs/guide.md")
    assert _shape(cand) == ("summary-only", None, None, None)
    assert cand["existed_then"] is False


@pytest.mark.parametrize("change", ["delete", "rename"])
def test_basename_only_match_at_snapshot_is_never_existed(tmp_path: Path, change: str) -> None:
    # R26, reviewer probe 6: an illustrative bare name matched an unrelated fixture
    later: dict[str, object] = (
        {"delete": ["tests/fixtures/config.yml"], "files": {"x.txt": "y\n"}}
        if change == "delete"
        else {"rename": {"tests/fixtures/config.yml": "tests/fixtures/settings.yml"}}
    )
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "The service reads `config.yml` at startup.\n",
                               "tests/fixtures/config.yml": "a: 1\n" * 20}),
        _c("02", "change fixture", **later),
    ])
    assert _shape(_one(repo)) == ("summary-only", None, None, None)


def test_deleted_path_with_same_basename_at_head_is_human(tmp_path: Path) -> None:
    # R27, reviewer probe 4: moved and rewritten, so git sees a delete plus an add
    old = "".join(f"old line {i}\n" for i in range(30))
    new = "".join(f"brand new content {i}\n" for i in range(30))
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "See `src/utils/helpers.py`.\n",
                               "src/utils/helpers.py": old}),
        _c("02", "move", delete=["src/utils/helpers.py"], files={"lib/helpers.py": new}),
    ])
    cand = _one(repo)
    assert _shape(cand) == ("human", "ambiguous", None, "ambiguous-rename")
    assert "lib/helpers.py" in cand["evidence"]
    assert cand["evidence_commit"] == _sha7(repo)


def test_resolve_decodes_percent_encoding(tmp_path: Path) -> None:
    files = frozenset({"reports/Gap analysis.md"})
    dirs = frozenset({"reports"})
    tok = _tok(text="reports/Gap%20analysis.md", context="link")
    assert resolve_token(tok, files, dirs, _reader({})) == "reports/Gap analysis.md"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": ("Read [the gap](reports/Gap%20analysis.md) and "
                          "[old](reports/Old%20one.md).\n"),
            "reports/Gap analysis.md": "# Gap\n",
            "reports/Old one.md": "# Old one, with enough body to be detected as a rename\n",
        }),
        _c("02", "rename", rename={"reports/Old one.md": "reports/New one.md"}),
    ])
    assert [_shape(c) for c in _cands(repo)] == [
        ("provable-replace", "unique", "reports/New%20one.md", None),
    ]


def test_deleted_file_existed_then_is_provable_delete_with_deleting_commit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "- `tools/old.sh`: a helper\n- `tools/keep.sh`: another\n",
            "tools/old.sh": "echo old\n",
            "tools/keep.sh": "echo keep\n",
        }),
        _c("02", "delete", delete=["tools/old.sh"]),
        _c("03", "later", files={"other.txt": "x\n"}),
    ])
    sha = _sha7(repo, "HEAD~1")
    cand = _one(repo)
    assert _shape(cand) == ("provable-delete", "deleted", None, None)
    assert cand["evidence_commit"] == sha
    assert cand["evidence"] == f"deleted in {sha}"
    assert cand["resolved_then"] == "tools/old.sh"


def test_line_written_after_deletion_is_summary_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "# Tool\n", "PROMPT.md": "prompt\n"}),
        _c("02", "drop prompt", delete=["PROMPT.md"],
           files={"README.md": "# Tool\n\nThere is no `PROMPT.md` file.\n"}),
    ])
    cand = _one(repo)
    assert _shape(cand) == ("summary-only", None, None, None)
    assert cand["existed_then"] is False
    assert cand["resolved_then"] is None
    assert cand["history_unavailable"] is False


def test_never_existed_path_is_summary_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "The run writes `out/report.json`.\n",
    })])
    cand = _one(repo)
    assert _shape(cand) == ("summary-only", None, None, None)
    assert cand["existed_then"] is False


def test_directory_rename_via_children(tmp_path: Path) -> None:
    body = "print('a long enough body for rename detection, file {}')\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "Code lives in `lib/`.\n",
            "lib/a.py": body.format("a"),
            "lib/b.py": body.format("b"),
        }),
        _c("02", "move", rename={"lib/a.py": "src/a.py", "lib/b.py": "src/b.py"}),
    ])
    cand = _one(repo)
    assert _shape(cand) == ("provable-replace", "unique", "src/", None)
    assert cand["evidence_commit"] == _sha7(repo)


def test_two_candidates_is_ambiguous_human(tmp_path: Path) -> None:
    body = "print('a long enough body for rename detection, file {}')\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "Code lives in `lib/`.\n",
            "lib/a.py": body.format("a"),
            "lib/b.py": body.format("b"),
        }),
        _c("02", "split", rename={"lib/a.py": "x/a.py", "lib/b.py": "y/b.py"}),
    ])
    cand = _one(repo)
    assert _shape(cand) == ("human", "ambiguous", None, "ambiguous-rename")


# -- anchors ---------------------------------------------------------------------------------


GUIDE = "# Guide\n\n## Install\n\nSteps here.\n\n## Usage\n\nUse it.\n"


def test_anchor_heading_renamed_unique(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "See [install](docs/guide.md#install).\n",
            "docs/guide.md": GUIDE,
        }),
        _c("02", "rename heading",
           files={"docs/guide.md": GUIDE.replace("## Install", "## Installation")}),
        _c("03", "later", files={"docs/guide.md": GUIDE.replace("## Install", "## Installation")
                                 + "\nMore.\n"}),
    ])
    sha = _sha7(repo, "HEAD~1")
    cand = _one(repo)
    assert cand["kind"] == "anchor"
    assert _shape(cand) == ("provable-replace", "unique", "installation", None)
    assert cand["evidence"] == f"heading renamed in {sha}"
    assert cand["evidence_commit"] == sha
    assert cand["resolved_then"] == "docs/guide.md"


def test_anchor_heading_removed_deleted(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "See [install](#install).\n\n## Install\n\nSteps.\n",
        }),
        _c("02", "drop heading", files={"README.md": "See [install](#install).\n\nSteps.\n"}),
    ])
    sha = _sha7(repo)
    cand = _one(repo)
    assert _shape(cand) == ("provable-delete", "deleted", None, None)
    assert cand["evidence"] == f"heading removed in {sha}"


DUP = "See [usage two](#usage-1).\n\n## Usage\n\nfirst\n\n## Usage\n\nsecond\n"


@pytest.mark.parametrize("after", [
    DUP.replace("## Usage\n\nfirst", "## Intro\n\nfirst"),  # first renamed
    DUP.replace("## Usage\n\nfirst\n\n", ""),  # first removed
])
def test_anchor_duplicate_suffix_is_human(tmp_path: Path, after: str) -> None:
    # R24, reviewer probe 1: #usage-1 now means a different heading's position
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": DUP}),
        _c("02", "change first", files={"README.md": after}),
    ])
    assert _shape(_one(repo)) == ("human", "ambiguous", None, "ambiguous-rename")


def test_anchor_removed_then_unrelated_heading_added_later_is_deleted(tmp_path: Path) -> None:
    # R24, reviewer probe 2: the removal and the addition are different commits
    doc = "See [install](#install).\n\n## Install\n\nx\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": doc}),
        _c("02", "drop install", files={"README.md": "See [install](#install).\n\nx\n"}),
        _c("03", "add troubleshooting",
           files={"README.md": "See [install](#install).\n\nx\n\n## Troubleshooting\n\ny\n"}),
    ])
    cand = _one(repo)
    assert _shape(cand) == ("provable-delete", "deleted", None, None)
    assert cand["evidence"] == f"heading removed in {_sha7(repo, 'HEAD~1')}"


def test_anchor_renamed_then_renamed_again_is_unique_to_head_name(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "See [install](docs/guide.md#install).\n",
                               "docs/guide.md": GUIDE}),
        _c("02", "rename", files={"docs/guide.md": GUIDE.replace("## Install", "## Setup")}),
        _c("03", "rename again",
           files={"docs/guide.md": GUIDE.replace("## Install", "## Installation")}),
    ])
    # the slug left in commit 02 for `setup`, which is gone at HEAD: not provable
    assert _shape(_one(repo)) == ("human", "ambiguous", None, "ambiguous-rename")


def test_anchor_with_missing_target_doc_is_the_path_finding(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "See [x](docs/gone.md#intro).\n",
    })])
    cands = _cands(repo)
    assert [c["kind"] for c in cands] == ["path"]


def test_anchor_target_above_repo_is_never_existed() -> None:
    tok = _tok(kind="anchor", text="intro", target_doc="../other.md", context="link")
    resolver_files = frozenset({"README.md"})
    assert resolve_token(tok, resolver_files, frozenset(), _reader({})) is None


def test_anchor_target_above_repo_classified_summary_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "See [x](../sibling/README.md#intro).\n",
    })])
    anchors = [c for c in _cands(repo) if c["kind"] == "anchor"]
    assert [_shape(c) for c in anchors] == [("summary-only", None, None, None)]


def test_heading_slugs_github_style() -> None:
    text = (
        "# Hello, World!\n\n## Hello, World!\n\n### `dd_resolve.py` usage\n\n"
        "## [Link](x.md) text\n\n```\n# not a heading\n```\n\n<a name=\"custom\"></a>\n"
        "<div id=\"box\"></div>\n"
    )
    slugs = heading_slugs(text)
    assert {"hello-world", "hello-world-1", "dd_resolvepy-usage", "link-text", "custom",
            "box"} <= slugs
    assert "not-a-heading" not in slugs
    assert slugify_heading("Über Café 2.0") == "über-café-20"


# -- scripts ---------------------------------------------------------------------------------


def test_make_target_removed(tmp_path: Path) -> None:
    make = "build:\n\techo b\n\nlint:\n\techo l\n\n.PHONY: build lint\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": "```bash\nmake build\nmake lint\n```\n",
            "Makefile": make,
        }),
        _c("02", "drop lint", files={"Makefile": "build:\n\techo b\n\n.PHONY: build\n"}),
    ])
    sha = _sha7(repo)
    cand = _one(repo)
    assert cand["kind"] == "script" and cand["text"] == "lint"
    assert _shape(cand) == ("provable-delete", "deleted", None, None)
    assert cand["evidence"] == f"removed in {sha}"
    assert cand["resolved_then"] == "Makefile"


def test_make_multi_target_and_include_resolve() -> None:
    files = frozenset({"Makefile", "mk/extra.mk", "README.md"})
    read = _reader({
        "Makefile": "VAR := x\nall test: deps\n\techo\ninclude mk/extra.mk\n",
        "mk/extra.mk": "release:\n\techo r\n",
    })
    for name in ("all", "test", "release"):
        tok = _tok(kind="script", script_tool="make", text=name)
        assert resolve_token(tok, files, frozenset({"mk"}), read) == name
    assert resolve_token(_tok(kind="script", script_tool="make", text="VAR"), files,
                         frozenset({"mk"}), read) is None


def test_npm_script_removed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "web/README.md": "Run `npm run e2e` and `npm run build`.\n",
            "web/package.json": '{"scripts": {"build": "vite build", "e2e": "playwright test"}}\n',
        }),
        _c("02", "drop e2e", files={"web/package.json": '{"scripts": {"build": "vite build"}}\n'}),
    ])
    cand = _one(repo, "web/README.md")
    assert cand["text"] == "e2e"
    assert _shape(cand) == ("provable-delete", "deleted", None, None)
    assert cand["evidence_commit"] == _sha7(repo)
    assert cand["resolved_then"] == "web/package.json"


def test_make_unfollowable_include_counts_as_every_name(tmp_path: Path) -> None:
    # R25, reviewer probe 3
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "Run `make test`.\n", "Makefile": "test:\n\tpytest\n"}),
        _c("02", "split", files={"Makefile": "include mk/*.mk\n",
                                 "mk/test.mk": "test:\n\tpytest\n"}),
    ])
    assert _cands(repo) == []


@pytest.mark.parametrize(("tool", "name", "text"), [
    ("make", "Makefile", "include $(ROOT)/rules.mk\nbuild:\n\techo\n"),
    ("make", "Makefile", "include missing.mk\nbuild:\n\techo\n"),
    ("make", "Makefile", "%.o: %.c\n\tcc\nbuild:\n\techo\n"),
    ("make", "Makefile", "$(TARGETS):\n\techo\nbuild:\n\techo\n"),
    ("just", "justfile", "import 'other.just'\nbuild:\n  echo\n"),
    ("just", "justfile", "mod tools\nbuild:\n  echo\n"),
    ("task", "Taskfile.yml", "version: '3'\nincludes:\n  docs: ./docs\ntasks:\n  build: {}\n"),
])
def test_open_manifests_lenient_at_head_strict_at_snapshot(tool: str, name: str,
                                                           text: str) -> None:
    files = frozenset({name})
    read = _reader({name: text})
    tok = _tok(kind="script", script_tool=tool, text="anything")
    assert resolve_token(tok, files, frozenset(), read) == "anything"
    assert script_source("README.md", tool, "anything", files, read, strict=True) is None
    assert script_source("README.md", tool, "build", files, read, strict=True) == name


def test_unparsable_manifest_never_proves_a_removal(tmp_path: Path) -> None:
    good = '{"scripts": {"e2e": "playwright test"}}\n'
    broken = '{"scripts": {"e2e": \n'
    head_broken = make_repo(tmp_path / "a", [
        _c("01", "one", files={"README.md": "Run `npm run e2e`.\n", "package.json": good}),
        _c("02", "break", files={"package.json": broken}),
    ])
    assert _cands(head_broken) == []  # lenient at HEAD: no finding
    then_broken = make_repo(tmp_path / "b", [
        _c("01", "one", files={"README.md": "Run `npm run e2e`.\n", "package.json": broken}),
        _c("02", "fix", files={"package.json": '{"scripts": {}}\n'}),
    ])
    assert [_shape(c) for c in _cands(then_broken)] == [("summary-only", None, None, None)]


def test_script_without_manifest_dropped(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "Run `make deploy`, `just ship` and `task release`.\n",
    })])
    assert len(_tokens(repo, "README.md")) == 3
    assert _cands(repo) == []


def test_justfile_and_taskfile_recipes_resolve() -> None:
    files = frozenset({"justfile", "Taskfile.yml"})
    read = _reader({
        "justfile": "set shell := [\"bash\"]\nbuild target:\n  echo\n@quiet:\n  echo\n",
        "Taskfile.yml": "version: '3'\ntasks:\n  release:\n    cmds: [echo]\n",
    })
    def res(tool: str, name: str) -> str | None:
        return resolve_token(_tok(kind="script", script_tool=tool, text=name), files,
                             frozenset(), read)
    assert res("just", "build") == "build"
    assert res("just", "quiet") == "quiet"
    assert res("just", "set") is None
    assert res("task", "release") == "release"
    assert res("task", "deploy") is None


# -- versions --------------------------------------------------------------------------------


def test_version_mismatch_python_and_node(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": (
            "Requires Python 3.10+.\n\nAlso fine with Python 3.11+.\n\n"
            "The web app needs Node 18+.\n\nRust 1.70+ is unrelated.\n"
        ),
        "pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3.11"\n',
        "package.json": '{"engines": {"node": ">=20.1"}}\n',
    })])
    cands = _cands(repo)
    assert [(c["text"], *_shape(c)) for c in cands] == [
        ("3.10", "provable-replace", "version-mismatch", "3.11", None),
        ("18", "provable-replace", "version-mismatch", "20", None),
    ]
    assert cands[0]["evidence"] == "manifest pyproject.toml says >=3.11"
    assert cands[1]["evidence"] == "manifest package.json says >=20.1"
    assert cands[0]["evidence_commit"] is None


def test_version_compared_at_lower_precision() -> None:
    # R29: the lower of the doc's and the manifest's precision
    files = frozenset({"pyproject.toml", "go.mod", "package.json", "README.md"})
    def res(runtime: str, floor: str, texts: dict[str, str]) -> str | None:
        tok = _tok(kind="version", text=floor, version={"runtime": runtime, "floor": floor})
        return resolve_token(tok, files, frozenset(), _reader(texts))
    py3 = {"pyproject.toml": '[project]\nrequires-python = ">=3"\n'}
    py3114 = {"pyproject.toml": '[project]\nrequires-python = ">=3.11.4"\n'}
    assert res("python", "3.10", py3) is not None
    assert res("python", "3.11", py3114) == "3.11"
    assert res("python", "3.10", py3114) is None
    go = {"go.mod": "module x\n\ngo 1.22\n"}
    assert res("go", "1.22", go) == "1.22"
    assert res("go", "1.21", go) is None
    node = {"package.json": '{"engines": {"node": ">=20.1"}}\n'}
    assert res("node", "18", node) is None
    assert res("node", "20", node) == "20"


def test_version_against_coarse_manifest_gives_no_candidate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "Requires Python 3.10+.\n",
        "pyproject.toml": '[project]\nname = "x"\nrequires-python = ">=3"\n',
    })])
    assert _cands(repo) == []


def test_version_pin_files_never_produce_a_candidate(tmp_path: Path) -> None:
    # R28, reviewer probe 5: .python-version is a pin, not a declared floor
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "Requires Python 3.10+.\n\nThe web app needs Node 18+.\n",
        "pyproject.toml": '[tool.poetry.dependencies]\npython = "^3.10"\n',
        ".python-version": "3.12.1\n",
        ".nvmrc": "v20.1.0\n",
        ".tool-versions": "python 3.12.1\nnodejs 20.1.0\n",
    })])
    assert _cands(repo) == []


def test_version_without_manifest_gives_no_candidate(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"README.md": "Needs Python 3.9+.\n"})])
    assert _cands(repo) == []


# -- trees -----------------------------------------------------------------------------------


TREE = "```\n.\n├── src/\n│   ├── old.py\n│   └── keep.py\n└── README.md\n```\n"
LABELLED = "```\nsrc/\n  old.py\n  keep.py\n  sub/\n    x.py\n```\n"


def test_tree_entry_renamed(tmp_path: Path) -> None:
    body = "print('a long enough body for rename detection')\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": TREE, "src/old.py": body, "src/keep.py": "k\n"}),
        _c("02", "rename", rename={"src/old.py": "src/new.py"}),
    ])
    cand = _one(repo)
    assert cand["kind"] == "tree" and cand["text"] == "src/old.py"
    assert _shape(cand) == ("provable-replace", "unique", "new.py", None)
    line = (repo / "README.md").read_text(encoding="utf-8").split("\n")[cand["line"] - 1]
    assert line[cand["col"] : cand["end_col"]] == "old.py"


def test_tree_entry_labelled_doc_relative(tmp_path: Path) -> None:
    body = "print('a long enough body for rename detection')\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"pkg/README.md": LABELLED, "pkg/src/old.py": body,
                               "pkg/src/keep.py": "k\n", "pkg/src/sub/x.py": "x\n"}),
        _c("02", "rename", rename={"pkg/src/old.py": "pkg/src/new.py"}),
    ])
    assert _shape(_one(repo, "pkg/README.md")) == ("provable-replace", "unique", "new.py", None)


def test_tree_entry_moved_to_other_parent_is_human(tmp_path: Path) -> None:
    body = "print('a long enough body for rename detection')\n"
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": TREE, "src/old.py": body, "src/keep.py": "k\n"}),
        _c("02", "move", rename={"src/old.py": "lib/old.py"}),
    ])
    assert _shape(_one(repo)) == ("human", "ambiguous", None, "ambiguous-rename")


def test_tree_placeholder_label_is_stripped() -> None:
    files = frozenset({"src/app.py"})
    tok = _tok(kind="tree", text="<project>/src/app.py", tree_label="<project>", context="tree")
    assert resolve_token(tok, files, frozenset({"src"}), _reader({})) == "src/app.py"


# -- routing ---------------------------------------------------------------------------------


def test_generated_and_never_edit_and_ignored_routing(tmp_path: Path) -> None:
    doc = (
        "# Tool\n\n"
        "<!-- BEGIN GENERATED -->\n- `gen.py`: generated\n<!-- END GENERATED -->\n\n"
        "<!-- drift-ignore: kept for the migration guide -->\n- `ign.py`: ignored\n\n"
        "Some text between the lists.\n\n"
        "- `free.py`: free\n\n"
        "## Rationale\n\n- `why.py`: rationale\n"
    )
    files = {name: f"print('{name} has a long enough body')\n"
             for name in ("gen.py", "ign.py", "free.py", "why.py")}
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": doc, **files}),
        _c("02", "delete", delete=list(files)),
    ])
    resolver = Resolver(repo, History(repo))
    tokens = _tokens(repo, "README.md")
    by_text = {t["text"]: resolver.classify(t) for t in tokens}
    assert by_text["ign.py"] is None
    assert [h["text"] for h in resolver.honoured] == ["ign.py"]
    assert _shape(by_text["gen.py"]) == ("human", "deleted", None, "generated-region")
    assert _shape(by_text["why.py"]) == ("human", "deleted", None, "never-edit-section")
    assert _shape(by_text["free.py"]) == ("provable-delete", "deleted", None, None)
    multi = dict(next(t for t in tokens if t["text"] == "free.py"), editable=False)
    assert _shape(resolver.classify(multi)) == ("human", "deleted", None, "prose-mention")


class _NoBlame(History):
    def line_snapshots(self, doc: str) -> dict[int, str] | None:
        return None


class _NoTree(History):
    def tree_at(self, sha: str) -> tuple[frozenset[str], frozenset[str]] | None:
        return super().tree_at(sha) if sha == "HEAD" else None


def test_no_history_means_no_edit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "- `old.py`: x\n", "old.py": "print('x')\n"}),
        _c("02", "delete", delete=["old.py"]),
    ])
    assert _shape(_one(repo)) == ("provable-delete", "deleted", None, None)
    for history in (_NoBlame(repo), _NoTree(repo)):
        resolver = Resolver(repo, history)
        cands = [c for t in _tokens(repo, "README.md") if (c := resolver.classify(t))]
        assert [_shape(c) for c in cands] == [("summary-only", None, None, None)]
        assert cands[0]["history_unavailable"] is True
        assert cands[0]["existed_then"] is False
        assert resolver.history_unavailable is True


def test_ignored_token_never_yields_a_candidate(tmp_path: Path) -> None:
    # R29, reviewer probe 7: ignored and never existed, and ignored without history
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "<!-- drift-ignore: example -->\nSee `nope/missing.py`.\n",
    })])
    tokens = _tokens(repo, "README.md")
    assert [t["ignored"] for t in tokens] == ["example"]
    for history in (History(repo), _NoBlame(repo)):
        resolver = Resolver(repo, history)
        assert resolver.classify(tokens[0]) is None
        assert resolver.history_unavailable is False
        assert [h["text"] for h in resolver.honoured] == ["nope/missing.py"]


# -- run and main ----------------------------------------------------------------------------


def test_run_writes_sorted_candidates_and_history_flag(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "`b.py` and `a.py`\n", "b.py": "print('b')\n"}),
        _c("02", "delete", delete=["b.py"]),
    ])
    workdir = tmp_path / "work"
    tokens = {"README.md": _tokens(repo, "README.md")}
    # a doc that is not committed has no blame: history unavailable, never an edit
    tokens["NOTES.md"] = extract_doc("NOTES.md", "`gone.py`\n", NEVER)[0]
    write_json(workdir / "inventory.json", {"docs": ["NOTES.md", "README.md"], "files": [],
                                            "excluded": [], "never_edit_re": DEFAULT_NEVER_EDIT})
    write_json(workdir / "tokens.json", {"docs": tokens, "markers": [], "skipped": []})
    assert main([str(repo), "--workdir", str(workdir)]) == EXIT_OK
    out = read_json(workdir / "candidates.json")
    assert out == run(repo, workdir)
    assert out["history_unavailable"] is True
    assert [(c["doc"], c["text"], c["class"]) for c in out["candidates"]] == [
        ("NOTES.md", "gone.py", "summary-only"),
        ("README.md", "b.py", "provable-delete"),
        ("README.md", "a.py", "summary-only"),
    ]
    assert out["honoured"] == []


def test_main_missing_tokens_exits_5(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"README.md": "x\n"})])
    workdir = tmp_path / "work"
    write_json(workdir / "inventory.json", {"docs": [], "files": [], "excluded": [],
                                            "never_edit_re": DEFAULT_NEVER_EDIT})
    assert main([str(repo), "--workdir", str(workdir)]) == EXIT_MISSING
    assert "tokens.json" in capsys.readouterr().err
