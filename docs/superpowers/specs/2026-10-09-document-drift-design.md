# document-drift: detect and fix stale markdown

Provenance: brainstormed 2026-10-09 from the research series in `docs/research/document-drift/` (01 to 07). The brief `07-brainstorm-brief.md` carried fourteen open decisions; the owner settled the ones that shape the design in the session, recorded in section 1.3. Citations of the form [02] refer to those notes.

Fixed constraints, inherited from the repository's two existing skills: Claude Code skill; SKILL.md orchestration with pinned commands, pinned output files and the exit-5 no-improvisation rule; pure Python 3.11+ with pyyaml as the only dependency, every script direct-path invocable as `python scripts/<name>.py`; read-only Agent subagents for LLM work, each writing its own output file with the Write tool and replying with a receipt; large data passed between steps as file paths, never inline on an argv (Windows 8191-character limit); redaction at every write of repository-derived text; LF-only output; no live LLM in tests; ruff, mypy strict, pytest and a SKILL.md linter in CI.

## 0. Guardrails for planning and implementation

- **(a) Assumptions surfaced.** Section 11 lists every assumption with status and cost if wrong. The validation pass in section 11.2 ran before owner review.
- **(b) Confidence per task.** Every plan task carries a confidence percentage; anything under 90 percent is resolved by investigation, a question or a spike before implementation.
- **(c) Documentation ships with code.** The repository `README.md`, `docs/architecture.md` (a new document-drift section) and `skills/document-drift/SKILL.md` change in the same PR as the code they describe. The skill must pass its own scan on this repository at the end of every phase.
- **(d) No input-specific rules.** No resolver, constant or test may depend on the identity of a fixture or a real repository. Constants (lead cap, recent-change window, fuzzy distance) are set inside bands measured across every available input and named in section 11 when they rest on few inputs.
- **(e) One branch, one PR per phase.** `feat/document-drift-phase-<n>`, created before the phase's first task. Approved specs and plans land on main.
- **(f) No time estimates.** Work is sized by scope and risk only.

## 1. Goal, non-goals, decisions

### 1.1 Goal

A skill, `/document-drift <repo>`, that finds the markdown documents in a repository, determines which of their statements about the code are no longer true, rewrites the documents to match the code where the evidence supports an edit, and leaves the result as commits on a new branch. The owner's own process pushes the branch, reads the change and opens the pull request; human review of that pull request is the gate before anything reaches the default branch.

### 1.2 Non-goals

