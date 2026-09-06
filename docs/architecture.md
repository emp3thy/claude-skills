# tech-debt-scan — architecture

This page is the design reference for the `tech-debt-scan` skill. The
canonical v2 spec is
[`docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md`](superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md)
in this repo; this page inlines and keeps current the parts of it a user
needs without reading the spec. Where this page and the scripts disagree,
**the scripts win** — they are the source of truth, and the test suite pins
their behaviour.

## Design principles

- **Language-independent.** The only language-aware code is the inventory's
  extension→language map, which also supplies each language's comment syntax
  to `patterns.py`. Every rule in `inventory.py`, `patterns.py` and `rules.py`
  is a union of idioms across languages; a test greps the scripts for any
  branch on a language name. Scout, verifier and remediation-note prompts are
  all language-neutral.
- **LLM does the judgement, scripts do the determinism.** The model runs each
  dispatched family's scout, verifies a batch of candidates against that
  family's questions and traps, and writes one remediation note per top-N
  finding; `rank.py`'s fixed formula deterministically scores every verified
  finding and picks the top N — no agent chooses or orders the final list.
  File walking, prompt rendering, markdown rendering, parsing, validation, and
  bundle writing are all pure Python with pinned commands and pinned output
  files — no improvisation.
- **Human in the loop.** Nothing is fixed automatically. A single `design.md`
  round-trips through human review: scan writes it, a human edits `status:`
  fields, promote reads it back.
- **Direct-path invocable scripts.** Every script runs as
  `python scripts/<name>.py` from `skills/tech-debt-scan/`. No package install,
  no `-m`, no cross-module package layout (the only intra-`scripts` imports are
  flat top-level imports resolved by the test `conftest.py` and `mypy_path`).
- **Read-only scouts.** Scout agents use Explore semantics; they never write.
- **Redaction at every write.** Every repository-derived string passes through
  `redaction.redact` at the point of writing, in every script. It runs two
  patterns: `CREDENTIAL_RE` for the assignment shape `name = "value"` — which is
  also `patterns.py`'s `security`/`credential` detection rule, so its scope is
  frozen — and `SECRET_TOKEN_RE`, which matches a well-known secret by its
  issuer prefix (Stripe, GitHub, AWS, Slack, Google, GitLab, npm, DigitalOcean,
  a PEM private-key header) wherever it appears, including inside an agent's
  prose restatement of a value it read. Both cut to `value[:4] + "***"`, so a
  reader cannot tell which pattern caught a secret; only `redact` uses the
  second one, so what the scan *finds* is unaffected by it. Where a string is
  also length-capped, `redact` runs **first** and the cap second: every branch
  of `SECRET_TOKEN_RE` is length-gated, so cutting a token in half stops it
  matching its own pattern and every later `redact` misses it too.

## Two-command flow

`/tech-debt-scan <repo>` runs a twelve-step chain (the spec numbers the full
fourteen; steps 4 and 11 — the tool probe and the baseline diff — are
inserted by phases 4 and 5 without renumbering the rest):

1. `inventory.py` writes `inventory.json` and `coupling.json`: churn,
   complexity, hotspots and change coupling.
