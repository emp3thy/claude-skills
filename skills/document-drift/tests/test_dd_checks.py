"""Tests for dd_checks: the spec 9.1 script checks, verifier batches and edits.json."""
from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Any

import pytest
from dd_checks import Context, batches, check, context, main, run
from dd_common import read_json, write_json
from dd_config import DEFAULTS
from dd_defindex import run as defindex_run
from dd_extract import run as extract_run
from dd_helpers import make_repo
from dd_inventory import run as inventory_run

STORE = (
    '"""Store module."""\n'
    "\n"
    'MODE = "old-option"\n'
    "\n"
    "\n"
    "def put(key, value):\n"
    '    """Store a value."""\n'
    "    counter_total = 1\n"
    "    return key, value, counter_total\n"
    "\n"
    "\n"
    "class Store:\n"
    "    def purge(self):\n"
    "        return None\n"
    "\n"
    'FLAGS = ["--dry-run"]\n'
    "cfg.retry_count = 3\n"
)
OTHER = "def helper_fn():\n    return 2\n"
README = (
    "# Demo\n"
    "\n"
    "The store keeps values.\n"
    "Values must be strings.\n"
    "Call `put` to save.\n"
    "\n"
    "## Options\n"
    "\n"
    "- `old_option` sets the mode.\n"
    "- `gone_option` was removed.\n"
    "\n"
    "<!-- drift-ignore: hand-written -->\n"
    "Protected paragraph text.\n"
    "\n"
    "<!-- BEGIN GENERATED -->\n"
    "Generated line.\n"
    "<!-- END GENERATED -->\n"
    "\n"
    "## Indented\n"
    "\n"
    "- item\n"
    "    nested text one\n"
    "    nested text two\n"
    "\n"
    "## History\n"
    "\n"
    "We used to have a flag.\n"
)
GUIDE = ("# Guide\n\n" + "".join(f"guide line {n}\n" for n in range(1, 21))
         + "\n## Part two\n\nMore text.\n\n- db\n    image: postgres\n\nimage: postgres\n")
FILES = {"src/store.py": STORE, "src/other.py": OTHER, "README.md": README,
         "docs/guide.md": GUIDE}


def _config(**over: Any) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULTS)
    caps = over.pop("caps", {})
    config["caps"].update(caps)
    config.update(over)
    return config


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    tmp = tmp_path_factory.mktemp("checks")
    root = make_repo(tmp, [{"date": "2026-01-01T00:00:00Z", "subject": "init", "files": FILES}])
    work = tmp / "work"
    inventory_run(root, work, _config())
    extract_run(root, work)
    defindex_run(root, work)
    return root, work


@pytest.fixture
def ctx(repo: tuple[Path, Path]) -> Context:
    root, work = repo
    return context(root, work, _config())


def _line(doc: str, text: str) -> int:
    return FILES[doc].split("\n").index(text) + 1


def _text(doc: str, start: int, end: int) -> str:
    return "\n".join(FILES[doc].split("\n")[start - 1:end])


def _edit(eid: str, doc: str = "README.md", start: int = 3, end: int | None = None,
          old: str | None = None, new: str = "x", kind: str = "correct",
          evidence: tuple[str, ...] = ("src/store.py:6",), subject: str | None = None,
          ) -> dict[str, Any]:
    end = start if end is None else end
    return {"id": eid, "doc": doc, "start_line": start, "end_line": end,
            "old": _text(doc, start, end) if old is None else old, "new": new, "type": kind,
            "claim": f"claim {eid}", "evidence": list(evidence), "subject": subject}


def _result(edit: dict[str, Any], ctx: Context) -> tuple[str, str | None, str | None]:
    return check(edit, ctx)


# ---------------------------------------------------------------- one test per check

def test_old_mismatch_drops_edit(ctx: Context) -> None:
    assert _result(_edit("u001-e01", old="The store keeps keys."), ctx) == (
        "dropped", "old-mismatch", None)
    assert _result(_edit("u001-e02", start=40, old="beyond"), ctx) == (
        "dropped", "old-mismatch", None)
    assert _result(_edit("u001-e03", doc="NOTES.md", old="x"), ctx)[1] == "old-mismatch"
    assert _result(_edit("u001-e04"), ctx) == ("kept", None, None)


