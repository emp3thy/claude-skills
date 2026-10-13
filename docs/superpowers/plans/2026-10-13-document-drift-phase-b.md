# document-drift Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a repository's root has no in-scope `README.md`, the run writes one from the code, in the same run and on the same branch as phase A's edits: one fact sheet per code area, one README composed from the sheets, every statement verified, the result in the additions commit.

**Architecture:** Three new script modules (`dd_areas`, `dd_sheets`, `dd_readme`) and three prompts (`sheet.md`, `readme.md`, `verify-readme.md`) plug into the staged driver: `start` adds the area split and the sheet agents to the first wave; a new `compose` stage validates the sheets and dispatches the writer; `verify` validates the writer's output, runs the citation check and adds the README's statements to the verifier batches; `finish` removes the rejected statements, writes `README.md` and commits it as a `create` edit. Phase A's dispatch, retry, verdict, apply, commit and summary code is extended, not forked.

**Tech Stack:** Python 3.11+, standard library plus `pyyaml`; pytest, ruff, mypy strict; canned JSON agent outputs; the live harness `tests/dd_live_run.py` for the one real run.

**Spec:** `docs/superpowers/specs/2026-10-13-document-drift-phase-b-design.md` (sections cited as "spec N"; the phase A spec as "A §n"). The spike that measured the design is spec 15; its throwaway scripts and draft prompts are the starting point for Tasks 2, 3, 4 and 6, not code to copy.

## Global Constraints

- Every module is `dd_`-prefixed under `skills/document-drift/scripts/`, with a `main(argv)` and a `run(...)`; every test file is `tests/test_dd_*.py`. Only `pyyaml` beyond the standard library. `ruff check .` and `mypy` (from the repository root) stay clean after every task; the full suite `pytest skills/document-drift -q` stays green.
- Every output file is written with `dd_common.write_json` or as UTF-8 with LF. Every repository-derived string that reaches a commit message or the summary passes through `dd_redaction.redact`. No test calls a model; no script, constant or test depends on the identity of a fixture or a real repository.
- Constants, from spec 11: `readme` true, `area_lines` 5000, `readme_lines` 300, `caps.sheet_agents` 12, `caps.readme_batch` 15, `models.sheet` `sonnet`, `models.readme` `opus`. Guarantee words are A §7.2's list, already `dd_checks._guarantees`. Name normalisation is `dd_defindex.norm`.
- Agents are read-only toward the repository and write one output file; every prompt carries A §7.4's mandatory lines verbatim (copy them from `prompts/review-first.md`, line 3).
- The commit grammar gains one bullet (spec 8) and nothing else changes in A §9.4. Exit codes are A §2's; `compose` refuses with exit 2 as spec 3 and 12 say.
- Branch: `feat/document-drift-phase-b` from `main`. Commit after every task with a `feat(document-drift):`, `test(document-drift):` or `docs(document-drift):` subject. `SKILL.md`, `docs/architecture.md` and `README.md` change in the same PR as the code.
- Every task carries a confidence figure. A task under 90% names the investigation that raises it; that investigation is the task's first step.

## Review Focus

1. **A repository whose only README is `docs/README.md` or `readme.rst`.** Phase B must trigger: the test is a root `.md` named README in any case. Test in Task 5 (`test_readme_trigger_is_root_markdown_only`).
2. **A sheet entry whose `defined_at` is a real place in a file outside the area.** The validator must reject it (the agent wandered), not accept it because the line resolves. Test in Task 4 (`test_defined_at_outside_the_area_is_invalid`).
3. **A writer output whose fence content lines lie in no claim, or whose claims overlap.** Both are structural and make the output invalid, so the retry fires once and then the run goes on without a README. Test in Task 6 (`test_fence_lines_need_a_claim`, `test_overlapping_claims_are_invalid`).
4. **A hidden name inside one table row of a 30-row table.** Only that row is pre-rejected; the table and the claim that covers it stay. Test in Task 6 (`test_hidden_name_rejects_the_row_not_the_table`).
5. **A `--check` run in README mode.** No `README.md` is written, the summary lists the `create` bullet under Planned edits, `finish` exits 1. Test in Task 7 (`test_check_mode_lists_the_readme_and_writes_nothing`).

---

## Shared contracts

