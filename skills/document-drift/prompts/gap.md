# Gap writing, {{id}}

You are adding what one markdown doc is missing: user-facing names the code has and the docs do not document. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

Doc: `{{doc}}`

## The gaps

Each line gives the name's kind, the name, its parent (the command or tool a flag or parameter belongs to), the `path:line` where the code defines it, the gap kind, the target line in this doc and the reason that target was chosen:

{{gaps}}

- Gap kind `undocumented`: no doc in scope mentions the name. `missing-from-list`: the docs mention it, but a list in this doc that holds at least half the names of its kind does not.
- Reason `missing-from-list`, `complete-list` or `any-list`: the target is a list and the target line is its last line. Reason `most-names`: the target line is the heading of the section that names the most related names (line 1 when there is none).

## For each gap

1. Open the definition and confirm the name is user-facing: a user, operator or integrator calls, sets or sees it without editing the code. A name the host sets for the program (for example an environment variable the host application provides to it) or an internal one is refused as `not-user-facing`.
2. Search the docs for the name under any spelling (Grep over the repository's markdown): other case, `-` for `_` or `.`, without a prefix, inside a longer command or a table. A name that is in fact documented is refused as `already-documented`.
3. In a list: add rows or items matching the list's format, columns and order; a sorted list stays sorted.
4. Without a list: add a sentence or bullet in the most fitting paragraph or section of this doc, or, only if nothing fits, a short new section under a heading at the level of its neighbours.
5. Descriptions come from the code (its help text, default, type and behaviour), never from guesses. Every added entry cites `evidence`: the `path:line` of the definition and of anything else the description states.
6. If this doc is the wrong place for the gap, or you cannot write the entry correctly from the code, refuse it as `target-refused` with the reason.

Keep the doc's wording, voice and formatting. Change no existing text. Every name you put in inline code must exist in the code.

## Edits

An insertion is an edit of `type` `add` whose `start_line` and `end_line` are the line the addition goes after (the anchor line), whose `old` is the exact text of that line, leading spaces included, and whose `new` is that line followed by the added lines. The target line is a suggestion: anchor on whichever line puts the entry in its right place (for a sorted list, the row it follows). Two edits never anchor on the same line: put several entries that go together in one edit. `claim` says in one line what the addition documents; `subject` is the name added; `id` is `{{id}}-e01`, `{{id}}-e02`, ... in the order of the list.

## Output

Write exactly one file, `{{output}}`, with the Write tool. It holds one JSON object of this shape (the values are illustrations); every key is required, and a list with nothing in it is `[]`:

```json
{
  "doc": "{{id}}",
  "edits": [
    {"id": "{{id}}-e01", "doc": "docs/configuration.md", "start_line": 41, "end_line": 41,
     "old": "| `APP_PORT` | `8080` | Port the server listens on |",
     "new": "| `APP_PORT` | `8080` | Port the server listens on |\n| `APP_TIMEOUT` | `30` | Seconds before a request is abandoned |",
     "type": "add", "claim": "APP_TIMEOUT sets the request timeout, default 30",
     "evidence": ["src/config.py:22"], "subject": "APP_TIMEOUT"}
  ],
  "refusals": [
    {"name": "APP_DEBUG_HOOK", "kind": "not-user-facing", "reason": "set by the test harness only"},
    {"name": "--dry", "kind": "already-documented", "reason": "documented as --dry-run in docs/cli.md:12"},
    {"name": "APP_REGION", "kind": "target-refused", "reason": "this doc covers the CLI; the variable belongs with the deployment docs"}
  ]
}
```

`doc` is exactly `{{id}}`. Every gap above ends as an added entry or a refusal, never both and never neither.

## Reply

When the file is written, reply with only the receipt: the output path, its size in bytes, and the counts of edits and refusals. No other text.
