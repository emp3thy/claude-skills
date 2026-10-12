"""The notice loop end to end (spec 7.3) on the ``go-cli`` fixture: three runs in one test, with
canned nominations at the first run only and the owner's own commits between runs.

1. Run 1 (a first run) nominates four paragraphs of ``docs/legacy.md`` (blocks A, B, C, D) and
   one line of the 20-item list in ``docs/usage.md`` (block E, widened to the whole list); each
   gets a 1st notice. The drift branch is merged into ``main``.
2. The owner rewrites B, names `options.go` in C and puts ``drift-ignore: prose`` above D.
3. Run 2 escalates A and E (2nd notice, ``unverified`` human entry) and clears B (block
   changed), C (now anchored) and D (drift-ignore). Merged.
4. The owner adds a malformed notice. Run 3 removes A with its notice, leaves E (more than
   ``max_delete_lines`` lines) in place as ``large-deletion``, and lists the malformed notice
   as stale without touching it.

Every run, owner commit and merge has its own pinned date, in order, so the run ids and shas
are the same on every machine.
"""
from __future__ import annotations

from pathlib import Path

from dd_commit import collect_human
from dd_common import read_json
from dd_corpus import (
    CANNED_ROOT,
    Workdir,
    drive,
    evaluate,
    git,
    merge_drift_branch,
    pinned_dates,
    prepare_fixture,
)
from dd_unverified import parse_notice

FIXTURE = "go-cli"
CANNED = CANNED_ROOT / FIXTURE
LEGACY, USAGE = "docs/legacy.md", "docs/usage.md"
RUN1, OWNER, RUN2, MALFORMED_DATE, RUN3 = (
    "2026-02-02", "2026-02-05", "2026-02-09", "2026-02-12", "2026-02-16")
OWNER_AUTHOR = "Barbara Liskov <barbara@example.com>"

# the first line of each block, as the fixture writes it
A = "Old reports listed findings in the order the files were read"
B = "The first versions wrote the report to standard error"
C = "Settings from the old configuration file still apply"
D = "A doc with no headings is treated as a single section."
E = "- A run reads every tracked markdown file."
B_REWRITTEN = ("The first versions wrote the report to standard error; it now goes to standard "
               "output, so it pipes.")
C_ANCHORED = ("Settings from the old configuration file still apply when no command line option "
              "in `options.go` overrides them.")
IGNORE = "<!-- drift-ignore: prose -->"
MALFORMED = "<!-- drift-unverified: bogus -->"


def _show(repo: Path, rev: str, doc: str) -> list[str]:
    return git(repo, "show", f"{rev}:{doc}").split("\n")


def _line(lines: list[str], start: str) -> int:
    """The 1-based number of the only line starting with ``start``."""
    found = [n for n, text in enumerate(lines, 1) if text.startswith(start)]
    assert len(found) == 1, f"{start!r} is on lines {found}"
    return found[0]


def _notice_above(lines: list[str], start: str) -> int | None:
    """The stage of the notice directly above the line starting with ``start``, or None."""
    above = _line(lines, start) - 1
    notice = parse_notice(lines[above - 1]) if above >= 1 else None
    return None if notice is None else notice["stage"]


def _head(run: Workdir) -> str:
    return str(read_json(run.path / "preflight.json")["head"])


def _actions(run: Workdir, blocks: dict[str, tuple[str, str]]) -> dict[str, str]:
    """The action of each of the run's notice decisions, keyed by the label in ``blocks``
    (label -> ``(doc, start of the block's first line)`` as of the run's starting HEAD); a
    decision on any other block fails."""
    found: dict[str, str] = {}
    for decision in read_json(run.path / "notices.json")["decisions"]:
        first = _show(run.repo, _head(run), decision["doc"])[decision["block"][0] - 1]
        label = [k for k, (doc, start) in blocks.items()
                 if doc == decision["doc"] and first.startswith(start)]
        assert len(label) == 1, f"a decision on an unexpected block: {decision}"
        found[label[0]] = str(decision["action"])
    return found


def _expect(run: Workdir, doc: str, start: str, *expect: str, notice_line: bool = False) -> None:
    """Judge ``expect`` (the corpus vocabulary) on the block starting with ``start``, or on its
    notice line, as of the run's starting HEAD."""
    line = _line(_show(run.repo, _head(run), doc), start) - (1 if notice_line else 0)
    item = {"id": start[:20], "state": 1, "doc": doc, "line": line, "expect": list(expect)}
    assert evaluate(item, run.path, 1) == [], f"{doc}:{line} {expect}"


def _owner_commit(repo: Path, date: str, subject: str,
                  changes: dict[str, list[tuple[str, str]]]) -> None:
    """Commit ``changes`` (per doc, ``(old, new)`` text replacements, each found once) on
    ``main`` as the owner on ``date``."""
    for doc, pairs in changes.items():
        path = repo / doc
        text = path.read_bytes().decode("utf-8")
        for old, new in pairs:
            assert text.count(old) == 1, f"{old!r} is not in {doc} once"
            text = text.replace(old, new)
        path.write_bytes(text.encode("utf-8"))
    with pinned_dates(date):
        git(repo, "commit", "-q", "-a", "--author", OWNER_AUTHOR, "-m", subject)


