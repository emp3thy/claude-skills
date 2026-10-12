from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from dd_anchors import run as anchors_run
from dd_changes import affected, last_run, review_ranges, run
from dd_common import EXIT_REFUSED, StepError, read_json, write_json
from dd_config import DEFAULTS
from dd_defindex import run as defindex_run
from dd_helpers import make_repo
from dd_inventory import run as inventory_run

_IDENTITY = ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.com",
             "-c", "commit.gpgsign=false")


def _c(day: str, subject: str, **kw: Any) -> dict[str, Any]:
    return {"date": f"2026-01-{day}T00:00:00Z", "subject": subject, **kw}


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *_IDENTITY, *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _rev(repo: Path, rev: str) -> str:
    return _git(repo, "rev-parse", rev)


def _commit(repo: Path, message: str, files: dict[str, str] | None = None,
            delete: tuple[str, ...] = ()) -> str:
    """Write ``files``, remove ``delete`` and commit everything; return the new HEAD."""
    for rel, text in (files or {}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    for rel in delete:
        _git(repo, "rm", "-q", "--", rel)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _rev(repo, "HEAD")


def _start(repo: Path, work: Path) -> None:
    """The start-stage outputs dd_changes reads: preflight, inventory, index, anchors."""
    write_json(work / "preflight.json", {"head": _rev(repo, "HEAD")})
    inventory_run(repo, work, {**DEFAULTS})
    defindex_run(repo, work)
    anchors_run(repo, work, {**DEFAULTS})


def _record(work: Path, head: str) -> None:
    write_json(work / "last-run.json", {"head": head, "run_id": "2026-01-01-abcd",
                                        "date": "2026-01-01", "committed": False})


def _line_of(text: str, needle: str) -> int:
    return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)


# --- last run -----------------------------------------------------------------------------

def _two_commits(tmp_path: Path) -> Path:
    return make_repo(tmp_path, [_c("01", "one", files={"README.md": "# One\n"}),
                                _c("02", "two", files={"README.md": "# Two\n"})])


def test_first_run_when_no_record(tmp_path: Path) -> None:
    repo = _two_commits(tmp_path)
    work = tmp_path / "work"
    assert last_run(repo, work, None, False) == {
        "mode": "first", "sha": None, "source": None, "scope": "first"}
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, False)
    assert read_json(work / "changes.json") == result
    assert result["mode"] == "first"
    assert result["last_run"] is None
    assert result["last_run_source"] is None
    assert result["scope"] == "first"
    assert result["changed_files"] == []
    assert result["hunks"] == {}
    assert result["affected"] == {}
    assert result["review"] == {"README.md": [[1, 1]]}


def test_later_run_from_drift_base_commit(tmp_path: Path) -> None:
    repo = _two_commits(tmp_path)
    base = _rev(repo, "HEAD~1")
    # an abbreviated sha in the trailer still records the full one
    _commit(repo, f"docs(drift): fix\n\nDrift-Base: {base[:7]}", {"README.md": "# Three\n"})
    _commit(repo, "more work", {"README.md": "# Four\n"})
    work = tmp_path / "work"
    assert last_run(repo, work, None, False) == {
        "mode": "later", "sha": base, "source": "commit", "scope": f"since {base}"}


def test_later_run_from_local_record_when_newer(tmp_path: Path) -> None:
    repo = _two_commits(tmp_path)
    base = _rev(repo, "HEAD")
    _commit(repo, f"docs(drift): fix\n\nDrift-Base: {base}", {"README.md": "# Three\n"})
    newer =_commit(repo, "later work", {"README.md": "# Four\n"})
    _commit(repo, "latest work", {"README.md": "# Five\n"})
    work = tmp_path / "work"
    _record(work, newer)
    assert last_run(repo, work, None, False) == {
        "mode": "later", "sha": newer, "source": "record", "scope": f"since {newer}"}
    # an older record loses to the newer Drift-Base sha
    _record(work, _rev(repo, "HEAD~4"))
    assert last_run(repo, work, None, False)["source"] == "commit"


def test_last_run_ignores_non_ancestor(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, [
        _c("01", "one", files={"README.md": "# One\n"}),
        _c("02", "side work", branch="side", files={"README.md": "# Side\n"}),
        _c("03", "main work", branch="main", files={"README.md": "# Main\n"}),
    ])
    work = tmp_path / "work"
    side = _rev(repo, "side")
    _record(work, side)
    assert not _git(repo, "branch", "--contains", side, "main")
    assert last_run(repo, work, None, False)["mode"] == "first"
    # a Drift-Base sha that is not an ancestor of HEAD does not count either
    _commit(repo, f"docs(drift): fix\n\nDrift-Base: {side}", {"README.md": "# Fix\n"})
    assert last_run(repo, work, None, False)["mode"] == "first"
    first = _rev(repo, "HEAD~2")
    _commit(repo, f"docs(drift): fix again\n\nDrift-Base: {first}", {"README.md": "# Again\n"})
    assert last_run(repo, work, None, False) == {
        "mode": "later", "sha": first, "source": "commit", "scope": f"since {first}"}
    # a newer Drift-Base naming a sha off HEAD's history falls back to the older one
    _commit(repo, f"docs(drift): stray\n\nDrift-Base: {side}", {"README.md": "# Stray\n"})
    assert last_run(repo, work, None, False)["sha"] == first


