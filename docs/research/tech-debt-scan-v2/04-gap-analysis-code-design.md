# Gap analysis: code and design families

Research note for tech-debt-scan v2. Written 2026-09-02. Scope: the eleven code- and design-family rows of `02-debt-types-consolidated.md` (TD-01, 05, 09, 11, 13, 17, 20, 21, 22, 24, 29), checked against the current skill under `skills/tech-debt-scan/` and section 3 of `05-architecture-best-practice.md`.

## Method

Each type's "repo-observable symptoms" cell in the consolidated master table was split into single symptoms and matched against the eight scout prompts in `scripts/categories.py`, the signals `scripts/inventory.py` computes, and the ranking and validation layer. A symptom is **searched** when a prompt names it or a script computes it, **implicit** when a prompt names a broader signal that catches it only if the scout happens to look, and **not searched** otherwise. Verdicts: COVERED, PARTIAL, ABSENT.

Facts every subsection relies on:

- The shared output contract (`categories.py:28-62`) asks for `file`, `line` and a free-text `note`, a `suggested_fix` and a self-reported `confidence`. No verbatim quote, line range, metric value or cap.
- Scouts add a severity point for hotspot location (`categories.py:32-37`) and `priority_score` multiplies by 1.5 again (`build_synthesis_prompt.py:63,129-133`).
- The inventory computes per-file LOC, indent units, max indent and commit count (`inventory.py:89-97,104-119,122-160`) and a top-20 hotspot list (`inventory.py:163-186`). No per-function metric, fan-in, change coupling, blame age, marker mining or tool probe. Only `EXT_TO_LANG` extensions are inventoried (`inventory.py:33-54`), so YAML, Makefiles and Dockerfiles are invisible to hotspot ranking.
- `category` must be one of eight names (`build_synthesis_prompt.py:261-266`); `debt_type` is one of eight buckets including `code` and `design` (`validation.py:15-26`), so no type in this slice is blocked at validation. Several are blocked at the category layer because no scout is asked to look.
- Tests pin the category set (`tests/test_categories.py:5-18`), require `suggested_fix` and `confidence` in every prompt (`test_categories.py:48-59`), forbid the token `import ` in prompts (`test_categories.py:39-45`, which rules out wording such as "import cycles"), pin the hotspot key set (`test_inventory.py:72`), pin fixture file counts (`test_inventory.py:10-31`) and pin 30 golden raw findings (`test_e2e.py:47`). Fixtures are nine-line files with no git history, so nothing churn-, blame- or coupling-driven is exercised.

## TD-01 Complex and oversized code units (rank 1)

**Verdict: PARTIAL.** Only the god-modules prompt applies: "Files well over 400 lines" (`categories.py:69`) and "Functions or methods with very high branching depth or many parameters" (`categories.py:72`), plus file-level indentation metrics. Nothing asks for method length; no threshold is named.

| Symptom | Status | Where |
|---|---|---|
| Method over 75 (or 25) lines | not searched | prompt is file-level |
| Cognitive over 15, cyclomatic over 10 | implicit | `categories.py:72`; file-level `complexity` (`inventory.py:104-119`) |
| Nesting over 4, bumpy road | implicit | `max_indent` is per file (`inventory.py:96`) |
| Over 7 (or 4) parameters | implicit | `categories.py:72`, no number |
| File over 250 lines | searched | `categories.py:69` (threshold 400) |
| Multi-operator conditionals | not searched | |
| Indentation-count approximation | searched | `inventory.py:104-119` |
| Weight by churn | searched | `inventory.py:163-186`, `categories.py:74-75` |

**Quality.** LLM reading of Long Method and Large Class reaches F1 0.87 to 0.89 (S4), so vagueness costs precision more than recall: with no threshold and no per-function lead the scout reports whatever looks big. File-level totals cannot tell one 300-line function from thirty 10-line ones. "Severity tracks size x reach" (`categories.py:76`) pushes raw size into severity, which principle 8 forbids. `debt_type: code` fits.

