# Assumption validation summary for the v2 design

Consolidates the four validation reports in this directory (`07-validation-source-claims.md`, `07-validation-git-tools.md`, `07-validation-fanin-patterns.md`, `07-validation-citations.md`) into the amendments the design brainstorm (`06-design-brainstorm.md`) needs before it becomes a spec. Written 2026-09-02.

## Headline

| Report | Checked | Confirmed | Partial | Refuted or misread |
|---|---|---|---|---|
| Source and test claims | 17 | 15 | 2 | 0 |
| Git, gitignore and tool experiments | 18 | 12 | 2 | 3 |
| Fan-in, cycles, regex leads, timing | 4 verdicts | 1 | 1 | 2 as designed (confirmed after amendments) |
| Citation traceability | 32 | 16 | 8 secondary or thin | 6 misread, 2 not found |

No family, stage or disposition is removed. The design survives with amendments in four areas: the parser and linter contracts, the git pass and tool probe details, the fan-in heuristic and two regex rules, and the wording of several evidence claims. Three items interact and must be settled together by the first live run: the bounded verifier context, the unvalidated complexity half of the hotspot interest term, and the unsupported 0.80 precision bar.

## Amendments to fold into the spec

### Parser, linter and test contracts (from the source-claims report)

1. `design_parser.py` ends a finding section only at the next H2, so every H1 that follows a finding is absorbed into that finding's `body_md` and copied into its PBI. The v2 layout puts "Below the cut", "Considered and rejected" and the rest after the findings, so the last promotable PBI would carry them. Fix: stop a section at an H1 as well (one condition at `design_parser.py:194`) plus a round-trip test. The claim "parser contract unchanged" is withdrawn.
2. `skill_check.py` takes the first `{a,b}` group in the top-level help as the subcommand list, and argparse prints optionals first. A script with subcommands and any top-level `choices=` option breaks the lint with a misleading "flag not accepted" message. Constraint for `design_writer.py` and `baseline.py`: every `choices=` option lives on a subparser. Flag matching is substring-based, so `--top` is satisfied by `--top5`; keep flag names distinct.
3. `churn` stays 0 when git is absent (`test_inventory.py:81` asserts it, `:61` compares it). Only the new history fields (`last_touched`, `authors`, `top_author_share` and so on) may be null.
4. The artefact walk must exclude the scan's own committed state files; `DEFAULT_IGNORE` matches `.tech-debt` by whole path part, so `.tech-debt.yaml` and `.tech-debt-baseline.json` would be classed as `config` artefacts.
5. `category` is a required anchor key and `bundle_writer.py:80` reads it unconditionally; the `family` alias must always be emitted, not only for one release by default.
6. Baseline write-back failure needs its own exit code; 4 already means "bundle write failed after a success".
7. The seven parser tests derive input from `tests/golden/design.md` by exact substring replacement (`status: pending`, `slug: finding-1`, `category: god-modules`). The v2 golden keeps those substrings or the tests get their own fixtures. `test_categories.py:62-66` requires "hotspot" and "Severity rubric" in every prompt; the v2 shared prefix must keep both words.
8. `accepted` is validated from phase 1 but `promote.py:110-111` counts it as pending until phase 5. Teach `promote.py` the count in the same phase the status is added.
9. `confidence` in a v1 anchor is parsed and discarded, not ignored on parse.

### Git pass, gitignore and tool probe (from the git-tools report)