def test_old_mismatch_is_not_repaired_when_lines_differ(ctx: Context) -> None:
    start = _line("README.md", "    nested text one")
    one_line = _edit("u001-e01", start=start, end=start + 1, old="nested text one")
    assert _result(one_line, ctx) == ("dropped", "old-mismatch", None)
    assert one_line["old"] == "nested text one"
    worded = _edit("u001-e02", start=start, end=start + 1,
                   old="nested text one\nnested text 2")
    assert _result(worded, ctx) == ("dropped", "old-mismatch", None)
    assert "repaired" not in worded


def test_old_mismatch_is_not_repaired_when_lines_differ_by_one(ctx: Context) -> None:
    plain = _line("docs/guide.md", "guide line 5")
    shifted = _edit("u001-e01", doc="docs/guide.md", start=plain + 1, old="guide line 5",
                    new="guide line five")
    assert _result(shifted, ctx) == ("dropped", "old-mismatch", None)
    pair = _edit("u001-e02", doc="docs/guide.md", start=plain + 1, end=plain + 2,
                 old="guide line 5\nguide line 6", new="guide line 5\nguide line six")
    assert _result(pair, ctx) == ("dropped", "old-mismatch", None)
    indented = _line("docs/guide.md", "    image: postgres")
    flat = _line("docs/guide.md", "image: postgres")
    twin = _edit("u001-e03", doc="docs/guide.md", start=flat, old="    image: postgres",
                 new="    image: postgres:16")
    assert _result(twin, ctx) == ("dropped", "old-mismatch", None)
    assert twin["old"] == "    image: postgres"
    assert "repaired" not in twin
    reverse = _edit("u001-e04", doc="docs/guide.md", start=indented, old="image: postgres",
                    new="image: mysql")
    assert _result(reverse, ctx) == ("dropped", "old-mismatch", None)
    assert "repaired" not in reverse


def test_whitespace_repair_reindents_new(ctx: Context) -> None:
    start = _line("README.md", "    nested text one")
    edit = _edit("u001-e01", start=start, end=start + 1,
                 old="nested text one\nnested text two",
                 new="nested text 1\n  nested text 2\nnested text 3")
    assert _result(edit, ctx) == ("kept", None, None)
    assert edit["old"] == "    nested text one\n    nested text two"
    assert edit["new"] == "    nested text 1\n      nested text 2\n    nested text 3"
    assert edit["repaired"] is True


def test_protected_regions_go_to_human(ctx: Context) -> None:
    ignored = _edit("u001-e01", start=_line("README.md", "Protected paragraph text."))
    generated = _edit("u001-e02", start=_line("README.md", "Generated line."))
    history = _edit("u001-e03", start=_line("README.md", "We used to have a flag."))
    for edit in (ignored, generated, history):
        assert _result(edit, ctx) == ("human", "protected", "protected")
    clear = _edit("n001", start=_line("README.md", "Protected paragraph text."), new="",
                  kind="clear", evidence=())
    assert _result(clear, ctx) == ("kept", None, None)


def test_evidence_must_name_a_line_of_a_tracked_file(ctx: Context) -> None:
    lines = len(STORE.split("\n")) - 1
    assert _result(_edit("u001-e01", evidence=("src/missing.py:1",)), ctx) == (
        "dropped", "evidence", None)
    assert _result(_edit("u001-e02", evidence=(f"src/store.py:{lines + 1}",)), ctx) == (
        "dropped", "evidence", None)
    assert _result(_edit("u001-e03", evidence=("src/store.py",)), ctx)[1] == "evidence"
    assert _result(_edit("u001-e04", evidence=()), ctx)[1] == "evidence"
    assert _result(_edit("g001-e01", kind="add", new=_text("README.md", 3, 3) + "\nMore.",
                         evidence=()), ctx)[1] == "evidence"
    assert _result(_edit("u001-e05", evidence=(f"src/store.py:{lines}",)), ctx)[0] == "kept"
    start = _line("README.md", "- `gone_option` was removed.")
    assert _result(_edit("u001-e06", start=start, new="", kind="remove", evidence=(),
                         subject="gone_option"), ctx) == ("kept", None, None)


