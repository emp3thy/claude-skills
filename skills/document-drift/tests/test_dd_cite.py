from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from dd_cite import check, index_names, main, run, subject_of
from dd_common import EXIT_MISSING, EXIT_OK, StepError, read_json, write_json
from dd_defindex import by_norm, norm
from dd_extract import extract_doc
from dd_inventory import DEFAULT_NEVER_EDIT

NEVER = re.compile(r"(?!)")


def _d(name: str, file: str, start: int, end: int, kind: str = "function",
       owners: Sequence[str] = ()) -> dict[str, Any]:
    return {"name": name, "norm": norm(name), "file": file, "start": start, "end": end,
            "kind": kind, "owners": list(owners), "change_ranges": [[start, end]],
            "reading": [start, end]}


def _n(name: str, kind: str, file: str, line: int) -> dict[str, Any]:
    return {"name": name, "kind": kind, "file": file, "line": line, "parent": None,
            "hidden": False}


def _defs(*defs: dict[str, Any]) -> Any:
    return by_norm(defs)


def _cite_at(line: str, text: str) -> tuple[int, int]:
    col = line.index(text)
    return col, col + len(text)


def _token(path: str, start: int, end: int, text: str) -> dict[str, Any]:
    return {"kind": "cite", "path": path, "start": start, "end": end, "text": text}


def _setup(tmp_path: Path, docs: Mapping[str, str], defs: Iterable[dict[str, Any]],
           names: Iterable[dict[str, Any]] = (), files: Mapping[str, int] | None = None,
           never: str = NEVER.pattern) -> tuple[Path, Path]:
    root, workdir = tmp_path / "repo", tmp_path / "work"
    root.mkdir(parents=True)
    for doc, text in docs.items():
        (root / doc).parent.mkdir(parents=True, exist_ok=True)
        (root / doc).write_bytes(text.encode("utf-8"))
    for path, count in (files or {}).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("x\n" * count, encoding="utf-8")
    tracked = sorted({*docs, *(files or {})})
    write_json(workdir / "inventory.json", {"docs": sorted(docs), "files": tracked,
                                            "excluded": [], "skipped": [],
                                            "never_edit_re": never})
    tokens: dict[str, Any] = {}
    markers: list[Any] = []
    for doc, text in docs.items():
        tokens[doc], doc_markers = extract_doc(doc, text, re.compile(never))
        markers += doc_markers
    write_json(workdir / "tokens.json", {"docs": tokens, "markers": markers, "skipped": []})
    write_json(workdir / "defindex.json", {"definitions": list(defs), "skipped": []})
    write_json(workdir / "patterns.json", {"names": list(names), "names_then": None,
                                           "skipped": []})
    return root, workdir


AGENT = "better_memory/services/agentcore.py"


def test_subject_is_the_nearest_name_before_then_after() -> None:
    defs = _defs(_d("promote_reflection", AGENT, 1838, 1843),
                 _d("EpisodeService", AGENT, 80, 120, "class"),
                 _d("foo", "x.py", 1, 2), _d("bar", "x.py", 5, 9))
    names = index_names([])
    line = "`promote_reflection` at `agentcore.py:1578`"
    subject = subject_of(line, *_cite_at(line, "agentcore.py:1578"), defs, names)
    assert subject is not None
    assert (subject["text"], subject["file"], subject["start"], subject["end"],
            subject["kind"], subject["count"]) == (
        "promote_reflection", AGENT, 1838, 1843, "definition", 1)
    line = "`agentcore.py:93` (EpisodeService)"
    subject = subject_of(line, *_cite_at(line, "agentcore.py:93"), defs, names)
    assert subject is not None and subject["text"] == "EpisodeService"
    line = "`foo` then `bar` in `x.py:3`"
    subject = subject_of(line, *_cite_at(line, "x.py:3"), defs, names)
    assert subject is not None and subject["text"] == "bar"
    line = "`x.py:3`" + " " * 70 + "foo"
    assert subject_of(line, *_cite_at(line, "x.py:3"), defs, names) is None


def test_bare_and_called_identifiers_resolve() -> None:
    storage = "better_memory/storage/agentcore.py"
    defs = _defs(_d("observe", storage, 80, 95),
                 _d("list_projects", storage, 200, 210, owners=["AgentCoreBackend"]))
    names = index_names([])
    line = "- `storage/agentcore.py:89` - observe() wraps the write"
    subject = subject_of(line, *_cite_at(line, "storage/agentcore.py:89"), defs, names)
    assert subject is not None
    assert (subject["text"], subject["start"], subject["end"]) == ("observe", 80, 95)
    line = "`AgentCoreBackend.list_projects()` lives at `agentcore.py:150`"
    subject = subject_of(line, *_cite_at(line, "agentcore.py:150"), defs, names)
    assert subject is not None
    assert (subject["text"], subject["start"], subject["end"]) == (
        "AgentCoreBackend.list_projects", 200, 210)


