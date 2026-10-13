---
name: document-drift
description: Keep a repository's markdown docs matching what its code does, in both directions. Rewrites or removes statements the code contradicts or names the code no longer has, adds user-facing commands, flags, environment variables, MCP tools, routes and scripts no doc mentions, and marks blocks that describe the code but name nothing in it. Agents that read the repository and write only their own output file review the docs against the code, verifier agents check every edit, and the result is commits on a new branch for review. Use when asked to check docs for drift, fix stale READMEs, or update docs after a refactor or a release.
triggers:
  - /document-drift
---

# document-drift

Keeps a repository's markdown docs matching what its code does, in both directions. Docs to
code: a statement a doc makes about this repository's code that the code contradicts, or that
names something the code no longer has, is rewritten or removed. Code to docs: a command,
flag, environment variable, MCP tool, route or script the code offers its users that no doc
mentions, or that is missing from a doc's list of such things, is added to the docs. The docs
are the record of what to check: the first run reviews every doc against the code it points
at; later runs review only the statements whose code changed since the last run, and document
only user-facing names added since then. Scripts decide what to review, check every proposed
edit, apply and commit; agents you dispatch from plan files do the reading. The
result is commits on a new branch; the user's own process pushes it, reads the change and
opens the pull request.

Not for: pushing, opening pull requests or writing a PR body; creating doc files; editing
excluded files (changelogs, licences, ADRs and decision records, RFCs, plans and specs,
research and archive folders, vendored and generated docs, templates); changing code (a
guarantee the code does not keep is listed for the user, not edited); running the project's
code, builds, installs, examples or `--help`; external URL checking, `.rst` and `.adoc`,
translated READMEs, prose style or markdown lint.

## No improvisation

Run the stages in order, dispatch exactly the plan entries, and relay the final summary.
Never edit a doc, never write an agent's output file yourself, never rerun a stage except as
the exit 3 rule below says, never push and never open a pull request, and never run the
project's code. Do not retry with other flags unless the user asks. On exit 5, stop and report
the message verbatim; when the message names `apply`, `commit` or `summary`, tell the user to
check `git status` and `git branch`, since docs may already be edited and the branch may
exist. A crash outside a step at `finish` names no step, but its message already carries that
`git status` and `git branch` pointer; relay it verbatim.

## Invocation

```
/document-drift <repo> [--base <ref>] [--full] [--branch <name>] [--check]
```

Run every command from this skill's directory (`skills/document-drift/`), with `<repo>` as an
absolute path. Give `start` the flags the user gave; give `verify` and `finish` none of them
except `--workdir` (they read the others from the run's record, and a different value is
refused).

1. Start the run:

   ```bash
   python scripts/dd_run.py <repo> --stage start [--base <ref>] [--full] [--branch <name>] [--check]
   ```

   It prints `plan-docs.json <path> with <n> entries` (or, for a repository with no doc in
   scope, the message that no-docs mode arrives in phase B).

2. Read `plan-docs.json`, the file at the path printed on the stdout line. For each entry
   dispatch one general-purpose Agent with the entry's `model`; it must have Read, Grep, Glob
   and Write, so it can write its one output file, and it is read-only toward the repository.
   Its prompt is exactly:

   `Read the file <prompt> in full and follow it. Write only <output>.`

   with the entry's `prompt` and `output` paths filled in. Dispatch all entries in one message
   so they run in parallel. Never paste the prompt file's content, and never write an output
   file yourself: each agent writes its own and replies with a receipt. When the file holds
   `[]`, skip to step 5.

3. Verify the agents' outputs and check their edits:

   ```bash
   python scripts/dd_run.py <repo> --stage verify
   ```

   On exit 3 it prints `retry.json <path> with <n> entries`: read `retry.json` at that path,
   dispatch those entries once, exactly as in step 2, then rerun the same command with
   `--retried`:

   ```bash
   python scripts/dd_run.py <repo> --stage verify --retried
   ```

   Otherwise it prints `plan-verify.json <path> with <n> entries`.

4. Read `plan-verify.json`, the file at the path printed on the stdout line, and dispatch the verifier entries the same way as in step 2, all in
   one message. When it holds `[]`, go to step 5.

5. Finish the run:

   ```bash
   python scripts/dd_run.py <repo> --stage finish
   ```

   On exit 3, the same rule as step 3: read `retry.json`, dispatch those entries once, then
   rerun with `--retried`:

   ```bash
   python scripts/dd_run.py <repo> --stage finish --retried
   ```

   Otherwise it prints the summary.

| Flag | Effect |
|------|--------|
| `--base <ref>` | Compare against `<ref>` instead of the last drift run. An unknown ref is refused. |
| `--full` | A first run (every doc reviewed in full) regardless of any previous run. |
| `--branch <name>` | The branch to create. Default `docs/drift-<YYYY-MM-DD>`, or the `branch` pattern in `.document-drift.yaml`. |
| `--check` | Run through verification and stop: no doc edit, no branch, no commit, no last-run record. The summary lists every edit that would apply as a commit bullet; `finish` exits 1 when an edit would apply (an accepted edit, or a kept notice edit, which needs no verdict). Runs from a detached HEAD or a dirty tree too; results are judged against the working tree, and a dirty indexed file can shift line ranges. |
| `--workdir <dir>` | Where the run's files go. Default `<repo>/.document-drift`, added to `.git/info/exclude`, never committed. Pass it only when the user asks, and then to every stage. |
| `--date <YYYY-MM-DD>` | Fixes the branch date and run id (for tests). Pass it only when the user asks. |
| `--retried` | Only on the rerun of a stage that exited 3, after dispatching `retry.json`. An output still missing or invalid then leaves its unit or batch unchecked, and the run goes on. |

