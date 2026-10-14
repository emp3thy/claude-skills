# document-drift Phase C Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the mechanical classes of doc drift script work (moved `path:line` citations, table cells contradicting scanned defaults, choices and required flags), hand every agent the scanned facts and the code it needs inside its prompt, and commit script edits in their own commit, so a run costs less and the agents' worst class of mistake disappears.

**Architecture:** Two new script modules run inside `start`: `dd_cite` checks every line citation against the definition index and the pattern scan, `dd_facts` checks fact tables against the scan's new `default`, `choices` and `required` fields; both write `script-edits.json`, which `dd_checks` folds in as a fourth edit source (`script`) that skips the verifier, `dd_apply` applies without a verdict and `dd_commit` lands in a third commit. `dd_dispatch` inlines the unit's code ranges, the facts and the script results into the review prompt with a reading rule and an optional `opened` output key. Phase A and B code is extended, not forked.

**Tech Stack:** Python 3.11+, standard library plus `pyyaml`; `ast` for the scan; pytest, ruff, mypy strict; canned agent outputs; the live harness for the measurement.

**Spec:** `docs/superpowers/specs/2026-10-14-document-drift-phase-c-design.md` (cited as "spec N"; the phase A spec as "A §n", its plan's Shared contracts as "A plan").

## Global Constraints

- Every module is `dd_`-prefixed under `skills/document-drift/scripts/`, with a `main(argv)` and a `run(...)`; tests are `tests/test_dd_*.py`. Only `pyyaml` beyond the standard library. From the repository root `ruff check .` and `mypy` stay clean and `python -m pytest skills/document-drift -q` green after every task; `python scripts/dd_check_skill.py` clean from the skill directory when `SKILL.md` changes.
- Output files are written with `dd_common.write_json` or as UTF-8 LF; every repository-derived string that reaches a commit message or the summary passes through `dd_redaction.redact`. No test calls a model. Nothing in scripts depends on the identity of a fixture or a real repository.
- The edit record is A plan's shared shape. Script edit ids: `c001`, `c002`, ... for `cite`, `f001`, ... for `fact`, in doc then line order. `source: "script"`, `status: "kept"` as written by the scripts.
- Subjects of a citation resolve only to definitions of rank 0 (`dd_defindex.RANK` value 0: `module`, `function`, `class`, `sql`, `file`) or to scanned names (spec 2.1). The nearest-name window after a citation is 60 characters.
- Commit grammar: the third commit's subject is `docs(drift): correct citations and facts`, bullets `- <doc>:<line> cite <subject> <file>:<old> -> <file>:<new>` and `- <doc>:<line> fact <name> <column> <old> -> <new> (<file>:<line>)` (spec 6). A §9.4's two commits do not change.
- No new config keys (spec 8). `drift-ignore` markers and `never_edit_heading` apply to script edits.
- Branch: `feat/document-drift-phase-c` from `main`. Commit after every task with a `feat(document-drift):`, `test(document-drift):` or `docs(document-drift):` subject and the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` line.
- Every task carries a confidence figure; a task under 90% names the investigation that raises it as its first step.

## Review Focus

1. **A subject whose only definition is in a file other than the cited one** (a function moved across files). The script must not rewrite the citation to the other file; it is a `use site` hint. Test in Task 2 (`test_subject_defined_elsewhere_is_a_use_site_hint`).
2. **Two citations on one doc line, both moved.** One `cite` edit for the line carries both rewrites, so the apply step never sees two edits whose `old` is the same line. Test in Task 2 (`test_two_moved_citations_on_one_line_are_one_edit`).
3. **A boolean default documented as `off` or `disabled`.** The scan says `false`; the row must not be rewritten to the word `false` when it already says the same thing. Test in Task 4 (`test_boolean_defaults_normalise_before_comparison`).
4. **The same flag under two commands with different defaults** (`--force` of `init` and of `sync`). The row under the `init` heading must be checked against `init`'s flag only; with no heading naming a parent, the row is skipped. Test in Task 4 (`test_rows_are_scoped_by_the_heading_parent`).
5. **A later-run prompt whose diff and inlined ranges together would exceed the unit's budget.** The inlined ranges are the touched anchors' ranges only and the rendered prompt stays within `unit_lines` plus headers. Test in Task 5 (`test_later_run_inlines_only_touched_ranges_within_budget`).

---

## Shared contracts

**Citation token** (`tokens.json`, added by Task 1 beside the existing path token of the same reference): the Token shape with `kind: "cite"`, `text: "<path>:<n>"` or `"<path>:<n>-<m>"` or `"<path>#L<n>"`, and extras `path` (the path as written), `start` (int), `end` (int, equal to `start` for a single line). Its span covers the whole `path:line` text. `dd_resolve`, `dd_anchors`, `dd_apply` and `dd_summary` ignore `cite` tokens (they select by kind today; Task 1 asserts it).

**Script edits file** `script-edits.json` (spec 5):

```json
{"edits": [edit records], "hints": {"<doc>": [{"line": 12, "kind": "cite-ambiguous" | "cite-use-site" | "cite-unresolved" | "not-in-scan", "text": "..."}]},
 "counts": {"citations": {"checked", "current", "moved", "ambiguous", "use_site", "unresolved"},
            "facts": {"rows_checked", "corrected", "not_in_scan"}}}
```

`dd_cite.run` creates it; `dd_facts.run` reads it and appends. Both are no-ops with empty lists when there is nothing to check.

**Name record** (`patterns.json`, Task 3): `{"name", "kind", "file", "line", "parent", "hidden", "default": str | null, "choices": [str] | null, "required": bool | null}`.

**Hint texts**: `cite ambiguous: <subject> <path>:<n>`; `cite use-site: <subject> is defined in <file>:<start>-<end>`; `cite unresolved: <path>:<n>`; `not in scan: <name>` or `not in scan: <name>; nearest <scanned name>` (edit distance at most 2 by `norm`).

**Review output**: gains optional `opened: [{"path", "why"}]`; `validate_review` accepts it (list of objects with string fields) and treats absence as `[]`.

**Prompt placeholders** added by Task 5: `review-first.md` and `review-later.md` gain `{{code}}` (the inlined blocks) and `{{settled}}` (the script results for the unit); `verify.md` gains `{{facts}}` per edit inside the existing edit rendering (no new top-level placeholder: `_edit_value` adds a `- Facts:` line); `gap.md`'s gap lines gain the facts inline.

---

### Task 1: Citation tokens

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_extract.py` (`_split_target` around line 160, the path-token emission around lines 325 and 344)
- Test: `skills/document-drift/tests/test_dd_extract.py`, `tests/test_dd_resolve.py`, `tests/test_dd_anchors.py`

**Interfaces:**
- Produces: for every inline-code or link path reference whose target carries `:N`, `:N-M` or `#LN`, a second token of kind `cite` (Shared contracts) at the same line and column, in addition to the path token the extractor emits today with the suffix stripped. Fence-argument paths keep today's behaviour (no cite token).

- [ ] **Step 1: Write the failing tests**: `test_cite_token_for_each_shape` (`` `src/app.py:12` ``, `` `src/app.py:12-20` ``, a link to `src/app.py#L7`: three cite tokens with `path`, `start`, `end`, the path token still present with `text` `src/app.py`), `test_no_cite_token_without_a_line` and `test_cite_tokens_are_ignored_by_resolve_and_anchors` (`candidates.json` and `anchors.json` for a doc with one cite token are byte-identical to the same doc without the suffix).
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_extract.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and the full suite** (phase A goldens hold `tokens.json`? check `tests/golden/*/state*/`; if a golden holds it, regenerate that file only and say so). Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): citation tokens`.

---

### Task 2: Citation checks

**Confidence:** 90%. The subject rule was probed on better-memory's 140 citations (spec 2.2); the only judgement left is the identifier regex, pinned below.

**Files:**
- Create: `skills/document-drift/scripts/dd_cite.py`
- Test: `skills/document-drift/tests/test_dd_cite.py`

**Interfaces:**
- Consumes: `tokens.json` (cite tokens and each doc's lines through `dd_checks._read`), `defindex.json` (`definitions` with `name`, `file`, `start`, `end`, `kind`), `patterns.json` (`names`), `inventory.json` (`files`, `never_edit_re`), the doc markers (`dd_checks._protected` for `drift-ignore` and never-edit regions).
- Produces: `subject_of(line: str, col: int, end_col: int, defs, names) -> Subject | None` (pure; `Subject = {"text", "file", "start", "end", "kind": "definition" | "scanned", "count": int}` where `count` is how many spans the name resolves to in the cited file); `check(token, subject, files, file_lengths) -> tuple[str, dict | None]` returning the case name of spec 2.2 and, for `moved`, the rewrite `{"old_cite": "agentcore.py:1578", "new_cite": "agentcore.py:1838-1843"}`; `run(root, workdir) -> dict` writing `script-edits.json`, with **one `cite` edit per doc line** holding every moved citation of that line (`old` and `new` the whole line; `subject` the first moved citation's subject; `evidence` one `file:start-end` per moved citation; `old_cite` and `new_cite` joined with `, ` when several, for the commit bullet of Task 7). A missing `tokens.json`, `defindex.json` or `patterns.json` raises `StepError` exit 5 naming the step.

- [ ] **Step 1: Write the failing tests**, on a `tmp_path` workdir with hand-written `tokens.json`, `defindex.json`, `patterns.json` and doc files:
  - `test_subject_is_the_nearest_name_before_then_after` (`` `promote_reflection` at agentcore.py:1578 `` resolves to `promote_reflection`; `` agentcore.py:93 (EpisodeService) `` to the name after; a line with `foo` and `bar` before picks `bar`);
  - `test_bare_and_called_identifiers_resolve` (`observe() wraps` after the citation resolves to the definition `observe`; `AgentCoreBackend.list_projects()` to the member);
  - `test_scanned_names_are_subjects` (a row `` | `GET /semantic` | `app.py:487` | `` resolves through the scan's route record at `app.py:470`: moved);
  - `test_literals_are_never_subjects` (`memory.db` with a `literal` definition: unresolved);
  - `test_cases` parametrised over spec 2.2's rows: current, moved single line (`:1578` becomes `:1838`), moved range (`:1578-1582` becomes `:1838-1843`), several definitions one covers, ambiguous;
  - `test_subject_defined_elsewhere_is_a_use_site_hint` (Review Focus 1);
  - `test_untracked_file_and_line_past_end_are_unresolved`;
  - `test_edit_record_shape_and_ids` (the whole record for one moved citation, `old` and `new` the full line, `old_cite`, `new_cite`, ids `c001`, `c002` in doc then line order);
  - `test_two_moved_citations_on_one_line_are_one_edit` (Review Focus 2: one record, both numbers changed in `new`, two evidence entries);
  - `test_ignored_and_never_edit_citations_are_skipped`;
  - `test_run_writes_script_edits_with_hints_and_counts`.
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_cite.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** Identifier regex for candidates: inline-code span contents, else `[A-Za-z_][\w.]*` words, each stripped of a trailing `()`; resolution through `dd_defindex.norm` against the index's `norm` with the last dotted segment as the member, specific match only (A §5.3); scanned names matched by `norm` with the route form (`routes=True`) for route kinds. The cited file matches a definition's `file` when the definition's path ends with the cited path's segments.
- [ ] **Step 4: Run the tests, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): citation checks against the definition index`.