10. Git pass: add `-c core.quotePath=false` and decode UTF-8, or non-ASCII paths arrive C-quoted; split the header line with `maxsplit=3` because subjects contain tabs.
11. Join churn and coupling against files present at HEAD. In ralph the top hotspot (27 commits) and the top coupled pair both named a file deleted at HEAD.
12. Author identity: `%aN` with a `[bot]` filter is not enough. Without `.mailmap` one person appears as two identities, and `Claude` and `Claude (worktree)` authors carry no `[bot]` marker, so the ownership family's three-author gate passes on a one-person repository. Record `%aE` as well, key authors by email, and add a configurable `bot_authors` list (default includes `Claude`, `dependabot`, `renovate`, `github-actions`).
13. Branch and tag commands: filter the `origin/HEAD` symref (`%(symref)` is non-empty), treat exit 128 from `merge-base --is-ancestor` as null rather than unmerged.
14. Gitignore: the design's claim that option B "breaks for every user who already ignores `.tech-debt/`" is refuted. Writing `!.tech-debt/` then `.tech-debt/*` then `!.tech-debt/baseline.json` works for every variant tested (`.tech-debt/`, `.tech-debt`, `**/.tech-debt/`, `.git/info/exclude`, global excludes). The root-file option has its own edge: a user rule `.tech-debt*` ignores it. Decision 5 reopens with both options viable.
15. Tool probe: ruff, gitleaks and osv-scanner all exit 1 when they find something. "Non-zero means failed" is refuted; use a per-tool exit-code table (or `--exit-zero` where offered) and treat unparseable JSON as the failure signal. Ruff emits absolute backslash filenames even for relative input; normalise. `UP` is pyupgrade, not deprecation; only `UP035` flags deprecated imports. Probe `<root>/node_modules/.bin` as well as PATH; never `npx`. osv-scanner JSON carries no line numbers, so its evidence is manifest-level. Only ruff is installed on this machine; the corpus goldens must use canned tool output.
16. osv-scanner sends package names, versions, ecosystems and file hashes to OSV.dev by default; `--offline` exists with a pre-downloaded database. gitleaks is local-only. The design's network notice is warranted; document `--offline` as the private-repository path.
17. Ralph reads none of `category`, `debt_type` or the family names. Its parser requires six PBI keys (`id`, `type`, `severity`, `attempts`, `created_at`, `updated_at`) and `target_repo` at claim time; unknown keys are ignored. Section 4.11 names all six.

### Fan-in heuristic, cycles and regex leads (from the fan-in report)

18. Approximate fan-in as designed is refuted for ranking: edge precision 0.14 to 0.18, Spearman 0.58 to 0.67 against the true import graph, and the F term off by more than 0.25 for 16 to 18 percent of files, driven by the `__init__` stem (28 to 41 percent of all approximate edges) and repository vocabulary no fixed stoplist covers. Two changes make it usable: match stems only in import-like lines (with continuation lines) for path-import languages, and mark any stem shared by two or more files, any package or index file, and any test-harness file as ambiguous. With those, precision 0.90 to 0.98, recall 1.0, Spearman 0.985 to 1.0, and `wF` 0.5 is safe. Keep the anywhere mode as a labelled lower-confidence fallback for C# and Java. Minimum stem length stays 4. Do not map package files to their directory name.
19. Approximate cycles as designed found 0 real cycles in 3 emitted and 0 of 7 true ones. From the import-line graph they become capped leads for the architecture scout only, never statistics, with a note that Python recall is low because cycles route through package re-exports.
20. Dead-code corroboration by fan-in 0 applies to ordinary modules only; entry points, scripts run by name and pytest-discovered files have import fan-in 0 without being dead, and the dead-code verifier question must name them.
21. Exception-swallow rule: keep `pass` and `return None` bodies; keep log bodies only when the log call does not carry the exception (no `exc_info`, no `.exception(`, no use of the `as` name), which removes every sampled false positive; emit `annotated: true` for a trailing comment or `noqa`; emit `BaseException` as its own higher-severity rule.
22. Commented-out code rule: 0 of 33 hits were code. Replace the punctuation test with "the run, stripped of comment markers, parses as a statement list" (`ast.parse` for Python; a keyword or assignment majority for other languages). As written it does not ship.
23. Credential rule: 0 of 9 hits were real (7 test fixtures, 2 `$VAR` placeholders). Exclude values starting with `$`, `${`, `{{`, `<`, `%` and values matching placeholder words; the fixture corpus needs seeded true positives.
24. Timing confirmed: stem graph 4.6 s and regex pass 3.6 s at 5,000 files; an inverted stem index removes the quadratic loop.