def test_plain_bare_words_are_not_subjects() -> None:
    defs = _defs(_d("line", "a.py", 10, 12))
    line = "`a.py:500` reads the line"
    assert subject_of(line, *_cite_at(line, "a.py:500"), defs, index_names([])) is None
    line = "`a.py:500` calls line() first"
    subject = subject_of(line, *_cite_at(line, "a.py:500"), defs, index_names([]))
    assert subject is not None and subject["text"] == "line"


def test_a_covering_candidate_wins_over_a_nearer_one(tmp_path: Path) -> None:
    defs = [_d("episodes", "ui/app.py", 222, 227), _d("episodes_banner", "ui/app.py", 251, 262),
            _d("episodes", "db/schema.sql", 5, 20, "sql")]
    line = "`episodes_banner` reads the `episodes` table (`app.py:251-262`)"
    subject = subject_of(line, *_cite_at(line, "app.py:251-262"), _defs(*defs),
                         index_names([]))
    assert subject is not None
    assert (subject["text"], subject["start"], subject["end"]) == ("episodes_banner", 251, 262)
    assert check(_token("app.py", 251, 262, "app.py:251-262"), subject,
                 frozenset({"ui/app.py", "db/schema.sql"}),
                 {"ui/app.py": 300, "db/schema.sql": 30}) == ("current", None)
    root, workdir = _setup(tmp_path, {"docs/a.md": line + "\n"}, defs, [],
                           {"ui/app.py": 300, "db/schema.sql": 30})
    result = run(root, workdir)
    assert result["edits"] == [] and result["hints"] == {}
    assert result["counts"]["citations"]["current"] == 1


def test_table_row_candidates_come_from_the_own_cell(tmp_path: Path) -> None:
    defs = [_d("episodes", "ui/app.py", 222, 227), _d("episodes_banner", "ui/app.py", 251, 262)]
    names = index_names([])
    # `episodes` sits in another cell than the citation and the row's name cell: no subject
    row = ("| Unclosed-episode banner | read | `episodes` | No | `app.py:251-262` calls "
           "`queries.unclosed_episode_count(conn)`. |")
    assert subject_of(row, *_cite_at(row, "app.py:251-262"), _defs(*defs), names) is None
    # a name in the citation's own cell is the subject
    row = "| Banner | `episodes` | `episodes_banner` at `app.py:240` |"
    subject = subject_of(row, *_cite_at(row, "app.py:240"), _defs(*defs), names)
    assert subject is not None and subject["text"] == "episodes_banner"
    # the row's name cell counts like the own cell (spec 2.1)
    row = "| `episodes_banner` | `episodes` | `app.py:240` |"
    subject = subject_of(row, *_cite_at(row, "app.py:240"), _defs(*defs), names)
    assert subject is not None and subject["text"] == "episodes_banner"
    # the own cell is also held to 120 characters before the citation; the name cell is not
    row = "| R4 | `episodes_banner` " + "x " * 70 + "at `app.py:240` |"
    assert subject_of(row, *_cite_at(row, "app.py:240"), _defs(*defs), names) is None
    row = "| `episodes_banner` | " + "x " * 70 + "at `app.py:240` |"
    subject = subject_of(row, *_cite_at(row, "app.py:240"), _defs(*defs), names)
    assert subject is not None and subject["text"] == "episodes_banner"
    # prose: before the citation only within 120 characters
    line = "`episodes_banner` " + "x " * 70 + "at `app.py:240`"
    assert subject_of(line, *_cite_at(line, "app.py:240"), _defs(*defs), names) is None
    doc = ("| what | tables | where |\n|---|---|---|\n"
           "| Banner | `episodes` | `app.py:240` |\n")
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, defs, [], {"ui/app.py": 300})
    result = run(root, workdir)
    assert result["edits"] == []
    assert result["counts"]["citations"]["unresolved"] == 1


