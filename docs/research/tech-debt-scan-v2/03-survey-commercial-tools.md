# Survey: How Commercial and Open-Source Technical-Debt Tools Are Designed

Research input for tech-debt-scan v2. Audience: the judge agent deriving an architecture for an LLM-driven, read-only repository scanner that finds debt, ranks it, and hands it to a human.

## 1. Method and sources

Every claim below comes from a page fetched during this survey (WebFetch, 2026-09-02) unless marked "search excerpt only". Pages that were unreachable are listed with the substitute used.

| Name | URL | Type |
|---|---|---|
| SonarQube metrics definition | https://docs.sonarsource.com/sonarqube-server/user-guide/code-metrics/metrics-definition | Product docs |
| SonarQube Cloud: new code | https://docs.sonarsource.com/sonarqube-cloud/standards/about-new-code.md | Product docs |
| SonarQube Cloud: new code calculation | https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/project-analysis/configuring-new-code-calculation.md | Product docs |
| SonarQube Cloud: rules and MQR mode | https://docs.sonarsource.com/sonarqube-cloud/standards/managing-rules/rules.md | Product docs |
| SonarQube Cloud: quality gates | https://docs.sonarsource.com/sonarqube-cloud/standards/managing-quality-gates/introduction-to-quality-gates.md | Product docs |
| SonarQube Cloud: editing issues | https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/issues/editing.md | Product docs |
| CodeScene: Code Health | https://codescene.io/docs/guides/technical/code-health.html | Product docs |
| CodeScene: Hotspots | https://codescene.io/docs/guides/technical/hotspots.html | Product docs |
| CodeScene: Change coupling | https://codescene.io/docs/guides/technical/change-coupling.html | Product docs |
| CodeScene: Knowledge distribution | https://codescene.io/docs/guides/social/knowledge-distribution.html | Product docs |
| CodeScene: PR integration | https://codescene.io/docs/guides/pr-integration/integrate-into-ci-cd.html | Product docs |
| CodeScene: Code Health product page | https://codescene.com/product/code-health | Marketing |
| Code Red (Tornhill and Borg) | https://arxiv.org/abs/2203.04374 | Paper |
| Qlty (ex Code Climate) maintainability metrics | https://docs.qlty.sh/cloud/maintainability/metrics | Product docs |
| Qlty complexity | https://docs.qlty.sh/complexity | Product docs |
| Codacy metrics FAQ | https://docs.codacy.com/faq/code-analysis/which-metrics-does-codacy-calculate/ | Product docs |
| Codacy repository dashboard | https://docs.codacy.com/repositories/repository-dashboard/ | Product docs |
| DeepSource issues | https://docs.deepsource.com/docs/dashboard/repository/issues | Product docs |
| Qodana baseline | https://www.jetbrains.com/help/qodana/qodana-baseline.html | Product docs |
| Qodana quality gates | https://www.jetbrains.com/help/qodana/quality-gate.html | Product docs |
| NDepend technical debt | https://www.ndepend.com/docs/technical-debt | Product docs |
| CAST Highlight: TD estimates | https://doc.casthighlight.com/feature-focus-enhanced-technical-debt-estimates/ | Product docs |
| CAST Highlight: TD Advisor | https://doc.casthighlight.com/exploring-new-technical-debt-advisor-views-cast-highlight/ | Product docs |
| Kiuwan code analysis | https://www.kiuwan.com/code-analysis/ | Marketing (docs page returned 403) |
| Embold | https://embold.io/ | Marketing |
| SciTools Understand | https://scitools.com/ | Marketing |
| DesigniteJava | https://github.com/tushartushar/DesigniteJava | OSS README |
| Arcan (ESSeRE lab) | https://essere.disco.unimib.it/wiki/arcan/ | Research site (arcan.tech suspended) |
| Sonargraph Architect | https://www.hello2morrow.com/products/sonargraph/architect | Marketing |
| Lattix metrics | https://docs.lattix.com/lattix/userGuide/Metrics.html | Product docs |
| Structure101 | https://sonarsource.com/structure101/ | Vendor notice |
| ArchUnit user guide | https://www.archunit.org/userguide/html/000_Index.html | OSS docs |
| dependency-cruiser | https://github.com/sverweij/dependency-cruiser | OSS README |
| madge | https://github.com/pahen/madge | OSS README |
| JDepend | https://raw.githubusercontent.com/clarkware/jdepend/master/docs/JDepend.html | OSS docs |
| Dependabot version updates | https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates | Product docs |
| Renovate Merge Confidence | https://docs.renovatebot.com/merge-confidence/ | Product docs |
| OSV-Scanner | https://google.github.io/osv-scanner/ and /configuration/ | OSS docs |
| deps.dev | https://docs.deps.dev/ | Product docs |
| Snyk Risk Score | https://docs.snyk.io/scan-fix-and-prevent/fix/prioritize-issues-for-fixing/risk-score | Product docs |
| npm outdated | https://docs.npmjs.com/cli/v10/commands/npm-outdated | Product docs |
| Sonatype State of the Software Supply Chain 2026 | https://www.sonatype.com/state-of-the-software-supply-chain/introduction | Industry report |
| knip | https://knip.dev/ | OSS docs |
| ts-prune | https://github.com/nadeesha/ts-prune | OSS README |
| vulture | https://github.com/jendrikseipp/vulture | OSS README |
| Go deadcode | https://pkg.go.dev/golang.org/x/tools/cmd/deadcode | OSS docs |
| jscpd | https://github.com/kucherenko/jscpd | OSS README |
| PMD CPD | https://pmd.github.io/pmd/pmd_userdocs_cpd.html | OSS docs |
| Simian | https://simian.quandarypeak.com/ | OSS docs |
| Stepsize | https://stepsize.com/technical-debt and Atlassian Marketplace app 1223357 | Marketing |
| SATDBailiff | https://arxiv.org/abs/2107.00073 | Paper |
| tsDetect smell catalogue | https://testsmells.org/pages/testsmells.html | Research tool docs |
| Develocity flaky test guide | https://docs.develocity.ai/2026.1/guides/flaky-test-detection-guide/ | Product docs |
| Buildkite Test Engine | https://buildkite.com/docs/pipelines/configure/tests/test-suites/test-state-and-quarantine and /docs/pipelines/reduce-flaky-tests | Product docs |
| PIT | https://pitest.org/ | OSS docs |
| Stryker configuration | https://stryker-mutator.io/docs/stryker-js/configuration/ | OSS docs |
| Jaspan and Green 2023, IEEE Software 40(3) | https://jimmyhmiller.com/pdfs/google-tech-debt.pdf (mirror; IEEE Xplore page returned no body) | Paper |
| getdx summary of Jaspan and Green | https://newsletter.getdx.com/p/measuring-and-managing-tech-debt | Secondary |

