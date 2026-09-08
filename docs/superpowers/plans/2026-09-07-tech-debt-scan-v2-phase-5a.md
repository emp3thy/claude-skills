# tech-debt-scan v2 phase 5a: the baseline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a second scan know what the first one found — `baseline.py` classifies every finding as NEW, UNCHANGED, moved, edited or RESOLVED against a committed baseline, `promote.py` writes human decisions back into it, and rejected or accepted findings stop recurring.

**Architecture:** `baseline.py` is a new script with two subcommands. `diff` reads `verified.json`, `ranked.json` and the baseline, and writes `diff.json`, which `design_writer.load_inputs` already loads and `_diff_for` already renders — that consumer has been waiting since phase 3. `record` is called in process by `promote.py` after it emits bundles, and writes each finding's status, reason, expiry and bundle path into the baseline, appending the gitignore triple so the baseline is tracked while the rest of the workdir stays ignored. Everything here is deterministic and testable without spending a token.

**Tech Stack:** Python 3.11+, standard library plus `yaml`. `pytest`. `git` for `check-ignore`, with a no-git path.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` — section 4.10 fixes both schemas, the five classifications, suppression and expiry, and the gitignore triple; 4.11 the frontmatter counts; 4.12 promote; 5 the step list; 11 phase 5a's scope and gate. Read 4.10 in full before Task 1.

## Global Constraints

- Python 3.11+; standard library only in the skill's scripts, plus `yaml`. No new dependencies.
- Flat sibling imports: `from evidence import fingerprint, find_quote`, `from inventory import write_json`, `from redaction import redact`. Never package-relative. Imports at the top of the file — ruff E402.
- `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q` all green before every commit. The suite baseline entering this plan is 1131 passed, 1 skipped, 7 deselected.
- Goldens are byte-compared, written LF-only through `inventory.write_json`, and regenerate byte-identically under `UPDATE_GOLDENS=1`. Clocks are pinned: the chain test's `SCAN_DATE = "2026-09-06"`; `baseline.py` takes `--today` and never reads the wall clock inside a test.
- **Redaction precedes truncation** everywhere a string is capped, and every text field reaching a document passes through `redact`. A baseline `title` is such a field.
- **The tier invariant holds:** `rules.py` and osv fact-class signals are the only producers of a non-`None` tier at merge time. Nothing here sets a tier.
- Spec section 8: a v1 `design.md` must still parse and promote byte-identically; `tests/golden/design-v1.md` pins it. `promote.py` without `--baseline` must behave exactly as it does today.
- Commit subjects in conventional-commit form; every body ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Confidence floor 92%. Every task states its confidence and embeds its own mitigation.

---

## Guardrails from prior sessions

- **Mutation-check every assertion** (this project, eleven instances on the last branch). For each assertion, apply the mutant that removes the behaviour and confirm the test fails; choose fixture values that make it fail rather than ones that happen to sort or compare correctly. Task 1's classification tests are the ones most at risk of passing by coincidence — a "moved" finding that would also match as "edited", say — so each classification test must exclude every other classification by construction.
- **Read the argparse setup, never an existing example, when documenting a command** (0.95, evidence 7). Task 6 documents step 11 and the `--baseline` flag from real `--help` output.
- **Keep docs in sync in the same change** (0.95, evidence 7). Each task updates the docstring of the module it changes.
- **A defect one field over from the one just fixed** (this project, twice). Task 1's `moved` classification keys on `line_start` differing; Task 3's `record` writes `line_start`. When either reads a line, check the neighbouring field.
- Dismissed as not applicable: the TypeScript `Partial<T>` reflection, the `tempfile.mkstemp` reflection (no temp files here beyond `tmp_path`), the ralph-queue reflection.

---

## Assumptions surfaced

### Real concerns

**1. "Edited" is a heuristic and the only classification that can be wrong in both directions.** Spec 4.10: same family and file, a candidate within 40 lines whose title shares at least half its tokens. Too loose and a genuinely new finding near an old one inherits the old one's status — including `rejected`, which would silently suppress it. Too tight and every retitled finding reads as RESOLVED plus NEW.

*Mitigation, embedded in Task 1:* token sharing is defined exactly — lower-cased, split on non-alphanumerics, stop-words not removed, the threshold `len(shared) * 2 >= len(baseline_tokens)` — and tested at the boundary on both sides: a title sharing exactly half matches, one sharing one token fewer does not, and a finding 41 lines away does not. A suppressed baseline entry matched only by the edited heuristic carries `note: "suppressed by edited match"` so a human can see the inference in `diff.json`.

**2. `record` is the only writer of a file that git tracks, and it runs inside `promote`.** A bug here corrupts the one artefact that persists across scans, and it runs after bundles are already on disk. `EXIT_WRITE_BACK` exists precisely because a write-back failure must not look like a promote failure.

*Mitigation, embedded in Tasks 3 and 4:* `record` writes the whole baseline atomically — serialise to a sibling temporary path, then `os.replace` — so a crash mid-write leaves the old baseline intact. Round-trip tests assert every field survives `record` then `load_baseline`. Task 4 asserts that when `record` raises, `promote` returns 6, the bundles it already emitted remain, and its own counts are still printed.

**3. The gitignore triple edits a file the user owns.** Appending to `<root>/.gitignore` is the one side effect on a file outside the workdir in the whole pipeline.

*Mitigation, embedded in Task 3:* the triple is appended only when `git check-ignore -q <baseline>` says the baseline is currently ignored, only once (a second run finds the lines and leaves the file alone), always with a preceding comment naming the skill, and never without git — without git the baseline is written and the check is skipped with a note. The test uses a real temporary git repository and asserts `check-ignore` flips from ignored to tracked after one edit and that a second run is a no-op.

### Verified safe

- `design_writer.load_inputs` already reads `diff.json` from the workdir as an optional input (`design_writer.py:202`), and `_diff_for` (`:334`) already renders each finding's `diff` from it. 5a produces the file; the consumer needs no change for the per-finding key.
- `promote.EXIT_WRITE_BACK = 6` is reserved and unreturned (`promote.py:57`); `run_promote` returns a `PromoteResult` carrying `emitted_paths`, so the bundle path per finding is available for `record`.
- `config.py:96` already has `"baseline": ".tech-debt/baseline.json"`.
- `evidence.fingerprint(family, path, quote) -> (fp, quote_hash)` and `evidence.find_quote(lines, quote, line_start, line_end, *, max_lines=6) -> (start, end) | None` exist and are what `diff` needs for moved and RESOLVED.
- `design_parser` already parses `reason` and `until` as optional anchor keys (`design_parser.py:73-74`), and `promote` already counts `accepted` (phase 1). `record` reads what the parser produces.
- `verified.json` findings carry `fingerprint`, `family`, `title`, `tier`, `quote_hash`, `evidence[0].file/line_start`; `ranked.json` carries `fingerprint`, `tier`, `in_top_n`. Both pinned by goldens.

### Minor or accepted

- The baseline records the primary evidence file only; a multi-file finding is tracked by its first evidence item, matching how it is fingerprinted.
- RESOLVED requires reading the file from disk; a baseline entry whose file is unreadable for a reason other than absence is RESOLVED with `note: "file unreadable"`.
- `diff` with an absent baseline marks everything NEW and writes `baseline_found: false`; the chain goldens for all three fixtures are exactly that case, so they change only by gaining `diff.json`.
- The frontmatter's `new` and `resolved` counts, which phase 3 omitted, land in Task 5 and move the `design.md` goldens.
- Nothing in 5a spends a token. The corpus repairs and the live run are 5b.

---

## File structure

| File | Responsibility |
|---|---|
| `skills/tech-debt-scan/scripts/baseline.py` | Create. `load_baseline`, `classify`, `diff`, `record`, `ensure_gitignore_triple`, and the two-subcommand CLI. |
| `skills/tech-debt-scan/scripts/promote.py` | Modify. `--baseline` flag; call `record` in process; return `EXIT_WRITE_BACK` on failure. |
| `skills/tech-debt-scan/scripts/design_writer.py` | Modify. Frontmatter `new` and `resolved` counts; suppressed findings excluded from the body. |
| `skills/tech-debt-scan/tests/test_baseline.py` | Create. |
| `skills/tech-debt-scan/tests/test_promote.py`, `test_design_writer.py`, `test_chain_goldens.py` | Modify. |
| `skills/tech-debt-scan/tests/golden/<fixture>/diff.json` | Create in Task 2. |
| `skills/tech-debt-scan/SKILL.md`, `docs/architecture.md`, `README.md` | Modify in Task 6. |

---

## Task 1: the baseline document and the five classifications

**Confidence: 92%.** Pure functions over dicts, fully specified by spec 4.10 — but "edited" is a heuristic, and the tests must make each classification exclude the others by construction.

**Files:**
- Create: `skills/tech-debt-scan/scripts/baseline.py`
- Create: `skills/tech-debt-scan/tests/test_baseline.py`

**Interfaces:**
- Consumes: `evidence.find_quote`, `evidence.normalise_quote`.
- Produces: `SCHEMA_VERSION = 2`, `STATUSES`, `EDIT_WINDOW = 40`, `load_baseline(path: Path) -> dict[str, Any] | None`, `title_tokens(title: str) -> set[str]`, `classify(finding, baseline, root, today) -> Classification`, and the `Classification` dataclass with `diff`, `note`, `matched`, `suppressed_as`.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_baseline.py`:

