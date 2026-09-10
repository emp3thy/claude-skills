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
  to `patterns.py`, and `tools_probe.py`'s tool registry, whose rows are
  inherently tool-specific (ruff and vulture are Python-only; madge, jscpd and
  knip are JS/TS-only; hadolint reads Dockerfiles; actionlint reads GitHub
  Actions workflows). Every rule in `inventory.py`, `patterns.py` and
  `rules.py` is a union of idioms across languages; a test greps every other
  script for a branch on a language name (`tools_probe.py` is the one
  exception the spec allows). Scout, verifier and remediation-note prompts are
  all language-neutral.
- **LLM does the judgement, scripts do the determinism.** The model runs each
  dispatched family's scout, verifies a batch of candidates against that
  family's questions and traps, and writes one remediation note per top-N
  finding; `rank.py`'s fixed formula deterministically scores every verified
  finding and picks the top N — no agent chooses or orders the final list.
  File walking, prompt rendering, markdown rendering, parsing, validation, and
  evidence-document rendering are all pure Python with pinned commands and
  pinned output files — no improvisation.
- **Human in the loop.** Nothing is fixed automatically. A single `design.md`
  round-trips through human review: scan writes it, a human edits `status:`
  fields, promote reads it back and hands one finding to a design session.
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

`/tech-debt-scan <repo>` runs the full fourteen-step chain (step 4, the tool
probe, landed in phase 4b; step 11, the baseline diff, lands in phase 5a):

1. `inventory.py` writes `inventory.json` and `coupling.json`: churn,
   complexity, hotspots and change coupling.
