# document-drift phase B: no-README mode

Provenance: brainstormed 2026-10-13 after phase A (`docs/superpowers/specs/2026-10-10-document-drift-agentic-design.md`, PRs #23 to #25) ran twice on the owner's `better-memory` repository. This spec settles the open points of that spec's section 12 and replaces it. Sections of the phase A spec are cited as "A §n".

## 1. Purpose and scope

A repository without a README is one nobody can check docs against. Phase B writes one from the code, in the same run, on the same branch and with the same checks as phase A's edits: agents that read the repository and write only their own output file, a script that validates every output, a verifier agent that judges every statement, and a commit the owner reviews.

In scope: the trigger, the split of the source into areas, one fact sheet per area, one README composed from the sheets, verification of every README statement, the commit, and how later runs treat the README. Out of scope: any other new doc file (A §N3 stands: phase B's README is the one file the skill creates), rewriting an existing README, docs in languages the pattern scan does not know (A §8.1), and a README over `readme_lines`.

## 2. Trigger

`start` sets `"readme": true` in `preflight.json` when the inventory (A §5.1) has no in-scope doc at `README.md` in the repository root, matched case-insensitively. A README that exists but is excluded, carries `drift-ignore-file`, or lies outside the root does not count: the skill may not edit it, so it writes none either. *Amended 2026-10-14: as built, the trigger is that no tracked file at the root is named `README.md`, matched case-insensitively, whether or not that file is in scope; the inventory's scope does not enter into it.* The config key `readme: false` turns phase B off.

Other in-scope docs are reviewed by phase A in the same run. A later run on a repository whose README the skill wrote treats it as any doc (section 9); `readme` is true again only when the README is gone.

## 3. Stages and files

Phase A's stages keep their flags, exit codes and refusals (A §9, `SKILL.md`). With `readme` true the run has one more stage and one more agent wave:

| Stage | Phase B work | Writes | Agents dispatched by the session |
|---|---|---|---|
| `start` | the area split (section 4); one plan entry per area with role `sheet` | `areas.json`, `prompts/sheet-aNN.md`, the entries in `plan-docs.json` | sheet agents, in the same wave as the review and gap agents |
| `compose` (new) | validates the sheet outputs with the exit-3 retry, fills the hints still missing after it (section 5.4), writes the writer's prompt | `sheets.json`, `plan-readme.json`, `prompts/readme-r001.md` | one writer agent (`plan-readme.json`) |
| `verify` | validates the writer's output with the exit-3 retry, runs the citation check, splits the README into statements, adds them to the verify batches | `readme.json`, and the usual `edits.json`, `plan-verify.json`, `prompts/verify-vNN.md` | verifier agents, as in phase A |
| `finish` | removes rejected statements, writes `README.md`, stages it in the additions commit | `applied.json`, `commits.json`, `summary.md`, as in phase A | none |

`compose` takes the same flags as the other stages (`--retried`, `--full`, `--check`, `--workdir`, `--date`) and refuses with exit 2 when they differ from the ones recorded at `start`, when `start` has not run, or when `readme` is false ("nothing to compose"). The session runs it only when `start` printed `readme: yes`; the live harness (`tests/dd_live_run.py`) gains the step and `--resume compose`. *Amended 2026-10-14: the writer's prompt file is `prompts/readme-r001.md`, rendered from the template `prompts/readme.md`; with no valid sheet, `compose` writes `plan-readme.json` as `[]` rather than no file.*

Order of a full run: `start`, wave (review, gap, sheet), `compose`, wave (writer), `verify`, wave (verifiers), `finish`. Under `--check`, `finish` reports the README it would have written (its statements, in the commit-bullet grammar) and writes nothing.

## 4. Areas

`dd_areas` splits the indexed source files (the files A §8.1's pattern scan reads, so tests, vendored and generated files are already out) by line count against `area_lines` (default 5,000):

1. Every top-level source directory is an area. The project files (the manifests and build files of A §8.1: `pyproject.toml`, `setup.cfg`, `package.json`, `Makefile`, `justfile`, `Taskfile.yml`, Dockerfiles, `.env.example`, and the root's loose source files) form one area, `a01`.
2. An area over budget is replaced by its subdirectories, each an area, plus one area for its loose files; the rule applies again to any of those over budget.
3. Loose files over budget are cut into consecutive groups of whole files in path order, each within budget; a single file over budget is an area on its own.
4. Sibling areas (same parent directory, the root included, so small top-level directories merge too) are merged in path order while the merged size stays within budget; `a01` takes part like any area.

`areas.json` is `{"area_lines", "areas": [{"id", "files": [{"path", "lines"}], "lines", "hints": [...]}]}` with ids `a01`, `a02`, ... in path order and, per area, the pattern-scan hints whose `path` is in the area: `{"kind", "name", "parent", "path", "line", "hidden"}`. *Amended 2026-10-14: a hint carries the pattern-scan record's keys, so its file is `file`, not `path`.* A hint whose file is in no area (a project file the scan read but the inventory did not index) goes to `a01`.

## 5. Fact sheets

### 5.1 Prompt

`prompts/sheet.md`, rendered per area with the placeholders `repo`, `area`, `files` (one line per file with its line count), `hints` (one line per hint, `- flag --force (parent agentcore init) src/cli.py:88` or `hidden`), `output`. The agent reads every file of its area with Read, Grep and Glob, writes exactly one file with Write, runs no command, writes no helper script (the mandatory lines of A §7.4 verbatim). It may open files outside the area to settle a reference, never to add an entry: an entry's `defined_at` is in the area.

### 5.2 Output

```json
{
  "area": "a03",
  "surface": [
    {"kind": "command", "name": "sync", "parent": null,
     "summary": "pulls the remote state into the local store",
     "default": null, "defined_at": "src/app/cli.py:41",
     "user_facing": true, "hidden": false}
  ],
  "behaviours": [
    {"statement": "the loader (`ConfigLoader.load`) reads `config.yaml` from the current directory before the user file",
     "evidence": ["src/app/config.py:17"]}
  ],
  "dismissed": [
    {"hint": "flag --legacy", "why": "help=argparse.SUPPRESS"}
  ]
}
```

- `surface` holds what a user can reach: the pattern scan's kinds (`command`, `flag`, `env`, `config`, `route`, `tool`, `param`, `script`, `entry`) plus `function`, `class` and `module` for a library's public API. `kind` and `name` are as the scan would write them (A §8.2's normalisation decides matches); `parent` is the command, tool or parser a flag or parameter belongs to; `summary` is one line; `default` is the default value as a string, or null; `defined_at` is one `path:line`; `hidden` is true when the code hides the name (A §8.1's rule).
- `behaviours` are the statements a README needs that no name carries: what the project does, what a command does to the data, where files are read from and written to, what happens on failure, what runs first. Every statement names the definition it describes in an inline-code span, in the wording the README will keep (so the README anchors, A §5.5). `evidence` is one or more `path:line`.
- `dismissed` lists the hints that are not surface entries, each with its reason (hidden, deprecated, internal, a false match of the scan).

### 5.3 Validator

`dd_sheets.validate(sheet, area, ctx)` returns the problems of one output; any problem makes it invalid and it goes through the exit-3 retry of A §7.4:

- shape: the three lists present, every key present with the right type;
- each surface entry: `kind` in the list above; `name` not empty; `defined_at` a `path:line` whose file is in the area and tracked at HEAD, whose line is within the file, and whose name is **at** that place: some token of the name of three or more characters, other than an interpreter or package-manager word (`python`, `node`, `npm`, `npx`, `uv`, `pip`) or a leading directory, appears within 3 lines of it, or the name, with a leading `python -m ` dropped and dots read as slashes, is the file's own path without its extension (a script or module names its file, and its line 1 is a valid place; *amended 2026-10-14: the three-character floor applies to picking tokens out of a multi-token name, and a name with no such token, such as `kv` or `gh`, is matched whole within 3 lines*); `summary` one line;
- each behaviour: a one-line `statement` with at least one inline-code span and no guarantee word (A §7.2's list); `evidence` not empty, each entry resolving as `defined_at` does;
- no two surface entries with the same `(kind, norm(name), parent)`, where a route's parent is its HTTP method (so `GET` and `POST` of one path are two entries);
- every hint of the area is a surface entry (matched by `(kind, norm(name), parent)`, flags keeping their dashes) or a `dismissed` entry naming it.

One repair, not a problem: a surface entry that matches a hint takes the hint's `hidden` value when the two differ, counted as `hidden corrected`. The scan reads the hiding from the code (`argparse.SUPPRESS`, `hidden=True`), and the spike's sheet agent marked a flag with a help string hidden, which cost five true README rows.

### 5.4 Retry, fill and caps

*Amended 2026-10-14, the strict-then-fill rule as built: on the first `compose` pass a sheet missing hints is invalid and goes to the retry; on the `--retried` pass a sheet that is valid in every other way is accepted and the missing hints are filled by script.* A sheet still invalid after the retry makes its area **unchecked**: its names reach no README and the summary lists the area. A valid sheet missing hints after the retry (only possible when the retry output is valid in every other way but still short) gets them **filled** by script: one surface entry per missing hint with the scan's kind, name, parent, `defined_at` and `hidden`, the summary `from the pattern scan`, `default` null, `user_facing` true. Filled entries are counted in the summary and carry `"filled": true` so the writer can tell them apart.

`caps.sheet_agents` (default 12) bounds the wave: areas past the cap, smallest first, are unchecked by the cap, as review units are in A §6.4. `sheets.json` is `{"sheets": {"a01": {...}, ...}, "unchecked": [{"area", "why"}], "filled": n}`, each entry carrying its id (`a03-s12` for the twelfth surface entry of `a03`, `a03-b04` for a behaviour) for the writer to cite.

## 6. The README writer

### 6.1 Prompt

`prompts/readme.md`, rendered once with `repo`, `name` and `description` (from `a01`'s project-file entries: the manifest's name and description, or the repository directory name and nothing), `sheets` (every valid sheet's entries with their ids, in area order, filled entries marked), `unchecked` (areas with no sheet, so the writer says nothing about them rather than guessing), `readme_lines`, `output`. The writer may open files to settle wording and never to add a fact: every statement cites a sheet entry.

### 6.2 README rules

Sections in this order, each omitted when no entry supports it: what the project is; install; run; commands and flags; configuration and environment variables; interfaces (routes, MCP tools, public API); files read and written. Surface entries go in lists or tables, one row per entry, with the summary and the default; behaviours become list items or one-sentence paragraphs in the section they belong to (a paragraph is one sentence, so a rejected statement costs one sentence, section 8). Every list item, table row and paragraph names the definition it rests on in an inline-code span once, as the sheet wrote it, preferring a public name (a command, a tool, an exported function) and naming a private helper only when no public name is what the statement describes; a run of statements about one definition names it in the first and says "it" after. Hidden entries, dismissed hints and unchecked areas never appear. No statement about intent, roadmap, quality or comparisons, no guarantee word, no fact a sheet does not carry, no badge, no licence paragraph unless a project file names the licence. At most `readme_lines` lines (default 300): a large project gets the tables and one sentence per behaviour.

### 6.3 Output

```json
{
  "text": "# myproject\n\nmyproject syncs ...\n",
  "claims": [
    {"start_line": 3, "end_line": 3, "cites": ["a01-b01"]},
    {"start_line": 12, "end_line": 14, "cites": ["a03-s12", "a03-s13"]}
  ]
}
```

A claim covers whole lines of `text` (1-based) and cites the entries those lines rest on. Headings, blank lines and fence lines need no claim; a fence's content lines do (a command example rests on the command's entry).

### 6.4 Citation check

`dd_readme.check(output, sheets, config)` runs in `verify`. A writer call costs minutes and dollars (section 16), so the check repairs what a script can repair and rejects statements rather than the whole output where it can; only a structural problem makes the output invalid, with the exit-3 retry, and an output still invalid after the retry means no README (summary: `readme: not written (<problem>)`):

- invalid: the first line is not a level-one heading; `text` has more than `readme_lines` lines; a line outside headings, blank lines and fence markers is in no claim or in two; a claim cites nothing or cites an id not in `sheets.json`;
- repaired and counted: a claim's lines name (in an inline-code span, by A §8.2's normalisation) a surface entry the claim does not cite: the id is added to the claim (`cites added`); a claim cites a surface entry none of its lines name (the name without a `$` prefix, as a span or as text): counted as `cited unnamed`, nothing removed;
- rejected before verification, as a Human-decision item `readme-rejected` with the check's reason, judged on the statement's own lines (section 6.5), never on the whole claim: a statement naming a hidden entry in a span; a statement with a guarantee word outside a fence.

*Amended 2026-10-14: structural problems go through the exit-3 retry via `dd_dispatch._problems`. The hidden-name rule as built: a span pre-rejects its statement when the entries it resolves to that the statement's claim cited explicitly include a hidden one, or when every entry of that name is hidden. The guarantee check ignores inline-code spans, so a flag named `--always-x` does not pre-reject.*

A writer may make one claim per table or section (the spike's second writer made 26 claims for 299 lines, the first 100), so every rule that removes text looks at statements, not claims; a statement's cited entries are the claim's surface entries its own lines name plus all the claim's behaviours.

No line-length rule: the README is read rendered, and the commit grammar's 160-character cut applies to commit lines only.

### 6.5 Statements

The check then splits the README into **statements**, the units the verifier judges and `finish` can remove: each list item (with its nested lines), each table row, each paragraph, and each fence, as one statement each, with its lines and the ids of the claims it lies in. `readme.json` is `{"text", "claims", "statements": [{"id": "r-s01", "start_line", "end_line", "section", "kind", "cites"}]}`. A heading, a table's header and separator rows, and a blank line are not statements. Sentences are not split: the spike showed that cutting one sentence out of a paragraph leaves prose that no longer reads ("It is built with hatchling" after its subject went), and that a splitter trips on version numbers; the writer's one-sentence paragraphs keep the unit small instead.

## 7. Verification

Statements are grouped by section into batches of at most `caps.readme_batch` (default 15: a table row is a short judgement, and the spike's batches of 10 ran under 30 seconds) and appended to `plan-verify.json` with role `verify` and the prompt `prompts/verify-readme.md`: for each statement its text, its lines with 10 lines of context, the cited entries (kind, name, summary, `defined_at` or evidence), and read access to the repository. The verifier accepts a statement only when it is true of this repository's code, supported by the code at the cited places (not merely by the sheet), and not about intent, other software or history. It writes the batch's verdicts as in A §9.2 (`{"statement": id, "verdict": "accept" | "reject" | "unsure", "reason"}`); the verdicts land in `verdicts.json` under `readme`.

A rejected or unsure statement is a Human-decision item of kind `readme-rejected` (`- README.md:<line> readme-rejected: <statement> (<reason>)`). A batch whose output is invalid after the retry leaves its statements **unverified**: they are removed as rejected ones are, and counted.

The README is one proposed edit in `edits.json`: `{"id": "r001", "doc": "README.md", "type": "create", "source": "readme", "statements": n}`, so the proposed, verdict and applied counts of A §9.5 see it as one edit, and the `kept`/`dropped` grammar of A §9.1 does not apply to it (the citation check is its script check).

## 8. Finish: apply and commit

`dd_readme.apply` builds the final text from `readme.json` and the verdicts: an accepted statement stays; a rejected, unsure or unverified one goes whole (a list item with its nested lines, a table row, a paragraph, a fence; a table left without rows, a section left with only its heading, and a blank-line run longer than one, are collapsed). No accepted statement at all means no README (summary: `readme: not written (no accepted statement)`). Otherwise `README.md` is written to the working tree with a trailing newline, recorded in `applied.json` as `{"applied": ["r001"], "readme": {"lines", "statements", "removed"}}`, and staged in the additions commit (A §9.4) with the bullet

```
- README.md:1 create readme (<n> statements from <n> sheets, <n> removed)
```

*Amended 2026-10-14: the bullet's statement count is the total at check time; `applied.json["readme"]["statements"]` is the kept count.* A `create` edit never goes in the corrections commit; a run with no other applied edit still makes the additions commit for it. Under `--check` the statements are listed instead and nothing is written.

## 9. Later runs

The README the skill wrote is an ordinary in-scope doc from the next run on: phase A reviews it, its inline-code spans anchor (A §5.3), the checkability section reports it, and the notice loop applies. Its first run is `first` for that doc as for any new doc. Nothing in the workdir marks it as generated; the commit bullet and `Drift-Run` trailer are the provenance.

## 10. Summary

`summary.md` gains a `README` section after `Gaps`, present when `readme` is true:

```
README
areas: 7 (25,956 lines, area_lines 5000)
sheets: 6 valid, 1 unchecked (a05: invalid after retry), 2 retried
hints: 98 accounted for, 3 filled from the scan
writer: 1 attempt
statements: 61 proposed, 55 accepted, 3 rejected, 1 unsure, 2 unverified
written: README.md, 142 lines
```

or `written: none (<reason>)`. The `Result` section names `README.md` among the committed files.

## 11. Configuration

New keys of `.document-drift.yaml` (A §10), with defaults:

| Key | Default | Meaning |
|---|---|---|
| `readme` | `true` | phase B runs when the root has no in-scope README |
| `area_lines` | `5000` | the area budget of section 4 |
| `readme_lines` | `300` | the longest README the writer may produce |
| `caps.sheet_agents` | `12` | areas given a sheet agent per run |
| `caps.readme_batch` | `15` | README statements per verifier batch |
| `models.sheet` | `sonnet` | the sheet agents |
| `models.readme` | `opus` | the writer: one call, and composition is where quality shows |

The verifier model stays `models.verify`.

## 12. Errors and refusals

- `compose` with `readme` false, or before `start`, or with other flags than `start` recorded: exit 2, nothing written.
- A missing stage output (`areas.json` at `compose`, `sheets.json` at `verify`): exit 5, naming the file and the step, as in phase A.
- No valid sheet after the retry: `compose` writes `sheets.json` with every area unchecked and `plan-readme.json` as `[]` (amended 2026-10-14; first written as no file), and prints `readme: no sheet; nothing to compose`; `verify` and `finish` then run as in phase A and the summary says `written: none (no valid sheet)`.
- Writer output missing or invalid after the retry: no README, the reason in the summary; the rest of the run is unaffected.
- A statement the verifier marks unsure goes to the owner, never into the README.

## 13. Testing and validation

- Unit tests for `dd_areas` (the four rules on synthetic trees, the project-file area, hint assignment), `dd_sheets` (every validator rule, the fill, the cap), `dd_readme` (the citation check rule by rule, the statement split, the apply rules including collapsed tables and sections), `dd_commit` (the `create` bullet and the additions-only rule), `dd_summary` (the section), `dd_run` (the `compose` stage, its refusals, the exit-3 loop, `--check`).
- A fourth fixture, `py-cli-nodocs`: a small Python CLI with subcommands, flags, env vars read through a helper, a config file, a hidden flag, a deprecated command and an internal helper, no docs at all. Canned sheets (one of them invalid once, to drive the retry; one short of a hint, to drive the fill), a canned writer output, canned verdicts with one rejection. The planted list names what must reach the README and the decoys that must not; the replay asserts both and the commit grammar.
- The live harness drives the `compose` step and resumes at it.
- One live run on a repository of the owner's with no README, judged by the owner as the better-memory runs were, recorded in `docs/evaluation-log.md` with a README row (areas, sheets, statements, acceptance, cost). Phase B is done when that row has a judged acceptable figure.

## 14. Decisions made in the brainstorm

| Point | Decision | Alternatives rejected |
|---|---|---|
| Trigger | no in-scope root README, other docs reviewed in the same run (section 2) | zero in-scope docs only; zero docs plus a `--write-readme` flag |
| Verifying a new file | script citation check, then a verifier per section with one verdict per statement (sections 6.4, 7) | script only; verifier only |
| Citations | a side file with line-ranged claims; the README stays clean and names its definitions in spans (section 6.3) | inline HTML markers; markers stripped after verification |
| Hint rule | strict with one retry, then filled by script (section 5.4) | strict and then unchecked; soft from the start |
| Fixture | a new no-docs fixture plus one live run judged by the owner (section 13) | a derived fixture; fixture only |
| Writer's wave | a new `compose` stage between `start` and `verify` (section 3) | reusing the exit-3 retry round; a separate command |

## 15. Validation spike (2026-10-13)

Run on `better-memory` at `9d5be26` (22,615 indexed lines, 113 files), ignoring its README, with throwaway scripts and draft prompts (`sheet.md`, `readme.md`, `verify-readme.md`) that the implementation plan turns into the real ones. The spike's workdir is `.document-drift-b/` in that repository (excluded from git), with the README at `README-spike.md`.

| Step | Agents | Tokens | Time | Cost | Result |
|---|---|---:|---:|---:|---|
| Areas (section 4 as first written) | script | | | | 10 areas: 249, 4,236, 2,790, 4,879, 2,463, 4,440, 2,408, 28, 1,088, 34 lines; three tiny ones because rule 4 did not merge at the root (amended) |
| Sheets | 10 Sonnet | 2,298,000 | 15 to 202 s each, 4 in parallel | $3.80 | 400 surface entries (99 functions, 95 params, 37 classes, 33 routes, 30 env, 28 config, 26 flags, 22 tools, 15 scripts, 8 commands), 323 behaviours, 4 hidden; all 10 parsed |
| Validator (section 5.3 as first written) | script | | | | 4 sheets valid; 21 name-rule failures, 18 of them `python -m pkg.module` and `scripts/x.sh` names (rule amended, then 3 remain); 7 hints missed in 2 areas; 1 guarantee word; 1 duplicate route pair (`GET`/`POST`); 1 behaviour without a span. With the amended rule, strict-plus-retry retries 3 of 10 sheets |
| Writer | 1 Opus | 517,703 | 750 s | $3.47 | 293 lines (cap 300), 100 claims, 225 statements (132 table rows, 83 list items, 10 paragraphs); 777-line prompt |
| Citation check (section 6.4 as first written) | script | | | | 6 problems: a hidden flag named twice, one entry named without a cite, one 160-character line; under the first rules the whole output would have been retried (amended to repair and reject per statement) |
| Verifiers | 3 Opus, 10 statements each | 403,944 | 23 to 29 s | $0.88 | 22 accept, 2 reject, 0 unsure; both rejections right (a version floor called a "default"; a boto3 error that fires only on the agentcore path) |
| Removal | script | | | | list items and rows removed cleanly; a sentence cut from a paragraph left broken prose, and the splitter broke on `3.12` (amended: paragraphs are the unit, one sentence each) |

**Full run with the amended rules (same day).** The writer re-run on the amended prompt (section 6.2), the statement-level check, every verifier batch, the removal pass.

| Step | Agents | Tokens | Time | Cost | Result |
|---|---|---:|---:|---:|---|
| Writer | 1 Opus | 444,204 | 698 s | $3.24 | 299 lines, 26 claims (one per table or section), 228 statements (143 rows, 80 items, 5 paragraphs); prose reads as a README ("Its `setup` command wires it into Claude Code through hooks") |
| Citation check | script | | | | 0 invalid; 16 cites added; 5 statements pre-rejected for naming a hidden flag, all five wrong because the sheet had marked `--home` hidden against the code (amended: the hint's `hidden` wins); the first version of the check judged hidden names and unnamed cites per claim and pre-rejected 61 statements, whole tables among them (amended: per statement) |
| Verifiers | 22 Opus, batches of 15 | 6,687,000 | 11 to 67 s each, 4 in parallel | $9.98 | 213 accept, 10 reject, 0 unsure; the rejections are precise imprecisions (a flag that skips one check but not another, a hook list where three hooks do not record errors, a variable read only in one mode) |
| Removal | script | | | | 15 statements removed (10 rejected, 5 pre-rejected), 300 to 285 lines, no broken prose |

A full run on this repository is 10 sheet agents, 1 writer and 22 verifier batches: $17 ($3.80, $3.24, $9.98) and about 25 minutes of agent time, the writer alone taking 12 of them. Verification is the largest cost: a batch of 15 rows with context runs $0.04 to $0.88, the expensive ones being the batches whose statements cite many entries.

First read of the README (B2, by the spike's author; the owner judges the live run of section 13): accurate and complete as a reference (every command, flag, variable, tool and route, with defaults), and a maintainer would keep the tables; the prose carries the span rule's cost ("It (`_handle_init`) creates the episodic memory", private helpers as anchors), amended in section 6.2 to name once per statement and prefer public names.

## 16. Assumptions

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| B1 | A Sonnet agent can write a sheet for a 5,000-line area that passes the validator, and account for every hint, within one call | Measured (section 15): 10 of 10 sheets parsed, 7 of 10 pass the amended validator, the rest for 7 missed hints, 1 guarantee word, 1 duplicate; 202 s and $0.96 for the largest area | More retries and unchecked areas; `area_lines` comes down |
| B2 | Sheets carry enough to write a README a maintainer keeps: the sheet's summaries and behaviours, not the code, are what the writer composes from | Validated: the owner read the full run's README (section 15, 285 lines after removal) on 2026-10-13 and would keep it | The writer reads the code for facts after all, and the citation check cannot gate what it adds |
| B3 | An Opus writer keeps to the sheets and cites what it names, so the citation check rejects few outputs | Measured twice: 100 then 26 claims, 3 then 16 citation faults (all repairable), 0 invented facts in 247 verified statements; 750 and 698 s, $3.47 and $3.24 a call, so the check repairs and rejects per statement instead of retrying the output | A second writer call per run, and a README not written when both fail |
| B4 | Statements by list item, table row, paragraph and fence are units a verifier can judge and `finish` can remove without leaving broken prose | Measured: 15 statements removed from the full run's README with no broken prose; sentence removal failed in the first pass and was dropped in favour of one-sentence paragraphs | Rejected statements leave gaps a reader notices; the owner edits the README by hand once |
| B5 | A verifier can judge a README statement from the cited places and the code without the sheet's reasoning | Measured on 247 statements over two passes: 235 accept, 12 reject, 0 unsure; every rejection read as right; $9.98 for the full run's 22 batches | Verdicts drift towards `unsure`, and the README loses true statements to the owner's list |
| B6 | `readme_lines` of 300 fits the surface of a 25,000-line project as tables and one sentence per behaviour | Measured once: 293 lines for 22,615 lines of code with 389 user-facing entries, so the default holds with no room; a larger project needs the cap raised or the writer told to drop behaviours first | A truncated README, or the writer drops behaviours to fit; the default moves |
| B7 | Later runs treat the written README as any doc without a special case | Follows from A §5 and §7 by construction | A README that drifts unseen, the thing phase A exists to prevent |