```python
"""Tests for baseline.py (spec 4.10)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TODAY = "2026-09-07"


def _finding(**over) -> dict:
    base = {
        "fingerprint": "aaaaaaaaaaaaaaaa", "family": "error-masking", "title": "Empty catch swallows write failure",
        "tier": "A", "quote_hash": "q" * 40,
        "evidence": [{"file": "src/pay/refund.py", "line_start": 33, "line_end": 33,
                      "quote": "except Exception:", "quote_verified": True}],
    }
    base.update(over)
    return base


def _entry(**over) -> dict:
    base = {
        "family": "error-masking", "file": "src/pay/refund.py", "line_start": 33,
        "quote_hash": "q" * 40, "title": "Empty catch swallows write failure", "tier": "A",
        "status": "pending", "first_seen": "2026-09-01", "last_seen": "2026-09-01",
        "reason": None, "until": None, "bundle": None,
    }
    base.update(over)
    return base


def _baseline(**entries) -> dict:
    return {"schema_version": 2, "last_scan": "2026-09-01", "preset": "balanced", "findings": entries}


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return tmp_path


class TestLoadBaseline:
    def test_absent_file_is_none(self, tmp_path: Path) -> None:
        from baseline import load_baseline

        assert load_baseline(tmp_path / "baseline.json") is None

    def test_wrong_schema_version_raises(self, tmp_path: Path) -> None:
        from baseline import BaselineError, load_baseline

        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"schema_version": 1, "findings": {}}), encoding="utf-8")
        with pytest.raises(BaselineError, match="schema_version"):
            load_baseline(path)

    def test_round_trips_every_field(self, tmp_path: Path) -> None:
        from baseline import load_baseline

        doc = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", reason="tracked in JIRA-1",
                                                until="2027-01-01", bundle="chore-x-2026-09-01"))
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        assert load_baseline(path) == doc


class TestTitleTokens:
    def test_lowercases_and_splits_on_non_alphanumerics(self) -> None:
        from baseline import title_tokens

        assert title_tokens("Empty catch, swallows-write failure!") == {
            "empty", "catch", "swallows", "write", "failure",
        }

    def test_stop_words_are_kept(self) -> None:
        """Spec 4.10 says half the tokens, not half the interesting ones."""
        from baseline import title_tokens

        assert "the" in title_tokens("the empty catch")


class TestClassify:
    def test_fingerprint_match_is_unchanged(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        out = classify(_finding(), _baseline(aaaaaaaaaaaaaaaa=_entry()), root, TODAY)
        assert out.diff == "UNCHANGED"
        assert out.matched == "aaaaaaaaaaaaaaaa"
        assert out.note is None

    def test_same_fingerprint_at_another_line_is_moved(self, tmp_path: Path) -> None:
        """The fingerprint carries no line, so a quote that moved keeps its
        fingerprint; the baseline's recorded line is what differs."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 40 + "except Exception:\n"})
        finding = _finding(evidence=[{"file": "src/pay/refund.py", "line_start": 41,
                                      "line_end": 41, "quote": "except Exception:",
                                      "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "UNCHANGED (moved)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_edited_match_shares_half_the_tokens_within_forty_lines(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        # Baseline title has 5 tokens; the new title shares 3 of them (>= half).
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 73,
                                      "line_end": 73, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33))
        out = classify(finding, base, root, TODAY)
        assert out.diff == "UNCHANGED (edited)"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_edited_requires_at_least_half_not_fewer(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        # Baseline title has 5 tokens; the new title shares exactly 2 (< half).
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch around nothing",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 35,
                                      "line_end": 35, "quote": "except:", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_edited_requires_forty_lines_not_forty_one(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch swallows write failure",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 74,
                                      "line_end": 74, "quote": "except:", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_edited_requires_the_same_family(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", family="security", quote_hash="r" * 40)
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry(line_start=33)), root, TODAY)
        assert out.diff == "NEW"

    def test_no_match_at_all_is_new(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/other.py": "y\n"})
        finding = _finding(fingerprint="cccccccccccccccc", quote_hash="s" * 40,
                           evidence=[{"file": "src/other.py", "line_start": 1, "line_end": 1,
                                      "quote": "y", "quote_verified": True}])
        out = classify(finding, _baseline(aaaaaaaaaaaaaaaa=_entry()), root, TODAY)
        assert out.diff == "NEW"
        assert out.matched is None

    def test_absent_baseline_is_new(self, tmp_path: Path) -> None:
        from baseline import classify

        out = classify(_finding(), None, tmp_path, TODAY)
        assert out.diff == "NEW"

    def test_rejected_match_is_suppressed(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="intentional"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as == "rejected"
        assert out.matched == "aaaaaaaaaaaaaaaa"

    def test_unexpired_accepted_match_is_suppressed(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2027-01-01"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as == "accepted"

    def test_expired_accepted_match_returns_as_unchanged_with_a_note(self, tmp_path: Path) -> None:
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-09-01"))
        out = classify(_finding(), base, root, TODAY)
        assert out.suppressed_as is None
        assert out.diff == "UNCHANGED"
        assert out.note == "acceptance expired"

    def test_accepted_expiring_today_is_still_suppressed(self, tmp_path: Path) -> None:
        """`until` is inclusive: the acceptance holds through its last day."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until=TODAY))
        assert classify(_finding(), base, root, TODAY).suppressed_as == "accepted"

    def test_suppression_through_an_edited_match_is_noted(self, tmp_path: Path) -> None:
        """A rejected entry matched only by the edited heuristic suppresses the
        new finding, and says so, because that inference can be wrong."""
        from baseline import classify

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80})
        finding = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                           title="Empty catch hides failure silently",
                           evidence=[{"file": "src/pay/refund.py", "line_start": 40,
                                      "line_end": 40, "quote": "except:", "quote_verified": True}])
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="by design"))
        out = classify(finding, base, root, TODAY)
        assert out.suppressed_as == "rejected"
        assert out.note == "suppressed by edited match"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'baseline'`.

