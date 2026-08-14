---
name: tech-debt-scan
description: Scan a repo for top-5 tech-debt findings; emit a design doc the user reviews, then convert approved findings to ralph-friendly PBI bundles.
triggers:
  - /tech-debt-scan
  - /tech-debt-promote
---

# tech-debt-scan

Language-independent, two-command tech-debt workflow. `/tech-debt-scan` walks a
repo, dispatches read-only scout agents per debt category, synthesises the top-5
findings, and renders a single `design.md`. The user edits `design.md` (flipping
`status: pending` to `approved` or `rejected`). `/tech-debt-promote` then parses
the edited file and emits a ralph-ready PBI bundle per approved finding.

Deterministic work (file walk, prompt rendering, parsing, validation, bundle
writing) lives in pure-Python scripts under `scripts/`. The LLM does only two
things: dispatch scout agents and pick the top 5. Everything else is a script
call with a pinned command and a pinned output file.

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

- Postcondition: `.tech-debt/inventory.json` exists (a JSON object with
  `root`, `total_files`, `total_loc`, `languages`, `files`). If it is missing,
  abort with exit 5.

### Step 2 — Dispatch scout agents (one per category)

- Prerequisite: `.tech-debt/inventory.json`.
- There is no script here. The seven categories are defined in
  `scripts/categories.py` (`CATEGORIES` + `get_prompt(name)`): `god-modules`,
  `duplication`, `dead-code`, `test-gaps`, `doc-drift`, `half-finished`,
  `infrastructure-debt`.
- For each category, dispatch one **read-only** Agent (Explore semantics) whose
  prompt is `get_prompt(<category>)`. Pass the inventory as a file path
  (`--inventory .tech-debt/inventory.json`) — never inline the JSON.
- Each scout returns a JSON array of findings, each with
  `title`, `severity` (1-5), `category`, `evidence` (`[{file,line,note}]`),
  `suggested_fix`.
- Postcondition: seven in-memory finding lists. If a scout returns nothing, record
  an empty list for that category and continue.

### Step 3 — Persist raw findings

- Prerequisite: the six scout result lists from Step 2.
- Concatenate every scout's findings into one JSON array and write it:

```bash
# Claude writes this file directly (no script):
#   .tech-debt/raw-findings.json  ->  [ {title, severity, category, evidence, suggested_fix}, ... ]
```

- Postcondition: `.tech-debt/raw-findings.json` exists. If it is missing, abort
  with exit 5.

### Step 4 — Build the synthesis prompt and pick the top 5

- Prerequisite: `.tech-debt/raw-findings.json`.
- Command:

```bash
python scripts/build_synthesis_prompt.py .tech-debt/raw-findings.json --inventory .tech-debt/inventory.json --out .tech-debt/synthesis-prompt.txt
```

- Send the rendered prompt to a synthesis Agent. It returns JSON with a `top5`
  array (exactly 5 items: `slug`, `title`, `severity`, `category`, `reasoning`,
  `evidence`, `suggested_fix`, `confidence`, `change_size`, `change_risk`,
  `disposition`, `why_now`, `scope_boundary`, `acceptance_criteria`). Write that
  response to `.tech-debt/top5.json`.
- When `.git` is present, findings are ranked by `severity × log1p(git_churn)`; otherwise by severity alone.
- On validation failure (the response is not valid JSON, not exactly 5 items, a
  bad slug, or a severity/category out of range), write the raw response to
  `.tech-debt/synthesis-failed-<timestamp>.json` and retry the synthesis prompt
  once with an appended "previous response failed schema; re-emit valid JSON".
  On a second failure, abort with exit 5.
- Postcondition: `.tech-debt/top5.json` exists and passes
  `build_synthesis_prompt.validate_synthesis_output`. If `raw-findings.json` held
  more than 30 findings, the builder logs how many were truncated (top-30 by
  severity).

### Step 5 — Render the design doc

- Prerequisite: `.tech-debt/top5.json` and `.tech-debt/inventory.json`.
- Command:

```bash
python scripts/design_writer.py render --top5 .tech-debt/top5.json --inventory .tech-debt/inventory.json --scan-date <YYYY-MM-DD> --out .tech-debt/design.md
```

- Postcondition: `.tech-debt/design.md` exists. The renderer re-parses its own
  output as a self-check; if that fails the command exits non-zero — abort with
  exit 5.

### Step 6 — Report to the user

- Tell the user where `design.md` is and what to do: review each finding, set
  each `status:` to `approved` or `rejected` (leave `pending` to skip), then run
  `/tech-debt-promote`. Do not promote on their behalf.

## `/tech-debt-promote` workflow

### Step 1 — Locate the edited design doc

- Prerequisite: a `design.md` the user has edited (default `.tech-debt/design.md`).
- Postcondition: the file exists. If missing, abort with exit 5.

### Step 2 — (Optional) Inspect the parsed findings

- Command:

```bash
python scripts/design_parser.py .tech-debt/design.md
```

- This prints the parsed findings as JSON to stdout. Use it to confirm statuses
  before promoting. It mutates nothing.

### Step 3 — Promote approved findings

- Prerequisite: the edited `design.md`.
- Command:

```bash
python scripts/promote.py .tech-debt/design.md --out ./tech-debt-pbis
```

- This parses the design, writes one PBI bundle per `approved` finding under
  `--out`, then flips those findings to `promoted` in `design.md` so a re-run is
  a no-op. Add `--force` to overwrite an existing bundle directory.
- Postcondition: a `chore-<slug>-<date>/` directory (with `PBI.md`, `PLAN.md`,
  `HISTORY.md`) under `./tech-debt-pbis` for each approved finding.

### Step 4 — Report and hand off

- Print the promote summary (emitted / already-promoted / rejected / pending
  counts). Tell the user the bundles are under `./tech-debt-pbis`. To queue one,
  copy a `chore-<slug>-<date>/` directory into the ralph queue's inbox and commit
  it with `chore(queue): add <id>`. This skill does not commit on the user's
  behalf.

## Token budget

A full scan dispatches seven scout agents plus one synthesis agent. Budget roughly
60-80k output tokens per scan (scout findings dominate). The scripts themselves
do no LLM work and are effectively free.

## Caveats

- **No live LLM in CI.** Tests never call an Agent; they feed canned JSON to the
  scripts. The `live` pytest marker is off by default.
- **Exit codes.** `inventory.py`: 2 on a bad path. `promote.py`: 0 success, 2 on
  a parse / mark-promoted error, 4 on a bundle-write failure after at least one
  bundle was written (roll-forward — the succeeded bundles persist).
- **Collision policy.** `promote.py` treats an existing bundle directory as
  already-promoted (counted, not re-emitted) unless `--force` is given.
- **Single-user.** Do not run two promotes against the same `design.md`
  concurrently; there is no file locking in Phase 1.
