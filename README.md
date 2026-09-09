# tech-debt-scan

Language-independent tech-debt scan skill for Claude Code. It walks any repo,
mines git history for hotspots, dispatches read-only LLM scout agents across
fourteen debt families, verifies the candidates a deterministic budget
selects, ranks the survivors with a fixed formula, and renders the top-N
findings into a single `design.md` — after a human reviews and approves
findings, `/tech-debt-promote` emits ralph-friendly PBI bundles you can drop
into a queue.

Human in the loop: nothing is fixed automatically. The LLM does three things:
run each dispatched family's scout, verify the candidates a deterministic
budget selects, and write one remediation note per top-N finding; every other
step — inventory, pattern and rule mining, merging, ranking, rendering,
parsing, validation, bundle writing — is a deterministic pure-Python script
with a pinned command and a pinned output file.

## Install

This repo is a collection of Claude Code skills. To make `tech-debt-scan`
available to Claude Code, symlink the skill directory into your skills folder:

```bash
git clone https://github.com/emp3thy/claude-skills.git
ln -s "$PWD/claude-skills/skills/tech-debt-scan" ~/.claude/skills/tech-debt-scan
```

On Windows (PowerShell, as admin or with developer mode on):

```powershell
git clone https://github.com/emp3thy/claude-skills.git
New-Item -ItemType SymbolicLink -Path "$HOME\.claude\skills\tech-debt-scan" `
  -Target "$PWD\claude-skills\skills\tech-debt-scan"
```

The helper scripts need Python 3.11+ and `pyyaml`. From the skill directory:

```bash
pip install pyyaml          # the only runtime dependency
```

The scripts are direct-path invocable (`python scripts/<name>.py`) — no package
install, no `-m`.

## Quickstart

Two commands, with a human review step in between.

1. **Scan** — produce a reviewable `design.md`:

   ```
   /tech-debt-scan <repo-path>
   ```

   This inventories the repo and mines patterns and rules, dispatches one
   scout agent per debt family the adaptive rule finds leads for (up to
   fourteen, `scripts/categories.py`'s `FAMILY_BLOCKS`), merges the
   candidates, dispatches read-only verifier agents over the ones a
   deterministic budget selects, ranks the verified survivors with a fixed
   priority formula, dispatches one remediation-note agent over the top N,
   and writes `.tech-debt/design.md`.

2. **Review** — open `.tech-debt/design.md`. Each finding has a `status:`
   field set to `pending`. Change it to `approved` to promote the finding,
   `rejected` to drop it, or `accepted` to record a deliberate deferral (with
   `reason:` and an optional `until:`). Leave it `pending` to skip for now.

3. **Promote** — convert approved findings into PBI bundles:

   ```
   /tech-debt-promote
   ```

   This writes one `chore-<slug>-<date>/` bundle (`PBI.md`, `PLAN.md`,
   `HISTORY.md`) per approved finding under `./tech-debt-pbis`, then flips those
   findings to `promoted` so a re-run is a no-op.

See `skills/tech-debt-scan/SKILL.md` for the full step-by-step workflow Claude
follows, including every pinned command and pre/post-condition.

## Also in this repo: karate-bootstrap

`karate-bootstrap` takes a Spring Boot, Quarkus, ASP.NET Core or Python service that has no
Karate tests and leaves it with a first ground-truth suite under `karate-tests/` that runs
green under Testcontainers (Postgres, ActiveMQ Artemis over AMQP 1.0, WireMock for
downstream HTTP, the shared db-manager image for the schema), locally and in Azure DevOps.

Install it the same way:

```bash
ln -s "$PWD/claude-skills/skills/karate-bootstrap" ~/.claude/skills/karate-bootstrap
```

Then, in Claude Code:

```
/karate-bootstrap <repo-path> [--service-dir <sub>] [--migrations-image <ref>] [--app-image <tag>]
                  [--max-iterations 15] [--double-trace] [--no-commit]
