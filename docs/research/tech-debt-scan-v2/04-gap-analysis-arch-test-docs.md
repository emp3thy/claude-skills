# Gap analysis: architecture, test, documentation, requirements and defect families

Research note for tech-debt-scan v2. Compiled 2026-09-02. Checks ten rows of `02-debt-types-consolidated.md` (TD-04, 06, 07, 08, 10, 12, 15, 18, 28, 32) against the current skill under `skills/tech-debt-scan/` and states the minimal steps that close each gap, consistent with section 3 of `05-architecture-best-practice.md`.

## 0. How the current skill searches

Three facts shape every verdict below.

- **Scouts are the only detector.** `scripts/categories.py` holds eight prompts (`god-modules`, `duplication`, `dead-code`, `test-gaps`, `doc-drift`, `half-finished`, `dependency-debt`, `architecture`) plus a shared output contract (`_OUTPUT_SCHEMA`, lines 28-62). A finding exists only if a prompt bullet led an LLM to look for it. There is no SATD miner, no tool probe and no verifier.
- **The inventory carries four signals.** `scripts/inventory.py` emits per file `loc`, `complexity` (indent units), `max_indent`, `churn` (commits in the window) and a top-20 `hotspots` list. The git pass at lines 130-160 discards commit boundaries, so nothing about co-change, authorship, commit messages, last-touched date, bug-fix share or test-to-source mapping survives. Only source extensions plus `.md` are walked (lines 33-54), so YAML, TOML, RST and CI files are invisible to the inventory even though scouts may read them.
- **The contract is fixed by tests.** `tests/test_categories.py` pins exactly eight category names, forbids the strings `def `, `import `, `.py file` and `Python module` in any prompt, and requires every prompt to contain the schema keys, the word "hotspot" and "Severity rubric". `tests/test_inventory.py` pins the exact key set of each hotspot entry and the fixture file counts. `validate_synthesis_output` rejects any category not in `CATEGORIES` (`build_synthesis_prompt.py:262`) and any `debt_type` outside `VALID_DEBT_TYPES` in `validation.py:15-26` (code, design, architecture, test, documentation, dependency, build, requirement).

Effort marks: S under half a day, M up to two days, L larger.

## TD-04 Missing or insufficient tests (rank 4)

**Verdict: PARTIAL.** The `test-gaps` prompt (`categories.py:106-117`) is the only searcher. It asks for "Core modules or critical paths with no corresponding test file" (line 109), "Error-handling and edge-case branches that no test exercises" (110), "Tests that assert nothing meaningful" (111-112) and hotspot files lacking regression tests (113-114).

| Symptom (consolidated) | Status | Where |
|---|---|---|
| No test directory or low test-to-source ratio | not searched | inventory has no path class |
| Production modules with no matching test file | searched | `categories.py:109` |
| skip, xfail, @Ignore, @Disabled markers | not searched | |
| Empty or assert-free tests | searched | `categories.py:111-112` |
| "TODO enable proper tests" comments | searched implicitly | `half-finished` markers, `categories.py:132-133`, not routed to test debt |
| Absent or low coverage threshold in CI config | not searched | CI files not inventoried |
| Source changed in commits with no test change | not searched | commit boundaries discarded |

**Quality.** The prompt names no naming conventions, ratio or search procedure, so two scouts map source to tests differently. Line 110 asks the scout to judge branch coverage by reading, which the reference architecture says must be reported as "not assessed". The evidence contract does not require the scout to list the test paths it searched, so a false "no test file" claim cannot be checked at review. Ranking accepts it: `test-gaps` and `debt_type: test` exist, and the category is in `CORE_CATEGORIES`.

**Gap steps.**