Inaccessible: SonarQube Server user-guide pages for Clean as You Code and issues (404; Cloud equivalents used), Sonar's Clean as You Code marketing page (404), the Code Climate developer docs (redirect to Qlty), designite-tools.com (empty body), arcan.tech (account suspended), lattix.com home (403), Kiuwan docs and support pages (403), Snyk's legacy priority-score URL (404). No published Microsoft, LinkedIn or Meta technical-debt tooling was found by search.

## 2. Tools and families

### SonarQube / SonarQube Cloud

Commercial with a free Community Build; broad multi-language rule engine. The fetched pages do not describe the scanner-to-server pipeline, so it is not covered here. Detection is rule based, with metrics layered on top. Technical debt is "the sum of the maintainability issue remediation costs", each issue carrying an effort in minutes. Debt ratio equals debt divided by (30 minutes per line, configurable, times lines of code); the SQALE maintainability rating is A below 5 percent, B 5 to 10, C 10 to 20, D 20 to 50, E above 50. In Multi-Quality Rule (MQR) mode each rule maps to one or more software qualities (Security, Reliability, Maintainability), each with its own impact severity (Blocker, High, Medium, Low, Info); the older type model (Bug, Vulnerability, Code Smell, Hotspot with Blocker to Info severities) is deprecated. Rules also carry clean code attributes (Consistency, Intentionality, Adaptability, Responsibility). Reliability and security ratings in MQR mode are set by the single worst open issue. New code is defined by previous version, number of days (default 30, maximum 90), specific version or specific date, with an organisation-level default. The stock "Sonar way" quality gate applies only to new code: reliability, security and maintainability ratings A, all new security hotspots reviewed, new coverage at least 80 percent, new duplication at most 3 percent. Gates report Passed, Failed or Not Computed. Issue statuses are Open, Accepted and False Positive, with reopen; changing status requires the Administer Issues permission, comments are optional, tags are inherited from rules, and bulk changes are supported. C-family projects can resolve issues from a code comment with a `sonar-resolve` keyword.

