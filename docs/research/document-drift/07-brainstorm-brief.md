# document-drift: brief for the design brainstorm

Written 2026-10-09. This is the input document for a `superpowers:brainstorming` session on a new Claude Code skill, `document-drift`, that scans a repository's markdown, compares it against the code, and fixes documents that are stale or describe code that no longer exists. It condenses the five research notes and the split analysis in this folder into: the problem, what the evidence says, a candidate shape to argue with, the decisions the session has to make, measurable success criteria, and the assumptions the design rests on. Nothing in it is approved; the candidate shape is a strawman.

## 0. The research series

| File | What it is | Headline |
|---|---|---|
| `01-what-good-looks-like.md` | Literature and practitioner best practice, 54 sources, 20 implications | Grounded reference checks reach 0.9 precision; prose-to-prose LLM judgement sits near 0.6; just-in-time detection beats post hoc by 12 F1 points; incompleteness must never be reported as drift |
| `02-drift-issue-taxonomy.md` | Eighteen drift categories (DD-01 to DD-18) from the literature plus 82 sampled real fixes across 32 repositories | Well over half of what maintainers fix is a token that no longer resolves; maintainers delete far more often than they rewrite; measured lags of 15.5 months for a path rename |
| `03-survey-existing-tools-and-skills.md` | Sixty artefacts: 21 skills and commands, 10 products, 21 CI tools, 8 research prototypes | No official Anthropic docs-drift skill exists; hybrid tools agree on the deterministic/LLM boundary; eight gaps a Claude skill could fill |
| `04-fix-workflows-and-safety.md` | How tools fix safely, 76 sources, a five-class safety ladder | Ruff's Safe / Unsafe / DisplayOnly and ESLint's fix / suggestion are the precedents; LLM rewrites are correct 55 to 65 percent of the time; agent doc PRs are accepted at 61 to 92 percent |
| `05-repo-primitives-and-conventions.md` | What this repository already provides: 27 primitives, 27 conventions, the seams | tech-debt-scan already does dangling refs and whole-repo staleness; it has no rename detection, no `.rst` or `.adoc`, and will not fix |
| `06-programmatic-vs-agentic-split.md` | The split by stage, by category and by fix class, plus ten unsettled points | Fourteen script stages, four agent stages; the fix stage is the only genuinely new line |

## 1. Problem statement

Documentation in a repository decays silently. Only a few percent of commits touch the README ([02] section 5), so a path rename, a dropped flag, a removed module or a changed default leaves prose behind for months. The reader who trusts it loses time; the agent that reads it as context (every Claude Code session reads README and CLAUDE.md) is misled.

The skill's job: find the markdown documents in a repository, determine which of their claims about the code are no longer true, fix the ones that can be fixed with evidence, propose the ones that need a human eye, and flag the ones a tool must never touch. Superpowers plan and spec folders describe intended work, not current code, and are excluded from scanning; so are the other historical or intent documents listed in section 4.4.

## 2. What the evidence says, in ten points

1. **Resolvable tokens are the mechanical core.** Paths, links, anchors, identifiers, flags, config keys, env vars, scripts, versions. Eleven of eighteen categories are detected by resolving a token against something authoritative, and the sample says this covers the majority of real fixes ([02] section 4; [06] section 3).
2. **History supplies the fix.** The two published fixers whose patches were merged derived the replacement from history (redirect chain, `git log -S`). A fifteen-month-old rename is recoverable from `git log --follow` ([02] implication 2).
3. **The two-snapshot test is the best confidence signal nobody uses.** A reference that resolved at the doc's last substantive commit and no longer does is "describes code that no longer exists"; one that never resolved is a weak lead ([03] gap 2).
4. **Deletion beats rewriting.** Maintainers in the sample deleted sections far more often than they rewrote them; Google's guidance is "default to delete"; a deletion cannot hallucinate ([02] implication 8; [01] implication 7).
5. **LLM prose judgement is a 0.6 instrument.** Naive prompting produced a 98 percent flag rate because the model treated every undocumented detail as drift; enumerating categories as yes/no fields and dropping incompleteness in code fixed it. Give the model the diff and the paragraph, not the repo ([01] implications 4 and 5).
6. **LLM rewrites are a 0.6 instrument too.** Human-rated correctness of automatic comment updates is 55 to 65 percent: fine for a proposal, wrong for an unattended commit ([04] class C).
7. **The doc may be right.** A code-comment mismatch raises bug-introduction odds about 1.5 times; 21.5 percent of apparent false positives in one README study were updates developers had overlooked. Report "mismatch", never "doc is stale", for behaviour-level findings, and never auto-fix normative sentences ([01] implication 18; [04] implication 12; [02] DD-18).
8. **Noise kills adoption.** A doc bot that comments on every PR is ignored, then disabled, then the docs rot again. Precision at real base rates is the metric; a maintainer on record said two-thirds precision with line numbers and reasons would be acceptable ([03] failure modes; [02] implication 6).
9. **Intent escape hatches are universal.** Every mature detector has an ignore marker with a reason, an intentional-doc list (changelogs, migration guides, tutorials showing an old API) and a way to learn from triage ([03] failure modes; [04] implication 15).
10. **The repository has most of the scaffolding.** File walk, path classification, dangling-reference regexes, per-file git history, redaction, the report writer and parser with the status round-trip, the baseline diff, the verifier prompt pattern, the fixture and golden conventions, the live-run harness and the SKILL.md linter all exist and are reusable as-is or by copy ([05] section 2).