1. Add a path class and test-to-source mapping to `inventory.py`: classify files as `test`, `source`, `doc` or `config` by path pattern (`tests/`, `__tests__/`, `test_*`, `*_test.*`, `*.spec.*`, `*Tests.cs`), map each source stem to candidate test files, and emit per-file `path_class` and `mapped_tests` plus a repo-level `test_to_source_ratio`. New fixture directory with a planted untested module and a decoy tested under an unconventional name; `test_inventory.py` gains assertions and existing counts are untouched. M.
2. Keep commit boundaries in the git pass (`git log --since=<n> months ago --name-only --format=%x1e%H` and split on the separator) and count, per source file, commits that touched it with no `test`-class file in the same commit; emit `untested_change_share`. S once step 1 exists.
3. Mine skip and expected-failure markers deterministically (`@pytest.mark.skip`, `xfail`, `@Ignore`, `@Disabled`, `it.skip`, `test.skip`, `xit(`, `[Ignore]`, `t.Skip(`) with file, line and quote; feed them to the scout as leads. Fits the stage-2 miner the reference architecture already calls for. S.
4. Detect a coverage gate in config by filename, not extension (`fail_under` in `.coveragerc` or `pyproject.toml`, `coverageThreshold` in Jest config, `check-coverage` in nyc, `codecov.yml`); emit `coverage_gate_present`. S.
5. Rewrite the prompt around leads: start from unmapped hotspot-band files, skip markers and high `untested_change_share`; require the evidence note to list the test paths searched; delete line 110's branch-coverage guess and add "coverage numbers are not assessed, never estimate them". S.
6. Verifier at moderate need. Tier A when the mapping script and the scout agree; tier B for a reading-only claim.

**Risk.** LLM coverage claims are plausible and unverifiable until the mapping script makes them checkable. A test file that asserts nothing is still a gap, so step 1 combines with the assert-free rule. Do not run the suite or a coverage tool.

## TD-06 Migration and lava-layer debt (rank 6)

**Verdict: PARTIAL, split across two scouts.** `half-finished` asks for "Partially migrated patterns (old and new approach coexisting, count how many call sites still sit on the old side)" (`categories.py:137-138`). `dependency-debt` asks for "Two or more packages doing the same job" (150-151) and "Vendored or copy-pasted library code that has diverged from upstream" (152).

| Symptom | Status | Where |
|---|---|---|
| Coexisting old and new implementations | searched | `categories.py:137-138`, `150-151` |
| Shims between them | not searched | |
| Partially applied codemods | not searched | |
| Mixed build systems | not searched | |
| "migrate", "deprecate", "legacy", "port" in commits and issues | not searched | no commit messages in inventory |
| Long-lived migration branches | not searched | no branch data |
| Vendored forks of upstream | searched | `categories.py:152` |
| Obsolete framework kept behind workarounds | searched implicitly | `categories.py:147-148` (staleness only, no workaround link) |

**Quality.** The old-side call-site count is the evidence the reference architecture wants, so the existing bullet is good. But Google's number-one hindrance is one bullet of four in a marker-oriented prompt, and the synthesis rule "prefer a spread of categories" (`build_synthesis_prompt.py:201-202`) makes a migration finding compete with marker findings inside `half-finished`. `debt_type: architecture` fits; no category names migration.

**Gap steps.**

1. Give migration its own family, `migration`: dual implementations with the old:new call-site ratio; paths named `legacy`, `old`, `v1`, `v2`, `compat`, `shim`; adapter modules that only bridge the two; two package managers, two lockfiles or superseded config formats side by side; a framework pinned behind workaround comments. Ask for the last commit that moved a call site as evidence the migration is still moving. `test_categories.py` `EXPECTED` and the golden `raw-findings.json` (pinned at 30 items) change. M.
2. Add commit-subject keywords to the inventory from the same git pass (`--format=%x1e%H%x09%s`): count commits per file whose subject matches `migrat|legacy|deprecat|port(ed|ing)|codemod|upgrade`; emit `migration_commit_count` per file and the top ten matching commits repo-wide. S.
3. Emit `naming_hints`: paths matching the names in step 1. S.
4. Branch age via `git for-each-ref --sort=committerdate refs/remotes` is cheap but noisy because remotes are pruned; optional, S.
5. Verifier at moderate need. The verifier must check churn on both sides: churn on the old side only means an abandoned migration, churn on neither side means dead code (route to TD-09). Tier A when keyword commits, dual implementation and change coupling agree.