def test_scanned_names_are_subjects(tmp_path: Path) -> None:
    app = "better_memory/ui/app.py"
    doc = "| route | at |\n|---|---|\n| `GET /semantic` | `app.py:487` |\n"
    root, workdir = _setup(tmp_path, {"docs/api.md": doc}, [],
                           [_n("/semantic", "route", app, 470)], {app: 600})
    names = index_names([_n("/semantic", "route", app, 470)])
    line = doc.splitlines()[2]
    subject = subject_of(line, *_cite_at(line, "app.py:487"), _defs(), names)
    assert subject is not None
    assert (subject["text"], subject["file"], subject["start"], subject["end"],
            subject["kind"]) == ("GET /semantic", app, 470, 470, "scanned")
    result = run(root, workdir)
    [edit] = result["edits"]
    assert edit["new"] == "| `GET /semantic` | `app.py:470` |"
    assert result["counts"]["citations"]["moved"] == 1


def test_literals_are_never_subjects(tmp_path: Path) -> None:
    lit = _d("memory.db", "db.py", 30, 30, "literal")
    line = "`memory.db` lives at `db.py:12`"
    assert subject_of(line, *_cite_at(line, "db.py:12"), _defs(lit), index_names([])) is None
    root, workdir = _setup(tmp_path, {"docs/a.md": line + "\n"}, [lit], [], {"db.py": 40})
    result = run(root, workdir)
    assert result["edits"] == []
    assert result["hints"] == {"docs/a.md": [
        {"line": 1, "kind": "cite-unresolved", "text": "cite unresolved: db.py:12"}]}
    assert result["counts"]["citations"]["unresolved"] == 1


_CASE_DEFS = (_d("promote_reflection", AGENT, 1838, 1843), _d("helper", "a.py", 10, 20),
              _d("helper", "a.py", 40, 50))
_FILES = frozenset({AGENT, "a.py"})
_LENGTHS = {AGENT: 2000, "a.py": 100}


@pytest.mark.parametrize(("line", "cite", "path", "start", "end", "expected"), [
    ("`promote_reflection` at `agentcore.py:1840`", "agentcore.py:1840", "agentcore.py",
     1840, 1840, ("current", None)),
    ("`promote_reflection` at `agentcore.py:1578`", "agentcore.py:1578", "agentcore.py",
     1578, 1578, ("moved", {"old_cite": "agentcore.py:1578", "new_cite": "agentcore.py:1838"})),
    ("`promote_reflection` at `agentcore.py:1578-1582`", "agentcore.py:1578-1582",
     "agentcore.py", 1578, 1582,
     ("moved", {"old_cite": "agentcore.py:1578-1582", "new_cite": "agentcore.py:1838-1843"})),
    ("[promote_reflection](agentcore.py#L1578-L1582)", "agentcore.py#L1578-L1582",
     "agentcore.py", 1578, 1582,
     ("moved", {"old_cite": "agentcore.py#L1578-L1582",
                "new_cite": "agentcore.py#L1838-L1843"})),
    ("`helper` at `a.py:45`", "a.py:45", "a.py", 45, 45,
     ("several definitions, one covers", None)),
    ("`helper` at `a.py:30`", "a.py:30", "a.py", 30, 30, ("ambiguous", None)),
], ids=["current", "moved-line", "moved-range", "moved-fragment", "one-covers", "ambiguous"])
def test_cases(line: str, cite: str, path: str, start: int, end: int,
               expected: tuple[str, Any]) -> None:
    subject = subject_of(line, *_cite_at(line, cite), _defs(*_CASE_DEFS), index_names([]))
    assert subject is not None
    assert check(_token(path, start, end, cite), subject, _FILES, _LENGTHS) == expected


def test_subject_defined_elsewhere_is_a_use_site_hint(tmp_path: Path) -> None:
    service = _d("ReflectionService", "services/reflection.py", 10, 80, "class")
    line = "`ReflectionService` is built in the app (`app.py:93-96`)"
    subject = subject_of(line, *_cite_at(line, "app.py:93-96"), _defs(service),
                         index_names([]))
    assert subject is not None and subject["count"] == 0
    assert check(_token("app.py", 93, 96, "app.py:93-96"), subject,
                 frozenset({"app.py", "services/reflection.py"}),
                 {"app.py": 200, "services/reflection.py": 90}) == ("use site", None)
    root, workdir = _setup(tmp_path, {"docs/a.md": line + "\n"}, [service], [],
                           {"app.py": 200, "services/reflection.py": 90})
    result = run(root, workdir)
    assert result["edits"] == []
    assert result["hints"] == {"docs/a.md": [
        {"line": 1, "kind": "cite-use-site",
         "text": "cite use-site: ReflectionService is defined in "
                 "services/reflection.py:10-80"}]}
    assert result["counts"]["citations"]["use_site"] == 1


