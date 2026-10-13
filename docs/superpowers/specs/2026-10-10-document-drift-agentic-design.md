# document-drift: make the docs match the code, in both directions

Provenance: brainstormed 2026-10-10 to 2026-10-12, after the first real run of the phase 1 skill (`docs/superpowers/specs/2026-10-09-document-drift-design.md`, PR #22) on the owner's `better-memory` repository read 38 docs, proposed no edit, and never opened a source file. The owner rejected that design: the point of the skill is that the docs match what the code does, and a gate built on git history cannot establish that. A first redesign (one fact-sheet agent per code area, every run a full audit) was validated and then revised: the facts that matter (what the code does, command-line flags, configuration, key classes and interfaces) change slowly, so the docs themselves are the record of what to check, and each run checks only what changed since the last. This spec covers **phase A**, normal runs on a repository that has docs. **Phase B**, writing a README for a repository with none, is designed in section 12 and built later.

Fixed constraints, unchanged from the repository's skills: Claude Code skill; SKILL.md orchestration with pinned commands, pinned output files and the no-improvisation rule; pure Python 3.11+ with pyyaml as the only runtime dependency, every script direct-path invocable as `python scripts/<name>.py`; read-only Agent subagents for LLM work, each writing its own output file with the Write tool and replying with a receipt; large data passed between steps as file paths, never inline on an argv; redaction at every write of repository-derived text; LF-only output; no live LLM in tests; ruff, mypy strict, pytest and a SKILL.md linter in CI; every module `dd_`-prefixed and every test file `test_dd_*.py`.

## 0. Guardrails for planning and implementation

- **(a) Assumptions surfaced.** Section 14 lists every assumption with its status and cost if wrong; the validation passes in sections 14.2 and 14.3 ran before owner review of this spec.
- **(b) Confidence per task.** Every plan task carries a confidence percentage; anything under 90 percent is resolved by investigation, a question or a spike before implementation.
- **(c) Documentation ships with code.** `README.md`, `docs/architecture.md` and `skills/document-drift/SKILL.md` change in the same PR as the code they describe.
- **(d) No input-specific rules.** No script, constant or test may depend on the identity of a fixture or a real repository. Constants are named in section 10 and their basis in section 14.
- **(e) One branch, one PR per phase.** Phase A is built on `feat/document-drift-agentic`, branched from `feat/document-drift-phase-1` so the kept phase 1 code comes with it. PR #22 is closed unmerged when this branch's PR opens; `main` never ships the history-gated version.
- **(f) No time estimates.** Work is sized by scope and risk only.

## 1. Goal, non-goals, decisions

### 1.1 Goal

A skill, `/document-drift <repo>`, that keeps a repository's markdown docs matching what its code does, in both directions:

- **Docs to code.** A statement a doc makes about this repository's code that the code contradicts, or that names something the code no longer has, is rewritten or removed.
- **Code to docs.** A command, flag, environment variable, MCP tool, route or script the code offers its users that no doc mentions, or that is missing from a doc's list of such things, is added to the docs.

The docs are the record of what to check. The first run reviews every doc against the code it points at; later runs review only the statements whose code changed since the last run, and document only user-facing names added since then. The result is commits on a new branch. The owner's own process pushes the branch, reads the change and opens the pull request; human review of that pull request is the gate before anything reaches the default branch.

### 1.2 Non-goals

- Pushing, opening pull requests, writing a PR body, or touching any remote.
- Creating doc files (phase B's README is the one planned exception).
- Editing excluded files: CHANGELOG, HISTORY, LICENSE, NOTICE, CODE_OF_CONDUCT, ADRs and decision records, RFCs, superpowers plans and specs, research and archive folders, vendored and generated docs, templates (the phase 1 exclusion set, unchanged).
- Changing code. When the doc states a guarantee the code does not keep, the doc is left alone and the case is listed for the owner, because the code may be the bug.
- Executing project code, building, installing, or running examples or `--help`. All checking is by reading source.
- Tracking facts no doc mentions, other than the user-facing names the pattern scan finds (section 8). An undocumented class or interface is not noticed.
- Rechecking, on a later run, a statement that names nothing in code formatting; it has no anchor and is checked on a first run or `--full` only.
- Undocumented behaviours as gaps.
- Pattern hints, definition ranges and flag parents for languages other than Python and JavaScript/TypeScript (other languages anchor to whole files and get no hints).
- External URL checking, `.rst` and `.adoc`, translated READMEs, prose style and markdown lint.

### 1.3 Decisions

Taken in the 2026-10-10 to 2026-10-12 brainstorm:

| # | Decision | Owner's answer |
|---|---|---|
| N1 | What the skill checks | The docs against what the code does, by reading the code. Git history is not a gate |
| N2 | Directions | Both: docs to code, and code to docs |
| N3 | Missing docs | Add entries to existing lists and tables; where no list fits, write a new section in the best-fitting existing doc. Never create doc files (phase B excepted) |
| N4 | Run size | Bounded by a configurable agent cap; the summary lists what the cap left unchecked |
| N6 | Guarantees | A "must/never/always/guarantees" statement the code contradicts is not edited; it is listed for the owner with both sides quoted |
| N7 | Commits | Two commits: corrections (docs to code), then additions (code to docs) |
| N8 | Phase 1 code | Reused where it fits; the two-snapshot gate and the provable fix classes are dropped |
| N9 | Baseline | The docs are the baseline: no separate inventory file. What a doc mentions is what is checked |
| N10 | Change anchor | Later runs diff from the last drift run: the newest `Drift-Base` in history, or the local last-run record. None means a first run |
| N11 | No docs | A full code scan writes a README (phase B) |
| N12 | Repeat gaps | Later runs propose only user-facing names added since the last run |
| N13 | Scope of this spec | Phase A: normal runs, first and later, both directions. Phase B (no-docs mode) is built later |
| N14 | Fact sheets | Dropped from normal runs; agents read the anchored code directly. Kept for phase B |
| N15 | Unverifiable docs | A doc that describes the code but names nothing the skill can anchor is itself a finding, not a doc to skip: the summary reports every doc's checkability on every run, and the review agent adds the missing names (`anchor` edits, in the corrections commit) so later runs can check the doc |
| N16 | Blocks that cannot be anchored | A block that describes the code but that no definition can be tied to gets a `drift-unverified` notice in the doc. Unchanged at the next run, the notice becomes a second notice saying it needs a human decision, and the block is listed in the commit's human-decision list. Unchanged at the run after that, the block is removed. Preamble, pitch, process and history are never noticed |

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
2. On the fixture corpus with canned agent outputs, every planted drift item produces its expected edit or human-decision entry, on a first run and on a later run after a planted code change, and no decoy produces either.
3. On a later run, a doc none of whose anchors changed is not reviewed, and no agent is dispatched when nothing in scope changed.
4. Every applied edit passed the script checks (section 9.1) and a verifier's accept (section 9.2), and creates no new broken path or anchor reference (section 9.3).
5. Commit messages match the grammar in section 9.4 exactly; a test asserts the grammar.
6. Script stages produce byte-identical outputs for a fixed repository state and fixed agent output files.
7. The first live run on `better-memory` is judged edit by edit by the owner; the acceptance rate, run time, agent count and token use are logged in `docs/evaluation-log.md`, and the acceptance bar for later runs is set from it (D14). A second live run, after real commits, is logged the same way.
8. The owner runs the skill on this repository before the PR is opened, and the run's edits are accepted or rejected in that PR.

## 2. Command contract

```
/document-drift <repo> [--base <ref>] [--full] [--branch <name>] [--check]
```

The session runs the driver one stage at a time (section 3):

```
python scripts/dd_run.py <repo> --stage <start|verify|finish> [--retried] [--base <ref>] [--full] [--branch <name>] [--check] [--workdir <dir>] [--date <YYYY-MM-DD>]
```

- `<repo>`, `--branch`, `--workdir`, `--date`: as in phase 1. The workdir defaults to `<repo>/.document-drift`, is added to `.git/info/exclude`, and is never committed.
- `--base <ref>`: compare against `<ref>` instead of the last drift run (section 6.1). An unknown ref is refused.
- `--full`: a first run regardless of any previous run.
- `--check`: run through verification and stop; no doc edit, no branch, no commit, and no last-run record. The summary lists every accepted edit in the commit-bullet grammar. Exit 1 when any accepted edit exists.
- `--base`, `--full`, `--branch`, `--check` and `--date` are given to `start`, which records them in `preflight.json`; later stages read them from there and refuse a different value (exit 2).
- `--retried`: see section 3.2.

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Stage succeeded. From `finish`: with edits, the branch exists with its commits and the user is on it; without edits, no branch was created |
| 1 | `finish` under `--check` only: accepted edits exist. Nothing was changed |
| 2 | Refused before any change: the phase 1 preflight refusals (not a git repository, not the top level, no commits, unknown `--base`; outside `--check` also a detached HEAD, a dirty tree, an existing branch, no git author identity, an invalid branch name), a stage run out of order, a flag that differs from the one `start` recorded, or (at `finish`) files outside the workdir that changed during the run |
| 3 | The previous agent wave left missing or invalid output files. The stage wrote `retry.json`; the session re-dispatches those entries once and reruns the same stage with `--retried` |
| 5 | A script step crashed or a script's own expected output is missing. The message names the step |
| 6 | The commit failed after edits were applied; the message says where the edits are (phase 1 semantics) |

## 3. Pipeline

### 3.1 Stages

| Stage | Script steps | Then the session dispatches |
|---|---|---|
| `start` | preflight; inventory; definition index (section 5.1); doc references and anchors (sections 5.2 to 5.4); run mode and change set (section 6); docs and statements to review; review units (section 6.4); pattern scan and gaps (section 8) | one review agent per unit and one gap agent per target doc (`plan-docs.json`); when there is nothing to dispatch, the session goes straight to `finish` |
| `verify` | output validation; script checks (section 9.1); verify batches | one verifier agent per batch (`plan-verify.json`) |
| `finish` | verdicts; tree check (any file outside the workdir that changed since preflight refuses the run, exit 2, naming the files); apply; re-scan and revert; heading link updates; commits; last-run record (section 6.5); summary | nothing |

Each stage checks that the previous stage completed (its output files exist and `preflight.json` matches); otherwise exit 2. Each stage prints one line naming its plan file and entry count, or, for `finish`, the summary. `finish` may follow `start` directly when `plan-docs.json` is empty.

### 3.2 Dispatch protocol

A plan file is a JSON list of entries `{id, role, prompt, output, model}`. `role` is `review`, `gap` or `verify`; `prompt` and `output` are absolute paths inside the workdir; `model` comes from config (section 10). For each entry the session dispatches one Agent, with the given model, whose prompt is a single instruction to read the prompt file in full and follow it; the session never pastes the prompt content (verifier prompts run to 25,000 characters, and pasted prompts would stay in the session's context for the rest of the run). Entries are dispatched in parallel where the host allows. The agent may read any file in the repository (Read, Grep, Glob) and writes exactly one file, `output`, with the Write tool. It replies with a receipt only (path, bytes, item count); the session never transcribes a reply into a file. Every prompt states that the agent runs no command and writes no helper script or other file: in validation, an agent without that sentence wrote three helper scripts and ran Python, and agents with it wrote nothing else.

At the start of the next stage the script validates every output of the previous wave against its schema. If any is missing or invalid and `--retried` was not given, the stage writes `retry.json` (the failed entries, in plan format) and exits 3, changing nothing else. The session dispatches those entries once and reruns the stage with `--retried`. With `--retried`, an output still missing or invalid marks its unit or batch as unchecked, and the stage continues. One failed agent never fails the run.

### 3.3 No improvisation

The session runs the stages in order, dispatches exactly the plan entries, and relays the final summary. It never edits a doc, never writes an agent's output file itself, never reruns a stage except as section 3.2 directs, and never pushes or opens a pull request. On exit 5 it stops and reports the message verbatim; when the step is apply, commit or summary, it tells the user to check `git status` and `git branch`.

## 4. Inventory and scope

**Docs.** Phase 1's doc inventory and exclusion set, unchanged: every tracked `.md` file outside the exclusions, with the `drift-ignore` markers, generated regions and never-edit sections (`never_edit_heading`) honoured as in phase 1. Excluded docs are listed in the summary by reason. A repository with no in-scope doc stops after `start` with the message that no-docs mode arrives in phase B (exit 0, no branch).

**Source.** Every tracked file is classified as `source`, `test`, `config`, `generated`, `vendored`, `doc` or `other`, using the classification globs phase 1 copied from tech-debt-scan's inventory. The definition index and the pattern scan read `source` files plus the project files below; `test`, `generated`, `vendored` and `other` files are never indexed. Agents may still open any file.

**Project files**, where tracked: `pyproject.toml`, `setup.cfg`, `setup.py`, `package.json`, `Makefile`, `justfile`, `Taskfile.yml`, `Dockerfile*`, `docker-compose*.yml`, `compose*.yml`, `.env.example`, `Cargo.toml`, `go.mod`, and workflow files under `.github/workflows/`.

## 5. Definitions and anchors

### 5.1 Definition index

A script builds an index from name to definitions. Each definition records its file, its line range, its kind and its owners (the names of the enclosing functions and classes, and the registered name of an enclosing registration such as `Tool(name="memory.retrieve", ...)`).

- **Python** (standard library `ast`): every module (by dotted path and by last segment), function, method and class, with its exact `lineno` to `end_lineno`; every string literal that looks like a name (`^[A-Za-z_][\w.\-]{2,}$` or a `--flag`), with the range of the largest enclosing node spanning at most 15 lines (so a registration call's whole argument list is the range of each name in it). A literal is a **registration** when it is the `name=` keyword of a call, or an argument of `add_argument`, `add_parser`, `get`, `getenv`, `route`, `get/post/put/patch/delete` (as decorators), `option`, `command`, or a function whose name starts with `_resolve`.
- **SQL** (`.sql` source files): `CREATE TABLE/VIEW/INDEX/TRIGGER` names, with the statement's range; column definitions and `ALTER TABLE ... ADD COLUMN` columns, each one line.
- **JavaScript and TypeScript**: `function`, `class`, `export const/let`, and method definitions, with ranges found by brace matching; string literals as for Python, with a one-line range.
- **Files**: every tracked non-test file by basename when the basename is unique in the repository.
- **Other languages**: no definitions; a path reference to such a file anchors the whole file.

Definition kinds have a rank: definitions (module, function, class, SQL object, file) rank 0; registrations and SQL columns rank 1; other literals rank 2.

### 5.2 References

The phase 1 extractor lists each in-scope doc's references: paths in links and code spans, and every inline-code span outside fenced blocks whose first token looks like a name or a path. An HTML `<code>...</code>` span counts as an inline-code span (`website/index.md` in `better-memory` is a 209-line landing page written in HTML whose only references are in `<code>` tags). Each reference records its doc line and its **block**: the paragraph, list, table or heading it sits in, plus the nearest heading above it.

A reference is **specific** when it contains `.`, `/` or `_`, starts with `--`, mixes case (`camelCase`), or is upper case with underscores (`BETTER_MEMORY_HOME`). Otherwise it is **bare** (`query`, `limit`, `scope`).

Names are compared after normalising both sides: an MCP tool prefix `mcp__<server>__` is removed, and `-` and `.` become `_`, except that a flag keeps its leading dashes.

### 5.3 Resolution

- A path that exists is resolved by the phase 1 resolver; it needs no anchor.
- A specific reference resolves to its definitions of the best rank present. More than 10 at that rank leaves it unanchored as ambiguous.
- A bare reference resolves only through context: to its definitions whose owners include a specific name in the same block or in the nearest heading (so `query` in the `memory.retrieve` parameter table resolves to that tool's `query`). With no context match, or more than 3 matches, it is unanchored.
- A reference with no definition is unanchored as unknown (SQL keywords, other software's API names, paths outside the repository).

Unanchored references are counted in the summary by reason. They are never guessed.

### 5.4 Anchors and their ranges

An **anchor** is a resolved reference with its definition's file and range. Two ranges are kept:

- the **change range**, for deciding whether code changed: the definition's full range, except that for a function or class over 60 lines it is the signature range (the definition line through its docstring, plus, for a class, each method's definition line), so a change inside a large body does not mark every doc that merely names the container;
- the **reading range**, given to a review agent: the definition's full range, capped at the signature range for definitions over 60 lines. The agent may open more.

On `better-memory` at `9d5be26`, 1,497 of 2,925 references anchor (51%) and 87 are existing paths; the anchors cover 10,251 of 21,402 source lines (section 14.3).

### 5.5 Checkability

A doc the skill cannot tie to the code is the doc most likely to drift unnoticed, by the skill and by its readers. So the script measures, for every in-scope doc on every run, its **checkability**: references, anchored references, the anchoring rate, and the number of blocks (paragraphs, list items and table rows outside fences) that hold no reference at all. A doc is **unverifiable** when it has no anchor, and **weakly anchored** when its anchoring rate is under `min_anchor_ratio` (default 0.25) or it has fewer than 3 anchors. Both are listed by name in the summary (section 9.5), with the note that a later run cannot see code changes that affect them until they name code. On `better-memory`, 12 of 38 docs have no anchor and 502 of 977 blocks carry no reference (section 14.3).

Checkability at the doc level is reported, never enforced: an unverifiable doc is not a human-decision item, because nothing in it is known to be wrong. The fixes work block by block: the `anchor` edit (section 7.1) gives a block the name it lacks, and the notice loop (section 7.3) asks the owner about the blocks nothing can be tied to, then removes the ones nobody answers for. A doc that still has no anchor after a first run is one where the agent found nothing to name, which is usually a doc that is not about the code (a contributing guide, a landing page's prose); the first-run summary separates those by the agent's `code_claims` count.

## 6. Run modes

### 6.1 The last run

`start` looks for two records and uses the newer:

1. **The newest commit reachable from HEAD whose message has a `Drift-Base:` line**, taking that line's sha, provided it is an ancestor of HEAD. A squash-merged drift PR keeps the line, because the squash message includes the commit messages.
2. **`<workdir>/last-run.json`** (section 6.5), provided its `head` is an ancestor of HEAD.

When both qualify, the one that is a descendant of the other is newer. `--base <ref>` replaces both. `--full`, or neither record, makes a **first run**. Otherwise it is a **later run** from the chosen sha, the **last-run commit**.

### 6.2 First run

Every in-scope doc is reviewed in full: every factual statement it makes about the code, with its anchors' reading ranges as the starting point. Every undocumented user-facing name the pattern scan finds is a gap candidate.

### 6.3 Later run

The script computes `git diff -U0 <last-run commit>..HEAD` for indexed files, and rebuilds the definition index at the last-run commit for the changed files only. A doc is **affected** when, since the last-run commit:

- one of its anchors' change ranges overlaps a changed hunk (a hunk that only removes lines counts as touching the line where it was);
- a reference that resolved at the last-run commit no longer resolves (the definition was deleted or renamed); or
- the doc itself changed.

For an affected doc, the review covers the statements tied to the affected anchors and missing names, and every section (by heading) of the doc that changed. The rest of the doc is not reviewed. A doc that is not affected costs nothing. When no doc is affected and no gap candidate exists, no agent is dispatched.

Gap candidates on a later run are the user-facing names the pattern scan finds in the changed files at HEAD but not in the same files at the last-run commit (N12).

### 6.4 Review units

Affected docs (on a first run, all docs) are grouped into units so that shared code is read once:

1. Docs are linked when they share an anchored definition.
2. Linked docs are packed in path order into units while the unit's size stays within `unit_lines` (default 6,000). Size is the reviewed doc lines plus, on a first run, the anchors' reading-range lines, or, on a later run, the changed hunk lines for those anchors plus the reading-range lines of anchors whose definitions were deleted.
3. A linked group larger than the budget on its own loses its link: its docs are packed one by one, in path order, like unlinked docs (amended 2026-10-13 after the first live run packed 27 linked docs into one 10,757-line unit).
4. A doc larger than the budget on its own is split at second-level headings.

Each unit's prompt carries its docs (paths and the line ranges to review), its anchors (`reference (doc line) -> file:start-end`), on a later run the relevant hunks as a unified diff, and the unit's scope (section 7.1). Unit ids are `u001`, `u002`, ... in path order.

### 6.5 Recording the run

After a successful `finish` (not under `--check`), the script writes `<workdir>/last-run.json` with the run's starting HEAD, run id and date, whether or not it made a commit, so a run with nothing to fix still moves the anchor on this machine. A commit carries the same sha in its `Drift-Base` line, which is how the anchor reaches other machines and CI.

## 7. Docs to code: review

### 7.1 What the agent checks

On a first run the agent checks every factual statement its docs make about this repository's code: names, paths, commands, flags, environment variables, config keys, defaults, counts and lists ("the six tools"), described behaviour, code examples (imports, call shapes, CLI invocations, field names in sample output) and directory trees. It starts from the anchors' reading ranges and opens whatever else it needs.

It has a second job on a first run: where a true statement describes a definition without naming anything the index can resolve ("the bootstrap renders the newest memories", "three buckets, surfaced separately"), and one definition clearly is the thing described, it proposes an **`anchor` edit** that names it in an inline-code span, in the doc's own wording ("the bootstrap (`SessionBootstrapService.bootstrap`) renders the newest memories"). An anchor edit changes nothing else; a statement that is wrong gets a `correct` edit instead, and a statement with several plausible definitions, or none, gets no edit. The agent also reports `code_claims`, the number of statements about this repository's code it found in each doc, so the summary can tell a doc that is not about the code from one that is but names nothing, and `unverified_blocks`: the blocks that describe this repository's code, hold no reference that anchors, and that it could not tie to one definition (so no `anchor` edit was possible). Preamble, a pitch for the project, process, plans, history and statements about other software are never unverified blocks: they are not claims about the code. The agent does not edit or move an existing `drift-unverified` notice.

On a later run the agent checks only the statements about the affected anchors and missing names, including statements that describe the changed behaviour without naming it, and the changed sections. It works from the diff and opens the current source whenever the diff alone does not settle a statement. It ignores everything else in the doc, even if it might be wrong. Anchor edits are proposed only within the changed sections.

In both modes it does not check statements about other software, plans, intent or opinion, or historical sentences ("X was removed in 2.0"), which are true as history.

### 7.2 Review output

The agent writes `review/<unit>.json`:

```json
{
  "unit": "u007",
  "claims_checked": 41,
  "code_claims": {"website/configuration.md": 38, "README.md": 60},
  "unverified_blocks": [{"doc": "README.md", "start_line": 131, "end_line": 134, "why": "describes retrieval ordering; no function clearly owns it"}],
  "not_reviewed": [],
  "edits": [
    {"id": "u007-e01", "doc": "website/configuration.md", "start_line": 54, "end_line": 54,
     "old": "| `BETTER_MEMORY_TOP_N` | `3` | ... |", "new": "| `BETTER_MEMORY_TOP_N` | `5` | ... |",
     "type": "correct", "claim": "default of BETTER_MEMORY_TOP_N is 3",
     "evidence": ["better_memory/config.py:57"], "subject": null},
    {"id": "u007-e02", "doc": "README.md", "start_line": 120, "end_line": 120,
     "old": "The bootstrap renders the newest memories first.", "new": "The bootstrap (`SessionBootstrapService.bootstrap`) renders the newest memories first.",
     "type": "anchor", "claim": "the bootstrap renders newest first",
     "evidence": ["better_memory/services/bootstrap.py:41"], "subject": "SessionBootstrapService.bootstrap"}
  ],
  "questions": [
    {"doc": "README.md", "line": 88, "kind": "guarantee-mismatch",
     "claim": "the stop hook never blocks", "code": "the hook waits on the synthesis lock",
     "evidence": ["better_memory/hooks/stop.py:30"]},
    {"doc": "README.md", "line": 140, "kind": "unsure", "claim": "...", "question": "...", "evidence": []}
  ]
}
```

- `type` is `correct` (change wrong text), `remove` (delete a statement about something the code no longer has) or `anchor` (name the definition a true statement describes, by inserting an inline-code span or by wrapping a bare name already in the statement). `subject` names the removed item for a `remove` edit when there is one, and the added name for an `anchor` edit; section 9.1 checks the former is absent from the source and the latter resolves to the evidence. The prompt's doc list marks a doc none of whose reviewed lines holds an anchor (`no anchors in these lines`, added 2026-10-13 after two live runs proposed no anchor edit): the agent is told every block of it that describes the code gets an `anchor` edit or an `unverified_blocks` entry.
- `code_claims` counts, per doc in the unit, the statements about this repository's code, including the ones that name nothing; 0 means the doc is not about the code.
- `unverified_blocks` lists whole blocks (a paragraph, a list, a table, by line range) for the notice loop of section 7.3. A block that already carries a notice, or that overlaps an edit in the same output, is not listed.
- `not_reviewed` (optional, added 2026-10-13) lists the ranges of the unit the agent did not check against the code, each with a `why`. The `verify` stage packs those ranges into retry units (fresh unit ids, `retry_of` naming the source unit, appended to `units.json` and `plan-docs.json`) and lists them in `retry.json` with the invalid outputs, so the session dispatches them once with the ordinary exit-3 rule. Ranges still reported as not reviewed on the `--retried` pass are listed in `edits.json` and the summary as not reviewed and are not retried again. A range the agent did not check is never an unverified block.

### 7.3 Blocks nothing can be tied to: the notice loop

A block that describes the code but that neither the index nor the agent can tie to a definition is not left alone: the doc gets a notice, the way an encyclopedia marks a claim with no citation. The loop is driven by the script on every run, with no agent, from the notices already in the docs; the agent only nominates new blocks (`unverified_blocks`) on a first run or in a changed section.

A notice is one HTML comment on its own line directly above the block, invisible in the rendered doc and plain in the PR diff:

```
<!-- drift-unverified: 1st notice, run 2026-10-12-a3f1, block 9c2e41d7. This describes the code but names nothing in it. Name what it describes, or add drift-ignore: <reason>. -->
<!-- drift-unverified: 2nd notice, run 2026-10-19-b77c, block 9c2e41d7. NEEDS A HUMAN DECISION: name what this describes, add drift-ignore: <reason>, or rewrite it. The next drift run removes this block otherwise. -->
```

`block` is the first 8 hex digits of the SHA-256 of the block's text with runs of whitespace collapsed, so an edit to the block is detectable without storing anything outside the doc. A list or table is noticed as a whole, and only when no item or row anchors.

On every run the script reads each notice and looks at its block:

| Found | Action | Commit bullet |
|---|---|---|
| The block now has an anchor (an `anchor` edit was applied, or the owner named something) | the notice is removed | `clear unverified notice (now anchored)` |
| The block's hash differs (the owner rewrote it) | the notice is removed; the block is reviewed afresh because its section changed, and may be nominated again, which starts a new 1st notice | `clear unverified notice (block changed)` |
| The block carries a `drift-ignore` marker | the notice is removed; the marker is the owner's answer | `clear unverified notice (drift-ignore)` |
| 1st notice, block unchanged and still unanchored | the notice becomes a 2nd notice, and the block is listed under "Needs a human decision" as `unverified` | `escalate unverified notice` |
| 2nd notice, block unchanged and still unanchored | the block and its notice are removed as a `remove` edit of type `unverified` | `remove unverified block (3rd notice, unchanged since <run id>)` |

A newly nominated block gets a 1st notice. A nomination counts only when it resolves to one block that is not a heading, its range does not run past that block, and the block holds no anchor; a nomination of a whole doc or of several blocks is skipped as `spans blocks` (added 2026-10-13: the first live run's review agent nominated seven whole docs it had not reviewed). Every notice edit goes into the corrections commit and through the script checks of section 9.1: a removal over `max_delete_lines` goes to a human as `large-deletion` instead, a block in a protected region as `protected`. Notice edits are script-generated statements of fact (unchanged, unanchored, counted), so they are not sent to a verifier. Under `--check`, they are listed and nothing is written. A notice whose run id is newer than the current run, or that is malformed, is listed in the summary as a stale marker and left alone.

The loop runs on a doc even when nothing else affects it, so a doc that names no code is still visited by the script, if not by an agent, on every run. It is the only place the skill deletes text it does not know to be wrong; it does so after two PRs that carried the question, and the deletion is itself a bullet in a PR the owner opens.
- `old` is the exact text of lines `start_line` to `end_line`, leading spaces included; `new` is their replacement (empty for a removal).
- Edits are minimal: change the wrong part, keep the doc's wording, voice and format, and do not reflow paragraphs or make style edits.
- A heading is edited only when the heading itself is wrong.
- A statement containing a guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`) that the code contradicts is a `guarantee-mismatch` question, never an edit.
- A claim the agent cannot settle is an `unsure` question.

## 8. Code to docs: gaps

### 8.1 Pattern scan

A script scans every indexed file, on every run, for user-facing names, each with its `path:line`, its kind and, for flags, its parent:

- **Python**: `add_argument("--x")` (parent: the command whose `add_parser("name")` created the parser the call is on, found through `ast` assignments) and `add_parser("x")`; `@click.command`, `@click.option("--x")`, `@app.command()`; `os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")`, and any string literal that starts with the prefix (up to and including the first `_`) of an environment variable read directly anywhere in the repository, such as `BETTER_MEMORY_` (projects read many variables through helpers); route decorators `@<name>.(get|post|put|patch|delete|route)("/x")`; MCP tool registrations `@<name>.tool(` and `Tool(` followed by `name="x"`, and each tool's input-schema property names as flags with the tool as parent.
- **JavaScript and TypeScript**: `process.env.X` and `process.env["X"]`; commander `.command("x")` and `.option("--x")`; yargs `.option("x")`; route calls `<name>.(get|post|put|patch|delete)("/x"`.
- **Project files**: `[project.scripts]` and `[project.entry-points]` names, `package.json` `scripts` and `bin`, Makefile and justfile targets, Taskfile tasks, `ENV` lines in Dockerfiles, keys in `.env.example`.

Every pattern matches across line breaks. A name is **hidden** when the code hides it (`help=argparse.SUPPRESS`, `hidden=True`, a leading underscore, a deprecation marker within three lines). Hidden names and names matching a glob in `undocumented_ok` are never gaps.

### 8.2 Detection

A name is **documented** when it appears in any in-scope doc, fenced blocks included. Excluded docs do not count. Names are compared after normalising both sides, case-sensitively:

- `-` and `.` inside a name become `_`, and an MCP tool prefix `mcp__<server>__` is removed (`memory.retrieve`, `memory_retrieve` and `mcp__better-memory__memory_retrieve` match);
- a flag keeps its leading dashes (without them `--force` matches the word "force" in any sentence);
- route placeholders `<id>`, `{id}` and `:id` become one placeholder;
- a single-word name matches as a whole word; a name with spaces matches as a substring of the normalised text;
- an MCP tool parameter is documented only inside the section whose heading names its tool, since parameter names (`query`, `scope`, `id`) are shared by many tools.

A **list** is a markdown table or bullet list in an in-scope doc in which at least 3 rows or items have a subject (the first cell, or the first inline-code span of the item) that matches a scanned name, all of one kind. For a list of flags, its scope is the parent named in the nearest heading above it (for an MCP parameter table, the tool), or, when no heading names one, the parents of its matched flags; for other kinds, the whole repository. A list is **complete-intended** when it holds at least half of the non-hidden names of its kind in its scope.

Gap candidates (all names on a first run, new names on a later run, section 6.3) become gaps of two kinds:

1. **Undocumented:** a candidate no in-scope doc mentions.
2. **Missing from a list:** a candidate of a complete-intended list's kind and scope that the list does not hold.

### 8.3 Targets

The script picks one target doc per gap, and records the reason:

- **Missing from a list:** that list's doc, at that list.
- **Undocumented:** first, a complete-intended list of the name's kind whose scope includes it, then any list of that kind; otherwise the in-scope doc that mentions the most names of the same kind from the same file or, for a flag, the same parent, ties broken by the shorter path; otherwise no target, and the name goes to "Needs a human decision" as `no-home`.

### 8.4 Gap writing

One gap agent per target doc receives the doc, its gaps (kind, name, parent, `path:line`, target and reason), and read access to the source. It writes `gaps/<doc id>.json` in the review edit schema with `type: "add"`. An insertion is an edit whose `old` is the anchor line and whose `new` is the anchor line followed by the added lines.

- Before adding, the agent opens the definition and confirms the name is user-facing (a user, operator or integrator calls, sets or sees it without editing the code). A name the host sets for the program (for example an environment variable Claude Code provides) or an internal one is refused as `not-user-facing`.
- It searches the in-scope docs for the name under any spelling. A name that is in fact documented is refused as `already-documented`; this backs up the name matching, which cannot know every spelling.
- In a list: add rows or items matching the list's format, columns and order; a sorted list stays sorted.
- Without a list: add a sentence or bullet in the most fitting paragraph or section, or, only if nothing fits, a short new section under a heading at the level of its neighbours.
- Descriptions come from the code; every added entry cites `evidence`.
- The agent may refuse a target with a reason as `target-refused`.

Refusals of kind `not-user-facing` and `already-documented` are dropped and counted in the summary; `target-refused` goes to "Needs a human decision".

## 9. Checks, verification, apply and commits

### 9.1 Script checks

Run at the start of `verify` on every edit from review and gap agents, in this order; the first failure decides. A failing edit is never verified or applied. It is listed in the summary with its reason, and the human-decision kinds are also listed in the last commit message:

| Check | Fails when | Result |
|---|---|---|
| `old-mismatch` | `old` is not exactly the text of lines `start_line` to `end_line`, after one repair: when the two differ only in leading whitespace, `old` is replaced by the doc's text and each line of `new` gets the indentation of the doc line it replaces | dropped |
| `protected` | the lines touch a `drift-ignore` region, a generated region or a never-edit section | human (`protected`) |
| `evidence` | an `evidence` entry names a missing file or a line outside it, or a `correct` or `add` edit has no evidence | dropped |
| `still-in-source` | a `remove` edit's `subject`, normalised as in section 5.2, still appears as a whole word in a tracked source file | dropped |
| `anchor-adds-name` | an `anchor` edit's `new` is not `old` with one inline-code span inserted (plus at most 3 other words, such as brackets or "the") or with one bare word wrapped in backticks and nothing else changed (amended 2026-10-13: the docs that name nothing often hold the name as a bare word), or the span's name does not resolve (section 5.3) to a definition in the evidence file, or `old` contains a guarantee word (an anchor edit never rewrites a guarantee) | dropped |
| `guarantee` | `old` contains a guarantee word that `new` does not | human (`guarantee-mismatch`) |
| `large-deletion` | a `remove` edit deletes more than `max_delete_lines` (default 15) lines, or deletes a heading line | human (`large-deletion`) |
| `large-section` | an `add` edit adds more than `max_section_lines` (default 40) lines | human (`large-section`) |
| `new-reference` | a path in `new` does not exist at HEAD, or a name in an inline-code span of `new` is neither in the definition index nor a whole word in a tracked source or project file | dropped |
| `overlap` | the line range overlaps an edit already kept for the same doc (review edits are kept before gap edits, then by id) | human (`overlap`) |

### 9.2 Verification

Edits that pass the checks are grouped by the file of their first evidence path (edits with no evidence, which are removals only, are grouped by doc) into batches of at most 10. One verifier agent per batch receives, for each edit, the claim, the evidence, the old and new text and 10 lines of the doc on either side, and read access to the source. It does not see the proposing agent's reasoning. It accepts an edit only when the old text is wrong about this repository's code, the new text is right and supported by the code, the edit is minimal, the old text is not about other software, intent or history, and it is not a contradicted guarantee. It accepts an `anchor` edit only when the statement is true and the named definition is the thing it describes, not merely a related one. It writes `verdicts/<batch>.json`: one entry per edit, `{"edit": id, "verdict": "accept" | "reject" | "unsure", "reason": "..."}`. Only accepted edits are applied. A rejected or unsure edit goes to "Needs a human decision" as `verify-rejected` with the verifier's reason. An edit with no verdict, because its batch was unchecked or its entry is missing, is listed in the summary as unverified and is not applied.

### 9.3 Apply and re-scan

Phase 1's apply step applies the accepted edits, per doc from the bottom up, each by exact match of `old`. The edited docs are then re-scanned with the phase 1 extractor and resolver against HEAD; an edit after which a path or anchor reference that resolved before no longer resolves is reverted and listed as `recheck-failed`. When an applied edit changes a heading, links to the old heading slug in in-scope docs are updated in the same commit, using phase 1's heading-rename handling, and listed under that edit.

### 9.4 Commits

`finish` creates the branch from the starting HEAD with `git switch -c` (after checking HEAD still equals the preflight HEAD), stages each edited doc by explicit path, and makes at most two commits:

```
docs(drift): correct stale docs

Drift-Run: <run id>
Drift-Base: <starting HEAD sha>
Drift-Scope: first | since <sha> | base <ref> | full
Drift-Unchecked: <n> doc units, <n> gap docs, <n> verify batches

- <doc>:<line> correct <claim> (<path:line>[, <path:line>...])
- <doc>:<line> remove <claim> (<subject> not in source)
- <doc>:<line> anchor <subject> (<path:line>)
- <doc>:<line> notice unverified block (1st notice)
- <doc>:<line> escalate unverified notice (2nd notice)
- <doc>:<line> clear unverified notice (now anchored | block changed | drift-ignore)
- <doc>:<line> remove unverified block (3rd notice, unchanged since <run id>)
```

```
docs(drift): document missing surface

Drift-Run: ...
Drift-Base: ...
Drift-Scope: ...
Drift-Unchecked: ...

- <doc>:<line> add <kind> <name> (<path:line>)
```

The first commit holds the applied review edits (`correct`, `remove` and `anchor`), the notice-loop edits of section 7.3 and their heading link updates; the second holds the applied gap edits. When one of them has no edits it is not made. The last commit made ends with:

```

Needs a human decision:
- <doc>:<line> <kind>: <claim or item> (<evidence or reason>)
- no-home: <kind> <name> (<path:line>)
```

A `no-home` item belongs to no doc, so its line carries no `<doc>:<line>` (its place is the definition in the evidence). The kinds are `guarantee-mismatch`, `unsure`, `unverified` (section 7.3, with the block's first line quoted), `large-deletion`, `large-section`, `protected`, `overlap`, `no-home`, `target-refused`, `verify-rejected` and `recheck-failed`. `<line>` is the line in the doc at the starting HEAD. Every repository-derived string is redacted and cut to one line of at most 160 characters. `commit_trailers` from config are appended at the end of the message, after the human-decision block. When no edit is applied, no branch is created and the list appears in the summary only. Human-decision items are not stored anywhere else: a later run raises one again only if its code changes again.

### 9.5 Summary

`summary.md`, also printed by `finish`: run id; mode (first, since a sha, base, full) and the last-run commit; base; docs scanned and excluded by reason; references, anchors and unanchored references by reason; checkability (section 5.5): every doc's references, anchors and rate, then the unverifiable and weakly anchored docs by name, split on a first run into docs with no code claims and docs with code claims that name nothing, with the number of anchor edits applied to each; the notice loop: notices placed, escalated, cleared by reason, and blocks removed; on a later run, changed files and hunks, and affected docs with the anchors that affected them; review units (checked, unchecked by the cap, unchecked after retry); claims checked; edits proposed by review and by gap agents; script check results by check; verdicts by kind; edits applied and reverted; gaps by kind and by target, and gap refusals by kind; the human-decision list; markers without reasons and stale markers; the branch and commit hashes, or "No branch created". Under `--check`, every accepted edit is listed in the commit-bullet grammar.

## 10. Configuration and limits

`.document-drift.yaml` at the repository root, optional. Phase 1's keys `exclude`, `never_edit_heading`, `branch` and `commit_trailers` keep their meaning; `lead_cap` and `recent_change_days` are removed (an unknown key warns, as before). New keys and defaults:

```yaml
unit_lines: 6000          # line budget per review unit
max_delete_lines: 15      # larger removals go to a human
max_section_lines: 40     # larger additions go to a human
min_anchor_ratio: 0.25    # docs anchoring below this are listed as weakly anchored
undocumented_ok: []       # globs of names that are never gaps
caps:
  review: 40              # review agents per run
  gaps: 15                # gap agents per run
  verify: 25              # verifier agents per run (10 edits each)
models:
  review: sonnet
  gap: sonnet
  verify: opus
```

**When a cap is reached**, the work beyond it is not dispatched and is listed in the summary and counted in `Drift-Unchecked`:

- **Review:** units holding README.md, CLAUDE.md or AGENTS.md first, then by the number of anchors in the unit (on a later run, affected anchors), descending, then by unit id.
- **Gaps:** target docs by the number of gaps, descending, then by path.
- **Verify:** batches in order; edits in batches beyond the cap are unverified and not applied.

## 11. Code, tests and evaluation

### 11.1 Code inventory

Kept unchanged from phase 1: `dd_common`, `dd_redaction`, `dd_check_skill`, `dd_md_scan`, `dd_extract`, `dd_apply`, `dd_preflight`.

Extended:

- `dd_inventory`: source classification and project files.
- `dd_config`: the keys of section 10.
- `dd_resolve`: resolution against HEAD only, no history.
- `dd_manifests`: entry points and scripts feed the project-files patterns.
- `dd_history`: reduced to the last-run search (section 6.1), `git diff -U0` hunks, reading files at a commit, and heading-rename link updates; blame snapshots, rename chains and deletion lookups are removed.
- `dd_commit`: two commits and the grammar of section 9.4.
- `dd_summary`: section 9.5.
- `dd_run`: the staged driver of section 3, including the last-run record.

Removed: `dd_fixes` (the provable fix classes). The heading-link update it held moves to `dd_apply`.

New:

- `dd_defindex`: the definition index (section 5.1), buildable at HEAD or, for given files, at another commit.
- `dd_anchors`: references (including HTML code spans), resolution, anchors, their ranges and per-doc checkability (sections 5.2 to 5.5).
- `dd_changes`: run mode, affected docs and review scope (sections 6.1 to 6.3).
- `dd_units`: review units (section 6.4).
- `dd_patterns`: the pattern scan (section 8.1).
- `dd_gaps`: detection and targets (sections 8.2, 8.3).
- `dd_checks`: the script checks (section 9.1), including `anchor-adds-name`.
- `dd_unverified`: the notice loop of section 7.3: notice grammar, block hashing, the per-notice decision and the edits it emits.
- `dd_dispatch`: plan files, prompt rendering, output validation and `retry.json` (section 3.2).
- `prompts/review-first.md`, `prompts/review-later.md`, `prompts/gap.md`, `prompts/verify.md`.

### 11.2 Tests

- Unit tests for every script, in the existing style. No test calls a model; agent outputs are canned JSON files.
- The three fixture repositories (`py-service`, `ts-web`, `go-cli`) are rebuilt for this design, each with a history of at least two states: the state of a first run, and later commits that change code the docs point at. Each gains planted drift in both directions:
  - **docs to code:** a wrong default, a wrong flag name, a wrong count, a removed tool still documented, a guarantee the code does not keep; and, in the later commits, a changed default and a renamed function the docs name;
  - **code to docs:** an environment variable missing from an env var table, an undocumented command, an undocumented MCP tool or route, and, in the later commits, a new flag;
  - **checkability:** a doc that describes a function without naming it (expected: listed as unverifiable, and the canned review output's `anchor` edit is applied, after which it anchors), a doc about the project's process with no code claims (listed as not about the code, no edit), and an HTML landing page whose references are in `<code>` tags (they anchor);
  - **notice loop:** a fixture with three states and canned nominations: a block nominated on the first run (expected: 1st notice), unchanged on the second (2nd notice and an `unverified` human-decision entry), unchanged on the third (removed, with its notice); a block the owner rewrote between runs (notice cleared, block changed); a block that gained a name (notice cleared, now anchored); a block given `drift-ignore` (notice cleared); a nominated block over `max_delete_lines` at its third sighting (`large-deletion`, not removed); and a malformed notice (listed as stale, untouched).
- Decoys that must produce no edit and no human entry: a canned `anchor` edit whose name resolves elsewhere than its evidence (dropped by `anchor-adds-name`), a historical sentence, a statement about other software, a hidden flag, an internal helper, an `undocumented_ok` item, a selective list (under half of its kind), a doc that names only code the later commits do not touch (it must not be reviewed on the later run), and a change inside a large class body that a doc mentions only by the class name.
- Tests for the last-run search: a drift commit, a squash-merged drift commit, a local record newer than the last drift commit, a record that is not an ancestor of HEAD (ignored), `--base`, `--full`.
- Canned outputs for every agent role per fixture, including one invalid output to exercise exit 3 and `--retried`.
- Golden files for every script stage's outputs and the commit messages, byte-compared and regenerated only under `UPDATE_GOLDENS=1`.
- The phase 1 CI self-scan step is removed: CI cannot run agents. Success criterion 8 replaces it.

### 11.3 Live evaluation

An opt-in harness (`tests/dd_live_run.py`, adapted from tech-debt-scan's `live_run.py`) runs the full skill with real agents on the fixture corpus and on a named repository, optionally from a given last-run commit to replay history. It appends a row to `docs/evaluation-log.md` with: repository, HEAD and mode, docs affected, edits proposed, applied and judged acceptable by the owner, planted items caught (corpus), decoys touched (corpus), human-decision entries, agents dispatched per role, run time and tokens. The first row, a first run on `better-memory`, sets the acceptance bar (D14).

## 12. Phase B: no-docs mode (designed, built later)

Superseded on 2026-10-13 by `docs/superpowers/specs/2026-10-13-document-drift-phase-b-design.md`, which settles the trigger (no in-scope root README, other docs reviewed in the same run), the `compose` stage, the sheet validator, the writer's cited claims, per-statement verification and the fixture. The outline below is kept as written.

When a repository has no in-scope doc, a full code scan writes `README.md`. This keeps the machinery of the first redesign:

1. **Areas.** The source is split by line count against `area_lines` (default 5,000): each top-level source directory is an area; a directory over the budget is replaced by its subdirectories plus one area for its loose files, loose files over the budget are cut into consecutive groups of whole files; sibling areas are merged in path order while within the budget. Project files form one area.
2. **Pattern scan** as in section 8.1, given to each area's agent as a checklist of hints.
3. **Fact sheets.** One agent per area writes a sheet: `surface` entries (kind, name, parent, summary, default, `defined_at`, user-facing, hidden) and `behaviours` (statement, evidence), with every hint accounted for, checked by script as validated in section 14.2.
4. **README writer.** One agent composes `README.md` from the sheets: what the project is, how to install and run it, commands and flags, configuration and environment variables, key interfaces. Every fact cites a sheet entry.
5. Verification as in section 9.2; the README lands in the additions commit.

Phase B gets its own plan and PR after phase A's first live runs.

## 13. What happens to phase 1

- This branch, `feat/document-drift-agentic`, starts from `feat/document-drift-phase-1` (PR #22).
- PR #22 is closed unmerged when this branch's PR opens.
- The 2026-10-09 spec carries a first line marking it superseded by this spec. Its plan and rulings file stay as the record of phase 1.
- The skill installed at `~/.claude/skills/document-drift` is a junction to the working copy, so it follows whichever branch is checked out.

## 14. Assumptions and validation

### 14.1 Assumptions

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| A0 | An agent comparing a doc with the code it points at finds real drift, and its edits are right | Validated on three docs (sections 14.2, 14.3): every edit the verifiers accepted and I checked was right | The skill produces noise; the live log would show it |
| A1 | A later run that reviews only the statements tied to changed code finds the drift those changes caused | Validated by replaying a week of `better-memory` history (section 14.3): all of that week's drift in two docs found, plus a new finding in a third | Drift caused by a change is missed until a `--full` run |
| A2 | Anchor resolution is accurate enough to decide what to read and what changed | Validated on `better-memory`: 51% of references anchored; of 25 sampled anchors, 19 right, 5 plausible, none wrong (section 14.3) | Docs reviewed for no reason (cost) or not reviewed when they should be (missed drift) |
| A3 | "A guarantee word in `old` but not in `new`" is a good enough proxy for an edit that rewrites a guarantee | Partly validated: 2.9% of doc lines carry a guarantee word, and no validation edit tripped the check | Some guarantee rewrites applied, still visible in the PR; or harmless edits sent to a human |
| A4 | A list holding at least half of its kind in its scope is meant to be complete | Validated after amendment (section 14.2) | Over-adding to selective lists; the owner removes rows in review or adds `undocumented_ok` |
| A5 | The pattern scan finds the user-facing names | Validated on `better-memory` after amendment: commands 7/7, routes 31/31, MCP tools 20/20, env vars 16/16 (section 14.2) | Gaps missed |
| A6 | Costs: a first run on a repository of `better-memory`'s size takes a few million tokens; a later run costs in proportion to what changed | First run estimated from the spike at 3 to 4 million tokens; a busy later week at under 1 million; a quiet week at none (section 14.3) | Runs too costly to repeat; the live log measures it |
| A7 | The host dispatches a plan's agents in parallel | Validated | Longer runs, same result |
| A8 | Read-only agents write only their output file | Validated only with an explicit prompt sentence (section 3.2); the `finish` tree check catches a stray write | A stray file in the repository; `finish` refuses the run |
| A9 | Verifiers with a fresh context and the source catch most wrong edits | Partly validated: of 20 edits, the verifiers rejected 2, both rightly; none of the 18 accepted edits I checked was wrong | Wrong edits reach the PR, where the owner rejects them |
| A10 | Gap agents write additions that are correct and match the doc's style | Validated on two gaps | Additions the owner has to rewrite |
| A13 | The agent separates blocks that describe the code from preamble, pitch, process and history well enough that the notice loop does not delete legitimate prose | First live run on `better-memory` (2026-10-13): 7 nominations, all whole docs the agent had not reviewed, none a legitimate block; the one-block rule in 7.3 and `not_reviewed` in 7.2 now separate the two. Two PR reviews stand between a nomination and a deletion, and the deletion is a reviewable bullet | A paragraph that was true but vague is deleted in a PR the owner merged without reading; one revert restores it |
| A11 | A `Drift-Base` line survives the owner's merge process | Holds for merge commits and GitHub's default squash message; a squash message edited by hand loses it, and the local record covers that machine only | A later run falls back to a first run, costly but correct |
| A12 | Given a true statement that names nothing, an agent can tell when one definition clearly is the thing described, and its `anchor` edit names the right one | Not validated: the fixture run and both live runs on `better-memory` (2026-10-13) proposed 0 anchor edits. The prompt now marks the docs with no anchor in their reviewed lines and asks for an anchor edit or an unverified block per code block there, and the check accepts a bare name wrapped in backticks; one review agent re-run on the unit holding better-memory's 11 unanchored docs still proposed none, counting those docs (PBIs, plans, `CLAUDE.md`) as 0 code claims, which the prompt's own rule allows. Needs a repository whose unanchored docs are prose about the code; the check and the verifier are the net | Wrong anchors send later runs to the wrong code for that statement, and a doc gains checkability it does not have |

### 14.2 Validation pass 1 (2026-10-10): the full-audit design

Run on `better-memory` at `9d5be26` (25,956 non-test source lines, 38 in-scope docs), with throwaway scripts and seven real agents, against the first redesign. Its measurements carry over where the parts are kept.

**Script measurements.**

| Check | Result | Amendment kept in this spec |
|---|---|---|
| Hint patterns as first written | Commands 7/7, routes 31/31, flags 19/19; **MCP tools 0/20** (`name=` is on the line after `Tool(`); **env vars 9/16** (7 read through a helper) | Patterns match across line breaks; string literals sharing a directly-read env var's prefix are env var names (section 8.1). Both then 100% |
| Name matching as first written, 98 user-facing items | 7 flagged undocumented, 1 truly undocumented (`BETTER_MEMORY_DIAG_LOGGING`); the rest documented under other spellings | Section 8.2's normalisation rules and the gap agent's `already-documented` refusal |
| Flag matching with dashes stripped | `--force` would match the word "force" anywhere | Flags keep their dashes |
| List scoping by code area | MCP parameter tables and the `agentcore` flag table measured against the wrong set | Flag and parameter lists are scoped by the parent named in the heading above them; the `agentcore` table then holds 11 of 12 and its missing `--force` is a real gap |
| Guarantee words | 133 of 4,615 doc lines (2.9%) | None |

**Spike with real agents.** One code area (hooks and MCP server, 3,411 lines), full reviews of two docs (`website/mcp-tools.md`, 302 lines; `docs/hooks-setup.md`, 387 lines), verification, and two gaps.

| Agent | Model | Tokens | Time | Output |
|---|---|---:|---:|---|
| Fact sheet (dropped in this design) | sonnet | 130,530 | 203 s | 148 surface entries, 129 behaviours |
| Review `mcp-tools.md` | sonnet | 104,909 | 81 s | 70 claims, 6 edits, 1 unsure question |
| Review `hooks-setup.md` | sonnet | 135,802 | 158 s | 48 claims, 15 edits |
| Verify batch 1 (10 edits) | opus | 87,525 | 74 s | 10 accept |
| Verify batch 2 (10 edits) | opus | 89,930 | 119 s | 8 accept, 2 reject |
| Gap: env var table | sonnet | 53,164 | 24 s | 1 row, correct |
| Gap: `agentcore init --force` | sonnet | 54,892 | 26 s | 1 sentence, correct |

One of the 21 review edits failed `old-mismatch` because the agent dropped the line's leading spaces; section 9.1 repairs whitespace-only differences. The accepted edits include a wrong default inject mode (`legacy` documented, `deferred` in code), a required parameter that is optional, a wrong return shape, a removed per-session latch still documented, and sample SQL naming columns the schema does not have. The two rejections were right: a claim about other software, and a correction that was still inaccurate.

### 14.3 Validation pass 2 (2026-10-12): the docs-as-baseline design

**Anchor resolution** (throwaway `ast` index and the section 5.3 rule) on `better-memory` at `9d5be26`: 2,925 references in 38 docs; 87 existing paths; 1,497 anchored (51%); 680 unanchored as ambiguous; 661 unanchored as unknown, mostly SQL keywords, AWS API names and Claude Code's own files. The first version of the rule, without SQL objects, unique file basenames and definition ranks, and with a no-context fallback for bare words, anchored 40% and anchored `Bash` in a hooks doc to an unrelated trigger parser; the rule in section 5.3 is the corrected one. Of 25 sampled anchors, 19 were right, 5 plausible, none wrong. The anchors cover 10,251 of 21,402 source lines, so a first run's reading ranges are about half the code.

**Checkability** (same index): 12 of the 38 docs have no anchor: the 10-line `CLAUDE.md` (its four references are a tool outside the repository), ten tech-debt PBI and plan files, and `website/index.md`, 209 lines with no markdown reference because it is HTML and names `memory.observe()` in `<code>` tags (section 5.2 now reads those). Of 977 blocks, 502 hold no reference; in the best-anchored docs a third to a half of blocks still name nothing (`website/mcp-tools.md` 28 of 94, `README.md` 51 of 93), so the anchor edits of section 7.1 have room to work on every doc. Which of those blocks make code claims is the agent's call, measured on the first live run.

**Replay of one week of history.** From `ad1615d` (the commit before a 17-commit feature week) to `9d5be26`: 111 hunks in 18 indexed files.

- With full definition ranges, 14 of 26 docs with anchors were affected, several only because they name a large class (`StorageBackend`, 475 lines) or `create_app` (772 lines). With signature ranges for definitions over 60 lines (section 5.4) the count stayed at 14, the remaining large-class matches being real changes to those classes' members.
- Review agents driven by the diff, scoped to the affected statements, on three of the affected docs:

| Doc | Full review (pass 1) | Diff-driven review | Tokens | Time |
|---|---|---|---:|---:|
| `website/mcp-tools.md` | 6 edits | 2 edits: the inject-mode default, the one drift that week caused | 56,880 | 33 s |
| `docs/hooks-setup.md` | 15 edits | 5 edits: every latch and inject-mode statement that week made wrong, all `old` texts exact | 58,181 | 33 s |
| `website/architecture.md` | not reviewed | 1 edit: the UI's capability context now reads seven flags, not six | 74,356 | 39 s |

Every drift item that week caused in the two compared docs was found; the drift that predates the week was correctly left to a first run.

**Cost.** A first run on `better-memory`: about 15 to 20 review units of 6,000 lines at about 110,000 tokens, about 10 gap agents at about 55,000, and about 14 verifier batches at about 90,000, so about 3 to 4 million tokens and 10 to 15 minutes with each wave in parallel. A later run after a busy week: about 14 affected docs packed into about 5 units at about 70,000 tokens, plus a few verifier batches, so under 1 million tokens. A week with no change to anchored code: no agents.

**Still unvalidated.** Anchor edits (A12), block classification for the notice loop (A13), the precision of the guarantee proxy (A3), JavaScript and TypeScript definition ranges, the flag-parent search through `ast` assignments, review units of several docs in one agent, and every script stage end to end. The plan's first tasks should make the live harness cheap to run early.
