# Survey: How LLM-Agent Tech-Debt Scan Skills, Commands and Products Are Designed

Research note 03 for the tech-debt-scan v2 architecture. Compiled 2026-09-02.

## 1. Method and sources

Searches ran across GitHub (SKILL.md, `.claude/commands`, `.claude/agents`, awesome lists, marketplaces), vendor documentation, and arXiv. Every artefact below was fetched and read; where only a README or docs page was reachable, that is stated. Inaccessible: the mcpmarket "Tech Debt Reviewer" (ten-agent skill) returned HTTP 429 twice; the Medium article on auditing a codebase with Cursor returned 403; the raw SKILL.md files for fastruby, ehmo and brooks-lint tech-debt were 404 at the guessed paths, so those entries rely on README and docs. No standalone Cursor rule, Moderne, Tessl, Blar or Devin "tech debt playbook" artefact was found; Stepsize now describes reporting only (acquired by ClickUp) and is omitted.

| # | Name | URL | Type | Popularity |
|---|------|-----|------|------------|
| 1 | ksimback/tech-debt-skill | https://github.com/ksimback/tech-debt-skill | Claude skill | 590 stars, 35 forks |
| 2 | fastruby/tech-debt-skill + blog | https://github.com/fastruby/tech-debt-skill ; https://www.fastruby.io/blog/tech-debt-audit-with-claude-code.html | Claude skill (Rails) | 21 stars; blog 2026-07-21 |
| 3 | anthropics/knowledge-work-plugins tech-debt | https://github.com/anthropics/knowledge-work-plugins/blob/main/engineering/skills/tech-debt/SKILL.md | Official Anthropic plugin skill | Anthropic-maintained |
| 4 | alirezarezvani tech-debt-tracker + /tech-debt | https://github.com/alirezarezvani/claude-skills (engineering/skills/tech-debt-tracker/SKILL.md) ; https://alirezarezvani.github.io/claude-skills/commands/tech-debt/ | Skill + command with scripts | 380-skill collection |
| 5 | hyhmrright/brooks-lint | https://github.com/hyhmrright/brooks-lint ; https://hyhmrright.github.io/brooks-lint/guide.html | Plugin (6 skills) | 1.4k stars, 66 forks |
| 6 | ehmo/code-overhaul-skill | https://github.com/ehmo/code-overhaul-skill | Claude skill | 95 stars |
| 7 | itsmesherry/claude-audit | https://github.com/itsmesherry/claude-audit | CLI product on Claude API | 11 stars |
| 8 | mhattingpete code-auditor | https://github.com/mhattingpete/claude-skills-marketplace/blob/main/productivity-skills-plugin/skills/code-auditor/SKILL.md | Marketplace skill | small |
| 9 | ZacheryGlass architecture-reviewer | https://github.com/ZacheryGlass/.claude/blob/master/agents/architecture-reviewer.md | Claude agent | personal |
| 10 | lodetomasi tech-debt-surgeon | https://github.com/lodetomasi/agents-claude-code/blob/main/tech-debt-surgeon.md | Claude agent | collection |
| 11 | wshobson/commands (tech-debt, full-review) | https://github.com/wshobson/commands | Commands + workflows | 2.6k stars |
| 12 | qdhenry/Claude-Command-Suite remove-dead-code | https://github.com/qdhenry/Claude-Command-Suite (.claude/skills/remove-dead-code/SKILL.md) | Skill (multi-agent) | 1.3k stars |
| 13 | github/awesome-copilot agents (janitor, simplifier, CAST advisor) | https://github.com/github/awesome-copilot/blob/main/docs/README.agents.md | Copilot agents | 200+ agents |
| 14 | GitHub Copilot "Reduce technical debt" | https://docs.github.com/en/copilot/tutorials/reduce-technical-debt | Vendor tutorial | official |
| 15 | Claude Code Code Review | https://code.claude.com/docs/en/code-review | Product docs | official |
| 16 | Anthropic AI-native SDLC | https://claude.com/blog/how-anthropic-secures-its-ai-native-software-development-lifecycle | Blog | 2026-07-21 |
| 17 | Qodo 2.0 | https://www.qodo.ai/blog/introducing-qodo-2-0-agentic-code-review/ | Product blog | 2026-02-04 |
| 18 | CodeScene ACE paper + product | https://arxiv.org/html/2507.03536 ; https://codescene.com/product/integrations/ide-extensions/ai-refactoring | Paper + product | AI-IDE 2025 |
| 19 | Sonar Remediation Agent / Vortex | https://www.sonarsource.com/blog/introducing-sonar-vortex/ | Product blog | 2026-06-30 |
| 20 | HackenProof multi-agent pipeline | https://hackenproof.com/blog/build-a-multi-agent-ai-code-review-pipeline | Blog | 2026-06-11 |
| 21 | CodeX-Verify | https://arxiv.org/abs/2511.16708 | Paper | 2025-12-03 |
| 22 | Augment Code detection guide | https://www.augmentcode.com/learn/how-to-automate-technical-debt-detection-with-ai | Vendor guide | 2025-10-10 |
| 23 | Cognition daily audit | https://cognition.com/blog/how-cognition-uses-devin-to-build-devin | Blog | 2026-02-27 |
| 24 | /refactor-suggest write-up | https://dev.to/myougatheaxo/automated-technical-debt-detection-with-claude-code-refactor-suggest-9hi | Blog | 2025-03-11 |
| 25 | Index-only: anthropics/skills, rohitg00 toolkit | https://github.com/anthropics/skills ; https://github.com/rohitg00/awesome-claude-code-toolkit | Catalogues | 173k / 2.6k stars |