`--base`, `--full`, `--branch`, `--check` and `--date` are given to `start`, which records
them; `verify` and `finish` take them from that record and refuse a different value (exit 2).

## Preconditions the run checks

`start` refuses (exit 2) when `<repo>` is not a git repository, is not the top level of a
working tree (a subdirectory, a bare repository or a `.git` directory: pass the repository's
top level), has no commits, or when `--base` names an unknown ref. Outside `--check` it also
refuses a detached HEAD, uncommitted changes, an existing target branch, a missing git author
identity (`user.name` and `user.email`) and an invalid branch name. Any stage refuses when it
is run out of order or with a flag that differs from the one `start` recorded, and `finish`
refuses, before it applies anything, when HEAD moved during the run (naming both commits; a
branch switch counts) or when files outside the workdir changed during the run (naming them).

## Exit codes

| Code | Meaning | What to tell the user |
|-----:|---------|-----------------------|
| 0 | The stage succeeded. From `finish`: with edits, the branch exists with its commits and the user is on it; without edits, no branch was created. | After `start` and `verify`, nothing: go on to the next step. After `finish`, the final message below. |
| 1 | `finish` under `--check` only: an edit would apply (an accepted edit, or a kept notice edit). Nothing was changed. | The printed summary; a run without `--check` would commit those edits. |
| 2 | Refused before any change. | The error line verbatim and what to fix (commit or stash, check out a branch, choose another `--branch`, set the git identity, run the stages in order with the same flags, leave the working tree and the checked-out branch alone during a run). |
| 3 | The previous agent wave left missing or invalid output files; the stage wrote `retry.json` and changed nothing else. | Nothing: dispatch the `retry.json` entries once and rerun the same stage with `--retried`. |
| 5 | A script step crashed or a script's own expected output is missing. The message names the step; a crash outside a step names none, and at `finish` its message already carries the `git status` and `git branch` pointer. | The error line verbatim. Stop: do not edit docs by hand. When the step is `apply`, `commit` or `summary`, docs may already be edited and the drift branch may exist: tell the user to check `git status` and `git branch`. |
| 6 | The commit failed after the edits were applied to the working tree. | The error line verbatim: it says where the edits are. Do not retry; the user decides. |

## What the user gets

- One branch, `docs/drift-<date>` by default, created from the starting HEAD with at most two
  commits, `docs(drift): correct stale docs` (review edits and notice edits) and then
  `docs(drift): document missing surface` (additions). A commit with no edits is not made.
  Each body has the lines `Drift-Run: <run id>`, `Drift-Base: <starting HEAD sha>`,
  `Drift-Scope: first | since <sha> | base <ref> | full` and
  `Drift-Unchecked: <n> doc units, <n> gap docs, <n> verify batches`, then one bullet per
  edit (`- <doc>:<line> correct|remove|anchor|add ...` and the notice bullets). The last
  commit made ends with a `Needs a human decision:` list when there is one: guarantees the
  code does not keep, unsure claims, blocks with a 2nd notice, edits too large or in a
  protected region, overlapping edits, names with no home, refused targets, edits a verifier
  rejected and edits reverted by the re-check. Only in-scope markdown files change. The
  `Drift-Base` line is how the next run finds where to start.
- `No branch created` when no edit was applied; the human-decision list is then in the
  summary only.
- Markers the user can add to a doc: `<!-- drift-ignore: reason -->` (the next block),
  `<!-- drift-ignore-next-line: reason -->`, `<!-- drift-ignore-file: reason -->`. A marker
  needs the colon and a reason; one without is listed in the summary and has no effect.
- The skill's own notices: a block that describes the code but names nothing the skill can
  tie to a definition gets a `<!-- drift-unverified: 1st notice, ... -->` comment on the line
  above it. The user answers it in one of three ways: name what the block describes (in an
  inline-code span), add a `drift-ignore: <reason>` marker, or rewrite the block. Any of them
  clears the notice on the next run (a rewritten block is reviewed afresh and may get a new
  1st notice). Unanswered, the next run turns it into a 2nd notice and
  lists the block under "Needs a human decision"; unanswered again, the run after that removes
  the block and its notice. The user must not edit a notice by hand except to answer it; a
  malformed notice is listed as stale and left alone.
- Optional `.document-drift.yaml` at the repository root:

  | Key | Default | Effect |
  |-----|---------|--------|
  | `exclude` | `[]` | Extra globs of docs to leave out. |
  | `never_edit_heading` | none | Extra regex for sections never edited. |
  | `branch` | `docs/drift-{date}` | The branch name pattern. |
  | `commit_trailers` | `[]` | Lines appended at the end of each commit message. |
  | `unit_lines` | `6000` | Line budget per review unit. |
  | `max_delete_lines` | `15` | Larger removals go to a human. |
  | `max_section_lines` | `40` | Larger additions go to a human. |
  | `min_anchor_ratio` | `0.25` | Docs anchoring below this are listed as weakly anchored. |
  | `undocumented_ok` | `[]` | Globs of names that are never gaps. |
  | `caps.review` / `caps.gaps` / `caps.verify` | `40` / `15` / `25` | Agents per run per role; work beyond a cap is listed as unchecked. |
  | `models.review` / `models.gap` / `models.verify` | `sonnet` / `sonnet` / `opus` | The model each role's agents run on. |

## Final message

Your final message to the user is the summary `finish` printed, verbatim, followed by the
branch name (or `No branch created`). Add nothing else except one line saying that pushing
the branch and opening the pull request are theirs to do.
