# tech-debt-scan — architecture

This page is the design reference for the `tech-debt-scan` skill. The
canonical spec lives in the private `ralph` repo at
`docs/superpowers/specs/2026-05-31-tech-debt-scan-design.md`; because this
skills repo cannot link cross-repo to a private file, the relevant design is
inlined here. Where this page and the scripts disagree, **the scripts win** —
they are the source of truth, and the test suite pins their behaviour.

## Design principles

- **Language-independent.** The only language-aware code is the inventory's
  extension→language map. Scout prompts and synthesis are language-neutral and
  reason about the inventory + the repo's own files.
- **LLM does the judgement, scripts do the determinism.** The model dispatches
  scout agents and picks the top 5. File walking, prompt rendering, markdown
  rendering, parsing, validation, and bundle writing are all pure Python with
  pinned commands and pinned output files — no improvisation.
- **Human in the loop.** Phase 1 never applies a fix. A single `design.md`
  round-trips through human review: scan writes it, a human edits `status:`
  fields, promote reads it back.
- **Direct-path invocable scripts.** Every script runs as
  `python scripts/<name>.py` from `skills/tech-debt-scan/`. No package install,
  no `-m`, no cross-module package layout (the only intra-`scripts` imports are
  flat top-level imports resolved by the test `conftest.py` and `mypy_path`).
- **Read-only scouts.** Scout agents use Explore semantics; they never write.

## Two-command flow

```
/tech-debt-scan <repo>                         /tech-debt-promote
─────────────────────────                      ──────────────────
inventory.py        → inventory.json           (human edits design.md:
scouts (Agent x6)   → [findings]                pending → approved/rejected)
  (Claude writes)   → raw-findings.json
build_synthesis_    → synthesis-prompt.txt     design_parser.py → (inspect)
  prompt.py                                     promote.py       → chore-<slug>-<date>/
synthesis (Agent)   → top5.json                   ├─ bundle_writer.py (per finding)
design_writer.py    → design.md                   └─ design_writer.mark_promoted
  render                                              (approved → promoted)
        │                                                    │
        └──────────────  design.md  (human review)  ─────────┘
```

All intermediate artefacts default to `.tech-debt/` under the scanned repo (the
directory is gitignored and is itself in the inventory ignore list). Bundles
default to `./tech-debt-pbis`.

## Scout categories

Six language-agnostic debt categories, defined in `scripts/categories.py`
(`CATEGORIES` + `get_prompt(name)`). One scout agent is dispatched per category:

| Category | Looks for |
| --- | --- |
| `god-modules` | Oversized files/classes/functions doing too much |
| `duplication` | Copy-pasted or near-duplicate logic |
| `dead-code` | Unreferenced functions, modules, exports |
| `test-gaps` | Critical paths with no or thin test coverage |
| `doc-drift` | Docs/comments that no longer match the code |
| `half-finished` | TODO/FIXME, stubbed work, abandoned branches |

Each scout returns a JSON array of `ScoutFinding` objects:

```json
{ "title": "...", "severity": 1, "category": "dead-code",
  "evidence": [{ "file": "...", "line": 1, "note": "..." }],
  "suggested_fix": "..." }
```

`title` ≤ 80 chars, `suggested_fix` ≤ 500 chars, `severity` an integer 1–5.

## Synthesis

`build_synthesis_prompt.py` reads `raw-findings.json`, sorts findings by
`severity` descending, caps at the top 30 (logging how many were truncated to
stderr), and renders a picker prompt that asks the synthesis Agent to choose the
single most important finding per category and return exactly five.

The Agent's response (`top5.json`) is validated by
`build_synthesis_prompt.validate_synthesis_output`, which raises `SynthesisError`
if the response is not valid JSON, does not contain a `top5` array of exactly 5
items, is missing a required field, or carries a bad `slug` / out-of-range
`severity` / unknown `category`.

## design.md format

`design_writer.py render` writes a single markdown document:

- **Frontmatter** (hand-rendered, not `yaml.dump`, to keep key order and avoid
  quoting the date): `scan_date`, `root`, `total_files`, `total_loc`,
  `languages`.
- **One `## ` section per finding.** Each section opens with a fenced ` ```yaml `
  anchor block carrying `status`, `slug`, `severity`, `category`, followed by
  `Reasoning`, `Evidence`, and `Suggested fix` prose.

The renderer re-parses its own output via `design_parser.parse_design` as a
self-check before exiting; a round-trip failure exits non-zero.

`design.md` is written LF-only (`write_bytes`) so it byte-matches across
platforms regardless of `core.autocrlf`.

## Validation rules

Shared validators live in `scripts/validation.py`:

- **Status** (`validate_status`): one of `pending`, `approved`, `rejected`,
  `promoted`.
- **Slug** (`validate_slug`): matches `^[a-z][a-z0-9-]{0,63}$` (starts with a
  lowercase letter, 1–64 chars total) and must not end with a hyphen.

## Promotion

`promote.py <design.md> --out <dir> [--force]`:

1. `design_parser.parse_design` parses the (human-edited) `design.md`.
2. For each finding with `status: approved`, `bundle_writer.write_bundle` writes
   a `chore-<slug>-<date>/` directory containing `PBI.md`, `PLAN.md`, and
   `HISTORY.md`. Severity maps to a word: 5 → `critical`, 4 → `high`, 3 →
   `normal`, 2/1 → `low`.
3. `design_writer.mark_promoted` flips each emitted finding's status from
   `approved` to `promoted` in place (atomic `os.replace` via a `.tmp` file,
   `.bak` of the prior content), so a re-run is a no-op.

**Collision policy.** An existing bundle directory is treated as
already-promoted (counted, not re-emitted) unless `--force` is given.

**Exit codes.** `0` success; `2` on a parse / mark-promoted error; `4` on a
bundle-write failure *after* at least one bundle was written (roll-forward — the
succeeded bundles persist and their findings are still marked promoted).

## CI and testing

- `scripts/skill_check.py` lints SKILL.md: it extracts every
  `python scripts/<name>.py` command, runs each script's `--help` (subcommand-
  aware), and asserts every `--flag` used in the documented command appears in
  the help. It runs in CI before pytest.
- Tests never call a live Agent. Scout dispatch and synthesis are exercised by
  feeding canned JSON to the scripts; the end-to-end test
  (`tests/test_e2e.py`) drives scan→promote against fixture repos with golden
  inputs. The `live` pytest marker is off by default.
- The full suite must pass `ruff`, `mypy --strict`, and `pytest` in CI.

## Scope

Phase 1 (human-in-the-loop) only. Phase 2 — autonomously applying fixes without
review — is deferred.
