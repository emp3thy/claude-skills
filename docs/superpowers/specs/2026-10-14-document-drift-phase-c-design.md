# document-drift phase C: script edits and narrower reading

Provenance: brainstormed 2026-10-14 after phase B (`docs/superpowers/specs/2026-10-13-document-drift-phase-b-design.md`, PR #26) and the first live runs of phase A on `better-memory` and on this repository. Sections of the phase A spec are cited as "A §n", of the phase B spec as "B §n".

## 1. Purpose and scope

The review agents are the cost of a run: 80% of the claude-skills run ($6.21 of $7.72 over 16 Sonnet calls averaging 750k tokens) and, on README runs, the verifiers behind them. Classifying every review edit of the two real runs (87 on `better-memory`, 18 here) showed that 40 of the 87 were a `path:line` citation that had moved, four of them botched by the agent (a second reference dropped while fixing the first), about one in eight was a default, count or enumeration the code defines, and the rest was prose only an agent can judge.

Phase C makes the mechanical classes script work and gives the agents the facts and the code they need in the prompt, so a run costs less and the agents' worst class of mistake disappears. In scope: citation checks against the definition index (section 2), scanned facts checked in doc tables and handed to every agent as hints (section 3), the review prompt carrying the code ranges inline with a reading rule (section 4), a third commit for script edits, the summary, the fixture and the measurement. Out of scope: prose rewrites by regex, a cheaper model for the review agents (measured separately; the all-Sonnet fixture run is in `docs/evaluation-log.md`), and any change to the sheet or writer prompts of phase B.

Quality bar: every script edit passes the same script checks as an agent edit, lands on the same branch, and is a reviewable bullet; nothing the agents find today is lost, because the agents keep every claim the scripts do not settle and get the scripts' results as hints.

## 2. Citation checks

### 2.1 Citation tokens

`dd_extract` recognises a path reference ending in `:N`, `:N-M` or `#LN` (`_LINE_SUFFIX`, `_LINE_FRAGMENT`) and today drops the line part. Phase C keeps it as a **citation** token beside the path token: `{"doc", "line", "col", "path", "start", "end", "subject"}`. `subject` is the nearest definition name on the same doc line before the citation (an inline-code span such as `` `promote_reflection` `` or `` `AgentCoreBackend.list_projects()` ``, or a bare dotted or snake_case word), or, when none precedes it, the first such name within 60 characters after it (`app.py:93 (EpisodeService)`); null when the line holds none. A name is a subject only when it resolves (A §5.3, specific match) to a definition of rank 0 (`module`, `function`, `class`, `sql`, `file`) whose file ends with the cited path; literals and SQL columns never are, so `memory.db` cannot claim a citation. Citations inside fences and under `drift-ignore` markers are skipped like any reference.

### 2.2 The check

`dd_cite` runs at `start`, after `anchors`, over every in-scope doc, and writes its edits into `script-edits.json` (section 5):

| case | rule | outcome |
|---|---|---|
| current | the subject resolves to one definition in the cited file and the cited line or range lies inside its current span | counted, no edit |
| moved | the subject resolves to one definition in the cited file and the citation lies outside its span | a `cite` edit: `N` becomes the definition's current start line; `N-M` becomes its current start and end; nothing else on the line changes |
| several definitions, one covers | the subject has several definitions in the file and exactly one span holds the citation | counted as current |
| ambiguous | the subject has several definitions in the file and none or several cover the citation, or its only definitions are in other files | no edit; a hint for the agent (`cite ambiguous: <subject> <path>:<n>`) |
| unresolved | no subject on the line, or the cited file is not tracked, or the line is past the file's end | no edit; a hint (`cite unresolved: <path>:<n>`); counted |

The edit record is the ordinary one (A plan, Shared contracts): `type: "cite"`, `source: "script"`, `status: "kept"`, `claim: "<subject> is at <file>:<start>-<end>"`, `evidence: ["<file>:<start>-<end>"]`, `subject: "<subject>"`, `old` and `new` the whole doc line, ids `c001`, `c002`, ... in doc then line order. A line holding several citations gets one edit per citation applied in order on the same line; `dd_apply`'s settle step merges edits on one line as it does for overlapping agent edits, or, when it cannot, the later ones are dropped as `overlap` and the summary counts them.

Measured on `better-memory` at `9d5be26` (probe, 2026-10-14): 140 line citations in 38 docs; the same-line rule resolves 84 (60 moved, 8 current, 16 ambiguous) and 56 have no definition name on their line, most of them table cells holding only a range, which stay with the agent as unresolved hints.

### 2.3 Later runs

Citations are checked on every run, on every in-scope doc, because the definition index is rebuilt every run and the check costs nothing. A `cite` edit therefore lands even on a doc outside the run's affected set (A §6.3).

## 3. Scanned facts

### 3.1 The scan

`dd_patterns`' name record gains three fields, each null when the code sets none:

- `default`: argparse and click `default=` (a literal; an expression gives null), argparse `action="store_true"` as `"false"` and `"store_false"` as `"true"`, `os.environ.get("X", "v")` and `os.getenv("X", "v")`'s second argument, an MCP tool parameter's schema `default`;
- `choices`: argparse `choices=[...]`, click `type=click.Choice([...])`, a schema `enum`, as a list of strings;
- `required`: argparse `required=True`, click `required=True`, a parameter named in a tool schema's `required` list; `true`, `false` or null.

Values are the literal's text without quotes. The scan keeps its cross-line matching (A §8.1), so a `default=` on the line after `add_argument(` is seen.

### 3.2 Table checks

`dd_facts` runs at `start`, after the scan, over every in-scope doc, and writes its edits into `script-edits.json`:

- A **fact table** is a markdown table whose header has a name column (the first column whose cells are mostly inline-code spans) and at least one value column whose header, lowercased, is or contains `default`, `required`, `values`, `choices`, `options` or `one of`.
- A row is **checked** when its name cell matches a scanned name by `norm` (flags keep their dashes), scoped by the parent named in the nearest heading above when the kind has parents (A §8.2's rule for flag lists). A row that matches several scanned names is skipped.
- The value cell is normalised before comparison: backticks and quotes stripped; `None`, `null`, `-`, `n/a`, `(none)` and an empty cell mean no default; for a required column `yes`, `true`, `required` mean required and `no`, `false`, `optional` mean not; a choices cell is its comma- or pipe-separated items.
- A mismatch writes a `fact` edit: the row with only that cell replaced by the scan's value in the cell's own style (backticks kept if the old cell had them; a choices cell keeps its separator). `type: "fact"`, `source: "script"`, `claim: "<name> <column> is <value>"`, `evidence: ["<file>:<line>"]`, `subject: "<name>"`, ids `f001`, ...
- A row whose name the scan does not have is never an edit: it becomes a hint (`not in scan: --worker; nearest --workers` when a scanned name is within edit distance 2 by `norm`, else `not in scan: --worker`), because without history nothing proves the row stale rather than the scan incomplete.

### 3.3 Facts as hints

Every agent that reasons about a scanned name gets its facts:

- the review prompt's anchor lines (`_anchors_value`) gain `(default 8080; choices a, b; required)` for scanned names in the unit;
- the verify prompt's edit context lists the facts for every scanned name the edit's `old` or `new` mentions;
- the gap prompt's gap lines gain the facts, so a new row or sentence carries the right default.

## 4. Inline ranges and the reading rule

`dd_dispatch._anchors_value` today prints each anchor's reading range as a location. Phase C renders the code:

- The unit's reading ranges are merged per file (overlapping or adjacent ranges joined), read at HEAD, and rendered as one fenced block per file and range, headed `### <file>:<start>-<end>`, every line numbered `n: text`. On a later run the changed hunks are already inlined as a diff (A §7.2); the reading ranges of the anchors the changes touched are added the same way, after the diff.
- The anchor list stays, one line per anchor, pointing at the block (`-> <file>:<start>-<end>, below`) and carrying the facts of section 3.3.
- The hints of sections 2 and 3 for the unit's ranges follow the anchors under `## Already settled by script`: the `cite` and `fact` edits made on those lines (`line N: <old> -> <new>`), the ambiguous and unresolved citations, the `not in scan` rows.
- The reading rule replaces "start from the code ranges above and open whatever else you need": the code the anchored claims rest on is below; open a file only when a claim in your ranges depends on code that is not, and list every file you opened in the output's optional `opened` key as `{"path", "why"}`. The agent must not propose an edit on a line that is already settled by script.
- The output shape gains `opened: []` (optional; absent means none). `validate_review` accepts it.

The prompt size is bounded by `unit_lines` (A §6.4), which already counts the reading ranges, so a unit at the cap puts about 80k tokens in the prompt. The sheet and writer prompts of phase B do not change.

## 5. Pipeline

`start` runs, between `anchors` and `changes`: `cite` (`dd_cite.run(root, workdir)`), `facts` (`dd_facts.run(root, workdir, config)` after `patterns`, which therefore moves before `units`), each appending to `script-edits.json`:

```json
{"edits": [...cite and fact edit records...],
 "hints": {"docs/x.md": [{"line": 12, "kind": "cite-ambiguous" | "cite-unresolved" | "not-in-scan", "text": "..."}]},
 "counts": {"citations": {"checked", "current", "moved", "ambiguous", "unresolved"},
            "facts": {"rows_checked", "corrected", "not_in_scan"}}}
```

`dd_checks.run` adds `script` to `SOURCES`. Script edits pass `old-mismatch`, `protected` and `overlap` like any edit; `large-deletion`, `new-reference`, `guarantee` and `anchor-adds-name` do not apply to them (a `cite` edit changes digits, a `fact` edit one cell). The overlap rule prefers a script edit: an agent edit covering a line a script edit changes is dropped as `overlap-script` and counted; two script edits on one line are both kept and settled at apply (section 2.2). `dd_apply.selected_edits` applies a kept `script` edit without a verdict, as it does notice edits; `dd_checks.batches` never puts a script edit in a verifier batch.

Under `--check`, script edits appear in the planned list with their bullets and count towards exit 1.

## 6. Commits

`dd_commit` gains a third kind, made after corrections and additions when any script edit was applied:

```
docs(drift): correct citations and facts

Drift-Run: ...
Drift-Base: ...
Drift-Scope: ...
Drift-Unchecked: ...

- <doc>:<line> cite <subject> <file>:<old> -> <file>:<new>
- <doc>:<line> fact <name> <column> <old> -> <new> (<file>:<line>)
```

A doc touched by an agent edit and a script edit is staged in the first commit that touches it (A §9.4), so its script edits ride in that commit and keep their bullets in the third; the third commit is made with `--allow-empty` when every script-edited doc was already staged, as the additions commit is today. The Human-decision list goes on the last commit made.

## 7. Summary

A `Script edits` section after `Edits proposed`:

```
Script edits
citations: 140 checked, 8 current, 60 moved, 16 ambiguous, 56 unresolved
fact rows: 23 checked, 2 corrected, 1 not in scan
agent edits dropped as overlap-script: 3
```

`Edits proposed` gains `script: <n>`; `Applied` lists the third commit's docs as it lists the others; `Result` lists the third commit. The evaluation-log row's notes gain `cite <moved>/<checked>; facts <corrected>/<checked>`; the live harness also records the sum of `opened` entries per review call in the notes (`opened <n>`), so the reading rule is measurable.

## 8. Configuration and markers

No new keys. A citation or a table the owner wants left alone takes a `drift-ignore` marker (A §4), honoured by both scripts. `never_edit_heading` applies to script edits as to any edit (`protected`).

## 9. Errors and refusals

`dd_cite` and `dd_facts` raise `StepError` exit 5 when `defindex.json`, `tokens.json` or `patterns.json` is missing, naming the step; a doc that cannot be read is skipped and counted as in phase A. A script edit whose `old` no longer matches at apply is reverted as `old-mismatch`, as any edit.

## 10. Testing and measurement

- Unit tests: `dd_extract` citation tokens for the three shapes (`file.py:N`, `` `file.py:N-M` ``, `file.py#LN`) and the subject rule (before, after, none, literal excluded); `dd_patterns` defaults, choices and required for argparse (`store_true` included), click, `os.environ.get` and an MCP schema; `dd_cite` every row of the table in 2.2; `dd_facts` the header detection, scoping by heading, every normalisation, the `not in scan` hint with and without a nearest name; `dd_dispatch` the inline blocks (merged ranges, numbering, the settled list, `opened` accepted); `dd_checks` the script source and `overlap-script`; `dd_commit` the third commit and `--allow-empty`; `dd_summary` the section.
- Fixtures: `py-service` state 2 gains a definition that moves and three citation shapes in two docs (one with a subject before, one after, one in a table cell with no subject), plus a flag table with a stale default, a `store_true` row and a row the scan lacks; the planted list gains `edit:cite`, `edit:fact`, and `hint:not-in-scan` (a new expectation: the hint appears in the unit's prompt); goldens regenerated and hand-checked.
- Measurement, the phase's acceptance test: two live runs on `better-memory` at one head, before and after, comparing review tokens per call, calls, cost, the edits found (the before run's agent `cite`-class edits must be matched by script edits after), and `opened` counts; and one live run on this repository. The target is review tokens per call halved; if not met, the spec records the figure and the prompt rule stays as the fallback (section 4) with the inline blocks removed.

## 11. Decisions made in the brainstorm

| Point | Decision | Alternatives rejected |
|---|---|---|
| Verification of script edits | none by agent; their own commit (`docs(drift): correct citations and facts`) | a verifier batch; the corrections commit |
| How far script fact edits go | table cells only; prose gets the facts as hints | prose regex rewrites; hints only |
| Narrower reading | code ranges inlined in the prompt plus a reading rule, measured | prompt rule only; a two-pass review |
| Rows the scan lacks | a hint to the agent, never a script `remove` | a script `remove` edit |

## 12. Assumptions

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| C1 | The same-line nearest-name rule finds the right subject for most citations and never a wrong one | Measured on better-memory: 84 of 140 resolved, 56 left to the agent; the probe found one wrong subject (`memory.db`, a literal), excluded by the rank-0 rule | A wrong subject rewrites a citation to a wrong line, which the owner sees as a bullet and reverts |
| C2 | The scan can read defaults, choices and required from argparse, click, env reads and MCP schemas as literals | Unverified; the cross-line matcher is there, and better-memory's MCP schemas and better-memory's argparse are the test | Null facts for some names: fewer checks, no wrong edits |
| C3 | Fact tables are recognisable by header and name column across real docs | Unverified; better-memory's `website/configuration.md` and `mcp-tools.md` tables and this repository's SKILL.md tables are the sample | Tables missed: fewer checks, no wrong edits |
| C4 | Inlining the reading ranges halves review tokens per call | Unverified; measured by the two live runs of section 10 | The prompt rule alone stays; the inline blocks go |
| C5 | Agents obey "do not edit a line settled by script" | Unverified; `overlap-script` is the net | Dropped duplicates, counted |
| C6 | Script edits need no agent verification | By construction: the evidence is the definition index or the scan, both rebuilt from HEAD | A wrong definition range (A §5's JS brace matching is the known weak spot) rewrites a citation wrongly; the bullet shows it |
