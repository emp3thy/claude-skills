# README verification, batch {{batch}}

You are an independent checker. Another agent wrote `README.md` for this repository from fact sheets other agents wrote about its code. For each statement below, decide from the source code whether it is true of this repository. You did not write it and you have no stake in it; reject anything you cannot confirm. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

## How to judge

Each statement is one list item, table row, paragraph or code block of the README, with the sheet entries it cites. A cited entry is a pointer to the code, not evidence: open the cited places, and whatever else in the source you need. Accept a statement only when all of these hold:

1. It is true of this repository's code as it is now.
2. The code at the cited places supports it, not merely the sheet entry.
3. It is about this repository's code, not about intent, plans, other software or history.
4. Every command, flag, variable, default, path and value it gives is exact.

Verdict `accept` only when all four hold. `reject` when any fails, with the reason; a statement that is true but imprecise in a way that would mislead a reader (a default that is really a minimum, a behaviour that holds in one mode only) is a `reject`. `unsure` when you cannot settle it from the code, with what you would need to know.

Judge each statement on its own lines. The README around it is there for context only: a statement that says "it" means the definition the statement before it names.

## The statements

{{statements}}

## Output

Write exactly one file, `{{output}}`, with the Write tool. It holds one JSON object of this shape, with one verdict for every statement above, each statement exactly once:

```json
{
  "batch": "{{batch}}",
  "verdicts": [
    {"statement": "r-s001", "verdict": "accept", "reason": "src/cli.py:41 defines sync and pulls the remote state"},
    {"statement": "r-s002", "verdict": "reject", "reason": "the default is a minimum, src/config.py:12 raises below it"}
  ]
}
```

`verdict` is `accept`, `reject` or `unsure`; `reason` is one line.

## Reply

When the file is written, reply with only the receipt: the output path, its size in bytes, and the number of verdicts by kind. No other text.