def test_untracked_file_and_line_past_end_are_unresolved(tmp_path: Path) -> None:
    runner = _d("run_all", "a.py", 1, 5)
    line = "`run_all` at `a.py:999`"
    subject = subject_of(line, *_cite_at(line, "a.py:999"), _defs(runner), index_names([]))
    assert subject is not None
    files, lengths = frozenset({"a.py"}), {"a.py": 50}
    assert check(_token("a.py", 999, 999, "a.py:999"), subject, files, lengths)[0] == \
        "unresolved"
    assert check(_token("missing.py", 3, 3, "missing.py:3"), subject, files, lengths)[0] == \
        "unresolved"
    assert check(_token("a.py", 0, 0, "a.py:0"), subject, files, lengths)[0] == "unresolved"
    doc = "`run_all` at `missing.py:3`\n\n`run_all` at `a.py:999`\n"
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, [runner], [], {"a.py": 50})
    result = run(root, workdir)
    assert result["edits"] == []
    assert result["hints"]["docs/a.md"] == [
        {"line": 1, "kind": "cite-unresolved", "text": "cite unresolved: missing.py:3"},
        {"line": 3, "kind": "cite-unresolved", "text": "cite unresolved: a.py:999"}]
    assert result["counts"]["citations"]["unresolved"] == 2


def test_edit_record_shape_and_ids(tmp_path: Path) -> None:
    defs = [_d("promote_reflection", AGENT, 1838, 1843), _d("helper", "a.py", 10, 20)]
    docs = {
        "docs/b.md": "`helper` at `a.py:3`\n",
        "docs/a.md": "Intro.\n\n`promote_reflection` at `agentcore.py:1578` does it.\n\n"
                     "`helper` at `a.py:30`\n",
    }
    root, workdir = _setup(tmp_path, docs, defs, [], {AGENT: 2000, "a.py": 100})
    result = run(root, workdir)
    assert [(e["id"], e["doc"], e["start_line"]) for e in result["edits"]] == [
        ("c001", "docs/a.md", 3), ("c002", "docs/a.md", 5), ("c003", "docs/b.md", 1)]
    assert result["edits"][0] == {
        "id": "c001", "doc": "docs/a.md", "start_line": 3, "end_line": 3,
        "old": "`promote_reflection` at `agentcore.py:1578` does it.",
        "new": "`promote_reflection` at `agentcore.py:1838` does it.",
        "type": "cite", "source": "script", "status": "kept", "check": None,
        "human_kind": None, "reason": None,
        "claim": f"promote_reflection is at {AGENT}:1838-1843",
        "evidence": [f"{AGENT}:1838-1843"], "subject": "promote_reflection",
        "old_cite": "agentcore.py:1578", "new_cite": "agentcore.py:1838",
    }


def test_two_moved_citations_on_one_line_are_one_edit(tmp_path: Path) -> None:
    defs = [_d("foo", "a.py", 20, 25), _d("bar", "a.py", 30, 31)]
    line = "`foo` at `a.py:3` and `bar` at `a.py:9-10` here"
    root, workdir = _setup(tmp_path, {"docs/a.md": line + "\n"}, defs, [], {"a.py": 40})
    result = run(root, workdir)
    [edit] = result["edits"]
    assert edit["old"] == line
    assert edit["new"] == "`foo` at `a.py:20` and `bar` at `a.py:30-31` here"
    assert edit["evidence"] == ["a.py:20-25", "a.py:30-31"]
    assert edit["subject"] == "foo"
    assert edit["claim"] == "foo is at a.py:20-25"
    assert (edit["old_cite"], edit["new_cite"]) == ("a.py:3, a.py:9-10", "a.py:20, a.py:30-31")
    assert result["counts"]["citations"]["moved"] == 2


def test_ignored_and_never_edit_citations_are_skipped(tmp_path: Path) -> None:
    defs = [_d("foo", "a.py", 20, 25)]
    doc = ("# Guide\n\n<!-- drift-ignore-next-line: pinned on purpose -->\n"
           "`foo` at `a.py:3`\n\n## History\n\n`foo` at `a.py:4`\n\n## Usage\n\n"
           "`foo` at `a.py:5`\n")
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, defs, [], {"a.py": 40},
                           never=DEFAULT_NEVER_EDIT)
    result = run(root, workdir)
    assert [(e["start_line"], e["new_cite"]) for e in result["edits"]] == [(12, "a.py:20")]
    assert result["counts"]["citations"]["checked"] == 1