**Risk.** Two implementations of one interface are often a deliberate strategy or multi-backend design, and "is it still planned" is human knowledge. Never assert "abandoned" from reading alone; require the churn evidence.

## TD-07 Cyclic dependencies (rank 7)

**Verdict: PARTIAL.** One bullet: "Circular dependencies between modules or packages" (`categories.py:163`). No graph, tool or lead is supplied; the scout must discover cycles by reading.

| Symptom | Status | Where |
|---|---|---|
| Import cycles in the module graph (DFS up to 5 hops) | searched, no method | `categories.py:163` |
| Class-level cycles merging into multi-hubs | not searched | needs a parser |
| Every component depending on most others | searched implicitly | `categories.py:169-170` (hubs) |
| No boundary tooling in manifests | not searched | |

**Quality.** Reading cannot build a dependency graph over hundreds of files, and the literature puts LLM precision on structural smells at 64 to 82 percent with 63 percent of static-detector findings intentional. The prompt cannot even say "import graph": `test_prompts_avoid_python_specific_terms` forbids the token `import `, which is why the current wording is "circular dependencies". Category and `debt_type` both `architecture`, so ranking accepts it.

**Gap steps.**

1. Stage-3 tool probe: `madge --circular --json` or `depcruise --output-type json` for JavaScript and TypeScript, `pycycle` or `import-linter` for Python, `jdepend` for Java, when installed; normalise to `tool-signals.json` cycles keyed by file. Never install. M, shared with the other slice's probe.
2. Inventory fallback: an approximate reference graph (edge A to B when A's text references B's stem), Tarjan SCC, and `cycles` of size 2 to 5 plus per-file `fan_in_approx` and `fan_out_approx`. Stem collisions (`utils`, `config`) create false edges, so every cycle is labelled approximate. M.
3. Boundary-tooling check by filename: `.dependency-cruiser.*`, `[tool.importlinter]`, `packwerk.yml`, ArchUnit in test dependencies; emit `boundary_tooling`. Absence is a severity modifier, never a finding. S.
4. Prompt: replace line 163 with a leads-driven instruction: for each tool or approximate cycle, open the member files and quote the referencing lines that close it; report cycle length and whether members are hotspots or change-coupled. Say "module references" to satisfy the forbidden-term test. Add the trap that Go and .NET forbid package-level cycles at compile time, so such a claim there is almost certainly wrong. S.
5. Verifier mandatory. Tool-confirmed cycle plus scout is tier A; reading-only is tier B at best per section 3. Class-level cycles are "not assessed" without a parser.
6. Fixture `tests/fixtures/cyclic-repo`: a three-file cycle planted, plus a decoy file referencing another file's stem only in a comment. New `test_inventory.py` cases for SCC output.

**Risk.** Highest false-positive family in the taxonomy. Do not ask the LLM to enumerate cycles unaided, do not score cycle counts, and do not report cycles in compile-forbidden languages.

## TD-08 Documentation debt (rank 8)

**Verdict: PARTIAL, drift covered and absence not.** `doc-drift` (`categories.py:118-128`) asks for README flags and commands the code no longer accepts (121-122), stale comments contradicting code (123), examples that would fail (124), and API or schema docs out of sync with signatures (125).

| Symptom | Status | Where |
|---|---|---|
| Absent or stub README | not searched | |
| README commands and paths that no longer exist | searched | `categories.py:121-122` |
| Public symbols without doc comments | not searched | |
| Docstrings contradicting signatures | searched | `categories.py:123`, `125` |
| Docs referencing deleted identifiers or files | searched implicitly | `121-122` covers README only |
| CHANGELOG stale relative to tags | not searched | no tag data (the golden has one, hand-authored) |
| No ADRs or contributing guide | not searched | |
| Docs untouched while referenced code churned | not searched | no doc-to-code link, no last-touched date |
| "needs documentation" comments | searched implicitly | `half-finished` markers, not routed to documentation |

