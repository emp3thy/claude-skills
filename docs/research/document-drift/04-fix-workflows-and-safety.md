# 04. Fix workflows and safety: how tools safely fix documentation, and where the programmatic/LLM line sits

## Scope and method

This note feeds the design of the `document-drift` skill: a Claude Code skill that scans a repository, finds markdown documents, compares them against the code, flags stale or dangling material, and then fixes it behind a human review gate. The note answers six questions: how AI and dependency tools present and gate automated edits and what users say about them; which doc edits are provably correct versus "needs reading" versus "never automate"; how to stop an LLM inventing content when it rewrites a document; how tools avoid re-flagging accepted exceptions; how a fix is verified after it is made; and precisely where seven hybrid tools draw the line between a deterministic layer and a model. It ends with a proposed safety ladder of five fix classes, a numbered list of design implications, and a sources table.

Method: 27 WebSearch calls and roughly 60 WebFetch calls, dated 9 October 2026. Hacker News was mined through the Algolia API (`hn.algolia.com/api/v1/search?query=...&tags=comment`), which returns full comment bodies. Vendor documentation was read directly where the page was reachable; where a page 403'd (deepdocs.dev), redirected to an empty page (OpenAI Codex quickstart), or only surfaced in a search summary, the Sources table says "snippet" and the text treats it as weaker evidence. Reddit and web.archive.org were not attempted. Quotations are verbatim from the page read unless marked as paraphrase. All numbers are vendor or paper claims unless an independent source is named.

## 1. Fix-presentation patterns in AI code tools

### Catalogue of patterns

**PR-per-change (one PR per finding or per task).** Dependabot's default is one PR per dependency, capped by `open-pull-requests-limit`: "If five pull requests with version updates are open, no further pull requests are raised" until some are merged or closed, and security PRs do not count (Dependabot options reference, read). The GitHub Copilot coding agent opens one PR per task: "Copilot can only work on one branch at a time and can open one pull request per task" (Copilot coding agent concept page, read). Sweep's launch post described the same shape, issue in, PR out, with a GitHub Actions loop "checking the code, telling Sweep about the errors, letting Sweep fix them, and checking again" (Launch HN story text, read via Algolia). The agentic Copilot Autofix (public preview July 2026) "Explores relevant files across your codebase", "Generates a proposed fix", "Validates the fix works by rerunning CodeQL", and "Iterates if needed, then opens a draft pull request ready for your review" (GitHub changelog, read).

**Batch PR (grouped changes).** Dependabot added groups to answer the PR-volume complaint. Groups are keyed by `applies-to`, `dependency-type`, `patterns`, `exclude-patterns` and `update-types`, with the stated purpose "This helps you focus your review time on higher risk updates, and minimize the time spent reviewing minor version updates" (Dependabot grouping page, read). Renovate's noise-reduction page recommends "intelligent grouping of related packages" but warns "Sometimes you're better off getting a single PR per dependency!" (Renovate noise reduction, read). The DeepDocs doc bot, per third-party listings, "opens a clean branch with suggested updates" and "updates only the relevant sections of your README files, API references, and tutorials while preserving existing style and structure" (snippet; the product page 403'd).

**Inline suggestion (GitHub suggested-changes blocks).** CodeRabbit, Copilot code review, Sourcery and Semgrep rule-defined fixes all use GitHub's native suggestion block, which the reviewer can apply one at a time ("Commit suggestion") or as a batch: "To quickly incorporate more than one suggested change into a single commit, you can also apply suggested changes as a batch" and "Applying one suggested change or a batch of suggested changes creates a single commit on the compare branch of the pull request" (GitHub suggested-changes docs, read). Semgrep: "When rules that include a Rule-defined fix are triggered, Semgrep suggests these fixes in your pull request or merge request comments" (Semgrep autofix docs, read). This is the cheapest accept/reject gate on GitHub because the platform owns the UI and the audit trail.

**Diff preview with accept/reject (IDE-side).** Classic Copilot Autofix shows "a preview of the code suggestion that the developer can accept, edit, or dismiss" and "presents all suggestions as proposed code changes that require explicit developer review and acceptance" (GitHub blog and responsible-use page, both read). Amazon Q Code Transformation ends with "the Proposed Changes tab" where the developer can "Download proposed changes", open "a diff view with your source code and upgraded code", and then "choose Accept" (AWS docs, read). Claude Code gates every file modification with a permission prompt in Manual mode ("File modification: Edit/write files: Yes"), and the approval "lasts until the session ends"; `acceptEdits` mode "Automatically accepts file edits and common filesystem commands" (Claude Code permissions docs, read). Cursor's official review page is thin: "The diff view shows changes as they happen" and "After the agent finishes a task, click Review then Find Issues" (Cursor docs, read); forum threads show the per-change accept/reject model has churned across versions, with Cursor 3 auto-applying edits and offering "Discard All Changes" instead of "Accept All" (Cursor forum, snippet). Codex cloud shows a diff per task and a "Create Pull Request" button (snippet; the official quickstart now redirects to a page without this content).

**"Proposed edit" comments (fix text in a comment, not a committable block).** Semgrep Assistant's AI "Suggested fix" is deliberately not inline: "It does not include inline code diffs", PR comments carry "step-by-step remediation instructions", and for committable changes the docs point back to deterministic rule-defined fixes (Semgrep Assistant overview, read). This is a notable design choice: the deterministic layer gets the committable button, the LLM layer gets prose.

**Status-field round-trip files (the tool writes a list, the human edits it, the tool reads it back).** The oldest precedent is `git rebase -i`: "An editor will be fired up with all the commits in your current branch", "To drop a commit, replace the command "pick" with "drop", or just delete the matching line", and "git rebase will not look at [the oneline descriptions] but at the commit names ... so do not delete or edit the names" (git-rebase docs, read). Terraform's plan file is the same idea in binary form: `plan -out` "Writes the generated plan to the given filename in an opaque file format that you can later pass to terraform apply to execute the planned changes", with the caveat that intervening changes "might cause the final effect of a configuration change" to differ (Terraform docs, read). Renovate's Dependency Dashboard is a live example on GitHub: an issue with "dynamic Markdown checkboxes" where ticking a box asks Renovate to create or recreate a PR, with `dependencyDashboardApproval` holding updates until approved; the maintainers warn against requiring approval for everything because "out of sight means out of mind" (Renovate dashboard docs, read). Dependabot's comment commands are a round trip through PR comments: "@dependabot ignore this dependency Closes the pull request and prevents Dependabot from creating any more pull requests for this dependency" (snippet of the reference page), with ignore preferences "stored ... centrally" and the advice that for multi-contributor repos "it is better to explicitly define the dependencies and versions to ignore in the configuration file" so "all contributors can see why" (Dependabot managing PRs page, read). Swimm's GitHub app puts an "Approve Auto-sync" button on the check that "accepts all Auto-synced docs from the GitHub App" and offers an "automatic Auto-sync approval" setting that commits "to your open pull request in a dedicated commit" (search snippet; the docs pages read did not contain the button text).