2. `patterns.py` writes `patterns.json`: regex leads and SATD markers.
3. `rules.py` writes `rule-findings.json`: deterministic tier-A findings.
4. A network notice, then `tools_probe.py` writes `tool-signals.json`. The
   notice states what osv-scanner sends to OSV.dev (package names, versions,
   ecosystems and file hashes), that every other first-cut tool is
   local-only, and how `tools.network: false` keeps the scan offline (see
   [External tool probe](#external-tool-probe)). `--no-tools` runs this step
   with `--skip-all`, and the file is still written with every tool
   `skipped`.
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
   `apply_verdicts.py` row below: A (confirmed and corroborated, **or** a
   `rules.py` finding **or** an osv-scanner advisory, the only two kinds of
   candidate allowed to reach tier A without a verifier having read them —
   read [What tier A means for a reader](#what-tier-a-means-for-a-reader) before
   trusting one), B (confirmed without corroboration, or downgraded), C
   (rejected, unverified, or capped by a family rule).
10. `rank.py` writes `ranked.json`, scoring every verified finding with the
    fixed formula `priority = severity x interest x tier_weight x
    tractability` (the `rank.py` row below has every term) and taking the
    top N.
11. `baseline.py diff` writes `diff.json`: every current finding is
    classified against the committed baseline (`NEW`, `UNCHANGED`,
    `UNCHANGED (moved)`, `UNCHANGED (edited)` or `RESOLVED` — see
    [The baseline](#the-baseline) below), and every baseline entry no
    current finding matched is checked on disk for `RESOLVED`. An absent
    baseline marks every finding `NEW`.
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
2. `promote.py --list-approved` prints the `approved` findings as JSON
   (read-only), most severe first, so the user can pick one.
3. `promote.py --select <slug>` renders `evidence.md` beside `design.md` for
   that single finding — `evidence_doc.render_evidence` copies the finding's
   own `body_md` verbatim and appends any matching `### Open questions from
   the scan` and `### Already ruled out` sections from the scan's negative
   space — then flips it to `promoted` via `design_writer.mark_promoted`.
   `--select` accepts a slug that is `approved` or already `promoted`, so a
   re-run re-renders rather than failing.
4. With `--baseline <path>`, `baseline.py record` is called in process to
   write every finding's decision — including `rejected` and `accepted`,
   with their `reason` and `until` — back into the baseline, and to write a
   `pending` entry for every verified finding that carried no decision (a
   suppressed finding has none, by design), refresh an entry it sees again
   against this scan, and migrate an entry whose code was edited onto the
   finding's new fingerprint with its decision intact, then
   `ensure_gitignore_triple` tracks the baseline the
   first time git reports it ignored (see [The baseline](#the-baseline)
   below).
5. The skill reads `evidence.md` and hands it to `superpowers:brainstorming`,
   which always ends by invoking `superpowers:writing-plans` — a tech-debt
   finding must leave a plan behind. Promote does not execute, queue or
   commit that plan.

All intermediate artefacts default to `.tech-debt/` under the scanned repo (the
directory is gitignored and is itself in the inventory ignore list).
`evidence.md` is written beside `design.md`, overwriting any previous evidence
document — it seeds one design session and is always re-derivable.

## Deterministic signals and the detect-verify-rank chain

The scripts below (landed across v2 phases 1 to 3) are wired into
`/tech-debt-scan` and `/tech-debt-promote` as of phase 3:

| Script | Reads | Writes | What it computes |
| --- | --- | --- | --- |
| `inventory.py <repo> --workdir .tech-debt` | the tree, one `git log` pass, `.tech-debt.yaml` | `inventory.json`, `coupling.json` | path classes (tests, generated, vendored, docs, source) on code files and artefacts alike, artefact classes, per-file churn and authorship (authors keyed by email, bots dropped, joined against HEAD), `hotspot_score` and the `hotspot_band` (top 10 percent of source files, 5 to 50), blame line share on the band, change-coupling pairs (`shared >= 3`, `ratio >= 0.30`, bulk commits over 50 files excluded), approximate fan-in and fan-out by identifier stems over import-like lines with the mechanical ambiguity rule, import-line cycles of size 2 to 5 as leads, directory instability, test mapping across seven naming conventions, the docs and tests blocks, and the size guard that never reads a file over 2 MB or with a NUL byte in its first KB (`skipped_large` per entry, `skipped_large_files` at the top level) |
| `patterns.py <repo> --workdir .tech-debt [--no-blame]` | `inventory.json`, the files | `patterns.json`; fills `files[].inline_disables` | regex leads per family (half-finished stubs and skips and no-timeout calls, error-masking catches with the caught variable and carrier exclusion, dead-code commented-out runs, legacy names, deprecations and flag SDK calls, security credentials with four-character redaction, string SQL, dynamic evaluation, TLS off, weak hashes, permissive CORS and suppressions, test-quality signals, stdout writes where a logger exists) and the SATD table with blame age and ticket flags; artefacts are scoped by their artefact class but every lead and SATD entry on one reports the artefact's real `path_class`, and an artefact classed `generated` or `vendored`, or marked `skipped_large`, is not scanned |
| `rules.py <repo> --workdir .tech-debt` | `inventory.json`, the artefacts | `rule-findings.json` | tier-A findings for CI jobs, Dockerfiles and compose images, Kubernetes manifests, manifests without lockfiles, release cadence and stale environment branches, and ownership (knowledge islands, inactive top authors, CODEOWNERS coverage); an island also needs `churn >= island_min_churn` (2) in the window; a CODEOWNERS the inventory skipped or that sits under a disabled tree is not consulted; migration leads for `setup.py` beside `pyproject.toml` and `tslint` beside `eslint`; an artefact under a tests, vendored or generated tree is skipped, an artefact the inventory marked `skipped_large` is never read, and every finding carries the artefact's `path_class` in `signals` |
| `plan_scan.py --workdir .tech-debt [--families <set>] [--top N]` | `inventory.json`, `coupling.json`, `patterns.json`, `rule-findings.json`, `tool-signals.json` (absent means no tool leads) | `scan-plan.json`, `prompts/scout-<family>.md`, an empty `scouts/` for phase 3's replies | the adaptive rule (a family runs only when it has at least one lead after path-class disables; an inventory lead counts only above the family's own floor, since `max_indent >= 1` and `loc >= 1` are true of every non-empty file — complex-units needs `longest_indented_run` or `deep_indent_lines` above zero, god-classes `loc >= 300` or `fan_in_approx >= 3`), the 40-lead cap applied independently to the pattern, SATD and inventory leads, band files first within each capped kind (the hotspot band, the coupled pairs, the artefacts, the cycles and the docs and tests signals are the remaining kinds and are emitted in full, the band already bounded by `hotspot_band.max`), the fourteen family blocks; `--families` takes `default`, `quick`, `deep`, a comma-separated list or a single family name (a list of one); a missing or corrupt signal file exits 2 with an `error:` line; inference-class tool signals (ruff, vulture, lizard, jscpd, knip, madge) add a capped `tool` lead kind per family, the same `LEAD_CAP` as the pattern and SATD kinds (phase 4b); `chunked` is true once source files exceed `chunking.max_files` or source LOC exceeds `chunking.max_loc` (both halved when the selected set is `deep`), splitting dispatch into per-directory module scouts with each family's lead cap applied per module rather than once repository-wide; `chunking.max_modules` (8, never halved) bounds that split, since entries are `families x modules` and one agent is dispatched per entry — over the limit, modules are ranked by hotspot-band files, then lead count, then plan order, and the survivors are recorded in `modules` with the cut ones and their lead counts in `modules_dropped`, while a family left with no scanned module moves from `families_run` to `families_skipped` with reason `no leads in the scanned modules` (phase 4b); each module's display name (`entries[].module` and the prompt's "top-level directory '<name>' only" phrase) is `_module_display`'s: a real top-level directory keeps its own name, and the repository-root sentinel (a true root-level file, distinct from a real directory that happens to be named `root`) displays as `"root"`, or as `"/"` — a label no directory can equal, since a path segment cannot be `/` — on the rare repository that also has a real top-level directory literally named `root` |
| `merge_findings.py --workdir .tech-debt` | `scan-plan.json`, the `scouts/<family>.json` it names, `rule-findings.json`, `tool-signals.json` (absent means no tool candidates), `inventory.json`, `patterns.json`, `.tech-debt.yaml` | `candidates.json` | one verified candidate list: a scout file missing from disk is counted under `missing_file` and one that is unreadable or not valid JSON is counted under `read_failed`, and neither aborts the merge — every other family's scout file is still read; malformed scout items are dropped with a reason and counted, and paths are normalised to root-relative forward slashes; every quote is re-found on disk (cited range first, then anywhere, whitespace-insensitive) so the recorded range is the real one, and a finding with no verified evidence becomes an `open_questions` entry with reason `quote not found` instead of a candidate; scout candidates of the same family whose primary evidence sits in the same file within 10 lines cluster into one (union of evidence, maximum severity, minimum effort, title and note from the highest-severity member, the lowest fingerprint keeping the identity); `confirmed_by` collects `scout:<family>` plus every pattern lead of the candidate's own family and every SATD marker and rule finding, each within 10 lines, `coupling` and `hotspot` from the primary file's signals, and `signal:no-mapped-tests` for `test-gaps`; suppressions match by fingerprint with an optional `until` expiry and path-class disables drop a family the config switches off for that class, both counted in `stats`; every title, note and quote is redacted before writing — the title and note at validation, before their 80- and 300-character caps are applied, so a cut never breaks a token out of the redactor's reach, and each quote after it has been matched on disk, which a redacted quote could not be — and rule findings are appended unchanged after the scout candidates as tier A; inference-class tool signals corroborate rather than raise: `tool:<name>` joins a same-family candidate that cites the signal's file in any evidence item, unless that file's path class disables the family — the same `families.per_path_class` check `plan_scan._filtered_sorted_leads` applies to the lead built from the same signal, so the two ends of one signal cannot disagree about whether the user's config covers it; fact-class tool signals (phase 4b, spec 4.5, 4.7) route three ways — an osv-scanner advisory enters as its own tier A candidate exactly like a rule finding (a null line range at manifest or lockfile level, since osv's JSON carries no line numbers); a gitleaks secret enters untiered, because a placeholder or fixture value needs a verifier's judgement, not a fact; a hadolint or actionlint fact merges into a same-file rule finding's `confirmed_by` when one exists and otherwise enters untiered on its own — the merge is tried before the untiered route's line-range guard, not after, since it reads no range at all (only the file the fact and the rule finding agree on), so a fact with no usable range still corroborates a rule finding it covers and only a fact that raises its own candidate is dropped for lacking one — and `rules.py` findings plus these osv facts are the *only* two producers of a non-null tier at merge time (`TestTierProducerInvariant`, spec 4.7's invariant), so every other candidate, tool-raised or not, still reaches a verifier before it can be trusted; every candidate also carries `tool`, right after `rule_id` — the tool name for a tool candidate, `null` for a scout or rule candidate — recording the producer for `evaluate.py`'s decoy-sources check without inspecting `confirmed_by`; a fact-class candidate's evidence also carries `column` (gitleaks' `StartColumn`, folded into the fingerprint span by `_fingerprint_span` so two different secrets matched by the same rule on the same line stay two candidates instead of collapsing onto one; `null` for every other tool and for a gitleaks record with no column); the column joined the fingerprint in phase 5b, so on the first scan after upgrading, gitleaks entries with a usable column read `UNCHANGED (edited)` rather than `UNCHANGED`, while those without a usable column retain their pre-upgrade fingerprints and still read `UNCHANGED` (suppressions still carry across, since the tool's message is the title and the edited heuristic matches it) |
| `verify_prompts.py --workdir .tech-debt [--top N]` | `candidates.json`, `inventory.json`, `coupling.json`, `.tech-debt.yaml` | `verify-plan.json`, `prompts/verify-<nn>.md`, an empty `verdicts/` for phase 3's replies | the budget rule of spec 4.8: every candidate with `tier: null` is ranked by provisional priority (the 4.9 formula at tier B, with `H`, `C` and `F` normalised against the candidate pool's own maxima, so a large raw signal such as a `coupling_degree` of 12 cannot outweigh severity in this provisional order), ties broken on fingerprint ascending; the first `max(top_multiple x N, min_candidates)` (3N or 30, whichever is larger) are selected, then every candidate at or above `always_min_severity` (5) and every candidate in `always_families` (`security`) is added, and the selection is truncated to `max_candidates` (72) in that same order; tier A candidates (rules and tool facts) are never sent to a verifier and appear in neither list, and every other unselected candidate is listed under `unverified`; batches of `batch_size` (6) sorted by primary file then fingerprint keep one file's candidates together; each prompt carries the read-only rule and an allowance of three further files the verifier may open and must name in `opened`, then per candidate its fingerprint, title, family, severity, effort, note, `confirmed_by`, the deterministic signals, every cited span read from disk with `context_lines` (30) lines of context either side and 1-based line numbers (the cited lines marked `>`), the change-coupled partners of the primary file from `coupling.pairs`, approximate referrers from the stem graph, built once per plan and passed to every prompt (`not computed` when the graph raises, so a graph failure never aborts a verification), the family's `verifier_questions`, the family block's own traps (the same list the scout prompt carries, under `known non-debt shapes for this family`) and then the `traps` from config whose `family` matches and whose `path_glob` fnmatches the primary file; every line of repository text passes through `redact`, and the prompt shares no text with the scout prompts beyond the read-only rule and that family trap list, restated on purpose so the verifier can match a known non-debt shape |
| `apply_verdicts.py --workdir .tech-debt` | `candidates.json`, `verify-plan.json`, the `verdicts/verify-<nn>.json` files `verify-plan.json`'s batches name | `verified.json` | the tier table of spec 4.8: a candidate already `tier: "A"` (rule findings, tool facts) stays A with no verifier; `confirm` with every cited quote `quote_verified` and at least one `confirmed_by` entry beyond the scout's own `scout:<family>` (a `pattern:`, `rule:`, `tool:`, `signal:` prefix, `satd`, `coupling`, `hotspot`, or a second `scout:` family counts as corroboration) earns A, otherwise B; `downgrade` or `refer` earns C; `reject` keeps `tier: null` with `verified: true` and the verdict's `proof` for the report's considered-and-rejected section; a candidate that was never selected, or was selected but no batch returned a verdict for it, is C with `verdict: "unverified"` and `verified: false` — the two states share the tier and the verdict word but not the `tier_reason`, which reads `not selected for verification` for the first (raise `--top` or the verifier budget) and `selected for verification, but no verdict came back` for the second (re-dispatch that batch); the 2.3 family caps then weaken a confirmed tier (never strengthen it) — duplication and architecture (unless `tool:` or `coupling`), god-classes TD-20 (unless `coupling`), test-gaps (unless `signal:no-mapped-tests`), test-quality (severity also capped at 3), dependency-debt, security and migration (unless `coupling`) cap at B; dead-code caps at C unless churn and fan-in are both 0 and `path_class` is `source` (then B) or a `tool:` is present (then no cap); doc-drift and pipeline-infra scout candidates cap at B unconditionally; every other family is uncapped; where a verdict exists its `severity` (1-5) and validated `effort` replace the scout's, and its `checked`, `opened`, `proof` and `trap_matched` are copied onto the finding; a verdict whose `fingerprint` matches no candidate is counted `unknown_fingerprint` and ignored, and a batch whose output file is missing on disk prints a warning and leaves its candidates `unverified` rather than failing the run; every finding also carries `tier_reason`, the prose for why it landed on that tier, computed on the same branch as the tier itself (`_tier_and_reason`) and read off `_family_cap_and_lift` for a capped one so the wording cannot drift from `family_cap`'s own branching — a tool-raised candidate gets its own sentence there (the tool that raised it is not its own corroboration), because its `confirmed_by` is empty by design and the scout wording would read as "no tool corroborated this"; test-quality's capped reason names spec 2.3's own wording — "CI data, which this scan never reads" — rather than "tool corroboration", the wording dependency-debt and security (the family table's two other tool-lift caps) keep, because this scan reads no CI signal for the family at all; exits 2 (with an `error:` line to stderr) when `candidates.json` or `verify-plan.json` is missing or unreadable/malformed |
| `rank.py --workdir .tech-debt [--preset balanced\|hotspot-first\|architecture\|quick-wins] [--top N]` | `verified.json`, `inventory.json`, `.tech-debt.yaml` | `ranked.json` | spec 4.9's priority formula: `priority = severity x interest x tier_weight x tractability`, `interest = 1 + wH*H + wC*C + wF*F` with `H`, `C` and `F` the finding's `hotspot_score`, `coupling_degree` and (`0` when the primary file's `fan_in_mode` is `anywhere`) `fan_in_approx`, each normalised against `repo_maxima(inventory)`; `tier_weight` is A 1.0, B 0.7, C 0.35; `tractability` is S 1.0, M 0.75, L 0.5 (`quick-wins`: 1.0, 0.5, 0.2); the four presets (`balanced`, `hotspot-first`, `architecture`, `quick-wins`) fix their own weights and tractability by name, `--preset` overrides `ranking.preset`, and only `balanced` reads `ranking.weights`/`ranking.tractability` from config; only tier A and B findings are eligible for the top N, and under `quick-wins` a duplication finding without `tool:` or `coupling` corroboration and every ownership finding are excluded from it too (still emitted with `in_top_n: false`); findings are walked in priority-descending, fingerprint-ascending order (the tie-break) filling the top N while each family holds fewer than `ceil(spread_cap x N)` (spread_cap 0.5) chosen entries, a finding a family cap displaces is marked `spread_capped: true` and keeps its priority-ordered `rank` (numbered over every finding, top or not); `formula_version` (1), every term, the preset name, weights and tractability are recorded on the document so any priority can be recomputed; the output is byte-identical across runs on identical inputs; exits 2 (with an `error:` line to stderr) when `verified.json` or `inventory.json` is missing, unreadable, malformed, of the wrong top-level shape, or `--preset` names an unknown preset |
| `baseline.py diff [--workdir .tech-debt] [--root <repo>] [--baseline <path>] [--today <date>]` | `verified.json`, the committed baseline (default `.tech-debt/baseline.json`, resolved against `--root`) | `diff.json` | spec 4.10: `--root` is the scanned repository every entry's `file` is resolved against, and defaults to the `root` the workdir's own `inventory.json` recorded (else `.`), because the chain is run from the skill's directory rather than the repository and the wrong root reports every unmatched entry RESOLVED with `file absent`; every current finding classified against the baseline — `UNCHANGED` on a fingerprint match, `UNCHANGED (moved)` when that same match's recorded `line_start` differs from the finding's current line, `UNCHANGED (edited)` on the one heuristic (same family and file, a baseline entry within `EDIT_WINDOW` (40) lines with an integer `line_start` on both sides, sharing at least half the baseline entry's title tokens — the nearest by line distance is kept when more than one qualifies), `RESOLVED` for a baseline entry no finding matched once its `quote` can no longer be found in the file or the file itself is gone (`file absent`; an entry with no recorded `quote` stays open with the note `quote unavailable` rather than resolving without proof), otherwise `NEW`; a `rejected` entry suppresses its finding indefinitely and an unexpired `accepted` entry suppresses it until `until`, both counted under `suppressed` instead of `status`; an `accepted` entry past `until` (or with an unparseable `until`) returns under `status` with the note `acceptance expired` (or `until is not a date`) and counts under both its classification and `expired`; an absent baseline marks every finding `NEW` with `baseline_found: false`; see [The baseline](#the-baseline) below |
| `baseline.py record --design <design.md> [--workdir .tech-debt] [--root <repo>] [--baseline <path>] [--today <date>]` | the edited `design.md`, `verified.json` | the baseline file, and (via `ensure_gitignore_triple`) possibly `<root>/.gitignore` | spec 4.10: writes every `design.md` finding's `status`, `reason` and `until` into the baseline, keyed by fingerprint and keeping entries this scan did not touch; also writes a `pending` entry for every `verified.json` finding with no decision and no prior entry, so a finding seen and undecided reads UNCHANGED rather than NEW next scan (ruling 25); an entry it sees again keeps only `status`, `reason`, `until` and `first_seen` and has every finding-derived field refreshed, and an entry whose code was edited since (matched by the same heuristic `diff` classifies with, over the whole baseline, with the result kept only when no current finding already owns it) migrates to the finding's new fingerprint with its decision intact and the old key removed (ruling 29); `--root` defaults the same way `diff`'s does; a decision with no fingerprint or an unrecognised status raises; the write is atomic (`os.replace` via a `.tmp` file); then `ensure_gitignore_triple` appends the tracked-baseline triple to `.gitignore` the first time git reports the baseline path ignored, returning `appended`, `present` (already tracked, or the triple already there), `no-git`, or `still-ignored` (the triple was appended but an ancestor directory is itself wholly ignored, so the baseline stays ignored until the user un-ignores that ancestor by hand); called in process by `promote.py --baseline`, never run standalone in the chain |
| `design_writer.py render --workdir .tech-debt --scan-date <date> [--out <path>]` | `ranked.json`, `verified.json`, `candidates.json`, `scan-plan.json`, `inventory.json`, `coupling.json`, and `notes.json`, `diff.json` and `tool-signals.json` when present | `design.md`, `findings.json` | spec 4.11's review document: literal-YAML frontmatter (`schema_version`, `scan_date`, `root`, `total_files`, `total_loc`, `languages`, `preset`, `families_run`, `families_skipped`, `tools_run`, `tools_absent`, `git_available`, `counts`), an empty list rendered as `key: []` on one line so it never reads back as `None` — the two tool lists come from `tool-signals.json`'s `tools` map, `ran` in `tools_run` and every other status in `tools_absent` with the status in parentheses, and are both `[]` when no signals file is present; the header with the review instructions and, only when `git_available`, the top five hotspots and coupled pairs (a `No git history` line instead); then the seven body sections in order — `# Top N` with one H2 per top-N finding, `# Below the cut`, `# Below the cut: tier C and unverified` (a `slug | family | file | reason` row per finding, the reason being `verified.json`'s `tier_reason`), `# Considered and rejected`, `# Looks bad but is fine`, `# Open questions for the maintainer` and `# Not assessed`. A finding is an H2 whose fenced `yaml` anchor carries `status`, `slug`, `fingerprint`, `tier`, `priority`, `family`, `category` (always the alias of `family`), `debt_type`, `type_id`, `severity`, `effort` and `diff`, followed by `### Proof`, `### Evidence` (one `` `file:start-end` `` line per item then its quote in an unlabelled fenced block), `### Signals` and, for a top-N finding, `### Remediation` and `### Acceptance criteria` (`remediation note not available` when the note agent has no entry). Slugs come from `slugs.unique_slugs` over the ranked order, so a finding's slug does not move when another is added below it; every title, proof and quote passes through `redact` at the point of writing; without `diff.json` every finding renders `diff: NEW` and the `new` and `resolved` counts are omitted; the output is LF-only and re-parsed through `design_parser.parse_design` as a write-time self-check |
| `design_writer.py notes-prompt --workdir .tech-debt [--top N]` | the same six documents `render` requires (via `load_inputs`) | `prompts/notes.md` | spec 4.11's Task 5: one prompt for the single remediation-note agent, over the top N only, in `ranked.json`'s `top_n` priority order — a role sentence naming the repository root, the read-only rule, then per top-N finding `## <n>. <title>` with `fingerprint`, `family`, `severity`, `effort`, the free-text proof and each evidence item as `` `file:start-end` `` followed by its quote in a fenced block (the same fencing `render` uses), then `NOTES_CONTRACT` verbatim (the `notes.json` reply shape: `fingerprint`, a `remediation` of at most 120 words with no code, and two to five checkable `acceptance_criteria`); every title, proof and quote is redacted. `--top` narrows the prompt below `ranked.json`'s own top N and never widens it. The agent's reply, stored as `notes.json`, is read back by `render` — via `notes_by_fingerprint`, which keeps only an entry whose fingerprint is in `top_n`, whose `remediation` is a non-empty string and whose `acceptance_criteria` is a list of strings, dropping anything else silently — into each top-N finding's `### Remediation` and `### Acceptance criteria` sections; a missing or malformed `notes.json` renders `NOTE_PLACEHOLDER` in both instead of failing |
| `evaluate.py --planted <planted.json> [--workdir <dir>] [--top N] [--json]` | `findings.json` (preferred) or `verified.json`, and `ranked.json` when present | stdout: the table, or the JSON report with `--json` | per-family precision, recall and decoy hits by tier, tier A precision, and decoys in tier A or the top N, against a fixture's `planted.json`. A decoy's `sources` list (exact tokens or a trailing-`*` prefix) restricts which producers can hit it; a family mismatch is still decided first. |
| `live_run.py <fixture-or-repo> [--workdir <dir>] [--families <set>] [--top N] [--preset <name>] [--churn-months N] [--model <alias>] [--max-budget-usd <n>] [--claude <path>] [--timeout <seconds>] [--log <path>] [--skip-agents] [--keep <dir>] [--tools] [--planted <path>]` | a corpus fixture (replayed) or a repository, then each stage's own inputs, plus a `planted.json` (the fixture's own, `<repo>/planted.json`, or `--planted`'s override) | every file the chain writes — `prompts/notes.md`, `notes.json`, `design.md`, `findings.json`, and (under `--tools`) `tool-signals.json` — plus `evaluation.json`, one row appended to `docs/evaluation-log.md`, and (under `--keep`) a copy of `evaluation.json`, `design.md`, `notes.json` and `findings.json` under `<dir>/<fixture-or-repo-name>` | the whole chain with real agents: the signal scripts, (`--tools`) the external tool probe, `plan_scan.py`, one `claude -p` call per scout prompt, `merge_findings.py`, `verify_prompts.py`, one call per verifier batch, `apply_verdicts.py`, `rank.py`, the single note agent's call, `design_writer.write_design`'s render of `design.md`/`findings.json` and, when a `planted.json` is present, scores `findings.json` with `evaluate.py` and logs a trailing `notes` column; refuses to run at all when the workdir already holds a `diff.json` or `baseline.json`; manual only, never CI — the [Live harness](#live-harness) section below has the argv, the retry rule and the exit codes |

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
are exercised without committing a `.git` directory. Every decoy carries a
`sources` list and `test_every_decoy_names_its_sources` pins it.

### Live harness

`live_run.py <fixture-or-repo>` drives the whole chain with real agents. It is
manual only and never runs in CI. Given a corpus fixture name it replays the
fixture through `tests/helpers/make_history.py` into a temporary directory
(any other argument is taken as a repository path). It refuses to run at all
when the workdir already holds a `diff.json` or a `baseline.json`: the harness
never diffs against a baseline, and `design_writer` drops baseline-suppressed
findings from `findings.json`, so a run scored there would set a bar from a
filtered population; the error names the fix (a fresh `--workdir`, or removing
the file). It then runs the deterministic signals, and, under `--tools`, the
external tool probe (`tools_probe.probe`, writing `tool-signals.json` before
`plan_scan.py` runs so a tool lead can reach a scout prompt and a tool
candidate can reach a verifier the same as any other run with the file
already present) — the same probe `/tech-debt-scan` step 4 runs, reaching the
network via osv-scanner when it is installed, unless `tools.network` is
`false` in `.tech-debt.yaml` — then `plan_scan.py`, one `claude -p` call per
scout prompt, `merge_findings.py`,
`verify_prompts.py`, one call per verifier batch, `apply_verdicts.py` and
`rank.py`. After ranking it renders the single remediation-note agent's
prompt and, when the top N is non-empty, dispatches one more `claude -p` call
under the same isolation and budget as the scouts, validating the reply
against `NOTES_SCHEMA` (an empty top N skips the call); the reply is written
to `notes.json`, and `design_writer.write_design` then renders `design.md`
and `findings.json` from it, so a top-N finding the note agent answered for
carries a real `### Remediation` and `### Acceptance criteria` rather than
`NOTE_PLACEHOLDER`. When a `planted.json` is present it scores `findings.json`
(not `verified.json`) with `evaluate.py`, prints the table and appends one row
to `docs/evaluation-log.md`: date, fixture, model, `churn_months`,
`tier_a_precision`, `reported_precision`, `decoys_tier_a`, `decoys_top_n`,
per-family `recall`, `scouts`, `verifiers`, `cost_usd` and `notes` —
the trailing column, the count of top-N findings the note agent actually
filled in over the top-N size, e.g. `3/5`. `tier_a_precision` comes from the
report's `tier_a` block and counts tier A findings alone, which is the
release bar; `reported_precision` is the per-family figure, which spans
tiers A and B. The history window is the fixture's `planted.json`
`churn_months` when present; a conflicting `--churn-months` is ignored, with a
warning printed to stderr, so the logged `churn_months` always matches the
window the run actually scored against. Without a planted value,
`--churn-months` sets the window, else the config default. `--keep <dir>`
copies `evaluation.json`, `design.md`, `notes.json` and `findings.json` into
`<dir>/<fixture-or-repo-name>` once scoring is done, so a run's documents can
be audited later without re-running the chain; the path is resolved to
absolute before anything else so it does not depend on the process's working
directory at the time the copy happens. `--planted <path>` overrides both the
fixture's own `planted.json` and a `<repo>/planted.json` lookup (`fixture_name`
is still derived the normal way), so a plain repository can be scored against
any fixture's planted file, or a hand-written one, without copying it into the
scanned tree. Together with `--tools` and `--keep`, a single paid invocation
against a corpus fixture runs the probe, scores the result and keeps its
documents in one command.

Every agent call is a list argv (never a shell string) in print mode:
`--setting-sources project --strict-mcp-config --disable-slash-commands` keep
the user's settings, MCP servers and slash commands out of the run,
`--output-format json --json-schema <the contract>` pins the reply shape to
`SCOUT_OUTPUT_SCHEMA`, `VERDICT_SCHEMA` or `NOTES_SCHEMA`, `--tools Read,Grep,Glob
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
the run. `--skip-agents` reuses the scout, verdict and notes files already in
the workdir instead of calling out. Flags: `--workdir`, `--families`, `--top`,
`--preset`, `--churn-months`, `--model`, `--max-budget-usd`, `--claude`,
`--timeout`, `--log`, `--skip-agents`, `--keep`, `--tools`, `--planted`; exit 2
on a bad target, malformed input, or a failed design-render self-check
(`DesignWriteError`, raised by `write_design`'s write-time re-parse), 3 when
`claude` is not on PATH (and `--skip-agents` is absent), 4 when an agent call
fails after its retry, `--skip-agents` finds no cached reply, or the workdir
holds a stale `diff.json` or `baseline.json`.

## External tool probe

`tools_probe.py` and `tool_normalisers.py` split the phase 4a work in two:
`tools_probe.py` owns every side effect — the CLI, presence detection, the
ten-row tool registry, the subprocess runner, timeouts and redaction — while
`tool_normalisers.py` holds the ten `normalise_<tool>(payload, root) ->
list[Signal]` functions as pure code with no I/O. The split exists so a
normaliser is testable from a captured payload with nothing mocked, and the
runner is testable with no tool installed at all.

Each registry row's artefact predicate and its argv builder must select the
same thing. A predicate narrower than the invocation gates a tool out of work
it would have done — osv-scanner's lockfile patterns matched the repository
root only while its invocation is `--recursive`, so a monorepo with per-package
lockfiles got no vulnerability scan at all. A predicate wider than the
invocation turns a tool loose on work its gate never selected for — jscpd's
gate is JS/TS while its invocation parsed every format it knows and descended
into `node_modules`, which produced 92% of the signals from a scan of this
repository. jscpd is now given `--format` restricted to its own gate's four
languages, and every tool — not jscpd alone — is kept out of the vendored and
generated trees `inventory.py` classifies, by one of the three mechanisms
described under redaction below. Every builder names its target with an
absolute path, because the runner also sets the child's working directory and
a relative operand would be resolved against it twice.

`python scripts/tools_probe.py <repo> [--workdir DIR] [--skip-all]` never
installs anything, never invokes `npx`, and never executes project code.
Presence detection is `shutil.which(name)` first, then
`<repo>/node_modules/.bin/<name>[.cmd|.exe|.ps1]` for `jscpd`, `knip` and
`madge` only — the three tools distributed as npm packages, whose project-
local install a repository already depends on; every other tool is
`shutil.which` alone. Each present tool the artefact predicate says is worth
running gets one subprocess call under a per-tool timeout, and lands in one
of four statuses: `ran` (the process exited with a code the registry allows
and its output parsed), `absent` (no executable found), `failed` (a rejected
exit code, a timeout, an OSError, output that failed to parse, or a
normaliser that raised — which costs that tool's signals and no others), or
`skipped` (no matching artefact, the tool is on the config deny list,
`--skip-all` was given, or — for osv-scanner offline — no local vulnerability
database). `tools_probe.py` writes `tool-signals.json` to the workdir, and
`/tech-debt-scan` step 4 runs it after the network notice below. Its
inference-class signals (ruff, vulture, lizard, jscpd, knip, madge) become
leads and `confirmed_by` corroboration through `plan_scan.py` and
`merge_findings.py`; its fact-class signals (osv-scanner, gitleaks, hadolint,
actionlint) become candidates, with osv-scanner alone entering at tier A —
see [What tier A means for a reader](#what-tier-a-means-for-a-reader) below.
Long repositories are also split into per-directory module scouts at this
point (`plan_scan.py`'s chunking, halved thresholds under `--deep`).

**The network notice.** Before step 4 runs, SKILL.md has Claude tell the user
what is about to reach the network: osv-scanner sends package names,
versions, ecosystems and file hashes to OSV.dev; every other first-cut tool
(gitleaks, ruff, vulture, lizard, jscpd, knip, madge, hadolint, actionlint) is
local-only and sends nothing. That claim rests on reading every tool's own
`argv_for` branch in `tools_probe.py`: none but osv-scanner's inserts a
network flag or builds a URL. That is a code-level check of what this
project asks each tool to do, not an independent audit of the nine binaries
themselves, and the phase 4b review flagged it as such: the "local-only"
half of the notice is verified in-repo for gitleaks alone, and the remaining
eight rest on the same argv-level check plus general knowledge of what a
static analyser does, which is a weaker standard than osv-scanner's half of
this notice meets (osv-scanner's network contract is OSV.dev's own
documented API). Closing that gap — an in-repo citation or a captured-run
confirmation per tool — is unresolved, deferred rather than fixed here.
Setting `tools.network: false` in `.tech-debt.yaml` keeps the whole scan
offline: the probe runs
`osv-scanner --offline` against a database pre-downloaded with
`osv-scanner --download-offline-databases` into
`OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY`; an absent database is reported as
`skipped: no local database` for that tool rather than failing the scan.
`--no-tools` runs the same step with `--skip-all`, and `tool-signals.json` is
still written, with every tool `skipped`.

Six of the ten normalisers — ruff, vulture, lizard, madge, jscpd, knip — were
written against real captured output from the tool installed on this
machine. The other four — osv-scanner, gitleaks and actionlint (Go binaries)
and hadolint (a Haskell binary) — are none of them installable on this
machine, so their normalisers were written from documented output schemas
alone and have never seen their tool run.
`skills/tech-debt-scan/tests/fixtures/tool-output/PROVENANCE.md` records
which fixture is which, and which command produced it. This distinction is
not a formality: four of the five tools that could be installed contradicted
their own documentation once actually run — madge silently returns an empty
graph and exits 0 on a real TypeScript import cycle unless given
`--extensions` explicitly, vulture exits 3 rather than the 1 most of this
registry's other tools use for "findings present" and has no JSON output
mode, lizard has no JSON output mode either (`--csv`, `--xml` and `--html`
are its only structured formats), and jscpd's JSON reporter never writes to
stdout — only to a report file in a directory the caller supplies. A
normaliser written only from documentation carries the same risk: nothing
has confirmed its assumed shape matches what the tool actually emits.

No field that can carry source text or a credential is ever copied into a
signal. `normalise_gitleaks` drops `Secret` and `Match` — the credential
gitleaks matched — outright rather than redacting them, because a redacted
secret is still its own first four characters while a dropped one is
nothing. `StartColumn` is kept, in `extra["column"]`, because it carries no
source text: two different secrets matched by the same rule on the same line
otherwise agree on family, path, line range and message too, and
`merge_findings._fact_candidate` folds the column into the fingerprint span
(`_fingerprint_span`) precisely so they stay two candidates instead of
collapsing onto one fingerprint a single verdict then decides for both.
`normalise_jscpd` drops `fragment`, the duplicated source itself,
for the same reason. `normalise_actionlint` drops `snippet`, a line of the
workflow file that may carry a token or an inline secret reference. In every
case the file and line range that remain are enough to find the finding by
hand.

Dropping those four fields is the first half of the guarantee; the second is
that **every string written into `tool-signals.json` goes through
`redaction.redact`**, not only the strings in the `signals` array. The array
was not the only route: `tools[<name>].reason` carries up to 200 characters
of a failing tool's stderr, and a tool that fails while reading a file
routinely prints the offending source line — vulture prints it on a syntax
error — so a credential on that line reached the document verbatim until the
whole-branch review found it. Redaction is applied to the document at the
point of writing, to dictionary keys as well as values and into every
container (list, tuple, set), so a field added later cannot miss it. It is
applied a second time, earlier, wherever `reason` is built: the general rule
above — redact first, cap second — is enforced in `tools_probe.py` by a
single `_capped` helper that every capping site calls, because truncating a
credential in half destroys the shape the later document-wide `redact` would
have matched on.

**What `tools[<name>].reason` may still contain, stated plainly.** It is
*arbitrary text the failed tool printed, minus credential-shaped substrings*
— not merely a variable name and punctuation. `redact` recognises shapes: an
assignment whose name contains password/secret/token/api_key/apikey/
access_key, and a token carrying a known issuer prefix. Everything else on
the line survives, up to the 200-character cap. A database connection string
whose password is neither prefixed nor assigned to a matching name —
`CONN = "postgres://admin:S3cretP4ssw0rd@db.internal:5432/prod"` — passes
through intact. This is a deliberate trade, not an oversight: dropping stderr
would make every tool failure undiagnosable, and the exposure is narrow — a
`failed` tool only, at most 200 characters, and only when the tool echoes
what it was reading. Read the module docstring's "no field that can carry
source text or a credential is ever copied into a signal" as the statement
about *signals* that it is; `reason` is in the `tools` map, and it is the one
place source text can reach the file.

**No tool is turned loose on a tree the repository does not own.** The
vendored and generated path classes are `inventory.py`'s — the same
`DEFAULT_IGNORE` and `PATH_CLASS_GLOBS` that decide every inventory entry's
`path_class`, and that `patterns.py` already refuses to scan, credential rule
included — so there is one notion of "vendored" in the skill and not two. The
probe applies it three ways, chosen by what each tool accepts: an ignore flag
where one exists (`jscpd --ignore`, `vulture --exclude`, `lizard -x`, `ruff
--extend-exclude` — never `ruff --exclude`, which replaces ruff's own
defaults instead of adding to them); a filtered operand list for the two
tools this module globs operands for itself (`hadolint`, `actionlint`); and a
filter over the signals produced, for the four with no usable path flag
(`madge`, whose `-x` takes a regular expression rather than globs; `knip` and
`gitleaks`, whose only path ignore is a config file in the repository being
scanned; and `osv-scanner`, which has none). That last filter runs for all
ten tools, so one that ignores the list it was given still cannot reach the
document. `artefact_present` discounts vendored matches for the same reason:
a repository whose only Dockerfile sits in `node_modules` has nothing for
hadolint to do, and a gate that claimed otherwise would be the
predicate-versus-argv disagreement again.

### What tier A means for a reader

Tier A is the report's strongest claim: `rank.py` weights it at 1.0 (against
0.7 for B), and a tier A finding is the one most likely to sit in `# Top N`.
For most tier A findings that claim rests on a verifier Agent having read the
code and confirmed it, plus at least one independent corroborating signal
(spec 4.8). **Two kinds of candidate skip that verifier entirely** and reach
tier A by construction: a `rules.py` finding (a deterministic fact — a
missing `timeout-minutes:`, an untagged `FROM`, a knowledge island — whose
quote is verified by construction, spec 4.4) and an osv-scanner advisory at
manifest or lockfile level (a fact about a *published* vulnerability, not
about how the repository uses the affected package, spec 4.5's fact-versus-
inference split). `merge_findings.py`'s own invariant test,
`TestTierProducerInvariant`, asserts over the fixture corpus and a canned
`tool-signals.json` that no other route — not gitleaks, not hadolint, not
actionlint, not a scout — can produce a candidate with a tier already set;
every one of those instead reaches the verifier or is merged into a rule
finding's `confirmed_by`, never gaining a tier of its own.

Read plainly: **a tier A osv advisory can reach the top of `design.md`
without any agent in this pipeline having read a line of the affected code.**
That is by design — a published CVE against a pinned version is a fact
`osv-scanner` fetched from OSV.dev, not a judgement call a verifier is better
placed to make — but it means a reader deciding whether to trust a tier A
finding should look at its `confirmed_by` and `source`: `rule:<id>` or
`tool:osv-scanner` (or both, when a manifest also tripped a `rules.py`
finding) means no verifier read it; anything else means one did.

## The baseline

`baseline.py` (spec 4.10) is two subcommands. `diff` (step 11) classifies
every finding in `verified.json` against the committed baseline and writes
`diff.json` for `design_writer.py` to render: a finding's own classification
into its `diff` anchor key in `design.md`, and the tally of baseline entries
no finding matched into the frontmatter's `resolved:` count, since a
resolved entry has no finding left to carry it. `record` writes a human's
decisions from an edited `design.md` back into the baseline, also writing a
`pending` entry for every verified finding a decision never covered,
refreshing every finding-derived field of an entry it sees again, and
migrating an entry whose code was edited onto the finding's new fingerprint
with its decision intact. It is never run standalone in the chain —
`promote.py` calls it in process when given `--baseline`.

**Classification.** Every current finding gets exactly one of four `diff`
values — `UNCHANGED`, `UNCHANGED (moved)`, `UNCHANGED (edited)` or `NEW` —
and those four are the only values `design.md` can carry on a finding.
`RESOLVED` is the fifth classification and belongs to a baseline entry, not
to a finding: it names an entry no current finding matched, so there is no
finding in the document to hang it on. It appears in `diff.json`'s `status`
map, keyed by the entry's own fingerprint, and is counted in the
frontmatter's `resolved:` line; nothing else in `design.md` reports it:

- `UNCHANGED` — its fingerprint matches a baseline entry. Also the answer
  when that entry's recorded `line_start`, or the finding's own current
  line, is not an integer: `UNCHANGED (moved)` compares two line numbers and
  needs both, so a match against an entry with `line_start: null` reads
  `UNCHANGED` however far the code has moved.
- `UNCHANGED (moved)` — its fingerprint matches a baseline entry, but the
  entry's recorded `line_start` differs from the finding's current line (a
  fingerprint carries no line, so a quote that moved keeps its identity).
- `UNCHANGED (edited)` — the one heuristic classification, and the only one
  that can misfire in either direction. No baseline entry shares the
  finding's fingerprint, but one does share its family and file, sits
  within `EDIT_WINDOW` (40) lines of the finding's line (an integer line is
  required on both sides — a manifest-level finding such as an osv-scanner
  advisory, which always has none, can never match via this heuristic and
  falls through to a direct fingerprint match or, failing that, `NEW`), and
  shares at least half the baseline entry's title tokens; when more than
  one baseline entry qualifies, the nearest by line distance is kept.
- `RESOLVED` (an entry, never a finding) — a baseline entry no current
  finding matched (by either route above), once its recorded `quote` can no
  longer be found in the file, or
  the file itself is gone (`file absent`) or is now a directory. An entry
  with no recorded `quote` — every entry written before `record` started
  writing one alongside `quote_hash` (this task) — fails closed instead: it
  stays open with the note `quote unavailable` rather than resolving on the
  mere absence of a way to check, so a suppressed entry is never dropped
  from the baseline just because a scan failed to reproduce its fingerprint.
- `NEW` — none of the above; also every finding when no baseline file
  exists at all (`baseline_found: false` in `diff.json`).

A direct fingerprint match and an edited match report expiry alike: whichever
route matched, an entry with `status: accepted` whose acceptance has since
expired carries the note `acceptance expired` (or `until is not a date` when
`until` cannot be parsed), and both routes count it under `counts.expired`.
An edited match's note is `suppressed by edited match` only while the match
is still currently suppressing; once that acceptance expires, the note
becomes whichever expiry note applies, exactly as a direct match's would.

**Suppression and expiry.** A baseline entry with `status: rejected`
suppresses its matched finding indefinitely; one with `status: accepted`
suppresses it until its `until` date. Both are listed under `diff.json`'s
`suppressed` array (with the entry's `reason`) instead of `status`, and
`design_writer.py` hides them from `design.md`'s body entirely while
counting them in the frontmatter's `suppressed` figure — a finding a human
already rejected or accepted on a previous run is not rendered again with a
status it already has. Once an `accepted` entry's `until` passes, the
finding is no longer suppressed: a direct fingerprint match reappears under
`status` with `diff: UNCHANGED` or `UNCHANGED (moved)` as the line
comparison dictates, carrying the note `acceptance expired` (or
`until is not a date` when `until` cannot be parsed as an ISO date) —
both cases are also counted under `counts.expired`.

**The gitignore triple.** The baseline lives inside the gitignored workdir
(`.tech-debt/baseline.json` by default), so `record` (via
`ensure_gitignore_triple`) tracks it the first time git reports the path as
ignored, by appending a comment line and three lines to `<root>/.gitignore`
— at the default location: `!.tech-debt/` (un-ignores the directory),
`.tech-debt/*` (re-ignores everything in it), then
`!.tech-debt/baseline.json` (un-ignores the baseline alone); the three
lines are derived from wherever the baseline actually lives, each path
segment escaped for gitignore's own metacharacters. It returns one of four
outcomes: `appended` (the triple was just written); `present` (the
baseline is already tracked, or the triple is already there — no edit
needed); `no-git` (no `git` executable on the machine, so the check is
skipped and the baseline is written regardless); or `still-ignored` (the
triple was appended — it is the correct pattern for this location — but
the baseline remains ignored, because an ancestor directory is itself
wholly ignored and no per-child `!` rule can undo that; the user must
un-ignore that ancestor by hand). `diff` never touches `.gitignore`; only
`record` does, and only `promote.py --baseline` calls `record` outside of
manual use.

**Exit 6.** `promote.py --select <slug> --baseline <path>` writes every
finding's decision back into the baseline after `evidence.md` is written and
`design.md` is marked promoted. When that write-back raises —
`BaselineError` (including a malformed baseline file), a `DesignParseError`
(the write-back re-parses `design.md` after the mark-promoted mutation, so a
document that became unparseable in between fails here), a `ValueError`
(including malformed JSON in `verified.json` or `ranked.json`), or an
`OSError` — `promote.py` returns `promote.EXIT_WRITE_BACK` (6). By that
point `evidence.md` is already on disk and `design.md` already shows
`promoted`: exit 6 means the write-back alone failed, never the selection
itself. The fix is to address the cause and re-run the same `--select`
command; `SELECTABLE` includes `promoted`, so a slug this run already
selected, or that a prior run already marked `promoted`, is re-rendered
rather than refused. Given `--baseline` with a v1 `design.md` (no
fingerprints), `promote.py` refuses before writing anything, with exit 2 —
a baseline keyed by fingerprint cannot record a decision that has none.

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
plus `new`/`resolved` once `diff.json` is present — step 11 always writes
one, whether or not a baseline file exists yet, so this holds for every
complete chain run and not only once a baseline has been committed;
`tools_run` names each tool
`tool-signals.json` records as `ran` and `tools_absent` every other one with
its status in parentheses — `absent`, `failed`, `skipped`, or `unknown` for a
status the four do not cover — which is spec 4.5's "names every absent tool"
and what tells a `--no-tools` run from a full probe; both are `[]` when the
workdir holds no `tool-signals.json`), a header naming the top
hotspots and coupled pairs, then seven body sections in order: `# Top N`,
`# Below the cut`, `# Below the cut: tier C and unverified`,
`# Considered and rejected`, `# Looks bad but is fine`,
`# Open questions for the maintainer`, `# Not assessed` (the skipped families, any modules the `chunking.max_modules` bound dropped, and the three standing limits).

A finding is an `## ` section whose fenced `yaml` anchor carries `status`,
`slug`, `fingerprint`, `tier`, `priority`, `family`, `category` (always the
`family` alias, so v1 tooling and a human skimming still see a `category`
key), `debt_type`, `type_id`, `severity`, `effort` and `diff`. Every other
section is an `# ` heading, which ends the preceding finding's body so a
negative-space section (rejections, open questions, and the rest) is never
copied into `evidence.md`. A top-N finding's body also carries `### Remediation`
and `### Acceptance criteria` from the remediation-note agent; a below-the-cut
tier A/B finding outside the top N carries `### Proof` and `### Evidence`
only, so it is still selectable without a note; `# Below the cut: tier C and
unverified` is a compact table instead of full sections, one row per tier C
or unverified finding.

The renderer re-parses its own output via `design_parser.parse_design` as a
self-check before exiting; a round-trip failure exits non-zero. The same call
also writes `findings.json` beside `design.md`: the same findings as
machine-readable JSON, preferred by `evaluate.py` over `verified.json`. Each
row copies `source`, `rule_id` and `tool` from the verified finding, right
after `confirmed_by`, so `evaluate.py` reads a finding's producer the same
way off either input.

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

`promote.py <design.md> (--list-approved | --select SLUG) [--baseline <path>]`
is a thin orchestrator over already-tested sub-modules — it holds no parsing
or rendering logic of its own:

1. `design_parser.parse_design` parses the (human-edited) `design.md`.
2. `--list-approved` prints the `approved` findings as JSON — `list_approved`
   sorts them by severity then priority, both descending — and exits 0
   without writing anything.
3. `--select <slug>` calls `select`, which finds the finding with that slug,
   confirms its status is in `SELECTABLE` (`approved` or `promoted` — the
   second lets a failed baseline write, or a second design session on the
   same finding, be re-run deliberately; `--list-approved` still only ever
   offers `approved`, so a re-run is never accidental), then
   `evidence_doc.render_evidence` writes `evidence.md` beside `design.md`
   (overwriting any previous one), and, only when the status was `approved`,
   `design_writer.mark_promoted` flips it to `promoted` in place (atomic
   `os.replace` via a `.tmp` file, `.bak` of the prior content). The write
   happens before the mark, so a failed render never consumes the finding;
   if the write succeeds but the mark then raises, the status is left
   `approved` and the error names the `evidence.md` already on disk.
4. With `--baseline <path>`, `baseline.py record` is called in process
   (`_write_back`, re-parsing `design.md` so the decisions reflect
   `select`'s own mark-promoted mutation) to write every finding's decision
   — `promoted`, `rejected`, `accepted` with its `reason` and `until`, or
   still `pending` or `approved` — back into the baseline; a verified
   finding with no decision at all (suppressed and so absent from
   `design.md`, by design) gets a fresh `pending` entry, one already
   recorded is refreshed against this scan, and one whose code was edited
   since migrates to the finding's new fingerprint keeping its decision, so
   each reads UNCHANGED rather than NEW next scan; then
   `ensure_gitignore_triple` tracks the baseline the first time git reports
   it ignored. A v1 `design.md` (no fingerprints) is refused before anything
   is written, since a baseline keyed by fingerprint cannot record a
   decision that has none. See [The baseline](#the-baseline) above for the
   classification, suppression, expiry and gitignore-triple mechanics this
   feeds.

**Exit codes.** `0` success; `2` on a parse or selection error (an unknown or
non-selectable slug, an evidence-write failure, or a v1 `design.md` given
with `--baseline`) — refused before anything is written, since a baseline
without fingerprints is worse than none; a v2 document with no findings at
all is not a v1 one and selects normally; `6` (`promote.EXIT_WRITE_BACK`,
see [Exit 6](#the-baseline) above) when `--baseline` was given and the
write-back raised after `evidence.md` was already written and `design.md`
already marked. Re-running the same `--select` command after fixing the
cause is safe — `SELECTABLE` includes `promoted`, so a finding this run
already selected, or that a prior run already marked `promoted`, is
re-rendered rather than refused.

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
evaluation, split into 5a and 5b). Phases 1 to 3 have landed: `/tech-debt-scan`
and `/tech-debt-promote` run the full detect-verify-rank chain end to end.
`--families deep` already selects the full fourteen-family set today
(`plan_scan.py`, phase 2). **Phase 4 has landed:** `tools_probe.py` runs the
ten first-cut external tools (phase 4a), and step 4's network notice, tool
leads and corroboration, the fact-class tier route, module chunking and the
halved deep thresholds are wired in (phase 4b) — see
[External tool probe](#external-tool-probe). **Phase 5a has landed:**
`baseline.py` diffs every finding against a committed baseline (step 11) and
promote writes decisions back into it — plus a `pending` entry for every
verified finding a decision never covered — appending the gitignore triple
where needed — see [The baseline](#the-baseline). Phase 5b, the live harness
run that repairs the corpus, has landed: the corpus repairs, the note
agent in the harness, and a run on 2026-09-09 over all three repaired
fixtures. That run set no bar, because a decoy reached tier A on
web-ts, so the provisional 0.80 figure stays until a run clears the
hard gate (see `docs/evaluation-log.md`). Autonomously applying fixes
without review is a separate follow-on, deferred and out of scope.