The official anthropics/skills repository contains no code-quality or tech-debt skill; it was checked only for structure guidance.

## 2. Artefacts

### 2.1 ksimback/tech-debt-skill

The most-adopted pure-Claude skill. Three phases: Orient (read README, manifests, ADRs; run `git log --oneline -200` and `git log --stat --since="6 months ago"`; cross-reference the 20 largest files with the 20 most-modified to locate concentration; write a one-paragraph architectural model), Audit, Deliver. Detection is hybrid: LLM reading with `rg` and `ast-grep`, plus stack tools run in parallel (knip, madge, depcheck, pip-audit, ruff, vulture, cargo udeps, govulncheck, staticcheck and similar). Missing tools are noted, never installed. Nine categories: architectural decay, consistency rot, type and contract debt, test debt, dependency and config debt, performance and resource hygiene, error handling and observability, security hygiene, documentation drift. Scoring is LLM judgement on Severity (Critical to Low) and Effort (S/M/L). False-positive controls are the strongest in the pure-prompt group: a `file:line` citation is mandatory or the finding "doesn't count"; a required "Looks bad but is actually fine" section; uncertain items go to "Open questions for the maintainer"; no generic best-practice pattern-matching; no sycophancy filler. Output is `TECH_DEBT_AUDIT.md` with a findings table (ID, Category, File:Line, Severity, Effort, Description, Recommendation; 30 to 80 rows), Top 5 fixes with diff sketches, and a quick-wins list (Low effort × Medium+ severity). Re-runs read the prior file and tag RESOLVED, updated and NEW. Repos over 50k LOC dispatch one subagent per module with a 200-finding cap. No test harness; the README admits weakness above 200k LOC.

### 2.2 fastruby/tech-debt-skill

A Rails-only skill that is mostly a deterministic tool orchestrator. It runs the test suite with coverage, then bundler-audit, Brakeman, Trivy, next_rails, libyear-bundler, RubyCritic, Skunk and rails_stats; raw outputs land in a timestamped directory and the LLM synthesises a self-contained HTML report. Categories map to a 100-point health score in five equal blocks: security, dependencies, coverage, complexity, maintainability (red under 50, yellow to 74, green from 75). Prioritisation is Skunk's churn × complexity × (1 - coverage) score, plus a "top 3 recommended actions" list. No verification stage, suppressions or configuration. The blog's key lesson is data freshness: a file showed 0 percent coverage and a SkunkScore of 440 until tests were rerun, after which it was 67 percent and 145. Stale inputs produce confidently wrong rankings.

