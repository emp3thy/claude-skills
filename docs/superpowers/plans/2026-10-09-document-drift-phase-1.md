# document-drift phase 1 (deterministic core) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `/document-drift` phase 1: a script-only skill that finds markdown references to paths, anchors, scripts, runtime versions and directory-tree entries that no longer hold, fixes the provable ones in place, and leaves one commit on a new branch with a "Needs a human decision" section for the rest.

**Architecture:** Pure-Python scripts under `skills/document-drift/scripts/`, each a library with a `run(...)` function plus a thin `main(argv)`, chained in-process by `dd_run.py` which checks every pinned output file (exit 5 when one is missing). Git is the source of truth for the tree, history (per-line blame snapshot, rename records) and the commit. No agents in this phase.

**Tech Stack:** Python 3.11+, pyyaml (runtime), git 2.30+ on PATH; pytest, ruff, mypy strict, markdown-it-py (dev only, parity test).

**Spec:** `docs/superpowers/specs/2026-10-09-document-drift-design.md` (sections 2 to 9 and 11; phase 1 scope in section 10). Read it before any task.

## Global Constraints

- Runtime dependencies: Python standard library and `pyyaml` only. `markdown-it-py` is a dev extra used by one test.
- Every module in `skills/document-drift/scripts/` and every helper in `skills/document-drift/tests/` is named `dd_*.py`, and every test file `test_dd_*.py`: the three skills share one pytest process and one mypy run, and karate-bootstrap uses `kb_` for the same reason. The tests directory has no `__init__.py`.
- Scripts are direct-path invocable from `skills/document-drift/`: `python scripts/dd_<name>.py ...`. Sibling imports are flat (`from dd_common import run_git`).
- Every git call is a list argv through `dd_common.run_git` (timeout 120 s). Commit messages go through a file (`git commit -F <path>`), never argv. Never `git add -A`, `git add .`, `git commit -a`, `git push`.
- JSON outputs are written by `dd_common.write_json` (UTF-8, `indent=1`, `sort_keys=True`, LF, trailing newline). All paths inside outputs are repository-relative with `/`.
- Every repository-derived string written into a commit message or `summary.md` passes through `dd_redaction.redact`.
- Doc edits preserve each file's line endings (CRLF or LF, detected per file) and its trailing-newline state.
- Line numbers in all outputs are 1-based; columns are 0-based character offsets within the line.
- Exit codes: 0 success, 1 `--check` found provable edits, 2 refused, 5 an expected step output is missing, 6 commit failed after edits were applied.
- ruff (line length 100, rules E F I B UP SIM), mypy strict over `skills/document-drift/scripts`, and `dd_check_skill.py` all pass in CI.

## Spec amendments this plan makes

Recorded in the spec by Task 12; each follows from a fact found while planning.