### Evidence wording (from the citations report)

25. Complex-units: the F1 0.87 to 0.89 range is the best of four models on three Java smells; nesting, conditionals and parameter counts were not measured. Keep default-on; drop "no tool needed".
26. Verifier: the 95.5 percent false-positive identification came from an agent exploring the repository; vanilla prompting reached 36.4 percent. The design's 30-line bounded verifier is closer to the vanilla condition. Give the verifier a bounded exploration allowance (open up to three referenced files on request) and expect a lower starting precision.
27. Hotspot interest term: Code Red groups files by Code Health only, with no churn component, and is vendor-authored. Churn is supported by the change-coupling studies; the indentation-complexity half is unvalidated. Reword principle 1, hold `wH` at default, add a fixture check.
28. "Self-reported confidence is near-random" cites a study of correctness judgement, not confidence self-reports. The decision to drop the field rests on the ACE validation results instead.
29. Architecture precision "64 to 82 percent" was measured against a tool's output, not humans; say "unmeasured against humans", keep verifier-mandatory and tier B.
30. The 0.80 tier A precision bar has no source. Present it as a provisional convention that the first live run tests. "The only measured one available" is withdrawn.
31. Chunking thresholds are untuned defaults: 200k LOC is a README remark; 1,500 files appears nowhere before the design.
32. The SATD miner is justified by determinism, blame age and corroboration, not by accuracy; zero-shot LLMs still beat the keyword baseline. The 0.58 figure belongs to a four-tag matcher, not the 62-pattern list.
33. Duplication importance rests on vendor data while the confirmed 71 percent benign-clone figure points the other way; re-score importance to 3. The tier B cap already protects the disposition.
34. Google's result: the linear-model null and the random-forest precision figure are from the same paragraph and consistent; the random-forest half supports the tier logic and should be cited that way. Principle 8 rests on the SonarQube and clone studies.
35. The 50 to 63 percent false-positive prior comes from one Python project's static-detector output; treat as an expectation for `evaluate.py` to replace.
36. Migration rank 6: Google's ordering is explicitly non-generalising; carry the thin flag in the reason column.

## Concern status after validation

| Concern | Status | Updated recommendation |
|---|---|---|
| 1. Verifier precision bar | Unvalidated; evidence now weaker (item 26, 30) | Option B: report the number at v2.0, make it hard at v2.1, and give the verifier the bounded exploration allowance |
| 2. Twelve default scouts | Unchanged | Adaptive by leads |
| 3. Approximate fan-in | Refuted as designed, confirmed with items 18 to 20 | Option A with the import-line and ambiguity amendments; `wF` 0 if either is dropped |
| 4. osv-scanner network | Confirmed | Option C, on with a SKILL.md notice, plus a documented `--offline` path |
| 5. Baseline location | Design's objection to option B refuted (item 14) | Reopened: B (gitignore triple with leading negation) keeps the root clean; A (root file) needs no gitignore edit but is caught by a `.tech-debt*` rule |
| 6. Family renames reach ralph | Confirmed harmless (item 17) | Option A, alias always emitted (item 5) |
| 7. Secret leakage | Credential rule precision 0 of 9 on real repositories; redaction still required | Option A, with placeholder filtering (item 23) |

## Confidence changes

| Component | Was | Now | Reason |
|---|---|---|---|
| Approximate fan-in and SCC | 75 | 90 with items 18 to 20 | measured precision 0.90 to 0.98 after amendments |
| Verifier and tiers | 70 | 60 | bounded context is closer to the 36 percent condition; bar unsupported |
| Tool probe | 80 | 85 | exit codes and JSON shapes now known for ruff; others need canned output |
| patterns.py | 90 | 85 | two of three sampled rules failed as written; fixes specified |
| Inventory git pass | 90 | 90 | confirmed fast and correct with items 10 to 13 |
| Reporting | 90 | 85 | parser change required (item 1) |