def test_notice_loop_over_three_runs(tmp_path: Path) -> None:
    repo = prepare_fixture(FIXTURE, tmp_path / FIXTURE, until_tag="state1")
    path = repo / ".document-drift"

    # -- run 1: four 1st notices in legacy.md, one over the whole 20-item list in usage.md
    run1 = Workdir(repo=repo, path=path, branch="docs/drift-run1")
    drive(run1, CANNED / "notice-run1", RUN1)
    for doc, start in ((LEGACY, A), (LEGACY, B), (LEGACY, C), (LEGACY, D), (USAGE, E)):
        _expect(run1, doc, start, "notice:1st")
    nominations = read_json(path / "notices.json")["nominations"]
    assert [n["skipped"] for n in nominations] == [None] * 5
    legacy, usage = _show(repo, run1.branch, LEGACY), _show(repo, run1.branch, USAGE)
    assert [_notice_above(legacy, s) for s in (A, B, C, D)] == [1, 1, 1, 1]
    assert _notice_above(usage, E) == 1
    list_lines = [n for n, text in enumerate(usage, 1) if text.startswith("- ")]
    assert len(list_lines) == 20 and list_lines[0] == _line(usage, E)
    merge_drift_branch(repo, run1.branch, RUN1)

    # -- between runs: the owner answers B, C and D
    _owner_commit(repo, OWNER, "docs: answer three legacy notices", {LEGACY: [
        (B + ", which made it awkward to pipe.", B_REWRITTEN),
        (C + " when no command line option overrides them.", C_ANCHORED),
        ("-->\n" + D, "-->\n" + IGNORE + "\n" + D),
    ]})
    legacy = _show(repo, "main", LEGACY)
    assert legacy[_line(legacy, D) - 2] == IGNORE  # the marker sits right above D

    # -- run 2: a later run in which only the docs changed
    run2 = Workdir(repo=repo, path=path, branch="docs/drift-run2")
    drive(run2, CANNED / "notice-run2", RUN2)
    changes = read_json(path / "changes.json")
    assert (changes["mode"], changes["changed_files"]) == ("later", [LEGACY, USAGE])
    blocks = {"A": (LEGACY, A), "B": (LEGACY, B_REWRITTEN), "C": (LEGACY, C_ANCHORED),
              "D": (LEGACY, D), "E": (USAGE, E)}
    assert _actions(run2, blocks) == {"A": "escalate", "B": "clear-changed",
                                      "C": "clear-anchored", "D": "clear-ignore",
                                      "E": "escalate"}
    for doc, start in ((LEGACY, A), (USAGE, E)):
        _expect(run2, doc, start, "notice:2nd")
        _expect(run2, doc, start, "human:unverified", notice_line=True)
    _expect(run2, LEGACY, B_REWRITTEN, "notice:cleared:changed")
    _expect(run2, LEGACY, C_ANCHORED, "notice:cleared:anchored")
    _expect(run2, LEGACY, D, "notice:cleared:ignore")
    assert [h["kind"] for h in collect_human(path)] == ["unverified", "unverified"]
    legacy, usage = _show(repo, run2.branch, LEGACY), _show(repo, run2.branch, USAGE)
    assert [_notice_above(legacy, s) for s in (A, B_REWRITTEN, C_ANCHORED, D)] == [
        2, None, None, None]
    assert legacy[_line(legacy, D) - 2] == IGNORE  # the owner's marker stays
    assert _notice_above(usage, E) == 2
    merge_drift_branch(repo, run2.branch, RUN2)

    # -- before run 3: a hand-written notice that does not match the grammar
    _owner_commit(repo, MALFORMED_DATE, "docs: a note of my own", {LEGACY: [
        (C_ANCHORED, MALFORMED + "\n" + C_ANCHORED)]})

    # -- run 3: A goes with its notice; E is too long to delete; the malformed notice stays
    run3 = Workdir(repo=repo, path=path, branch="docs/drift-run3")
    drive(run3, CANNED / "notice-run3", RUN3)
    assert _actions(run3, blocks) == {"A": "remove", "E": "remove"}
    _expect(run3, LEGACY, A, "notice:removed")
    _expect(run3, USAGE, E, "human:large-deletion", notice_line=True)
    edits = read_json(path / "edits.json")["edits"]
    large = [e for e in edits if e["doc"] == USAGE and e["type"] == "unverified"]
    assert [(e["status"], e["check"]) for e in large] == [("human", "large-deletion")]
    assert int(large[0]["end_line"]) - int(large[0]["start_line"]) + 1 > 15
    start_legacy = _show(repo, _head(run3), LEGACY)
    stale = read_json(path / "notices.json")["stale"]
    assert stale == [{"doc": LEGACY, "line": _line(start_legacy, MALFORMED),
                      "reason": "malformed"}]
    legacy, usage = _show(repo, run3.branch, LEGACY), _show(repo, run3.branch, USAGE)
    assert legacy == [text for n, text in enumerate(start_legacy, 1)
                      if n not in (_line(start_legacy, A) - 1, _line(start_legacy, A))]
    assert not [text for text in legacy if parse_notice(text) is not None]
    assert legacy[_line(legacy, C_ANCHORED) - 2] == MALFORMED  # untouched
    assert usage == _show(repo, _head(run3), USAGE)  # E and its 2nd notice stay in place
    assert _notice_above(usage, E) == 2
    assert [h["kind"] for h in collect_human(path)] == ["large-deletion"]