### CodeScene

Commercial, multi-language, behavioural analysis that fuses source metrics with version-control mining. Code Health is a 1 to 10 score (10 is most maintainable) bucketed green, yellow, red. It aggregates more than 25 factors at module level (low cohesion via LCOM4, brain class, developer congestion, complex code by departed contributors, large files), function level (brain method, DRY violations, complex method, primitive obsession, large method) and implementation level (nested complexity, bumpy road, complex conditionals, large or duplicated assertion blocks). File scores are averaged weighted by lines of code; rules can be re-weighted or disabled through a JSON file or in-code directives. Hotspots rank files by change frequency times low code health, then boost by change coupling, cross-team impact and coordination bottlenecks; the docs cite a case where prioritised hotspots were 1.2 percent of the code but 12.5 percent of effort and 45 percent of bugs. Change coupling is inferred from co-commits, same-author edits within a time window, or shared ticket IDs. Knowledge analysis computes key-personnel risk, low system mastery and coordination bottlenecks from full file history, and simulates off-boarding. PR gates include a hotspot-decline gate, critical health rules, new-code health, advisory rules, goal violations and codeowners protection, scoped by glob, with per-finding suppression and counts of detected, fixed, ignored and suppressed findings. Validation: the Code Red paper (Tornhill and Borg) analysed 39 proprietary codebases and 30,737 files and reports 15 times more defects, 124 percent longer development time and 9 times longer maximum cycle time for low-health code.

### Code Climate (Qlty), Codacy, DeepSource, Qodana

Qlty inherits Code Climate's model: a project grade from technical debt ratio (A below 5 percent, B 5 to 10, C 10 to 20, D 20 to 50, F 50 and above), file and directory grades from a logarithmic function of accumulated debt, and effort in minutes attached only to duplication and structure issues, not complexity. Three maintainability inputs: complexity (cognitive and cyclomatic), duplication, structure smells. Codacy grades A to F as a weighted average of issues, complexity, duplication and coverage without publishing weights, evaluates PRs as "up to standards" against configurable gate rules, and tracks issue categories including security, style, unused code and documentation. DeepSource groups issues into Recommended, Secrets, Bug Risk, Anti-pattern, Security, Performance, Typecheck, Coverage, Style and Documentation, with Critical, Major and Minor severities, first-seen and last-seen sorting, in-code `skipcq` suppression, dashboard suppression by glob, test files or repository, an Autofix that opens PRs, and false-positive marking that feeds back to the vendor. Qodana's baseline is a SARIF snapshot; each later run classifies problems as Unchanged, New or Absent, and quality gates fail the build (exit code 255) on a total threshold, per-severity thresholds (critical, high, moderate, low, info), coverage thresholds including fresh-code coverage, and license audits.

### NDepend, CAST Highlight, Kiuwan, Embold, Understand

