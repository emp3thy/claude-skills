# tech-debt-scan v2 Phase 2 (detect, verify, rank) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the detect, verify, rank chain (`plan_scan.py`, `merge_findings.py`, `verify_prompts.py`, `apply_verdicts.py`, `rank.py`) on top of the phase 1 signals, prove it with real Claude scouts and verifiers through a `claude -p` harness over the three-fixture corpus, and leave `/tech-debt-scan` running v1 until phase 3.

**Architecture:** Every stage is a direct-path Python script that reads and writes pinned files under `--workdir`. `plan_scan.py` renders one prompt per family from `categories.py` v2 blocks plus a leads block, and writes `scan-plan.json`. Scouts (LLM) write `scouts/<family>.json`; `merge_findings.py` verifies every quote on disk, fingerprints, clusters and corroborates into `candidates.json`; `verify_prompts.py` selects a budgeted subset into `prompts/verify-<nn>.md`; verifiers (LLM) write `verdicts/verify-<nn>.json`; `apply_verdicts.py` earns tiers into `verified.json`; `rank.py` orders deterministically into `ranked.json`; `evaluate.py` scores against `planted.json`. `live_run.py` drives the whole chain with real agents through `claude -p` and appends a row to `docs/evaluation-log.md`; its first run produces the CI goldens.

**Tech Stack:** Python 3.11+, pyyaml (only runtime dependency), pytest, ruff, mypy strict, the Claude Code CLI (`claude -p`) for the live harness only.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` (binding). Sections 2.3 (family table, verifier questions, tier caps), 2.4 (sets, adaptive rule), 4.6 to 4.9 (the four scripts and their contracts), 6 (goldens, live policy), 11 (phase 2 scope). Amended in this branch at 016178d and fb477c2 for the categories.py coexistence, the island churn floor, the plan_scan set forms, targeted goldens and the live harness.

**Branch:** `feat/tech-debt-scan-v2-phase-2`, already created off `main` (f672ba6) and checked out in the main checkout at `C:/Users/gethi/source/claude-skills` (no linked worktree: the standards doc records Windows worktree-removal hazards).

## Global Constraints

Copied from spec sections 0, 3.3 and 5; every task's requirements include these.

- Python 3.11+ (`requires-python = ">=3.11"`); CI matrix runs 3.11 and 3.12. pyyaml is the only runtime dependency; every new script uses the standard library plus `yaml`.
- Every script is direct-path invocable as `python scripts/<name>.py` from `skills/tech-debt-scan/`; sibling imports are flat top-level imports (`from config import load_config`), never package imports. `mypy_path` and `tests/conftest.py` already resolve them.
- Every v2 script accepts `--workdir` (default `.tech-debt`) and reads and writes the pinned file names inside it. No file list ever appears on a command line.
- Rendered output is LF-only: JSON through `inventory.write_json` (`write_bytes` of `json.dumps(doc, indent=2) + "\n"`); Markdown prompts through `write_bytes(text.encode("utf-8"))`.
- JSON keys are emitted in the spec's pinned order (4.6 to 4.9); tests pin the order with `list(doc)` assertions.
- Git and tool calls run with `timeout=120` and return a null result on failure; a missing optional signal never aborts a scan. `claude -p` calls in `live_run.py` run with a per-call timeout of 900 s and are the one external process the phase adds; they never run in CI.
- Language-agnostic rule (spec 0(d), 3.3): the extension map in `inventory.py` is the only language-aware table; any per-language branch anywhere else is a defect. `test_no_script_branches_on_a_language_name` already globs every script.
- No live LLM in tests; the `live` pytest marker never runs in CI (`addopts = "-m 'not live'"`).
- Gate for every task and for the PR, from the repository root: `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q`; all green.
- Windows-safe argv: every subprocess call is a list, never a shell string; paths are forward-slashed in output.
- Docs ship with code (spec 0(c)): `docs/architecture.md` script table and `README.md` "Output formats" table gain a row for every new script and output in the same task that lands it; `SKILL.md` is untouched until phase 3.
- Commit trailers: every `git commit` in this plan ends its message with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` (pass a second `-m` or a heredoc body); the task steps show only the subject line.
- `/tech-debt-scan` and `/tech-debt-promote` keep running v1: `categories.py` keeps `CATEGORY_PROMPTS`, `CATEGORIES`, `CORE_CATEGORIES` and `get_prompt`; `build_synthesis_prompt.py`, `design_writer.py` and `test_e2e.py` are untouched.

## Guardrails (from project memory and standards)

- [[keep-docs-in-sync]] (confidence 0.95, useful 28x): the README and architecture rows for each new script land in the same commit as the script; every token in a rewritten doc line is verified against the code; module docstrings enumerate what the module reads and writes.
- [[redaction-invariant]] (phase 1 lesson, recorded 2026-09-05): every script that writes a quote passes it through `redaction.redact`; in this phase that is `merge_findings.py` (every candidate quote) and `verify_prompts.py` (every rendered span).
- [[field-split-readers]] (phase 1 follow-up lesson): when a plan introduces a new field beside an old one, it names every reader of the old field and says which one each reader now uses. Task 1 moves `fingerprint` and `_signals`; the task lists both readers.
- [[verify-red-is-red]] (confidence 0.75): every RED step below names the exact failure expected; where an earlier layer could already satisfy the assertion, the step says so.
- [[live-harness-isolation]] (verified this session): `claude -p` inside a Claude Code session must run with `--setting-sources project --strict-mcp-config --disable-slash-commands` so user hooks cannot hijack the result; `--bare` fails auth on this machine. Task 9 pins the argv.
- Dismissed: worktree-on-Windows hazards (no worktree used); mkstemp/fdopen (no temp files opened by fd); TypeScript Partial (no TypeScript); Playwright textContent (no browser tests).

## File structure

| File | Task | Responsibility |
|---|---|---|
| `skills/tech-debt-scan/scripts/evidence.py` | 1 | leaf module: `fingerprint`, `normalise_quote`, `find_quote`, `signals_for` shared by `rules.py`, `merge_findings.py`, `verify_prompts.py`, `rank.py` |
| `skills/tech-debt-scan/scripts/rules.py` | 1, 2 | imports the two helpers from `evidence.py`; island churn floor; CODEOWNERS guard |
| `skills/tech-debt-scan/scripts/config.py` | 2 | `rules.ownership.island_min_churn: 2` |
| `skills/tech-debt-scan/scripts/categories.py` | 3 | v1 symbols kept; v2 `FAMILIES`, `FAMILY_BLOCKS`, `render_scout_prompt`, `SCOUT_OUTPUT_SCHEMA` |
| `skills/tech-debt-scan/scripts/plan_scan.py` | 4 | adaptive rule, leads block, prompt rendering, `scan-plan.json` |
| `skills/tech-debt-scan/scripts/merge_findings.py` | 5 | validation, quote verification, fingerprint, cluster, corroboration, suppressions, `candidates.json` |
| `skills/tech-debt-scan/scripts/verify_prompts.py` | 6 | budget rule, batching, context extraction, traps, `verify-plan.json`, `prompts/verify-<nn>.md`, `VERDICT_SCHEMA` |
| `skills/tech-debt-scan/scripts/apply_verdicts.py` | 7 | verdict join, tier table, family caps, `verified.json` |
| `skills/tech-debt-scan/scripts/rank.py` | 8 | formula, presets, spread cap, `ranked.json` |
| `skills/tech-debt-scan/scripts/live_run.py` | 9 | replay, signal scripts, `claude -p` dispatch, chain, evaluate, log row |
| `docs/evaluation-log.md` | 9, 10 | dated rows from live runs |
| `skills/tech-debt-scan/tests/golden/<fixture>/` | 10 | `scouts/*.json`, `verdicts/*.json`, `candidates.json`, `verify-plan.json`, `verified.json`, `ranked.json` per fixture |
| `skills/tech-debt-scan/tests/test_evidence.py`, `test_categories.py`, `test_plan_scan.py`, `test_merge_findings.py`, `test_verify_prompts.py`, `test_apply_verdicts.py`, `test_rank.py`, `test_live_run.py`, `test_chain_goldens.py`, `test_rules.py` | 1 to 10 | one test module per script; the golden chain test runs the whole chain per fixture |
| `docs/architecture.md`, `README.md` | 4 to 9, 11 | script table and output-format rows |

## Task overview and confidence

| Task | Deliverable | Confidence |
|---|---|---|
| 1 | `evidence.py` leaf module; `rules.py` imports it | 97% |
| 2 | island churn floor, CODEOWNERS guard, namespace pin | 95% |
| 3 | `categories.py` v2 blocks and renderer; `test_categories.py` v2 | 92% |
| 4 | `plan_scan.py` | 91% |
| 5 | `merge_findings.py` | 92% |
| 6 | `verify_prompts.py` | 91% |
| 7 | `apply_verdicts.py` | 94% |
| 8 | `rank.py` | 94% |
| 9 | `live_run.py` with a fake-`claude` test | 91% |
| 10 | first live run, goldens, golden chain test | 90% |
| 11 | docs sweep, second live run as the gate, PR | 95% |

Every task at or above 90 percent after the mitigations embedded in its text (Tasks 4, 6, 9 and 10 name theirs).

---

### Task 1: `evidence.py`, the shared leaf module

**Files:**
- Create: `skills/tech-debt-scan/scripts/evidence.py`
- Modify: `skills/tech-debt-scan/scripts/rules.py` (delete `fingerprint` at lines 125-130 and `_signals` at lines 627-650; import both from `evidence`)
- Test: `skills/tech-debt-scan/tests/test_evidence.py`

