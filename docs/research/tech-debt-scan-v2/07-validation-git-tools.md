# tech-debt-scan v2: validation of git, gitignore and tool assumptions

Empirical checks of the assumptions in `06-design-brainstorm.md` sections 4.2, 4.4, 4.9, 4.11, 4.13, concerns 4 to 6 and section 7. Run 2026-09-02 on Windows 11 with git 2.51.0.windows.1, Python 3.12.10 and ruff 0.15.4. Real repositories were only read; every write experiment used a throwaway repository in the session scratchpad. `C:\Users\gethi\source\repos` is not a git repository, so `better-memory` (650 commits) was added as a third, larger sample.

## E1. The single git pass

Command, exactly as in 4.2, run through `subprocess.run` with a list argv and no shell (the way `inventory.py:143-149` already runs git):

```
git -C <root> log --since="12 months ago" --name-only --relative --format=%x1e%H%x09%aN%x09%aI%x09%s -- .
```

| Repository | Commits in window | Output | git wall | parse wall | Bulk commits (>50 files) |
|---|---|---|---|---|---|
| claude-skills | 5 | 5 KB | 0.06 s | 0.001 s | 1 |
| ralph | 140 | 56 KB | 0.34 s | 0.012 s | 1 |
| better-memory | 604 | 161 KB | 0.74 s | 0.028 s | 1 |

Observations.

- The record separator is emitted once per commit (5, 140 and 604 occurrences of byte 0x1e). The header line is `hash<TAB>author<TAB>ISO date<TAB>subject`, followed by a blank line and one path per line. A record with a subject containing a tab would break a naive `split("\t")`; splitting with `maxsplit=3` handles it.
- Paths are root-relative and forward-slash on all three repositories (zero backslashes).
- `--relative` is a no-op when `-C` points at the repository root, because `-C` sets the working directory. When `-C` points at a subdirectory (`ralph/ralph_executor`), paths come out relative to that subdirectory (`cli.py`, `safety/cycle_detector.py`) and the log is restricted to it; without `--relative` the same call prints `ralph_executor/cli.py`. The shell's own cwd (the scratchpad) had no effect. The flag therefore does what the design wants for a monorepo package scan.
- Path quoting. With the default `core.quotePath=true`, a path containing a non-ASCII character is emitted C-quoted: `"src/sub dir/caf\303\251 file.py"`. Spaces alone are not quoted. The v1 parser does not unquote. Passing `-c core.quotePath=false` prints the raw UTF-8 path `src/sub dir/café file.py`.
- Shell safety of the format string. As a single argv through `subprocess` (no shell) and through PowerShell the string arrives intact. Through `cmd.exe` it is intact only while no environment variable named `H` exists: with `H=zzz` the output became `zzzx09emp3thy`, because `cmd` expands `%H%`. The scripts never go through `cmd`, so this is a documentation note, not a defect.
- The design's "bulk commits excluded" filter caught exactly one commit per repository, the initial import.

