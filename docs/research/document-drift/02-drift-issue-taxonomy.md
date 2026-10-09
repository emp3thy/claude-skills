# Documentation drift: an evidence-based taxonomy of what gets found and fixed

Research note for the `document-drift` skill. Written 2026-10-09.

## 1. Scope and method

**Question.** When documentation in a repository (README.md and other markdown) stops matching the code, what kinds of mismatch actually get noticed and fixed, how common is each kind, how is each detected, and how is each fixed?

**Sources of evidence.**

1. Published empirical studies that categorise documentation defects, outdated comments, API-doc inconsistencies and README content. Eight papers were read in full text (PDFs extracted locally with pypdf, or arXiv HTML renders); the rest were read at abstract or summary level. The Sources table (section 7) says which.
2. A sample of real fix commits and pull requests on GitHub, gathered two ways:
   - **Popular-repo sweep (core REST API).** For 32 well-known repositories across Go, Rust, Python, JavaScript/TypeScript, Java, C, Ruby, C#, Lua/Vimscript and shell, I pulled the 100 most recent commits touching `README.md` and the 100 most recent commits touching the main docs directory (`gh api repos/O/R/commits?path=...`), then kept commits whose first message line matched a drift vocabulary (`outdated|stale|obsolete|no longer|broken|dead link|fix.*link|remov|renam|wrong|incorrect|mismatch|inconsisten|drift|sync|does not exist|moved`). That produced 544 raw hits (277 unique on README paths) against 2,456 README commits sampled. From those hits I hand-picked 98 commits whose messages indicated a doc-to-code mismatch and read their markdown diffs.
   - **Keyword search (GitHub search API).** `gh search commits "fix outdated README"`, `"remove reference to removed" docs`, and `gh search prs "update docs to match"`, `"outdated README"`. These mostly return small or personal repositories, so I used them only to add 21 diverse recent examples, each of whose diffs I also read.
   - Total diffs read: 119. Of those, 82 are tabulated in section 3; 23 near-duplicate link, badge and install fixes were left out of the table for length but still count in the sweep figures, and 14 were excluded as not actually drift (pure formatting, sponsor removals, empty markdown patches).
3. Tool landscape (link checkers, drift detectors), from web search snippets.

**Honest limits.** This is a sample, not a census. The sweep only sees commits whose *message* uses drift vocabulary; silent fixes bundled into feature commits are invisible to it, which biases the sample toward catch-up fixes and away from same-commit co-changes. The keyword regex is broad (it also catches "remove sponsor", "rename branch"), so the 11% hit rate below is an upper bound on the share of README commits that are drift fixes. Durations between cause and fix are only available when the fix cites the cause; I report three.

**What was unreachable.** The GitHub search endpoint rate-limited parallel calls (secondary limit) so searches ran sequentially and some search queries returned nothing usable. The Aghajani 2019 figure gives per-subcategory counts only as an image; I quote the counts that appear in the text. Reddit and web.archive.org were not attempted. No Playwright or Chrome tools were used.

## 2. What the literature says

### 2.1 Aghajani et al., "Software documentation issues unveiled" (ICSE 2019)

Read in full. The study classified **878 documentation-related artifacts** from mailing lists, Stack Overflow, issues and pull requests into a taxonomy of 162 issue types. The top-level split relevant here is "Information Content (What)", with 485 artifacts, divided into:

- **Correctness (72).** "The type of documentation most frequently impacted by correctness issues was code examples, accounting for 50% of the cases in which we labeled a documentation type, followed by installation guidelines (20%)." Leaves: inappropriate installation instructions, wrong translation, erroneous code examples, wrong code comments, faulty tutorial, violation of best practices in example code.
- **Completeness (268).** "Completeness accounts for 55% of the issues related to the documentation content." Leaves include missing documentation for a new feature/component, missing code behavior clarifications, missing diagrams, missing links, missing installation steps.
- **Up-to-dateness (190).** "A document is outdated when it is not in sync with other parts of a system. Up-to-dateness differs from Correctness and Completeness in that the information was correct and complete before a change was introduced. Up-to-dateness problems account for 39% of issues related to documentation content. In 21% of these cases, the inconsistency appeared to be between a system's behavior and its description in the documentation." Leaves (from Fig. 1): code-doc inconsistency, outdated/obsolete references, missing documentation for a new release, outdated translations, outdated example, outdated version information, outdated license/copyright information, outdated installation instructions, broken link, link to an old version of doc, screenshot does not reflect current GUI, behavior described in documentation but not implemented, code must change to match doc.

Two statements matter for a fixer tool. First, "outdated references (e.g., links to old versions of the system) ... was the most prevalent issue within this category." Second, on direction of fix: "While most of the times is the documentation that does not reflect what is implemented in the code, in other cases it is the code that needs to be updated to match the documentation ... There were also situations in which there was a debate to decide whether the code or the documentation needed adjustment." The paper quotes a user: "the setLeftScale and setRightScale routines mentioned in the doxygen documentation seem not to exist", which is exactly the missing-symbol case a script can prove.

### 2.2 Aghajani et al., "Software documentation: the practitioners' perspective" (ICSE 2020)

Read in full. Two surveys, **146 practitioners**. Figure 2 reports the percentage of practitioners who rated each issue as important; the up-to-dateness rows (reported by the paper) are:

| Up-to-dateness issue | % rating it important |
|---|---|
| Missing documentation for a new feature/component | 69% |
| Code-documentation inconsistency | 59% |
| Outdated installation instructions | 54% |
| Missing documentation for a new release | 53% |
| Outdated example | 51% |
| Outdated version information | 32% |
| Outdated screenshot | 29% |
| Outdated license/copyright information | 26% |
| Outdated translation | 19% |

The paper also reports "Outdated/Obsolete references" at 64% and "Wrong code comments" at 49% in the maintainability and correctness rows, and says: "Inconsistency between code and documentation was also perceived as an important issue by practitioners (59% of them) and is one of the top recurring issues they face." The authors note a practitioner's mitigation that is directly relevant to a fixer: "limit code comments to the minimum needed, so it is simpler to co-evolve them with code (i.e., if a comment documents useless details, it is more likely that changes implemented in the code will impact it)."

### 2.3 Wen, Nagy, Bavota, Lanza, "A large-scale empirical study on code-comment inconsistencies" (ICPC 2019)

Read in full. Change history of **1,500 Java projects, 3,323,198 commits**. Reported findings:

- "between 13% and 20% of code changes trigger comment updates" (13% for class comments, 20% for method comments when the whole code entity changes).
- Rename, literal and method-invocation changes are the categories most likely to trigger comment updates; many other change types rarely do.
- From a manual analysis of **500 commits** (362 true comment-related), the taxonomy has six roots: Application Logic (136), Code Design/Quality (80), Formatting/Readability (63), Maintenance (17), Copyright/License, Others. "Updated comments following refactorings were also frequent (14), particularly after renamed methods/variables (11)". Technical-debt (TODO) comments were the largest single group (54), often deleted when the debt was paid; the authors found cases where "developers fixed the technical debt issue but left the comment by mistake", requiring a later commit such as "Remove forgotten outdated comment".
- A lag example: in Apache Cordova Android the class hierarchy was refactored in 2012 but "its Javadoc comment has only been updated one year later, in 2013".
- A prevention pattern: Apache Groovy replaced a hard-coded list of supported JDK versions with a reference to a constant, "to also avoid uptodateness issues in the future".

### 2.4 Fluri, Wursch, Gall, "Do code and comments co-evolve?" (WCRE 2007) and the 2009 Software Quality Journal extension

Snippet level only. The 2007 study (ArgoUML, Azureus, JDT Core) reported that "97% of comment changes are done in the same revision as the associated source code change" and that "newly added code barely gets commented". The 2009 extension over eight systems reported that "in six out of the eight systems, code and comments co-evolve in 90 percent of the cases" and that "API changes and comments do not co-evolve but they are re-documented in a later revision." The last clause is the drift case: API changes are the ones whose documentation lags.

### 2.5 Zhou et al., "Analyzing APIs documentation and code to detect directive defects" (ICSE 2017)

Abstract level. On JDK 1.8, "out of around 2000 API usage constraints, our approach can detect 1158 defective document directives, with a precision rate of 81.6%, and a recall rate of 82.0%." The directives are parameter constraints and exception declarations, which is a narrower, mechanically checkable form of doc-code inconsistency than README prose.

### 2.6 Uddin and Robillard, "How API documentation fails" (IEEE Software 2015)

Read in full. Two surveys totalling 323 developers and 179 documentation units. Table 2 counts examples (E) and developers (D) per problem: Incompleteness 20/20, Ambiguity 16/15, Unexplained examples 10/8, **Obsoleteness ("The documentation on a topic referred to a previous version of the API") 6/6**, Inconsistency 5/4, Incorrectness 4/4; presentation problems Bloat 12/11, Fragmentation 5/5, Excess structural information 4/3, Tangled information 4/3. "Respondents ranked six problems as Blocker at least once: incompleteness, ambiguity, obsoleteness, incorrectness, inconsistency, and unexplained examples." So obsoleteness is not the most frequent complaint, but it is a blocker when it happens.

### 2.7 Khan et al., "Automatic detection of five API documentation smells" (SANER 2021)

Read via arXiv HTML. The five smells are Bloated, Excess Structural Info, Tangled, Fragmented and Lazy. On a 1,000-unit benchmark, "778 units (78%) contain at least one smell"; Lazy 275 (27.5%) was most frequent, Bloated 141 (14.1%) least. 95.2% of 21 surveyed developers said smells hurt productivity. These are presentation smells, not drift, but "Lazy" (a description that restates the signature) is relevant: such prose is the easiest to regenerate and the least worth protecting from an automated rewrite.

### 2.8 Prana et al., "Categorizing the content of GitHub README files" (EMSE 2018)

Read via arXiv HTML. **4,226 sections from 393 READMEs.** Table 3:

| Category | % of sections | % of files containing it |
|---|---|---|
| What | 16.7% | 97.0% |
| Why | 2.7% | 25.7% |
| How | 58.4% | 88.5% |
| When | 4.3% | 21.4% |
| Who | 7.6% | 52.9% |
| References | 20.3% | 60.8% |
| Contribution | 2.9% | 27.8% |
| Other | 1.4% | 6.9% |

"How" (getting started, installation, configuration, requirements, dependencies, demo, errors and bugs, how to run) is 58% of all sections. The paper has no formal How subcategories; those are example headings from its coding reference.

### 2.9 Studies of README change over time

- **Adapting Installation Instructions in Rapidly Evolving Software Ecosystems** (arXiv 2312.03250, IEEE TSE 2025). Read via arXiv HTML. 400 repositories, 1,163 README commits touching installation sections. Table II (1,168 data points, multi-label): Pre-installation 628 (54.0%, of which Dependency Setup 527 / 45.3%, Platform Setup 82 / 7.1%); Installation-related 429 (36.9%; Source code 267 / 23.0%, Published package 162 / 13.9%); Document presentation 477 (41.0%); External resources management 366 (31.5%; project external documentation 120, project non-documentation artefact 136, third-party external resources 110); Help information 265 (22.8%); Post-installation 248 (21.3%). Trigger counts in the readable part of the results: Update of software version 131, Add or modify software functionality 83, Incomplete documentation in previous README 78, Command or file path updates 76, Update of software dependencies 52, Self-motivated improvement 50, Instruction or content issues in previous README 48, Request by downstream users 13, Outdated elements in previous README 12. The paper notes that errors in URLs are "less apparent and more severe" than errors in commands, which fail visibly.
- **Does My README File Need To Be Updated? Exploring LLM-Based README Maintenance** (arXiv 2603.00489). Read via arXiv HTML. 25,511 PRs from 714 repositories; "only 0.8% of all PRs in the dataset involving modifications to the README file." The best LLM configuration "recovers half of the pull requests historically accompanied by README updates" at "28% user-facing accuracy under the observed prevalence." In a retrospective over 20 repositories, "21.5% of temporally matched recommendations identify updates overlooked by developers (15.34% delayed fixes and 6.13% valid but ignored)". Failure analysis of 200 false recommendations: Semantically Irrelevant Noise 40 to 44% (cosmetic doc changes, tangled PRs), Context and Information Deficit 32 to 34% (vague PR descriptions, project-specific knowledge gaps), Document Structural Ambiguity 23 to 24% (several plausible insertion points; the model named a section rather than a paragraph). The JabRef maintainer interviewed said: "If your output has line numbers and the reasons, then it is a no-brainer" and "I would expect two-thirds to three-quarters to be OK, and the rest being rubbish."
- **npm README study** (arXiv 1802.08391, snippet): across 119,093 npm packages "a README was updated up to 7 times" on average.
- **IPSJ 2021 early README evolution** (snippet): "on average 3.6% of commits include the modification of README files".

### 2.10 Link rot

- Hata, Treude, Kula, Ishio, "9.6 Million Links in Source Code Comments" (ICSE 2019), summary page read: "Almost 10% of links are dead overall", "links are rarely updated after they're committed" while "many link targets evolve"; the authors submitted link-fixing pull requests "resulting in most of our fixes being merged successfully."
- Xiao et al. (EMSE 2023, snippet): of 18.2 million links in commit messages, "14% of links that are prone to evolve become unavailable over time" and "70% of the distinct links suffer from decay".

### 2.11 Stale symbol references in comments

