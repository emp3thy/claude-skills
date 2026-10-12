from __future__ import annotations

from pathlib import Path
from typing import Any

from dd_anchors import checkability, references, resolve, run
from dd_common import read_json
from dd_config import DEFAULTS
from dd_defindex import Definition, by_norm, norm
from dd_defindex import run as defindex_run
from dd_helpers import make_repo
from dd_inventory import run as inventory_run

NO_FILES: frozenset[str] = frozenset()


def _def(name: str, file: str, start: int, end: int, kind: str,
         owners: tuple[str, ...] = ()) -> Definition:
    return Definition(name=name, norm=norm(name), file=file, start=start, end=end, kind=kind,
                      owners=list(owners), change_ranges=[[start, end]],
                      reading=[start, end])


def _resolve(doc: str, text: str, defs: list[Definition],
             files: frozenset[str] = NO_FILES,
             dirs: frozenset[str] = NO_FILES) -> tuple[list[Any], list[dict[str, Any]]]:
    return resolve(references(doc, text), by_norm(defs), files, dirs)


def test_references_from_code_spans_and_html_code_tags() -> None:
    text = ("# Guide\n"
            "\n"
            "## Storage\n"
            "\n"
            "Call `svc.store.save(path)` and then <code>load_all</code> to read.\n"
            "\n"
            "- the `limit` flag, see <CODE class=\"x\">--max-items</CODE>\n")
    refs = references("docs/guide.md", text)
    assert [(r["line"], r["text"]) for r in refs] == [
        (5, "svc.store.save"), (5, "load_all"), (7, "limit"), (7, "--max-items")]
    save, load, limit, flag = refs
    assert save == {"doc": "docs/guide.md", "line": 5, "text": "svc.store.save",
                    "norm": "svc_store_save", "specific": True, "block": [5, 5],
                    "heading": "Storage", "context": ["load_all"]}
    assert load["context"] == ["svc_store_save"]
    assert limit["specific"] is False and limit["block"] == [7, 7]
    assert limit["context"] == ["--max-items"]
    assert flag["specific"] is True and flag["norm"] == "--max-items"


def test_references_skip_fences_and_short_words() -> None:
    text = ("Intro `ab` and `x` and `1.2.3` and `a/b` and `--v` and `run_all now`.\n"
            "\n"
            "```\n"
            "`hidden_name` <code>fenced_name</code>\n"
            "```\n"
            "\n"
            "    <code>indented_name</code>\n"
            "\n"
            "Literal `<code>quoted_name</code>` stays one span.\n")
    refs = references("README.md", text)
    # the code span holding literal <code> text is one reference, not two
    assert [r["text"] for r in refs] == ["a/b", "--v", "run_all", "<code>quoted_name</code>"]
    assert refs[0]["heading"] is None


def test_specific_resolves_to_best_rank() -> None:
    defs = [_def("memory.retrieve", "svc/server.py", 10, 20, "reg"),
            _def("memory.retrieve", "svc/client.py", 5, 5, "literal")]
    anchors, unanchored = _resolve("README.md", "Use `memory.retrieve` to read.\n", defs)
    assert unanchored == []
    assert anchors == [{"doc": "README.md", "line": 1, "ref": "memory.retrieve",
                        "file": "svc/server.py", "start": 10, "end": 20, "kind": "reg",
                        "change_ranges": [[10, 20]], "reading": [10, 20]}]


def test_dotted_name_falls_back_to_last_segment() -> None:
    defs = [_def("save_all", "svc/store.py", 3, 9, "function")]
    anchors, unanchored = _resolve("README.md", "Call `store.save_all`.\n", defs)
    assert [(a["ref"], a["file"]) for a in anchors] == [("store.save_all", "svc/store.py")]
    assert unanchored == []