NDepend (.NET) makes every rule a CQLinq query that emits two numbers per issue: Debt (time to fix) and Annual Interest (time lost per year if unfixed). Severity is derived from annual interest: Info under 2 minutes a year, Minor under 20 minutes, Major under 2 hours, Critical under 10 hours, Blocker above. Debt rating uses the SQALE A to E bands, and Breaking Point equals debt divided by annual interest, so lower means faster payback. The baseline defaults to the nearest 30-day-old analysis and "since baseline" queries list new and fixed issues. CAST Highlight computes debt as occurrences of each code insight times a per-insight effort from a vendor-calibrated, editable template, expressed in time rather than money. Its Technical Debt Advisor segments applications by business criticality and technology obsolescence into Update First, Update Next and Up-To-Date, and flags applications appearing in multiple risk categories, across three debt sources: software health (agility, resiliency, elegance), deprecated technology and outdated open source. Kiuwan (search excerpt only; docs returned 403) reports a Global Indicator over security, efficiency, maintainability, reliability and portability, a Risk Index, and Effort to Target computed from defect priority and remediation effort. Embold advertises 30 or more design anti-patterns, coupling and cohesion metrics, and on-premise PR review. Understand is a commercial multi-language metrics and dependency-graph workbench with 3000-plus CodeCheck rules oriented to MISRA and AUTOSAR compliance.

### Architecture-smell and dependency-structure tools

DesigniteJava (Apache-2.0) detects 17 design smells (for example Cyclic-Dependent Modularization, Hub-like Modularization, Insufficient Modularization, Deep and Wide Hierarchy) and 10 implementation smells (Complex Method, Long Parameter List, Magic Number, Empty catch) and emits class metrics such as WMC, DIT, LCOM, fan-in and fan-out. Arcan detects Unstable Dependency, Hub-Like Dependency, Cyclic Dependency and God Component on a graph database; a search excerpt of its 2017 tool paper reports precision between 70 and 100 percent. Sonargraph Architect uses an architecture DSL, a "cycle break-up computer" that finds the cheapest edges to cut, and an issues view where findings can be filtered, ignored or turned into tasks. Lattix works on a dependency structure matrix and publishes system metrics: System Stability equals 100 minus average impact over atom count times 100, System Cyclicality and Intercomponent Cyclicality (target near zero), and coupling enrichment relative to a random graph. Structure101 was acquired by Sonar and is no longer sold. ArchUnit turns architecture rules into JUnit tests (layers, onion, slice cycles, naming) and its FreezingArchRule stores existing violations so only new ones fail, shrinking the store as violations are fixed. dependency-cruiser reports circular, orphan, missing and forbidden dependencies plus reachability at error, warn or info severity with JSON, dot, mermaid and HTML outputs; madge finds cycles, orphans and leaves. JDepend defines the classic package metrics: instability I = Ce / (Ce + Ca), abstractness A, and distance from the main sequence D = |A + I - 1|.

### Dependency and supply-chain tools

Dependabot detects newer semver versions from manifests named in a config file, opens PRs, and applies a default 3-day cooldown that security updates skip. Renovate's Merge Confidence attaches Age, Adoption, Passing and Confidence badges to update PRs; confidence is Low, Neutral, High or Very High, learned from millions of Renovate PRs since 2017 with a proprietary model, and drives auto-merge policies. OSV-Scanner matches lockfiles, source and container images against OSV.dev and adds license scanning; its TOML config suppresses a vulnerability by id with an optional `ignoreUntil` date and `reason`, and package overrides carry `effectiveUntil` and `reason`. deps.dev exposes full dependency graphs, OSV advisories and version data for seven ecosystems through web, API and BigQuery. Snyk's Risk Score (0 to 1000) multiplies an impact subscore (CVSS confidentiality, integrity, availability, scope, plus user-set business criticality) by a likelihood subscore (exploit maturity, daily EPSS, vulnerability age, CVSS exploitability, social trends, package popularity), adjusted by reachability and transitive depth. `npm outdated` prints Current, Wanted, Latest and Depended-by, colouring in-range updates red and out-of-range yellow, with JSON output. Sonatype's 2026 report stresses continued download of vulnerable versions despite available fixes and warns of "triage failure, false confidence, and wasted effort" when vulnerability data is incomplete.