def test_run_writes_script_edits_with_hints_and_counts(tmp_path: Path) -> None:
    defs = [_d("foo", "a.py", 20, 25), _d("helper", "a.py", 1, 5), _d("helper", "a.py", 8, 9),
            _d("Elsewhere", "b.py", 1, 3, "class")]
    doc = ("`foo` at `a.py:21`\n\n`foo` at `a.py:3`\n\n`helper` at `a.py:30`\n\n"
           "`Elsewhere` at `a.py:2`\n\nsee `a.py:4`\n")
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, defs, [], {"a.py": 40, "b.py": 5})
    result = run(root, workdir)
    assert read_json(workdir / "script-edits.json") == result
    assert result["counts"] == {
        "citations": {"checked": 5, "current": 1, "moved": 1, "ambiguous": 1, "use_site": 1,
                      "unresolved": 1},
        "facts": {"rows_checked": 0, "corrected": 0, "not_in_scan": 0}}
    assert result["hints"] == {"docs/a.md": [
        {"line": 5, "kind": "cite-ambiguous", "text": "cite ambiguous: helper a.py:30"},
        {"line": 7, "kind": "cite-use-site",
         "text": "cite use-site: Elsewhere is defined in b.py:1-3"},
        {"line": 9, "kind": "cite-unresolved", "text": "cite unresolved: a.py:4"}]}
    assert [e["id"] for e in result["edits"]] == ["c001"]
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_OK


@pytest.mark.parametrize(("name", "step"), [("tokens.json", "dd_extract"),
                                            ("defindex.json", "dd_defindex"),
                                            ("patterns.json", "dd_patterns")])
def test_missing_inputs_raise(tmp_path: Path, name: str, step: str) -> None:
    root, workdir = _setup(tmp_path, {"docs/a.md": "x\n"}, [])
    (workdir / name).unlink()
    with pytest.raises(StepError) as info:
        run(root, workdir)
    assert info.value.code == EXIT_MISSING and step in str(info.value)
    assert main([str(root), "--workdir", str(workdir)]) == EXIT_MISSING


def test_prose_citation_with_no_path_token_is_checked(tmp_path: Path) -> None:
    defs = [_d("promote_reflection", AGENT, 1838, 1843), _d("Store", "src/store.py", 1, 9, "class")]
    doc = ("The write happens at agentcore.py:1578 in promote_reflection().\n\n"
           "- `Store` is at src/store.py:4, 7 and agentcore.py:1840-1841 (promote_reflection)\n")
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, defs, [],
                           {AGENT: 2000, "src/store.py": 9})
    result = run(root, workdir)
    [edit] = result["edits"]
    assert edit["new"] == "The write happens at agentcore.py:1838 in promote_reflection()."
    assert result["counts"]["citations"] == {"checked": 3, "current": 2, "moved": 1,
                                             "ambiguous": 0, "use_site": 0, "unresolved": 0}


def test_bare_path_matching_two_files_is_ambiguous_unless_the_subject_picks_one(
        tmp_path: Path) -> None:
    defs = [_d("foo", "a/app.py", 10, 12)]
    files = {"a/app.py": 50, "b/app.py": 50}
    line = "`foo()` is called at `app.py:40`"
    # the path names two files: the subject never picks one of them
    root, workdir = _setup(tmp_path / "far", {"docs/x.md": line + "\n"}, defs, [], files)
    result = run(root, workdir)
    assert result["edits"] == []
    assert result["hints"] == {"docs/x.md": [
        {"line": 1, "kind": "cite-ambiguous", "text": "cite ambiguous: foo app.py:40"}]}
    assert result["counts"]["citations"]["ambiguous"] == 1
    # a doc beside a/app.py resolves the path to that one file: moved
    root, workdir = _setup(tmp_path / "near", {"a/README.md": line + "\n"}, defs, [], files)
    [edit] = run(root, workdir)["edits"]
    assert (edit["old_cite"], edit["new_cite"]) == ("app.py:40", "app.py:10")
    assert edit["evidence"] == ["a/app.py:10-12"]


def test_heading_citations_are_never_rewritten(tmp_path: Path) -> None:
    defs = [_d("foo", "a.py", 20, 25)]
    doc = "# `foo` at `a.py:3`\n\n`foo` at `a.py:4`\n"
    root, workdir = _setup(tmp_path, {"docs/a.md": doc}, defs, [], {"a.py": 40})
    result = run(root, workdir)
    assert [(e["start_line"], e["new_cite"]) for e in result["edits"]] == [(3, "a.py:20")]
    assert result["hints"] == {"docs/a.md": [
        {"line": 1, "kind": "cite-unresolved", "text": "cite unresolved: a.py:3 (heading)"}]}
    assert result["counts"]["citations"] == {"checked": 2, "current": 0, "moved": 1,
                                             "ambiguous": 0, "use_site": 0, "unresolved": 1}
