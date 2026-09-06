---
name: tech-debt-scan
description: Scan a repo for top-N tech-debt findings via a hotspot-aware detect-verify-rank pipeline (churn x complexity, then family-scoped scouts, verification, and ranking); emit a design doc the user reviews, then convert approved findings to ralph-friendly PBI bundles.
triggers:
  - /tech-debt-scan
  - /tech-debt-promote
---

# tech-debt-scan

Language-independent, two-command tech-debt workflow. `/tech-debt-scan` walks a
repo, mines git history for hotspots, then runs a three-stage pipeline —
**detect** (deterministic signal scripts plus one scout agent per debt
family), **verify** (read-only verifier agents apply per-family questions and
traps to the candidates a deterministic budget selects), **rank** (a fixed
priority formula orders the survivors) — and renders a single `design.md`. The
user edits `design.md` (flipping `status: pending` to `approved`, `rejected`,
or `accepted`). `/tech-debt-promote` then parses the edited file and emits a
ralph-ready PBI bundle per approved finding.

Deterministic work (file walk, churn mining, pattern and rule mining,
candidate merging, verification prompts, ranking, prompt rendering, parsing,
validation, bundle writing) lives in pure-Python scripts under `scripts/`. The
LLM does only three things: run each dispatched family's scout, verify a batch
of candidates, and write one remediation note per top-N finding. No agent
picks the final list or its order — the deterministic ranking formula does.

## Methodology

The scan is grounded in three published ideas:

- **Hotspot analysis** (Tornhill, *Your Code as a Crime Scene*): debt interest
  is proportional to how often the code is touched. `inventory.py` mines
  per-file **churn** (commits in a window, default 12 months) and a
  language-agnostic **complexity** proxy (indentation units), then ranks files
  by normalised churn x complexity (`hotspot_score`, `hotspot_band`). Debt in
  a hotspot is re-paid on every change; debt in cold code can usually wait.
