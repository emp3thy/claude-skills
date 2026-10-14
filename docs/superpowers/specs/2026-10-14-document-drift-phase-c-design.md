# document-drift phase C: script edits and narrower reading

Provenance: brainstormed 2026-10-14 after phase B (`docs/superpowers/specs/2026-10-13-document-drift-phase-b-design.md`, PR #26) and the first live runs of phase A on `better-memory` and on this repository. Sections of the phase A spec are cited as "A §n", of the phase B spec as "B §n".

## 1. Purpose and scope

The review agents are the cost of a run: 80% of the claude-skills run ($6.21 of $7.72 over 16 Sonnet calls averaging 750k tokens) and, on README runs, the verifiers behind them. Classifying every review edit of the two real runs (87 on `better-memory`, 18 here) showed that 40 of the 87 were a `path:line` citation that had moved, four of them botched by the agent (a second reference dropped while fixing the first), about one in eight was a default, count or enumeration the code defines, and the rest was prose only an agent can judge.

Phase C makes the mechanical classes script work and gives the agents the facts and the code they need in the prompt, so a run costs less and the agents' worst class of mistake disappears. In scope: citation checks against the definition index (section 2), scanned facts checked in doc tables and handed to every agent as hints (section 3), the review prompt carrying the code ranges inline with a reading rule (section 4; the inline blocks were removed after the measurement, section 10), a third commit for script edits, the summary, the fixture and the measurement. Out of scope: prose rewrites by regex, a cheaper model for the review agents (measured separately; the all-Sonnet fixture run is in `docs/evaluation-log.md`), and any change to the sheet or writer prompts of phase B.

Quality bar: every script edit passes the same script checks as an agent edit, lands on the same branch, and is a reviewable bullet; nothing the agents find today is lost, because the agents keep every claim the scripts do not settle and get the scripts' results as hints.

## 2. Citation checks

### 2.1 Citation tokens

`dd_extract` recognises a path reference ending in `:N`, `:N-M` or `#LN` (`_LINE_SUFFIX`, `_LINE_FRAGMENT`) and today drops the line part. Phase C keeps it as a **citation** token beside the path token: `{"doc", "line", "col", "path", "start", "end"}` (amended 2026-10-14: the token carries no `subject`; `dd_cite` computes it from the doc line when it checks the citation). The subject is the nearest **resolving name** on the same doc line before the citation or, when none precedes it, the first within 60 characters after it (`app.py:93 (EpisodeService)`, `` `storage/agentcore.py:89` - observe() wraps ``); null when the line holds none. A name resolves in one of two ways:

- a definition subject: any identifier on the line, in an inline-code span or bare, with or without `()` and with or without an `Owner.` prefix, that resolves (A §5.3, specific match) to a definition of rank 0 (`module`, `function`, `class`, `sql`, `file`) in the repository; literals and SQL columns never do, so `memory.db` cannot claim a citation;
- a scanned subject: a route path, MCP tool name, command, flag or env var the pattern scan found (A §8.1), such as `` `GET /semantic` `` in a table row; the scan's own `file` and `line` are its definition span (one line).

A table row's name cell counts as "on the line" like any other cell. Amended 2026-10-14 after a probe on `better-memory` (section 2.2): the first draft took only backticked, dotted or snake_case names and only definitions in the cited file, which left the tech-debt PBI items (`path:line` then `observe() wraps ...`) and the route tables with no subject. Citations inside fences and under `drift-ignore` markers are skipped like any reference.

Amended 2026-10-14 after the subject-rule fixes of the first probe rounds: candidates on the line before the citation are taken within 120 characters of it (when the line is a table row, only those in the citation's own cell, plus the row's name cell at any distance), after it within 60. A bare word is a candidate only when it is specific (`EpisodeService`, `store.save`) or written as a call (`observe()`), so a plain word never claims a citation. A `file` or `module` definition of the cited file is never a subject: a citation naming its own file says nothing about the line. The cited path resolves against the doc's directory, then the repository root; a path matching several tracked files makes the citation ambiguous. Python definition spans start at the first decorator line, so a citation that includes the decorator is current. A bare prose citation (`storage.py:89` outside code spans and links) is a cite token like any other.

### 2.2 The check

`dd_cite` runs at `start`, after `patterns` (amended 2026-10-14; section 5), over every in-scope doc, and writes its edits into `script-edits.json` (section 5):

| case | rule | outcome |
|---|---|---|
| current | the subject resolves to one definition in the cited file and the cited line or range lies inside its current span | counted, no edit |
| moved | the subject resolves to one definition in the cited file and the citation lies outside its span | a `cite` edit: `N` becomes the definition's current start line; `N-M` becomes its current start and end; nothing else on the line changes |
| any candidate's span covers the citation | some candidate on the line has a definition in the cited file whose span holds the citation (amended 2026-10-14; replaces "several definitions, one covers") | counted as current |
| ambiguous | the subject has several definitions in the file and none covers the citation, or the cited path matches several tracked files (amended 2026-10-14) | no edit; a hint for the agent (`cite ambiguous: <subject> <path>:<n>`) |
| use site | the subject resolves only to definitions in other files than the cited one: the citation points at a call or instantiation, which no index of definitions can check (`` `ReflectionService` ... (`app.py:93-96`) ``) | no edit; a hint (`cite use-site: <subject> is defined in <file>:<start>-<end>`); counted |
| unresolved | no subject on the line, or the cited file is not tracked, or the line is past the file's end | no edit; a hint (`cite unresolved: <path>:<n>`); counted |

The edit record is the ordinary one (A plan, Shared contracts): `type: "cite"`, `source: "script"`, `status: "kept"`, `claim: "<subject> is at <file>:<start>-<end>"`, `evidence: ["<file>:<start>-<end>"]`, `subject: "<subject>"`, `old` and `new` the whole doc line, ids `c001`, `c002`, ... in doc then line order. Amended 2026-10-14: a doc line holding moved citations gets one `cite` edit carrying every moved citation on it. A line holding both a `cite` and a `fact` edit keeps the first by id and drops the second as `overlap`. A citation on a heading line is never rewritten: it is unresolved, with the hint `(heading)`.

Amended 2026-10-14 after the final review: a scanned subject's span is one line, so a citation of a route table (`` | `GET /semantic` | `app.py:470-490` | `` with the route at 470) is current when it contains that line, or when it lies inside the rank-0 definition (not `file` or `module`) that encloses the line, such as the decorated handler (`app.py:471`); otherwise it is moved to the line as before. A citation whose subject is defined in the cited file but not at the cited lines is a use site, not moved, when a cited line at HEAD names the subject (its last dotted segment as a whole word) and is not a line defining it ("wired when `register_routes()` is called at `app.py:50`"); its hint is the use-site hint above. Re-run over the after run's inputs at `better-memory` `9d5be26`, both rules leave the counts of section 12 C1 unchanged.

Measured on `better-memory` at `9d5be26` (probe, 2026-10-14): 140 line citations in 38 docs. With the first draft's narrow subject rule, 84 resolved (60 moved, 8 current, 16 ambiguous) and 56 did not. Reading the 56: 15 are tech-debt PBI items whose subject is a bare `observe()` after the citation, 18 are table rows whose subject is a route or method in another cell, 16 are the ambiguous ones above, 5 are use sites, 2 cite an untracked file or a line past its end. Amended 2026-10-14, measured at `better-memory` `9d5be26` with the implemented rule: 140 citations, 129 cite tokens (prose citations included), 51 skipped under never-edit headings, 78 checked: 6 current, 10 moved, 17 use sites, 45 unresolved, 0 wrong rewrites. This replaces the estimate of about 110 of 140 made before the rule was run. That figure (10 moved, 17 use sites, 0 ambiguous) predates fix round 3 (a cited path naming several tracked files is ambiguous, a heading citation is never rewritten); the implemented rule's figure is section 12 C1's (4 moved, 16 use sites, 7 ambiguous).

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

Amended 2026-10-14: the boolean vocabulary (`off/disabled/no/false/✗/✘/n/x`, `on/enabled/yes/true/✓/✔/y`) applies to a default column only when the scanned default is literally `true` or `false`; a boolean word the vocabulary does not know is never rewritten. A cell's value is its leading code span only, and the rest of the cell is kept on a rewrite; a multi-word cell with no leading span counts as checked and is never rewritten, and so does a no-value cell against a boolean `false`. When the heading names a parent that no match has, only global (no-parent) matches count. `\|` in a cell is unescaped to compare and `|` is escaped to write. Several wrong cells in one row give one edit with `; `-joined fields.

Amended 2026-10-14 after the final review: an empty-string scanned default (`os.getenv("PORT", "")`) is no fact, so it never rewrites a cell and the row counts as checked; a row name written as a shell variable (`$PORT`, `${PORT}`, `${PORT:-8000}`) is the bare name. The verify prompt calls a fact the scan's reading of one definition: new text that states it differently is suspect, not proven wrong.

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

Amended 2026-10-14: on a later run the unit size counts the touched anchors' reading ranges, the code the prompt inlines. A file counts as opened when the agent Reads it; searches do not. An empty default renders as `default ""`, and a reading range past the file's end is noted in its block.

Amended 2026-10-14 after the measurement: the inline blocks were removed under section 10's rule (the halving target was not met). The prompt has no `## The code` section; each anchor line gives its reading range as phase A printed it (`-> <file>:<start>-<end>`, no `, below`) with the facts of section 3.3. The reading rule and `opened` stay: the agent reads the listed ranges with Read, opens another file only when a claim depends on code outside them, and lists every such file in `opened`. The unit size keeps counting the touched anchors' reading ranges on a later run, the code the agent is asked to read. The settled list is split in two: `## Already settled by script` holds only the `cite` and `fact` edits on the unit's lines (`- <doc>:<line>: <old> -> <new>`), which no edit may touch; `## Not settled by script: these need you` holds the hints (`- <doc>:<line>: <text>`), which are the agent's work: it checks and corrects them like any claim, and a citation whose definition it can find gets a `correct` edit with the right line. The live run had listed the hints under the settled heading, and its agents left all 17 hinted lines alone (section 12 C1).

## 5. Pipeline

`start` runs, after `patterns`: `cite` (`dd_cite.run(root, workdir)`), then `facts` (`dd_facts.run(root, workdir, config)`), both before `gaps` and `dispatch`, each appending to `script-edits.json` (amended 2026-10-14; `patterns` stays where phase A runs it, after `units`):

```json
{"edits": [...cite and fact edit records...],
 "hints": {"docs/x.md": [{"line": 12, "kind": "cite-ambiguous" | "cite-unresolved" | "not-in-scan", "text": "..."}]},
 "counts": {"citations": {"checked", "current", "moved", "ambiguous", "use_site", "unresolved"},
            "facts": {"rows_checked", "corrected", "not_in_scan"}}}
```

`dd_checks.run` adds `script` to `SOURCES`. Script edits pass `old-mismatch`, `protected` and `overlap` like any edit; `large-deletion`, `new-reference`, `guarantee` and `anchor-adds-name` do not apply to them (a `cite` edit changes digits, a `fact` edit one cell). The overlap rule prefers a script edit: an agent edit covering a line a script edit changes is dropped as `overlap-script` and counted; of two script edits on one line, the first by id is kept and the second dropped as `overlap` (section 2.2). `dd_apply.selected_edits` applies a kept `script` edit without a verdict, as it does notice edits; `dd_checks.batches` never puts a script edit in a verifier batch.

Amended 2026-10-14: `cite` runs after `patterns` (it reads `patterns.json`), `facts` after `cite`, both before `gaps` and `dispatch`. For agent sources `overlap-script` runs right after `old-mismatch`.

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
citations: 140 checked, 8 current, 60 moved, 16 ambiguous, 5 use sites, 51 unresolved
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
- Result (2026-10-14, `docs/evaluation-log.md`): review tokens per call fell from 1.46M to 1.17M, 20%, not the halving. The figure is confounded: the after run's review agents proposed 9 fewer edits (83 against 92) and skipped the 20 citation lines of section 12 C1, both of which cut tokens on their own, and each side is a single run. Under this section's rule the inline blocks were removed (section 4's second amendment); the prompt rule and `opened` stay.

## 11. Decisions made in the brainstorm

| Point | Decision | Alternatives rejected |
|---|---|---|
| Verification of script edits | none by agent; their own commit (`docs(drift): correct citations and facts`) | a verifier batch; the corrections commit |
| How far script fact edits go | table cells only; prose gets the facts as hints | prose regex rewrites; hints only |
| Narrower reading | code ranges inlined in the prompt plus a reading rule, measured; the inline blocks removed after the measurement (section 10), the reading rule kept | prompt rule only; a two-pass review |
| Rows the scan lacks | a hint to the agent, never a script `remove` | a script `remove` edit |

## 12. Assumptions

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| C1 | The same-line nearest-name rule, with definitions and scanned names as subjects, finds the right subject for most citations and never a wrong one | Measured 2026-10-14 at better-memory `9d5be26` (full live run): 78 citations checked, 6 current, 4 moved, 7 ambiguous, 16 use sites, 45 unresolved; the 4 rewrites (`list_for_project`, `list_session_exposures`, `observe`, `create_app`) each target the first line of the subject's current span in `defindex.json`: 4 rewrites, 0 wrong. The rule is right when it speaks but speaks rarely: the before run's agents proposed 50 edits on a line holding a `path:line` citation, of which 28 were kept and 25 accepted and applied. In the after run 2 of the 50 lines became script edits and 20 got no edit at all (`agentcore-mapping.md` lines 33, 35-37, 39-44, 53, 69 and 73; `data-sources.md` lines 127-132 and 167; recounted from the two workdirs), 14 of which the before run had applied; 17 of the 20 were listed as hints (12 `cite-unresolved`, 5 `cite-use-site`) under "Already settled by script" and the agents treated them as off limits, which the split of section 4's second amendment fixes. Single runs on each side; see the evaluation log | A wrong subject rewrites a citation to a wrong line, which the owner sees as a bullet and reverts; unresolved citations stay stale |
| C2 | The scan can read defaults, choices and required from argparse, click, env reads and MCP schemas as literals | Measured 2026-10-14 (same run): 73 fact rows checked, 1 corrected (`website/mcp-tools.md:60` `outcome` Required `yes` to `no`, from the schema at `mcp/tools.py:257`); no wrong edit seen. Reading the MCP schema's `required` list was needed by one review agent anyway (u003 opened `mcp/tools.py` for `memory.retrieve`) | Null facts for some names: fewer checks, no wrong edits |
| C3 | Fact tables are recognisable by header and name column across real docs | Measured 2026-10-14 (same run): 73 rows found in better-memory's tables; 4 rows not in scan, all env var names, in two tables: `README.md:117` (`AUDIT_LOG_RETRIEVED`) and `website/configuration.md` lines 11, 15 and 16 (`AUDIT_LOG_RETRIEVED`, `BETTER_MEMORY_TEST_AGENTCORE`, `BETTER_MEMORY_TEST_AGENTCORE_REGION`), given to the agents as hints, never removed | Tables missed: fewer checks, no wrong edits |
| C4 | Inlining the reading ranges halves review tokens per call | Measured 2026-10-14: review tokens per call fell 20% (1.46M to 1.17M over 5 calls; cost $4.64 to $4.69, 191 s to 184 s per call), confounded by 9 fewer review edits and the 20 skipped citation lines of C1, one run per side; the 8 files the agents opened are in the evaluation log. Not met: the inline blocks were removed under section 10's rule; the prompt rule and `opened` stay | The prompt rule alone stays; the inline blocks go (done) |
| C5 | Agents obey "do not edit a line settled by script" | Measured 2026-10-14: 2 `notice` placements (the two PBI.md lines the script rewrote), not agent corrections, were dropped as `overlap-script`; no review or gap edit was. Obeyed, and over-obeyed: the agents also left the hinted lines alone (C1) | Dropped duplicates, counted |
| C6 | Script edits need no agent verification | By construction: the evidence is the definition index or the scan, both rebuilt from HEAD. The live run's 5 script edits were checked by hand against `defindex.json` and the scan and are right | A wrong definition range (A §5's JS brace matching is the known weak spot) rewrites a citation wrongly; the bullet shows it |