### Dead code and duplication

knip starts from entry files, applies more than 150 framework plugins, and reports unused files, exports, dependencies, types and enum members, with `ignore` and `ignoreDependencies` for known false positives and a production mode. ts-prune is in maintenance mode and points users to knip. vulture assigns confidence per finding kind: 100 percent for unused arguments and unreachable code, 90 percent for imports, 60 percent for everything else, filtered by `--min-confidence`, with generated whitelists for dynamic usage. Go's deadcode runs Rapid Type Analysis from main entry points and offers `-whylive` to print the shortest call path proving a function is reachable, while warning that reachability does not make deletion safe. jscpd uses Rabin-Karp token hashing across 224 formats and ships SARIF, Code Climate, markdown and "ai" reporters plus `--baseline` with `--fail-on-new-clones`. PMD CPD uses the same algorithm, requires an explicit minimum-token threshold, ignores literals, identifiers and annotations on request, and honours `CPD-OFF`/`CPD-ON` comments. Simian reports duplicate blocks from a default of 6 lines and is now Apache-2.0.

### Self-admitted technical debt and debt trackers

Stepsize let developers file debt issues from the IDE, linked to code, prioritised by impact on velocity, quality or morale, and positioned itself as a triage layer before Jira; it has been acquired by ClickUp and its integrations page now says "coming soon". Its free Jira app was last updated January 2023 with 46 installs. SATDBailiff mines method-level comments, applies a state-of-the-art SATD detector, and tracks each admission through text changes to removal, validated against manually labelled data. Search results also surface MAT, DebtHunter and the FixMe bot, which were not fetched.

### Test-health tools

tsDetect catalogues 19 test smells for JUnit, including Assertion Roulette, Conditional Test Logic, Eager Test, Mystery Guest, Sleepy Test, Ignored Test, Magic Number Test and Unknown Test (no assertion). Develocity marks a test FLAKY when it fails and passes within one task execution under retry, compares outcomes across builds, and ranks "the most severe flaky tests and their trends". Buildkite Test Engine keeps tests in enabled, muted or skipped states, quarantines automatically via workflow monitors, notifies through Slack, webhooks or Linear, and restores tests when reliability recovers. PIT reports mutation coverage next to line coverage and recommends running incrementally on changed code. Stryker defaults to thresholds of 80 (high), 60 (low) and no break, has an incremental mode backed by a JSON file, and offers json and dashboard reporters.

### Google: Jaspan and Green (2023)

Since 2018 Google's quarterly engineering survey asks whether engineers are "hindered by unnecessary complexity and technical debt". Interviews and factor analysis yielded ten mutually exclusive categories, ordered by how often they hindered engineers: migration needed or in progress; documentation on projects and APIs; testing; code quality; dead or abandoned code; code degradation; team lacks expertise; dependencies; migration poorly executed or abandoned; release process. Surveys are lagging indicators, so the authors tested 117 log-derived metrics for three debt types (degradation, expertise, migrations). Linear regression explained under 1 percent of variance; random forests reached over 80 percent precision but only 10 to 25 percent recall. Their diagnosis: debt is a relation between the present state and a possible better state, which a metric cannot see without a human modeller. Management moved to a debt framework, a four-level maturity model (reactive, proactive, strategic, structural), training, and tooling for indicators such as poor test coverage, stale documentation and deprecated dependencies. The share of engineers reporting hindrance fell, the largest trend shift in five years of the survey.

## 3. Cross-cutting patterns

### Shared pipeline shape

Every tool follows collect, detect, classify, score, gate, present. Collection is either a parser over source (Sonar, Designite, Qlty), a graph over dependencies (Lattix, Arcan, dependency-cruiser), a mining pass over version control (CodeScene, SATDBailiff), or a lookup against an external database (OSV, deps.dev, Snyk). Detection is overwhelmingly rule based with numeric thresholds; only Renovate's Merge Confidence and Snyk's EPSS input use learned models. Classification always attaches a category and a severity per finding. Scoring aggregates to a file, directory or project figure. Gating compares that figure against a threshold, usually on new code only. Presentation is a dashboard plus PR decoration plus machine-readable export (SARIF is the common denominator across Qodana, jscpd and OSV-Scanner).

