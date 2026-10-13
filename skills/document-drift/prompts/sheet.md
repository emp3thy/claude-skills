# Fact sheet, area {{area}}

You are describing one area of a repository's code, for a README that another agent will write from your sheet. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`

## The area

Read every one of these files in full (line counts given):

{{files}}

You may open files outside the area to settle what a name refers to, never to add an entry: every `defined_at` and every piece of evidence is inside the area.

## Hints

A script scanned the area for user-facing names. Every hint below is either a `surface` entry (same kind, name and parent) or a `dismissed` entry giving the reason it is not user-facing (hidden, deprecated, internal, or a false match of the scan). Hints are not the whole surface: add what the scan missed.

{{hints}}

## What to write

- `surface`: what a user can reach. Kinds: `command`, `flag`, `env`, `config`, `route`, `tool`, `param`, `script`, `entry`, and for a library's public API `function`, `class`, `module`. `name` is as the user writes it (flags keep their dashes, env vars their case). `parent` is the command, tool or parser a flag or parameter belongs to (a route's HTTP method), else null. `summary` is one line. `default` is the default value as a string, or null. `defined_at` is one `path:line` in the area, relative to the repository root with forward slashes, where the name is defined. `user_facing` is true when a user of the project meets it. `hidden` is true when the code hides it (`help=argparse.SUPPRESS`, `hidden=True`, a leading underscore, a deprecation marker); a help string alone does not hide a name.
- `behaviours`: the statements a README needs that no name carries: what the project does, what a command does to the data, where files are read from and written to, what happens on failure, what runs first. Each is one sentence that names the definition it describes in an inline-code span, in the wording a README could keep, with `evidence`: one or more `path:line` in the area. Never use `must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never` or `is required` in a statement. State no intent, plan, history or opinion.
- `dismissed`: each hint that is not a surface entry, with its `why`.

Be complete: every command, flag, environment variable, config key, route, tool and script in the area, and every behaviour a user would need to know. Be exact: a wrong default is worse than none.

## Output

Write exactly one file, `{{output}}`, holding one JSON object of this shape (the values are illustrations); every key is required, and a list with nothing in it is `[]`:

```json
{
  "area": "{{area}}",
  "surface": [
    {"kind": "command", "name": "sync", "parent": null,
     "summary": "pulls the remote state into the local store",
     "default": null, "defined_at": "src/app/cli.py:41",
     "user_facing": true, "hidden": false},
    {"kind": "flag", "name": "--force", "parent": "sync",
     "summary": "overwrites local rows that changed since the last sync",
     "default": "false", "defined_at": "src/app/cli.py:47",
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

## Reply

When the file is written, reply with only the receipt: the output path and the counts of surface entries, behaviours and dismissed hints. No other text.