- **Debt taxonomy** (SATD / Alves et al.): every finding carries a `debt_type`
  (code, design, architecture, test, documentation, dependency, build,
  requirement, security, infrastructure, knowledge-process, defect) on top of
  its **family** (one of fourteen, `scripts/categories.py`'s `FAMILY_BLOCKS`)
  and an optional `type_id` (`TD-01` to `TD-35`), so reports can be sliced by
  the kind of liability, not just by which family found it.
- **Detect, verify, rank.** Rule scripts and family-scoped scout agents emit
  candidates; read-only verifier agents apply each family's questions and
  known-non-debt traps to the candidates a signal budget selects, earning
  every candidate a tier (A confirmed and corroborated, B confirmed or
  downgraded, C unverified or capped); a fixed formula (severity x interest x
  tier weight x tractability) then scores every verified finding and takes
  the top N. No agent orders the list — the formula does.

## No improvisation

If any expected output file from a numbered step is missing, abort with exit 5. Do not retry steps you weren't told to retry. Do not invent intermediate state. Do not skip steps.

## When to use

- `/tech-debt-scan <repo-path>` — produce a reviewable `design.md` of the worst
  debt in a repo. Run it against any language; the scripts and scout prompts
  are language-agnostic.
- `/tech-debt-promote` — after a human has reviewed `design.md` and marked
  findings `approved`, `rejected` or `accepted`, convert the approved ones
  into PBI bundles you can paste into a ralph queue.

Human-in-the-loop throughout. There is no autonomous "fix it" step. This is
delivery phase 3: the scan runs without external tool signals or a baseline
diff; phases 4 and 5 add them.

## Flags

`/tech-debt-scan <repo> [--quick | --deep] [--preset balanced|hotspot-first|architecture|quick-wins] [--families a,b,c] [--top N]`.
`--quick` selects the quick family set (six families) and `--top 3`; `--deep`
selects the deep family set (all fourteen families, `plan_scan.py --families
deep`); `--families` overrides both and bypasses the adaptive rule.

## Conventions

- All intermediate artefacts live under `.tech-debt/` in the scanned repo (or
  the current directory). The directory is gitignored.
- All script commands below are run from the skill's `skills/tech-debt-scan/`
  directory so the `scripts/<name>.py` paths resolve. Each script is
  direct-path invocable (`python scripts/<name>.py`), no `-m`, no package
  install.
- Large intermediate data (the inventory, leads, evidence spans) always passes
  between steps as a **file path** under `--workdir`, never inline JSON on an
  argv or hand-built into a prompt — a large inventory would blow the Windows
  8191-char argv ceiling. `plan_scan.py` and `verify_prompts.py` render the
  scout and verifier prompts as files for the same reason; dispatch each
  Agent with the prompt file's content, not a hand-built one.
- `--workdir` (default `.tech-debt`) is the directory every chain script, from
  `inventory.py` through `design_writer.py render`, reads its inputs from and
  writes its outputs to. Pass the same `--workdir` to every command in one
  scan.

## Scan steps

Step numbers are fixed across phases: this phase ships the list without steps
4 and 11, which phases 4 and 5 insert without renumbering.

1. `python scripts/inventory.py <repo> --workdir .tech-debt` writes
   `inventory.json` and `coupling.json`. Add `--churn-months <n>` to change
   the window. When `git_available` is false, `churn` is 0, `hotspots` is
   empty and the history fields are null; say so in the report.
2. `python scripts/patterns.py <repo> --workdir .tech-debt` writes
   `patterns.json` and fills `inline_disables` in `inventory.json`.
3. `python scripts/rules.py <repo> --workdir .tech-debt` writes
   `rule-findings.json`.
5. `python scripts/plan_scan.py --workdir .tech-debt --families <set> --top <n>`
   writes `scan-plan.json` and `prompts/scout-*.md`; `<set>` is `default`,
   `quick`, `deep` or a comma-separated list.
6. Dispatch one read-only Agent per plan entry with the prompt file's
   content; write each response verbatim to the output path the plan names.
   A missing output file after dispatch is exit 5; an empty findings list is
   not.
7. `python scripts/merge_findings.py --workdir .tech-debt` writes
   `candidates.json`.
8. `python scripts/verify_prompts.py --workdir .tech-debt --top <n>` writes
   `prompts/verify-*.md` and `verify-plan.json`; dispatch one read-only Agent
   per batch; write each response to the `verdicts/verify-<nn>.json` path the
   plan names.
9. `python scripts/apply_verdicts.py --workdir .tech-debt` writes
   `verified.json`.
10. `python scripts/rank.py --workdir .tech-debt --preset <p> --top <n>`
    writes `ranked.json`.
12. `python scripts/design_writer.py notes-prompt --workdir .tech-debt --top <n>`
    writes `prompts/notes.md`; dispatch one read-only Agent; write
    `notes.json`.
13. `python scripts/design_writer.py render --workdir .tech-debt --scan-date <date> --out .tech-debt/design.md`
    writes `design.md` and `findings.json`, self-checking through the parser;
    a non-zero exit is exit 5.
14. Report: the path, the counts from the frontmatter, tools absent, git
    absent, families skipped, and the instruction to set each `status:` to
    `approved`, `rejected` or `accepted` (with `reason:` and optional
    `until:`) and run `/tech-debt-promote`. Never promote on the user's
    behalf.

## Promote steps

1. Locate the edited `design.md` (default `.tech-debt/design.md`); missing is
   exit 5.
2. Optional: `python scripts/design_parser.py .tech-debt/design.md` prints
   the parsed findings as JSON and mutates nothing.
3. `python scripts/promote.py .tech-debt/design.md --out ./tech-debt-pbis`
   writes one bundle per `approved` finding, flips them to `promoted` in
   `design.md` so a re-run is a no-op. Add `--force` to overwrite an existing
   bundle directory.
4. Report the counts (emitted, already promoted, rejected, accepted,
   pending) and the bundle location under `./tech-debt-pbis`. To queue a
   bundle, copy its `chore-<slug>-<date>/` directory into the ralph inbox and
   commit it as `chore(queue): add <id>`. This skill does not commit on the
   user's behalf.

## Token budget

| Scan | v1 | v2 quick | v2 default | v2 deep |
|---|---|---|---|---|
| Scout agents | 8 (4 quick) | 6 | 12 | 14, more with chunking |
| Verifier batches | 0 | 3 to 5 | 5 to 7 | 8 to 12 |
| Note agent | 1 top-N picker | 1 | 1 | 1 |
| Output tokens | 80 to 110k | 35 to 50k | 60 to 85k | 90 to 130k |
| Input tokens | unbounded reads | 250 to 400k | 500 to 800k | 0.8 to 1.3M |
| Script time | seconds | under 2 min | under 2 min | under 3 min |
| Tool time | none | 0 to 10 min | 0 to 10 min | 0 to 10 min |

Output stays near v1 because scouts are lead-driven and capped and there is no
separate agent call to pick the top N. Input grows because scouts and
verifiers read cited spans with context; the 40-lead cap, the adaptive rule
and the verifier budget bound it. Tool time is 0 in this phase — no external
tool runs until a later phase adds the network probe step.

## Caveats

- **No live LLM in CI.** Tests never call an Agent; they feed canned JSON to
  the scripts. The `live` pytest marker is off by default.
- **Churn is best-effort.** `inventory.py` shells out to `git log`; if git is
  missing, times out, or the path is not a repository, churn falls back to 0
  and `hotspots` is empty. This is never a fatal error.
- **Exit codes.** `inventory.py`: 2 on a bad path. `promote.py`: 0 success, 2
  on a parse / mark-promoted error, 4 on a bundle-write failure after at
  least one bundle was written (roll-forward — the succeeded bundles
  persist), 6 (`EXIT_WRITE_BACK`) reserved for phase 5's baseline write-back
  — no code path returns it yet.
- **Single-user.** Do not run two promotes against the same `design.md`
  concurrently; there is no file locking.
- **Backwards compatibility.** A v1 `design.md` (no `fingerprint`, `tier`,
  `priority` or `type_id` in its anchors) still parses, renders and promotes:
  `category` is read as `family`, a v1 `confidence` value is parsed and
  discarded, and `god-modules` as a category value still promotes. The v1
  top-N picker step and its files are gone with no shim: they are never
  produced or consumed, and nothing outside this repository reads them.
- **No tools or baseline yet.** This phase ships without external tool
  signals or a baseline diff: every `design.md` renders `tools_run` and
  `tools_absent` as empty lists, and every finding carries `diff: NEW`.
  Phases 4 and 5 add them.
