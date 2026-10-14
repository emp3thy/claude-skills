# Docs review, unit {{unit}}

You are checking markdown docs against the code they describe, and proposing edits where a doc is wrong. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

## The docs

Check these docs, and only the line ranges given (line numbers are 1-based, counted in each file as it is now):

{{docs}}

The docs name these definitions in the code. Each line gives the reference, where the doc names it, and the code range to read first; for a user-facing name the scan found, it ends with the facts the code sets (its default, its choices, and whether it is required or optional):

{{anchors}}

## Already settled by script

Scripts have already corrected these lines of the docs (a citation's line number or a fact table's cell), each shown as `<doc>:<line>: <old> -> <new>`:

{{settled}}

Do not edit these lines: the script's correction stands.

## Not settled by script: these need you

The scripts checked these citations and table rows but could not settle them (a citation that is ambiguous, cites a use rather than the definition, or resolves to nothing; a table row whose name is not in the scan), each shown as `<doc>:<line>: <what the script found>`:

{{unsettled}}

These are your work: check and correct them like any claim. A citation whose definition you can find gets a `correct` edit with the right line.

## What to check

Check every factual statement the docs make about this repository's code: names, paths, commands, flags, environment variables, config keys, defaults, counts and lists ("the six tools"), described behaviour, code examples (imports, call shapes, CLI invocations, field names in sample output) and directory trees. Read the code ranges listed above with Read; open another file only when a claim in your ranges depends on code outside them, and list every such file in `opened` with one reason each.

Do not check statements about other software, plans, intent or opinion, or historical sentences ("X was removed in 2.0"), which are true as history.

## Edit rules

Code is the truth. Make the minimal change: fix the wrong part, keep the doc's wording, voice and formatting. No reflowing, no style edits, no improvements to things that are not wrong. Do not add missing material here (another step documents what the code has and the docs lack), except where a statement is wrong because it is incomplete in a way that misleads. Edit a heading only when the heading itself is wrong.

- An edit replaces whole lines `start_line` to `end_line` of one doc. `doc` is the doc's path as listed above, with forward slashes. `old` is the exact text of those lines, leading spaces included, joined with newlines; `new` is their replacement (empty for a removal). Edits never overlap.
- `type` is `correct` (change wrong text), `remove` (delete a statement about something the code no longer has) or `anchor` (below).
- `claim` is the statement you checked, in one line. `evidence` lists the `path:line` places in the code that settle it, paths relative to the repository root, with forward slashes (`src/app/cli.py:17`).
- `subject` names the removed item for a `remove` edit when there is one, the added name for an `anchor` edit, and is null otherwise.
- `id` is `{{unit}}-e01`, `{{unit}}-e02`, ... in the order of the list.

### Anchor edits

A later run can only check a doc through the names it holds in inline-code spans (the anchors listed above). Where a true statement describes a definition in the code without such a name ("the loader reads the user file first", "three buckets, surfaced separately", "the dispatcher in server.py holds 22 handlers"), and one definition clearly is the thing described, propose an `anchor` edit that names it in an inline-code span, in the doc's own wording: "the loader (`ConfigLoader.load`) reads the user file first". When the statement already has the name as a bare word, wrap that word in backticks instead ("in _call_tool" becomes "in `_call_tool`"). An `anchor` edit changes nothing else: `new` is `old` with one inline-code span added (or one bare word wrapped), plus at most three other words such as brackets or "the". Its `subject` is the added name and its `evidence` includes the definition's `path:line`. A statement that is wrong gets a `correct` edit instead. A statement with several plausible definitions, or none, gets no edit. Never anchor a statement that contains a guarantee word (below).

A doc marked `no anchors in these lines` above is one no later run can check at all. Go over every block of it that describes this repository's code before you finish: each such block gets an `anchor` edit for its clearest statement, or a place in `unverified_blocks` when no definition clearly is the thing described. Blocks that are not about the code (preamble, process, plans, history) get neither.

## Questions instead of edits

- A statement containing a guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`) that the code contradicts is never edited: report it as a `guarantee-mismatch` question with the doc's `claim`, what the code does (`code`) and the `evidence`. The code may be the bug, so the owner decides.
- A claim you cannot settle is an `unsure` question, with the `question` you would ask the owner and any `evidence` you found.

## Code claims and unverified blocks

- `code_claims` counts, for every doc in this unit, the statements about this repository's code you found in the ranges you checked, including the ones that name nothing. 0 means the doc is not about the code.
- `unverified_blocks` lists whole blocks (a paragraph, a list, a table, by line range) that describe this repository's code, hold no reference that anchors, and that you could not tie to one definition (so no `anchor` edit was possible), each with a one-line `why`. Preamble, a pitch for the project, process, plans, history and statements about other software are never unverified blocks: they are not claims about the code. A block that already carries a `drift-unverified` notice (an HTML comment on the line directly above it), or that overlaps one of your edits, is not listed.
- `not_reviewed` lists the line ranges of these docs you did not check against the code (for instance when the unit was too large to finish), each with a one-line `why`; another agent gets them. A range you did not check is never an unverified block and is not counted in `code_claims`. Checked everything: `[]`.
- `opened` lists every file you opened beyond the code ranges listed above (reading outside a listed range counts), each as `{"path", "why"}`: the path relative to the repository root, with forward slashes, and the claim that needed it, in one line. A file counts as opened when you Read it; Grep and Glob searches do not count. Opened nothing: `[]`.
- Do not edit or move an existing `drift-unverified` notice.

## Output

Write exactly one file, `{{output}}`, with the Write tool. It holds one JSON object of this shape (the values are illustrations); every key is required, and a list with nothing in it is `[]`:

```json
{
  "unit": "{{unit}}",
  "claims_checked": 41,
  "code_claims": {"docs/configuration.md": 38, "README.md": 60},
  "unverified_blocks": [{"doc": "README.md", "start_line": 131, "end_line": 134, "why": "describes retrieval ordering; no function clearly owns it"}],
  "not_reviewed": [],
  "opened": [],
  "edits": [
    {"id": "{{unit}}-e01", "doc": "docs/configuration.md", "start_line": 54, "end_line": 54,
     "old": "| `APP_TOP_N` | `3` | ... |", "new": "| `APP_TOP_N` | `5` | ... |",
     "type": "correct", "claim": "default of APP_TOP_N is 3",
     "evidence": ["src/config.py:57"], "subject": null},
    {"id": "{{unit}}-e02", "doc": "README.md", "start_line": 120, "end_line": 120,
     "old": "The loader reads the user file first.", "new": "The loader (`ConfigLoader.load`) reads the user file first.",
     "type": "anchor", "claim": "the loader reads the user file first",
     "evidence": ["src/loader.py:41"], "subject": "ConfigLoader.load"}
  ],
  "questions": [
    {"doc": "README.md", "line": 88, "kind": "guarantee-mismatch",
     "claim": "the stop hook never blocks", "code": "the hook waits on a lock",
     "evidence": ["src/hooks/stop.py:30"]},
    {"doc": "README.md", "line": 140, "kind": "unsure", "claim": "...", "question": "...", "evidence": []}
  ]
}
```

`claims_checked` is the number of statements you checked across the unit.

## Reply

When the file is written, reply with only the receipt: the output path, its size in bytes, and the counts of edits, questions, unverified blocks, not-reviewed ranges and opened files. No other text.