def test_still_in_source_drops_removal_of_a_live_name(ctx: Context) -> None:
    start = _line("README.md", "- `old_option` sets the mode.")
    live = _edit("u001-e01", start=start, new="", kind="remove", evidence=(),
                 subject="old_option")
    assert _result(live, ctx) == ("dropped", "still-in-source", None)
    method = _edit("u001-e02", start=start, new="", kind="remove", evidence=(),
                   subject="`purge()`")
    assert _result(method, ctx) == ("dropped", "still-in-source", None)
    for n, flag in enumerate(("--dry-run", "dry-run")):
        removal = _edit(f"u001-f{n}", start=start, new="", kind="remove", evidence=(),
                        subject=flag)
        assert _result(removal, ctx) == ("dropped", "still-in-source", None)
    dotted = _edit("u001-e04", start=start, new="", kind="remove", evidence=(),
                   subject="retry_count")
    assert _result(dotted, ctx) == ("dropped", "still-in-source", None)
    gone = _edit("u001-e03", start=start, new="", kind="remove", evidence=(),
                 subject="old_options")
    assert _result(gone, ctx) == ("kept", None, None)


def test_anchor_adds_name(ctx: Context) -> None:
    start = _line("README.md", "The store keeps values.")
    good = _edit("u001-e01", start=start, kind="anchor", subject="put",
                 new="The store keeps values via `put`.", evidence=("src/store.py:6",))
    assert _result(good, ctx) == ("kept", None, None)
    words = _edit("u001-e02", start=start, kind="anchor", subject="put",
                  new="The store keeps values via the call `put` every day.",
                  evidence=("src/store.py:6",))
    assert _result(words, ctx) == ("dropped", "anchor-adds-name", None)
    two = _edit("u001-e03", start=start, kind="anchor", subject="put",
                new="The store keeps values via `put` or `Store`.",
                evidence=("src/store.py:6",))
    assert _result(two, ctx) == ("dropped", "anchor-adds-name", None)
    reworded = _edit("u001-e04", start=start, kind="anchor", subject="put",
                     new="The store holds values via `put`.", evidence=("src/store.py:6",))
    assert _result(reworded, ctx) == ("dropped", "anchor-adds-name", None)
    unknown = _edit("u001-e05", start=start, kind="anchor", subject="nowhere_fn",
                    new="The store keeps values via `nowhere_fn`.",
                    evidence=("src/store.py:6",))
    assert _result(unknown, ctx) == ("dropped", "anchor-adds-name", None)
    guarantee = _line("README.md", "Values must be strings.")
    rewrites = _edit("u001-e06", start=guarantee, kind="anchor", subject="put",
                     new="Values must be strings (`put`).", evidence=("src/store.py:6",))
    assert _result(rewrites, ctx) == ("dropped", "anchor-adds-name", None)


def test_anchor_adds_name_accepts_bracketed_name(ctx: Context) -> None:
    start = _line("README.md", "The store keeps values.")
    edit = _edit("u001-e01", start=start, kind="anchor", subject="Store",
                 new="The store (`Store`) keeps values.", evidence=("src/store.py:12",))
    assert _result(edit, ctx) == ("kept", None, None)
    dotted = _edit("u001-e02", start=start, kind="anchor", subject="Store.purge",
                   new="The store keeps values [`Store.purge`].", evidence=("src/store.py:13",))
    ctx.kept.clear()
    assert _result(dotted, ctx) == ("kept", None, None)


def test_anchor_adds_name_rejects_name_resolving_elsewhere(ctx: Context) -> None:
    start = _line("README.md", "The store keeps values.")
    edit = _edit("u001-e01", start=start, kind="anchor", subject="helper_fn",
                 new="The store keeps values (`helper_fn`).", evidence=("src/store.py:6",))
    assert _result(edit, ctx) == ("dropped", "anchor-adds-name", None)


def test_guarantee_word_dropped_goes_to_human(ctx: Context) -> None:
    start = _line("README.md", "Values must be strings.")
    weakened = _edit("u001-e01", start=start, new="Values are strings.")
    assert _result(weakened, ctx) == ("human", "guarantee", "guarantee-mismatch")
    kept = _edit("u001-e02", start=start, new="Values must be bytes.")
    assert _result(kept, ctx) == ("kept", None, None)
    negated = _edit("u001-e03", start=start, new="Values MUST NOT be strings.")
    assert _result(negated, ctx) == ("human", "guarantee", "guarantee-mismatch")