### 2.3 Anthropic knowledge-work-plugins tech-debt

Anthropic's official engineering plugin treats tech debt as a management framework rather than a scanner. Six categories: code, architecture, test, dependency, documentation, infrastructure debt. It defines a deterministic priority formula, `Priority = (Impact + Risk) × (6 - Effort)`, each on 1 to 5, and asks for a prioritised list with effort, business justification and a phased plan runnable alongside feature work. It contains no detection method, no evidence rule, no verification and no tracker integration. Its value is the scoring rubric and the insistence on business justification per item.

### 2.4 alirezarezvani tech-debt-tracker and /tech-debt

A scan → prioritise → dashboard pipeline built on three Python scripts: `debt_scanner.py` (emits `debt_items[]`, `file_statistics`, `recommendations` as JSON), `debt_prioritizer.py` (frameworks `cost_of_delay`, `wsjf`, `rice`; takes `--team-size` and `--sprint-capacity` and emits `prioritized_backlog` and `sprint_allocation`) and `debt_dashboard.py`, which computes trends from dated snapshot files `debt_YYYY-MM-DD.json`. Categories follow the same six-type taxonomy as 2.3. Verification is stated as a post-remediation loop: "re-run step 1, re-run step 3 with the new snapshot, and assert the targeted categories' counts dropped." Pattern detection is regex-level rather than semantic, and there are no evidence or false-positive instructions. Its distinctive contribution is the JSON inventory as the unit of exchange between deterministic stages, and snapshot-based trend tracking.

### 2.5 hyhmrright/brooks-lint

The best-engineered pure-prompt plugin found. Six skills share one taxonomy of six "decay risks" (R1 Cognitive Overload, R2 Change Propagation, R3 Knowledge Duplication, R4 Accidental Complexity, R5 Dependency Disorder, R6 Domain Model Distortion), each with concrete signals such as nesting over 3 or one change touching 3+ unrelated files. `/brooks-debt` scores items by Pain × Spread and produces a repayment roadmap; `/brooks-health` yields a composite 0 to 100 score. Every finding uses the chain Symptom → Source (book and chapter) → Consequence → Remedy with Critical/Warning/Suggestion severity. Health scoring is deterministic given the finding set, under three presets (strict, balanced, legacy-friendly). Configuration in `.brooks-lint.yaml` covers disable, focus, per-code severity override, ignore globs, path-level suppress and custom risk codes. Outputs: Markdown, Mermaid dependency graphs, SARIF 2.1.0 for GitHub Code Scanning, and a trend delta against `.brooks-lint-history.json`. Evaluation is unusually mature: a frozen corpus of 30 model-generated reports with nine deliberate false-positive scenarios, a 57-scenario eval suite, live-API evals and parser regression tests; a GitHub Action gates on score, critical findings and regression.

### 2.6 ehmo/code-overhaul-skill

An interactive audit that puts the human loop at the centre. Step 0 is a preflight scan (deprecation and warning density, TODO concentration, dependency drift, complexity hotspots) that recommends a depth; the user then commits to SURGICAL (one theme), SYSTEMATIC (section by section, at most four issues per section) or FULL AUDIT, and scope is never silently reduced. Five sections (Architecture, Code Quality, Tests, Performance, Dependencies) each end with an Approve/Revise/Pause gate; findings carry hierarchical IDs like 3.2B so batches can be approved at once. Each finding offers three options labelled with effort, risk, blast radius and maintenance cost, and the final report places items in a DO FIRST / PLAN CAREFULLY / IF TIME / SKIP impact-effort matrix. Deferred items become beads issues with file references and prerequisites; a production failure-modes table (test coverage × handling × visibility) supplies escalation evidence. Stack addenda exist for Swift, Go and web. No automated tests.

### 2.7 itsmesherry/claude-audit