**Quality.** The drift bullets are concrete and cheap to verify by comparing two artefacts. The "missing" half (35 of 101 documented doc defects) is absent, and the git channel the academic report rates strong, docs untouched while code changed, has no data. The category is outside `CORE_CATEGORIES`, so a quick scan skips Google's rank-2 hindrance. `doc-drift` and `debt_type: documentation` fit.

**Gap steps.**

1. Walk doc files (`.md`, `.rst`, `.adoc`, `docs/`) as `path_class: doc` and emit a `docs` block: `readme_present` with LOC, `contributing_present`, `adr_dir_present`, and `changelog_present` with its last commit date against the latest tag (`git describe --tags --abbrev=0`; `git log -1 --format=%cI -- CHANGELOG.md`). S.
2. Doc-to-code staleness: extract backtick and path-like tokens from each doc, check they exist (`dangling_refs`), and compare the doc's last commit date with the newest among referenced files (`stale_vs_code_days`). Needs per-file last-touched dates from the git pass. M.
3. Public-symbol doc-comment ratio needs a parser per language; a regex approximation is low precision, so report per module or mark "not assessed". S if attempted.
4. Prompt: add absent or stub README, missing contributing guide and ADRs, CHANGELOG behind tags, and the `dangling_refs` leads; require each drift finding to cite both the doc line and the code line it contradicts. S.
5. Add `doc-drift` to `CORE_CATEGORIES`. `test_core_categories_are_a_subset` still passes. S.
6. Verifier cheap; tier B until the live evaluation reports an F1.

**Risk.** Missing docstrings are diffuse and individually trivial; one finding per undocumented function would flood the list. Aggregate per module and keep the absence of ADRs at severity 2 or below on its own.

## TD-10 Layering and modularity violations (rank 10)

**Verdict: PARTIAL, with one bullet that cites data the inventory does not carry.** The `architecture` prompt asks for layering violations (`categories.py:164-165`), shotgun surgery where "co-changing files in the churn data are the tell" (166-168), unstable hubs with high fan-in and fan-out (169-170), missing seams (171-172) and configuration sprawl (173). The inventory has no co-change data, so line 168 points the scout at a signal that does not exist.

| Symptom | Status | Where |
|---|---|---|
| UI or handlers importing persistence directly | searched | `categories.py:164-165` |
| Fan-in and fan-out over 20 | searched, no threshold or data | `categories.py:169-170` |
| Stable modules depending on unstable ones | not searched | |
| Components over 30 classes or 27,000 LOC | not searched | no directory aggregation |
| Component cohesion under 0.2 | not searched | needs a parser |
| Shared mutable global state | not searched | `171-172` is about side effects, not state |
| Functionality in the wrong component | not searched | human intent |
| Several inconsistent copies of one data model | searched implicitly | `duplication`, `categories.py:82-83` |
| Shotgun-surgery commits across many directories | searched, data absent | `categories.py:166-168` |

**Quality.** Layering claims rest on layers inferred from directory names with no stated procedure, and hub claims carry no numbers. The prompt correctly says fixes are usually effort L. Category and `debt_type` `architecture` fit.

**Gap steps.**

1. Change coupling in the inventory from the TD-04 git pass: per-commit file sets with commits touching over 50 files excluded as bulk changes, pair counts, `coupling` entries `{a, b, shared_commits, ratio, cross_directory}` at 3 or more shared commits and a 30 percent ratio, and per-file `coupling_degree`. Tests need a git-built temporary repository helper in `conftest.py`. M.
2. Directory aggregation: per top-level and second-level directory, file count, LOC, churn sum and directory-to-directory edges from the approximate graph of TD-07 step 2; flag directories over 27,000 LOC or 30 files as god-component leads. S with the graph.
3. Instability per directory, fan-out over fan-in plus fan-out; flag edges from a stable directory (under 0.3) to an unstable one (over 0.7), marked approximate. S with the graph.
4. Prompt: point the shotgun bullet at `coupling`; add global mutable state and duplicated data models; put numbers on hubs (fan-in and fan-out both over 20, or top 5 percent); require the scout to state the layers it inferred and cite `ARCHITECTURE.md`, an ADR or an import-linter contract when one exists. S.
5. Verifier mandatory; tier A only with coupling or tool corroboration; "wrong component" claims are tier C for a human.
6. Fixture: a git-built repository where `ui/view.py` and `db/repo.py` co-change in four of five commits with no reference between them (the S34 definition of a modularity violation), plus a decoy pair that co-changes only in a bulk version-bump commit.