def test_specific_over_ten_definitions_is_ambiguous() -> None:
    ten = [_def("handle_it", f"svc/m{i:02d}.py", 1, 4, "function") for i in range(10)]
    anchors, unanchored = _resolve("README.md", "See `handle_it`.\n", ten)
    assert len(anchors) == 10 and unanchored == []
    eleven = [*ten, _def("handle_it", "svc/m10.py", 1, 4, "function")]
    anchors, unanchored = _resolve("README.md", "See `handle_it`.\n", eleven)
    assert anchors == []
    assert unanchored == [{"doc": "README.md", "line": 1, "ref": "handle_it",
                           "reason": "ambiguous"}]


def test_bare_resolves_through_block_context() -> None:
    text = ("## memory.retrieve\n"
            "\n"
            "| Parameter | Meaning |\n"
            "|---|---|\n"
            "| `query` | what to look for |\n")
    defs = [_def("query", "svc/server.py", 10, 20, "literal", ("memory_retrieve",)),
            _def("query", "svc/server.py", 30, 40, "literal", ("memory_observe",))]
    refs = references("docs/tools.md", text)
    assert refs[0]["context"] == ["memory_retrieve"]
    anchors, unanchored = resolve(refs, by_norm(defs), NO_FILES, NO_FILES)
    assert [(a["ref"], a["start"], a["end"]) for a in anchors] == [("query", 10, 20)]
    assert unanchored == []


def test_bare_without_context_is_unanchored() -> None:
    defs = [_def("query", "svc/server.py", 10, 20, "literal", ("memory_retrieve",))]
    anchors, unanchored = _resolve("README.md", "Pass a `query`.\n", defs)
    assert anchors == []
    assert unanchored == [{"doc": "README.md", "line": 1, "ref": "query",
                           "reason": "ambiguous"}]
    four = [_def("query", f"svc/s{i}.py", 1, 2, "literal", ("memory_retrieve",))
            for i in range(4)]
    anchors, unanchored = _resolve("README.md", "## memory.retrieve\n\nPass a `query`.\n",
                                   four)
    assert anchors == []
    assert [u["reason"] for u in unanchored] == ["ambiguous"]


def test_unknown_name_is_unanchored_unknown() -> None:
    defs = [_def("other_name", "svc/a.py", 1, 2, "function")]
    anchors, unanchored = _resolve("README.md", "Run `SELECT` then `frobnicate`.\n", defs)
    assert anchors == []
    assert unanchored == [
        {"doc": "README.md", "line": 1, "ref": "SELECT", "reason": "unknown"},
        {"doc": "README.md", "line": 1, "ref": "frobnicate", "reason": "unknown"}]


def test_existing_path_is_not_an_anchor() -> None:
    defs = [_def("app.py", "src/app.py", 1, 1, "file"),
            _def("helpers.py", "src/helpers.py", 1, 1, "file")]
    files = frozenset({"src/app.py", "src/helpers.py", "docs/guide.md"})
    dirs = frozenset({"src", "docs"})
    text = "Edit `src/app.py` or `../src/helpers.py`; `helpers.py` is a file name.\n"
    anchors, unanchored = _resolve("docs/guide.md", text, defs, files, dirs)
    assert unanchored == [
        {"doc": "docs/guide.md", "line": 1, "ref": "src/app.py", "reason": "path"},
        {"doc": "docs/guide.md", "line": 1, "ref": "../src/helpers.py", "reason": "path"}]
    assert [(a["ref"], a["file"]) for a in anchors] == [("helpers.py", "src/helpers.py")]