- [ ] **Step 3: Write the classification core**

Create `skills/tech-debt-scan/scripts/baseline.py`:

```python
"""The baseline: what the last scan found, and what a human decided (spec 4.10).

``diff`` classifies every current finding against the committed baseline --
UNCHANGED, UNCHANGED (moved), UNCHANGED (edited), NEW -- and every baseline
entry no current finding matched as RESOLVED, writing ``diff.json`` for
``design_writer`` to render. ``record`` is called in process by ``promote.py``
and writes each finding's status, reason, expiry and bundle back, so a
``rejected`` finding stops recurring and an ``accepted`` one returns when its
expiry passes.

Three classifications are exact and one is a heuristic. A fingerprint match
is UNCHANGED, or UNCHANGED (moved) when the baseline recorded a different
line -- the fingerprint carries no line, so a quote that moved keeps it. An
edited match is the heuristic: same family and file, within ``EDIT_WINDOW``
lines, a title sharing at least half the baseline title's tokens. It can be
wrong in both directions, so a suppression that rests on it is noted.

The baseline lives inside the ignored workdir and is re-included by three
``.gitignore`` lines appended once by ``record``; see ``ensure_gitignore_triple``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[int] = 2
STATUSES: Final[tuple[str, ...]] = ("pending", "approved", "rejected", "accepted", "promoted")
SUPPRESSING: Final[frozenset[str]] = frozenset({"rejected", "accepted"})
EDIT_WINDOW: Final[int] = 40
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


class BaselineError(Exception):
    """A baseline that cannot be read or written."""


@dataclass(frozen=True)
class Classification:
    diff: str  # NEW | UNCHANGED | UNCHANGED (moved) | UNCHANGED (edited)
    matched: str | None  # baseline fingerprint, if any
    note: str | None
    suppressed_as: str | None  # "rejected" | "accepted" | None


def load_baseline(path: Path) -> dict[str, Any] | None:
    """The baseline document, or None when the file does not exist."""
    import json

    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise BaselineError(f"{path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        raise BaselineError(f"{path}: schema_version must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("findings"), dict):
        raise BaselineError(f"{path}: findings must be an object")
    return doc


def title_tokens(title: str) -> set[str]:
    """Lower-cased tokens split on non-alphanumerics; stop-words are kept (spec 4.10)."""
    return {t for t in _TOKEN.split(title.lower()) if t}


def _primary(finding: dict[str, Any]) -> tuple[str | None, int | None]:
    evidence = finding.get("evidence") or []
    if not evidence or not isinstance(evidence[0], dict):
        return None, None
    file = evidence[0].get("file")
    line = evidence[0].get("line_start")
    return (file if isinstance(file, str) else None,
            line if isinstance(line, int) else None)


def _expired(entry: dict[str, Any], today: str) -> bool:
    until = entry.get("until")
    if not isinstance(until, str):
        return False
    try:
        return date.fromisoformat(until) < date.fromisoformat(today)
    except ValueError:
        return False


def _suppressed_as(entry: dict[str, Any], today: str) -> str | None:
    status = entry.get("status")
    if status == "rejected":
        return "rejected"
    if status == "accepted" and not _expired(entry, today):
        return "accepted"
    return None


def _edited_match(
    finding: dict[str, Any], baseline: dict[str, Any], file: str, line: int | None
) -> str | None:
    """The fingerprint of a baseline entry this finding is an edit of, if any."""
    wanted = title_tokens(str(finding.get("title", "")))
    family = finding.get("family")
    best: tuple[int, str] | None = None
    for fp, entry in baseline["findings"].items():
        if entry.get("family") != family or entry.get("file") != file:
            continue
        base_line = entry.get("line_start")
        if line is not None and isinstance(base_line, int) and abs(base_line - line) > EDIT_WINDOW:
            continue
        base_tokens = title_tokens(str(entry.get("title", "")))
        shared = len(wanted & base_tokens)
        if base_tokens and shared * 2 >= len(base_tokens):
            distance = abs((base_line or 0) - (line or 0))
            if best is None or distance < best[0]:
                best = (distance, fp)
    return best[1] if best else None


def classify(
    finding: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> Classification:
    """One current finding against the baseline (spec 4.10)."""
    if baseline is None:
        return Classification("NEW", None, None, None)
    fp = str(finding.get("fingerprint", ""))
    file, line = _primary(finding)
    entry = baseline["findings"].get(fp)
    if entry is not None:
        suppressed = _suppressed_as(entry, today)
        note = None
        if entry.get("status") == "accepted" and suppressed is None:
            note = "acceptance expired"
        moved = isinstance(line, int) and isinstance(entry.get("line_start"), int) \
            and entry["line_start"] != line
        return Classification("UNCHANGED (moved)" if moved else "UNCHANGED", fp, note, suppressed)
    if file is not None:
        edited = _edited_match(finding, baseline, file, line)
        if edited is not None:
            entry = baseline["findings"][edited]
            suppressed = _suppressed_as(entry, today)
            note = "suppressed by edited match" if suppressed else None
            return Classification("UNCHANGED (edited)", edited, note, suppressed)
    return Classification("NEW", None, None, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q`
Expected: PASS, 18 tests.

- [ ] **Step 5: Mutation-check the classification boundaries**

Before committing, apply each of these mutants by hand, run the suite, confirm the named test fails, then revert. Record all four in the report.

| Mutant | Must fail |
|---|---|
| `shared * 2 >= len(base_tokens)` → `>` | `test_edited_match_shares_half_the_tokens_within_forty_lines` |
| `> EDIT_WINDOW` → `>= EDIT_WINDOW` | the 40-line boundary test needs a case at exactly 40; add `test_edited_match_at_exactly_forty_lines` if the mutant survives |
| `date.fromisoformat(until) < today` → `<=` | `test_accepted_expiring_today_is_still_suppressed` |
| drop the `entry.get("family") != family` check | `test_edited_requires_the_same_family` |

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/scripts/baseline.py skills/tech-debt-scan/tests/test_baseline.py
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the baseline document and the five classifications

A fingerprint match is UNCHANGED, or moved when the baseline recorded a
different line -- the fingerprint carries no line, so a quote that moved
keeps it. An edited match is the one heuristic: same family and file,
within forty lines, a title sharing at least half the baseline title's
tokens. It can be wrong in both directions, so a suppression resting on
it is noted rather than silent. Every boundary is tested from both sides
and mutation-checked.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `baseline.py diff` and its goldens