**Risk.** The 63 percent intentional rate applies here most. Do not report "monolith" as a finding, and do not score global coupling metrics; the reference architecture excludes them.

## TD-12 Test smells (rank 12)

**Verdict: ABSENT.** The only overlap is `test-gaps` line 111-112 (assert-free tests), which is Unknown Test filed as a gap.

| Symptom | Status |
|---|---|
| Assertion Roulette | not searched |
| Eager Test | not searched |
| Unknown Test (no assertion) | searched under `test-gaps`, `categories.py:111-112` |
| Conditional Test Logic | not searched |
| Mystery Guest, Resource Optimism | not searched |
| Sleepy Test | not searched |
| Magic Number Test | not searched |
| Exception handling in tests | not searched |
| Duplicate Assert | not searched |
| General Fixture | not searched |
| toString asserts | not searched |

**Quality.** No category exists, so a scout cannot emit one that passes `validate_synthesis_output`. `debt_type: test` fits.

**Gap steps.**

1. New family `test-quality` covering TD-12 and the TD-18 indicators, leaving `test-gaps` for TD-04. The prompt lists the tsDetect catalogue with lexical thresholds: Assertion Roulette at three or more unmessaged assertions, Eager Test at three or more distinct production calls, Unknown Test as no assertion and no expected exception, Conditional Test Logic as branching or loops in the body, Mystery Guest and Resource Optimism as external access without an existence check, Sleepy Test, Magic Number Test, exception handling in the body, Duplicate Assert, General Fixture, toString equality. Findings aggregate per file at severity 2 to 3 unless the file is in the hotspot band or an Unknown Test guards a critical path. Trap: Go table-driven loops and parametrised tests are idioms, not conditional logic. `EXPECTED` in `test_categories.py` changes. M.
2. Deterministic lead miner over `test`-class files (from TD-04 step 1): per test file, counts of sleep calls, try or catch blocks, assertion statements per test function, numeric literals in assertions, file or socket constructors; emit to a `test-signals.json`. This is the language-agnostic stand-in for tsDetect, which is Java-only. S.
3. Verifier at low need (74 to 80 percent LLM accuracy on lexical rules); tier A when the miner and scout agree, tier B otherwise.
4. Fixture: a test file with a sleep, an assertion-free test and a conditional test planted, and a table-driven decoy.

**Risk.** With 97 percent of test files smelly, this family floods the candidate list; the per-scout cap and the family spread rule in ranking matter more here than anywhere else. About 2 percent of smells are ever fixed, which is why importance is 3; occurrence must not promote it.

## TD-15 Change coupling and hotspots (rank 15)

**Verdict: PARTIAL, hotspots present and coupling absent.**

| Symptom | Status | Where |
|---|---|---|
| Change frequency times complexity per file | collected | `inventory.py:163-186`; consumed at `categories.py:32-37` and `build_synthesis_prompt.py:120-134` |
| Co-changing file pairs across module boundaries | not collected | `inventory.py:156-159` drops commit boundaries; `categories.py:166-168` asks for it anyway |
| Churn concentrated in already-complex files | collected | hotspot score |