**Workdir files added by phase B** (phase A's table in the phase A plan stands):

| Stage | File | Written by |
|---|---|---|
| start | `preflight.json` gains `readme: bool` | `dd_run` |
| start | `areas.json` | `dd_areas` |
| start | `plan-docs.json` gains the `sheet` entries; `prompts/sheet-aNN.md` | `dd_dispatch.plan_sheets` |
| agents | `sheets/aNN.json` | sheet agents |
| compose | `sheets.json`, `plan-readme.json`, `prompts/readme-r001.md` | `dd_sheets`, `dd_dispatch.plan_readme` |
| agents | `readme/r001.json` | the writer |
| verify | `readme.json`; `edits.json` gains the `create` edit; `plan-verify.json` gains the README batches; `prompts/verify-vNN.md` | `dd_readme.check_step`, `dd_dispatch.plan_verify_readme` |
| finish | `verdicts.json` gains `readme` and `readme_unverified`; `applied.json` gains `readme`; `README.md` in the working tree | `dd_dispatch.collect_verdicts`, `dd_readme.apply` |

`dd_run.OUTPUTS` gains `areas.json`, `sheets.json`, `plan-readme.json`, `readme.json`; `OUTPUT_DIRS` gains `sheets`, `readme`.

**Area record** (`areas.json`, spec 4): `{"area_lines": int, "areas": [{"id": "a01", "files": [{"path", "lines"}], "lines": int, "hints": [Name...]}]}` with `Name` the `dd_patterns` record `{"name", "kind", "file", "line", "parent", "hidden"}`.

**Sheet output** (spec 5.2), written by the agent; `dd_sheets` adds `id` to every entry (`a03-s12`, `a03-b04`), `filled: true` to filled entries, and corrects `hidden`:

```json
{"area": "a03",
 "surface": [{"kind": "command", "name": "sync", "parent": null, "summary": "...", "default": null,
              "defined_at": "src/app/cli.py:41", "user_facing": true, "hidden": false}],
 "behaviours": [{"statement": "the loader (`ConfigLoader.load`) reads ...", "evidence": ["src/app/config.py:17"]}],
 "dismissed": [{"hint": "flag --legacy", "why": "help=argparse.SUPPRESS"}]}
```

`sheets.json`: `{"sheets": {"a01": sheet, ...}, "unchecked": [{"area", "why"}], "filled": int, "hidden_corrected": int}`.

**Writer output** (spec 6.3): `{"text": str, "claims": [{"start_line", "end_line", "cites": [id...]}]}`.

**Statement record** (spec 6.5), in `readme.json` `{"text", "claims", "statements": [...], "cites_added": int, "cited_unnamed": int}`: `{"id": "r-s001", "start_line", "end_line", "section": str, "kind": "item"|"table-row"|"paragraph"|"fence", "text": str, "cites": [id...], "prereject": str|null}`. Ids are zero-padded to three digits in README order.

**Plan entry roles:** `sheet` (output `sheets/aNN.json`, key `area`), `readme` (output `readme/r001.json`, no id key: the output has `text` and `claims`), and `verify` entries of two kinds, told apart by their key: `edits` (phase A) or `statements` (README). `dd_dispatch.ROLE_DIRS` gains `"sheet": "sheets"` and `"readme": "readme"`.

**README verdict output** (spec 7): `{"batch": "v07", "verdicts": [{"statement": "r-s012", "verdict": "accept"|"reject"|"unsure", "reason": str}]}`, validated like phase A's by expected ids. `verdicts.json` gains `"readme": {sid: {"verdict", "reason"}}` and `"readme_unverified": [sid...]`.

**The create edit** in `edits.json` `edits`: `{"id": "r001", "doc": "README.md", "start_line": 1, "end_line": 1, "old": "", "new": "", "type": "create", "claim": "readme from <n> sheets", "evidence": [], "subject": null, "source": "readme", "status": "kept", "check": null, "human_kind": null, "reason": null, "statements": int}`. `dd_apply.selected_edits` never selects it (its source is `readme`, and it has no verdict); `dd_readme.apply` applies it.

**`applied.json`** gains `"readme": {"lines": int, "statements": int, "removed": int} | null`, and `"applied"` gains `"r001"` when the README was written.

**Commit bullet** (spec 8): `- README.md:1 create readme (<n> statements from <n> sheets, <n> removed)`, in the additions commit only, `README.md` staged by path.

**Human-decision kind** added: `readme-rejected` (`{"doc": "README.md", "line": <start_line>, "kind": "readme-rejected", "text": <statement text, one line>, "evidence": [<reason>]}`), from pre-rejections and from `reject` and `unsure` verdicts.

**Stage lines on stdout:** `start` prints `readme: yes` or `readme: no` before its plan line; `compose` prints `plan-readme.json <path> with 1 entries` or `readme: no sheet; nothing to compose`; `verify` and `finish` print as today. `dd_live_run.PLAN_LINE` gains `plan-readme`.

---

### Task 1: Configuration keys

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_config.py`
- Test: `skills/document-drift/tests/test_dd_config.py`

**Interfaces:**
- Produces: `DEFAULTS` gains `readme: True`, `area_lines: 5000`, `readme_lines: 300`, `caps.sheet_agents: 12`, `caps.readme_batch: 15`, `models.sheet: "sonnet"`, `models.readme: "opus"`, validated as the existing keys are (`readme` a bool; the ints positive; the models non-empty strings).

- [ ] **Step 1: Write the failing tests** in `test_dd_config.py`: `test_defaults_include_phase_b_keys` (every key with its default), `test_readme_must_be_bool_and_area_lines_positive` (`readme: "yes"` warns and keeps `True`; `area_lines: 0` warns and keeps 5000; `caps: {sheet_agents: "x"}` warns and keeps 12 for that sub-key only).
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_config.py -v`. Expected: FAIL on missing keys.
- [ ] **Step 3: Implement** in `DEFAULTS` and the validator table, following the existing per-sub-key pattern.
- [ ] **Step 4: Run the tests, `ruff check .`, `mypy`.** Expected: PASS, clean.
- [ ] **Step 5: Commit** `feat(document-drift): phase B config keys`.

---

### Task 2: Areas

**Confidence:** 92%.

**Files:**
- Create: `skills/document-drift/scripts/dd_areas.py`
- Test: `skills/document-drift/tests/test_dd_areas.py`

**Interfaces:**
- Consumes: `dd_inventory.indexed_files(inventory)`, `dd_inventory.is_project_file(rel)`, `patterns.json` `names`.
- Produces: `split(files: list[tuple[str, int]], project: set[str], area_lines: int) -> list[list[str]]` (pure: path groups in area order) and `run(root, workdir, config) -> dict` writing `areas.json` (Shared contracts). Line counts are the file's lines as `dd_dispatch._doc_lines` counts them (a file that cannot be read counts 0 and stays in its area).

- [ ] **Step 1: Write the failing tests**, each on a synthetic file list (no repository), with `area_lines` 100:
  - `test_project_files_and_root_loose_files_form_a01` (`pyproject.toml`, `Makefile` and `main.py` at the root go to the first group; `src/...` does not);
  - `test_directory_within_budget_is_one_area`;
  - `test_directory_over_budget_splits_into_subdirectories_plus_loose_files` (`src/` of 250 lines with `src/a/` 80, `src/b/` 90, loose 80: three groups);
  - `test_loose_files_over_budget_are_chunked_in_path_order` (five 30-line loose files: groups of three and two);
  - `test_single_file_over_budget_is_its_own_area`;
  - `test_siblings_merge_in_path_order_within_budget` (sub-areas of 30, 30, 50, 30 lines become 60+50? no: 30+30 merge to 60, 50 does not fit, 50+30 merge to 80: expect `[[a, b], [c, d]]`);
  - `test_top_level_directories_merge_too` (`docs/`, `scripts/`, `website/` of 20 lines each and `a01` of 10 lines merge into one group, spec 4 rule 4 at the root);
  - `test_hints_follow_their_file_and_strays_go_to_a01` on a `tmp_path` repository with `inventory.json` and `patterns.json` written by hand, asserting `areas.json`'s ids, `lines` and `hints`.
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_areas.py -v`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** `split` as spec 4's four rules in order (rule 2 recursive, rule 3 on loose files, rule 4 at every level including the root, `a01` taking part) and `run`. Ids `a01`, `a02`, ... in path order after merging.
- [ ] **Step 4: Run the tests, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): split the source into areas`.

---

### Task 3: Sheet prompt and sheet plan entries

**Confidence:** 92%.

**Files:**
- Create: `skills/document-drift/prompts/sheet.md`
- Modify: `skills/document-drift/scripts/dd_dispatch.py` (`ROLE_DIRS`, `_entry`, `_problems`, new `plan_sheets`, `validate_sheet`)
- Test: `skills/document-drift/tests/test_dd_dispatch.py`

**Interfaces:**
- Consumes: `areas.json` (Task 2); `dd_sheets.validate` arrives in Task 4, so this task's `validate_sheet(obj) -> list[str]` checks shape only (the three lists, every surface key present with its type, `area` a string); Task 4 wires the full validator into `_problems`.
- Produces: `plan_sheets(root, workdir, config) -> list[PlanEntry]`: one entry per area within `caps.sheet_agents` (areas past the cap, smallest first, are not planned and are returned by `dd_areas`'s order; `plan_sheets` records them in `areas.json` as `"unplanned": [ids]`), role `sheet`, id the area id, model `models.sheet`, prompt `prompts/sheet-aNN.md` rendered from `sheet.md` with placeholders `repo`, `area`, `files`, `hints`, `output`; the entries appended to `plan-docs.json` after the review and gap entries. `_entry` maps role `sheet` to prefix `sheet` and dir `sheets`.

- [ ] **Step 1: Write `prompts/sheet.md`** from spec 5.1 and 5.2: the mandatory lines; the area's files; the hints as a checklist with the rule that every hint is a surface entry or dismissed; the kinds; the behaviour rules (one sentence, one inline-code span naming the definition, no guarantee word, no intent or history); the output shape of spec 5.2 as the JSON illustration; the receipt reply. The spike's draft (spec 15) has this structure; tighten, do not paste.
- [ ] **Step 2: Write the failing tests**: `test_plan_sheets_one_entry_per_area_within_cap` (three areas, cap 2: entries `a01`, `a02` with role `sheet`, prompts naming every file of the area with its line count and every hint as `- <kind> <name> (parent <p>) <file>:<line>` plus ` hidden` when hidden; `a03` in `areas.json` `unplanned`; `plan-docs.json` holds review, gap, then sheet entries), `test_sheet_prompt_has_mandatory_lines_and_no_placeholder_left`, `test_validate_sheet_shape` (a missing list, a surface entry missing `defined_at`, `area` not a string).
- [ ] **Step 3: Run** the two tests. Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run the dispatch tests and the full suite, ruff, mypy.** Expected: PASS (phase A goldens unchanged: `plan_sheets` is not yet called by `dd_run`).
- [ ] **Step 6: Commit** `feat(document-drift): sheet prompt and plan entries`.

---

### Task 4: Sheet validator, fill and `sheets.json`

**Confidence:** 90%. The spike validated every rule on ten real sheets (spec 15); the name rule's wording is spec 5.3's amended text.

**Files:**
- Create: `skills/document-drift/scripts/dd_sheets.py`
- Modify: `skills/document-drift/scripts/dd_dispatch.py` (`_problems`: role `sheet` calls `dd_sheets.validate` after the shape check, with the area from `areas.json`)
- Test: `skills/document-drift/tests/test_dd_sheets.py`

**Interfaces:**
- Consumes: `areas.json`; `dd_defindex.norm`; `dd_checks._guarantees` (import it; do not copy the list).
- Produces: `KINDS` (spec 5.2's twelve); `validate(sheet: Any, area: Mapping, root: Path, tracked: set[str]) -> list[str]` (problems; empty when valid); `fill(sheet, area) -> int` (adds the missing hints as surface entries, spec 5.4; returns how many); `correct_hidden(sheet, area) -> int`; `run(root, workdir, config, failed: frozenset[str]) -> dict` writing `sheets.json` (Shared contracts): every planned area whose output is valid and not in `failed` gets its sheet with ids, hidden corrected and filled; the others and the unplanned areas are `unchecked` with `why` in `invalid after retry`, `no output`, `over the cap`.

- [ ] **Step 1: Write the failing tests**, on a `tmp_path` repository made with `dd_helpers.make_repo` holding `src/app/cli.py` (a `sync` command and a `--force` flag with help text), `src/app/config.py`, `scripts/setup.sh`, and an `areas.json` with two areas:
  - `test_valid_sheet_has_no_problems`;
  - `test_defined_at_outside_the_area_is_invalid` (Review Focus 2: a line that exists in the other area's file);
  - `test_defined_at_line_outside_the_file_is_invalid`;
  - `test_name_must_be_at_its_place` (`sync` defined at a line 10 lines away: invalid; `python -m app.cli` at `src/app/cli.py:1`: valid by the file rule; `scripts/setup.sh` at `scripts/setup.sh:1`: valid; `--force` at its `add_argument` line: valid);
  - `test_route_duplicates_are_keyed_by_method` (two `/items` entries with parents `GET` and `POST`: valid; two with the same parent: invalid);
  - `test_behaviour_needs_a_span_and_no_guarantee_word`;
  - `test_every_hint_is_an_entry_or_dismissed` (a missing `env APP_TOKEN`: invalid, the problem names it);
  - `test_fill_adds_missing_hints_from_the_scan` (`filled: true`, summary `from the pattern scan`, `user_facing` true, the hint's `hidden`);
  - `test_hidden_takes_the_hints_value` (an entry marked hidden for a flag whose hint is not hidden: corrected, counted);
  - `test_run_writes_sheets_json_with_ids_and_unchecked` (one valid, one in `failed`, one unplanned: `unchecked` has two entries with their `why`; ids `a01-s01`, `a01-b01`).
- [ ] **Step 2: Run** `pytest skills/document-drift/tests/test_dd_sheets.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `dd_sheets` and wire `_problems`. The name rule: tokens of three or more characters other than `python`, `node`, `npm`, `npx`, `uv`, `pip` and a leading directory, any within 3 lines of `defined_at`; or the name, `python -m ` dropped and dots as slashes, equal to the file path without extension.
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): fact sheet validator and sheets.json`.

---

### Task 5: The trigger, the `compose` stage and the writer's plan entry

**Confidence:** 90%. The open question was whether `start`'s steps tolerate a repository with no doc at all; a spike on 2026-10-13 ran every step from preflight to dispatch on such a repository and all passed (units and the plan empty, patterns and gaps populated), so README mode runs the full step list and the `NO_DOCS` shortcut applies only when `readme` is false.

**Files:**
- Create: `skills/document-drift/prompts/readme.md`
- Modify: `skills/document-drift/scripts/dd_run.py` (`STAGES`, `OUTPUTS`, `OUTPUT_DIRS`, `stage_start`, new `stage_compose`, `_resume`, `stage_verify`, `stage_finish`, `main`), `skills/document-drift/scripts/dd_dispatch.py` (`plan_readme`, `validate_readme` shape check, `_problems` for role `readme`)
- Test: `skills/document-drift/tests/test_dd_run.py`, `tests/test_dd_dispatch.py`

**Interfaces:**
- Consumes: Tasks 1 to 4.
- Produces:
  - `dd_run.readme_wanted(inventory, config) -> bool`: `config["readme"]` and no entry of `inventory["docs"]` equal to `readme.md` case-insensitively (root only, no slash). `stage_start` records `readme` in `preflight.json`, prints `readme: yes|no`, runs the full step list when it is true (the `NO_DOCS` message only when it is false and there is no doc), and after the dispatch step calls `dd_areas.run` then `dd_dispatch.plan_sheets`.
  - `stage_compose(root, workdir, *, retried, given) -> int`: `_resume` with stage `start` required (`verify` and `finish` refuse when `readme` and the stage is not past `compose`: message `compose has not run; run --stage compose first`); refuses with exit 2 and `nothing to compose: this run writes no README` when `readme` is false; `_outputs_or_retry` over role `sheet`; `dd_sheets.run`; with at least one valid sheet, `dd_dispatch.plan_readme` and the plan line; else `plan-readme.json` `[]` and the message `readme: no sheet; nothing to compose`; records `stage: compose`.
  - `dd_dispatch.plan_readme(root, workdir, config) -> list[PlanEntry]`: one entry `r001`, role `readme`, model `models.readme`, prompt `prompts/readme-r001.md` rendered from `readme.md` with `repo`, `name`, `description`, `sheets`, `unchecked`, `readme_lines`, `output`. `name` is the manifest name `dd_inventory._manifest_name` finds for the first project file that has one, else the root directory's name; `description` the manifest's description or the text `(the manifest has no description)`. `sheets` renders every entry as the spike did: `- <id> <kind> \`<name>\`[, parent \`<p>\`]: <summary>[; default \`<d>\`]; <defined_at>[ (filled from the scan)]` and `- <id>: <statement> (<evidence>)`, hidden entries left out.
  - `validate_readme(obj) -> list[str]`: shape only (`text` a string, `claims` a list of objects with int `start_line`, `end_line` and list `cites`). The citation check is Task 6.
  - `stage_verify`: `_failed` over `plan-docs.json` roles `review`, `gap` and, when `readme`, `plan-readme.json` role `readme`, all in one `retry.json`. `stage_finish`: with `readme`, the `_no_docs` early exit is skipped.

- [ ] **Step 1: Write `prompts/readme.md`** from spec 6.1 and 6.2 (the spike's second draft is the structure): the mandatory lines; the sheets; the unchecked areas; the README rules verbatim from spec 6.2; the output shape of spec 6.3; the receipt.
- [ ] **Step 2: Write the failing tests** in `test_dd_run.py`, using its `_repo` helper plus a variant `_repo_no_readme` (the same files without `README.md`) and `tests/canned/small/sheets/a01.json` (a valid sheet for the small fixture, written in this task):
  - `test_readme_trigger_is_root_markdown_only` (Review Focus 1: `docs/README.md` alone triggers; `Readme.MD` at the root does not; `readme: false` in config does not);
  - `test_start_in_readme_mode_plans_sheets_and_prints_readme_yes`;
  - `test_start_with_no_doc_and_readme_runs_the_full_steps` (no `NO_DOCS` message; `patterns.json` and `areas.json` exist; the plan holds only sheet entries);
  - `test_compose_refuses_without_readme_and_before_start`;
  - `test_compose_retries_a_bad_sheet_then_plans_the_writer` (missing output: exit 3 with the sheet entry in `retry.json`; after `answer`, exit 0 with `plan-readme.json ... with 1 entries`; the prompt names `a01-s01`);
  - `test_compose_with_no_valid_sheet_plans_nothing` (`--retried` with the output still missing: the message, `plan-readme.json` `[]`, stage `compose`);
  - `test_verify_refuses_before_compose_in_readme_mode`.
  In `test_dd_dispatch.py`: `test_plan_readme_renders_sheets_and_name`, `test_validate_readme_shape`.
- [ ] **Step 3: Run** them. Expected: FAIL.
- [ ] **Step 4: Implement.** `compose` goes into `STAGES` between `start` and `verify`; `_resume`'s allowed stages become `start`, `compose`, `verify`.
- [ ] **Step 5: Run the tests, the full suite, ruff, mypy.** Expected: PASS; phase A fixtures have READMEs, so their goldens are unchanged except `preflight.json` (not a golden) and the `readme: no` line (assert it in `test_dd_run`'s existing start test).
- [ ] **Step 6: Commit** `feat(document-drift): README trigger, compose stage, writer plan`.

---

### Task 6: Citation check, statements and README verifier batches

**Confidence:** 90%. The spike ran the check and the splitter on two real writer outputs (spec 15); the statement-level rules are spec 6.4 and 6.5 as amended.

**Files:**
- Create: `skills/document-drift/scripts/dd_readme.py` (check half), `skills/document-drift/prompts/verify-readme.md`
- Modify: `skills/document-drift/scripts/dd_dispatch.py` (`plan_verify_readme`, `validate_readme_verdicts`, `_problems` for `statements` batches, `collect_verdicts`), `skills/document-drift/scripts/dd_run.py` (`stage_verify` calls `dd_readme.check_step` after `dd_checks.run`)
- Test: `skills/document-drift/tests/test_dd_readme.py`, `tests/test_dd_dispatch.py`, `tests/test_dd_run.py`

**Interfaces:**
- Consumes: `sheets.json`, `readme/r001.json`, `edits.json` and `plan-verify.json` as `dd_checks.run` left them.
- Produces:
  - `dd_readme.check(output, sheets, readme_lines) -> tuple[list[str], dict]`: the invalid problems (spec 6.4's first bullet) and, when there are none, the `readme.json` content with claims repaired (`cites_added`), `cited_unnamed` counted, statements split (spec 6.5: item with nested lines, table row, paragraph, fence; headings, table header and separator rows and blank lines are not statements), each statement's `cites` the claim's surface entries its lines name plus all its behaviours, and `prereject` set for a hidden name in a span or a guarantee word outside a fence. Naming is spec 6.4's loose match: the name without a `$` prefix equal to a span by `norm`, or present in the lines as text.
  - `dd_readme.check_step(root, workdir, config, failed: frozenset[str]) -> dict | None`: None when `plan-readme.json` is empty or the writer's entry is in `failed` (summary reason `no writer output`); else runs `check`, writes `readme.json`, appends the `create` edit to `edits.json` and the `readme-rejected` human items for pre-rejections, then calls `dd_dispatch.plan_verify_readme`. An invalid output raises nothing: it writes `readme.json` with `"invalid": [problems]` and no statements, and no batches.
  - `dd_dispatch.plan_verify_readme(root, workdir, statements, config) -> list[PlanEntry]`: statements without `prereject`, grouped by `section` in README order, batches of `caps.readme_batch`, entries `vNN` continuing after the existing `plan-verify.json` ids, key `statements`, prompt from `verify-readme.md` with `repo`, `batch`, `statements` (each: id, section, lines, text in a fence, the cited entries one per line, the README around it with 10 lines of context, numbered), `output`; appended to `plan-verify.json`.
  - `validate_readme_verdicts(obj, expected_ids)`: as `validate_verdicts` with key `statement`. `collect_verdicts` routes `statements` batches into `readme` and `readme_unverified`.

- [ ] **Step 1: Write `prompts/verify-readme.md`** from spec 7 (the spike's draft is the structure).
- [ ] **Step 2: Write the failing tests** in `test_dd_readme.py` on hand-written `sheets` dicts and writer outputs:
  - `test_valid_output_has_no_problems_and_statements_in_order` (a README with a paragraph, a list with a nested line, a table, a fence: kinds, lines, sections, ids `r-s001`...);
  - `test_first_line_must_be_a_heading_and_length_capped`;
  - `test_fence_lines_need_a_claim` and `test_overlapping_claims_are_invalid` (Review Focus 3);
  - `test_unknown_cite_is_invalid`;
  - `test_naming_an_uncited_entry_adds_the_cite` (`cites_added` 1 and the claim's `cites` grown);
  - `test_cited_but_unnamed_is_counted_not_removed`;
  - `test_hidden_name_rejects_the_row_not_the_table` (Review Focus 4: 30 rows, one naming a hidden entry: that statement has `prereject`, the others none);
  - `test_guarantee_word_prerejects_outside_fences`;
  - `test_statement_cites_are_the_named_surface_entries_plus_behaviours`;
  - `test_dollar_prefixed_env_name_counts_as_named`.
  In `test_dd_dispatch.py`: `test_plan_verify_readme_batches_by_section_and_continues_ids` (existing `v01`, `v02` from edits; README statements become `v03`...; a batch never mixes sections; `caps.readme_batch` 2 splits a 3-statement section), `test_validate_readme_verdicts`, `test_collect_verdicts_routes_statement_batches`. In `test_dd_run.py`: `test_verify_in_readme_mode_checks_the_writer_output_and_plans_batches` (with `tests/canned/small/readme/r001.json` written in this task: `edits.json` holds the `create` edit, `plan-verify.json` the statement batches, the line count printed includes them) and `test_invalid_writer_output_is_retried_then_no_readme`.
- [ ] **Step 3: Run** them. Expected: FAIL.
- [ ] **Step 4: Implement.** The sentence is never split (spec 6.5). A nested list line is one starting with whitespace directly under an item.
- [ ] **Step 5: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 6: Commit** `feat(document-drift): README citation check, statements and verifier batches`.

---

### Task 7: Apply, commit and `--check` for the README

**Confidence:** 90%. The removal rules ran on the spike's README (15 statements removed, no broken prose).

**Files:**
- Modify: `skills/document-drift/scripts/dd_readme.py` (apply half), `skills/document-drift/scripts/dd_run.py` (`stage_finish`, `_would_apply`), `skills/document-drift/scripts/dd_commit.py` (`render_bullet` `create`, `run` groups and staging, `collect_human` `readme-rejected` from verdicts and `no-home` suppression), `skills/document-drift/scripts/dd_apply.py` (`apply_edits` leaves `r001` alone; nothing else)
- Test: `skills/document-drift/tests/test_dd_readme.py`, `tests/test_dd_commit.py`, `tests/test_dd_run.py`

**Interfaces:**
- Produces:
  - `dd_readme.apply(root, workdir) -> dict | None`: from `readme.json` and `verdicts.json` (`readme`, `readme_unverified`), removes every statement that is pre-rejected, rejected, unsure or unverified, whole (spec 8), collapses a table left with only its header and separator, a section left with only its heading, and blank-line runs; with no accepted statement returns None and writes nothing; else writes `README.md` (LF, trailing newline), updates `applied.json` (`applied` gains `r001`, `readme` set) and returns the `readme` record.
  - `dd_commit.render_bullet` handles `type == "create"`; `run` puts a `create` edit in `additions`, stages `README.md`, and makes the additions commit even when no other doc is left to stage (the existing `--allow-empty` rule does not apply: the README is staged); `collect_human` adds `readme-rejected` for every `reject` and `unsure` in `verdicts.json["readme"]` (text the statement's text, evidence the reason) and leaves `no-home` out when `applied.json["readme"]` is set (the README is where those names went; spec 2's "other docs reviewed in the same run" keeps every other human item).
  - `dd_run.stage_finish`: after `dd_apply.apply_edits`, `dd_readme.apply` under the same `edits_at_risk`; `_would_apply` is also true when `readme.json` has a statement that is neither pre-rejected nor rejected, unsure or unverified. Under `--check`, `dd_summary`'s planned edits list the `create` bullet (Task 8 renders it; this task asserts the exit code and that no `README.md` exists).

- [ ] **Step 1: Write the failing tests**: in `test_dd_readme.py` `test_apply_removes_items_rows_paragraphs_and_fences_whole`, `test_apply_collapses_empty_tables_and_sections`, `test_apply_with_nothing_accepted_writes_nothing`; in `test_dd_commit.py` `test_create_bullet_and_additions_commit_stage_the_readme` (a run with one `create` edit and no other edit: one additions commit, `README.md` in it, the bullet exact), `test_readme_rejected_and_no_home_suppressed_in_human_list`; in `test_dd_run.py` `test_finish_writes_the_readme_and_commits_it` (small fixture without README, canned sheets, writer output and verdicts with one reject: `README.md` on the drift branch lacks the rejected row, `commits.json` has the additions commit, `applied.json["readme"]["removed"] == 1`, the human list has one `readme-rejected`) and `test_check_mode_lists_the_readme_and_writes_nothing` (Review Focus 5).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): write and commit the README`.

---

### Task 8: Summary section

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/scripts/dd_summary.py` (`_readme_section`, `_result_section`'s planned edits, `render`)
- Test: `skills/document-drift/tests/test_dd_summary.py`

**Interfaces:**
- Produces: a `README` section after `Gaps` when `preflight.json` has `readme` true, with spec 10's lines exactly: `areas: <n> (<lines> lines, area_lines <n>)`, `sheets: <n> valid, <n> unchecked (<id>: <why>, ...), <n> retried` (retried: sheet entries present in `retry.json`), `hints: <n> accounted for, <n> filled from the scan`, `writer: <n> attempt(s)`, `statements: <n> proposed, <n> accepted, <n> rejected, <n> unsure, <n> unverified`, `written: README.md, <n> lines` or `written: none (<reason>)` with the reasons `no valid sheet`, `no writer output`, `invalid writer output`, `no accepted statement`, `check mode`. `Result` names `README.md` among the committed files; under `--check` the planned edits include the `create` bullet.

- [ ] **Step 1: Write the failing tests**: `test_readme_section_counts` (a workdir built with the module's `_wd` helper plus `areas.json`, `sheets.json`, `readme.json`, `verdicts.json`, `applied.json`), `test_readme_section_reasons_for_none`, `test_readme_section_absent_without_readme`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): README summary section`.

---

### Task 9: The `py-cli-nodocs` fixture, canned outputs and goldens

**Confidence:** 90%. The canned verdicts must carry the statement ids the splitter produces from the canned writer output; the splitter is deterministic (the spike produced the same 228 ids on every rerun of the check over one writer output, spec 15), so Step 1 runs `start`, `compose` and `verify` on the fixture with the canned sheets and writer output, reads `readme.json`, and writes the verdicts and the planted list from the ids it finds.

**Files:**
- Create: `skills/document-drift/tests/fixtures/corpus/py-cli-nodocs/{history.yaml,planted.json,files/...}`, `tests/canned/py-cli-nodocs/state1/{sheets,readme,verdicts}/...`, `tests/canned/py-cli-nodocs/state1-invalid/sheets/a02.json`, `tests/golden/py-cli-nodocs/state1/...`
- Modify: `skills/document-drift/tests/dd_corpus.py` (`FIXTURES`, `ROLE_DIRS`, `answer`, `evaluate`), `tests/test_dd_corpus.py`, `tests/test_dd_goldens.py`

**Interfaces:**
- Produces: the fixture (spec 13): a Python CLI `kv` with `init` and `sync` subcommands, flags `--force` and `--dry-run` with help text, a hidden `--legacy` (`help=argparse.SUPPRESS`), a deprecated `migrate` command (a `# deprecated` marker within three lines), env vars `KV_HOME` and `KV_TOKEN` read through a helper by prefix, a config file `settings.toml` with two keys, a Flask route `/items/<key>`, a `Store` class and a `_rotate` helper, `pyproject.toml` with `[project.scripts]`, and no `.md` file. Two areas at `area_lines` 5000 (one is enough code; set `area_lines: 60` in the fixture's `.document-drift.yaml` to get two). `answer` learns roles `sheet` (dir `sheets`) and `readme` (dir `readme`), and matches statement batches by statement id against `verdicts/` files. `evaluate` learns `readme:names:<name>` (the drift branch's `README.md` holds the name in an inline-code span), `readme:absent:<name>`, and `human:readme-rejected` on `README.md` with the item's line.
- The planted list: `init`, `sync`, `--force`, `--dry-run`, `KV_HOME`, `KV_TOKEN`, both config keys, the route and `Store` expect `readme:names`; `--legacy`, `migrate` and `_rotate` expect `readme:absent`; one canned statement (a wrong default for `--dry-run`) expects `human:readme-rejected`; `a02`'s first canned sheet is invalid (a missing hint) so the retry path runs, and the `state1-invalid` variant drives `test_invalid_output_exits_3_then_retried_marks_unchecked` for a sheet.

- [ ] **Step 1: Write the fixture files, `history.yaml` (one commit, tag `state1`) and the canned sheets and writer output**, then run the pipeline by hand (`run_fixture` with the verdicts missing) to read `readme.json`'s statement ids; write the canned verdicts and `planted.json` from them.
- [ ] **Step 2: Extend `dd_corpus`** and add the fixture to `FIXTURES`; run `pytest skills/document-drift/tests/test_dd_corpus.py -k nodocs -v`. Expected: every planted item passes; the retry test passes for the sheet.
- [ ] **Step 3: Goldens.** Run `pytest skills/document-drift/tests/test_dd_goldens.py -k nodocs`; it fails for the missing golden directory; generate it the way the phase A goldens were generated (see that test's docstring), read `README.md`, `readme.json`, `sheets.json`, `edits.json` and `commit-msg-additions.txt` by hand against the spec, then rerun. Expected: PASS.
- [ ] **Step 4: Run the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `test(document-drift): py-cli-nodocs fixture, canned outputs and goldens`.

---

### Task 10: Live harness

**Confidence:** 92%.

**Files:**
- Modify: `skills/document-drift/tests/dd_live_run.py` (`ROLES`, `PLAN_LINE`, `drive`, `--resume` choices, `render_row` notes)
- Test: `skills/document-drift/tests/test_dd_live_run.py`

**Interfaces:**
- Produces: `drive` reads `preflight.json`'s `readme` after `start`; when true it runs `compose` with the retry rule, dispatches `plan-readme.json`, then `verify` as today. `--resume compose` is accepted. `ROLES` gains `sheet` and `readme`. The row's `agents` cell counts sheet and writer calls in its existing per-role grammar (extend the cell to `review/gap/verify/sheet/readme` when any of the last two is non-zero, else unchanged) and the notes say `readme: <n> lines` when `applied.json["readme"]` is set.

- [ ] **Step 1: Write the failing tests** with the file's fake-stage pattern: `test_drive_runs_compose_and_the_writer_wave_in_readme_mode`, `test_drive_skips_compose_without_readme`, `test_resume_compose_reuses_the_sheet_wave`, `test_row_counts_sheet_and_readme_calls`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, the full suite, ruff, mypy.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(document-drift): live harness drives the compose stage`.

---

### Task 11: Docs

**Confidence:** 95%.

**Files:**
- Modify: `skills/document-drift/SKILL.md` (the `compose` step between steps 2 and 3, with the `readme: yes` rule and the exit-3 rule; the `create` bullet in "What the user gets"; the new config keys), `docs/architecture.md` (the stage table row, the three modules, the three prompts), `README.md` (the skill's one-paragraph description mentions the README), `docs/superpowers/specs/2026-10-10-document-drift-agentic-design.md` (§4's "Creating doc files" and N11's row point at the phase B spec), `docs/evaluation-log.md` (the README columns `areas`, `sheets`, `statements accepted/rejected/unsure`, `readme lines` for phase B rows, added to the phase A table's legend)
- Check: `python scripts/dd_check_skill.py` from the skill directory stays clean.

- [ ] **Step 1: Write the doc changes.**
- [ ] **Step 2: Run** the SKILL linter and the full suite. Expected: clean.
- [ ] **Step 3: Commit** `docs(document-drift): phase B stages, config and commit bullet`.

---

### Task 12: Live run and the evaluation row

**Confidence:** 90%. The spike already ran every agent kind on better-memory (spec 15); the unknown is only the owner's repository.

**Files:**
- Modify: `docs/evaluation-log.md`, the phase B spec's section 16 (B2, B4 final status)

- [ ] **Step 1:** Run `python tests/dd_live_run.py <repo the owner names> --full --log ../../docs/evaluation-log.md` from the skill directory; on a crash, fix, record the fix as a memory observation, and `--resume` at the failed stage.
- [ ] **Step 2:** Relay the summary and the branch to the owner; the owner judges the README and fills `judged acceptable`.
- [ ] **Step 3:** Record the row's figures in spec 16 and commit `docs(document-drift): phase B live run`.