**Confidence: 93%.** Composition of Task 1 over two documents plus a RESOLVED pass that reads files. The one judgment is what a RESOLVED check does for a baseline entry whose file is unreadable.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/baseline.py`
- Modify: `skills/tech-debt-scan/tests/test_baseline.py`, `test_chain_goldens.py`
- Create: `skills/tech-debt-scan/tests/golden/<fixture>/diff.json` for all three fixtures

**Interfaces:**
- Consumes: `classify`, `load_baseline`, `evidence.find_quote`, `inventory.write_json`.
- Produces: `diff(verified: dict, baseline: dict | None, root: Path, today: str) -> dict` returning the `diff.json` document of spec 4.10, and the CLI `python scripts/baseline.py diff --workdir <dir> [--baseline <path>] [--today YYYY-MM-DD]`.

- [ ] **Step 1: Write the failing tests**

Append to `test_baseline.py`:

```python
class TestDiff:
    def _verified(self, *findings: dict) -> dict:
        return {"schema_version": 2, "findings": list(findings)}

    def test_absent_baseline_marks_everything_new(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(_finding()), None, tmp_path, TODAY)
        assert out["baseline_found"] is False
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "NEW"
        assert out["counts"] == {"new": 1, "unchanged": 0, "moved": 0, "edited": 0,
                                 "resolved": 0, "suppressed": 0, "expired": 0}

    def test_an_unmatched_baseline_entry_whose_quote_is_gone_is_resolved(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "nothing here\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry())
        out = diff(self._verified(), base, root, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "RESOLVED"
        assert out["counts"]["resolved"] == 1

    def test_an_unmatched_entry_whose_file_is_gone_is_resolved(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(), _baseline(aaaaaaaaaaaaaaaa=_entry()), tmp_path, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["diff"] == "RESOLVED"
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "file absent"

    def test_an_unmatched_entry_whose_quote_still_exists_is_not_resolved(self, tmp_path: Path) -> None:
        """The scan simply did not raise it this time; it is neither resolved nor
        current, so it is absent from status and counted nowhere."""
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry())
        base["findings"]["aaaaaaaaaaaaaaaa"]["quote"] = "except Exception:"
        out = diff(self._verified(), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["counts"]["resolved"] == 0

    def test_suppressed_findings_are_listed_not_statused(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="rejected", reason="by design"))
        out = diff(self._verified(_finding()), base, root, TODAY)
        assert "aaaaaaaaaaaaaaaa" not in out["status"]
        assert out["suppressed"] == [{"fingerprint": "aaaaaaaaaaaaaaaa", "status": "rejected",
                                      "reason": "by design"}]
        assert out["counts"]["suppressed"] == 1

    def test_expired_acceptance_is_counted(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 32 + "except Exception:\n"})
        base = _baseline(aaaaaaaaaaaaaaaa=_entry(status="accepted", until="2026-01-01"))
        out = diff(self._verified(_finding()), base, root, TODAY)
        assert out["status"]["aaaaaaaaaaaaaaaa"]["note"] == "acceptance expired"
        assert out["counts"]["expired"] == 1

    def test_counts_sum_over_every_classification(self, tmp_path: Path) -> None:
        from baseline import diff

        root = _repo(tmp_path, {"src/pay/refund.py": "x\n" * 80, "src/gone.py": "z\n"})
        moved = _finding(evidence=[{"file": "src/pay/refund.py", "line_start": 41,
                                    "line_end": 41, "quote": "except Exception:",
                                    "quote_verified": True}])
        edited = _finding(fingerprint="bbbbbbbbbbbbbbbb", quote_hash="r" * 40,
                          title="Empty catch hides failure silently",
                          evidence=[{"file": "src/pay/refund.py", "line_start": 60,
                                     "line_end": 60, "quote": "except:", "quote_verified": True}])
        new = _finding(fingerprint="cccccccccccccccc", quote_hash="s" * 40, family="security",
                       evidence=[{"file": "src/gone.py", "line_start": 1, "line_end": 1,
                                  "quote": "z", "quote_verified": True}])
        base = _baseline(
            aaaaaaaaaaaaaaaa=_entry(line_start=33),
            dddddddddddddddd=_entry(file="src/pay/refund.py", line_start=70,
                                    title="Entirely different wording here", quote="absent"),
            eeeeeeeeeeeeeeee=_entry(file="src/missing.py", line_start=1, quote="gone"),
        )
        out = diff(self._verified(moved, edited, new), base, root, TODAY)
        assert out["counts"] == {"new": 1, "unchanged": 0, "moved": 1, "edited": 1,
                                 "resolved": 2, "suppressed": 0, "expired": 0}

    def test_the_document_has_the_spec_shape(self, tmp_path: Path) -> None:
        from baseline import diff

        out = diff(self._verified(), None, tmp_path, TODAY)
        assert set(out) == {"schema_version", "baseline_found", "status", "suppressed", "counts"}
        assert out["schema_version"] == 2
```

Note the baseline entry gains an optional `quote` field alongside `quote_hash`: RESOLVED needs the text to search for, and a hash cannot be searched. Spec 4.10's schema lists `quote_hash`; `record` in Task 3 writes both, and `load_baseline` accepts an entry without `quote` (RESOLVED then falls back to `note: "quote unavailable"` and treats the entry as resolved only when the file is absent).

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q -k Diff`
Expected: FAIL, `ImportError: cannot import name 'diff'`.

- [ ] **Step 3: Write `diff` and the CLI**

Append to `baseline.py` (imports go at the top of the file):

```python
def _resolved(entry: dict[str, Any], root: Path) -> tuple[bool, str | None]:
    """Whether an unmatched baseline entry's debt is gone, and why."""
    file = entry.get("file")
    if not isinstance(file, str):
        return True, "file unknown"
    path = root / file
    if not path.is_file():
        return True, "file absent"
    quote = entry.get("quote")
    if not isinstance(quote, str) or not quote:
        return False, "quote unavailable"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return True, "file unreadable"
    line = entry.get("line_start") if isinstance(entry.get("line_start"), int) else None
    return find_quote(lines, quote, line, line) is None, None


def diff(
    verified: dict[str, Any], baseline: dict[str, Any] | None, root: Path, today: str
) -> dict[str, Any]:
    """The ``diff.json`` document of spec 4.10."""
    status: dict[str, dict[str, Any]] = {}
    suppressed: list[dict[str, Any]] = []
    counts = {"new": 0, "unchanged": 0, "moved": 0, "edited": 0,
              "resolved": 0, "suppressed": 0, "expired": 0}
    matched: set[str] = set()
    for finding in verified.get("findings") or []:
        if not isinstance(finding, dict):
            continue
        fp = str(finding.get("fingerprint", ""))
        out = classify(finding, baseline, root, today)
        if out.matched:
            matched.add(out.matched)
        if out.suppressed_as:
            entry = baseline["findings"][out.matched] if baseline and out.matched else {}
            suppressed.append({"fingerprint": fp, "status": out.suppressed_as,
                               "reason": entry.get("reason") or ""})
            counts["suppressed"] += 1
            continue
        status[fp] = {"diff": out.diff, "note": out.note, "matched": out.matched}
        if out.note == "acceptance expired":
            counts["expired"] += 1
        counts[{"NEW": "new", "UNCHANGED": "unchanged", "UNCHANGED (moved)": "moved",
                "UNCHANGED (edited)": "edited"}[out.diff]] += 1
    if baseline is not None:
        for fp, entry in baseline["findings"].items():
            if fp in matched:
                continue
            gone, note = _resolved(entry, root)
            if gone:
                status[fp] = {"diff": "RESOLVED", "note": note, "matched": None}
                counts["resolved"] += 1
    return {"schema_version": SCHEMA_VERSION, "baseline_found": baseline is not None,
            "status": status, "suppressed": suppressed, "counts": counts}
```

Then the CLI: an `argparse` parser with subparsers `diff` and `record` (Task 3 fills `record`); `diff` takes `--workdir` (default `.tech-debt`), `--baseline` (default from `config["baseline"]`, resolved against the repository root, which is `--root` defaulting to `.`), and `--today` (default `date.today().isoformat()`). It reads `verified.json` from the workdir, writes `diff.json` there through `write_json`, prints the counts, and exits 2 with a message on a missing input or a `BaselineError`.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q`
Expected: PASS.

- [ ] **Step 5: Add `diff.json` to the chain goldens**

Extend `_chain` in `test_chain_goldens.py` to run `diff` with no baseline after `apply` and before `write_design`, writing `diff.json` into the workdir, and compare it against `tests/golden/<fixture>/diff.json`. Every fixture has no baseline, so every status is NEW and `baseline_found` is `false` — that is the correct golden and the point is that the chain now produces the file the renderer has been waiting for.

```bash
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q
```

Read one generated `diff.json` and confirm every finding in the fixture's `verified.json` appears in `status` as NEW, and nothing else moved. `design.md` must **not** move in this task: `_diff_for` already rendered `NEW` for an absent document and now renders `NEW` from a present one. If it moves, stop and report.

- [ ] **Step 6: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): baseline.py diff writes the document the renderer was waiting for

design_writer has loaded diff.json as an optional input since phase 3 and
rendered NEW for everything because nothing produced it. Now baseline.py
diff produces it: every current finding classified, every unmatched
baseline entry checked on disk and marked RESOLVED when its quote or its
file is gone, suppressed findings listed rather than statused, and an
expired acceptance counted. The chain goldens gain diff.json with every
status NEW, which is exactly right for a corpus with no baseline.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `baseline.py record` and the gitignore triple

**Confidence: 92%.** The only writer of a tracked file, and the only edit to a file the user owns. Both are guarded and both are tested against a real git repository.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/baseline.py`
- Modify: `skills/tech-debt-scan/tests/test_baseline.py`

**Interfaces:**
- Consumes: `load_baseline`, `inventory.write_json`, `redaction.redact`, `design_parser`'s finding dicts (`fingerprint`, `status`, `reason`, `until`, `family`, `title`, `tier`), `findings.json` entries (`fingerprint`, `evidence`, `quote_hash` from `verified.json`).
- Produces: `record(baseline_path, *, decisions, findings, bundles, today, preset) -> dict` returning the written document; `ensure_gitignore_triple(root, baseline_path) -> str` returning `"appended"`, `"present"` or `"no-git"`; the CLI `python scripts/baseline.py record --workdir <dir> --design <design.md> [--baseline <path>] [--today ...]`.

- [ ] **Step 1: Write the failing tests**

Append to `test_baseline.py`:

```python
import subprocess


def _git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".tech-debt/\n", encoding="utf-8")
    return tmp_path


def _decision(**over) -> dict:
    base = {"fingerprint": "aaaaaaaaaaaaaaaa", "status": "approved", "family": "error-masking",
            "title": "Empty catch swallows write failure", "tier": "A",
            "reason": None, "until": None}
    base.update(over)
    return base


class TestRecord:
    def test_writes_every_field_and_round_trips(self, tmp_path: Path) -> None:
        from baseline import load_baseline, record

        path = tmp_path / ".tech-debt" / "baseline.json"
        doc = record(path, decisions=[_decision(status="accepted", reason="tracked",
                                                until="2027-01-01")],
                     findings=[_finding()], bundles={}, today=TODAY, preset="balanced")
        entry = doc["findings"]["aaaaaaaaaaaaaaaa"]
        assert entry == {"family": "error-masking", "file": "src/pay/refund.py", "line_start": 33,
                         "quote_hash": "q" * 40, "quote": "except Exception:",
                         "title": "Empty catch swallows write failure", "tier": "A",
                         "status": "accepted", "first_seen": TODAY, "last_seen": TODAY,
                         "reason": "tracked", "until": "2027-01-01", "bundle": None}
        assert load_baseline(path) == doc

    def test_first_seen_survives_a_second_record(self, tmp_path: Path) -> None:
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        record(path, decisions=[_decision()], findings=[_finding()], bundles={},
               today="2026-09-01", preset="balanced")
        doc = record(path, decisions=[_decision()], findings=[_finding()], bundles={},
                     today=TODAY, preset="balanced")
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["first_seen"] == "2026-09-01"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["last_seen"] == TODAY

    def test_a_promoted_finding_records_its_bundle(self, tmp_path: Path) -> None:
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        doc = record(path, decisions=[_decision(status="promoted")], findings=[_finding()],
                     bundles={"aaaaaaaaaaaaaaaa": "chore-empty-catch-2026-09-07"},
                     today=TODAY, preset="balanced")
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["bundle"] == "chore-empty-catch-2026-09-07"

    def test_an_entry_absent_from_this_scan_is_kept(self, tmp_path: Path) -> None:
        """The baseline remembers decisions across scans; a finding the scan did
        not raise this time keeps its status."""
        from baseline import record

        path = tmp_path / ".tech-debt" / "baseline.json"
        record(path, decisions=[_decision(status="rejected", reason="by design")],
               findings=[_finding()], bundles={}, today="2026-09-01", preset="balanced")
        doc = record(path, decisions=[], findings=[], bundles={}, today=TODAY, preset="balanced")
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["status"] == "rejected"
        assert doc["findings"]["aaaaaaaaaaaaaaaa"]["last_seen"] == "2026-09-01"

    def test_an_unknown_status_raises(self, tmp_path: Path) -> None:
        from baseline import BaselineError, record

        with pytest.raises(BaselineError, match="status"):
            record(tmp_path / "b.json", decisions=[_decision(status="maybe")],
                   findings=[_finding()], bundles={}, today=TODAY, preset="balanced")

    def test_title_and_reason_are_redacted(self, tmp_path: Path) -> None:
        from baseline import record

        doc = record(tmp_path / "b.json",
                     decisions=[_decision(reason='see token = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"')],
                     findings=[_finding(title='key "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" leaks')],
                     bundles={}, today=TODAY, preset="balanced")
        blob = json.dumps(doc)
        assert "sk_live_51H8f2kL9mN3pQ7rS4tU6vW" not in blob
        assert "sk_l***" in blob

    def test_the_write_is_atomic(self, tmp_path: Path, monkeypatch) -> None:
        """A crash mid-write must leave the previous baseline intact."""
        import baseline as mod

        path = tmp_path / "b.json"
        mod.record(path, decisions=[_decision()], findings=[_finding()], bundles={},
                   today="2026-09-01", preset="balanced")
        before = path.read_bytes()

        def boom(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(mod.os, "replace", boom)
        with pytest.raises(mod.BaselineError):
            mod.record(path, decisions=[_decision(status="rejected")], findings=[_finding()],
                       bundles={}, today=TODAY, preset="balanced")
        assert path.read_bytes() == before


class TestGitignoreTriple:
    def test_appends_the_triple_once_and_the_baseline_becomes_tracked(self, tmp_path: Path) -> None:
        from baseline import ensure_gitignore_triple

        root = _git_repo(tmp_path)
        baseline = root / ".tech-debt" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/baseline.json"])
        assert ignored.returncode == 0, "precondition: the baseline starts ignored"

        assert ensure_gitignore_triple(root, baseline) == "appended"
        text = (root / ".gitignore").read_text(encoding="utf-8")
        assert text.endswith("!.tech-debt/\n.tech-debt/*\n!.tech-debt/baseline.json\n")
        tracked = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/baseline.json"])
        assert tracked.returncode == 1, "the baseline is no longer ignored"
        other = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", ".tech-debt/ranked.json"])
        assert other.returncode == 0, "every other workdir file stays ignored"

        assert ensure_gitignore_triple(root, baseline) == "present"
        assert (root / ".gitignore").read_text(encoding="utf-8") == text

    def test_creates_gitignore_when_absent(self, tmp_path: Path) -> None:
        from baseline import ensure_gitignore_triple

        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        baseline = tmp_path / ".tech-debt" / "baseline.json"
        baseline.parent.mkdir()
        baseline.write_text("{}", encoding="utf-8")
        # Not ignored to begin with, so nothing to do.
        assert ensure_gitignore_triple(tmp_path, baseline) == "present"

    def test_without_git_reports_no_git(self, tmp_path: Path, monkeypatch) -> None:
        import baseline as mod

        monkeypatch.setattr(mod.shutil, "which", lambda name: None)
        assert mod.ensure_gitignore_triple(tmp_path, tmp_path / "b.json") == "no-git"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q -k "Record or Gitignore"`
Expected: FAIL, `ImportError: cannot import name 'record'`.

- [ ] **Step 3: Write `record` and the triple**

Append to `baseline.py`:

```python
TRIPLE: Final[tuple[str, ...]] = ("!.tech-debt/", ".tech-debt/*", "!.tech-debt/baseline.json")
TRIPLE_COMMENT: Final[str] = "# tech-debt-scan: track the baseline, ignore the rest of the workdir"


def record(
    baseline_path: Path,
    *,
    decisions: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    bundles: dict[str, str],
    today: str,
    preset: str,
) -> dict[str, Any]:
    """Write every decision into the baseline and return the document (spec 4.10).

    ``decisions`` are the parsed design.md findings; ``findings`` the matching
    ``verified.json`` entries, which carry the file, line and quote the design
    document does not; ``bundles`` maps a promoted fingerprint to its bundle
    directory name. Entries absent from this scan are kept: the baseline
    remembers decisions across scans. The write is atomic so a crash mid-write
    leaves the previous baseline intact.
    """
    existing = load_baseline(baseline_path) or {"findings": {}}
    by_fp = {str(f.get("fingerprint")): f for f in findings if isinstance(f, dict)}
    out = dict(existing["findings"])
    for decision in decisions:
        fp = str(decision.get("fingerprint", ""))
        status = str(decision.get("status", ""))
        if status not in STATUSES:
            raise BaselineError(f"{fp}: unknown status {status!r}")
        finding = by_fp.get(fp, {})
        file, line = _primary(finding)
        quote = None
        evidence = finding.get("evidence") or []
        if evidence and isinstance(evidence[0], dict):
            quote = evidence[0].get("quote")
        previous = out.get(fp, {})
        out[fp] = {
            "family": decision.get("family") or finding.get("family"),
            "file": file,
            "line_start": line,
            "quote_hash": finding.get("quote_hash"),
            "quote": redact(quote) if isinstance(quote, str) else None,
            "title": redact(str(decision.get("title") or finding.get("title") or ""))[:120],
            "tier": decision.get("tier") or finding.get("tier"),
            "status": status,
            "first_seen": previous.get("first_seen") or today,
            "last_seen": today,
            "reason": redact(str(decision["reason"])) if decision.get("reason") else None,
            "until": decision.get("until"),
            "bundle": bundles.get(fp, previous.get("bundle")),
        }
    doc = {"schema_version": SCHEMA_VERSION, "last_scan": today, "preset": preset,
           "findings": dict(sorted(out.items()))}
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    temp = baseline_path.with_suffix(".json.tmp")
    try:
        write_json(temp, doc)
        os.replace(temp, baseline_path)
    except OSError as exc:
        temp.unlink(missing_ok=True)
        raise BaselineError(f"{baseline_path}: {exc}") from exc
    return doc


def ensure_gitignore_triple(root: Path, baseline_path: Path) -> str:
    """Append the triple once when git ignores the baseline (spec 4.10).

    Returns ``"appended"``, ``"present"`` (already tracked, or the triple is
    already there) or ``"no-git"``.
    """
    if shutil.which("git") is None:
        return "no-git"
    rel = baseline_path.resolve().relative_to(root.resolve()).as_posix()
    check = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", rel],
                           capture_output=True, check=False)
    if check.returncode != 0:
        return "present"
    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    lines = existing.splitlines()
    if all(line in lines for line in TRIPLE):
        return "present"
    block = "\n".join((TRIPLE_COMMENT, *TRIPLE)) + "\n"
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore.write_text(prefix + block, encoding="utf-8")
    return "appended"
```

`record`'s subcommand parses the design with `design_parser.parse_design`, reads `verified.json` for the findings, calls `record` then `ensure_gitignore_triple`, prints what it did (including `"appended the gitignore triple"` when it did), and exits 2 on `BaselineError`. `os`, `shutil`, `subprocess`, `find_quote`, `write_json` and `redact` are imported at the top of the module.

- [ ] **Step 4: Run to verify they pass, then mutation-check the triple**

Run: `python -m pytest skills/tech-debt-scan/tests/test_baseline.py -q`
Expected: PASS.

Then reorder the triple to `.tech-debt/*`, `!.tech-debt/`, `!.tech-debt/baseline.json` and confirm `test_appends_the_triple_once_and_the_baseline_becomes_tracked` fails — spec 4.10 says the order is load-bearing, and this proves it. Revert.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): baseline.py record writes decisions back, and tracks the file

