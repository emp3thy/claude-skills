# tech-debt-scan: performance family, graph-history join, concern scout

Amendment to `2026-09-04-tech-debt-scan-v2-design.md`. Provenance: a three-strand research survey on 2026-09-12 (performance-detection techniques, architecture-detection techniques, and the existing landscape of agent skills, MCP servers, products and papers; 30, 33 and 69 items respectively, synthesis at the session's research artefact). Its conclusions that this design acts on:

- No existing skill, plugin or product combines deterministic leads, a per-family LLM reader, a verifier pass and a fixed ranking at repository scope. Every whole-repo audit skill is a single cold read, the mode the literature measures worst (unconstrained LLM review F1 below 20 percent; sycophancy flipping verdicts in up to 72 percent of cases unless evidence is demanded first). The pipeline this skill already has is the shape the evidence supports; the gaps are in coverage, not method.
- The single strongest-evidence architecture signal in the literature is co-change between files with no structural path between them (Wong et al., ICSE 2011; Xiao et al., ICSE 2016 -- such debts absorb 51 to 85 percent of maintenance effort). The scanner computes both halves and never joins them.
- Local performance smells are reliably detectable from source and are already encoded rule-for-rule in mainstream linters; N+1 and algorithmic-complexity claims depend on runtime cardinality and are the field's weakest static technique. An LLM cannot find performance hotspots unaided; paired with a located rule hit it can judge one.
- The reader-judgment column of architecture (scattered functionality, semantic duplication, drift) has no metric signature, and the strongest LLM evidence is for a reader confirming a deterministic candidate rather than finding one cold.

Fixed constraints, unchanged from the v2 design: Claude Code skill; SKILL.md orchestration with pinned commands, pinned output files and the exit-5 no-improvisation rule; pure Python 3.11+ with pyyaml as the only dependency, every script direct-path invocable; read-only Agent subagents for all LLM work; language-agnostic by default, external tools only when already installed; human review of `design.md`; no live LLM in tests; Windows-safe argv; LF-only rendered output; ruff, mypy strict, pytest and `skill_check.py` in CI.

## 0. Guardrails for planning and implementation

- **(a) Handoffs are rendered and assumptions bucketed.** This spec and the implementation plan are rendered visually for review, with assumptions in three buckets (section 9).
- **(b) Confidence per task.** Every plan task carries a confidence percentage; a task under 90 percent embeds its mitigation in the task text.
- **(c) Documentation ships with code.** `SKILL.md`, `docs/architecture.md`, `README.md` and `docs/evaluation-log.md` change in the same PR as the code they describe.
- **(d) Verify before commit.** Where a task says "follows existing pattern X", the implementer reads X's source before writing.
- **(e) No live LLM in tests.** Scout and verifier behaviour is exercised through canned JSON and the fixture corpus; the `live` marker stays off in CI.
- **(f) Full suite before every commit.** Every task's verification step runs `python -m pytest` from the repository root with no path arguments, whatever the brief's blast-radius analysis names. A brief's file list is a hypothesis about coupling, not a proof of it.
- **(g) Agents write their own artifacts.** Every dispatched agent writes its output file itself and returns a receipt; a reply transcribed by the caller loses data past a few kilobytes (issue #19).
- **(h) One branch, one PR:** `feat/tech-debt-scan-perf-arch`, already created.

## 1. Goal, non-goals, success criteria

**Goal.** Close the three coverage gaps the research identified, inside the existing detect-verify-rank pipeline: a deterministic graph-history join feeding the architecture family, a lead-driven `performance` family with tiering honest about what source can prove, and one index-led `concerns` scout for the reader-judgment column. The v2 pipeline's invariants -- deterministic ordering, evidence-cited findings, per-family caps, the baseline -- hold for every new finding.

**Success criteria.**

1. Every coupled pair in `coupling.json` carries `has_edge`, `edge_direction` and `lead_kind`; the architecture scout prompt renders modularity-violation and unstable-interface leads as their own labelled sections.
2. `performance` is a family in the `default` and `deep` sets, absent from `quick`; `performance` is a valid `debt_type`; TD-36 and TD-37 are valid type ids; `validation.py`'s type-id ceiling is 37.
3. A `performance` finding carrying TD-37 never exceeds tier C, whatever the verifier says, and `design.md`'s cap sentence for it names the reason.
4. A `performance` finding carrying TD-36 reaches tier A on a `tool:` corroboration plus a verifier confirm, tier B on confirm without a tool hit, exactly as the table in section 3.
5. `concern_index.py` writes `concern-index.json` with at most 40 candidates, each naming its files, directories, hotspot touch and coupling, from `inventory.json` and `coupling.json` alone; two runs over the same workdir produce byte-identical output.
6. The `concerns` scout is dispatched at most once per scan, chunked or not, and its findings follow the C / B / A ladder in section 4.
7. The fixture corpus carries at least one planted item and one decoy per new family, and the live evaluation reports tier-A precision for them under the existing bar.
8. `/tech-debt-scan` over a repository with no coupled pairs, no PERF hits and no recurring names produces a `design.md` identical to today's apart from the two families listed under `families_skipped` with reason `no leads`.

**Non-goals.** Runtime inputs of any kind (profiles, benchmarks, traces) -- recorded as a follow-on lead source. Per-language performance normalisers beyond ruff (Clippy, Roslyn, PMD) -- same mechanism, later. Per-repository threshold calibration for hub-like and god-component signatures. Reporting the baseline's `RESOLVED` count as a resolution rate. Consuming Enola or CodeScene as lead producers. Semantic (embedding) similarity for duplicate detection. Per-module concern scouts. Any change to `rank.py`'s formula or presets, to the baseline, to `design_writer`'s rendering, or to promote.

## 2. Graph-history join

**Where.** `inventory.py`, at the point it already holds the `GraphResult` from `reference_graph.build_reference_graph` and writes `coupling.json` from the git pass. No new script.

**Persistence.** `coupling.json` gains `edges`: the reference graph's `(referrer, target)` list as root-relative path pairs. It sits beside its siblings -- `cycles`, `directories` and `unstable_edges` are already written into `coupling.json`, not `inventory.json` (`inventory.py:888-895`), so the graph's outputs stay in one document. On a 5,000-file repository this is a few thousand short pairs; it is what makes the join and the concern index reproducible from the workdir without re-walking the tree.

**Per pair**, for every entry in `coupling.json`'s `pairs` (already filtered by `min_shared: 3`, `min_ratio: 0.3`):

- `has_edge`: true when the reference graph carries a direct edge `a -> b` or `b -> a`. Direct only. Transitive reachability is not computed; the literature's signal is the absence of any declared relation, and a two-hop path is a relation.
- `edge_direction`: `"a->b"`, `"b->a"`, `"both"` or `null`.
- `lead_kind`:
  - `modularity-violation` when `has_edge` is false. Files that change together with no structural reason. `cross_directory: true` is the strong form the studies measured; same-directory pairs keep the kind but the prompt marks them weaker, since sibling data or fixture files co-change innocently.
  - `unstable-interface` when `has_edge` is true and either side's `fan_in_approx` lies in the repository's top decile of non-null fan-in. Dependents keep changing with the thing they depend on. A decile, not a fixed number: the surveyed tools' hub thresholds disagree by an order of magnitude.
  - `null` otherwise.

**Consumption.** `plan_scan.py` already feeds coupled pairs into the architecture family's lead block. The two kinds render as their own labelled sections, each pair with its `shared_commits`, `ratio`, direction and, for unstable interfaces, the fan-in decile. `categories.py`'s architecture questions gain two: "Is the co-change explained by a dependency the graph cannot see -- a config file, a schema, a generated pair, a test and its subject?" and "Is the high-fan-in side an intentional facade whose dependents are meant to change with it?" The traps gain one: a `.proto`/schema and its generated code.

**Tiering.** Unchanged. `_family_cap_and_lift` already lifts the architecture cap on a `coupling` token; a join lead carries that token by construction, so verifier confirm plus the pair's own signal is tier A. Nothing in `rank.py` changes.

## 3. Performance family

**Taxonomy.** `validation.py`: `performance` added to `VALID_DEBT_TYPES`; `_TYPE_ID_MAX` becomes 37. `categories.py`'s taxonomy table gains:

| ID | Name | Disposition |
|---|---|---|
| TD-36 | Local performance smell | IN -- `performance` family; provable from source |
| TD-37 | Cardinality claim | IN -- `performance` family; capped at tier C |

TD-36 covers allocation or I/O inside a loop, string concatenation in a loop, a regex compiled per call, redundant traversal, an inefficient collection call. TD-37 covers N+1, algorithmic complexity, and any "will not scale" claim. The scout assigns exactly one per finding, with the rule that a TD-37 finding must state *why* N could be large -- a user-data collection, a per-request path, a paginated source -- not just the loop's shape.

**Lead sources**, most precise first:

1. `ruff PERF*`. `RUFF_SELECT` (`tools_probe.py:326`) gains `PERF101,PERF102,PERF203,PERF401,PERF402,PERF403`; `RUFF_KINDS` (`tool_normalisers.py:138`) maps each to `("performance", "perf-smell")`. All six exist on the installed ruff 0.15.4 (`unnecessary-list-cast`, `incorrect-dict-iterator`, `try-except-in-loop`, `manual-list-comprehension`, `manual-list-copy`, `manual-dict-comprehension`). `tests/test_tools_probe.py:1332` asserts `set(RUFF_SELECT) == set(RUFF_KINDS)`, so both must change together. These are micro-smells: the normaliser assigns severity 2 and the verifier raises it only with a hot-path reason. The `tool:ruff` token these signals carry is what lifts the cap to A.
2. `patterns.py`: a new `_scan_loops` scanner modelled on `_scan_catches` (`patterns.py:436`): a loop-header regex (`for`, `while`, `foreach`, `.forEach(`, `.map(`) finds the header line, then the body is delimited by the existing `_indented_body` for indentation languages or `_brace_body` for brace languages, and four body regexes run over it: (i) an I/O or process call (`open(`, `subprocess.run(`, `requests.`, `fetch(`, `.query(`, `.execute(`); (ii) a regex compile (`re.compile(`, `new RegExp(`, `Pattern.compile(`); (iii) a sort call (`sorted(`, `.sort(`); (iv) a membership test against a list literal (`in [`). These are leads, not findings; each is verified.
3. A hotspot-band file whose `max_indent` (already in `inventory.json` per file) is 4 or more -- deep nesting where churn is. lizard is not a source here: its CSV carries NLOC, CCN and token counts but no nesting depth (`tool_normalisers.py:258-261`).
4. The hotspot band itself. Interest is proportional to churn.

**Scout block.** `FAMILY_BLOCKS["performance"]`: definition; the TD-36 / TD-37 rule; what to report and what not to -- no startup-only initialisation, no loop over an enum or a config list, no test or benchmark code, no generated or vendored code.

**Verifier questions.** Does this run per request, per item or per file, or once? What bounds N -- user data, a config list, a fixed enum? Is there already a cache, a batch, an index or a memo on this path? Is the expensive call actually inside the loop, or hoisted above it? For TD-37: what evidence of scale exists -- a comment, a test with a large N, an issue reference?

**Traps.** Startup initialisation; bounded enum or config loops; deliberate simplicity on a cold path; generated or vendored code; benchmark and test files.

**Tiering**, implemented as a new branch in `apply_verdicts._family_cap_and_lift`:

| Finding | Tier | Lift |
|---|---|---|
| TD-36, `tool:` token, verifier confirms | A | -- |
| TD-36, any family: verifier downgrades, refers, or a quote fails | C | the pipeline's existing rule for every family (`_tier_and_reason`) |
| TD-36, no `tool:` token, verifier confirms | B max | tool corroboration |
| TD-37, any verdict | C | the lift names "runtime evidence, which this scan never reads" |

**Sets.** `config.py`'s `default` and `deep` gain `performance`; `quick` stays at six. The adaptive rule applies unchanged.

**Evaluation.** Each fixture in the corpus gains one planted TD-36 item and one decoy (a loop over a five-element enum that allocates; a regex compiled once at import time). `docs/evaluation-log.md` records the family's precision from its first run under the existing provisional 0.80 bar.

## 4. Concern index and concern scout

**`concern_index.py` -> `concern-index.json`.** A new deterministic step between `inventory.py` and `patterns.py`. Inputs: `inventory.json` (files with `path_class` and `hotspot_score`, the hotspot band) and `coupling.json` (the `directories` aggregates -- `path`, `files`, `loc`, `churn`, `fan_in`, `fan_out`, `instability` -- plus `pairs` and, after section 2, `edges`). Reads each `path_class: source` file once and extracts definition names with a per-language regex table:

| Language | Definition line |
|---|---|
| Python | `def name(`, `class Name` |
| JavaScript / TypeScript | `function name(`, `class Name`, `const name = (`, `export function name(` |
| Go | `func name(`, `func (r) name(` |
| Rust | `fn name(`, `struct Name`, `impl Name` |
| Java / C# | a method signature: access modifier, type, `name(` |

Unknown language: aggregates only, no names.

**Candidate rule.** A normalised name -- lower-cased, camel and snake split to a token tuple -- defined in at least two files across at least two directories. Excluded: a stoplist of idioms (`main`, `init`, `new`, `run`, `setup`, `teardown`, `test_*`, `__init__`, `__str__`, `__repr__`) and of per-adapter naming (`normalise`, `parse`, `load`, `render`, `handle`, `build`), the last because one function per backend or tool is a pattern, not scatter. Ranked by directory count, then hotspot share; top 40 kept. Each candidate records `name`, `files`, `directories`, `hotspot_touch` (any file in the band) and `coupled` (any two of its files form a `coupling.json` pair). Output is sorted and deterministic.

**Family.** `FAMILY_BLOCKS["concerns"]`: scattered functionality, semantic duplicate functionality, drift from a written convention. `debt_type: architecture`; `type_id` TD-05 for semantic duplication, TD-10 for scatter, none for drift. Member of `default` and `deep`; not `quick`.

**Dispatch.** `plan_scan.py` adds one plan entry when `concern-index.json` has at least one candidate or the hotspot band is non-empty; otherwise `families_skipped` with reason `no leads`. Exactly one entry whether or not the plan is chunked -- the index is repository-wide, and scatter across modules is the point.

**Prompt.** The scout receives the directory aggregates, the hotspot band, the coupling pairs and the candidates. It never receives file leads. It is instructed to read at most 60 files to confirm candidates and at most 10 more of its own choosing for drift, naming each of those with a reason, and to report `files_read` in its output. The budget is instructional and audited -- `merge_findings.py` copies `files_read` into `stats` -- because nothing can enforce a read-only agent's reads. This is additive: `merge_findings.py` reads only the `findings` key from a scout document (`merge_findings.py:881`), so an extra top-level key is ignored today and recording it changes no existing path.

**Verifier questions.** Is the recurring name the same concept or a homonym? Would consolidating change behaviour? Is this a deliberate per-module implementation -- adapter, plugin, backend? For drift: which written convention does it contradict -- an ADR, README, CLAUDE.md, a `docs/` page -- cited by file and line, or is it the reader's taste?

**Traps.** Adapter and plugin naming (this repository's own `normalise_<tool>` functions); generated code; fixtures and corpora; language idioms.

**Tiering**, a new branch in `_family_cap_and_lift`:

| Finding | Tier |
|---|---|
| Verifier does not confirm | C |
| Verifier confirms | B |
| Verifier confirms and a `hotspot` or `coupling` token is present | A |

**Evaluation.** Each fixture gains one planted scattered function (the same concept implemented in two directories under one name) and one decoy (an adapter pattern: one `parse_<format>` per format).

## 5. Cross-cutting changes

**Chain.** Scan steps become: 1 inventory (now writing `edges` and the coupling annotations into `coupling.json`), **1a `concern_index.py`**, then 2 patterns onward unchanged in order. `SKILL.md` documents the new step; `skill_check.py` verifies the command. Sixteen families: `categories.FAMILIES` (`categories.py:44`) gains both names -- `merge_findings.py` imports it and drops any tool fact naming a family outside it (`merge_findings.py:707`) -- and `FAMILY_SETS` (`config.py:100-118`) adds them to `default` and `deep`; `plan_scan.py` renders two new prompt files; `verify_prompts.py` picks up the two families' question and trap blocks from `categories.py` as it does for the others; `apply_verdicts.py` gains the two cap branches; `merge_findings.py` records `files_read`.

**Budget.** Default scan: 14 scouts (12 + `performance` + `concerns`), at most one more verifier batch. The token-budget table in `SKILL.md` updates. The concern scout's cost is bounded by the 40-candidate cap and the 70-read instruction, not by repository size.

**Docs shipped in the same PR.** `SKILL.md` (steps, family list, budget table, caveats), `docs/architecture.md` (the join, the index, the two families' tier rules), `README.md` (family count), `docs/evaluation-log.md` (the corpus additions and the first run's numbers).

**Untouched.** `rank.py`; `baseline.py`; `design_writer.py`'s rendering; `promote.py`; `evidence_doc.py`; every existing family's prompt block, questions, traps and cap.

## 6. Tests

- `test_inventory_v2.py`: `edges` persisted in `coupling.json`; `has_edge` / `edge_direction` / `lead_kind` on pairs; the fan-in decile computed over non-null values only; a pair with a direct edge in either direction is never a modularity violation; a same-directory violation is kept and flagged.
- New `test_concern_index.py`: each language's regex table against a fixture line set; the normalisation (camel and snake to the same tuple); the stoplist; the two-files-two-directories rule; the top-40 cut and its ordering; `hotspot_touch` and `coupled`; byte-identical output on a second run; unknown language yields aggregates only.
- `test_tool_normalisers.py`: each `PERF*` code maps to the performance family with a `tool:ruff` token.
- `test_patterns.py`: the four performance regexes, each with a positive inside a loop body and a negative at loop level.
- `test_apply_verdicts.py`: the performance ladder (all four rows) and the concerns ladder (all three rows), plus the TD-37 cap sentence.
- `test_plan_scan.py`: the concerns entry dispatched once on a chunked plan; skipped with `no leads` on an empty index and empty band; `performance` and `concerns` present in `default` and `deep`, absent from `quick`.
- `test_validation.py`: `performance` accepted as a debt type; `TD-36` and `TD-37` join the `good` parametrisation at `:91`; `TD-38` rejected.
- `test_categories.py`: `FAMILIES` carries both new names; each new block has a definition, questions and traps.
- `test_tools_probe.py:1332` parity test stays green with both sides extended.
- `test_chain_goldens.py` / `test_e2e.py`: goldens regenerated for the two families' scout and verdict files on the fixtures that carry planted items; the corpus fixtures gain their planted items and decoys under `tests/fixtures/corpus`.
- `test_skill_check.py`: the new step's command matches `concern_index.py`'s argparse.

## 7. Build order

1. Taxonomy and validation: `VALID_DEBT_TYPES`, `_TYPE_ID_MAX`, the two family blocks' definitions in `categories.py`, the family sets in `config.py`. Pure data; everything else depends on it.
2. Graph-history join in `inventory.py`, with `edges` persisted, and the architecture prompt sections in `plan_scan.py` and `categories.py`.
3. `concern_index.py` and its tests.
4. Performance leads: `RUFF_SELECT` / `RUFF_KINDS`, the `patterns.py` table.
5. The two cap branches in `apply_verdicts.py`; `files_read` in `merge_findings.py`.
6. `plan_scan.py`: the concerns entry, the two prompt renderings, the chunked-plan rule.
7. Corpus: planted items and decoys, regenerated goldens, e2e updates.
8. `SKILL.md`, `docs/architecture.md`, `README.md`, `docs/evaluation-log.md`; `skill_check.py` green.

## 8. Migration and compatibility

A `coupling.json` from an earlier scan lacks the three new pair fields and `edges`; `plan_scan.py` treats an absent `lead_kind` as `null`, and a `coupling.json` without `edges` makes `concern_index.py` exit 5 with a message naming the missing key -- the chain is re-run from step 1, which is the no-improvisation rule applied. A baseline written before this change reads unchanged; new families produce new fingerprints and read as `NEW`. A `design.md` from an earlier scan parses unchanged: no anchor key is added. `quick` scans produce byte-identical `design.md` before and after.

## 9. Assumptions

**Real concerns**

1. **The four performance regexes will fire on things that are not loops.** `_scan_loops` delimits a body with `_indented_body` for indentation languages and `_brace_body` for brace languages, the same pair `_scan_catches` uses, so formatted code in either family is handled; the heuristic failure is a multi-line call argument list indented under a loop header in code no formatter has touched, which reads as body. *Decision:* they are leads, every one of which passes through a verifier whose first question is whether the call is actually inside the loop; and the corpus decoys measure the false-positive rate from the first run. *Residual risk:* lead noise consumes scout budget on repositories with unformatted code.
2. **The concern scout's read budget is unenforceable.** A read-only agent reads what it decides to read; the 60 + 10 instruction is audited through `files_read`, not enforced. *Decision:* accept, because the alternative -- pre-reading the 40 candidates' files into the prompt -- costs more tokens than it saves and removes the reader's judgment about which candidates deserve a look. *Residual risk:* an over-reading scout on a large repository; `files_read` in `stats` makes it visible.
3. **Name recurrence is a weak proxy for scattered functionality.** Two `validate` functions in two directories are usually unrelated. *Decision:* the stoplist removes the commonest idioms, the verifier's first question is "same concept or homonym", and the tier ladder keeps unconfirmed candidates at C. *Residual risk:* a scan on a repository with a strong naming convention floods the 40 slots with homonyms; the corpus decoy (`parse_<format>`) is exactly this case and measures it.

**Verified safe**

- `GraphResult.edges` and `directories` already exist (`reference_graph.py:59-67`); `inventory.py` writes `cycles`, `directories` and `unstable_edges` into the `coupling.json` document (`inventory.py:888-895`) and drops `edges` -- persisting it beside them is one line. Verified 2026-09-12: `edges` appears nowhere in `inventory.py`'s output.
- `_family_cap_and_lift` (`apply_verdicts.py:72`) is one function that returns both the cap and its lift description per family; `family_cap` (`:120`) and `_tier_and_reason` (`:166`) both read off it, so the cap sentence in `design.md` cannot drift from the tier logic. The `hotspot` and `coupling` tokens the new ladders test for are already written into `confirmed_by` by `merge_findings.py` (`:338` for `hotspot`) and read by `_token` (`apply_verdicts.py:56`).
- `RUFF_SELECT` (`tools_probe.py:326`) and `RUFF_KINDS` (`tool_normalisers.py:138`) are the existing mechanism for mapping a ruff code to a family; the normaliser drops any code outside `RUFF_KINDS` (`tool_normalisers.py:179-181`), and the parity test at `tests/test_tools_probe.py:1332` fails if only one side changes. All six `PERF` codes verified present on ruff 0.15.4.
- `_TYPE_ID_MAX` (`validation.py:40`) is the only taxonomy ceiling: the only other `TD-35` in `scripts/` is `pipeline-infra`'s own type-id tuple (`categories.py:420`), not a bound. `tests/test_validation.py:91` parametrises `TD-35` as valid and needs `TD-36`, `TD-37` added and `TD-38` as the new rejection case.
- `plan_scan._pairs` (`plan_scan.py:217`) already renders every coupled pair into the architecture lead block with `shared`, `ratio` and a `cross_only` switch; the join's `lead_kind` and direction extend that renderer rather than adding a lead source.
- `verify_prompts.py` reads each family's questions and traps from `FAMILY_BLOCKS` (`verify_prompts.py:31`, `:247`); two new blocks are picked up with no change there.
- `patterns.py` already has body-scoped scanning for both indentation and brace languages: `_scan_catches` (`:436`) with `_indented_body` (`:374`) and `_brace_body`; `_scan_loops` is the same shape with a different header regex.
- `coupling.json` pairs already carry `a`, `b`, `shared_commits`, `ratio`, `cross_directory` and are filtered by `min_shared: 3`, `min_ratio: 0.3` (`config.py`); the join adds fields and removes nothing.
- The v2 design's success criterion 8 ("a second scan classifies each finding NEW, UNCHANGED or RESOLVED") is unaffected: new families produce new fingerprints through the same `merge_findings` path.

**Minor or accepted**

- Six ruff codes only; other languages' local smells come through the `patterns.py` table until their normalisers land.
- The fan-in decile is computed per scan, so a file's `unstable-interface` status can change between scans as the repository grows; the baseline keys on fingerprint, not on lead kind, so this does not churn decisions.
- The concern scout's own findings can cite files the candidates did not name (the 10 free reads); that is the point of the allowance.
- Thresholds for hub-like and god-component signatures stay fixed; calibration is a recorded follow-on.
- The `RESOLVED` count stays a raw number in the frontmatter; reporting it as a rate is a recorded follow-on.