A CLI on the Claude API rather than a skill, notable for its guardrail engineering. Pipeline: file scan honouring `.gitignore`, deterministic analysers (20+ secret rules, CVE lookup, AST/regex complexity), then an agentic loop where Claude investigates with read-only tools (`get_project_summary`, `read_file`, `search_code`, `read_dependency_manifest`, `list_files`). Seven dimensions: security, code quality, performance, architecture, dependencies, testing, documentation. Score 0 to 100 with letter grade and per-dimension bars; each finding has path, line, snippet and remediation. Controls: path sandboxing, a 25-turn cap, a 500k token budget, a repetition circuit breaker and result-size caps. Outputs Markdown, HTML, JSON and a per-turn agent trace; `--categories` filters scope; exit code 1 on critical findings for CI. No verification pass or baseline.

### 2.8 Single-agent audit prompts: mhattingpete code-auditor, ZacheryGlass architecture-reviewer, lodetomasi tech-debt-surgeon

These represent the modal design in marketplaces: one prompt, one pass. code-auditor covers six dimensions (architecture, code quality, security, performance, testing, maintainability), requires "file:line reference" and "actionable recommendations (not just observations)", classifies Critical to Low, and splits fixes into quick wins under a day and initiatives over five days, with a health score and metrics header. architecture-reviewer evaluates separation of concerns, SOLID, scalability and maintainability, with the instruction to avoid speculative findings and cite file, line and snippet; output is Strengths / Critical Risks / Improvements. tech-debt-surgeon is remediation-oriented (seams, incremental replacement, feature flags) across seven categories. None uses git history, tooling, verification, dedup, baselines or configuration.

### 2.9 wshobson/commands: tools/tech-debt and workflows/full-review

`tech-debt.md` is a prescriptive single prompt with numeric thresholds (methods over 50 lines, nesting over 3, cyclomatic over 10, god classes over 500 lines or 20 methods), churn and shotgun-surgery indicators, and duplication counts. Five categories: code, architecture (including technology debt), testing, documentation, infrastructure. Severity is four-tier, and ranking is ROI-based: effort against monthly cost (velocity loss hours × rate, bug cost). It demands quantification everywhere ("Quantify: Lines duplicated, locations") but has no confidence field or uncertainty handling, and assumes metrics exist. `full-review.md` is the fan-out pattern: six agents (code-reviewer, security-auditor, architect-reviewer, performance-engineer, test-automator, optional tdd-orchestrator) run in parallel via the Task tool and are consolidated into Critical / Recommendations / Suggestions / Positive. Merge is by prompt, with no dedup key or verification.

### 2.10 qdhenry remove-dead-code

A narrow but well-controlled multi-agent skill. Scout agents split by category (unused exports, orphaned files, dead imports, unreachable functions, unused dependencies), then a dedicated validator agent cross-checks every scout finding against the whole codebase before anything is flagged. The stated bias is explicit: "False negatives (missing some dead code) are acceptable. False positives (removing live code) are not." Protected classes (dynamic imports, reflection, string lookups, re-exported public types, framework route conventions, test helpers) are never removed. A timestamped backup branch is mandatory, a report precedes any removal, and type-check runs afterward. This scout-then-validator shape is the one most directly reusable for a scan skill.

### 2.11 github/awesome-copilot agents and the Copilot tech-debt tutorial

The C#/.NET Janitor lists five task categories (modernisation, code quality, performance, test coverage, documentation), scans in a fixed order and requires "Run tests after each modification." gem-code-simplifier is a hidden subagent that detects dead code via git blame and tests, complexity via cyclomatic and nesting metrics, and duplication over three lines; it reverts on failed verification and returns only JSON with confidence-weighted learnings. The CAST Imaging advisor shows the tool-backed pattern: an MCP server supplies `quality_insights` and occurrences, and prioritisation uses transaction involvement and data-graph dependencies, with an instruction to verify unexpected occurrences before reporting. GitHub's own tutorial is prompt-and-issue driven: ask Copilot for a prioritised list with problem statement, acceptance criteria and file pointers, file an issue per item, assign to the coding agent, and keep human PR approval; it lists five debt types (duplication, missing tests, outdated dependencies, inconsistent patterns, legacy code).