record keeps every decision across scans -- a rejected finding the next scan
does not raise still stays rejected -- and writes atomically so a crash
mid-write leaves the previous baseline intact. Titles, reasons and quotes
are redacted before they are stored.

The gitignore triple is appended once, only when git says the baseline is
ignored, and a real repository proves it flips the file to tracked while
every other workdir file stays ignored. Reordering the three lines fails
the test, which is the point: spec 4.10's order is load-bearing.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: promote write-back and exit 6

**Confidence: 94%.** `promote` already has the result object, the counts and the reserved exit code; this task adds one flag, one call and one failure branch.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/promote.py`
- Modify: `skills/tech-debt-scan/tests/test_promote.py`

**Interfaces:**
- Consumes: `baseline.record`, `baseline.ensure_gitignore_triple`, `baseline.BaselineError`; `run_promote(design_path, *, out_root, force, date) -> PromoteResult` with `emitted_paths`.
- Produces: `--baseline <path>` on the CLI; `PromoteResult.wrote_back: bool`; `EXIT_WRITE_BACK` returned when `record` raises.

- [ ] **Step 1: Write the failing tests**

Append to `test_promote.py`, using whatever fixture helper the file already has for a v2 `design.md` with a workdir:

```python
class TestWriteBack:
    def test_without_baseline_flag_nothing_is_written(self, v2_design_workdir) -> None:
        from promote import _main

        design, workdir = v2_design_workdir
        assert _main([str(design), "--out", str(workdir / "pbis")]) == 0
        assert not (workdir / "baseline.json").exists()

    def test_with_baseline_flag_every_decision_is_recorded(self, v2_design_workdir) -> None:
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        baseline = workdir / "baseline.json"
        assert _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)]) == 0
        doc = load_baseline(baseline)
        assert doc is not None
        statuses = {e["status"] for e in doc["findings"].values()}
        assert "promoted" in statuses  # every approved finding was emitted, so is now promoted

    def test_an_emitted_finding_records_its_bundle_directory(self, v2_design_workdir) -> None:
        from baseline import load_baseline
        from promote import _main

        design, workdir = v2_design_workdir
        baseline = workdir / "baseline.json"
        _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(baseline)])
        doc = load_baseline(baseline)
        promoted = [e for e in doc["findings"].values() if e["status"] == "promoted"]
        assert promoted and all(e["bundle"] for e in promoted)
        assert all((workdir / "pbis" / e["bundle"]).is_dir() for e in promoted)

    def test_write_back_failure_is_exit_6_and_bundles_remain(self, v2_design_workdir, monkeypatch) -> None:
        import baseline as bmod
        from promote import EXIT_WRITE_BACK, _main

        design, workdir = v2_design_workdir

        def boom(*a, **k):
            raise bmod.BaselineError("simulated")

        monkeypatch.setattr(bmod, "record", boom)
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline",
                      str(workdir / "baseline.json")])
        assert code == EXIT_WRITE_BACK == 6
        assert any((workdir / "pbis").iterdir()), "bundles emitted before the write-back remain"

    def test_a_promote_failure_is_not_reported_as_write_back(self, v2_design_workdir) -> None:
        """Exit 6 means the write-back failed and nothing else did."""
        from promote import EXIT_WRITE_BACK, _main

        design, workdir = v2_design_workdir
        # A second run without --force hits the already-promoted path, which is not exit 6.
        _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(workdir / "b.json")])
        code = _main([str(design), "--out", str(workdir / "pbis"), "--baseline", str(workdir / "b.json")])
        assert code != EXIT_WRITE_BACK