def test_large_deletion_goes_to_human(ctx: Context) -> None:
    first = _line("docs/guide.md", "guide line 1")
    long = _edit("u001-e01", doc="docs/guide.md", start=first, end=first + 15, new="",
                 kind="remove", evidence=())
    assert _result(long, ctx) == ("human", "large-deletion", "large-deletion")
    heading = _line("docs/guide.md", "## Part two")
    titled = _edit("u001-e02", doc="docs/guide.md", start=heading, end=heading + 2, new="",
                   kind="remove", evidence=())
    assert _result(titled, ctx) == ("human", "large-deletion", "large-deletion")
    # an unverified removal's range holds its notice line too; spec 7.3 measures the block
    notice = _edit("n001", doc="docs/guide.md", start=first, end=first + 16, new="",
                   kind="unverified", evidence=())
    assert _result(notice, ctx) == ("human", "large-deletion", "large-deletion")
    short = _edit("u001-e03", doc="docs/guide.md", start=first, end=first + 14, new="",
                  kind="remove", evidence=())
    assert _result(short, ctx) == ("kept", None, None)


def test_unverified_removal_of_a_block_at_the_limit_is_kept(ctx: Context) -> None:
    # a notice line plus a block of exactly max_delete_lines lines: the block is measured
    first = _line("docs/guide.md", "guide line 1")
    at_limit = _edit("n001", doc="docs/guide.md", start=first, end=first + 15, new="",
                     kind="unverified", evidence=())
    assert _result(at_limit, ctx) == ("kept", None, None)


def test_large_section_goes_to_human(ctx: Context) -> None:
    start = _line("README.md", "Call `put` to save.")
    old = _text("README.md", start, start)
    added = "\n".join(f"- added {n}" for n in range(41))
    big = _edit("g001-e01", start=start, kind="add", new=f"{old}\n{added}")
    assert _result(big, ctx) == ("human", "large-section", "large-section")
    fits = _edit("g001-e02", start=start, kind="add",
                 new=old + "\n" + "\n".join(f"- added {n}" for n in range(40)))
    assert _result(fits, ctx) == ("kept", None, None)


def test_new_reference_must_exist(ctx: Context) -> None:
    start = _line("README.md", "Call `put` to save.")
    missing = _edit("u001-e01", start=start, new="Call `put` from `src/gone.py` to save.")
    assert _result(missing, ctx) == ("dropped", "new-reference", None)
    linked = _edit("u001-e02", start=start, new="Call `put` ([code](src/gone.py)) to save.")
    assert _result(linked, ctx) == ("dropped", "new-reference", None)
    unknown = _edit("u001-e03", start=start, new="Call `put_many_values` to save.")
    assert _result(unknown, ctx) == ("dropped", "new-reference", None)
    word = _edit("u001-e04", start=start, new="Call `put` and read `counter_total`.")
    assert _result(word, ctx) == ("kept", None, None)
    ctx.kept.clear()
    path = _edit("u001-e05", start=start, new="Call `put` from [store](src/store.py).")
    assert _result(path, ctx) == ("kept", None, None)


def test_overlap_goes_to_human(ctx: Context) -> None:
    first = _line("docs/guide.md", "guide line 1")
    one = _edit("u001-e01", doc="docs/guide.md", start=first, end=first + 1,
                new="guide line one\nguide line two")
    two = _edit("u001-e02", doc="docs/guide.md", start=first + 1, new="guide line two")
    other = _edit("u001-e03", doc="docs/guide.md", start=first + 2, new="guide line three")
    assert _result(one, ctx) == ("kept", None, None)
    assert _result(two, ctx) == ("human", "overlap", "overlap")
    assert _result(other, ctx) == ("kept", None, None)


# ---------------------------------------------------------------- batches

def test_batches_group_by_evidence_file_max_10() -> None:
    def edit(eid: str, evidence: list[str], doc: str = "README.md") -> dict[str, Any]:
        return {"id": eid, "doc": doc, "evidence": evidence, "source": "review",
                "status": "kept", "type": "correct" if evidence else "remove"}

    many = [edit(f"u001-e{n:02d}", [f"src/a.py:{n}", "src/b.py:1"]) for n in range(12, 0, -1)]
    kept = [*many, edit("u002-e01", ["src/b.py:3"]),
            edit("u002-e02", [], doc="docs/z.md"),
            {**edit("u003-e01", ["src/b.py:4"]), "status": "dropped"},
            {**edit("n001", []), "source": "notice"}]
    groups = batches(kept)
    assert [[e["id"] for e in b] for b in groups] == [
        ["u002-e02"],
        [f"u001-e{n:02d}" for n in range(1, 11)],
        ["u001-e11", "u001-e12"],
        ["u002-e01"],
    ]


