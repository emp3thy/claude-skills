# tech-debt-promote as a design entry point — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `/tech-debt-promote` from a PBI-bundle emitter into a design entry point that selects one approved finding, writes `.tech-debt/evidence.md`, and seeds a brainstorming session.

**Architecture:** A new pure renderer (`evidence_doc.py`) turns one parsed `design.md` finding plus the scan's open questions into a standalone markdown document. `promote.py` loses its bundle machinery and gains two deterministic subcommands — `--list-approved` and `--select <slug>` — while `SKILL.md` drives the conversational half (the choice, the brainstorming handoff). `baseline.py` loses the bundle vouching that only made sense while bundles existed.

**Tech Stack:** Python 3.11+, pyyaml (the only dependency), pytest, ruff, mypy strict. Every script is direct-path invocable as `python scripts/<name>.py`; no package install, no `-m`.

**Spec:** `docs/superpowers/specs/2026-09-10-tech-debt-promote-brainstorm-design.md`

## Global Constraints

- All work happens in `skills/tech-debt-scan/`. Run pytest, ruff and mypy from that directory.
- Python 3.11+; pyyaml is the only runtime dependency. No new dependencies.
- Every script is direct-path invocable (`python scripts/<name>.py`); sibling imports are bare (`from design_parser import parse_design`), never packaged.
- Rendered output is **LF-only**: build with `"\n".join(parts)` and write via `write_bytes` so Windows text-mode CRLF translation never corrupts it.
- Content is ASCII-only — no em-dash — so a default-encoding `read_text` on Windows byte-matches the utf-8 bytes written.
- `ruff check`, `mypy --strict` and `pytest` must pass before every commit. Ruff preset is `E,F,I,B,UP,SIM`, line length 100.
- Tests never call an LLM. The `live` marker stays off by default.
- Branch: `feat/tech-debt-promote-brainstorm` (already created; the spec is committed on it).
- Commit style: Conventional Commits, scope `tech-debt-scan`.

---

## File Structure

| Path | Responsibility | Task |
|---|---|---|
| `scripts/evidence_doc.py` | **new** — pure renderer: finding + scan questions to markdown | 1 |
| `tests/test_evidence_doc.py` | **new** — its tests | 1 |
| `scripts/baseline.py` | drop the `bundles` parameter, the vouching guard and the `bundle` field | 2 |
| `tests/test_baseline.py` | delete 3 guard tests, amend 1, strip 25 `bundles={}` call sites | 2 |
| `scripts/promote.py` | add `list_approved` and `select`; later drop the bundle path | 3, 4 |
| `tests/test_promote.py` | new-surface tests; later drop bundle tests | 3, 4 |
| `scripts/bundle_writer.py` | **deleted** | 4 |
| `tests/test_bundle_writer.py`, `tests/golden/bundle*/` | **deleted** | 4 |
| `tests/test_e2e.py` | chain ends at `evidence.md`, not a bundle | 4 |
| `SKILL.md`, `docs/architecture.md`, `README.md` | the promote procedure and its prose | 5 |

---

### Task 1: `evidence_doc.py`, the evidence renderer

**Confidence: 95%** — a pure function over data shapes verified against the live `design.md`, `candidates.json` and `parse_design` output on 2026-09-10.

**Files:**
- Create: `skills/tech-debt-scan/scripts/evidence_doc.py`
- Test: `skills/tech-debt-scan/tests/test_evidence_doc.py`

**Interfaces:**
- Consumes: `parse_design(path)["findings"][n]` — a dict with `title`, `status`, `slug`, `severity`, `category`, `body_md`, `line`, and optionally `family`, `fingerprint`, `tier`, `priority`, `type_id`, `debt_type`, `effort`, `diff`. And `parse_design(path)["metadata"]` — the design.md frontmatter, carrying `root`, `scan_date`, `preset`.
- Produces:
  - `evidence_locations(body_md: str) -> list[tuple[str, int]]`
  - `render_evidence(finding: dict[str, Any], *, metadata: dict[str, Any], open_questions: list[dict[str, Any]], looks_bad_but_fine: list[dict[str, Any]]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evidence_doc.py`:

```python
from __future__ import annotations

from typing import Any

from evidence_doc import evidence_locations, render_evidence

BODY = """### Proof

self._control is written at agentcore.py:135 and read nowhere.

### Evidence

- `better_memory/storage/agentcore.py:135-135`

```
        self._control = control_client
```

- `better_memory/storage/factory.py:82-86`

```
        control_client = boto3.client("bedrock-agentcore-control")