---

### Task 3: Scanned facts

**Confidence:** 92%. The scan already visits every `add_argument`, `click.option`, `environ.get` and schema property call with its `ast` node; the fields are keyword reads on those nodes.

**Files:**
- Modify: `skills/document-drift/scripts/dd_patterns.py` (`Name`, `_File.add`, `_argparse`, `_decorated`, `_schema_params`, `_python_call`, the JS scanners)
- Test: `skills/document-drift/tests/test_dd_patterns.py`

**Interfaces:**
- Produces: the Name record with `default`, `choices`, `required` (Shared contracts). argparse: `default=` literal text (an `ast.Constant`; any other expression gives null), `action="store_true"` gives `"false"`, `"store_false"` gives `"true"`, `choices=` a list or tuple of constants, `required=True/False`; click `option`: `default=`, `type=click.Choice([...])`, `required=`; `os.environ.get("X", "v")` and `os.getenv("X", "v")`: the second argument when a constant; MCP schema properties: `default` and `enum` from the property's dict, `required` from the schema's `required` list; JS `process.env.X || "v"` is out of scope (null). Every other record keeps nulls.

- [ ] **Step 1: Write the failing tests**: `test_argparse_defaults_choices_required` (`default=8080` → `"8080"`; `default="x"` → `"x"`; `store_true` → `"false"`; `choices=["a", "b"]`; `required=True`; `default=os.getcwd()` → null), `test_click_option_facts`, `test_env_default_from_second_argument`, `test_mcp_schema_default_enum_required`, `test_facts_are_null_when_absent` (every existing fixture's names carry the three keys as null).
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_patterns.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests and the full suite.** `patterns.json` is a golden for the phase A fixtures: regenerate those files only (the three new keys, null or filled) and read the diff by hand. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): scan defaults, choices and required`.

---

### Task 4: Fact tables

**Confidence:** 90%. The table parser is `dd_md_scan`'s existing block model (`table_header`, `table_row` kinds); scoping by heading is `dd_gaps._heading_before` and `_named_parents`, reused.

**Files:**
- Create: `skills/document-drift/scripts/dd_facts.py`
- Test: `skills/document-drift/tests/test_dd_facts.py`

**Interfaces:**
- Consumes: `patterns.json` (Task 3), the docs' blocks through `dd_md_scan.scan`, `dd_gaps._heading_before` and `_named_parents` (import them; if they are private, promote them to public names in `dd_gaps` in this task), `script-edits.json` (Task 2).
- Produces: `fact_tables(doc_text) -> list[Table]` (`Table = {"header_line", "name_col", "value_cols": {column name: index}, "rows": [{"line", "cells", "name"}]}`; a value column's header, lowercased, is or contains `default`, `required`, `values`, `choices`, `options` or `one of`); `normalise(cell: str, column: str) -> str | None` (spec 3.2's rules; booleans `off`, `disabled`, `no`, `false` → `"false"`, `on`, `enabled`, `yes`, `true` → `"true"`; a choices cell → its items joined by `, `); `check_row(row, table, names, parent) -> tuple[str, dict | None]` returning `checked`, `corrected` (with the edit record, which carries `column`, `old_cell` and `new_cell` for the commit bullet of Task 7), `not-in-scan` or `skipped`; `run(root, workdir, config) -> dict` appending to `script-edits.json`; a missing `patterns.json` or `script-edits.json` raises `StepError` exit 5 naming the step; `drift-ignore` markers and never-edit regions skip a table as they skip any block.

- [ ] **Step 1: Write the failing tests**: `test_fact_table_detection` (a table with a `Default` column and a backticked name column is one; a table without a value column is not; `One of` counts), `test_row_with_stale_default_is_corrected` (`| \`--port\` | ... | 8000 |` against `8080`: the edit's `new` is the row with only that cell changed, backticks kept when the old cell had them), `test_boolean_defaults_normalise_before_comparison` (Review Focus 3), `test_no_default_spellings_are_equal` (`-`, `None`, empty against null: no edit), `test_choices_cell_compares_as_a_set` (`a \| b` against `["a", "b"]`: no edit; `a, c` corrected keeping the comma separator), `test_required_column`, `test_rows_are_scoped_by_the_heading_parent` (Review Focus 4), `test_unknown_name_is_a_hint_with_nearest`, `test_several_matches_are_skipped`, `test_run_appends_to_script_edits` (ids `f001`..., counts).
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_facts.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): fact tables checked against the scan`.

---

### Task 5: Prompts: inline ranges, facts, settled lines, `opened`

**Confidence:** 90%. The size bound follows from `unit_lines` counting the reading ranges (A §6.4); the later-run case is pinned by Review Focus 5's test.

**Files:**
- Modify: `skills/document-drift/scripts/dd_dispatch.py` (`_anchors_value`, new `_code_value`, `_settled_value`, `_edit_value`, `_gaps_value`, `validate_review`), `skills/document-drift/prompts/review-first.md`, `review-later.md`, `verify.md`, `gap.md`
- Test: `skills/document-drift/tests/test_dd_dispatch.py`

**Interfaces:**
- Consumes: `script-edits.json` (hints and edits), `patterns.json` facts.
- Produces: `_code_value(root, unit, affected, later) -> str`: per file, the unit's anchors' reading ranges (on a later run only the touched anchors' ranges) merged when overlapping or adjacent, rendered as `### <file>:<start>-<end>` followed by a fenced block of `n: text` lines; `_settled_value(unit, script) -> str`: the `cite` and `fact` edits on the unit's doc ranges as `- <doc>:<line>: <old> -> <new>` and the hints as `- <doc>:<line>: <text>`, or `(none)`; anchor lines gain `(default 8080; choices a, b; required)` from the scan for scanned names; `_edit_value` gains `- Facts: <name>: default 8080; ...` for scanned names in `old` or `new`; `_gaps_value` lines gain the same. `validate_review` accepts `opened`.
- The prompts: `review-first.md` and `review-later.md` get a `## The code` section with `{{code}}`, a `## Already settled by script` section with `{{settled}}`, the reading rule of spec 4 replacing "Start from the code ranges above and open whatever else you need", the rule that no edit may touch a settled line, and `"opened": []` in the output shape with its meaning; `verify.md` and `gap.md` only gain the fact lines.