**Gap steps.**

1. Split unit-level symptoms into a `complex-units` family with named leads: function over 75 lines, over 7 parameters, nesting over 4, conditional with 4 or more boolean operators. Traps: flat data tables, generated files, switch-over-enum, test setup. Changes `test_categories.py:5-18`. S.
2. Tool probe: `lizard` (multi-language per-function NLOC, CCN, parameter count) when installed; `ruff` C901/PLR091x and `eslint` `complexity` as fallbacks, normalised to `{file, line_start, line_end, metric, value}` leads. M.
3. Inventory fallback: lines at indent 4 or deeper, and longest run of indented lines, per file. S.
4. Evidence contract: line range, verbatim quote and the observed number ("112 lines, 9 params"). Shared with every family. S.
5. Verifier question: large but cohesive? S once the verifier exists.
6. Fixture: a 120-line function with nesting 6 and 9 parameters; decoy: a 300-line lookup table. Update `test_inventory.py` counts. S.

**Risk.** Lowest false-positive prior in the slice. Do not rank on LOC; remove the scout-side severity bump so the hotspot amplifier counts once.

## TD-05 Duplicated code (rank 5)

**Verdict: PARTIAL.** The prompt asks for "Identical or near-identical blocks repeated across files" (`categories.py:82`) and "Parallel functions that differ only in a constant or a type name" (`categories.py:83`), with no size threshold, tool or corroboration rule.

| Symptom | Status | Where |
|---|---|---|
| 100 duplicated tokens, 10 to 30 lines | implicit | `categories.py:82`, no threshold |
| Type-1 clone over 20 lines | implicit | `categories.py:82` |
| Near-identical helpers under different names | searched | `categories.py:83` |
| Copy-paste class hierarchies | not searched | |
| Duplicated test setup and assertions | not searched | no path class; golden raw finding 9 reports one at severity 1 anyway |
| Duplicated CI or build YAML | not searched | YAML not inventoried |
| Add-only commits, two-week rewrites, AI trailers | not searched | commit counts only (`inventory.py:122-160`) |

**Quality.** The reference architecture says token clones need jscpd or CPD, the LLM's value is semantic near-duplicates, and duplication is reported only when the copies are change-coupled or a tool corroborates (71 percent of clones beneficial, S38). None of these gates exist. "Severity tracks how many copies exist" (`categories.py:87`) scores on count. The magic-literal bullet (`categories.py:84-85`) is TD-21, the noisiest symptom in the taxonomy.

**Gap steps.**

1. Change coupling in `inventory.py` from the same `git log` pass: pairs co-committing at least three times at 30 percent, plus coupling degree, to `coupling.json`. Corroborator for TD-05, TD-20 and TD-11. M.
2. Tool probe: `jscpd` or PMD CPD, normalised to clone pairs with line ranges and token counts. M.
3. Prompt rewrite: questions ("are the copies a coupling pair?", "which path class?"), traps (test fixtures, language boilerplate, generated and vendored code); drop the literal bullet and the copy-count sentence. S.
4. Tier rule: without a tool hit or coupling pair, cap at tier B and exclude from `quick-wins`. S once tiers exist.
5. Fixture: two near-identical helpers co-committed in synthetic history; decoy: duplicated setup under `tests/`. M.

**Risk.** High false-positive prior without coupling. Do not score on copy count; AI-era git signals are recorded, not weighted (principle 8 forbids scoring on code age).

## TD-09 Dead, unused and speculative code (rank 9)

**Verdict: PARTIAL.** The prompt covers unreferenced definitions (`categories.py:94`), unreachable branches (`:95-96`), commented-out blocks (`:97`) and zero-churn files with no inbound references (`:99-100`), with a sound conservatism clause (`:101-103`).