**Quality.** Hotspots are correctly treated as interest, not as a finding. Two defects: the amplifier is applied twice, once as a scout severity increment (`categories.py:35-36`, and the rubric line 41 "3 + hotspot") and again as `HOTSPOT_BOOST` 1.5 in the ranker (`build_synthesis_prompt.py:63`); and the list is a top-20 cut normalised by the repository maximum, so one outlier file suppresses every other hotspot.

**Gap steps.**

1. Change coupling in the inventory, as in TD-10 step 1. This single signal corroborates TD-07, TD-10 and TD-06 and is the reporting condition for duplication in the other slice. M.
2. Move the amplifier to the ranker only: delete lines 32-37 and the "3 + hotspot" clause, and replace `HOTSPOT_BOOST` with the reference formula's interest term (`1 + wH·H + wC·C`, C the coupling degree). `test_priority_score_boosts_hotspot_evidence` changes; the prompt test still passes if "hotspot" stays as guidance. S.
3. Emit per-file `hotspot_score` and a top-decile `hotspot_band` beside the display list; add no keys to hotspot entries, whose key set `test_inventory.py:72` pins. S.
4. Render the hotspot summary and top coupled pairs as an optional `design.md` section, off when data is absent so the golden stays byte-identical. S.
5. Same-author and same-ticket coupling need conventions the scan cannot know; skip.

**Risk.** Co-change has benign causes (feature work across UI and API, generated code, version bumps). The bulk-commit filter and ratio threshold handle most of it, and coupling is a corroborator, never a finding by itself.

## TD-18 Flaky tests (rank 18)

**Verdict: ABSENT.** No prompt mentions tests being non-deterministic. `categories.py:171-172` (side effects in production code) is about testability, not test flakiness.

| Symptom | Status |
|---|---|
| Retry decorators or @flaky | not searched |
| Sleep-based waits | not searched |
| Wall clock, network, ordering, randomness, shared static state | not searched |
| CI retry-on-failure config | not searched |
| "flaky" in commit messages | not searched |

**Gap steps.**

1. A "flakiness leading indicators (unconfirmed)" block in the `test-quality` prompt: sleep waits, retry markers (`@flaky`, `@pytest.mark.flaky`, `jest.retryTimes`, `retries:` in Playwright or Cypress config, NUnit `[Retry]`), wall-clock reads in assertions, unseeded randomness, real hosts or ports, shared module-level mutable state. Every finding is labelled unconfirmed with severity capped at 3 without CI evidence. S within the TD-12 step.
2. The same test-signals miner counts sleeps, retry markers, `now()` calls and unseeded random calls per test file. S.
3. Commit-subject keyword `flak` per test file from the TD-06 keyword pass, emitted as `flaky_fix_commits`. S.
4. CI config check by filename for `--reruns`, `pytest-rerunfailures`, `retry`, `rerun` in workflow YAML and test runner config; emit `ci_retry_config` with file and line. S.
5. Verifier at low need; never tier A without CI data, per the consolidated report's runtime-only caveat.

**Risk.** Prevalence is unmeasurable statically and the indicators cover about three quarters of root causes. A sleep can be correct (rate-limit tests), and fake timers or a frozen clock should downgrade the finding. Never claim a test is flaky and never run it.

## TD-28 Requirements debt (rank 28)

**Verdict: PARTIAL.** `half-finished` asks for stubs that "return a placeholder or raise 'not implemented'" (`categories.py:134`) and marker comments (132-133).

| Symptom | Status | Where |
|---|---|---|
| NotImplementedError stubs | searched | `categories.py:134` |
| "not implemented yet", "no methods yet for" | searched implicitly | `categories.py:132-134` |
| Hard-coded happy-path handling | not searched | |
| No timeouts, pagination or validation | not searched | |
| Stubs surviving many commits | not searched | no blame age |
| Vague wording in in-repo specs | not searched | human channel |

**Quality.** Adequate for stubs. `debt_type: requirement` exists and the category fits. Importance is 2, the weakest cost association in the taxonomy, so steps are minimal.

**Gap steps.**