- [ ] **Step 1: Write the failing tests**: `test_code_blocks_merge_ranges_and_number_lines`, `test_later_run_inlines_only_touched_ranges_within_budget` (Review Focus 5: a unit of two anchors where the change touched one; the rendered prompt's inlined lines count at most the unit's `size`), `test_settled_section_lists_script_edits_and_hints_in_range`, `test_anchor_lines_carry_facts`, `test_verify_and_gap_prompts_carry_facts`, `test_validate_review_accepts_opened`, `test_prompts_have_the_reading_rule_and_no_placeholder_left`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** The phase A goldens do not hold prompts; `plan-docs.json` paths are unchanged. Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): review prompts carry the code, the facts and the settled lines`.

---

### Task 6: Pipeline: `start` steps, the `script` source, apply

**Confidence:** 92%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_run.py` (`stage_start`, `OUTPUTS`), `scripts/dd_checks.py` (`SOURCES`, `run`, `_overlap`, `batches`), `scripts/dd_apply.py` (`selected_edits`), `scripts/dd_dispatch.py` (`plan_docs` reads `script-edits.json`)
- Test: `skills/document-drift/tests/test_dd_run.py`, `tests/test_dd_checks.py`, `tests/test_dd_apply.py`

**Interfaces:**
- Produces: `stage_start` runs `cite` after `anchors` and `facts` after `patterns` (`patterns` stays after `changes`, which it reads), both before `dispatch`; `OUTPUTS` gains `script-edits.json`. `dd_checks.SOURCES` gains `script`; `run` loads `script-edits.json` (optional: absent means none) and checks its edits with `old-mismatch`, `protected` and `overlap` only (a `CHECKS_BY_SOURCE` mapping keeps the agent list for the others); script edits are checked first so `_overlap` drops a later agent edit on the same lines with the check name `overlap-script`, counted in `edits.json` as `overlap_script: n`; `batches` skips `script` edits. `dd_apply.selected_edits` applies a kept `script` edit without a verdict.