- Pushing, opening pull requests, writing a PR body, or touching any remote.
- Writing documentation that does not exist (absence is tech-debt-scan's TD-08 half; incompleteness is not drift [01]).
- Editing CHANGELOG, HISTORY, LICENSE, NOTICE, CODE_OF_CONDUCT, ADRs, RFCs, superpowers plans and specs, roadmap, rationale or deprecation sections, people and sponsor lists, or generated regions.
- Changing code when the doc is right and the code is wrong. Those findings are reported, never "fixed" in the doc [02 DD-18].
- Executing project code, building, installing, or running examples. Fenced blocks are parsed and their references resolved, nothing more.
- External URL checking, `.rst` and `.adoc`, translated READMEs (later phase, section 10).
- Prose style or markdown lint (Vale and markdownlint exist).
- A health score.

### 1.3 Decisions taken in the brainstorm

| # | Decision | Owner's answer |
|---|---|---|
| D7 | Gate for edits | The skill edits the files and commits; a human validates in PR review. No report round-trip, no interactive prompts |
| D-out | Output | A new branch with commits only. No push, no PR body file |
| D-shape | Commit structure | One commit per fix class: provable fixes, then rewritten prose |
| D-unfix | Findings not edited | Listed in a "Needs a human decision" section at the end of the last commit message; when there are no edits, printed only and no branch is created |
| D5 | Examples | Parse and resolve only; never execute |
| D4 | Scope | Whole repository by default; `--base <ref>` narrows to docs that reference code changed since the ref |
| D2 | Identifiers | Acted on only when the two-snapshot test shows the identifier existed when its line was last written and is gone now. Amended by the validation pass: the snapshot is per line, and identifiers are never deleted by script, only replaced on a unique rename or reported |
| D9 | tech-debt-scan | Standalone; a `--from-evidence` seam is specified (section 10) and built in a later phase |
| D13 | Documents | `.md` files outside the exclusions, including CLAUDE.md and AGENTS.md at any depth |
| D-arch | Architecture | Script pipeline with narrow agents, tech-debt-scan's pattern |
| D14 | Rewrite quality bar | Measured on the first live run; the bar is set from that measurement |

### 1.4 Success criteria

1. On a clean tree, a run that finds provable drift leaves exactly one new branch whose commits change only in-scope markdown files, and leaves the original branch and working tree untouched.
2. On the fixture corpus, every planted drift item of a class the current phase covers produces the expected edit, and no planted decoy produces an edit.
3. Every provable edit is correct on the corpus (100 percent; a wrong provable edit is a defect, not a rate).
4. Every edit, after application, clears its finding on re-check and creates no new finding.
5. Commit messages match the grammar in section 7 exactly, so the owner's PR process can parse them; a test asserts the grammar.
6. Scripts produce byte-identical outputs for a fixed repository state and fixed agent files.
7. A second run on the resulting branch finds nothing to edit for the same findings (idempotence), and a `drift-ignore` marker suppresses a finding on every later run.
8. The skill passes its own scan on this repository.
9. The rewrite acceptance rate is measured and logged on the first live run (phase 3); the bar is set from it.

## 2. Command contract

```
/document-drift <repo> [--base <ref>] [--branch <name>] [--workdir <dir>] [--no-agents]
```

- `<repo>` defaults to the current directory.
- `--base <ref>`: scope to docs that reference (at HEAD or at a token's line snapshot) a path changed in `git diff --name-only <ref>...HEAD`, plus docs changed in that range.
- `--branch <name>`: default `docs/drift-<YYYY-MM-DD>`; a pattern can be set in config.
- `--workdir`: default `.document-drift`. The skill adds the workdir to `.git/info/exclude` (never to `.gitignore`, which would be a repository change) and never commits it.
- `--no-agents`: run only the deterministic stages (always the behaviour in phases 1 and 2).

Exit codes: 0 success (with or without a branch); 2 refused (dirty tree, detached HEAD, branch exists, not a git repository); 5 an expected step output is missing (the no-improvisation rule); 6 commit failed after edits were applied (edits left in the working tree, branch left in place, the summary says which step failed).

The run never switches the user's checkout away from where it started except to create the drift branch at commit time; it creates the branch from the starting HEAD with `git switch -c`, carrying the working-tree edits, commits, and leaves the user on the drift branch. The summary prints the branch name and the commit hashes.

## 3. Pipeline

Script steps run from `skills/document-drift/` with pinned commands and pinned outputs under `--workdir`. Agent steps dispatch read-only agents whose prompts are rendered to files by a script.

| Step | Layer | Command or agent | Output | Phase |
|---|---|---|---|---|
| 1 | Script | `preflight.py` | `preflight.json` (HEAD sha, branch, clean tree, git version, workdir excluded) | 1 |
| 2 | Script | `inventory.py` | `inventory.json` (every file classified; in-scope docs; exclusions with reasons; per-file last-touched; per-doc last substantive commit) | 1 |
| 3 | Script | `extract.py` | `tokens.json` (typed tokens per doc with line, column, block context, section heading path, ignore state) | 1 |
| 4 | Script | `resolve.py` | `candidates.json` (unresolved tokens with history lookups, proposed class, evidence) | 1, extended in 2 |
| 5 | Script | `leads.py` | `leads.json` and `prompts/judge-<nn>.md` | 3 |
| 6 | Agent | judge | `judged/judge-<nn>.json` | 3 |
| 7 | Script | `verify_prompts.py` | `prompts/verify-<nn>.md` | 3 |
| 8 | Agent | verifier | `verdicts/verify-<nn>.json` | 3 |
| 9 | Script | `merge.py` | `findings.json` (every finding, quote re-found on disk, fingerprinted, final class) | 1 |
| 10 | Script | `fixes.py` | `hunks-provable.json` | 1 |
| 11 | Agent | rewriter | `rewrites/rewrite-<nn>.json` | 3 |
| 12 | Agent | checker | `checks/check-<nn>.json` | 3 |
| 13 | Script | `apply.py` | edited docs in the working tree; `applied.json` (applied, reverted with reason) | 1 |
| 14 | Script | `commit.py` | the branch and commits; `commits.json` | 1 |
| 15 | Script | `summary.py` | `summary.md` printed to the terminal | 1 |

In phases 1 and 2, steps 5 to 8, 11 and 12 do not exist; `merge.py` reads only `candidates.json`.

## 4. Inventory and scope

**Walk.** Copied from tech-debt-scan's `inventory.py` walk and path classification (section 9), with symlinks skipped, files over 2 MB or with a NUL in the first KB skipped, and the standard ignore list (`.git`, `node_modules`, `vendor`, `third_party`, `.venv`, `venv`, `site-packages`, `dist`, `build` under the existing conditional rule, `target`, `.tox`, `__pycache__`).

**In scope.** Files ending `.md` (case-insensitive) that survive the exclusions. CLAUDE.md and AGENTS.md at any depth are in scope.

**Built-in exclusions**, each recorded with its reason in `inventory.json` and in the summary:

- Paths: `docs/superpowers/**` (plans, specs, and the archive and research folders beside them), `.superpowers/**`, `docs/research/**`, `**/research_notes/**`, `**/archive/**`, `**/adr/**`, `**/adrs/**`, `**/decisions/**`, `**/rfcs/**`, `**/rfc/**`. The validation pass (11.2) found nearly every stale-looking reference in the owner's repositories inside archive and research folders, which are dated records by nature.
- Vendored nested libraries: a directory below the root that holds its own `LICENSE*` file and a package or library manifest (`package.json`, `pyproject.toml`, `setup.py`, `Cargo.toml`, `go.mod`, `library.json`, `library.properties`, `CMakeLists.txt` with a `project(` line) whose name differs from the root project's, or any directory under `libraries/`, `extern/`, `external/`, `third_party/`, `deps/`. The validation pass found a copied Arduino library's own docs producing findings.
- Basenames: `CHANGELOG*`, `CHANGES*`, `HISTORY*`, `RELEASE_NOTES*`, `LICENSE*`, `LICENCE*`, `NOTICE*`, `COPYING*`, `CODE_OF_CONDUCT*`, `SECURITY*`, `AUTHORS*`, `CONTRIBUTORS*`, `MAINTAINERS*`, `CODEOWNERS`.
- Classes from the copied path classifier: vendored, generated, tests (a `README.md` under `tests/` is a fixture, not a doc).
- `.gitattributes` entries marking a path `linguist-generated` or `linguist-vendored`.
- A file whose first five lines contain `DO NOT EDIT` or `Code generated`.
- Git submodules (paths listed in `.gitmodules`).
- Templates: a file under a directory named `templates`, `template`, `skeleton` or `cookiecutter*`, or whose name ends `.tmpl.md`.
- `<!-- drift-ignore-file: reason -->` anywhere in the file.
- Config `exclude` globs.

**Never-edit sections.** Inside an in-scope doc, a section whose heading matches the never-edit regex (default `(?i)\b(why|rationale|decision|decisions|history|roadmap|deprecated|deprecation|migration|changelog|release notes|license|licence)\b`) is scanned for the summary but every finding in it becomes a human decision. Config may extend the regex.

**Line snapshot.** For each token that does not resolve at HEAD, the snapshot is the commit that last changed the token's line: `git blame -w -M --porcelain -L <n>,<n> -- <doc>`. Ignoring whitespace (`-w`) and in-file moves (`-M`) keeps formatting commits from resetting it. This sha is the token's **snapshot** for the two-snapshot test (6.2). A per-line snapshot, not the doc's last commit, is required: the validation pass (11.2) found docs edited after a file's deletion, and lines written in the deleting commit to say the file is gone ("There is no `PROMPT.md` file"); both must read as deliberate, never as drift.

**Doc lag.** The doc's last substantive commit (newest commit whose diff for the doc changes a line outside link targets and whitespace, author not a bot by the copied `bot_authors` rule) is kept only as an ordering key for phase 3 judge leads.

**`--base` scope.** Changed paths from `git diff --name-only <ref>...HEAD`. A doc is in scope when it changed in the range, or when any of its path tokens resolves (at HEAD or at the doc's snapshot) to a changed path or a directory containing one, or when any identifier token appears in a changed file at the base ref.

## 5. Extraction

`md_scan.py` is a pure-Python block scanner sufficient for CommonMark structure the resolvers need: ATX and setext headings, fenced code blocks (backtick and tilde, info string, length-aware closing, fences indented inside list items), indented code, block quotes, list items, tables (with escaped pipes), HTML comments, link reference definitions and reference-style links, inline code spans (including spans that continue across a line break and multi-backtick spans), inline links, images and autolinks. It is not a renderer; it reports spans with line and column. The constructs listed after the basics are the ones a naive line scanner got wrong in the validation pass (11.2). A parity test compares its spans with `markdown-it-py` on a fixed corpus of real documents; `markdown-it-py` is a dev-only test dependency, so the runtime stays pyyaml-only.

`extract.py` emits one token per occurrence with: `doc`, `line`, `col`, `kind`, `text`, `context` (`prose`, `inline-code`, `fence:<info>`, `link-target`, `table-cell`, `heading`, `tree-block`), `heading_path`, `ignored` (and the marker reason).

| Kind | Where it comes from | Phase |
|---|---|---|
| `path` | Inline code or a fence line that looks like a path (contains `/` or a known extension, no spaces, not a URL); link and image targets without a scheme | 1 |
| `anchor` | `#fragment` in a link target, same doc or another doc | 1 |
| `script` | `make <t>`, `npm run <t>`, `yarn <t>`, `pnpm <t>`, `just <t>`, `task <t>`, `./<path>`, `python <path>`, `bash <path>`, `sh <path>` in fences and inline code | 1 |
| `version` | Runtime floors and versions near a runtime word: `Python 3.11+`, `Node >= 18`, `requires Go 1.22`, `rust 1.75`, and the project's own name followed by a version | 1 |
| `tree` | A fenced block without an info string (or `text`) whose lines look like a directory tree (`├──`, `└──`, `|--`, or indented names ending `/`) | 1 |
| `identifier` | Inline code that matches an identifier shape (`snake_case`, `camelCase`, `PascalCase`, dotted `a.b.c`, `Name()`), not a path, not a keyword | 2 |
| `flag` | `--long-flag` and `-x` tokens in fences and inline code following a command word | 2 |
| `envvar` | `UPPER_SNAKE` tokens of at least two segments in inline code, fences, or after `$`/`${`/`%`/`env.` | 2 |
| `configkey` | Inline code `a.b.c` or `snake_key` inside a section whose heading matches `(?i)config|settings|options|environment`, or in a table row in such a section | 2 |
| `claim` | Sentences containing a capability or time word (`not supported`, `does not`, `doesn't`, `cannot`, `only`, `currently`, `not yet`, `no longer`, `by default`, `always`, `never`) that also contain another token | 3 (lead source) |

Placeholders are dropped at extraction: anything containing `<...>`, `{{...}}`, `${...}` as the whole token, `your-`, `my-`, `example`, `foo`, `bar`, `baz`, `xxx`, `TODO`, `*` globs, and paths under a directory the doc instructs the reader to create (a `mkdir`, `touch` or "create" verb on the same line or the preceding line). Not paths: a token whose only `/` is a leading one (`/pipeline`, `/tech-debt-promote`, URL routes and slash commands), a fraction or ratio (`3/5`, `X/Y`), a dotted name with no `/` and no known extension.

Runtime artefacts are a large share of unresolved paths in practice (`.tech-debt/`, `inventory.json`, `state.json`): they are produced by running the project and are never in the tree. They resolve `never-existed` and are summary-only, which is the intended outcome; no special rule is needed.

## 6. Resolution and classification

### 6.1 Resolvers

All resolvers are language-neutral by union of idioms; none executes project code.

- **Path.** Resolved relative to the doc's directory, then the repository root. A path that resolves to a directory is resolved. A trailing `:line` or `#L<n>` is stripped before resolving.
- **Anchor.** Target doc's headings slugged GitHub-style (lower-case, punctuation other than `-` and `_` removed, spaces to `-`, duplicate suffix `-1`, `-2`), plus explicit `<a name>` and `id=` anchors.
- **Script.** Makefile targets (`^name:` rules, excluding `.PHONY` lines), `package.json` `scripts` keys at the nearest enclosing package, `justfile` recipes, `Taskfile.yml` tasks, and file existence for path-invoked scripts.
- **Version.** The nearest manifest: `pyproject.toml` `requires-python`, `package.json` `engines.node`, `Cargo.toml` `rust-version`, `go.mod` `go` directive, `.nvmrc`, `.python-version`, `.tool-versions`, and the project's own version from the same manifests. TOML is parsed with `tomllib` (standard library). A version claim is drift only when the manifest states a different floor; a doc floor higher than the manifest is drift too.
- **Tree.** Each entry's path, assembled from indentation, must exist. Entries the doc omits are never drift.
- **Identifier (phase 2).** Present when it appears as a whole token in any tracked non-markdown text file at HEAD: source, config and data files alike (CSV headers and JSON keys name things docs talk about). The same file classes are used at the snapshot, so the two sides of the test are comparable. Dotted names resolve when the last segment resolves and, if the other segments name a module path, that path exists. A name that also appears with `_` and `.` swapped (`memory_record_use` and `memory.record_use`), or with a prefix stripped, resolves: tool and command names are often derived at runtime.
- **Flag (phase 2).** Present when it appears as a string literal in any source file (`"--name"`, `'--name'`), or in a definition idiom for argparse, click, typer, clap (`long = "name"`, `#[arg(long)]` on a field `name`), cobra and pflag (`Flags().<Type>("name"`), commander and yargs (`.option('--name`), picocli (`names = {"--name"`), System.CommandLine (`"--name"`), or in a checked-in man page or `--help` text file.
- **Envvar (phase 2).** Present when it appears in any source, config, Dockerfile, compose, CI workflow or `.env.example` file.
- **Configkey (phase 2).** Present when its last segment appears as a key in any config-classified file, or as a string literal or field name in any source file.

### 6.2 History lookups for unresolved tokens

- **Two-snapshot test.** Did the token resolve at its line snapshot (section 4)? Paths: `git cat-file -e <sha>:<path>` for each candidate resolution. Anchors: the target doc's headings at that sha. Identifiers, flags, env vars, config keys: `git grep -w -F -q <token> <sha> -- <the same pathspecs as the HEAD resolver>`. Result: `existed-then` (resolved when the line was last written, and not now) or `never-existed` (did not resolve when the line was written: a deliberate mention of something removed, an illustrative name, a runtime artefact, or a mistake at birth).
- **Path rename.** `git log --follow -M --diff-filter=R --name-status --format=%H <snapshot>..HEAD -- <path>`, and when that finds nothing (the path no longer exists so `--follow` cannot start), `git log -M --diff-filter=R --name-status <snapshot>..HEAD` filtered to entries whose old path equals the token. Chains are followed to the final name. Unique final name existing at HEAD: `rename-unique`. Several: `rename-ambiguous`. None: `deleted`.
- **Symbol rename (phase 2).** `git log -S<token> --format=%H <snapshot>..HEAD` gives the commits that changed the token's occurrence count. In the newest commit that removed the last occurrence, pair each removed line containing the token with the added lines of the same hunk; the replacement candidate is the token at the same position in the most similar added line (token-level alignment). One candidate across all such lines, which resolves at HEAD: `rename-unique`. Otherwise `rename-ambiguous` or `deleted`.
- **Version.** The manifest value is the fix.

### 6.3 Classes

| Class | Condition | Edit |
|---|---|---|
| `provable-replace` | `existed-then` and `rename-unique`, or a version mismatch with a manifest value, or an anchor whose heading was renamed with a unique match | Token-exact replacement by script |
| `provable-delete` | A `path`, `anchor`, `script` or `tree` token that is `existed-then` and `deleted`, and whose deletion unit (section 7.1) is smaller than a paragraph. Never an identifier, flag, env var or config key: in the validation pass every identifier that existed then and not now, in a live doc, was a false positive | Deletion by script |
| `rewrite` | A judged finding confirmed by the verifier (phase 3) | Hunk by the rewriter, checked by the checker |
| `human` | `rename-ambiguous`; an identifier, flag, env var or config key that is `existed-then` with no unique rename (kind `removed-symbol`); a deletion unit of a paragraph or more; a token in a never-edit section; a finding in a generated region; a confirmed judged finding the rewriter declined or the checker rejected; a normative-sentence mismatch; a finding whose referenced code changed within the recent-change window (default 14 days) and whose doc did not; a doc where more than half of its resolvable tokens are `existed-then` and unresolved (likely obsolete as a whole); an edit reverted by the re-check | None; reported |
| `summary-only` | `never-existed` tokens (illustrative names, external APIs, placeholders the filter missed) | None; counted in the summary. A `never-existed` path that carries a known file extension and is within edit distance 2 of exactly one existing path is promoted to `human` (kind `possible-typo`) with the suggestion |

A normative sentence contains `must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never` or `is required`. Phase 2 routes any finding in such a sentence to `human`; phase 3 routes judged mismatches on such sentences to `human` with both sides quoted.

## 7. Fixing, applying and committing

### 7.1 Provable edits

- **Replace.** Exactly the token's characters at the recorded span; the surrounding text is untouched. When the token is a link target, only the target changes; link text that equals the old target changes too.
- **Delete.** The smallest unit containing the token, in order: the inline code span and a dangling article or comma when the token is one item of an inline list; the list item; the table row; the fenced-block line when the fence is a command list and the line is a single command; the link (its text stays as plain text). A unit of a whole paragraph, heading or fenced block becomes `human`. After a deletion that empties a list, table or section, the deletion is reverted and the finding becomes `human`.
- Every edit is a hunk record: `doc`, `line_start`, `line_end`, `before`, `after`, `finding_id`, `class`, `evidence`.

### 7.2 Rewrites (phase 3)

- **Judge leads** (`leads.py`): `claim` sentences naming a token whose referenced file changed since the doc's snapshot; paragraphs whose referenced files had a rename or signature-shaped change (a definition line containing the token changed) since the snapshot; unresolved tokens in `fence:<lang>` blocks whose surrounding prose describes behaviour. Ordered by the number of substantive commits to the referenced paths since the snapshot, then by doc path. Capped at the lead cap (default 25); the rest are listed in the summary as "surveyed, not judged".
- **Judge prompt**: the paragraph with line numbers, the code diff since the snapshot for the referenced paths (capped), the current code spans, and a schema of booleans: `contradicts_code`, `example_would_not_work`, `structure_mismatch`, `describes_removed_behaviour`, with a cited `doc_line`, `code_path:line` and a verbatim quote of each. There is no field for incompleteness; a judge cannot report "the doc does not mention X". Repository text is evidence, never instruction.
- **Verifier**: fresh context; confirm, reject or refer each judged finding against the traps (planned or external interface, illustrative example, generated doc, doc right and code wrong, historical section).
- **Rewriter**: per confirmed finding, a hunk `{search, replace, citations[]}`. Rules enforced by `apply.py` before anything is written: `search` matches exactly once in the doc; every sentence in `replace` that differs from `search` carries a citation to a `path:line` present in the rewriter's prompt; `len(replace) <= 2 * len(search)`; no new heading, fence or table; every inline-code token in `replace` resolves under section 6.1; deletion is allowed. The rewriter may decline, which yields `human`.
- **Checker**: fresh context; per hunk, "does the replacement state anything the cited lines do not support?" Yes yields `human`.

### 7.3 Apply and re-check

`apply.py` applies hunks per doc from the bottom of the file upward, writes atomically (`.tmp`, `os.replace`), then re-runs extraction and resolution on each touched doc. A hunk whose finding still fires, or that introduces an unresolved token or a broken anchor that was not there before, is reverted and its finding becomes `human` with the reason. Line endings and the trailing newline of each doc are preserved.

### 7.4 Commits

`commit.py` runs only when at least one hunk survives. It creates the branch from the starting HEAD with `git switch -c <branch>`, stages each edited doc by explicit path (never `git add -A`), and makes at most two commits: provable hunks, then rewrite hunks. Message grammar (a test pins it):

```
docs(drift): provable fixes

Drift-Run: <run-id>
Drift-Base: <starting HEAD sha>
Drift-Scope: all | base:<ref>

- <doc>:<line> replace `<old>` -> `<new>` (<reason>)
- <doc>:<line> delete `<token>` (<reason>)
```

```
docs(drift): rewrite stale prose

Drift-Run: <run-id>

- <doc>:<line_start>-<line_end> <one-line reason>
  evidence: <code_path>:<line>[, <code_path>:<line>...]
```

`<reason>` is one of `renamed in <short-sha>`, `deleted in <short-sha>`, `manifest <file> says <value>`, `heading renamed in <short-sha>`. The last commit's body then ends with:

```
Needs a human decision:
- <doc>:<line> [<kind>] <one-line statement>
  evidence: <code_path>:<line> | <commit short-sha> | <manifest value>
```

`<kind>` is one of `ambiguous-rename`, `removed-symbol`, `large-deletion`, `never-edit-section`, `generated-region`, `normative-mismatch`, `recent-code-change`, `obsolete-doc`, `possible-typo`, `rewrite-declined`, `rewrite-rejected`, `recheck-failed`. Commit trailers (attribution) come from config `commit_trailers`, empty by default. Every string written passes through `redact`. When no hunk survives, no branch is created and the same "Needs a human decision" list is printed in the summary.

## 8. Configuration, markers and summary

`.document-drift.yaml` at the repository root, optional:

```yaml
exclude: []                  # extra globs
never_edit_heading: null     # extra regex, OR-ed with the default
lead_cap: 25
recent_change_days: 14
branch: "docs/drift-{date}"
commit_trailers: []
```

Inline markers (HTML comments, so they do not render): `<!-- drift-ignore-file: reason -->`, `<!-- drift-ignore: reason -->` (the next block), `<!-- drift-ignore-next-line: reason -->`. A marker without a reason is itself reported in the summary and ignored. A marker whose block produces no finding is reported as stale; the skill never removes markers.

Generated regions: blocks between markers of embedme (`<!-- embedme ... -->`), mdsh (`<!-- BEGIN mdsh -->`), cog (`[[[cog` ... `[[[end]]]`), terraform-docs (`<!-- BEGIN_TF_DOCS -->`), and `<!-- BEGIN GENERATED`/`<!-- END GENERATED` are never edited; findings inside become `human` with kind `generated-region`.

`summary.md`: run id; scope; docs scanned and docs excluded by reason; tokens per kind and resolution rate; findings per class; hunks applied and reverted; the human-decision list; markers without reasons and stale markers; "surveyed, not judged" docs; the branch and commit hashes or "no branch created".

## 9. Code inventory

New skill directory `skills/document-drift/` with `SKILL.md`, `scripts/`, `prompts/` (phase 3), `tests/`.

Copied from `skills/tech-debt-scan/scripts/` with a test asserting byte equality against the source or naming an intended divergence: `redaction.py`, `validation.py`, `slugs.py`, `evidence.py` (`find_quote`, `fingerprint`), `git_history.py`, `reference_graph.py` (`identifier_tokens`, `file_stem`), `skill_check.py`. Copied and adapted: the walk, ignore and path-classification parts of `inventory.py`, `config.py`, `tests/helpers/make_history.py` (gaining a `rename` key so fixtures can express renames git detects). New: `preflight.py`, `md_scan.py`, `extract.py`, `resolve.py`, `history.py` (two-snapshot, path and symbol rename), `merge.py`, `fixes.py`, `apply.py`, `commit.py`, `summary.py`, and in phase 3 `leads.py`, `verify_prompts.py`, the prompt templates and a `live_run.py` harness adapted from tech-debt-scan's.

### 9.1 Tests and evaluation

- **Fixture corpus** at `tests/fixtures/corpus/<name>/`: `files/` (final tree), `history.yaml` replayed into a real repository by the copied `make_history.py` (renames, the two-snapshot test and blame are history facts), `planted.json` with `planted[]` and `decoys[]`. Three fixtures, Python, TypeScript and Go, so every resolver idiom has a positive case in at least two.
- **Planted drift**, each with doc file, line and expected class: a path renamed in a later commit (provable replace); a path deleted with no rename (provable delete); an anchor whose heading was renamed; a removed make or npm script; a version floor behind the manifest; a directory tree entry renamed; a CLAUDE.md naming a deleted script. Phase 2 adds: a removed identifier with a unique rename, a removed flag, a renamed env var, a removed config key. Phase 3 adds: a stale negation ("X is not supported" where X shipped) and an example whose described behaviour changed.
- **Planted decoys**, each with `why` and must produce no edit: a sentence written in the deleting commit saying the file no longer exists (S3's shape); an illustrative identifier that never existed; an external API name; a path the doc tells the reader to create; a runtime artefact path; a URL route and a slash command; a CHANGELOG entry; a file under `docs/superpowers/plans/`; a vendored library's README; a section under a "Rationale" heading; a generated region; a block under `drift-ignore`; a normative "must" sentence where the code regressed (expected `human`, never an edit); a reference whose code changed within the recent-change window (expected `human`).
- **Goldens**: `inventory.json`, `tokens.json`, `candidates.json`, `findings.json`, `hunks-provable.json`, the edited docs and the commit messages, byte-compared, regenerated only under `UPDATE_GOLDENS=1`. Phase 3 agent outputs are canned files from the first live run.
- **End to end**: replay a fixture, run the whole chain with canned agent files, assert the branch name, the commit count, the commit-message grammar of 7.4 exactly, that only in-scope docs changed, that a second run on the drift branch makes no commit, and that a dirty tree is refused.
- **Parity**: `md_scan.py` spans against `markdown-it-py` (dev-only dependency) on a fixed set of real documents copied into `tests/fixtures/markdown/`.
- **Byte equality** of every file copied from tech-debt-scan (section 9).
- **Self-scan**: the skill runs on this repository in CI and must produce no provable edit.
- **Live evaluation** (phase 3): an opt-in harness runs real agents on the corpus and on one owner repository, appends a row to `docs/evaluation-log.md` with per-class precision and the rewrite acceptance rate judged by the owner.

## 10. Phases and the tech-debt-scan seam

1. **Phase 1, deterministic core.** Steps 1 to 4 for `path`, `anchor`, `script`, `version`, `tree`; path rename and two-snapshot for paths; steps 9, 10, 13 to 15; markers, exclusions, never-edit sections, generated regions; the commit grammar; the corpus with history in three languages; the skill passes its own scan on this repository.
2. **Phase 2, identifiers and interfaces.** `identifier`, `flag`, `envvar`, `configkey` extraction and resolution; symbol rename; the human-decision routing rules (normative, recent change, obsolete doc, possible typo); the "Needs a human decision" section.
3. **Phase 3, agents.** Steps 5 to 8, 11 and 12; the rewrite commit; the live harness; the first evaluation-log row, which sets the rewrite bar.
4. **Later.** `--from-evidence <path>`: parse a tech-debt-scan `evidence.md` whose metadata names the `doc-drift` family, seed the run with that finding's doc and lines, and run the normal pipeline scoped to that doc; `/tech-debt-promote` gains a branch that routes `doc-drift` findings here instead of to a brainstorm (a tech-debt-scan spec amendment). Also `.rst` and `.adoc`, translated README families, external links behind a `--network` flag.

## 11. Assumptions

### 11.1 Table

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| A1 | Token resolution (paths, anchors, scripts, versions, identifiers, flags, env vars, config keys) covers most real drift fixes | Measured on [02]'s sample of 82 fixes across 32 repositories; not on this owner's repositories | The provable commit is thin; most value moves to phase 3 |
| A2 | The per-line two-snapshot test separates `existed-then` from `never-existed` correctly for paths, so `existed-then` unresolved paths are safe to delete | Measured, small sample (11.2 S2, S3): it correctly protected both deliberate "no longer exists" sentences found; no false `existed-then` path in a live doc after the exclusions. For identifiers it is not sufficient (all live-doc hits were false positives), hence identifiers never delete | Wrong deletions of correct prose; the re-check cannot catch these because the deleted token no longer fires. The corpus carries the deliberate-mention decoy (9.1) |
| A3 | Git rename detection gives a unique final name often enough to make `provable-replace` worthwhile for paths | Measured (11.2 S4): 0 to 52 percent of vanished paths, typically about 20; ambiguous never observed | Provable replace stays a minority edit; the provable commit is mostly deletions, which is consistent with maintainer behaviour in [02] |
| A4 | Symbol rename pairing by hunk alignment gives a unique, correct candidate often enough to be worth phase 2 | Unverified; validation planned as a phase 2 spike on real history | Symbol renames fall back to `human`; phase 2 shrinks to existence checks |
| A5 | Union-of-idioms flag detection finds defined flags precisely across languages | Unverified; regexes in the sibling skill were measured on Python only | `flag` findings produce false deletes; phase 2 must measure before enabling provable deletes for flags |
| A6 | A hand-written block scanner (no markdown library) is adequate for the spans the resolvers need | Measured (11.2 S5): even a naive line scanner agreed with CommonMark on 99.6 percent of inline code spans and 98.8 percent of fence lines over 321 docs; the residual constructs are now named requirements of `md_scan.py`, guarded by a parity test | A mis-located span makes a provable edit hit the wrong text; the exact-span replace and the re-check are the backstops |
| A7 | `git blame -w -M` on the token's line gives the right snapshot | Measured on the two real cases (11.2 S3); `-w -M` behaviour on reformatted docs unmeasured | A reflowed paragraph moves the snapshot forward, turning `existed-then` into `never-existed`: a missed finding, never a wrong edit |
| A8 | Placeholder, "create this path", slash-route and fraction filtering, plus `never-existed` being summary-only, keeps noise out of the edits | Measured (11.2 S1): unresolved paths that never existed are dominated by runtime artefacts, URL routes, slash commands and fractions; none can produce an edit by construction | The summary's counts are noisy; the `possible-typo` promotion is the only path to a human decision and is restricted to tokens with a file extension |
| A9 | Constrained rewrites plus a checker exceed the published 55 to 65 percent correctness | Unverified; measured in phase 3 by design (D14) | Rewrites become `human` by default; the skill is a provable fixer plus a reporter |
| A10 | The owner's PR process can parse the commit grammar in 7.4 | Owner-stated process; grammar not yet seen by it | A grammar change; cheap before phase 1 ships |
| A11 | Leaving the user on the drift branch after a run is acceptable | Unverified; inferred from "just create the branch" | A config switch to return to the starting branch |
| A12 | Default lead cap 25 and recent-change window 14 days are reasonable | Unmeasured conventions; rest on no input yet (guardrail 0(d)) | Too many or too few judged leads; tune from the first live run |
| A13 | Copy-with-byte-equality is acceptable for sharing code with tech-debt-scan | Repository precedent (karate-bootstrap) | A shared package would need a change to the direct-path rule |
| A14 | Running inside the target repository's working tree (not a worktree) is safe given the clean-tree refusal | Inferred | A worktree mode would isolate the user's checkout |

### 11.2 Validation pass

Spikes run on 2026-10-09 on this machine, throwaway code in the session scratchpad. Inputs: the owner's thirteen repositories under `~/sources` and three cloned open-source repositories with long histories (httpie/cli in Python, sharkdp/bat in Rust, junegunn/fzf in Go). Only git was read; no project code ran. Every rule adopted below is generic; no input-specific behaviour was encoded (guardrail 0(d)).

**S1. Current-state scan (A8).** Extract path and identifier tokens from every in-scope doc with the draft exclusions, resolve at HEAD, apply the doc-level two-snapshot test. Over 13 repositories: 5,263 path tokens, 1,718 unresolved; 6,254 identifier tokens, 1,487 unresolved. Most unresolved paths never existed in history (1,526 of 1,718; 91 more were in a "create this" context, 92 existed earlier in history but not at the doc's last commit, and 9 existed then): runtime artefacts (`.tech-debt/`, `inventory.json`, `state.json`, `CLAIM.json`), URL routes and slash commands (`/pipeline`, `/tech-debt-promote`), fractions (`3/5`, `X/Y`) and illustrative names. Every `existed-then` path sat in `docs/superpowers/archive/` or `docs/superpowers/research/`. Amendments: exclusions widened to all of `docs/superpowers/**`, research and archive folders (section 4); slash-route and fraction filters (section 5).

**S2. Identifier hand check (A2).** Every `existed-then` identifier in a live doc was checked by hand. All were false positives: an MCP tool name the code spells `memory.record_use` while the doc correctly uses the exposed `memory_record_use`; a CSV column name (`x_ref`) the resolver missed because it read only code files; Kubernetes status words in a sample bug report; function names in a vendored copy of an Arduino library's own docs. Amendments: identifiers never `provable-delete` (6.3); identifier resolution reads all non-markdown text files including data, at both snapshots (6.1); runtime-derived name variants resolve (6.1); vendored nested libraries excluded (section 4).

**S3. Historical replay (A2, A7).** Freeze each doc at commits a quarter, a half and three quarters through first-parent history, resolve its path tokens against HEAD, and compare with the maintainers' HEAD version of the doc. Two references in live docs looked stale at HEAD: `ralph/prompt/README.md` naming `PROMPT.md`, and `better-memory/website/architecture.md` naming `_claude_md_sentinel.py`. Both lines were written in the very commit that deleted the file, to say it no longer exists ("There is no `PROMPT.md` file", "drift sentinel retired"). A test of "did it ever exist" would have deleted correct prose. `git blame` on the line returned the deleting commit, where the target was already absent, so a per-line test classifies both as `never-existed`: correct. Amendment: the snapshot is per line (section 4, 6.2), and the corpus gains this shape as its first decoy (9.1).

**S4. Rename uniqueness (A3).** For every path present half-way through history and absent at HEAD, follow git's rename records to HEAD.

| Repository | Vanished paths | Unique rename | Ambiguous | Deleted |
|---|---|---|---|---|
| httpie/cli | 17 | 3 | 0 | 14 |
| sharkdp/bat | 29 | 15 | 0 | 14 |
| junegunn/fzf | 3 | 1 | 0 | 2 |
| better-memory | 11 | 0 | 0 | 11 |
| ralph | 14 | 3 | 0 | 11 |

The one replayed doc reference to a renamed path (bat's README naming a syntax file moved into a subfolder) was predicted correctly: the maintainers' HEAD README names the predicted path.

**S5. Parser parity (A6).** A naive line scanner (fence regex, inline backtick regex, inline link regex) against `markdown-it-py` 3.0.0 in CommonMark mode, over 321 in-scope docs from ten repositories:

| Measure | Reference count | Disagreements |
|---|---|---|
| Fence lines | 19,515 | 229 (1.2 percent) |
| Inline code spans | 27,526 | 118 missed, 121 extra (0.4 percent each) |
| Link targets | 5,227 | 161 missed (3.1 percent), 42 extra |

Disagreements came from code spans continuing across a line break, reference-style links, escaped pipes in tables, fences indented inside list items and multi-backtick spans. Amendment: these are named requirements of `md_scan.py` with a parity test (section 5).

**Not validated here, and the planned step:**

- A4 symbol rename pairing: a phase 2 spike on the replay harness, scoring predicted replacements against the maintainers' later doc text.
- A5 flag idioms: a phase 2 spike over the three open-source repositories, whose READMEs document many flags.
- A9 rewrite quality: the phase 3 live run.
- A10 to A14 need the owner's word or the first real run.
- Real path drift in live docs was rare in this sample. After the exclusions, no `existed-then` path remained in a live doc at HEAD, so `provable-delete` precision rests on two protected true negatives and the design argument. The corpus must carry the evidence.