def test_base_overrides_records(tmp_path: Path) -> None:
    repo = _two_commits(tmp_path)
    first = _rev(repo, "HEAD~1")
    _commit(repo, f"docs(drift): fix\n\nDrift-Base: {first}", {"README.md": "# Three\n"})
    work = tmp_path / "work"
    _record(work, _rev(repo, "HEAD"))
    assert last_run(repo, work, "HEAD~1", False) == {
        "mode": "later", "sha": _rev(repo, "HEAD~1"), "source": "base",
        "scope": "base HEAD~1"}
    with pytest.raises(StepError) as raised:
        last_run(repo, work, "no-such-ref", False)
    assert raised.value.code == EXIT_REFUSED
    assert str(raised.value) == "--base no-such-ref is not a commit in this repository"


def test_full_forces_first(tmp_path: Path) -> None:
    repo = _two_commits(tmp_path)
    first = _rev(repo, "HEAD~1")
    _commit(repo, f"docs(drift): fix\n\nDrift-Base: {first}", {"README.md": "# Three\n"})
    work = tmp_path / "work"
    _record(work, _rev(repo, "HEAD"))
    full = {"mode": "first", "sha": None, "source": None, "scope": "full"}
    assert last_run(repo, work, None, True) == full
    assert last_run(repo, work, "HEAD~1", True) == full
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, True)
    assert (result["mode"], result["scope"], result["last_run"]) == ("first", "full", None)
    assert result["review"] == {"README.md": [[1, 1]]}


# --- affected docs ------------------------------------------------------------------------

STORE = '''\
"""Item storage."""


def save_item(item):
    """Save one item."""
    data = dict(item)
    data["saved"] = True
    return data


def load_item(key):
    """Load one item."""
    return {"key": key}
'''

DOC_A = "# Saving\n\nCall `save_item` to persist an item.\n"
DOC_B = "# Loading\n\nCall `load_item` to read an item back.\n"


def _later(tmp_path: Path, files: dict[str, str]) -> tuple[Path, Path, str]:
    """A repo whose first commit holds ``files``, recorded as the last run."""
    repo = make_repo(tmp_path, [_c("01", "init", files=files)])
    work = tmp_path / "work"
    head = _rev(repo, "HEAD")
    _record(work, head)
    return repo, work, head


def test_affected_by_change_range_overlap(tmp_path: Path) -> None:
    repo, work, base = _later(tmp_path, {"svc/store.py": STORE, "docs/a.md": DOC_A,
                                         "docs/b.md": DOC_B})
    _commit(repo, "save sets a flag", {"svc/store.py": STORE.replace("True", "1")})
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, False)
    assert (result["mode"], result["last_run"], result["last_run_source"]) == (
        "later", base, "record")
    assert result["scope"] == f"since {base}"
    assert result["changed_files"] == ["svc/store.py"]
    changed = _line_of(STORE, '"saved"')
    [hunk] = result["hunks"]["svc/store.py"]
    assert (hunk["new_start"], hunk["new_end"]) == (changed, changed)
    assert result["affected"] == {"docs/a.md": {
        "anchor_reasons": [{"ref": "save_item", "line": 3, "file": "svc/store.py",
                            "hunk": [changed, changed]}],
        "missing": [], "doc_changed": False, "sections": []}}
    assert result["review"] == {"docs/a.md": [[3, 3]]}


def test_pure_deletion_touches_its_new_start() -> None:
    anchor = {"doc": "d.md", "line": 2, "ref": "fn_x", "file": "m.py", "start": 5, "end": 9,
              "kind": "function", "change_ranges": [[5, 9]], "reading": [5, 9]}
    inside = {"file": "m.py", "old_start": 6, "old_end": 7, "new_start": 5, "new_end": 4,
              "text": "-a\n-b\n"}
    after = {"file": "m.py", "old_start": 11, "old_end": 11, "new_start": 10, "new_end": 9,
             "text": "-c\n"}
    found = affected([anchor], [], {}, {"m.py": [inside, after]}, set(), {"d.md": "x\n"})
    assert found["d.md"]["anchor_reasons"] == [
        {"ref": "fn_x", "line": 2, "file": "m.py", "hunk": [5, 4]}]


def _big_class() -> str:
    methods = "".join(f"    def method_{i}(self):\n        return {i}\n\n" for i in range(30))
    return f'class BigStore:\n    """Stores things."""\n\n{methods}'


