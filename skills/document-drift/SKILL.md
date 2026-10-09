---
name: document-drift
description: Find markdown documentation that names files, anchors, scripts, runtime versions or directory entries that no longer exist, fix the provable ones and leave a commit on a new branch for review. Use when asked to check docs for drift, fix stale READMEs, or update docs after a refactor.
triggers:
  - /document-drift
---

# document-drift

Finds the markdown documents in a repository, checks every reference they make to the code
(file paths, `#anchors`, `make`/`npm`/`yarn`/`pnpm`/`just`/`task` scripts, runtime version
floors, directory-tree entries) and fixes the ones the git history proves stale. The result is
one commit on a new branch; the user's own process pushes it, reads the change and opens the
pull request. Everything here is a deterministic script: there are no agents in phase 1, and
your job is to run one command, relay its summary, and stop.

A path, anchor, script or tree reference is fixed only when it resolved at the commit that last
wrote its line and does not resolve now (the two-snapshot test), and git history gives one
provable outcome: a unique rename (replace the token), a deletion (delete the list item, table
row, command line or tree line it is the subject of, or unlink the link), or a renamed heading.
A runtime version floor is fixed when the nearest declared manifest floor (`requires-python`,
`engines.node`, the `go` directive, `rust-version`) contradicts it. Everything else is either counted in the summary (a name that never
existed, such as a runtime artefact or an illustrative path) or listed under "Needs a human
decision".

## When to use

- The user asks to check docs for drift, broken file references or stale READMEs.
- After a refactor that renamed or deleted files, headings, scripts or a runtime floor.
- Before a release, to clean docs on a branch the user will review.

Not for: writing missing documentation, prose style, external URL checking, `.rst` or `.adoc`
files, or changing code when the doc is right and the code is wrong.

## No improvisation

Run the one command below and nothing else. If it exits 5, an expected step output is missing
or a step crashed: stop and report the message verbatim. Do not hand-edit any doc, do not
re-run individual steps, do not invent the missing file, and do not retry with other flags
unless the user asks. Never push, never open a pull request, never run the project's code, and
never edit an excluded file (changelogs, licences, ADRs, plans and specs, research and archive
folders, vendored libraries, templates, generated files). The skill does none of these itself
either.

## Invocation

```
/document-drift <repo> [--base <ref>] [--branch <name>] [--check]
```

Run from this skill's directory (`skills/document-drift/`), with `<repo>` as an absolute path:

```bash
python scripts/dd_run.py <repo> [--base <ref>] [--branch <name>]
```

To report without editing anything (no branch, no commit, no change to the working tree):

```bash
python scripts/dd_run.py <repo> --check
```

| Flag | Effect |
|------|--------|
| `--base <ref>` | Only docs that changed in `<ref>...HEAD`, or that name a path changed in that range (at HEAD or at the line's snapshot). |
| `--branch <name>` | The branch to create. Default `docs/drift-<YYYY-MM-DD>`, or the `branch` pattern in `.document-drift.yaml`. |
| `--check` | Stop after planning the fixes; exit 1 when any provable edit exists. No doc edit, no branch, no commit (the workdir is still created and, inside the repository, added to `.git/info/exclude`). Runs from a detached HEAD too. |

The scripts also accept `--workdir <dir>` (default `<repo>/.document-drift`, added to
`.git/info/exclude`, never committed) and `--date YYYY-MM-DD` (fixes the branch date and run
id; for tests). Pass them only when the user asks.

## Preconditions the run checks

The run refuses (exit 2) when `<repo>` is not a git repository, has no commits, has a detached
HEAD, has uncommitted changes, already has the target branch, has no git author identity
(`user.name` and `user.email`), or when the branch name is not a valid git branch name. An
unknown or invalid `--base` ref is refused with exit 2 too. In `--check` mode only "not a git
repository", "no commits" and an unknown `--base` ref apply: check mode creates no branch, so
it also runs from a detached HEAD or a dirty tree.

## Exit codes

| Code | Meaning | What to tell the user |
|-----:|---------|-----------------------|
| 0 | Success. With provable fixes, a branch exists with one commit and the user is now on it. Without them, no branch was created. | The printed summary and the branch name (or "No branch created"). |
| 1 | `--check` only: provable edits exist. Nothing was changed. | The printed summary; a run without `--check` would commit those edits. |
| 2 | Refused before any change. | The error line verbatim and what to fix (commit or stash, check out a branch, choose another `--branch`, set the git identity). |
| 5 | An expected step output is missing, or a step crashed. | The error line verbatim (it names the step). Stop: do not edit docs by hand. When the step is `apply`, `commit` or `summary`, docs may already be edited, and after `commit` the drift branch and its commit may exist: tell the user to check `git status` and `git branch`. |
| 6 | The commit failed after the edits were applied to the working tree. | The error line verbatim: it says where the edits are. Some failures happen before any branch exists (HEAD moved during the run, `git switch -c` failed, an applied edit with no finding), leaving the edits in the working tree on the original branch; later ones name the drift branch the user is on and whether the edits are staged. Do not retry; the user decides. |

## What the user gets

- One branch, `docs/drift-<date>` by default, created from the starting HEAD with one commit
  `docs(drift): provable fixes`. Its body has a `Drift-Run`, `Drift-Base` and `Drift-Scope`
  line, one bullet per edit (`- <doc>:<line> replace|delete|unlink ... (<reason>)`) and, when
  there are any, a `Needs a human decision:` list. Only in-scope markdown files change.
- No branch at all when nothing is provable; the human-decision list is then in the summary
  only.
- Markers the user can add to a doc: `<!-- drift-ignore: reason -->` (the next block),
  `<!-- drift-ignore-next-line: reason -->`, `<!-- drift-ignore-file: reason -->`.
- Optional `.document-drift.yaml` at the repository root: `exclude` (extra globs),
  `never_edit_heading` (extra regex for sections never edited), `branch`, `commit_trailers`.

## Final message

Your final message to the user is the summary the command printed, verbatim, followed by the
branch name (or "No branch created"). Add nothing else except one line saying that pushing the
branch and opening the pull request are theirs to do.