Coupling, computed with the design thresholds (shared >= 3, ratio >= 0.30, bulk > 50 excluded, source-class pairs only, ratio = shared / mean of the two files' non-bulk commit counts):

| Repository | Candidate pairs | Emitted | Top pairs (shared, ratio) |
|---|---|---|---|
| claude-skills | 21 | 0 | none reach shared >= 3 |
| ralph | 821 | 49 | config.py + loop.py (13, 0.53); config.py + setup_cmds.py (12, 0.63); claude_spawn.py + config.py (11, 0.52); loop.py + queue/movements.py (10, 0.54, cross-directory); cli.py + config.py (10, 0.49) |
| better-memory | 814 | 20 | storage/protocol.py + storage/sqlite.py (12, 0.69); storage/agentcore.py + protocol.py (9, 0.38); agentcore.py + sqlite.py (8, 0.33); hooks/observer.py + hooks/session_close.py (6, 0.46); services/session_bootstrap.py + storage/protocol.py (5, 0.30) |

The pairs are meaningful. `setup_cmds.py` imports from `config.py`; `queue/movements.py` imports `git_ops`; `storage/sqlite.py` implements the `StorageBackend` protocol declared in `storage/protocol.py`; `hooks/contextual_inject.py` imports `services/context_seen.py` (a 4-commit, 0.80-ratio pair). The interface-plus-implementation and config-plus-consumer shapes are exactly what change coupling is meant to surface.

Two problems the pass exposed.

1. **Deleted files.** ralph's most-churned file, `ralph_executor/loop.py` (27 commits), no longer exists at HEAD; it was split in commit 0dbf18e. It heads the churn table and appears in the top coupling pair. The v1 inventory joins churn onto files that exist, but `coupling.json` as specified has no such join. Pairs and churn must be filtered to paths present in `files`, or the architecture scout will be handed leads to a file it cannot open.
2. **Author identity.** ralph has no `.mailmap`, and its commits carry two identities for one person (`emp3thy`, `gethin`) plus `Claude (worktree)` and `Claude`, none of which ends in `[bot]`. The design's `[bot]` filter and `%aN` give ralph three "human" authors, which passes the ownership family's three-author gate for a one-person repository. better-memory shows the same pattern.

Verdict: CONFIRMED for the command, separator, path shape, performance and coupling quality. Recommended changes: add `-c core.quotePath=false` and decode stdout as UTF-8 with replacement; split the header with `maxsplit=3`; filter churn and pairs to files present at HEAD; add a configurable bot-author pattern (`bot_authors: ["[bot]", "^Claude"]`) and state in the report that authorship is by name, not by person, when no `.mailmap` exists.

## E2. Branches and tags

`git for-each-ref --format='%(refname:short)%09%(committerdate:iso8601)' refs/heads refs/remotes` on ralph prints one tab-separated line per ref, e.g. `main<TAB>2026-06-11 18:58:20 +0100`. The `iso8601` date uses a space separator and a numeric offset; `iso8601-strict` gives the `T` form if a single parser is wanted for both this and `%aI`. One trap: `refs/remotes/origin/HEAD` prints as the bare name `origin` because it is a symbolic ref. Adding `%(symref)` to the format and skipping rows where it is non-empty, or passing `--exclude=refs/remotes/*/HEAD`, removes it.

`git merge-base --is-ancestor <ref> HEAD` returns 0 for `main` and 1 for every other local branch on ralph (all unmerged), with no output. Exit 128 on an unknown ref must be treated as null rather than "unmerged".

`git tag --sort=creatordate --format='%(refname:short)%09%(creatordate:iso8601)'` runs but ralph, claude-skills and better-memory have no tags at all, so the shape was confirmed on the throwaway repository: `light1<TAB>2026-09-02 21:44:00 +0100` for a lightweight tag (creatordate falls back to the commit date) and the tag date for an annotated one. The release-cadence rule ("5 or more tags") is inert on every repository available here, which is fine but means it has no local test subject.

Verdict: CONFIRMED, with the symref filter as a required change.

## E3. Blame cost

`git blame -w --line-porcelain <path>` on the three most-churned existing ralph source files:

| File | Lines | Wall |
|---|---|---|
| ralph_executor/config.py | 1174 | 0.147 s |
| ralph_executor/claude_spawn.py | 627 | 0.090 s |
| ralph_executor/cli.py | 689 | 0.099 s |

Every line yields one `author ` and one `author-time ` record (1174 of each for config.py), both trivially parseable with a line-anchored regex; `author-time` is a Unix epoch integer. The 50 most-churned existing files took 4.36 s in total. The design's cap of 50 hotspot-band files plus 200 pattern files is therefore in the 5 to 25 second range on a repository of this size; cost grows with file length and history depth, and the 120-second per-call timeout is generous.

Verdict: CONFIRMED.

## E4. Gitignore re-inclusion (concern 5)

Throwaway repository, git 2.51, file `.tech-debt/baseline.json` plus a sibling `inventory.json` that must stay ignored. "Tracked" means `git add` (without `-f`) staged the file.

| Case | `.gitignore` content | baseline tracked | inventory ignored |
|---|---|---|---|
| a | `.tech-debt/` then `!.tech-debt/baseline.json` | no | yes |
| b | `.tech-debt/*` then `!.tech-debt/baseline.json` | yes | yes |
| c | user `.tech-debt/`, skill appends `.tech-debt/*` + `!.tech-debt/baseline.json` | no | yes |
| c2 | user `.tech-debt/`, skill appends `!.tech-debt/` + `.tech-debt/*` + `!.tech-debt/baseline.json` | yes | yes |
| d | user `.tech-debt` (no slash), skill appends `.tech-debt/*` + `!…baseline.json` | no | yes |
| d2 | as d but with `!.tech-debt/` first | yes | yes |
| f | user `**/.tech-debt/`, skill appends the c2 trio | yes | yes |
| g | `.tech-debt/` only in `.git/info/exclude`, skill trio in `.gitignore` | yes | yes |
| h | `.tech-debt/` only in a global `core.excludesFile`, skill trio in `.gitignore` | yes | yes |
| i | root `.tech-debt-baseline.json` with user rule `.tech-debt/` | not ignored | n/a |
| i2 | root `.tech-debt-baseline.json` with user rule `.tech-debt*` | ignored | n/a |

Git's documented rule holds: once a directory is excluded, no pattern can re-include a file inside it, so cases a, c and d fail exactly as the design says. The design's claim is accurate as stated. What it misses is that the fix is one line: writing `!.tech-debt/` before the skill's own two lines un-excludes the directory, after which `.tech-debt/*` re-excludes its contents and the file negation works (c2, d2, f). Because a repository `.gitignore` outranks `.git/info/exclude` and the global excludes file, the trio also wins against rules the skill cannot see (g, h). A further alternative is `git add -f .tech-debt/baseline.json` once: a tracked file stays tracked and shows as modified regardless of any ignore rule (verified), at the cost of `promote.py` touching the index.

The root-file option has its own edge: a user rule spelled `.tech-debt*` ignores `.tech-debt-baseline.json` (i2). Only claude-skills itself has a `.tech-debt/` rule today; ralph's `.gitignore` has none.

Verdict: CONFIRMED that `.tech-debt/` + a file negation fails and that `.tech-debt/*` is needed; PARTIAL on the consequence, because a three-line block starting with `!.tech-debt/` works for every existing-rule variant tested. Decision 5 can stay with the root file, but "breaks for every user who already ignores `.tech-debt/`" overstates option B's cost.

## E5. Tool availability and output shapes

Present: ruff 0.15.4 (on PATH and as `python -m ruff`). Absent: osv-scanner, gitleaks, vulture, lizard, jscpd, knip, madge, hadolint, actionlint. Node 22 and npm are installed, but the only global package is a Gmail MCP server, and neither ralph nor claude-skills has a `node_modules/.bin` with jscpd, knip or madge. `shutil.which` will therefore find none of the JS tools even on a JS repository that lists them as dev dependencies; the probe should also look in `<root>/node_modules/.bin/` before declaring a tool absent, and must never fall back to `npx`, which downloads.

ruff with the design's selection over `skills/`:

```
ruff check --output-format json --select E722,BLE001,S110,S112,C901,PLR0911,PLR0912,PLR0913,PLR0915,F401 skills/
```

produced two findings, both on `build_synthesis_prompt.validate_synthesis_output`. One item:

```json
{"cell": null, "code": "C901",
 "filename": "C:\\Users\\gethi\\source\\claude-skills\\skills\\tech-debt-scan\\scripts\\build_synthesis_prompt.py",
 "location": {"column": 5, "row": 218}, "end_location": {"column": 30, "row": 218},
 "message": "`validate_synthesis_output` is too complex (14 > 10)",
 "noqa_row": 218, "fix": null, "url": "https://docs.astral.sh/ruff/rules/complex-structure"}
```

File, line (`location.row`) and rule id (`code`) are all present. Three points for the normaliser: `filename` is absolute with backslashes even when a relative path is passed, so it must be relativised and forward-slashed; ruff exits 1 whenever it reports a finding and 0 only when clean, so the design's "non-zero exit means failed" rule would mark every useful run as failed unless `--exit-zero` is passed (verified: exit 0 with the same two findings); and ruff reads the target repository's own `pyproject.toml` or `ruff.toml`, so a repository that sets `extend-select` or `ignore` changes the probe's results. `--isolated` makes the probe reproducible at the cost of the repository's `exclude` list. All rule codes in the selection exist in 0.15.4 (S110 `try-except-pass`, S112 `try-except-continue`, BLE001 `blind-except`, PLR0911 `too-many-return-statements`). The `UP` group named in 4.4 for deprecations is pyupgrade, a syntax-modernisation set; only UP035 (`deprecated-import`) concerns deprecation, so `UP` should be narrowed to that rule.

The same exit-code trap applies to gitleaks (exit 1 on leaks by default, configurable with `--exit-code`) and osv-scanner (exit 1 when vulnerabilities are found). `tools_probe.py` needs a per-tool "findings exit code" table rather than a blanket rule.

Verdict: PARTIAL. The JSON shape supports the design; the failure rule, path form and `UP` selection need the changes above.

## E6. Network use of osv-scanner and gitleaks (concern 4)

osv-scanner's README (https://github.com/google/osv-scanner) states that the scanner "queries this API [OSV.dev] to check packages for known vulnerabilities" and that "data sent includes package names, versions, ecosystems, and file hashes". The concern is real and applies by default. The offline page (https://google.github.io/osv-scanner/usage/offline-mode/; the `experimental/offline-mode/` path the older docs used now returns 404) documents `--offline` ("no network connection is required after the initial database download"), `--offline-vulnerabilities` (local database, other network features allowed) and `--download-offline-databases`. The database lives at `{dir}/osv-scanner/{ecosystem}/all.zip`, downloaded from `https://osv-vulnerabilities.storage.googleapis.com/<ECOSYSTEM>/all.zip`, with the directory set by `OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY` (default: the user cache dir, then temp). Commit-level scanning is not supported offline. The JSON output (https://google.github.io/osv-scanner/output/) is `results[].source.path` plus `packages[].package{name, version, ecosystem}` and `vulnerabilities[]`; it carries no line number, so the normaliser must either locate the package in the lockfile by search or emit `line_start: null` for osv signals.

gitleaks' README (https://github.com/gitleaks/gitleaks) describes no network use: `git` mode wraps `git log -p` locally, `dir` mode scans the working tree, rules ship in the binary or a local config, and JSON goes to `-f json -r <path>`. The README now marks the project "feature complete" with security patches only and points new users to Betterleaks, which is worth knowing when the tool list is finalised.

Verdict: CONFIRMED. Recommended change: `tools.network: false` should map to `osv-scanner --offline` (marked `skipped: no local database` when the database is absent) rather than to skipping the tool outright, and decision 4's notice should name the data sent.

## E7. Ralph's dependence on `category` (concern 6)

A search of ralph for `category`, `debt_type`, `god-modules`, `tech-debt` and `chore-` (excluding `.git`, `.venv`, `node_modules`) finds hits only in ralph's own `.tech-debt/design.md` and archived scans, and in two design documents under `docs/superpowers/specs/` that narrate past scans. No Python file in ralph reads `category` or any category name.

Ralph's PBI parser is `ralph_executor/queue/filesystem.py:112-119`. It loads the frontmatter with `yaml.safe_load`, then indexes exactly `id`, `type`, `severity`, `attempts`, `created_at` and `updated_at`; a missing key raises `QueueError("missing required field")`. `depends_on` is optional. `type` must be one of `feature`, `bug`, `pr-feedback` (`types.py:19`) and must agree with the entry file, so `PBI.md` implies `feature` (`filesystem.py:141`). `target_repo` is read separately at claim time by `pbi_claim.read_target_repo_from_pbi`. Unknown keys are ignored, so `fingerprint`, `tier`, `type_id`, `family` and a retained `category` alias are all safe to add.

Verdict: CONFIRMED. The 4.11 claim is sufficient but its list is incomplete: `id`, `severity` (as `critical|high|normal|low`) and `attempts` are also load-bearing, and `bundle_writer.py` already emits them. The design should name all six required keys so a future edit does not drop one.

## E8. Windows argv length

Expanding every command in 4.13 with an absolute script path (`C:\Users\gethi\source\claude-skills\skills\tech-debt-scan\scripts\`), a 75-character repository path, all 14 family names in `--families`, `--top 10` and `--preset hotspot-first` gives a longest line of 299 characters (`plan_scan.py`). The git pass argv is 187 characters and a blame call on a 40-level-deep path is 209. No command in 4.13 embeds a file list; the only list-valued argument is `--families`, bounded by the 16 known names. All are far below cmd's 8191-character limit and the 32,767-character CreateProcess limit.

Verdict: CONFIRMED.

## Summary

| Assumption | Verdict | Consequence |
|---|---|---|
| 4.2 git pass command runs, emits 0x1e records, root-relative forward-slash paths, fixed argv | CONFIRMED | Add `-c core.quotePath=false` and UTF-8 decoding; split header with `maxsplit=3` |
| 4.2 `--relative` gives paths relative to the scanned root regardless of cwd | CONFIRMED | None |
| 4.2 performance (section 7: 90 percent) | CONFIRMED | 0.06 to 0.74 s for 5 to 604 commits; 120 s timeout is ample |
| 4.2 coupling thresholds yield meaningful pairs | CONFIRMED | 49 pairs on ralph, 20 on better-memory, 0 on claude-skills; pairs match import relationships |
| 4.2 churn and coupling refer to live files | REFUTED | ralph's top hotspot and top pair cite a deleted file; join against HEAD |
| 4.2 `[bot]` filter and `%aN` give human author counts | PARTIAL | Multiple identities and `Claude` authors inflate counts; configurable bot pattern, report the caveat |
| 4.2 branch and tag commands | CONFIRMED | Filter symbolic `origin/HEAD` via `%(symref)`; treat exit 128 as null |
| 4.2 blame on 50 hotspot files is affordable | CONFIRMED | 4.4 s for 50 files on ralph |
| 4.9 / concern 5: `.tech-debt/` + file negation fails, `.tech-debt/*` needed | CONFIRMED | Design statement is correct |
| Concern 5: the `.tech-debt/*` form "breaks for every user who already ignores `.tech-debt/`" | PARTIAL | A leading `!.tech-debt/` line fixes every variant tested, including info/exclude and global excludes; option B is cheaper than stated |
| 4.4 tools present on this machine | CONFIRMED (ruff only) | Probe should also check `node_modules/.bin`; JS tools otherwise never found |
| 4.4 ruff JSON gives file, line, rule | CONFIRMED | Absolute backslash `filename` must be normalised |
| 4.4 non-zero exit means `failed` | REFUTED | ruff, gitleaks and osv-scanner exit 1 on findings; per-tool exit table or `--exit-zero` |
| 4.4 `UP` selects deprecation rules | REFUTED | `UP` is pyupgrade; use UP035 only |
| Concern 4: osv-scanner uses the network by default | CONFIRMED | Sends names, versions, ecosystems, hashes; `--offline` with a pre-downloaded database exists |
| Concern 4: gitleaks needs no network | CONFIRMED | Local `git log -p`; project is feature-complete, successor named |
| Concern 6 / 4.11: nothing in ralph reads `category`; required keys unchanged | CONFIRMED | Name all six required keys (`id`, `type`, `severity`, `attempts`, `created_at`, `updated_at`) plus `target_repo` |
| 4.13 commands under the Windows argv ceiling, no embedded file lists | CONFIRMED | Longest expanded command 299 characters |