## 3. Candidate shape (a strawman to argue with)

### 3.1 Commands

- `/document-drift <repo> [--base <ref>] [--apply safe|none|all-approved] [--network] [--workdir .document-drift]` scans and writes a report.
- The human edits `status:` fields in the report.
- `/document-drift-apply` reads the report back and applies approved hunks, re-verifies, records the baseline.
- `/document-drift --from-evidence <path>` accepts a tech-debt-scan `evidence.md` for a `doc-drift` finding (the promote seam, [05] section 3b).

### 3.2 Pipeline, with the layer per step

Script steps are pinned commands with pinned output files under `--workdir`; agent steps are read-only Explore agents that write their own output file and reply with a receipt (the repository's convention, [05] C-rules).

1. `inventory.py` walks and classifies the tree, applies exclusions, records git availability. Script.
2. `extract.py` parses each doc with a markdown parser and emits typed tokens with doc line and fence context. Script.
3. `resolve.py` resolves every token against tree, anchors, identifier sets, `--help` or parser idioms, schemas, manifests and registries; runs the rename and two-snapshot lookups; emits `candidates.json` with a confidence class per candidate. Script.
4. `temporal.py` computes per-doc, per-referenced-path lag against substantive commits and the kind of change, as ordering keys only. Script.
5. `links.py` (only with `--network`) checks external URLs with cache and retries. Script.
6. `examples.py` parses fenced blocks and resolves their imports; runs nothing unless the repository's own doctest runner is configured. Script.
7. `plan.py` selects the leads that need comprehension, bundles paragraph plus diff plus the relevant code span, renders one prompt file per document batch. Script.
8. Comprehension agents answer the enumerated schema per lead (over-promise, direct mismatch, example not runnable, structure mismatch; incompleteness is not a field). Agent.
9. `merge.py` relocates every quoted doc and code line, diverts fabricated citations, fingerprints, assigns the fix class. Script.
10. Verifier agents confirm, downgrade, reject or refer each comprehension finding in a fresh context. Agent.
11. `fixes.py` authors class A and B hunks from the rename map and manifest values. Script.
12. Fix agents author class C hunks under the SEARCH/REPLACE, citation, length and no-new-identifier constraints. Agent.
13. Faithfulness agents check each class C hunk in a fresh context. Agent.
14. `report.py` renders `drift.md` with frontmatter, one section per finding (id, class, category, doc line, evidence, proposed hunk, `status: pending`), the negative-space sections (intentional, not assessed, open questions, skipped documents) and the coverage table; self-checks by re-parsing. Script.
15. On apply: `apply.py` reads back by id, applies approved hunks atomically, re-runs steps 2 and 3 on touched docs, refuses any hunk that does not take its finding to zero or creates a new one, records the baseline. Script.

### 3.3 Finding schema (sketch)

`id`, `category` (DD-xx), `class` (A to E), `doc` and `doc_line`, `quote`, `token` and `token_kind`, `resolution` (what was looked up and what came back), `history` (rename candidate, two-snapshot result, commit), `code_evidence` (`path:line` and quote, when the finding is about code), `proposed_hunk` (search, replace, or delete), `confidence_basis` (resolver, history, agent, verifier), `status`.

### 3.4 Configuration (`.document-drift.yaml`, sketch)

Exclude globs (defaults: `docs/superpowers/plans/**`, `docs/superpowers/specs/**`, `CHANGELOG*`, `LICENSE*`, `adr/**`, `rfcs/**`, vendored and generated paths, `README_*.md` siblings handled as a family); intentional-doc globs; per-category class overrides; apply policy; network on or off; declared doc-to-code map, optional; ignore markers with reasons are inline (`<!-- drift-ignore: REASON -->`).

### 3.5 What is reused from tech-debt-scan

Reuse as-is by copy with a byte-equality test: `redaction.py`, `validation.py`, `slugs.py`, `evidence.py`, `design_parser.py`, `git_history.py`, `reference_graph.py`, `skill_check.py`, the walk and classification parts of `inventory.py`, `tests/helpers/make_history.py`. Copy and adapt: the design writer, the baseline, the promote orchestrator, the verifier prompt renderer, config loading, the live harness, the evaluator. Not applicable: the ranking formula and the tier table ([05] section 2).

## 4. Decisions the brainstorm must make

Each with options and the evidence-backed recommendation. Numbers match [06] section 5.

**D1. Doc-to-code relationship: inferred only, or inferred plus declared, or learned.** Recommendation: inferred by the token extractor, with an optional declared map in config and a write-back of accepted findings as learned exceptions ([03] gap 3; [01] implication 17).

**D2. Check backticked identifiers by default?** Recommendation: yes, but rank by the two-snapshot test and report "never resolved" tokens only in the coverage section unless the user opts in ([03] gap 2).

**D3. Author class C text before or after human approval?** Recommendation: after verification, before human review, so the human approves a concrete diff, following the note-agent precedent; cap the number of class C proposals per run ([05] section 4; [04] section 1 on reviewer abandonment).

**D4. Scope: whole-repo audit, change-driven, or both.** Recommendation: both in one skill; `--base` derives scope from changed files, no `--base` runs a bounded audit ordered by temporal signals, with "surveyed but not deeply inspected" disclosed ([03] gap 8).

**D5. Execute fenced code blocks?** Recommendation: parse and import-resolve only in v1; run only when the repository already configures a doctest-style runner; never install or build ([01] implication 12; tech-debt-scan non-goals).

**D6. Date lag: finding, warning or ordering key.** Recommendation: ordering key only ([01] section 3 tier 3).

**D7. Do classes A and B auto-apply by default?** Options: never without a status flip (this repository's precedent); Ruff-like auto-apply of A and B; a bulk pre-approval line at the top of the report. Recommendation: the bulk pre-approval line, so one human action approves every provable hunk and nothing is written without a status flip ([04] implication 1; [05] C18).

**D8. Language-agnostic flag and config resolution.** Recommendation: `--help` diff when a command is runnable without side effects, else a union-of-idioms regex over parser source; measure precision on the fixture corpus before trusting either ([06] 5.8).

**D9. Standalone, promotion target, or both.** Recommendation: standalone first with the `--from-evidence` seam designed in; the tool-registry feedback edge is a later phase ([05] section 3).

**D10. Code sharing with tech-debt-scan.** Recommendation: copy with a byte-equality test, as karate-bootstrap did; consolidate only if a third copy appears ([05] section 7).

**D11. Report format and the status vocabulary.** Reuse the design.md anchor shape and `pending / approved / rejected / accepted / promoted`, reading `approved` as "apply" and `promoted` as "applied", or extend `OPTIONAL_KEYS` and add `applied`? ([05] P9, P10).

**D12. README translations and mirrored docs.** Apply the same structural edit across `README_*.md` siblings, or flag the siblings only? ([02] section 5).

**D13. Which doc formats.** `.md` only, or `.md`, `.rst` and `.adoc`? The repository's docs block never reaches `.rst` or `.adoc` today ([05] receipt).

**D14. The precision bar and how it is measured.** A human-labelled sample of the target repository, not a paper figure; what number sets the bar for auto-apply classes versus proposal classes? ([01] implication 19).

## 5. Non-goals, candidate

Generating documentation that does not exist (absence is tech-debt-scan's TD-08 half, and incompleteness is not drift). Editing CHANGELOG, LICENSE, CODE_OF_CONDUCT, people lists, ADRs, RFCs, roadmap and plan or spec folders. Fixing code when the doc is right (flag with both sides). Running builds or project code beyond a configured doctest runner. Editing generated regions (route to the generator). Prose style and lint (Vale and markdownlint exist). A composite documentation health score. Any network call without `--network`.

## 6. Success criteria, candidate and measurable

1. Every DD-01 to DD-18 category has an explicit disposition (scanned, flag-only, out of scope) and a named detect layer and fix class.
2. On the fixture corpus, no planted decoy reaches class A or B, and every class A or B hunk applies cleanly and takes its finding to zero.
3. `resolve.py` and `report.py` produce byte-identical output for a fixed inventory and fixed agent files.
4. Every finding cites a doc line that `merge.py` found on disk; every class C hunk cites a `path:line` that resolves; fabricated citations are diverted, never reported.
5. A second run over the same repository classifies each finding NEW, UNCHANGED or RESOLVED and honours ignore markers with reasons; stale markers are reported.
6. The report carries coverage: documents scanned, documents skipped and why, token classes resolved, claim classes examined, and acceptance per class from the previous run.
7. Precision of class A and B on a human-labelled sample of two real repositories meets a bar the brainstorm sets (the literature's floor is two-thirds; the auto-apply classes should be well above it).
8. Deterministic stages complete without the network and without executing project code.

## 7. Fixture corpus requirements

At least one fixture with real git history replayed from `history.yaml` ([05] P25), because staleness, renames and the two-snapshot test are history facts. Planted drift, one per category the skill scans: a path to a deleted file; a path to a file renamed in a later commit; an identifier the code no longer defines; a flag a script no longer accepts; an example importing a moved symbol; a version string behind the manifest; a directory tree missing a renamed entry; a negated capability sentence that shipped; a README untouched while its referenced file churned. Planted decoys with `why` and `sources`: a path that resolves only as a directory; a dotted name that is prose; a URL in a fenced block; illustrative pseudo-code; a doc describing a planned or external interface; a generated API doc; a CHANGELOG entry describing an old version; a plan-folder document; a normative sentence where the code regressed (must route to E, never A to C); a `README_fr.md` sibling. Three languages so every resolver idiom fires on at least two ([05] section 5).

## 8. Risks

- **Noise from identifier resolution** buries real findings (the awesome-copilot experience). Mitigation: two-snapshot ranking and D2.
- **Over-editing by the fix agent** despite constraints. Mitigation: SEARCH/REPLACE with single anchor, length cap, faithfulness check, per-hunk approval.
- **Editing a doc that was right.** Mitigation: normative-sentence routing to E, recent-change routing to E, "mismatch" wording.
- **Prompt injection from repository text.** README, comments and commit messages are evidence, never instruction; prompts must say so ([03] failure modes).
- **Copy drift between skills** in the shared scripts. Mitigation: byte-equality tests.
- **Windows argv and reply truncation.** Pass files, not inline JSON; agents write their own output ([05] C-rules).

## 9. Assumptions

Each assumption the candidate shape rests on, its status, and what it costs if wrong.

| # | Assumption | Status | Cost if wrong |
|---|---|---|---|
| A1 | Token resolution against tree, manifests and parsers covers the majority of real drift fixes | Measured in [02]'s 82-fix sample and sweep, not on this owner's repositories | The script layer finds less than expected; more load on the 0.6-precision agent stage |
| A2 | The two-snapshot test separates "gone" from "never existed" with high precision | Unverified; proposed by DOCER's observation, never measured | Identifier checking stays as noisy as awesome-copilot found it; D2 defaults to opt-in |
| A3 | Rename detection from `git log --follow` and `git log -S` yields a unique candidate often enough to make class A worthwhile | Unverified on any corpus; `git_history.py` has no rename detection today | Class A shrinks toward version strings only; more findings fall to class B or D |
| A4 | A `--help` diff or a union-of-idioms regex resolves CLI flags precisely enough across languages | Unverified; tech-debt-scan's regex rules were measured on Python only | DD-04 moves from mechanical to assisted |
| A5 | Config keys can be resolved against a schema, defaults file or struct without a per-language parser | Unverified | DD-05 moves to assisted |
| A6 | A constrained class C prompt with a second-model check lifts acceptance above the published 55 to 65 percent | Unverified; the published figures are for unconstrained updaters | Class C becomes display-only in practice; the skill is mostly a deleter and renamer |
| A7 | Markdown is the only doc format that matters for v1 | Owner-stated scope; `.rst` and `.adoc` are D13 | Repositories with Sphinx or AsciiDoc docs get partial coverage |
| A8 | The design.md status round-trip is an acceptable fix gate for an interactive session | Verified as a pattern in tech-debt-scan; unverified for fixes | A per-hunk interactive prompt may be wanted instead; D7 and D11 |
| A9 | Agent output of 5 to 24 KB per step requires file hand-off | Measured in tech-debt-scan ([05] C-rules) | None if followed |
| A10 | Copying shared scripts with a byte-equality test is an acceptable sharing model | Repository precedent, owner not asked | A shared package would need a change to the direct-path rule |
| A11 | No executing project code is a hard constraint for this skill as for tech-debt-scan | Inferred from the sibling skill's non-goals; owner not asked for this skill | D5 may open to sandboxed doctest execution |
| A12 | Published precision figures do not transfer; the bar must be set on a human-labelled sample | Stated in three sources ([01] implication 19) | None if followed; a paper figure used as a bar would be wrong |
| A13 | The owner wants a standalone skill with the promote seam, not a tech-debt-scan extension | Owner's request says "another skill"; the seam is my inference | D9 |

## 10. Suggested order for the session

Confirm the problem statement and non-goals (sections 1 and 5). Walk D7, D3 and D5 first, because the fix policy, who authors proposals and whether anything executes shape everything else. Then D4, D2 and D1, which set the scope and the noise floor. Then D9 to D13, which are integration and format choices. Set the success criteria and the precision bar last (D14), once the classes are agreed. Each assumption in section 9 that the session decides matters should become either a spike before planning or an amendment to the spec.