### 2.12 Claude Code Code Review and Anthropic's SDLC post

Anthropic's own reviewer is the clearest statement of the fan-out / verify / dedup / rank pipeline: parallel agents each hunt one class of issue, "a verification step checks candidates against actual code behavior to filter out false positives", results are deduplicated and ranked by severity, and every finding carries collapsible reasoning explaining how it was verified. Severity is Important / Nit / Pre-existing. A `REVIEW.md` file reaches the finding and verification agents and lets teams redefine severity, cap nit volume, skip paths and categories already enforced by CI, set a verification bar ("behavior claims need a file:line citation, not an inference from naming") and control re-review convergence. Reactions feed tuning; a machine-readable severity tally allows gating; effort level trades coverage against confidence. The SDLC post adds two operational controls: agents must "write a proof that their finding is valid", which raised substantive comments from 16 to 54 percent of PRs, and new agents run in shadow mode posting for human approval "until trust is earned".

### 2.13 Qodo 2.0

Parallel specialists (bug detection, code quality, security, test coverage) feed a judge agent that "resolves conflicts, removes duplicates, and filters out low-signal results", passing only findings above a confidence-and-relevance threshold. A recommendation agent grounds findings in past PRs and prior review decisions so previously accepted patterns are not re-flagged. Qodo argues recall should be optimised first because missed issues cannot be recovered downstream while precision can be tuned by filtering; its benchmark reported F1 60.1 percent and recall 56.7 percent on injected bugs.

### 2.14 CodeScene ACE

A product and paper about validated LLM refactoring, valuable here for its detection and verification design. Targets come from the CodeHealth metric's smells (Complex Conditional, Complex Method, Deep Nested Logic, Bumpy Road, Large Method) intersected with git-derived hotspots, so effort goes where poor quality meets high change frequency. LLM output passes a three-stage cascade: syntactic (linters), quality (CodeHealth must improve and the target smell must be gone) and semantic (pattern rules for known failure modes such as empty stubs). Raw LLM correctness was 37 percent across 100k+ attempts; after validation, 98 percent precision at 52 percent recall. Quality degrades beyond roughly 70 to 130 lines per function. The stated lesson is that out-of-the-box models need guardrails backed by ground-truth data.

### 2.15 Sonar Remediation Agent and Vortex

A backlog burn-down agent: engineers assign historical reliability, security, maintainability and SCA issues from the dashboard; the agent generates a fix and re-runs the same analysis engine, and a fix that fails the quality gate or introduces a new smell is regenerated. "The agent does not guess. It proves." Output is a PR with humans deciding what ships. Detection remains deterministic Sonar rules; the LLM is confined to remediation.

### 2.16 HackenProof pipeline and CodeX-Verify

Two independent sources on why category fan-out beats a single pass. HackenProof's four narrow agents (reentrancy, access control, cross-function auth, integer overflow) each carry one instruction over a shared, cached codebase prefix; findings merge on a `(contract, location)` key and, rather than collapsing duplicates, record which agents confirmed each spot. On a 5k-line protocol the single pass produced three findings, the fan-out fifteen with nine multi-agent confirmations, and it recovered a critical bug the single pass had reached and dismissed. CodeX-Verify formalises this: agents with low correlation (0.05 to 0.25) detect different bug types, single agents scored 32.8 percent accuracy while four combined reached 72.4 percent, at 76.1 percent true-positive rate.

### 2.17 Augment Code guide, Cognition daily audit, /refactor-suggest

Augment's guidance is about ranking inputs: change frequency, collaboration breadth, business criticality and test coverage, and about scoping adoption ("Pick the top three. See if the AI can generate fixes. Review the fixes."). Cognition runs Devin daily over PRs merged in the last 24 hours, flags three concrete violation types (hard-coded colours, non-standard spacing, components that should use the shared library) and files one Linear ticket per violation; no dedup step is described. The /refactor-suggest post uses four axes (banded cyclomatic complexity, semantic duplication, naming, dead code) with numeric score and effort per finding.