2. `patterns.py` writes `patterns.json`: regex leads and SATD markers.
3. `rules.py` writes `rule-findings.json`: deterministic tier-A findings.
5. `plan_scan.py` writes `scan-plan.json` and `prompts/scout-<family>.md`,
   applying the adaptive rule over the [family table](#scout-families)
   below: a family is dispatched only when it has at least one lead.
6. One read-only scout Agent per plan entry writes its reply to the path the
   plan names.
7. `merge_findings.py` writes `candidates.json`: one verified, deduplicated
   candidate list.
8. `verify_prompts.py` writes `verify-plan.json` and
   `prompts/verify-<nn>.md`, selecting candidates for verification under a
   provisional-priority budget rule (the `verify_prompts.py` row in the
   table below has the exact selection order and caps).
9. Read-only verifier Agents reply per batch; `apply_verdicts.py` writes
   `verified.json`, earning every candidate a tier from the table in the
   `apply_verdicts.py` row below: A (confirmed and corroborated, or a rule
   or tool fact), B (confirmed without corroboration, or downgraded), C
   (rejected, unverified, or capped by a family rule).
10. `rank.py` writes `ranked.json`, scoring every verified finding with the
    fixed formula `priority = severity x interest x tier_weight x
    tractability` (the `rank.py` row below has every term) and taking the
    top N.
12. `design_writer.py notes-prompt` writes `prompts/notes.md`; one read-only
    remediation-note Agent writes `notes.json`.
13. `design_writer.py render` writes `design.md` and `findings.json`,
    self-checking through `design_parser.py`.
14. Report: the path, the counts from the frontmatter, tools absent, git
    absent, families skipped, and the instruction to set each finding's
    `status:` and run `/tech-debt-promote`.

The user edits `design.md`, flipping each finding's `status:` to `approved`,
`rejected` or `accepted`. `/tech-debt-promote` then:

1. Locates the edited `design.md`.
2. Optionally inspects it with `design_parser.py` (read-only).
3. `promote.py` writes one `chore-<slug>-<date>/` bundle per `approved`
   finding via `bundle_writer.py`, then flips each to `promoted` via
   `design_writer.mark_promoted`.
4. Reports the counts and the bundle location.

All intermediate artefacts default to `.tech-debt/` under the scanned repo (the
directory is gitignored and is itself in the inventory ignore list). Bundles
default to `./tech-debt-pbis`.

## Deterministic signals and the detect-verify-rank chain

The scripts below (landed across v2 phases 1 to 3) are wired into
`/tech-debt-scan` and `/tech-debt-promote` as of phase 3:

| Script | Reads | Writes | What it computes |
| --- | --- | --- | --- |
| `inventory.py <repo> --workdir .tech-debt` | the tree, one `git log` pass, `.tech-debt.yaml` | `inventory.json`, `coupling.json` | path classes (tests, generated, vendored, docs, source) on code files and artefacts alike, artefact classes, per-file churn and authorship (authors keyed by email, bots dropped, joined against HEAD), `hotspot_score` and the `hotspot_band` (top 10 percent of source files, 5 to 50), blame line share on the band, change-coupling pairs (`shared >= 3`, `ratio >= 0.30`, bulk commits over 50 files excluded), approximate fan-in and fan-out by identifier stems over import-like lines with the mechanical ambiguity rule, import-line cycles of size 2 to 5 as leads, directory instability, test mapping across seven naming conventions, the docs and tests blocks, and the size guard that never reads a file over 2 MB or with a NUL byte in its first KB (`skipped_large` per entry, `skipped_large_files` at the top level) |
| `patterns.py <repo> --workdir .tech-debt [--no-blame]` | `inventory.json`, the files | `patterns.json`; fills `files[].inline_disables` | regex leads per family (half-finished stubs and skips and no-timeout calls, error-masking catches with the caught variable and carrier exclusion, dead-code commented-out runs, legacy names, deprecations and flag SDK calls, security credentials with four-character redaction, string SQL, dynamic evaluation, TLS off, weak hashes, permissive CORS and suppressions, test-quality signals, stdout writes where a logger exists) and the SATD table with blame age and ticket flags; artefacts are scoped by their artefact class but every lead and SATD entry on one reports the artefact's real `path_class`, and an artefact classed `generated` or `vendored`, or marked `skipped_large`, is not scanned |
| `rules.py <repo> --workdir .tech-debt` | `inventory.json`, the artefacts | `rule-findings.json` | tier-A findings for CI jobs, Dockerfiles and compose images, Kubernetes manifests, manifests without lockfiles, release cadence and stale environment branches, and ownership (knowledge islands, inactive top authors, CODEOWNERS coverage); an island also needs `churn >= island_min_churn` (2) in the window; a CODEOWNERS the inventory skipped or that sits under a disabled tree is not consulted; migration leads for `setup.py` beside `pyproject.toml` and `tslint` beside `eslint`; an artefact under a tests, vendored or generated tree is skipped, an artefact the inventory marked `skipped_large` is never read, and every finding carries the artefact's `path_class` in `signals` |
| `plan_scan.py --workdir .tech-debt [--families <set>] [--top N]` | `inventory.json`, `coupling.json`, `patterns.json`, `rule-findings.json` | `scan-plan.json`, `prompts/scout-<family>.md`, an empty `scouts/` for phase 3's replies | the adaptive rule (a family runs only when it has at least one lead after path-class disables; an inventory lead counts only above the family's own floor, since `max_indent >= 1` and `loc >= 1` are true of every non-empty file — complex-units needs `longest_indented_run` or `deep_indent_lines` above zero, god-classes `loc >= 300` or `fan_in_approx >= 3`), the 40-lead cap applied independently to the pattern, SATD and inventory leads, band files first within each capped kind (the hotspot band, the coupled pairs, the artefacts, the cycles and the docs and tests signals are the remaining kinds and are emitted in full, the band already bounded by `hotspot_band.max`), the fourteen family blocks; `--families` takes `default`, `quick`, `deep`, a comma-separated list or a single family name (a list of one); a missing or corrupt signal file exits 2 with an `error:` line; `chunked` is always false until phase 4 |
| `merge_findings.py --workdir .tech-debt` | `scan-plan.json`, the `scouts/<family>.json` it names, `rule-findings.json`, `inventory.json`, `patterns.json`, `.tech-debt.yaml` | `candidates.json` | one verified candidate list: a scout file missing from disk is counted under `missing_file` and one that is unreadable or not valid JSON is counted under `read_failed`, and neither aborts the merge — every other family's scout file is still read; malformed scout items are dropped with a reason and counted, and paths are normalised to root-relative forward slashes; every quote is re-found on disk (cited range first, then anywhere, whitespace-insensitive) so the recorded range is the real one, and a finding with no verified evidence becomes an `open_questions` entry with reason `quote not found` instead of a candidate; scout candidates of the same family whose primary evidence sits in the same file within 10 lines cluster into one (union of evidence, maximum severity, minimum effort, title and note from the highest-severity member, the lowest fingerprint keeping the identity); `confirmed_by` collects `scout:<family>` plus every pattern lead of the candidate's own family and every SATD marker and rule finding, each within 10 lines, `coupling` and `hotspot` from the primary file's signals, and `signal:no-mapped-tests` for `test-gaps`; suppressions match by fingerprint with an optional `until` expiry and path-class disables drop a family the config switches off for that class, both counted in `stats`; every title, note and quote is redacted before writing — the title and note at validation, before their 80- and 300-character caps are applied, so a cut never breaks a token out of the redactor's reach, and each quote after it has been matched on disk, which a redacted quote could not be — and rule findings are appended unchanged after the scout candidates as tier A |
| `verify_prompts.py --workdir .tech-debt [--top N]` | `candidates.json`, `inventory.json`, `coupling.json`, `.tech-debt.yaml` | `verify-plan.json`, `prompts/verify-<nn>.md`, an empty `verdicts/` for phase 3's replies | the budget rule of spec 4.8: every candidate with `tier: null` is ranked by provisional priority (the 4.9 formula at tier B, with `H`, `C` and `F` normalised against the candidate pool's own maxima, so a large raw signal such as a `coupling_degree` of 12 cannot outweigh severity in this provisional order), ties broken on fingerprint ascending; the first `max(top_multiple x N, min_candidates)` (3N or 30, whichever is larger) are selected, then every candidate at or above `always_min_severity` (5) and every candidate in `always_families` (`security`) is added, and the selection is truncated to `max_candidates` (72) in that same order; tier A candidates (rules and tool facts) are never sent to a verifier and appear in neither list, and every other unselected candidate is listed under `unverified`; batches of `batch_size` (6) sorted by primary file then fingerprint keep one file's candidates together; each prompt carries the read-only rule and an allowance of three further files the verifier may open and must name in `opened`, then per candidate its fingerprint, title, family, severity, effort, note, `confirmed_by`, the deterministic signals, every cited span read from disk with `context_lines` (30) lines of context either side and 1-based line numbers (the cited lines marked `>`), the change-coupled partners of the primary file from `coupling.pairs`, approximate referrers from the stem graph, built once per plan and passed to every prompt (`not computed` when the graph raises, so a graph failure never aborts a verification), the family's `verifier_questions`, the family block's own traps (the same list the scout prompt carries, under `known non-debt shapes for this family`) and then the `traps` from config whose `family` matches and whose `path_glob` fnmatches the primary file; every line of repository text passes through `redact`, and the prompt shares no text with the scout prompts beyond the read-only rule and that family trap list, restated on purpose so the verifier can match a known non-debt shape |
| `apply_verdicts.py --workdir .tech-debt` | `candidates.json`, `verify-plan.json`, the `verdicts/verify-<nn>.json` files `verify-plan.json`'s batches name | `verified.json` | the tier table of spec 4.8: a candidate already `tier: "A"` (rule findings, tool facts) stays A with no verifier; `confirm` with every cited quote `quote_verified` and at least one `confirmed_by` entry beyond the scout's own `scout:<family>` (a `pattern:`, `rule:`, `tool:`, `signal:` prefix, `satd`, `coupling`, `hotspot`, or a second `scout:` family counts as corroboration) earns A, otherwise B; `downgrade` or `refer` earns C; `reject` keeps `tier: null` with `verified: true` and the verdict's `proof` for the report's considered-and-rejected section; a candidate that was never selected, or was selected but no batch returned a verdict for it, is C with `verdict: "unverified"` and `verified: false`; the 2.3 family caps then weaken a confirmed tier (never strengthen it) — duplication and architecture (unless `tool:` or `coupling`), god-classes TD-20 (unless `coupling`), test-gaps (unless `signal:no-mapped-tests`), test-quality (severity also capped at 3), dependency-debt, security and migration (unless `coupling`) cap at B; dead-code caps at C unless churn and fan-in are both 0 and `path_class` is `source` (then B) or a `tool:` is present (then no cap); doc-drift and pipeline-infra scout candidates cap at B unconditionally; every other family is uncapped; where a verdict exists its `severity` (1-5) and validated `effort` replace the scout's, and its `checked`, `opened`, `proof` and `trap_matched` are copied onto the finding; a verdict whose `fingerprint` matches no candidate is counted `unknown_fingerprint` and ignored, and a batch whose output file is missing on disk prints a warning and leaves its candidates `unverified` rather than failing the run; exits 2 (with an `error:` line to stderr) when `candidates.json` or `verify-plan.json` is missing or unreadable/malformed |
| `rank.py --workdir .tech-debt [--preset balanced\|hotspot-first\|architecture\|quick-wins] [--top N]` | `verified.json`, `inventory.json`, `.tech-debt.yaml` | `ranked.json` | spec 4.9's priority formula: `priority = severity x interest x tier_weight x tractability`, `interest = 1 + wH*H + wC*C + wF*F` with `H`, `C` and `F` the finding's `hotspot_score`, `coupling_degree` and (`0` when the primary file's `fan_in_mode` is `anywhere`) `fan_in_approx`, each normalised against `repo_maxima(inventory)`; `tier_weight` is A 1.0, B 0.7, C 0.35; `tractability` is S 1.0, M 0.75, L 0.5 (`quick-wins`: 1.0, 0.5, 0.2); the four presets (`balanced`, `hotspot-first`, `architecture`, `quick-wins`) fix their own weights and tractability by name, `--preset` overrides `ranking.preset`, and only `balanced` reads `ranking.weights`/`ranking.tractability` from config; only tier A and B findings are eligible for the top N, and under `quick-wins` a duplication finding without `tool:` or `coupling` corroboration and every ownership finding are excluded from it too (still emitted with `in_top_n: false`); findings are walked in priority-descending, fingerprint-ascending order (the tie-break) filling the top N while each family holds fewer than `ceil(spread_cap x N)` (spread_cap 0.5) chosen entries, a finding a family cap displaces is marked `spread_capped: true` and keeps its priority-ordered `rank` (numbered over every finding, top or not); `formula_version` (1), every term, the preset name, weights and tractability are recorded on the document so any priority can be recomputed; the output is byte-identical across runs on identical inputs; exits 2 (with an `error:` line to stderr) when `verified.json` or `inventory.json` is missing, unreadable, malformed, of the wrong top-level shape, or `--preset` names an unknown preset |
| `design_writer.py render --workdir .tech-debt --scan-date <date> [--out <path>]` | `ranked.json`, `verified.json`, `candidates.json`, `scan-plan.json`, `inventory.json`, `coupling.json`, and `notes.json` and `diff.json` when present | `design.md`, `findings.json` | spec 4.11's review document: literal-YAML frontmatter (`schema_version`, `scan_date`, `root`, `total_files`, `total_loc`, `languages`, `preset`, `families_run`, `families_skipped`, `tools_run`, `tools_absent`, `git_available`, `counts`), an empty list rendered as `key: []` on one line so it never reads back as `None`; the header with the review instructions and, only when `git_available`, the top five hotspots and coupled pairs (a `No git history` line instead); then the seven body sections in order — `# Top N` with one H2 per top-N finding, `# Below the cut`, `# Below the cut: tier C and unverified`, `# Considered and rejected`, `# Looks bad but is fine`, `# Open questions for the maintainer` and `# Not assessed`. A finding is an H2 whose fenced `yaml` anchor carries `status`, `slug`, `fingerprint`, `tier`, `priority`, `family`, `category` (always the alias of `family`), `debt_type`, `type_id`, `severity`, `effort` and `diff`, followed by `### Proof`, `### Evidence` (one `` `file:start-end` `` line per item then its quote in an unlabelled fenced block), `### Signals` and, for a top-N finding, `### Remediation` and `### Acceptance criteria` (`remediation note not available` when the note agent has no entry). Slugs come from `slugs.unique_slugs` over the ranked order, so a finding's slug does not move when another is added below it; every title, proof and quote passes through `redact` at the point of writing; without `diff.json` every finding renders `diff: NEW` and the `new` and `resolved` counts are omitted; the output is LF-only and re-parsed through `design_parser.parse_design` as a write-time self-check |
| `design_writer.py notes-prompt --workdir .tech-debt [--top N]` | the same six documents `render` requires (via `load_inputs`) | `prompts/notes.md` | spec 4.11's Task 5: one prompt for the single remediation-note agent, over the top N only, in `ranked.json`'s `top_n` priority order — a role sentence naming the repository root, the read-only rule, then per top-N finding `## <n>. <title>` with `fingerprint`, `family`, `severity`, `effort`, the free-text proof and each evidence item as `` `file:start-end` `` followed by its quote in a fenced block (the same fencing `render` uses), then `NOTES_CONTRACT` verbatim (the `notes.json` reply shape: `fingerprint`, a `remediation` of at most 120 words with no code, and two to five checkable `acceptance_criteria`); every title, proof and quote is redacted. `--top` narrows the prompt below `ranked.json`'s own top N and never widens it. The agent's reply, stored as `notes.json`, is read back by `render` — via `notes_by_fingerprint`, which keeps only an entry whose fingerprint is in `top_n`, whose `remediation` is a non-empty string and whose `acceptance_criteria` is a list of strings, dropping anything else silently — into each top-N finding's `### Remediation` and `### Acceptance criteria` sections; a missing or malformed `notes.json` renders `NOTE_PLACEHOLDER` in both instead of failing |
| `evaluate.py --planted <planted.json> [--workdir <dir>] [--top N] [--json]` | `findings.json` (preferred) or `verified.json`, and `ranked.json` when present | stdout: the table, or the JSON report with `--json` | per-family precision, recall and decoy hits by tier, tier A precision, and decoys in tier A or the top N, against a fixture's `planted.json` |
| `live_run.py <fixture-or-repo> [--workdir <dir>] [--families <set>] [--top N] [--preset <name>] [--churn-months N] [--model <alias>] [--max-budget-usd <n>] [--claude <path>] [--timeout <seconds>] [--log <path>] [--skip-agents]` | a corpus fixture (replayed) or a repository, then each stage's own inputs | every file the chain writes plus `evaluation.json`, and one row appended to `docs/evaluation-log.md` | the whole chain with real agents: the signal scripts, `plan_scan.py`, one `claude -p` call per scout prompt, `merge_findings.py`, `verify_prompts.py`, one call per verifier batch, `apply_verdicts.py`, `rank.py` and, when a `planted.json` is present, `evaluate.py`; manual only, never CI — the [Live harness](#live-harness) section below has the argv, the retry rule and the exit codes |

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

### Live harness

`live_run.py <fixture-or-repo>` drives the whole chain with real agents. It is
manual only and never runs in CI. Given a corpus fixture name it replays the
fixture through `tests/helpers/make_history.py` into a temporary directory
(any other argument is taken as a repository path), then runs the deterministic
signals, `plan_scan.py`, one `claude -p` call per scout prompt,
`merge_findings.py`, `verify_prompts.py`, one call per verifier batch,
`apply_verdicts.py` and `rank.py`; when a `planted.json` is present it scores
the run with `evaluate.py`, prints the table and appends one row to
`docs/evaluation-log.md`: date, fixture, model, `churn_months`,
`tier_a_precision`, `reported_precision`, `decoys_tier_a`, `decoys_top_n`,
per-family `recall`, `scouts`, `verifiers` and `cost_usd`. `tier_a_precision`
comes from the report's `tier_a` block and counts tier A findings alone, which
is the release bar; `reported_precision` is the per-family figure, which spans
tiers A and B. The history window is the fixture's `planted.json`
`churn_months` when present; a conflicting `--churn-months` is ignored, with a
warning printed to stderr, so the logged `churn_months` always matches the
window the run actually scored against. Without a planted value,
`--churn-months` sets the window, else the config default.

Every agent call is a list argv (never a shell string) in print mode:
`--setting-sources project --strict-mcp-config --disable-slash-commands` keep
the user's settings, MCP servers and slash commands out of the run,
`--output-format json --json-schema <the contract>` pins the reply shape to
`SCOUT_OUTPUT_SCHEMA` or `VERDICT_SCHEMA`, `--tools Read,Grep,Glob
--allowedTools Read,Grep,Glob` keep the agent read-only, `--max-budget-usd`
caps each call and `cwd` is the repository so the read tools see the tree. The
prompt itself is piped to the child's stdin and is never an argument:
`claude -p` with no positional argument reads a piped stdin as the prompt,
Windows caps a `CreateProcess` command line at 32,767 characters, and
`list2cmdline`'s quote and backslash escaping pushes a quote-heavy verifier
prompt past that ceiling. Nothing is trimmed, so the last candidates and the
verdict contract always reach the agent. The reply is the envelope's
`structured_output` when it carries one and otherwise
`result` with Markdown fences stripped; a payload that fails the contract is
retried once with an appended re-emit instruction, and a second failure ends
the run. `--skip-agents` reuses the scout and verdict files already in the
workdir instead of calling out. Flags: `--workdir`, `--families`, `--top`,
`--preset`, `--churn-months`, `--model`, `--max-budget-usd`, `--claude`,
`--timeout`, `--log`, `--skip-agents`; exit 2 on a bad target or malformed
input, 3 when `claude` is not on PATH (and `--skip-agents` is absent), 4 when
an agent call fails after its retry or `--skip-agents` finds no cached reply.

## Scout families

`scripts/categories.py` defines fourteen language-agnostic debt families
(`FAMILIES`, one `FamilyBlock` per name in `FAMILY_BLOCKS`). `plan_scan.py`
dispatches one scout Agent per family that its adaptive rule finds at least
one lead for:

| Family | Looks for |
| --- | --- |
| `complex-units` | Single functions, methods or blocks whose branching and nesting make them hard to change safely |
| `god-classes` | A type, module or file with too many reasons to change, inappropriate intimacy, or long message chains |
| `duplication` | The same logic in two or more places that change together |
| `dead-code` | Units with no callers, unreachable branches, leftover commented-out code, and flags stuck at one value |
| `error-masking` | Failures caught and hidden — empty or catch-all catches, disabled assertions |
| `test-gaps` | Behaviour that changes often with no automated test guarding it |
| `half-finished` | Self-admitted debt markers, stubs, skip markers, calls with no timeout |
| `migration` | Two ways of doing one thing coexisting; an old idiom still called after its replacement landed |
| `dependency-debt` | Structural dependency problems: missing lockfiles, duplicate-purpose packages, floating ranges, stale vendoring |
| `doc-drift` | Documentation that contradicts the code it describes |
| `architecture` | Dependency cycles, misplaced code, directories whose stability contradicts what depends on them |
| `security` | Pattern-level security debt: credential-shaped literals, string-built SQL, dynamic eval, disabled TLS, weak hashes, wildcard CORS |
| `test-quality` | Tests that sleep, read the wall clock, use unseeded randomness, assert nothing, or hide flakiness |
| `pipeline-infra` | Duplicated pipeline YAML, manual release steps, dev-only container paths in production use, stdout instead of logging |

Each `FamilyBlock` carries its own definition, scout `questions`, known-non-debt
`traps`, allowed `type_ids` and `debt_types`, and a shorter set of
`verifier_questions` a verifier Agent sees for that family's candidates.
`plan_scan.py` renders the scout prompt from a block; `verify_prompts.py`
renders the verifier prompt from the same block plus any matching config
`traps`. A scout's reply is one JSON object of `findings`, `open_questions`,
`looks_bad_but_fine` and `not_assessed` (`SCOUT_OUTPUT_SCHEMA`); each finding
carries `title`, `family`, `debt_type`, `type_id`, `severity`, `effort`,
`signals_cited`, `evidence` (verbatim quotes) and `note` — never a
`suggested_fix` or a `confidence` self-report.

**The v1 categories are gone.** The eight v1 categories (`god-modules`,
`duplication`, `dead-code`, `test-gaps`, `doc-drift`, `half-finished`,
`dependency-debt`, `architecture`) and the symbols that defined them —
`CATEGORY_PROMPTS`, `CATEGORIES`, `CORE_CATEGORIES`, `get_prompt` and their
shared `_OUTPUT_SCHEMA` — were deleted from `categories.py` in phase 3 (spec
3.2), together with their only consumers, `build_synthesis_prompt.py` and
SKILL.md v1. A v1 `design.md` still promotes unchanged: its `category` value
(for example `god-modules`) is a string `design_parser` reads as `family`, and
no v1 path ever read a scout prompt.

## design.md format

`design_writer.py render` writes a single markdown document (spec 4.11): a
hand-rendered YAML frontmatter block (`schema_version`, `scan_date`, `root`,
`total_files`, `total_loc`, `languages`, `preset`, `families_run`,
`families_skipped`, `tools_run`, `tools_absent`, `git_available`, `counts`,
plus `new`/`resolved` once a baseline exists), a header naming the top
hotspots and coupled pairs, then seven body sections in order: `# Top N`,
`# Below the cut`, `# Below the cut: tier C and unverified`,
`# Considered and rejected`, `# Looks bad but is fine`,
`# Open questions for the maintainer`, `# Not assessed`.

A finding is an `## ` section whose fenced `yaml` anchor carries `status`,
`slug`, `fingerprint`, `tier`, `priority`, `family`, `category` (always the
`family` alias, so v1 tooling and a human skimming still see a `category`
key), `debt_type`, `type_id`, `severity`, `effort` and `diff`. Every other
section is an `# ` heading, which ends the preceding finding's body so a
negative-space section (rejections, open questions, and the rest) is never
copied into a PBI. A top-N finding's body also carries `### Remediation` and
`### Acceptance criteria` from the remediation-note agent; a below-the-cut
tier A/B finding outside the top N carries `### Proof` and `### Evidence`
only, so it is still promotable without a note; `# Below the cut: tier C and
unverified` is a compact table instead of full sections, one row per tier C
or unverified finding.

The renderer re-parses its own output via `design_parser.parse_design` as a
self-check before exiting; a round-trip failure exits non-zero. The same call
also writes `findings.json` beside `design.md`: the same findings as
machine-readable JSON, preferred by `evaluate.py` over `verified.json`.

`design.md` is written LF-only (`write_bytes`) so it byte-matches across
platforms regardless of `core.autocrlf`.

## Validation rules

Shared validators live in `scripts/validation.py`:

- **Status** (`validate_status`): one of `pending`, `approved`, `rejected`,
  `accepted`, `promoted`.
- **Slug** (`validate_slug`): matches `^[a-z][a-z0-9-]{0,63}$` (starts with a
  lowercase letter, 1–64 chars total) and must not end with a hyphen.
- **Debt type** (`validate_debt_type`): one of `code`, `design`, `architecture`,
  `test`, `documentation`, `dependency`, `build`, `requirement`, `security`,
  `infrastructure`, `knowledge-process`, `defect`.
- **Effort** (`validate_effort`): `S`, `M` or `L`.
- **Type id** (`validate_type_id`): `TD-01` to `TD-35`; checked only when present.
- **Tier** (`validate_tier`): `A`, `B` or `C`.

Every one raises `ValidationError` (a `ValueError`) naming the offending value.
A v1 anchor's `confidence` value is still an accepted optional key — the
parser keeps it so a hand-edited v1 `design.md` does not fail to parse — but
it is never validated or rendered; `validate_confidence` was removed with the
v1 top-N picker it existed for (spec 8).

## Promotion

`promote.py <design.md> --out <dir> [--force]`:

1. `design_parser.parse_design` parses the (human-edited) `design.md`.
2. For each finding with `status: approved`, `bundle_writer.write_bundle` writes
   a `chore-<slug>-<date>/` directory containing `PBI.md`, `PLAN.md`, and
   `HISTORY.md`. Severity maps to a word: 5 → `critical`, 4 → `high`, 3 →
   `normal`, 2/1 → `low`. `PBI.md`'s frontmatter carries `PBI_OPTIONAL_KEYS`
   (`fingerprint`, `tier`, `type_id`, `family`, `debt_type`, `effort`) after
   `category` when a v2 finding's anchor has them; a v1 finding has none of
   these, so its bundle's key order — and bytes — never move (spec 8).
   `priority` is a scan-time rank artifact, never a PBI key. `PLAN.md`'s steps
   are `bundle_writer.acceptance_criteria(body_md)` — the checklist under the
   finding's own `### Acceptance criteria` section, numbered in order — or the
   one-step stub pointing back at `PBI.md` when that section is absent or
   holds the writer's placeholder text rather than a list.
3. `design_writer.mark_promoted` flips each emitted finding's status from
   `approved` to `promoted` in place (atomic `os.replace` via a `.tmp` file,
   `.bak` of the prior content), so a re-run is a no-op.

**Collision policy.** An existing bundle directory is treated as
already-promoted (counted, not re-emitted) unless `--force` is given.

**Exit codes.** `0` success; `2` on a parse / mark-promoted error; `4` on a
bundle-write failure *after* at least one bundle was written (roll-forward — the
succeeded bundles persist and their findings are still marked promoted); `6`
(`promote.EXIT_WRITE_BACK`) is reserved for phase 5's baseline write-back — no
code path returns it yet.

## CI and testing

- `scripts/skill_check.py` lints SKILL.md: it extracts every
  `python scripts/<name>.py` command, runs each script's `--help` (subcommand-
  aware), and asserts every `--flag` used in the documented command appears in
  the help. It runs in CI before pytest.
- Tests never call a live Agent. Scout and verifier dispatch are exercised by
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

Human in the loop throughout: nothing is fixed automatically. The v2 delivery
phases run from phase 1 (deterministic signals) to phase 5 (baseline and
evaluation). Phases 1 to 3 have landed: `/tech-debt-scan` and
`/tech-debt-promote` run the full detect-verify-rank chain end to end, without
external tool signals or a baseline diff. `--families deep` already selects
the full fourteen-family set today (`plan_scan.py`, phase 2). Phase 4 adds
the tool probe, tier caps lifted by tool presence and module chunking; phase 5
adds the baseline, its `diff` reporting, and promote write-back. Autonomously
applying fixes without review is a separate follow-on, deferred and out of
scope.