```

If no such fixture exists, write `v2_design_workdir` in `conftest.py` or beside the tests: it copies a corpus fixture's `design.md`, `verified.json` and `findings.json` goldens into `tmp_path`, edits one finding's status to `approved`, and yields `(design_path, workdir)`.

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL — `--baseline` is an unrecognised argument.

- [ ] **Step 3: Wire the write-back**

In `promote.py`: add `--baseline` (type `Path`, default `None`) to the parser. After `run_promote` returns, when `--baseline` was given and `result.exit_code == 0`: derive the decisions by re-parsing the design (statuses as edited, with every finding in `emitted_paths` promoted to `promoted`), read `verified.json` from the design's directory for the findings, build `bundles` from `emitted_paths`, call `baseline.record(...)` then `baseline.ensure_gitignore_triple(...)`, and print the outcome. Wrap the write-back in `try/except BaselineError`: print the error to stderr, keep the counts line, and return `EXIT_WRITE_BACK`. The docstring's "no code path returns it yet" sentence goes.

A v1 `design.md` has no fingerprints; with `--baseline`, `promote` reports that a v1 document cannot be written back and returns 2 before emitting anything, because a baseline without fingerprints is worse than none.

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_promote.py -q`
Expected: PASS, and the existing v1-still-promotes test still passes byte-identically.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): promote writes decisions back to the baseline