### Prioritisation models compared

| Tool | Unit of severity | Effort model | Business or usage weighting | Composite | Gate |
|---|---|---|---|---|---|
| SonarQube | Impact severity per software quality (Blocker to Info) | Minutes per issue, summed | None | Debt ratio over 30 min per line, A to E | New-code ratings and thresholds |
| CodeScene | Code Health 1 to 10 per file | Not per issue | Change frequency, coupling, team congestion, author departure | Hotspot rank | Health delta, hotspot decline, goals |
| Qlty / Code Climate | Per-check issue | Minutes for duplication and structure only | None | Debt ratio A to F; log scale per file | Mergeability gates |
| NDepend | Derived from annual interest | Debt and annual interest per issue | Test coverage inside formulas | Breaking point = debt / interest | Since-baseline new issues |
| CAST Highlight | Per code insight | Occurrences times template effort | Business criticality times obsolescence | Advisor segments | Portfolio ranking |
| Qodana | Severity buckets | None | None | Counts | Per-severity thresholds, baseline-relative |
| DeepSource | Critical, Major, Minor plus High, Medium, Low priority | None | First and last seen | Counts | Not fetched |
| Snyk | Impact subscore | Fixability | Reachability, transitive depth, business criticality | Risk Score 0 to 1000 | Policy |
| Renovate | Confidence Low to Very High | None | Adoption, age, pass rate across users | Confidence | Auto-merge policy |
| vulture | Confidence 60 to 100 percent by finding kind | None | None | Filter | `--min-confidence` |
| Develocity / Buildkite | Flaky outcome, severity by frequency | None | Build impact | Trend | Quarantine states |

Two distinct families stand out. Effort-accounting tools (Sonar, Qlty, NDepend, CAST, Kiuwan) price every finding and sum it. Behavioural tools (CodeScene, Snyk, Renovate, Develocity) rank by expected cost of leaving the finding alone, using change frequency, reachability, exploit likelihood or build impact. Google's result that no static metric predicted felt debt argues that the second family is the one closer to what humans call debt.

### Baseline and new-code strategies

Sonar's new-code definition (version, days, date) restricts gates to recent changes. Qodana and ArchUnit persist a snapshot of accepted violations and report only deltas, with the store shrinking as violations disappear. jscpd's `--baseline` and `--fail-on-new-clones` do the same for duplication. NDepend takes the nearest 30-day-old analysis as baseline automatically. CodeScene gates on the direction of change (does this PR make a hotspot worse) rather than absolute level. DeepSource keeps first-seen and last-seen timestamps so age is a sort key.

### Issue lifecycle

The minimal state machine is Open, Accepted (deliberate deferral) and False Positive (detector wrong), each reopenable, with an audit comment and a permission gate (Sonar). Sonargraph adds "convert to task". Buildkite's enabled, muted and skipped states are the test-health analogue, with automatic promotion back to enabled. OSV-Scanner attaches an expiry date and a reason to every suppression, which is the most disciplined form found.

### False-positive control

