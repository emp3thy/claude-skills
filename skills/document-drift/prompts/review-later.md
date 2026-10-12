# Docs review, unit {{unit}}

You are checking markdown docs against recent changes to the code they describe, and proposing edits where a doc is now wrong. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

## The docs

These are the parts of the docs to check (line numbers are 1-based, counted in each file as it is now), with the sections of each doc that themselves changed:

{{docs}}

Since commit {{last_run}}, the code below changed. The docs refer to these names, whose definitions the changes touched (each line gives the reference, where the doc names it, and the code range to read):

{{anchors}}

The changes, as a diff from commit {{last_run}} to now:

{{diff}}

## Your scope

Check only the docs' statements about these names and the behaviour these changes affect (including statements that describe that behaviour without naming them), and the changed sections listed above. Open the current source whenever the diff alone does not settle a statement. Ignore everything else in the docs, even if it might be wrong: other runs cover it.

Do not check statements about other software, plans, intent or opinion, or historical sentences ("X was removed in 2.0"), which are true as history.

## Edit rules

Code is the truth. Make the minimal change: fix the wrong part, keep the doc's wording, voice and formatting. No reflowing, no style edits, no improvements to things that are not wrong. Do not add missing material here (another step documents what the code has and the docs lack), except where a statement is wrong because it is incomplete in a way that misleads. Edit a heading only when the heading itself is wrong.

- An edit replaces whole lines `start_line` to `end_line` of one doc. `old` is the exact text of those lines, leading spaces included, joined with newlines; `new` is their replacement (empty for a removal). Edits never overlap.
- `type` is `correct` (change wrong text), `remove` (delete a statement about something the code no longer has) or `anchor` (below).
- `claim` is the statement you checked, in one line. `evidence` lists the `path:line` places in the current code that settle it, paths relative to the repository root.
- `subject` names the removed item for a `remove` edit when there is one, the added name for an `anchor` edit, and is null otherwise.
- `id` is `{{unit}}-e01`, `{{unit}}-e02`, ... in the order of the list.

### Anchor edits

Only within the changed sections: where a true statement describes a definition in the code without naming anything ("the loader reads the user file first"), and one definition clearly is the thing described, propose an `anchor` edit that names it in an inline-code span, in the doc's own wording: "the loader (`ConfigLoader.load`) reads the user file first". An `anchor` edit changes nothing else: `new` is `old` with one inline-code span added, plus at most three other words such as brackets or "the". Its `subject` is the added name and its `evidence` includes the definition's `path:line`. A statement that is wrong gets a `correct` edit instead. A statement with several plausible definitions, or none, gets no edit. Never anchor a statement that contains a guarantee word (below). A doc with no changed sections gets no `anchor` edit.

## Questions instead of edits

- A statement containing a guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`) that the code contradicts is never edited: report it as a `guarantee-mismatch` question with the doc's `claim`, what the code does (`code`) and the `evidence`. The code may be the bug, so the owner decides.
- A claim you cannot settle is an `unsure` question, with the `question` you would ask the owner and any `evidence` you found.

## Code claims and unverified blocks

- `code_claims` counts, for every doc in this unit, the statements about this repository's code you found in the parts you checked, including the ones that name nothing. 0 means those parts are not about the code.
- `unverified_blocks` lists, only within the changed sections, whole blocks (a paragraph, a list, a table, by line range) that describe this repository's code, hold no reference that anchors, and that you could not tie to one definition (so no `anchor` edit was possible), each with a one-line `why`. Preamble, a pitch for the project, process, plans, history and statements about other software are never unverified blocks: they are not claims about the code. A block that already carries a `drift-unverified` notice (an HTML comment on the line directly above it), or that overlaps one of your edits, is not listed.
- Do not edit or move an existing `drift-unverified` notice.

## Output

Write exactly one file, `{{output}}`, with the Write tool. It holds one JSON object of this shape (the values are illustrations); every key is required, and a list with nothing in it is `[]`:

```json
{
  "unit": "{{unit}}",
  "claims_checked": 12,
  "code_claims": {"docs/configuration.md": 9, "README.md": 3},
  "unverified_blocks": [{"doc": "README.md", "start_line": 131, "end_line": 134, "why": "describes retrieval ordering; no function clearly owns it"}],
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

When the file is written, reply with only the receipt: the output path, its size in bytes, and the counts of edits, questions and unverified blocks. No other text.