1. Stage-2 SATD miner: include stub patterns (`NotImplementedError`, `NotImplementedException`, `throw new Error("not implemented")`, `panic("not implemented")`, `unimplemented!()`) with `git blame` age and the number of commits to the file since introduction, so "stubs surviving many commits" is measurable. S within the miner.
2. Prompt: one bullet for hard-coded happy paths and absent guards (no error branch where the contract implies several, no validation at a trust boundary, no timeout on a network call, unbounded list without pagination), each citing the call and the missing guard, `debt_type: requirement`. Coordinate with TD-34 in the other slice so timeouts and pagination are asked for once. S.
3. Trap in the prompt: abstract base members that raise not-implemented are the pattern, not debt. S.
4. Do not attempt spec-smell detection; the specification lives outside the repository.

**Risk.** Abstract methods, interface defaults and plugin hooks are the standard false positives. Keep severity at 3 or below unless the stub sits on a user-facing path.

## TD-32 Defect debt (rank 32)

**Verdict: PARTIAL, and unfilable.** `half-finished` lists `WORKAROUND` among its markers (`categories.py:132`); "known bug", expected-failure markers and issue references are not asked for. No `defect` value exists in `VALID_DEBT_TYPES`, so a defect finding must be misfiled as `code` or `requirement`.

| Symptom | Status | Where |
|---|---|---|
| "known bug", "workaround", "bug in the above method" comments | searched partially | `categories.py:132` (workaround only) |
| xfail markers | not searched | |
| Issue links marked won't-fix | not searched | tracker data |
| Catch-all swallowing around a known failure | not searched | error masking is in the other slice, the "known failure" link is not asked |
| Issue references in commits never closed | not searched | tracker data |

**Gap steps.**

1. Add `defect` to `VALID_DEBT_TYPES` (`validation.py:15-26`), to the contract text at `categories.py:52-53` and to `_output_schema` at `build_synthesis_prompt.py:98-99`. `test_validation.py` parametrises the accept test over the set and its reject list (`""`, `Code`, `perf`, `tests`) does not name `defect`, so no test changes. S.
2. Miner patterns: `known bug`, `known issue`, `kludge`, `workaround`, `@pytest.mark.xfail`, `expectedFailure`, `test.fail`, `it.fails`, and issue references (`#\d+`, `issues/\d+`, `[A-Z]+-\d+`) inside comments, with blame age. S.
3. Prompt bullet in `half-finished`: known-defect markers and expected-failure tests, citing the marker and any issue reference, `debt_type: defect`. S.
4. Tracker lookups (`gh issue view`) are out of scope for an offline read-only scan; report "not assessed".

**Risk.** Contested as debt by four studies and ranked 32; an xfail with a reason and a ticket is process working correctly. Spend no verifier budget here and do not create a category; age is the only severity lever.

## Summary

| ID | Name | Rank | Verdict | Symptoms searched / total | Headline gap step | Effort |
|---|---|---|---|---|---|---|
| TD-04 | Missing tests | 4 | PARTIAL | 2 + 1 implicit / 7 | Path class and test-to-source mapping in the inventory; prompt rewritten to leads with no coverage guessing | M |
| TD-06 | Migration debt | 6 | PARTIAL | 2 + 1 implicit / 8 | Own `migration` family plus commit-keyword and naming-hint signals | M |
| TD-07 | Cyclic dependencies | 7 | PARTIAL | 1 + 1 implicit / 4 | Tool probe with approximate-graph SCC fallback; verifier mandatory | M |
| TD-08 | Documentation debt | 8 | PARTIAL | 3 + 2 implicit / 9 | Doc presence, dangling refs and doc-vs-code staleness in the inventory; add to `CORE_CATEGORIES` | M |
| TD-10 | Modularity violations | 10 | PARTIAL | 3 + 1 implicit / 9 | Change coupling and directory aggregation; fix the shotgun bullet that cites absent data; verifier | M |
| TD-12 | Test smells | 12 | ABSENT | 1 / 11 | New `test-quality` family with the tsDetect catalogue and a regex lead miner | M |
| TD-15 | Change coupling and hotspots | 15 | PARTIAL | 2 / 3 | Co-change pairs from the git pass; one amplifier, in the ranker only | M |
| TD-18 | Flaky tests | 18 | ABSENT | 0 / 5 | Leading-indicator block in `test-quality`, CI retry config, `flak` commit count, all labelled unconfirmed | S |
| TD-28 | Requirements debt | 28 | PARTIAL | 1 + 1 implicit / 6 | Stub age from blame in the miner; happy-path bullet | S |
| TD-32 | Defect debt | 32 | PARTIAL | 1 partial / 5 | Add `defect` debt type; marker and xfail patterns in the miner | S |

