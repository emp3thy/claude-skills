# tech-debt-scan

Language-independent tech-debt scan skill for Claude Code. It walks any repo,
dispatches read-only LLM scout agents per debt category, synthesises the top-5
findings into a single `design.md`, and — after a human reviews and approves
findings — emits ralph-friendly PBI bundles you can drop into a queue.

Phase 1 is human-in-the-loop: nothing is fixed automatically. The LLM does only
two things (dispatch scouts, pick the top 5); every other step is a deterministic
pure-Python script with a pinned command and a pinned output file.

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

   This inventories the repo, runs six scout agents, picks the top-5 debt items,
   and writes `.tech-debt/design.md`.

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
| `raw-findings.json` | Claude (from scouts) | `[{title, severity, category, evidence, suggested_fix}]` |
| `top5.json` | synthesis Agent | `{top5: [{slug, title, severity, category, reasoning, evidence, suggested_fix}]}` (exactly 5) |
| `design.md` | `design_writer.py render` | frontmatter + one H2 section per finding, each with a `yaml` status anchor |
| `chore-<slug>-<date>/` | `promote.py` | a PBI bundle: `PBI.md`, `PLAN.md`, `HISTORY.md` |

All intermediate artefacts live under `.tech-debt/` in the scanned repo (gitignore
it). The v2 signal scripts (`inventory.py --workdir`, `patterns.py`, `rules.py`,
`evaluate.py`) run by hand for now; `/tech-debt-scan` still follows the v1 steps
until phase 3. Every threshold they use comes from an optional `.tech-debt.yaml`
at the repository root; `python scripts/config.py <repo>` prints the effective
values. See [`docs/architecture.md`](docs/architecture.md) for the full design,
the debt categories, and the validation rules.

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

## Status

Phase 1 (human-in-the-loop) only. Phase 2 ("mow the lawn" autonomy — apply fixes
without review) is deferred and out of scope.

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
