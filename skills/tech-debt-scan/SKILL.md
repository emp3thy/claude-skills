---
name: tech-debt-scan
description: Scan a repo for top-N tech-debt findings (hotspot-aware: churn x complexity); emit a design doc the user reviews, then convert approved findings to ralph-friendly PBI bundles.
triggers:
  - /tech-debt-scan
  - /tech-debt-promote
---

# tech-debt-scan

Language-independent, two-command tech-debt workflow. `/tech-debt-scan` walks a
repo, mines git history for hotspots, dispatches read-only scout agents per
debt category, synthesises the top-N findings (default 5), and renders a single
`design.md`. The user edits `design.md` (flipping `status: pending` to
`approved` or `rejected`). `/tech-debt-promote` then parses the edited file and
emits a ralph-ready PBI bundle per approved finding.

Deterministic work (file walk, churn mining, prompt rendering, parsing,
validation, bundle writing) lives in pure-Python scripts under `scripts/`. The
LLM does only two things: dispatch scout agents and pick the top N. Everything
else is a script call with a pinned command and a pinned output file.

## Methodology

The scan is grounded in three published ideas:

- **Hotspot analysis** (Tornhill, *Your Code as a Crime Scene*): debt interest
  is proportional to how often the code is touched. `inventory.py` mines
  per-file **churn** (commits in a window, default 12 months) and a
  language-agnostic **complexity** proxy (indentation units), then ranks files
  by normalised churn x complexity. Debt in a hotspot is re-paid on every
  change; debt in cold code can usually wait.
- **Debt taxonomy** (SATD / Alves et al.): every finding carries a `debt_type`
  (code, design, architecture, test, documentation, dependency, build,
  requirement) on top of its scout category, so reports can be sliced by the
  kind of liability, not just by which scout found it.
- **Impact x interest x tractability ranking**: scouts emit `severity` (a fixed
  rubric), `effort` (S/M/L), and `confidence` (low/medium/high). A
  deterministic composite priority score (severity x effort weight x
  confidence weight x hotspot boost) pre-ranks findings before synthesis, and
  the synthesis model applies the same rubric when picking the final list.

## No improvisation

If any expected output file from a numbered step is missing, abort with exit 5. Do not retry steps you weren't told to retry. Do not invent intermediate state. Do not skip steps.

## When to use

- `/tech-debt-scan <repo-path>` — produce a reviewable `design.md` of the worst
  debt in a repo. Run it against any language; the scouts and scripts are
  language-agnostic.
- `/tech-debt-promote` — after a human has reviewed `design.md` and marked
  findings `approved`/`rejected`, convert the approved ones into PBI bundles you
  can paste into a ralph queue.

This is Phase 1 (human-in-the-loop). There is no autonomous "fix it" step.

## Flexibility knobs

All optional; defaults reproduce the standard scan.

| Knob | Where | Effect |
|------|-------|--------|
| `--churn-months <n>` | `inventory.py` | Git-history window for churn (default 12). |
| category subset | Step 2 | Dispatch fewer scouts. `categories.CORE_CATEGORIES` (god-modules, duplication, test-gaps, half-finished) is the recommended quick-scan set; the user can also name categories explicitly. |
| `--top <n>` | `build_synthesis_prompt.py` | Ask synthesis for n findings instead of 5. Pass the same n when validating (`validate_synthesis_output(text, expected_count=n)`). |
| `--inventory <path>` | `build_synthesis_prompt.py` | Enables hotspot-aware pre-ranking and injects the hotspot table into the synthesis prompt. Always pass it on a full scan. |

If the user asks for a "quick scan", use `CORE_CATEGORIES` and `--top 3`. If
they ask for a "deep scan" or "audit", dispatch all eight categories and
consider `--top 10`.

## Conventions

- All intermediate artefacts live under `.tech-debt/` in the scanned repo (or
  the current directory). The directory is gitignored.
- All script commands below are run from the skill's `skills/tech-debt-scan/`
  directory so the `scripts/<name>.py` paths resolve. Each script is
  direct-path invocable (`python scripts/<name>.py`), no `-m`, no package install.
