---
name: karate-bootstrap
description: Bootstrap a first ground-truth Karate integration-test suite that runs green under Testcontainers for a Spring Boot, Quarkus, ASP.NET Core or Python service that has no Karate tests. Use when asked to add karate tests, bootstrap integration tests, or build a testcontainers suite for a service or repo. Not for unit tests.
triggers:
  - /karate-bootstrap
---

# karate-bootstrap

Takes a service repository with no Karate tests and leaves it with a first "ground truth"
suite under `karate-tests/` that runs green under Testcontainers, locally and in Azure DevOps.
The suite documents the behaviour the service has today; suspected defects are quarantined
and reported, never fixed. Scripts do every deterministic step (discovery, the ledger, gates,
scaffolding, report parsing, git checkpoints); you do the judgement inside narrow subagent
tasks (tracing code paths, confirming validation rules, writing features) and the fix loop.

Read `reference/testcontainers-notes.md` once before a run. Read the stack cheat sheet the
ledger names (`reference/stack-<stack>.md`) when you dispatch the first trace. Read
`reference/failure-triage.md` before the first fix iteration.

## No improvisation

If any expected output file from a numbered step is missing, abort with exit 5. Do not retry
steps you were not told to retry. Do not edit `flow-map.yaml`, `rules/*.csv` or
`kb-runtime.json` by hand: every change goes through a script. Do not compose a subagent
prompt yourself: render it with `kb_prompt.py`. Never edit the application's source, its
Dockerfile or its pipeline. Never push.

## Invocation

```
/karate-bootstrap <repo-path> [--service-dir <sub>] [--migrations-image <ref>] [--app-image <tag>]
                  [--max-iterations 15] [--double-trace] [--no-commit]
```

| Flag | Effect |
|------|--------|
| `--service-dir <sub>` | The service lives in a sub-directory of the repo (monorepo). Pass it to every script that accepts it; `<root>` below means `<repo-path>/<sub>`. |
| `--migrations-image <ref>` | The db-manager image that owns the schema. Without it the scaffold looks the database up in `~/.karate-bootstrap/config.yaml` and aborts with exit 4 when nothing matches. |
| `--app-image <tag>` | Test a prebuilt image instead of building the Dockerfile: adds `-Dapp.image=<tag>` to every Maven run. |
| `--max-iterations <n>` | Fix-loop cap (default 15). |
| `--double-trace` | Trace every entry twice with independent subagents and merge both results; disagreements get a third, narrower trace. |
| `--no-commit` | Write files only; pass `--no-commit` to every `kb_checkpoint.py` call so git is never touched. |

## Conventions

- Run every `python scripts/...` command from this skill's directory (`skills/karate-bootstrap/`)
  so the relative script paths resolve; scripts are direct-path invocable, no package install.
  Pass `<root>` as an absolute path.