**Interactive per-finding approval.** Claude Code's Manual mode and `ruff check --fix` with `--unsafe-fixes` hints are the CLI shape of this; Semgrep's `--autofix --dryrun` is a "preview, then apply" shape: "To test the fix before applying it, use both the --autofix and --dryrun flags" (Semgrep autofix docs, read).

### What users complain about

The complaints cluster into four themes, each with a quotable source.

1. **Volume and review fatigue.** Dependabot: "Dependabot adds more noise than value" (matharmin, HN 2021); "12 per PR, so people stop reading them" (indiekitai, HN 2026); switching to "grouped weekly Dependabot PRs because the daily volume was 'a little too much noise'" (casmn, HN 2025) (all read via Algolia). CodeRabbit: "tools like CodeRabbit create too much noise, are hard to configure" (nnorbert, HN 2026); "CodeRabbit and qodo were too noisy to be useful" (oscarestudillom, HN 2026). The Lychee maintainer's one-month audit of 28 PRs and about 290 findings classified "15% useless, 13% wrong assumptions, 21% nitpicks, 13% thoughtful, 35% quality improvements, 3% security/critical", and concluded "Automated issues that are not relevant are just noise and wastes time" while still calling the tool "impressively thorough" (lycheeorg.dev post, read). A secondary write-up adds that the real problem is reviews per push: "CodeRabbit reviews every push by default" so eight commits produce eight reviews, and "Review fatigue is the failure mode" (aicodereview.cc, read, secondary).

