# tech-debt-scan — architecture

This page is the design reference for the `tech-debt-scan` skill. The
canonical spec lives in the private `ralph` repo at
`docs/superpowers/specs/2026-05-31-tech-debt-scan-design.md`; because this
skills repo cannot link cross-repo to a private file, the relevant design is
inlined here. Where this page and the scripts disagree, **the scripts win** —
they are the source of truth, and the test suite pins their behaviour.

## Design principles

- **Language-independent.** The only language-aware code is the inventory's
  extension→language map, which also supplies each language's comment syntax
  to `patterns.py`. Every rule in `inventory.py`, `patterns.py` and `rules.py`
  is a union of idioms across languages; a test greps the scripts for any
  branch on a language name. Scout prompts and synthesis are language-neutral.
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

## Deterministic signals (v2 phase 1)

Phases 1 and 2 of the v2 design (`docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md`)
add the scripts below, which run by hand until phase 3 wires them into the workflow:

| Script | Reads | Writes | What it computes |
| --- | --- | --- | --- |
| `inventory.py <repo> --workdir .tech-debt` | the tree, one `git log` pass, `.tech-debt.yaml` | `inventory.json`, `coupling.json` | path classes (tests, generated, vendored, docs, source) on code files and artefacts alike, artefact classes, per-file churn and authorship (authors keyed by email, bots dropped, joined against HEAD), `hotspot_score` and the `hotspot_band` (top 10 percent of source files, 5 to 50), blame line share on the band, change-coupling pairs (`shared >= 3`, `ratio >= 0.30`, bulk commits over 50 files excluded), approximate fan-in and fan-out by identifier stems over import-like lines with the mechanical ambiguity rule, import-line cycles of size 2 to 5 as leads, directory instability, test mapping across seven naming conventions, the docs and tests blocks, and the size guard that never reads a file over 2 MB or with a NUL byte in its first KB (`skipped_large` per entry, `skipped_large_files` at the top level) |
| `patterns.py <repo> --workdir .tech-debt [--no-blame]` | `inventory.json`, the files | `patterns.json`; fills `files[].inline_disables` | regex leads per family (half-finished stubs and skips and no-timeout calls, error-masking catches with the caught variable and carrier exclusion, dead-code commented-out runs, legacy names, deprecations and flag SDK calls, security credentials with four-character redaction, string SQL, dynamic evaluation, TLS off, weak hashes, permissive CORS and suppressions, test-quality signals, stdout writes where a logger exists) and the SATD table with blame age and ticket flags; artefacts are scoped by their artefact class but every lead and SATD entry on one reports the artefact's real `path_class`, and an artefact classed `generated` or `vendored`, or marked `skipped_large`, is not scanned |
| `rules.py <repo> --workdir .tech-debt` | `inventory.json`, the artefacts | `rule-findings.json` | tier-A findings for CI jobs, Dockerfiles and compose images, Kubernetes manifests, manifests without lockfiles, release cadence and stale environment branches, and ownership (knowledge islands, inactive top authors, CODEOWNERS coverage); an island also needs `churn >= island_min_churn` (2) in the window; a CODEOWNERS the inventory skipped or that sits under a disabled tree is not consulted; migration leads for `setup.py` beside `pyproject.toml` and `tslint` beside `eslint`; an artefact under a tests, vendored or generated tree is skipped, an artefact the inventory marked `skipped_large` is never read, and every finding carries the artefact's `path_class` in `signals` |
| `plan_scan.py --workdir .tech-debt [--families <set>] [--top N]` | `inventory.json`, `coupling.json`, `patterns.json`, `rule-findings.json` | `scan-plan.json`, `prompts/scout-<family>.md` | the adaptive rule (a family runs only when it has at least one lead after path-class disables), the 40-lead cap with hotspot-band files first, the fourteen family blocks; `chunked` is always false until phase 4 |
| `merge_findings.py --workdir .tech-debt` | `scan-plan.json`, the `scouts/<family>.json` it names, `rule-findings.json`, `inventory.json`, `patterns.json`, `.tech-debt.yaml` | `candidates.json` | one verified candidate list: malformed scout items are dropped with a reason and counted, and paths are normalised to root-relative forward slashes; every quote is re-found on disk (cited range first, then anywhere, whitespace-insensitive) so the recorded range is the real one, and a finding with no verified evidence becomes an `open_questions` entry with reason `quote not found` instead of a candidate; scout candidates of the same family whose primary evidence sits in the same file within 10 lines cluster into one (union of evidence, maximum severity, minimum effort, title and note from the highest-severity member, the lowest fingerprint keeping the identity); `confirmed_by` collects `scout:<family>` plus every pattern lead, SATD marker and rule finding within 10 lines, `coupling` and `hotspot` from the primary file's signals, and `signal:no-mapped-tests` for `test-gaps`; suppressions match by fingerprint with an optional `until` expiry and path-class disables drop a family the config switches off for that class, both counted in `stats`; every title, note and quote is redacted before writing, and rule findings are appended unchanged after the scout candidates as tier A |
| `verify_prompts.py --workdir .tech-debt [--top N]` | `candidates.json`, `inventory.json`, `coupling.json`, `.tech-debt.yaml` | `verify-plan.json`, `prompts/verify-<nn>.md` | the budget rule of spec 4.8: every candidate with `tier: null` is ranked by provisional priority (the 4.9 formula at tier B, with `H`, `C` and `F` normalised against the candidate pool's own maxima, so a large raw signal such as a `coupling_degree` of 12 cannot outweigh severity in this provisional order), ties broken on fingerprint ascending; the first `max(top_multiple x N, min_candidates)` (3N or 30, whichever is larger) are selected, then every candidate at or above `always_min_severity` (5) and every candidate in `always_families` (`security`) is added, and the selection is truncated to `max_candidates` (72) in that same order; tier A candidates (rules and tool facts) are never sent to a verifier and appear in neither list, and every other unselected candidate is listed under `unverified`; batches of `batch_size` (6) sorted by primary file then fingerprint keep one file's candidates together; each prompt carries the read-only rule and an allowance of three further files the verifier may open and must name in `opened`, then per candidate its fingerprint, title, family, severity, effort, note, `confirmed_by`, the deterministic signals, every cited span read from disk with `context_lines` (30) lines of context either side and 1-based line numbers (the cited lines marked `>`), the change-coupled partners of the primary file from `coupling.pairs`, approximate referrers from the stem graph (`not computed` when the graph raises, so a graph failure never aborts a verification), the family's `verifier_questions` and the `traps` from config whose `family` matches and whose `path_glob` fnmatches the primary file; every line of repository text passes through `redact`, and the prompt shares no text with the scout prompts beyond the read-only rule |
| `evaluate.py --planted <planted.json> --workdir <dir>` | `findings.json` or `verified.json`, `ranked.json` | stdout | per-family precision, recall and decoy hits by tier, and decoys in tier A or the top N, against a fixture's `planted.json` |

`config.py` loads `.tech-debt.yaml` with the spec defaults; `git_history.py`
and `reference_graph.py` hold the git pass and the stem graph that
`inventory.py` uses. Without git, churn is 0, the history fields are null and
`coupling.json` holds empty lists. The v1 command
`inventory.py <repo> --out <path>` still writes only `inventory.json`.

The fixture corpus under `skills/tech-debt-scan/tests/fixtures/corpus/`
(`service-py`, `web-ts`, `mixed-decoys` in Go) keeps each tree in `files/`, its
commit history in `history.yaml` and its planted debt and decoys in
`planted.json`; `tests/helpers/make_history.py` replays a history into a
temporary git repository at test time, so churn, coupling, blame and branches
are exercised without committing a `.git` directory.

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
- The corpus fixtures are replayed into temporary git repositories once per
  test session (`conftest.py` session fixtures); tests that count churn pass an
  explicit window (`churn_months=240` or `1`) because fixture dates are fixed
  while the default 12-month window moves. Corpus scoring is only meaningful at
  that window, so each `planted.json` records it as a top-level `churn_months`
  (240) that `evaluate.py` reads back into its report and prints above the
  table; scored under the moving default, service-py's ownership decoy reaches
  tier A.

## Scope

Phase 1 (human-in-the-loop) only. Phase 2 — autonomously applying fixes without
review — is deferred.