```

The run scans the repo, traces every endpoint and listener to its database writes, message
publishes and outbound calls, extracts validation rules as CSV data, scaffolds a Maven module
with the Testcontainers harness, generates the features, runs them and iterates until green
or a stop condition, quarantining suspected app defects in `karate-tests/defects.md`. By
default it commits at each phase gate on a `karate-bootstrap` branch and never pushes.

Requirements on the machine: Python 3.11+ with `pyyaml`, JDK 17+, Maven (or the bundled
wrapper), and a container engine (docker or podman; see
`skills/karate-bootstrap/reference/podman.md`). See
[`skills/karate-bootstrap/SKILL.md`](skills/karate-bootstrap/SKILL.md) for every pinned
command, and `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` for the design.

Three runnable fixture services live under `skills/karate-bootstrap/tests/fixtures/live/`, one
per stack the skill supports: a Spring Boot service, an ASP.NET Core service and a FastAPI
service, each with a Flyway `db-manager/` image and one deliberately planted defect. The
`karate-live` CI job runs the skill's whole chain against them with real Postgres, Artemis,
WireMock and application containers, proving the generated suite goes green and the planted
defect is quarantined rather than fixed. Reproduce a run locally with Docker or Podman:

```bash
KB_CONTAINERS=1 pytest -m containers -k spring-shipments -v
```

## Output formats

| Artefact | Written by | Shape |
| --- | --- | --- |
| `inventory.json` | `inventory.py` | `{schema_version: 2, root, total_files, total_loc, languages, git_available, churn_window_months, hotspots[], hotspot_band[], files[], artefacts{}, skipped_large_files, docs{}, tests{}, git{}, boundary_tooling[], lint_config[], signal_sources{}}`; each `files[]` entry carries `path_class`, `hotspot_score`, `inline_disables`, the git history fields (`last_touched`, `authors`, `top_author`, `top_author_share`, `top_author_line_share`, `bugfix_share`, `migration_commits`, `flaky_commits`, `untested_change_share`), `mapped_tests`, `fan_in_approx`, `fan_out_approx`, `fan_in_mode`, `coupling_degree` and `skipped_large`; each `artefacts{}` entry carries `{path, path_class, loc, churn, last_touched, size_bytes, skipped_large}` |
| `coupling.json` | `inventory.py` (with `--workdir`) | `{schema_version: 2, min_shared, min_ratio, bulk_threshold, fan_in_mode, pairs[], degree{}, cycles[], directories[], unstable_edges[]}` |
| `patterns.json` | `patterns.py` | `{schema_version: 2, leads{<family>: [{rule, file, line, quote, path_class, extra}]}, satd[], stats{}}`; a lead or SATD entry on an artefact carries the artefact's real `path_class` (a workflow under a tests tree reports `tests`, not `ci`) while rule scope still keys on the artefact class, and artefacts classed `generated` or `vendored` or marked `skipped_large` are not scanned; also fills `files[].inline_disables` in `inventory.json` |
| `rule-findings.json` | `rules.py` | `{schema_version: 2, findings[], leads{migration[]}}`; each finding is a candidate with `source: "rule"`, `tier: "A"`, `confirmed_by: ["rule:<id>"]` and the artefact's `path_class` in `signals`; artefacts under a tests, vendored or generated tree are skipped, and an artefact the inventory marked `skipped_large` is never read |
| `tool-signals.json` | `tools_probe.py <repo> [--workdir DIR] [--skip-all]`, run as `/tech-debt-scan` step 4 after a network notice | `{schema_version: 2, tools{<name>: {status, version, duration_s, reason}}, signals[]}`; `status` is one of `ran`, `absent`, `failed`, `skipped`; the ten normalisers turning each tool's raw output into `signals[]` live in `tool_normalisers.py`; read by `plan_scan.py` (inference-class signals become leads) and `merge_findings.py` (fact-class signals become candidates — an osv-scanner advisory reaches tier A without a verifier, the same way a `rules.py` finding does) |
| `scan-plan.json` | `plan_scan.py` | `{schema_version: 2, set, top, chunked, thresholds{max_files, max_loc, max_modules}, modules[], modules_dropped[{module, leads}], entries[{family, module, prompt, output, leads}], families_run[], families_skipped[{family, reason}]}`; `thresholds` is the chunking config in force (`max_files` and `max_loc` halved when the set is `deep`, `max_modules` never); on a chunked plan `modules` names the top-level directories dispatched and `modules_dropped` those the `max_modules` bound cut with the leads they held, ranked out by hotspot-band files then lead count — a family left with no scanned module joins `families_skipped` with reason `no leads in the scanned modules`; both module lists are empty on an unchunked plan |
| `candidates.json` | `merge_findings.py` | `{schema_version: 2, candidates[], open_questions[{file, line_start, question, reason}], looks_bad_but_fine[{file, line_start, why}], stats{<family>: {raw, dropped, quote_failed, clustered, suppressed, disabled}}}`; each candidate is `{fingerprint, quote_hash, family, debt_type, type_id, title, severity, effort, source, rule_id, tool, note, evidence[{file, line_start, line_end, quote, quote_verified}], confirmed_by[], signals_cited[], signals{}, tier}` with `tier: null` for scout candidates; `tool` names the tool that raised a tool candidate and is `null` for a scout or rule candidate; a scout file the plan names but that is absent adds `missing_file: 1` to that family's stats; a family with at least one dropped item adds `dropped_reasons: []`, the reason string from each drop, appended after `missing_file` when both are present; rule findings keep `source: "rule"` and `tier: "A"` and are appended after the scout candidates. Fact-class tool signals enter as `source: "tool"` candidates by three routings: an osv-scanner advisory arrives `tier: "A"` with a null line range (the manifest or lockfile is the evidence), so it skips the verifier exactly as a rule finding does; a gitleaks secret arrives untiered, because a placeholder or a fixture needs a verifier's judgement; a hadolint or actionlint fact merges into a same-file rule finding's `confirmed_by` when one exists and otherwise enters untiered on its own. Every tool-raised candidate but the osv one carries an empty `confirmed_by`, so it cannot corroborate itself, and `rules.py` plus those osv facts stay the only producers of a non-null tier at merge time. Inference-class signals corroborate instead of raising anything: `tool:<name>` joins the `confirmed_by` of a same-family candidate citing that file in any of its evidence items — unless the file's path class disables the family, the same `families.per_path_class` check `plan_scan` applies to the lead built from the same signal |
| `verify-plan.json` | `verify_prompts.py` | `{schema_version: 2, top, batch_size, selected[], unverified[], batches[{prompt, output, fingerprints[]}]}`; `selected` is every fingerprint sent for verification, in batch order, and `unverified` every `tier: null` candidate the budget rule left out; tier A candidates are in neither list; each batch names the prompt written at `prompts/verify-<nn>.md` (two digits from 01) and the `output` path `verdicts/verify-<nn>.json` the read-only verifier's reply must be stored at, a JSON array of `{fingerprint, verdict, proof, severity, effort, trap_matched, checked[], opened[]}` with `verdict` one of `confirm`, `downgrade`, `reject`, `refer` |
| `verified.json` | `apply_verdicts.py` | `{schema_version: 2, findings[<candidate keys> + tier_reason, verdict, proof, checked, opened, trap_matched, verified], stats{selected, verdicts, unknown_fingerprint, missing_verdict, tier_a, tier_b, tier_c, rejected}}`; each finding is a candidate with `tier` overwritten by the earned tier (`A`/`B`/`C`/`null`, spec 4.8 plus the 2.3 family caps) and `verdict` one of `confirm`, `downgrade`, `reject`, `refer`, `rule` (tier-A candidates verified by construction) or `unverified` (not selected, or selected with no returned verdict; `verified: false`); a `reject` keeps `tier: null` with `verified: true` and its `proof`. `tier_reason` is the prose for why the finding landed on that tier, computed on the same branch as the tier itself so the two cannot disagree, read by `design_writer.py` for the design document's tier C and `unverified` table: what corroborated a tier A, which corroboration a capped family wanted (and, for a tool-raised candidate, that the tool which raised it is not its own corroboration), which way the verifier went, and — the two states a bare `unverified` conflates — `not selected for verification` against `selected for verification, but no verdict came back` |
| `ranked.json` | `rank.py` | `{schema_version: 2, formula_version: 1, preset, top, weights{wH, wC, wF}, tractability{S, M, L}, top_n[], findings[{fingerprint, rank, priority, terms{severity, H, C, F, interest, tier_weight, tractability, priority}, tier, in_top_n, spread_capped}]}`; `findings` is every finding ordered by priority descending then fingerprint ascending (the tie-break), `rank` numbering that order; `top_n` is the fingerprints, in that same order, of the findings that made the top `top` under the chosen `preset` (`balanced`, `hotspot-first`, `architecture` or `quick-wins`) — tier A and B only, minus (under `quick-wins`) uncorroborated duplication and every ownership finding, capped at `ceil(spread_cap x top)` per family with the excess marked `spread_capped: true`; byte-identical for identical inputs |
| `diff.json` | `baseline.py diff [--workdir DIR] [--root <repo>] [--baseline <path>] [--today <date>]`, run as `/tech-debt-scan` step 11 | `{schema_version: 2, baseline_found, status{<fingerprint>: {diff, note, matched}}, suppressed[{fingerprint, status, reason}], counts{new, unchanged, moved, edited, resolved, suppressed, expired}}`; `--root` is the scanned repository the baseline and its entries are resolved against and defaults to the `root` recorded in the workdir's `inventory.json` (else `.`); every current finding is classified against the committed baseline (`.tech-debt/baseline.json` by default) as `NEW`, `UNCHANGED` (fingerprint match), `UNCHANGED (moved)` (fingerprint match, recorded line differs), `UNCHANGED (edited)` (the one heuristic — same family and file, a baseline entry within `EDIT_WINDOW` (40) lines sharing at least half its title's tokens, nearest by line distance breaking a tie) or, for a baseline entry no finding matched, `RESOLVED` once its `quote` is gone from the file or the file itself is gone (`file absent`; an entry with no recorded `quote` stays open with the note `quote unavailable` rather than resolving without proof); a `rejected` baseline entry suppresses its finding indefinitely and an unexpired `accepted` one suppresses it until `until`, both listed under `suppressed` instead of `status`; a direct fingerprint match against an expired `accepted` entry returns under `status` with the note `acceptance expired` (or `until is not a date`) and counts under both its classification and `expired`; an absent baseline marks every finding `NEW` with `baseline_found: false`; read by `design_writer.py render` |
| `.tech-debt/baseline.json` (or wherever `--baseline`/the config `baseline` key points) | `baseline.py record --design <design.md> [--workdir DIR] [--root <repo>] [--baseline <path>] [--today <date>]`, called in process by `promote.py --baseline` — never run standalone in the chain | `{schema_version: 2, last_scan, preset, findings{<fingerprint>: {family, file, line_start, quote_hash, quote, title, tier, status, first_seen, last_seen, reason, until, bundle}}}`; writes every `design.md` finding's decision back, atomically, keeping entries this scan did not touch; also writes a `pending` entry for every `verified.json` finding with no decision and no prior entry (ruling 25); an entry it sees again keeps only its `status`, `reason`, `until`, `bundle` and `first_seen` and has every other field refreshed from this scan, and an entry whose code was edited since migrates to the finding's new fingerprint with its decision intact, the old key removed (ruling 26); a decision with no fingerprint or an unrecognised status raises, and a `promoted` decision with no bundle on record raises; then `ensure_gitignore_triple` appends `!<dir>/`, `<dir>/*`, `!<dir>/<name>` to the repository's `.gitignore` the first time git reports the baseline path ignored, returning `appended`, `present`, `no-git` or `still-ignored` (the triple was appended but an ancestor directory is itself wholly ignored, so the baseline stays ignored until the user un-ignores that ancestor by hand) |
| `prompts/notes.md` | `design_writer.py notes-prompt` | spec 4.11's Task 5 prompt for the single remediation-note agent: a role sentence naming the repository root, the read-only rule, then per top-N finding (`ranked.json`'s `top_n`, in priority order) `## <n>. <title>` with `fingerprint`, `family`, `severity`, `effort`, the redacted proof and each evidence item as `` `file:start-end` `` followed by its redacted quote in a fenced block, then the `NOTES_CONTRACT` verbatim (the `notes.json` reply shape below); `--top` narrows the top N below `ranked.json`'s own top and never widens it |
| `notes.json` | the remediation-note agent | `[{fingerprint, remediation, acceptance_criteria[]}]`, one entry per top-N finding: `remediation` at most 120 words on how to pay the debt down (no code), `acceptance_criteria` two to five checkable statements; read back by `design_writer.py render` into each top-N finding's `### Remediation` and `### Acceptance criteria` sections via `notes_by_fingerprint`, which drops an entry whose fingerprint is not in `ranked.json`'s `top_n`, whose `remediation` is not a non-empty string, or whose `acceptance_criteria` is not a list of strings; a missing or malformed `notes.json` renders `NOTE_PLACEHOLDER` (`remediation note not available`) in both sections instead of failing |
| `design.md` | `design_writer.py render` | v2 frontmatter (`schema_version: 2`, `scan_date`, `root`, `total_files`, `total_loc`, `languages`, `preset`, `families_run`, `families_skipped`, `tools_run`, `tools_absent`, `git_available`, `counts{candidates, quote_failed, verified, tier_a, tier_b, tier_c, unverified, rejected, suppressed}` plus `new` and `resolved` when `diff.json` is present), written as literal YAML lines with an empty list as `key: []`; `tools_run` names every tool `tool-signals.json` records as `ran` and `tools_absent` every other tool with its status in parentheses (`absent`, `failed`, `skipped`, or `unknown` for a status the four do not cover), so spec 4.5's "names every absent tool" holds and a `--no-tools` run (ten `skipped`) is not the same document as a full probe — both lists are empty when the workdir has no `tool-signals.json` at all; then the scan header and the seven body sections in order — `# Top N`, `# Below the cut`, `# Below the cut: tier C and unverified`, `# Considered and rejected`, `# Looks bad but is fine`, `# Open questions for the maintainer`, `# Not assessed`. A finding is an H2 whose fenced `yaml` anchor carries `status`, `slug`, `fingerprint`, `tier`, `priority`, `family`, `category`, `debt_type`, `type_id`, `severity`, `effort` and `diff`; every other section is an H1, which ends the preceding finding's body so it is never copied into a PBI. `# Top N` carries a full H2 per top-N finding (`### Proof`, `### Evidence`, `### Signals`, `### Remediation`, `### Acceptance criteria`) and `# Below the cut` a compact H2 — the same anchor, then `### Proof` and `### Evidence` only — per tier A or B finding outside the top N, so it is promotable without the note agent's sections; `# Below the cut: tier C and unverified` is a `slug \| family \| file \| reason` table, one row per tier C or `unverified` finding, the reason being `verified.json`'s `tier_reason` (the prose for how it landed there) rather than the bare verdict word; `# Considered and rejected` is one bullet per `reject`, naming the bolded title, the primary evidence file and the verifier's proof — replaced by `trap_matched` when the verifier matched a trap; `# Looks bad but is fine` merges `candidates.json`'s `looks_bad_but_fine` entries with those trap rejections; `# Open questions for the maintainer` lists `candidates.json`'s `open_questions`, prefixed `quote not found: ` when that was the reason; `# Not assessed` names the skipped families, the modules a chunked plan's `max_modules` bound dropped (with their lead counts, when there are any), and the three standing limits (tools, runtime-only, by design). An empty section renders `_None._`, and an evidence quote is fenced with one more backtick than its own longest backtick run |
| `findings.json` | `design_writer.py render` | `{schema_version: 2, findings[{fingerprint, slug, title, family, debt_type, type_id, severity, effort, evidence, signals, confirmed_by, source, rule_id, tool, tier, verdict, proof, priority, terms, in_top_n, spread_capped, diff}]}`, written beside `design.md`: the machine-readable twin of the same findings, in the same order (`ranked.json` order, then any verified finding with no rank entry). `evidence` is `verified.json`'s items with the quotes redacted; `title` and `proof` are redacted too; `source`, `rule_id` and `tool` are copied from the verified finding unchanged, naming its producer; `priority` and `terms` come from the rank entry (`null` and `{}` when there is none), `in_top_n` from membership of `ranked.json`'s `top_n`, and `diff` from `diff.json` (`NEW` when absent). `evaluate.py` prefers this file over `verified.json` |
| `chore-<slug>-<date>/` | `promote.py` | a PBI bundle: `PBI.md`, `PLAN.md`, `HISTORY.md`. `PBI.md`'s frontmatter carries `fingerprint`, `tier`, `type_id`, `family`, `debt_type` and `effort` after `category` when the finding's anchor has them (v2; a v1 finding's bundle is unchanged, spec 8), never `priority`. `PLAN.md` lists the finding's own `### Acceptance criteria` checklist, numbered in order, or the one-step stub when there is none |
| `evaluation.json` | `live_run.py` (the `evaluate.py` report), evaluation only, not part of `/tech-debt-scan` | `{schema_version: 2, source, top, churn_months, families{<family>: {planted, found, recall, reported, precise, precision, decoy_hits{A, B, C}}}, planted[{id, family, found, tiers[], tier_met}], decoys[{id, family, hit_tiers[], in_top_n}], decoys_in_tier_a, decoys_in_top_n, tier_a{reported, precise, precision}, counts{reported, on_planted, on_decoys, unplanted}}`; written only when the target carries a `planted.json`, and the same report is printed as a table and condensed into the `docs/evaluation-log.md` row. `source` is the file scored, `"findings.json"` or `"verified.json"` (whichever `evaluate.load_findings` found; `live_run.py` prefers `findings.json`). A finding counts as `reported` at tier A or B; `tier_a.precision` counts tier A alone, which is the release bar, while the per-family `precision` spans A and B. `churn_months` is the window the run was scored under (null when the fixture records none) |

All intermediate artefacts live under `.tech-debt/` in the scanned repo
(gitignore it). `/tech-debt-scan` runs the full v2 chain: the signals
(`inventory.py --workdir`, `patterns.py`, `rules.py`), then `plan_scan.py`,
the scout agents, `merge_findings.py`, `verify_prompts.py`, the verifier
agents, `apply_verdicts.py`, `rank.py`, the remediation-note agent
(`design_writer.py notes-prompt`) and `design_writer.py render`. `live_run.py`
drives the same chain end to end with real agents, for evaluation against the
fixture corpus (never in CI). Every threshold the chain uses comes from an
optional `.tech-debt.yaml` at the repository root; `python scripts/config.py
<repo>` prints the effective values. See
[`docs/architecture.md`](docs/architecture.md) for the full design, the debt
families, and the validation rules.

## Language support

Inventory and scouts are language-agnostic. The inventory classifies files by
extension; everything else is language-neutral. Recognised languages:

Python, C#, Java, Kotlin, TypeScript (`.ts`/`.tsx`), JavaScript (`.js`/`.jsx`),
Go, Rust, Ruby, PHP, Swift, C/C++ (`.c`/`.h`/`.cpp`/`.cc`/`.cxx`/`.hpp`), and
Markdown.

Files in common build/dependency directories (`node_modules`, `obj`, `target`,
`.venv`, `venv`, `__pycache__`, `dist`, `.git`, IDE and tool caches, and
`.tech-debt`) are skipped. A directory named `bin` or `build` is skipped when
it holds no package manifest and its parent is the repository root or holds a
manifest itself, which covers build output sitting beside the manifest that
produced it; a `bin` or `build` package nested under an ordinary source
directory is walked. Manifests, lockfiles, CI, container, IaC, SQL, notebook,
model-binary, config and governance files are inventoried as artefacts rather
than as code.

## Live evaluation

`live_run.py` runs the whole scan chain against a corpus fixture (or any
repository path) with real Claude scouts and verifiers. It refuses to run at
all when the workdir already holds a `diff.json` or a `baseline.json`, since
scoring there would set a bar from a filtered population (run again with a
fresh `--workdir`, or remove the file). `--tools` runs the external tool
probe first, writing `tool-signals.json` before planning so a tool lead can
reach a scout prompt and a tool candidate can corroborate a finding, the same
as any run where that file is already present. After ranking it
renders the remediation-note prompt and, when the top N is non-empty,
dispatches one more agent call for the single note agent, validated against
`NOTES_SCHEMA` and written to `notes.json`; it then renders `design.md` and
`findings.json` with `design_writer.write_design`, so a top-N finding the note
agent answered for carries a real remediation and acceptance criteria instead
of the placeholder. It scores `findings.json` (not `verified.json`) against
the fixture's planted debt and decoys, and appends a row to
[`docs/evaluation-log.md`](docs/evaluation-log.md) — date, fixture, model,
`churn_months` (the fixture's `planted.json` value when present, else
`--churn-months`, else the config default; a conflicting `--churn-months` is
ignored with a warning), `tier_a_precision` (tier A findings alone, the release
bar), `reported_precision` (the same ratio over tiers A and B), decoys at tier
A, decoys in the top N, per-family recall, the scout and verifier call counts,
the run's cost, and a trailing `notes` column: the count of top-N findings the
note agent actually filled in over the top-N size, e.g. `3/5`. A decoy's
`sources` list (exact tokens or a trailing-`*` prefix) restricts which
producers can hit it; a family mismatch is still decided first. `--keep <dir>`
copies `evaluation.json`, `design.md`, `notes.json` and `findings.json` into
`<dir>/<fixture-or-repo-name>` once scoring is done, so a run's documents can
be audited later without re-running the chain. `--planted <path>` scores a
plain repository against any fixture's planted file (or a hand-written one)
without copying it into the tree, overriding both the fixture's own
`planted.json` and a `<repo>/planted.json` lookup — so a paid run against a
fixture is one command: probe, score and keep, together.

```
python scripts/live_run.py service-py --model sonnet --max-budget-usd 1.00 \
    --tools --keep runs/2026-09-09
```

This costs real tokens and never runs in CI; the test suite drives the same
code path with a fake `claude` executable passed through `--claude`.

## Status

Human in the loop throughout — nothing is fixed automatically.

The v2 design ships in five phases. Phases 1 and 2 landed the deterministic
signals (`config.py`, inventory v2 with `coupling.json`, `patterns.py`,
`rules.py`) and the detect, verify and rank chain (`categories.py` v2's
fourteen family blocks, `plan_scan.py`, `merge_findings.py`,
`verify_prompts.py`, `apply_verdicts.py`, `rank.py`), with `evaluate.py`, the
fixture corpus, the goldens and the evaluation log that scores it. **Phase 3
is complete:** `design_writer.py`, `design_parser.py`, `bundle_writer.py` and
`promote.py` render and promote the v2 report, and `/tech-debt-scan` and
`/tech-debt-promote` now run this chain end to end. `--families deep` already
selects the full fourteen-family set today (`plan_scan.py`, phase 2).

**Phase 4 is complete.** Phase 4a built `tools_probe.py` and
`tool_normalisers.py`, which run ten already-installed external tools
(osv-scanner, gitleaks, ruff, vulture, lizard, jscpd, knip, madge, hadolint,
actionlint) — never installing anything and never invoking `npx` — and write
`tool-signals.json`. Phase 4b wired that file into the scan: `/tech-debt-scan`
step 4 gives the user a network notice (what osv-scanner sends to OSV.dev,
that every other tool is local-only, and how `tools.network: false` stays
offline — see `skills/tech-debt-scan/SKILL.md` for the exact wording) and
then runs the probe; `--no-tools` runs it with `--skip-all` instead, still
writing the file with every tool `skipped`.

Inference-class signals (ruff, vulture, lizard, jscpd, knip, madge) become
scout leads and `confirmed_by` corroboration that lifts several families'
tier caps; fact-class signals (osv-scanner, gitleaks, hadolint, actionlint)
become candidates, and an osv-scanner advisory is one of only **two** kinds
of finding that can reach tier A — the report's strongest,
most-likely-to-rank-first claim — without a verifier agent ever reading the
affected code; the other is a `rules.py` finding. Every other tool-raised
candidate, including gitleaks and hadolint findings, still goes through a
verifier before it can outrank anything. Long repositories are also chunked
into per-directory module scouts as of phase 4b. A gitleaks finding's
fingerprint now includes its column (phase 5b) when available, so on the first scan after
upgrading, gitleaks entries with a usable column read `UNCHANGED (edited)`
rather than `UNCHANGED`, while those without a usable column retain their pre-upgrade fingerprints and still read `UNCHANGED`; suppressions still carry across, because the tool's
message is the title and the edited heuristic matches it.

**Phase 5a is complete.** `baseline.py` (spec 4.10) diffs every current
finding against a committed `.tech-debt/baseline.json` and writes
`diff.json` (`/tech-debt-scan` step 11), so a re-scan's `design.md` carries
`diff: NEW`, `UNCHANGED`, `UNCHANGED (moved)` or `UNCHANGED (edited)` on
every finding, plus `new` and `resolved` counts in the frontmatter. The
fifth classification, `RESOLVED`, is the one a finding can never carry: it
names a baseline entry no current finding matched, so it lives in
`diff.json` and in that `resolved:` count alone. `/tech-debt-promote --baseline <path>` then writes each
finding's decision back — `promoted`, `rejected` or `accepted`, with its
reason and expiry — so a `rejected` finding stops recurring, an `accepted`
one returns once its `until` date passes, and the first write to a
gitignored baseline location appends the three-line gitignore triple that
tracks it while leaving the rest of the workdir ignored. A write-back
failure after the bundles are already emitted exits 6; the bundles and the
promoted statuses stay, and re-running promote picks up what it already
emitted rather than duplicating it. Phase 5b — the live-run measurement
that repairs the fixture corpus — has landed: the corpus repairs, the
note agent in the harness, and a live run on 2026-09-09 over all three
fixtures. That run set no bar, because a decoy reached tier A on
web-ts, so the provisional 0.80 figure stays until a run clears the
hard gate (see `docs/evaluation-log.md`).

"Mow the lawn" autonomy — applying fixes without review — is a separate
follow-on, deferred and out of scope.

## References

- [`docs/architecture.md`](docs/architecture.md) — full design, debt
  families, and validation rules (the spec content, inlined and kept current).
- [`skills/tech-debt-scan/SKILL.md`](skills/tech-debt-scan/SKILL.md) — the
  step-by-step workflow Claude follows.
- Canonical design spec:
  [`docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md`](docs/superpowers/specs/2026-09-04-tech-debt-scan-v2-design.md)
  in this repo.

## License

MIT. See [`LICENSE`](LICENSE).
