# document-drift Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the history-gated phase 1 pipeline with the docs-as-baseline design: a staged driver that anchors every doc reference to a code definition, reviews docs against the code with agents (all docs on a first run, only what changed on later runs), documents missing user-facing names, runs the notice loop for blocks nothing can be tied to, and commits the accepted edits on a new branch.

**Architecture:** Scripts do everything deterministic (inventory, definition index, anchors, change set, units, pattern scan, gaps, notice loop, checks, apply, commits, summary) and write pinned JSON files in the workdir. The session runs `dd_run.py --stage start|verify|finish` and, between stages, dispatches read-only Agents from plan files; each Agent reads one prompt file and writes one output file. Phase 1's markdown scanner, extractor, path resolver, apply core, preflight, redaction and SKILL linter are kept; the two-snapshot gate and provable fix classes go.

**Tech Stack:** Python 3.11+, standard library plus `pyyaml`; `ast` for Python definitions; git plumbing through `dd_common.run_git`; pytest, ruff, mypy strict; canned JSON agent outputs in tests.

**Spec:** `docs/superpowers/specs/2026-10-10-document-drift-agentic-design.md` (sections cited as "spec N").

## Global Constraints

- Every module is `dd_`-prefixed under `skills/document-drift/scripts/`, direct-path invocable as `python scripts/<name>.py`, with a `main(argv)` and a `run(...)`; every test file is `tests/test_dd_*.py`. Only `pyyaml` beyond the standard library. `ruff check .` and `mypy` (strict, scripts only) stay clean after every task.
- Large data moves as file paths, never on argv. Every output file is written with `dd_common.write_json` (indent 1, sorted keys, LF) or as UTF-8 with LF. Every repository-derived string that reaches a commit message or the summary passes through `dd_redaction.redact`.
- No test calls a model. Agent outputs are canned JSON files. No script, constant or test depends on the identity of a fixture or a real repository (spec 0d).
- Constants, copied from spec 10: `unit_lines` 6000, `max_delete_lines` 15, `max_section_lines` 40, `min_anchor_ratio` 0.25, caps review 40, gaps 15, verify 25, verifier batch size 10, models review `sonnet`, gap `sonnet`, verify `opus`. Signature-range threshold 60 lines; literal enclosing-node cap 15 lines; ambiguity limits 10 (specific) and 3 (bare); list threshold 3 subjects; complete-intended at half (spec 5, 8).
- Commit grammar is spec 9.4 verbatim; exit codes are spec 2 verbatim. `README.md`, `docs/architecture.md` and `skills/document-drift/SKILL.md` change in the same PR as the code (spec 0c).
- Branch: all work on `feat/document-drift-agentic` (already exists, holds the spec). Commit after every task with a `feat(document-drift):`, `test(document-drift):` or `docs(document-drift):` subject.
- Every task carries a confidence figure (spec 0b). A task under 90% names the investigation that raises it; that investigation is the task's first step.

## Review Focus