## 3. Cross-cutting patterns

What most designs share:

- A category taxonomy of five to nine buckets. The union across artefacts is: code/complexity, architecture and dependency structure, consistency, type and contract, test, dependency and config, performance, error handling and observability, security hygiene, documentation, infrastructure.
- Four-tier severity plus an effort size, both assigned by LLM judgement; a "quick wins" cut of low effort × high severity (1, 5, 6, 8, 13).
- Markdown report as the primary deliverable, usually a single file at repo root, with an executive summary and a findings table.
- A `file:line` evidence rule (1, 8, 9, 15, 18).

What the best designs add:

- Deterministic inputs before judgement: git churn and hotspots (1, 2, 5 via R2 signals, 14, 22), stack linters and dependency scanners (1, 2, 7), numeric thresholds (9, 24).
- Category-per-agent fan-out with a shared prefix, followed by a verifier and a judge that dedups on a location key and keeps confirmation counts (10, 12, 13, 16). The evidence that this cuts false positives while raising recall is consistent across a vendor (12), a startup (13), a practitioner (16) and a paper (21).
- Explicit negative space: a "looks bad but is fine" section (1), open questions instead of guesses (1), and a bias statement about which error is acceptable (10).
- Deterministic scoring formulas with tunable presets (3, 4, 5, 9), and a hotspot multiplier so the same smell in hot code outranks it in cold code (14, 2).
- Baselines and diffing: RESOLVED/NEW tagging against the prior report (1), dated JSON snapshots with trend deltas (4, 5), history files and regression gates (5).
- Suppression and scope configuration: ignore globs, disabled codes, severity overrides, path suppressions (5), category filters and budgets (7), instructions about what CI already enforces (12).
- Machine-readable outputs alongside prose: JSON inventory (4, 7, 16), SARIF (5), exit codes and severity tallies for gating (7, 12).
- Evaluation harnesses: frozen corpora with intentional false-positive cases (5), benchmarks with injected bugs (13), ground-truth refactoring datasets (14).
- Trust ramps: shadow mode until trust is earned (12), backup branches before change (10), human approval on every PR (11, 14, 15).

Anti-patterns observed:

- Single-prompt "comprehensive audit" with no tooling, history, verification or citations (8, 10, 9 partly). These produce generic best-practice lists.
- Demanding quantification the agent cannot measure (9), which invites fabricated numbers.
- Stale deterministic inputs feeding confident rankings (2).
- Health scores without a stated formula (8, 7), which cannot be compared across runs.
- Remediation bundled into the scan without a report-then-approve gate (contrast 10 and 6, which gate).
- Regex-level "pattern scanners" presented as debt detection (4).

Comparison table (Y = present, P = partial, - = absent):

| Artefact | Tooling | Git history | Fan-out | Verifier | Dedup key | Confidence | Evidence rule | Deterministic score | Baseline/diff | Config/suppress | Machine output | Human gate | Evals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 ksimback | Y | Y | P (per module) | - | - | P (open questions) | Y | - | Y | P | - | - | - |
| 2 fastruby | Y | Y (Skunk) | - | - | - | - | P | Y | - | - | P (raw dirs) | - | - |
| 3 Anthropic tech-debt | - | - | - | - | - | - | - | Y | - | - | - | - | - |
| 4 tech-debt-tracker | P (scripts) | - | - | - | - | - | - | Y | Y | - | Y | - | - |
| 5 brooks-lint | - | P | - | - | - | - | Y | Y | Y | Y | Y (SARIF) | P | Y |
| 6 code-overhaul | P | P | - | - | - | - | P | P (matrix) | - | - | P (issues) | Y | - |
| 7 claude-audit | Y | - | - | - | - | - | Y | Y | - | Y | Y | - | - |
| 8 code-auditor et al. | P | - | - | - | - | - | Y | - | - | - | - | - | - |
| 9 wshobson | - | P | Y (full-review) | - | - | - | P | Y (ROI) | - | - | - | - | - |
| 10 remove-dead-code | Y | - | Y (by category) | Y | - | P (bias stated) | Y | - | - | - | - | Y | - |
| 11 Copilot agents | Y | P (blame) | - | P (tests) | - | P | - | - | - | - | Y (JSON) | Y | - |
| 12 Claude Code Review | - | - | Y | Y | Y | Y (effort) | Y | - | P (re-review) | Y (REVIEW.md) | Y | Y | Y (reactions) |
| 13 Qodo 2.0 | - | Y (PR history) | Y | Y (judge) | Y | Y | - | - | - | - | - | Y | Y |
| 14 CodeScene ACE | Y | Y | - | Y (3-stage) | - | Y | - | Y | - | - | - | Y | Y |
| 15 Sonar | Y | - | - | Y (re-analyse) | - | - | - | Y | - | - | - | Y | - |
| 16 HackenProof / 21 CodeX | - | - | Y | P (confirmations) | Y | P | Y | - | - | - | Y | - | Y |