def test_not_affected_by_change_inside_large_class_body(tmp_path: Path) -> None:
    source = _big_class()
    repo, work, _ = _later(tmp_path, {"svc/big.py": source,
                                      "docs/big.md": "# Big\n\nUse `BigStore` here.\n"})
    _commit(repo, "change a method body",
            {"svc/big.py": source.replace("return 17", "return 1700")})
    _start(repo, work)
    [anchor] = [a for a in read_json(work / "anchors.json")["anchors"]
                if a["ref"] == "BigStore"]
    body = _line_of(source, "return 17")
    assert not any(s <= body <= e for s, e in anchor["change_ranges"])
    result = run(repo, work, {**DEFAULTS}, None, False)
    assert result["changed_files"] == ["svc/big.py"]
    assert result["affected"] == {}
    assert result["review"] == {}


def test_affected_by_reference_that_no_longer_resolves(tmp_path: Path) -> None:
    doc = "# Store\n\nCall `save_item` first.\n\nThen `purge_everything` clears it.\n"
    repo, work, _ = _later(tmp_path, {"svc/store.py": STORE,
                                      "svc/purge.py": "def purge_everything():\n    pass\n",
                                      "docs/store.md": doc})
    _commit(repo, "rename save and drop purge",
            {"svc/store.py": STORE.replace("save_item", "store_item")},
            delete=("svc/purge.py",))
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, False)
    assert result["changed_files"] == ["svc/purge.py", "svc/store.py"]
    entry = result["affected"]["docs/store.md"]
    # each carries the definition's range at the last-run commit, so units can be sized
    save = _line_of(STORE, "def save_item")
    save_end = _line_of(STORE, "return data")
    assert entry["missing"] == [
        {"ref": "save_item", "line": 3, "file": "svc/store.py", "start": save,
         "end": save_end, "reading": [save, save_end]},
        {"ref": "purge_everything", "line": 5, "file": "svc/purge.py", "start": 1, "end": 2,
         "reading": [1, 2]},
    ]
    assert entry["anchor_reasons"] == []
    assert entry["doc_changed"] is False
    assert result["review"] == {"docs/store.md": [[3, 3], [5, 5]]}


SECTIONED = """\
# Guide

Intro line.

## Alpha

Alpha text.

### Alpha one

Alpha one text.

## Beta

Beta text.
"""


def test_affected_by_doc_change_gives_changed_sections(tmp_path: Path) -> None:
    repo, work, _ = _later(tmp_path, {"docs/guide.md": SECTIONED,
                                      "docs/plain.md": "one\n\ntwo\n",
                                      "docs/same.md": "# Same\n\nStill here.\n"})
    _commit(repo, "edit docs", {
        "docs/guide.md": SECTIONED.replace("Alpha one text.", "Alpha one changed.")
                                  .replace("Beta text.", "Beta changed."),
        "docs/plain.md": "one\n\ntwo changed\n",
    })
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, False)
    alpha_one = _line_of(SECTIONED, "### Alpha one")
    beta = _line_of(SECTIONED, "## Beta")
    lines = len(SECTIONED.splitlines())
    assert result["affected"]["docs/guide.md"] == {
        "anchor_reasons": [], "missing": [], "doc_changed": True,
        "sections": [[alpha_one, beta - 1], [beta, lines]]}
    assert result["affected"]["docs/plain.md"]["sections"] == [[1, 3]]
    assert "docs/same.md" not in result["affected"]
    assert result["review"] == {"docs/guide.md": [[alpha_one, lines]],
                                "docs/plain.md": [[1, 3]]}
    # doc hunks drive sections but are not code hunks
    assert result["hunks"] == {}


def test_untouched_doc_is_not_affected(tmp_path: Path) -> None:
    repo, work, _ = _later(tmp_path, {"svc/store.py": STORE, "docs/a.md": DOC_A,
                                      "docs/b.md": DOC_B,
                                      "svc/other.py": "def unrelated_fn():\n    return 1\n"})
    _commit(repo, "unrelated change",
            {"svc/other.py": "def unrelated_fn():\n    return 2\n"})
    _start(repo, work)
    result = run(repo, work, {**DEFAULTS}, None, False)
    assert result["changed_files"] == ["svc/other.py"]
    assert list(result["hunks"]) == ["svc/other.py"]
    assert result["affected"] == {}
    assert result["review"] == {}


def test_review_ranges_merge_blocks_and_sections() -> None:
    def ref(line: int, text: str, block: list[int]) -> dict[str, Any]:
        return {"doc": "d.md", "line": line, "text": text, "norm": text, "specific": True,
                "block": block, "heading": None, "context": []}

    refs = [ref(3, "fn_a", [3, 4]), ref(10, "fn_b", [10, 12]), ref(11, "fn_c", [11, 12]),
            ref(40, "fn_d", [40, 41])]
    entry = {"anchor_reasons": [{"ref": "fn_a", "line": 3, "file": "m.py", "hunk": [1, 1]},
                                {"ref": "fn_b", "line": 10, "file": "m.py", "hunk": [1, 1]}],
             "missing": [{"ref": "fn_c", "line": 11, "file": "m.py"}],
             "doc_changed": True, "sections": [[30, 35], [12, 20]]}
    assert review_ranges("d.md", entry, refs) == [[3, 4], [10, 20], [30, 35]]
    assert review_ranges("d.md", None, refs, line_count=50) == [[1, 50]]