## Cross-cutting observations

**One extended git pass unlocks five types.** Keeping commit boundaries and subjects (`git log --since=<n> months ago --name-only --format=%x1e%H%x09%cI%x09%s`) yields change coupling (TD-10, TD-15, corroboration for TD-07 and TD-06), untested-change share (TD-04), keyword counts for migration, flakiness and bug fixes (TD-06, TD-18, TD-32; bug-fix share recorded, not scored) and last-touched dates (TD-08). One M task that nearly every step above depends on.

**Path classification is the second shared primitive.** Labelling files test, source, doc or config enables test-to-source mapping (TD-04), the test-signals miner (TD-12, TD-18), doc staleness (TD-08) and the reference architecture's path-class suppressions. Today the inventory cannot tell a test from a module.

**An approximate reference graph serves three types.** Stem-reference edges give fan-in and fan-out, SCC cycles and directory-level instability for TD-07 and TD-10, and fan-in zero for dead code in the other slice, all labelled approximate for the verifier.

**The stage-2 miner is where the low-rank types live.** Stub age, defect markers, skip markers and expected-failure markers (TD-28, TD-32, TD-04) are pattern lists on the SATD miner the other slice needs for TD-22; they should not be built separately.

**The eight categories do not map cleanly.** `test-gaps` covers TD-04 only; `half-finished` mixes TD-22 markers, TD-28 stubs, TD-32 defects, TD-06 migrations and TD-30 flags; `architecture` names TD-07, TD-10 and TD-15 signals with no data behind them; `doc-drift` covers drift but not absence. The re-cut needed is two additions (`migration`, `test-quality`) and a data-fed rewrite of `architecture`. `test_eight_categories` and the golden `raw-findings.json` count are the tests that move.

**Three contract-level items touch every family.** The hotspot amplifier is counted twice and belongs in the ranker only. The forbidden-term test blocks "import" in prompts, so the architecture family must say "module references". Self-reported `confidence` drives the ranker weight and the "drop low-confidence unless severity 5" rule; the reference architecture replaces it with earned tiers, and the verifier steps above assume that lands in the ranking redesign.

**Missing `debt_type` values.** `defect` is absent; the taxonomy's knowledge-process family has no value either, though that is the other slice's concern.

## Recommended priority order

Ordered by taxonomy rank against effort, shared work first because every later step depends on it.

1. **Extended git pass plus path classification** in `inventory.py` (change coupling, keyword counts, last-touched date, test mapping, hotspot band). One M task unlocking TD-04, 06, 10, 15 and 18.
2. **TD-04 prompt rewrite and skip-marker leads.** Rank 4, S once step 1 exists.
3. **TD-06 `migration` family.** Rank 6, M; its signals come from step 1.
4. **Architecture rewrite for TD-07 and TD-10.** Tool probe, approximate graph, thresholds, verifier. Two M tasks sharing the graph; the highest false-positive family, so the verifier ships with it.
5. **TD-08 documentation signals and `CORE_CATEGORIES` inclusion.** Rank 8, M; can run in parallel with step 4.
6. **`test-quality` family for TD-12 and TD-18.** One M prompt plus an S miner; the per-scout cap must exist first or the family floods the candidate list.
7. **Miner extensions and the `defect` debt type for TD-28 and TD-32.** S each, riding on the SATD miner the other slice builds for TD-22.
