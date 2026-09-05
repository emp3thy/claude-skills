# tech-debt-scan v2 Phase 1 follow-up (parked re-review findings) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents are available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the findings the phase 1 final re-review parked, before the phase 2 merge stage builds on `patterns.json` and `rule-findings.json`.

**Spec:** `docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md` (binding). Sections 4.2 (artefact `path_class`, size guard), 4.3 (`patterns.py` leads carry `path_class`), 4.4 (`rules.py`). The origin of every item is the phase 1 final review and its scoped re-review (merged in PR #4); nothing here is new design.

**Branch:** `fix/tech-debt-scan-v2-phase-1-followup` off `main` at 6163c90, already created and checked out in the main checkout at `C:/Users/gethi/source/claude-skills` (no linked worktree: the standards doc records Windows worktree-removal hazards).

**Out of scope:** the knowledge-island churn floor (spec-level, the phase 2 plan decides); `docs/architecture.md` "six scout categories" (phase 3 rewrites the page); splitting `patterns.py` or `inventory.py`; every other "can wait" minor from the final review.

## Global Constraints

Copied from spec sections 0 and 3.3; every task's requirements include these.

- Python 3.11+; pyyaml is the only runtime dependency; every script is direct-path invocable from `skills/tech-debt-scan/` with flat sibling imports (`from inventory import MAX_SCAN_BYTES`), never package imports.
- Language-agnostic rule (spec 0(d), 3.3): the extension map in `inventory.py` is the only language-aware table; any per-language branch anywhere else is a defect.
- Git and tool calls are list argv through `run_git` with `timeout=120` and a null result on failure; a missing signal never aborts a scan.
- Rendered output is LF-only, written with `write_bytes(text.encode("utf-8"))`; JSON keys stay in the spec's pinned order.
- No live LLM in tests; the `live` marker never runs in CI.
- Gate for every task and for the PR, from the repository root: `python -m ruff check .`, `python -m mypy`, `python skills/tech-debt-scan/scripts/skill_check.py`, `python -m pytest -q`; all green.
- Windows-safe: list argv everywhere, forward-slashed paths in output.
- Docs in sync: `README.md` "Output formats" table and `docs/architecture.md` script table describe `patterns.json` and `rule-findings.json`; any contract change lands in the same commit.
- Commit trailers: every commit message ends with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Conventional-commit subjects.
- TDD: each defect gets a failing test first (RED shown), then the fix (GREEN).

## Guardrails (from project memory and standards)

- [[keep-docs-in-sync]] (confidence 0.95): README and architecture.md rows for `patterns.py` and `rules.py` change in the same commit as the code; verify every token in a rewritten doc line against the source.
- [[redaction-invariant]] (this branch's own lesson): every quote any script writes passes through `redaction.redact`; Task 1 closes the last writer in `rules.py`.
- Dismissed: worktree-on-Windows hazards (no worktree used); mkstemp/fdopen (no temp files here); TypeScript Partial (no TypeScript).

## File structure

| File | Task | Change |
|---|---|---|
| `skills/tech-debt-scan/scripts/rules.py` | 1 | `_read` honours the size guard and `skipped_large`; `_disabled` applied to configs; tslint lead quote redacted |
| `skills/tech-debt-scan/tests/test_rules.py` | 1 | three new tests |
| `skills/tech-debt-scan/tests/test_evaluate.py` | 1 | width-assertion slice covers every family row |
| `skills/tech-debt-scan/scripts/patterns.py` | 2 | `ScanFile` gains `scope`; artefact `ScanFile`s carry the real `path_class`; generated/vendored/`skipped_large` artefacts skipped |
| `skills/tech-debt-scan/tests/test_patterns.py` | 2 | two new tests; existing artefact assertions updated |
| `docs/architecture.md`, `README.md`, spec 4.3 | 2 | `patterns.json` leads on artefacts carry the real `path_class` |

---

### Task 1: `rules.py` reads only what the inventory would, filters configs, redacts the tslint lead; `test_evaluate.py` slice

**Files:**
- Modify: `skills/tech-debt-scan/scripts/rules.py` (`_read` at ~140, `_manifest_hits` at ~383-437)
- Modify: `skills/tech-debt-scan/tests/test_rules.py`
- Modify: `skills/tech-debt-scan/tests/test_evaluate.py` (line 158)

**Confidence:** 95% (each change is a few lines against code read at plan-write time; `rules.py` already imports from `inventory`, so importing `MAX_SCAN_BYTES` and `NUL_SNIFF_BYTES` adds no cycle; the existing Dockerfile-redaction and path-class tests in `test_rules.py` are the templates for the new ones).

**Findings this task closes (from the phase 1 re-review, verbatim intent):**
- `rules.py` `_read` reads every artefact whole with no size cap and ignores the inventory's `skipped_large` flag, so a multi-hundred-MB Dockerfile, workflow or manifest is still decoded in full by `rules.py` after `inventory.py` marked it skipped.
- `_disabled` filters `manifests` but not `configs`: a `tslint.json` under a tests, vendored or generated tree still emits a migration lead while a `pyproject.toml`/`setup.py` pair under one no longer does.
- The tslint migration lead's quote (`rules.py` ~431) is the one write path in `rules.py` that still skips `redact`; its sibling `setup.py` lead four lines above was redacted.
- `tests/test_evaluate.py:158`: `render_table` emits 2 header lines + F family rows + 3 tail rows, so `lines[2:-4]` stops one row short of the final family row; `lines[2:-3]` is the intended slice.

- [ ] **Step 1: Write the failing tests in `tests/test_rules.py`**

Follow the style of `test_credential_in_a_dockerfile_quote_is_redacted` and the root-vs-`tests/fixtures/x/` Dockerfile test (synthetic repo under `tmp_path`, `build_all(repo, churn_months=240)`, then `run_rules`). Add:

1. `test_skipped_large_artefact_is_never_read`: a synthetic repo whose root `Dockerfile` is `MAX_SCAN_BYTES + 1` bytes (a valid first line `FROM alpine:3.20` then padding so a naive read would still yield a `container` finding) and a second `Dockerfile` under `svc/` with a NUL byte inside its first 1 KB. Build the inventory (both entries have `skipped_large: true`), monkeypatch `rules._read` with a wrapper that records every `rel` it is asked for, run `run_rules`, and assert: neither Dockerfile produced a finding, and the recorder never saw either path. Then call `rules._read(root, "Dockerfile")` directly and assert it returns `""` (the size guard inside `_read` itself, independent of the flag).
2. `test_tslint_lead_under_a_tests_tree_is_skipped_and_its_quote_redacted`: a repo with `tslint.json` + `.eslintrc.json` at root and the same pair under `tests/fixtures/y/`; the root `tslint.json` first line is `{"token": "abcdefghijkl0123"}`. Assert exactly one migration lead, its `file` is the root `tslint.json`, its `path_class` is `"source"` (the artefact's real path class, not the literal `"config"`), the secret is absent from `json.dumps(leads)` and `abcd***` is present.
3. In `tests/test_evaluate.py`, change the slice at line 158 to `lines[2:-3]` and add, beside it, an assertion that the slice length equals the number of family rows in the report (`len(report["families"])` or the equivalent key the test already reads) so the slice cannot silently shrink again.

- [ ] **Step 2: Run the new tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_rules.py -k "skipped_large_artefact or tslint_lead" -q
python -m pytest skills/tech-debt-scan/tests/test_evaluate.py -k render -q
```
Expected: the two `test_rules.py` tests fail (a finding is produced from the oversized Dockerfile; two tslint leads with the raw secret); the `test_evaluate.py` change passes or fails depending on the last family row's width, either is acceptable for the slice change as long as the length assertion is what pins it.

- [ ] **Step 3: Fix `rules.py`**

1. Import `MAX_SCAN_BYTES` and `NUL_SNIFF_BYTES` from `inventory` (flat import beside `write_json`). Rewrite `_read` so it returns `""` without reading when `path.stat().st_size > MAX_SCAN_BYTES`, reads the first `NUL_SNIFF_BYTES` first and returns `""` when a NUL is present, otherwise reads and decodes as today; `OSError` still returns `""`.
2. Extend `_disabled(artefact)` to also return `True` when `artefact.get("skipped_large")` is true (name stays; its docstring says it answers "should rules.py look at this artefact at all"). Apply `_disabled` to the `configs` set in `_manifest_hits` exactly as it is applied to `manifests`.
3. In the tslint lead, wrap the quote in `redact(...)` and set `path_class` from the config artefact's own `path_class` entry instead of the literal `"config"`; keep a dict of config artefacts by path so the lookup is O(1).
4. Update the `rules.py` module docstring sentence that describes what is skipped (tests/vendored/generated artefacts) to add "and artefacts the inventory marked `skipped_large`".

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests/test_rules.py skills/tech-debt-scan/tests/test_evaluate.py -q
```

- [ ] **Step 5: Docs**

`README.md` `rule-findings.json` row and `docs/architecture.md` `rules.py` row: add that artefacts the inventory marked `skipped_large` are never read. Verify every other token in the rewritten cells against the code.

- [ ] **Step 6: Gate and commit**

Full gate from the repository root (all four commands). Commit:

```
fix(tech-debt-scan): rules.py honours the size guard, filters configs and redacts the tslint lead
```

---

### Task 2: `patterns.py` scans artefacts by rule scope but reports their real path class

**Files:**
- Modify: `skills/tech-debt-scan/scripts/patterns.py` (`ScanFile` at ~110-130, `_scan_files` at ~848-870, the scope check at ~927)
- Modify: `skills/tech-debt-scan/tests/test_patterns.py`
- Modify: `docs/architecture.md` (patterns.py row), `README.md` (`patterns.json` row), spec section 4.3 (one sentence)

**Confidence:** 92% (the scope mechanism was read at plan-write time: `Rule.scope` sets such as `ALL_TEXT` and `SOURCE_CI_CONFIG` contain artefact class names, and `_run_rule` checks `sf.path_class not in rule.scope`, so the artefact class must keep driving scope while the emitted `path_class` changes; the risk is corpus tests that assert artefact leads carry a class name, which Step 2 surfaces).

**Finding this task closes (from the phase 1 re-review):**
- `patterns.py` `_scan_files` passes the artefact *class* (`ci`, `container`, `config`, ...) as `ScanFile.path_class`, so `patterns.json` leads and SATD entries on artefacts carry `ci`/`container` where `rules.py` now carries the real path class, and a workflow or Dockerfile under a fixture tree is scanned and reported as if it were first-party. Phase 2's merge applies path-class disables to leads (spec 4.7 step 7) and needs the real class.

**Design (fixed):** `ScanFile` gains a `scope: str` field; `Rule.scope` is checked against `sf.scope`, not `sf.path_class`. For code files `scope == path_class` (unchanged behaviour). For artefacts `scope` is the artefact class (so `ALL_TEXT` and `SOURCE_CI_CONFIG` keep matching exactly as today) and `path_class` is the artefact entry's real `path_class` from the inventory. Emitted leads and SATD entries carry `sf.path_class`. Artefacts whose `path_class` is `generated` or `vendored`, or whose entry has `skipped_large: true`, are not scanned (the same skip the code-file loop applies). Scanners that test `sf.path_class == "tests"` (the credential scanner) therefore now also skip tests-tree artefacts. `_logger_present` keeps `sf.path_class == "source"`.

- [ ] **Step 1: Write the failing tests in `tests/test_patterns.py`**

1. `test_artefact_leads_carry_the_real_path_class_and_keep_rule_scope`: a synthetic repo with `.github/workflows/ci.yml` at root and an identical copy under `tests/fixtures/z/.github/workflows/ci.yml`, both containing a line that fires an artefact-scoped rule (a SATD marker `# TODO: pin the runner image` is in `ALL_TEXT`, and `NODE_TLS_REJECT_UNAUTHORIZED=0` fires `tls-disabled` in `SOURCE_CI_CONFIG`). Run patterns. Assert: the root workflow's leads exist with `path_class == "source"`; the fixture-tree workflow's SATD lead exists with `path_class == "tests"`; the `tls-disabled` lead fires on the root workflow (scope still matches the `ci` class) and not on the fixture-tree one if the scanner skips tests (assert whichever the credential/security scanner's existing `tests` skip implies, and state it in the test's docstring); no lead anywhere carries `path_class` equal to an artefact class name (`"ci"`, `"container"`, `"config"`, `"build"`).
2. `test_generated_vendored_and_skipped_large_artefacts_are_not_scanned`: a repo with `vendor/Dockerfile`, `generated/compose.yaml` (or whichever glob the inventory classifies as generated) and a root `Dockerfile` of `MAX_SCAN_BYTES + 1` bytes; assert none of the three appears in any lead or SATD entry and that `_scan_files` returns no `ScanFile` for them.
3. Run the whole `test_patterns.py` and `test_corpus.py` to find existing assertions on artefact `path_class` values (`"ci"`, `"config"`, `"build"` in lead or SATD entries); update each to the real path class, keeping the test's intent. The `satd.scope` assertion at line ~72 is about `Rule.scope` and stays.

- [ ] **Step 2: Run the new tests to verify they fail**

```
python -m pytest skills/tech-debt-scan/tests/test_patterns.py -k "real_path_class or not_scanned" -q
```
Expected: both fail (leads carry `"ci"`; vendored/generated/oversized artefacts are scanned).

- [ ] **Step 3: Change `patterns.py`**

1. Add `scope: str` to `ScanFile` (after `path_class`); do not add it to the emitted dict.
2. In `_scan_files`, code files: `ScanFile(path, path_class, path_class, ...)`. Artefacts: read `path_class = str(artefact["path_class"])`; skip when it is `generated` or `vendored` or when `artefact.get("skipped_large")` is true; otherwise `ScanFile(path, path_class, cls, ...)`.
3. Change the scope check to `if sf.scope not in rule.scope`.
4. Update the module docstring paragraph that explains artefact scanning: scope by artefact class, report the real path class, the three skips.

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest skills/tech-debt-scan/tests/test_patterns.py skills/tech-debt-scan/tests/test_corpus.py skills/tech-debt-scan/tests/test_rules.py -q
```

- [ ] **Step 5: Docs and spec**

- `docs/architecture.md` `patterns.py` row and `README.md` `patterns.json` row: leads and SATD entries on artefacts carry the artefact's real `path_class`; rule scope still keys on the artefact class; generated, vendored and `skipped_large` artefacts are not scanned.
- Spec 4.3: one sentence after "Every regex is a union of idioms across languages; the extension map only says which comment markers to strip." stating the same contract (this is the in-branch spec amendment the phase 1 branch also practised).

- [ ] **Step 6: Gate and commit**

Full gate from the repository root. Commit:

```
fix(tech-debt-scan): patterns.py reports the real path class on artefact leads
```

---

## Finish

After both tasks: final whole-branch review (most capable model) over `git merge-base main HEAD..HEAD`, one fix wave at most, then `superpowers:finishing-a-development-branch` (push, PR against `main`, squash merge once CI is green).