- Scouts always receive the inventory as a **file path** (`--inventory <path>`),
  never inline JSON — a large inventory would blow the Windows 8191-char argv
  ceiling.

## `/tech-debt-scan` workflow

### Step 1 — Inventory the repo

- Prerequisite: a target repo path.
- Command:

```bash
python scripts/inventory.py <repo-path> --out .tech-debt/inventory.json
```

- Add `--churn-months <n>` to widen or narrow the churn window.
- Postcondition: `.tech-debt/inventory.json` exists (a JSON object with
  `schema_version`, `root`, `total_files`, `total_loc`, `languages`,
  `git_available`, `churn_window_months`, `hotspots`, `hotspot_band`, `files`,
  `artefacts`, `docs`, `tests`, `git`; each file entry carries `loc`,
  `complexity`, `max_indent`, `churn`, `path_class`, `hotspot_score`). If it is
  missing, abort with exit 5. When `inventory.py` is run with `--workdir
  .tech-debt` instead of `--out`, it also writes `.tech-debt/coupling.json`; the
  command above with `--out` is unchanged and writes only the inventory.
- When `git_available` is false (no git, or not a repository), churn is 0 and
  `hotspots` is empty — the scan still works, it just loses the interest
  signal. Mention this in the final report.

### Step 2 — Dispatch scout agents (one per category)

- Prerequisite: `.tech-debt/inventory.json`.
- There is no script here. The eight categories are defined in
  `scripts/categories.py` (`CATEGORIES` + `get_prompt(name)`): `god-modules`,
  `duplication`, `dead-code`, `test-gaps`, `doc-drift`, `half-finished`,
  `dependency-debt`, `architecture`. For a quick scan, dispatch only
  `CORE_CATEGORIES`.
- For each category, dispatch one **read-only** Agent (Explore semantics) whose
  prompt is `get_prompt(<category>)`. Pass the inventory as a file path
  (`--inventory .tech-debt/inventory.json`) — never inline the JSON. The
  prompts already tell the scout to use the inventory's `hotspots`, `churn`,
  and `complexity` fields as a severity amplifier.
- Each scout returns a JSON array of findings, each with
  `title`, `severity` (1-5, fixed rubric), `category`, `debt_type`, `effort`
  (S/M/L), `confidence` (low/medium/high), `evidence` (`[{file,line,note}]`),
  `suggested_fix`.
- Postcondition: one in-memory finding list per dispatched category. If a scout
  returns nothing, record an empty list for that category and continue.

### Step 3 — Persist raw findings

- Prerequisite: the scout result lists from Step 2.
- Concatenate every scout's findings into one JSON array and write it:

```bash
# Claude writes this file directly (no script):
#   .tech-debt/raw-findings.json  ->  [ {title, severity, category, debt_type, effort, confidence, evidence, suggested_fix}, ... ]
```

- Postcondition: `.tech-debt/raw-findings.json` exists. If it is missing, abort
  with exit 5.

### Step 4 — Build the synthesis prompt and pick the top N

- Prerequisite: `.tech-debt/raw-findings.json`.
- Command:

```bash
python scripts/build_synthesis_prompt.py .tech-debt/raw-findings.json --inventory .tech-debt/inventory.json --out .tech-debt/synthesis-prompt.txt
```

- Add `--top <n>` when the user asked for a different count (default 5).
- The builder pre-ranks findings by the composite priority score (severity x
  effort weight x confidence weight x hotspot boost) and truncates to the top
  30 by that score, logging how many were dropped.
- Send the rendered prompt to a synthesis Agent. It returns JSON with a `top5`
  array (exactly N items — the key is named `top5` regardless of N: `slug`,
  `title`, `severity`, `category`, `debt_type`, `effort`, `confidence`,
  `reasoning`, `evidence`, `suggested_fix`). Write that response to
  `.tech-debt/top5.json`.
- On validation failure (the response is not valid JSON, not exactly N items, a
  bad slug, or a severity/category/debt_type/effort/confidence out of range),
  write the raw response to `.tech-debt/synthesis-failed-<timestamp>.json` and
  retry the synthesis prompt once with an appended "previous response failed
  schema; re-emit valid JSON". On a second failure, abort with exit 5.
