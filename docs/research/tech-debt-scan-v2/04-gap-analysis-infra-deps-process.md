# Gap analysis: dependency, security, build, infrastructure, process, data and ML debt types

Research note for tech-debt-scan v2. Compiled 2026-09-02. Slice: TD-02, 03, 14, 16, 19, 23, 25, 26, 27, 30, 31, 33, 34 and 35 from `02-debt-types-consolidated.md`. Coverage is checked against that report's "Repo-observable symptoms" column. Recommended steps follow section 3 of `05-architecture-best-practice.md`: tool-backed facts before LLM inference, earned confidence tiers, ownership from git, and "not assessed" instead of a guess. File and line references are to `skills/tech-debt-scan/`. Effort: S under half a day, M up to two days, L larger.

## 1. What the current skill can and cannot see

Four properties of the skill decide coverage for this slice before any prompt is read.

**The inventory lists source and markdown only.** `scripts/inventory.py:33-54` (`EXT_TO_LANG`) maps nineteen code extensions plus `.md`; `walk_inventory` skips every other file at lines 215-218. Manifests, lockfiles, `Dockerfile`, workflow YAML, `*.tf`, Kubernetes and compose YAML, `*.ipynb`, `*.sql`, `.env`, `CODEOWNERS`, `.python-version`, model binaries and every configuration format are absent from `files`, `total_files`, `languages` and `hotspots`. Churn is mined for every path git reports (lines 122-160) but never emitted for unlisted files. Scouts can still read the whole tree, but nothing tells them these files exist, how much they churn, or that the repository has infrastructure at all. `DEFAULT_IGNORE` (lines 56-73) also drops any directory named `build` or `bin`, which in some repositories hold build scripts and CLI entry points.

**Git yields commit counts only.** `_git_churn` uses `--pretty=format:` with `--name-only`; author names, dates, tags and branches are never collected, so every ownership, recency, cadence or branch-age symptom in this slice is unobservable.

**The classification vocabulary has no slot for most of the slice.** `scripts/validation.py:15-26` allows `code, design, architecture, test, documentation, dependency, build, requirement`. Security, infrastructure, knowledge or process, data, ML and performance findings must be misfiled. Categories are pinned to eight names in `categories.py:65-178`; `validate_synthesis_output` rejects any other (`build_synthesis_prompt.py:261-266`) and `tests/test_categories.py:5-18` asserts the exact set.

**There is no tool probe and no verifier.** The dependency prompt asks the scout to identify advisories itself (`categories.py:147-148`) and to mark unverifiable ones low confidence (156-157). The synthesis prompt then drops low-confidence findings "unless severity is 5" (`build_synthesis_prompt.py:200`). A hallucinated vulnerability is, by the rubric at `categories.py:40`, severity 5, so the one filter meant to catch it lets it through.

## 2. Shared gap steps

Referenced by label below.