```

### Remediation

Delete the parameter from the bottom up.

### Acceptance criteria

- [ ] grep for _control returns no hits.
"""


def _finding(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "AgentCoreBackend stores a control_client it never reads",
        "status": "approved",
        "slug": "agentcorebackend-stores-a-control-client-it-never-reads",
        "severity": "2",
        "category": "dead-code",
        "body_md": BODY,
        "line": 491,
        "family": "dead-code",
        "fingerprint": "4cba0399f66dd81c",
        "tier": "A",
        "type_id": "TD-09",
        "debt_type": "code",
        "effort": "S",
        "diff": "NEW",
    }
    base.update(over)
    return base


def _metadata(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "root": r"C:\Users\gethi\source\better-memory",
        "scan_date": "2026-09-09",
        "preset": "balanced",
    }
    base.update(over)
    return base


def test_evidence_locations_reads_every_cited_span() -> None:
    assert evidence_locations(BODY) == [
        ("better_memory/storage/agentcore.py", 135),
        ("better_memory/storage/factory.py", 82),
    ]


def test_header_carries_the_scan_and_classification_facts() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    lines = out.split("\n")
    assert lines[0] == "# AgentCoreBackend stores a control_client it never reads"
    assert r"Repository: C:\Users\gethi\source\better-memory" in lines
    assert "Scan: 2026-09-09 (preset balanced)" in lines
    assert "Finding: 4cba0399f66dd81c | dead-code | TD-09 | code" in lines
    assert "Tier A | severity 2 | effort S | NEW" in lines


def test_body_is_copied_verbatim() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert BODY.strip("\n") in out


def test_matching_open_questions_are_rendered_by_file() -> None:
    questions = [
        {"file": "better_memory/storage/agentcore.py", "line_start": 135,
         "question": "Is control_client retained for a planned operation?"},
        {"file": "better_memory/services/reflection.py", "line_start": 12,
         "question": "Unrelated question about another file."},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=questions, looks_bad_but_fine=[]
    )
    assert "### Open questions from the scan" in out
    assert "Is control_client retained for a planned operation?" in out
    assert "Unrelated question about another file." not in out


def test_matched_entries_are_ordered_by_line_proximity() -> None:
    questions = [
        {"file": "better_memory/storage/agentcore.py", "line_start": 900, "question": "far"},
        {"file": "better_memory/storage/agentcore.py", "line_start": 140, "question": "near"},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=questions, looks_bad_but_fine=[]
    )
    assert out.index("near") < out.index("far")


def test_looks_bad_but_fine_matches_any_evidence_file() -> None:
    entries = [
        {"file": "better_memory/storage/factory.py", "line_start": 82,
         "why": "The factory builds one client per backend by design."},
    ]
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=entries
    )
    assert "### Already ruled out" in out
    assert "The factory builds one client per backend by design." in out


def test_unmatched_sections_are_omitted_entirely() -> None:
    out = render_evidence(
        _finding(),
        metadata=_metadata(),
        open_questions=[{"file": "other.py", "line_start": 1, "question": "q"}],
        looks_bad_but_fine=[{"file": "other.py", "line_start": 1, "why": "w"}],
    )
    assert "### Open questions from the scan" not in out
    assert "### Already ruled out" not in out


def test_output_is_lf_only_and_ends_with_one_newline() -> None:
    out = render_evidence(
        _finding(), metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert "\r" not in out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_absent_optional_fields_render_a_dash() -> None:
    finding = _finding()
    for key in ("tier", "type_id", "debt_type", "effort", "diff", "family"):
        finding.pop(key)
    out = render_evidence(
        finding, metadata=_metadata(), open_questions=[], looks_bad_but_fine=[]
    )
    assert "Finding: 4cba0399f66dd81c | dead-code | - | -" in out
    assert "Tier - | severity 2 | effort - | -" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_evidence_doc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evidence_doc'`

- [ ] **Step 3: Write the renderer**

Create `scripts/evidence_doc.py`:

```python
"""Render one approved design.md finding as evidence.md, the seed for a design session.

``/tech-debt-promote`` selects a single finding and materialises it here as a
standalone document a brainstorming session reads. Everything from ``### Proof``
through ``### Acceptance criteria`` is the finding's own ``body_md``, copied
verbatim: what the verifier confirmed is what the brainstorm reads.

Two sections are added from the scan's own negative space. ``open_questions``
and ``looks_bad_but_fine`` are anchored to ``file`` and ``line_start``, never to
a fingerprint, so matching them to a finding is a heuristic: an entry matches
when its file is one of the files the finding cites, and matched entries are
ordered by distance from the finding's first cited line. Neither section is
rendered when nothing matches.

Pure: no filesystem access, no imports from the rest of the chain. Direct-path
invocable is not needed -- ``promote.py`` is the only caller.
"""
from __future__ import annotations

import re
from typing import Any, Final

# design_writer renders each evidence item as ``- `path:start-end` `` (or
# ``- `path:start` `` when the span is one line), so the location of every span
# the finding cites can be read back out of body_md without verified.json.
_EVIDENCE_LINE: Final[re.Pattern[str]] = re.compile(
    r"^- `([^`]+?):(\d+)(?:-\d+)?`\s*$", re.MULTILINE
)
_ABSENT: Final[str] = "-"
_QUESTIONS_HEADING: Final[str] = "### Open questions from the scan"
_RULED_OUT_HEADING: Final[str] = "### Already ruled out"


def evidence_locations(body_md: str) -> list[tuple[str, int]]:
    """Every ``(file, line_start)`` the finding's Evidence section cites, in order."""
    return [(match.group(1), int(match.group(2))) for match in _EVIDENCE_LINE.finditer(body_md)]


def _field(finding: dict[str, Any], key: str) -> str:
    value = finding.get(key)
    return _ABSENT if value is None or value == "" else str(value)


def _matched(
    entries: list[dict[str, Any]], files: set[str], anchor: int | None
) -> list[dict[str, Any]]:
    """``entries`` whose file the finding cites, nearest the anchor line first.

    ``sorted`` is stable, so entries equidistant from the anchor -- and every
    entry when there is no anchor -- keep their input order.
    """
    hits = [entry for entry in entries if str(entry.get("file") or "") in files]
    if anchor is None:
        return hits
    return sorted(hits, key=lambda entry: abs(int(entry.get("line_start") or 0) - anchor))


def render_evidence(
    finding: dict[str, Any],
    *,
    metadata: dict[str, Any],
    open_questions: list[dict[str, Any]],
    looks_bad_but_fine: list[dict[str, Any]],
) -> str:
    """The evidence.md text for ``finding``; LF-only, one trailing newline."""
    locations = evidence_locations(str(finding.get("body_md") or ""))
    files = {file for file, _ in locations}
    anchor = locations[0][1] if locations else None

    parts: list[str] = [
        f"# {finding.get('title') or ''}",
        "",
        f"Repository: {metadata.get('root') or _ABSENT}",
        f"Scan: {metadata.get('scan_date') or _ABSENT} "
        f"(preset {metadata.get('preset') or _ABSENT})",
        f"Finding: {_field(finding, 'fingerprint')} | {_field(finding, 'family')} "
        f"| {_field(finding, 'type_id')} | {_field(finding, 'debt_type')}",
        f"Tier {_field(finding, 'tier')} | severity {_field(finding, 'severity')} "
        f"| effort {_field(finding, 'effort')} | {_field(finding, 'diff')}",
        "",
        str(finding.get("body_md") or "").strip("\n"),
    ]

    questions = _matched(open_questions, files, anchor)
    if questions:
        parts += ["", _QUESTIONS_HEADING, "", "Ask these before proposing approaches:", ""]
        parts += [
            f"- `{entry.get('file')}:{entry.get('line_start')}` - {entry.get('question')}"
            for entry in questions
        ]

    ruled_out = _matched(looks_bad_but_fine, files, anchor)
    if ruled_out:
        parts += ["", _RULED_OUT_HEADING, "", "A scout examined these and dismissed them:", ""]
        parts += [
            f"- `{entry.get('file')}:{entry.get('line_start')}` - {entry.get('why')}"
            for entry in ruled_out
        ]

    return "\n".join(parts) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_evidence_doc.py -v`
Expected: PASS, 9 tests

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check scripts/evidence_doc.py tests/test_evidence_doc.py && python -m mypy --strict scripts/evidence_doc.py`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add scripts/evidence_doc.py tests/test_evidence_doc.py
git commit -m "feat(tech-debt-scan): render a finding as evidence.md

Pure renderer for the design-session seed: the finding's body verbatim,
plus the scan's open questions and ruled-out entries matched by file and
ordered by line proximity."
```

---

### Task 2: Remove bundle vouching from the baseline

**Confidence: 92%** — every edit site is enumerated below from a grep of the current file; the residual 8% is the 25 mechanical call-site edits in a 1352-line test file, mitigated by Step 1 listing them before any edit.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/baseline.py` (docstring `:7`; `record` signature `:366`; docstring `:374`, `:382-384`, `:406`; guard `:426-428`; entry field `:442`; entry field `:463`; CLI call `:587`)
- Modify: `skills/tech-debt-scan/scripts/promote.py:265-283` — `_write_back`'s `bundles` construction and argument
- Test: `skills/tech-debt-scan/tests/test_baseline.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `baseline.record(baseline_path, *, decisions, findings, today, preset) -> dict[str, Any]` — the `bundles` keyword is gone; entries no longer carry a `bundle` key.

- [ ] **Step 1: Enumerate the edit sites**

Run: `grep -n "bundle" scripts/baseline.py tests/test_baseline.py`
Expected: 12 hits in `baseline.py`; 47 in `test_baseline.py` — 25 `bundles={}` call sites, 2 non-empty `bundles={...}`, 3 expected-dict `"bundle": None` keys (`:49`, `:549`, `:695`), and the 4 named tests at `:563`, `:651`, `:661`, `:843`. Confirm these counts before editing; if they differ, the file has moved on and the line numbers below need re-deriving.

- [ ] **Step 2: Write the failing test for the new contract**

Add to `tests/test_baseline.py`, inside the same class as `test_first_seen_survives_a_second_record`:

```python
    def test_promoted_records_without_a_bundle(self, tmp_path: Path) -> None:
        """`promoted` now means "selected for a design session"; there is no
        bundle to vouch for, so recording one must simply work."""
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        doc = record(path, decisions=[_decision(status="promoted")], findings=[_finding()],
                     today=TODAY, preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry["status"] == "promoted"
        assert "bundle" not in entry

    def test_a_legacy_entry_carrying_a_bundle_still_reads(self, tmp_path: Path) -> None:
        """A baseline written before this change carries `bundle` on every
        entry; it is ignored on read, never an error."""
        from baseline import load_baseline, record

        path = tmp_path / ".tech-debt" / "baseline.json"
        path.parent.mkdir(parents=True)
        legacy = _baseline(**{"aaaaaaaaaaaaaaaa": _entry(
            status="promoted", bundle="chore-empty-catch-2026-04-01")})
        path.write_text(json.dumps(legacy), encoding="utf-8")

        assert load_baseline(path) is not None
        doc = record(path, decisions=[_decision(status="promoted")], findings=[_finding()],
                     today=TODAY, preset="balanced")
        assert "bundle" not in doc["findings"]["aaaaaaaaaaaaaaaa"]
```

Note: `_entry(**over)` still accepts `bundle=` via its `base.update(over)` after Step 4 removes `"bundle": None` from its defaults, so the legacy fixture above keeps working.

- [ ] **Step 3: Run them to verify they fail**

Run: `python -m pytest tests/test_baseline.py -k "without_a_bundle or legacy_entry" -v`
Expected: FAIL — `TypeError: record() missing 1 required keyword-only argument: 'bundles'`

- [ ] **Step 4: Edit `scripts/baseline.py`**

Delete the parameter from the signature:

```python
def record(
    baseline_path: Path,
    *,
    decisions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    today: str,
    preset: str,
) -> dict[str, Any]:
```

Delete the guard (currently `:426-428`) so the decision loop reads:

```python
        finding = by_fp.get(fp, {})
        previous = _entry_for(finding, fp, out, by_fp)
        fields = _entry_fields(
```

Delete `"bundle": bundle,` from the decision loop's entry dict (`:442`) and `"bundle": previous.get("bundle"),` from the findings loop's entry dict (`:463`).

Delete `bundles={},` from the module's own CLI call site (`:587`).

Update the module docstring: `:7` becomes "and writes each finding's status, reason and expiry back, so a"; delete the `bundles` sentences at `:374` and `:382-384`; drop `bundle` from the `:406` field list.

- [ ] **Step 5: Edit `scripts/promote.py`'s `_write_back`**

Delete the whole `bundles` construction block and the argument, leaving:

```python
    prior = baseline.load_baseline(baseline_path)

    baseline.record(
        baseline_path,
        decisions=decisions,
        findings=findings,
        today=today,
        preset=preset,
    )
```

`prior` and `prior_findings` become unused here — delete both lines and the now-unused `out_root` parameter's only use. Leave `out_root` on the signature for now; Task 4 removes it with the rest of the bundle path. Update `_write_back`'s docstring to drop its Ruling 2 and Ruling 3 bundle paragraphs.

- [ ] **Step 6: Mechanical test edits**

In `tests/test_baseline.py`:
- Delete `"bundle": None,` from `_entry()`'s defaults (`:49`) and from the two expected-dict literals (`:549`, `:695`).
- Delete `bundles={}` / `bundles={...}` from all 25 call sites (`sed -i 's/, bundles={}//; s/bundles={},//'` will not be safe across line breaks — do it by hand or verify the diff).
- Delete `test_a_promoted_finding_records_its_bundle`, `test_promoted_with_no_bundle_and_no_history_raises` and `test_promoted_keeps_a_previously_recorded_bundle` outright.
- Rename `test_a_decided_finding_migrates_and_keeps_its_bundle` to `test_a_decided_finding_migrates_and_keeps_its_decision`; drop `bundle="chore-empty-catch-2026-01-05"` from its `_entry(...)` fixture and the `assert entry["bundle"] == ...` line; keep every migration assertion.

- [ ] **Step 7: Run the full baseline and promote suites**

Run: `python -m pytest tests/test_baseline.py tests/test_promote.py -v`
Expected: PASS. `test_baseline.py` reports 76 tests (77 − 3 deleted + 2 added).

- [ ] **Step 8: Run the gates**

Run: `python -m ruff check scripts tests && python -m mypy --strict scripts`
Expected: both clean

- [ ] **Step 9: Commit**

```bash
git add scripts/baseline.py scripts/promote.py tests/test_baseline.py
git commit -m "refactor(tech-debt-scan): drop bundle vouching from the baseline

promoted now means selected for a design session, so record() no longer
takes a bundles map, no longer refuses a promoted decision without one,
and entries no longer carry a bundle field. Legacy entries carrying it
still read."
```

---

### Task 3: `--list-approved` and `--select` on promote

**Confidence: 93%** — signatures and data shapes verified against the live `design.md`, `candidates.json` and `mark_promoted`. The new surface lands alongside the bundle path, so the suite stays green; Task 4 removes the old half.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/promote.py`
- Test: `skills/tech-debt-scan/tests/test_promote.py`

**Interfaces:**
- Consumes: `evidence_doc.render_evidence(...)` from Task 1; `baseline.record(...)` from Task 2.
- Produces:
  - `SelectionError(Exception)`
  - `list_approved(design_path: Path) -> list[dict[str, Any]]` — rows of `slug`, `title`, `family`, `severity` (int), `effort`, `primary_file`, `fingerprint`
  - `select(design_path: Path, slug: str) -> Path` — writes `<design dir>/evidence.md`, marks the finding `promoted`, returns the written path

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_promote.py`:

```python
# design-worked-example.md is the v2 golden: two findings, both `status: pending`,
# both carrying fingerprints. Document order is severity 4 then severity 5.
V2_GOLDEN = Path(__file__).parent / "golden" / "design-worked-example.md"


def _v2_design(tmp_path: Path, *, approve: int = 1) -> Path:
    src = tmp_path / "design.md"
    src.write_text(
        V2_GOLDEN.read_text(encoding="utf-8").replace(
            "status: pending", "status: approved", approve
        ),
        encoding="utf-8",
    )
    return src


def test_list_approved_returns_only_approved_rows(tmp_path: Path) -> None:
    from promote import list_approved

    rows = list_approved(_v2_design(tmp_path, approve=2))
    assert len(rows) == 2
    assert set(rows[0]) == {
        "slug", "title", "family", "severity", "effort", "primary_file", "fingerprint",
    }
    assert all(isinstance(row["severity"], int) for row in rows)


def test_list_approved_is_empty_when_nothing_is_approved(tmp_path: Path) -> None:
    from promote import list_approved

    src = tmp_path / "design.md"
    src.write_text(V2_GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    assert list_approved(src) == []


def test_list_approved_orders_by_severity_descending(tmp_path: Path) -> None:
    """The golden's severity-4 finding precedes its severity-5 one in the
    document, so a passing assertion here proves the sort, not the file order."""
    from promote import list_approved

    rows = list_approved(_v2_design(tmp_path, approve=2))
    assert [row["severity"] for row in rows] == [5, 4]
    assert rows[0]["slug"] == "hard-coded-credential-in-the-gateway-client"


def test_select_writes_evidence_and_marks_promoted(tmp_path: Path) -> None:
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    written = select(src, slug)

    assert written == tmp_path / "evidence.md"
    text = written.read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert "Repository: " in text
    assert "status: promoted" in src.read_text(encoding="utf-8")
    assert list_approved(src) == []


def test_select_folds_in_matching_open_questions(tmp_path: Path) -> None:
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    finding = list_approved(src)[0]
    primary = finding["primary_file"]
    (tmp_path / "candidates.json").write_text(
        json.dumps({
            "open_questions": [
                {"file": primary, "line_start": 1, "question": "Is this deliberate?"}
            ],
            "looks_bad_but_fine": [],
        }),
        encoding="utf-8",
    )
    text = select(src, finding["slug"]).read_text(encoding="utf-8")
    assert "### Open questions from the scan" in text
    assert "Is this deliberate?" in text


def test_select_rejects_an_unknown_slug(tmp_path: Path) -> None:
    from promote import SelectionError, select

    with pytest.raises(SelectionError, match="unknown"):
        select(_v2_design(tmp_path), "no-such-slug")


def test_select_rejects_a_pending_finding(tmp_path: Path) -> None:
    from promote import SelectionError, select

    src = tmp_path / "design.md"
    src.write_text(V2_GOLDEN.read_text(encoding="utf-8"), encoding="utf-8")
    slug = parse_design(src)["findings"][0]["slug"]
    with pytest.raises(SelectionError, match="pending"):
        select(src, slug)


def test_select_accepts_an_already_promoted_finding(tmp_path: Path) -> None:
    """A re-run after a failed baseline write, or a second design session on
    the same finding, must be possible."""
    from promote import list_approved, select

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    select(src, slug)
    written = select(src, slug)
    assert written.is_file()
```

Add `from design_parser import parse_design` to the test module's imports.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_promote.py -k "list_approved or select" -v`
Expected: FAIL — `ImportError: cannot import name 'list_approved' from 'promote'`

- [ ] **Step 3: Implement the new surface**

Add to `scripts/promote.py`, above `_main`:

```python
from evidence_doc import render_evidence

# design.md statuses `--select` accepts. `promoted` is included so a failed
# baseline write, or a second design session on the same finding, can be
# re-run; `--list-approved` still offers only `approved`, so a re-run is
# always deliberate rather than suggested.
SELECTABLE: Final[frozenset[str]] = frozenset({"approved", "promoted"})


class SelectionError(Exception):
    """Raised when the requested slug is unknown or not selectable."""


def _severity(finding: dict[str, Any]) -> int:
    try:
        return int(finding["severity"])
    except (KeyError, TypeError, ValueError):
        return 0


def _priority(finding: dict[str, Any]) -> float:
    try:
        return float(finding.get("priority") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def list_approved(design_path: Path) -> list[dict[str, Any]]:
    """The `approved` findings in ``design_path``, most severe first.

    Ordered by severity then priority, both descending, so the row the user is
    most likely to pick is first. Read-only: nothing is written and no status
    changes.
    """
    findings = parse_design(design_path)["findings"]
    approved = [f for f in findings if f.get("status") == "approved"]
    approved.sort(key=lambda f: (-_severity(f), -_priority(f)))
    rows: list[dict[str, Any]] = []
    for finding in approved:
        locations = evidence_locations(str(finding.get("body_md") or ""))
        rows.append({
            "slug": finding["slug"],
            "title": finding["title"],
            "family": finding.get("family") or finding["category"],
            "severity": _severity(finding),
            "effort": finding.get("effort"),
            "primary_file": locations[0][0] if locations else None,
            "fingerprint": finding.get("fingerprint"),
        })
    return rows


def select(design_path: Path, slug: str) -> Path:
    """Write ``evidence.md`` for ``slug`` and mark it promoted; return the path.

    Writes beside ``design_path`` (the workdir), overwriting any previous
    evidence document: it seeds one design session and is always re-derivable.
    The design.md mark happens after the write, so a failed render never
    consumes the finding.
    """
    parsed = parse_design(design_path)
    finding = next((f for f in parsed["findings"] if f.get("slug") == slug), None)
    if finding is None:
        raise SelectionError(f"unknown slug: {slug}")
    status = str(finding.get("status", ""))
    if status not in SELECTABLE:
        raise SelectionError(f"{slug} is {status}, not approved")

    candidates = _read_json_object(design_path.parent / "candidates.json")
    text = render_evidence(
        finding,
        metadata=parsed["metadata"],
        open_questions=candidates.get("open_questions") or [],
        looks_bad_but_fine=candidates.get("looks_bad_but_fine") or [],
    )
    out_path = design_path.parent / "evidence.md"
    out_path.write_bytes(text.encode("utf-8"))

    if status == "approved":
        mark_promoted(design_path, slugs=[slug])
    return out_path
```

Add `from evidence_doc import evidence_locations, render_evidence` to the imports (one import line, both names).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_promote.py -v`
Expected: PASS — the new tests plus every existing bundle test still green

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check scripts tests && python -m mypy --strict scripts`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add scripts/promote.py tests/test_promote.py
git commit -m "feat(tech-debt-scan): add --list-approved and --select to promote

list_approved returns the approved findings most severe first; select
writes .tech-debt/evidence.md from the chosen finding and marks it
promoted. The bundle path is untouched and comes out next."
```

---

### Task 4: Remove the bundle path

**Confidence: 93%** — the bundle assertions outside `test_promote.py` are confined to `test_e2e.py` (`:137-178`, `:239-263`), confirmed by grep on 2026-09-10; `test_chain_goldens.py` has none and `test_design_writer.py`'s only hit is a docstring. Step 1 re-confirms before deleting.

**Files:**
- Delete: `skills/tech-debt-scan/scripts/bundle_writer.py`, `skills/tech-debt-scan/tests/test_bundle_writer.py`, `skills/tech-debt-scan/tests/golden/bundle/`, `skills/tech-debt-scan/tests/golden/bundle-v2/`
- Modify: `skills/tech-debt-scan/scripts/promote.py` — `run_promote`, `PromoteResult`, `_existing_bundle_dir`, `_write_back`, `_main`
- Modify: `skills/tech-debt-scan/tests/test_promote.py`, `skills/tech-debt-scan/tests/test_e2e.py`
- Modify: `skills/tech-debt-scan/scripts/design_writer.py` (docstrings `:12`, `:389-390`, `:424`, `:619`), `skills/tech-debt-scan/scripts/slugs.py` (docstring `:3`)

**Interfaces:**
- Consumes: `list_approved`, `select`, `SelectionError` from Task 3.
- Produces: `promote.py`'s final CLI — `promote.py <design.md> --list-approved` and `promote.py <design.md> --select <slug> [--baseline PATH]`; exit codes 0, 2, 6.

- [ ] **Step 1: Re-confirm the blast radius**

Run: `grep -rn "bundle" scripts/ tests/ --include=*.py | grep -v __pycache__`
Expected: hits only in `promote.py`, `test_promote.py`, `test_e2e.py`, the two docstring files above, and `test_tools_probe.py:1261` (`bundle.min.js`, unrelated — leave it). Any other file means this step's list is stale; stop and report.

- [ ] **Step 2: Delete the bundle module, its tests and its goldens**

```bash
git rm scripts/bundle_writer.py tests/test_bundle_writer.py
git rm -r tests/golden/bundle tests/golden/bundle-v2
```

- [ ] **Step 3: Strip the bundle path out of `promote.py`**

Delete `PromoteResult`, `_existing_bundle_dir`, `run_promote` and the `bundle_writer` import entirely. `_write_back` loses its `result` and `out_root` parameters and takes the design path, baseline path, today and preset it needs:

```python
def _write_back(design_path: Path, baseline_path: Path, today: str) -> str:
    """Record every decision in ``design_path`` into the baseline; return the outcome.

    Re-parses ``design_path`` so the decisions reflect ``select``'s own
    mark-promoted mutation, and reads the matching ``verified.json`` and
    ``ranked.json`` (preset defaults to "balanced" when ranked.json or its
    preset key is absent) from the design's own directory.

    Raises BaselineError, DesignParseError, ValueError or OSError on any
    failure -- the caller turns each into EXIT_WRITE_BACK. ``root`` for the
    gitignore triple is derived from ``baseline_path`` itself, never from the
    process's cwd.
    """
    decisions = parse_design(design_path)["findings"]
    verified = _read_json_object(design_path.parent / "verified.json")
    findings = verified.get("findings") or []
    ranked = _read_json_object(design_path.parent / "ranked.json")
    preset = str(ranked.get("preset") or "balanced")

    baseline.record(
        baseline_path,
        decisions=decisions,
        findings=findings,
        today=today,
        preset=preset,
    )
    return baseline.ensure_gitignore_triple(_repo_root_for_baseline(baseline_path), baseline_path)
```

Replace `_main` with:

```python
def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select one approved tech-debt finding and seed a design session"
    )
    parser.add_argument("design", type=Path, help="path to the edited design.md")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list-approved", action="store_true",
        help="print the approved findings as JSON and exit",
    )
    group.add_argument("--select", metavar="SLUG", help="write evidence.md for this finding")
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help="record every finding's decision into this baseline after selecting",
    )
    args = parser.parse_args(argv)

    try:
        parsed = parse_design(args.design)
    except DesignParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_approved:
        print(json.dumps(list_approved(args.design), indent=2))
        return 0

    # A v1 design.md carries no fingerprints; refuse before anything is written,
    # since a baseline without fingerprints is worse than none. A document with
    # no findings answers the same way and is not a v1 document.
    if args.baseline is not None and parsed["findings"] and not any(
        f.get("fingerprint") for f in parsed["findings"]
    ):
        print(
            f"error: {args.design} has no fingerprints (a v1 design.md); "
            "refusing to write a baseline without them",
            file=sys.stderr,
        )
        return 2

    try:
        written = select(args.design, args.select)
    except (SelectionError, DesignWriteError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {written}")

    if args.baseline is not None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            outcome = _write_back(args.design, args.baseline, today)
        except (BaselineError, DesignParseError, ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_WRITE_BACK
        print(f"wrote {args.baseline}")
        if outcome == "appended":
            print("appended the gitignore triple")
        elif outcome == "still-ignored":
            print(
                "appended the gitignore triple, but the baseline is still ignored; "
                "an ancestor directory is ignored and must be un-ignored by hand"
            )

    return 0
```

Rewrite the module docstring to describe the two subcommands, and update `EXIT_WRITE_BACK`'s comment: the write-back now runs after `evidence.md` was written and `design.md` was marked, so exit 6 means only the baseline failed and the command is re-runnable.

Delete the now-unused `shutil`/`subprocess` imports only if `_repo_root_for_baseline` no longer needs them — it does need both, so leave them.

- [ ] **Step 4: Delete the bundle tests in `test_promote.py`**

Remove every test that calls `run_promote` or asserts on `chore-*` directories, `emitted_count`, `already_promoted_count`, `emitted_paths` or `PromoteResult`. Keep and re-express as `--select`/`--list-approved` equivalents: the v1-refusal test, the invalid-status test (now a `parse_design` failure through `_main`), and the baseline write-back tests. Add:

```python
def test_main_list_approved_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from promote import _main

    src = _v2_design(tmp_path)
    assert _main([str(src), "--list-approved"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1 and rows[0]["slug"]


def test_main_select_writes_evidence(tmp_path: Path) -> None:
    from promote import _main, list_approved

    src = _v2_design(tmp_path)
    slug = list_approved(src)[0]["slug"]
    assert _main([str(src), "--select", slug]) == 0
    assert (tmp_path / "evidence.md").is_file()


def test_main_requires_a_mode(tmp_path: Path) -> None:
    from promote import _main

    with pytest.raises(SystemExit):
        _main([str(_v2_design(tmp_path))])
```

- [ ] **Step 5: Rewrite the e2e chain ending**

In `tests/test_e2e.py`, replace the bundle assertions at `:137-178` and `:239-263` with the evidence-document ending: after the chain renders `design.md` and a status is flipped to `approved`, call `promote._main([str(design), "--select", slug, "--baseline", str(baseline)])`, then assert `evidence.md` exists, starts with `# `, contains `Repository: `, that `design.md` now reads `status: promoted`, and that the baseline entry for `_FP_PROMOTED` has `status == "promoted"` and no `bundle` key. Update the module docstring's "to a PBI bundle" to "to evidence.md".

- [ ] **Step 6: Update the two stale docstrings**

`scripts/design_writer.py`: `:12` ("once their bundles have been emitted" → "once they are selected for a design session"), `:389-390` (drop the bundle-id sentence from the slug's identity list), `:424` ("out of the body that bundle_writer copies into a PBI" → "out of the body that evidence_doc copies into evidence.md"), `:619` (drop the `bundle_writer.py` reference). `scripts/slugs.py:3`: drop "in a PBI bundle id".

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS, with `test_bundle_writer.py` gone from collection

- [ ] **Step 8: Run the gates**

Run: `python -m ruff check scripts tests && python -m mypy --strict scripts && python scripts/skill_check.py`
Expected: ruff and mypy clean. `skill_check.py` **fails** here — SKILL.md still names `--out` and `--force`. That is expected and Task 5 fixes it; record the failure message and continue.

- [ ] **Step 9: Commit**

```bash
git add -A scripts tests
git commit -m "feat(tech-debt-scan)!: remove the PBI bundle path from promote

Deletes bundle_writer.py, its tests and its goldens, and reduces promote
to --list-approved and --select. Ralph packaging belongs to ralph's own
skills; what this skill owes is the evidence and the design session.

BREAKING CHANGE: promote no longer emits chore-<slug> bundles and the
--out and --force flags are gone."
```

---

### Task 5: SKILL.md and the docs

**Confidence: 95%** — prose and one lint gate; `skill_check.py` mechanically verifies that every `python scripts/<name>.py` command in SKILL.md matches a real script and its real flags, so the gate proves the rewrite.

**Files:**
- Modify: `skills/tech-debt-scan/SKILL.md` — the "Promote steps" section, the bundle sentences in Conventions and Caveats, and the `/tech-debt-promote` line under "When to use"
- Modify: `docs/architecture.md`, `README.md`

**Interfaces:**
- Consumes: promote's final CLI from Task 4.
- Produces: the documented procedure the LLM follows at run time.

- [ ] **Step 1: Rewrite SKILL.md's promote steps**

Replace the whole "## Promote steps" section with:

```markdown
## Promote steps

1. Locate the edited `design.md` (default `.tech-debt/design.md`); missing is
   exit 5.
2. `python scripts/promote.py <design.md> --list-approved` prints the approved
   findings as JSON: slug, title, family, severity, effort, primary file,
   fingerprint, most severe first. An empty list means nothing is approved —
   say so, name the file to edit, and stop. Never approve on the user's behalf.
3. Show the list and ask the user which single finding to work on. One per
   invocation: a second finding is a second run, with fresh context.
4. `python scripts/promote.py <design.md> --select <slug> --baseline <repo>/.tech-debt/baseline.json`
   writes `.tech-debt/evidence.md`, flips that finding to `promoted` in
   `design.md`, and records every finding's decision into the baseline. Exit 2
   is a selection or parse failure and nothing was consumed; exit 6 means the
   evidence document and the design.md mark both landed and only the baseline
   write failed — fix the cause and re-run the same command, which is
   idempotent because `--select` accepts an already-promoted slug.
5. Read `.tech-debt/evidence.md` and invoke `superpowers:brainstorming`, seeded
   with it. Its `### Open questions from the scan` section is the scan's own
   unanswered questions about this code: ask those first.
6. The brainstorm always ends by invoking `superpowers:writing-plans`, whatever
   it classified the work as — a tech-debt finding must leave a plan behind.
   The plan is the deliverable; this skill does not execute it, queue it or
   commit it on the user's behalf.
```

- [ ] **Step 2: Fix the surrounding prose**

Under "When to use", replace the `/tech-debt-promote` bullet with: "`/tech-debt-promote` — after a human has reviewed `design.md` and marked findings `approved`, `rejected` or `accepted`, pick one approved finding and open a design session on it."

In Conventions, the baseline bullet keeps its wording. In Caveats: delete the `promote.py` exit-code line's bundle clauses (exit 4 is gone; exit 6 no longer mentions bundles), replace the "Single-user" caveat's "two promotes against the same `design.md`" wording with the same warning about concurrent `--select` runs, and in "Backwards compatibility" replace the bundle sentence with: "a v1 `design.md` still parses and selects; the PBI bundle format is gone with no shim, since ralph's own skills own queue packaging."

Delete the phrase "then `/tech-debt-promote` emits ralph-friendly PBI bundles you can drop into a queue" from the opening paragraph and replace with "then `/tech-debt-promote` opens a design session on one approved finding."

- [ ] **Step 3: Run the lint gate**

Run: `python scripts/skill_check.py`
Expected: `ok: all SKILL.md commands match their scripts`

- [ ] **Step 4: Update `docs/architecture.md` and `README.md`**

In `docs/architecture.md`, rewrite every bundle reference to describe the evidence document and the design session. In `README.md`, the two-command quickstart's second command becomes the design session rather than PBI bundles, and the "Install" and dependency sections are untouched.

- [ ] **Step 5: Run everything one last time**

Run: `python -m pytest && python -m ruff check scripts tests && python -m mypy --strict scripts && python scripts/skill_check.py`
Expected: all four clean

- [ ] **Step 6: Commit**

```bash
git add SKILL.md ../../docs/architecture.md ../../README.md
git commit -m "docs(tech-debt-scan): document promote as a design entry point"
```

---

## Self-Review

**Spec coverage.** Section 2's command contract → Tasks 3 and 5. Section 3's `evidence.md` → Task 1. Section 4's baseline changes → Task 2. Section 5's code inventory → Tasks 1–5 (every deleted, rewritten, new and amended path appears in the File Structure table). Section 6's tests → the test steps in each task. Section 7's build order → the task order, unchanged. Section 8's migration → Task 2 Step 2's legacy-entry test and Task 5's compatibility caveat. No spec requirement is unimplemented.

**Type consistency.** `render_evidence` and `evidence_locations` are defined in Task 1 with the exact signatures Task 3 imports. `baseline.record`'s post-change signature is stated in Task 2's Interfaces and used unchanged in Task 4's `_write_back`. `list_approved`'s seven row keys are asserted in Task 3's first test and consumed in Task 4's `_main`. `SelectionError` is defined in Task 3 and caught in Task 4.

**Known deviation from the spec, deliberate:** spec section 3 says the matched sections use "the finding's evidence list", implying `verified.json`. The plan reads the same locations out of `body_md` with `_EVIDENCE_LINE` instead, which is the shape `design_writer` renders and is already verified on disk. This keeps `evidence_doc.py` pure and removes a `verified.json` read from `select`. The behaviour is identical.