- [ ] **Step 1: Write the failing tests**: in `test_dd_checks.py` `test_script_edits_pass_three_checks_only`, `test_agent_edit_on_a_script_line_is_overlap_script`, `test_batches_skip_script_edits`; in `test_dd_apply.py` `test_selected_edits_takes_script_edits_without_verdict`; in `test_dd_run.py` `test_start_runs_cite_and_facts_and_clears_their_output` (the small fixture with a planted moved citation: `script-edits.json` exists after `start`, is cleared by the next `start`, and the edit lands in `edits.json` with `source: script` after `verify` and in the drift branch after `finish`).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS; `edits.json` goldens of the phase A fixtures gain `overlap_script: 0` only if the key is unconditional: make it unconditional and regenerate those goldens, reading the diff by hand.
- [ ] **Step 5: Commit** `feat(document-drift): script edits through the checks and apply`.

---

### Task 7: Third commit and the summary

**Confidence:** 92%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_commit.py` (`SUBJECTS`, `KIND_ORDER`, `render_bullet`, `run`), `scripts/dd_summary.py` (`_edits_section`, new `_script_section`, `_result_section`)
- Test: `skills/document-drift/tests/test_dd_commit.py`, `tests/test_dd_summary.py`

**Interfaces:**
- Produces: `KIND_ORDER = ("corrections", "additions", "citations")`, subject `docs(drift): correct citations and facts`; `render_bullet` renders `cite` (`- <doc>:<line> cite <subject> <old_cite> -> <new_cite>`, from the fields Task 2 writes) and `fact` (`- <doc>:<line> fact <name> <column> <old_cell> -> <new_cell> (<file>:<line>)`, from the fields Task 4 writes); `run` groups `source == "script"` into `citations`, stages docs in the first commit that touches them, makes the citations commit with `--allow-empty` when nothing is left to stage, and puts the human list on the last commit made. `dd_summary`: `Edits proposed` gains `script: <n>`; a `Script edits` section after it with spec 7's three lines; `Result` lists the third commit; under `--check` the planned list includes script edits.

- [ ] **Step 1: Write the failing tests**: `test_citations_commit_after_additions_with_bullets`, `test_citations_commit_allow_empty_when_docs_already_staged`, `test_human_list_on_last_commit_made` (a run with corrections and citations: the list on the citations commit), `test_script_section_counts`, `test_planned_list_includes_script_edits_under_check`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): citations commit and script summary`.