**Interfaces:**
- Produces: `fingerprint(family: str, path: str, quote: str) -> tuple[str, str]` (unchanged behaviour: `sha1(family|path|sha1(normalised quote))[:16]` and the inner hash); `normalise_quote(text: str) -> str` (whitespace runs collapsed to one space, stripped); `find_quote(lines: Sequence[str], quote: str, line_start: int | None, line_end: int | None, *, max_lines: int = 6) -> tuple[int, int] | None` (1-based inclusive range where the normalised quote is found: first at the cited range, then anywhere); `signals_for(inventory: dict[str, Any], path: str | None) -> dict[str, Any]` (the 4.7 `signals` object: `hotspot_score`, `churn`, `coupling_degree`, `fan_in_approx`, `path_class`, `in_hotspot_band`, from the file entry, else the artefact entry's `path_class`, else the null shape).
- Readers of the moved symbols: `rules.py` (`_candidate` calls `fingerprint`; `_candidate` calls `_signals`, renamed to `signals_for`). No other module imports either today (`grep -rn "fingerprint\|_signals" scripts/` returns `rules.py` only).

**Confidence:** 97% (pure moves plus two new pure functions; the fingerprint test pins the existing rule-findings golden values so a behaviour change would fail).

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_evidence.py`:

```python
"""evidence.py: fingerprint, quote normalisation and search, inventory signals (spec 4.7)."""
from __future__ import annotations

from typing import Any

from evidence import find_quote, fingerprint, normalise_quote, signals_for


def test_fingerprint_matches_the_phase_1_rule_findings_shape() -> None:
    fp, quote_hash = fingerprint("pipeline-infra", "Dockerfile", "FROM alpine")
    assert len(fp) == 16 and len(quote_hash) == 40
    assert fingerprint("pipeline-infra", "Dockerfile", "FROM   alpine ") == (fp, quote_hash)
    assert fingerprint("security", "Dockerfile", "FROM alpine")[0] != fp


def test_normalise_quote_collapses_whitespace() -> None:
    assert normalise_quote("  a \t b\n\n c ") == "a b c"


def test_find_quote_prefers_the_cited_range_then_anywhere() -> None:
    lines = ["x = 1", "try:", "    pass", "except Exception:", "    pass", "y = 2", "try:", "    pass"]
    assert find_quote(lines, "except Exception:\n    pass", 4, 5) == (4, 5)
    assert find_quote(lines, "except Exception:  pass", 1, 2) == (4, 5)
    assert find_quote(lines, "try:\n    pass", 7, 8) == (7, 8)
    assert find_quote(lines, "try:\n    pass", None, None) == (2, 3)
    assert find_quote(lines, "not here", 1, 1) is None
    assert find_quote(lines, "", 1, 1) is None


def test_signals_for_reads_files_then_artefacts_then_null_shape() -> None:
    inventory: dict[str, Any] = {
        "hotspot_band": ["a.py"],
        "files": [{"path": "a.py", "hotspot_score": 0.5, "churn": 3, "coupling_degree": 1,
                   "fan_in_approx": 2, "path_class": "source"}],
        "artefacts": {"ci": [{"path": ".github/workflows/ci.yml", "path_class": "source"}]},
    }
    assert signals_for(inventory, "a.py") == {
        "hotspot_score": 0.5, "churn": 3, "coupling_degree": 1, "fan_in_approx": 2,
        "path_class": "source", "in_hotspot_band": True,
    }
    assert signals_for(inventory, ".github/workflows/ci.yml")["path_class"] == "source"
    assert signals_for(inventory, ".github/workflows/ci.yml")["in_hotspot_band"] is False
    assert signals_for(inventory, None) == {
        "hotspot_score": 0.0, "churn": 0, "coupling_degree": 0, "fan_in_approx": None,
        "path_class": None, "in_hotspot_band": False,
    }
    assert list(signals_for(inventory, "a.py")) == [
        "hotspot_score", "churn", "coupling_degree", "fan_in_approx", "path_class", "in_hotspot_band",
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_evidence.py -q`
Expected: `ModuleNotFoundError: No module named 'evidence'` at collection.

- [ ] **Step 3: Write `evidence.py`**

```python
"""Evidence helpers shared by every script that fingerprints, verifies or scores a quote.

A leaf module (standard library only, no sibling imports) so ``rules.py``,
``merge_findings.py``, ``verify_prompts.py``, ``rank.py`` and phase 5's
``baseline.py`` can import it without pulling in each other's tables.

``fingerprint`` is spec 4.7 step 4; ``find_quote`` is step 3 (cited range first,
then anywhere in the file, whitespace-normalised); ``signals_for`` is step 6.
"""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

SIGNAL_KEYS: tuple[str, ...] = (
    "hotspot_score", "churn", "coupling_degree", "fan_in_approx", "path_class", "in_hotspot_band",
)


def normalise_quote(text: str) -> str:
    """Collapse every whitespace run to one space and strip the ends."""
    return " ".join(text.split())


def fingerprint(family: str, path: str, quote: str) -> tuple[str, str]:
    """Spec 4.7: sha1(family|path|sha1(normalised quote))[:16] and the inner hash."""
    quote_hash = hashlib.sha1(normalise_quote(quote).encode("utf-8")).hexdigest()
    outer = hashlib.sha1(f"{family}|{path}|{quote_hash}".encode()).hexdigest()
    return outer[:16], quote_hash


def _window_matches(lines: Sequence[str], start: int, end: int, wanted: str) -> bool:
    return normalise_quote("\n".join(lines[start - 1:end])) == wanted


def find_quote(
    lines: Sequence[str],
    quote: str,
    line_start: int | None,
    line_end: int | None,
    *,
    max_lines: int = 6,
) -> tuple[int, int] | None:
    """1-based inclusive range holding ``quote`` after whitespace normalisation.

    The cited range is tried first (so a quote that is genuinely there keeps
    its line numbers); otherwise every window of 1 to ``max_lines`` lines is
    tried from the top, and the first match is the real range.
    """
    wanted = normalise_quote(quote)
    if not wanted:
        return None
    total = len(lines)
    if line_start is not None and line_end is not None:
        start, end = max(1, line_start), min(total, max(line_start, line_end))
        if start <= end and _window_matches(lines, start, end, wanted):
            return start, end
    span = min(max_lines, max(1, quote.count("\n") + 1))
    for width in range(1, span + 1):
        for start in range(1, total - width + 2):
            if _window_matches(lines, start, start + width - 1, wanted):
                return start, start + width - 1
    return None


def signals_for(inventory: dict[str, Any], path: str | None) -> dict[str, Any]:
    """The 4.7 ``signals`` object for ``path``: file entry, else artefact entry, else nulls."""
    signals: dict[str, Any] = {
        "hotspot_score": 0.0, "churn": 0, "coupling_degree": 0, "fan_in_approx": None,
        "path_class": None, "in_hotspot_band": False,
    }
    if path is None:
        return signals
    for entry in inventory.get("files", []):
        if entry.get("path") == path:
            signals["hotspot_score"] = entry.get("hotspot_score", 0.0)
            signals["churn"] = entry.get("churn", 0)
            signals["coupling_degree"] = entry.get("coupling_degree", 0)
            signals["fan_in_approx"] = entry.get("fan_in_approx")
            signals["path_class"] = entry.get("path_class")
            signals["in_hotspot_band"] = path in inventory.get("hotspot_band", [])
            return signals
    for entries in (inventory.get("artefacts") or {}).values():
        for artefact in entries:
            if artefact.get("path") == path:
                signals["churn"] = artefact.get("churn", 0)
                signals["path_class"] = artefact.get("path_class")
                return signals
    return signals
```

- [ ] **Step 4: Point `rules.py` at the leaf module**

In `rules.py`: add `from evidence import fingerprint, signals_for` beside the other flat imports; delete the `fingerprint` function (lines 125-130) and `_signals` (lines 627-650); in `_candidate` replace `_signals(inventory, path)` with `signals_for(inventory, path)`. Remove the now-unused `hashlib` import if nothing else uses it (`grep -n hashlib rules.py`). Keep the module docstring sentence that describes fingerprints, pointing at `evidence.py`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_evidence.py skills/tech-debt-scan/tests/test_rules.py -q`
Expected: all pass; the existing rule-findings fingerprint assertions in `test_rules.py` are unchanged because `fingerprint` normalises identically.

- [ ] **Step 6: Lint, type-check, commit**

Run the gate. Commit:

```
refactor(tech-debt-scan): move fingerprint and signals into evidence.py
```

---
### Task 2: island churn floor, CODEOWNERS guard, namespace pin

**Files:**
- Modify: `skills/tech-debt-scan/scripts/config.py` (`DEFAULTS["rules"]["ownership"]`)
- Modify: `skills/tech-debt-scan/scripts/rules.py` (`_band_hits` lines 531-566, `_ownership_hits` lines 569-596)
- Modify: `skills/tech-debt-scan/tests/test_rules.py`, `skills/tech-debt-scan/tests/test_patterns.py`
- Modify: `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` is already amended (4.1, 4.4); `docs/architecture.md` `rules.py` row gains the floor.

**Interfaces:**
- Consumes: `_disabled(artefact)` from `rules.py` (True for a disabled path class or `skipped_large`); `ARTEFACT_SCAN_CLASSES` from `patterns.py`; `PATH_CLASS_GLOBS` keys from `inventory.py` (`grep -n "PATH_CLASS_GLOBS" inventory.py` for the exact name; if the constant is named differently use that name, the test reads it by import).
- Produces: config key `rules.ownership.island_min_churn` (default 2).

**Confidence:** 95% (three small guarded changes against code read at plan time; the service-py corpus already pins ownership recall and the `_disabled` helper exists).

- [ ] **Step 1: Write the failing tests**

Append to `skills/tech-debt-scan/tests/test_rules.py` (reuse the file's `build_all` and `run_rules` imports and its `_run`/`_at` helpers; `now` is the injectable date the file already passes):

```python
def test_island_needs_the_churn_floor(service_py_repo: Path) -> None:
    """A hotspot-band file with one author but churn below island_min_churn is not an island."""
    from copy import deepcopy

    from config import DEFAULTS
    inventory, _ = build_all(service_py_repo, churn_months=240)
    islands_default = [
        f for f, _ in _run(service_py_repo, inventory) if f["rule_id"] == "ownership.knowledge-island"
    ]
    strict = deepcopy(DEFAULTS)
    strict["rules"]["ownership"]["island_min_churn"] = 10_000
    findings, _ = run_rules(service_py_repo, inventory, strict, now=NOW)
    assert islands_default, "the corpus must plant at least one island"
    assert [f for f in findings if f["rule_id"] == "ownership.knowledge-island"] == []
    lax = deepcopy(DEFAULTS)
    lax["rules"]["ownership"]["island_min_churn"] = 0
    findings_lax, _ = run_rules(service_py_repo, inventory, lax, now=NOW)
    assert len([f for f in findings_lax if f["rule_id"] == "ownership.knowledge-island"]) >= len(islands_default)


def test_codeowners_under_a_disabled_tree_or_skipped_large_is_not_consulted(tmp_path: Path) -> None:
    """The unowned-hotspot check only reads a CODEOWNERS the inventory would read."""
    import json

    from config import DEFAULTS
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "CODEOWNERS").write_text("* @team\n", encoding="utf-8")
    inventory, _ = build_all(repo)
    inventory["git_available"] = True
    inventory["git"] = {"authors": [
        {"email": f"u{i}@x", "name": f"u{i}", "commits": 1, "last_active": "2026-01-01"}
        for i in range(3)
    ]}
    inventory["hotspot_band"] = ["src/a.py"]
    governance = inventory["artefacts"]["governance"]
    assert [a["path"] for a in governance] == ["CODEOWNERS"]
    governance[0]["skipped_large"] = True
    findings, _ = run_rules(repo, inventory, DEFAULTS, now=NOW)
    rules = {f["rule_id"] for f in findings}
    assert "ownership.unowned-hotspot" not in rules
    assert "ownership.no-codeowners" not in rules, json.dumps(findings, indent=1)
```

Add `NOW` at module top if the file does not already define it: `NOW = datetime(2026, 9, 1, tzinfo=UTC)` (check the existing tests for the date they pass and reuse that constant name).

Append to `skills/tech-debt-scan/tests/test_patterns.py`:

```python
def test_artefact_and_path_class_namespaces_stay_disjoint() -> None:
    """ScanFile.scope keys rule scope on the artefact class; path_class is the inventory's.

    The two names must never collide, or a rule scoped to an artefact class would
    also match a code file whose path class carried that name.
    """
    from inventory import PATH_CLASS_GLOBS

    path_classes = set(PATH_CLASS_GLOBS) | {"source"}
    assert set(ARTEFACT_SCAN_CLASSES).isdisjoint(path_classes)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_rules.py -k "churn_floor or codeowners_under" skills/tech-debt-scan/tests/test_patterns.py -k namespaces -q`
Expected: the churn-floor test fails with `KeyError: 'island_min_churn'` (or islands still present at 10_000); the CODEOWNERS test fails because `ownership.unowned-hotspot` fires on an empty pattern list; the namespace test passes already (it is a pin, not a red step; say so in the report).

- [ ] **Step 3: Implement**

`config.py`: in `DEFAULTS["rules"]["ownership"]` add `"island_min_churn": 2` after `"island_max_authors": 2`.

`rules.py` `_band_hits`: extend the island predicate:

```python
        churn = entry.get("churn")
        island = (
            isinstance(share, float)
            and isinstance(authors, int)
            and isinstance(churn, int)
            and share >= float(own["island_share"])
            and authors <= int(own["island_max_authors"])
            and churn >= int(own["island_min_churn"])
        )
```

`rules.py` `_ownership_hits`: replace the CODEOWNERS selection with

```python
    codeowners = next(
        (
            str(a["path"]) for a in governance
            if _basename(str(a["path"])) == "CODEOWNERS" and not _disabled(a)
        ),
        None,
    )
    codeowners_present = any(_basename(str(a["path"])) == "CODEOWNERS" for a in governance)
```

and gate the `no-codeowners` branch on `not codeowners_present` (a CODEOWNERS that exists but is skipped is neither unowned-checked nor reported missing). Update the `_ownership_hits` docstring and the module docstring's ownership sentence.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_rules.py skills/tech-debt-scan/tests/test_patterns.py skills/tech-debt-scan/tests/test_config.py -q`

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md` `rules.py` row: add "an island also needs `churn >= island_min_churn` (2) in the window; a CODEOWNERS the inventory skipped or that sits under a disabled tree is not consulted". `README.md` needs no change (it does not list rule thresholds; verify with `grep -n island README.md`). Run the gate. Commit:

```
fix(tech-debt-scan): knowledge islands need a churn floor; CODEOWNERS honours the inventory guard
```

---

### Task 3: `categories.py` v2 family blocks and the scout prompt renderer

**Files:**
- Modify: `skills/tech-debt-scan/scripts/categories.py` (append the v2 section; keep every v1 symbol)
- Rewrite: `skills/tech-debt-scan/tests/test_categories.py`

**Interfaces:**
- Produces: `FAMILIES: tuple[str, ...]` (the fourteen scout families in dispatch order: `complex-units`, `god-classes`, `duplication`, `dead-code`, `error-masking`, `test-gaps`, `half-finished`, `migration`, `dependency-debt`, `doc-drift`, `architecture`, `security`, `test-quality`, `pipeline-infra`); `FamilyBlock` dataclass (`definition: str`, `questions: tuple[str, ...]`, `traps: tuple[str, ...]`, `type_ids: tuple[str, ...]`, `debt_types: tuple[str, ...]`, `verifier_questions: tuple[str, ...]`); `FAMILY_BLOCKS: dict[str, FamilyBlock]`; `SEVERITY_RUBRIC: str`; `render_scout_prompt(family: str, *, repo_summary: str, leads_block: str, scout_cap: int, disabled_note: str) -> str`; `SCOUT_OUTPUT_SCHEMA: dict[str, Any]` (a JSON Schema for one scout file, used by `live_run.py --json-schema`).
- Consumed by: Task 4 (`plan_scan.py` renders prompts), Task 6 (`verifier_questions`), Task 9 (`SCOUT_OUTPUT_SCHEMA`).

**Confidence:** 92% (data plus one string renderer; the risk is a family text tripping the token ban, which Step 1's test catches on the first run and is fixed by rewording).

- [ ] **Step 1: Rewrite `tests/test_categories.py`**

```python
"""categories.py: the v1 prompts (skipped until phase 3) and the v2 family blocks (spec 4.6)."""
from __future__ import annotations

import json

import pytest
from categories import (
    CATEGORIES,
    CORE_CATEGORIES,
    FAMILIES,
    FAMILY_BLOCKS,
    SCOUT_OUTPUT_SCHEMA,
    SEVERITY_RUBRIC,
    get_prompt,
    render_scout_prompt,
)
from config import FAMILY_SETS
from validation import VALID_DEBT_TYPES, validate_type_id

V1_SKIP = pytest.mark.skip(reason="v1 scout prompts are retired in phase 3 (spec 11)")

EXPECTED_FAMILIES = (
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "test-quality", "pipeline-infra",
)
FORBIDDEN = ("def ", ".py file", "python module", "__init__", "pip install")


def _render(family: str) -> str:
    return render_scout_prompt(
        family,
        repo_summary="root: r, 10 files, 100 LOC, languages: python, typescript; git: yes",
        leads_block="Hotspot-band files: src/a.py (0.91)\n",
        scout_cap=12,
        disabled_note="Families disabled on tests: duplication, complex-units, god-classes",
    )


# --- v1 (kept until phase 3) ----------------------------------------------------


@V1_SKIP
def test_eight_categories() -> None:
    assert len(set(CATEGORIES)) == 8 and set(CORE_CATEGORIES) <= set(CATEGORIES)


@V1_SKIP
def test_v1_prompts_carry_the_v1_schema() -> None:
    for cat in CATEGORIES:
        assert '"suggested_fix"' in get_prompt(cat)


# --- v2 -------------------------------------------------------------------------


def test_fourteen_families_in_dispatch_order() -> None:
    assert FAMILIES == EXPECTED_FAMILIES
    assert set(FAMILY_BLOCKS) == set(FAMILIES)
    assert FAMILIES == FAMILY_SETS["deep"]


def test_every_block_is_complete_and_valid() -> None:
    for family, block in FAMILY_BLOCKS.items():
        assert len(block.definition) > 60, family
        assert 4 <= len(block.questions) <= 6, family
        assert block.traps, family
        assert block.type_ids, family
        for type_id in block.type_ids:
            validate_type_id(type_id)
        assert block.debt_types and set(block.debt_types) <= VALID_DEBT_TYPES, family
        assert block.verifier_questions, family


def test_rendered_prompt_has_prefix_block_leads_and_contract() -> None:
    for family in FAMILIES:
        text = _render(family)
        assert "read-only" in text.lower()
        assert "do not invent" in text.lower()
        assert '"line_start"' in text and '"line_end"' in text and '"quote"' in text
        assert '"type_id"' in text and '"signals_cited"' in text
        assert '"open_questions"' in text and '"looks_bad_but_fine"' in text
        assert '"not_assessed"' in text
        assert "suggested_fix" not in text and "confidence" not in text
        assert "an empty list is a correct answer" in text
        assert "12" in text
        assert "hotspot" in text.lower() and "Severity rubric" in text
        assert "Families disabled on tests" in text
        assert FAMILY_BLOCKS[family].definition in text
        assert "Hotspot-band files: src/a.py" in text


def test_rubric_has_no_hotspot_amplifier() -> None:
    assert "+1" not in SEVERITY_RUBRIC and "3 + hotspot" not in SEVERITY_RUBRIC
    assert SEVERITY_RUBRIC.startswith("Severity rubric")


def test_v2_prompts_avoid_language_specific_terms() -> None:
    for family in FAMILIES:
        low = _render(family).lower()
        for bad in FORBIDDEN:
            assert bad not in low, f"{family}: {bad!r}"


def test_never_assert_rules_are_present() -> None:
    text = _render("security")
    for claim in ("coverage", "CVE", "end-of-life", "deprecat", "flak", "exploitab"):
        assert claim.lower() in text.lower(), claim


def test_output_schema_is_valid_json_schema_shape() -> None:
    schema = SCOUT_OUTPUT_SCHEMA
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"family", "module", "findings", "open_questions",
                                       "looks_bad_but_fine", "not_assessed"}
    finding = schema["properties"]["findings"]["items"]
    assert set(finding["required"]) == {"title", "family", "debt_type", "severity", "effort",
                                        "signals_cited", "evidence", "note"}
    json.dumps(schema)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_categories.py -q`
Expected: `ImportError: cannot import name 'FAMILIES' from 'categories'`.

- [ ] **Step 3: Append the v2 section to `categories.py`**

Append after `get_prompt` (leave everything above untouched; update the module docstring's first line to "Scout prompts: the eight v1 categories (retired in phase 3) and the fourteen v2 family blocks (spec 2.3, 4.6)."):

```python
# =============================================================================
# v2 (spec 2.3, 4.6): fourteen family blocks and the shared prefix.
# =============================================================================

from dataclasses import dataclass  # noqa: E402  (v2 section appended below the v1 data)


@dataclass(frozen=True, slots=True)
class FamilyBlock:
    """One family's scout block: what to look for, what to distrust, what it may emit."""

    definition: str
    questions: tuple[str, ...]
    traps: tuple[str, ...]
    type_ids: tuple[str, ...]
    debt_types: tuple[str, ...]
    verifier_questions: tuple[str, ...]


FAMILIES: Final[tuple[str, ...]] = (
    "complex-units", "god-classes", "duplication", "dead-code", "error-masking",
    "test-gaps", "half-finished", "migration", "dependency-debt", "doc-drift",
    "architecture", "security", "test-quality", "pipeline-infra",
)

SEVERITY_RUBRIC: Final[str] = """Severity rubric (apply consistently; location is scored later by a script, not by you):
  5 = active correctness, security, data-loss, or money risk right now
  4 = materially slows or endangers most changes in its area
  3 = recurring friction the team pays regularly
  2 = localized annoyance, rarely on the change path
  1 = cosmetic"""

NEVER_ASSERT: Final[str] = """Never assert any of these without a tool fact you were given: test coverage numbers,
CVE or vulnerability status, end-of-life or currency of a dependency, library-level deprecation,
test flakiness, exploitability of a security pattern. Put such claims under "not_assessed"."""

FAMILY_BLOCKS: Final[dict[str, FamilyBlock]] = {
    "complex-units": FamilyBlock(
        definition=(
            "COMPLEX UNITS: single functions, methods or blocks whose branching and nesting make "
            "them hard to change safely. Deep indentation runs and long indented spans in the leads "
            "are the deterministic signal; confirm by reading the unit."
        ),
        questions=(
            "Does the cited span show the branching the lead claims (nested conditions, long chains)?",
            "Is the unit on a change path (a hotspot-band file or a coupled pair), or cold?",
            "Is the size a symptom of mixed responsibilities that a split would separate?",
            "Would a table, a state machine or a strategy remove the branching?",
        ),
        traps=(
            "A large lookup table, a generated switch or a declarative state machine is long but cohesive.",
            "Generated or vendored code is not a finding.",
        ),
        type_ids=("TD-01",),
        debt_types=("code", "design"),
        verifier_questions=(
            "Large but cohesive (table, state machine, generated)?",
            "Does the span show the branching claimed?",
            "Is the unit on a change path?",
        ),
    ),
    "god-classes": FamilyBlock(
        definition=(
            "GOD CLASSES: a type, module or file that owns too many reasons to change, plus "
            "inappropriate intimacy (reaching into another unit's internals) and long message "
            "chains. Size, approximate fan-in and coupled pairs in the leads point at candidates."
        ),
        questions=(
            "Does the unit have more than one reason to change? Name the responsibilities.",
            "Do its methods cluster over disjoint sets of fields (two classes in one)?",
            "Is it a hub that most of the repository reaches for?",
            "Does a caller chain through several objects to reach data it should be handed?",
        ),
        traps=(
            "A facade, a DTO, a fluent builder or a thin controller is wide by design.",
            "A large file that is one cohesive concept is a complex-units question, not this one.",
        ),
        type_ids=("TD-11", "TD-20"),
        debt_types=("design", "code"),
        verifier_questions=(
            "One reason to change?",
            "Do methods cluster over disjoint fields?",
            "Facade, DTO or fluent builder trap?",
        ),
    ),
    "duplication": FamilyBlock(
        definition=(
            "DUPLICATION: the same logic in two or more places that must change together. Coupled "
            "pairs in the leads are the change-history signal; tool clone reports arrive when a "
            "clone detector is installed."
        ),
        questions=(
            "Are the copies changed together in history (a coupled pair) or by a tool report?",
            "Do the copies differ only in a constant, a type name or a message?",
            "Would one shared abstraction be simpler than the copies, or would it couple unrelated code?",
            "How many copies exist and how far apart do they sit?",
        ),
        traps=(
            "Fixture, generated and vendored duplication is intentional.",
            "Repeated literal values alone (magic numbers, strings) are not this family.",
            "Two similar-looking units with different reasons to change are not duplicates.",
        ),
        type_ids=("TD-05",),
        debt_types=("code",),
        verifier_questions=(
            "Copies change-coupled or tool-confirmed?",
            "Path class fixture, generated, vendored?",
            "Would a shared abstraction be simpler than the copies?",
        ),
    ),
    "dead-code": FamilyBlock(
        definition=(
            "DEAD CODE: units with no callers, unreachable branches, commented-out code left in "
            "place, legacy-named leftovers, deprecated units still present, and feature flags that "
            "only ever take one value. Zero approximate fan-in with zero churn on an ordinary "
            "module is the deterministic signal; pattern leads mark the textual cases."
        ),
        questions=(
            "Which dynamic-reference patterns did you check: reflection, string dispatch, routes, dependency injection, serialisation?",
            "Is the file an entry point, a script run by name, or a test a runner discovers by convention?",
            "Is the unit part of a public or plugin surface that external code may call?",
            "For a flag: is it a permission, a kill switch, or genuinely permanently off?",
            "For a deprecated unit: does anything in the repository still call it?",
        ),
        traps=(
            "Entry points and runner-discovered tests have no in-repository caller and are alive.",
            "A documented kill switch is deliberately always-on.",
            "A middle-man class that exists for a documented reason.",
        ),
        type_ids=("TD-09", "TD-30", "TD-17", "TD-20"),
        debt_types=("code",),
        verifier_questions=(
            "Which dynamic-reference patterns were checked (reflection, string dispatch, routes, DI, serialisation)?",
            "Entry point, script run by name, or runner-discovered test?",
            "Public or plugin surface?",
            "Flag is permission or kill-switch?",
        ),
    ),
    "error-masking": FamilyBlock(
        definition=(
            "ERROR MASKING: failures caught and hidden, so nobody learns of them. Empty catch blocks, "
            "catch-everything variants, log-only catches that drop the cause, and disabled assertions. "
            "Pattern leads give the candidate sites; read each body."
        ),
        questions=(
            "What failure is hidden, and who or what would otherwise learn of it?",
            "Is the catch a process boundary, a retry that re-raises, or a cleanup block (all acceptable)?",
            "When the error is re-thrown or logged, is the cause preserved?",
            "Do assertions still run in the configuration the leads show?",
        ),
        traps=(
            "A catch at a process or request boundary that reports and continues is correct.",
            "A retry loop that re-raises after the last attempt is not masking.",
        ),
        type_ids=("TD-13",),
        debt_types=("code", "defect"),
        verifier_questions=(
            "What failure is hidden and who learns of it?",
            "Process boundary, retry that re-raises, or cleanup block?",
            "Cause preserved on rethrow?",
        ),
    ),
    "test-gaps": FamilyBlock(
        definition=(
            "TEST GAPS: behaviour that changes often with no automated test guarding it. Hotspot-band "
            "files with no mapped test, a high untested-change share, skip markers and a missing "
            "coverage gate are the leads."
        ),
        questions=(
            "Which test paths did you search, and by what naming conventions?",
            "Is there an unconventionally named test that the mapping missed?",
            "Does the mapped test assert behaviour, or only that code ran?",
            "What is the blast radius of the untested behaviour if it regresses?",
        ),
        traps=(
            "A file exercised through an integration or end-to-end suite has coverage the mapping cannot see.",
            "Glue, configuration and generated code rarely need unit tests.",
        ),
        type_ids=("TD-04",),
        debt_types=("test",),
        verifier_questions=(
            "Which test paths were searched?",
            "Is there an unconventionally named test?",
            "Does the mapped test assert behaviour?",
        ),
    ),
    "half-finished": FamilyBlock(
        definition=(
            "HALF-FINISHED WORK: self-admitted debt markers, stubs that raise or return placeholders, "
            "expected-failure and skip markers, known-bug notes, and calls that wait forever (no "
            "timeout). The SATD list carries each marker's age and whether a ticket is referenced."
        ),
        questions=(
            "Does the marker name a concrete risk, a date or a ticket, or is it vague?",
            "Is the stub an abstract contract that subclasses fill (not debt) or an unimplemented path?",
            "Is the named risk still present in the code next to the marker?",
            "For a call without a timeout: what waits when the remote never answers?",
        ),
        traps=(
            "Abstract methods and interface contracts raise not-implemented on purpose.",
            "A marker that documents a deliberate, ticketed deferral is process working as intended.",
        ),
        type_ids=("TD-22", "TD-28", "TD-32", "TD-34"),
        debt_types=("code", "requirement", "defect"),
        verifier_questions=(
            "Stub is an abstract contract?",
            "Ticket tracks it?",
            "Named risk still present in the code?",
        ),
    ),
    "migration": FamilyBlock(
        definition=(
            "MIGRATION DEBT: two ways of doing one thing coexisting, an old idiom still called after "
            "its replacement landed, and superseded configuration kept beside its successor. Naming "
            "hints, migration commits, dual-manifest leads and deprecation annotations point at candidates."
        ),
        questions=(
            "Which side has churn: the old, the new, both or neither?",
            "What share of call sites still sit on the old side? Cite the count.",
            "Is the dual arrangement a deliberate multi-backend design?",
            "Is there a plan, ticket or date for finishing the move?",
        ),
        traps=(
            "Deliberate multi-backend or adapter designs keep two paths on purpose.",
            "A compatibility shim with a stated removal date is a finished decision.",
        ),
        type_ids=("TD-06", "TD-17"),
        debt_types=("design", "dependency", "build"),
        verifier_questions=(
            "Churn on old side, new side, both or neither?",
            "Deliberate multi-backend?",
            "Call-site ratio cited?",
        ),
    ),
    "dependency-debt": FamilyBlock(
        definition=(
            "DEPENDENCY DEBT, structural only: manifests without a lockfile or with two lockfile kinds, "
            "two packages doing one job, floating version ranges inside a library, vendored copies of "
            "libraries, and a runtime version file that disagrees with the manifest. Read the manifest, "
            "lockfile, runtime-version and governance artefacts in the leads."
        ),
        questions=(
            "Is the lockfile missing, or elsewhere (a monorepo root)?",
            "Do two dependencies serve the same purpose (two HTTP clients, two date libraries)?",
            "Is a floating range declared inside a library that others consume?",
            "Does a vendored copy diverge from an upstream that is also declared?",
        ),
        traps=(
            "A library manifest without a lockfile is normal; an application manifest without one is not.",
            "A duplicate-purpose pair with churn on one side is a migration, not a dependency finding.",
        ),
        type_ids=("TD-02",),
        debt_types=("dependency",),
        verifier_questions=(
            "Lockfile missing or elsewhere (monorepo)?",
            "Duplicate-purpose pair is a migration?",
            "Floating range inside a library?",
        ),
    ),
    "doc-drift": FamilyBlock(
        definition=(
            "DOC DRIFT: documentation that contradicts the code it describes. Dangling references, "
            "documents older than the code they cover, and missing README, CONTRIBUTING, ADR or "
            "CHANGELOG entries are the leads."
        ),
        questions=(
            "Cite both the document line and the contradicting code line.",
            "Would the documented example still run as written?",
            "Is the reference dangling because the target moved, or was renamed?",
            "For an absence finding, aggregate per module rather than per file.",
        ),
        traps=(
            "A document that describes a planned or external interface is not drift.",
            "Generated API docs regenerate on release; check the generator, not the output.",
        ),
        type_ids=("TD-08",),
        debt_types=("documentation",),
        verifier_questions=(
            "Both the doc line and the contradicting code line cited?",
            "Example still runnable?",
            "Absence findings aggregated per module?",
        ),
    ),
    "architecture": FamilyBlock(
        definition=(
            "ARCHITECTURE DEBT: dependency cycles between modules, code in the wrong component, and "
            "directories whose stability contradicts what depends on them. Cycle leads, coupled pairs, "
            "directory aggregates, unstable edges and any declared boundary tooling are the signals."
        ),
        questions=(
            "Is the cycle real at the language level, or does the language forbid package cycles (Go, .NET)?",
            "Is the co-change explained by a declared dependency or by feature work?",
            "Does an ADR, an import contract or a boundary tool state the intended layers?",
            "Which component should own the misplaced code, and what depends on it today?",
        ),
        traps=(
            "Re-export packages create apparent cycles that the compiler resolves.",
            "A cycle inside one cohesive package is a design smell, not an architecture finding.",
        ),
        type_ids=("TD-07", "TD-10"),
        debt_types=("architecture", "design"),
        verifier_questions=(
            "Language forbids package cycles (Go, .NET)?",
            "Co-change explained by a declared dependency or feature work?",
            "ADR or import contract states the layers?",
        ),
    ),
    "security": FamilyBlock(
        definition=(
            "SECURITY DEBT, pattern level: credential-shaped literals, string-built SQL, dynamic "
            "evaluation and shell-out, disabled TLS verification, weak hashes, wildcard CORS, and "
            "suppressed security rules. Pattern leads give the sites; you judge context, never exploitability."
        ),
        questions=(
            "Is the site under a test, example or fixture path, and does the value look like a placeholder?",
            "Can user input reach the SQL or shell site, by which path?",
            "Is a suppression justified by a comment nearby?",
            "Is the disabled verification scoped to a local or development target?",
        ),
        traps=(
            "Placeholders, examples and test fixtures are not secrets.",
            "A weak hash used for a cache key or a checksum is not a security finding.",
        ),
        type_ids=("TD-03",),
        debt_types=("security",),
        verifier_questions=(
            "Path class example, fixture or test, and secret entropy?",
            "User input reachable at the SQL or shell site?",
            "Suppression justified nearby?",
        ),
    ),
    "test-quality": FamilyBlock(
        definition=(
            "TEST QUALITY: tests that sleep, read the wall clock, use unseeded randomness, wrap logic "
            "in try or catch, branch on conditions, assert nothing, or assert against magic numbers. "
            "Per-file signal counts, CI retry configuration and flaky-commit history are the leads."
        ),
        questions=(
            "Is the pattern a table-driven or parametrised idiom rather than conditional logic?",
            "Do fake timers or a frozen clock make the wall-clock read deterministic?",
            "Does the assertion-free test guard a critical path, or is it a smoke test by design?",
            "Does the retry configuration hide a known flaky test?",
        ),
        traps=(
            "Parametrised tests loop by design.",
            "A smoke test that only checks startup is honest about its purpose.",
        ),
        type_ids=("TD-12", "TD-18"),
        debt_types=("test",),
        verifier_questions=(
            "Table-driven or parametrised idiom?",
            "Fake timers or frozen clock?",
            "Does the assertion-free test guard a critical path?",
        ),
    ),
    "pipeline-infra": FamilyBlock(
        definition=(
            "PIPELINE AND INFRASTRUCTURE DEBT, judgement symptoms only (the deterministic rule findings "
            "are produced separately): duplicated pipeline YAML, manual release steps, dev-only "
            "container paths in production use, and stdout writes where a logger exists."
        ),
        questions=(
            "Is the duplicated YAML generated from a template or hand-copied?",
            "Is the manual step documented as intentional?",
            "Is the dev-only container path used by a production job?",
            "Do the stdout writes sit in a CLI entry point (fine) or in library code with a logger present?",
        ),
        traps=(
            "A CLI tool prints by design.",
            "A dev-only compose file with a floating tag is expected.",
        ),
        type_ids=("TD-14", "TD-19", "TD-27", "TD-35"),
        debt_types=("build", "infrastructure"),
        verifier_questions=(
            "Dev-only Dockerfile or compose path?",
            "Duplicated YAML generated from a template?",
            "Manual step documented as intentional?",
        ),
    ),
}
```

Then the contract and renderer (same file, after `FAMILY_BLOCKS`):

```python
SCOUT_OUTPUT_CONTRACT: Final[str] = """Output: one JSON object with exactly these keys.

{
  "family": "<this family>",
  "module": null,
  "findings": [
    {
      "title": "<=80 chars",
      "family": "<this family>",
      "debt_type": "<one of the allowed debt types above>",
      "type_id": "<one of the allowed TD ids above, or null>",
      "severity": 1-5,
      "effort": "S" | "M" | "L",
      "signals_cited": ["hotspot", "pattern:<family>:<rule>", "coupling", "satd"],
      "evidence": [
        {"file": "relative/path", "line_start": 120, "line_end": 123, "quote": "verbatim, at most 6 lines"}
      ],
      "note": "<=300 chars on what is wrong; no fix proposals"
    }
  ],
  "open_questions": [{"file": "", "line_start": 0, "question": ""}],
  "looks_bad_but_fine": [{"file": "", "line_start": 0, "why": ""}],
  "not_assessed": ["<claims you could not make>"]
}

Every quote must be copied verbatim from the file; a quote that is not in the file
is discarded by a script, together with the finding. Do not include a confidence
field or a suggested fix."""

SCOUT_OUTPUT_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["family", "module", "findings", "open_questions", "looks_bad_but_fine", "not_assessed"],
    "properties": {
        "family": {"type": "string"},
        "module": {"type": ["string", "null"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "family", "debt_type", "severity", "effort",
                             "signals_cited", "evidence", "note"],
                "properties": {
                    "title": {"type": "string", "maxLength": 80},
                    "family": {"type": "string"},
                    "debt_type": {"type": "string"},
                    "type_id": {"type": ["string", "null"]},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "effort": {"type": "string", "enum": ["S", "M", "L"]},
                    "signals_cited": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["file", "line_start", "line_end", "quote"],
                            "properties": {
                                "file": {"type": "string"},
                                "line_start": {"type": "integer", "minimum": 1},
                                "line_end": {"type": "integer", "minimum": 1},
                                "quote": {"type": "string"},
                            },
                        },
                    },
                    "note": {"type": "string", "maxLength": 300},
                },
            },
        },
        "open_questions": {"type": "array", "items": {"type": "object"}},
        "looks_bad_but_fine": {"type": "array", "items": {"type": "object"}},
        "not_assessed": {"type": "array", "items": {"type": "string"}},
    },
}


def render_scout_prompt(
    family: str,
    *,
    repo_summary: str,
    leads_block: str,
    scout_cap: int,
    disabled_note: str,
) -> str:
    """Shared prefix, then the family block, then the leads block, then the contract (spec 4.6)."""
    block = FAMILY_BLOCKS[family]
    questions = "\n".join(f"  - {q}" for q in block.questions)
    traps = "\n".join(f"  - {t}" for t in block.traps)
    parts = [
        f"You are a read-only scout for one debt family: {family}.",
        "",
        "Repository: " + repo_summary,
        "",
        "Rules: you have read-only access (read and search files; change nothing). Do not invent "
        "findings, files, lines or quotes; every claim cites a file, a line range and a verbatim "
        "quote of at most 6 lines. Report at most "
        f"{scout_cap} findings; that number is a ceiling, and an empty list is a correct answer "
        "when the repository has nothing in this family. Do not propose fixes.",
        "",
        NEVER_ASSERT,
        "",
        disabled_note,
        "",
        SEVERITY_RUBRIC,
        "",
        block.definition,
        "",
        "Questions to answer for every candidate:",
        questions,
        "",
        "Traps (do not report these):",
        traps,
        "",
        f"Allowed debt_type values: {', '.join(block.debt_types)}. "
        f"Allowed type_id values: {', '.join(block.type_ids)}.",
        "",
        "Leads (deterministic signals; start here, then read beyond them if budget allows):",
        leads_block.rstrip("\n"),
        "",
        SCOUT_OUTPUT_CONTRACT,
    ]
    return "\n".join(parts) + "\n"
```

Add `from typing import Any` to the module's imports (the file already imports `Final`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_categories.py -q`
Expected: v2 tests pass; the two v1 tests are reported skipped. If `test_v2_prompts_avoid_language_specific_terms` fails, reword the offending block text; do not weaken the ban.

- [ ] **Step 5: Gate and commit**

`python -m pytest -q` must still pass in full (`test_build_synthesis_prompt.py` and `test_e2e.py` import the v1 symbols). Commit:

```
feat(tech-debt-scan): categories.py v2 family blocks, shared prefix and scout contract
```

---
### Task 4: `plan_scan.py`, the adaptive rule and the leads block

**Files:**
- Create: `skills/tech-debt-scan/scripts/plan_scan.py`
- Test: `skills/tech-debt-scan/tests/test_plan_scan.py`
- Modify: `docs/architecture.md` (script table row), `README.md` (output-formats row for `scan-plan.json`)

**Interfaces:**
- Consumes: `load_config`, `enabled_families`, `FAMILY_SETS`, `ConfigError` (`config.py`); `write_json` (`inventory.py`); `FAMILIES`, `render_scout_prompt` (`categories.py`); the phase 1 documents `inventory.json`, `coupling.json`, `patterns.json`, `rule-findings.json` in the workdir.
- Produces: `build_plan(workdir: Path, config: dict[str, Any], *, families: str | list[str] | None, top: int | None) -> tuple[dict[str, Any], dict[str, str]]` returning the `scan-plan.json` document and `{prompt relative path: text}`; `leads_for(family: str, docs: ScanDocs, config: dict[str, Any]) -> list[Lead]`; `LEAD_CAP = 40`; `ScanDocs` dataclass (`inventory`, `coupling`, `patterns`, `rules`) loaded by `load_docs(workdir)`; `write_plan(workdir, plan, prompts)`.
- CLI: `python scripts/plan_scan.py --workdir .tech-debt [--families default|quick|deep|a,b,c] [--top N]`; exit 2 when `inventory.json` is missing or config is invalid; writes `scan-plan.json` and `prompts/scout-<family>.md`.

**Confidence:** 91% (the leads block draws on documents whose shapes were read at plan time; the one risk is a family whose lead sources are all empty on every fixture, which the corpus test surfaces and which the adaptive rule handles by design). Mitigation embedded: Step 1's corpus test asserts the exact `families_run` set per fixture only after Step 4 prints it, and the plan records the printed sets as the pinned expectation (the implementer fills the three tuples from the first run and states them in the report; the reviewer checks them against `planted.json`).

**Design (fixed):**

- A lead is `Lead(kind, path, line, text, score)`; `kind` is one of `hotspot`, `coupling`, `pattern`, `satd`, `artefact`, `cycle`, `inventory`, `docs`, `tests`. The leads block is rendered as one section per kind present, in that order, each line `- <path>[:<line>] <text>`; hotspot-band entries first inside every section (score descending), then path ascending; at most `LEAD_CAP` (40) lines per family.
- Sources per family (spec 2.3 "Leads from"):

| Family | Sources |
|---|---|
| complex-units | `hotspot` band files; `inventory`: the top 10 source files by `longest_indented_run`, then `deep_indent_lines`, each line `deep_indent_lines=<n> longest_run=<n> max_indent=<n>` |
| god-classes | `hotspot`; `inventory`: top 10 source files by `loc`, then by `fan_in_approx` (nulls last); `coupling` pairs |
| duplication | `hotspot`; `coupling` pairs (`a <-> b shared=<n> ratio=<r>`) |
| dead-code | `hotspot`; `inventory`: source files with `fan_in_approx == 0` and `churn == 0` (`fan_in=0 churn=0`); `pattern` leads for family dead-code |
| error-masking | `hotspot`; `pattern` leads for error-masking |
| test-gaps | `hotspot`; `tests`: hotspot-band files with empty `mapped_tests` (`no mapped test`), source files with `untested_change_share >= 0.5` (`untested_change_share=<v>`), `pattern` skip-marker leads (rule `skip-marker`, family half-finished), and one line `coverage_gate: <value>` from `inventory.tests` when present |
| half-finished | `hotspot`; `satd` entries (`<marker> age_days=<n> ticket=<bool>`); `pattern` leads for half-finished |
| migration | `hotspot`; `inventory`: files with `migration_commits > 0` (`migration_commits=<n>`); `artefact`: `rule-findings.leads.migration`; `coupling` pairs |
| dependency-debt | `artefact`: every `manifest`, `lockfile`, `runtime_version`, `governance` artefact (`<class>`) |
| doc-drift | `docs`: `dangling_refs` (`dangling: <token>` per entry, path = the doc when the entry names one, else `README.md`), `stale_vs_code_days` (`stale <n> days`), presence flags that are false (`missing: CONTRIBUTING`, `missing: ADR directory`, `missing: CHANGELOG`) |
| architecture | `hotspot`; `cycle` (`members: a, b, c`); `coupling` pairs with `cross_directory` true; `docs`: `unstable_edges` (`<from> -> <to> instability <a> depends on <b>`), `boundary_tooling` (`declared: <name>`) |
| security | `pattern` leads for security (quotes already redacted by `patterns.py`) |
| test-quality | `pattern` leads for test-quality; `tests`: `ci_retry_config` line when present; `inventory`: files with `flaky_commits > 0` |
| pipeline-infra | `pattern` leads for pipeline-infra; `artefact`: `ci`, `container`, `iac` artefacts |