"We Must Have Missed This Comment: Detecting and Repairing Stale Function References in Linux Kernel Comments" (arXiv 2608.03734, abstract read). ReCite finds comment references to functions that no longer exist, traces each symbol's git history, and uses an LLM to propose a repair. On Linux v6.18-rc1 it found "869 stale references"; of 200 sampled repairs "178 (89.0%) provide useful repair guidance" and "85 (42.5%) directly applicable"; "Of our 75 submitted patches, 50 have been accepted." This is the closest published analogue to the mechanical part of `document-drift`: resolve every code-like token in a doc against the current tree, and use history to explain what replaced it.

## 3. Sampled fixes

### 3.1 Sweep-level numbers (from my sample)

- 31 repositories had a README commit history available; 2,456 README commits were sampled (up to 100 per repo). **277 (11.3%) matched the drift vocabulary.** From reading about 60 of these, I estimate roughly three quarters are genuine doc-to-code or doc-to-world fixes, the rest being sponsor, emoji or formatting removals. So on the order of **8% of README commits in mature projects are drift fixes**, as an upper-bound estimate from my sample.
- Of the 277 README hits: **126 (45%) mention a link, badge, URL, anchor, logo or image; 117 (42%) are removals of something obsolete, outdated, dead or no longer existing; 29 (10%) are renames; only 2 use "wrong" or "incorrect".** People do not usually write "wrong" in a drift-fix message; they write "remove" or "fix link".
- Per-repo README hits over the window: express 19, vite 18, neovim 15, kubernetes 15, ohmyzsh 13, terraform 13, hugo 13, black 12, deno 12, ripgrep 12, rails 10, junit5 10, compose 10. The older and more widely linked the README, the more link and badge churn it accumulates.
- **Lag where the fix cites the cause:** giantswarm/kong-app renamed `helm/kong-app/crds` to `files` on 2025-06-25 and the README path was fixed on 2026-10-08 (15.5 months). vitest implemented `page.mark()` callback grouping on 2026-06-04 and the guide sentence saying it was unsupported was fixed on 2026-10-05 (4 months). Black dropped Python 3.7 on 2023-07-05 and the README's "requires Python 3.7+" was bumped on 2023-09-18 (2.5 months).
- **Same-commit co-change vs catch-up.** 14 of the 82 tabulated fixes (17%) updated the doc in the same commit or PR as the code change (flag renames in bat, prettier, git, helix, compose, ohmyzsh; config renames in rubocop; directory and script renames in neovim, deno; the `rails` to `bin/rails` and `reset` to `preflight` sweeps). The other 83% are catch-up fixes landing after the fact.

### 3.2 The sampled-fix table

Category IDs refer to the taxonomy in section 4. "Fix" is what the diff did. Rows R1 to R21 come from keyword search; R22 onwards from the popular-repo sweep.