def test_checkability_statuses() -> None:
    defs = [_def(f"func_{i:02d}", "svc/a.py", i + 1, i + 1, "function") for i in range(12)]
    texts = {
        "none.md": "# None\n\nSome prose.\n\nCalls `missing_one`.\n",
        "two.md": "# Two\n\n- `func_00`\n- `func_01`\n- plain item\n",
        "most.md": "# Most\n\n" + "".join(f"`func_{i:02d}` " for i in range(10))
                   + "`gone_a` `gone_b`\n\n| a | b |\n|---|---|\n| x | y |\n",
        "thin.md": "# Thin\n\n" + "".join(f"`func_{i:02d}` " for i in range(3))
                   + "".join(f"`gone_{i:02d}` " for i in range(10)) + "\n",
    }
    docs = sorted(texts)
    refs = [r for doc in docs for r in references(doc, texts[doc])]
    anchors, _ = resolve(refs, by_norm(defs), NO_FILES, NO_FILES)
    result = checkability(docs, texts, refs, anchors, {**DEFAULTS})
    assert result["none.md"] == {"references": 1, "anchored": 0, "rate": 0.0, "blocks": 2,
                                 "blocks_noref": 1, "status": "unverifiable"}
    assert result["two.md"] == {"references": 2, "anchored": 2, "rate": 1.0, "blocks": 3,
                                "blocks_noref": 1, "status": "weak"}
    assert result["most.md"] == {"references": 12, "anchored": 10, "rate": 0.8333,
                                 "blocks": 3, "blocks_noref": 2, "status": "ok"}
    assert result["thin.md"]["status"] == "weak"
    assert result["thin.md"]["rate"] == 0.2308
    assert checkability(["empty.md"], {"empty.md": ""}, [], [], {**DEFAULTS}) == {
        "empty.md": {"references": 0, "anchored": 0, "rate": 0.0, "blocks": 0,
                     "blocks_noref": 0, "status": "unverifiable"}}


SERVER = '''\
def handle_retrieve(query):
    """Find memories."""
    return query


TOOLS = [
    Tool(name="memory.retrieve", schema={"query": str}),
    Tool(name="memory.observe", schema={"query": str}),
]
'''


def test_run_writes_counts_by_reason(tmp_path: Path) -> None:
    doc = ("# Tools\n"
           "\n"
           "`handle_retrieve` and `mcp__mem__memory.retrieve` live in `svc/server.py`.\n"
           "\n"
           "Pass a `query` and a `NOT_DEFINED_ANYWHERE`.\n")
    files = {"svc/server.py": SERVER, "docs/tools.md": doc, "README.md": "# Readme\n"}
    repo = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": files}])
    work = tmp_path / "work"
    inventory_run(repo, work, {**DEFAULTS})
    defindex_run(repo, work)
    result = run(repo, work, {**DEFAULTS})
    assert read_json(work / "anchors.json") == result
    assert result["counts"] == {"references": 5, "paths": 1, "anchored": 2, "ambiguous": 1,
                                "unknown": 1}
    assert [(u["ref"], u["reason"]) for u in result["unanchored"]] == [
        ("svc/server.py", "path"), ("query", "ambiguous"),
        ("NOT_DEFINED_ANYWHERE", "unknown")]
    assert {(a["ref"], a["kind"]) for a in result["anchors"]} == {
        ("handle_retrieve", "function"), ("mcp__mem__memory.retrieve", "reg")}
    assert result["checkability"]["docs/tools.md"]["status"] == "weak"
    assert result["checkability"]["README.md"]["status"] == "unverifiable"
    assert result["skipped"] == []


def test_run_skips_unreadable_doc(tmp_path: Path) -> None:
    files = {"svc/a.py": "def alpha_beta():\n    pass\n", "README.md": "`alpha_beta`\n",
             "docs/bad.md": "# Bad\n"}
    repo = make_repo(tmp_path, [{"date": "2026-01-01T00:00:00Z", "subject": "init",
                                 "files": files}])
    work = tmp_path / "work"
    inventory_run(repo, work, {**DEFAULTS})
    defindex_run(repo, work)
    (repo / "docs" / "bad.md").write_bytes(b"# Bad \xff\xfe\n")
    result = run(repo, work, {**DEFAULTS})
    assert result["skipped"] == [{"doc": "docs/bad.md", "reason": "unreadable"}]
    assert list(result["checkability"]) == ["README.md"]
    assert result["counts"]["anchored"] == 1