--baseline records every finding's edited status, and marks each emitted
one promoted with its bundle directory, then appends the gitignore triple
if the baseline is ignored. Exit 6, reserved since phase 3, is returned
only when the write-back itself failed: the bundles already on disk remain
and the counts are still printed, so a write-back failure cannot be
mistaken for a promote failure.

A v1 design.md has no fingerprints and is refused with --baseline before
anything is emitted; without the flag it promotes exactly as before.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: the frontmatter counts and suppressed findings

**Confidence: 93%.** Two small renderer changes against a document that already exists, moving every `design.md` golden by two frontmatter lines.

**Files:**
- Modify: `skills/tech-debt-scan/scripts/design_writer.py`
- Modify: `skills/tech-debt-scan/tests/test_design_writer.py`, `test_chain_goldens.py`

**Interfaces:**
- Consumes: `inputs.diff` — the `diff.json` document of Task 2.
- Produces: frontmatter `counts.new` and `counts.resolved` from `diff.counts`; `counts.suppressed` includes baseline suppressions; a finding listed in `diff.suppressed` is omitted from the document body.

- [ ] **Step 1: Write the failing tests**

Add to `test_design_writer.py`, driving `write_design` with an `inputs.diff` constructed in the test:

```python
class TestDiffInFrontmatter:
    def test_new_and_resolved_counts_come_from_the_diff(self, render_inputs) -> None:
        from design_writer import write_design

        inputs = render_inputs(diff={"schema_version": 2, "baseline_found": True,
                                     "status": {}, "suppressed": [],
                                     "counts": {"new": 3, "unchanged": 1, "moved": 0, "edited": 0,
                                                "resolved": 2, "suppressed": 0, "expired": 0}})
        text = write_design(inputs, inputs.workdir / "design.md").read_text(encoding="utf-8")
        assert "  new: 3\n" in text
        assert "  resolved: 2\n" in text

    def test_without_a_diff_document_the_counts_are_omitted_as_before(self, render_inputs) -> None:
        from design_writer import write_design

        inputs = render_inputs(diff=None)
        text = write_design(inputs, inputs.workdir / "design.md").read_text(encoding="utf-8")
        assert "  new:" not in text
        assert "  resolved:" not in text

    def test_a_suppressed_finding_is_not_in_the_body_but_is_counted(self, render_inputs) -> None:
        from design_parser import parse_design
        from design_writer import write_design

        inputs = render_inputs()
        victim = inputs.verified["findings"][0]["fingerprint"]
        inputs = render_inputs(diff={"schema_version": 2, "baseline_found": True, "status": {},
                                     "suppressed": [{"fingerprint": victim, "status": "rejected",
                                                     "reason": "by design"}],
                                     "counts": {"new": 0, "unchanged": 0, "moved": 0, "edited": 0,
                                                "resolved": 0, "suppressed": 1, "expired": 0}})
        out = write_design(inputs, inputs.workdir / "design.md")
        parsed = parse_design(out)
        assert victim not in {f["fingerprint"] for f in parsed["findings"]}
        assert "  suppressed: 1\n" in out.read_text(encoding="utf-8")
```

`render_inputs` is whatever helper `test_design_writer.py` already uses to build a `RenderInputs` from a fixture; give it a `diff` keyword if it lacks one.

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL on the first assertion of each — the counts are not rendered and the suppressed finding is still in the body.

- [ ] **Step 3: Render the counts and drop suppressed findings**

In `design_writer.py`: where the frontmatter `counts` block is built, add `new` and `resolved` from `inputs.diff["counts"]` when a diff document is present, and add the diff's `suppressed` count to the existing `suppressed` count. Where findings are gathered for the body, exclude any fingerprint in `inputs.diff["suppressed"]`. Update the module docstring's account of what `diff.json` contributes.

- [ ] **Step 4: Run the tests, regenerate the design goldens, and read one**

```bash
python -m pytest skills/tech-debt-scan/tests/test_design_writer.py -q
UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests -q
python -m pytest skills/tech-debt-scan/tests -q
```