# ---------------------------------------------------------------- run

def _plan_entry(work: Path, eid: str, role: str, doc: str | None = None) -> dict[str, Any]:
    folder = "review" if role == "review" else "gaps"
    entry: dict[str, Any] = {"id": eid, "role": role, "model": "sonnet",
                             "prompt": (work / "prompts" / f"{role}-{eid}.md").as_posix(),
                             "output": (work / folder / f"{eid}.json").as_posix()}
    if doc is not None:
        entry["doc"] = doc
    return entry


def _review(unit: str, edits: list[dict[str, Any]], **over: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"unit": unit, "claims_checked": 4, "code_claims": {"README.md": 2},
                           "unverified_blocks": [], "edits": edits, "questions": []}
    out.update(over)
    return out


def _setup(tmp_path: Path, repo: tuple[Path, Path], reviews: dict[str, dict[str, Any]],
           gaps: dict[str, tuple[str, dict[str, Any]]],
           notice_edits: list[dict[str, Any]]) -> Path:
    _, base = repo
    work = tmp_path / "work"
    shutil.copytree(base, work)
    plan = [_plan_entry(work, uid, "review") for uid in reviews]
    plan += [_plan_entry(work, gid, "gap", doc) for gid, (doc, _) in gaps.items()]
    for uid, out in reviews.items():
        write_json(work / "review" / f"{uid}.json", out)
    for gid, (_, out) in gaps.items():
        write_json(work / "gaps" / f"{gid}.json", out)
    write_json(work / "plan-docs.json", plan)
    write_json(work / "units.json", {"units": [], "unchecked": ["u009"]})
    write_json(work / "gaps.json", {
        "candidates": [], "lists": [], "gaps": [], "no_home": [], "unchecked": ["docs/z.md"],
        "targets": {"README.md": [{"name": "APP_HOST", "kind": "env", "parent": None,
                                   "file": "src/store.py", "line": 3,
                                   "gap_kind": "undocumented", "target_doc": "README.md",
                                   "target_line": 5, "reason": "most-names"}]}})
    write_json(work / "notices.json", {"decisions": [], "edits": notice_edits, "stale": [],
                                       "nominations": []})
    return work


def test_notice_edits_checked_not_batched(tmp_path: Path, repo: tuple[Path, Path]) -> None:
    root, _ = repo
    first = _line("docs/guide.md", "guide line 1")
    notice = _edit("n001", doc="docs/guide.md", start=first,
                   new="<!-- drift-unverified: 1st notice -->\nguide line 1", kind="notice",
                   evidence=())
    removal = _edit("n002", doc="docs/guide.md", start=first + 2, end=first + 18, new="",
                    kind="unverified", evidence=())
    review = _edit("u001-e01", start=_line("README.md", "Call `put` to save."),
                   new="Call `put` to store.")
    work = _setup(tmp_path, repo, {"u001": _review("u001", [review])}, {}, [notice, removal])
    result = run(root, work, _config())
    assert read_json(work / "edits.json") == result
    status = {e["id"]: (e["source"], e["status"], e["check"]) for e in result["edits"]}
    assert status == {"u001-e01": ("review", "kept", None),
                      "n001": ("notice", "kept", None),
                      "n002": ("notice", "human", "large-deletion")}
    plan = read_json(work / "plan-verify.json")
    assert [p["edits"] for p in plan] == [["u001-e01"]]
    assert result["human"] == [
        {"doc": "docs/guide.md", "line": first + 2, "kind": "large-deletion",
         "text": "claim n002 (deletes 16 lines (more than 15))", "evidence": []}]


