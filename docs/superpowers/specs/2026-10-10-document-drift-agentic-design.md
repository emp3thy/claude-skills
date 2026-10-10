# document-drift: make the docs match the code, in both directions

Provenance: brainstormed 2026-10-10, after the first real run of the phase 1 skill (`docs/superpowers/specs/2026-10-09-document-drift-design.md`, PR #22) on the owner's `better-memory` repository. That run read 38 docs and 377 references, proposed no edit, and never opened a source file. The owner rejected the design: the point of the skill is that the docs match what the code does, and a gate built on git history cannot establish that. This spec supersedes the 2026-10-09 spec. It keeps that spec's command shape, exclusions, edit mechanics and commit grammar where they still fit, and replaces its core.

Fixed constraints, unchanged from the repository's skills: Claude Code skill; SKILL.md orchestration with pinned commands, pinned output files and the no-improvisation rule; pure Python 3.11+ with pyyaml as the only runtime dependency, every script direct-path invocable as `python scripts/<name>.py`; read-only Agent subagents for LLM work, each writing its own output file with the Write tool and replying with a receipt; large data passed between steps as file paths, never inline on an argv; redaction at every write of repository-derived text; LF-only output; no live LLM in tests; ruff, mypy strict, pytest and a SKILL.md linter in CI; every module `dd_`-prefixed and every test file `test_dd_*.py`.

## 0. Guardrails for planning and implementation

- **(a) Assumptions surfaced.** Section 12 lists every assumption with its cost if wrong.
- **(b) Confidence per task.** Every plan task carries a confidence percentage; anything under 90 percent is resolved by investigation, a question or a spike before implementation.
- **(c) Documentation ships with code.** `README.md`, `docs/architecture.md` and `skills/document-drift/SKILL.md` change in the same PR as the code they describe.
- **(d) No input-specific rules.** No script, constant or test may depend on the identity of a fixture or a real repository. Constants are named in section 9 and their basis in section 12.
- **(e) One branch, one PR.** `feat/document-drift-agentic`, branched from `feat/document-drift-phase-1` so the kept phase 1 code comes with it. PR #22 is closed unmerged when this branch's PR opens; `main` never ships the history-gated version.
- **(f) No time estimates.** Work is sized by scope and risk only.

## 1. Goal, non-goals, decisions

### 1.1 Goal

A skill, `/document-drift <repo>`, that reads a repository's code and its markdown documents and makes the documents match the code, in both directions:

- **Docs to code.** A statement a doc makes about this repository's code that the code contradicts, or that names something the code no longer has, is rewritten or removed.
- **Code to docs.** Something the code offers its users (a tool, command, flag, environment variable, config key, route, hook, script, public API or user file) that no doc mentions, or that is missing from a doc's list of such things, is added to the docs.

The result is commits on a new branch. The owner's own process pushes the branch, reads the change and opens the pull request; human review of that pull request is the gate before anything reaches the default branch.

### 1.2 Non-goals

- Pushing, opening pull requests, writing a PR body, or touching any remote.
- Creating new doc files. Additions go into existing in-scope docs, as list entries or new sections.
- Editing excluded files: CHANGELOG, HISTORY, LICENSE, NOTICE, CODE_OF_CONDUCT, ADRs and decision records, RFCs, superpowers plans and specs, research and archive folders, vendored and generated docs, templates (the phase 1 exclusion set, unchanged).
- Changing code. When the doc states a guarantee the code does not keep, the doc is left alone and the case is listed for the owner, because the code may be the bug.
- Executing project code, building, installing, or running examples or `--help`. All checking is by reading source.
- Documenting internals that no doc already lists (private helpers, internal modules, test utilities).
- Undocumented behaviours as gaps. Only surface items (section 5.2) can be gaps; the set of behaviours has no end.
- External URL checking, `.rst` and `.adoc`, translated READMEs, prose style and markdown lint.
- Pattern hints for languages other than Python and JavaScript/TypeScript (section 5.1). Other languages are still read by the sheet agents, without hints.

### 1.3 Decisions

Taken in the 2026-10-10 brainstorm:

| # | Decision | Owner's answer |
|---|---|---|
| N1 | What the skill checks | The docs against what the code does, by reading the code. Git history is not a gate; it is used only for `--base` and cache keys |
| N2 | Directions | Both: docs to code, and code to docs |
| N3 | Missing docs | Add entries to existing lists and tables; where no list fits, write a new section in the best-fitting existing doc. Never create doc files |
| N4 | Run size | Full sweep by default under a configurable agent cap; the summary lists what the cap left unchecked; `--base` narrows a run |
| N5 | Architecture | Code fact sheets first (one agent per code area), then one agent per doc unit compares the doc with the sheets and may open the source, gap agents add missing items, verifier agents check every edit |
| N6 | Guarantees | A "must/never/always/guarantees" statement the code contradicts is not edited; it is listed for the owner with both sides quoted |
| N7 | Commits | Two commits: corrections (docs to code), then additions (code to docs) |
| N8 | Phase 1 code | Reused where it fits; the two-snapshot gate and the provable fix classes are dropped |

Carried over from the 2026-10-09 brainstorm, still in force:

| # | Decision | Owner's answer |
|---|---|---|
| D7 | Gate for edits | The skill edits the files and commits; a human validates in PR review. No report round-trip, no interactive prompts |
| D-out | Output | A new branch with commits only. No push, no PR body file |
| D-unfix | Findings not edited | Listed in a "Needs a human decision" section at the end of the last commit message; when there are no edits, printed only and no branch is created |
| D5 | Examples | Read, never executed |
| D13 | Documents | `.md` files outside the exclusions, including CLAUDE.md and AGENTS.md at any depth |
| D14 | Quality bar | Measured on the first live run; the bar is set from that measurement |

### 1.4 Success criteria

1. On a clean tree, a run with edits leaves exactly one new branch whose commits change only in-scope markdown files, and leaves the original branch untouched.
2. On the fixture corpus with canned agent outputs, every planted drift item (both directions, section 10.2) produces its expected edit or human-decision entry, and no decoy produces either.
3. Every applied edit passed the script checks (section 8.1) and a verifier's accept (section 8.2), and creates no new broken path or anchor reference (section 8.3).
4. Commit messages match the grammar in section 8 exactly; a test asserts the grammar.
5. Script stages produce byte-identical outputs for a fixed repository state and fixed agent output files.
6. The first live run on `better-memory` is judged edit by edit by the owner; the acceptance rate, run time, agent count and token use are logged in `docs/evaluation-log.md`, and the acceptance bar for later runs is set from it (D14).
7. The owner runs the skill on this repository before the PR is opened, and the run's edits are accepted or rejected in that PR.

## 2. Command contract

```
/document-drift <repo> [--base <ref>] [--branch <name>] [--check]
```

The session runs the driver one stage at a time (section 3):

```
python scripts/dd_run.py <repo> --stage <start|docs|verify|finish> [--retried] [--base <ref>] [--branch <name>] [--check] [--workdir <dir>] [--date <YYYY-MM-DD>]
```

- `<repo>`, `--branch`, `--workdir`, `--date`: as in phase 1. The workdir defaults to `<repo>/.document-drift`, is added to `.git/info/exclude`, and is never committed.
- `--base <ref>`: scope the run to code areas with a file changed in `git diff --name-only --no-renames <ref>...HEAD`, and to docs that changed in that range or map to a changed area (section 6.1). An unknown ref is refused.
- `--check`: run through verification and stop; no doc edit, no branch, no commit. The summary lists every accepted edit in the commit-bullet grammar. Exit 1 when any accepted edit exists.
- `--branch`, `--base`, `--check` and `--date` are given to the `start` stage, which records them in `preflight.json`; later stages read them from there and refuse a different value (exit 2).
- `--retried`: see section 3.2.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Stage succeeded. From `finish`: with edits, the branch exists with its commits and the user is on it; without edits, no branch was created |
| 1 | `finish` under `--check` only: accepted edits exist. Nothing was changed |
| 2 | Refused before any change: the phase 1 preflight refusals (not a git repository, not the top level, no commits, unknown `--base`; outside `--check` also a detached HEAD, a dirty tree, an existing branch, no git author identity, an invalid branch name), a stage run out of order, or a flag that differs from the one `start` recorded |
| 3 | The previous agent wave left missing or invalid output files. The stage wrote `retry.json`; the session re-dispatches those entries once and reruns the same stage with `--retried` |
| 5 | A script step crashed or a script's own expected output is missing. The message names the step |
| 6 | The commit failed after edits were applied; the message says where the edits are (phase 1 semantics) |

## 3. Pipeline

### 3.1 Stages

| Stage | Script steps | Then the session dispatches |
|---|---|---|
| `start` | preflight; inventory (docs and source); areas; hints; cache lookup | one sheet agent per area without a valid cached sheet (`plan-sheets.json`) |
| `docs` | sheet validation and check; cache store; doc map; doc units; gap detection and targeting | one review agent per doc unit and one gap agent per target doc (`plan-docs.json`) |
| `verify` | edit validation and script checks; overlap resolution; verify batches | one verifier agent per batch (`plan-verify.json`) |
| `finish` | verdicts; apply; re-scan and revert; heading link updates; commits; summary | nothing |

Each stage checks that the previous stage completed (its output files exist and `preflight.json` matches); otherwise exit 2. Each stage prints one line naming its plan file and entry count, or, for `finish`, the summary.

### 3.2 Dispatch protocol

A plan file is a JSON list of entries `{id, role, prompt, output, model}`. `role` is `sheet`, `review`, `gap` or `verify`; `prompt` and `output` are absolute paths inside the workdir; `model` comes from config (section 9). For each entry the session dispatches one Agent with the prompt file's content as its prompt and the given model, in parallel where the host allows. The agent may read any file in the repository (Read, Grep, Glob) and writes exactly one file, `output`, with the Write tool. It replies with a receipt only (path, bytes, item count); the session never transcribes a reply into a file.

At the start of the next stage the script validates every output of the previous wave against its schema. If any is missing or invalid and `--retried` was not given, the stage writes `retry.json` (the failed entries, in plan format) and exits 3, changing nothing else. The session dispatches those entries once and reruns the stage with `--retried`. With `--retried`, an output still missing or invalid marks its area or doc unit as unchecked, and the stage continues. One failed agent never fails the run.

### 3.3 No improvisation

The session runs the four stages in order, dispatches exactly the plan entries, and relays the final summary. It never edits a doc, never writes an agent's output file itself, never reruns a stage except as section 3.2 directs, and never pushes or opens a pull request. On exit 5 it stops and reports the message verbatim; when the step is apply, commit or summary, it tells the user to check `git status` and `git branch`.

## 4. Inventory and scope

**Docs.** Phase 1's doc inventory and exclusion set, unchanged: every tracked `.md` file outside the exclusions, with the `drift-ignore` markers, generated regions and never-edit sections (`never_edit_heading`) honoured as in phase 1. Excluded docs are listed in the summary by reason.

**Source.** Every tracked file is classified as `source`, `test`, `config`, `generated`, `vendored`, `doc` or `other`, using the classification globs phase 1 copied from tech-debt-scan's inventory. Areas are built from `source` files plus the project files below; `test`, `generated`, `vendored` and `other` files are never part of an area. Agents may still open any file while checking.

**Project files.** One area of its own holding, where tracked: `pyproject.toml`, `setup.cfg`, `setup.py`, `package.json`, `Makefile`, `justfile`, `Taskfile.yml`, `Dockerfile*`, `docker-compose*.yml`, `compose*.yml`, `.env.example`, `Cargo.toml`, `go.mod`, and workflow files under `.github/workflows/`.

## 5. Code areas and fact sheets

### 5.1 Areas and hints

**Splitting.** Areas are built from the source tree by line count, against the budget `area_lines` (default 5,000):

1. Start with each top-level directory holding source files, and one area for the top-level loose source files.
2. A directory over the budget is replaced by one area per subdirectory plus one for its own loose files; repeat until every area fits or is a single directory with no subdirectories. Loose files still over the budget are cut into consecutive groups of whole files, sorted by path, each within the budget (a single file over the budget is an area alone).
3. Sibling areas under the same parent are merged, in path order, while the merged size stays within the budget.

Area ids are `a01`, `a02`, ... in path order of each area's first file, with the project-files area last. Each area records its files, its line count and its key: the SHA-256 of the sorted `(path, blob sha)` pairs plus the sheet prompt version.

**Hints.** A pattern scan of each area's files collects likely surface names, each with its `path:line`:

- Python: `add_argument("--x")` and `add_parser("x")` (argparse); `@click.command`, `@click.option("--x")`, `@app.command()` (click, typer); `os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")`; route decorators `@<name>.(get|post|put|patch|delete|route)("/x")`; MCP tool registrations `@<name>.tool(` and `Tool(name="x"`.
- JavaScript and TypeScript: `process.env.X` and `process.env["X"]`; commander `.command("x")` and `.option("--x")`; yargs `.option("x")`; route calls `<name>.(get|post|put|patch|delete)("/x"`.
- Project files: `[project.scripts]` and `[project.entry-points]` names, `package.json` `scripts` and `bin`, Makefile and justfile targets, Taskfile tasks, `ENV` lines in Dockerfiles, keys in `.env.example`.

Hints are leads, not facts. Each gets an id (`h0001`, ...) and goes to its area's sheet agent as a checklist.

### 5.2 Fact sheet schema

The sheet agent reads its area and writes `sheets/<area>.json`:

```json
{
  "area": "a03",
  "surface": [
    {"kind": "envvar", "name": "BETTER_MEMORY_HOME", "summary": "Root directory for the database and spool",
     "default": "~/.better-memory", "defined_at": "better_memory/config.py:41", "user_facing": true}
  ],
  "behaviours": [
    {"statement": "memory_retrieve returns at most 5 memories per bucket unless top_n is given",
     "evidence": ["better_memory/services/retrieve.py:88"]}
  ],
  "hints": [
    {"id": "h0012", "status": "included"},
    {"id": "h0013", "status": "internal", "reason": "test-only override read by conftest"}
  ]
}
```

- `kind` is one of `tool`, `command`, `flag`, `envvar`, `configkey`, `route`, `hook`, `script`, `api`, `userfile`, `module`.
- `user_facing` is true for anything a user, operator or integrator calls, sets or sees without editing the code. Internal modules and helpers are recorded with `user_facing: false` (kind `module` for modules) so a doc that lists them can be checked.
- `default` is a string or null. `summary` and `statement` are single lines of at most 200 characters.
- Every hint id given to the agent appears in `hints`, as `included` (a `surface` entry carries that name) or `internal` with a reason.
- Items the code hides are recorded with `hidden: true`: argparse `help=argparse.SUPPRESS`, click `hidden=True`, names starting with `_`, items marked deprecated in code.

### 5.3 Sheet check

At the start of `docs`, each sheet is validated against the schema, then checked by script:

- every `defined_at` and every `evidence` entry names a tracked file and a line within it;
- the cited line, or one of the two lines on either side, contains the item's `name` (for `surface`) or at least one inline-code token or identifier from the `statement` (for `behaviours`);
- an entry that fails is dropped and counted under its reason (`missing-file`, `bad-line`, `name-not-at-line`);
- a hint id the sheet omits, or marks `included` while no `surface` entry carries its name, is reported as unaccounted in the summary.

A sheet that fails schema validation is a failed output (section 3.2). A sheet that passes validation, after the check has dropped its bad entries, is stored in the cache.

### 5.4 Cache

Checked sheets are stored as `<workdir>/cache/sheets/<area key>.json`. At `start`, an area whose key has a cached sheet is not dispatched. The cache is never committed and can be deleted at any time; a changed sheet prompt changes every key.

## 6. Docs to code: review

### 6.1 Doc map

The phase 1 extractor pulls each in-scope doc's references (paths, inline code, fenced commands, names). A sheet is relevant to a doc when the doc names one of the sheet's surface items (whole word, matched with the normalisation of section 7.1), names one of the area's files, or names a directory holding them. Every doc also receives the **surface index**: the names, kinds and summaries of every user-facing item in every sheet, without behaviours. README.md at the repository root, and CLAUDE.md and AGENTS.md at any depth, describe the whole project and therefore receive every sheet in full.

The phase 1 resolver, run against HEAD only, lists the doc's path and anchor references that do not resolve now. These go to the review agent as hints.

Under `--base`, the docs reviewed are those changed in the range or relevant to an area with a changed file.

### 6.2 Doc units

A doc of at most `doc_unit_lines` (default 400) lines is one unit. A longer doc is split at its second-level headings into consecutive units of at most that size; a second-level section over the size is split at third-level headings, and a section still over the size is one unit. Each unit of a split doc also carries the doc's title and its table of headings. Docs under 100 lines that receive the same relevant sheets are packed together into one unit while the unit stays within the size. Unit ids are `u001`, `u002`, ... in doc path order.

### 6.3 What the review agent checks

The agent checks every factual statement the unit makes about this repository's code: names, paths, commands, flags, environment variables, config keys, defaults, counts and lists ("the six tools"), described behaviour, code examples (imports, call shapes, CLI invocations, field names in sample output) and directory trees. It reads the sheets first and opens the source whenever a sheet does not settle a claim.

It does not check statements about other software, plans, intent or opinion, or historical sentences ("X was removed in 2.0"), which are true as history.

### 6.4 Review output

The agent writes `review/<unit>.json`:

```json
{
  "unit": "u007",
  "claims_checked": 41,
  "edits": [
    {"id": "u007-e01", "doc": "website/configuration.md", "start_line": 54, "end_line": 54,
     "old": "| `BETTER_MEMORY_TOP_N` | `3` | ... |", "new": "| `BETTER_MEMORY_TOP_N` | `5` | ... |",
     "type": "correct", "claim": "default of BETTER_MEMORY_TOP_N is 3",
     "evidence": ["better_memory/config.py:57"], "subject": null}
  ],
  "questions": [
    {"doc": "README.md", "line": 88, "kind": "guarantee-mismatch",
     "claim": "the stop hook never blocks", "code": "the hook waits on the synthesis lock",
     "evidence": ["better_memory/hooks/stop.py:30"]},
    {"doc": "README.md", "line": 140, "kind": "unsure", "claim": "...", "question": "...", "evidence": []}
  ]
}
```

- `type` is `correct` (change wrong text) or `remove` (delete a statement about something the code no longer has). `subject` names the removed item for a `remove` edit when there is one; section 8.1 checks it is absent from the source.
- `old` is the exact text of lines `start_line` to `end_line`; `new` is their replacement (empty for a removal).
- Edits are minimal: change the wrong part, keep the doc's wording, voice and format, and do not reflow paragraphs or make style edits.
- A heading is edited only when the heading itself is wrong.
- A statement containing a guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`) that the code contradicts is a `guarantee-mismatch` question, never an edit.
- A claim the agent cannot settle is an `unsure` question.

## 7. Code to docs: gaps

### 7.1 Detection

A user-facing, non-hidden surface item is **documented** when its name appears as a whole word in any in-scope doc, fenced blocks included. Names are compared after normalising both sides: leading dashes are removed, `-` and `.` become `_`, and an MCP tool prefix `mcp__<server>__` is removed. Comparison is case-sensitive. Excluded docs do not count.

A **list** is a markdown table or bullet list in an in-scope doc in which at least 3 rows or items have a subject (the first cell, or the first inline-code span of the item) that matches a surface item, all of one kind. The list's scope is the set of areas its matched items come from. The list is **complete-intended** when it already holds at least half of the items of its kind in its scope that are user-facing and not hidden, or, for kind `module`, at least half of that scope's modules.

Two kinds of gap:

1. **Undocumented:** a user-facing, non-hidden item that is not documented.
2. **Missing from a list:** an item of a complete-intended list's kind and scope that the list does not hold. For kind `module`, `user_facing: false` items qualify; otherwise they never do.

Items whose name matches a glob in `undocumented_ok` are never gaps. Under `--base`, only items from areas with a changed file can be gaps.

### 7.2 Targets

The script picks one target doc per gap, and records the reason:

- **Missing from a list:** that list's doc, at that list.
- **Undocumented:** first, a complete-intended list of the item's kind whose scope includes the item's area, then any list of that kind; otherwise the in-scope doc that mentions the most surface items of the same area and kind, ties broken by the shorter path; otherwise no target, and the item goes to "Needs a human decision" as `no-home`.

### 7.3 Gap writing

One gap agent per target doc receives the doc, its gap items with their sheet entries and targets, and read access to the source. It writes `gaps/<doc id>.json` in the review edit schema with `type: "add"`. An insertion is expressed as an edit whose `old` is the anchor line and whose `new` is the anchor line followed by the added lines.

- In a list: add rows or items matching the list's format, columns and order; a sorted list stays sorted.
- Without a list: write a short new section at the best place in the doc, under a heading at the level that fits its neighbours.
- Descriptions come from the code; every added entry cites `evidence`.
- The agent may refuse a target with a reason, as a `questions` entry of kind `target-refused`.

## 8. Checks, verification, apply and commits

### 8.1 Script checks

Run at the start of `verify` on every edit from review and gap agents, in this order; the first failure decides. A failing edit is never verified or applied. It is listed in the summary with its reason, and the human-decision kinds are also listed in the last commit message:

| Check | Fails when | Result |
|---|---|---|
| `old-mismatch` | `old` is not exactly the text of lines `start_line` to `end_line` | dropped |
| `protected` | the lines touch a `drift-ignore` region, a generated region or a never-edit section | human (`protected`) |
| `evidence` | an `evidence` entry names a missing file or a line outside it, or a `correct` or `add` edit has no evidence | dropped |
| `still-in-source` | a `remove` edit's `subject`, normalised as in section 7.1, still appears as a whole word in a tracked source file | dropped |
| `guarantee` | `old` contains a guarantee word that `new` does not | human (`guarantee-mismatch`) |
| `large-deletion` | a `remove` edit deletes more than `max_delete_lines` (default 15) lines, or deletes a heading line | human (`large-deletion`) |
| `large-section` | an `add` edit adds more than `max_section_lines` (default 40) lines | human (`large-section`) |
| `new-reference` | a path in `new` does not exist at HEAD, or a name in an inline-code span of `new` is neither a sheet surface name nor a whole word in a tracked source or project file | dropped |
| `overlap` | the line range overlaps an edit already kept for the same doc (review edits are kept before gap edits, then by id) | human (`overlap`) |

### 8.2 Verification

Edits that pass the checks are grouped by the area of their first evidence path (edits with no evidence, which are removals only, are grouped by doc) into batches of at most 10. One verifier agent per batch receives, for each edit, the claim, the evidence, the old and new text and 10 lines of the doc on either side, and read access to the source. It does not see the proposing agent's reasoning. It writes `verdicts/<batch>.json`: one entry per edit, `{"edit": id, "verdict": "accept" | "reject" | "unsure", "reason": "..."}`. Only accepted edits are applied. A rejected or unsure edit goes to "Needs a human decision" as `verify-rejected` with the verifier's reason. An edit with no verdict, because its batch was unchecked or its entry is missing, is listed in the summary as unverified and is not applied.

### 8.3 Apply and re-scan

Phase 1's apply step applies the accepted edits, per doc from the bottom up, each by exact match of `old`. The edited docs are then re-scanned with the phase 1 extractor and resolver against HEAD; an edit after which a path or anchor reference that resolved before no longer resolves is reverted and listed as `recheck-failed`. When an applied edit changes a heading, links to the old heading slug in in-scope docs are updated in the same commit, using phase 1's heading-rename handling, and listed under that edit.

### 8.4 Commits

`finish` creates the branch from the starting HEAD with `git switch -c` (after checking HEAD still equals the preflight HEAD), stages each edited doc by explicit path, and makes at most two commits:

```
docs(drift): correct stale docs

Drift-Run: <run id>
Drift-Base: <starting HEAD sha>
Drift-Scope: all | base <ref>
Drift-Unchecked: <n> areas, <n> doc units

- <doc>:<line> correct <claim> (<path:line>[, <path:line>...])
- <doc>:<line> remove <claim> (<subject> not in source)
```

```
docs(drift): document missing surface

Drift-Run: ...
Drift-Base: ...
Drift-Scope: ...
Drift-Unchecked: ...

- <doc>:<line> add <kind> <name> (<path:line>)
```

The first commit holds the applied review edits and their heading link updates; the second holds the applied gap edits. When one of them has no edits it is not made. The last commit made ends with:

```

Needs a human decision:
- <doc>:<line> <kind>: <claim or item> (<evidence or reason>)
```

The kinds are `guarantee-mismatch`, `unsure`, `large-deletion`, `large-section`, `protected`, `overlap`, `no-home`, `target-refused`, `verify-rejected` and `recheck-failed`. `<line>` is the line in the doc at the starting HEAD. Every repository-derived string is redacted and cut to one line of at most 160 characters. `commit_trailers` from config are appended after the `Drift-` lines. When no edit is applied, no branch is created and the list appears in the summary only.

### 8.5 Summary

`summary.md`, also printed by `finish`: run id; scope; base; docs scanned and excluded by reason; areas (total, from cache, checked, unchecked by the cap, unchecked after retry); sheet entries dropped by reason and unaccounted hints; doc units (checked, unchecked); claims checked; edits proposed by review and by gap agents; script check results by check; verdicts by kind; edits applied and reverted; gaps by kind and by target; the human-decision list; markers without reasons and stale markers; the branch and commit hashes, or "No branch created". Under `--check`, every accepted edit is listed in the commit-bullet grammar.

## 9. Configuration and limits

`.document-drift.yaml` at the repository root, optional. Phase 1's keys `exclude`, `never_edit_heading`, `branch` and `commit_trailers` keep their meaning; `lead_cap` and `recent_change_days` are removed (an unknown key warns, as before). New keys and defaults:

```yaml
area_lines: 5000          # line budget per code area
doc_unit_lines: 400       # line budget per doc unit
max_delete_lines: 15      # larger removals go to a human
max_section_lines: 40     # larger additions go to a human
undocumented_ok: []       # globs of surface names that are never gaps
caps:
  sheets: 12              # sheet agents per run (cached areas are free)
  docs: 40                # review agents per run
  gaps: 15                # gap agents per run
  verify: 15              # verifier agents per run
models:
  sheet: sonnet
  review: sonnet
  gap: sonnet
  verify: opus
```

**When a cap is reached**, the work beyond it is not dispatched and is listed in the summary and counted in `Drift-Unchecked`:

- **Sheets:** areas without a cached sheet are dispatched in descending order of the number of in-scope docs that name one of their files or directories, then by area id.
- **Review:** units of README.md, CLAUDE.md and AGENTS.md first, then by the number of references the unit makes into checked areas, descending, then by unit id.
- **Gaps:** target docs by the number of gaps, descending, then by path.
- **Verify:** batches in order; edits in batches beyond the cap are unverified and not applied.

## 10. Code, tests and evaluation

### 10.1 Code inventory

Kept unchanged from phase 1: `dd_common`, `dd_redaction`, `dd_check_skill`, `dd_md_scan`, `dd_extract`, `dd_apply`, `dd_preflight`.

Extended:

- `dd_inventory`: source classification and project files.
- `dd_config`: the keys of section 9.
- `dd_resolve`: resolution against HEAD only, no history.
- `dd_manifests`: entry points and scripts feed the project-files hints.
- `dd_history`: reduced to `--base` diffs, blob shas for area keys and heading-rename link updates; blame snapshots, rename chains and deletion lookups are removed.
- `dd_commit`: two commits and the grammar of section 8.
- `dd_summary`: section 8.5.
- `dd_run`: the staged driver of section 3.

Removed: `dd_fixes` (the provable fix classes). The heading-link update it held moves to `dd_apply`.

New:

- `dd_areas`: splitting and keys (section 5.1).
- `dd_hints`: the pattern scan (section 5.1).
- `dd_sheets`: sheet schema, check and cache (sections 5.2 to 5.4).
- `dd_docmap`: doc map and units (sections 6.1, 6.2).
- `dd_gaps`: detection and targets (sections 7.1, 7.2).
- `dd_checks`: the script checks (section 8.1).
- `dd_dispatch`: plan files, prompt rendering, output validation and `retry.json` (section 3.2).
- `prompts/sheet.md`, `prompts/review.md`, `prompts/gap.md`, `prompts/verify.md`, each with a version line that feeds cache keys.

### 10.2 Tests

- Unit tests for every script, in the existing style. No test calls a model; agent outputs are canned JSON files.
- The three fixture repositories (`py-service`, `ts-web`, `go-cli`) are rebuilt for this design. Each gains planted drift in both directions:
  - **docs to code:** a wrong default, a wrong flag name, a wrong count, a removed tool still documented, a guarantee the code does not keep;
  - **code to docs:** an environment variable missing from an env var table, an undocumented command, an undocumented MCP tool or route.
- Each also gains decoys that must produce no edit and no human entry: a historical sentence, a statement about other software, a hidden flag, an internal helper, an `undocumented_ok` item, a selective list (under half of its kind).
- Canned outputs for every agent role per fixture, including one invalid output to exercise exit 3 and `--retried`, and one invented `defined_at` to exercise the sheet check.
- Golden files for every script stage's outputs and the commit messages, byte-compared and regenerated only under `UPDATE_GOLDENS=1`.
- The phase 1 CI self-scan step is removed: CI cannot run agents. Success criterion 7 replaces it.

### 10.3 Live evaluation

An opt-in harness (`tests/dd_live_run.py`, adapted from tech-debt-scan's `live_run.py`) runs the full skill with real agents on the fixture corpus and on a named repository. It appends a row to `docs/evaluation-log.md` with: repository and HEAD, edits proposed, applied and judged acceptable by the owner, planted items caught (corpus), decoys touched (corpus), human-decision entries, agents dispatched per role, run time and tokens. The first row, on `better-memory`, sets the acceptance bar (D14).

## 11. What happens to phase 1

- This branch, `feat/document-drift-agentic`, starts from `feat/document-drift-phase-1` (PR #22).
- PR #22 is closed unmerged when this branch's PR opens.
- The 2026-10-09 spec gets a first line marking it superseded by this spec. Its plan and rulings file stay as the record of phase 1.
- The skill installed at `~/.claude/skills/document-drift` is a junction to the working copy, so it follows whichever branch is checked out.

## 12. Assumptions

| # | Assumption | Basis | Cost if wrong |
|---|---|---|---|
| A1 | A 5,000-line area fits one sheet agent with room to read it properly | Typical agent context; `better-memory` has about 25,000 non-test source lines, giving 6 to 8 areas | Shallow sheets that miss behaviours; lower `area_lines` |
| A2 | Hints plus the `file:line` check catch most sheet omissions and inventions | The hint patterns cover how the corpus and `better-memory` declare their surface | Gaps missed and drift hidden; review agents opening the source is the second line of defence |
| A3 | "A guarantee word in `old` but not in `new`" is a good enough proxy for an edit that rewrites a guarantee | Guarantees are phrased with those words in the corpus and in `better-memory` | Some guarantee rewrites applied, still visible in the PR; or harmless edits sent to a human |
| A4 | A list holding at least half of its kind in its scope is meant to be complete | Judgement; selective lists ("common settings") usually hold a few items | Over-adding to selective lists; the owner removes rows in review or adds `undocumented_ok` |
| A5 | The default caps cover a repository of `better-memory`'s size without being reached | `better-memory`: 38 in-scope docs (4,615 lines, none over 400) and 6 to 8 areas, so about 8 sheet agents, at most 38 review agents, and gap and verifier agents within 15 each | Unchecked docs on larger repositories, listed in the summary; raise the caps |
| A6 | A full run on a repository of that size costs minutes and a few million tokens | About 60 to 75 agents, each reading a few thousand lines | Runs too slow or costly to repeat; the cache and `--base` make later runs cheaper, and the live log measures it |
| A7 | The host dispatches a plan's agents in parallel | Claude Code runs several Agent calls from one message concurrently | Longer runs, same result |
| A8 | Read-only agents write only their output file | The same contract tech-debt-scan relies on | A stray write shows up as a dirty tree; preflight of the next run refuses |
| A9 | Verifiers with a fresh context and the source catch most wrong edits | Independent check, no access to the proposing agent's reasoning | Wrong edits reach the PR, where the owner rejects them; the live log measures the rate |