| Symptom | Status | Where |
|---|---|---|
| Unused imports (S1128) | not searched | `import ` token forbidden (`test_categories.py:41`) |
| Commented-out code (S125) | searched | `categories.py:97` |
| Types with fan-in 0 | implicit | `categories.py:94`; no fan-in signal |
| Files with no inbound imports | searched | `categories.py:99-100`; scout computes references itself |
| Unreachable branches | searched | `categories.py:95-96` |
| Unused parameters and hooks | not searched | |
| One-implementation or empty abstractions | not searched | |
| Orphan config keys | not searched | |
| Unused dependencies | not searched | absent from dependency prompt too |
| Names containing old, bak, v1 | not searched | |
| TODO "remove after" | implicit | `categories.py:132-133` |
| Untouched for years while neighbours churn | searched | 12-month churn window only; no last-touched date |

**Quality.** The reference architecture: tools win; reading cannot see dynamic dispatch, reflection, route conventions or external callers; without a tool a finding is tier C unless churn and approximate fan-in are both zero. The skill has neither the tool nor fan-in, and its only precision control is self-reported confidence, which synthesis uses as a gate ("Drop low-confidence findings unless severity is 5", `build_synthesis_prompt.py:200`) despite kappa 0.10 to 0.21 against ground truth (S15). The golden top-5 promotes a medium-confidence dead-code finding with the fix "delete legacy_export and its tests".

**Gap steps.**