Every corpus `design.md` moves by two lines — `new: <n>` equal to the finding count and `resolved: 0` — because Task 2 gave every fixture a `diff.json`. Read one and confirm exactly those two lines changed. `design-worked-example.md` has no diff document and must not move.

- [ ] **Step 5: Run the gate and commit**

```bash
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
git add skills/tech-debt-scan
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): the report counts new and resolved, and hides suppressed findings

Phase 3 omitted the new and resolved counts because nothing produced
diff.json. It exists now, so the frontmatter carries both, the suppressed
count includes baseline suppressions, and a finding a human rejected or
accepted last time is left out of the body rather than shown again with a
status it already has.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: SKILL.md step 11, the `--baseline` flag, and the documents

**Confidence: 94%.** The step list is machine-checked; the prose is not, and the prose is what tells a user their `.gitignore` is about to be edited.

**Files:**
- Modify: `skills/tech-debt-scan/SKILL.md`, `docs/architecture.md`, `README.md`
- Modify: `docs/research/tech-debt-scan-v2/06-design-brainstorm.md` (one line)

- [ ] **Step 1: Read the real flags**

```bash
python skills/tech-debt-scan/scripts/baseline.py --help
python skills/tech-debt-scan/scripts/baseline.py diff --help
python skills/tech-debt-scan/scripts/baseline.py record --help
python skills/tech-debt-scan/scripts/promote.py --help
```

Every flag documented must appear in that output.

- [ ] **Step 2: Insert step 11 where the numbering has held it open**

Spec section 5 gives the line: `python scripts/baseline.py diff --workdir .tech-debt --baseline .tech-debt/baseline.json` writes `diff.json`; an absent baseline marks everything NEW. Do not renumber anything.

Add `--baseline .tech-debt/baseline.json` to the promote step, and state in one sentence beside it that the write-back may append three lines to the repository's `.gitignore` so the baseline is tracked, and what those lines do. A user should not discover that from a diff.

- [ ] **Step 3: The documents**

`docs/architecture.md` and `README.md`: describe `baseline.py`'s two subcommands, the five classifications with one sentence on the edited heuristic and its note, suppression and expiry, the gitignore triple, and exit 6's meaning. Remove any statement that `diff: NEW` is unconditional or that exit 6 is reserved.

`docs/research/tech-debt-scan-v2/06-design-brainstorm.md:624` still says a repository with tools installed "earns" tier A — the wording spec 11 replaced. It is a superseded document; add one line at its head saying so and pointing at the spec, rather than editing its history.

- [ ] **Step 4: Sweep and gate**

Every command, flag, path, exit code and step count in the three documents checked against the code at HEAD.

```bash
python skills/tech-debt-scan/scripts/skill_check.py
python -m ruff check .
python -m mypy
python -m pytest -q
git add skills/tech-debt-scan/SKILL.md docs
git commit -m "$(cat <<'EOF'
feat(tech-debt-scan): SKILL.md step 11 diffs against the baseline, promote writes back

Step 11 lands in the gap the numbering has held open since phase 3, and
the promote step gains --baseline with one sentence saying the write-back
may append three lines to the repository's .gitignore and why. The
documents describe the five classifications, the one heuristic among
them and its note, suppression and expiry, and what exit 6 means now that
something returns it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: the end-to-end re-scan test and the gate

**Confidence: 92%.** The one test that exercises the phase's promise as a sequence — scan, decide, re-scan — rather than as parts. Its risk is fixture plumbing, not logic.

**Files:**
- Modify: `skills/tech-debt-scan/tests/test_e2e.py`

- [ ] **Step 1: Write the re-scan test**

Using the canned chain the e2e test already drives over `service-py`:

1. Run the chain to `design.md` with no baseline; assert every finding renders `diff: NEW`.
2. Edit the document: mark one finding `rejected` with a reason, one `accepted` with `until` a year ahead, one `approved`. Run `promote --baseline`. Assert exit 0, the bundle exists, and the baseline holds three entries with those statuses, the approved one now `promoted`.
3. Run `baseline.py diff` with the same `verified.json` and today's pinned date; render again. Assert the rejected and accepted findings are absent from the body and counted as `suppressed: 2`, the promoted one renders `diff: UNCHANGED`, and every other finding is `UNCHANGED`.
4. Run `diff` again with `--today` set past the acceptance's `until`. Assert the accepted finding is back in the body with `note: acceptance expired` and `expired: 1`.
5. Delete the rejected finding's evidence file from the fixture copy and run `diff` once more. Assert its entry is `RESOLVED` with `note: file absent` — a rejected finding whose code is gone is resolved, not suppressed, so the baseline can be pruned.

Each step asserts on the rendered document or the written JSON, never on internal state.

- [ ] **Step 2: Run it, then the full gate**

```bash
python -m pytest skills/tech-debt-scan/tests/test_e2e.py -q
python -m ruff check .
python -m mypy
python skills/tech-debt-scan/scripts/skill_check.py
python -m pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add skills/tech-debt-scan/tests/test_e2e.py
git commit -m "$(cat <<'EOF'
test(tech-debt-scan): a scan, a decision and a re-scan, end to end

The phase's promise as a sequence rather than as parts: a rejected finding
stops recurring, an accepted one returns when its expiry passes, a
promoted one reads UNCHANGED, and a rejected finding whose file is gone is
RESOLVED rather than suppressed, so the baseline can be pruned.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review

**Spec coverage.** 4.10's schemas and five classifications: Tasks 1 and 2. Suppression, expiry and the expired note: Task 1, counted in Task 2, rendered in Task 5. RESOLVED on disk: Task 2. `record` round-tripping `reason` and `until`: Task 3. The triple, appended once, order load-bearing, `check-ignore` confirming: Task 3. Promote write-back and exit 6: Task 4. 4.11's `new` and `resolved` counts: Task 5. Section 5's step 11 and the `--baseline` flag: Task 6. Section 8's v1 compatibility: Task 4 refuses a v1 document only under `--baseline` and its existing byte-identical test stays. Section 11's 5a gate: Tasks 1–4 and 7. Nothing in 5a is unassigned.

**Deliberately out of scope**, as 5b: every corpus repair, the `sources` list on decoys, the zero-churn file, the note agent in the live harness, the live run, and setting the bar.

**One deviation from the spec's schema, recorded.** The baseline entry carries `quote` beside `quote_hash`. Spec 4.10's schema lists only the hash, but RESOLVED has to search the file for the text and a hash cannot be searched. `record` writes both; `load_baseline` accepts an entry without `quote`, and `diff` then treats it as RESOLVED only when its file is absent, noting `quote unavailable`. Task 6 adds the field to the spec's schema block.

**Placeholder scan.** Task 4's fixture and Task 5's `render_inputs` are named as "whatever the file already has, or write it" — both files have such helpers today, and the step says what to write if not. Every other step carries its code.

**Type consistency.** `Classification(diff, matched, note, suppressed_as)` is defined in Task 1 and read only in Task 2. `record(baseline_path, *, decisions, findings, bundles, today, preset) -> dict` is defined in Task 3 and called in Task 4 with exactly those keywords. `ensure_gitignore_triple(root, baseline_path) -> str` returns one of three strings, matched in Task 3's tests and printed in Task 4. `diff(verified, baseline, root, today) -> dict` is called by the CLI in Task 2 and by the chain test.
