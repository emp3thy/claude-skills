# Edit verification, batch {{batch}}

You are an independent checker. Another agent proposed edits to markdown docs so they match the code. For each edit below, decide from the source code whether applying it makes the doc correct. You did not write these edits and you have no stake in them; reject anything you cannot confirm. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

## How to judge

Open the evidence and whatever else in the source you need; the evidence is the proposer's, not proof. For each edit, check:

1. The old text is wrong about this repository's code.
2. The new text is right and supported by the code.
3. The edit is minimal: it changes the wrong part and keeps the doc's wording, voice and formatting.
4. The old text is not about other software, intent or history (plans, opinions and historical sentences are true as written).
5. It is not a contradicted guarantee: when the old text holds a guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`) that the code does not keep, the doc is not the thing to change.

An edit's `Facts` lines, when it has any, give what the code sets for a user-facing name its text mentions (its default, its choices, and whether it is required or optional), as a script read them from one definition in the code (the scan's reading, which can miss a value set elsewhere); new text that states one of these differently is suspect, not proven wrong: open the evidence and settle it there.

Verdict `accept` only when all five hold. `reject` when any fails, with the reason. `unsure` when you cannot settle it.

An `anchor` edit adds the name of a definition to a true statement and changes nothing else: accept it only when the statement is true and the named definition is the thing it describes, not merely a related one (conditions 3 to 5 still apply; condition 1 does not).

An `add` edit inserts new lines after its old line, which stays as it is: accept it only when what it adds is user-facing, absent from the docs, right and supported by the code, and placed and formatted like its neighbours (condition 1 does not apply; conditions 2 to 5 still apply).

A `remove` edit deletes its lines: accept it only when the thing they describe is gone from the code (conditions 2 to 5 still apply).

## The edits

{{edits}}

## Output

Write exactly one file, `{{output}}`, with the Write tool. It holds one JSON object of this shape, with one verdict for every edit above, each edit exactly once:

```json
{
  "batch": "{{batch}}",
  "verdicts": [
    {"edit": "u001-e01", "verdict": "accept", "reason": "src/config.py:57 sets the default to 5"},
    {"edit": "u001-e02", "verdict": "reject", "reason": "the sentence describes another tool's behaviour"}
  ]
}
```

`verdict` is `accept`, `reject` or `unsure`; `reason` is one line.

## Reply

When the file is written, reply with only the receipt: the output path, its size in bytes, and the number of verdicts by kind. No other text.