- `<tests>` is `<root>/karate-tests`. Every artefact the run produces lives there. Rendered
  prompts go to `<tests>/.prompts/` (ignored by the template's `.gitignore`).
- `<skill>` is this skill's absolute directory; `templates/karate-tests/README.md.tmpl` is
  referenced relative to it.
- Maven runs from `<tests>`: `mvn -B test` (JDK 17 or newer and a container engine on the
  machine; `./mvnw -B test` when Maven is not installed). Append `-Dapp.image=<tag>` when
  `--app-image` was given. Podman users: `reference/podman.md`.
- Every step names one command and one output. A step's postcondition is the file it must
  leave behind.

## Exit codes

| Code | Meaning |
|-----:|---------|
| 0 | Suite green (or green with quarantined defects listed in `defects.md`). |
| 2 | A gate or script rejected its input; the message names the gap. |
| 3 | Unsupported stack (not Spring Boot, Quarkus, ASP.NET Core or a Python web framework). |
| 4 | No schema source: no `--migrations-image` and no matching central config entry. |
| 5 | An expected output file is missing (the no-improvisation rule). |
| 6 | Stopped by a stop condition after committing what exists. |
| 7 | Container runtime, JDK 17+ or Maven missing on this machine. |

## Subagents

Three kinds, each driven by a prompt file `kb_prompt.py` renders for one entry. Read the
rendered file and pass its complete text as the subagent's prompt; add nothing, remove nothing.

| Kind | Agent | May write | Returns |
|------|-------|-----------|---------|
| trace | read-only (Explore) | nothing | JSON matching the ledger entry schema |
| rules | read-only (Explore) | nothing | JSON with `csv` (header plus rows), `rows`, `dropped_candidates`, `notes` |
| generate | general-purpose | files under `<tests>` only (`features/`, `stubs/`, `seed/`) | JSON listing the files written |

Save every JSON reply to `<tests>/.prompts/<kind>-<slug>.json` before you feed it to a script.
Dispatch trace subagents one at a time unless `--double-trace` asks for pairs.

## Workflow

### Step 0: Preflight

- Prerequisite: `<repo-path>` exists.
- Commands:

```bash
python scripts/kb_checkpoint.py begin --repo <repo-path>
python scripts/detect.py <root> --service-dir <sub> --out <tests>/stack.json
```

- `begin` creates and checks out `karate-bootstrap` when the repo is on its default branch and
  leaves any other branch alone. Add `--no-commit` when the flag was given (then it does
  nothing). `detect.py` checks the container runtime, JDK and Maven, then classifies the
  stack; omit `--service-dir` when there is none. Exit 7 means the machine cannot run
  Step 7: stop and report what is missing. Add `--skip-toolchain` only when the user asked
  for a dry run that stops before Step 7 (Steps 0 to 6 need no toolchain).
- Postcondition: `<tests>/stack.json`. Exit 3 or 7 from `detect.py` ends the run with that code.

### Step 1: Discover

- Prerequisite: `<tests>/stack.json`.
- Command:

```bash
python scripts/discover.py <root> --stack <tests>/stack.json --out-env <tests>/env-map.json --out-ledger <tests>/flow-map.yaml
```

- Postcondition: `<tests>/env-map.json` (config keys with roles, port, readiness, auth mode)
  and `<tests>/flow-map.yaml` seeded with one untraced entry per entry point.

### Step 2: Confirm entry points and auth

- Prerequisite: the two files from Step 1.
- Open `<tests>/flow-map.yaml` and the routes in the code once. For every entry point the
  regexes missed (a route, a listener), add it:

```bash
python scripts/flow_map.py add-entry --ledger <tests>/flow-map.yaml --id "<METHOD> <path>" --kind http --handler <file:line> --method <METHOD> --path <path>
python scripts/flow_map.py add-entry --ledger <tests>/flow-map.yaml --id "amq <destination>" --kind amq-subscribe --handler <file:line> --destination <destination> --type queue
```

- Verify `app.auth` yourself even when `discover.py` wrote `confirmed: true`: it guesses
  `disabled` from a config key such as `app.security.enabled` without proving the code reads
  it. Grep the source for that key (cheat sheet: "Auth switches"). When nothing reads it, or
  the mode is otherwise wrong, read the security configuration and record what you found:

```bash
python scripts/flow_map.py set-auth --ledger <tests>/flow-map.yaml --mode disabled --key <ENV_VAR> --value <off-value>
python scripts/flow_map.py set-auth --ledger <tests>/flow-map.yaml --mode jwks --issuer-keys <ISSUER_ENV>,<JWKS_ENV>
```

  Use `--mode none` when the app has no auth and `--mode blocked` when it cannot be switched
  off or pointed at a test issuer.
- Postcondition: `<tests>/flow-map.yaml` lists every entry point and `app.auth.mode` is one you
  verified against the code (`disabled` additionally carries `key`, `value` and
  `confirmed: true`; `jwks` carries `keys`; `none` and `blocked` carry only the mode).

### Step 3: Trace every entry point

- Prerequisite: `<tests>/flow-map.yaml`, `<tests>/env-map.json`.
- Loop until `next` prints `{"done": true}`:

```bash
python scripts/flow_map.py next --phase traced --ledger <tests>/flow-map.yaml
python scripts/kb_prompt.py render --prompt trace --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --out <tests>/.prompts/trace-<slug>.md
python scripts/flow_map.py merge <tests>/.prompts/trace-<slug>.json --ledger <tests>/flow-map.yaml
```

  Between `render` and `merge`, dispatch the trace subagent with the rendered prompt and save
  its reply as `<tests>/.prompts/trace-<slug>.json` (`merge` accepts the bare object or one
  wrapped in a code fence). `next` prints the entry id, its
  handler and the cheat sheet path; `<slug>` is the id lower-cased with non-alphanumerics
  collapsed to `-` (`POST /api/deals` becomes `post-api-deals`).
- If `merge` reports `unresolved: N` above zero, re-render with the first unresolved location
  and dispatch again, then merge again; repeat until the entry merges with zero unresolved:

```bash
python scripts/kb_prompt.py render --prompt trace --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --focus <file:line> --out <tests>/.prompts/trace-<slug>-2.md
```

- With `--double-trace`: dispatch two independent subagents from the same rendered prompt,
  merge the first reply, then merge the second (the ledger keeps the union of exits; a `via`
  present in only one reply is a disagreement to resolve with a third, `--focus` trace).
- Gate:

```bash
python scripts/flow_map.py validate --phase traced --ledger <tests>/flow-map.yaml --repo <root> --env <tests>/env-map.json
```

  The gate also runs `verify-refs`: every exit's `via` must sit within three lines of a marker
  token from the cheat sheet, or the entry is reset to untraced. On any gap, go back to the loop
  for the entries it names. Do not edit the ledger to silence a gap.
- Postcondition: `validate --phase traced` prints `phase traced: pass`.

### Step 4: Validation rules

- Prerequisite: the traced ledger.
- Command:

```bash
python scripts/kb_rules.py extract <root> --ledger <tests>/flow-map.yaml --out-dir <tests>
```

- For every entry whose `rules.sources` has a file with `scanned: false`, render the rules
  prompt for that source, dispatch a read-only rules subagent, save the `csv` field of its
  JSON reply as `<tests>/rules/<slug>-<n>.rows.csv` (the header line is included; `<n>` is the
  same 1-based source number as the rendered prompt, so an entry with two sources leaves two
  rows files), then append the rows and mark the source scanned:

```bash
python scripts/kb_prompt.py render --prompt rules --ledger <tests>/flow-map.yaml --entry "<id>" --source <source-file> --repo <root> --tests-dir <tests> --out <tests>/.prompts/rules-<slug>-<n>.md
python scripts/kb_rules.py add "<id>" <tests>/rules/<slug>-<n>.rows.csv --ledger <tests>/flow-map.yaml --out-dir <tests>
python scripts/kb_rules.py mark-scanned "<id>" <source-file> --ledger <tests>/flow-map.yaml
```

  `add` de-duplicates on field, mutation and value and assigns `rule_id`s; run it once per
  rows file even when the file is empty of new rows.
- Postcondition: every entry with validation responses has `rules.file` and a `rules.count`
  matching its CSV, and every source is `scanned: true`. The generated gate in Step 6 checks
  this.

### Step 5: Scaffold the module

- Prerequisite: the traced ledger and `<tests>/env-map.json`.
- Command:

```bash
python scripts/kb_scaffold.py <root> --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --out <tests> --migrations-image <ref>
```

  Omit `--migrations-image` to resolve the image from `~/.karate-bootstrap/config.yaml`
  (`--config <path>` points elsewhere). Exit 4 means no schema source: stop and report it.
  Add `--force` only when re-scaffolding a module whose harness files you intend to refresh;
  generated content is never overwritten either way.
- Postcondition: `<tests>/pom.xml`, `<tests>/src/test/resources/kb-runtime.json`, the harness
  classes and `<tests>/defects.md`. Then:

```bash
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 5 --message "scaffold the Karate module"
```

### Step 6: Generate features

- Prerequisite: the scaffolded module and the rules files.
- Loop until `next` prints `{"done": true}`:

```bash
python scripts/flow_map.py next --phase generated --ledger <tests>/flow-map.yaml
python scripts/kb_prompt.py render --prompt generate --ledger <tests>/flow-map.yaml --env <tests>/env-map.json --entry "<id>" --repo <root> --tests-dir <tests> --out <tests>/.prompts/generate-<slug>.md
python scripts/flow_map.py mark --entry "<id>" --generated --feature features/<slug>.feature --stub stubs/<downstream>/default.json --seed seed/<slug>.sql --ledger <tests>/flow-map.yaml
```

  Between `render` and `mark`, dispatch the generate subagent (general-purpose, may write only
  under `<tests>`) and save its JSON reply as `<tests>/.prompts/generate-<slug>.json`. Pass
  every path from the reply's `features`, `stubs` and `seeds` lists to `mark` (repeat
  `--feature`, `--stub`, `--seed` as needed; omit a flag whose list is empty). Features are
  recorded relative to `src/test/resources`; `mark` trims that prefix when a reply includes it.