---

### Task 8: Fixture, goldens and the harness

**Confidence:** 90%. The fixture's state-2 history already moves definitions (`connect renamed open_store`), so a planted citation on `connect` moves with it.

**Files:**
- Modify: `skills/document-drift/tests/fixtures/corpus/py-service/history.yaml` (state-2 commits and the final `files/` docs), `planted.json`, `tests/canned/py-service/state2/`, `tests/golden/py-service/state2/`, `tests/dd_corpus.py` (`hint:` expectation), `tests/dd_live_run.py` (`render_row` notes)
- Test: `skills/document-drift/tests/test_dd_corpus.py`, `tests/test_dd_goldens.py`, `tests/test_dd_live_run.py`

**Interfaces:**
- Produces: `py-service` state 2 gains, in `docs/operations.md` or a new `docs/internals.md`: a citation `` `open_store` at src/svc/storage.py:N `` written for the state-1 line (moved in state 2: `edit:cite`), a citation with the subject after it (`src/svc/storage.py:N (open_store)`: `edit:cite`), a table cell citation with no subject (`hint:cite-unresolved`), a use-site citation of a class defined elsewhere (`hint:cite-use-site`), and a flag table under `## serve` with a stale `--port` default (`edit:fact`), a `store_true` row written `off` (`none`), and a row naming `--worker` (`hint:not-in-scan`). `dd_corpus.evaluate` gains `hint:<kind>`: the hint appears in `script-edits.json` on the item's doc line. `render_row` notes gain `cite <moved>/<checked>; facts <corrected>/<checked>; opened <n>` (the sum of review outputs' `opened` entries) on every run.

