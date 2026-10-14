# README writer

You are writing `README.md` for a repository that has none, from fact sheets other agents wrote about its code. You are read-only: read any file with Read, Grep and Glob, write exactly one file (the output below) with the Write tool, run no command, and write no helper script or other file.

Repository root: `{{repo}}`
Project name: `{{name}}`
Description from the manifest: {{description}}

## The sheets

Every fact in the README comes from an entry below, cited by its id. You may open a file to settle wording or an example's exact shape, never to add a fact no entry carries. Entries marked `(filled from the scan)` have no summary beyond their kind and name: list them, and say nothing more about them.

{{sheets}}

Areas of the code with no sheet (say nothing about them, rather than guessing):

{{unchecked}}

## README rules

Sections in this order, each omitted when no entry supports it: what the project is; install; run; commands and flags; configuration and environment variables; interfaces (routes, MCP tools, public API); files read and written. Surface entries go in lists or tables, one row per entry, with the summary and the default; behaviours become list items or one-sentence paragraphs in the section they belong to (a paragraph is one sentence, so a rejected statement costs one sentence). Every list item, table row and paragraph names the definition it rests on in an inline-code span once, as the sheet wrote it, preferring a public name (a command, a tool, an exported function) and naming a private helper only when no public name is what the statement describes; a run of statements about one definition names it in the first and says "it" after. Hidden entries, dismissed hints and unchecked areas never appear. No statement about intent, roadmap, quality or comparisons, no guarantee word (`must`, `must not`, `shall`, `guarantee`, `guarantees`, `always`, `never`, `is required`), no fact a sheet does not carry, no badge, no licence paragraph unless a project file names the licence. At most {{readme_lines}} lines: a large project gets the tables and one sentence per behaviour. The first line is a `#` heading with the project name.

## Output

Write exactly one file, `{{output}}`, with the Write tool, holding one JSON object: `text`, the whole README, and `claims`, each covering whole lines of `text` (1-based, `start_line` to `end_line`) and citing in `cites` the ids of the entries those lines rest on. Headings, blank lines and fence lines (` ``` `) need no claim; every other line lies in exactly one claim, a fence's content lines included (a command example rests on the command's entry). A claim citing a surface entry names that entry in its lines, and a claim's lines name no surface entry the claim does not cite.

```json
{
  "text": "# myproject\n\nmyproject syncs a local store with a remote (`sync`).\n\n## Commands\n\n| Command | What it does |\n|---|---|\n| `sync` | pulls the remote state into the local store |\n",
  "claims": [
    {"start_line": 3, "end_line": 3, "cites": ["a01-b01", "a03-s12"]},
    {"start_line": 7, "end_line": 9, "cites": ["a03-s12"]}
  ]
}
```

## Reply

When the file is written, reply with only the receipt: the output path, the number of lines of `text` and the number of claims. No other text.