- **G0 Artefact classes in the inventory (M).** Second walk in `inventory.py` producing `artefacts: {class: [{path, loc, churn, last_commit, size_bytes}]}` with classes `manifest` (package.json, pyproject.toml, requirements*.txt, go.mod, Cargo.toml, Gemfile, *.csproj, pom.xml, build.gradle*), `lockfile` (package-lock.json, yarn.lock, pnpm-lock.yaml, poetry.lock, uv.lock, go.sum, Cargo.lock, Gemfile.lock, packages.lock.json), `runtime_version` (.python-version, .nvmrc, .tool-versions, .ruby-version, global.json, rust-toolchain*), `ci` (.github/workflows/*.yml, .gitlab-ci.yml, azure-pipelines.yml, .circleci/config.yml, Jenkinsfile), `build` (Makefile, justfile, Taskfile.yml, *.sh, *.ps1), `container` (Dockerfile*, docker-compose*.yml, .devcontainer/*), `iac` (*.tf, *.tfvars, *.hcl, *.bicep, Chart.yaml, YAML with `apiVersion:` and `kind:`), `notebook` (*.ipynb), `sql` (*.sql, migrations/, alembic/versions/, db/migrate/, *.prisma), `model_binary` (*.pkl, *.pt, *.h5, *.onnx, *.safetensors, *.joblib; size and LFS-pointer status only, never opened), `config` (remaining *.yml, *.yaml, *.json, *.toml, *.ini, *.cfg, .env*), `governance` (CODEOWNERS, SECURITY.md, CONTRIBUTING.md, PULL_REQUEST_TEMPLATE*, dependabot.yml, renovate.json, docs/adr/**). Leave `files`, `total_files` and `languages` untouched so `tests/test_inventory.py:12,23,31` hold. Add fixture `tests/fixtures/infra-repo/` with one instance per class plus decoys, and an "Artefacts present" header line in `design_writer` emitted only when the key exists so the golden `design.md` stays byte-identical.
- **G1 Git metadata in the inventory (M).** Replace the single log call with `git log --since=<window> --name-only --pretty=format:'%H%x09%aN%x09%aI'` parsed into per-file `authors`, `top_author_share`, `last_commit`, and a repo-wide per-author last-active date; for hotspot files only, `git blame -w --line-porcelain <path>` for `top_author_line_share`. Add `branches` (`git for-each-ref --format='%(refname:short)%09%(committerdate:iso8601)' refs/heads refs/remotes`, merged state via `git merge-base --is-ancestor`) and `tags` (`git tag --sort=creatordate --format='%(refname:short)%09%(creatordate:iso8601)'`). Put new fields on `files` entries, not hotspot entries, because `test_inventory.py:72` pins the hotspot key set.
- **G2 Tools probe (M).** New `scripts/tools_probe.py`: `shutil.which` each tool, run those present with JSON output into `.tech-debt/tools/`, and write a manifest marking each tool `ran`, `absent` or `failed`. Tool-derived findings are tier A; a family with no tool present renders as "not assessed" in `design.md`. Add the command to SKILL.md so `skill_check.py` lints it.
- **G3 Extend `VALID_DEBT_TYPES` (S).** Add `security`, `infrastructure`, `knowledge-process`, `data`, `ml-ai`, `performance`; update the value lists at `categories.py:52-53`, `build_synthesis_prompt.py:98-99` and SKILL.md lines 33-36. `tests/test_validation.py:51-53` is parametrised over the set and passes unchanged.
- **G4 Category registration (S each).** New prompt in `CATEGORY_PROMPTS`, `EXPECTED` updated in `tests/test_categories.py:5-14`, a `CORE_CATEGORIES` decision. Prompts must avoid `def `, `import `, `.py file` and `Python module` (`test_categories.py:41`) and end with `_OUTPUT_SCHEMA`. SKILL.md says "eight" in Step 2 and the token budget; `tests/test_e2e.py:3` still says "six scouts".
- **G5 Earned tiers (M, owned by the ranking redesign).** Tool or deterministic-script facts are tier A; LLM-read structural facts whose quoted line the verifier finds are tier B; LLM inference about currency, vulnerability, staleness, rollout state or who is on the team is reported as "not assessed", never as a finding.

## 3. Per-type analysis

### TD-02 Outdated, vulnerable, unmaintained or EOL dependencies (rank 2)

**Verdict: PARTIAL.** The `dependency-debt` prompt (`categories.py:142-159`) names the manifests to inspect (144-146) and asks for "Dependencies pinned far behind their current major version, or to a version with known end-of-life or security advisories you can identify" (147-148), abandoned packages (149), duplicate-purpose packages (150-151), vendored copies (152), deprecated API usage (153) and "Manifest vs lockfile drift, or a missing lockfile entirely" (154). Those manifests are not inventoried, so the scout has no churn or date for them. The manifest-level checks are specific enough for an LLM; the staleness and advisory checks are exactly what the reference architecture forbids without a tool, and the low-confidence caveat is defeated by the severity-5 exception. `debt_type: dependency` fits.

| Symptom | Status | Pointer |
|---|---|---|
| Versions several majors behind | searched, unverifiable by reading | 147-148 |
| Lockfile untouched for a year | files-not-inventoried | inventory.py:216 |
| EOL runtime in .python-version, .nvmrc, Dockerfile FROM, engines | not searched; files-not-inventoried | |
| Floating ranges or no lockfile | searched implicitly (missing lockfile only) | 154 |
| One library at several versions | searched implicitly (lockfile drift) | 154 |
| Vendored library copies | searched | 152 |
| No Dependabot or Renovate config, or PRs unmerged | not searched; files-not-inventoried | |
| "old version", "legacy" comments | not searched | |

**Gap steps.**
1. G0 `manifest`, `lockfile`, `runtime_version`, `governance` so the scout receives lockfile age, runtime-version files and Dependabot or Renovate presence (S after G0).
2. G2 with `osv-scanner --format json -r .` as primary (one binary reads every lockfile ecosystem), then `npm outdated --json`, `pip-audit -f json`, `dotnet list package --outdated --format json`, `cargo outdated --format json`, `go list -m -u -json all` when present; EOL via the endoflife.date API, not assessed offline (M).
3. Prompt rewrite: delete "or to a version with known end-of-life or security advisories you can identify"; add runtime-version files, floating ranges and Dependabot or Renovate absence; emit structural facts only when no tool ran (S).
4. Remove or restrict to tier A the severity-5 exception at `build_synthesis_prompt.py:200` (S, part of G5).
5. Fixture: `package.json` with a caret range and no lockfile, an old `.nvmrc`, and a pinned-and-locked Python decoy (S).

**Risk.** Never assert a CVE, EOL date or "N majors behind" from model memory. Two apparently redundant packages may be a deliberate migration (TD-06); report the pair and let the verifier look for a migration marker.

### TD-03 Security weaknesses in code and config (rank 3)

**Verdict: ABSENT.** No prompt asks for any security symptom; the word appears once, as a rubric level (`categories.py:40`). No `security` debt type exists, so a found secret must be filed as `code`.

| Symptom | Status |
|---|---|
| Hard-coded secrets in source, .env, CI YAML or git history | not searched; .env and CI files-not-inventoried |
| String-built SQL | not searched |
| eval, subprocess shell=True, unsafe deserialisation | not searched |
| Disabled TLS verification, weak crypto, permissive CORS | not searched |
| nosec or eslint-disable on security rules | not searched |
| No SECURITY.md | not searched; files-not-inventoried |
| No secret or dependency scanning in CI | not searched; files-not-inventoried |
| Containers as root | not searched; files-not-inventoried |
| CWE Top 25 pattern classes | not searched |

**Gap steps.**
1. G3 `security`; G4 a `security` category, on by default given rank 3 (S).
2. Prompt limited to the pattern-level classes the taxonomy marks LLM-readable: credentials in source, `.env` and CI files; SQL or shell built by concatenation; eval and unsafe deserialisation; TLS verification off; deprecated hash and cipher names; wildcard CORS; suppression comments on security rules; no `SECURITY.md`; no scanning job in the `ci` artefacts; Dockerfiles without `USER`. Require a verbatim quote with any secret value redacted (M).
3. G2 with `gitleaks detect --report-format json`, `trivy fs --scanners vuln,secret,misconfig --format json .`, `semgrep --config p/security-audit --json`, `bandit -f json -r .`; tool hits are tier A and merge with scout hits by file and line (M).
4. Fixture: a key in a `.env.example` decoy, a real-looking key in `config.py`, and a `cursor.execute("... " + user_input)` line (S).

**Risk.** Secrets are the highest false-positive class: fixtures, examples and public keys look like credentials. The verifier checks path class and entropy, and the report never prints the matched value. Taint-flow classes need CodeQL or Semgrep; the scout must not claim exploitability, and the category stays read-only.

### TD-14 CI pipeline, build and developer-tooling debt (rank 14)

**Verdict: ABSENT.** No prompt mentions CI, workflows, Makefiles or setup. Workflow YAML, Makefiles, shell scripts and container files are not inventoried, and `DEFAULT_IGNORE` drops `build/` and `bin/`. The `duplication` prompt (79-89) could in principle catch copy-pasted YAML and `half-finished` (129-141) catches TODO markers, but neither names these files and both are steered to hotspots that contain none of them. `debt_type: build` fits. The taxonomy marks the family "single-line checks", so a script beats a scout.

| Symptom | Status |
|---|---|
| Linters not failing the job; allow-failure; retry-on-failure | not searched; files-not-inventoried |
| No timeout-minutes; mutable runner; no permissions block; no cache | not searched; files-not-inventoried |
| Actions pinned by tag not SHA; deprecated actions | not searched |
| Commented-out jobs; copy-pasted CI YAML | not searched (duplication prompt does not name YAML) |
| Build logic split across Makefile, shell and npm scripts | not searched |
| Over- or under-declared dependencies | not searched |
| Manual build or setup steps in README | not searched (doc-drift at 121-122 asks about stale commands, not manual steps) |
| Several package managers or lockfiles; no devcontainer or compose | not searched |
| "TODO fix when tool supports" | searched implicitly by half-finished (132-133) |

**Gap steps.**
1. G0 `ci`, `build`, `container`, `lockfile`, `governance` (prerequisite).
2. Deterministic `scripts/config_lint.py` over the `ci` class: per job, missing `timeout-minutes`, missing `permissions`, `continue-on-error: true`, `uses:` without a 40-hex SHA, `runs-on` ending in `-latest`, no cache step, commented-out job blocks. Tier A, written straight into the raw-findings channel (M).
3. G2 with `actionlint -format '{{json .}}'` and `zizmor --format json .github/workflows` (S after G2).
4. Optional `pipeline-infra` scout (G4, off by default, on for "deep scan", consistent with the reference architecture keeping this family optional) for the judgment symptoms: duplicated workflow YAML, build logic split across tools, manual README steps, several package managers, no devcontainer or compose. Shared with TD-19, 27 and 33 (M).
5. Fixture: one workflow with no timeout and an unpinned action, one fully compliant decoy (S).

**Risk.** The reference architecture warns against counting lint violations as debt: one aggregated finding per workflow file, severity 2 to 3 unless a permissions or pinning gap sits on a publishing workflow.

### TD-16 Knowledge concentration and bus factor (rank 16)

**Verdict: ABSENT.** The inventory holds no author data and no prompt asks who wrote a file; the architecture prompt's "no single owner" (173) is about configuration. No debt type fits. The reference architecture rates ownership a Must-level signal.

| Symptom | Status |
|---|---|
| One author owns most lines of a file | not searched; no signal |
| Main authors inactive for N months | not searched; no signal |
| Complex hotspots with a single author | not searched; no signal |
| Directories with no CODEOWNERS entry | not searched; files-not-inventoried |
| Low reviewer diversity | not observable (platform review data) |
| All debt issues raised by one developer | not observable (issue tracker) |

**Gap steps.**
1. G1 (prerequisite) and G0 `governance` with a `codeowners.py` helper that reports, per hotspot path, whether any CODEOWNERS rule matches (S).
2. Deterministic generator, no LLM: per hotspot, "knowledge island" when `top_author_line_share >= 0.8` and `authors <= 2`; "former-contributor hotspot" when the top author's last-active date is older than six months; "unowned hotspot" when CODEOWNERS exists and no rule matches. Tier A; severity 3, 4 in the top five hotspots; `debt_type: knowledge-process` (M).
3. Fixture: a temporary git repository built in the test with two authors and known dates (S).

**Risk.** Author identity is noisy: bots, squash-merge authors, name variants without `.mailmap`, and solo-maintainer repositories all look like islands. Apply `.mailmap`, drop `[bot]` authors, suppress the category below three human authors, and word inactivity as "no commits in six months", never "has left".

### TD-19 IaC and container configuration smells (rank 19)

**Verdict: ABSENT.** Dockerfiles, Terraform, Kubernetes and compose YAML are not inventoried and no prompt names them; no `infrastructure` debt type exists. The taxonomy marks this "single-line checks".

| Symptom | Status |
|---|---|
| Unpinned apt, pip, apk; untagged base image; ADD vs COPY; missing pipefail; latest tags | not searched; files-not-inventoried |
| No resource limits; root user | not searched; files-not-inventoried |
| IaC hard-coded secrets, empty passwords, admin-by-default, HTTP without TLS, weak crypto, invalid IP binding | not searched; files-not-inventoried |
| Hard-coded AMI IDs and CIDRs | not searched |
| Terraform without remote state | not searched |
| Duplicated Kubernetes YAML | not searched |
| No IaC for a deployed service | not observable from the repository |

**Gap steps.**
1. G0 `container` and `iac` (prerequisite).
2. Extend `config_lint.py` with the hadolint-equivalent Dockerfile rules (`FROM` untagged or `latest`, `apt-get install` or `pip install` unversioned, `ADD` for local files, piped `RUN` without `set -o pipefail`, no `USER`) and Kubernetes rules (`resources.limits` absent, `image:` with `latest`, `privileged: true`). Tier A (M).
3. G2 with `hadolint -f json`, `checkov -d . -o json`, `trivy config --format json .`, `kube-linter lint --format json` (S after G2).
4. Judgment symptoms (duplicated manifests per service, environment values in IaC, no Terraform backend) go to the `pipeline-infra` scout; G3 `infrastructure`; fixture with one smelly and one clean Dockerfile (S).

**Risk.** Development-only Dockerfiles and local compose files legitimately use `latest` and root; classify by path (`docker-compose.dev.yml`, `.devcontainer/`) and lower severity. IaC secrets belong to TD-03's tool pass; do not report twice.

### TD-23 Process and ownership debt (rank 23)

**Verdict: ABSENT.** Only "TODOs without tickets" is adjacent to an existing instruction: half-finished weighs markers "that name a concrete risk or a date over vague notes" (132-133) but never checks for a ticket reference. Branches, ADR directories, PR templates and CODEOWNERS are neither inventoried nor asked for. Section 5 of the taxonomy keeps only the CODEOWNERS, branch-age and TODO-age proxies; this analysis respects that. No debt type fits.

| Symptom | Status |
|---|---|
| No CODEOWNERS | not searched; files-not-inventoried |
| No debt label or tracking | not observable (issue tracker) |
| TODOs without tickets | searched implicitly (marker found, ticket not checked) at 132-133 |
| Empty ADR directory; no PR template | not searched; files-not-inventoried |
| Many stale, unmerged or long-lived divergent branches | not searched; no branch signal |
| Issues open for years; low review participation | not observable |

**Gap steps.**
1. G0 `governance` and G1 `branches` (prerequisites).
2. Deterministic generator shared with TD-16: "no CODEOWNERS" when absent and three or more human authors; "stale branches" when more than N unmerged branches exceed 90 days (count plus the three oldest); "no ADR or PR template" as one severity-1 informational finding (S).
3. Ticket-reference regex (`#\d+`, `[A-Z]{2,}-\d+`, issue URLs) as a one-line extension of the SATD miner planned for TD-22 in the other slice, reporting the share of markers without a reference (S, depends on that miner).
4. `debt_type: knowledge-process` (G3).

**Risk.** Proxies with weak cost evidence (I = 3): severity 1 to 2, one finding per proxy, excluded from quick wins. Forks and mirrors show stale remote branches that are not the team's; count `refs/heads` and the configured upstream only.

### TD-25 ML model, pipeline and notebook debt (rank 25)

**Verdict: ABSENT.** `.ipynb` files and model binaries are not inventoried; no prompt mentions notebooks, models, training or experiments; the inventory cannot recognise an ML repository. No debt type fits.

| Symptom | Status |
|---|---|
| Notebooks in production paths; out-of-order execution counts; untitled notebooks | not searched; files-not-inventoried |
| Missing dependency pins | searched implicitly by dependency-debt (154) |
| Scripts chaining scripts | not searched |
| Model binaries committed | not searched; files-not-inventoried |
| Hyperparameters hard-coded in many places | not searched (duplication at 84-85 covers repeated literals generically) |
| Experiment flags left in | searched implicitly by dead-code (98) and half-finished (134) |
| No model or data versioning | not searched |
| Feature code duplicated between training and serving | not searched |
| No monitoring hooks | not observable |

**Gap steps.**
1. G0 `notebook` and `model_binary`; a `notebook_stats.py` that reads each `.ipynb` as JSON for cell count, monotonic `execution_count`, and `Untitled*` names (S).
2. Domain gate: enable a `data-ml` scout (G4) only when the inventory shows notebooks, model binaries, or a manifest naming torch, tensorflow, sklearn, xgboost, lightgbm, transformers or mlflow (S).
3. `data-ml` prompt (shared with TD-26 and TD-31): notebooks referenced from production code or CI, scripts invoking scripts by path with no orchestrator, the same hyperparameter literal in several files, feature code present in both training and serving paths, no DVC, MLflow or registry references. Must avoid `import ` and `.py file` (`test_categories.py:41`) (M).
4. G3 `ml-ai`; fixture with a non-monotonic notebook and a small fake `.pkl` (S).

**Risk.** Research repositories are supposed to contain notebooks; only notebooks referenced from non-notebook code or CI are debt. Model staleness and training-serving skew are runtime-only. Model binaries are reported by size and path, never opened.

### TD-26 Data and schema debt (rank 26)

**Verdict: ABSENT.** `.sql` files are not inventoried; migration files in Python, TypeScript or C# are inventoried as code but no prompt asks about migrations, schemas or ORM models. Half-finished's "partially migrated patterns" (137-138) is code migration (TD-06). No debt type fits.

| Symptom | Status |
|---|---|
| Migration history squashed, conflicting or hand-edited | not searched |
| Many nullable or catch-all columns and JSON blobs; no foreign keys | not searched |
| Undocumented tables | not searched |
| ORM models diverging from schema | not searched |
| SQL embedded in strings | not searched (TD-03 covers the injection case) |
| "synchronize with database" comments | searched implicitly by half-finished only if phrased as a marker |
| Hard-coded file paths and dataset versions | not searched |
| No schema validation | not searched |

**Gap steps.**
1. G0 `sql` including migration directories, with migration count and newest date (prerequisite).
2. Deterministic checks where a framework makes them cheap: Alembic multiple heads (more than one leaf in the `down_revision` chain), Django migrations containing `RunSQL` or edited dependencies, Prisma schema with no migrations directory (S).
3. `data-ml` clauses: tables where most columns are nullable or blob-typed, tables with no foreign key, model fields absent from the newest migration, raw SQL strings outside a repository layer, dataset paths or versions as literals (M).
4. G3 `data`; fixture with a two-head Alembic chain and a single-head decoy (S).

**Risk.** Nullable and JSON columns are often intentional (event stores, audit tables): report a table only when more than half its columns qualify and cite the DDL line. Data quality is runtime-only.

### TD-27 Deployment and release-process debt (rank 27)

**Verdict: ABSENT.** Deploy workflows are not inventoried, tags are not mined, and no prompt mentions releases, deploys, rollbacks or version bumps. `debt_type: build` is the nearest fit.

| Symptom | Status |
|---|---|
| Manual deploy runbooks | not searched (doc-drift checks staleness, not manual-ness) |
| No deploy workflow | not searched; files-not-inventoried |
| Hand-made version-bump commits | not searched; no commit-message signal |
| No rollback path | not observable with confidence |
| Environment-specific branches; long-lived hotfix branches | not searched; no branch signal |
| Irregular release tags | not searched; no tag signal |
| Email-only CI notification | not searched |

**Gap steps.**
1. G1 `tags` and `branches`; G0 `ci` (prerequisites).
2. Deterministic: release cadence from tag dates (median and maximum gap when at least five tags exist); `hotfix/*`, `release/*`, `prod` or `staging` branches older than 90 days and unmerged; no workflow whose name or `on:` block contains `release`, `deploy` or `publish` (S).
3. Runbooks and version-bump commits go to the `pipeline-infra` scout at severity 1 (S after that scout exists).

**Risk.** Libraries release rarely by design and internal tools deploy without tags; report cadence only when tags exist and gaps are extreme, and never infer "no rollback path". Thin row (O = 2.5, I = 2.5), off by default in the reference architecture.

### TD-30 Stale feature flags (rank 30)

**Verdict: PARTIAL.** Three prompts touch flags: dead-code "Feature flags or config switches that are always one value" (98), half-finished "Branches behind a flag that was never enabled" (134-135), and architecture "Configuration or feature-flag sprawl with no single owner" (173). The golden raw findings carry "feature flag OLD_CHECKOUT permanently off" under dead-code, so the path works. The clauses are split across three scouts with no shared definition of a flag, so one flag can be reported three times, and age, the taxonomy's primary signal, cannot be produced. No debt type fits; `code` is the fallback.

| Symptom | Status | Pointer |
|---|---|---|
| Checks on flags fully rolled out or disabled everywhere | searched | 98, 134 |
| Release toggles older than about 90 days | not searched (no age signal) | |
| Nested flags | not searched | |
| Flags with no config reference | not searched; config files-not-inventoried | |
| Branches on constants | searched | 98 |
| Feature directories behind permanently-off flags | searched implicitly | 134-135 |

**Gap steps.**
1. One scout only (dead-code) carries the flag clause, naming common SDK calls (`variation(`, `isEnabled(`, `is_active(`, `FEATURE_` environment reads) and asking for the flag name, every check site and its value in every config file; remove the flag lines from the architecture prompt; add a nested-flag line (S).
2. Verifier step: `git log -S<name> --diff-filter=A --format=%aI -- .` per reported flag; "older than 90 days" only from that date (S, needs the verifier stage).
3. G0 `config` so "no config reference" is checkable (S after G0).

**Risk.** Permission and kill-switch flags are permanent by design; exclude names containing `admin`, `kill`, `maintenance` or `permission` unless also constant. Rollout state is not observable.

### TD-31 LLM-specific debt (rank 31)

**Verdict: ABSENT.** No prompt mentions prompts, models, SDKs or output parsing. No debt type fits.

| Symptom | Status |
|---|---|
| Prompts as string literals scattered in code | not searched (duplication covers repeated literals generically) |
| No prompt versioning or tests | not searched |
| Brittle parsing of model output | not searched |
| Pinned or deprecated model names | not searched |
| Retry and cost hacks | not searched |
| Hallucinated imports or file references in generated code | not searched |
| SDK version pins | searched implicitly by dependency-debt |

**Gap steps.**
1. Extend the TD-25 domain gate: enable when a manifest names anthropic, openai, langchain, llamaindex, litellm, the Vercel AI SDK or google-genai (S).
2. `data-ml` clauses: multi-line prompt strings embedded in application code rather than a prompts directory; model identifiers as literals in several files; output parsed by string splitting or regular expressions where structured output or tool use exists; no test exercising a prompt against a recorded response (M, shared prompt).
3. Deprecation is a currency claim: emit the model identifiers found and mark "currency not assessed" unless a repo-provided allowlist or tool confirms (S). G3 `ml-ai`.

**Risk.** Young, largely grey evidence; severity 2 to 3. A model the scout believes deprecated may have been re-released; the TD-02 never-assert rule applies.

### TD-33 Configuration sprawl (rank 33)

**Verdict: PARTIAL.** Only the architecture prompt's "Configuration or feature-flag sprawl with no single owner" (173) addresses it, and every configuration format is outside the inventory. No debt type fits.

| Symptom | Status |
|---|---|
| Sprawling YAML, JSON or env files | searched implicitly (173); files-not-inventoried |
| Duplicated config across environments | not searched |
| Environment-specific values in code | not searched |
| Config keys never read | not searched (dead-code asks about switches always one value, not orphan keys) |
| Hyperparameters as literals | not searched (see TD-25) |
| Config not covered by tests | not searched |
| Config lines approaching source lines | not measurable without inventory |

**Gap steps.**
1. G0 `config` with LOC, so config-to-source ratio becomes a header number (S after G0).
2. Deterministic: for `config/<env>.*` or `*.<env>.yml` families, key and value overlap between environment files; keys never appearing as a string literal in source as orphan candidates, tier B because dynamic access hides readers (M).
3. Move the configuration sentence from the architecture prompt into the `pipeline-infra` scout with environment-values-in-code and duplicated-environment-config clauses; G3 `infrastructure` (S).

**Risk.** Orphan keys share dead code's dynamic-access blind spot; cap at tier B and make the verifier list the access patterns searched. Thin evidence (O = 2, I = 2): one aggregated finding per repository.

### TD-34 Performance and reliability engineering debt (rank 34)

**Verdict: ABSENT.** The architecture prompt's "side-effectful code (network, clock, filesystem)" (171-172) is a testability seam, not a performance symptom. No prompt asks for query patterns, timeouts, pagination or load tests. No debt type fits.

| Symptom | Status |
|---|---|
| N+1 query patterns | not searched |
| Synchronous IO in hot paths | not searched |
| No timeouts or retries on network calls | not searched |
| Unbounded queries | not searched |
| Missing indexes in migrations | not searched; SQL files-not-inventoried |
| No rate limiting; no load tests | not searched |

**Gap steps (if pursued).**
1. Two pattern rules in the deterministic miner: HTTP calls with no timeout (`requests.get(` without `timeout=`, `fetch(` without an abort signal, `HttpClient` without `Timeout`) and ORM query calls inside a loop body. Tier B, severity 2 (M).
2. Everything else needs a profiler or production data: not assessed.

**Risk.** No measured precision and narrative evidence only (O = 1). Out of scope for v2 except the no-timeout rule, which is cheap and has a clear fix.

### TD-35 Observability and logging debt (rank 35)

**Verdict: ABSENT.** No prompt mentions logging, metrics, tracing, correlation IDs or health endpoints. The golden raw findings include "logging setup duplicated per entrypoint" as a duplication finding, the only incidental route; "catch blocks that log nothing" belongs to TD-13 in the code slice. No debt type fits.

| Symptom | Status |
|---|---|
| print or console.log instead of a logger | not searched |
| Inconsistent log formats; no correlation IDs | not searched |
| No metrics or tracing libraries in manifests | not searched; files-not-inventoried |
| No health endpoints | not searched |
| Secrets or PII in logs | not searched (TD-03 catches literal secrets only) |
| Debug logging in production config | not searched; files-not-inventoried |

**Gap steps (if pursued).**
1. Miner rule: count `print(` and `console.log(` in non-test, non-CLI source in a repository that also uses a logger; one aggregated finding with the top five files (S).
2. For a service repository (has `ci` and `container` artefacts and an HTTP framework), no logging, metrics or tracing library is a severity-1 informational finding; `debt_type: infrastructure` (S after G0).

**Risk.** CLIs and scripts print by design. Weakest-evidence row (score 3); out of scope for v2 beyond step 1.

## 4. Summary table

| ID | Name | Rank | Verdict | Symptoms searched / total | Headline gap step | Effort |
|---|---|---|---|---|---|---|
| TD-02 | Outdated dependencies | 2 | PARTIAL | 4 / 8 (2 implicit) | Tools probe (osv-scanner and friends), strip advisory claims from the prompt, inventory manifests and lockfiles | M |
| TD-03 | Security weaknesses | 3 | ABSENT | 0 / 9 | New `security` scout (pattern classes only) plus gitleaks, trivy and semgrep probe; `security` debt type | M |
| TD-14 | CI, build, tooling | 14 | ABSENT | 1 / 9 (implicit) | Inventory `ci` and `build` classes; deterministic `config_lint.py`; actionlint and zizmor probe | M |
| TD-16 | Knowledge concentration | 16 | ABSENT | 0 / 6 (2 not observable) | Author and recency signals (G1); deterministic knowledge-island generator; CODEOWNERS matching | M |
| TD-19 | IaC and container smells | 19 | ABSENT | 0 / 7 (1 not observable) | Inventory `container` and `iac`; Dockerfile and Kubernetes rules in `config_lint.py`; hadolint and checkov probe | M |
| TD-23 | Process and ownership | 23 | ABSENT | 1 / 6 (implicit; 3 not observable) | Governance-file presence and stale-branch counts from G0 and G1; ticket-reference check on SATD markers | S |
| TD-25 | ML pipeline and notebooks | 25 | ABSENT | 2 / 9 (implicit) | Inventory notebooks and model binaries; domain-gated `data-ml` scout | M |
| TD-26 | Data and schema | 26 | ABSENT | 1 / 8 (implicit) | Inventory `sql` and migrations; Alembic and Django head checks; `data-ml` clauses | M |
| TD-27 | Release process | 27 | ABSENT | 0 / 7 (1 not observable) | Tag cadence and long-lived environment branches from G1; deploy-workflow presence from G0 | S |
| TD-30 | Stale feature flags | 30 | PARTIAL | 3 / 6 (1 implicit) | Consolidate flag clauses into one scout; flag age via `git log -S` in the verifier | S |
| TD-31 | LLM prompt debt | 31 | ABSENT | 1 / 7 (implicit) | Domain-gated `data-ml` clauses; never assert model deprecation | M |
| TD-33 | Configuration sprawl | 33 | PARTIAL | 1 / 7 (implicit) | Inventory `config`; environment-file key-overlap script; move clause to `pipeline-infra` | M |
| TD-34 | Performance and reliability | 34 | ABSENT | 0 / 6 | No-timeout pattern rule only; the rest not assessed | S (rule only) |
| TD-35 | Observability | 35 | ABSENT | 0 / 6 | print and console.log aggregate rule only | S (rule only) |

## 5. Cross-cutting observations

**One inventory change unblocks eleven types.** TD-02, 03, 14, 19, 23, 25, 26, 27, 30, 33 and 35 each have a symptom that lives in a file the inventory refuses to list. G0 is the highest-leverage step in the slice, and it lets `design.md` say "no CI, container or IaC artefacts present; those families were not assessed", a truthful negative rather than silence.

**One git change unblocks four.** TD-16, 23 and 27 need authorship, dates, branches and tags (G1); TD-30 needs `git log -S` for flag age. The reference architecture already rates ownership a Must-level corroborator for architecture findings, so G1 is shared cost with the other slice.

**Most of this slice is script work, not prompt work.** TD-14, 16, 19, 23, 27 and most of TD-33 are single-line or counting checks. Scripts give tier-A findings, deterministic re-runs and no token cost, and reserve the scouts for judgment calls (copy-pasted pipelines, knowledge islands that matter, schema design), mirroring the reference architecture's split between stages 1 to 3 and stage 5.

**The tools probe is the only honest route to currency claims.** TD-02, 03 and 31 contain currency or vulnerability symptoms. The current prompt invites the model to assert them and relies on a confidence flag that the severity-5 exception disables. Until G2 exists, delete the invitation from the prompt.

**Three new scouts, two of them gated.** A default-on `security` scout; an optional `pipeline-infra` scout for TD-14, 19, 27 and 33; a domain-gated `data-ml` scout for TD-25, 26 and 31 that never runs without notebooks, models, SQL or an LLM SDK present. The default scan grows from eight scouts to nine; a deep scan on an ML service repository runs eleven.

**Vocabulary and tests.** Six debt-type additions (G3) cover the slice with no test edits. Each new category must be added to `test_categories.py` in the same commit, with the "eight" count in SKILL.md and the "six scouts" docstring in `test_e2e.py` corrected.

## 6. Priority order and exclusions

Ordered by taxonomy rank against effort, prerequisites first.

1. **G0 artefact classes and G3 debt types** (M + S): prerequisite for everything below.
2. **TD-02** (rank 2): prompt rewrite and severity-5 fix are S and can land before the probe; G2 with osv-scanner follows (M).
3. **TD-03** (rank 3): `security` scout plus gitleaks, trivy and semgrep probe (M). Highest importance score in the slice with zero coverage.
4. **G1 git metadata** (M), then the **TD-16** generator (M): the ownership signal also serves the architecture family.
5. **TD-14 and TD-19** together via `config_lint.py` (M): the cheapest tier-A findings in the taxonomy.
6. **TD-30** consolidation and **TD-23 and TD-27** proxies (S each): small, riding on G0 and G1.
7. **TD-25, 26 and 31** behind the domain gate (M for the shared scout): apply to a minority of repositories.
8. **TD-33** environment-overlap script (M): last, thin evidence.

**Recommended out of scope for v2**, consciously rather than as coverage gaps:

- **TD-34 performance and reliability**, except the no-timeout rule: narrative evidence only, everything else needs a profiler or production data.
- **TD-35 observability**, except the print-versus-logger aggregate: lowest score in the taxonomy; log formats, alert noise and PII in logs are runtime or judgment questions with no measured precision.
- **Runtime-only aspects of retained rows**, per taxonomy section 5: exploitability, EOL without a registry, flag rollout state, infrastructure drift, deploy frequency, model staleness, data quality. Emit the leading indicator and the label "not assessed".
- **Non-repository signals in TD-16 and TD-23**: reviewer diversity, issue-tracker labels, who is still employed. Git proxies only, worded as proxies.
- **TD-27 beyond tag cadence and long-lived environment branches**: "no rollback path" and "manual runbook" are not reliably readable, and the family is off by default in the reference architecture.