Three mechanisms recur. Confidence per finding kind (vulture, Renovate, Snyk, Arcan's published precision). Configuration of entry points and dynamic usage so the analyser sees what a human knows (knip plugins, vulture whitelists, Go `-whylive`). In-code suppression with a rule key (`skipcq`, `CPD-OFF`, `sonar-resolve`, `ts-prune-ignore-next`), plus glob-scoped rules so tests and generated code get different bars (CodeScene, DeepSource). Structural tools also self-limit scope: Go deadcode explicitly says unreachable does not mean deletable.

### Integration with human workflow

PR decoration is universal. Sonar frames the gate question by context: "can I release" on main, "can I merge" on a PR. CodeScene reports counts of detected, fixed, ignored and suppressed findings per PR. Renovate and Dependabot pre-package the fix as the finding. Buildkite routes findings to Slack or Linear and auto-recovers. Stepsize's insight was a triage layer that decides what enters the backlog, because a raw dump becomes a "graveyard". Google's insight was to measure hindrance felt by people and to slice it by team, since categories differ by domain.

## 4. Transferable recommendations for an LLM-driven read-only scanner

Each item names its evidence and whether an LLM reading files can approximate it or a real tool is needed.

1. **Adopt a fixed taxonomy with two axes: debt category and software quality.** Use Google's ten categories (they are empirically grounded and mutually exclusive) as the category axis and Sonar's Security, Reliability, Maintainability as the impact axis, each with its own Blocker to Info severity. LLM-approximable; the taxonomy is a prompt schema.

2. **Score each finding with debt and interest separately, then rank by breaking point.** NDepend's two-number model and Snyk's impact-times-likelihood are the clearest. The LLM can estimate fix effort in coarse buckets and estimate interest from change frequency. Effort in minutes summed to a debt ratio (Sonar, Qlty) is not recommended: it requires per-rule calibration the LLM cannot reproduce consistently.

3. **Weight by behaviour, not just structure.** CodeScene's hotspot rank (churn times low health) is the single best-validated prioritiser found (Code Red, 39 codebases). Change frequency, co-change coupling and author concentration come from `git log`, which a read-only skill can run. Needs git, not a parser; the LLM interprets the numbers.

4. **Gate on direction, not level.** Report whether a file is getting worse (CodeScene hotspot decline, Qodana New versus Unchanged, ArchUnit freeze store, jscpd baseline). Store a baseline of accepted findings keyed by file and fingerprint, report deltas, and shrink the store when findings vanish. LLM-approximable with a JSON store; fingerprint stability is the hard part.

5. **Emit a confidence per finding kind and let the reader filter.** vulture's fixed confidence by kind and Renovate's four-level confidence show that honesty about detector reliability is what makes output usable. LLM-approximable and important, since LLM dead-code and duplication judgments are weaker than tool judgments.

6. **Delegate what tools do better and read their output.** Cycles, orphans, unused exports, token-level clones and known vulnerabilities are solved by dependency-cruiser, madge, knip, vulture, jscpd or CPD and OSV-Scanner, most with JSON or SARIF output. Needs real tools; the LLM should invoke them when present and fall back to reading only when absent, flagging the fallback as lower confidence.

7. **Minimal lifecycle: Open, Accepted with reason and expiry, False Positive, Fixed.** Sonar's three states plus OSV-Scanner's `ignoreUntil` and `reason`. Every human decision should be recorded next to the finding so the next scan does not re-raise it. LLM-approximable in a register file.

8. **Scope rules by path.** Different bars for tests, generated code and hot paths (CodeScene glob rules, DeepSource test-file suppression, PMD ignore options). LLM-approximable.

9. **Report per-scan counts of detected, fixed, ignored and suppressed** so reviewers see the delta and the noise budget (CodeScene PR stats). LLM-approximable.

10. **Treat test health as first-class debt.** Google ranks testing third. tsDetect's smell list is readable by an LLM from test source; flakiness and mutation score need CI history or a mutation tool and should be marked "not assessed" rather than guessed.

11. **Track self-admitted debt through history.** SATDBailiff-style tracking of TODO and FIXME comments from introduction to removal is cheap with git blame and gives age, which Google's tooling list also values. Needs git; LLM classifies the comment.

12. **Ask the humans and slice by team.** Google found no metric predicted felt debt. A scanner should include a short survey-derived question set or at least invite the reviewer to tag which categories actually hinder them, and weight future scans accordingly. LLM-approximable; this is the feedback loop Sonar's false-positive marking and DeepSource's vendor feedback implement at product scale.

13. **Output SARIF or a SARIF-shaped JSON** alongside markdown, so results can flow into existing viewers and baselines (Qodana, jscpd, OSV-Scanner). LLM-approximable.
