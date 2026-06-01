# tech-debt-scan

Language-independent tech-debt scan skill for Claude Code. It walks any repo,
dispatches read-only LLM scout agents per debt category, synthesises the top-5
findings into a single `design.md`, and — after a human reviews and approves
findings — emits ralph-friendly PBI bundles you can drop into a queue.

Phase 1 is human-in-the-loop: nothing is fixed automatically. The LLM does only
two things (dispatch scouts, pick the top 5); every other step is a deterministic
pure-Python script with a pinned command and a pinned output file.

## Install

This repo is a collection of Claude Code skills. To make `tech-debt-scan`
available to Claude Code, symlink the skill directory into your skills folder:

```bash
git clone https://github.com/emp3thy/claude-skills.git
ln -s "$PWD/claude-skills/skills/tech-debt-scan" ~/.claude/skills/tech-debt-scan
```

On Windows (PowerShell, as admin or with developer mode on):

```powershell
git clone https://github.com/emp3thy/claude-skills.git
New-Item -ItemType SymbolicLink -Path "$HOME\.claude\skills\tech-debt-scan" `
  -Target "$PWD\claude-skills\skills\tech-debt-scan"
```

The helper scripts need Python 3.11+ and `pyyaml`. From the skill directory:

```bash
pip install pyyaml          # the only runtime dependency
```

The scripts are direct-path invocable (`python scripts/<name>.py`) — no package
install, no `-m`.

## Quickstart

Two commands, with a human review step in between.

1. **Scan** — produce a reviewable `design.md`:

   ```
   /tech-debt-scan <repo-path>
   ```

   This inventories the repo, runs six scout agents, picks the top-5 debt items,
   and writes `.tech-debt/design.md`.

2. **Review** — open `.tech-debt/design.md`. Each finding has a `status:` field
   set to `pending`. Change it to `approved` to promote the finding, or
   `rejected` to drop it. Leave it `pending` to skip for now.

3. **Promote** — convert approved findings into PBI bundles:

   ```
   /tech-debt-promote
   ```

   This writes one `chore-<slug>-<date>/` bundle (`PBI.md`, `PLAN.md`,
   `HISTORY.md`) per approved finding under `./tech-debt-pbis`, then flips those
   findings to `promoted` so a re-run is a no-op.

See `skills/tech-debt-scan/SKILL.md` for the full step-by-step workflow Claude
follows, including every pinned command and pre/post-condition.

## Output formats

| Artefact | Written by | Shape |
| --- | --- | --- |
| `inventory.json` | `inventory.py` | `{root, total_files, total_loc, languages, files[]}` |
| `raw-findings.json` | Claude (from scouts) | `[{title, severity, category, evidence, suggested_fix}]` |
| `top5.json` | synthesis Agent | `{top5: [{slug, title, severity, category, reasoning, evidence, suggested_fix}]}` (exactly 5) |
| `design.md` | `design_writer.py render` | frontmatter + one H2 section per finding, each with a `yaml` status anchor |
| `chore-<slug>-<date>/` | `promote.py` | a PBI bundle: `PBI.md`, `PLAN.md`, `HISTORY.md` |

All intermediate artefacts live under `.tech-debt/` in the scanned repo (gitignore
it). See [`docs/architecture.md`](docs/architecture.md) for the full design,
the six debt categories, and the validation rules.

## Language support

Inventory and scouts are language-agnostic. The inventory classifies files by
extension; everything else is language-neutral. Recognised languages:

Python, C#, Java, Kotlin, TypeScript (`.ts`/`.tsx`), JavaScript (`.js`/`.jsx`),
Go, Rust, Ruby, PHP, Swift, C/C++ (`.c`/`.h`/`.cpp`/`.cc`/`.cxx`/`.hpp`), and
Markdown.

Files in common build/dependency directories (`node_modules`, `bin`, `obj`,
`target`, `.venv`, `venv`, `__pycache__`, `dist`, `build`, `.git`, IDE and tool
caches, and `.tech-debt`) are skipped.

## Status

Phase 1 (human-in-the-loop) only. Phase 2 ("mow the lawn" autonomy — apply fixes
without review) is deferred and out of scope.

## References

- [`docs/architecture.md`](docs/architecture.md) — full design, categories, and
  validation rules (the spec content, inlined).
- [`skills/tech-debt-scan/SKILL.md`](skills/tech-debt-scan/SKILL.md) — the
  step-by-step workflow Claude follows.
- Canonical design spec:
  `docs/superpowers/specs/2026-05-31-tech-debt-scan-design.md` in the private
  `ralph` repo (not linkable from here; inlined into `docs/architecture.md`).

## License

MIT. See [`LICENSE`](LICENSE).