- Path-class disables: `config["families"]["per_path_class"]` maps a path class to `{"disable": [...] | "all"}`; a lead whose file's `path_class` (from the inventory file or artefact entry, `source` when unknown) disables this family is dropped before counting. The prompt's `disabled_note` lists them: `Families disabled on <class>: <names>` per class (or `all families`).
- Adaptive rule: a family in the requested set is dispatched when its filtered leads are non-empty; otherwise `families_skipped` gets `{"family", "reason": "no leads"}`. A family in `config["families"]["disabled"]` is skipped with `disabled`; a family not in the set is skipped with `not in set`. An explicit list bypasses the adaptive rule (dispatched even with zero leads) but not `disabled`.
- Repository summary: `root: <root>, <total_files> files, <total_loc> LOC, languages: <a, b>; git: yes|no`.
- `top` comes from `--top`, else `config["top"]`.
- Chunking: `chunked` is always false; `thresholds` copies `config["chunking"]`; every entry has `module: null`.
- Determinism: families in `FAMILIES` order; leads sorted as above; the prompt text is a pure function of the documents and config.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_plan_scan.py`:

```python
"""plan_scan.py: leads block, adaptive rule, set forms, prompt rendering (spec 2.4, 4.6)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from categories import FAMILIES
from config import DEFAULTS
from inventory import build_all, write_json, write_outputs
from patterns import run_patterns
from plan_scan import LEAD_CAP, ScanDocs, _main, build_plan, leads_for, load_docs
from rules import run_rules

from make_history import replay_fixture

CORPUS = ("service-py", "web-ts", "mixed-decoys")


def _signals(repo: Path, workdir: Path, *, churn_months: int = 240) -> None:
    """Run the phase 1 chain into workdir exactly as SKILL.md v2 steps 1 to 3 will."""
    inventory, coupling = build_all(repo, churn_months=churn_months, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json",
               {"schema_version": 2, "findings": findings, "leads": leads})


@pytest.fixture(scope="module")
def corpus_workdirs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, tuple[Path, Path]]:
    out: dict[str, tuple[Path, Path]] = {}
    for name in CORPUS:
        repo = replay_fixture(name, tmp_path_factory.mktemp(name))
        workdir = tmp_path_factory.mktemp(f"{name}-wd")
        _signals(repo, workdir)
        out[name] = (repo, workdir)
    return out


# Filled in by the implementer from the first green run (Step 4) and checked by the
# reviewer against planted.json: every family with a planted item must be run.
EXPECTED_RUN: dict[str, set[str]] = {
    "service-py": set(),
    "web-ts": set(),
    "mixed-decoys": set(),
}


def test_plan_shape_and_default_set(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["service-py"]
    plan, prompts = build_plan(workdir, DEFAULTS, families=None, top=None)
    assert list(plan) == ["schema_version", "set", "top", "chunked", "thresholds", "entries",
                          "families_run", "families_skipped"]
    assert plan["schema_version"] == 2 and plan["set"] == "default" and plan["top"] == 5
    assert plan["chunked"] is False and plan["thresholds"] == DEFAULTS["chunking"]
    for entry in plan["entries"]:
        assert list(entry) == ["family", "module", "prompt", "output", "leads"]
        assert entry["module"] is None
        assert entry["prompt"] == f"prompts/scout-{entry['family']}.md"
        assert entry["output"] == f"scouts/{entry['family']}.json"
        assert entry["prompt"] in prompts
    run = [e["family"] for e in plan["entries"]]
    assert run == plan["families_run"] == [f for f in FAMILIES if f in run]
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert set(run) | set(skipped) == set(FAMILIES)
    assert skipped["test-quality"] == "not in set" and skipped["pipeline-infra"] == "not in set"


@pytest.mark.parametrize("name", CORPUS)
def test_every_planted_family_is_dispatched(
    name: str, corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    _, workdir = corpus_workdirs[name]
    plan, _ = build_plan(workdir, DEFAULTS, families="deep", top=None)
    planted = json.loads((Path(__file__).parent / "fixtures" / "corpus" / name / "planted.json")
                         .read_bytes())
    scout_families = {p["family"] for p in planted["planted"]} - {"ownership"}
    assert scout_families <= set(plan["families_run"]), plan["families_skipped"]
    assert EXPECTED_RUN[name] == set(plan["families_run"])


def test_set_forms_and_explicit_list_bypass_adaptive_rule(
    corpus_workdirs: dict[str, tuple[Path, Path]]
) -> None:
    _, workdir = corpus_workdirs["mixed-decoys"]
    quick, _ = build_plan(workdir, DEFAULTS, families="quick", top=3)
    assert quick["set"] == "quick" and quick["top"] == 3
    assert set(quick["families_run"]) <= {"complex-units", "error-masking", "test-gaps",
                                          "half-finished", "dependency-debt", "security"}
    deep, _ = build_plan(workdir, DEFAULTS, families="deep", top=None)
    assert deep["set"] == "deep"
    explicit, prompts = build_plan(workdir, DEFAULTS, families=["doc-drift", "duplication"], top=None)
    assert explicit["set"] == "explicit"
    assert explicit["families_run"] == ["duplication", "doc-drift"]  # FAMILIES order, not argv order
    assert {s["reason"] for s in explicit["families_skipped"]} == {"not in set"}
    cfg = deepcopy(DEFAULTS)
    cfg["families"]["disabled"] = ["duplication"]
    disabled, _ = build_plan(workdir, cfg, families=["doc-drift", "duplication"], top=None)
    assert {s["family"]: s["reason"] for s in disabled["families_skipped"]}["duplication"] == "disabled"
    with pytest.raises(Exception):
        build_plan(workdir, DEFAULTS, families="nonsense", top=None)


def test_no_leads_family_is_skipped_with_reason(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    plan, _ = build_plan(workdir, DEFAULTS, families=None, top=None)
    skipped = {s["family"]: s["reason"] for s in plan["families_skipped"]}
    assert skipped.get("security") == "no leads"
    assert skipped.get("dependency-debt") == "no leads"


def test_lead_cap_and_hotspot_band_first(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["service-py"]
    docs = load_docs(workdir)
    inflated = ScanDocs(
        inventory=docs.inventory,
        coupling=docs.coupling,
        patterns=deepcopy(docs.patterns),
        rules=docs.rules,
    )
    band = docs.inventory["hotspot_band"][0]
    extra = [
        {"rule": "satd-marker", "file": f"src/z{i}.py", "line": 1, "quote": "# TODO x",
         "path_class": "source", "extra": {}}
        for i in range(60)
    ] + [{"rule": "satd-marker", "file": band, "line": 1, "quote": "# TODO band",
          "path_class": "source", "extra": {}}]
    inflated.patterns["leads"]["half-finished"] = extra + inflated.patterns["leads"]["half-finished"]
    leads = leads_for("half-finished", inflated, DEFAULTS)
    assert len(leads) == LEAD_CAP
    assert leads[0].path in docs.inventory["hotspot_band"]


def test_path_class_disables_drop_leads_and_are_named_in_the_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / "tests" / "test_a.py").write_text(
        "def test_a():\n    try:\n        pass\n    except Exception:\n        pass\n", encoding="utf-8")
    (repo / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    _signals(repo, workdir)
    cfg = deepcopy(DEFAULTS)
    cfg["families"]["per_path_class"]["tests"] = {"disable": ["error-masking"]}
    plan, prompts = build_plan(workdir, cfg, families=["error-masking", "half-finished"], top=None)
    text = prompts["prompts/scout-error-masking.md"]
    assert "tests/test_a.py" not in text.split("Leads (deterministic signals")[1]
    assert "Families disabled on tests: error-masking" in text
    entry = next(e for e in plan["entries"] if e["family"] == "error-masking")
    assert entry["leads"] == 0


def test_cli_writes_plan_and_prompts(corpus_workdirs: dict[str, tuple[Path, Path]]) -> None:
    _, workdir = corpus_workdirs["web-ts"]
    assert _main(["--workdir", str(workdir), "--families", "quick", "--top", "3"]) == 0
    plan = json.loads((workdir / "scan-plan.json").read_bytes())
    assert plan["top"] == 3
    for entry in plan["entries"]:
        prompt = (workdir / entry["prompt"]).read_bytes()
        assert b"\r" not in prompt and prompt.endswith(b"\n")
        text = prompt.decode("utf-8")
        assert "hotspot" in text.lower() and "Severity rubric" in text
    assert (workdir / "scan-plan.json").read_bytes().count(b"\r") == 0
    assert _main(["--workdir", str(workdir / "missing")]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -q`
Expected: `ModuleNotFoundError: No module named 'plan_scan'`.

- [ ] **Step 3: Write `plan_scan.py`**

```python
"""Decide which scouts run and render their prompts (spec 2.4, 4.6).

Reads ``inventory.json``, ``coupling.json``, ``patterns.json`` and
``rule-findings.json`` from ``--workdir`` (an absent ``tool-signals.json`` means
every tool skipped), applies the adaptive rule, and writes ``scan-plan.json``
plus one ``prompts/scout-<family>.md`` per dispatched family. SKILL.md (phase 3)
dispatches exactly the plan's entries. In phase 2 ``chunked`` is always false and
the chunking thresholds are recorded only.

Leads are one union of deterministic signals per family (the table in the plan
for this phase); at most ``LEAD_CAP`` lines reach a prompt, hotspot-band files
first. Path-class disables from ``families.per_path_class`` drop leads before
the adaptive rule counts them, and the prompt names the disabled families.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from categories import FAMILIES, render_scout_prompt
from config import FAMILY_SETS, ConfigError, load_config
from inventory import write_json

SCHEMA_VERSION: Final[int] = 2
LEAD_CAP: Final[int] = 40
KIND_ORDER: Final[tuple[str, ...]] = (
    "hotspot", "coupling", "pattern", "satd", "artefact", "cycle", "inventory", "docs", "tests",
)
KIND_TITLE: Final[dict[str, str]] = {
    "hotspot": "Hotspot-band files (score)",
    "coupling": "Change-coupled pairs",
    "pattern": "Pattern leads",
    "satd": "Self-admitted debt markers",
    "artefact": "Artefacts",
    "cycle": "Import cycles (approximate, lead only)",
    "inventory": "Inventory signals",
    "docs": "Documentation and structure signals",
    "tests": "Test signals",
}
PATTERN_FAMILIES: Final[frozenset[str]] = frozenset(
    {"dead-code", "error-masking", "half-finished", "security", "test-quality", "pipeline-infra"}
)


@dataclass(slots=True)
class Lead:
    kind: str
    path: str
    line: int | None
    text: str
    score: float = 0.0


@dataclass(slots=True)
class ScanDocs:
    inventory: dict[str, Any]
    coupling: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    rules: dict[str, Any] = field(default_factory=dict)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_bytes())
    return loaded if isinstance(loaded, dict) else {}


def load_docs(workdir: Path) -> ScanDocs:
    inventory = _read_json(workdir / "inventory.json")
    if not inventory:
        raise FileNotFoundError(f"{workdir / 'inventory.json'} not found; run inventory.py first")
    return ScanDocs(
        inventory=inventory,
        coupling=_read_json(workdir / "coupling.json"),
        patterns=_read_json(workdir / "patterns.json"),
        rules=_read_json(workdir / "rule-findings.json"),
    )


# --- path classes and disables ----------------------------------------------------


def _path_classes(docs: ScanDocs) -> dict[str, str]:
    classes = {str(e["path"]): str(e.get("path_class", "source")) for e in docs.inventory.get("files", [])}
    for entries in (docs.inventory.get("artefacts") or {}).values():
        for artefact in entries:
            classes.setdefault(str(artefact["path"]), str(artefact.get("path_class", "source")))
    return classes


def disabled_families(config: dict[str, Any], path_class: str) -> set[str]:
    rule = (config.get("families", {}).get("per_path_class") or {}).get(path_class) or {}
    disable = rule.get("disable", [])
    if disable == "all":
        return set(FAMILIES)
    return {str(name) for name in disable}


def disabled_note(config: dict[str, Any]) -> str:
    lines = []
    for path_class in sorted((config.get("families", {}).get("per_path_class") or {})):
        names = disabled_families(config, path_class)
        if not names:
            continue
        label = "all families" if names == set(FAMILIES) else ", ".join(sorted(names))
        lines.append(f"Families disabled on {path_class}: {label}")
    return "\n".join(lines) if lines else "No path-class disables are configured."


# --- lead sources -------------------------------------------------------------------


def _files(docs: ScanDocs) -> list[dict[str, Any]]:
    return [e for e in docs.inventory.get("files", []) if isinstance(e, dict)]


def _source_files(docs: ScanDocs) -> list[dict[str, Any]]:
    return [e for e in _files(docs) if e.get("path_class") == "source"]


def _band(docs: ScanDocs) -> list[Lead]:
    scores = {str(e["path"]): float(e.get("hotspot_score") or 0.0) for e in _files(docs)}
    return [Lead("hotspot", p, None, f"score {scores.get(p, 0.0):.2f}", scores.get(p, 0.0))
            for p in docs.inventory.get("hotspot_band", [])]


def _pairs(docs: ScanDocs, *, cross_only: bool = False) -> list[Lead]:
    out = []
    for pair in docs.coupling.get("pairs", []):
        if cross_only and not pair.get("cross_directory"):
            continue
        text = f"<-> {pair['b']} shared={pair['shared_commits']} ratio={pair['ratio']}"
        out.append(Lead("coupling", str(pair["a"]), None, text, float(pair["ratio"])))
    return out


def _pattern_leads(docs: ScanDocs, family: str, *, rule: str | None = None) -> list[Lead]:
    out = []
    for item in (docs.patterns.get("leads") or {}).get(family, []):
        if rule is not None and item.get("rule") != rule:
            continue
        out.append(Lead("pattern", str(item["file"]), int(item["line"]),
                        f"{family}:{item['rule']}: {item['quote']}"))
    return out


def _satd(docs: ScanDocs) -> list[Lead]:
    out = []
    for item in docs.patterns.get("satd", []):
        text = (f"{item['marker']} age_days={item.get('age_days')} "
                f"ticket={bool(item.get('ticket_ref'))}: {item['quote']}")
        out.append(Lead("satd", str(item["file"]), int(item["line"]), text))
    return out


def _artefacts(docs: ScanDocs, classes: tuple[str, ...]) -> list[Lead]:
    out = []
    artefacts = docs.inventory.get("artefacts") or {}
    for cls in classes:
        for artefact in artefacts.get(cls, []):
            if artefact.get("skipped_large"):
                continue
            out.append(Lead("artefact", str(artefact["path"]), None, cls))
    return out