1. **A doc with CRLF line endings.** Edits must apply (apply keeps each line's own ending) and the block hash must not depend on the ending. Test in Task 13 (`test_apply_edits_keeps_crlf`) and Task 10 (`test_block_hash_ignores_line_endings`).
2. **An agent output whose `old` text is right but whose line numbers are off by one.** `old-mismatch` must drop it rather than apply it at the wrong lines; the whitespace repair must not mask it. Test in Task 12 (`test_old_mismatch_is_not_repaired_when_lines_differ`).
3. **A later run whose last-run commit is on another branch (not an ancestor of HEAD).** It must be ignored and the run falls back to the next record or a first run. Test in Task 6 (`test_last_run_ignores_non_ancestor`).
4. **A repository where a basename is shared by several files, or a definition name is defined in many places.** Resolution must stay unanchored (ambiguous) rather than pick one. Tests in Task 4 (`test_specific_over_ten_definitions_is_ambiguous`, `test_bare_without_context_is_unanchored`).
5. **A notice whose block is the last block of the doc, or whose run id is newer than the current run.** The remove edit must not run past the end of the doc, and the newer notice must be left alone as stale. Tests in Task 10 (`test_remove_edit_at_end_of_doc`, `test_future_notice_is_stale`).

---

## Shared contracts

These names are used by several tasks. A task's Interfaces block refers to them rather than restating them.

**Workdir files** (default `<repo>/.document-drift`, in `.git/info/exclude`):

| Stage | File | Written by |
|---|---|---|
| start | `preflight.json` | `dd_preflight` plus the run fields `run_id`, `date`, `check`, `branch`, `base`, `full`, `stage` |
| start | `inventory.json` | `dd_inventory` (phase 1 keys plus `sources`, `project_files`) |
| start | `tokens.json` | `dd_extract` (unchanged) |
| start | `defindex.json` | `dd_defindex` |
| start | `anchors.json` | `dd_anchors` |
| start | `changes.json` | `dd_changes` |
| start | `units.json` | `dd_units` |
| start | `patterns.json` | `dd_patterns` |
| start | `gaps.json` | `dd_gaps` |
| start | `notices.json` | `dd_unverified` (decisions on existing notices); extended at `verify` with nominations |
| start | `plan-docs.json`, `prompts/review-uNNN.md`, `prompts/gap-gNNN.md` | `dd_dispatch` |
| agents | `review/uNNN.json`, `gaps/gNNN.json` | review and gap agents |
| verify | `retry.json` (when needed), `edits.json`, `plan-verify.json`, `prompts/verify-vNN.md` | `dd_dispatch`, `dd_checks` |
| agents | `verdicts/vNN.json` | verifier agents |
| finish | `verdicts.json`, `applied.json`, `commits.json`, `commit-msg-corrections.txt`, `commit-msg-additions.txt`, `summary.md`, `last-run.json` | `dd_dispatch`, `dd_apply`, `dd_commit`, `dd_summary`, `dd_run` |

**Run id:** `f"{date}-{sha256(f'{head}:{scope}:{date}').hexdigest()[:4]}"`, for example `2026-10-12-a3f1` (spec 7.3 example shape). `scope` is `first`, `since <sha>`, `base <ref>` or `full`.

**Edit record** (one shape for every edit, agent-written or script-written):

```json
{"id": "u007-e01", "doc": "docs/x.md", "start_line": 54, "end_line": 54,
 "old": "exact text of those lines", "new": "replacement or empty",
 "type": "correct", "claim": "one line", "evidence": ["path:line"], "subject": null}
```

`type` is one of `correct`, `remove`, `anchor` (review agents), `add` (gap agents), `notice`, `escalate`, `clear`, `unverified` (notice loop, script-written, ids `n001`, `n002`, ... in doc then line order). `dd_checks` adds `source` (`review`, `gap`, `notice`), `status` (`kept`, `dropped`, `human`), `check` (the failing check or null), `human_kind` and `reason`.

**Definition record:** `{"name", "norm", "file", "start", "end", "kind", "owners": [norm...], "change_ranges": [[s, e], ...], "reading": [s, e]}`; `kind` in `module`, `function`, `class`, `sql`, `file` (rank 0), `reg`, `sqlcol` (rank 1), `literal` (rank 2).

**Reference record:** `{"doc", "line", "text", "norm", "specific": bool, "block": [s, e], "heading": str|null, "context": [norm...]}` where `context` is the specific norms in the same block plus those in the nearest heading.

**Anchor record:** `{"doc", "line", "ref", "file", "start", "end", "kind", "change_ranges", "reading"}`.

**Hunk record** (from `git diff -U0`): `{"file", "old_start", "old_end", "new_start", "new_end", "text"}`; a pure deletion has `new_end = new_start - 1` and counts as touching `new_start` (spec 6.3).

**Notice line grammar** (spec 7.3), matched by `^<!-- drift-unverified: (1st|2nd) notice, run (\S+), block ([0-9a-f]{8})\. .* -->$` on its own line, directly above the block:

```
<!-- drift-unverified: 1st notice, run {run_id}, block {hash}. This describes the code but names nothing in it. Name what it describes, or add drift-ignore: <reason>. -->
<!-- drift-unverified: 2nd notice, run {run_id}, block {hash}. NEEDS A HUMAN DECISION: name what this describes, add drift-ignore: <reason>, or rewrite it. The next drift run removes this block otherwise. -->
```

**Block hash:** `sha256(" ".join(block_text.split())).hexdigest()[:8]`.

**Human-decision entry:** `{"doc", "line", "kind", "text", "evidence"}`; `kind` in `guarantee-mismatch`, `unsure`, `unverified`, `large-deletion`, `large-section`, `protected`, `overlap`, `no-home`, `target-refused`, `verify-rejected`, `recheck-failed`.

**Plan entry:** `{"id", "role": "review"|"gap"|"verify", "prompt": abs path, "output": abs path, "model"}`.

**Name normalisation** (`dd_defindex.norm`): strip a leading `mcp__<server>__`; a name starting with `--` keeps its dashes and is otherwise unchanged; every other name has `-` and `.` replaced by `_`. Route placeholders `<x>`, `{x}`, `:x` become `{}` (used by `dd_gaps` only).

---

### Task 1: Configuration keys

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_config.py`
- Test: `skills/document-drift/tests/test_dd_config.py`

**Interfaces:**
- Produces: `load_config(root) -> (config, warnings)` with the new keys `unit_lines`, `max_delete_lines`, `max_section_lines`, `min_anchor_ratio`, `undocumented_ok`, `caps` (`review`, `gaps`, `verify`), `models` (`review`, `gap`, `verify`), defaults as in Global Constraints. `lead_cap` and `recent_change_days` stay until Task 16 removes them with `dd_fixes`.

- [ ] **Step 1: Write the failing tests** in `test_dd_config.py`: `test_defaults_include_agentic_keys` (every new key with its default), `test_caps_and_models_are_validated_per_subkey` (a `caps: {review: "x"}` warns and keeps the default for `review` only; `models: {verify: 3}` likewise), `test_min_anchor_ratio_must_be_between_0_and_1`, `test_undocumented_ok_must_be_string_list`.
- [ ] **Step 2: Run them**: `pytest skills/document-drift/tests/test_dd_config.py -v`. Expected: FAIL on missing keys.
- [ ] **Step 3: Implement** the keys in `DEFAULTS` and `_VALIDATORS`; nested mappings are validated per sub-key (unknown sub-keys warn; a wrong value warns and keeps that sub-key's default).
- [ ] **Step 4: Run the tests**. Expected: PASS. Also `ruff check . && mypy`.
- [ ] **Step 5: Commit** `feat(document-drift): agentic config keys`.

---

### Task 2: Inventory source classes and project files

**Confidence:** 92%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_inventory.py` (around `_classify`, `run`)
- Test: `skills/document-drift/tests/test_dd_inventory.py`

**Interfaces:**
- Consumes: `_classify(rel)` and `PATH_CLASS_GLOBS` already in the module.
- Produces: `inventory.json` gains `"sources": {"source": [...], "test": [...], "config": [...], "generated": [...], "vendored": [...], "doc": [...], "other": [...]}` (every tracked file in exactly one class, sorted) and `"project_files": [...]` (the spec 4 list, those tracked). New function `indexed_files(inventory: dict) -> list[str]` returning `sources["source"] + project_files`, sorted, used by Tasks 3 and 8.

- [ ] **Step 1: Write the failing tests**: `test_sources_partition_every_tracked_file` (union equals `files`, classes disjoint), `test_project_files_lists_only_tracked_spec_names` (a `Dockerfile.dev`, `.github/workflows/ci.yml`, `package.json` listed; an untracked `justfile` not), `test_indexed_files_is_source_plus_project_files`, `test_markdown_is_doc_class_not_source`.
- [ ] **Step 2: Run**: `pytest skills/document-drift/tests/test_dd_inventory.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** A file is `doc` when it ends with `.md` (any case); else `_classify` decides; `None` becomes `other`. Project files match by basename or the `.github/workflows/` prefix.
- [ ] **Step 4: Run the tests and the full suite** (`pytest skills/document-drift -q`). Expected: PASS; goldens unaffected because `inventory.json` is not a golden.
- [ ] **Step 5: Commit** `feat(document-drift): classify sources and project files in the inventory`.

---

### Task 3: Definition index

**Confidence:** 85%. The uncertain part is JavaScript/TypeScript ranges by brace matching. Raise it first: Step 1 runs the matcher on `tests/fixtures/corpus/ts-web/files/src/**` and checks by hand that every `function`, `class`, `export const` and method gets a range ending at its closing brace, including arrow functions and template literals containing braces. Record the result in the task report.

**Files:**
- Create: `skills/document-drift/scripts/dd_defindex.py`
- Test: `skills/document-drift/tests/test_dd_defindex.py`

**Interfaces:**
- Consumes: `dd_inventory.indexed_files`, `dd_history.History.show`, `dd_common.run_git`.
- Produces:
  - `norm(name: str) -> str` (Shared contracts), `is_specific(text: str) -> bool` (spec 5.2: contains `.`, `/` or `_`, starts with `--`, mixes case, or is `^[A-Z][A-Z0-9_]{3,}$`), `RANK: dict[str, int]`.
  - `build(files: list[str], read: Callable[[str], str | None], unique_basenames: set[str]) -> list[Definition]`.
  - `run(root: Path, workdir: Path) -> dict` writing `defindex.json` as `{"definitions": [...]}` for `indexed_files` at HEAD plus `file` definitions for every tracked non-test file with a unique basename.
  - `at_commit(root: Path, sha: str, files: list[str]) -> list[Definition]` (same builder, reading through `History.show`).
  - `by_norm(definitions) -> dict[str, list[Definition]]`.
  - `signature_ranges(node) -> tuple[list[tuple[int, int]], tuple[int, int]]` for Python: for a function or class of more than 60 lines, `change_ranges` is `[(start, docstring_end)]` plus, for a class, `(m.lineno, m.lineno)` per method; `reading` is `(start, docstring_end)`; otherwise both are the full range.

- [ ] **Step 1: JS/TS spike** as described in Confidence; keep nothing but the finding.
- [ ] **Step 2: Write the failing tests**: `test_python_function_and_class_ranges` (exact `lineno`/`end_lineno`), `test_module_indexed_by_dotted_path_and_last_segment` (`svc.storage` and `storage`; `__init__` dropped), `test_literal_registration_kinds` (`Tool(name="store.put")` is `reg` with owner; `add_argument("--port")` is `reg`; a plain string in a dict is `literal`), `test_literal_range_is_smallest_node_within_15_lines`, `test_owners_include_enclosing_defs_and_registration_name`, `test_large_class_signature_ranges` (a 70-line class: change ranges are the header plus each method line; reading is the header), `test_sql_objects_and_columns`, `test_ts_function_class_export_const_and_method_ranges`, `test_unique_basename_file_definitions` (shared basenames excluded), `test_norm_and_is_specific` (table of cases from spec 5.2, including `mcp__better-memory__memory_retrieve` and `--force`), `test_at_commit_reads_old_content` (a repo where the function moved between commits).
- [ ] **Step 3: Run**: `pytest skills/document-drift/tests/test_dd_defindex.py -v`. Expected: FAIL with import error.
- [ ] **Step 4: Implement** `dd_defindex.py`. Python through `ast` with a parent map; `ast.get_docstring` end line via the first body statement's `end_lineno` when it is a string constant, else the definition line. SQL and JS/TS by regexes over lines; JS/TS ranges by counting braces outside strings, template literals and comments. Syntax errors skip the file (counted in `defindex.json` under `"skipped"`).
- [ ] **Step 5: Run the tests**. Expected: PASS.
- [ ] **Step 6: Commit** `feat(document-drift): definition index`.

---

### Task 4: References, anchors and checkability

**Confidence:** 90%.

**Files:**
- Create: `skills/document-drift/scripts/dd_anchors.py`
- Test: `skills/document-drift/tests/test_dd_anchors.py`

**Interfaces:**
- Consumes: `dd_md_scan.scan` (blocks and `code` inlines), `dd_defindex.norm`, `is_specific`, `by_norm`, `RANK`; `dd_resolve.path_matches`; `dd_history.History.head_files`.
- Produces:
  - `references(doc: str, text: str) -> list[Reference]`: every `code` inline outside fences whose first token matches `^[A-Za-z_][\w.\-]{2,}$|^--[\w-]+$` or contains `/`, plus every `<code>…</code>` span found by regex on non-fence lines; `block` is the scanner block's line range; `heading` the nearest heading text above; `context` per Shared contracts.
  - `resolve(refs, defs: dict[str, list[Definition]], files: frozenset[str], dirs: frozenset[str]) -> tuple[list[Anchor], list[dict]]` applying spec 5.3: an existing path resolves without an anchor (counted as `path`); a specific reference takes the best-rank definitions, over 10 is `ambiguous`; a bare reference takes definitions whose owners intersect `context`, none or over 3 is `ambiguous`; no definition is `unknown`. A dotted name falls back to its last segment.
  - `checkability(docs: list[str], texts, refs, anchors, config) -> dict[doc, {...}]` with `status` `unverifiable` (no anchor), `weak` (rate under `min_anchor_ratio` or fewer than 3 anchors), else `ok`; `blocks` and `blocks_noref` count paragraphs, list items and table rows outside fences.
  - `run(root: Path, workdir: Path, config: dict) -> dict` writing `anchors.json` (`references`, `anchors`, `unanchored`, `checkability`, `counts`).
  - `anchors_for(doc) ` helpers are the caller's job; the file is the contract.

- [ ] **Step 1: Write the failing tests**: `test_references_from_code_spans_and_html_code_tags`, `test_references_skip_fences_and_short_words`, `test_specific_resolves_to_best_rank` (a `reg` and a `literal` of the same name: only the `reg`), `test_specific_over_ten_definitions_is_ambiguous`, `test_bare_resolves_through_block_context` (`query` in a table under `## memory.retrieve` resolves to that tool's `query` owner), `test_bare_without_context_is_unanchored`, `test_unknown_name_is_unanchored_unknown`, `test_existing_path_is_not_an_anchor`, `test_checkability_statuses` (three docs: none, 2 anchors, 10 of 12), `test_run_writes_counts_by_reason`.
- [ ] **Step 2: Run**: `pytest skills/document-drift/tests/test_dd_anchors.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `dd_anchors.py`.
- [ ] **Step 4: Run the tests**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): references, anchors and checkability`.

---

### Task 5: History helpers for later runs

**Confidence:** 92%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_history.py` (add only; removals are Task 16)
- Test: `skills/document-drift/tests/test_dd_history.py`

**Interfaces:**
- Produces: `drift_base_commits(root) -> list[tuple[str, str]]` (commit sha, `Drift-Base` sha) newest first from `git log --format=%H%x00%B --grep=^Drift-Base:` over `HEAD`; `is_ancestor(root, a, b) -> bool` (`git merge-base --is-ancestor a b`); `changed_files(root, sha) -> list[str]` (`git diff --name-only --no-renames sha HEAD`); `diff_hunks(root, sha, files) -> dict[str, list[Hunk]]` from `git diff -U0 sha HEAD -- files` parsed per Shared contracts.

- [ ] **Step 1: Write the failing tests**: `test_drift_base_commits_newest_first`, `test_drift_base_found_in_squash_message` (a commit whose body embeds a drift message), `test_is_ancestor`, `test_diff_hunks_ranges_and_pure_deletion` (a hunk `@@ -5,2 +5,0 @@` gives `new_start 5`, `new_end 4`), `test_diff_hunks_only_requested_files`.
- [ ] **Step 2: Run**: `pytest skills/document-drift/tests/test_dd_history.py -v -k "drift_base or ancestor or diff_hunks"`. Expected: FAIL.
- [ ] **Step 3: Implement** with `run_git`, `-c core.quotePath=false`, `--literal-pathspecs`.
- [ ] **Step 4: Run the tests**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): last-run commits and diff hunks`.

---

### Task 6: Run mode, change set and affected docs

**Confidence:** 90%.

**Files:**
- Create: `skills/document-drift/scripts/dd_changes.py`
- Test: `skills/document-drift/tests/test_dd_changes.py`

**Interfaces:**
- Consumes: Task 5 functions; `dd_defindex.at_commit`, `by_norm`; `dd_anchors.resolve`, `references`; `anchors.json`, `defindex.json`, `inventory.json`; `<workdir>/last-run.json` (`{"head", "run_id", "date", "committed"}`).
- Produces:
  - `last_run(root, workdir, base: str | None, full: bool) -> dict`: `{"mode": "first"|"later", "sha": str|None, "source": "commit"|"record"|"base"|None, "scope": str}` per spec 6.1 (both records must be ancestors of HEAD; when both qualify the descendant wins; `--base` wins over both; `--full` forces `first`).
  - `affected(anchors, refs, defs_then: dict, hunks, changed_docs: set[str], texts) -> dict[doc, {"anchor_reasons": [...], "missing": [...], "doc_changed": bool, "sections": [[s, e]...]}]`: a doc is affected by an anchor whose any change range overlaps a hunk of its file (pure deletions touch `new_start`), by a reference that resolved at the last-run commit (against `defs_then`) and does not now, or because the doc changed (its changed sections by heading from `git diff -U0` on the doc).
  - `review_ranges(doc, affected_entry, refs) -> list[[s, e]]`: on a later run the blocks of the affected references plus the changed sections, merged; on a first run the whole doc.
  - `run(root, workdir, config, base, full) -> dict` writing `changes.json` (Shared contracts) with `review` as `{doc: ranges}` for every doc on a first run and affected docs on a later run.

- [ ] **Step 1: Write the failing tests** (small repos built with `dd_helpers.make_repo`): `test_first_run_when_no_record`, `test_later_run_from_drift_base_commit`, `test_later_run_from_local_record_when_newer`, `test_last_run_ignores_non_ancestor` (record head on another branch), `test_base_overrides_records`, `test_full_forces_first`, `test_affected_by_change_range_overlap`, `test_not_affected_by_change_inside_large_class_body`, `test_affected_by_reference_that_no_longer_resolves` (renamed function), `test_affected_by_doc_change_gives_changed_sections`, `test_untouched_doc_is_not_affected`, `test_review_ranges_merge_blocks_and_sections`.
- [ ] **Step 2: Run**: `pytest skills/document-drift/tests/test_dd_changes.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `dd_changes.py`.
- [ ] **Step 4: Run the tests**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): run modes and affected docs`.

---

### Task 7: Review units

**Confidence:** 92%.

**Files:**
- Create: `skills/document-drift/scripts/dd_units.py`
- Test: `skills/document-drift/tests/test_dd_units.py`

**Interfaces:**
- Consumes: `changes.json` (`review`, `hunks`, `mode`), `anchors.json`, doc texts, `config["unit_lines"]`, `config["caps"]["review"]`.
- Produces: `build(review: dict[str, list], anchors, hunks, mode, texts, unit_lines) -> list[Unit]` with `Unit = {"id", "docs": [{"doc", "ranges"}], "anchors": [Anchor], "hunks": [Hunk], "size"}`; docs linked by a shared anchored definition (`file:start`), packed in path order within `unit_lines` where size is the reviewed doc lines plus, on a first run, the anchors' reading-range lines (each definition counted once per unit), or, on a later run, the hunk lines plus the reading ranges of missing definitions; a doc over budget alone is split at `##` headings into several units. Ids `u001`... in path order of the first doc. `order_for_cap(units) -> list[Unit]`: README/CLAUDE/AGENTS units first, then by anchor count descending, then id; units beyond `caps.review` go to `"unchecked"`. `run(workdir, config) -> dict` writes `units.json`.

- [ ] **Step 1: Write the failing tests**: `test_docs_sharing_a_definition_are_linked`, `test_packing_respects_unit_lines`, `test_large_doc_split_at_second_level_headings`, `test_first_run_size_counts_reading_ranges_once`, `test_later_run_size_counts_hunks`, `test_cap_order_puts_readme_first`, `test_ids_follow_path_order`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): review units`.

---

### Task 8: Pattern scan

**Confidence:** 85%. The uncertain part is the argparse flag parent through `ast` assignments (`sub = parsers.add_parser("init"); sub.add_argument("--force")`, including parsers passed into helper functions). Raise it first: Step 1 writes the resolver as a pure function over an `ast.Module` and exercises it on three shapes (direct chain, assignment then call, parser passed to a `_add_init_flags(p)` helper where the parent is the call site's parser); the third may legitimately give `parent: null`, which the task report records.

**Files:**
- Create: `skills/document-drift/scripts/dd_patterns.py`
- Modify: `skills/document-drift/scripts/dd_manifests.py` (expose entry points and scripts of project files)
- Test: `skills/document-drift/tests/test_dd_patterns.py`

**Interfaces:**
- Consumes: `dd_inventory.indexed_files`, `dd_history.History.show`, `dd_manifests` (`_make_targets`, `_script_names`, extended with `entry_points(path, text) -> list[str]` for `pyproject.toml` scripts and entry points and `package.json` `scripts`/`bin`).
- Produces: `scan(files: list[str], read: Reader) -> list[Name]` with `Name = {"name", "kind", "file", "line", "parent", "hidden"}`, `kind` in `command`, `flag`, `env`, `route`, `tool`, `param`, `script`, `target`; the patterns of spec 8.1 (Python by `ast`, JS/TS and project files by regex, all matching across line breaks), env-prefix families, hidden detection (`argparse.SUPPRESS`, `hidden=True`, leading underscore, a deprecation word within three lines). `run(root, workdir, last_run_sha: str | None) -> dict` writes `patterns.json` as `{"names": [...], "names_then": [...] | null}` where `names_then` is the scan of the changed files at the last-run commit (spec 6.3).

- [ ] **Step 1: Flag-parent spike** as above.
- [ ] **Step 2: Write the failing tests**: `test_argparse_commands_flags_and_parents`, `test_hidden_flag_suppress_and_underscore`, `test_click_and_typer_commands`, `test_env_direct_reads_and_prefix_family` (`os.getenv("SVC_HOME")` makes `"SVC_CACHE_DIR"` in a helper call an env), `test_routes_decorators`, `test_mcp_tool_multiline_name_and_params` (`Tool(` with `name=` on the next line; schema properties as `param` with the tool as parent), `test_js_process_env_commander_and_routes`, `test_project_files_scripts_targets_env_and_dotenv`, `test_names_then_for_changed_files`.
- [ ] **Step 3: Run**. Expected: FAIL. **Step 4: Implement.** **Step 5: Run**. Expected: PASS.
- [ ] **Step 6: Commit** `feat(document-drift): pattern scan for user-facing names`.

---

### Task 9: Gap detection and targets

**Confidence:** 90%.

**Files:**
- Create: `skills/document-drift/scripts/dd_gaps.py`
- Test: `skills/document-drift/tests/test_dd_gaps.py`

**Interfaces:**
- Consumes: `patterns.json`, `inventory.json` (in-scope docs), doc texts, `dd_md_scan.scan` (lists and tables), `dd_defindex.norm`, `config["undocumented_ok"]`, `config["caps"]["gaps"]`.
- Produces: `documented(name: Name, texts) -> bool` (spec 8.2 rules: whole word for single words, substring for multiword, placeholders unified, params only under their tool's heading); `lists(texts, names) -> list[List]` with `List = {"doc", "line_start", "line_end", "kind", "scope": [parents] | null, "subjects": [...], "complete": bool}`; `candidates(names, names_then) -> list[Name]` (all on a first run; names absent from `names_then` on a later run); `gaps(...) -> list[Gap]` with `Gap = {"name", "kind", "parent", "file", "line", "gap_kind": "undocumented"|"missing-from-list", "target_doc", "target_line", "reason"}` and targets per spec 8.3; `run(workdir, config) -> dict` writes `gaps.json` as `{"candidates", "lists", "gaps", "targets": {doc: [Gap]}, "no_home": [Name], "unchecked": [docs beyond the cap, ordered by gap count then path]}`.

- [ ] **Step 1: Write the failing tests**: `test_documented_whole_word_and_flag_keeps_dashes` (`--force` not matched by "force"), `test_mcp_spellings_match`, `test_param_documented_only_under_tool_heading`, `test_list_needs_three_subjects_of_one_kind`, `test_flag_list_scoped_by_heading_parent`, `test_complete_intended_at_half`, `test_missing_from_list_targets_that_list`, `test_undocumented_targets_doc_with_most_same_kind_names`, `test_no_home_when_nothing_fits`, `test_hidden_and_undocumented_ok_never_gaps`, `test_later_run_candidates_are_new_names_only`, `test_gap_cap_order`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): gap detection and targets`.

---

### Task 10: Notice loop

**Confidence:** 90%.

**Files:**
- Create: `skills/document-drift/scripts/dd_unverified.py`
- Test: `skills/document-drift/tests/test_dd_unverified.py`

**Interfaces:**
- Consumes: doc texts, `anchors.json`, `tokens.json` markers (`drift-ignore` regions, `honoured`), `dd_md_scan.scan` (to find the block below a notice: the next non-blank block; a list is every item with the block's `list_id`; a table is the run of `table_row`/`table_delim` blocks), `preflight.json` run id.
- Produces:
  - `parse_notice(line: str) -> Notice | None` (`{"stage": 1|2, "run", "hash"}`), `render_notice(stage, run_id, hash) -> str` (exact text per Shared contracts), `block_hash(text) -> str`.
  - `decide(doc, text, anchors_for_doc, ignore_regions, run_id) -> tuple[list[Decision], list[Edit], list[Stale]]` with `Decision = {"doc", "line", "stage", "run", "hash", "block": [s, e], "action": "clear-anchored"|"clear-changed"|"clear-ignore"|"escalate"|"remove"}` and the edits of spec 7.3's table (`clear`: old is the notice line, new `""`; `escalate`: old the 1st line, new the 2nd line; `remove`: old the notice plus the block, new `""`, type `unverified`, subject the hash, claim `3rd notice, unchanged since <run id>`). A notice whose run id sorts after the current run id, or that fails to parse after matching `drift-unverified`, is stale.
  - `nominate(nominations: list[{"doc", "start_line", "end_line", "why"}], texts, existing_decisions, run_id) -> list[Edit]` of type `notice` (old the block's first line, new the notice line plus the first line), skipping blocks that already carry a notice, overlap a decided block or lie in an ignore region.
  - `run_start(root, workdir, run_id) -> dict` writes `notices.json` `{"decisions", "edits", "stale"}`; `run_verify(workdir, nominations, run_id)` appends nomination edits. Edit ids `n001`... in doc then line order, numbered over both calls.

- [ ] **Step 1: Write the failing tests**: `test_parse_and_render_roundtrip`, `test_block_hash_ignores_line_endings`, `test_first_notice_unchanged_escalates`, `test_second_notice_unchanged_removes_block_and_notice`, `test_changed_block_clears`, `test_anchored_block_clears`, `test_drift_ignore_clears`, `test_list_and_table_are_one_block`, `test_remove_edit_at_end_of_doc`, `test_future_notice_is_stale`, `test_malformed_notice_is_stale`, `test_nomination_skips_noticed_and_ignored_blocks`, `test_edit_ids_in_doc_then_line_order`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): notice loop for unverifiable blocks`.

---

### Task 11: Dispatch, prompts and output validation

**Confidence:** 90%.

**Files:**
- Create: `skills/document-drift/scripts/dd_dispatch.py`, `skills/document-drift/prompts/review-first.md`, `prompts/review-later.md`, `prompts/gap.md`, `prompts/verify.md`
- Test: `skills/document-drift/tests/test_dd_dispatch.py`

**Interfaces:**
- Consumes: `units.json`, `gaps.json`, `changes.json`, `edits.json` (Task 12), `config["models"]`, doc texts.
- Produces:
  - `render(template: str, values: dict[str, str]) -> str`: replaces `{{name}}` placeholders; an unknown placeholder raises. Templates are read from `prompts/` next to the scripts.
  - `plan_docs(root, workdir, config) -> list[PlanEntry]` writing `plan-docs.json` and `prompts/review-uNNN.md` (one per unit within the cap; template `review-first` or `review-later` by `changes.json` mode) and `prompts/gap-gNNN.md` (one per target doc within the cap, ids `g001`... in path order). Review prompt values: repository root, the unit's docs with line ranges, the anchors as `` `ref` (doc line) -> file:start-end ``, on a later run the hunks as a unified diff, the output path, the unit id. Gap prompt values: the doc, its gaps (kind, name, parent, `path:line`, target line and reason), the output path.
  - `plan_verify(root, workdir, batches, config) -> list[PlanEntry]` writing `plan-verify.json` and `prompts/verify-vNN.md` (each edit with claim, evidence, old, new, 10 doc lines either side).
  - `validate_review(obj) -> list[str]`, `validate_gap(obj) -> list[str]`, `validate_verdicts(obj, expected_ids) -> list[str]`: empty list when valid; checks types, required keys, `type` and `kind` enums, `old` a string, `start_line <= end_line`, every verdict id expected and present once. A gap output is `{"doc": id, "edits": [Edit with type add], "refusals": [{"name", "kind": "not-user-facing"|"already-documented"|"target-refused", "reason"}]}`.
  - `collect_verdicts(workdir, plan) -> dict` writing `verdicts.json` as `{"verdicts": {edit id: {"verdict", "reason"}}, "unverified": [edit ids whose batch was unchecked or whose entry is missing]}`.
  - `check_outputs(workdir, plan, role) -> tuple[list[str], list[PlanEntry]]` (valid output ids, failed entries); `write_retry(workdir, failed)`.
- Mandatory sentences in every prompt: the agent is read-only (Read, Grep, Glob), writes exactly one file (the output path) with the Write tool, runs no command, writes no helper script or other file, and replies with only the output path, its byte size and item counts. The review prompts carry spec 7.1's scope (first or later), the `anchor` edit rule, the `code_claims` and `unverified_blocks` fields with the preamble/pitch/process/history exclusion, the guarantee-word rule and the `unsure` rule; the gap prompt carries spec 8.4 (confirm user-facing, search for other spellings, list format, refusals `not-user-facing`, `already-documented`, `target-refused`); the verify prompt carries spec 9.2's five conditions plus the `anchor` condition. Start from the validated spike prompts, whose text is reproduced in spec 14.2 and 14.3's description and in the task brief's appendix below.

- [ ] **Step 1: Write the failing tests**: `test_render_replaces_and_rejects_unknown`, `test_plan_docs_one_entry_per_unit_and_gap_doc_within_caps`, `test_review_prompt_contains_anchors_and_diff_on_later_run`, `test_prompts_carry_mandatory_sentences` (every rendered prompt contains "exactly one file", "no command", "helper script"), `test_validate_review_rejects_bad_type_and_missing_old`, `test_validate_verdicts_requires_every_id_once`, `test_check_outputs_lists_missing_and_invalid`, `test_write_retry_is_plan_format`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement** the module and write the four templates. **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): agent dispatch plans and prompts`.

**Appendix for the brief: validated prompt bases.** The later-run review prompt validated in spec 14.3 opened: "You are checking one markdown doc against recent changes to the code it describes, and proposing edits where the doc is now wrong. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file." It then gave the repository root, the doc and its line count, the sentence "Since the docs were last checked (commit X), the code below changed. The doc refers to these names, whose definitions the changes touched:" followed by the anchor lines, the diff in a fenced block, a "Your scope" section ("Check only the doc's statements about these names and the behaviour these changes affect (including statements that describe that behaviour without naming them). Open the current source whenever the diff alone does not settle a statement. Ignore everything else in the doc, even if it might be wrong: other runs cover it."), the output schema and the edit rules. The first-run prompt validated in spec 14.2 had the same frame with the "What to check" paragraph of spec 7.1 and the edit rules: "Code is the truth. Make the minimal change: fix the wrong part, keep the doc's wording, voice and formatting. No reflowing, no style edits, no improvements to things that are not wrong. Do not add missing material here (another step documents what the code has and the docs lack), except where a statement is wrong because it is incomplete in a way that misleads. Edit a heading only when the heading itself is wrong." The verify prompt validated in spec 14.2 opened: "You are an independent checker. Another agent proposed edits to markdown docs so they match the code. For each edit below, decide from the source code whether applying it makes the doc correct. You did not write these edits and you have no stake in them; reject anything you cannot confirm." and listed the five conditions as a numbered list, then "Verdict accept only when all five hold. reject when any fails, with the reason. unsure when you cannot settle it."

---

### Task 12: Script checks and verify batches

**Confidence:** 92%.

**Files:**
- Create: `skills/document-drift/scripts/dd_checks.py`
- Test: `skills/document-drift/tests/test_dd_checks.py`

**Interfaces:**
- Consumes: `review/*.json`, `gaps/*.json` (validated by Task 11), `notices.json` edits, `tokens.json` (markers, generated regions, never-edit headings), `defindex.json`, `inventory.json`, doc texts at HEAD, `config`.
- Produces:
  - `check(edit, ctx) -> tuple[str, str | None, str | None]` returning `(status, check, human_kind)` for the spec 9.1 table in order: `old-mismatch` (with the whitespace repair, which rewrites `old` and re-indents `new` in place), `protected`, `evidence`, `still-in-source`, `anchor-adds-name`, `guarantee`, `large-deletion`, `large-section`, `new-reference`, `overlap`. Guarantee words: `must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`, matched as whole words, case-insensitive. `anchor-adds-name`: `new` minus one inline-code span equals `old` after removing at most 3 extra words (tokens split on whitespace, brackets stripped), the span's name resolves through `dd_anchors.resolve` to a definition in the evidence file, and `old` holds no guarantee word.
  - `batches(kept_edits) -> list[list[Edit]]` grouped by first evidence file (removals with no evidence by doc), batches of at most 10, ordered by group key then id; batches beyond `caps.verify` are unverified.
  - `run(root, workdir, config) -> dict` writing `edits.json` (Shared contracts; review edits before gap edits before notice edits; notice edits are checked but never batched) with `questions` (from review outputs, each a human entry of its kind), `refusals` (from gap outputs: `not-user-facing` and `already-documented` counted only; `target-refused` becomes a human entry), `unverified_blocks`, `code_claims`, `unchecked_units`, `unchecked_gap_docs`, `unverified_batches`.

- [ ] **Step 1: Write the failing tests**, one per check plus: `test_old_mismatch_is_not_repaired_when_lines_differ`, `test_whitespace_repair_reindents_new`, `test_anchor_adds_name_accepts_bracketed_name`, `test_anchor_adds_name_rejects_name_resolving_elsewhere`, `test_batches_group_by_evidence_file_max_10`, `test_notice_edits_checked_not_batched`, `test_order_review_gap_notice`, `test_gap_refusals_counted_or_human`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): script checks and verify batches`.

---

### Task 13: Apply edits and heading links

**Confidence:** 88%. The uncertain part is reusing `dd_apply._Checker` for the spec 9.3 re-scan with edits that are not phase 1 hunks. Raise it first: Step 1 reads `_Checker`, `_Text` and `_apply_doc` and writes in the task report which of them `apply_edits` reuses unchanged and which it wraps; the rule to implement is "revert when the multiset of unresolved `(kind, text)` path or anchor tokens after the edit is not a subset of the multiset before". Spec 11.1 lists `dd_apply` as unchanged; this plan extends it instead of writing a synthetic phase 1 hunk adapter, because the hunk shape (`finding_id`, `token_kind`) belongs to the removed `dd_fixes`.

**Files:**
- Modify: `skills/document-drift/scripts/dd_apply.py` (add; the phase 1 `run` goes in Task 16)
- Test: `skills/document-drift/tests/test_dd_apply.py`

**Interfaces:**
- Consumes: `edits.json`, `verdicts.json` (`{"verdicts": {edit id: {"verdict", "reason"}}, "unverified": [ids]}`), `tokens.json`, `inventory.json`; `dd_resolve.heading_slugs`, `slugify_heading`.
- Produces:
  - `apply_edits(root, workdir) -> dict` writing `applied.json` as `{"applied": [ids], "reverted": [{"edit", "reason"}], "docs": [...], "link_updates": [{"doc", "line", "old", "new", "edit"}]}`. Applies, per doc from the bottom up, every edit whose status is `kept` and whose verdict is `accept`, plus every kept notice edit (no verdict needed); exact match of `old` against the current lines (ending-preserving, as `_Text` does); after each edit the doc is re-extracted and the unresolved path and anchor tokens compared; a failure reverts that edit with `recheck-failed`. Writes each doc once, atomically.
  - `update_heading_links(root, workdir, applied_edits, texts) -> list[dict]`: for an applied edit whose range held a heading line and whose `new` heading differs, every in-scope doc's anchor token targeting the old slug of that doc is rewritten to the new slug; the edited docs join `docs`.

- [ ] **Step 1: Read** `_Checker`, `_Text`, `_apply_doc`; record the reuse decision.
- [ ] **Step 2: Write the failing tests**: `test_apply_accepted_edits_bottom_up`, `test_rejected_and_unverified_edits_not_applied`, `test_notice_edits_apply_without_verdict`, `test_apply_edits_keeps_crlf`, `test_recheck_reverts_edit_that_breaks_a_path`, `test_heading_edit_updates_links_in_other_docs`, `test_doc_written_once_atomically`.
- [ ] **Step 3: Run**. Expected: FAIL. **Step 4: Implement.** **Step 5: Run** the new tests and the old `test_dd_apply.py` tests (still green until Task 16). Expected: PASS.
- [ ] **Step 6: Commit** `feat(document-drift): apply agent edits with re-scan and heading links`.

---

### Task 14: Two commits and the human-decision list

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_commit.py`
- Test: `skills/document-drift/tests/test_dd_commit.py`

**Interfaces:**
- Consumes: `edits.json`, `verdicts.json`, `applied.json`, `gaps.json` (`no_home`, gap refusals from `gaps/*.json`), `notices.json`, `preflight.json`, `changes.json`.
- Produces:
  - `collect_human(workdir) -> list[HumanEntry]` sorted by doc then line: questions (`guarantee-mismatch`, `unsure`), check results with `human_kind`, `no-home`, `target-refused`, `verify-rejected` (reject and unsure verdicts, with the reason), `recheck-failed`, `unverified` (escalated notices, text the block's first line).
  - `render_bullet(edit, applied_doc_line) -> str` per spec 9.4 grammar: `correct <claim> (<evidence...>)`, `remove <claim> (<subject> not in source)`, `anchor <subject> (<evidence>)`, `notice unverified block (1st notice)`, `escalate unverified notice (2nd notice)`, `clear unverified notice (<reason>)`, `remove unverified block (3rd notice, unchanged since <run id>)`, `add <kind> <name> (<evidence>)`.
  - `render_message(kind: "corrections"|"additions", bullets, *, run_id, base, scope, unchecked: tuple[int, int, int], human: list | None, trailers) -> str` with subjects `docs(drift): correct stale docs` and `docs(drift): document missing surface`, the four `Drift-` lines, then the bullets, then (only when `human` is given) the `Needs a human decision:` block, then trailers; every string redacted and cut to 160 characters per line.
  - `run(root, workdir, branch, run_id, base, scope, trailers) -> dict` writing `commits.json` `{"branch", "commits": [{"sha", "kind"}]}` and the two message files; creates the branch only when at least one commit will be made; the human block goes on the last commit made.

- [ ] **Step 1: Write the failing tests**: `test_bullet_grammar_for_every_edit_type` (one assertion per type, exact strings), `test_message_grammar_corrections_and_additions` (exact expected text, including `Drift-Unchecked`), `test_human_block_on_last_commit_only`, `test_no_commit_without_edits_and_no_branch`, `test_collect_human_kinds_and_order`, `test_lines_cut_to_160_and_redacted`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): two drift commits with the phase A grammar`.

---

### Task 15: Summary

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_summary.py`
- Test: `skills/document-drift/tests/test_dd_summary.py`

**Interfaces:**
- Consumes: every workdir file of the run; `dd_commit.collect_human`, `render_bullet`.
- Produces: `render(workdir) -> str` with the sections of spec 9.5 in this order: run and mode; docs (scanned, excluded by reason, skipped); references and anchors (anchored, unanchored by reason); checkability (every doc's `refs/anchored/rate`, then unverifiable and weak docs by name; on a first run split by `code_claims` zero or not, with anchor edits applied per doc); notice loop (placed, escalated, cleared by reason, removed, stale); later-run change set (changed files, hunks, affected docs with their reasons); review units (checked, unchecked by cap, unchecked after retry); claims checked; edits proposed by source; check results by check; verdicts by kind; applied and reverted; gaps by kind and target, refusals by kind; the human-decision list; markers without reasons and stale markers; branch and commits or `No branch created`; under `--check`, `Planned edits:` with every accepted edit as a bullet. `run(workdir) -> str` writes `summary.md`.

- [ ] **Step 1: Write the failing tests** from a hand-built workdir: `test_summary_sections_in_order`, `test_checkability_lists_unverifiable_and_weak_docs`, `test_notice_loop_counts`, `test_check_mode_lists_planned_edits_as_bullets`, `test_no_branch_line`.
- [ ] **Step 2: Run**. Expected: FAIL. **Step 3: Implement.** **Step 4: Run**. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): phase A summary`.

---

### Task 16: Staged driver, phase 1 removals

**Confidence:** 90%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_run.py` (rewrite), `dd_preflight.py` (record `base`, `full`, `branch`, `check`, `date`), `dd_resolve.py` (drop history use: `Resolver` resolves against HEAD only; `run` keeps writing `candidates.json` for path and anchor tokens with `resolved: bool`), `dd_history.py` (remove `line_snapshots`, `renames_since`, `final_name`, `deleting_commit`, `last_commit_touching`, `prefetch`), `dd_apply.py` (remove the phase 1 `run`, `_settle_findings`, `_verdict` for hunks; `main` calls `apply_edits`), `dd_config.py` (remove `lead_cap`, `recent_change_days`), `dd_common.py` (add `EXIT_RETRY = 3`)
- Delete: `scripts/dd_fixes.py`, `tests/test_dd_fixes.py`, `tests/test_dd_goldens.py`, `tests/test_dd_corpus.py`, `tests/golden/**`, the phase 1 parts of `tests/test_dd_run.py`, `test_dd_resolve.py`, `test_dd_history.py`, `test_dd_apply.py`, `test_dd_commit.py`, `test_dd_summary.py` that exercise removed behaviour (keep the rest)
- Test: `skills/document-drift/tests/test_dd_run.py` (rewritten), `tests/canned/small/` (canned agent outputs for the small-repo test)

**Interfaces:**
- Consumes: `dd_dispatch.collect_verdicts` (writes `verdicts.json` at `finish`).
- Produces: `main(argv)` with `repo`, `--stage {start,verify,finish}` (required), `--retried`, `--base`, `--full`, `--branch`, `--check`, `--workdir`, `--date`. `stage_start(...)`, `stage_verify(...)`, `stage_finish(...)` each returning an exit code. Step order inside `start`: preflight, inventory, extract, resolve (paths), defindex, anchors, changes, units, patterns, gaps, notices (`run_start`), dispatch (`plan_docs`); every step wrapped by `_step` (exit 5 on crash or missing output); `start` deletes every pinned output first, including `review/`, `gaps/`, `verdicts/`, `prompts/`. `verify`: refuse (exit 2) unless `plan-docs.json` exists and `preflight.json` flags equal the argv flags; `check_outputs` for review and gap roles; without `--retried` and with failures, write `retry.json` and exit 3; else mark failed units and gap docs unchecked; notices `run_verify` with the nominations; `dd_checks.run`; `plan_verify`; print the plan file and entry count. `finish`: same precondition on `plan-verify.json` (or `plan-docs.json` empty); verdict outputs validated the same way (exit 3 / `--retried`); tree check (`git status --porcelain` paths outside the workdir that differ from preflight's list: exit 2 naming them); under `--check`: summary, exit 1 if any accepted edit else 0, no apply, no commit, no record; else `apply_edits`, `update_heading_links`, `dd_commit.run`, `last-run.json` (`{"head", "run_id", "date", "committed"}`), summary; exit 0. `finish` directly after `start` is allowed when `plan-docs.json` is `[]`. A repository with no in-scope doc stops `start` after the inventory with the message `no markdown docs in scope; no-docs mode arrives in phase B` and exit 0, writing an empty `plan-docs.json` (spec 4). Exit codes per spec 2.

- [ ] **Step 1: Write the failing tests** on a small repo built with `make_repo` and canned outputs under `tests/canned/small/`: `test_start_writes_plan_and_prompts`, `test_verify_before_start_is_refused`, `test_flag_mismatch_between_stages_is_refused`, `test_missing_agent_output_exits_3_and_writes_retry`, `test_retried_marks_unit_unchecked`, `test_finish_commits_two_commits_and_records_last_run` (asserts the original branch's HEAD is unchanged and each commit touches only in-scope `.md` files, success criterion 1), `test_no_docs_stops_with_phase_b_message`, `test_check_mode_exits_1_without_changes_or_record`, `test_finish_refuses_when_tree_changed_outside_workdir`, `test_empty_plan_allows_finish_after_start`, `test_second_run_is_later_run_from_drift_base`, `test_crashed_step_exits_5`.
- [ ] **Step 2: Run**. Expected: FAIL.
- [ ] **Step 3: Implement** the driver and the removals; fix the kept tests that imported removed names.
- [ ] **Step 4: Run** the whole suite: `pytest skills/document-drift -q && ruff check . && mypy && python skills/document-drift/scripts/dd_check_skill.py`. The SKILL linter still passes because SKILL.md changes in Task 17; if it fails on a removed flag, update the one command line now. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): staged driver; remove the history-gated pipeline`.

---

### Task 17: SKILL.md, README, architecture, CI

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/SKILL.md` (rewrite), `README.md` (the document-drift section), `docs/architecture.md` (the document-drift section), `.github/workflows/test.yml` (remove the `dd_run.py . --check` self-scan step; keep `dd_check_skill.py`)
- Test: `python skills/document-drift/scripts/dd_check_skill.py` and `tests/test_dd_copies.py` (if it compares SKILL.md excerpts, update it)

- [ ] **Step 1: Rewrite SKILL.md** with: the description and triggers; what the skill does (spec 1.1) and not (spec 1.2); the no-improvisation rule (spec 3.3); the procedure as numbered steps with the exact commands: `python scripts/dd_run.py <repo> --stage start [--base <ref>] [--full] [--branch <name>] [--check]`, "read `plan-docs.json`; for each entry dispatch one read-only Agent with its `model`, whose prompt is exactly: `Read the file <prompt> in full and follow it. Write only <output>.`; dispatch all entries in one message; when the plan is empty skip to finish", `python scripts/dd_run.py <repo> --stage verify`, the exit 3 retry rule, the verifier dispatch from `plan-verify.json`, `python scripts/dd_run.py <repo> --stage finish`, and the exit code table of spec 2; the markers (`drift-ignore` family and the skill's own `drift-unverified` notices, which the user must not edit by hand except to answer them); the config keys; the final message rule (summary verbatim, branch name or `No branch created`, one line that pushing and the PR are the user's).
- [ ] **Step 2: Update README.md and docs/architecture.md** to describe the phase A pipeline (stages, files, both directions, notice loop) and point at the new spec; mark the phase 1 pipeline description as replaced.
- [ ] **Step 3: Edit the workflow** and run `python skills/document-drift/scripts/dd_check_skill.py`. Expected: exit 0.
- [ ] **Step 4: Run** `pytest skills/document-drift -q`. Expected: PASS.
- [ ] **Step 5: Commit** `docs(document-drift): phase A skill procedure and docs`.

---

### Task 18: Fixture corpus, part 1: `py-service`

**Confidence:** 85%. The uncertain part is keeping canned outputs' line numbers and unit ids in step with the fixture text. Raise it first: Step 1 writes the fixture docs and code, runs `--stage start` on the replayed fixture, and reads `units.json` and `anchors.json` before writing any canned file; canned files quote `old` text copied from the doc.

**Files:**
- Modify: `tests/fixtures/corpus/py-service/history.yaml`, `files/**`, `planted.json`
- Create: `tests/canned/py-service/state1/{review,gaps,verdicts}/*.json`, `tests/canned/py-service/state2/...`
- Modify: `tests/dd_corpus.py` (new evaluation vocabulary), `tests/dd_make_history.py` (`replay_fixture(name, dest, until_tag=None)` replays the commits up to and including the one carrying `tag: <until_tag>`; `continue_fixture(name, repo, after_tag)` replays the remaining commits onto the repository's current branch, so a test can run the drift pipeline between the two states and merge its branch first)

**Fixture content** (history: state-1 commits, then state-2 commits tagged `state2`; `planted.json` keyed by state):

| id | state | where | what | expect |
|---|---|---|---|---|
| p1 | 1 | `README.md` | "`--port` defaults to 8000"; code `add_argument("--port", default=8080)` | `edit:correct` |
| p2 | 1 | `README.md` | flag written `--worker`; code `--workers` | `edit:correct` |
| p3 | 1 | `README.md` | "two routes"; `routes.py` registers three | `edit:correct` |
| p4 | 1 | `docs/tools.md` | list item for `store.delete`; no such `Tool(` | `edit:remove` |
| p5 | 1 | `README.md` | "The store **never** blocks"; `Store.put` takes a lock | `human:guarantee-mismatch` |
| p6 | 1 | `docs/configuration.md` | env table has `SVC_HOME`, `SVC_PORT`; code also reads `SVC_LOG_LEVEL` | `gap:missing-from-list:docs/configuration.md` |
| p7 | 1 | `src/svc/cli.py` | `init` command with `--force`, `--db`; no doc mentions `init` | `gap:undocumented:docs/cli.md` |
| p8 | 1 | `docs/design.md` | "Expired rows are purged nightly" names nothing; canned `anchor` edit adds `Store.purge` | `edit:anchor` then `anchors` |
| p9 | 1 | `docs/process.md` | contributing guide, no code claims (`code_claims` 0) | `not-about-code` |
| p10 | 1 | `docs/design.md` | block "Writes go to disk before the reply returns" nominated as unverified | `notice:1st` |
| d1 | 1 | `README.md` | "`store.sync` was removed in 1.2" | `none` |
| d2 | 1 | `README.md` | "SQLite's `VACUUM` reclaims space" | `none` |
| d3 | 1 | `src/svc/cli.py` | `--debug` with `help=argparse.SUPPRESS` | `none` |
| d4 | 1 | `src/svc/_internal.py` | `_helper` | `none` |
| d5 | 1 | `.document-drift.yaml` | `undocumented_ok: ["store.list"]`; `store.list` absent from docs | `none` |
| d6 | 1 | `docs/tools.md` | a selective list of 1 of 3 tools under "Examples" | `none` |
| d7 | 1 | canned review | an `anchor` edit naming `connect` with evidence in `cli.py` | `dropped:anchor-adds-name` |
| p11 | 2 | `src/svc/cli.py` | `--port` default becomes 9090; README (fixed at state 1) affected | `affected` and `edit:correct` |
| p12 | 2 | `src/svc/storage.py` | `connect` renamed `open_store`; `docs/design.md` names `connect` | `affected` and `edit:correct` |
| p13 | 2 | `src/svc/cli.py` | new flag `--timeout` on `serve`; `docs/cli.md` flag table complete-intended | `gap:missing-from-list:docs/cli.md` |
| d8 | 2 | `src/svc/storage.py` | a line changed inside `Store.get`'s body (class over 60 lines); `docs/tools.md` names only `Store` | `not-affected` |
| d9 | 2 | `docs/untouched.md` | names only `routes.py` functions, unchanged | `not-reviewed` |
| x1 | 1 | `CHANGELOG.md` | would be an edit if scanned | `excluded` |

`src/svc/tools.py` registers `store.put`, `store.get`, `store.list` with `Tool(` and `name=` on the next line and an input schema; `src/svc/schema.sql` creates `items`; `pyproject.toml` has `[project.scripts] svc = "svc.cli:main"`; `src/svc/config.py` reads env vars through `os.environ.get` and a `_env()` helper.

**Canned outputs:** state 1 review outputs (one per unit, ids from `units.json`), with `code_claims`, `unverified_blocks` for p10, edits for p1–p4, p8, d7, a `guarantee-mismatch` question for p5; gap outputs for p6, p7; verdicts accepting every kept edit except one `reject` (a planted wrong correction, listed as `human:verify-rejected`, id `p14`); one invalid review output under `state1-invalid/` for the retry test. State 2: review outputs for the affected units, gap output for p13, verdicts.

**New evaluation vocabulary** (`dd_corpus.evaluate`): `edit:<type>` (an applied edit of that type on the doc line), `human:<kind>`, `gap:<gap_kind>:<target doc>`, `dropped:<check>`, `none` (no edit, no human entry, no gap on that doc line or name), `excluded`, `affected`/`not-affected` (doc in `changes.json` `affected`), `not-reviewed` (doc in no unit), `anchors` (the doc line has an anchor in the next run's `anchors.json`), `not-about-code` (`code_claims` 0 in the summary split), `notice:1st|2nd|removed|cleared:<reason>` (from `notices.json` decisions and applied notice edits).

- [ ] **Step 1: Write the fixture**, replay it, run `start`, read `units.json`/`anchors.json`.
- [ ] **Step 2: Write `planted.json` and the canned outputs.**
- [ ] **Step 3: Write the failing tests** in a new `tests/test_dd_corpus.py`: `run_fixture(name, state, tmp_path, canned_invalid=False) -> Workdir` drives `start`, copies canned review and gap files, `verify`, copies verdicts, `finish`; for state 2 it runs state 1 first, merges the drift branch into the main branch with `git merge --no-ff`, then `continue_fixture(..., after_tag="state1")` (so the `Drift-Base` commit is an ancestor of HEAD); one parametrised test per planted item asserting its expectation; `test_invalid_output_exits_3_then_retried_marks_unchecked`; `test_no_agent_dispatched_when_nothing_changed` (state 2 run again right after its own drift run).
- [ ] **Step 4: Run** `pytest skills/document-drift/tests/test_dd_corpus.py -v -k py_service`. Expected: PASS after fixing fixture or code; a failure that reveals a script bug is fixed in the script with its own unit test.
- [ ] **Step 5: Commit** `test(document-drift): py-service fixture for phase A`.

---

### Task 19: Fixture corpus, part 2: `ts-web` and `go-cli`, notice loop

**Confidence:** 85% (same reason and remedy as Task 18).

**Files:**
- Modify: `tests/fixtures/corpus/ts-web/**`, `tests/fixtures/corpus/go-cli/**`
- Create: `tests/canned/ts-web/...`, `tests/canned/go-cli/...`, `tests/test_dd_notice_loop.py`

**`ts-web` planted items:** `process.env.API_URL` and `process.env.FEATURE_FLAGS` read, docs table lists one (`gap:missing-from-list`); commander `.command("build")` and `.option("--minify")`, `--minify` undocumented (`gap:undocumented`); an express route `app.get("/api/items/:id")` documented as `/api/items/{id}` (decoy `none`, placeholders unify); `index.md` as an HTML landing page with `<code>renderApp()</code>` (`anchors`); a wrong default in `docs/api.md` (`edit:correct`); a wrong count in `README.md`; state 2 renames a TS function the docs name (`affected`, `edit:correct`) and leaves `docs/frontend.md` untouched (`not-reviewed`).

**`go-cli` planted items:** Go has no definitions, so references anchor to files by unique basename: `docs/usage.md` names `options.go` and `env.go` (`anchors`); Makefile targets `build`, `lint`, `release` with `release` undocumented (`gap:undocumented`); a wrong flag name in `README.md` fixed by a canned edit (`edit:correct`); `docs/legacy.md` describing behaviour with no names (`unverifiable`, nominated block `notice:1st`).

**Notice loop test** (`test_dd_notice_loop.py`, on `go-cli`): three runs driven in one test with canned nominations at run 1 only:
1. Run 1 (first run): `docs/legacy.md` gets four 1st notices (blocks A, B, C, D) and `docs/usage.md` one on a 20-line list (block E). Merge the drift branch into main.
2. Between runs: rewrite block B; add `` `options.go` `` to block C; put `<!-- drift-ignore: prose -->` above block D.
3. Run 2 (later run; nothing else changed): expect `escalate` on A and E (`notice:2nd`, `human:unverified`), `clear` on B (`block changed`), C (`now anchored`), D (`drift-ignore`). Merge.
4. Run 3: expect A removed with its notice (`notice:removed`), E (over `max_delete_lines`) left in place as `human:large-deletion`; a hand-written malformed notice added before run 3 is listed as stale and untouched.

- [ ] **Step 1: Write both fixtures**, replay, run `start`, then write `planted.json` and canned outputs.
- [ ] **Step 2: Write the tests** (parametrised items for both fixtures; the notice-loop test).
- [ ] **Step 3: Run** `pytest skills/document-drift/tests/test_dd_corpus.py skills/document-drift/tests/test_dd_notice_loop.py -v`. Expected: PASS.
- [ ] **Step 4: Commit** `test(document-drift): ts-web and go-cli fixtures; notice loop end to end`.

---

### Task 20: Goldens

**Confidence:** 92%.

**Files:**
- Create: `tests/test_dd_goldens.py`, `tests/golden/<fixture>/<state>/**`

- [ ] **Step 1: Write the test**: for each fixture and state, run the canned pipeline with `--date 2026-01-02 --branch docs/drift-golden`; compare byte for byte `defindex.json`, `anchors.json`, `changes.json`, `units.json`, `patterns.json`, `gaps.json`, `notices.json`, `edits.json`, `plan-docs.json`, `plan-verify.json`, `applied.json`, both commit messages (`git log --format=%B`) and every edited doc; `UPDATE_GOLDENS=1` regenerates. Absolute paths inside plan files are rewritten to `<workdir>` before comparing.
- [ ] **Step 2: Generate** with `UPDATE_GOLDENS=1 pytest skills/document-drift/tests/test_dd_goldens.py`, read every commit message and edited doc, then run without the variable. Expected: PASS twice (determinism, success criterion 6).
- [ ] **Step 3: Commit** `test(document-drift): phase A goldens`.

---

### Task 21: Live harness and evaluation log

**Confidence:** 85%. The uncertain part is the `claude -p` invocation on this machine; `skills/tech-debt-scan/scripts/live_run.py` (`launcher_argv`, `claude_argv`, `dispatch`, prompt on stdin) is the validated reference. Raise it first: Step 1 runs that harness's `--help` and one trivial `claude -p` through its `dispatch` to confirm the launcher works here.

**Files:**
- Create: `skills/document-drift/tests/dd_live_run.py`
- Modify: `docs/evaluation-log.md` (a `document-drift` section with the column list)

**Interfaces:**
- Produces: `python tests/dd_live_run.py <fixture name | repo path> [--from <sha>] [--full] [--check] [--keep <dir>] [--budget <usd>]`: replays a fixture to a temporary directory (or uses the repository), runs `start`, dispatches every plan entry through `claude -p` (prompt file content on stdin, the entry's model, read-only tools, per-call budget), `verify`, the verifiers, `finish`; then appends a row to `docs/evaluation-log.md` with repository, HEAD, mode, docs affected, units, edits proposed by source, kept after checks, verdicts by kind, applied, human entries, notices placed, gaps by kind, planted caught and decoys touched (fixtures only), agents per role, wall time and tokens; `--keep` copies the workdir. It never calls the model from pytest (`test_dd_live_run.py` covers argument parsing and the row format only).

- [ ] **Step 1: Launcher check** as above.
- [ ] **Step 2: Write the failing tests** (`test_dd_live_run.py`): `test_row_format`, `test_fixture_name_or_path`, `test_refuses_without_claude`.
- [ ] **Step 3: Implement.** **Step 4: Run** the tests; then run the harness once on `py-service` state 1 with real agents and read the row. Expected: the planted items of Task 18 are caught by real agents too; any miss is recorded in the row and in the task report, not fixed by changing the fixture.
- [ ] **Step 5: Commit** `feat(document-drift): live evaluation harness`.

---

### Task 22: Live runs and the acceptance bar

**Confidence:** n/a (owner-judged; success criteria 7 and 8).

- [ ] **Step 1:** Run the harness on `better-memory` (`--full`) and append the row; the owner judges every applied edit, human entry and notice; record acceptance rate, time, agents and tokens; set the acceptance bar in `docs/evaluation-log.md` (D14). Record spec 14.1's A12 and A13 results (anchor edits proposed, accepted, judged right; nominated blocks that were in fact preamble).
- [ ] **Step 2:** After real commits on `better-memory`, run again without `--full` and append the row (a later run).
- [ ] **Step 3:** Run `/document-drift` on this repository through the skill (not the harness), push nothing; the edits are accepted or rejected in the phase A PR.
- [ ] **Step 4:** Record every assumption whose status changed in spec 14.1; commit `docs(document-drift): live evaluation rows and assumption status`.
- [ ] **Step 5:** Memory sweep (CLAUDE.md), then `superpowers:finishing-a-development-branch`; the PR closes #22 unmerged (spec 0e).