| # | Repo and link | Drift category | What changed in the code or world | Fix |
|---|---|---|---|---|
| R1 | [wagtail/eslint-config-wagtail e950a54](https://github.com/wagtail/eslint-config-wagtail/commit/e950a54588baceab0a1aa78399616204d9e0098a) | DD-12 enumeration | ESLint 9 migration swapped plugin set | rewrite dependency list |
| R2 | [dherault/serverless-offline 1200252](https://github.com/dherault/serverless-offline/commit/12002524ef54dc18e4c3004a505de4f71c9b8e6a) | DD-10 behaviour claim | reload and lifecycle behaviour changed | rewrite option descriptions, add sections |
| R3 | [darkleaf/di 00f058d](https://github.com/darkleaf/di/commit/00f058de5abda1d9f179e753fa511d08974e5762) | DD-06 missing symbol | `di/instrument` removed | delete mention |
| R4 | [upsertco/perch 42b17df](https://github.com/upsertco/perch/commit/42b17dfcff243a45e0964502e941cfbcdaea34b7) | DD-11 architecture | inline diff overlay removed | rewrite CLAUDE.md module map, keybinding list, event loop |
| R6 | [microsoft/agent-framework 1e527a3](https://github.com/microsoft/agent-framework/commit/1e527a328cff67445035fbc77978991d88c1be1d) | DD-05 config option | `scope_to_per_operation_thread_id`, `thread_id` unsupported | rewrite scoping section |
| R7 | [giantswarm/kong-app #552](https://github.com/giantswarm/kong-app/pull/552) | DD-02 renamed path | `crds/` renamed `files/` 15 months earlier | update path and link |
| R8 | [wow-look-at-my/go-toolchain #577](https://github.com/wow-look-at-my/go-toolchain/pull/577) | DD-04 removed flag | `--log-level` removed | delete table row, same PR |
| R9 | [vitest-dev/vitest #11484](https://github.com/vitest-dev/vitest/pull/11484) | DD-10 behaviour claim | grouping implemented 4 months earlier | rewrite one sentence |
| R10 | [infiniflow/ragflow #20663](https://github.com/infiniflow/ragflow/pull/20663) | DD-11 architecture | "Go-native service architecture" no longer accurate | delete section in all translated READMEs |
| R11 | [bropedio/brave-new-world c39c0a2](https://github.com/bropedio/brave-new-world/commit/c39c0a24f03018beb795c1838bc2c1301039e902) | DD-08 build step | assembler `xkas` replaced by `asar` | replace token |
| R12 | [markvilar/viper 2d47815](https://github.com/markvilar/viper/commit/2d47815d66b834c800dbf03f499e2d2d8c8312af) | DD-07 example | attribute renamed, decorator gained kwarg | edit snippet |
| R13 | [copona/copona 2042782](https://github.com/copona/copona/commit/2042782db40e07247e608fb44d20e3f5513da02e) | DD-08 install | installer flow and `docker compose` v2 | rewrite steps |
| R14 | [hongseongug812-ui/llm-bench-dashboard 3c18cdc](https://github.com/hongseongug812-ui/llm-bench-dashboard/commit/3c18cdc901409f6f896e300aedd8e3174cd4cfbe) | DD-10 feature claim | automatic PDF generation removed | rewrite bullet |
| R15 | [plainenglishh/luausdr 0d0e8fc](https://github.com/plainenglishh/luausdr/commit/0d0e8fc04de047debb3ce7e89f2298c19436cb45) | DD-07 example | sink callback signature changed | rewrite snippet |
| R16 | [quantmew/ripperdoc 190f49e](https://github.com/quantmew/ripperdoc/commit/190f49eb654989ea062af35bd2b4fda86c976d33) | DD-12 enumeration | slash commands added, built-in skills removed | add and delete list items |
| R17 | [SunsetFi/suntime-js 3d4e6ef](https://github.com/SunsetFi/suntime-js/commit/3d4e6efc305015316a14b1b1095e83bb3736a28c) | DD-02 deleted page | `02-detailed-walkthrough.md` deleted | delete or retarget links |
| R18 | [polyipseity/information 1ce8763](https://github.com/polyipseity/information/commit/1ce87639c109d0a36f2869bb0a19996fcc8440ca) | DD-12 enumeration | 7 submodules removed | delete paths from lists |
| R19 | [visionme-studio/visionme-stellar #146](https://github.com/visionme-studio/visionme-stellar/pull/146) | DD-08 install (also DD-17) | placeholder clone URL, wrong package manager, nonexistent dirs, missing LICENSE | rewrite Getting Started |
| R20 | [zed-industries/zed b3dd515](https://github.com/zed-industries/zed/commit/b3dd51560bb00cd90a2a56dd29f79e9c7b3c1cda) | DD-01 external URL | pages moved (found by lychee) | retarget URLs |
| R21 | [foxlabo/tsumugi 5d8f568](https://github.com/foxlabo/tsumugi/commit/5d8f5688ae077b9c2b882f37c801a122e9829825) | DD-10 behaviour claim | provider and network behaviour changed | rewrite privacy section, fix link |
| R22 | [cli/cli 123f469](https://github.com/cli/cli/commit/123f469e58) | DD-02 link path | `/docs/...` absolute links did not resolve | change to `./docs/...` |
| R23 | [cli/cli 9d11ced](https://github.com/cli/cli/commit/9d11cedd18) | DD-02 branch in URL | default branch renamed master to trunk | replace in URLs |
| R24 | [cli/cli 6dae307](https://github.com/cli/cli/commit/6dae3077b8) | DD-08 install command | escaped pipe `\|` in curl command | fix command, fix link |
| R26 | [hashicorp/terraform f261fa6](https://github.com/hashicorp/terraform/commit/f261fa62a9) | DD-08 build setup | Vagrantfile removed | delete Vagrant paragraphs |
| R27 | [hashicorp/terraform 0673fe3](https://github.com/hashicorp/terraform/commit/0673fe3273) | DD-08 build command | `make updatedeps` target removed | delete command |
| R28 | [hashicorp/terraform a0a1cbc](https://github.com/hashicorp/terraform/commit/a0a1cbc819) | DD-08 prerequisites | cgo and CMake no longer needed | delete prerequisites |
| R29 | [hashicorp/terraform bb9d9dc](https://github.com/hashicorp/terraform/commit/bb9d9dcd3d) | DD-17 incorrect at birth | "Mac OS X Linux" wording | edit words |
| R30 | [hashicorp/terraform f521ba6](https://github.com/hashicorp/terraform/commit/f521ba6cd7) | DD-11 architecture | "enhanced backend" distinction dropped | rewrite architecture.md section |
| R31 | [hashicorp/terraform 1c1eef0](https://github.com/hashicorp/terraform/commit/1c1eef0e0b) | DD-03 badge | FOSSA badge broken | replace with license link |
| R32 | [gohugoio/hugo f914774](https://github.com/gohugoio/hugo/commit/f914774f6b) | DD-03 badge | Bitdeli service dead | delete badge |
| R33 | [BurntSushi/ripgrep 049354b](https://github.com/BurntSushi/ripgrep/commit/049354b766) | DD-08 install | Fedora 24 copr EOL | delete block |
| R37 | [BurntSushi/ripgrep c78c323](https://github.com/BurntSushi/ripgrep/commit/c78c3236a8) | DD-10 capability claim | "no SIMD" statement obsolete | delete clause |
| R40 | [sharkdp/bat 83b00bc](https://github.com/sharkdp/bat/commit/83b00bc653) | DD-04 flag rename | `--squeeze` to `--squeeze-blank` | update help-text docs, same commit |
| R42 | [astral-sh/uv 07d3e50](https://github.com/astral-sh/uv/commit/07d3e5085a) | DD-02 anchors | headings renamed (`#project` to `#projects`), `.md` suffix in site URLs | fix anchors |
| R43 | [astral-sh/uv 9e2e9f2](https://github.com/astral-sh/uv/commit/9e2e9f2d10) | DD-07 example | `pypy@3.11` pin example dropped | simplify example |
| R45 | [pallets/flask be6ec06](https://github.com/pallets/flask/commit/be6ec06894) | DD-01 external URL | Hypercorn moved GitLab to GitHub | retarget |
| R48 | [psf/black 2e641d1](https://github.com/psf/black/commit/2e641d1744) | DD-01 external service | Black Playground gone | delete references, rewrite template |
| R49 | [psf/black e974fc3](https://github.com/psf/black/commit/e974fc3c52) | DD-09 version string | 3.7 dropped 2.5 months earlier | bump "3.7+" to "3.8+" |
| R50 | [psf/black 2189bca](https://github.com/psf/black/commit/2189bcaac0) | DD-09 version string | 3.6 dropped | bump |
| R52 | [psf/black 6384eeb](https://github.com/psf/black/commit/6384eeb0b4) | DD-09 version string | wrong release number in FAQ | edit "25.2.0" to "25.9.0" |
| R55 | [pydantic/pydantic 51d2b27](https://github.com/pydantic/pydantic/commit/51d2b27aa9) | DD-07 example | examples no longer raised; error code unused | fix examples, delete section |
| R58 | [astral-sh/ruff 694334c](https://github.com/astral-sh/ruff/commit/694334c51c) | DD-08 install channel | Alpine package moved testing to community | retarget link and wording |
| R59 | [vitejs/vite 36a24aa](https://github.com/vitejs/vite/commit/36a24aa0df) | DD-10 behaviour claim | `web_modules` support removed | rewrite paragraph |
| R60 | [vitejs/vite f452cf3](https://github.com/vitejs/vite/commit/f452cf3761) | DD-05 config key | `plugins` renamed `configureServer` | replace key in example |
| R61 | [vitejs/vite 40a3999](https://github.com/vitejs/vite/commit/40a3999e66) | DD-06 missing symbol | `RemoteEnvironmentTransport` export does not exist | delete import |
| R64 | [prettier/prettier 1c806f8](https://github.com/prettier/prettier/commit/1c806f81b2) | DD-04 flag rename | `--resolve-config` to `--find-config-path` | replace, same commit |
| R65 | [prettier/prettier ad223ed](https://github.com/prettier/prettier/commit/ad223eda4a) | DD-05 config option | `options.editorconfig` does not exist | rewrite sentence |
| R66 | [prettier/prettier e9045d0](https://github.com/prettier/prettier/commit/e9045d0fcc) | DD-10 external standard | TC39 decided decorator placement | delete paragraph |
| R68 | [expressjs/express 0513655](https://github.com/expressjs/express/commit/05136550c7) | DD-02 repo move | repository moved orgs | fix links |
| R70 | [expressjs/express cb4c56e](https://github.com/expressjs/express/commit/cb4c56e9a7) | DD-13 people list | role change | move entry |
| R71 | [eslint/eslint 305d5b9](https://github.com/eslint/eslint/commit/305d5b91ae) | DD-12 enumeration | rules deprecated | delete `related_rules` entries |
| R73 | [eslint/eslint 80259a9](https://github.com/eslint/eslint/commit/80259a9b0d) | DD-14 whole document | eslintrc config system removed | delete files |
| R74 | [junit-team/junit5 032f09e](https://github.com/junit-team/junit5/commit/032f09e151) | DD-16 naming | project no longer "JUnit 5" | replace name |
| R75 | [curl/curl 87c5b26](https://github.com/curl/curl/commit/87c5b26a0a) | DD-15 status tracker | SMB removed in 8.23.0 | move DEPRECATE.md entry to "removed" |
| R76 | [curl/curl ccecc61](https://github.com/curl/curl/commit/ccecc619a5) | DD-15 status tracker | bug no longer happens | delete KNOWN_BUGS entry |
| R77 | [curl/curl 1760258](https://github.com/curl/curl/commit/1760258b16) | DD-01 external URLs (also DD-03) | binding sites moved, Codacy dropped | retarget, delete badge, delete ECH.md |
| R78 | [git/git 4ebec19](https://github.com/git/git/commit/4ebec19711) | DD-04 flag rename | `--show-ref-format` renamed | update, add deprecated alias, same commit |
| R79 | [rails/rails 410c493](https://github.com/rails/rails/commit/410c4930fe) | DD-10 behaviour claim | `reorder` semantics described wrongly | rewrite two sentences |
| R81 | [rails/rails da10062](https://github.com/rails/rails/commit/da10062b87) | DD-05 config key | wrong option name for CheckPending | fix name, add section |
| R82 | [rails/rails e5feb13](https://github.com/rails/rails/commit/e5feb13674) | DD-17 incorrect at birth | "purge jobs" for destroy queue | edit word |
| R83 | [rails/rails fe8a6b2](https://github.com/rails/rails/commit/fe8a6b264e) | DD-02 anchor | section does not exist | delete link |
| R84 | [rails/rails db1ae8c](https://github.com/rails/rails/commit/db1ae8cbb4) | DD-04 command | global `rails` to `bin/rails` | replace across tree |
| R85 | [rubocop/rubocop 3896eb6](https://github.com/rubocop/rubocop/commit/3896eb6f76) | DD-05 config keys | parameters renamed | update cop docs, same commit |
| R87 | [dotnet/runtime 6103855](https://github.com/dotnet/runtime/commit/6103855840) | DD-04 CLI argument | createdump PID argument removed | rewrite usage paragraph, same commit |
| R93 | [neovim/neovim b0f9228](https://github.com/neovim/neovim/commit/b0f9228179) | DD-10 tooling claim | scan-build dropped | delete section |
| R94 | [neovim/neovim f05a289](https://github.com/neovim/neovim/commit/f05a2891d3) | DD-02 path | build dirs renamed | update paths, same commit |
| R96 | [helix-editor/helix 030e7ab](https://github.com/helix-editor/helix/commit/030e7ab988) | DD-06 file name | `indents.toml` became `indents.scm` | replace, delete stale note |
| R97 | [helix-editor/helix 7044d7d](https://github.com/helix-editor/helix/commit/7044d7d804) | DD-04 flag rename | `--fetch-grammars` to `--grammar fetch` | replace, same commit |
| R98 | [helix-editor/helix 0eba0db](https://github.com/helix-editor/helix/commit/0eba0db4a0) | DD-08 install command | SymbolicLink does not work, Junction does | edit command, add note |
| R100 | [docker/compose 009a239](https://github.com/docker/compose/commit/009a239510) | DD-04 alias | `convert` alias removed | delete aliases block, same commit |
| R103 | [denoland/deno a2064ca](https://github.com/denoland/deno/commit/a2064ca89c) | DD-11 architecture | Go runtime removed | rewrite description |
| R104 | [denoland/deno db65c72](https://github.com/denoland/deno/commit/db65c723ae) | DD-08 script name | `run_hooks.py` renamed `setup.py` | replace, same commit |
| R105 | [zed-industries/zed 7f00507](https://github.com/zed-industries/zed/commit/7f00507e01) | DD-05 defaults | defaults changed (`auto_indent` enum) | rewrite entries |
| R106 | [zed-industries/zed ba7da93](https://github.com/zed-industries/zed/commit/ba7da93e5c) | DD-05 config keys | settings removed or renamed | delete and rename entries |
| R107 | [zed-industries/zed ca90b85](https://github.com/zed-industries/zed/commit/ca90b8555d) | DD-14 whole document | local collaboration feature removed | delete page and its links |
| R108 | [kubernetes/kubernetes 2bbd07c](https://github.com/kubernetes/kubernetes/commit/2bbd07c019) | DD-01 external URL | interactive tutorial defunct | delete sentence and reference |
| R110 | [rust-lang/cargo 1ba5fc5](https://github.com/rust-lang/cargo/commit/1ba5fc5daa) | DD-17 incorrect at birth | feature name mis-documented | replace identifier |
| R111 | [rust-lang/cargo 3b0f31e](https://github.com/rust-lang/cargo/commit/3b0f31e2d7) | DD-08 prerequisites | cmake no longer required | delete bullet |
| R112 | [ohmyzsh/ohmyzsh 85c4941](https://github.com/ohmyzsh/ohmyzsh/commit/85c4941492) | DD-04 removed flag | `--unattended` removed | add migration note, same commit |
| R113 | [ohmyzsh/ohmyzsh b2f35a7](https://github.com/ohmyzsh/ohmyzsh/commit/b2f35a7b98) | DD-16 naming | plugin `osx` renamed `macos` | replace, same commit |
| R114 | [tailwindlabs/tailwindcss e73c247](https://github.com/tailwindlabs/tailwindcss/commit/e73c2472fd) | DD-03 badge | branch `next` to `main` | fix badge URL |
| R115 | [tailwindlabs/tailwindcss 2b1a695](https://github.com/tailwindlabs/tailwindcss/commit/2b1a6959d3) | DD-16 naming | `@tailwind reset` renamed `preflight` | replace, same commit |

### 3.3 Counts per category (from my sample of 82)

| Category | Count | Share |
|---|---|---|
| DD-08 Install, build, setup steps stale | 12 | 15% |
| DD-10 Feature, behaviour or capability claim stale | 9 | 11% |
| DD-04 CLI flag, command, alias removed or renamed | 9 | 11% |
| DD-02 Broken intra-repo link, anchor or path | 8 | 10% |
| DD-05 Config key, option, default removed, renamed or wrong | 7 | 9% |
| DD-01 Dead or moved external URL | 5 | 6% |
| DD-12 Enumeration out of sync | 4 | 5% |
| DD-07 Code example wrong | 4 | 5% |
| DD-11 Architecture prose stale | 4 | 5% |
| DD-03 Stale badge or service widget | 3 | 4% |
| DD-06 Code identifier no longer exists | 3 | 4% |
| DD-09 Version or platform string stale | 3 | 4% |
| DD-16 Naming and terminology drift | 3 | 4% |
| DD-17 Incorrect at birth | 3 | 4% |
| DD-14 Whole document obsolete | 2 | 2% |
| DD-15 Status-tracker doc stale | 2 | 2% |
| DD-13 People or sponsor list stale | 1 | 1% |
| DD-18 Doc right, code wrong | 0 | 0% |

Caveat: DD-01 and DD-03 are under-represented in this table because I left out near-identical "fix link" and "remove badge" commits; in the raw sweep, link, badge and image fixes were 45% of all README hits. DD-08 is over-represented relative to a random README commit because install sections are where mature projects accumulate per-distro blocks that each rot independently (ripgrep's README had five such per-distro deletions in the sweep, two of which are tabulated).

## 4. Consolidated taxonomy

Detectability: **mechanical** (a script proves the doc wrong against the tree, the git history or an HTTP response), **assisted** (a script finds candidates; a reader confirms), **comprehension** (needs reading the code and the prose). Fixability: **mechanical** (deterministic edit), **LLM-rewrite** (needs a new sentence or paragraph, reviewable), **flag-only** (the doc might be right and the code wrong, or the fix is a product decision). Prevalence combines the literature, the sweep and the sample, with the basis stated.

| ID | Name | Description | Example | Prevalence (basis) | Detect | Fix | Cheapest reliable signal |
|---|---|---|---|---|---|---|---|
| DD-01 | Dead or moved external URL | Link to a site, page, package index or service that 404s, redirects elsewhere or no longer exists | Hypercorn moved GitLab to GitHub (R45); Black Playground gone (R48) | High. ~10% of links in code comments dead (Hata 2019); 14% of evolving links in commits go unavailable (Xiao 2023); 45% of README drift hits in my sweep mention a link, badge or image | mechanical | mechanical for redirect-following and removal; LLM-rewrite when the referenced thing no longer exists at all | HTTP status and final redirect URL (lychee); treat 3xx-to-different-path as "moved", 404 as "dead" |
| DD-02 | Broken intra-repo link, anchor or path | Relative link, heading anchor or path literal that no longer resolves in the tree; default-branch names baked into URLs | `crds/` renamed `files/` unnoticed 15 months (R7); `#project` to `#projects` (R42); master to trunk (R23) | High. "Command or file path updates" was a top-three trigger (76 of 614) in the installation study; 10% of my sample | mechanical | mechanical when `git log --follow` or a unique rename candidate exists; LLM-rewrite when the target was deleted | Resolve every relative link, anchor and backticked path against the tree; for misses, search git history for the rename |
| DD-03 | Stale badge or third-party service widget | CI, coverage, chat, analytics or sponsor badge whose service was dropped or shut down | Bitdeli (R32), Codecov (R92), FOSSA (R31), branch `next` in badge URL (R114) | Medium. 27 of 277 README hits in my sweep name a CI or badge service | mechanical | mechanical (delete) once the badge image URL 404s or the referenced workflow or branch no longer exists | Fetch badge image; cross-check workflow and branch names against `.github/workflows` and `git branch` |
| DD-04 | CLI flag, command, subcommand or alias removed or renamed | Doc shows an option the parser no longer accepts, or the old spelling | `--squeeze` to `--squeeze-blank` (R40); `--py36` removed (R51); `convert` alias removed (R100) | High in CLI projects. 11% of my sample; the most common same-commit co-change | mechanical when flags are extractable (help text, argparse/clap/cobra definitions, man pages) | mechanical for rename (old to new) and removal (delete row or line); LLM-rewrite when semantics changed | Diff doc-quoted `--flags` and subcommands against `--help` output or the parser source |
| DD-05 | Config key, option, env var or default removed, renamed or wrong | Settings reference lists keys that no longer exist, old names, or wrong defaults | Zed settings reference (R105, R106); `options.editorconfig` (R65); wrong config name (R81) | Medium-high. 9% of my sample; practitioners rate code-doc inconsistency 59% important (Aghajani 2020) | mechanical for key existence when a schema, default config or struct exists; assisted for defaults | mechanical for rename and delete; LLM-rewrite for changed semantics or defaults | Extract backticked `snake_case` and `dotted.keys` from docs, resolve against config schema, struct fields or `default.yml` |
| DD-06 | Code identifier referenced in prose no longer exists | Function, class, module, file or dependency named in prose or an import line that is gone | `di/instrument` (R3); `RemoteEnvironmentTransport` import (R61); `indents.toml` (R96) | Medium. The ReCite study found 869 such references in one kernel snapshot; "documented code that does not exist in the system anymore" is called out in Aghajani 2019 | mechanical (grep or symbol index) | mechanical when history shows a unique rename; LLM-rewrite when removed; flag when ambiguous | Tokenise backticked identifiers, resolve with ctags, LSP or `rg -w`; on miss, `git log -S` to find the replacing name |
| DD-07 | Code example or snippet wrong | Example no longer compiles, runs, or prints what the doc says | Decorator gained required kwarg (R12); callback signature changed (R15); example did not raise (R55) | Medium. Code examples are 50% of correctness issues (Aghajani 2019); "erroneous code examples" rated important by 59% (Aghajani 2020) | assisted (compile, doctest, type-check the fenced block) | LLM-rewrite, verified by re-running the example | Extract fenced blocks, run them in a sandbox or at least compile and type-check; compare printed output comments |
| DD-08 | Install, build or setup steps stale | Commands, prerequisites, package channels, distro blocks or scripts that no longer apply | Fedora copr EOL (R33); `make updatedeps` gone (R27); cmake not required (R111); wrong PowerShell cmdlet (R98) | Highest in READMEs. Pre-installation changes were 54% and installation 37% of README install commits (installation study); "outdated installation instructions" rated important by 54% (Aghajani 2020); 15% of my sample | assisted; mechanical only for script names, make targets and referenced files | mechanical for removed targets and files; LLM-rewrite for changed procedures; flag when the change is a platform-support decision | Resolve every script path, make target, package name and CLI command in the install section against the tree, Makefile, package manifest and `--help` |
| DD-09 | Version or platform-support string stale | Minimum runtime version, release number or supported-platform list lags the manifest | "Python 3.7+" 2.5 months after 3.7 was dropped (R49); wrong release number in FAQ (R52) | Medium. "Update of software version" was the single largest trigger (131 of 614) in the installation study; "outdated version information" rated important by 32% | mechanical | mechanical (copy from manifest: `requires-python`, `engines`, `rust-version`, `go` directive) | Compare doc version strings with the single source of truth in the package manifest |
| DD-10 | Feature, behaviour or capability claim stale | Prose asserts something is supported, unsupported, default, or works a certain way, and the code moved on | "grouping is not currently supported" 4 months after it shipped (R9); `web_modules` support removed (R59); "no SIMD" (R37) | High. Up-to-dateness is 39% of content issues and 21% of those are behaviour vs description (Aghajani 2019); 11% of my sample | comprehension; assisted when the claim names a flag, option or file | LLM-rewrite with the citing commit as evidence; flag when the claim is about intent or roadmap | Cross-reference every sentence containing "supports", "does not", "currently", "not yet", "by default" with the symbols it names; stale negations ("not supported") are the best hunting ground |
| DD-11 | Architecture or how-it-works prose stale | Module maps, data-flow descriptions, component lists that no longer match the tree | perch CLAUDE.md module map (R4); Terraform backend architecture (R30); Deno "Go removal" (R103) | Medium-low in count but high in cost. 5% of my sample; Aghajani 2020 practitioners called for generated diagrams | assisted (module map vs directory tree; named components vs packages) and comprehension for the narrative | LLM-rewrite for the structural parts (directory trees, component tables); flag-only for rationale and design intent | Diff any directory tree or component table in the doc against `ls` and the package graph; flag narrative paragraphs that name a missing component |
| DD-12 | Enumeration out of sync | Lists of commands, plugins, rules, aliases, submodules or layout entries missing new items or keeping removed ones | Slash-command list (R16); 7 removed submodules (R18); deprecated `related_rules` (R71) | Medium. 5% of my sample; practitioners rate "missing documentation for a new feature" the most important up-to-dateness issue (69%) | mechanical when the list has a code counterpart (registry, directory, enum) | mechanical for removals; LLM-rewrite for additions (needs a description) | Pair each list with its generator (directory listing, registry, enum) and diff the sets |
| DD-13 | People, sponsors or team lists stale | Maintainer, triager or sponsor lists out of date | express triagers (R70) | Low in drift terms (19 of 277 README hits mention sponsors, users or team) | assisted (compare with CODEOWNERS, MAINTAINERS, org API) | flag-only; these are social, not technical, decisions | Compare with CODEOWNERS or MAINTAINERS files only; never auto-edit |
| DD-14 | Whole document obsolete | A page documents a removed subsystem, config format or feature | eslintrc processor docs (R73); local collaboration page (R107) | Low count, high value. 2% of my sample; "Remove X docs" commits recur in every large repo | assisted (page's named symbols mostly unresolved; inbound links removed) | flag-only with a deletion proposal; deletion is a maintainer decision | Ratio of unresolved identifiers to total identifiers in the page, plus age since last edit versus the code it names |
| DD-15 | Status-tracker document stale | KNOWN_BUGS, DEPRECATE, TODO, ROADMAP, CHANGELOG-unreleased entries that have been resolved or shipped | SMB removal (R75); fixed bug still listed (R76); "Remove forgotten outdated comment" (Wen 2019) | Medium in repos that keep such files; technical-debt comments were the largest group (54 of 362) in Wen 2019 | assisted (issue links closed; deprecation dates passed; TODO target symbols gone) | mechanical for date-passed and issue-closed entries; flag for the rest | Resolve issue URLs through the API for state; compare "removed in X.Y" dates with the current version |
| DD-16 | Naming and terminology drift | Project, product, plugin, directive or branch renamed; old term survives in prose | "JUnit 5" to "JUnit" (R74); `osx` to `macos` (R113); `reset` to `preflight` (R115) | Medium. 10% of README drift hits in my sweep are renames | mechanical when the old name is a token that no longer resolves; assisted for prose names | mechanical replace when the rename is 1:1 and documented in history; flag when the old name is also a legitimate historical reference | Build a rename map from `git log -S` and changelogs; grep docs for old tokens |
| DD-17 | Incorrect at birth | The doc never matched the code: wrong word, wrong identifier, wrong platform | "Mac OS X Linux" (R29); `target-spec-json` vs `json-target-spec` (R110); "purge jobs" (R82) | Low but steady. 4% of my sample; "incorrectness" was rare but judged severe (Uddin 2015) | mechanical when an identifier; comprehension otherwise | mechanical for identifiers; LLM-rewrite for wording | Same identifier resolution as DD-06; fuzzy-match misses against real identifiers (edit distance 1 to 3) |
| DD-18 | Doc right, code wrong | The documented contract is the intended one and the implementation drifted or regressed | "the callback is not thread-safe which it has to be according to the documentation" (Aghajani 2019) | Unknown share; Aghajani 2019 reports debates over which side to fix; 0 in my commit sample because the fix lands in code | comprehension | flag-only; a doc fixer must never "fix" the doc here | Any mismatch where the doc sentence is normative ("must", "guarantees", "always") and recent; route to a human with both sides shown |

**Reading the table for the skill design.** DD-01 through DD-06, DD-09, DD-12 and most of DD-16 share one signal: a token in the doc (URL, path, anchor, flag, key, identifier, version) fails to resolve against something authoritative (HTTP, the tree, the parser, the manifest, the registry). That is the mechanical core and, by the sweep, it accounts for well over half of drift fixes. DD-07 and DD-08 need execution or at least compilation to be reliable. DD-10 and DD-11 need comprehension and should produce a cited proposal, not a silent edit. DD-13, DD-14 and DD-18 should only ever be flagged.

## 5. README-specific findings

**Typical sections and how often they exist** (reported by Prana et al. 2018, 393 READMEs): some "What" section in 97% of files, "How" (install, usage, configuration, requirements) in 88.5%, "References" (links, related work, docs) in 60.8%, "Who" (team, acknowledgements) in 52.9%, "Contribution" in 27.8%, "Why" in 25.7%, "When" (status, roadmap, versions) in 21.4%. By volume, "How" is 58.4% of all sections and "References" 20.3%.

**Which sections drift most, triangulated:**

1. **Install and setup (How).** The installation study found 1,163 commits across 400 repos touched installation content, with dependency setup the largest subcategory (45.3%) and "update of software version" the largest trigger. In my sample, install-section fixes were the largest category (15%) and came in two shapes: a per-platform block rotting independently (ripgrep's Fedora copr, RHEL copr, brew tap; uv's pacman) and a procedure changing wholesale (copona's installer; Terraform's `make updatedeps`; Deno's build script rename). Practitioners rate "outdated installation instructions" important at 54% (Aghajani 2020).
2. **References, links and badges.** 45% of README drift hits in my sweep name a link, badge, URL, anchor, logo or image. These are the most mechanically checkable and the most merged class of automated fix (Hata et al. had "most of our fixes merged").
3. **Usage and CLI reference.** Flag renames and removals (bat, prettier, git, black, compose) are the one class that maintainers most often fix in the same commit as the code. The lagging cases are option-description prose (serverless-offline) and option tables in secondary docs (go-toolchain's README table, dotnet's feature-switch table).
4. **Feature or status claims (What and When).** Negations age worst: "not currently supported", "isn't in any other package repositories", "no SIMD", "Segfaulty" (Deno). Prana found "When" sections (status) in only 21% of READMEs, but when they exist they are among the staler content.
5. **Architecture and project-layout trees.** Directory trees and module maps in README or CLAUDE.md (perch, Flask tutorial layout, polyipseity's instruction index) are diffable against `ls` and go stale quietly.
6. **Who and sponsors.** Churns constantly (19 of 277 hits) but is not a code-drift problem and should be left alone by the skill.

**README update frequency.** Only 0.8% of PRs touch the README (2603.00489); 3.6% of commits touch it (IPSJ 2021); npm packages average up to 7 README edits over their life (1802.08391). READMEs are edited rarely and in bursts, which is why catch-up fixes dominate my sample (83%).

**Localised READMEs.** ragflow's fix (R10) had to remove the same section from README_ar.md, README_fr.md and others. A fixer should treat `README_*.md` and `README.*.md` as a family and apply the same structural edit, or at least flag the siblings.

## 6. Design implications for `document-drift`

1. **Run the resolvers first, prose second.** Resolve every URL, relative path, anchor, backticked identifier, flag, config key and version string before any LLM reads a paragraph. In the sweep this covers the majority of what maintainers actually fix, and these fixes are the ones with a provable justification.
2. **Use history to propose the replacement, not just the removal.** The two published fixers with merged patches (Hata et al. for links, ReCite for kernel symbols) both derive the fix from the target's history (redirect chain; `git log -S`). Fifteen-month-old path renames (R7) are trivially recoverable from `git log --follow`.
3. **Rename-map before grep.** Build the rename map (old flag to new flag, old key to new key, old product name to new name) from `--help` diffs, changelogs and `git log -S`, then apply it to docs. This covers DD-04, DD-05, DD-06, DD-16 and most DD-02.
4. **Treat negated capability sentences as hot spots.** "Not supported", "not yet", "currently", "only", "no longer" sentences that name a symbol should be re-checked against that symbol every run.
5. **Never auto-edit DD-13, DD-14, DD-18.** People lists, whole-page deletions, and normative contract sentences go to a human with both sides shown.
6. **Report with line numbers and the reason.** The one maintainer interview on record asked for exactly that and said two-thirds precision would be acceptable; the LLM study's main failure modes were vague suggestions and wrong insertion points.
7. **Apply structural edits across README translations and mirrored docs** (`docs/` plus `website/versioned_docs/`, as in prettier R66 and R67).
8. **Prefer deletion over rewriting for removed features.** In the sample, maintainers deleted sections (ripgrep, Flask HPKP, Black Atom, Terraform Vagrant, ragflow) far more often than they rewrote them. A fixer that proposes a clean deletion with the citing commit is closer to maintainer behaviour than one that invents replacement prose.

## 7. Sources

| # | Source | How read | Used for |
|---|---|---|---|
| 1 | Aghajani, Nagy, Vega-Marquez, Linares-Vasquez, Moreno, Bavota, Lanza. Software documentation issues unveiled. ICSE 2019. DOI 10.1109/ICSE.2019.00122. PDF at inf.usi.ch/faculty/lanza/PUBS/P/Agha2019a.pdf | full text (pypdf extraction) | taxonomy, 878 artifacts, 72/268/190 counts, 39% and 21% figures, quotes |
| 2 | Aghajani et al. Software documentation: the practitioners' perspective. ICSE 2020. PDF at inf.usi.ch/faculty/lanza/PUBS/P/Agha2020a.pdf | full text (pypdf extraction) | 146 practitioners, per-issue importance percentages |
| 3 | Wen, Nagy, Bavota, Lanza. A large-scale empirical study on code-comment inconsistencies. ICPC 2019. PDF at inf.usi.ch/faculty/lanza/PUBS/P/Wen2019a.pdf | full text (pypdf extraction) | 1,500 projects, 13 to 20% trigger rate, 500-commit taxonomy, lag example |
| 4 | Fluri, Wursch, Gall. Do code and comments co-evolve? WCRE 2007; and Fluri et al. SQJ 2009 extension | abstracts via search snippets | 97% and 90% co-evolution figures, "re-documented in a later revision" |
| 5 | Zhou, Ruan, Yu, Gall, Gu. Analyzing APIs documentation and code to detect directive defects. ICSE 2017. DOI 10.1109/ICSE.2017.11 | abstract via search snippet | 1,158 defective directives, 81.6% precision, 82.0% recall |
| 6 | Uddin, Robillard. How API documentation fails. IEEE Software 32(4), 2015. PDF at cs.mcgill.ca/~martin/papers/ieeesw2015.pdf | full text (pypdf extraction) | ten problems, Table 2 counts, blocker list |
| 7 | Khan, Khondaker, Uddin, Iqbal. Automatic detection of five API documentation smells: practitioners' perspectives. SANER 2021. arXiv 2102.08486 | arXiv HTML (partial) | five smells, 78% and 27.5% prevalence |
| 8 | Prana, Treude, Thung, Atapattu, Lo. Categorizing the content of GitHub README files. EMSE 2018. arXiv 1802.06997 | arXiv HTML (Table 2 and 3) | README section categories and percentages |
| 9 | Adapting installation instructions in rapidly evolving software ecosystems. arXiv 2312.03250, IEEE TSE 2025 | arXiv HTML v3 (both halves) | change categories, trigger counts |
| 10 | Does my README file need to be updated? Exploring LLM-based README maintenance. arXiv 2603.00489 | arXiv HTML (both halves) | 0.8% of PRs, 21.5% overlooked, failure categories, maintainer quotes |
| 11 | Hata, Treude, Kula, Ishio. 9.6 million links in source code comments. ICSE 2019. DOI 10.1109/ICSE.2019.00123 | neverworkintheory.org summary and abstract | ~10% dead links, fixes merged |
| 12 | Xiao et al. Links in commit messages. EMSE 2023 | search snippet | 14% and 70% decay figures |
| 13 | We must have missed this comment: detecting and repairing stale function references in Linux kernel comments. arXiv 2608.03734 | arXiv abstract page | 869 stale references, 89% useful, 50 of 75 patches accepted |
| 14 | An empirical study on README contents for JavaScript packages. arXiv 1802.08391 | search snippet | up to 7 README updates on average |
| 15 | IPSJ 2021 study of early README evolution (ipsj.ixsq.nii.ac.jp/records/210665) | search snippet | 3.6% of commits touch README |
| 16 | GitHub repositories with links to academic papers. arXiv 2004.00199 | search snippet | README links rarely change |
| 17 | neverworkintheory.org, 2021-10-06, Software Documentation Issues Unveiled | page read | confirmation of taxonomy structure (figure only) |
| 18 | Tooling: lychee (lycheeverse), markdown-link-check, Swimm auto-sync docs, codocia crate, borghei/claude-skills doc-drift-detector | search snippets | section 4 "cheapest signal" column and section 6 |
| 19 | GitHub REST API, 32 repositories, 2,456 README commits and 32 docs-directory histories; 119 commit and PR diffs read via `gh api` | diffs read | sections 3 and 4 |

Scratch data (raw sweep output, extracted PDF text, patches) is in the session scratchpad under `gh/` and `pdftext/`; it is not part of the deliverable.
