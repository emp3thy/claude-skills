# tech-debt-scan

Language-independent tech-debt scan skill for Claude Code. It walks any repo,
dispatches read-only LLM scout agents per debt category, synthesises the top-5
findings into a single `design.md`, and — after a human reviews and approves
findings — emits ralph-friendly PBI bundles you can drop into a queue.

Human in the loop: nothing is fixed automatically. The LLM does only the
judgement calls (dispatch scouts, pick the top 5, and in the v2 chain give the
per-candidate verdicts); every other step is a deterministic pure-Python script
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

   This inventories the repo, runs eight scout agents (one per category in
   `categories.CATEGORIES`), picks the top-5 debt items, and writes
   `.tech-debt/design.md`.

2. **Review** — open `.tech-debt/design.md`. Each finding has a `status:` field
   set to `pending`. Change it to `approved` to promote the finding, or
   `rejected` to drop it. Leave it `pending` to skip for now.

3. **Promote** — convert approved findings into PBI bundles:

   ```
   /tech-debt-promote
   ```

   This writes one `chore-<slug>-<date>/` bundle (`PBI.md`, `PLAN.md`,
   `HISTORY.md`) per approved finding under `./tech-debt-pbis`, then flips those
   findings to `promoted` so a re-run is a no-op.

See `skills/tech-debt-scan/SKILL.md` for the full step-by-step workflow Claude
follows, including every pinned command and pre/post-condition.

## Output formats

| Artefact | Written by | Shape |
| --- | --- | --- |
| `inventory.json` | `inventory.py` | `{schema_version: 2, root, total_files, total_loc, languages, git_available, churn_window_months, hotspots[], hotspot_band[], files[], artefacts{}, skipped_large_files, docs{}, tests{}, git{}, boundary_tooling[], lint_config[], signal_sources{}}`; each `files[]` entry carries `path_class`, `hotspot_score`, `inline_disables`, the git history fields (`last_touched`, `authors`, `top_author`, `top_author_share`, `top_author_line_share`, `bugfix_share`, `migration_commits`, `flaky_commits`, `untested_change_share`), `mapped_tests`, `fan_in_approx`, `fan_out_approx`, `fan_in_mode`, `coupling_degree` and `skipped_large`; each `artefacts{}` entry carries `{path, path_class, loc, churn, last_touched, size_bytes, skipped_large}` |
| `coupling.json` | `inventory.py` (with `--workdir`) | `{schema_version: 2, min_shared, min_ratio, bulk_threshold, fan_in_mode, pairs[], degree{}, cycles[], directories[], unstable_edges[]}` |
| `patterns.json` | `patterns.py` | `{schema_version: 2, leads{<family>: [{rule, file, line, quote, path_class, extra}]}, satd[], stats{}}`; a lead or SATD entry on an artefact carries the artefact's real `path_class` (a workflow under a tests tree reports `tests`, not `ci`) while rule scope still keys on the artefact class, and artefacts classed `generated` or `vendored` or marked `skipped_large` are not scanned; also fills `files[].inline_disables` in `inventory.json` |
| `rule-findings.json` | `rules.py` | `{schema_version: 2, findings[], leads{migration[]}}`; each finding is a candidate with `source: "rule"`, `tier: "A"`, `confirmed_by: ["rule:<id>"]` and the artefact's `path_class` in `signals`; artefacts under a tests, vendored or generated tree are skipped, and an artefact the inventory marked `skipped_large` is never read |
| `scan-plan.json` | `plan_scan.py` | `{schema_version: 2, set, top, chunked, thresholds{}, entries[{family, module, prompt, output, leads}], families_run[], families_skipped[{family, reason}]}` |
| `candidates.json` | `merge_findings.py` | `{schema_version: 2, candidates[], open_questions[{file, line_start, question, reason}], looks_bad_but_fine[{file, line_start, why}], stats{<family>: {raw, dropped, quote_failed, clustered, suppressed, disabled}}}`; each candidate is `{fingerprint, quote_hash, family, debt_type, type_id, title, severity, effort, source, rule_id, note, evidence[{file, line_start, line_end, quote, quote_verified}], confirmed_by[], signals_cited[], signals{}, tier}` with `tier: null` for scout candidates; a scout file the plan names but that is absent adds `missing_file: 1` to that family's stats; a family with at least one dropped item adds `dropped_reasons: []`, the reason string from each drop, appended after `missing_file` when both are present; rule findings keep `source: "rule"` and `tier: "A"` and are appended after the scout candidates |
| `verify-plan.json` | `verify_prompts.py` | `{schema_version: 2, top, batch_size, selected[], unverified[], batches[{prompt, output, fingerprints[]}]}`; `selected` is every fingerprint sent for verification, in batch order, and `unverified` every `tier: null` candidate the budget rule left out; tier A candidates are in neither list; each batch names the prompt written at `prompts/verify-<nn>.md` (two digits from 01) and the `output` path `verdicts/verify-<nn>.json` the read-only verifier's reply must be stored at, a JSON array of `{fingerprint, verdict, proof, severity, effort, trap_matched, checked[], opened[]}` with `verdict` one of `confirm`, `downgrade`, `reject`, `refer` |
| `verified.json` | `apply_verdicts.py` | `{schema_version: 2, findings[<candidate keys> + verdict, proof, checked, opened, trap_matched, verified], stats{selected, verdicts, unknown_fingerprint, missing_verdict, tier_a, tier_b, tier_c, rejected}}`; each finding is a candidate with `tier` overwritten by the earned tier (`A`/`B`/`C`/`null`, spec 4.8 plus the 2.3 family caps) and `verdict` one of `confirm`, `downgrade`, `reject`, `refer`, `rule` (tier-A candidates verified by construction) or `unverified` (not selected, or selected with no returned verdict; `verified: false`); a `reject` keeps `tier: null` with `verified: true` and its `proof` |
| `ranked.json` | `rank.py` | `{schema_version: 2, formula_version: 1, preset, top, weights{wH, wC, wF}, tractability{S, M, L}, top_n[], findings[{fingerprint, rank, priority, terms{severity, H, C, F, interest, tier_weight, tractability, priority}, tier, in_top_n, spread_capped}]}`; `findings` is every finding ordered by priority descending then fingerprint ascending (the tie-break), `rank` numbering that order; `top_n` is the fingerprints, in that same order, of the findings that made the top `top` under the chosen `preset` (`balanced`, `hotspot-first`, `architecture` or `quick-wins`) — tier A and B only, minus (under `quick-wins`) uncorroborated duplication and every ownership finding, capped at `ceil(spread_cap x top)` per family with the excess marked `spread_capped: true`; byte-identical for identical inputs |
| `evaluation.json` | `live_run.py` (the `evaluate.py` report) | `{schema_version: 2, top, churn_months, families{<family>: {planted, found, recall, reported, precise, precision, decoy_hits{A, B, C}}}, planted[{id, family, found, tiers[], tier_met}], decoys[{id, family, hit_tiers[], in_top_n}], decoys_in_tier_a, decoys_in_top_n, tier_a{reported, precise, precision}, counts{reported, on_planted, on_decoys, unplanted}}`; written only when the target carries a `planted.json`, and the same report is printed as a table and condensed into the `docs/evaluation-log.md` row. A finding counts as `reported` at tier A or B; `tier_a.precision` counts tier A alone, which is the release bar, while the per-family `precision` spans A and B. `churn_months` is the window the run was scored under (null when the fixture records none) |
| `raw-findings.json` | Claude (from scouts) | `[{title, severity, category, debt_type, effort, confidence, evidence[{file, line, note}], suggested_fix}]`; `title` at most 80 characters, `suggested_fix` at most 500, `severity` an integer 1-5, and `debt_type`, `effort` and `confidence` validated by `validation.py` when present |
| `top5.json` | synthesis Agent | `{top5: [{slug, title, severity, category, reasoning, evidence, suggested_fix}]}`, exactly as many items as `build_synthesis_prompt.py --top` asked for (default 5); the key stays `top5` whatever the count |
| `design.md` | `design_writer.py render` | frontmatter + one H2 section per finding, each with a `yaml` status anchor |
| `chore-<slug>-<date>/` | `promote.py` | a PBI bundle: `PBI.md`, `PLAN.md`, `HISTORY.md` |