2. **Wrong or shallow fixes.** Sweep "tried to redefine constant variables", misplaced code, and "the result didn't work" on a non-trivial d3 task (andoando, HN 2024). Copilot coding agent "repeatedly failed CSS changes" (ravedave5, HN 2025). Review bots "report samples, not exhaustive lists": the same bug pattern was flagged twice when present five times, and a rerun flagged a different line (chaosinc604, HN 2026). HN also records a security incident attributed to an AI-generated Copilot Autofix (sippeangelo, HN 2026, read via Algolia; the attribution is the commenter's).

3. **Agents editing things they were not asked to touch.** The Copilot coding agent injected promotional "tips" into PR descriptions, including human-authored PRs, across roughly 1.5M PRs; GitHub's timrogers called it "the wrong judgement call" and disabled it (HN March 2026, read via Algolia). The lesson for a doc fixer is that scope creep in a bot's edits is noticed and resented more than the bot's errors.

4. **Tone and gatekeeping.** Review bots "issue commands in an imperative tone" (hypfer, HN 2026) and push developers "into arguing with an AI about design choices" (eloisius, HN 2026).

### What maintainers say about acceptance rates

- GitHub on classic Copilot Autofix: suggestions "shown to remediate more than two-thirds of found vulnerabilities with little or no editing", covering "more than 90% of alert types in JavaScript, Typescript, Java, and Python" (found-means-fixed blog, read). A GitHub employee on HN: "more than 100,000 fixes applied with Autofix in the last 6 months" and "an average 3x speed up in time to fix over no Autofix" (summarity, HN 2025, read via Algolia).
- Semgrep on noise filtering: filters "one in five SAST findings as a false positive", at "a 95% alignment rate with users" (later wording: 96% with security researchers), and the product page states "Multimodal is over 95% accurate in categorizing Semgrep Code findings as false positives" (Semgrep overview, read; blog, snippet).
- Agent-authored PRs, independent data (AIDev-pop, 33,596 PRs across five agents, repos with 100+ stars): overall 71.48% merged. Per task type, docs PRs are accepted most often: Claude 0.75, Copilot 0.61, Cursor 0.74, Devin 0.71, Codex 0.92, versus 0.38 to 0.81 for features (arXiv 2602.02345, read). The paper offers no causal explanation; the plausible one for this skill is that doc PRs are small and cheap to verify. The companion failure study found the top rejection reason is "Abandoned/Not Reviewed" at 38% ("PR closed with no meaningful human interaction"), that "Not merged PRs tend to introduce larger modifications in the number of files and LOC than merged ones", and that "Each additional failed CI check was associated with about 15% lower odds of merging"; maintainers' advice is that "PRs should be small, focused, and limited to a single coherent change" (arXiv 2601.15195, read). GitHub's lukehoban argued on HN that Copilot's lower merge rate partly reflects "draft PRs are visible in the open" versus tools that iterate privately (HN 2025, read via Algolia).
- Renovate's stated policy on when to automerge is a usable acceptance heuristic: "enable automerge for any dependency update where you would select "merge" anyway", "Renovate will wait for the required tests to pass before it automerges", and "The lowest risk type of update to automerge is probably lockFileMaintenance" (Renovate automerge docs, read).

## 2. Safety taxonomy for doc edits

### The clearest precedents: Ruff and ESLint

Ruff's linter documentation (read) defines two user-facing classes plus a hidden third. "Ruff labels fixes as "safe" and "unsafe". The meaning and intent of your code will be retained when applying safe fixes, but the meaning could change when applying unsafe fixes. Specifically, an unsafe fix could lead to a change in runtime behavior, the removal of comments, or both." Policy: "Ruff only enables safe fixes by default. Unsafe fixes can be enabled by settings unsafe-fixes in your configuration file", and "By default, Ruff will display a hint when unsafe fixes are available but not enabled." Safety is adjustable per rule ("lint.extend-safe-fixes and lint.extend-unsafe-fixes") and is surfaced in machine output: "The safety of each fix is available under the applicability field." The source enum has a third variant, `DisplayOnly`, documented as a fix that "may be incorrect or produce invalid syntax, so it is meant only for display and manual application by the user"; `Unsafe` fixes "may match the user's intent but are uncertain", still "have valid syntax", and "require user opt-in" (Ruff source commit, snippet). The contributor guide tells rule authors "You will also need to decide when to offer this fix and whether it is safe or unsafe" and requires a "## Fix safety" docs section for any fix that is "(sometimes) unsafe"; it also warns that text-based edits "make it harder to avoid syntax errors" so "be sure to add even more test fixtures than usual", while AST-based edits "should essentially never introduce syntax errors" (Ruff CONTRIBUTING, read).

ESLint draws the same line with different words (custom-rules page and core concepts, both read). Fixes: "Fixes safely correct the violation without changing application logic", and the rule author's constraint is "Avoid any fixes that could change the runtime behavior of code and cause it to stop working", with fixes "as small as possible" and "Only make one fix per message". Suggestions: "Suggestions may change application logic and so cannot be automatically applied", they are offered "if a fix potentially changes functionality or if there are multiple valid ways to fix a rule", "are applied as stand-alone changes, without triggering multipass fixes", and "cannot be applied through the ESLint CLI and are only available through editor integrations". Authors are told "Don't try to do too much and suggest large refactors".

Four transferable rules fall out of these two: (a) the safe class is defined by preservation of meaning, not by how confident the detector is; (b) the unsafe class is still syntactically valid and still offered, but opt-in; (c) multiple valid resolutions automatically demote a fix to suggestion; (d) safety is a per-rule property that users can override in both directions.

### Other policy lines

- **Semgrep** keeps rule-defined fixes "deterministic and user-defined" and applies them only with `--autofix`; the LLM "Suggested fix" is prose, not a diff (Semgrep docs, read).
- **Copilot Autofix** states the asymmetry plainly: "The system has no understanding of the programmer's intent", and for large files "the context provided to the LLM may be truncated" and the feature "will not attempt a fix" rather than guess (responsible-use page, read). Not attempting is itself a safety class.
- **Dependabot** separates risk by semver level and by dependency type (`update-types`, `dependency-type`), applies "a 3-day cooldown to version updates even when cooldown isn't configured", and exempts security updates from both grouping defaults and the PR limit (options reference, read). Renovate: automerge "works particularly well for devDependencies and for production dependencies that have great test coverage", and without tests "Renovate won't automerge by default" (Renovate docs, read).
- **OpenRewrite/Moderne** keeps transformations deterministic because large-scale refactoring "requires accuracy and trust in your system", recipes are "precise, deterministic, and fast", and the LLM is "called only when needed"; they cite an LLM-only failure where "the LLM alone misread "this" as a determiner and changed "class" to "classe"" (Moderne blog, read).
- **Google** on documentation: "A small set of fresh and accurate docs is better than a large assembly of "documentation" in various states of disrepair", "Dead docs are bad. They misinform, they slow down, they incite despair", and "Default to delete or leave behind if migrating. Stragglers can always be recovered" (docguide best practices, read). Its code-review checklist: "If a CL changes how users build, test, interact with, or release code, check to see that it also updates associated documentation, including READMEs", and "If the CL deletes or deprecates code, consider whether the documentation should also be deleted" (eng-practices, read). Note that comments and docs are different: comments explain "the reasoning behind a decision", which "the code itself can't possibly contain" (same page). That sentence is the clearest published justification for a "never automate rationale" rule: the code cannot contradict a statement of intent, so a detector cannot prove it stale.

### Applying the taxonomy to documentation

**Provably correct (mechanical-safe).** The evidence is a deterministic artefact the tool can show. Path renamed: git rename detection (`git log --follow`, `-M`) yields old and new paths; the doc reference matches the old path exactly; the new path exists. Link target gone: the file or anchor does not exist at HEAD, and no rename candidate exists. Version string: the manifest (package.json, pyproject, Cargo.toml) carries one canonical version and the doc's string differs from it in a recognisable version position. CLI flag removed: the parser definition (argparse `add_argument`, clap derive, commander `.option`) no longer declares it and no alias does. Swimm's own product line is drawn here: "Minor changes (variable name or parameter value change, for example) are automatically updated without intervention" (Swimm blog, read), and the VS Code docs describe the unit of sync as "code elements (snippets, tokens and paths)" (read). The CUP/HebCup literature draws the same boundary from the other side: a heuristic updater that rewrites single tokens is "only useful for code-indicative samples, whose changed tokens/sub-tokens in comments can also be found in corresponding code changes" and "is not sufficiently effective beyond simple updates" (HatCUP/CBS snippets), and LLMCup's worst category is "Non-Code-Ind & Multi-Tokens updates" at 0.095 accuracy, "comment changes that lack code anchoring" (LLMCup, read). Token-anchored edits are the safe class in both engineering and research.

**Plausible but needs reading.** Any sentence whose truth value depends on behaviour rather than on an identifier: "the server retries three times", "this command is idempotent", a step-by-step tutorial. These correspond to ESLint suggestions and Ruff unsafe fixes: offered, syntactically valid, opt-in, one at a time. The C4RLLaMA manual evaluation gives the base rate: "the percentage of correct comment updates by C4RLLaMA was 65.0% and 55.9% in Just-in-time and Post Hoc, respectively" (ICSE 2025 abstract, read). Roughly one in three rewrites is wrong, which is a reading rate, not an auto-apply rate.

**Never automate.** Design rationale, intent, roadmap, policy, licence text, CHANGELOG history, security advisories, and any doc that may be describing the intended behaviour while the code regressed. The last case matters: Radmanesh et al. found "inconsistent changes are around 1.5 times more likely to lead to a bug-introducing commit" and that "the impact ... is highest immediately after the inconsistency is introduced" (arXiv 2409.10781, read). A doc that disagrees with fresh code is evidence of a bug as often as evidence of a stale doc, and a tool that silently "fixes" the doc destroys that evidence. Google's "Documentation is the Story of Your Code" and "comments are for ... the reasoning behind a decision" are the published statements of why these are out of scope.

## 3. Hallucination control for LLM rewrites of docs

Evidence that constraints are needed. "When Models Edit Too Much" (arXiv 2609.04061, read) builds 400 problems with known minimal patches and finds over-editing "even in strong frontier models such as GPT-5.5"; a model "can reach a high Pass@1 while still making unnecessarily large edits". A single prompt-level preservation clause "lowered average excess Levenshtein distance from 0.195 to 0.131, reduced added cognitive complexity by 26.6%, and raised Pass@1 by 2.3 points", which is real but partial. DocAgent's motivation lists LLM documentation that is "incomplete, unhelpful, or factually incorrect", including invented components "especially in large or proprietary repositories" (arXiv 2504.08725, read). The README-maintenance study (arXiv 2603.00489, read) reframes the task as locate-and-justify rather than regenerate: given a PR, decide "whether a README update is needed", "identify where in the README the change should be made", and "provide a justification by explaining the triggering events"; the best configuration "recovers about half of the pull requests historically paired with README updates" and reaches "28% user-facing accuracy", with manual annotation showing "21.5% of temporally matched recommendations flagged updates developers had overlooked".

Techniques with published precedent:

1. **Edit-only output with an applier that rejects ungrounded edits.** The `lcea` format requires SEARCH/REPLACE blocks where "a SEARCH block must match exactly once in the target file" (pypi, snippet). Any edit whose anchor text is not found verbatim is rejected before it reaches the human. This is the single strongest structural defence because it makes "invent a paragraph" impossible: the model can only replace text that exists.

2. **Length and novelty guards.** The POaaS minimal-edit system rejects "any specialist output that exceeds 2× the original character length", has a guard that "rejects edits that add new content or remove explicit constraints", and a "fail-safe fallback that returns the original unchanged if all candidates fail" (arXiv 2603.16045, snippet). ESLint's "as small as possible" and "Only make one fix per message" are the deterministic cousins.

3. **Delete beats rewrite.** Google: "Default to delete or leave behind if migrating. Stragglers can always be recovered." Swimm's resolution menu for an Outdated element is binary: "you can replace it with another element, or just delete it altogether" (VS Code docs, read). A deletion cannot hallucinate; the worst case is a missing sentence, which git preserves.

4. **Cite the code line for each changed claim.** Semgrep's dataflow traces "give the models context so guidance can reference specific files and locations instead of guessing" (Semgrep tech blog, read). Copilot Autofix's prompt is built from "CodeQL alert data in SARIF format", "short snippets around each source location, sink location", "The first ~10 lines from each file involved", and "Help text for the CodeQL query" (responsible-use page, read): the model only ever sees evidence the deterministic engine selected. For docs, the equivalent is: every proposed sentence must carry a `path:line` whose content was passed in the prompt, and the applier rejects citations that do not resolve.

5. **Two-pass propose-then-verify with a separate chain.** Semgrep runs "a separate review chain" that "rates the fix on four attributes: whether the issue persists, whether the code is malformed, whether more code or infrastructure changes are needed, and whether the LLM can fix the issue at all", arguing a fresh chain of thought works "like "another human" in the loop" (tech blog, read). DocAgent's Verifier scores the Writer's draft; the evaluation framework scores "Completeness, Helpfulness, and Truthfulness" (read, abstract only). LLMCup generates several candidates and a ranker "selects the final output by scoring alignment between code changes and comment changes"; R2ComSync adds retrieval of similar past cases plus three reranking rules and reports that "LLMs fall short of State-Of-The-Art (SOTA) CCS approaches" without them (both read). The common lesson: a single generation is the weakest configuration; generate several, verify against the code, rank.

6. **Test by execution.** For commands and examples, the only honest verifier is running them (see section 5). Copilot Autofix internal testing asks "Has the fix changed the output of any of the repository tests?" (read).

7. **Forbid new sections and new facts.** The README study found generative regeneration is the wrong tool for incremental maintenance (snippet of the full text; the abstract read supports the localise-and-justify framing). DeepDocs markets "updates only the relevant sections ... while preserving existing style and structure" (snippet). Combined with 1 and 2 this becomes enforceable: reject any hunk that adds a heading, adds a fenced block, or adds a sentence containing an identifier that does not occur in the repository.

Caveat on human studies: LLMCup's user study (7 graduate students, 100 sampled cases where LLMCup and ground truth differed) rated LLM comments slightly above human ones on consistency, naturalness and helpfulness (read), but the paper "does not analyze hallucination, over-editing, or ignoring code changes as LLM failure modes", and its edit-effort metrics are slightly worse than the heuristic baselines because of "more verbose yet semantically rich comments". Verbosity is a cost in documentation, so a rater study that rewards richness should not be read as licence to rewrite.

## 4. Idempotence, re-runs and baselines

Precedents, from most to least structured:

- **Inline markers in markdown.** markdownlint supports `<!-- markdownlint-disable -->`, `<!-- markdownlint-enable -->`, `<!-- markdownlint-disable-line -->`, `<!-- markdownlint-disable-next-line -->`, `<!-- markdownlint-capture -->`/`restore`, file-wide `<!-- markdownlint-disable-file -->`, and `<!-- markdownlint-configure-file { ... } -->`; a change "applies starting from the line the comment is on", and "Most rules ignore HTML comments entirely" (README, read). This is the exact shape for `<!-- drift-ignore -->` and `<!-- drift-ignore-next-line REASON -->`, and HTML comments are invisible in rendered output.
- **Inline markers with codes and unused-suppression checking.** Ruff: "# noqa: {code}" per line, "# ruff: noqa" per file, and the rule `unused-noqa` (RUF100) "to enforce that your suppressions are "valid"" (read). CodeQL 2.12.0: "// codeql[query-id]" comments that "must be placed on a blank line before the alert" (changelog, read). The important detail is RUF100: a suppression whose finding no longer fires is itself reported, so suppressions do not rot.
- **Ignore files for link checkers.** lychee: exclusions "by putting them into a file called .lycheeignore", `--exclude-path` for paths, plus a response cache (`.lycheecache`, `--max-cache-age` default 1d) (README, read).
- **Baselines by commit.** Semgrep diff-aware scans "only shows new findings relative to some specified baseline commit", with the finding identity "(rule ID, file path, syntactic context, index)" so a finding survives line shifts (findings-ci, read). The recommended baseline for CI is the merge-base (snippet).
- **Baselines by period or reference.** SonarQube's new code: "Previous version", "Number of days" (max 90), "Specific analysis", "Reference branch" (read). A quirk worth copying: a recently closed issue that reappears is re-raised rather than created new, preserving its history (community thread, snippet).
- **Reasons attached to suppressions.** Semgrep's platform ignore records "False positive", "Acceptable risk", or "No time to fix" (read). Dependabot advises that ignores belong in the config file so "all contributors can see why" (read). CodeQL's `dismiss-alerts` action reads SARIF suppressions and "reopens alerts whose suppression was removed" (snippet), which is suppression-as-code with automatic expiry.
- **Time-boxed acceptance.** Google attaches freshness dates: documents "note the last time a document was reviewed, and metadata in the documentation set will send email reminders when the document hasn't been touched in, for example, three months" (book quote, snippet). Dependabot's cooldown and Renovate's `minimumReleaseAge` are the dependency equivalents: wait N days before acting.
- **Approval that lives in a human-editable artefact.** Renovate's Dependency Dashboard (checkboxes in an issue) and git's rebase todo (section 1) show that a markdown file with a status column is a legitimate, well-understood approval surface, provided the tool reads back stable identifiers and not the human-readable text ("git rebase will not look at [the oneline descriptions] but at the commit names").

The cleanest precedent for "accepted drift, do not report again until X" is a combination: a finding identity that is content-based rather than line-based (Semgrep's tuple), an inline marker with a reason and an optional expiry (markdownlint syntax, Semgrep reasons, Google freshness dates), and a stale-suppression check that reports markers whose finding no longer fires (Ruff RUF100). Nothing surveyed combines all three, which is an opportunity for the skill.

## 5. Verification after fixing

What tools actually do, in rough order of strength:

1. **Re-run the deterministic detector on the result.** Copilot Autofix's internal testing merges the suggestion unedited and checks "Was the code scanning alert fixed by the suggestion?", "Did the fix introduce any new code scanning alerts?", "Did the fix introduce any syntax errors that code scanning can detect?", and "Has the fix changed the output of any of the repository tests?"; "Suggestions that fail internal testing are not displayed to users" (responsible-use page, read). The agentic version "Validates the fix works by rerunning CodeQL" and its PR "includes a summary of the fix, why it closes the alert, and the validation steps Copilot took" (changelog, read). Semgrep feeds the LLM's code back through the engine and "returns the exact match location, which is fed back to the model as added context" (tech blog, read). Moderne describes "validate the LLM suggestion with our 100% accurate refactoring system" (blog, read; the accuracy figure is a vendor claim). For docs: after applying, the drift detector must report zero findings for that doc, and zero new findings elsewhere.

2. **Build or test gate before merge.** Amazon Q "first builds your code in the source language version", then after transformation "you verify and accept the changes in your IDE"; the docs warn "The initial and validation builds use the client-side environment" (AWS docs, read). Renovate "will wait for the required tests to pass before it automerges" and, in branch mode, "If tests fail, Renovate raises a PR for you to review" (read). The Copilot coding agent will not even run CI without a human click, because "GitHub Actions workflows can be privileged and have access to sensitive secrets" (read).

3. **Execute documentation code blocks.** `mdbook test` exists because "The Rust Programming Book uses a lot of code examples that could get outdated" and blocks tagged `ignore` are skipped (snippet). pytest-markdown-docs collects fences in `python`, `python3`, `py` from `.md`, `.mdx`, `.svx` and docstrings, with `notest` to exclude, `continuation` to chain blocks, and `fixture:<name>` for injected globals (pypi, read). Hugging Face's doc-builder added runnable blocks because unexecuted snippets lead "to documentation drift" (snippet). For shell commands in a README, the practical check is `--help`/`--version` parsing or a sandboxed dry run, not a full execution.

4. **Link and anchor check.** lychee with `--accept` ranges and caching (read). This is also the detector, so it doubles as rule 1 for link fixes.

5. **Diff size and shape checks.** The agentic-PR study's finding that larger PRs merge less often (read) and the minimal-edit paper's excess-Levenshtein metric (read) justify a hard cap per hunk and per file, plus structural assertions (no new headings, no new fenced blocks, no new identifiers absent from the repo). POaaS's "2× the original character length" cap is a concrete number (snippet).

6. **Independent reviewer pass.** Semgrep's self-review chain and DocAgent's Verifier (section 3). GitHub additionally "spot-checks successful suggestions" and runs "A filtering system on the LLM" for harmful output (read). The HN report that a reviewer bot "flagged two sites with the same pattern, which appeared five times" (read via Algolia) is the caution: an LLM reviewer samples, so it complements rule 1 rather than replacing it.

7. **Render check.** None of the surveyed tools renders markdown as a gate; markdownlint is the nearest, and its inline-comment handling (section 4) means a rendered-output check is cheap to add. This is a gap rather than a precedent.

## 6. The programmatic/agentic split in hybrid tools

| Tool | Deterministic layer does | Model does | Their stated reason |
|---|---|---|---|
| **Ruff** (+ any LLM pair) | Detects, classifies each fix as Safe / Unsafe / DisplayOnly, applies Safe by default, exposes `applicability` in JSON | Nothing in Ruff itself; an LLM pair would consume DisplayOnly and Unsafe hints | "The meaning and intent of your code will be retained when applying safe fixes" (read) |
| **ESLint** | Detects; applies fixes that do not change logic in multipass; emits suggestions that "cannot be automatically applied" | Editor or agent chooses among suggestions | "Suggestions may change application logic" (read) |
| **Semgrep + Assistant** | Rule-defined `fix:` produces committable PR suggestions; engine re-checks LLM output; finding identity and baselines | Noise filtering (hide, never close), prose "Suggested fix", remediation guidance, memories | Engine output "feeds back" as context; "Ultimately, it's a suggestion and it's up to the engineer to accept it or not" (blog, snippet) |
| **CodeQL + Copilot Autofix** | CodeQL finds the alert and supplies SARIF, source/sink snippets, query help; CodeQL re-runs to validate; filters out failing suggestions | Writes the patch and explanation; agentic version explores and iterates | "The system has no understanding of the programmer's intent"; truncated context means "will not attempt a fix" (read) |
| **Sourcery** | Rules-based Python refactorings ("specific, rules-based, suggestions"), one-click in IDE | PR review comments across 30+ languages | Docs say it "combines large language models and static analysis" (snippet; split per comment not published) |
| **Swimm Auto-sync** | Tracks code-coupled snippets, tokens and paths; auto-updates "Minor changes (variable name or parameter value change)"; marks others Outdated and fails the check | None in auto-sync (patented algorithm; no LLM claim in docs read) | "We will only notify you if there is a significant change that requires your attention" (read) |
| **Amazon Q Code Transformation** | Builds source version first; "uses parts of OpenRewrite" for mechanical upgrades; produces a diff for Accept | Analyzes, "generates a transformation plan", handles "a long tail of Java libraries with backward-incompatible changes" | Foundation models "essential for context-specific code transformations" (AWS blog, snippet); a third party estimates recipes did "more than 80% of the changes" (snippet) |
| **Moderne / OpenRewrite + LLM** | Recipes walk the LST "in a deterministic way, calling the AI model only when needed", reinsert the model's output into the tree, emit data tables and PRs | Receives "only the parts of the code that need evaluation or transformation"; suggests fixes reviewed as diffs | "accuracy and trust in your system"; recipes "guide and focus the LLM" for "more predictable and reliable results" (read) |

The pattern across all seven: the deterministic layer owns detection, identity, scoping of what the model sees, application of anything meaning-preserving, and post-hoc verification; the model owns judgement calls (is this a false positive, how should this sentence read) and is never the thing that decides whether its own output is applied. Where a vendor gives the model a committable button (Copilot Autofix), it first filters the model's output through the deterministic engine and tests, and still labels the result "proposed code changes that require explicit developer review and acceptance".

## Proposed safety ladder for doc fixes

Five classes, from mechanical-safe to flag-only. Names deliberately mirror Ruff and ESLint so reviewers recognise them.

### Class A: Safe (auto-apply, batched, reported)

Definition: an edit whose correctness follows from a deterministic artefact the tool can print, and which cannot change the meaning of any sentence other than by making a reference resolve again.

Evidence that justifies auto-apply: Ruff applies Safe fixes by default on the principle that "meaning and intent ... will be retained"; Swimm auto-updates renames and parameter values "without intervention"; HebCup-style single-token, code-anchored updates are where heuristics beat neural models.

Verification that must pass: the rename or target exists at HEAD (git rename detection or filesystem check); the replaced token appears verbatim in the doc; re-running the detector on the doc yields zero findings for that rule; the hunk changes only the token (no sentence boundary crossed); link check passes for any link touched.

Examples: path `src/old/name.py` to `src/new/name.py` where `git log --follow` shows the rename; anchor `#install` to `#installation` where the heading was renamed in the same commit; version string `1.4.2` to the manifest's `1.5.0` in a line matching a version pattern; relative link to a moved file.

### Class B: Safe-delete (auto-apply, each in its own hunk, listed prominently)

Definition: removal of a reference, line, bullet, or table row whose subject no longer exists in the repository and has no rename candidate.

Evidence: Google's "Default to delete ... Stragglers can always be recovered"; Swimm's Outdated resolution is "replace ... or just delete it altogether"; ESLint's removal semantics (`fix` returning null removes the suggestion).

Verification: no file, symbol, flag, or anchor at HEAD matches the reference (including fuzzy rename detection at a conservative threshold); the deletion does not orphan a sentence (the remaining text still parses as a list item or sentence); the detector goes green; a diff-shape check confirms deletions only, no insertions beyond punctuation.

Examples: a bullet documenting `--legacy-mode` where argparse no longer defines it or any alias; a row in a config table for a key no longer read anywhere; a link to a deleted file with no rename.

### Class C: Unsafe (proposed, opt-in per hunk, model-generated under constraints)

Definition: a rewrite of existing prose where the detector proves the current text is wrong but the correct text requires reading code behaviour.

Evidence against auto-apply: C4RLLaMA's 65.0% / 55.9% correct-update rates; LLMCup's 0.095 accuracy on non-code-anchored multi-token updates; over-editing "even in strong frontier models"; Copilot Autofix's "no understanding of the programmer's intent".

Verification: SEARCH/REPLACE applier with exact single match; every changed sentence carries a `path:line` citation that resolves and whose content was in the prompt; hunk length at most 2× the original; no new headings, fenced blocks, or identifiers absent from the repo; a second, independent model pass answers "does the rewritten sentence state anything the cited lines do not support?" and rejects on yes; detector goes green; the human accepts each hunk individually (GitHub suggestion block or per-finding prompt).

Examples: "retries three times" when the constant is now 5; a function described as synchronous that is now async; a config example whose key names changed.

### Class D: Display-only (shown with a proposed edit, never applied by the tool)

Definition: a finding where the tool can show a plausible replacement but cannot verify it, or where there are multiple valid resolutions (ESLint's rule for demoting a fix to a suggestion).

Evidence: Ruff's DisplayOnly ("may be incorrect ... meant only for display and manual application"); Semgrep's AI "Suggested fix" that "does not include inline code diffs".

Verification: none applied by the tool; the report shows the finding, the evidence, and a candidate text, and the human edits by hand or dismisses with a reason that becomes an inline marker.

Examples: a tutorial step whose command still exists but whose output or side effects changed; a README section describing an architecture that was partially refactored; a doc that disagrees with code younger than N days (possible regression).

### Class E: Flag-only (reported, no proposed text)

Definition: documents or sections whose content is intent, rationale, history, or policy, where the code cannot be the ground truth.

Evidence: Google on comments carrying "the reasoning behind a decision" that "the code itself can't possibly contain"; the 1.5× bug-introduction risk of inconsistency, which means a mismatch may be a code bug; Copilot Autofix's "will not attempt a fix" when context is insufficient.

Verification: the report cites the mismatch and routes it to a human with a "doc is right / code is right / both wrong" choice; nothing is edited.

Examples: CHANGELOG entries, LICENSE, CODE_OF_CONDUCT, roadmap and design-decision documents, security policy, superpowers plan and spec folders, any section under a heading matching "Why", "Rationale", "Decision", "History".

## Design implications

1. Default to Class A and B auto-apply and everything else opt-in, because Ruff's "safe by default, unsafe behind a flag, display-only never applied" is the clearest precedent and its users accept it (Ruff linter docs).
2. Expose the class of every finding in machine-readable output, as Ruff exposes `applicability` in JSON, so a CI consumer can gate on it (Ruff linter docs).
3. Let the user promote or demote classes per rule, mirroring `extend-safe-fixes` and `extend-unsafe-fixes`, because repositories differ in how much they trust their manifests and parsers (Ruff linter docs).
4. Demote any fix with more than one valid resolution to Class D automatically, following ESLint's rule that suggestions exist "if there are multiple valid ways to fix a rule" (ESLint custom rules).
5. Keep each hunk a single change and never chain LLM fixes in one pass, because ESLint applies suggestions "as stand-alone changes, without triggering multipass fixes" and Copilot Autofix rejects fixes that introduce new alerts (ESLint custom rules; GitHub responsible-use page).
6. Prefer deletion to rewriting whenever the referent is gone, because "Stragglers can always be recovered" and a deletion cannot hallucinate (Google docguide).
7. Make the LLM emit SEARCH/REPLACE blocks whose anchor must match exactly once, and reject anything else before the human sees it (lcea; POaaS guards).
8. Require a `path:line` citation per changed sentence and reject citations that do not resolve, copying how CodeQL supplies source/sink snippets and Semgrep supplies dataflow traces so the model "can reference specific files and locations instead of guessing" (Semgrep tech blog; GitHub responsible-use page).
9. Cap each rewritten hunk at twice the original length and forbid new headings, fenced blocks and unseen identifiers, since over-editing persists in frontier models and larger PRs merge less often (arXiv 2609.04061; arXiv 2601.15195).
10. Run a separate verifier pass with a fresh context on every Class C hunk, because Semgrep found a second chain works "like another human in the loop" and DocAgent ships a dedicated Verifier (Semgrep tech blog; DocAgent).
11. Re-run the deterministic detector after applying and refuse to present any fix that does not take the finding to zero or that creates a new finding, exactly as Copilot Autofix's internal testing does (GitHub responsible-use page).
12. Treat a doc/code mismatch where the code changed within the last N days as a possible regression and route it to Class E rather than editing the doc, because inconsistency is 1.5× more likely to precede a bug and the effect is highest immediately after introduction (arXiv 2409.10781).
13. Present fixes on GitHub as suggestion blocks that can be committed singly or as a batch, since that is the gate CodeRabbit, Copilot review, Semgrep and Sourcery all converge on and the platform records who accepted what (GitHub suggested-changes docs).
14. For local runs, write a single markdown report with stable finding IDs and a status column the human edits, then read back IDs rather than prose, following git-rebase's "do not delete or edit the names" and Renovate's checkbox dashboard (git-rebase docs; Renovate dashboard docs).
15. Support `<!-- drift-ignore: REASON -->` and `<!-- drift-ignore-next-line -->` using markdownlint's comment grammar, require a reason as Semgrep does, and report markers whose finding no longer fires as Ruff's RUF100 does (markdownlint README; Semgrep findings-ci; Ruff linter docs).
16. Give findings a content-based identity (rule, path, surrounding text, index) rather than a line number so accepted exceptions survive edits, as Semgrep's 4-tuple does (Semgrep findings-ci).
17. Batch Class A and B into one commit or PR and keep Class C hunks individually acceptable, because dependency-bot users complain about per-change volume and Dependabot's own answer was grouping "to focus your review time on higher risk updates" (Dependabot grouping docs; HN Dependabot comments).
18. Never touch plan/spec folders, CHANGELOG, LICENSE, or sections whose heading signals rationale, since comments and design docs carry "the reasoning behind a decision" that code cannot contradict (Google eng-practices).
19. Do not edit anything outside the flagged doc region, because the Copilot "tips in PR descriptions" incident shows scope creep in a bot's edits draws more anger than its mistakes (HN, March 2026).
20. Report acceptance per class after each run and tune defaults from it, because the only acceptance data in the wild (two-thirds for Autofix, 61 to 92 percent for agent doc PRs, 35 percent "quality improvements" for CodeRabbit) came from measuring, not from design (GitHub blog; arXiv 2602.02345; lycheeorg.dev).

## Sources

| # | Source | URL | Read or snippet |
|---|---|---|---|
| 1 | Ruff linter docs: fix safety, error suppression | https://docs.astral.sh/ruff/linter/ | Read |
| 2 | Ruff CONTRIBUTING: adding an auto-fix, fix safety section | https://raw.githubusercontent.com/astral-sh/ruff/main/CONTRIBUTING.md | Read |
| 3 | Ruff Applicability enum history (Safe/Unsafe/DisplayOnly) | https://git.joshthomas.dev/language-servers/ruff/commit/95c8f5fd0f3c2dc53aa5cfede909f33c1eef58e7 | Snippet |
| 4 | ESLint custom rules: Applying Fixes, Providing Suggestions | https://eslint.org/docs/latest/extend/custom-rules | Read |
| 5 | ESLint core concepts: Rule Fixes, Rule Suggestions | https://eslint.org/docs/latest/use/core-concepts/ | Read |
| 6 | Semgrep autofix docs | https://docs.semgrep.dev/writing-rules/autofix | Read |
| 7 | Semgrep Assistant overview | https://docs.semgrep.dev/semgrep-assistant/overview | Read |
| 8 | Semgrep: the tech behind Assistant (2024) | https://semgrep.dev/blog/2024/the-tech-behind-semgrep-assistant | Read |
| 9 | Semgrep: noise filtering announcement (2025) | https://semgrep.dev/blog/2025/announcing-ai-noise-filtering-and-triage-memories | Snippet |
| 10 | Semgrep findings in CI: identity, baseline, ignore | https://docs.semgrep.dev/semgrep-ci/findings-ci.md | Read |
| 11 | SonarQube about new code | https://docs.sonarsource.com/sonarqube-server/10.8/core-concepts/clean-as-you-code/about-new-code | Read |
| 12 | CodeQL CLI 2.12.0 changelog: inline suppression | https://codeql.github.com/docs/codeql-overview/codeql-changelog/codeql-cli-2.12.0/ | Read |
| 13 | advanced-security/dismiss-alerts action | https://github.com/advanced-security/dismiss-alerts | Snippet |
| 14 | GitHub: responsible use of Copilot Autofix | https://docs.github.com/en/code-security/code-scanning/managing-code-scanning-alerts/responsible-use-autofix-code-scanning | Read |
| 15 | GitHub blog: found means fixed | https://github.blog/security/vulnerability-research/found-means-fixed-introducing-code-scanning-autofix-powered-by-github-copilot-and-codeql/ | Read |
| 16 | GitHub changelog: agentic autofix public preview (2026-07-10) | https://github.blog/changelog/2026-07-10-agentic-autofix-for-code-scanning-alerts-in-public-preview/ | Read |
| 17 | GitHub: about Copilot coding agent | https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent | Read |
| 18 | GitHub: reviewing Copilot PRs | https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/review-copilot-prs | Read |
| 19 | Microsoft Learn: Copilot coding agent tasks (requester cannot approve) | https://learn.microsoft.com/en-us/training/modules/github-copilot-code-agent/3-assign-track-troubleshoot-copilot-code-agent-tasks | Snippet |
| 20 | GitHub: incorporating feedback, suggested changes batches | https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/incorporating-feedback-in-your-pull-request | Read |
| 21 | GitHub: Copilot code review across the PR lifecycle | https://docs.github.com/en/copilot/tutorials/use-copilot-code-review-across-the-pull-request-lifecycle | Snippet |
| 22 | Dependabot options reference | https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference | Read (first 100k chars) |
| 23 | Dependabot: optimizing PR creation (groups) | https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/optimizing-pr-creation-version-updates | Read |
| 24 | Dependabot: managing PRs (ignore stored centrally) | https://docs.github.com/en/code-security/dependabot/working-with-dependabot/managing-pull-requests-for-dependency-updates | Read |
| 25 | Dependabot PR comment commands reference | https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-pull-request-comment-commands | Snippet |
| 26 | Renovate: noise reduction | https://docs.renovatebot.com/noise-reduction/ | Read |
| 27 | Renovate: automerge | https://docs.renovatebot.com/key-concepts/automerge/ | Read |
| 28 | Renovate: dependency dashboard | https://docs.renovatebot.com/key-concepts/dashboard/ | Read |
| 29 | Swimm: keep docs updated with Auto-sync | https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/ | Read |
| 30 | Swimm blog: GitHub app announcement | https://swimm.io/blog/keeping-internal-docs-up-to-date-always-with-the-swimm-github-app | Read |
| 31 | Swimm: VS Code keep docs up to date | https://docs.swimm.io/ide-integrations/vs-code/ide-plugins-vscode-keep-docs-up-to-date | Read |
| 32 | Swimm "Approve Auto-sync" button and auto-approval setting | (search summary of docs.swimm.io) | Snippet |
| 33 | Claude Code: configure permissions | https://code.claude.com/docs/en/permissions | Read |
| 34 | Cursor docs: agent review | https://cursor.com/docs/agent/review | Read |
| 35 | Cursor forum threads on accept/reject and Review panel | https://forum.cursor.com/t/bring-back-per-change-apply-inline-diff-review-you-re-throwing-away-your-best-ux-advantage/160856 | Snippet |
| 36 | OpenAI Codex cloud workflow (quickstart redirected to empty page) | https://developers.openai.com/codex/quickstart | Snippet |
| 37 | Launch HN: Sweep (YC S23), story text | https://hn.algolia.com/api/v1/search?query=%22Launch%20HN%3A%20Sweep%22&tags=story | Read (API) |
| 38 | HN comments: Sweep AI | https://hn.algolia.com/api/v1/search?query=%22Sweep%20AI%22&tags=comment | Read (API) |
| 39 | HN comments: CodeRabbit | https://hn.algolia.com/api/v1/search?query=CodeRabbit&tags=comment | Read (API) |
| 40 | HN comments: Copilot coding agent | https://hn.algolia.com/api/v1/search?query=%22Copilot%20coding%20agent%22&tags=comment | Read (API) |
| 41 | HN comments: Copilot autofix | https://hn.algolia.com/api/v1/search?query=%22Copilot%20autofix%22&tags=comment | Read (API) |
| 42 | HN comments: Dependabot noise | https://hn.algolia.com/api/v1/search?query=dependabot%20noise%20PRs&tags=comment | Read (API) |
| 43 | HN comments: Swimm | https://hn.algolia.com/api/v1/search?query=Swimm%20documentation&tags=comment | Read (API) |
| 44 | Lychee maintainer: one month with CodeRabbit | https://lycheeorg.dev/2025-09-13-code-rabbit/ | Read |
| 45 | aicodereview.cc: CodeRabbit too noisy (secondary) | https://aicodereview.cc/blog/coderabbit-reduce-noise | Read (secondary) |
| 46 | A Task-Level Evaluation of AI Agents in Open-Source Projects (arXiv 2602.02345) | https://arxiv.org/html/2602.02345v1 | Read |
| 47 | Where Do AI Coding Agents Fail? (arXiv 2601.15195) | https://arxiv.org/html/2601.15195v1 | Read |
| 48 | Moderne: AI-assisted refactoring in the Moderne platform | https://moderne.ai/blog/ai-assisted-refactoring-in-the-moderne-platform | Read |
| 49 | OpenRewrite LST and ICSME 2023 deterministic refactoring (search summaries) | https://conf.researchr.org/details/icsme-2023/icsme-2023-tool-demo-track/7/Deterministic-Automatic-Refactoring-at-Scale | Snippet |
| 50 | Amazon Q Developer: code transformation (Java) | https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/code-transformation.html | Read |
| 51 | AWS blog on Q Code Transformation and OpenRewrite; third-party 80% estimate | https://aws.amazon.com/blogs/aws/upgrade-your-java-applications-with-amazon-q-code-transformation-preview/ ; https://ecosystem4engineering.substack.com/p/automated-refactoring-ai-versus-deterministic | Snippet |
| 52 | Sourcery docs and third-party comparisons | https://docs.sourcery.ai/Coding-Assistant/What-Is-Sourcery/Integrations | Snippet |
| 53 | Google documentation best practices | https://google.github.io/styleguide/docguide/best_practices.html | Read |
| 54 | Google eng-practices: what to look for in a code review | https://google.github.io/eng-practices/review/reviewer/looking-for.html | Read |
| 55 | Software Engineering at Google: freshness dates (quote) | https://www.goodreads.com/quotes/11341657-at-google-we-often-attach-freshness-dates-to-documentation-such | Snippet |
| 56 | lychee README: .lycheeignore, exclude, cache, accept | https://raw.githubusercontent.com/lycheeverse/lychee/master/README.md | Read |
| 57 | markdownlint README: inline configuration comments | https://raw.githubusercontent.com/DavidAnson/markdownlint/main/README.md | Read |
| 58 | git-rebase docs: interactive mode | https://git-scm.com/docs/git-rebase | Read |
| 59 | Terraform plan docs | https://developer.hashicorp.com/terraform/cli/commands/plan | Read |
| 60 | CUP: Automating Just-In-Time Comment Updating (ASE 2020) | https://conf.researchr.org/details/ase-2020/ase-2020-papers/45/Automating-Just-In-Time-Comment-Updating | Snippet |
| 61 | HebCup / HatCUP / CBS on heuristic vs neural updating | https://arxiv.org/abs/2205.00600v1 ; https://conf.researchr.org/details/icse-2023/icse-2023-journal-first-papers/6/On-the-Significance-of-Category-Prediction-for-Code-Comment-Synchronization | Snippet |
| 62 | LLMCup: Ranking-Enhanced Comment Updating with LLMs (arXiv 2507.08671) | https://arxiv.org/html/2507.08671v1 | Read |
| 63 | C4RLLaMA: comment inconsistency detection and rectification (ICSE 2025) | https://conf.researchr.org/details/icse-2025/icse-2025-research-track/10/Code-Comment-Inconsistency-Detection-and-Rectification-Using-a-Large-Language-Model | Read (abstract) |
| 64 | R2ComSync (arXiv 2510.21106) | https://arxiv.org/abs/2510.21106 | Read (abstract) |
| 65 | Does My README File Need To Be Updated? (arXiv 2603.00489) | https://arxiv.org/abs/2603.00489 | Read (abstract) |
| 66 | When Models Edit Too Much (arXiv 2609.04061) | https://arxiv.org/abs/2609.04061 | Read (abstract) |
| 67 | DocAgent (arXiv 2504.08725, ACL 2025 demo) | https://arxiv.org/abs/2504.08725v2 | Read (abstract) |
| 68 | LARCH: LLM-based README creation with heuristics (arXiv 2308.03099) | https://arxiv.org/pdf/2308.03099 | Snippet |
| 69 | Impact of code comment inconsistency on bug introducing (arXiv 2409.10781) | https://arxiv.org/abs/2409.10781 | Read (abstract) |
| 70 | POaaS: minimal-edit prompt optimization guards (arXiv 2603.16045) | https://arxiv.org/pdf/2603.16045 | Snippet |
| 71 | lcea: minimal diff format and robust edit applier | https://pypi.org/project/lcea/ | Snippet |
| 72 | pytest-markdown-docs | https://pypi.org/project/pytest-markdown-docs/ | Read |
| 73 | mdbook test | https://romero.srht.site/mdbook/cli/test.html | Snippet |
| 74 | Hugging Face: from doctest to runnable Markdown | https://api-inference.huggingface.co/blog/huggingface/runnable-examples | Snippet |
| 75 | DeepDocs (site 403'd; third-party listings) | https://deepdocs.dev/ ; https://feedbagel.com/post/deepdocs-ai-powered-github-documentation-updater | Snippet |
| 76 | Factory Droid document automation; Cursor generate-docs workflow; probot update-docs | https://docs.factory.ai/guides/droid-exec/document-automation ; https://cursor.com/workflows/autonomous-agents/generate-docs ; https://github.com/behaviorbot/update-docs | Snippet |