1. Tool probe: `knip` (JS/TS), `vulture` with per-kind confidence (Python), `deadcode -whylive` (Go); C# needs a build, so "not assessed". M.
2. Inventory: approximate fan-in (files whose text references this file's stem, flagged `approximate`) and last-touched date. M.
3. Tier rule: without a tool hit, tier C unless churn and fan-in are zero; the verifier lists the dynamic-reference patterns it checked (reflection, string dispatch, route decorators, DI registration, manifest entry points, serialisation). S.
4. Prompt: add legacy names, commented-out code density, unused module references (phrased to pass the test), "remove after" leads, and the protected-class list. S.
5. Pattern leads: commented-out code (comment lines ending in `;`, `{`, `)` or containing `=`) and legacy-name matches, recorded not scored. S.
6. Fixture: an unreferenced helper in a zero-churn file; decoys: a manifest-declared entry point with no in-repo caller, a function reached via `getattr` on a string. M.

**Risk.** Highest false-positive prior in the slice. Never let a tier C dead-code finding reach the top N; never ask the scout for the deletion as a fix.

## TD-11 God class, brain class, low cohesion (rank 11)

**Verdict: PARTIAL.** This is what god-modules mostly is: "mixing unrelated concerns (I/O, business rules, presentation, persistence all in one place)" (`categories.py:70-71`) and "A file referenced by almost everything" (`:73`). It is cut at file level, so in C#, Java and TypeScript a god class inside a moderate file is missed.

| Symptom | Status | Where |
|---|---|---|
| Over 20 public methods, over 30 methods, WMC over 100 | implicit | `categories.py:69` file size only |
| LCOM over 0.8 with 7 or more members | implicit | `categories.py:70-71` is the readable proxy |
| Brain class (size, complexity, centrality) | implicit | `categories.py:69,73-75`; no fan-in figure |
| Procedural class (long parameterless methods, no fields) | not searched | |
| "Should be a separate class" comments | not searched | needs SATD leads |
| Misplaced responsibilities | searched | `categories.py:70-71` |

**Quality.** S4's F1 on Large Class means a well-shaped prompt suffices and the verifier's job is the "large but cohesive" trap. Missing: Designite thresholds as leads, a cohesion question ("do methods cluster over disjoint field sets?"), class-level language. `debt_type: design` fits and is what the golden uses.

**Gap steps.**

1. Re-scope god-modules to `god-classes`: leads are file over 250 to 400 lines, public methods over 20, methods over 30 (from the lizard probe), top approximate fan-in; questions on responsibility clusters, field-access disjointness, procedural shape; traps: facades, DTOs, generated code, cohesive parsers. S.
2. Reuse TD-09's fan-in for centrality instead of asking the scout to guess. Shared.
3. Route SATD leads containing "separate class", "split", "too big" here. S once `satd.py` exists.
4. Verifier question: single reason to change; cohesive table or state machine? S.
5. Fixture: a class with 25 public methods over three concerns; decoy: a 300-line cohesive tokenizer. S.

**Risk.** Moderate; the false positive is cohesive size. Drop "severity tracks size x reach".

## TD-13 Poor exception handling and error masking (rank 13)

**Verdict: ABSENT.** No prompt mentions catch blocks, swallowed errors or generic exceptions. The nearest wording, test-gaps' "Error-handling and edge-case branches that no test exercises" (`categories.py:110`), is about coverage. A scout that found an empty catch would have to mislabel it to pass `build_synthesis_prompt.py:261-266`. Section 3 of the reference architecture also omits this family, which should be fed back: it is O = 5, pattern-level readable, and the most common Bandit class across 197K PyPI packages.

| Symptom | Status |
|---|---|
| Bare except, empty catch, catch-all with pass | not searched |
| Generic Exception thrown or caught (S00112) | not searched |
| Rethrow without cause (S1166) | not searched |
| Superfluous throws (S1130) | not searched |
| Disabled assertions | not searched |
| Catch blocks that log nothing | not searched |
| try/except pass in generated code | not searched |

**Quality.** Nothing to assess. `debt_type: code` fits.

**Gap steps.**

1. New `error-masking` family: definition; leads from a pattern pass; questions ("what failure is hidden and who learns of it?", "is this a process boundary where a catch-all is legitimate?", "is the cause preserved on rethrow?"); traps: top-level handlers, retry loops that re-raise after N attempts, cleanup blocks, tests asserting an exception. Add to `CORE_CATEGORIES`. Changes `test_categories.py:5-18`. S.
2. Pattern leads: `except:`, `except Exception`, `catch (Exception`, `catch {}`, `catch (e) {}`, `rescue => e` followed by an empty body, `pass`, `return null` or a bare log. Rank by hotspot band and cap per scout; Apache averages 1,180 S00112 items per commit. S.
3. Tool probe: `ruff` E722/BLE001/S110/S112, `eslint` `no-empty`, Bandit B110/B112. Tool hit plus hotspot band earns tier A. S.
4. Verifier required: the boundary case is the dominant legitimate use; severity 5 only when the masked failure sits on a money, data or security path. S.
5. Fixture: `except Exception: pass` around a write in a hotspot file; decoy: a `main()` that catches, logs and exits non-zero. S.

**Risk.** Detection is cheap; precision rests on the boundary trap and on not counting instances. The +47 percent growth figure is vendor data and must not raise severity.

## TD-17 Deprecated API usage and idiom drift (rank 17)

**Verdict: PARTIAL.** Split across two scouts: "Usage of APIs the dependency itself marks deprecated" in dependency-debt (`categories.py:153`) and "Partially migrated patterns (old and new approach coexisting, count how many call sites still sit on the old side)" in half-finished (`:137-138`).

| Symptom | Status | Where |
|---|---|---|
| Calls to deprecated third-party targets | searched | `categories.py:153`; unverifiable, `node_modules` and `.venv` are ignored (`inventory.py:56-73`) |
| In-repo deprecation annotations without removal (S1123, S1133) | not searched | |
| Compiler or runtime deprecation warnings | not searched | needs a build; out of scope |
| Mixed idioms (callbacks beside async) | implicit | `categories.py:137-138` |
| Superseded config formats side by side | not searched | |
| Absent linter config, many inline disables | not searched | |

**Quality.** The third-party claim is the kind the reference architecture forbids without a source: its dependency paragraph says staleness and EOL "need a tool or registry lookup; without one the scout must not assert them", and S15's finding that a third of false rejections cite absent statements applies to library deprecations recalled from memory. The in-repo symptom is a cheap pattern nobody mines. `debt_type` is ambiguous between `code` and `dependency`; the taxonomy says code.

**Gap steps.**

1. Pattern leads for in-repo markers (`@deprecated`, `[Obsolete]`, `@Deprecated`, `DeprecationWarning`, "deprecated" in doc comments) with blame age and approximate caller count; route to dead-code when callers are zero, to half-finished when they remain. S.
2. Third-party deprecated calls become tool-gated (`eslint-plugin-deprecation`, TypeScript `@deprecated` surfacing, `ruff` UP rules); without a tool the scout may nominate to `open_questions` only. S rule, M probe.
3. Superseded config formats as a deterministic manifest check (setup.py with pyproject, tslint with eslint, two lockfile kinds), as migration leads. S.
4. Linter config presence and inline-disable density per file (`noqa`, `eslint-disable`, `pragma warning disable`, `SuppressWarnings`) as inventory fields, recorded not scored. Shared with TD-29. S.
5. Fixture: an in-repo deprecated function still called from two files; decoy: a deprecated wrapper with a documented removal date. S.

**Risk.** Library-knowledge hallucination. Never assert third-party deprecation without a tool or the installed package's source; treat idiom drift as migration debt with call-site counts as evidence.

## TD-20 Coupling smells (rank 20)

**Verdict: ABSENT.** Feature Envy, Inappropriate Intimacy, Message Chains and Middle Man are not named anywhere. The architecture prompt's "Unstable hubs" (`categories.py:169-170`) and "Circular dependencies between modules" (`:163`) are module-level TD-07 and TD-10 signals.

| Symptom | Status |
|---|---|
| Method using more members of another class than its own | not searched |
| Two classes accessing each other's internals | not searched |
| Long call chains | not searched |
| Classes that only delegate | not searched |
| Large parameter bundles between collaborators | not searched (`categories.py:72` is a different symptom) |

**Quality.** Marked needs-tool in the taxonomy; Feature Envy has the lowest yield (at most 2.3 percent of methods). The structure family reads at 100 percent recall and 64 to 82 percent precision (S5); 63 percent of a static detector's findings were intentional (S6). `debt_type: design` fits.

**Gap steps.**

1. No standalone scout. Add two questions to `god-classes`: Inappropriate Intimacy (two files each referencing the other's private-looking members, with coupling pairs as leads) and Message Chains (accessor depth 4 or more outside builders and fluent APIs). S.
2. Middle Man folds into dead-code's speculative-generality question ("a class that only forwards calls"). S.
3. Feature Envy is tool-only (Designite, JDeodorant when present); otherwise "not assessed". S.
4. Verifier mandatory; tier B at best without a tool hit or coupling pair. S.
5. Fixture: a mutually intimate file pair and a 5-deep chain; decoy: a fluent builder. S.

**Risk.** High intentional-design rate; fluent APIs and DTO access mimic the smells. Use the coupling pair as corroboration, never as the finding; do not rank on global coupling metrics.

## TD-21 Magic numbers and hard-coded literals (rank 21)

**Verdict: PARTIAL, and should stay deliberately limited.** The duplication prompt asks for "Repeated literal values (paths, magic numbers, format strings) that should be a single shared constant" (`categories.py:84-85`).

| Symptom | Status | Where |
|---|---|---|
| Numeric literal other than 0 or 1 | not searched | repeated values only |
| Duplicated string literals (S1192) | searched | `categories.py:84-85` |
| Numeric literals as assertion arguments | not searched | |
| Hard-coded thresholds, paths, URLs | implicit | `categories.py:84` names paths |

**Quality.** Importance 1.5 with no cost evidence; one instance per 16 LOC; no fault link (T:S8, S9). The anti-pattern list says lint violations are evidence, never a score input. Coverage is right in spirit and wrong in placement: literals belong in the trap list, not in a "signals to look for" bullet.

**Gap steps.**

1. Move the literal bullet from signals to traps: report a literal only when the same value appears in three or more files that would change together, as a duplication finding with the literal as evidence. S.
2. When the repo's linter config enables a magic-number rule (`ruff` PLR2004, `eslint` `no-magic-numbers`), tool hits are evidence for a duplication or configuration finding, never findings. S.
3. Report "not assessed: magic literals, excluded by design". S.
4. Fixture decoy: HTTP status codes and array indices that must yield nothing. S.

**Risk.** Noise. No scout, no counts.

## TD-22 Self-admitted debt markers (rank 22)

**Verdict: PARTIAL.** The half-finished prompt asks for "TODO / FIXME / HACK / XXX / WORKAROUND markers describing unfinished work, weigh ones that name a concrete risk or a date over vague notes" (`categories.py:132-133`). Five of roughly 62 known patterns; the LLM does the grep.

| Symptom | Status | Where |
|---|---|---|
| Marker keywords (about 62 patterns) | searched | `categories.py:132-133`, 5 patterns |
| Sonar S1135 | searched | same |
| Markers without a ticket reference | not searched | |
| Marker age from git blame | not searched | no blame signal |
| Markers in build files and tests | not searched | not directed there; build files not inventoried |

**Quality.** The reference architecture inverts the division of labour: a keyword matcher reaches F1 0.58 untrained, zero-shot LLM search trails fine-tuned models by 6 to 9 points (S1, S3), and blame age is unavailable to a scout. Stage 2 is a `satd.py` whose output the scout classifies. SATD is also cross-cutting: a marker within ten lines of another family's finding is one of the corroborations that earns tier A (stage 7), which is impossible while markers live in a scout's free text. The category mixes TD-22, TD-28, TD-30 and TD-06.

**Gap steps.**

1. `satd.py`: deterministic miner over every text file including build, CI and test paths, curated pattern list (start from T:S48's 62), emitting marker, file, line, quoted comment, ticket-reference flag (`#123`, `ABC-123`, URLs) and blame age. Output `.tech-debt/satd.json`. M.
2. Feed `satd.json` to the half-finished scout as leads (classify type and severity by reading around each; do not search) and to merge as corroboration at the same location. S once merge exists.
3. Prompt: remove the grep instruction; traps: vendored code, docs describing the TODO convention, string literals, changelogs, markers with an open ticket. S.
4. Report: marker counts by age band in statistics, never as findings; a marker is a finding only when it names a concrete risk meeting the rubric. S.
5. Fixture: a two-year-old FIXME naming data loss in a hotspot file and a ticketed TODO; decoy: a TODO inside a string. Needs synthetic blame history. M.

**Risk.** Low verifier need for markers; moderate for the migration claims sharing the scout. Do not score marker counts; do not re-raise ticketed markers.

## TD-24 Hierarchy and encapsulation smells (rank 24)

**Verdict: ABSENT.** No prompt names inheritance, overrides or field visibility.

| Symptom | Status |
|---|---|
| Refused Bequest (subclass ignores or throws on inherited members) | not searched |
| Inheritance depth over 6 or over 10 children | not searched |
| Public or public static fields (S1104) | not searched |
| Class Data Should Be Private | not searched |

**Quality.** Importance 2, no direct cost evidence. Public fields are idiomatic in Python dataclasses, Go structs and TypeScript, a smell in Java and C#; a cross-language LLM read would flag idiomatic code at scale (S1104 sits in 80 percent of Apache commits). Hierarchy depth needs a parser. `debt_type: design` fits.

**Gap steps.**

1. One Refused Bequest question in `god-classes`, fed by pattern leads for `NotImplementedError`, `NotSupportedException` or empty bodies inside overriding methods; trap: an abstract base whose stubs are the contract. S.
2. Deep or wide hierarchies: tool-only; otherwise "not assessed". S.
3. Public fields: only when the repo's linter config enables the rule or a tool hit exists, Java and C# only. S.
4. Fixture: a subclass throwing on three inherited methods; decoy: an abstract base with stubs. S.

**Risk.** Cross-language false positives on visibility; low payoff. No scout.

## TD-29 Convention and formatting violations (rank 29)

**Verdict: ABSENT, and mostly rightly so.** Nothing asks for naming, ordering or layout; no prompt mentions lint configuration.

| Symptom | Status |
|---|---|
| Member order, naming, statements per line, modifier order | not searched |
| Inconsistent naming and layout across directories | not searched |
| Many inline lint disables | not searched |

**Quality.** Importance 1; clean and dirty classes do not differ in faults (T:S8, S9). Stage 0 records "families CI already enforces" and the tooling note says the repo's linter config is the source of truth. The symptoms with scanner value are indirect: absent linter config, inline-disable density (a hotspot with thirty suppressions is a lead for TD-13, TD-17 and TD-03), and two conventions coexisting across directories, which is migration debt.

**Gap steps.**

1. Inventory: linter and formatter config presence and inline-disable count per file, recorded not scored. Shared with TD-17 step 4. S.
2. Migration scout question: two conventions coexisting with directory counts, only when an in-repo lint config exists that one side violates. S.
3. Report "not assessed: convention violations, run the repo's own linter". S.
4. Optional probe: when `ruff` or `eslint` and a repo config both exist, run in check mode with JSON output and record per-file counts as evidence, flagged "CI already enforces" when a workflow runs the same linter. M.
5. Fixture decoy: a camelCase file in a snake_case repo yielding nothing. S.

**Risk.** Overwhelming noise for no measured cost. Never count violations.

## Summary table

| ID | Name | Rank | Verdict | Searched / total (implicit) | Headline gap step | Effort |
|---|---|---|---|---|---|---|
| TD-01 | Complex and oversized units | 1 | PARTIAL | 3 / 8 (+3) | Per-function metrics via lizard probe with inventory fallback; split unit-level scout from god-modules | M |
| TD-05 | Duplicated code | 5 | PARTIAL | 1 / 7 (+2) | Change coupling in inventory plus jscpd probe; tier B cap without corroboration | M |
| TD-09 | Dead and speculative code | 9 | PARTIAL | 4 / 12 (+2) | knip/vulture/deadcode probe plus approximate fan-in; tier C rule without them | M |
| TD-11 | God class, low cohesion | 11 | PARTIAL | 1 / 6 (+3) | Re-scope god-modules to class level with thresholds and a cohesion question | S |
| TD-13 | Error masking | 13 | ABSENT | 0 / 7 | New error-masking family plus regex leads and ruff/eslint/bandit probe | M |
| TD-17 | Deprecated API usage | 17 | PARTIAL | 1 / 6 (+1) | In-repo deprecation leads with caller counts; third-party claims tool-gated | S |
| TD-20 | Coupling smells | 20 | ABSENT | 0 / 5 | Intimacy and chain questions in the design scout with coupling pairs as leads; Feature Envy tool-only | S |
| TD-21 | Magic literals | 21 | PARTIAL | 1 / 4 (+1) | Move literals to the trap list; evidence-only under duplication | S |
| TD-22 | SATD markers | 22 | PARTIAL | 2 / 5 | Deterministic satd.py with blame age feeding leads and tier corroboration | M |
| TD-24 | Hierarchy and encapsulation | 24 | ABSENT | 0 / 4 | Refused Bequest question in the design scout; public fields tool-only, language-gated | S |
| TD-29 | Convention violations | 29 | ABSENT | 0 / 3 | No scout; record lint-config presence and disable density; report not assessed | S |

## Cross-cutting observations

**The eight categories do not map onto the taxonomy.** They are search assignments, each straddling several types: god-modules holds TD-01, TD-10 and TD-11; duplication holds TD-05 and TD-21; dead-code holds TD-09 and TD-30; half-finished holds TD-22, TD-28, TD-30, TD-06 and part of TD-17; dependency-debt holds TD-02 and TD-17; architecture holds TD-07, TD-10, TD-15 and TD-33. `debt_type` is too coarse to recover the type (TD-01 and TD-13 are both `code`) and has no mapping rule. So the evaluation harness cannot report per-type precision, and the one rank-13-or-better type with no home (TD-13) is invisible rather than weak. Recommendation: keep `category` as the family axis and `debt_type` for reporting, and add an optional `type_id` (TD-xx) that each prompt lists as its allowed values and `validation.py` checks when present, the backwards-compatible pattern used for `debt_type`; carry it through `design_parser.OPTIONAL_KEYS` (`design_parser.py:40`) and the bundle frontmatter (`bundle_writer.py:84-87`).

**Re-cut for this slice.** Six families cover the eleven types with the right verifier posture: `complex-units` (TD-01), `god-classes` (TD-11, plus the TD-20 intimacy and chain questions and the TD-24 Refused Bequest question), `duplication` (TD-05, literals as traps), `dead-code` (TD-09, Middle Man folded in), `error-masking` (TD-13, new) and `half-finished` (TD-22 leads, TD-28, TD-06, TD-17 idiom drift). TD-21, TD-29, Feature Envy and public fields are excluded or tool-only and named in "not assessed" so the exclusion is visible.

**Three deterministic signals close gaps across six types.** Change coupling serves TD-05, TD-20 and TD-11; approximate fan-in with last-touched date serves TD-09, TD-11 and TD-17; one `patterns.py` lead table serves TD-22 (markers), TD-13 (catch-alls), TD-17 (deprecation annotations), TD-24 (throw-in-override), TD-09 (commented-out code, legacy names) and TD-29 (inline disables). One pattern table keyed by family is cheaper than five scripts and gives every family the leads block stage 4 expects. The tool probe covers TD-01, 05, 09, 13 and 17 and is where most tier A corroboration for this slice will come from.

**Shared-prefix changes that fix several types at once.** Line range, verbatim quote and observed metric in the evidence contract; drop `suggested_fix` and `confidence` (S16, S15); a per-scout cap instead of "exactly N"; a definition, four to six questions, a traps list and a leads block per family; remove the scout-side hotspot bump. "Severity tracks size x reach" (`categories.py:76`) and "severity tracks how many copies" (`:87`) are the two places raw counts leak into ranking and must be reworded to the rubric.

**Tests that change.** `test_categories.py:5-18` (category set), `:48-59` (drop `suggested_fix` and `confidence`, add `quote` and `line_start`), `:39-45` (replace the `import ` ban with a check that permits "unused imports" and "import cycles"), `test_inventory.py:72` (hotspot key equality) and fixture counts, `test_e2e.py:47` (30 golden findings) and `golden/top5.json` (carries `confidence`). Fixtures need a synthetic git history built in `conftest.py`, or TD-05 coupling, TD-09 churn and TD-22 blame age stay untested.

## Recommended priority order

1. **TD-13 error-masking family with pattern leads** (rank 13, ABSENT, M). Largest hole per unit effort: O = 5, cheap to detect, no home today.
2. **Shared prefix rewrite and `patterns.py`** (cross-cutting, M). Unlocks the leads model for TD-22, TD-13, TD-17, TD-24 and TD-09 in one pass and removes the two count-to-severity sentences.
3. **`satd.py` with blame age** (TD-22, M). Low rank alone, but it is the corroboration that lets every other family earn tier A and it removes the LLM-grep anti-pattern.
4. **Re-cut god-modules into `complex-units` and `god-classes`** (TD-01 rank 1, TD-11 rank 11; S for prompts, M with lizard). Highest-ranked type in the slice with the best LLM reliability, so a good prompt pays immediately.
5. **Change coupling, jscpd probe, tier cap** (TD-05 rank 5, M). Coupling also serves TD-20 and TD-11.
6. **Dead-code probe, approximate fan-in, tier C rule** (TD-09 rank 9, M). After the verifier exists; without it more recall on this type is a net loss.
7. **In-repo deprecation leads and tool gating** (TD-17, S).
8. **TD-20 and TD-24 questions in the design scout** (S each), once the verifier is in place.
9. **TD-21 and TD-29 exclusion steps** (S), folded into the prompt rewrite so the exclusions appear in the report.