All intermediate artefacts live under `.tech-debt/` in the scanned repo (gitignore
it). The v2 scripts run by hand for now, in this order: the signals
(`inventory.py --workdir`, `patterns.py`, `rules.py`), then the chain
(`plan_scan.py`, the scout agents, `merge_findings.py`, `verify_prompts.py`, the
verifier agents, `apply_verdicts.py`, `rank.py`) and `evaluate.py`;
`live_run.py` drives all of it end to end with real agents. `/tech-debt-scan`
still follows the v1 steps until phase 3. Every threshold they use comes from an
optional `.tech-debt.yaml` at the repository root; `python scripts/config.py
<repo>` prints the effective values. See
[`docs/architecture.md`](docs/architecture.md) for the full design, the debt
categories, and the validation rules.

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
repository path) with real Claude scouts and verifiers, scores the result
against the fixture's planted debt and decoys, and appends a row to
[`docs/evaluation-log.md`](docs/evaluation-log.md) — date, fixture, model,
`churn_months` (the fixture's `planted.json` value when present, else
`--churn-months`, else the config default; a conflicting `--churn-months` is
ignored with a warning), `tier_a_precision` (tier A findings alone, the release
bar), `reported_precision` (the same ratio over tiers A and B), decoys at tier
A, decoys in the top N, per-family recall, the scout and verifier call counts
and the run's cost:

```
python scripts/live_run.py service-py --model sonnet --max-budget-usd 1.00
```

This costs real tokens and never runs in CI; the test suite drives the same
code path with a fake `claude` executable passed through `--claude`.

## Status

Human in the loop throughout — nothing is fixed automatically.

The v2 design ships in five phases. Phase 1 landed the deterministic signals
(`config.py`, inventory v2 with `coupling.json`, `patterns.py`, `rules.py`,
`evaluate.py`, the fixture corpus). Phase 2 lands the detect, verify and rank
chain — `categories.py` v2 with its fourteen family blocks, `plan_scan.py`,
`merge_findings.py`, `verify_prompts.py`, `apply_verdicts.py` and `rank.py` —
runnable by hand or behind the `live_run.py` harness, with the goldens and the
evaluation log that scores it; `/tech-debt-scan` still runs v1. Phase 3 rewrites
the report and cuts SKILL.md over to the v2 chain; phases 4 and 5 add external
tools and the baseline.

"Mow the lawn" autonomy — applying fixes without review — is a separate
follow-on, deferred and out of scope.

## References

- [`docs/architecture.md`](docs/architecture.md) — full design, categories, and
  validation rules (the spec content, inlined).
- [`skills/tech-debt-scan/SKILL.md`](skills/tech-debt-scan/SKILL.md) — the
  step-by-step workflow Claude follows.
- Canonical design spec:
  `docs/superpowers/specs/2026-05-31-tech-debt-scan-design.md` in the private
  `ralph` repo (not linkable from here; inlined into `docs/architecture.md`).

## License

MIT. See [`LICENSE`](LICENSE).
