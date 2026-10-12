from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from dd_common import EXIT_MISSING, EXIT_OK, read_json, write_json
from dd_extract import extract_doc
from dd_helpers import make_repo
from dd_inventory import DEFAULT_NEVER_EDIT
from dd_manifests import script_source
from dd_resolve import Resolver, heading_slugs, main, resolve_token, run, slugify_heading

NEVER = re.compile(DEFAULT_NEVER_EDIT)


def _c(day: str, subject: str, **kw: object) -> dict[str, object]:
    return {"date": f"2026-01-{day}T00:00:00Z", "subject": subject, **kw}


def _tokens(repo: Path, doc: str) -> list[dict[str, Any]]:
    text = (repo / doc).read_bytes().decode("utf-8")
    tokens, _ = extract_doc(doc, text, NEVER)
    return tokens


def _resolved(repo: Path, doc: str = "README.md") -> list[tuple[str, str, bool]]:
    resolver = Resolver(repo)
    return [(c["kind"], c["text"], c["resolved"]) for t in _tokens(repo, doc)
            if (c := resolver.candidate(t)) is not None]


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


# -- resolution at HEAD ----------------------------------------------------------------------


def test_path_and_anchor_tokens_are_marked_resolved_at_head(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={
            "README.md": ("See `src/app.py` and `src/gone.py`.\n\n"
                          "Read [setup](docs/guide.md#setup), [old](docs/guide.md#removed) "
                          "and [lost](docs/lost.md#intro).\n\nRun `make build`.\n"),
            "docs/guide.md": "# Guide\n\n## Setup\n\nText.\n",
            "src/app.py": "x = 1\n",
            "src/gone.py": "y = 2\n",
            "Makefile": "build:\n\techo\n",
        }),
        _c("02", "delete", delete=["src/gone.py"]),
    ])
    got = _resolved(repo)
    assert ("path", "src/app.py", True) in got
    assert ("path", "src/gone.py", False) in got
    assert ("anchor", "setup", True) in got
    assert ("anchor", "removed", False) in got
    assert ("anchor", "intro", False) in got
    assert all(kind in ("path", "anchor") for kind, _, _ in got)


def test_path_present_on_disk_counts_as_resolved(tmp_path: Path) -> None:
    # R66: a once-tracked runtime artefact, now untracked and ignored, is still on disk
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "- `state.json` holds the cursor.\n",
                               "state.json": "{}\n"}),
        _c("02", "untrack", delete=["state.json"], files={".gitignore": "state.json\n"}),
    ])
    assert _resolved(repo) == [("path", "state.json", False)]
    (repo / "state.json").write_text("{}\n", encoding="utf-8")
    assert _resolved(repo) == [("path", "state.json", True)]


def test_anchor_target_above_repo_is_unresolved(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={
        "README.md": "See [x](../sibling/README.md#intro).\n",
    })])
    assert ("anchor", "intro", False) in _resolved(repo)


def test_resolution_reads_no_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dd_history

    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "See `a.py` and `b.py`.\n", "a.py": "a\n",
                               "b.py": "b\n"}),
        _c("02", "delete", delete=["b.py"]),
    ])
    seen: list[str] = []
    real = dd_history.run_git

    def spy(root: Path, args: list[str], stdin: str | None = None) -> str | None:
        seen.extend(a for a in args if a in ("blame", "log", "cat-file"))
        return real(root, args, stdin)

    monkeypatch.setattr(dd_history, "run_git", spy)
    assert _resolved(repo) == [("path", "a.py", True), ("path", "b.py", False)]
    assert seen == []


def test_run_writes_sorted_candidates(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "`b.py` and `a.py`, [top](#top)\n",
                               "b.py": "print('b')\n"}),
    ])
    workdir = tmp_path / "work"
    tokens = {"README.md": _tokens(repo, "README.md"),
              "NOTES.md": extract_doc("NOTES.md", "`gone.py`\n", NEVER)[0]}
    write_json(workdir / "inventory.json", {"docs": ["NOTES.md", "README.md"], "files": [],
                                            "excluded": [], "never_edit_re": DEFAULT_NEVER_EDIT})
    write_json(workdir / "tokens.json", {"docs": tokens, "markers": [], "skipped": []})
    assert main([str(repo), "--workdir", str(workdir)]) == EXIT_OK
    out = read_json(workdir / "candidates.json")
    assert out == run(repo, workdir)
    assert list(out) == ["candidates"]
    assert [(c["doc"], c["kind"], c["text"], c["resolved"], c["resolved_to"])
            for c in out["candidates"]] == [
        ("NOTES.md", "path", "gone.py", False, None),
        ("README.md", "path", "b.py", True, "b.py"),
        ("README.md", "path", "a.py", False, None),
        ("README.md", "anchor", "top", False, None),
    ]


def test_main_missing_tokens_exits_5(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path, [_c("01", "one", files={"README.md": "x\n"})])
    workdir = tmp_path / "work"
    write_json(workdir / "inventory.json", {"docs": [], "files": [], "excluded": [],
                                            "never_edit_re": DEFAULT_NEVER_EDIT})
    assert main([str(repo), "--workdir", str(workdir)]) == EXIT_MISSING
    assert "tokens.json" in capsys.readouterr().err


# -- resolve_token over a tree ---------------------------------------------------------------


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


def test_resolve_decodes_percent_encoding() -> None:
    files = frozenset({"reports/Gap analysis.md"})
    dirs = frozenset({"reports"})
    tok = _tok(text="reports/Gap%20analysis.md", context="link")
    assert resolve_token(tok, files, dirs, _reader({})) == "reports/Gap analysis.md"


def test_anchor_target_above_repo_never_resolves() -> None:
    tok = _tok(kind="anchor", text="intro", target_doc="../other.md", context="link")
    assert resolve_token(tok, frozenset({"README.md"}), frozenset(), _reader({})) is None


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


@pytest.mark.parametrize(("tool", "name", "text"), [
    ("make", "Makefile", "include $(ROOT)/rules.mk\nbuild:\n\techo\n"),
    ("make", "Makefile", "include missing.mk\nbuild:\n\techo\n"),
    ("make", "Makefile", "%.o: %.c\n\tcc\nbuild:\n\techo\n"),
    ("make", "Makefile", "$(TARGETS):\n\techo\nbuild:\n\techo\n"),
    ("just", "justfile", "import 'other.just'\nbuild:\n  echo\n"),
    ("just", "justfile", "mod tools\nbuild:\n  echo\n"),
    ("task", "Taskfile.yml", "version: '3'\nincludes:\n  docs: ./docs\ntasks:\n  build: {}\n"),
])
def test_open_manifests_resolve_every_name(tool: str, name: str, text: str) -> None:
    files = frozenset({name})
    read = _reader({name: text})
    tok = _tok(kind="script", script_tool=tool, text="anything")
    assert resolve_token(tok, files, frozenset(), read) == "anything"
    assert script_source("README.md", tool, "anything", files, read, strict=True) is None
    assert script_source("README.md", tool, "build", files, read, strict=True) == name


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


def test_tree_placeholder_label_is_stripped() -> None:
    files = frozenset({"src/app.py"})
    tok = _tok(kind="tree", text="<project>/src/app.py", tree_label="<project>", context="tree")
    assert resolve_token(tok, files, frozenset({"src"}), _reader({})) == "src/app.py"