## 4. Design recommendations for a Claude Code tech-debt-scan skill

1. Split the pipeline into deterministic inventory, LLM detection, LLM verification, deterministic ranking, and reporting, and keep each stage's output as JSON so stages can be rerun independently (4, 7, 16, 12).
2. Build the inventory from git and tools before any judgement: churn and hotspots over a fixed window, largest files, ownership breadth, plus whatever linters and dependency scanners are installed, recorded as absent if missing (1, 2, 14, 22). Refresh coverage and similar inputs before trusting them (2).
3. Fan out detection one agent per category over a shared, cached repository prefix, with a narrow single instruction each and a per-agent finding cap (16, 12, 13, 21, 1). Fan out by module only for very large repos, nesting category agents inside module scopes (1).
4. Require every finding to carry `file:line`, a short evidence quote and a claimed category, and instruct agents that uncertain items go to an "open questions" list rather than the findings table (1, 9, 12).
5. Add a verifier agent that re-reads each cited location and must write a one-paragraph proof or reject; findings that fail are dropped or downgraded, and the proof is kept in the report (12, 10, 14). State the error bias explicitly, as remove-dead-code does: a missed item is acceptable, a fabricated one is not (10).
6. Deduplicate on a normalised `(path, line-range, category)` key and keep the count of agents that independently confirmed each item as a confidence signal rather than collapsing it (16, 13).
7. Rank with a stated deterministic formula over LLM-assigned inputs, for example severity × hotspot weight × (inverse effort), in the spirit of `(Impact + Risk) × (6 - Effort)` and Skunk's churn × complexity × (1 - coverage), with named presets a repo can choose (3, 2, 5, 14). Never ask the model to invent cost figures it cannot measure (9).
8. Keep a "considered and rejected" section and a "looks bad but is fine" section in the report; they are the cheapest false-positive control found and they make re-runs converge (1, 12).
9. Persist a baseline: a dated JSON snapshot plus the Markdown report, and on re-run tag items RESOLVED, CHANGED, NEW, with a trend delta and an optional regression gate (1, 4, 5).
10. Provide a repo-level configuration file for ignore globs, category focus and disable lists, per-category severity overrides, path suppressions and a note of what CI already enforces so the scan does not duplicate lint (5, 12, 7).
11. Emit Markdown for humans and JSON (optionally SARIF) for machines, with a severity tally line that a workflow can parse, and an exit code convention (5, 7, 12).
12. Hand off to humans by producing a report first and then, only on approval, creating one issue or PBI per accepted finding with problem statement, acceptance criteria and file pointers (14, 23, 6, 11). Batch approvals by hierarchical IDs rather than per-item prompts (6).
13. Ship an evaluation corpus: a fixture repository with planted debt and planted decoys that must stay clean, plus a parser test that scores are deterministic for a fixed finding set (5, 13, 14).
14. Start remediation, if offered at all, in shadow mode behind a backup branch and full test run, and keep it a separate skill from the scan (12, 10, 15).