def test_order_review_gap_notice(tmp_path: Path, repo: tuple[Path, Path]) -> None:
    root, _ = repo
    line = _line("README.md", "Call `put` to save.")
    old = _text("README.md", line, line)
    gap = _edit("g001-e01", start=line, kind="add", new=f"{old}\n- `MODE` sets the mode.",
                evidence=("src/store.py:3",))
    review_b = _edit("u002-e01", start=line, new="Call `put` to store.")
    review_a = _edit("u001-e01", start=_line("README.md", "The store keeps values."),
                     new="The store keeps keys.")
    notice = _edit("n001", start=line, new=f"<!-- drift-unverified: 1st notice -->\n{old}",
                   kind="notice", evidence=())
    work = _setup(tmp_path, repo,
                  {"u002": _review("u002", [review_b]), "u001": _review("u001", [review_a])},
                  {"g001": ("README.md", {"doc": "g001", "edits": [gap], "refusals": []})},
                  [notice])
    result = run(root, work, _config())
    assert [(e["id"], e["status"], e["check"]) for e in result["edits"]] == [
        ("u001-e01", "kept", None), ("u002-e01", "kept", None),
        ("g001-e01", "human", "overlap"), ("n001", "human", "overlap")]
    assert result["code_claims"] == {"README.md": 4}
    overlap = [h for h in result["human"] if h["kind"] == "overlap"]
    assert overlap[0]["evidence"] == ["src/store.py:3"]
    assert overlap[0]["text"].startswith("claim g001-e01 (lines ")


def test_gap_refusals_counted_or_human(tmp_path: Path, repo: tuple[Path, Path]) -> None:
    root, _ = repo
    refusals = [{"name": "APP_HOST", "kind": "target-refused", "reason": "not about hosts"},
                {"name": "APP_DEBUG", "kind": "not-user-facing", "reason": "internal"},
                {"name": "APP_PORT", "kind": "already-documented", "reason": "docs/x.md:3"}]
    work = _setup(tmp_path, repo, {},
                  {"g001": ("README.md", {"doc": "g001", "edits": [], "refusals": refusals})},
                  [])
    result = run(root, work, _config())
    assert result["refusals"] == [
        {"name": "APP_DEBUG", "kind": "not-user-facing", "reason": "internal",
         "doc": "README.md"},
        {"name": "APP_PORT", "kind": "already-documented", "reason": "docs/x.md:3",
         "doc": "README.md"}]
    assert result["human"] == [{"doc": "README.md", "line": 5, "kind": "target-refused",
                                "text": "APP_HOST", "evidence": ["not about hosts"]}]


def test_run_lists_unchecked_questions_and_unverified_batches(
        tmp_path: Path, repo: tuple[Path, Path]) -> None:
    root, _ = repo
    first = _line("docs/guide.md", "guide line 1")
    files = ("src/other.py:1", "src/store.py:1", "README.md:1")
    edits = [_edit(f"u001-e{n:02d}", doc="docs/guide.md", start=first + n,
                   new=f"guide line {n + 1}!", evidence=(files[n],))
             for n in range(3)]
    question = {"doc": "README.md", "line": 4, "kind": "guarantee-mismatch",
                "claim": "values must be strings", "code": "put takes anything",
                "evidence": ["src/store.py:6"]}
    blocks = [{"doc": "README.md", "start_line": 3, "end_line": 3, "why": "names nothing"}]
    reviews = {"u001": _review("u001", edits, questions=[question], unverified_blocks=blocks),
               "u002": _review("u002", [_edit("u002-e01", new="The store keeps keys.")])}
    work = _setup(tmp_path, repo, reviews,
                  {"g001": ("docs/guide.md", {"doc": "g001", "edits": [], "refusals": []})}, [])
    result = run(root, work, _config(caps={"verify": 2}), failed={"u002", "g001"})
    assert result["unchecked_units"] == ["u002", "u009"]
    assert result["unchecked_gap_docs"] == ["docs/guide.md", "docs/z.md"]
    assert [e["id"] for e in result["edits"]] == ["u001-e00", "u001-e01", "u001-e02"]
    assert result["questions"] == [question]
    assert result["human"] == [{"doc": "README.md", "line": 4, "kind": "guarantee-mismatch",
                                "text": "values must be strings",
                                "evidence": ["src/store.py:6"]}]
    assert result["unverified_blocks"] == blocks
    assert result["unverified_batches"] == [["u001-e01"]]
    plan = read_json(work / "plan-verify.json")
    assert [p["edits"] for p in plan] == [["u001-e02"], ["u001-e00"]]


def test_main_writes_edits_json(tmp_path: Path, repo: tuple[Path, Path],
                                capsys: pytest.CaptureFixture[str]) -> None:
    root, _ = repo
    work = _setup(tmp_path, repo, {}, {}, [])
    assert main([str(root), "--workdir", str(work)]) == 0
    assert read_json(work / "edits.json")["edits"] == []
    assert "edits.json" in capsys.readouterr().out
    (work / "notices.json").unlink()
    assert main([str(root), "--workdir", str(work)]) == 5