- Postcondition: `.tech-debt/top5.json` exists and passes
  `build_synthesis_prompt.validate_synthesis_output` (pass `expected_count=n`
  when `--top` was used).

### Step 5 — Render the design doc

- Prerequisite: `.tech-debt/top5.json` and `.tech-debt/inventory.json`.
- Command:

```bash
python scripts/design_writer.py render --top5 .tech-debt/top5.json --inventory .tech-debt/inventory.json --scan-date <YYYY-MM-DD> --out .tech-debt/design.md
```

- Postcondition: `.tech-debt/design.md` exists. Each finding's yaml anchor
  carries `status`, `slug`, `severity`, `category`, and (when present)
  `debt_type`, `effort`, `confidence`. The renderer re-parses its own output as
  a self-check; if that fails the command exits non-zero — abort with exit 5.

### Step 6 — Report to the user

- Tell the user where `design.md` is and what to do: review each finding, set
  each `status:` to `approved` or `rejected` (leave `pending` to skip), then run
  `/tech-debt-promote`. Do not promote on their behalf.
- Include a one-line hotspot summary (top 3 hotspot files and whether any
  finding sits in one), and note if `git_available` was false.

## `/tech-debt-promote` workflow

### Step 1 — Locate the edited design doc

- Prerequisite: a `design.md` the user has edited (default `.tech-debt/design.md`).
- Postcondition: the file exists. If missing, abort with exit 5.

### Step 2 — (Optional) Inspect the parsed findings

- Command:

```bash
python scripts/design_parser.py .tech-debt/design.md
```

- This prints the parsed findings as JSON to stdout (including any
  `debt_type`/`effort`/`confidence` carried in the anchors). Use it to confirm
  statuses before promoting. It mutates nothing.

### Step 3 — Promote approved findings

- Prerequisite: the edited `design.md`.
- Command:

```bash
python scripts/promote.py .tech-debt/design.md --out ./tech-debt-pbis
```

- This parses the design, writes one PBI bundle per `approved` finding under
  `--out`, then flips those findings to `promoted` in `design.md` so a re-run is
  a no-op. Add `--force` to overwrite an existing bundle directory. PBI
  frontmatter carries `debt_type` and `effort` when the design has them.
- Postcondition: a `chore-<slug>-<date>/` directory (with `PBI.md`, `PLAN.md`,
  `HISTORY.md`) under `./tech-debt-pbis` for each approved finding.

### Step 4 — Report and hand off

- Print the promote summary (emitted / already-promoted / rejected / pending
  counts). Tell the user the bundles are under `./tech-debt-pbis`. To queue one,
  copy a `chore-<slug>-<date>/` directory into the ralph queue's inbox and commit
  it with `chore(queue): add <id>`. This skill does not commit on the user's
  behalf.

## Token budget

A full scan dispatches eight scout agents plus one synthesis agent. Budget
roughly 80-110k output tokens per scan (scout findings dominate). A quick scan
(`CORE_CATEGORIES`, four scouts) is roughly half that. The scripts themselves
do no LLM work and are effectively free.

## Caveats

- **No live LLM in CI.** Tests never call an Agent; they feed canned JSON to the
  scripts. The `live` pytest marker is off by default.
- **Churn is best-effort.** `inventory.py` shells out to `git log`; if git is
  missing, times out, or the path is not a repository, churn falls back to 0
  and `hotspots` is empty. This is never a fatal error.
- **Exit codes.** `inventory.py`: 2 on a bad path. `promote.py`: 0 success, 2 on
  a parse / mark-promoted error, 4 on a bundle-write failure after at least one
  bundle was written (roll-forward — the succeeded bundles persist).
- **Collision policy.** `promote.py` treats an existing bundle directory as
  already-promoted (counted, not re-emitted) unless `--force` is given.
- **Single-user.** Do not run two promotes against the same `design.md`
  concurrently; there is no file locking in Phase 1.
- **Backwards compatibility.** Designs and top5 payloads produced by the
  previous version (no `debt_type`/`effort`/`confidence`) still parse, render,
  and promote; the new fields are validated only when present.