1. Section 9: modules are `dd_`-prefixed; `merge.py` is folded into `dd_fixes.py` (no agent output to merge in phase 1); `dd_run.py` chains the steps; only `redaction.py` is copied byte-for-byte; `git_history.py`, `evidence.py`, `validation.py`, `slugs.py` and `reference_graph.py` are not needed until phase 2 or 3.
2. Section 4 walk: the doc list comes from `git ls-files` (preflight already requires a clean git tree, so every doc is tracked), with tech-debt-scan's path-class globs copied; no filesystem walk.
3. Section 7.1: phase 1 deletes only list items and table rows whose subject is the token, single-command fence lines, tree leaf lines, and unlinks links; an inline prose mention becomes `human` with new kind `prose-mention` (prose is phase 3's rewrite job).
4. Section 7.4: the provable commit body gains the verb `unlink`; the human-decision kinds gain `prose-mention`; the section moves into phase 1 because phase 1 already yields human findings.
5. Section 6.3: the recent-change rule does not apply to path, anchor, script, tree or version findings (a rename or deletion is a deliberate act recorded in history); it applies from phase 2 to symbol findings and in phase 3 to judged findings.
6. Section 5: phase 1 `version` tokens are runtime floors only (a floor marker such as `+`, `>=`, `or later` is required); the project's own version is deferred.
7. Section 2: `--check` (no edits, exit 1 when any provable hunk exists) and `--date` (fixes the branch date and run id, for tests) are added; preflight refuses when git has no author identity; `--no-agents` arrives with phase 3, the first phase that has agents to skip.

## Review Focus

Inputs the spec implies but no feature test would otherwise exercise; each line names the task that owns its test.

1. A Windows checkout with `core.autocrlf=true`: docs have CRLF endings and an edit must keep CRLF on every line it writes (Task 8, `test_apply_preserves_crlf`).
2. Link targets with URL encoding or spaces (`reports/Gap%20analysis.md`): decode before resolving, so a present file is not reported (Task 6, `test_resolve_decodes_percent_encoding`).
3. A shallow clone or missing history objects: blame or `cat-file` fails, the token must be treated as not existed-then (summary-only, never an edit), and the summary says history was unavailable (Task 6, `test_no_history_means_no_edit`).
4. A doc that is not UTF-8, is over 2 MB, or has a NUL byte: skipped with a reason, never crashes the run (Task 3, `test_unreadable_doc_skipped_with_reason`).
5. Monorepo docs that name paths relative to their package, or bare filenames: suffix and basename resolution must find them so nothing present is reported (Task 6, `test_resolve_suffix_and_basename`).

## File structure

```
skills/document-drift/
  SKILL.md
  scripts/
    dd_common.py        run_git, write_json, read_json, exit codes, StepError
    dd_redaction.py     byte copy of tech-debt-scan scripts/redaction.py
    dd_check_skill.py   copy of karate-bootstrap kb_check_skill.py, retargeted
    dd_config.py        .document-drift.yaml loading and defaults
    dd_md_scan.py       markdown block and inline scanner
    dd_inventory.py     doc list and exclusions          -> inventory.json
    dd_extract.py       typed tokens                     -> tokens.json
    dd_history.py       blame snapshots, trees at a sha, renames, heading history
    dd_resolve.py       resolution, two-snapshot, classes -> candidates.json
    dd_fixes.py         findings and provable hunks      -> findings.json, hunks-provable.json
    dd_apply.py         apply, re-check, revert          -> applied.json
    dd_preflight.py     refusal checks, workdir exclude  -> preflight.json
    dd_commit.py        branch, commit, message grammar  -> commits.json
    dd_summary.py       terminal summary                 -> summary.md
    dd_run.py           the chain
  tests/
    conftest.py
    dd_make_history.py  copy of tech-debt-scan tests/helpers/make_history.py + rename + dict input
    dd_helpers.py       tiny repo builders for unit tests
    fixtures/corpus/{py-service,ts-web,go-cli}/{files/,history.yaml,planted.json}
    fixtures/markdown/  parity corpus
    golden/<fixture>/   byte goldens
    test_dd_*.py
```

Shared shapes, used by several tasks (all JSON objects; `null` where absent):

- **Token** (`tokens.json` is `{"docs": {doc: [Token...]}, "markers": [...], "skipped": [...]}`): `doc`, `line`, `col`, `end_col`, `kind` (`path` `anchor` `script` `version` `tree`), `text` (the reference as written), `target_doc` (anchor only: the doc whose headings it names), `script_tool` (script only: `make` `npm` `yarn` `pnpm` `just` `task`), `version` (version only: `{"runtime": str, "floor": str}`), `context` (`inline-code` `link` `image` `fence` `tree` `prose`), `link` (`{"col", "end_col", "text"}` of the whole `[text](target)` when the token is a link target), `block` (`{"kind", "line_start", "line_end"}` where kind is `paragraph` `list_item` `table_row` `fence` `heading` `tree`), `subject` (true when the token is the first reference in its list item or the first cell of its table row), `heading_path` (list of heading texts), `never_edit` (bool), `generated` (bool), `ignored` (marker reason or null), `editable` (false when the span crosses lines).
- **Candidate** (`candidates.json` is `{"candidates": [...], "history_unavailable": bool}`): every Token field plus `resolved_then` (repository path the token named at its snapshot, or null), `snapshot` (sha or null), `existed_then` (bool), `outcome` (`unique` `ambiguous` `deleted` `version-mismatch`), `replacement` (new token text or null), `evidence_commit` (7-char sha or null), `evidence` (string), `class` (`provable-replace` `provable-delete` `human` `summary-only`), `human_kind` (`ambiguous-rename` `large-deletion` `prose-mention` `never-edit-section` `generated-region` `recheck-failed` or null).
- **Hunk** (`hunks-provable.json` is `{"hunks": [...]}`): `id` (`H001`...), `finding_id` (`F001`...), `doc`, `line_start`, `line_end`, `before` (list of line strings without endings), `after` (list), `verb` (`replace` `delete` `unlink`), `token_kind`, `token_text`, `new_text` (replace only), `reason` (e.g. `renamed in a1b2c3d`).

---

### Task 1: Skill scaffold, copied modules and repo wiring

**Confidence:** 95%

**Files:**
- Create: `skills/document-drift/scripts/dd_common.py`, `skills/document-drift/scripts/dd_redaction.py` (byte copy of `skills/tech-debt-scan/scripts/redaction.py`), `skills/document-drift/scripts/dd_check_skill.py` (copy of `skills/karate-bootstrap/scripts/kb_check_skill.py`; module docstring usage line and nothing else changed except the name in it), `skills/document-drift/SKILL.md` (frontmatter `name: document-drift`, `description`, `triggers: [/document-drift]`, one-paragraph body; Task 11 fills it), `skills/document-drift/tests/conftest.py` (same shape as karate's: put `scripts/` and `tests/` on `sys.path`), `skills/document-drift/tests/dd_make_history.py`, `skills/document-drift/tests/dd_helpers.py`
- Modify: `pyproject.toml` (append `skills/document-drift/tests` to `testpaths`; append `skills/document-drift/scripts` to mypy `files` and `mypy_path`; add `"markdown-it-py>=3.0"` to the `dev` extra), `.github/workflows/test.yml` (add `- run: python skills/document-drift/scripts/dd_check_skill.py` after the karate line; set `fetch-depth: 0` on the test job's checkout so history-based tests and the later self-scan see full history)
- Test: `skills/document-drift/tests/test_dd_common.py`, `test_dd_copies.py`, `test_dd_make_history.py`

**Interfaces:**
- Produces, in `dd_common`: `run_git(root: Path, args: Sequence[str]) -> str | None` (stdout, or None on any failure; same contract as tech-debt-scan `git_history.run_git`); `git_ok(root: Path, args: Sequence[str]) -> bool` (exit code 0); `write_json(path: Path, doc: Any) -> None`; `read_json(path: Path) -> Any`; constants `EXIT_OK=0`, `EXIT_FOUND=1`, `EXIT_REFUSED=2`, `EXIT_MISSING=5`, `EXIT_COMMIT=6`, `MAX_DOC_BYTES=2_000_000`; `class StepError(Exception)` with attribute `code: int`.
- Produces, in `dd_make_history`: `replay_history(history_yaml: Path, files_root: Path, dest: Path) -> Path` and `replay_fixture(name: str, dest: Path) -> Path` as in the source (with `CORPUS_ROOT` pointing at this skill's `tests/fixtures/corpus`), plus `replay_commits(commits: list[dict[str, Any]], files_root: Path | None, dest: Path) -> Path` (the same loop over an in-memory list); each commit may carry `rename: {old: new}`, applied with `git mv` before `files` are written.
- Produces, in `dd_helpers`: `make_repo(tmp_path: Path, commits: list[dict[str, Any]]) -> Path` (wraps `replay_commits`, identity `Fixture <fixture@example.com>`, dates required in each commit).

- [ ] **Step 1: Create the branch**

Run: `git switch -c feat/document-drift-phase-1`
Expected: `Switched to a new branch 'feat/document-drift-phase-1'`

- [ ] **Step 2: Write the failing tests**

```python
# test_dd_copies.py
def test_redaction_is_byte_identical_to_tech_debt_scan():
    here = Path(__file__).resolve().parents[2]
    assert (here / "document-drift/scripts/dd_redaction.py").read_bytes() == \
        (here / "tech-debt-scan/scripts/redaction.py").read_bytes()

# test_dd_make_history.py
def test_rename_key_produces_a_git_rename(tmp_path):
    repo = make_repo(tmp_path, [
        {"author": "A <a@x>", "date": "2024-01-01T00:00:00+00:00", "subject": "add",
         "files": {"src/old.py": "x = 1\n"}},
        {"author": "A <a@x>", "date": "2024-02-01T00:00:00+00:00", "subject": "mv",
         "rename": {"src/old.py": "src/new.py"}},
    ])
    log = run_git(repo, ["log", "-M", "--diff-filter=R", "--name-status", "--format="])
    assert "src/old.py\tsrc/new.py" in log

# test_dd_common.py
def test_run_git_returns_none_on_failure(tmp_path):
    assert run_git(tmp_path, ["rev-parse", "HEAD"]) is None

def test_write_json_is_sorted_lf_with_trailing_newline(tmp_path):
    p = tmp_path / "x.json"
    write_json(p, {"b": 1, "a": [1]})
    assert p.read_bytes() == b'{\n "a": [\n  1\n ],\n "b": 1\n}\n'
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest skills/document-drift/tests -v`
Expected: FAIL (modules not found)

- [ ] **Step 4: Implement the scaffold**

Copy the two source files as named above. `dd_check_skill.py` defaults `--skill` to `../SKILL.md` and `--scripts` to its own directory, exactly as the karate copy does. Write `dd_common.py` and the two test helpers to the interfaces. `pip install -e ".[dev]"` to pick up markdown-it-py.

- [ ] **Step 5: Verify**

Run: `pytest skills/document-drift/tests -v && ruff check . && mypy && python skills/document-drift/scripts/dd_check_skill.py`
Expected: all pass; the existing suites still pass (`pytest -q` at repo root shows no new failures).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .github/workflows/test.yml skills/document-drift
git commit -m "feat(document-drift): skill scaffold, copied modules and test helpers"
```

---

### Task 2: Markdown scanner

**Confidence:** 90%. The naive scanner measured in the spec's validation pass (S5) already agreed on 99.6 percent of inline code; the constructs it missed are listed below and each gets a test.

**Files:**
- Create: `skills/document-drift/scripts/dd_md_scan.py`, `skills/document-drift/tests/fixtures/markdown/constructs.md` (one example of every construct below), and copies of this repository's `README.md`, `docs/architecture.md`, `skills/tech-debt-scan/SKILL.md` and `skills/karate-bootstrap/SKILL.md` into `tests/fixtures/markdown/` (frozen copies, so the parity test does not move when those docs change)
- Test: `skills/document-drift/tests/test_dd_md_scan.py`, `test_dd_md_parity.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Block: kind: str; line_start: int; line_end: int; info: str | None; level: int | None; text: str | None; parent: int | None` with `kind` one of `heading` `paragraph` `list_item` `table_row` `table_delim` `fence` `indented_code` `blockquote` `html` `refdef` `blank`; `info` the fence info string; `level` the heading level; `text` the heading text; `parent` the index of the enclosing list item for nested blocks.
  - `@dataclass(frozen=True) class Inline: kind: str; line: int; col: int; end_line: int; end_col: int; text: str; label: str | None; outer_col: int | None; outer_end_col: int | None; block: int` with `kind` one of `code` `link` `image` `autolink` `reflink`; `text` the code content or link target (unescaped, reference links resolved through refdefs); `label` the link text; `outer_*` the span of the whole `[label](target)`.
  - `@dataclass(frozen=True) class Comment: line_start: int; line_end: int; body: str`
  - `@dataclass(frozen=True) class Scan: lines: list[str]; blocks: list[Block]; inlines: list[Inline]; comments: list[Comment]`
  - `scan(text: str) -> Scan`; `lines` are the text split on `\r\n` or `\n` without endings.

- [ ] **Step 1: Write the failing construct tests**

One test per construct, each asserting exact `Block` or `Inline` fields on a small string: `test_backtick_and_tilde_fences_close_only_on_same_char_and_length`, `test_fence_indented_inside_list_item_is_a_fence`, `test_code_span_continuing_across_line_break` (`end_line == line + 1`), `test_multi_backtick_span_containing_backtick` (``` `` a`b `` ``` gives text ``a`b``), `test_reference_style_link_resolves_through_refdef`, `test_escaped_pipe_does_not_split_table_cell`, `test_table_row_blocks_have_line_numbers`, `test_setext_heading_text_and_level`, `test_html_comment_is_a_comment_not_a_paragraph`, `test_nested_list_item_parent_index`, `test_image_inline_kind`, `test_inline_code_inside_fence_is_not_an_inline`, `test_crlf_input_gives_same_scan_as_lf`.

- [ ] **Step 2: Write the failing parity test**

```python
# test_dd_md_parity.py
@pytest.mark.parametrize("name", sorted(p.name for p in MARKDOWN_DIR.glob("*.md")))
def test_parity_with_commonmark(name):
    text = (MARKDOWN_DIR / name).read_text(encoding="utf-8")
    ours, ref = scan(text), reference_spans(text)   # reference_spans uses markdown-it-py
    assert fence_lines(ours) == ref.fence_lines
    assert Counter(i.text for i in ours.inlines if i.kind == "code") == ref.code_spans
    assert Counter(i.text for i in ours.inlines if i.kind in ("link", "reflink", "image")) \
        == ref.link_targets
```

`reference_spans` lives in the test file and uses `MarkdownIt("commonmark").enable("table")`, reading `fence` token maps, `code_inline` children and `link_open`/`image` hrefs. A construct the scanner deliberately does not model goes in an explicit `KNOWN_DIFFERENCES` dict in the test with a one-line reason; the dict starts empty.

- [ ] **Step 3: Run to verify failure**

Run: `pytest skills/document-drift/tests/test_dd_md_scan.py skills/document-drift/tests/test_dd_md_parity.py -v`
Expected: FAIL (module not found)

- [ ] **Step 4: Implement `scan(text: str) -> Scan` in `dd_md_scan.py`**

Two passes: a block pass over lines (fence state machine with opening char and length, list item indentation stack for nesting and indented fences, table detection by a delimiter row, setext underline lookback, HTML comment spans), then an inline pass per paragraph, list item and table row joining the block's lines with `\n` so code spans can cross a line break, mapping offsets back to (line, col). Link reference definitions are collected in the block pass and applied in the inline pass.

- [ ] **Step 5: Verify**

Run: `pytest skills/document-drift/tests -v && mypy && ruff check .`
Expected: PASS, `KNOWN_DIFFERENCES` empty or each entry justified.

- [ ] **Step 6: Commit**

```bash
git add skills/document-drift/scripts/dd_md_scan.py skills/document-drift/tests
git commit -m "feat(document-drift): markdown scanner with CommonMark parity test"
```

---

### Task 3: Config and inventory

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_config.py`, `skills/document-drift/scripts/dd_inventory.py`
- Test: `skills/document-drift/tests/test_dd_config.py`, `test_dd_inventory.py`

**Interfaces:**
- Consumes: `dd_common.run_git`, `write_json`, `MAX_DOC_BYTES`.
- Produces:
  - `dd_config.DEFAULTS = {"exclude": [], "never_edit_heading": None, "branch": "docs/drift-{date}", "commit_trailers": [], "lead_cap": 25, "recent_change_days": 14}`; `CONFIG_FILENAME = ".document-drift.yaml"`; `load_config(root: Path) -> tuple[dict[str, Any], list[str]]` (merged config and warnings: unknown keys and wrong types produce a warning and the default).
  - `dd_inventory.DEFAULT_NEVER_EDIT = r"(?i)\b(why|rationale|decision|decisions|history|roadmap|deprecated|deprecation|migration|changelog|release notes|license|licence)\b"`; `run(root: Path, workdir: Path, config: dict[str, Any]) -> dict[str, Any]` writing `workdir/inventory.json` = `{"docs": [path...], "excluded": [{"path", "reason"}], "skipped": [{"path", "reason"}], "files": [every tracked path], "never_edit_re": str}`; `main(argv: list[str] | None = None) -> int` with `<repo> --workdir DIR`.

- [ ] **Step 1: Write the failing tests**

Build each case with `dd_helpers.make_repo` and assert membership of `docs` and the exact `reason` string in `excluded`:

- `test_superpowers_tree_excluded` (`docs/superpowers/plans/x.md`, `docs/superpowers/archive/y.md`: reason `path:docs/superpowers/**`)
- `test_research_archive_adr_rfc_excluded` (one doc under each of `docs/research/`, `a/research_notes/`, `a/archive/`, `a/adr/`, `a/rfcs/`)
- `test_history_basenames_excluded` (`CHANGELOG.md`, `HISTORY.md`, `LICENSE.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`: reason `basename:<glob>`)
- `test_claude_and_agents_md_in_scope_at_any_depth`
- `test_vendored_nested_library_excluded` (`libs/foo/LICENSE` plus `libs/foo/library.json` plus `libs/foo/README.md`: reason `vendored-library:libs/foo`; a nested package whose manifest names the root project is not excluded)
- `test_vendored_dir_names_excluded` (`libraries/`, `extern/`, `external/`, `third_party/`, `deps/`, `vendor/`)
- `test_tests_class_excluded` (`tests/fixtures/x/README.md`)
- `test_gitattributes_linguist_generated_and_vendored` (`docs/api/** linguist-generated`)
- `test_do_not_edit_header_excluded` (first five lines)
- `test_submodule_path_excluded` (gitlink from `git ls-files -s` mode 160000)
- `test_template_dirs_and_tmpl_md_excluded`
- `test_drift_ignore_file_marker_excluded` (reason `marker:<reason text>`)
- `test_config_exclude_glob`
- `test_unreadable_doc_skipped_with_reason` (Review Focus 4: non-UTF-8 bytes give `skipped` reason `not-utf8`, over `MAX_DOC_BYTES` gives `too-large`, NUL in the first KB gives `binary`)
- `test_load_config_unknown_key_warns`

- [ ] **Step 2: Run to verify failure**

Run: `pytest skills/document-drift/tests/test_dd_inventory.py skills/document-drift/tests/test_dd_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `load_config` and `dd_inventory.run`**

Doc candidates are `git ls-files -z` entries ending `.md` (case-insensitive). Copy tech-debt-scan's `PATH_CLASS_GLOBS` `vendored`, `generated` and `tests` tuples (from `skills/tech-debt-scan/scripts/inventory.py:170-183`) and its `_classify_path` matching rule (fnmatchcase against the relative path and the basename). Exclusion checks run in the order the spec lists them in section 4 and the first match records the reason. `.gitattributes` patterns follow git's rule: no `/` matches the basename at any depth, otherwise anchored to the repository root, `**` allowed.

- [ ] **Step 4: Verify**

Run: `pytest skills/document-drift/tests -v && mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/document-drift/scripts/dd_config.py skills/document-drift/scripts/dd_inventory.py skills/document-drift/tests/test_dd_config.py skills/document-drift/tests/test_dd_inventory.py
git commit -m "feat(document-drift): config loading and doc inventory with exclusions"
```

---

### Task 4: Token extraction

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_extract.py`
- Test: `skills/document-drift/tests/test_dd_extract.py`

**Interfaces:**
- Consumes: `dd_md_scan.scan`, `Scan`, `Block`, `Inline`; `inventory.json`.
- Produces: `extract_doc(doc: str, text: str, never_edit_re: re.Pattern[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]` (Tokens, and markers `{"doc", "line", "kind", "reason", "target_line_start", "target_line_end"}`); `run(root: Path, workdir: Path) -> dict[str, Any]` writing `tokens.json`; `main(argv)` with `<repo> --workdir DIR`. Token shape: see "Shared shapes".

Extraction rules (spec section 5, phase 1 kinds):

- `path`: an inline code span or link/image target (scheme-less, `#fragment` split off into an `anchor` token when present) that has a `/` or a known extension, has no whitespace, is not a URL, and passes the filters. A trailing `:<n>`, `:<n>-<m>` or `#L<n>...` is stripped from `text` but not from the span. Fence lines contribute `path` tokens only as arguments of `./x`, `python x`, `python3 x`, `bash x`, `sh x`, `pwsh x`, `node x`.
- Filters (token dropped): contains `<`, `>`, `{{`, `${`, `*`; matches `(?i)\b(your|my)[-_]|\bexample\b|\b(foo|bar|baz|xxx|todo)\b`; a single leading `/` and no other `/` (routes, slash commands); a ratio (`^[\w]{1,3}/[\w]{1,3}$` with no `.`); a `mkdir`, `touch`, `create`, `creates`, `new file` word on the token's line or the line before.
- Known extensions: the union in `dd_extract.KNOWN_EXTS` (code, config, docs and script extensions; copy the set used by the spike in the spec's validation pass and add `.csv`, `.ipynb`).
- `anchor`: `#frag` in a link target; `target_doc` is the link's path part resolved later, or the current doc when the target is only `#frag`.
- `script`: in fences whose info is empty or one of `bash sh shell console zsh powershell ps1 pwsh cmd`, and in inline code: `make <t>`, `npm run <t>`, `yarn <t>` / `yarn run <t>`, `pnpm <t>` / `pnpm run <t>`, `just <t>`, `task <t>`, after an optional `$ ` or `> ` prompt. Yarn and pnpm builtins (`install add remove init upgrade dlx exec create why link publish version info run`) are not scripts.
- `version`: `(?i)\b(python|node(?:\.js)?|go|golang|rust)\s+(?:version\s+)?(?:>=\s*|≥\s*|v)?(\d+(?:\.\d+){0,2})\s*(\+|or (?:later|newer|higher|above))` and `(?i)\b(python|node(?:\.js)?|go|golang|rust)\s*>=\s*(\d+(?:\.\d+){0,2})`; `text` is the number, the span is the number's span; `version.runtime` normalised to `python` `node` `go` `rust`.
- `tree`: a fence with empty or `text`/`txt` info whose non-empty lines contain at least two of `├──`, `└──`, `|--`, `` `-- ``, or are indented names ending `/`; each entry line yields one token whose `text` is the entry's repository path assembled from indentation (four-character levels; a first line that is a single name ending `/` with no glyph is a root label, not an entry); entries `...` and lines whose name contains a space are skipped; a trailing `# comment` or `<- comment` is not part of the name; the span is the name's span.
- `block`, `subject`: from the scan; `subject` is true for the first `code`/`link` inline of a list item's first line or of a table row's first cell.
- `never_edit`: any heading in `heading_path` matches the regex. `generated`: inside a region between the spec's generated markers (section 8). `ignored`: the reason of a `drift-ignore` marker covering the next block or of `drift-ignore-next-line` covering the next line; a marker without a reason is reported in `markers` with `reason: null` and ignores nothing.

- [ ] **Step 1: Write the failing tests**

`test_inline_code_path_token`, `test_link_target_with_fragment_gives_path_and_anchor`, `test_same_doc_anchor_target_doc_is_self`, `test_line_suffix_stripped_from_text_not_span`, `test_filters_drop_placeholders_routes_ratios_and_create_paths` (parametrised: `<name>/x.py`, `/pipeline`, `3/5`, `my-project/x`, `` mkdir `out/` ``), `test_fence_python_argument_is_path`, `test_scripts_in_bash_fence_and_inline` (assert `script_tool` per idiom; `yarn install` not a token), `test_version_floor_forms` (parametrised over `Python 3.11+`, `Node >= 18`, `requires Go 1.22 or later`, `Python 3.12` gives no token), `test_tree_entries_assembled_from_indentation` (assert `text` values `src/`, `src/app.py`, `docs/guide.md`), `test_tree_root_label_skipped`, `test_subject_flag_list_and_table`, `test_never_edit_from_ancestor_heading`, `test_generated_region_flag`, `test_drift_ignore_next_block_and_next_line`, `test_marker_without_reason_reported_not_honoured`, `test_multiline_code_span_not_editable`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest skills/document-drift/tests/test_dd_extract.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `extract_doc` and `run`**

- [ ] **Step 4: Verify**

Run: `pytest skills/document-drift/tests -v && mypy`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add skills/document-drift/scripts/dd_extract.py skills/document-drift/tests/test_dd_extract.py
git commit -m "feat(document-drift): typed token extraction for paths, anchors, scripts, versions, trees"
```

---

### Task 5: History primitives

**Confidence:** 90%. Blame porcelain format and rename records were checked on this machine's git (2.55) while planning.

**Files:**
- Create: `skills/document-drift/scripts/dd_history.py`
- Test: `skills/document-drift/tests/test_dd_history.py`

**Interfaces:**
- Consumes: `dd_common.run_git`.
- Produces, all caching per instance:
  - `class History: __init__(self, root: Path)`
  - `line_snapshots(self, doc: str) -> dict[int, str] | None`: line number to full sha from `git blame -w -M --porcelain HEAD -- <doc>` (blame HEAD, never the working tree); None when blame fails.
  - `tree_at(self, sha: str) -> tuple[frozenset[str], frozenset[str]] | None`: files and directories from `git ls-tree -r --name-only <sha>`; None on failure.
  - `show(self, sha: str, path: str) -> str | None`
  - `renames_since(self, sha: str) -> dict[str, tuple[str, str]]`: old path to (new path, 7-char commit) from `git log -M --diff-filter=R --name-status --format=%x1e%h <sha>..HEAD`, oldest first so chains compose.
  - `final_name(self, sha: str, path: str) -> tuple[set[str], str | None]`: follow the chain from `path`; returns the set of final names that exist at HEAD and the commit of the last hop.
  - `deleting_commit(self, sha: str, path: str) -> str | None`: `git log -1 --format=%h --diff-filter=D <sha>..HEAD -- <path>`.
  - `last_commit_touching(self, sha: str, path: str, needle: str) -> str | None`: `git log -1 --format=%h -S<needle> <sha>..HEAD -- <path>`.
  - `head_files(self) -> tuple[frozenset[str], frozenset[str]]`.

- [ ] **Step 1: Write the failing tests**

With `make_repo`: `test_line_snapshots_point_at_line_author_commit` (two commits, line 2 added by the second; assert map[2] equals the second commit's sha), `test_line_snapshots_ignore_whitespace_only_change` (`-w`), `test_line_snapshots_none_without_history` (a repo whose doc path does not exist at HEAD), `test_tree_at_lists_files_and_dirs`, `test_final_name_follows_two_hop_chain`, `test_final_name_empty_when_deleted`, `test_deleting_commit`, `test_last_commit_touching_finds_removed_make_target`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest skills/document-drift/tests/test_dd_history.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `History`**

Porcelain parsing: a header line `^[0-9a-f]{40} \d+ (\d+)` gives the sha and final line number; content lines start with a tab.

- [ ] **Step 4: Verify and commit**

Run: `pytest skills/document-drift/tests -v && mypy`
Expected: PASS

```bash
git add skills/document-drift/scripts/dd_history.py skills/document-drift/tests/test_dd_history.py
git commit -m "feat(document-drift): git history primitives (line snapshots, trees, renames)"
```

---

### Task 6: Resolution, two-snapshot test and classes

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_resolve.py`
- Test: `skills/document-drift/tests/test_dd_resolve.py`

**Interfaces:**
- Consumes: `History`; `tokens.json`; `inventory.json` (`files`).
- Produces: `resolve_token(token: dict[str, Any], files: frozenset[str], dirs: frozenset[str], read: Callable[[str], str | None]) -> str | None` (what the token names in the given tree: a repository path, a heading slug, a script name or a manifest floor; None when unresolved; `read(path)` returns that file's text in the same tree, so the one function serves HEAD, a snapshot, and Task 8's in-memory re-check); `class Resolver: __init__(self, root: Path, history: History)` with `classify(self, token: dict[str, Any]) -> dict[str, Any] | None` (a Candidate, or None when the token resolves); `run(root: Path, workdir: Path) -> dict[str, Any]` writing `candidates.json`; `main(argv)`.
- Also produces `slugify_heading(text: str) -> str` (GitHub style: lower-case, drop characters other than letters, digits, spaces, `-`, `_`; spaces to `-`) and `heading_slugs(text: str) -> set[str]` (with `-1`, `-2` duplicates and explicit `<a name>`/`id=` anchors).

Rules (spec 6.1 to 6.3 as amended):

- Path resolution order: percent-decode; strip a leading `./`; doc-relative (normalised); repository-root; for tokens with `/`, any tracked path ending with `/` + token; for bare names, any tracked basename equal to the token. A directory resolves. The mode that matched (`doc`, `root`, `suffix`, `basename`) is recorded and reused to write the replacement in the same mode.
- Anchor: path part must resolve first (an unresolved path part is the path token's finding, not the anchor's); slug in `heading_slugs` of the target doc at HEAD.
- Script: the nearest manifest walking up from the doc's directory: `Makefile` targets (`^([A-Za-z0-9_.-]+)\s*:(?!=)` lines, excluding `.PHONY`), `package.json` `scripts` keys, `justfile` recipes (`^([A-Za-z0-9_-]+)(\s+[^:]*)?:`), `Taskfile.yml` `tasks` keys. No manifest of that tool anywhere up to the root: the token is dropped (not a finding).
- Version: compare the floor with the manifest floor (`pyproject.toml` `[project].requires-python` lower bound or `.python-version`; `package.json` `engines.node` lower bound or `.nvmrc`; `go.mod` `go` directive; `Cargo.toml` `[package].rust-version`), parsed with `tomllib` and `json`. Equal at the doc's precision (`3.11` equals `3.11.4`'s `3.11`) resolves. Different: candidate with `outcome: version-mismatch`, `replacement` the manifest floor at the doc's precision, `evidence` `manifest <file> says <value>`. No manifest value: no finding.
- Tree: the assembled path resolves like a root-relative path.
- Two-snapshot (paths, anchors, scripts, trees): snapshot = `line_snapshots(doc)[line]`; `existed_then` = the token resolves against the snapshot's tree (and, for anchors, the target doc's headings at the snapshot; for scripts, the manifest at the snapshot). Blame or tree unavailable: `existed_then` false and `history_unavailable` true.
- Outcomes for existed-then tokens: paths and tree entries use `final_name` of `resolved_then` (directories: the common parent of the final names of every snapshot file under it, when they share one); one name gives `unique` with the replacement written in the original mode (suffix and basename modes must also be unique at HEAD, else `ambiguous`); several give `ambiguous`; none give `deleted` with `evidence_commit` from `deleting_commit`. Anchors: headings removed and added in the target doc between snapshot and HEAD; exactly one removed (the anchor's) and exactly one added gives `unique` (replacement is the new slug, evidence `heading renamed in <sha>`); removed with none added gives `deleted` (`heading removed in <sha>`). Scripts: always `deleted` (`removed in <sha>` from `last_commit_touching(manifest, name)`).
- Class: `never-existed` (existed_then false) gives `summary-only`. Otherwise in order: `ignored` set gives no candidate (counted as honoured marker); `generated` gives `human`/`generated-region`; `never_edit` gives `human`/`never-edit-section`; `editable` false gives `human`/`prose-mention`; `ambiguous` gives `human`/`ambiguous-rename`; `unique` or `version-mismatch` gives `provable-replace`; `deleted` gives `provable-delete` (Task 7 may demote it to `human` by the deletion-unit rules).

- [ ] **Step 1: Write the failing tests**

Each builds a small history with `make_repo` and asserts the candidate's `class`, `outcome`, `replacement` and `human_kind`:

- `test_present_path_gives_no_candidate`
- `test_renamed_file_doc_relative_mode_replacement` (doc `pkg/README.md` naming `old.py`, renamed `pkg/new.py`: replacement `new.py`)
- `test_renamed_file_root_mode_replacement`
- `test_resolve_suffix_and_basename` (Review Focus 5)
- `test_resolve_decodes_percent_encoding` (Review Focus 2)
- `test_deleted_file_existed_then_is_provable_delete_with_deleting_commit`
- `test_line_written_after_deletion_is_summary_only` (the spec's S3 shape: the doc line saying "There is no `PROMPT.md`" is committed in the deleting commit)
- `test_never_existed_path_is_summary_only`
- `test_directory_rename_via_children`
- `test_two_candidates_is_ambiguous_human`
- `test_anchor_heading_renamed_unique`, `test_anchor_heading_removed_deleted`
- `test_make_target_removed`, `test_npm_script_removed`, `test_script_without_manifest_dropped`
- `test_version_mismatch_python_and_node` (manifest `>=3.11`, doc `3.10+` gives replacement `3.10`→`3.11`; doc `3.11+` gives none; precision kept: doc `18+` vs `>=20.1` gives `20`)
- `test_tree_entry_renamed`
- `test_generated_and_never_edit_and_ignored_routing`
- `test_no_history_means_no_edit` (Review Focus 3: a blame failure gives `summary-only` and `history_unavailable: true`)

- [ ] **Step 2: Run to verify failure**

Run: `pytest skills/document-drift/tests/test_dd_resolve.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `dd_resolve`**

- [ ] **Step 4: Verify and commit**

Run: `pytest skills/document-drift/tests -v && mypy`
Expected: PASS

```bash
git add skills/document-drift/scripts/dd_resolve.py skills/document-drift/tests/test_dd_resolve.py
git commit -m "feat(document-drift): resolution, per-line two-snapshot test and fix classes"
```

---

### Task 7: Findings and provable hunks

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_fixes.py`
- Test: `skills/document-drift/tests/test_dd_fixes.py`

**Interfaces:**
- Consumes: `candidates.json`; `dd_md_scan.scan` (to find list item, table and fence extents in the current doc text).
- Produces: `plan_hunks(doc_text: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]` (hunks, and the candidates demoted to human with their new `human_kind`); `run(root: Path, workdir: Path) -> dict[str, Any]` writing `findings.json` = `{"findings": [Candidate + "id": "F001"...]}` ordered by doc then line then col, and `hunks-provable.json`; `main(argv)`.

Edit rules (spec 7.1 as amended):

- `provable-replace`: replace the characters `[col, end_col)` of the line with `replacement`; when the token is a link target and the link's label equals the old target text, the label is replaced too; `verb: replace`.
- `provable-delete`, tried in order:
  1. Token is the `subject` of a `list_item` with no nested child items and at least one sibling item: delete the item's lines. Only item in its list, or has children: `human`/`large-deletion`.
  2. Token is the `subject` of a `table_row` (not the header) and the table keeps at least one data row: delete the row. Otherwise `human`/`large-deletion`.
  3. Token is a `script` or fence `path` on a line of a shell fence whose stripped content (after an optional `$ ` prompt) is a single command with no `&&`, `||`, `;`, `|`, and the fence keeps at least one other non-empty line: delete that line. Otherwise `human`/`large-deletion`.
  4. Token is a `tree` entry with no deeper-indented lines directly beneath it: delete the line. Otherwise `human`/`large-deletion`.
  5. Token is a `link` target (not an image): replace the whole `[label](target)` with `label`; `verb: unlink`.
  6. Anything else: `human`/`prose-mention`.
- Two candidates producing the same line range merge into one hunk (first finding id wins, the others are listed in the hunk's `also` field and in the commit body under the same line). Overlapping but different ranges: the later one in document order becomes `human`/`large-deletion`.
- `before`/`after` hold whole lines; `after` is empty for a line deletion.

- [ ] **Step 1: Write the failing tests**

Pure text tests (no git): `test_replace_inline_code_span_only`, `test_replace_link_target_and_matching_label`, `test_delete_subject_list_item_with_continuation_lines`, `test_only_list_item_is_large_deletion`, `test_list_item_with_children_is_large_deletion`, `test_non_subject_inline_mention_is_prose_mention`, `test_delete_table_row_subject`, `test_last_table_data_row_is_large_deletion`, `test_delete_single_command_fence_line`, `test_compound_command_line_is_large_deletion`, `test_delete_tree_leaf_line`, `test_tree_parent_is_large_deletion`, `test_unlink_keeps_label`, `test_image_is_prose_mention`, `test_same_range_hunks_merge`, `test_findings_ordered_and_numbered`.

- [ ] **Step 2: Run to verify failure, implement, verify, commit**

Run: `pytest skills/document-drift/tests/test_dd_fixes.py -v` (FAIL), implement `plan_hunks` and `run`, then `pytest skills/document-drift/tests -v && mypy` (PASS).

```bash
git add skills/document-drift/scripts/dd_fixes.py skills/document-drift/tests/test_dd_fixes.py
git commit -m "feat(document-drift): findings and provable hunks with deletion-unit rules"
```

---

### Task 8: Apply and re-check

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_apply.py`
- Test: `skills/document-drift/tests/test_dd_apply.py`

**Interfaces:**
- Consumes: `hunks-provable.json`, `findings.json`; `dd_extract.extract_doc`; `dd_resolve.resolve_token`.
- Produces: `run(root: Path, workdir: Path) -> dict[str, Any]` writing `applied.json` = `{"applied": [hunk ids], "reverted": [{"hunk", "reason"}], "docs": [edited doc paths]}` and updating `findings.json` so each reverted hunk's findings become `human`/`recheck-failed`; `main(argv)`.

Rules (spec 7.3):

- Read each doc with `newline=""`; detect the ending (`\r\n` when it is the majority line ending, else `\n`) and the trailing-newline state; apply hunks bottom-up by `line_start`.
- Before applying a hunk, its `before` lines must equal the current lines exactly, else revert with reason `before-mismatch`.
- After applying a hunk, re-extract the doc in memory and resolve its tokens against HEAD: the multiset of unresolved `(kind, text)` must be a subset of the previous multiset minus the hunk's own token(s), and for `replace` the new text must resolve. Otherwise undo that hunk and record `recheck-new-finding` or `recheck-still-unresolved`.
- Write the doc atomically (`<doc>.dd-tmp` then `os.replace`) once all its hunks are settled, with the original endings.

- [ ] **Step 1: Write the failing tests**

`test_apply_replace_and_delete_bottom_up`, `test_apply_preserves_crlf` (Review Focus 1: a CRLF doc stays CRLF on every line, including edited ones), `test_apply_preserves_missing_trailing_newline`, `test_before_mismatch_reverts`, `test_replacement_that_does_not_resolve_is_reverted_and_marked_recheck_failed`, `test_delete_that_exposes_no_new_finding_is_kept`.

- [ ] **Step 2: Run to verify failure, implement, verify, commit**

Run: `pytest skills/document-drift/tests/test_dd_apply.py -v` (FAIL), implement, `pytest skills/document-drift/tests -v && mypy` (PASS).

```bash
git add skills/document-drift/scripts/dd_apply.py skills/document-drift/tests/test_dd_apply.py
git commit -m "feat(document-drift): apply hunks with re-check and revert"
```

---

### Task 9: Preflight and commit

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_preflight.py`, `skills/document-drift/scripts/dd_commit.py`
- Test: `skills/document-drift/tests/test_dd_preflight.py`, `test_dd_commit.py`

**Interfaces:**
- Produces:
  - `dd_preflight.run(root: Path, workdir: Path, branch: str, check: bool) -> dict[str, Any]` writing `preflight.json` = `{"head", "branch_from", "branch", "git_version"}`; raises `StepError(code=EXIT_REFUSED)` with a one-line message for: not a git repository, detached HEAD, dirty tree (`git status --porcelain` non-empty; the workdir is excluded first), branch exists, no author identity (`git var GIT_AUTHOR_IDENT` fails). In `check` mode only the first two refusals apply. Appends the workdir's repository-relative path to the file named by `git rev-parse --git-path info/exclude` when absent.
  - `dd_commit.render_message(findings: list[dict[str, Any]], hunks: list[dict[str, Any]], applied: list[str], *, run_id: str, base: str, scope: str, trailers: list[str]) -> str` (the exact grammar below, redacted); `dd_commit.render_human(findings: list[dict[str, Any]]) -> str` (the section alone, also used by the summary); `dd_commit.run(root: Path, workdir: Path, branch: str, run_id: str, scope: str, trailers: list[str]) -> dict[str, Any]` writing `commits.json` = `{"branch": str | None, "commits": [sha...]}`; raises `StepError(code=EXIT_COMMIT)` when a git step fails after edits exist.

Message grammar (spec 7.4 as amended; one commit in phase 1, so the human section ends this message):

```
docs(drift): provable fixes

Drift-Run: <run-id>
Drift-Base: <starting HEAD sha, 40 chars>
Drift-Scope: all | base:<ref>

- <doc>:<line> replace `<old>` -> `<new>` (<reason>)
- <doc>:<line> delete `<token>` (<reason>)
- <doc>:<line> unlink `<target>` (<reason>)

Needs a human decision:
- <doc>:<line> [<kind>] <statement>
  evidence: <evidence>
```

`<reason>` is `renamed in <sha7>`, `deleted in <sha7>`, `removed in <sha7>`, `heading renamed in <sha7>`, `heading removed in <sha7>` or `manifest <file> says <value>`. Statements per kind: `ambiguous-rename` "`<token>` was renamed to one of <n> paths: <a>, <b>"; `large-deletion` "`<token>` no longer exists and removing it would remove a whole <block kind>"; `prose-mention` "`<token>` no longer exists and is mentioned in running prose"; `never-edit-section` "`<token>` no longer exists, in a section headed '<heading>'"; `generated-region` "`<token>` no longer exists inside a generated region; regenerate it"; `recheck-failed` "the proposed edit for `<token>` did not pass the re-check (<reason>)". The human section is omitted when empty; the body bullets are ordered by doc then line; trailers from config follow after one blank line. Run id: first 12 hex characters of `sha256(f"{head}:{scope}:{date}")`.

- [ ] **Step 1: Write the failing tests**

Preflight: `test_refuses_dirty_tree`, `test_refuses_detached_head`, `test_refuses_existing_branch` (message names `--branch`), `test_refuses_missing_identity` (run with `GIT_CONFIG_GLOBAL` pointing at an empty file and no repo-local identity), `test_check_mode_allows_dirty_tree`, `test_workdir_added_to_info_exclude_once`.
Commit: `test_render_message_exact_grammar` (golden string built from three findings, one per verb, and two human findings), `test_human_section_omitted_when_empty`, `test_message_is_redacted` (a token text containing `ghp_` plus 36 characters comes out cut), `test_commit_creates_branch_from_start_and_stages_only_edited_docs` (an untracked file in the working tree stays untracked; `git show --stat` lists only the edited docs), `test_no_hunks_no_branch` (`commits.json` has `branch: null`).

- [ ] **Step 2: Run to verify failure, implement, verify, commit**

Run: `pytest skills/document-drift/tests/test_dd_preflight.py skills/document-drift/tests/test_dd_commit.py -v` (FAIL), implement, `pytest skills/document-drift/tests -v && mypy` (PASS). The commit uses `git switch -c <branch>`, `git add -- <doc>...`, `git commit -F <workdir>/commit-msg.txt`.

```bash
git add skills/document-drift/scripts/dd_preflight.py skills/document-drift/scripts/dd_commit.py skills/document-drift/tests/test_dd_preflight.py skills/document-drift/tests/test_dd_commit.py
git commit -m "feat(document-drift): preflight refusals and the commit grammar"
```

---

### Task 10: Summary and the chain runner

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/scripts/dd_summary.py`, `skills/document-drift/scripts/dd_run.py`
- Test: `skills/document-drift/tests/test_dd_summary.py`, `test_dd_run.py`

**Interfaces:**
- Consumes: every earlier `run`.
- Produces:
  - `dd_summary.run(workdir: Path) -> str` writing `summary.md`: run id; scope; docs scanned; docs excluded and skipped by reason (counts plus paths); tokens per kind and resolved count; candidates per class; hunks applied and reverted; the human section from `render_human`; markers without reasons; markers whose covered block produced no candidate (stale); `history unavailable` line when set; config warnings; branch and commit shas, or `No branch created.`
  - `dd_run.main(argv: list[str] | None = None) -> int`: `<repo> [--base REF] [--branch NAME] [--workdir DIR] [--date YYYY-MM-DD] [--check]`. Default workdir `<repo>/.document-drift`, default date today, default branch from config `branch` with `{date}`. Order: preflight, inventory, extract, resolve, fixes, then (not `--check`) apply and commit, then summary printed to stdout. After each step the pinned outputs are checked: `preflight.json`, `inventory.json`, `tokens.json`, `candidates.json`, `findings.json` and `hunks-provable.json`, `applied.json`, `commits.json`, `summary.md`; a missing one exits 5 naming the file. `StepError` exits with its code and message on stderr. `--check` exits 1 when `hunks-provable.json` has any hunk, else 0.
  - `--base <ref>`: inventory keeps only docs that changed in `git diff --name-only <ref>...HEAD` or whose `path` tokens resolve, at HEAD or at their snapshot, to a changed path or a directory containing one; the filter is applied after resolve and recorded in `inventory.json` as `scope_dropped`.

- [ ] **Step 1: Write the failing tests**

`test_run_end_to_end_small_repo` (one renamed file in a README list item: exit 0, branch `docs/drift-2026-01-02` with `--date 2026-01-02`, one commit whose message matches the grammar, the doc edited), `test_check_mode_exits_1_and_edits_nothing`, `test_missing_output_exits_5` (monkeypatch `dd_fixes.run` to skip writing: exit 5 and the filename on stderr), `test_refusal_exit_2_message`, `test_base_scope_drops_unrelated_docs`, `test_summary_lists_human_findings_and_stale_markers`, `test_second_run_on_drift_branch_makes_no_commit` (run once, then run again with `--branch docs/drift-again`: `commits.json` branch null).

- [ ] **Step 2: Run to verify failure, implement, verify, commit**

Run: `pytest skills/document-drift/tests/test_dd_run.py skills/document-drift/tests/test_dd_summary.py -v` (FAIL), implement, `pytest skills/document-drift/tests -v && mypy` (PASS).

```bash
git add skills/document-drift/scripts/dd_summary.py skills/document-drift/scripts/dd_run.py skills/document-drift/tests/test_dd_summary.py skills/document-drift/tests/test_dd_run.py
git commit -m "feat(document-drift): summary and the chain runner with check and base modes"
```

---

### Task 11: Fixture corpus, goldens and the end-to-end test

**Confidence:** 90%

**Files:**
- Create: `skills/document-drift/tests/fixtures/corpus/{py-service,ts-web,go-cli}/{files/,history.yaml,planted.json}`, `skills/document-drift/tests/golden/<fixture>/{tokens.json,candidates.json,findings.json,hunks-provable.json,commit-msg.txt,docs/<edited doc paths>}`, `skills/document-drift/tests/test_dd_corpus.py`, `skills/document-drift/tests/test_dd_goldens.py`

**Interfaces:**
- Consumes: `dd_make_history.replay_fixture`, `dd_run.main`.
- `planted.json` = `{"planted": [{"id", "doc", "line", "kind", "expect"}], "decoys": [{"id", "doc", "line", "why", "expect"}]}`; `expect` is `replace:<new text>`, `delete`, `unlink`, `human:<kind>`, or `none` (no candidate, or `summary-only`).

Corpus content. Each fixture's history has at least five commits with fixed dates in 2024 and 2025 so renames and deletions happen after the doc lines that name them. Spread so that every token kind has a positive case in at least two fixtures:

| Planted (expect) | py-service | ts-web | go-cli |
|---|---|---|---|
| File renamed, list-item subject (`replace`) | yes | yes | |
| File renamed, named in `CLAUDE.md` (`replace`) | | | yes |
| Directory renamed (`replace`) | | yes | yes |
| File deleted, list-item subject (`delete`) | yes | | yes |
| File deleted, prose link (`unlink`) | yes | yes | |
| File deleted, inline prose mention (`human:prose-mention`) | yes | | yes |
| Only item in its list deleted (`human:large-deletion`) | | yes | |
| Heading renamed, anchor link (`replace`) | yes | | yes |
| Make target removed, bash fence line (`delete`) | yes | | yes |
| npm script removed, bash fence line (`delete`) | | yes | |
| Runtime floor behind manifest (`replace`) | yes (Python) | yes (Node) | yes (Go) |
| Tree entry renamed (`replace`) and tree leaf deleted (`delete`) | yes | yes | |

Decoys, each `expect: none` unless stated: the deliberate removal sentence committed in the deleting commit (all three); an illustrative never-existed path; a "create `out/`" path; a runtime artefact (`state.json`); a URL route `/health` and a slash command; a ratio `3/5`; a `CHANGELOG.md` entry naming a deleted file; a `docs/superpowers/plans/` doc naming a deleted file; a vendored `third_party/lib/README.md` naming a missing file; a deleted file under a `## Rationale` heading (`human:never-edit-section`); a deleted file inside an embedme generated region (`human:generated-region`); a deleted file under `drift-ignore` with a reason; a `templates/README.md` naming a missing file.

- [ ] **Step 1: Write the tests**

```python
# test_dd_corpus.py
@pytest.mark.parametrize("fixture", ["py-service", "ts-web", "go-cli"])
def test_replay_tree_equals_files_dir(fixture, tmp_path): ...

@pytest.mark.parametrize("fixture", ["py-service", "ts-web", "go-cli"])
def test_every_planted_item_and_decoy_meets_expectation(fixture, tmp_path):
    repo = replay_fixture(fixture, tmp_path / fixture)
    assert dd_run.main([str(repo), "--check", "--workdir", str(tmp_path / "wd")]) in (0, 1)
    findings = read_json(tmp_path / "wd" / "findings.json")["findings"]
    hunks = read_json(tmp_path / "wd" / "hunks-provable.json")["hunks"]
    for item in planted["planted"] + planted["decoys"]:
        assert outcome_for(item, findings, hunks) == item["expect"], item["id"]

def test_no_decoy_produces_an_edit(): ...           # across all fixtures
def test_every_token_kind_positive_in_two_fixtures(): ...

# test_dd_goldens.py
@pytest.mark.parametrize("fixture", ["py-service", "ts-web", "go-cli"])
def test_outputs_match_goldens(fixture, tmp_path):
    # full run with --date 2026-01-02 and --branch docs/drift-golden; compare the four JSON
    # outputs, the commit message (git log -1 --format=%B) and every edited doc byte for byte;
    # UPDATE_GOLDENS=1 rewrites the golden directory instead of comparing.
```

- [ ] **Step 2: Author the fixtures and run**

Run: `pytest skills/document-drift/tests/test_dd_corpus.py -v`
Expected: PASS once the fixtures are authored and the pipeline meets every expectation. A failing expectation is a pipeline bug or a fixture bug; fix the right one and say which in the commit body.

- [ ] **Step 3: Generate goldens and inspect them**

Run: `UPDATE_GOLDENS=1 pytest skills/document-drift/tests/test_dd_goldens.py -v` then `pytest skills/document-drift/tests/test_dd_goldens.py -v`
Expected: PASS. Read every `commit-msg.txt` and edited doc in the golden tree before committing; a golden is a reviewed artefact, not a recording.

- [ ] **Step 4: Commit**

```bash
git add skills/document-drift/tests
git commit -m "test(document-drift): three-language fixture corpus, goldens and end-to-end checks"
```

---

### Task 12: SKILL.md, documentation, self-scan and spec amendments

**Confidence:** 90%. The self-scan may surface real drift in this repository's docs; fixing it is part of this task and the right outcome (spec guardrail 0(c)).

**Files:**
- Modify: `skills/document-drift/SKILL.md`, `README.md` (new section "Also in this repo: document-drift" after the karate-bootstrap section: what it does, install symlink lines, the one command, phase 1 scope), `docs/architecture.md` (new section "document-drift": pipeline table, token kinds, classes, deletion-unit rules, commit grammar, exclusions; link the spec), `.github/workflows/test.yml` (add `- run: python skills/document-drift/scripts/dd_run.py . --check`), `docs/superpowers/specs/2026-10-09-document-drift-design.md` (the seven amendments at the top of this plan, each in the section it changes, plus a dated "Amendments in phase 1" list at the end of section 10)
- Test: `dd_check_skill.py` (CI) and the self-scan

**SKILL.md content:** frontmatter (`name: document-drift`; description: "Find markdown documentation that names files, anchors, scripts, runtime versions or directory entries that no longer exist, fix the provable ones and leave a commit on a new branch for review. Use when asked to check docs for drift, fix stale READMEs, or update docs after a refactor."; triggers `/document-drift`); when to use; the command `python scripts/dd_run.py <repo> [--base <ref>] [--branch <name>]` run from `skills/document-drift/`; what it never does (push, open PRs, execute project code, edit excluded files); the exit codes and what to tell the user for each; the no-improvisation rule (exit 5 means stop and report, do not hand-edit docs); that the final message to the user is the printed summary plus the branch name.

- [ ] **Step 1: Run the self-scan and fix what it finds**

Run: `python skills/document-drift/scripts/dd_run.py . --check --workdir "$TEMP/dd-self"`
Expected: exit 0. If exit 1, read `$TEMP/dd-self/summary.md`, fix each real drift in this repository's docs by hand (or fix the pipeline when the finding is wrong), and re-run until exit 0. Record any pipeline fix with a test in the owning task's test file.

- [ ] **Step 2: Write SKILL.md, README and architecture sections; apply the spec amendments**

- [ ] **Step 3: Verify the whole suite**

Run: `ruff check . && mypy && python skills/tech-debt-scan/scripts/skill_check.py && python skills/karate-bootstrap/scripts/kb_check_skill.py && python skills/document-drift/scripts/dd_check_skill.py && pytest -v`
Expected: all pass, no regressions in the other skills.

- [ ] **Step 4: Live check on two owner repositories**

Run, against throwaway clones so the owner's checkouts are untouched: `git clone ~/sources/ralph "$TEMP/dd-live/ralph" && python skills/document-drift/scripts/dd_run.py "$TEMP/dd-live/ralph" --date <today>`, and the same for `better-memory`.
Expected: exit 0. Read every edit in the resulting commit and every human finding; write the counts (docs scanned, candidates per class, edits, edits judged correct) as a new row in `docs/evaluation-log.md` under a "document-drift" heading. A wrong provable edit is a defect: add a decoy reproducing it to the corpus, fix, re-run.

- [ ] **Step 5: Memory sweep, commit and open the PR**

Record non-obvious facts from the phase's commits and reviews in better-memory (per CLAUDE.md), then:

```bash
git add skills/document-drift/SKILL.md README.md docs/architecture.md docs/evaluation-log.md .github/workflows/test.yml docs/superpowers/specs/2026-10-09-document-drift-design.md
git commit -m "docs(document-drift): SKILL.md, README and architecture sections, self-scan in CI, spec amendments"
```

Then follow `superpowers:finishing-a-development-branch`.
