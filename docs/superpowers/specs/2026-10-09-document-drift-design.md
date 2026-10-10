> **Superseded** on 2026-10-10 by [`2026-10-10-document-drift-agentic-design.md`](2026-10-10-document-drift-agentic-design.md). The first real run showed that a gate built on git history cannot check that the docs match the code; this spec stays as the record of phase 1.

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
/document-drift <repo> [--base <ref>] [--branch <name>] [--workdir <dir>] [--check] [--date <YYYY-MM-DD>]
```

- `<repo>` defaults to the current directory.
- `--base <ref>`: scope to docs that reference (at HEAD or at a token's line snapshot) a path changed in `git diff --name-only --no-renames <ref>...HEAD`, plus docs changed in that range. `--no-renames` lists both sides of a rename, so a doc naming the old path stays in scope. An unknown ref is refused.
- `--branch <name>`: default `docs/drift-<YYYY-MM-DD>`; a pattern can be set in config. A name `git check-ref-format --branch` rejects is refused (R48).
- `--workdir`: default `.document-drift`. The skill adds the workdir to `.git/info/exclude` (never to `.gitignore`, which would be a repository change) and never commits it. A workdir outside the repository is not added (R47).
- `--check` (amendment 7): run to the planned hunks and stop; no doc edit, no branch, no commit (the workdir is still created and, when inside the repository, added to `.git/info/exclude`). Exit 1 when any provable hunk exists. It runs from a detached HEAD (R56).
- `--date` (amendment 7): fixes the branch date and the run id, for tests.
- `--no-agents` arrives with phase 3, the first phase that has agents to skip; phases 1 and 2 are always deterministic.

Exit codes: 0 success (with or without a branch); 1 `--check` found provable edits; 2 refused (not a git repository, not the top level of a working tree (a subdirectory, a bare repository or a `.git` directory, R61), no commits yet, an unknown `--base` ref; outside `--check` also a detached HEAD, an invalid branch name, a dirty tree, an existing branch, or no git author identity; `--check` creates no branch, so it runs from a detached HEAD, as a CI checkout is, R56); 5 an expected step output is missing or a step crashed (the no-improvisation rule; R49: any exception other than a step's own refusal prints its traceback and exits 5 naming the step, so exit 1 stays reserved for `--check`; R65: so does an exception outside every step, such as clearing the old outputs, rewriting `preflight.json`, writing the summary to stdout or reading the final hunks). When the step is apply, commit or summary, docs may already be edited, and after commit the drift branch and its commit may exist (a summary crash after a successful commit exits 5 with both in place, R50), so the user is told to check `git status` and `git branch` (R57); 6 commit failed after edits were applied, and the message says where the edits are: a moved HEAD, a failed `git switch -c` or an applied hunk with no finding stops before any branch exists, with the edits in the working tree on the original branch; a failed `git add` or `git commit` names the drift branch the user is on and whether the edits are staged (R57).

The run never switches the user's checkout away from where it started except to create the drift branch at commit time; it creates the branch from the starting HEAD with `git switch -c`, carrying the working-tree edits, commits, and leaves the user on the drift branch. Before `switch -c` it checks that HEAD still equals the preflight HEAD; if not it exits 6 before any branch is made (R48). The summary prints the branch name and the commit hashes.

## 3. Pipeline

Script steps run from `skills/document-drift/` with pinned commands and pinned outputs under `--workdir`. Agent steps dispatch read-only agents whose prompts are rendered to files by a script. Script modules are `dd_`-prefixed (amendment 1: the three skills share one pytest process and one mypy run), and `dd_run.py` chains the steps.

| Step | Layer | Command or agent | Output | Phase |
|---|---|---|---|---|
| 1 | Script | `dd_preflight.py` | `preflight.json` (`head`, `branch_from` (null when `--check` runs from a detached HEAD), `branch`, `git_version`; `dd_run.py` adds `run_id`, `scope`, `check`, `date` and `config_warnings`) | 1 |
| 2 | Script | `dd_inventory.py` | `inventory.json` (every tracked file; in-scope docs; exclusions and skips with reasons; the never-edit regex; `scope_dropped` under `--base`) | 1 |
| 3 | Script | `dd_extract.py` | `tokens.json` (typed tokens per doc with line, column span, block context, section heading path, ignore state; markers; skipped docs) | 1 |
| 4 | Script | `dd_resolve.py` | `candidates.json` (unresolved tokens with history lookups, proposed class, evidence; `honoured`, the tokens a marker suppressed) | 1, extended in 2 |
| 5 | Script | `leads.py` | `leads.json` and `prompts/judge-<nn>.md` | 3 |
| 6 | Agent | judge | `judged/judge-<nn>.json` | 3 |
| 7 | Script | `verify_prompts.py` | `prompts/verify-<nn>.md` | 3 |
| 8 | Agent | verifier | `verdicts/verify-<nn>.json` | 3 |
| 9 | Script | `merge.py`; in phase 1 folded into `dd_fixes.py` (amendment 1) | `findings.json` (every finding with an id, final class) | 1 |
| 10 | Script | `dd_fixes.py` | `hunks-provable.json` | 1 |
| 11 | Agent | rewriter | `rewrites/rewrite-<nn>.json` | 3 |
| 12 | Agent | checker | `checks/check-<nn>.json` | 3 |
| 13 | Script | `dd_apply.py` | edited docs in the working tree; `applied.json` (applied, reverted with reason) | 1 |
| 14 | Script | `dd_commit.py` | the branch and commits; `commits.json` | 1 |
| 15 | Script | `dd_summary.py` | `summary.md` printed to the terminal | 1 |

In phases 1 and 2, steps 5 to 8, 11 and 12 do not exist, and there is no agent output to merge, so `dd_fixes.py` reads `candidates.json` and writes both `findings.json` and `hunks-provable.json`. With `--base`, `dd_run.py` filters the docs out of scope between steps 4 and 9. `--check` stops after step 10 and runs only the summary.

Before step 1, `dd_run.py` deletes every pinned output in the workdir, so a stale `applied.json` or `findings.json` can neither satisfy an exit-5 check nor be consumed again (R45); `dd_apply.py` only ever runs after `dd_fixes.py` in the same chain.

## 4. Inventory and scope

**Doc list (amendment 2).** No filesystem walk: the doc list comes from `git ls-files` (outside `--check` preflight requires a clean tree, so every doc is tracked; under `--check` an untracked doc is not scanned and a modified one is read as it is in the working tree), with tech-debt-scan's path-class globs copied. Symlinks are skipped, and files over 2 MB, not UTF-8 or with a NUL byte are skipped with a reason. The walk's ignore list still applies as an exclusion (R10): a doc with a path component in `node_modules`, `.venv`, `venv`, `site-packages`, `dist`, `target`, `.tox` or `__pycache__`, or in `build` or `bin` when that directory holds no manifest file (tech-debt-scan's `MANIFEST_NAMES`), is excluded with reason `ignored-dir:<name>`.

**In scope.** Files ending `.md` (case-insensitive) that survive the exclusions. CLAUDE.md and AGENTS.md at any depth are in scope.

**Built-in exclusions**, each recorded with its reason in `inventory.json` and in the summary:

- Paths: `docs/superpowers/**` (plans, specs, and the archive and research folders beside them), `.superpowers/**`, `docs/research/**`, `**/research_notes/**`, `**/archive/**`, `**/adr/**`, `**/adrs/**`, `**/decisions/**`, `**/rfcs/**`, `**/rfc/**`. The validation pass (11.2) found nearly every stale-looking reference in the owner's repositories inside archive and research folders, which are dated records by nature.
- Vendored nested libraries: a directory below the root that holds its own `LICENSE*` file and a package or library manifest (`package.json`, `pyproject.toml`, `setup.py`, `Cargo.toml`, `go.mod`, `library.json`, `library.properties`, `CMakeLists.txt` with a `project(` line) whose name differs from the root project's, or any directory under `libraries/`, `extern/`, `external/`, `third_party/`, `deps/`. The validation pass found a copied Arduino library's own docs producing findings.
- Basenames: `CHANGELOG*`, `CHANGES*`, `HISTORY*`, `RELEASE_NOTES*`, `LICENSE*`, `LICENCE*`, `NOTICE*`, `COPYING*`, `CODE_OF_CONDUCT*`, `SECURITY*`, `AUTHORS*`, `CONTRIBUTORS*`, `MAINTAINERS*`, `CODEOWNERS`. The globs are case-sensitive; in addition the exact conventional stem (the name before its first dot, including the hyphen variants `RELEASE-NOTES` and `CODE-OF-CONDUCT`) matches in any case (R9). So `changelog.md` and `LICENSE-MIT` are excluded, while `license-faq.md` and `notice-board.md` stay in scope.
- Classes from the copied path classifier: vendored, generated, tests (a `README.md` under `tests/` is a fixture, not a doc).
- `.gitattributes` entries marking a path `linguist-generated` or `linguist-vendored`.
- A file whose first five lines contain `DO NOT EDIT` or `Code generated`.
- Git submodules (paths listed in `.gitmodules`).
- Templates: a file under a directory named `templates`, `template`, `skeleton` or `cookiecutter*`, or whose name ends `.tmpl.md`.
- `<!-- drift-ignore-file: reason -->` anywhere in the file, as a real HTML comment: the same text quoted in inline code, a fence or indented code (as docs about the marker quote it) does not count (R55). A file marker with no colon or an empty reason excludes nothing and is reported as a marker without a reason (R66).
- Config `exclude` globs.

The recorded reason strings are stable (R8), checked in this order with the first match recorded: `path:<glob>`, `ignored-dir:<name>`, `vendored-library:<dir>`, `basename:<glob>`, `class:vendored|generated|tests`, `gitattributes:linguist-generated|linguist-vendored`, `header:do-not-edit`, `submodule:<path>`, `template`, `marker:<reason>`, `config:<glob>`.

**Never-edit sections.** Inside an in-scope doc, a section whose heading matches the never-edit regex (default `(?i)\b(why|rationale|decision|decisions|history|roadmap|deprecated|deprecation|migration|changelog|release notes|license|licence)\b`) is scanned for the summary but every finding in it becomes a human decision. Config may extend the regex; the default and the extra pattern are OR-ed with each part's leading inline flag scoped to its own group (R8a), because a global `(?i)` in the middle of a pattern is an error on Python 3.11 and later.

**Line snapshot.** For each token that does not resolve at HEAD, the snapshot is the commit that last changed the token's line: `git blame -w -M --porcelain -L <n>,<n> -- <doc>`. Ignoring whitespace (`-w`) and in-file moves (`-M`) keeps formatting commits from resetting it. This sha is the token's **snapshot** for the two-snapshot test (6.2). A per-line snapshot, not the doc's last commit, is required: the validation pass (11.2) found docs edited after a file's deletion, and lines written in the deleting commit to say the file is gone ("There is no `PROMPT.md` file"); both must read as deliberate, never as drift.

**Doc lag.** The doc's last substantive commit (newest commit whose diff for the doc changes a line outside link targets and whitespace, author not a bot by the copied `bot_authors` rule) is kept only as an ordering key for phase 3 judge leads.

**`--base` scope.** Changed paths from `git diff --name-only --no-renames <ref>...HEAD` (both sides of a rename). A doc is in scope when it changed in the range, or when any of its path or tree tokens (R66) resolves (at HEAD, or at that token's line snapshot as its `resolved_then`) to a changed path or a directory containing one, or (phase 2) when any identifier token appears in a changed file at the base ref.

## 5. Extraction

`dd_md_scan.py` is a pure-Python block scanner sufficient for CommonMark structure the resolvers need: ATX and setext headings, fenced code blocks (backtick and tilde, info string, length-aware closing, fences indented inside list items), indented code, block quotes, list items, tables (with escaped pipes), HTML comments, link reference definitions and reference-style links, inline code spans (including spans that continue across a line break and multi-backtick spans), inline links, images and autolinks. It is not a renderer; it reports spans with line and column. The constructs listed after the basics are the ones a naive line scanner got wrong in the validation pass (11.2). A parity test compares its spans with `markdown-it-py` on a fixed corpus of real documents; `markdown-it-py` is a dev-only test dependency, so the runtime stays pyyaml-only.

Reference-style images are their own inline kind (`refimage`, beside `image`), because images are never unlinked (R5). A link reference definition is exposed as a `refdef` inline whose span is its destination (R6), and reference-style usages carry only their label span.

`dd_extract.py` emits one token per occurrence with: `doc`, `line`, `col`, `end_col`, `kind`, `text`, `context` (`inline-code`, `link`, `image`, `refdef`, `fence`, `tree`, `prose`), `link` (the whole `[text](target)` span when the token is a link target), `block` (`paragraph`, `list_item`, `table_row`, `table_header`, `fence`, `heading`, `tree`, with its line range), `subject`, `heading_path`, `target_doc`, `script_tool`, `version`, `tree_label`, `never_edit`, `generated`, `ignored` (the marker reason) and `editable` (false when the span crosses a line break). Path and anchor tokens come from `refdef` inlines, never from `reflink` or `refimage` usages, so an edit lands on the definition and a reference used three times is one token (R11). `subject` is true when the token comes from the first code, link, image or refdef inline of a list item's first line or of a table body row's first cell; when that inline yields no token there is no subject (R18). A table header row has block kind `table_header` and is never a subject, and a `drift-ignore` before a table covers the whole contiguous table (R15). `target_doc` is always repository-relative: the doc's directory joined and normalised for `x.md#f`, the doc itself for `#f` (R17).

**Spans (R13).** A path token's span covers exactly its `text`. A trailing `:<n>` or `#L<n>` is stripped before resolving and stays outside the span, so a replace keeps the suffix; deletion units are whole items, rows, lines or links and never need it.

| Kind | Where it comes from | Phase |
|---|---|---|
| `path` | Inline code or a fence line that looks like a path (contains `/` or a known extension, no spaces, not a URL); link and image targets without a scheme | 1 |
| `anchor` | `#fragment` in a link target, same doc or another doc | 1 |
| `script` | `make <t>`, `npm run <t>`, `yarn <t>`, `pnpm <t>`, `just <t>`, `task <t>` in shell fences and inline code (`script_tool` names the tool; package-manager built-ins such as `install` are not targets). `./<path>`, `python <path>`, `bash <path>` and `sh <path>` arguments on fence lines are `path` tokens | 1 |
| `version` | Runtime floors near a runtime word (`Python`, `Node`, `Node.js`, `Go`, `golang`, `Rust`) carrying a floor marker: `Python 3.11+`, `Node >= 18`, `Go 1.22 or later`. Amendment 6: a floor marker (`+`, `>=`, `or later`, `or newer`) is required in phase 1; a bare version (`requires Go 1.22`, `rust 1.75`) and the project's own version are deferred. The runtime word starts a word no `.`, `-` or word character precedes, so a package such as `opencv-python>=4.8` is no floor (R59) | 1 |
| `tree` | A fenced block without an info string (or `text`, `txt`) whose lines look like a directory tree, by the rule below | 1 |
| `identifier` | Inline code that matches an identifier shape (`snake_case`, `camelCase`, `PascalCase`, dotted `a.b.c`, `Name()`), not a path, not a keyword | 2 |
| `flag` | `--long-flag` and `-x` tokens in fences and inline code following a command word | 2 |
| `envvar` | `UPPER_SNAKE` tokens of at least two segments in inline code, fences, or after `$`/`${`/`%`/`env.` | 2 |
| `configkey` | Inline code `a.b.c` or `snake_key` inside a section whose heading matches `(?i)config|settings|options|environment`, or in a table row in such a section | 2 |
| `claim` | Sentences containing a capability or time word (`not supported`, `does not`, `doesn't`, `cannot`, `only`, `currently`, `not yet`, `no longer`, `by default`, `always`, `never`) that also contain another token | 3 (lead source) |

Placeholders are dropped at extraction: anything containing `<...>`, `{{...}}`, `${...}` as the whole token, `your-`, `my-`, `example`, `foo`, `bar`, `baz`, `xxx`, `TODO`, `*` globs, and paths under a directory the doc instructs the reader to create (a `mkdir`, `touch` or "create" verb on the same line or the preceding line). Not paths: a token whose only `/` is a leading one (`/pipeline`, `/tech-debt-promote`, URL routes and slash commands), a fraction or ratio (`3/5`, `X/Y`), a dotted name with no `/` and no known extension. The ratio filter drops only `^\d+/\d+$` and `^[A-Za-z]/[A-Za-z]$` (R14): a wider shape would drop real paths such as `src/lib` and `cmd/api`.

**Tree detection (R16, R19).** A fence is a tree when it has at least two glyph lines (`├──`, `└──`, `|--`, `` `-- ``), or when every non-empty line is a single name (with an optional trailing comment), at least two lines end with `/`, and at least one line is indented deeper than a preceding `name/` line; a list of unindented `name/` lines alone is never a tree. The indentation unit is the smallest positive indentation step (for glyph trees, the glyph prefix width per level). A description column without a comment marker ends the name at the first run of two or more spaces. A first line `name/` with no glyph whose following lines are all its descendants is a root label: tokens keep it as a path prefix in `text`, and `tree_label` names it so resolution tries the path with the label first and then without it. A first line `.` or `./` is a root marker: it is dropped, `tree_label` is null, and the children are doc-relative or root paths.

Runtime artefacts are a large share of unresolved paths in practice (`.tech-debt/`, `inventory.json`, `state.json`): they are produced by running the project and are never in the tree. They resolve `never-existed` and are summary-only, which is the intended outcome. One that was once tracked (committed, then untracked and ignored) would look `existed-then` and deleted; a path or tree entry absent from HEAD but present on disk in the working tree therefore counts as resolved (R66). An empty directory left behind by a move does not count.

## 6. Resolution and classification

### 6.1 Resolvers

All resolvers are language-neutral by union of idioms; none executes project code.

- **Path.** Percent-decoded and stripped of a leading `./`, then resolved relative to the doc's directory, then the repository root, then by suffix (a token with `/`) or basename (a bare name), so monorepo docs that name package-relative paths and bare filenames are not reported. A path that resolves to a directory is resolved. A trailing `:line` or `#L<n>` is stripped before resolving. HEAD is the tree `git ls-tree HEAD` lists (R23). Suffix and basename matches are leniency at HEAD only; at the snapshot see 6.2 (R26). A path absent from HEAD but present on disk in the working tree counts as resolved (R66, section 5).
- **Anchor.** Target doc's headings slugged GitHub-style (lower-case, punctuation other than `-` and `_` removed, spaces to `-`, duplicate suffix `-1`, `-2`), plus explicit `<a name>` and `id=` anchors. An anchor whose `target_doc` climbs above the repository never existed (R22).
- **Script.** Makefile targets (`^name:` rules, excluding `.PHONY` lines), `package.json` `scripts` keys at the nearest enclosing package, `justfile` recipes, `Taskfile.yml` tasks, and file existence for path-invoked scripts. A manifest this parser cannot see into counts as defining every name, the same lenient rule as an unparsable one (R25): a Makefile with an include it cannot follow (a glob or a variable), a pattern rule (`%`) or a variable target; a justfile with `import` or `mod`; a Taskfile with `includes`.
- **Version.** The nearest declared floor: `pyproject.toml` `requires-python`, `package.json` `engines.node`, `Cargo.toml` `[package]` `rust-version`, `go.mod` `go` directive. Pin files (`.python-version`, `.nvmrc`, `.tool-versions`) never produce a candidate: a pin is not a floor (R28); the `[workspace.package]` `rust-version` fallback is dropped (R31). TOML is parsed with `tomllib` (standard library). A version claim is drift only when the manifest states a different floor; a doc floor higher than the manifest is drift too. The two are compared at the lower of their precisions, so a doc `3.10` against `>=3` resolves (R29). A mismatch is provable only when the doc floor equalled the manifest floor at the line's snapshot (the manifest read at that sha): the manifest moved on and the doc did not. A floor that was never the manifest's (a sentence about a dropped version, another package's floor) is summary-only (R59).
- **Tree.** Each entry's path, assembled from indentation, must exist, resolved doc-relative first and then root-relative (R12), with the `tree_label` prefix first and then without it; a label containing `<`, `>`, `{{` or `${` is always dropped (R22). Entries the doc omits are never drift.
- **Identifier (phase 2).** Present when it appears as a whole token in any tracked non-markdown text file at HEAD: source, config and data files alike (CSV headers and JSON keys name things docs talk about). The same file classes are used at the snapshot, so the two sides of the test are comparable. Dotted names resolve when the last segment resolves and, if the other segments name a module path, that path exists. A name that also appears with `_` and `.` swapped (`memory_record_use` and `memory.record_use`), or with a prefix stripped, resolves: tool and command names are often derived at runtime.
- **Flag (phase 2).** Present when it appears as a string literal in any source file (`"--name"`, `'--name'`), or in a definition idiom for argparse, click, typer, clap (`long = "name"`, `#[arg(long)]` on a field `name`), cobra and pflag (`Flags().<Type>("name"`), commander and yargs (`.option('--name`), picocli (`names = {"--name"`), System.CommandLine (`"--name"`), or in a checked-in man page or `--help` text file.
- **Envvar (phase 2).** Present when it appears in any source, config, Dockerfile, compose, CI workflow or `.env.example` file.
- **Configkey (phase 2).** Present when its last segment appears as a key in any config-classified file, or as a string literal or field name in any source file.

### 6.2 History lookups for unresolved tokens

- **Two-snapshot test.** Did the token resolve at its line snapshot (section 4)? Paths: whether `<sha>:<path>` exists for each candidate resolution, asked for every token of the run in one `git cat-file --batch-check` call; a snapshot's tree is never listed, and a directory's files are listed with `git ls-tree -r -z --name-only <sha> -- <dir>` (R63). Anchors: the target doc's headings at that sha. Identifiers, flags, env vars, config keys: `git grep -w -F -q <token> <sha> -- <the same pathspecs as the HEAD resolver>`. Result: `existed-then` (resolved when the line was last written, and not now) or `never-existed` (did not resolve when the line was written: a deliberate mention of something removed, an illustrative name, a runtime artefact, or a mistake at birth).
- **Snapshot resolution modes (R26).** At the snapshot only doc-relative and root-relative resolution count as existed-then. A suffix or basename-only match at the snapshot is treated as never-existed (summary-only): loose matches are leniency at HEAD, not evidence. A replacement is therefore written in one of those two modes and must itself resolve at HEAD to exactly the new path.
- **Path rename (R67).** One old-to-new map per snapshot from `git log -M --diff-filter=R --name-status --topo-order <snapshot>..HEAD`, applied oldest first, so when parallel branches rename the same path the topologically last rename's target wins; there is no `--follow` lookup (the path no longer exists at HEAD, so `--follow` could not start from it). Chains are followed to the final name, in `--topo-order` so oldest-first holds under skewed dates (R21). Final name existing at HEAD: `rename-unique`. None: `deleted`. A single file therefore never has several final names in phase 1; detecting parallel renames of one file as ambiguous is deferred to phase 2. A directory (R60) is `rename-unique` only when every file it held at the snapshot has a final name and all of them sit under one new directory (a direct child's new parent; a deeper file must keep its path below the directory); every file deleted is `deleted`; any mix (some deleted and some moved, files moved apart) is `rename-ambiguous`. A path that exists at HEAD is never rewritten (a recreated or never-renamed path is not drift), and a chain that returns to an earlier name finishes on that name (R20). History lookups by path pass `--literal-pathspecs` (R21).
- **Same basename (R27).** Before a path is classified `deleted`, if any HEAD file has the same basename as the snapshot path, the outcome is `rename-ambiguous` (human), with the HEAD candidates in the evidence: git misses heavy rewrites and renames inside large commits.
- **Tree rename (R22).** A renamed tree entry's replacement is the entry's own last segment only; a rename that changes a parent directory is `rename-ambiguous` (the edit would touch another line).
- **Anchor rename (R24, R30, R32 to R35).** The commit that removed the anchor's slug is found by listing the commits that changed the target doc since the snapshot and comparing each with its first parent; the anchor's own slug must be defined in the parent and absent in the commit (R32). More than one such commit is `rename-ambiguous` (R35): parallel removals make any single choice a guess. In the one removing commit: exactly one slug removed (the anchor's) and exactly one added, with the new slug present at HEAD (R31), the two headings at the same level, both section bodies (the lines after the heading up to the next heading of the same or higher level) non-empty after stripping whitespace (R33), and a `difflib.SequenceMatcher` ratio of at least `HEADING_BODY_SIMILARITY = 0.6` between the bodies in the parent and in the commit (R30): `rename-unique`. The anchor's slug removed with none added in that commit, however many other slugs went with it: `deleted` (R34). Anything else, an anchor that carries a `-N` duplicate suffix, or an anchor whose base slug still exists at HEAD: `rename-ambiguous` (R24).
- **Symbol rename (phase 2).** `git log -S<token> --format=%H <snapshot>..HEAD` gives the commits that changed the token's occurrence count. In the newest commit that removed the last occurrence, pair each removed line containing the token with the added lines of the same hunk; the replacement candidate is the token at the same position in the most similar added line (token-level alignment). One candidate across all such lines, which resolves at HEAD: `rename-unique`. Otherwise `rename-ambiguous` or `deleted`.
- **Version.** The manifest value is the fix, when the doc floor equalled the manifest floor at the line's snapshot (R59; otherwise summary-only).
- **Evidence (R64).** A provable outcome names the commit that proves it: a path, tree or anchor delete or a script removal whose commit cannot be found is `human`/`ambiguous-rename`, and `dd_fixes.py` refuses (exit 5) a hunk whose reason has neither a 7-character sha after ` in ` nor a `manifest ` prefix.

### 6.3 Classes

| Class | Condition | Edit |
|---|---|---|
| `provable-replace` | `existed-then` and `rename-unique`, or a version mismatch with a manifest value, or an anchor whose heading was renamed with a unique match | Token-exact replacement by script |
| `provable-delete` | A `path`, `anchor`, `script` or `tree` token that is `existed-then` and `deleted`, and whose deletion unit (section 7.1) is smaller than a paragraph. Never an identifier, flag, env var or config key: in the validation pass every identifier that existed then and not now, in a live doc, was a false positive | Deletion by script |
| `rewrite` | A judged finding confirmed by the verifier (phase 3) | Hunk by the rewriter, checked by the checker |
| `human` | `rename-ambiguous`; an identifier, flag, env var or config key that is `existed-then` with no unique rename (kind `removed-symbol`); a deletion unit of a paragraph or more; a token in a never-edit section; a finding in a generated region; a confirmed judged finding the rewriter declined or the checker rejected; a normative-sentence mismatch; a finding whose referenced code changed within the recent-change window (default 14 days) and whose doc did not; a doc where more than half of its resolvable tokens are `existed-then` and unresolved (likely obsolete as a whole); an edit reverted by the re-check | None; reported |
| `summary-only` | `never-existed` tokens (illustrative names, external APIs, placeholders the filter missed) | None; counted in the summary. A `never-existed` path that carries a known file extension and is within edit distance 2 of exactly one existing path is promoted to `human` (kind `possible-typo`) with the suggestion |

A normative sentence contains `must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never` or `is required`. Phase 2 routes any finding in such a sentence to `human`; phase 3 routes judged mismatches on such sentences to `human` with both sides quoted.

**Recent-change rule (amendment 5).** The recent-change rule does not apply to `path`, `anchor`, `script`, `tree` or `version` findings: a rename or deletion is a deliberate act recorded in history. It applies from phase 2 to symbol findings and in phase 3 to judged findings.

**Phase 1 routing.** In phase 1 the `human` kinds produced are `ambiguous-rename`, `large-deletion`, `prose-mention` (amendment 3), `never-edit-section`, `generated-region`, `heading-reference` (R62) and `recheck-failed`; the routing order is generated region, never-edit section, a span that is not `editable` (`prose-mention`), then an ambiguous outcome. `normative-mismatch`, `recent-code-change`, `obsolete-doc`, `possible-typo` and `removed-symbol` arrive with phase 2. A token under a `drift-ignore` marker never yields a candidate of any class and never sets `history_unavailable`; it is listed in `honoured` so the summary can tell live markers from stale ones (R29, R23).

## 7. Fixing, applying and committing

### 7.1 Provable edits

- **Replace.** Exactly the token's characters at the recorded span; the surrounding text is untouched. When the token is a link target, only the target changes; link text that equals the old target changes too. A replacement written into a `link`, `image` or `refdef` destination percent-encodes space, `(`, `)`, `<` and `>`; when the original destination used the `<...>` form only `<` and `>` are encoded (R41). Inline-code and tree replacements are verbatim. A `refdef` token may be replaced (R11). A replace whose token sits in a heading is `human`/`heading-reference` (R62): the heading's slug may be a link target in another doc.
- **Delete (amendment 3).** Phase 1 deletes only these units, tried in order, the first that applies deciding: the list item whose subject is the token, when it has no nested item and at least one sibling; the table body row whose subject is the token, when the table keeps another body row; a single-command line of a shell fence that is a command list and keeps another command line; a tree leaf line (no deeper entry directly beneath it); the link, whose text stays as plain text (`unlink`; images are never unlinked). Any other token, such as a non-subject mention in a paragraph, list item, table cell or heading, is `human` with kind `prose-mention`: prose is phase 3's rewrite job. Only a rule that applies but whose unit is unsafe (below) gives `human`/`large-deletion`.
- **Stricter deletion rules (R38, R39, R40).** Also `human`/`large-deletion`: a reference definition (removing it breaks every usage, R11); a fence line with mixed prompt styles, a `&`, `|` or `;` compound, a continuation, or a fence left with only comments; the first ordered item under text; an item that contains a reference definition; a delete on a line another edit already changes; and any delete inside a block quote, where the unit or any ancestor block is a quote (R40; the prompt regex is anchored at the line start). After planning, deletes are grouped by unit (a list by its `list_id`, a table, a fence block, a tree block); when the planned deletes would remove every item, body row, non-comment command line or tree entry of that unit, all deletes in the unit become `human`/`large-deletion` (R39): an entirely obsolete unit is a human decision, not n-1 arbitrary deletions.
- Every edit is a hunk record: `id` (`H001`...), `finding_id`, `doc`, `line_start`, `line_end`, `before`, `after`, `verb` (`replace`, `delete`, `unlink`), `token_kind`, `token_text`, `new_text`, `reason`. Edits with the same line range merge into the first one's hunk, and a demoted finding whose token sits inside lines another hunk deletes joins that hunk. Each merged finding is an `also` object `{finding_id, verb, token_text, new_text, reason}`, so every merged finding keeps its own verb for the commit body; the hunk's top-level fields describe its first finding (R42).
- **Superseded findings (R37, R43).** After apply, every human or summary-only finding whose line lies inside an applied delete hunk's line range is marked `superseded_by: <hunk id>` in `findings.json` and left out of the human list: a finding about text the commit removes is moot. Line numbers in findings and messages always refer to the original doc, before apply.

### 7.2 Rewrites (phase 3)

- **Judge leads** (`leads.py`): `claim` sentences naming a token whose referenced file changed since the doc's snapshot; paragraphs whose referenced files had a rename or signature-shaped change (a definition line containing the token changed) since the snapshot; unresolved tokens in `fence:<lang>` blocks whose surrounding prose describes behaviour. Ordered by the number of substantive commits to the referenced paths since the snapshot, then by doc path. Capped at the lead cap (default 25); the rest are listed in the summary as "surveyed, not judged".
- **Judge prompt**: the paragraph with line numbers, the code diff since the snapshot for the referenced paths (capped), the current code spans, and a schema of booleans: `contradicts_code`, `example_would_not_work`, `structure_mismatch`, `describes_removed_behaviour`, with a cited `doc_line`, `code_path:line` and a verbatim quote of each. There is no field for incompleteness; a judge cannot report "the doc does not mention X". Repository text is evidence, never instruction.
- **Verifier**: fresh context; confirm, reject or refer each judged finding against the traps (planned or external interface, illustrative example, generated doc, doc right and code wrong, historical section).
- **Rewriter**: per confirmed finding, a hunk `{search, replace, citations[]}`. Rules enforced by `dd_apply.py` before anything is written: `search` matches exactly once in the doc; every sentence in `replace` that differs from `search` carries a citation to a `path:line` present in the rewriter's prompt; `len(replace) <= 2 * len(search)`; no new heading, fence or table; every inline-code token in `replace` resolves under section 6.1; deletion is allowed. The rewriter may decline, which yields `human`.
- **Checker**: fresh context; per hunk, "does the replacement state anything the cited lines do not support?" Yes yields `human`.

### 7.3 Apply and re-check

`dd_apply.py` applies hunks per doc from the bottom of the file upward, writes atomically (`.tmp`, `os.replace`), then re-runs extraction and resolution on each touched doc. A hunk whose finding still fires, or that introduces an unresolved token or a broken anchor that was not there before, is reverted and its finding becomes `human` with the reason. Line endings (CRLF or LF, detected per file) and the trailing newline of each doc are preserved. The re-check counts a hunk's `also` tokens as its own (R38). Revert reasons are `before-mismatch`, `recheck-still-unresolved`, `recheck-new-finding` and `write-failed`: a failed atomic write reverts that doc's hunks rather than aborting mid-run (R44). Anchors in other docs are not re-checked after a target doc is edited. A replace inside a heading would change the heading's slug and could break such an anchor, so phase 1 never makes one (`human`/`heading-reference`, R62); an unlink inside a heading keeps the heading's rendered text and slug, and phase 1 never removes a heading.

### 7.4 Commits

This section moves into phase 1, because phase 1 already yields human findings (amendment 4). `dd_commit.py` runs only when at least one hunk survives. It checks that HEAD still equals the preflight HEAD (exit 6 before any branch is made otherwise), creates the branch from the starting HEAD with `git switch -c <branch>`, stages each edited doc by explicit path with `git --literal-pathspecs add -- <docs>` (never `git add -A`; pathspec magic would let `docs/[a].md` stage `docs/a.md` too), and commits with `git commit --cleanup=verbatim -F <file>`. An applied hunk whose finding id is missing from `findings.json` is exit 6, never skipped (R48). It makes at most two commits: provable hunks, then rewrite hunks (phase 3); phase 1 makes one. Message grammar (a test pins it):

```
docs(drift): provable fixes

Drift-Run: <run-id>
Drift-Base: <starting HEAD sha>
Drift-Scope: all | base:<ref>

- <doc>:<line> replace `<old>` -> `<new>` (<reason>)
- <doc>:<line> delete `<token>` (<reason>)
- <doc>:<line> unlink `<token>` (<reason>)
```

The verb `unlink` is added by amendment 4. Bullets are ordered by doc, line and column, one per finding (a hunk's `also` findings each get their own bullet with their own verb, R42). A `script` token is shown as its invocation (`make lint`, `npm run lint`, `yarn lint`, `pnpm lint`, `just lint`, `task lint`) in bullets and human statements, and a `tree` replace shows full paths on both sides, the new one being the old path with its last segment replaced (R51).

```
docs(drift): rewrite stale prose

Drift-Run: <run-id>

- <doc>:<line_start>-<line_end> <one-line reason>
  evidence: <code_path>:<line>[, <code_path>:<line>...]
```

`<reason>` is one of `renamed in <short-sha>`, `deleted in <short-sha>`, `removed in <short-sha>` (a script target), `manifest <file> says <value>`, `heading renamed in <short-sha>`, `heading removed in <short-sha>`. The last commit's body then ends with:

```
Needs a human decision:
- <doc>:<line> [<kind>] <one-line statement>
  evidence: <the finding's evidence string, or none>
```

`<kind>` is one of `ambiguous-rename`, `removed-symbol`, `large-deletion`, `prose-mention` (amendment 4), `never-edit-section`, `generated-region`, `heading-reference` (R62), `normative-mismatch`, `recent-code-change`, `obsolete-doc`, `possible-typo`, `rewrite-declined`, `rewrite-rejected`, `recheck-failed`. The statement for `ambiguous-rename` is "`<token>` was renamed or moved and no single new name is provable" (anchors, same-basename cases, partly moved directories and outcomes without an evidence commit share the kind); the statement for `heading-reference` is "`<token>` is named in a heading; changing it would break links to that heading"; the `large-deletion` statement names its unit in words: "a list item", "a table row", "a fence line", "a tree line", "a paragraph", "a heading" (R66); the evidence line is the finding's `evidence` string (for example `deleted in a1b2c3d; HEAD has src/x.py`), and the `recheck-failed` statement names the revert reason, `write-failed` included (R46). Superseded findings are left out (R37). Commit trailers (attribution) come from config `commit_trailers`, empty by default. Every string written passes through `redact`. When no hunk survives, no branch is created and the same "Needs a human decision" list is printed in the summary.

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

Inline markers (HTML comments, so they do not render): `<!-- drift-ignore-file: reason -->`, `<!-- drift-ignore: reason -->` (the next block), `<!-- drift-ignore-next-line: reason -->`. A marker counts only as a real HTML comment found by the scanner; the same text inside inline code or a fence is documentation, not a marker (R55). A marker without a reason (no colon after the marker word, or nothing after the colon) is itself reported in the summary and ignored; that holds for `drift-ignore-file` too, which then excludes nothing (R66). A marker whose block produces no finding is reported as stale; the skill never removes markers.

Generated regions: blocks between markers of embedme (`<!-- embedme ... -->`), mdsh (`<!-- BEGIN mdsh -->`), cog (`[[[cog` ... `[[[end]]]`), terraform-docs (`<!-- BEGIN_TF_DOCS -->`), and `<!-- BEGIN GENERATED`/`<!-- END GENERATED` are never edited; findings inside become `human` with kind `generated-region`.

`summary.md`: run id; scope; the starting HEAD (`Base:`); docs scanned and docs excluded by reason; tokens per kind and the resolved count (tokens minus findings minus those a marker suppressed); findings per class; hunks applied and reverted (under `--check`, every planned hunk's findings as lines in the commit-bullet grammar, R66); the human-decision list; markers without reasons and stale markers (a marker with a reason is stale when the lines it covers hold no token it suppressed, read from `honoured`); "surveyed, not judged" docs (phase 3); the branch and commit hashes or "no branch created" (R50). Every repository-derived string passes through `redact`.

## 9. Code inventory

New skill directory `skills/document-drift/` with `SKILL.md`, `scripts/`, `prompts/` (phase 3), `tests/`.

Amendment 1: every module is `dd_`-prefixed and every test file `test_dd_*.py` (the three skills share one pytest process and one mypy run, as karate-bootstrap's `kb_` prefix does). Copied byte-for-byte from `skills/tech-debt-scan/scripts/`, with a test asserting byte equality: `redaction.py` as `dd_redaction.py`, the only one phase 1 needs. `git_history.py`, `evidence.py`, `validation.py`, `slugs.py` and `reference_graph.py` are not needed until phase 2 or 3. Copied and adapted: `dd_check_skill.py` (from karate-bootstrap's `kb_check_skill.py`), the path-classification globs and `MANIFEST_NAMES` of `inventory.py`, `dd_config.py`, `tests/dd_make_history.py` (from `tests/helpers/make_history.py`, gaining a `rename` key so fixtures can express renames git detects). New in phase 1: `dd_common.py`, `dd_preflight.py`, `dd_inventory.py`, `dd_md_scan.py`, `dd_extract.py`, `dd_history.py` (blame snapshots, trees at a sha, renames, heading history), `dd_resolve.py`, `dd_manifests.py` (script and version manifest parsing, split from resolve, R23), `dd_fixes.py` (with `merge.py` folded in), `dd_apply.py`, `dd_commit.py`, `dd_summary.py` and `dd_run.py`, which chains the steps. Later: symbol rename in `dd_history.py` (phase 2); `leads.py`, `verify_prompts.py`, the prompt templates and a `live_run.py` harness adapted from tech-debt-scan's (phase 3).

### 9.1 Tests and evaluation

- **Fixture corpus** at `tests/fixtures/corpus/<name>/`: `files/` (final tree), `history.yaml` replayed into a real repository by the copied `make_history.py` (renames, the two-snapshot test and blame are history facts), `planted.json` with `planted[]` and `decoys[]`. Three fixtures, Python, TypeScript and Go, so every resolver idiom has a positive case in at least two.
- **Planted drift**, each with doc file, line and expected class: a path renamed in a later commit (provable replace); a path deleted with no rename (provable delete); an anchor whose heading was renamed; a removed make or npm script; a version floor behind the manifest; a directory tree entry renamed; a CLAUDE.md naming a deleted script. Phase 2 adds: a removed identifier with a unique rename, a removed flag, a renamed env var, a removed config key. Phase 3 adds: a stale negation ("X is not supported" where X shipped) and an example whose described behaviour changed.
- **Planted decoys**, each with `why` and must produce no edit: a sentence written in the deleting commit saying the file no longer exists (S3's shape); an illustrative identifier that never existed; an external API name; a path the doc tells the reader to create; a runtime artefact path; a URL route and a slash command; a CHANGELOG entry; a file under `docs/superpowers/plans/`; a vendored library's README; a section under a "Rationale" heading; a generated region; a block under `drift-ignore`; a normative "must" sentence where the code regressed (expected `human`, never an edit); a reference whose code changed within the recent-change window (expected `human`).
- **Goldens**: `inventory.json`, `tokens.json`, `candidates.json`, `findings.json`, `hunks-provable.json`, the edited docs and the commit messages, byte-compared, regenerated only under `UPDATE_GOLDENS=1`. Phase 3 agent outputs are canned files from the first live run.
- **End to end**: replay a fixture, run the whole chain with canned agent files, assert the branch name, the commit count, the commit-message grammar of 7.4 exactly, that only in-scope docs changed, that a second run on the drift branch makes no commit, and that a dirty tree is refused.
- **Parity**: `dd_md_scan.py` spans against `markdown-it-py` (dev-only dependency) on a fixed set of real documents copied into `tests/fixtures/markdown/`.
- **Byte equality** of every file copied from tech-debt-scan (section 9).
- **Corpus expectations (R53).** Besides a class per planted item and "no edit" per decoy, a decoy can expect `excluded` (the doc is absent from `tokens.json` and from the findings) or `no-token` (no token at that doc and line). Excluded-doc decoys are written so that, if scanned, they would yield a provable edit, so the exclusion is what the test proves. The corpus and goldens are pinned to LF in `.gitattributes`, so `core.autocrlf=true` cannot change a golden sha (R52).
- **Self-scan**: the skill runs on this repository in CI as `dd_run.py . --check` with a workdir outside the checkout and must exit 0 (no provable edit). A `pull_request` checkout is a detached HEAD, which `--check` accepts (R56).
- **Live evaluation** (phase 3): an opt-in harness runs real agents on the corpus and on one owner repository, appends a row to `docs/evaluation-log.md` with per-class precision and the rewrite acceptance rate judged by the owner.

## 10. Phases and the tech-debt-scan seam

1. **Phase 1, deterministic core.** Steps 1 to 4 for `path`, `anchor`, `script`, `version`, `tree`; path rename and two-snapshot for paths; steps 9, 10, 13 to 15; markers, exclusions, never-edit sections, generated regions; the commit grammar and the "Needs a human decision" section (amendment 4); `--check` and `--date`; the corpus with history in three languages; the skill passes its own scan on this repository.
2. **Phase 2, identifiers and interfaces.** `identifier`, `flag`, `envvar`, `configkey` extraction and resolution; symbol rename; the human-decision routing rules (normative, recent change, obsolete doc, possible typo).
3. **Phase 3, agents.** Steps 5 to 8, 11 and 12; the rewrite commit; the live harness; the first evaluation-log row, which sets the rewrite bar.
4. **Later.** `--from-evidence <path>`: parse a tech-debt-scan `evidence.md` whose metadata names the `doc-drift` family, seed the run with that finding's doc and lines, and run the normal pipeline scoped to that doc; `/tech-debt-promote` gains a branch that routes `doc-drift` findings here instead of to a brainstorm (a tech-debt-scan spec amendment). Also `.rst` and `.adoc`, translated README families, external links behind a `--network` flag.

### Amendments in phase 1 (2026-10-09)

The plan's seven amendments, each applied in the section it changes:

- Amendment 1 (sections 3, 9): modules are `dd_`-prefixed; `merge.py` is folded into `dd_fixes.py`; `dd_run.py` chains the steps; only `redaction.py` is copied byte-for-byte.
- Amendment 2 (section 4): the doc list comes from `git ls-files`, with tech-debt-scan's path-class globs copied; no filesystem walk.
- Amendment 3 (sections 6.3, 7.1): phase 1 deletes only subject list items and table rows, single-command fence lines and tree leaf lines, and unlinks links; an inline prose mention is `human`/`prose-mention`.
- Amendment 4 (sections 7.4, 10): the commit body gains the verb `unlink`, the human kinds gain `prose-mention`, and section 7.4 moves into phase 1.
- Amendment 5 (section 6.3): the recent-change rule does not apply to path, anchor, script, tree or version findings.
- Amendment 6 (section 5): phase 1 `version` tokens are runtime floors with a floor marker only; the project's own version is deferred.
- Amendment 7 (section 2): `--check` and `--date` are added; preflight refuses when git has no author identity; `--no-agents` arrives with phase 3.

Rulings made during implementation that change designed behaviour (ledger `.superpowers/sdd/2026-10-09-document-drift-phase-1/progress.md`):

- R5 (section 5): reference-style images are a separate inline kind `refimage`, so they are never unlinked.
- R6, R11 (sections 5, 7.1): path and anchor tokens come from reference definitions, never from reference usages; a definition may be replaced, and deleting one is `large-deletion`.
- R8, R8a (section 4): exclusion reason strings are fixed, and the never-edit regex parts keep their inline flags scoped to their own group.
- R9 (section 4): basename exclusions also match the exact conventional stem case-insensitively, and otherwise stay case-sensitive.
- R10 (section 4): the walk's ignore list still excludes docs under `node_modules`, `dist`, `target` and the like, with `build` and `bin` only when they hold no manifest.
- R12 (section 6.1): tree entries resolve doc-relative first, then root-relative.
- R13 (section 5): a path token's span covers only the path, never a `:<n>` or `#L<n>` suffix.
- R14 (section 5): the ratio filter drops only digit ratios and single-letter ratios, so `src/lib` stays a path.
- R15 (section 5): table header rows are never subjects, and a `drift-ignore` before a table covers the whole table.
- R16, R19 (section 5): tree detection, indentation unit, description columns, root labels (`tree_label`) and the `.` root marker are defined.
- R17 (section 5): an anchor's `target_doc` is always repository-relative.
- R18 (section 5): the subject is the first code, link, image or refdef inline of an item's first line or a row's first cell, and no subject when that inline yields no token.
- R20, R21 (section 6.2): a path present at HEAD is never rewritten, rename chains finish on a name they return to, renames are walked in topological order, and path lookups use literal pathspecs.
- R22 (sections 6.1, 6.2): a tree rename replaces only the entry's last segment, a parent rename is human, placeholder labels are dropped, and anchors above the repository never existed.
- R23 (sections 3, 6.1, 9): `dd_manifests.py` is split from resolve, `candidates.json` carries `honoured`, and HEAD is read with `git ls-tree HEAD`.
- R24, R30 to R35 (section 6.2): an anchor rename is provable only from a single removing commit with one slug removed and one added at the same level and similar non-empty bodies (`HEADING_BODY_SIMILARITY = 0.6`); `-N` suffixes, surviving base slugs and several removing commits are human.
- R25 (section 6.1): a script manifest with includes, imports, pattern rules or variable targets the parser cannot follow counts as defining every name.
- R26 (section 6.2): at the snapshot only doc-relative and root-relative resolution count as existed-then.
- R27 (section 6.2): a deleted path whose basename a HEAD file shares is a human decision.
- R28, R31 (section 6.1): pin files never produce a version candidate, and the Cargo workspace floor fallback is dropped.
- R29 (sections 6.1, 6.3): an ignored token never yields a candidate, and versions compare at the lower of the two precisions.
- R37, R43 (sections 7.1, 7.4): a human or summary-only finding inside an applied delete's lines is marked `superseded_by` and left out of the human list; line numbers refer to the original doc.
- R38 (section 7.1): stricter deletion rules (compound or continued fence lines, comment-only remainders, first ordered items, items holding a definition, a second edit on one line) and folding demoted deletes into the hunk that removes their lines.
- R39 (section 7.1): when the planned deletes would empty a list, table, fence or tree, every delete in that unit becomes `large-deletion`.
- R40 (section 7.1): any delete inside a block quote is `large-deletion`.
- R41 (section 7.1): a replacement in a link, image or definition destination is percent-encoded.
- R42 (sections 7.1, 7.4): a hunk's merged findings are `also` objects that keep their own verb, token and reason.
- R44 (section 7.3): a failed atomic write reverts that doc's hunks with reason `write-failed`.
- R45 (section 3): `dd_run.py` deletes every pinned output before the first step.
- R46 (section 7.4): human statements and evidence lines have fixed wording, the evidence line being the finding's evidence string.
- R47 (section 2): a workdir outside the repository is not added to `info/exclude`, and a repository with no commits is refused.
- R48 (sections 2, 7.4): staging uses literal pathspecs, a moved HEAD and a missing finding id are exit 6, and an invalid branch name is refused.
- R49 (section 2): a crashed step exits 5 naming the step, so exit 1 stays reserved for `--check`.
- R50 (sections 2, 8): the summary carries a `Base:` line and counts resolved tokens as tokens minus findings minus suppressed ones; a summary crash after a successful commit exits 5, and the branch and commit exist.
- R51 (section 7.4): scripts are shown as their invocation and tree replaces as full paths in the commit body.
- R52, R53 (section 9.1): corpus and goldens are LF-pinned, and decoys can expect `excluded` or `no-token`.
- R55 (sections 4, 8): the `drift-ignore-file` marker counts only as a real HTML comment from the scanner, so a doc that quotes it in inline code or a fence stays in scope.
- R56 (sections 2, 3, 9.1): `--check` creates no branch, so it runs from a detached HEAD (as a CI checkout is) and skips the branch-name check; `branch_from` is then null.
- R57 (sections 2, 4, 7.1): documentation accuracy: what exit 5 and exit 6 leave behind, the two-snapshot test's scope (not version floors), `--base` mechanics, `--check` side effects and the `prose-mention` and `large-deletion` split.

Rulings from the final whole-branch review:

- R59 (sections 5, 6.1, 6.2): the runtime word of a version floor needs a left boundary (`opencv-python>=4.8` is no floor), and a floor mismatch is provable only when the doc floor equalled the manifest floor at the line's snapshot; otherwise summary-only. This narrows R57's "not version floors": version floors now take the snapshot test against the manifest.
- R60 (section 6.2): a directory is a unique rename only when every file it held has a final name under one new directory; all deleted is `deleted`, any mix is `ambiguous-rename`.
- R61 (section 2): `<repo>` must be the top level of a working tree; a subdirectory, a bare repository or a `.git` directory is refused (exit 2), in `--check` mode too.
- R62 (sections 6.3, 7.1, 7.3, 7.4): a replace inside a heading is `human`/`heading-reference`, because another doc may link to the heading's slug; 7.3's claim that no anchor can break is corrected.
- R63 (sections 6.1, 6.2): a snapshot's tree is never listed; the run asks `git cat-file --batch-check` once for every snapshot path it needs and lists a directory with `git ls-tree -r <sha> -- <dir>`. HEAD resolution is unchanged.
- R64 (section 6.2): a provable outcome without an evidence commit is `human`/`ambiguous-rename`, and a hunk whose reason has no 7-character sha after ` in ` and no `manifest ` prefix stops the run with exit 5.
- R65 (section 2): an exception outside every step (clearing outputs, rewriting `preflight.json` or `inventory.json`, writing stdout, reading the final hunks) prints its traceback and exits 5.
- R66 (sections 4, 5, 6.1, 7.4, 8): the `--check` summary lists every planned edit as a commit bullet; the `large-deletion` statement names its unit in words; a marker with no colon or an empty reason is a marker without a reason (a file marker then excludes nothing); `--base` scope counts tree tokens; a path absent from HEAD but present on disk counts as resolved.
- R67 (section 6.2): file renames use one old-to-new map from `git log -M --diff-filter=R` per snapshot (parallel renames of one path take the topologically last target) instead of the designed `--follow` lookup; reporting a file renamed differently on parallel branches as ambiguous is deferred to phase 2.
- R70 (section 6.2, after the final review): directory and tree listings read `git ls-tree -z` output, because without `-z` git C-quotes a name holding a quote, a backslash, a tab or a control character even with `core.quotePath=false`; such a child fell out of a directory's file list, so a partly deleted directory could still read as wholly moved and get a provable replace.

## 11. Assumptions

### 11.1 Table

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| A1 | Token resolution (paths, anchors, scripts, versions, identifiers, flags, env vars, config keys) covers most real drift fixes | Measured on [02]'s sample of 82 fixes across 32 repositories; not on this owner's repositories | The provable commit is thin; most value moves to phase 3 |
| A2 | The per-line two-snapshot test separates `existed-then` from `never-existed` correctly for paths, so `existed-then` unresolved paths are safe to delete | Measured, small sample (11.2 S2, S3): it correctly protected both deliberate "no longer exists" sentences found; no false `existed-then` path in a live doc after the exclusions. For identifiers it is not sufficient (all live-doc hits were false positives), hence identifiers never delete. Partly measured by the phase 1 implementation: the corpus (three fixtures, 24 planted items, 20 decoys) passes with every planted item at its expected class and no decoy edited, and the 2026-10-09 live run of the built pipeline on ralph and better-memory classed both S3 sentences `summary-only` again, with no provable edit in either repository. The live sample still holds no true `existed-then` path, so delete precision on real drift rests on the corpus | Wrong deletions of correct prose; the re-check cannot catch these because the deleted token no longer fires. The corpus carries the deliberate-mention decoy (9.1) |
| A3 | Git rename detection gives a unique final name often enough to make `provable-replace` worthwhile for paths | Measured (11.2 S4): 0 to 52 percent of vanished paths, typically about 20; ambiguous never observed. Phase 1 adds routes to `ambiguous-rename` that S4 did not model (same basename at HEAD, R27; parent-directory tree renames, R22); their frequency on real repositories is unmeasured, since the live run produced no rename candidate | Provable replace stays a minority edit; the provable commit is mostly deletions, which is consistent with maintainer behaviour in [02] |
| A4 | Symbol rename pairing by hunk alignment gives a unique, correct candidate often enough to be worth phase 2 | Unverified; validation planned as a phase 2 spike on real history | Symbol renames fall back to `human`; phase 2 shrinks to existence checks |
| A5 | Union-of-idioms flag detection finds defined flags precisely across languages | Unverified; regexes in the sibling skill were measured on Python only | `flag` findings produce false deletes; phase 2 must measure before enabling provable deletes for flags |
| A6 | A hand-written block scanner (no markdown library) is adequate for the spans the resolvers need | Measured (11.2 S5): even a naive line scanner agreed with CommonMark on 99.6 percent of inline code spans and 98.8 percent of fence lines over 321 docs; the residual constructs are now named requirements of `dd_md_scan.py`, guarded by a parity test. Phase 1: `dd_md_scan.py` passes the parity test against `markdown-it-py` on the committed real-document corpus (`tests/fixtures/markdown/`), counting autolinks with links (R2); refdef titles on a later line and link validation are not modelled | A mis-located span makes a provable edit hit the wrong text; the exact-span replace and the re-check are the backstops |
| A7 | `git blame -w -M` on the token's line gives the right snapshot | Measured on the two real cases (11.2 S3); `-w -M` behaviour on reformatted docs unmeasured | A reflowed paragraph moves the snapshot forward, turning `existed-then` into `never-existed`: a missed finding, never a wrong edit |
| A8 | Placeholder, "create this path", slash-route and fraction filtering, plus `never-existed` being summary-only, keeps noise out of the edits | Measured (11.2 S1): unresolved paths that never existed are dominated by runtime artefacts, URL routes, slash commands and fractions; none can produce an edit by construction | The summary's counts are noisy; the `possible-typo` promotion is the only path to a human decision and is restricted to tokens with a file extension |
| A9 | Constrained rewrites plus a checker exceed the published 55 to 65 percent correctness | Unverified; measured in phase 3 by design (D14) | Rewrites become `human` by default; the skill is a provable fixer plus a reporter |
| A10 | The owner's PR process can parse the commit grammar in 7.4 | Owner-stated process; grammar not yet seen by it | A grammar change; cheap before phase 1 ships |
| A11 | Leaving the user on the drift branch after a run is acceptable | Unverified; inferred from "just create the branch" | A config switch to return to the starting branch |
| A12 | Default lead cap 25 and recent-change window 14 days are reasonable | Unmeasured conventions; rest on no input yet (guardrail 0(d)) | Too many or too few judged leads; tune from the first live run |
| A13 | Copy-with-byte-equality is acceptable for sharing code with tech-debt-scan | Repository precedent (karate-bootstrap) | A shared package would need a change to the direct-path rule |
| A14 | Running inside the target repository's working tree (not a worktree) is safe given the clean-tree refusal | Inferred | A worktree mode would isolate the user's checkout |
| A15 | `HEADING_BODY_SIMILARITY = 0.6` (difflib ratio between the old and new section bodies) separates a heading rename from a section replaced in the same commit (R30) | Unmeasured convention; rests on no input (guardrail 0(d)). Two of the three corpus fixtures (`py-service`, `go-cli`) carry a renamed-heading item that clears it, and the 2026-10-09 live run produced no anchor candidate, so neither side of the threshold has been observed on real history | Too high: renamed headings with edited bodies become human decisions. Too low: an anchor is followed to a heading that replaced a different section. Measure on the first live run with anchor drift |

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
- Phase 1 live check (2026-10-09, `docs/evaluation-log.md`): the built pipeline on throwaway clones of ralph and better-memory scanned 37 and 38 docs, produced 166 and 87 candidates, all `summary-only`, no human finding and no edit, and no branch. Of the 253 unresolved path and tree references, exactly two had ever existed in history, the two S3 sentences, both correctly protected by the per-line snapshot.