- [ ] **Step 1: Plant the fixture changes** in the state-2 commits only (state-1 goldens must not change), run the pipeline once to learn the line numbers, then write the canned review outputs (unchanged where the agent is not involved) and `planted.json`.
- [ ] **Step 2: Extend `evaluate` and `render_row`; run** `pytest skills/document-drift/tests/test_dd_corpus.py -k py-service -v` and `test_dd_live_run.py -v`. Expected: every planted item passes, including the new ones.
- [ ] **Step 3: Goldens.** Regenerate `tests/golden/py-service/state2/` and read `script-edits.json`, `edits.json`, `commit-msg-citations.txt` and `summary.md` by hand against spec 2.2, 3.2, 6 and 7.
- [ ] **Step 4: Run the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `test(document-drift): phase C plants in py-service state 2, goldens, harness notes`.

---

### Task 9: Docs

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/SKILL.md` ("What the user gets": the third commit and its bullets; the human kinds unchanged; the summary's `Script edits` section), `docs/architecture.md` (the `start` row gains `cite` and `facts`; the modules `dd_cite` and `dd_facts`; a paragraph on script edits and the inline prompt), `README.md` (one clause), the phase A spec (§7.2's output shape gains `opened`; §9.4 points at the phase C spec for the third commit), the phase C spec (any amendment the implementation forced, dated), `docs/evaluation-log.md` (the notes legend for `cite`, `facts`, `opened`).
- Check: `python scripts/dd_check_skill.py` clean.

- [ ] **Step 1: Write the doc changes.**
- [ ] **Step 2: Run** the SKILL linter and the full suite. Expected: clean.
- [ ] **Step 3: Commit** `docs(document-drift): phase C script edits and prompts`.

---

### Task 10: Measurement

**Confidence:** 90%. The harness and the evaluation log already record every figure the acceptance test needs.

**Files:**
- Modify: `docs/evaluation-log.md`, the phase C spec's section 12 (C1 to C6 status)

- [ ] **Step 1: The "before" run.** Before merging phase C, from a checkout of `main` (a `git worktree add` of `main` is fine), run `python tests/dd_live_run.py C:/Users/gethi/sources/better-memory --full --log <this repository's docs/evaluation-log.md>` at better-memory's current head, with better-memory's `.document-drift.yaml` as it is. Record the row.
- [ ] **Step 2: The "after" run.** From the phase C branch, the same command at the same head. Record the row.
- [ ] **Step 3: Compare** review tokens per call, calls, cost, the script edits made against the before run's agent `cite`-class edits (every citation the agent fixed before must be a `cite` edit after, or a listed hint), and the `opened` count. Write the comparison as a paragraph under the table and the C1 to C6 statuses in the spec. If review tokens per call did not halve, say so and leave the decision (keep the inline blocks or fall back to the prompt rule) to the owner in the final report.
- [ ] **Step 4: One live run on this repository** at `main` with the phase C code, logged.
- [ ] **Step 5: Commit** `docs(document-drift): phase C measurement`.