- Gate:

```bash
python scripts/flow_map.py validate --phase generated --ledger <tests>/flow-map.yaml --repo <root> --tests-dir <tests>
```

  Gaps name the entry and what is missing (a feature, a `Db.` assertion for a written table, a
  `Jms.` assertion for a published destination, a `Stubs.verify` for an outbound call, a rules
  count mismatch, an exclusive-state call without `@parallel=false`). Re-dispatch the generate
  subagent for that entry with the gap text appended to the rendered prompt, then `mark` and
  validate again.
- Postcondition: `validate --phase generated` prints `phase generated: pass`. Then:

```bash
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 6 --message "generate features, stubs and seeds"
```

### Step 7: First run

- Prerequisite: the generated gate passed.
- Self-test first, from `<tests>`: `mvn -B test -Dkb.skipContainers=true`. It compiles the
  module and runs the harness smoke feature without containers. A failure here is a scaffold
  or environment problem (JDK, Maven Central): fix the environment or report exit 7; never
  edit the Java.
- Full run, from `<tests>`: `mvn -B test` (plus `-Dapp.image=<tag>` when given). The first run
  builds the app image and can take several minutes. Then:

```bash
python scripts/kb_report.py parse --reports <tests>/target/karate-reports --out <tests>/target/report.json
python scripts/flow_map.py record-run --ledger <tests>/flow-map.yaml --report <tests>/target/report.json
python scripts/flow_map.py validate --phase green --ledger <tests>/flow-map.yaml --repo <root> --report <tests>/target/report.json --defects <tests>/defects.md
```