def _top_by(docs: ScanDocs, keys: tuple[str, ...], limit: int, label: str) -> list[Lead]:
    def sort_key(entry: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(-(entry.get(k) or 0) for k in keys)

    ranked = sorted(_source_files(docs), key=sort_key)[:limit]
    return [
        Lead("inventory", str(e["path"]), None,
             " ".join(f"{k}={e.get(k)}" for k in keys) if not label else label.format(**e))
        for e in ranked
        if any((e.get(k) or 0) > 0 for k in keys)
    ]


def _inventory_where(docs: ScanDocs, predicate: Any, text: str) -> list[Lead]:
    return [Lead("inventory", str(e["path"]), None, text.format(**e))
            for e in _source_files(docs) if predicate(e)]


def _docs_leads(docs: ScanDocs) -> list[Lead]:
    block = docs.inventory.get("docs") or {}
    out = []
    for ref in block.get("dangling_refs", []):
        if isinstance(ref, dict):
            out.append(Lead("docs", str(ref.get("doc", "README.md")), ref.get("line"),
                            f"dangling: {ref.get('token')}"))
        else:
            out.append(Lead("docs", "README.md", None, f"dangling: {ref}"))
    for doc, days in (block.get("stale_vs_code_days") or {}).items():
        if isinstance(days, int) and days > 0:
            out.append(Lead("docs", str(doc), None, f"stale {days} days behind the code"))
    for flag, label in (("contributing_present", "CONTRIBUTING"), ("adr_dir_present", "ADR directory"),
                        ("changelog_present", "CHANGELOG")):
        if block.get(flag) is False:
            out.append(Lead("docs", "README.md", None, f"missing: {label}"))
    return out


def _cycles(docs: ScanDocs) -> list[Lead]:
    return [Lead("cycle", str(c["members"][0]), None, "members: " + ", ".join(c["members"]))
            for c in docs.coupling.get("cycles", []) if c.get("members")]


def _structure(docs: ScanDocs) -> list[Lead]:
    out = [Lead("docs", str(e["from"]), None,
                f"-> {e['to']} instability {e['from_instability']} depends on {e['to_instability']}")
           for e in docs.coupling.get("unstable_edges", [])]
    out += [Lead("docs", str(name), None, "declared: boundary tooling")
            for name in docs.inventory.get("boundary_tooling", [])]
    return out


def _tests_leads(docs: ScanDocs) -> list[Lead]:
    band = set(docs.inventory.get("hotspot_band", []))
    out = [Lead("tests", str(e["path"]), None, "no mapped test")
           for e in _source_files(docs) if e["path"] in band and not e.get("mapped_tests")]
    out += _inventory_where(
        docs, lambda e: isinstance(e.get("untested_change_share"), float) and e["untested_change_share"] >= 0.5,
        "untested_change_share={untested_change_share}")
    out += _pattern_leads(docs, "half-finished", rule="skip-marker")
    gate = (docs.inventory.get("tests") or {}).get("coverage_gate")
    if gate:
        out.append(Lead("tests", "coverage", None, f"coverage_gate: {gate}"))
    return out


def _test_quality_extras(docs: ScanDocs) -> list[Lead]:
    out = []
    retry = (docs.inventory.get("tests") or {}).get("ci_retry_config")
    if retry:
        out.append(Lead("tests", "ci", None, f"ci_retry_config: {retry}"))
    out += _inventory_where(docs, lambda e: (e.get("flaky_commits") or 0) > 0,
                            "flaky_commits={flaky_commits}")
    return out


def _migration_rule_leads(docs: ScanDocs) -> list[Lead]:
    return [Lead("artefact", str(item["file"]), item.get("line"), f"{item['rule']}: {item['quote']}")
            for item in (docs.rules.get("leads") or {}).get("migration", [])]


def _raw_leads(family: str, docs: ScanDocs) -> list[Lead]:
    if family == "complex-units":
        return _band(docs) + _top_by(docs, ("longest_indented_run", "deep_indent_lines", "max_indent"), 10, "")
    if family == "god-classes":
        return _band(docs) + _top_by(docs, ("loc", "fan_in_approx"), 10, "") + _pairs(docs)
    if family == "duplication":
        return _band(docs) + _pairs(docs)
    if family == "dead-code":
        dead = _inventory_where(
            docs, lambda e: e.get("fan_in_approx") == 0 and (e.get("churn") or 0) == 0, "fan_in=0 churn=0")
        return _band(docs) + dead + _pattern_leads(docs, "dead-code")
    if family == "error-masking":
        return _band(docs) + _pattern_leads(docs, "error-masking")
    if family == "test-gaps":
        return _band(docs) + _tests_leads(docs)
    if family == "half-finished":
        return _band(docs) + _satd(docs) + _pattern_leads(docs, "half-finished")
    if family == "migration":
        moved = _inventory_where(docs, lambda e: (e.get("migration_commits") or 0) > 0,
                                 "migration_commits={migration_commits}")
        return _band(docs) + moved + _migration_rule_leads(docs) + _pairs(docs)
    if family == "dependency-debt":
        return _artefacts(docs, ("manifest", "lockfile", "runtime_version", "governance"))
    if family == "doc-drift":
        return _docs_leads(docs)
    if family == "architecture":
        return _band(docs) + _cycles(docs) + _pairs(docs, cross_only=True) + _structure(docs)
    if family == "security":
        return _pattern_leads(docs, "security")
    if family == "test-quality":
        return _pattern_leads(docs, "test-quality") + _test_quality_extras(docs)
    if family == "pipeline-infra":
        return _pattern_leads(docs, "pipeline-infra") + _artefacts(docs, ("ci", "container", "iac"))
    raise KeyError(family)


def leads_for(family: str, docs: ScanDocs, config: dict[str, Any]) -> list[Lead]:
    """Filtered, ordered, capped leads for one family (hotspot-band first, then path)."""
    classes = _path_classes(docs)
    band = set(docs.inventory.get("hotspot_band", []))
    kept = [
        lead for lead in _raw_leads(family, docs)
        if family not in disabled_families(config, classes.get(lead.path, "source"))
    ]
    kept.sort(key=lambda lead: (
        KIND_ORDER.index(lead.kind), lead.path not in band, -lead.score, lead.path, lead.line or 0,
    ))
    return kept[:LEAD_CAP]


def render_leads(leads: list[Lead]) -> str:
    if not leads:
        return "(no deterministic leads for this family; read the hotspot band and the tree)\n"
    lines: list[str] = []
    current = ""
    for lead in leads:
        if lead.kind != current:
            current = lead.kind
            lines.append(f"{KIND_TITLE[current]}:")
        where = f"{lead.path}:{lead.line}" if lead.line is not None else lead.path
        lines.append(f"- {where} {lead.text}")
    return "\n".join(lines) + "\n"


# --- plan -----------------------------------------------------------------------------


def _resolve_set(config: dict[str, Any], families: str | list[str] | None) -> tuple[str, list[str]]:
    if families is None:
        families = config["families"]["enabled"]
    if isinstance(families, list):
        unknown = [f for f in families if f not in FAMILIES]
        if unknown:
            raise ConfigError(f"unknown families: {unknown}")
        return "explicit", [f for f in FAMILIES if f in families]
    if "," in families:
        return _resolve_set(config, [f.strip() for f in families.split(",") if f.strip()])
    if families not in FAMILY_SETS:
        raise ConfigError(f"families must be default, quick, deep or a list, got {families!r}")
    return families, list(FAMILY_SETS[families])


def _repo_summary(inventory: dict[str, Any]) -> str:
    languages = ", ".join(str(lang) for lang in inventory.get("languages", [])) or "none detected"
    git = "yes" if inventory.get("git_available") else "no"
    return (f"root: {inventory.get('root')}, {inventory.get('total_files')} files, "
            f"{inventory.get('total_loc')} LOC, languages: {languages}; git: {git}")


def build_plan(
    workdir: Path,
    config: dict[str, Any],
    *,
    families: str | list[str] | None,
    top: int | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """The scan-plan document and every rendered prompt keyed by its relative path."""
    docs = load_docs(workdir)
    set_name, wanted = _resolve_set(config, families)
    explicit = set_name == "explicit"
    disabled = {str(name) for name in config["families"].get("disabled", [])}
    summary = _repo_summary(docs.inventory)
    note = disabled_note(config)
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    prompts: dict[str, str] = {}
    for family in FAMILIES:
        if family in disabled:
            skipped.append({"family": family, "reason": "disabled"})
            continue
        if family not in wanted:
            skipped.append({"family": family, "reason": "not in set"})
            continue
        leads = leads_for(family, docs, config)
        if not leads and not explicit:
            skipped.append({"family": family, "reason": "no leads"})
            continue
        prompt_path = f"prompts/scout-{family}.md"
        prompts[prompt_path] = render_scout_prompt(
            family, repo_summary=summary, leads_block=render_leads(leads),
            scout_cap=int(config["scout_cap"]), disabled_note=note,
        )
        entries.append({"family": family, "module": None, "prompt": prompt_path,
                        "output": f"scouts/{family}.json", "leads": len(leads)})
    plan = {
        "schema_version": SCHEMA_VERSION,
        "set": set_name,
        "top": int(top if top is not None else config["top"]),
        "chunked": False,
        "thresholds": dict(config["chunking"]),
        "entries": entries,
        "families_run": [e["family"] for e in entries],
        "families_skipped": skipped,
    }
    return plan, prompts


def write_plan(workdir: Path, plan: dict[str, Any], prompts: dict[str, str]) -> None:
    for rel, text in prompts.items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    write_json(workdir / "scan-plan.json", plan)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan the scout dispatch and render its prompts")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding the signal files")
    parser.add_argument("--families", default=None,
                        help="default, quick, deep or a comma-separated list (default: config)")
    parser.add_argument("--top", type=int, default=None, help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    try:
        docs = load_docs(workdir)
        config = load_config(Path(str(docs.inventory.get("root", "."))))
        plan, prompts = build_plan(workdir, config, families=args.families, top=args.top)
    except (FileNotFoundError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_plan(workdir, plan, prompts)
    print(f"planned {len(plan['entries'])} scout(s); skipped {len(plan['families_skipped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

Note on `_top_by`: pass `label=""` to render `key=value` pairs; the helper's signature keeps `label` so `_inventory_where` and `_top_by` share one rendering idiom. `fnmatch` is imported for `traps` glob matching in Task 6; remove the import here if ruff reports it unused (F401) and add it there.

- [ ] **Step 4: Run the tests, fill `EXPECTED_RUN`, verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_plan_scan.py -q`. The first run fails only on `EXPECTED_RUN` (empty sets). Print the three `families_run` lists (add a temporary `print` or run `python scripts/plan_scan.py --workdir <wd> --families deep` over each replayed fixture), copy them into `EXPECTED_RUN`, state them in the report, and rerun until green. Every family with a planted item (except `ownership`) must appear; if one does not, the lead source table above is wrong for that family: fix the source, not the expectation.

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md` script table: add the row `| \`plan_scan.py --workdir .tech-debt [--families <set>] [--top N]\` | \`inventory.json\`, \`coupling.json\`, \`patterns.json\`, \`rule-findings.json\` | \`scan-plan.json\`, \`prompts/scout-<family>.md\` | the adaptive rule (a family runs only when it has at least one lead after path-class disables), the 40-lead cap with hotspot-band files first, the fourteen family blocks; \`chunked\` is always false until phase 4 |`. `README.md` output-formats table: add `| \`scan-plan.json\` | \`plan_scan.py\` | \`{schema_version: 2, set, top, chunked, thresholds{}, entries[{family, module, prompt, output, leads}], families_run[], families_skipped[{family, reason}]}\` |`. Run the gate. Commit:

```
feat(tech-debt-scan): plan_scan.py with the adaptive rule and per-family leads
```

---
### Task 5: `merge_findings.py`

**Files:**
- Create: `skills/tech-debt-scan/scripts/merge_findings.py`
- Test: `skills/tech-debt-scan/tests/test_merge_findings.py`
- Modify: `docs/architecture.md`, `README.md` (rows for `candidates.json`)

**Interfaces:**
- Consumes: `fingerprint`, `find_quote`, `signals_for` (`evidence.py`); `redact` (`redaction.py`); `FAMILIES` (`categories.py`); `validate_debt_type`, `validate_effort`, `validate_type_id`, `ValidationError` (`validation.py`); `write_json` (`inventory.py`); `disabled_families` (`plan_scan.py`); the workdir files `scan-plan.json`, `scouts/<family>.json`, `rule-findings.json`, `inventory.json`, `coupling.json`, `patterns.json`; config `suppressions`, `families.per_path_class`.
- Produces: `merge(workdir: Path, root: Path, config: dict[str, Any], *, today: date | None = None) -> dict[str, Any]` (the `candidates.json` document); `CLUSTER_WINDOW = 10`; `EFFORT_RANK = {"S": 0, "M": 1, "L": 2}`.
- CLI: `python scripts/merge_findings.py --workdir .tech-debt`; exit 2 when `scan-plan.json` or `inventory.json` is missing.

**Confidence:** 92% (each step of spec 4.7 is a pure function over documents whose shapes Tasks 1 to 4 fix; the quote search is Task 1's `find_quote`; the one judgement call, that rule candidates corroborate but never merge with scout candidates, is recorded as a ruling in the design below).

**Design (fixed):**

1. Load the plan; for each entry read `scouts/<output>` when present (a missing scout file is recorded in `stats[family].missing_file = 1` and skipped; SKILL.md treats a missing file as exit 5 upstream, the merge never aborts).
2. Validate each finding: `title` non-empty string (truncated to 80), `family` equal to the scout's family, `debt_type` valid, `type_id` valid when present (else null), `severity` int 1 to 5, `effort` in S/M/L, `evidence` a non-empty list of dicts with `file` str, `line_start`/`line_end` ints or null, `quote` str; `note` string (truncated to 300, default ""); `signals_cited` list of strings (default []). Anything else drops the item with a reason string appended to `stats[family].dropped_reasons` and `dropped += 1`.
3. Normalise each evidence path: replace backslashes, strip a leading `./`, resolve against `root`; an evidence item outside `root` or on a missing file is dropped (counted under `quote_failed` only if no evidence survives).
4. Verify each quote with `find_quote` on the file's lines (`read_bytes().decode("utf-8", "replace").splitlines()`); the real range replaces the cited one; `quote_verified: true`. Unverified evidence is dropped. A finding with no verified evidence goes to `open_questions` as `{"file", "line_start", "question": "<title>", "reason": "quote not found"}` and counts under `quote_failed`.
5. Fingerprint on the primary (first verified) evidence item: `fingerprint(family, file, quote)`; record `quote_hash`.
6. Cluster scout candidates: same family and same primary file, ranges overlapping or within `CLUSTER_WINDOW` lines (compare `[line_start, line_end]` of primaries); union evidence (deduplicated by `(file, line_start, line_end)`), max severity, min effort by `EFFORT_RANK`, `title` and `note` from the highest-severity member (tie: lowest fingerprint), `confirmed_by` union, `signals_cited` union (sorted), `type_id` from the same member, `fingerprint` of the surviving primary (the member with the lowest fingerprint keeps its identity); `stats[family].clustered` counts members absorbed.
7. Corroboration on each scout candidate: `scout:<family>` always; `pattern:<rule>` for every pattern lead of any family on the same file within `CLUSTER_WINDOW` lines of any evidence line; `satd` for a SATD entry likewise; `rule:<rule_id>` for a rule finding whose evidence overlaps the same way; `coupling` when the primary file's `coupling_degree > 0`; `hotspot` when `in_hotspot_band`; `signal:no-mapped-tests` for family `test-gaps` when the primary file's inventory entry has empty `mapped_tests`. **Ruling:** rule candidates keep their own identity (source `rule`, tier A) and are appended unchanged after the scout candidates; they corroborate a scout candidate but never merge into it, so a tier A rule fact is never diluted by a scout claim (cost if wrong: two neighbouring entries for one site, which the design report shows side by side).
8. Attach `signals` with `signals_for(inventory, primary file)`.
9. Suppressions: `config["suppressions"]` items `{fingerprint, reason, until}`; drop when the fingerprint matches and `until` is null or `until >= today` (ISO date); `stats[family].suppressed += 1`. Path-class disables: drop when the family is in `disabled_families(config, signals.path_class)`; `stats[family].disabled += 1` (a sixth stats key, added to spec 4.7 in this task).
10. Redact every quote, title and note with `redact` (phase 1 invariant), then emit candidates sorted by `(family order in FAMILIES, primary file, line_start, fingerprint)`.

Candidate key order: `fingerprint, quote_hash, family, debt_type, type_id, title, severity, effort, source, rule_id, note, evidence, confirmed_by, signals_cited, signals, tier`. Rule candidates already carry this order from `rules.py` (verify with `list(candidate)` in the test). `tier` is `null` for scout candidates.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_merge_findings.py`:

```python
"""merge_findings.py: validation, quote verification, clustering, corroboration (spec 4.7)."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from config import DEFAULTS
from evidence import fingerprint
from inventory import build_all, write_json, write_outputs
from merge_findings import CLUSTER_WINDOW, _main, merge
from patterns import run_patterns
from rules import run_rules

SECRET = "sk_live_51H8f2kL9mN3pQ7rS4tU6vW"


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "pay.py").write_text(
        "import logging\n"
        "log = logging.getLogger(__name__)\n"
        "\n"
        "def refund(order):\n"
        "    try:\n"
        "        order.refund()\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "def charge(order):\n"
        "    # TODO: retry on timeout\n"
        f'    token = "{SECRET}"\n'
        "    return order.charge(token)\n",
        encoding="utf-8",
    )
    (repo / "src" / "util.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    workdir = tmp_path / "wd"
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, _ = run_patterns(repo, inventory, DEFAULTS, blame=False)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json", {"schema_version": 2, "findings": findings, "leads": leads})
    write_json(workdir / "scan-plan.json", {
        "schema_version": 2, "set": "explicit", "top": 5, "chunked": False,
        "thresholds": DEFAULTS["chunking"],
        "entries": [
            {"family": "error-masking", "module": None, "prompt": "prompts/scout-error-masking.md",
             "output": "scouts/error-masking.json", "leads": 1},
            {"family": "security", "module": None, "prompt": "prompts/scout-security.md",
             "output": "scouts/security.json", "leads": 1},
        ],
        "families_run": ["error-masking", "security"], "families_skipped": [],
    })
    return repo, workdir


def _finding(family: str, title: str, file: str, start: int, end: int, quote: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "title": title, "family": family, "debt_type": "code", "type_id": None,
        "severity": 3, "effort": "M", "signals_cited": [],
        "evidence": [{"file": file, "line_start": start, "line_end": end, "quote": quote}],
        "note": "n",
    }
    item.update(extra)
    return item


def _scout(workdir: Path, family: str, findings: list[dict[str, Any]], **channels: Any) -> None:
    doc = {"family": family, "module": None, "findings": findings,
           "open_questions": channels.get("open_questions", []),
           "looks_bad_but_fine": channels.get("looks_bad_but_fine", []),
           "not_assessed": []}
    write_json(workdir / "scouts" / f"{family}.json", doc)


def test_invented_quote_becomes_an_open_question_and_moved_quote_gets_real_range(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(workdir, "error-masking", [
        _finding("error-masking", "swallowed", "src/pay.py", 7, 8, "except Exception:\n        pass"),
        _finding("error-masking", "moved", "src/pay.py", 1, 2, "except   Exception:  pass"),
        _finding("error-masking", "invented", "src/pay.py", 3, 3, "this line does not exist"),
    ])
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert list(doc) == ["schema_version", "candidates", "open_questions", "looks_bad_but_fine", "stats"]
    scout_candidates = [c for c in doc["candidates"] if c["source"] == "scout"]
    assert len(scout_candidates) == 1, "the two verified findings cluster (same range)"
    cand = scout_candidates[0]
    assert cand["evidence"][0] == {"file": "src/pay.py", "line_start": 7, "line_end": 8,
                                   "quote": "except Exception:\n        pass", "quote_verified": True}
    assert cand["tier"] is None
    assert doc["open_questions"] == [
        {"file": "src/pay.py", "line_start": 3, "question": "invented", "reason": "quote not found"}
    ]
    stats = doc["stats"]["error-masking"]
    assert list(stats) == ["raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled"]
    assert stats["raw"] == 3 and stats["quote_failed"] == 1 and stats["clustered"] == 1


def test_fingerprint_cluster_and_corroboration(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(workdir, "error-masking", [
        _finding("error-masking", "a", "src/pay.py", 7, 8, "except Exception:\n        pass", severity=2, effort="L"),
        _finding("error-masking", "b", "src/pay.py", 5, 6, "try:\n        order.refund()", severity=4, effort="S",
                 signals_cited=["pattern:error-masking:swallowed-catch"]),
    ])
    _scout(workdir, "security", [])
    doc = merge(workdir, repo, DEFAULTS)
    cand = next(c for c in doc["candidates"] if c["source"] == "scout")
    assert cand["severity"] == 4 and cand["effort"] == "S" and cand["title"] == "b"
    assert len(cand["evidence"]) == 2
    fp, qh = fingerprint("error-masking", "src/pay.py", "try:\n        order.refund()")
    assert cand["fingerprint"] in {fp, fingerprint("error-masking", "src/pay.py", "except Exception:\n        pass")[0]}
    assert "scout:error-masking" in cand["confirmed_by"]
    assert any(c.startswith("pattern:") for c in cand["confirmed_by"])
    assert cand["signals_cited"] == ["pattern:error-masking:swallowed-catch"]
    assert list(cand) == ["fingerprint", "quote_hash", "family", "debt_type", "type_id", "title",
                          "severity", "effort", "source", "rule_id", "note", "evidence",
                          "confirmed_by", "signals_cited", "signals", "tier"]
    assert list(cand["signals"]) == ["hotspot_score", "churn", "coupling_degree", "fan_in_approx",
                                     "path_class", "in_hotspot_band"]


def test_far_apart_findings_do_not_cluster_and_satd_corroborates(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    lines = ["x = %d" % i for i in range(1, 40)]
    (repo / "src" / "long.py").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _scout(workdir, "error-masking", [
        _finding("error-masking", "top", "src/long.py", 1, 1, "x = 1"),
        _finding("error-masking", "bottom", "src/long.py", 1 + CLUSTER_WINDOW + 1, 1 + CLUSTER_WINDOW + 1,
                 f"x = {1 + CLUSTER_WINDOW + 1}"),
    ])
    _scout(workdir, "security", [
        _finding("security", "todo-site", "src/pay.py", 11, 11, "# TODO: retry on timeout"),
    ])
    doc = merge(workdir, repo, DEFAULTS)
    masking = [c for c in doc["candidates"] if c["family"] == "error-masking"]
    assert len(masking) == 2
    todo = next(c for c in doc["candidates"] if c["title"] == "todo-site")
    assert "satd" in todo["confirmed_by"]


def test_malformed_items_are_dropped_and_counted(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    bad = [
        {"title": "no evidence", "family": "security", "debt_type": "code", "severity": 3,
         "effort": "M", "signals_cited": [], "evidence": [], "note": ""},
        _finding("security", "wrong family", "src/pay.py", 12, 12, "token", family="dead-code"),
        _finding("security", "bad severity", "src/pay.py", 12, 12, "token", severity=9),
        _finding("security", "bad type", "src/pay.py", 12, 12, "token", type_id="TD-99"),
        "not a dict",
    ]
    _scout(workdir, "security", bad)  # type: ignore[arg-type]
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    assert [c for c in doc["candidates"] if c["source"] == "scout"] == []
    assert doc["stats"]["security"]["dropped"] == 5


def test_suppression_with_expiry_and_path_class_disable(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    quote = "except Exception:\n        pass"
    fp, _ = fingerprint("error-masking", "src/pay.py", quote)
    _scout(workdir, "error-masking", [_finding("error-masking", "a", "src/pay.py", 7, 8, quote)])
    _scout(workdir, "security", [])
    cfg = deepcopy(DEFAULTS)
    cfg["suppressions"] = [{"fingerprint": fp, "reason": "known", "until": "2026-12-31"}]
    live = merge(workdir, repo, cfg, today=date(2026, 9, 5))
    assert [c for c in live["candidates"] if c["source"] == "scout"] == []
    assert live["stats"]["error-masking"]["suppressed"] == 1
    expired = merge(workdir, repo, cfg, today=date(2027, 1, 1))
    assert len([c for c in expired["candidates"] if c["source"] == "scout"]) == 1
    cfg2 = deepcopy(DEFAULTS)
    cfg2["families"]["per_path_class"]["source"] = {"disable": ["error-masking"]}
    off = merge(workdir, repo, cfg2)
    assert [c for c in off["candidates"] if c["source"] == "scout"] == []
    assert off["stats"]["error-masking"]["disabled"] == 1


def test_secret_is_redacted_everywhere_and_rule_candidates_pass_through(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    (repo / "Dockerfile").write_text("FROM alpine:3.20\nRUN apk add curl\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json", {"schema_version": 2, "findings": findings, "leads": leads})
    _scout(workdir, "security", [
        _finding("security", f'hard-coded token = "{SECRET}"', "src/pay.py", 12, 12, f'token = "{SECRET}"',
                 note=f'token = "{SECRET}" assigned in charge()'),
    ], looks_bad_but_fine=[{"file": "src/util.py", "line_start": 1, "why": "helper by design"}])
    _scout(workdir, "error-masking", [])
    doc = merge(workdir, repo, DEFAULTS)
    text = json.dumps(doc)
    assert SECRET not in text and "sk_l***" in text
    rule = [c for c in doc["candidates"] if c["source"] == "rule"]
    assert rule and all(c["tier"] == "A" for c in rule)
    assert doc["candidates"][-1]["source"] == "rule"
    assert doc["looks_bad_but_fine"] == [{"file": "src/util.py", "line_start": 1, "why": "helper by design"}]


def test_cli(tmp_path: Path) -> None:
    repo, workdir = _repo(tmp_path)
    _scout(workdir, "error-masking", [])
    _scout(workdir, "security", [])
    assert _main(["--workdir", str(workdir)]) == 0
    raw = (workdir / "candidates.json").read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert _main(["--workdir", str(tmp_path / "nowhere")]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q`
Expected: `ModuleNotFoundError: No module named 'merge_findings'`.

- [ ] **Step 3: Write `merge_findings.py`**

```python
"""Turn scout output and rule findings into one verified candidate list (spec 4.7).

Reads ``scan-plan.json`` (which scout files to expect), ``scouts/<family>.json``,
``rule-findings.json``, ``inventory.json``, ``coupling.json`` and
``patterns.json`` from ``--workdir``, and ``.tech-debt.yaml`` from the
repository root. Writes ``candidates.json``.

Steps, in order: validate each scout item (malformed items are dropped and
counted); normalise paths; verify every quote on disk through
``evidence.find_quote`` (a finding with no verified evidence is diverted to
``open_questions`` with reason ``quote not found``); fingerprint on the primary
evidence; cluster same-family, same-file findings within ``CLUSTER_WINDOW``
lines; corroborate from pattern leads, SATD markers, rule findings, coupling
and the hotspot band; attach inventory signals; apply suppressions and
path-class disables; redact every quote, title and note.

Rule findings enter as tier A candidates with ``source: "rule"`` and are never
merged into a scout candidate: they corroborate it (``rule:<id>`` in
``confirmed_by``) and stand beside it, so a verified-by-construction fact is
never diluted by a scout claim.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any, Final

from categories import FAMILIES
from config import ConfigError, load_config
from evidence import find_quote, fingerprint, signals_for
from inventory import write_json
from plan_scan import disabled_families
from redaction import redact
from validation import ValidationError, validate_debt_type, validate_effort, validate_type_id

SCHEMA_VERSION: Final[int] = 2
CLUSTER_WINDOW: Final[int] = 10
EFFORT_RANK: Final[dict[str, int]] = {"S": 0, "M": 1, "L": 2}
STAT_KEYS: Final[tuple[str, ...]] = ("raw", "dropped", "quote_failed", "clustered", "suppressed", "disabled")
TITLE_MAX: Final[int] = 80
NOTE_MAX: Final[int] = 300


def _new_stats() -> dict[str, int]:
    return dict.fromkeys(STAT_KEYS, 0)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_bytes()) if path.is_file() else None


# --- validation -----------------------------------------------------------------------


def _normalise_path(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    rel = raw.replace("\\", "/").strip()
    while rel.startswith("./"):
        rel = rel[2:]
    if rel.startswith("/") or ".." in rel.split("/") or ":" in rel.split("/")[0]:
        return None
    return rel


def _validate(item: Any, family: str) -> dict[str, Any] | str:
    """A cleaned finding, or the reason it was dropped."""
    if not isinstance(item, dict):
        return "not an object"
    title = item.get("title")
    if not isinstance(title, str) or not title.strip():
        return "missing title"
    if item.get("family") != family:
        return f"family {item.get('family')!r} is not {family!r}"
    try:
        validate_debt_type(str(item.get("debt_type")))
        validate_effort(str(item.get("effort")))
        type_id = item.get("type_id")
        if type_id is not None:
            validate_type_id(str(type_id))
    except ValidationError as exc:
        return str(exc)
    severity = item.get("severity")
    if not isinstance(severity, int) or isinstance(severity, bool) or not 1 <= severity <= 5:
        return f"severity {severity!r} out of range"
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "no evidence"
    cleaned: list[dict[str, Any]] = []
    for ev in evidence:
        if not isinstance(ev, dict):
            continue
        rel = _normalise_path(ev.get("file"))
        quote = ev.get("quote")
        start, end = ev.get("line_start"), ev.get("line_end")
        if rel is None or not isinstance(quote, str):
            continue
        cleaned.append({
            "file": rel,
            "line_start": start if isinstance(start, int) and not isinstance(start, bool) else None,
            "line_end": end if isinstance(end, int) and not isinstance(end, bool) else None,
            "quote": quote,
        })
    if not cleaned:
        return "no usable evidence"
    note = item.get("note")
    cited = item.get("signals_cited")
    return {
        "title": title.strip()[:TITLE_MAX],
        "family": family,
        "debt_type": str(item["debt_type"]),
        "type_id": str(type_id) if type_id is not None else None,
        "severity": severity,
        "effort": str(item["effort"]),
        "signals_cited": sorted({str(s) for s in cited}) if isinstance(cited, list) else [],
        "evidence": cleaned,
        "note": (note.strip() if isinstance(note, str) else "")[:NOTE_MAX],
    }


# --- quote verification ---------------------------------------------------------------


class _Files:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._cache:
            path = self.root / rel
            try:
                text = path.read_bytes().decode("utf-8", errors="replace") if path.is_file() else None
            except OSError:
                text = None
            self._cache[rel] = text.splitlines() if text is not None else None
        return self._cache[rel]


def _verify(finding: dict[str, Any], files: _Files) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for ev in finding["evidence"]:
        lines = files.lines(ev["file"])
        if lines is None:
            continue
        found = find_quote(lines, ev["quote"], ev["line_start"], ev["line_end"])
        if found is None:
            continue
        verified.append({"file": ev["file"], "line_start": found[0], "line_end": found[1],
                         "quote": ev["quote"], "quote_verified": True})
    return verified


# --- clustering and corroboration ----------------------------------------------------


def _near(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_start > b_end + CLUSTER_WINDOW or b_start > a_end + CLUSTER_WINDOW)


def _primary(cand: dict[str, Any]) -> dict[str, Any]:
    return cand["evidence"][0]


def _absorb(keep: dict[str, Any], other: dict[str, Any]) -> None:
    seen = {(e["file"], e["line_start"], e["line_end"]) for e in keep["evidence"]}
    for ev in other["evidence"]:
        key = (ev["file"], ev["line_start"], ev["line_end"])
        if key not in seen:
            keep["evidence"].append(ev)
            seen.add(key)
    if (other["severity"], -int(other["fingerprint"], 16)) > (keep["severity"], -int(keep["fingerprint"], 16)):
        keep["title"], keep["note"], keep["type_id"] = other["title"], other["note"], other["type_id"]
        keep["debt_type"] = other["debt_type"]
    keep["severity"] = max(keep["severity"], other["severity"])
    keep["effort"] = min(keep["effort"], other["effort"], key=lambda e: EFFORT_RANK[e])
    keep["signals_cited"] = sorted(set(keep["signals_cited"]) | set(other["signals_cited"]))
    keep["confirmed_by"] = sorted(set(keep["confirmed_by"]) | set(other["confirmed_by"]))


def _cluster(cands: list[dict[str, Any]], stats: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    cands.sort(key=lambda c: (c["family"], _primary(c)["file"], _primary(c)["line_start"], c["fingerprint"]))
    out: list[dict[str, Any]] = []
    for cand in cands:
        p = _primary(cand)
        for keep in out:
            k = _primary(keep)
            if (keep["family"] == cand["family"] and k["file"] == p["file"]
                    and _near(k["line_start"], k["line_end"], p["line_start"], p["line_end"])):
                if cand["fingerprint"] < keep["fingerprint"]:
                    cand, keep = keep, cand  # the lower fingerprint keeps the identity
                    out[out.index(cand)] = keep
                _absorb(keep, cand)
                stats[keep["family"]]["clustered"] += 1
                break
        else:
            out.append(cand)
    return out


def _evidence_lines(cand: dict[str, Any]) -> list[tuple[str, int, int]]:
    return [(e["file"], e["line_start"], e["line_end"]) for e in cand["evidence"]]


def _corroborate(
    cand: dict[str, Any],
    patterns: dict[str, Any],
    rules: list[dict[str, Any]],
    inventory: dict[str, Any],
) -> None:
    sources = set(cand["confirmed_by"])
    spans = _evidence_lines(cand)

    def hits(file: str, line: int | None) -> bool:
        return line is not None and any(f == file and _near(s, e, line, line) for f, s, e in spans)

    for family, leads in (patterns.get("leads") or {}).items():
        for lead in leads:
            if hits(str(lead["file"]), lead.get("line")):
                sources.add(f"pattern:{lead['rule']}")
    for marker in patterns.get("satd", []):
        if hits(str(marker["file"]), marker.get("line")):
            sources.add("satd")
    for rule in rules:
        for ev in rule.get("evidence", []):
            if ev.get("file") and hits(str(ev["file"]), ev.get("line_start")):
                sources.add(f"rule:{rule['rule_id']}")
    signals = cand["signals"]
    if signals["coupling_degree"]:
        sources.add("coupling")
    if signals["in_hotspot_band"]:
        sources.add("hotspot")
    if cand["family"] == "test-gaps":
        entry = next((e for e in inventory.get("files", []) if e["path"] == _primary(cand)["file"]), None)
        if entry is not None and not entry.get("mapped_tests"):
            sources.add("signal:no-mapped-tests")
    cand["confirmed_by"] = sorted(sources)


# --- suppressions and disables --------------------------------------------------------


def _suppressed(cand: dict[str, Any], config: dict[str, Any], today: date) -> bool:
    for item in config.get("suppressions") or []:
        if not isinstance(item, dict) or item.get("fingerprint") != cand["fingerprint"]:
            continue
        until = item.get("until")
        if until is None:
            return True
        try:
            return date.fromisoformat(str(until)) >= today
        except ValueError:
            return True
    return False


# --- assembly -------------------------------------------------------------------------


def _candidate(finding: dict[str, Any], verified: list[dict[str, Any]], inventory: dict[str, Any]) -> dict[str, Any]:
    primary = verified[0]
    fp, quote_hash = fingerprint(finding["family"], primary["file"], primary["quote"])
    return {
        "fingerprint": fp,
        "quote_hash": quote_hash,
        "family": finding["family"],
        "debt_type": finding["debt_type"],
        "type_id": finding["type_id"],
        "title": finding["title"],
        "severity": finding["severity"],
        "effort": finding["effort"],
        "source": "scout",
        "rule_id": None,
        "note": finding["note"],
        "evidence": verified,
        "confirmed_by": [f"scout:{finding['family']}"],
        "signals_cited": finding["signals_cited"],
        "signals": signals_for(inventory, primary["file"]),
        "tier": None,
    }


def _redact_candidate(cand: dict[str, Any]) -> None:
    cand["title"] = redact(cand["title"])
    cand["note"] = redact(cand["note"])
    for ev in cand["evidence"]:
        ev["quote"] = redact(ev["quote"])


def _order(cands: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(c: dict[str, Any]) -> tuple[Any, ...]:
        p = c["evidence"][0] if c["evidence"] else {"file": "", "line_start": 0}
        return (FAMILIES.index(c["family"]) if c["family"] in FAMILIES else len(FAMILIES),
                p.get("file") or "", p.get("line_start") or 0, c["fingerprint"])
    return sorted(cands, key=key)


def merge(workdir: Path, root: Path, config: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """The candidates.json document for the scouts named in the plan."""
    plan = _read_json(workdir / "scan-plan.json")
    inventory = _read_json(workdir / "inventory.json")
    if not isinstance(plan, dict) or not isinstance(inventory, dict):
        raise FileNotFoundError(f"scan-plan.json and inventory.json are required in {workdir}")
    patterns = _read_json(workdir / "patterns.json") or {}
    rules_doc = _read_json(workdir / "rule-findings.json") or {}
    rule_findings = [f for f in rules_doc.get("findings", []) if isinstance(f, dict)]
    today = today or date.today()
    files = _Files(root.resolve())
    stats: dict[str, dict[str, int]] = {}
    scout_cands: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    looks_fine: list[dict[str, Any]] = []
    for entry in plan.get("entries", []):
        family = str(entry["family"])
        stats.setdefault(family, _new_stats())
        doc = _read_json(workdir / str(entry["output"]))
        if not isinstance(doc, dict):
            stats[family]["missing_file"] = 1
            continue
        for q in doc.get("open_questions", []) or []:
            if isinstance(q, dict):
                open_questions.append({"file": q.get("file"), "line_start": q.get("line_start"),
                                       "question": str(q.get("question", "")), "reason": None})
        for item in doc.get("looks_bad_but_fine", []) or []:
            if isinstance(item, dict):
                looks_fine.append({"file": item.get("file"), "line_start": item.get("line_start"),
                                   "why": str(item.get("why", ""))})
        for raw in doc.get("findings", []) or []:
            stats[family]["raw"] += 1
            cleaned = _validate(raw, family)
            if isinstance(cleaned, str):
                stats[family]["dropped"] += 1
                continue
            verified = _verify(cleaned, files)
            if not verified:
                stats[family]["quote_failed"] += 1
                first = cleaned["evidence"][0]
                open_questions.append({"file": first["file"], "line_start": first["line_start"],
                                       "question": cleaned["title"], "reason": "quote not found"})
                continue
            scout_cands.append(_candidate(cleaned, verified, inventory))
    clustered = _cluster(scout_cands, stats)
    kept: list[dict[str, Any]] = []
    for cand in clustered:
        _corroborate(cand, patterns, rule_findings, inventory)
        if _suppressed(cand, config, today):
            stats[cand["family"]]["suppressed"] += 1
            continue
        if cand["family"] in disabled_families(config, str(cand["signals"]["path_class"] or "source")):
            stats[cand["family"]]["disabled"] += 1
            continue
        _redact_candidate(cand)
        kept.append(cand)
    for cand in rule_findings:
        stats.setdefault(cand["family"], _new_stats())
        if _suppressed(cand, config, today):
            stats[cand["family"]]["suppressed"] += 1
            continue
    rule_kept = [c for c in rule_findings if not _suppressed(c, config, today)]
    return {
        "schema_version": SCHEMA_VERSION,
        "candidates": _order(kept) + _order(rule_kept),
        "open_questions": open_questions,
        "looks_bad_but_fine": looks_fine,
        "stats": stats,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge scout output and rule findings into candidates.json")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding the scan files")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    inventory = _read_json(workdir / "inventory.json")
    if not isinstance(inventory, dict) or not (workdir / "scan-plan.json").is_file():
        print(f"error: scan-plan.json and inventory.json are required in {workdir}", file=sys.stderr)
        return 2
    root = Path(str(inventory.get("root", ".")))
    try:
        config = load_config(root)
        doc = merge(workdir, root, config)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(workdir / "candidates.json", doc)
    print(f"{len(doc['candidates'])} candidate(s), {len(doc['open_questions'])} open question(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

Note the double suppression loop over rule findings in `merge`: collapse it into one pass that both counts and filters (the sketch shows the intent; the implementer writes it once). `open_questions` from the scouts' own channel carry `reason: null`; diverted findings carry `"quote not found"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_merge_findings.py -q`

- [ ] **Step 5: Spec note, docs, gate, commit**

Spec 4.7 `stats` line: add `"disabled": 0` after `"suppressed": 0` and one sentence "Rule findings are appended unchanged after the scout candidates and corroborate rather than merge." `docs/architecture.md` row for `merge_findings.py --workdir .tech-debt` (inputs: the plan, scouts, rule findings, inventory, coupling, patterns; output `candidates.json`; one line each for quote verification, clustering within 10 lines, corroboration sources, suppressions and path-class disables, redaction). `README.md` row for `candidates.json` with the key list. Run the gate. Commit:

```
feat(tech-debt-scan): merge_findings.py verifies quotes, clusters and corroborates candidates
```

---
### Task 6: `verify_prompts.py`, the budget rule and the verifier contract

**Files:**
- Create: `skills/tech-debt-scan/scripts/verify_prompts.py`
- Test: `skills/tech-debt-scan/tests/test_verify_prompts.py`
- Modify: `docs/architecture.md`, `README.md` (rows for `verify-plan.json`)

**Interfaces:**
- Consumes: `candidates.json`, `inventory.json`, `coupling.json`; config `verifier.*`, `ranking.*`, `traps`, `top`; `FAMILY_BLOCKS[family].verifier_questions` (`categories.py`); `redact` (`redaction.py`); `write_json` (`inventory.py`); `provisional_priority(candidate, maxima, weights, tractability)` from Task 8 is NOT available yet, so this task defines the 4.9 formula once in `evidence.py` as `priority_terms(...)` (see Step 3) and Task 8 reuses it.
- Produces: `select_candidates(candidates, config, top) -> tuple[list[dict], list[str]]` (selected candidates in priority order, unverified fingerprints); `build_batches(selected, batch_size) -> list[list[dict]]`; `render_verify_prompt(batch, *, root, inventory, coupling, config) -> str`; `build_verify_plan(workdir, root, config, top) -> tuple[dict, dict[str, str]]`; `VERDICT_SCHEMA: dict[str, Any]`; `VERDICT_VALUES = ("confirm", "downgrade", "reject", "refer")`.
- CLI: `python scripts/verify_prompts.py --workdir .tech-debt [--top N]`; writes `verify-plan.json` and `prompts/verify-<nn>.md` (two-digit, from 01); exit 2 when `candidates.json` is missing.

**Confidence:** 91% (the budget rule and batching are arithmetic over the candidate list; context extraction reads files already verified by the merge; the referrer list uses `reference_graph.build_reference_graph` over `GraphFile`s built from the inventory, an API read at plan time). Mitigation embedded: the referrer computation is wrapped so a graph failure yields "referrers: not computed" rather than an abort, and the test asserts the prompt still renders.

**Design (fixed):**

- `priority_terms` (in `evidence.py`, shared with Task 8): given a candidate, repo maxima `{"hotspot": h, "coupling": c, "fan_in": f}`, weights `{wH, wC, wF}`, tractability `{S, M, L}` and a tier, returns the dict `{"severity", "H", "C", "F", "interest", "tier_weight", "tractability", "priority"}` with `H = hotspot_score / h`, `C = coupling_degree / c`, `F = fan_in_approx / f` (0 when null, or when the file's `fan_in_mode` is `anywhere`), each 0 when the maximum is 0; `interest = 1 + wH*H + wC*C + wF*F`; `tier_weight` A 1.0, B 0.7, C 0.35, null 0.7 (the provisional tier B of 4.8); `priority = round(severity * interest * tier_weight * tractability, 4)`. `repo_maxima(inventory)` computes the three maxima over `files[]`, counting `fan_in_approx` only for entries with `fan_in_mode == "import-lines"`.
- Budget rule (4.8): `n = max(top_multiple * top, min_candidates)`; rank every candidate with `tier` null by provisional priority (tier B), tie-break fingerprint ascending; take the first `n`; add every candidate with `severity >= always_min_severity` and every candidate in `always_families`; truncate to `max_candidates` by the same order; tier A candidates are never selected; the rest are `unverified`.
- Batches: sort selected by `(primary file, -priority, fingerprint)` and chunk by `batch_size`, so candidates on one file share a batch where possible.
- Prompt per batch, in this order: a header (read-only rule, the exploration allowance: "you may open up to three further files you name, chosen from the referrers, the change-coupled files or the callees of the cited span; list them in `opened`"), then per candidate: `fingerprint`, `title`, `family`, `severity`, `effort`, `note`, `confirmed_by`, the deterministic signals, each evidence span rendered from disk with `context_lines` (30) lines of context each side and 1-based line numbers (`   120 | text`, the cited lines marked with `>`), the change-coupled files (`coupling.pairs` with the primary file), approximate referrers (files whose import lines reference the primary file's stem, from `build_reference_graph` edges; "not computed" on any exception), the family's verifier questions, and the traps (config `traps` whose `family` matches and whose `path_glob` `fnmatch`es the primary file). Every rendered line passes through `redact`. The verifier prompt shares no text with the scout prompts beyond the read-only rule (the test checks `SEVERITY_RUBRIC` is absent).
- Verdict contract appended to every prompt: a JSON array of `{fingerprint, verdict, proof (<=150 words citing line numbers), severity, effort, trap_matched, checked, opened}`.
- `verify-plan.json` keys: `schema_version, top, batch_size, selected, unverified, batches[{prompt, output, fingerprints}]`.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_verify_prompts.py`:

```python
"""verify_prompts.py: budget rule, batching, context, traps, contract (spec 4.8)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from categories import SEVERITY_RUBRIC
from config import DEFAULTS
from evidence import fingerprint, priority_terms, repo_maxima
from inventory import build_all, write_json, write_outputs
from verify_prompts import (
    VERDICT_SCHEMA,
    _main,
    build_batches,
    build_verify_plan,
    render_verify_prompt,
    select_candidates,
)


def _cand(family: str, file: str, start: int, sev: int, *, tier: str | None = None,
          hotspot: float = 0.0, coupling: int = 0, effort: str = "M") -> dict[str, Any]:
    quote = f"line {start}"
    fp, qh = fingerprint(family, file, quote)
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code", "type_id": None,
        "title": f"{family} {file}:{start}", "severity": sev, "effort": effort, "source": "scout",
        "rule_id": None, "note": "n",
        "evidence": [{"file": file, "line_start": start, "line_end": start, "quote": quote,
                      "quote_verified": True}],
        "confirmed_by": [f"scout:{family}"], "signals_cited": [],
        "signals": {"hotspot_score": hotspot, "churn": 0, "coupling_degree": coupling,
                    "fan_in_approx": None, "path_class": "source", "in_hotspot_band": hotspot > 0.5},
        "tier": tier,
    }


def test_priority_terms_reproduce_the_spec_worked_example() -> None:
    maxima = {"hotspot": 1.0, "coupling": 10, "fan_in": 10}
    weights, tract = DEFAULTS["ranking"]["weights"], DEFAULTS["ranking"]["tractability"]
    x = {"severity": 4, "effort": "M",
         "signals": {"hotspot_score": 0.8, "coupling_degree": 4, "fan_in_approx": 2}}
    terms = priority_terms(x, maxima, weights, tract, tier="A", fan_in_mode="import-lines")
    assert terms == {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
                     "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    y = {"severity": 5, "effort": "S", "signals": {"hotspot_score": 0, "coupling_degree": 0, "fan_in_approx": None}}
    assert priority_terms(y, maxima, weights, tract, tier="B", fan_in_mode="import-lines")["priority"] == 3.5
    z = {"severity": 3, "effort": "L", "signals": {"hotspot_score": 1.0, "coupling_degree": 10, "fan_in_approx": 5}}
    assert priority_terms(z, maxima, weights, tract, tier="A", fan_in_mode="import-lines")["priority"] == 4.125
    assert priority_terms(z, maxima, weights, tract, tier="A", fan_in_mode="anywhere")["F"] == 0


def test_budget_rule_floors_inclusions_cap_and_tier_a_exclusion() -> None:
    cands = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(80)]
    cands += [_cand("security", "src/s.py", 1, 1), _cand("dead-code", "src/hi.py", 1, 5),
              _cand("pipeline-infra", "Dockerfile", 1, 3, tier="A")]
    selected, unverified = select_candidates(cands, DEFAULTS, top=5)
    fps = {c["fingerprint"] for c in selected}
    assert len(selected) <= DEFAULTS["verifier"]["max_candidates"] == 72
    assert cands[80]["fingerprint"] in fps, "always_families includes security"
    assert cands[81]["fingerprint"] in fps, "always_min_severity 5"
    assert cands[82]["fingerprint"] not in fps and cands[82]["fingerprint"] not in unverified
    assert len(fps) + len(unverified) == 82
    few = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(20)]
    sel, unv = select_candidates(few, DEFAULTS, top=2)
    assert len(sel) == 20 and unv == [], "max(3N, 30) floor covers all twenty"
    top_multiple = [_cand("dead-code", f"src/f{i}.py", 1, 2) for i in range(40)]
    sel, unv = select_candidates(top_multiple, DEFAULTS, top=12)
    assert len(sel) == 36 and len(unv) == 4, "3N beats the 30 floor at N=12"


def test_batches_group_by_file_and_size() -> None:
    cands = [_cand("dead-code", "src/a.py", i, 2) for i in range(1, 8)]
    cands += [_cand("dead-code", "src/b.py", 1, 4)]
    selected, _ = select_candidates(cands, DEFAULTS, top=5)
    batches = build_batches(selected, DEFAULTS["verifier"]["batch_size"])
    assert [len(b) for b in batches] == [6, 2]
    assert {c["evidence"][0]["file"] for c in batches[0]} == {"src/a.py"}


def test_prompt_renders_context_coupling_questions_traps_and_contract(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    body = "\n".join(f"line {i}" for i in range(1, 101)) + "\n"
    (repo / "src" / "a.py").write_text(body, encoding="utf-8")
    (repo / "src" / "b.py").write_text('token = "abcdefghijkl0123"\nfrom a import x\n', encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    coupling["pairs"] = [{"a": "src/a.py", "b": "src/b.py", "shared_commits": 4, "ratio": 0.8,
                          "cross_directory": False}]
    cfg = deepcopy(DEFAULTS)
    cfg["traps"] = [{"family": "dead-code", "path_glob": "src/*.py", "note": "entry points live here"},
                    {"family": "security", "path_glob": "src/*.py", "note": "never shown"}]
    cand = _cand("dead-code", "src/a.py", 50, 3)
    cand["evidence"].append({"file": "src/b.py", "line_start": 1, "line_end": 1,
                             "quote": 'token = "abcdefghijkl0123"', "quote_verified": True})
    text = render_verify_prompt([cand], root=repo, inventory=inventory, coupling=coupling, config=cfg)
    assert cand["fingerprint"] in text
    assert "    20 | line 20" in text and "    80 | line 80" in text and "    19 | " not in text
    assert ">    50 | line 50" in text
    assert "src/b.py" in text and "shared=4" in text
    assert "Which dynamic-reference patterns were checked" in text
    assert "entry points live here" in text and "never shown" not in text
    assert "up to three further files" in text
    assert "abcdefghijkl0123" not in text and "abcd***" in text
    assert SEVERITY_RUBRIC not in text
    assert '"verdict"' in text and '"trap_matched"' in text and '"opened"' in text
    assert "referrers" in text.lower()


def test_verify_plan_and_cli(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("\n".join(f"line {i}" for i in range(1, 20)) + "\n", encoding="utf-8")
    inventory, coupling = build_all(repo, config=DEFAULTS)
    workdir = tmp_path / "wd"
    write_outputs(inventory, coupling, workdir)
    cands = [_cand("dead-code", "src/a.py", i, 2) for i in range(1, 9)]
    cands.append(_cand("pipeline-infra", "src/a.py", 9, 3, tier="A"))
    write_json(workdir / "candidates.json", {"schema_version": 2, "candidates": cands,
                                             "open_questions": [], "looks_bad_but_fine": [], "stats": {}})
    plan, prompts = build_verify_plan(workdir, repo, DEFAULTS, top=5)
    assert list(plan) == ["schema_version", "top", "batch_size", "selected", "unverified", "batches"]
    assert plan["selected"] == [c["fingerprint"] for b in plan["batches"] for c in [{"fingerprint": f} for f in b["fingerprints"]]]
    assert [b["prompt"] for b in plan["batches"]] == ["prompts/verify-01.md", "prompts/verify-02.md"]
    assert [b["output"] for b in plan["batches"]] == ["verdicts/verify-01.json", "verdicts/verify-02.json"]
    assert set(prompts) == {"prompts/verify-01.md", "prompts/verify-02.md"}
    assert cands[-1]["fingerprint"] not in plan["selected"]
    assert _main(["--workdir", str(workdir), "--top", "5"]) == 0
    raw = (workdir / "prompts" / "verify-01.md").read_bytes()
    assert b"\r" not in raw
    assert json.loads((workdir / "verify-plan.json").read_bytes())["top"] == 5
    assert _main(["--workdir", str(tmp_path / "none")]) == 2


def test_verdict_schema_shape() -> None:
    item = VERDICT_SCHEMA["items"]
    assert VERDICT_SCHEMA["type"] == "array"
    assert set(item["required"]) == {"fingerprint", "verdict", "proof", "severity", "effort",
                                     "trap_matched", "checked", "opened"}
    assert item["properties"]["verdict"]["enum"] == ["confirm", "downgrade", "reject", "refer"]
    assert repo_maxima({"files": []}) == {"hotspot": 0.0, "coupling": 0, "fan_in": 0}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_verify_prompts.py -q`
Expected: `ImportError: cannot import name 'priority_terms' from 'evidence'`.

- [ ] **Step 3: Add `priority_terms` and `repo_maxima` to `evidence.py`**

Append to `evidence.py` (spec 4.9; Task 8 imports the same two functions):

```python
TIER_WEIGHT: dict[str | None, float] = {"A": 1.0, "B": 0.7, "C": 0.35, None: 0.7}


def repo_maxima(inventory: dict[str, Any]) -> dict[str, float | int]:
    """Repository maxima for the H, C and F terms; fan-in counts import-line entries only."""
    files = [e for e in inventory.get("files", []) if isinstance(e, dict)]
    hotspot = max((float(e.get("hotspot_score") or 0.0) for e in files), default=0.0)
    coupling = max((int(e.get("coupling_degree") or 0) for e in files), default=0)
    fan_in = max(
        (int(e["fan_in_approx"]) for e in files
         if isinstance(e.get("fan_in_approx"), int) and e.get("fan_in_mode", "import-lines") == "import-lines"),
        default=0,
    )
    return {"hotspot": hotspot, "coupling": coupling, "fan_in": fan_in}


def priority_terms(
    candidate: dict[str, Any],
    maxima: dict[str, float | int],
    weights: dict[str, float],
    tractability: dict[str, float],
    *,
    tier: str | None,
    fan_in_mode: str,
) -> dict[str, Any]:
    """Every term of the 4.9 formula, rounded so a reader can recompute the priority."""
    signals = candidate.get("signals") or {}

    def ratio(value: Any, maximum: float | int) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not maximum:
            return 0.0
        return round(float(value) / float(maximum), 4)

    h = ratio(signals.get("hotspot_score"), maxima["hotspot"])
    c = ratio(signals.get("coupling_degree"), maxima["coupling"])
    f = 0.0 if fan_in_mode != "import-lines" else ratio(signals.get("fan_in_approx"), maxima["fan_in"])
    interest = round(1 + weights["wH"] * h + weights["wC"] * c + weights["wF"] * f, 4)
    tier_weight = TIER_WEIGHT.get(tier, 0.7)
    tract = float(tractability.get(str(candidate.get("effort")), tractability["M"]))
    severity = int(candidate.get("severity") or 0)
    return {
        "severity": severity, "H": h, "C": c, "F": f, "interest": interest,
        "tier_weight": tier_weight, "tractability": tract,
        "priority": round(severity * interest * tier_weight * tract, 4),
    }
```

- [ ] **Step 4: Write `verify_prompts.py`**

```python
"""Select the candidates worth a verifier's time and render their prompts (spec 4.8).

Reads ``candidates.json``, ``inventory.json`` and ``coupling.json`` from
``--workdir`` and ``.tech-debt.yaml`` from the repository root. Writes
``verify-plan.json`` and ``prompts/verify-<nn>.md``; SKILL.md (phase 3)
dispatches one read-only agent per batch and stores its reply at the plan's
``output`` path.

Budget rule: provisional priority (the 4.9 formula at tier B) ranks every
unverified candidate; the top ``max(top_multiple x N, min_candidates)`` plus
every severity-5 and every ``always_families`` candidate are selected, capped
at ``max_candidates``; tier A candidates (rules, tool facts) are never sent;
the rest are listed as ``unverified``. Batches of ``batch_size`` group
candidates by primary file. Each prompt carries the cited spans with
``context_lines`` of context, the change-coupled files, approximate referrers,
the family's verification questions and the repository's traps; every line is
redacted. The verifier prompt shares no text with the scout prompts beyond the
read-only rule.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Final

from categories import FAMILY_BLOCKS
from config import ConfigError, load_config
from evidence import priority_terms, repo_maxima
from inventory import write_json
from redaction import redact
from reference_graph import GraphFile, build_reference_graph, file_stem

SCHEMA_VERSION: Final[int] = 2
VERDICT_VALUES: Final[tuple[str, ...]] = ("confirm", "downgrade", "reject", "refer")
EXPLORATION_FILES: Final[int] = 3

VERDICT_CONTRACT: Final[str] = """Reply with one JSON array, one object per candidate, exactly these keys:

[
  {
    "fingerprint": "<as given>",
    "verdict": "confirm" | "downgrade" | "reject" | "refer",
    "proof": "<=150 words citing line numbers",
    "severity": 1-5,
    "effort": "S" | "M" | "L",
    "trap_matched": "<the trap note you matched, or null>",
    "checked": ["<what you checked, e.g. reflection, string-dispatch>"],
    "opened": ["<every further file you opened, at most three>"]
  }
]

confirm: the debt is real as described. downgrade: real but less severe (give the
severity). reject: not debt (say why; a matched trap goes in trap_matched).
refer: you could not decide from the code; a human must look."""

VERDICT_SCHEMA: Final[dict[str, Any]] = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["fingerprint", "verdict", "proof", "severity", "effort", "trap_matched",
                     "checked", "opened"],
        "properties": {
            "fingerprint": {"type": "string"},
            "verdict": {"type": "string", "enum": list(VERDICT_VALUES)},
            "proof": {"type": "string"},
            "severity": {"type": "integer", "minimum": 1, "maximum": 5},
            "effort": {"type": "string", "enum": ["S", "M", "L"]},
            "trap_matched": {"type": ["string", "null"]},
            "checked": {"type": "array", "items": {"type": "string"}},
            "opened": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def _primary(cand: dict[str, Any]) -> dict[str, Any]:
    return cand["evidence"][0]


# --- budget rule ------------------------------------------------------------------------


def select_candidates(
    candidates: list[dict[str, Any]], config: dict[str, Any], top: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """(selected in priority order, unverified fingerprints) per the 4.8 budget rule."""
    vcfg = config["verifier"]
    rcfg = config["ranking"]
    maxima = {"hotspot": 1.0, "coupling": 1, "fan_in": 1}  # provisional: relative order only
    pool = [c for c in candidates if c.get("tier") is None]
    for c in pool:
        c["_provisional"] = priority_terms(c, maxima, rcfg["weights"], rcfg["tractability"],
                                          tier="B", fan_in_mode="import-lines")["priority"]
    pool.sort(key=lambda c: (-c["_provisional"], c["fingerprint"]))
    n = max(int(vcfg["top_multiple"]) * int(top), int(vcfg["min_candidates"]))
    chosen = pool[:n]
    always = {c["fingerprint"] for c in pool
              if int(c["severity"]) >= int(vcfg["always_min_severity"])
              or c["family"] in set(vcfg["always_families"])}
    chosen += [c for c in pool[n:] if c["fingerprint"] in always]
    chosen = chosen[: int(vcfg["max_candidates"])]
    selected_fps = {c["fingerprint"] for c in chosen}
    unverified = [c["fingerprint"] for c in pool if c["fingerprint"] not in selected_fps]
    for c in pool:
        c.pop("_provisional", None)
    return chosen, unverified


def build_batches(selected: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    order = sorted(selected, key=lambda c: (_primary(c)["file"], c["fingerprint"]))
    return [order[i:i + batch_size] for i in range(0, len(order), batch_size)]


# --- prompt rendering -------------------------------------------------------------------


def _span(root: Path, ev: dict[str, Any], context: int) -> str:
    path = root / ev["file"]
    try:
        lines = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return f"{ev['file']}: unreadable"
    start, end = int(ev["line_start"]), int(ev["line_end"])
    lo, hi = max(1, start - context), min(len(lines), end + context)
    out = [f"{ev['file']}:{start}-{end}"]
    for number in range(lo, hi + 1):
        marker = ">" if start <= number <= end else " "
        out.append(f"{marker}{number:6d} | {redact(lines[number - 1])}")
    return "\n".join(out)


def _coupled(coupling: dict[str, Any], file: str) -> list[str]:
    out = []
    for pair in coupling.get("pairs", []):
        if pair.get("a") == file:
            out.append(f"{pair['b']} shared={pair['shared_commits']} ratio={pair['ratio']}")
        elif pair.get("b") == file:
            out.append(f"{pair['a']} shared={pair['shared_commits']} ratio={pair['ratio']}")
    return sorted(out)


def _referrers(root: Path, inventory: dict[str, Any], config: dict[str, Any], file: str) -> str:
    try:
        graph_files = []
        for entry in inventory.get("files", []):
            path = root / str(entry["path"])
            if entry.get("path_class") in ("generated", "vendored") or not path.is_file():
                continue
            graph_files.append(GraphFile(
                str(entry["path"]), str(entry.get("language") or ""), str(entry.get("path_class")),
                path.read_bytes().decode("utf-8", errors="replace"),
                int(entry.get("loc") or 0), int(entry.get("churn") or 0),
            ))
        result = build_reference_graph(graph_files, config["fan_in"])
        stem = file_stem(file)
        referrers = sorted({src for src, dst in result.edges if dst == file or file_stem(dst) == stem})
        return ", ".join(referrers) if referrers else "none found"
    except Exception:  # noqa: BLE001  (a graph failure must never abort verification)
        return "not computed"


def _traps(config: dict[str, Any], family: str, file: str) -> list[str]:
    out = []
    for trap in config.get("traps") or []:
        if not isinstance(trap, dict) or trap.get("family") != family:
            continue
        if fnmatch.fnmatch(file, str(trap.get("path_glob", "*"))):
            out.append(str(trap.get("note", "")))
    return out


def render_verify_prompt(
    batch: list[dict[str, Any]],
    *,
    root: Path,
    inventory: dict[str, Any],
    coupling: dict[str, Any],
    config: dict[str, Any],
) -> str:
    context = int(config["verifier"]["context_lines"])
    parts = [
        "You are a read-only verifier. Read and search files; change nothing.",
        "For each candidate below decide whether the described debt is real, using the cited "
        "span, the surrounding code and the questions listed. Before giving a verdict you may "
        f"open up to {EXPLORATION_FILES} further files you name, chosen from the referrers, the "
        "change-coupled files or the callees of the cited span; record them in `opened`.",
        "",
    ]
    for index, cand in enumerate(batch, start=1):
        primary = _primary(cand)
        block = FAMILY_BLOCKS[cand["family"]]
        signals = cand["signals"]
        parts += [
            f"## Candidate {index}",
            f"fingerprint: {cand['fingerprint']}",
            f"title: {redact(cand['title'])}",
            f"family: {cand['family']}  severity: {cand['severity']}  effort: {cand['effort']}",
            f"note: {redact(cand['note'])}",
            f"confirmed_by: {', '.join(cand['confirmed_by'])}",
            f"signals: hotspot_score={signals['hotspot_score']} churn={signals['churn']} "
            f"coupling_degree={signals['coupling_degree']} fan_in_approx={signals['fan_in_approx']} "
            f"path_class={signals['path_class']} in_hotspot_band={signals['in_hotspot_band']}",
            "",
        ]
        for ev in cand["evidence"]:
            parts += [_span(root, ev, context), ""]
        coupled = _coupled(coupling, primary["file"])
        parts.append("change-coupled files: " + (", ".join(coupled) if coupled else "none"))
        parts.append("approximate referrers: " + _referrers(root, inventory, config, primary["file"]))
        parts.append("questions:")
        parts += [f"  - {q}" for q in block.verifier_questions]
        traps = _traps(config, cand["family"], primary["file"])
        if traps:
            parts.append("traps recorded for this repository (a match is a reject with trap_matched):")
            parts += [f"  - {redact(t)}" for t in traps]
        parts.append("")
    parts.append(VERDICT_CONTRACT)
    return "\n".join(parts) + "\n"


# --- plan -----------------------------------------------------------------------------------


def build_verify_plan(
    workdir: Path, root: Path, config: dict[str, Any], top: int
) -> tuple[dict[str, Any], dict[str, str]]:
    candidates_doc = json.loads((workdir / "candidates.json").read_bytes())
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    coupling_path = workdir / "coupling.json"
    coupling = json.loads(coupling_path.read_bytes()) if coupling_path.is_file() else {}
    selected, unverified = select_candidates(list(candidates_doc["candidates"]), config, top)
    batches = build_batches(selected, int(config["verifier"]["batch_size"]))
    prompts: dict[str, str] = {}
    entries = []
    for number, batch in enumerate(batches, start=1):
        prompt_rel = f"prompts/verify-{number:02d}.md"
        prompts[prompt_rel] = render_verify_prompt(
            batch, root=root, inventory=inventory, coupling=coupling, config=config)
        entries.append({"prompt": prompt_rel, "output": f"verdicts/verify-{number:02d}.json",
                        "fingerprints": [c["fingerprint"] for c in batch]})
    plan = {
        "schema_version": SCHEMA_VERSION,
        "top": int(top),
        "batch_size": int(config["verifier"]["batch_size"]),
        "selected": [fp for e in entries for fp in e["fingerprints"]],
        "unverified": unverified,
        "batches": entries,
    }
    return plan, prompts


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select candidates for verification and render the prompts")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding candidates.json")
    parser.add_argument("--top", type=int, default=None, help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    if not (workdir / "candidates.json").is_file() or not (workdir / "inventory.json").is_file():
        print(f"error: candidates.json and inventory.json are required in {workdir}", file=sys.stderr)
        return 2
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    root = Path(str(inventory.get("root", ".")))
    try:
        config = load_config(root)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    top = args.top if args.top is not None else int(config["top"])
    plan, prompts = build_verify_plan(workdir, root, config, top)
    for rel, text in prompts.items():
        target = workdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
    write_json(workdir / "verify-plan.json", plan)
    print(f"{len(plan['selected'])} candidate(s) in {len(plan['batches'])} batch(es); "
          f"{len(plan['unverified'])} unverified")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

`select_candidates` uses unit maxima for the provisional ranking because only the relative order matters at this stage and the real maxima belong to `rank.py`; state this in the docstring. The test's `test_batches_group_by_file_and_size` asserts a `[6, 2]` split: with `build_batches` sorting by file then fingerprint, the seven `src/a.py` candidates fill the first batch of six and the seventh joins `src/b.py` in the second.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_verify_prompts.py skills/tech-debt-scan/tests/test_evidence.py -q`

- [ ] **Step 6: Docs, gate, commit**

`docs/architecture.md` row for `verify_prompts.py --workdir .tech-debt [--top N]` (inputs, outputs `verify-plan.json` and `prompts/verify-<nn>.md`, the budget rule in one line, batches of 6 by file, 30 lines of context, traps from config). `README.md` row for `verify-plan.json` (`{schema_version: 2, top, batch_size, selected[], unverified[], batches[{prompt, output, fingerprints[]}]}`). Run the gate. Commit:

```
feat(tech-debt-scan): verify_prompts.py applies the verifier budget and renders batches
```

---

### Task 7: `apply_verdicts.py` and the tier table

**Files:**
- Create: `skills/tech-debt-scan/scripts/apply_verdicts.py`
- Test: `skills/tech-debt-scan/tests/test_apply_verdicts.py`
- Modify: `docs/architecture.md`, `README.md` (rows for `verified.json`)

**Interfaces:**
- Consumes: `candidates.json`, `verify-plan.json`, `verdicts/verify-<nn>.json`; `VERDICT_VALUES` (`verify_prompts.py`); `validate_effort` (`validation.py`); `write_json`.
- Produces: `apply(candidates: list[dict], verify_plan: dict, verdicts: dict[str, list[dict]]) -> dict[str, Any]` (the `verified.json` document `{"schema_version": 2, "findings": [...], "stats": {...}}`); `earned_tier(candidate, verdict) -> str | None`; `family_cap(candidate) -> str | None`; `CORROBORATING_PREFIXES`.
- CLI: `python scripts/apply_verdicts.py --workdir .tech-debt`; exit 2 when `candidates.json` or `verify-plan.json` is missing; a missing verdict file for a planned batch leaves its candidates `unverified` and prints a warning (SKILL.md handles exit 5 upstream).

**Confidence:** 94% (a pure join plus a table; every branch has a named test).

**Tier table (fixed, spec 4.8 and the 2.3 caps):**

| Case | tier | verified |
|---|---|---|
| candidate already `tier: "A"` (rule, tool fact) | A | true |
| verdict confirm, corroborated | A, then capped by family | true |
| verdict confirm, not corroborated | B | true |
| verdict downgrade or refer | C | true |
| verdict reject | null (kept, `verified: true`, `verdict: "reject"`) | true |
| selected, no verdict returned; or not selected | C (`verdict: "unverified"`) | false |

Corroboration: any `confirmed_by` entry not equal to `scout:<own family>` (prefixes `pattern:`, `satd`, `rule:`, `tool:`, `coupling`, `hotspot`, `signal:`, or a second `scout:` family).

Family caps applied after a confirm (the strongest allowed tier when the condition holds; `A` otherwise):

| Family | Cap | Unless |
|---|---|---|
| duplication | B | `confirmed_by` has `tool:` or `coupling` |
| dead-code | C | `signals.churn == 0` and `signals.fan_in_approx == 0` and `path_class == "source"` (then B); `tool:` present (then A) |
| god-classes with `type_id` TD-20 | B | `coupling` present |
| architecture | B | `type_id` TD-10 caps at C unless `coupling` or `tool:`; any `tool:` or `coupling` lifts to A |
| test-gaps | B | `signal:no-mapped-tests` present |
| test-quality | B (and severity at most 3) | `tool:` present |
| migration | B | `coupling` present or evidence spans two files both with churn > 0 (the merge does not carry per-file churn for secondary evidence, so phase 2 uses `coupling` only; noted in the docstring) |
| dependency-debt | B | `tool:` present |
| doc-drift | B | none in phase 2 |
| security | B | `tool:` present |
| pipeline-infra (scout source) | B | none |
| complex-units, error-masking, half-finished, ownership | no cap | |

The verifier's `severity` and `effort` replace the scout's when present and valid. `checked`, `opened`, `proof`, `trap_matched` are copied. Output finding key order: the candidate keys, then `verdict, proof, checked, opened, trap_matched, verified`, with `tier` (already a candidate key) overwritten in place. `stats`: `{"selected", "verdicts", "unknown_fingerprint", "missing_verdict", "tier_a", "tier_b", "tier_c", "rejected"}`.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_apply_verdicts.py`:

```python
"""apply_verdicts.py: verdict join, tier table, family caps (spec 4.8, 2.3)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from apply_verdicts import _main, apply, earned_tier, family_cap
from evidence import fingerprint
from inventory import write_json


def _cand(family: str, sev: int = 3, *, confirmed: list[str] | None = None, tier: str | None = None,
          type_id: str | None = None, churn: int = 1, fan_in: int | None = 1) -> dict[str, Any]:
    fp, qh = fingerprint(family, "src/a.py", f"q {family} {sev} {confirmed}")
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code", "type_id": type_id,
        "title": "t", "severity": sev, "effort": "M", "source": "rule" if tier == "A" else "scout",
        "rule_id": None, "note": "",
        "evidence": [{"file": "src/a.py", "line_start": 1, "line_end": 1, "quote": "q", "quote_verified": True}],
        "confirmed_by": confirmed if confirmed is not None else [f"scout:{family}"],
        "signals_cited": [],
        "signals": {"hotspot_score": 0.0, "churn": churn, "coupling_degree": 0, "fan_in_approx": fan_in,
                    "path_class": "source", "in_hotspot_band": False},
        "tier": tier,
    }


def _verdict(cand: dict[str, Any], verdict: str, **extra: Any) -> dict[str, Any]:
    v: dict[str, Any] = {"fingerprint": cand["fingerprint"], "verdict": verdict, "proof": "p",
                         "severity": cand["severity"], "effort": cand["effort"], "trap_matched": None,
                         "checked": ["x"], "opened": []}
    v.update(extra)
    return v


def _plan(*cands: dict[str, Any]) -> dict[str, Any]:
    fps = [c["fingerprint"] for c in cands]
    return {"schema_version": 2, "top": 5, "batch_size": 6, "selected": fps, "unverified": [],
            "batches": [{"prompt": "prompts/verify-01.md", "output": "verdicts/verify-01.json",
                         "fingerprints": fps}]}


@pytest.mark.parametrize(
    ("verdict", "confirmed", "tier"),
    [
        ("confirm", ["scout:error-masking", "pattern:swallowed-catch"], "A"),
        ("confirm", ["scout:error-masking", "scout:dead-code"], "A"),
        ("confirm", ["scout:error-masking", "hotspot"], "A"),
        ("confirm", ["scout:error-masking"], "B"),
        ("downgrade", ["scout:error-masking", "pattern:x"], "C"),
        ("refer", ["scout:error-masking", "pattern:x"], "C"),
        ("reject", ["scout:error-masking", "pattern:x"], None),
    ],
)
def test_tier_table(verdict: str, confirmed: list[str], tier: str | None) -> None:
    cand = _cand("error-masking", confirmed=confirmed)
    assert earned_tier(cand, _verdict(cand, verdict)) == tier


def test_family_caps() -> None:
    assert family_cap(_cand("duplication", confirmed=["scout:duplication", "pattern:x"])) == "B"
    assert family_cap(_cand("duplication", confirmed=["scout:duplication", "coupling"])) is None
    assert family_cap(_cand("dead-code", churn=1, fan_in=1)) == "C"
    assert family_cap(_cand("dead-code", churn=0, fan_in=0)) == "B"
    assert family_cap(_cand("dead-code", confirmed=["scout:dead-code", "tool:knip"])) is None
    assert family_cap(_cand("god-classes", type_id="TD-20")) == "B"
    assert family_cap(_cand("god-classes", type_id="TD-11")) is None
    assert family_cap(_cand("architecture", type_id="TD-10")) == "C"
    assert family_cap(_cand("architecture", type_id="TD-07")) == "B"
    assert family_cap(_cand("architecture", type_id="TD-07", confirmed=["scout:architecture", "coupling"])) is None
    assert family_cap(_cand("test-gaps")) == "B"
    assert family_cap(_cand("test-gaps", confirmed=["scout:test-gaps", "signal:no-mapped-tests"])) is None
    assert family_cap(_cand("security")) == "B"
    assert family_cap(_cand("doc-drift")) == "B"
    assert family_cap(_cand("error-masking")) is None
    assert family_cap(_cand("complex-units")) is None


def test_apply_joins_overrides_and_counts() -> None:
    a = _cand("error-masking", 4, confirmed=["scout:error-masking", "pattern:x"])
    b = _cand("duplication", 3, confirmed=["scout:duplication", "pattern:y"])
    c = _cand("dead-code", 2)
    d = _cand("pipeline-infra", 3, tier="A")
    e = _cand("test-quality", 5, confirmed=["scout:test-quality", "satd"])
    plan = _plan(a, b, c, e)
    verdicts = {"verdicts/verify-01.json": [
        _verdict(a, "confirm", severity=2, effort="S"),
        _verdict(b, "confirm"),
        _verdict(e, "confirm"),
        {"fingerprint": "unknown000000000", "verdict": "confirm", "proof": "", "severity": 1,
         "effort": "S", "trap_matched": None, "checked": [], "opened": []},
    ]}
    doc = apply([a, b, c, d, e], plan, verdicts)
    assert list(doc) == ["schema_version", "findings", "stats"]
    by_fp = {f["fingerprint"]: f for f in doc["findings"]}
    assert by_fp[a["fingerprint"]]["tier"] == "A"
    assert by_fp[a["fingerprint"]]["severity"] == 2 and by_fp[a["fingerprint"]]["effort"] == "S"
    assert by_fp[b["fingerprint"]]["tier"] == "B", "duplication capped without tool or coupling"
    assert by_fp[c["fingerprint"]]["tier"] == "C" and by_fp[c["fingerprint"]]["verdict"] == "unverified"
    assert by_fp[c["fingerprint"]]["verified"] is False
    assert by_fp[d["fingerprint"]]["tier"] == "A" and by_fp[d["fingerprint"]]["verified"] is True
    assert by_fp[e["fingerprint"]]["severity"] == 3, "test-quality severity capped at 3"
    assert by_fp[e["fingerprint"]]["tier"] == "B", "test-quality capped at B without a tool"
    finding = by_fp[a["fingerprint"]]
    assert list(finding)[-6:] == ["verdict", "proof", "checked", "opened", "trap_matched", "verified"]
    assert doc["stats"] == {"selected": 4, "verdicts": 3, "unknown_fingerprint": 1, "missing_verdict": 1,
                            "tier_a": 2, "tier_b": 2, "tier_c": 1, "rejected": 0}


def test_reject_and_trap_are_kept(tmp_path: Path) -> None:
    a = _cand("dead-code", confirmed=["scout:dead-code", "pattern:x"])
    plan = _plan(a)
    doc = apply([a], plan, {"verdicts/verify-01.json": [
        _verdict(a, "reject", trap_matched="entry points live here")]})
    f = doc["findings"][0]
    assert f["tier"] is None and f["verdict"] == "reject" and f["trap_matched"] == "entry points live here"
    assert doc["stats"]["rejected"] == 1


def test_cli_reads_verdict_files(tmp_path: Path) -> None:
    a = _cand("error-masking", confirmed=["scout:error-masking", "satd"])
    workdir = tmp_path / "wd"
    write_json(workdir / "candidates.json", {"schema_version": 2, "candidates": [a],
                                             "open_questions": [], "looks_bad_but_fine": [], "stats": {}})
    write_json(workdir / "verify-plan.json", _plan(a))
    (workdir / "verdicts").mkdir()
    (workdir / "verdicts" / "verify-01.json").write_text(json.dumps([_verdict(a, "confirm")]), encoding="utf-8")
    assert _main(["--workdir", str(workdir)]) == 0
    doc = json.loads((workdir / "verified.json").read_bytes())
    assert doc["findings"][0]["tier"] == "A"
    assert (workdir / "verified.json").read_bytes().count(b"\r") == 0
    assert _main(["--workdir", str(tmp_path / "none")]) == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py -q`
Expected: `ModuleNotFoundError: No module named 'apply_verdicts'`.

- [ ] **Step 3: Write `apply_verdicts.py`**

```python
"""Join verifier verdicts to candidates and assign the earned tier (spec 4.8, 2.3 caps).

Reads ``candidates.json``, ``verify-plan.json`` and every ``verdicts/verify-<nn>.json``
the plan names from ``--workdir``; writes ``verified.json``.

Tier A: confirmed, quote verified, and at least one independent corroboration
in ``confirmed_by`` (anything beyond the scout's own ``scout:<family>`` entry).
Tier B: confirmed without corroboration. Tier C: downgraded, referred, or
unverified (not selected, or selected with no verdict). Rejected findings keep
``tier: null`` with the proof for the report's "considered and rejected"
section. Rule findings and tool facts are tier A without a verifier. Family
caps from spec 2.3 apply after a confirm; the verifier's severity and effort
replace the scout's. Migration's "churn on both sides" lift uses the
``coupling`` corroboration only, because a candidate carries churn for its
primary file alone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

from inventory import write_json
from validation import ValidationError, validate_effort
from verify_prompts import VERDICT_VALUES

SCHEMA_VERSION: Final[int] = 2
CORROBORATING_PREFIXES: Final[tuple[str, ...]] = ("pattern:", "rule:", "tool:", "signal:")
CORROBORATING_TOKENS: Final[frozenset[str]] = frozenset({"satd", "coupling", "hotspot"})
TIER_ORDER: Final[dict[str, int]] = {"A": 0, "B": 1, "C": 2}


def _has(cand: dict[str, Any], prefix: str) -> bool:
    return any(str(s).startswith(prefix) for s in cand.get("confirmed_by", []))


def _token(cand: dict[str, Any], name: str) -> bool:
    return name in cand.get("confirmed_by", [])


def corroborated(cand: dict[str, Any]) -> bool:
    own = f"scout:{cand['family']}"
    for source in cand.get("confirmed_by", []):
        s = str(source)
        if s == own:
            continue
        if s.startswith(CORROBORATING_PREFIXES) or s in CORROBORATING_TOKENS or s.startswith("scout:"):
            return True
    return False


def family_cap(cand: dict[str, Any]) -> str | None:
    """The strongest tier the family allows without tool corroboration; None means no cap."""
    family = cand["family"]
    signals = cand.get("signals") or {}
    tool, coupling = _has(cand, "tool:"), _token(cand, "coupling")
    if family == "duplication":
        return None if tool or coupling else "B"
    if family == "dead-code":
        if tool:
            return None
        ordinary = (signals.get("churn") == 0 and signals.get("fan_in_approx") == 0
                    and signals.get("path_class") == "source")
        return "B" if ordinary else "C"
    if family == "god-classes":
        return "B" if cand.get("type_id") == "TD-20" and not coupling else None
    if family == "architecture":
        if tool or coupling:
            return None
        return "C" if cand.get("type_id") == "TD-10" else "B"
    if family == "test-gaps":
        return None if _token(cand, "signal:no-mapped-tests") else "B"
    if family in ("test-quality", "dependency-debt", "security"):
        return None if tool else "B"
    if family == "migration":
        return None if coupling else "B"
    if family in ("doc-drift", "pipeline-infra") and cand.get("source") == "scout":
        return "B"
    return None


def _weakest(a: str, b: str | None) -> str:
    return a if b is None or TIER_ORDER[a] >= TIER_ORDER[b] else b


def earned_tier(cand: dict[str, Any], verdict: dict[str, Any] | None) -> str | None:
    if cand.get("tier") == "A":
        return "A"
    if verdict is None:
        return "C"
    kind = str(verdict.get("verdict"))
    if kind == "reject":
        return None
    if kind in ("downgrade", "refer"):
        return "C"
    if kind != "confirm" or not all(e.get("quote_verified") for e in cand.get("evidence", [])):
        return "C"
    base = "A" if corroborated(cand) else "B"
    return _weakest(base, family_cap(cand))


def _finding(cand: dict[str, Any], verdict: dict[str, Any] | None, *, selected: bool) -> dict[str, Any]:
    out = dict(cand)
    out["tier"] = earned_tier(cand, verdict)
    if verdict is not None:
        severity = verdict.get("severity")
        if isinstance(severity, int) and not isinstance(severity, bool) and 1 <= severity <= 5:
            out["severity"] = severity
        effort = verdict.get("effort")
        try:
            validate_effort(str(effort))
            out["effort"] = str(effort)
        except ValidationError:
            pass
        if cand["family"] == "test-quality" and not _has(cand, "tool:"):
            out["severity"] = min(int(out["severity"]), 3)
        out["verdict"] = str(verdict.get("verdict"))
        out["proof"] = str(verdict.get("proof", ""))
        out["checked"] = [str(c) for c in verdict.get("checked", []) or []]
        out["opened"] = [str(o) for o in verdict.get("opened", []) or []]
        trap = verdict.get("trap_matched")
        out["trap_matched"] = str(trap) if trap else None
        out["verified"] = True
    elif cand.get("tier") == "A":
        out.update({"verdict": "rule", "proof": "verified by construction", "checked": [], "opened": [],
                    "trap_matched": None, "verified": True})
    else:
        out.update({"verdict": "unverified", "proof": "", "checked": [], "opened": [],
                    "trap_matched": None, "verified": False})
    return out


def apply(
    candidates: list[dict[str, Any]],
    verify_plan: dict[str, Any],
    verdicts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    known = {c["fingerprint"] for c in candidates}
    by_fp: dict[str, dict[str, Any]] = {}
    unknown = 0
    for items in verdicts.values():
        for item in items:
            if not isinstance(item, dict) or item.get("verdict") not in VERDICT_VALUES:
                continue
            fp = str(item.get("fingerprint"))
            if fp in known:
                by_fp[fp] = item
            else:
                unknown += 1
    selected = set(verify_plan.get("selected", []))
    findings = [_finding(c, by_fp.get(c["fingerprint"]), selected=c["fingerprint"] in selected)
                for c in candidates]
    counts = {"A": 0, "B": 0, "C": 0}
    rejected = 0
    for f in findings:
        if f["tier"] in counts:
            counts[f["tier"]] += 1
        elif f["verdict"] == "reject":
            rejected += 1
    stats = {
        "selected": len(selected),
        "verdicts": len(by_fp),
        "unknown_fingerprint": unknown,
        "missing_verdict": len([fp for fp in selected if fp not in by_fp]),
        "tier_a": counts["A"], "tier_b": counts["B"], "tier_c": counts["C"], "rejected": rejected,
    }
    return {"schema_version": SCHEMA_VERSION, "findings": findings, "stats": stats}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply verifier verdicts and write verified.json")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding the scan files")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    cand_path, plan_path = workdir / "candidates.json", workdir / "verify-plan.json"
    if not cand_path.is_file() or not plan_path.is_file():
        print(f"error: candidates.json and verify-plan.json are required in {workdir}", file=sys.stderr)
        return 2
    candidates = json.loads(cand_path.read_bytes())["candidates"]
    plan = json.loads(plan_path.read_bytes())
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for batch in plan.get("batches", []):
        path = workdir / str(batch["output"])
        if not path.is_file():
            print(f"warning: {path} missing; its candidates stay unverified", file=sys.stderr)
            continue
        loaded = json.loads(path.read_bytes())
        verdicts[str(batch["output"])] = loaded if isinstance(loaded, list) else []
    doc = apply(candidates, plan, verdicts)
    write_json(workdir / "verified.json", doc)
    s = doc["stats"]
    print(f"tier A {s['tier_a']}, B {s['tier_b']}, C {s['tier_c']}, rejected {s['rejected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

The `selected` keyword on `_finding` is accepted and unused in phase 2 (a selected candidate with no verdict and an unselected one both land in `unverified`); keep it so the phase 5 baseline can tell the two apart, and say so in a comment.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_apply_verdicts.py -q`

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md` row for `apply_verdicts.py --workdir .tech-debt` (the tier table in one line, family caps, verifier overrides). `README.md` row for `verified.json` (`{schema_version: 2, findings[<candidate keys> + verdict, proof, checked, opened, trap_matched, verified], stats{}}`). Run the gate. Commit:

```
feat(tech-debt-scan): apply_verdicts.py earns tiers from verdicts, corroboration and family caps
```

---
### Task 8: `rank.py`

**Files:**
- Create: `skills/tech-debt-scan/scripts/rank.py`
- Test: `skills/tech-debt-scan/tests/test_rank.py`
- Modify: `docs/architecture.md`, `README.md` (rows for `ranked.json`)

**Interfaces:**
- Consumes: `verified.json`, `inventory.json`; config `ranking.*`, `top`; `priority_terms`, `repo_maxima` (`evidence.py`); `write_json`.
- Produces: `PRESETS: dict[str, dict[str, Any]]` (`balanced`, `hotspot-first`, `architecture`, `quick-wins` with `weights`, `tractability`, `exclude`); `rank(verified: dict, inventory: dict, config: dict, *, preset: str, top: int) -> dict` (the `ranked.json` document); `FORMULA_VERSION = 1`.
- CLI: `python scripts/rank.py --workdir .tech-debt [--preset balanced|hotspot-first|architecture|quick-wins] [--top N]`; exit 2 when `verified.json` or `inventory.json` is missing or the preset is unknown.

**Confidence:** 94% (arithmetic already pinned by Task 6's worked-example test; the spread cap and tie-break are a sort with a counter).

**Design (fixed):**

- Eligible for the top N: tier A or B only (tier C and rejected are emitted with `in_top_n: false`); under `quick-wins`, duplication candidates without `tool:` or `coupling` corroboration and every ownership finding are excluded from the top N (still emitted, `in_top_n: false`).
- Order: priority descending, then fingerprint ascending. Walk the order; a finding joins the top N while fewer than N are chosen and its family holds fewer than `ceil(spread_cap * N)` chosen entries; a finding displaced by the family cap gets `spread_capped: true` and stays where the priority put it in `findings` (rank numbers count every finding in priority order, top or not).
- Presets: `balanced` (wH 1.0, wC 0.5, wF 0.5), `hotspot-first` (1.5, 0.5, 0.25), `architecture` (0.75, 1.0, 1.0), `quick-wins` (balanced weights; tractability S 1.0, M 0.5, L 0.2). Config `ranking.weights` and `ranking.tractability` override the `balanced` preset only (the others are fixed by name); `--preset` overrides `ranking.preset`.
- `F` uses the primary file's `fan_in_mode` from the inventory entry (`anywhere` gives 0); `repo_maxima` supplies the denominators.
- Output key order: `schema_version, formula_version, preset, top, weights, tractability, top_n, findings[{fingerprint, rank, priority, terms, tier, in_top_n, spread_capped}]`.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_rank.py`:

```python
"""rank.py: the 4.9 formula, presets, spread cap, determinism (spec 4.9)."""
from __future__ import annotations

import json
from copy import deepcopy
from math import ceil
from pathlib import Path
from typing import Any

import pytest
from config import DEFAULTS
from evidence import fingerprint
from inventory import write_json
from rank import FORMULA_VERSION, PRESETS, _main, rank


def _inventory() -> dict[str, Any]:
    def entry(path: str, hotspot: float, degree: int, fan_in: int | None, mode: str = "import-lines") -> dict[str, Any]:
        return {"path": path, "path_class": "source", "hotspot_score": hotspot, "churn": 1,
                "coupling_degree": degree, "fan_in_approx": fan_in, "fan_in_mode": mode}
    return {"hotspot_band": ["x.py"], "files": [
        entry("x.py", 0.8, 4, 2), entry("y.py", 0.0, 0, None), entry("z.py", 1.0, 10, 5),
        entry("w.py", 0.5, 2, 9, mode="anywhere"),
    ]}


def _finding(family: str, path: str, sev: int, effort: str, tier: str | None, *,
             hotspot: float = 0.0, degree: int = 0, fan_in: int | None = None,
             confirmed: list[str] | None = None, verdict: str = "confirm") -> dict[str, Any]:
    fp, qh = fingerprint(family, path, f"{family}{path}{sev}{effort}")
    return {
        "fingerprint": fp, "quote_hash": qh, "family": family, "debt_type": "code", "type_id": None,
        "title": "t", "severity": sev, "effort": effort, "source": "scout", "rule_id": None, "note": "",
        "evidence": [{"file": path, "line_start": 1, "line_end": 1, "quote": "q", "quote_verified": True}],
        "confirmed_by": confirmed or [f"scout:{family}"], "signals_cited": [],
        "signals": {"hotspot_score": hotspot, "churn": 1, "coupling_degree": degree, "fan_in_approx": fan_in,
                    "path_class": "source", "in_hotspot_band": hotspot > 0.5},
        "tier": tier, "verdict": verdict, "proof": "", "checked": [], "opened": [], "trap_matched": None,
        "verified": tier is not None,
    }


def _worked_example() -> list[dict[str, Any]]:
    return [
        _finding("error-masking", "x.py", 4, "M", "A", hotspot=0.8, degree=4, fan_in=2),   # X 6.30
        _finding("security", "y.py", 5, "S", "B"),                                          # Y 3.50
        _finding("architecture", "z.py", 3, "L", "A", hotspot=1.0, degree=10, fan_in=5),   # Z 4.125
    ]


def test_worked_example_balanced_and_quick_wins() -> None:
    verified = {"schema_version": 2, "findings": _worked_example(), "stats": {}}
    doc = rank(verified, _inventory(), DEFAULTS, preset="balanced", top=3)
    assert list(doc) == ["schema_version", "formula_version", "preset", "top", "weights", "tractability",
                         "top_n", "findings"]
    assert doc["formula_version"] == FORMULA_VERSION == 1
    ordered = [(f["fingerprint"], f["priority"]) for f in doc["findings"]]
    x, y, z = _worked_example()
    assert ordered == [(x["fingerprint"], 6.3), (z["fingerprint"], 4.125), (y["fingerprint"], 3.5)]
    assert doc["top_n"] == [x["fingerprint"], z["fingerprint"], y["fingerprint"]]
    assert doc["findings"][0]["terms"] == {"severity": 4, "H": 0.8, "C": 0.4, "F": 0.2, "interest": 2.1,
                                           "tier_weight": 1.0, "tractability": 0.75, "priority": 6.3}
    assert [f["rank"] for f in doc["findings"]] == [1, 2, 3]
    quick = rank(verified, _inventory(), DEFAULTS, preset="quick-wins", top=3)
    assert [round(f["priority"], 2) for f in quick["findings"]] == [4.2, 3.5, 1.65]
    assert quick["top_n"] == [x["fingerprint"], y["fingerprint"], z["fingerprint"]]


def test_presets_and_config_override() -> None:
    assert set(PRESETS) == {"balanced", "hotspot-first", "architecture", "quick-wins"}
    assert PRESETS["hotspot-first"]["weights"] == {"wH": 1.5, "wC": 0.5, "wF": 0.25}
    assert PRESETS["architecture"]["weights"] == {"wH": 0.75, "wC": 1.0, "wF": 1.0}
    assert PRESETS["quick-wins"]["tractability"] == {"S": 1.0, "M": 0.5, "L": 0.2}
    cfg = deepcopy(DEFAULTS)
    cfg["ranking"]["weights"] = {"wH": 2.0, "wC": 0.0, "wF": 0.0}
    verified = {"schema_version": 2, "findings": _worked_example(), "stats": {}}
    doc = rank(verified, _inventory(), cfg, preset="balanced", top=3)
    assert doc["weights"] == {"wH": 2.0, "wC": 0.0, "wF": 0.0}
    assert doc["findings"][0]["terms"]["interest"] == 2.6
    fixed = rank(verified, _inventory(), cfg, preset="hotspot-first", top=3)
    assert fixed["weights"] == PRESETS["hotspot-first"]["weights"], "named presets ignore config weights"


def test_tier_c_and_rejected_never_in_top_n_and_f_is_zero_for_anywhere() -> None:
    findings = [
        _finding("dead-code", "y.py", 5, "S", "C", verdict="downgrade"),
        _finding("dead-code", "x.py", 5, "S", None, verdict="reject"),
        _finding("error-masking", "w.py", 2, "S", "B", fan_in=9),
    ]
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="balanced", top=5)
    assert doc["top_n"] == [findings[2]["fingerprint"]]
    by = {f["fingerprint"]: f for f in doc["findings"]}
    assert by[findings[0]["fingerprint"]]["in_top_n"] is False
    assert by[findings[1]["fingerprint"]]["in_top_n"] is False and by[findings[1]["fingerprint"]]["tier"] is None
    assert by[findings[2]["fingerprint"]]["terms"]["F"] == 0.0


def test_spread_cap_and_fingerprint_tie_break() -> None:
    findings = [_finding("error-masking", f"e{i}.py", 4, "S", "A") for i in range(5)]
    findings += [_finding("security", "s.py", 2, "S", "A")]
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="balanced", top=4)
    cap = ceil(DEFAULTS["ranking"]["spread_cap"] * 4)
    top = [f for f in doc["findings"] if f["in_top_n"]]
    assert sum(1 for f in top if findings[0]["family"] == "error-masking" and f["fingerprint"] in
               {x["fingerprint"] for x in findings[:5]}) == cap
    assert findings[5]["fingerprint"] in doc["top_n"]
    capped = [f for f in doc["findings"] if f["spread_capped"]]
    assert len(capped) == 3 and all(not f["in_top_n"] for f in capped)
    masking_ranked = [f["fingerprint"] for f in doc["findings"] if f["fingerprint"] != findings[5]["fingerprint"]]
    assert masking_ranked == sorted(masking_ranked), "equal priority breaks ties by fingerprint"


def test_quick_wins_exclusions() -> None:
    findings = [
        _finding("duplication", "x.py", 5, "S", "B"),
        _finding("duplication", "z.py", 5, "S", "A", confirmed=["scout:duplication", "coupling"]),
        _finding("ownership", "y.py", 5, "S", "A", confirmed=["rule:ownership.knowledge-island"]),
        _finding("error-masking", "y.py", 1, "S", "B"),
    ]
    findings[2]["source"] = "rule"
    doc = rank({"findings": findings}, _inventory(), DEFAULTS, preset="quick-wins", top=5)
    assert doc["top_n"] == [findings[1]["fingerprint"], findings[3]["fingerprint"]]


def test_byte_identical_over_two_runs_and_cli(tmp_path: Path) -> None:
    workdir = tmp_path / "wd"
    write_json(workdir / "inventory.json", {"root": str(tmp_path), **_inventory()})
    write_json(workdir / "verified.json", {"schema_version": 2, "findings": _worked_example(), "stats": {}})
    assert _main(["--workdir", str(workdir), "--preset", "balanced", "--top", "3"]) == 0
    first = (workdir / "ranked.json").read_bytes()
    assert _main(["--workdir", str(workdir), "--preset", "balanced", "--top", "3"]) == 0
    assert first == (workdir / "ranked.json").read_bytes()
    assert b"\r" not in first
    assert json.loads(first)["preset"] == "balanced"
    assert _main(["--workdir", str(workdir), "--preset", "nonsense"]) == 2
    assert _main(["--workdir", str(tmp_path / "none")]) == 2


@pytest.mark.parametrize("name", ["service-py", "web-ts", "mixed-decoys"])
def test_hotspot_score_correlates_with_planted_debt(name: str, request: pytest.FixtureRequest) -> None:
    """Spec 4.9: the corpus checks that hotspot_score tracks planted debt (complexity half unvalidated)."""
    from inventory import build_all

    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    inventory, _ = build_all(repo, churn_months=240, config=DEFAULTS)
    planted = json.loads((Path(__file__).parent / "fixtures" / "corpus" / name / "planted.json").read_bytes())
    planted_paths = {p["path"] for p in planted["planted"] if p.get("path")}
    scores = {e["path"]: e["hotspot_score"] for e in inventory["files"] if e["path_class"] == "source"}
    if len(scores) < 4 or not planted_paths & set(scores):
        pytest.skip("fixture too small for a correlation check")
    mean_planted = sum(scores[p] for p in scores if p in planted_paths) / len([p for p in scores if p in planted_paths])
    mean_other = sum(scores[p] for p in scores if p not in planted_paths) / max(1, len([p for p in scores if p not in planted_paths]))
    assert mean_planted >= mean_other, (mean_planted, mean_other)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_rank.py -q`
Expected: `ModuleNotFoundError: No module named 'rank'`.

- [ ] **Step 3: Write `rank.py`**

```python
"""Deterministic priority ranking of verified findings (spec 4.9).

Reads ``verified.json`` and ``inventory.json`` from ``--workdir`` and
``.tech-debt.yaml`` from the repository root; writes ``ranked.json``.

    priority     = severity x interest x tier_weight x tractability
    interest     = 1 + wH*H + wC*C + wF*F   (H, C, F in [0, 1], repo-relative)
    tier_weight  = A 1.0, B 0.7, C 0.35
    tractability = S 1.0, M 0.75, L 0.5 (quick-wins: 1.0, 0.5, 0.2)

Only tier A and B findings can enter the top N; tier C, rejected and (under
``quick-wins``) uncorroborated duplication and ownership findings are emitted
with ``in_top_n: false``. No family holds more than ``ceil(spread_cap x N)`` of
the top N; a displaced finding carries ``spread_capped: true``. Ties break on
the fingerprint. Every term, the preset, the weights and ``formula_version``
are recorded so a reader can recompute any priority; the output is
byte-identical for identical inputs.
"""
from __future__ import annotations

import argparse
import json
import sys
from math import ceil
from pathlib import Path
from typing import Any, Final

from config import ConfigError, load_config
from evidence import priority_terms, repo_maxima
from inventory import write_json

SCHEMA_VERSION: Final[int] = 2
FORMULA_VERSION: Final[int] = 1
PRESETS: Final[dict[str, dict[str, Any]]] = {
    "balanced": {"weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
                 "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "hotspot-first": {"weights": {"wH": 1.5, "wC": 0.5, "wF": 0.25},
                      "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "architecture": {"weights": {"wH": 0.75, "wC": 1.0, "wF": 1.0},
                     "tractability": {"S": 1.0, "M": 0.75, "L": 0.5}, "exclude": False},
    "quick-wins": {"weights": {"wH": 1.0, "wC": 0.5, "wF": 0.5},
                   "tractability": {"S": 1.0, "M": 0.5, "L": 0.2}, "exclude": True},
}
ELIGIBLE_TIERS: Final[frozenset[str]] = frozenset({"A", "B"})


def _settings(config: dict[str, Any], preset: str) -> tuple[dict[str, float], dict[str, float], bool]:
    if preset not in PRESETS:
        raise ConfigError(f"unknown preset {preset!r}; expected one of {sorted(PRESETS)}")
    chosen = PRESETS[preset]
    if preset == "balanced":
        rcfg = config.get("ranking") or {}
        weights = {k: float(v) for k, v in (rcfg.get("weights") or chosen["weights"]).items()}
        tract = {k: float(v) for k, v in (rcfg.get("tractability") or chosen["tractability"]).items()}
        return weights, tract, False
    return dict(chosen["weights"]), dict(chosen["tractability"]), bool(chosen["exclude"])


def _excluded_by_quick_wins(finding: dict[str, Any]) -> bool:
    if finding["family"] == "ownership":
        return True
    if finding["family"] == "duplication":
        sources = finding.get("confirmed_by", [])
        return not any(str(s).startswith("tool:") or s == "coupling" for s in sources)
    return False


def rank(
    verified: dict[str, Any],
    inventory: dict[str, Any],
    config: dict[str, Any],
    *,
    preset: str,
    top: int,
) -> dict[str, Any]:
    weights, tract, exclude = _settings(config, preset)
    maxima = repo_maxima(inventory)
    modes = {str(e["path"]): str(e.get("fan_in_mode", "import-lines")) for e in inventory.get("files", [])}
    spread_cap = float((config.get("ranking") or {}).get("spread_cap", 0.5))
    per_family_cap = max(1, ceil(spread_cap * top))
    scored = []
    for finding in verified.get("findings", []):
        primary = finding["evidence"][0]["file"] if finding.get("evidence") else ""
        terms = priority_terms(finding, maxima, weights, tract, tier=finding.get("tier"),
                               fan_in_mode=modes.get(primary, "import-lines"))
        scored.append((finding, terms))
    scored.sort(key=lambda item: (-item[1]["priority"], item[0]["fingerprint"]))
    chosen: list[str] = []
    per_family: dict[str, int] = {}
    entries = []
    for position, (finding, terms) in enumerate(scored, start=1):
        eligible = finding.get("tier") in ELIGIBLE_TIERS and not (exclude and _excluded_by_quick_wins(finding))
        capped = False
        in_top = False
        if eligible and len(chosen) < top:
            if per_family.get(finding["family"], 0) < per_family_cap:
                chosen.append(finding["fingerprint"])
                per_family[finding["family"]] = per_family.get(finding["family"], 0) + 1
                in_top = True
            else:
                capped = True
        entries.append({
            "fingerprint": finding["fingerprint"], "rank": position, "priority": terms["priority"],
            "terms": terms, "tier": finding.get("tier"), "in_top_n": in_top, "spread_capped": capped,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "formula_version": FORMULA_VERSION,
        "preset": preset,
        "top": int(top),
        "weights": weights,
        "tractability": tract,
        "top_n": chosen,
        "findings": entries,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank verified findings deterministically")
    parser.add_argument("--workdir", default=".tech-debt", help="directory holding verified.json")
    parser.add_argument("--preset", default=None, help="balanced, hotspot-first, architecture or quick-wins")
    parser.add_argument("--top", type=int, default=None, help="findings to report (default: config)")
    args = parser.parse_args(argv)
    workdir = Path(args.workdir)
    verified_path, inventory_path = workdir / "verified.json", workdir / "inventory.json"
    if not verified_path.is_file() or not inventory_path.is_file():
        print(f"error: verified.json and inventory.json are required in {workdir}", file=sys.stderr)
        return 2
    inventory = json.loads(inventory_path.read_bytes())
    try:
        config = load_config(Path(str(inventory.get("root", "."))))
        preset = args.preset or str(config["ranking"]["preset"])
        top = args.top if args.top is not None else int(config["top"])
        doc = rank(json.loads(verified_path.read_bytes()), inventory, config, preset=preset, top=top)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_json(workdir / "ranked.json", doc)
    print(f"ranked {len(doc['findings'])} finding(s); top {len(doc['top_n'])} under preset {preset}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_rank.py -q`. If `test_hotspot_score_correlates_with_planted_debt` fails on a fixture, report the two means; the fixture, not the formula, is under test there and the ruling belongs to the controller.

- [ ] **Step 5: Docs, gate, commit**

`docs/architecture.md` row for `rank.py --workdir .tech-debt [--preset <p>] [--top N]` (the formula, the four presets, the spread cap, the tie-break, byte-identical output). `README.md` row for `ranked.json`. Run the gate. Commit:

```
feat(tech-debt-scan): rank.py orders verified findings by the 4.9 formula
```

---
### Task 9: `live_run.py`, the `claude -p` harness

**Files:**
- Create: `skills/tech-debt-scan/scripts/live_run.py`
- Create: `docs/evaluation-log.md` (header only; rows come from runs)
- Test: `skills/tech-debt-scan/tests/test_live_run.py`
- Modify: `docs/architecture.md`, `README.md` (harness section)

**Interfaces:**
- Consumes: every earlier script's public function (`build_all`, `write_outputs`, `run_patterns`, `run_rules`, `build_plan`, `write_plan`, `merge`, `build_verify_plan`, `apply`, `rank`, `evaluate`, `render_table`) and the two contracts `SCOUT_OUTPUT_SCHEMA` (`categories.py`) and `VERDICT_SCHEMA` (`verify_prompts.py`); `replay_fixture` is a test helper and must NOT be imported by a script (mypy covers `scripts/` only), so the harness re-implements the two-line replay call through `subprocess`-free means: it accepts either a repository path or a corpus fixture name, and for a fixture name it invokes `python tests/helpers/make_history.py <name> <dest>` (add a `__main__` to that helper in this task: `replay_fixture(sys.argv[1], Path(sys.argv[2]))`).
- Produces: `claude_argv(prompt_file: Path, *, model: str, budget: float, schema: dict, claude: str) -> list[str]`; `dispatch(prompt_file, output_file, *, cwd, model, budget, schema, claude, timeout) -> DispatchResult` (`status`, `cost_usd`, `turns`, `error`); `run_chain(repo, workdir, *, families, top, preset, churn_months, model, budget, claude, timeout, skip_agents)`; `log_row(log_path, fixture, report, cost) -> None`.
- CLI: `python scripts/live_run.py <fixture-or-repo> [--workdir <dir>] [--families <set>] [--top N] [--preset p] [--model sonnet] [--max-budget-usd 1.0] [--claude <path>] [--timeout 900] [--log docs/evaluation-log.md] [--skip-agents]`; exit 3 when `claude` is not on PATH and `--skip-agents` is absent; exit 4 when any agent call fails after one retry.

**Confidence:** 91% after mitigations. The CLI recipe was verified this session (`claude -p --setting-sources project --strict-mcp-config --disable-slash-commands --output-format json --tools Read,Grep,Glob --allowedTools Read,Grep,Glob --model haiku --max-budget-usd 0.10` returned `{"type": "result", "subtype": "success", "is_error": false, ...}` with the reply in `result`; `--bare` returned "Not logged in" and an isolated `CLAUDE_CONFIG_DIR` returned `api_error`). Two mitigations are embedded: (1) the reply is taken from `structured_output` when the envelope carries it (the `--json-schema` path) and otherwise from `result` with Markdown fences stripped, then validated against the contract, with one retry that appends "previous response failed the schema; re-emit valid JSON"; (2) the harness test uses a fake `claude` executable written into `tmp_path` and passed with `--claude`, so CI never needs the real CLI.

**Design (fixed):**

- Argv (list, never a shell string): `[claude, "-p", "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands", "--output-format", "json", "--json-schema", json.dumps(schema), "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob", "--model", model, "--max-budget-usd", f"{budget:.2f}", prompt_text]` where `prompt_text` is the prompt file's content (the prompt is the positional argument; on Windows the argv ceiling is 32 767 characters for `CreateProcess`, and a rendered prompt with 40 leads stays under 20 000; the harness asserts `len(prompt_text) < 30_000` and otherwise trims the leads block with a warning).
- `cwd` is the repository (fixture checkout) so `Read`, `Grep` and `Glob` see the tree; `timeout` 900 s per call; `subprocess.run(..., capture_output=True, text=True, encoding="utf-8", errors="replace")`.
- Reply extraction: parse stdout as JSON; `is_error` true or `subtype != "success"` is a failure with the `result` text as the error; the payload is `structured_output` if present, else `result` with a leading ```` ```json ```` or ```` ``` ```` fence and trailing fence removed, parsed as JSON. Scout payloads are validated against `SCOUT_OUTPUT_SCHEMA` structurally (top-level keys present, `findings` a list) and verifier payloads must be a list; anything else triggers the single retry.
- Cost: `total_cost_usd` from each envelope is summed into the run's cost.
- `run_chain` order: replay or use the repository; `build_all(churn_months=...)` (the fixture's `planted.json` `churn_months` when present, else `--churn-months`, else config); `write_outputs`; `run_patterns` (write `patterns.json`, patch `inline_disables`); `run_rules` (write `rule-findings.json`); `build_plan` + `write_plan`; for each entry `dispatch` (skipped when `--skip-agents` and the output already exists); `merge` (write `candidates.json`); `build_verify_plan` (write plan and prompts); for each batch `dispatch`; `apply` (write `verified.json`); `rank` (write `ranked.json`); when `planted.json` exists, `evaluate` (write `evaluation.json`, print `render_table`) and `log_row`.
- `docs/evaluation-log.md` row format (one table): `| <date> | <fixture> | <model> | <tier A precision> | <decoys in tier A> | <decoys in top N> | <per-family recall, "fam=0.50" joined by space> | <scout calls> | <verifier calls> | <cost USD> |`. The header is created by Task 9 with no rows.

- [ ] **Step 1: Write the failing tests**

Create `skills/tech-debt-scan/tests/test_live_run.py`:

```python
"""live_run.py: argv, reply extraction, retry, the chain with a fake claude (spec 6 live policy)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from categories import SCOUT_OUTPUT_SCHEMA
from live_run import _main, claude_argv, dispatch, extract_reply, log_row, run_chain

FAKE = '''#!/usr/bin/env python
import json, sys
prompt = sys.argv[-1]
mode = "scout" if "read-only scout" in prompt else "verifier"
marker = "FAIL_ONCE"
state = __import__("pathlib").Path(__file__).with_suffix(".state")
if "--json-schema" not in sys.argv:
    raise SystemExit(9)
if mode == "scout":
    family = prompt.split("debt family: ")[1].split(".")[0].strip()
    payload = {"family": family, "module": None, "findings": [], "open_questions": [],
               "looks_bad_but_fine": [], "not_assessed": ["coverage numbers"]}
else:
    fps = [line.split("fingerprint: ")[1].strip() for line in prompt.splitlines() if line.startswith("fingerprint: ")]
    payload = [{"fingerprint": fp, "verdict": "confirm", "proof": "p", "severity": 3, "effort": "M",
                "trap_matched": None, "checked": ["x"], "opened": []} for fp in fps]
if not state.exists() and "FAIL_ONCE" in prompt:
    state.write_text("failed once")
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": "not json at all", "total_cost_usd": 0.01, "num_turns": 1}))
    raise SystemExit(0)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "```json\\n" + json.dumps(payload) + "\\n```", "total_cost_usd": 0.02, "num_turns": 2}))
'''


@pytest.fixture
def fake_claude(tmp_path: Path) -> str:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    if os.name != "nt":
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    # The harness accepts a "<python> <script>" launcher so Windows needs no shebang support.
    return f"{sys.executable} {script}"


def test_claude_argv_is_a_list_with_the_isolation_flags(tmp_path: Path) -> None:
    prompt = tmp_path / "p.md"
    prompt.write_text("hello", encoding="utf-8")
    argv = claude_argv(prompt, model="sonnet", budget=1.0, schema=SCOUT_OUTPUT_SCHEMA, claude="claude")
    assert argv[:2] == ["claude", "-p"]
    for flag in ("--setting-sources", "--strict-mcp-config", "--disable-slash-commands", "--output-format",
                 "--json-schema", "--tools", "--allowedTools", "--model", "--max-budget-usd"):
        assert flag in argv
    assert argv[argv.index("--setting-sources") + 1] == "project"
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert argv[argv.index("--max-budget-usd") + 1] == "1.00"
    assert argv[-1] == "hello"
    assert "--bare" not in argv


def test_extract_reply_prefers_structured_output_then_fenced_result() -> None:
    env = {"type": "result", "subtype": "success", "is_error": False, "result": "```json\n[1]\n```",
           "structured_output": {"a": 1}, "total_cost_usd": 0.5}
    assert extract_reply(json.dumps(env)) == ({"a": 1}, 0.5, None)
    env.pop("structured_output")
    assert extract_reply(json.dumps(env)) == ([1], 0.5, None)
    bad = {"type": "result", "subtype": "error_max_turns", "is_error": True, "result": "boom"}
    assert extract_reply(json.dumps(bad))[2] == "boom"
    assert extract_reply("not json")[2] is not None
    assert extract_reply(json.dumps({**env, "result": "plain text"}))[2] is not None


def test_dispatch_retries_once_on_invalid_payload(tmp_path: Path, fake_claude: str) -> None:
    prompt = tmp_path / "scout.md"
    prompt.write_text("You are a read-only scout for one debt family: security. FAIL_ONCE", encoding="utf-8")
    out = tmp_path / "scouts" / "security.json"
    result = dispatch(prompt, out, cwd=tmp_path, model="haiku", budget=0.1, schema=SCOUT_OUTPUT_SCHEMA,
                      claude=fake_claude, timeout=60)
    assert result.status == "ok" and result.attempts == 2 and result.cost_usd == pytest.approx(0.03)
    assert json.loads(out.read_bytes())["family"] == "security"
    assert "previous response failed the schema" in result.last_prompt


def test_run_chain_over_a_corpus_fixture_with_the_fake(tmp_path: Path, fake_claude: str,
                                                        service_py_repo: Path) -> None:
    workdir = tmp_path / "wd"
    log = tmp_path / "log.md"
    log.write_text("| date | fixture | model | tier_a_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |\n|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    summary = run_chain(service_py_repo, workdir, families="quick", top=3, preset="balanced",
                        churn_months=240, model="haiku", budget=0.1, claude=fake_claude, timeout=60,
                        skip_agents=False, planted=Path(__file__).parent / "fixtures" / "corpus" / "service-py" / "planted.json",
                        log_path=log, fixture_name="service-py")
    for name in ("inventory.json", "patterns.json", "rule-findings.json", "scan-plan.json",
                 "candidates.json", "verify-plan.json", "verified.json", "ranked.json", "evaluation.json"):
        assert (workdir / name).is_file(), name
    plan = json.loads((workdir / "scan-plan.json").read_bytes())
    for entry in plan["entries"]:
        assert (workdir / entry["output"]).is_file()
    assert summary["scout_calls"] == len(plan["entries"]) and summary["cost_usd"] > 0
    rows = log.read_text(encoding="utf-8").splitlines()
    assert rows[-1].startswith("| 20") and "service-py" in rows[-1] and "haiku" in rows[-1]


def test_cli_exit_codes(tmp_path: Path) -> None:
    assert _main([str(tmp_path / "missing-repo"), "--skip-agents"]) == 2
    (tmp_path / "repo").mkdir()
    assert _main([str(tmp_path / "repo"), "--claude", str(tmp_path / "no-such-binary")]) == 3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/tech-debt-scan/tests/test_live_run.py -q`
Expected: `ModuleNotFoundError: No module named 'live_run'`.

- [ ] **Step 3: Add a `__main__` to `tests/helpers/make_history.py`**

Append:

```python
if __name__ == "__main__":
    import sys as _sys

    replay_fixture(_sys.argv[1], Path(_sys.argv[2]))
    print(Path(_sys.argv[2]))
```

- [ ] **Step 4: Write `live_run.py`**

```python
"""Run the whole scan chain with real Claude scouts and verifiers (spec 6, live policy).

Manual only, never in CI. Given a corpus fixture name (replayed into a temporary
directory through ``tests/helpers/make_history.py``) or any repository path, the
harness runs the phase 1 signal scripts, ``plan_scan.py``, one ``claude -p``
call per scout prompt, ``merge_findings.py``, ``verify_prompts.py``, one call
per verifier batch, ``apply_verdicts.py`` and ``rank.py``; when a
``planted.json`` exists it scores the result with ``evaluate.py`` and appends a
row to ``docs/evaluation-log.md``.

Every ``claude`` call is a list argv in print mode with JSON output, structured
output from the contract's JSON schema, read-only tools only, user settings and
MCP servers excluded (``--setting-sources project --strict-mcp-config
--disable-slash-commands``; ``--bare`` loses auth on this machine) and a per-call
dollar budget. A reply that fails the contract is retried once with an appended
instruction; a second failure stops the run with exit 4.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from apply_verdicts import apply
from categories import SCOUT_OUTPUT_SCHEMA
from config import ConfigError, load_config
from evaluate import evaluate, render_table
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from rank import rank
from rules import run_rules
from verify_prompts import VERDICT_SCHEMA, build_verify_plan

ISOLATION: Final[tuple[str, ...]] = (
    "--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
)
TOOLS: Final[str] = "Read,Grep,Glob"
PROMPT_LIMIT: Final[int] = 30_000
RETRY_SUFFIX: Final[str] = "\n\nThe previous response failed the schema; re-emit valid JSON only.\n"
LOG_HEADER: Final[str] = (
    "| date | fixture | model | tier_a_precision | decoys_tier_a | decoys_top_n | recall | scouts "
    "| verifiers | cost_usd |\n|---|---|---|---|---|---|---|---|---|---|\n"
)


@dataclass(slots=True)
class DispatchResult:
    status: str
    attempts: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    last_prompt: str = ""


def claude_argv(prompt_file: Path, *, model: str, budget: float, schema: dict[str, Any], claude: str) -> list[str]:
    text = prompt_file.read_bytes().decode("utf-8")
    if len(text) > PROMPT_LIMIT:
        print(f"warning: {prompt_file.name} is {len(text)} chars; trimming to {PROMPT_LIMIT}", file=sys.stderr)
        text = text[:PROMPT_LIMIT]
    launcher = shlex.split(claude, posix=True) if " " in claude else [claude]
    return [
        *launcher, "-p", *ISOLATION,
        "--output-format", "json", "--json-schema", json.dumps(schema),
        "--tools", TOOLS, "--allowedTools", TOOLS,
        "--model", model, "--max-budget-usd", f"{budget:.2f}",
        text,
    ]


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def extract_reply(stdout: str) -> tuple[Any, float, str | None]:
    """(payload, cost, error): the agent's JSON reply from a claude -p envelope."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        return None, 0.0, f"envelope is not JSON: {stdout[:200]}"
    if not isinstance(envelope, dict):
        return None, 0.0, "envelope is not an object"
    cost = float(envelope.get("total_cost_usd") or 0.0)
    if envelope.get("is_error") or envelope.get("subtype") != "success":
        return None, cost, str(envelope.get("result") or envelope.get("subtype") or "error")
    if "structured_output" in envelope and envelope["structured_output"] is not None:
        return envelope["structured_output"], cost, None
    try:
        return json.loads(_strip_fences(str(envelope.get("result", "")))), cost, None
    except json.JSONDecodeError:
        return None, cost, "result is not JSON"


def _valid(payload: Any, schema: dict[str, Any]) -> bool:
    if schema.get("type") == "array":
        return isinstance(payload, list)
    return isinstance(payload, dict) and all(k in payload for k in schema.get("required", [])) \
        and isinstance(payload.get("findings"), list)


def dispatch(
    prompt_file: Path,
    output_file: Path,
    *,
    cwd: Path,
    model: str,
    budget: float,
    schema: dict[str, Any],
    claude: str,
    timeout: int,
) -> DispatchResult:
    result = DispatchResult(status="failed")
    prompt_text = prompt_file.read_bytes().decode("utf-8")
    for attempt in (1, 2):
        result.attempts = attempt
        result.last_prompt = prompt_text
        argv = claude_argv(prompt_file, model=model, budget=budget, schema=schema, claude=claude)
        argv[-1] = prompt_text
        try:
            proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            result.error = str(exc)
            return result
        payload, cost, error = extract_reply(proc.stdout)
        result.cost_usd += cost
        if error is None and _valid(payload, schema):
            output_file.parent.mkdir(parents=True, exist_ok=True)
            write_json(output_file, payload) if isinstance(payload, dict) else output_file.write_bytes(
                (json.dumps(payload, indent=2) + "\n").encode("utf-8"))
            result.status = "ok"
            result.error = None
            return result
        result.error = error or "payload failed the contract"
        prompt_text = prompt_text + RETRY_SUFFIX
    return result


def log_row(log_path: Path, fixture: str, model: str, report: dict[str, Any], *,
            scouts: int, verifiers: int, cost: float) -> None:
    families = report.get("families", {})
    tier_a = [f for f in families.values()]
    reported = sum(int(f.get("reported", 0)) for f in tier_a)
    precise = sum(int(f.get("precise", 0)) for f in tier_a)
    precision = f"{precise / reported:.2f}" if reported else "-"
    recall = " ".join(f"{name}={f['recall']:.2f}" for name, f in sorted(families.items())
                      if f.get("recall") is not None)
    row = (f"| {datetime.now(UTC).date().isoformat()} | {fixture} | {model} | {precision} | "
           f"{report.get('decoys_in_tier_a', 0)} | {report.get('decoys_in_top_n', 0)} | {recall or '-'} | "
           f"{scouts} | {verifiers} | {cost:.2f} |\n")
    if not log_path.is_file():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_bytes(LOG_HEADER.encode("utf-8"))
    log_path.write_bytes(log_path.read_bytes() + row.encode("utf-8"))


def _signals(repo: Path, workdir: Path, config: dict[str, Any], churn_months: int | None) -> dict[str, Any]:
    inventory, coupling = build_all(repo, churn_months=churn_months, config=config)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, config)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, config)
    write_json(workdir / "rule-findings.json", {"schema_version": 2, "findings": findings, "leads": leads})
    return inventory


def run_chain(
    repo: Path,
    workdir: Path,
    *,
    families: str | None,
    top: int | None,
    preset: str | None,
    churn_months: int | None,
    model: str,
    budget: float,
    claude: str,
    timeout: int,
    skip_agents: bool,
    planted: Path | None = None,
    log_path: Path | None = None,
    fixture_name: str = "",
) -> dict[str, Any]:
    repo = repo.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    config = load_config(repo)
    planted_doc = json.loads(planted.read_bytes()) if planted and planted.is_file() else None
    if churn_months is None and planted_doc and isinstance(planted_doc.get("churn_months"), int):
        churn_months = int(planted_doc["churn_months"])
    _signals(repo, workdir, config, churn_months)
    plan, prompts = build_plan(workdir, config, families=families, top=top)
    write_plan(workdir, plan, prompts)
    cost = 0.0
    scout_calls = 0
    for entry in plan["entries"]:
        output = workdir / str(entry["output"])
        if skip_agents and output.is_file():
            continue
        if skip_agents:
            raise RuntimeError(f"--skip-agents but {output} is missing")
        res = dispatch(workdir / str(entry["prompt"]), output, cwd=repo, model=model, budget=budget,
                       schema=SCOUT_OUTPUT_SCHEMA, claude=claude, timeout=timeout)
        cost += res.cost_usd
        scout_calls += 1
        if res.status != "ok":
            raise RuntimeError(f"scout {entry['family']} failed: {res.error}")
    write_json(workdir / "candidates.json", merge(workdir, repo, config))
    top_n = int(top if top is not None else plan["top"])
    vplan, vprompts = build_verify_plan(workdir, repo, config, top_n)
    for rel, text in vprompts.items():
        (workdir / rel).parent.mkdir(parents=True, exist_ok=True)
        (workdir / rel).write_bytes(text.encode("utf-8"))
    write_json(workdir / "verify-plan.json", vplan)
    verifier_calls = 0
    verdicts: dict[str, list[dict[str, Any]]] = {}
    for batch in vplan["batches"]:
        output = workdir / str(batch["output"])
        if not (skip_agents and output.is_file()):
            res = dispatch(workdir / str(batch["prompt"]), output, cwd=repo, model=model, budget=budget,
                           schema=VERDICT_SCHEMA, claude=claude, timeout=timeout)
            cost += res.cost_usd
            verifier_calls += 1
            if res.status != "ok":
                raise RuntimeError(f"verifier {batch['prompt']} failed: {res.error}")
        verdicts[str(batch["output"])] = json.loads(output.read_bytes())
    candidates = json.loads((workdir / "candidates.json").read_bytes())["candidates"]
    verified = apply(candidates, vplan, verdicts)
    write_json(workdir / "verified.json", verified)
    inventory = json.loads((workdir / "inventory.json").read_bytes())
    ranked = rank(verified, inventory, config, preset=preset or str(config["ranking"]["preset"]), top=top_n)
    write_json(workdir / "ranked.json", ranked)
    summary: dict[str, Any] = {"scout_calls": scout_calls, "verifier_calls": verifier_calls, "cost_usd": cost,
                               "top_n": ranked["top_n"]}
    if planted_doc is not None:
        report = evaluate(verified["findings"], planted_doc, set(ranked["top_n"]), top=top_n)
        write_json(workdir / "evaluation.json", report)
        print(render_table(report))
        summary["report"] = report
        if log_path is not None:
            log_row(log_path, fixture_name or repo.name, model, report,
                    scouts=scout_calls, verifiers=verifier_calls, cost=cost)
    print(f"agent calls: {scout_calls} scouts, {verifier_calls} verifier batches; cost ${cost:.2f}")
    return summary


def _replay(name: str, dest: Path) -> Path:
    helper = Path(__file__).resolve().parent.parent / "tests" / "helpers" / "make_history.py"
    subprocess.run([sys.executable, str(helper), name, str(dest)], check=True, timeout=120)
    return dest


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the scan chain with real Claude agents (manual, never CI)")
    parser.add_argument("target", help="corpus fixture name (service-py, web-ts, mixed-decoys) or a repo path")
    parser.add_argument("--workdir", default=None, help="scan workdir (default: <repo>/.tech-debt)")
    parser.add_argument("--families", default=None, help="default, quick, deep or a comma-separated list")
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--preset", default=None)
    parser.add_argument("--churn-months", type=int, default=None)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--max-budget-usd", type=float, default=1.0, help="per agent call")
    parser.add_argument("--claude", default=None, help="claude executable (default: on PATH)")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per agent call")
    parser.add_argument("--log", default=None, help="evaluation log to append to (default: docs/evaluation-log.md)")
    parser.add_argument("--skip-agents", action="store_true", help="reuse existing scout and verdict files")
    args = parser.parse_args(argv)
    corpus = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "corpus"
    planted: Path | None = None
    fixture_name = ""
    if (corpus / args.target).is_dir():
        fixture_name = args.target
        planted = corpus / args.target / "planted.json"
        repo = _replay(args.target, Path(tempfile.mkdtemp(prefix=f"live-{args.target}-")))
    else:
        repo = Path(args.target)
        if not repo.is_dir():
            print(f"error: {repo} is not a directory or a corpus fixture", file=sys.stderr)
            return 2
        candidate = repo / "planted.json"
        planted = candidate if candidate.is_file() else None
    claude = args.claude or shutil.which("claude")
    if not args.skip_agents and (claude is None or (" " not in claude and shutil.which(claude) is None
                                                    and not Path(claude).is_file())):
        print("error: claude executable not found; install Claude Code or pass --claude", file=sys.stderr)
        return 3
    workdir = Path(args.workdir) if args.workdir else repo / ".tech-debt"
    log = Path(args.log) if args.log else Path(__file__).resolve().parents[3] / "docs" / "evaluation-log.md"
    try:
        run_chain(repo, workdir, families=args.families, top=args.top, preset=args.preset,
                  churn_months=args.churn_months, model=args.model, budget=args.max_budget_usd,
                  claude=claude or "", timeout=args.timeout, skip_agents=args.skip_agents,
                  planted=planted, log_path=log, fixture_name=fixture_name)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4
    print(f"workdir: {workdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

`dispatch` writes a dict payload through `write_json` and a list payload through the same LF-only idiom; the conditional expression in the sketch is to be written as an `if` statement. `Path(__file__).resolve().parents[3]` is the repository root from `skills/tech-debt-scan/scripts/live_run.py`.

- [ ] **Step 5: Create `docs/evaluation-log.md`**

```markdown
# tech-debt-scan evaluation log

One row per live run of `scripts/live_run.py` over a corpus fixture (spec section 6). Tier A
precision is measured against the provisional 0.80 bar (reported at v2.0, hard at v2.1); zero
decoys at tier A or in the top N is hard from v2.0. Recall is reported without a bar.

| date | fixture | model | tier_a_precision | decoys_tier_a | decoys_top_n | recall | scouts | verifiers | cost_usd |
|---|---|---|---|---|---|---|---|---|---|
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest skills/tech-debt-scan/tests/test_live_run.py -q`. The fake `claude` is a Python script launched as `"<python> <script>"`; `claude_argv` splits a launcher containing a space with `shlex`.

- [ ] **Step 7: Docs, gate, commit**

`docs/architecture.md`: a short "Live harness" paragraph after the script table (what it runs, the isolation flags, the log). `README.md`: a "Live evaluation" section with the one command `python scripts/live_run.py service-py --model sonnet --max-budget-usd 1.00` and the sentence that it costs real tokens and never runs in CI. Run the gate (`skill_check.py` still passes: SKILL.md does not name the harness). Commit:

```
feat(tech-debt-scan): live_run.py drives the chain through claude -p and logs the evaluation
```

---
### Task 10: first live run, goldens, and the golden chain test

**Files:**
- Create: `skills/tech-debt-scan/tests/golden/<fixture>/scouts/<family>.json`, `.../verdicts/verify-<nn>.json`, `.../candidates.json`, `.../verify-plan.json`, `.../verified.json`, `.../ranked.json` for `service-py`, `web-ts`, `mixed-decoys`
- Create: `skills/tech-debt-scan/tests/test_chain_goldens.py`
- Modify: `docs/evaluation-log.md` (three rows from the run), `pyproject.toml` (`live` marker already declared; add `norecursedirs` entry only if the golden tree gains a `test_*.py` name, which it must not)

**Interfaces:**
- Consumes: `live_run.run_chain` with the real `claude`; every script's public function as in Task 9.
- Produces: the golden tree; `UPDATE_GOLDENS=1` environment switch in the chain test to regenerate the deterministic goldens (`candidates.json`, `verify-plan.json`, `verified.json`, `ranked.json`) from the canned scouts and verdicts, never the scouts and verdicts themselves.

**Confidence:** 90% after mitigations. The uncertainty is the live output itself (how many findings a real scout returns on a small fixture). Mitigations: (1) the run uses the `deep` set so every family with leads is exercised; (2) if a fixture's live scouts return no finding for a planted family, the implementer adds one hand-written finding to that scout golden citing the planted lines verbatim from the fixture file, labelled in a `"_note"` key that the merge ignores (a string key on the scout document, not on a finding), and records which findings were added in the report; (3) two hand edits per fixture are required regardless: one finding whose quote is invented (pins the diversion path; goes in the scout file of the family with the most findings) and one verdict with `verdict: "reject"` and a non-null `trap_matched` on a decoy or an added finding (pins the trap path).

**Cost note:** run on `sonnet` with `--max-budget-usd 1.00` per call; three fixtures, expected 5 to 9 scout calls and 2 to 5 verifier batches each. Record the three `cost_usd` values in the report.

- [ ] **Step 1: Run the harness over each fixture**

From `skills/tech-debt-scan/`:

```
python scripts/live_run.py service-py --families deep --top 5 --model sonnet --max-budget-usd 1.00 --workdir ../../.tech-debt-live/service-py
python scripts/live_run.py web-ts --families deep --top 5 --model sonnet --max-budget-usd 1.00 --workdir ../../.tech-debt-live/web-ts
python scripts/live_run.py mixed-decoys --families deep --top 5 --model sonnet --max-budget-usd 1.00 --workdir ../../.tech-debt-live/mixed-decoys
```

Each run prints the evaluation table and appends a row to `docs/evaluation-log.md`. Exit 4 means an agent call failed twice: read the error, fix the harness if it is a harness bug (report it), rerun that fixture. `.tech-debt-live/` is outside the skill tree; add it to the repository `.gitignore` in this task.

- [ ] **Step 2: Copy the agent outputs into the golden tree and apply the hand edits**

For each fixture copy `scouts/*.json` and `verdicts/*.json` from the live workdir into `tests/golden/<fixture>/`. Then:

1. In the scout file with the most findings, append one finding whose quote is `"this quote was never in the file"` on a real file at lines 1 to 1, title `invented quote (golden pin)`; it must NOT match anything, so the merge diverts it.
2. In one verdict file, change one entry's `verdict` to `"reject"` and set `trap_matched` to `"golden trap: intentional fixture"`; choose an entry whose candidate sits on a decoy path when one exists, else any entry.
3. For every planted family with zero live findings, add one hand-written finding citing the planted lines (quote copied verbatim from `tests/fixtures/corpus/<fixture>/files/<path>`), and add `"_note": "hand-added: <family>"` at the top level of that scout document.

- [ ] **Step 3: Write the failing chain test**

Create `skills/tech-debt-scan/tests/test_chain_goldens.py`:

```python
"""The detect, verify, rank chain over the corpus with canned scouts and verdicts (spec 6, 11).

Scout and verdict files are the first live run's output (plus the hand edits the
phase 2 plan names); every deterministic stage is compared byte for byte to its
golden. Regenerate the deterministic goldens with UPDATE_GOLDENS=1 after an
intentional change; never regenerate the scouts or verdicts by hand.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from apply_verdicts import apply
from config import DEFAULTS
from evaluate import evaluate
from inventory import build_all, write_json, write_outputs
from merge_findings import merge
from patterns import run_patterns
from plan_scan import build_plan, write_plan
from rank import rank
from rules import run_rules
from verify_prompts import build_verify_plan

GOLDEN = Path(__file__).parent / "golden"
CORPUS = Path(__file__).parent / "fixtures" / "corpus"
FIXTURES = ("service-py", "web-ts", "mixed-decoys")
UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"


def _canon(doc: dict[str, Any], root: str) -> bytes:
    text = json.dumps(doc, indent=2) + "\n"
    return text.replace(root, "<root>").encode("utf-8")


def _check(name: str, doc: dict[str, Any], golden: Path, root: str) -> None:
    got = _canon(doc, root)
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(got)
    assert golden.is_file(), f"missing golden {golden}"
    assert got == golden.read_bytes(), f"{name} differs from {golden}"


def _chain(name: str, repo: Path, tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workdir = tmp_path / "wd"
    planted = json.loads((CORPUS / name / "planted.json").read_bytes())
    inventory, coupling = build_all(repo, churn_months=int(planted["churn_months"]), config=DEFAULTS)
    write_outputs(inventory, coupling, workdir)
    patterns, inline = run_patterns(repo, inventory, DEFAULTS, blame=False)
    for entry in inventory["files"]:
        entry["inline_disables"] = inline.get(entry["path"], 0)
    write_json(workdir / "inventory.json", inventory)
    write_json(workdir / "patterns.json", patterns)
    findings, leads = run_rules(repo, inventory, DEFAULTS)
    write_json(workdir / "rule-findings.json", {"schema_version": 2, "findings": findings, "leads": leads})
    plan, prompts = build_plan(workdir, DEFAULTS, families="deep", top=5)
    write_plan(workdir, plan, prompts)
    golden = GOLDEN / name
    for entry in plan["entries"]:
        src = golden / entry["output"]
        assert src.is_file(), f"golden scout missing for {entry['family']} on {name}"
        shutil.copy(src, workdir / entry["output"])
    for extra in sorted((golden / "scouts").glob("*.json")):
        assert extra.name in {Path(e["output"]).name for e in plan["entries"]}, \
            f"golden scout {extra.name} is not in the plan for {name}"
    root = str(repo.resolve())
    candidates = merge(workdir, repo, DEFAULTS)
    write_json(workdir / "candidates.json", candidates)
    _check("candidates", candidates, golden / "candidates.json", root)
    vplan, _ = build_verify_plan(workdir, repo, DEFAULTS, 5)
    _check("verify-plan", vplan, golden / "verify-plan.json", root)
    verdicts = {}
    for batch in vplan["batches"]:
        src = golden / batch["output"]
        assert src.is_file(), f"golden verdict missing: {src}"
        verdicts[batch["output"]] = json.loads(src.read_bytes())
    verified = apply(candidates["candidates"], vplan, verdicts)
    _check("verified", verified, golden / "verified.json", root)
    ranked = rank(verified, inventory, DEFAULTS, preset="balanced", top=5)
    _check("ranked", ranked, golden / "ranked.json", root)
    return candidates, verified, ranked


@pytest.mark.parametrize("name", FIXTURES)
def test_chain_matches_goldens_and_meets_the_corpus_bar(name: str, request: pytest.FixtureRequest,
                                                        tmp_path: Path) -> None:
    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    candidates, verified, ranked = _chain(name, repo, tmp_path)
    planted = json.loads((CORPUS / name / "planted.json").read_bytes())
    report = evaluate(verified["findings"], planted, set(ranked["top_n"]), top=5)
    assert report["decoys_in_tier_a"] == 0, report["decoys"]
    assert report["decoys_in_top_n"] == 0, report["decoys"]
    assert report["counts"]["on_planted"] > 0
    diverted = [q for q in candidates["open_questions"] if q["reason"] == "quote not found"]
    assert len(diverted) == 1, "exactly one invented quote is pinned per fixture"
    assert any(f["verdict"] == "reject" and f["trap_matched"] for f in verified["findings"])
    assert all(f["tier"] in ("A", "B") for f in verified["findings"] if f["fingerprint"] in ranked["top_n"])


@pytest.mark.parametrize("name", FIXTURES)
def test_every_golden_quote_except_the_pin_verifies(name: str, request: pytest.FixtureRequest) -> None:
    from evidence import find_quote

    repo = request.getfixturevalue(name.replace("-", "_") + "_repo")
    misses = []
    for scout in sorted((GOLDEN / name / "scouts").glob("*.json")):
        for finding in json.loads(scout.read_bytes())["findings"]:
            for ev in finding["evidence"]:
                path = repo / ev["file"]
                lines = path.read_bytes().decode("utf-8", "replace").splitlines() if path.is_file() else []
                if find_quote(lines, ev["quote"], ev.get("line_start"), ev.get("line_end")) is None:
                    misses.append((scout.name, finding["title"]))
    assert misses == [(m[0], m[1]) for m in misses if m[1] == "invented quote (golden pin)"], misses
    assert len(misses) == 1
```

- [ ] **Step 4: Generate the deterministic goldens and run**

Run: `UPDATE_GOLDENS=1 python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` (PowerShell: `$env:UPDATE_GOLDENS="1"; python -m pytest ...; Remove-Item Env:UPDATE_GOLDENS`), then `python -m pytest skills/tech-debt-scan/tests/test_chain_goldens.py -q` without the switch. Expected: both green. If `decoys_in_tier_a` is not 0, do not edit the verdict to hide it: report which decoy reached tier A and through which corroboration; the controller rules whether the cap table (Task 7) or the fixture is wrong.

- [ ] **Step 5: Gate and commit**

Run the gate (`norecursedirs` already excludes `fixtures/corpus`; the golden tree holds no `test_*.py`). Commit:

```
test(tech-debt-scan): corpus goldens from the first live run and the golden chain test
```

---

### Task 11: docs sweep, the phase gate live run, and the PR

**Files:**
- Modify: `docs/architecture.md`, `README.md`, `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` (only where a task above recorded an amendment note: 4.7 stats key, 4.6 set forms are already amended), `docs/evaluation-log.md` (three more rows)
- No SKILL.md change (phase 3).

**Confidence:** 95%.

- [ ] **Step 1: Docs sweep**

Read `docs/architecture.md` top to bottom and `README.md` "Output formats" and "Status" against the code: every script table row exists for `plan_scan.py`, `merge_findings.py`, `verify_prompts.py`, `apply_verdicts.py`, `rank.py`, `live_run.py`; every output row exists for `scan-plan.json`, `candidates.json`, `verify-plan.json`, `verified.json`, `ranked.json`, `evaluation.json`; the README "Status" paragraph says phase 2 lands the chain behind the harness while `/tech-debt-scan` still runs v1 until phase 3. Verify every flag named in a doc line against the script's argparse (`python scripts/<name>.py --help`).

- [ ] **Step 2: The phase gate live run**

From `skills/tech-debt-scan/`, rerun all three fixtures exactly as in Task 10 Step 1 (fresh workdirs under `../../.tech-debt-live/gate-<fixture>`). Record the three rows the harness appends. The gate passes when every row shows `decoys_tier_a` 0 and `decoys_top_n` 0; `tier_a_precision` is reported against 0.80 and does not block (spec success criterion 2 at v2.0). If a run fails with exit 4, the harness or a prompt has a defect: fix, rerun, report. Do not copy this run's output into the goldens.

- [ ] **Step 3: Full gate and commit**

```
docs(tech-debt-scan): phase 2 documentation sweep and gate live-run rows
```

- [ ] **Step 4: PR**

The PR opens after the final whole-branch review through `superpowers:finishing-a-development-branch` (phase 1 ruling), against `main`, titled `feat(tech-debt-scan): v2 phase 2 detect, verify, rank (plan_scan, merge, verify, apply, rank, live harness)`. The body lists the six scripts, the golden tree, the evaluation-log rows with their precision numbers, and the deferred items the reviews parked.

---

## Self-review

**Spec coverage (phase 2 scope, section 11):** `categories.py` v2 with all fourteen blocks (Task 3); `plan_scan.py` with the adaptive rule and no chunking (Task 4); `merge_findings.py` (Task 5); `verify_prompts.py` and `apply_verdicts.py` (Tasks 6, 7); `rank.py` (Task 8); goldens for scouts, candidates, verdicts, verified and ranked (Task 10); gate items: quote-fabrication diversion (Task 5 test and Task 10 pin), tier table (Task 7), budget rule (Task 6), spread cap and determinism and the worked example (Task 8), `evaluate.py` over the goldens (Task 10); the amendments: island churn floor and CODEOWNERS guard and namespace pin (Task 2), set forms (Task 4), targeted goldens and live harness with the first evaluation rows (Tasks 9, 10, 11). `4.6` prompt test constraints (fourteen-family set, token ban, schema keys, "hotspot" and "Severity rubric") are Task 3's tests. `4.8` tests: budget selection floors and inclusions and cap and tier A exclusion, batch grouping, context at file boundaries (the `19 |` absent assertion), traps from config, tier table, family caps, unknown fingerprint dropped, missing verdict unverified, verifier severity override: Tasks 6 and 7. Traps from rejected baseline entries are phase 5 (spec 4.8 names the baseline; the plan's Task 6 renders config traps only, stated in its docstring). `4.9` tests: byte-identical, worked example for both presets, preset weights, spread cap, tie-break, F zero cases, tier C excluded, quick-wins exclusions, hotspot correlation: Task 8.

**Placeholder scan:** no TBD, TODO, "similar to", or "add validation" phrases; every code step carries its code; the only implementer-filled values are `EXPECTED_RUN` in Task 4 (three sets, filled from the first run and checked by the reviewer against `planted.json`) and the golden files in Task 10 (produced by the live run and the three named hand edits).

**Type consistency:** `fingerprint(family, path, quote) -> tuple[str, str]`, `find_quote(lines, quote, line_start, line_end, *, max_lines=6)`, `signals_for(inventory, path)`, `priority_terms(candidate, maxima, weights, tractability, *, tier, fan_in_mode)`, `repo_maxima(inventory)` are defined in Task 1 and Task 6 (`evidence.py`) and used by Tasks 5, 6, 8 with those signatures; `disabled_families(config, path_class)` is defined in Task 4 and imported by Task 5; `FAMILY_BLOCKS[...].verifier_questions` is defined in Task 3 and read in Task 6; `VERDICT_VALUES` and `VERDICT_SCHEMA` are defined in Task 6 and read in Tasks 7 and 9; `SCOUT_OUTPUT_SCHEMA` is defined in Task 3 and read in Task 9; `build_plan(workdir, config, *, families, top)` and `write_plan` (Task 4) are called by Task 9 and Task 10 with those keywords; `merge(workdir, root, config, *, today=None)` (Task 5) is called by Tasks 9 and 10; `build_verify_plan(workdir, root, config, top)` (Task 6) by Tasks 9 and 10; `apply(candidates, verify_plan, verdicts)` (Task 7) by Tasks 9 and 10; `rank(verified, inventory, config, *, preset, top)` (Task 8) by Tasks 9 and 10; `evaluate(findings, planted_doc, top_n, *, top)` and `render_table` exist in phase 1's `evaluate.py` with those signatures.