- If Maven produced no `target/karate-reports/*.json` at all, the app never started: treat it
  as an infra failure in Step 8 using `target/app.log` and `target/db-manager.log`.
- Postcondition: `<tests>/target/report.json`. When the green gate passes, go to Step 9.

### Step 8: Iterate until green or stopped

- Prerequisite: `<tests>/target/report.json` with failures.
- Loop:

```bash
python scripts/kb_iterate.py next --report <tests>/target/report.json --tests-dir <tests>
```

  Read the group it prints (the largest failure signature with its evidence) and classify it
  with `reference/failure-triage.md`: infra, stub-or-seed, expectation, or app-defect. Then
  log the iteration before changing anything:

```bash
python scripts/kb_iterate.py log --log <tests>/.iterations.log --signature "<signature>" --hypothesis "<one sentence>" --change "<one sentence>" --classification <class>
```

  Add `--unfixable` to an infra iteration that cannot be fixed from inside `<tests>`.
- Make the one change the hypothesis names, inside `<tests>` only. For an expectation change,
  also record it:

```bash
python scripts/flow_map.py override --ledger <tests>/flow-map.yaml --entry "<id>" --scenario "<scenario>" --field <what> --old "<expected>" --new "<observed>" --reason "<why>"
```

  For a suspected app defect, tag the scenario `@known-defect` and append the `defects.md`
  entry described in `failure-triage.md`; no override.
- Re-run the touched feature from `<tests>`:
  `mvn -B test -Dkarate.options="classpath:features/<slug>.feature"`, then the full
  `mvn -B test`, then:

```bash
python scripts/kb_report.py parse --reports <tests>/target/karate-reports --out <tests>/target/report.json
python scripts/flow_map.py record-run --ledger <tests>/flow-map.yaml --report <tests>/target/report.json
python scripts/kb_iterate.py check-stop --log <tests>/.iterations.log --report <tests>/target/report.json --max-iterations 15
python scripts/flow_map.py validate --phase green --ledger <tests>/flow-map.yaml --repo <root> --report <tests>/target/report.json --defects <tests>/defects.md
```

  `check-stop` prints `continue`, `done`, or `stop:<reason>` with exit 6. Pass the user's
  `--max-iterations` value. On `stop:` go to Step 9 and finish with exit 6. On `done` and a
  passing green gate, go to Step 9. Otherwise loop.
- Postcondition per iteration: a new line in `<tests>/.iterations.log` and a fresh
  `<tests>/target/report.json`.

### Step 9: Report

- Prerequisite: `<tests>/target/report.json` and `<tests>/defects.md`.
- Commands:

```bash
python scripts/kb_report.py summary --ledger <tests>/flow-map.yaml --defects <tests>/defects.md --report <tests>/target/report.json --template templates/karate-tests/README.md.tmpl --out <tests>/README.md
python scripts/kb_checkpoint.py commit --repo <repo-path> --phase 9 --message "first ground-truth Karate suite"
```

- Postcondition: `<tests>/README.md`. Tell the user: the branch and commit, the counts table
  `summary` printed, how many scenarios are quarantined and where `defects.md` is, the auth
  and schema modes used, and how to run the suite (`cd karate-tests && mvn test`). Exit 0 on a
  passing green gate, 6 after a stop condition.

## Token budget

One trace subagent per entry point (a small service has 3 to 10), one rules subagent per
validation source, one generate subagent per entry point, then the fix loop. Budget about 30k
output tokens per entry point for trace, rules and generate together, and 5 to 15k per fix
iteration. Scripts do no LLM work.

## Caveats

- Postgres only; ActiveMQ Artemis over AMQP 1.0 only; downstream HTTP is stubbed, never called.
- The generated suite documents current behaviour. A quarantined scenario is a suspected
  defect for a developer to judge, not a verdict.
- No live LLM in this repo's tests: `kb_check_skill.py` lints these commands and
  `tests/test_kb_dry_run.py` executes the chain with canned subagent replies.
- Windows: `mvn` needs `JAVA_HOME`; the template test in this repo shows the exact value used.
