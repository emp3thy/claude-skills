# karate-bootstrap Plan 2 of 4: Harness and Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the skill everything between "ledger validated" and "suite green": the Karate Maven module it drops into a repo (a real project compiled in this repo's CI), the Testcontainers harness that runs Postgres, Artemis, WireMock, the db-manager and the app, and the four Python scripts that scaffold it, parse its reports, drive the fix loop and checkpoint to git.

**Architecture:** The Java harness under `templates/karate-tests/` is identical for every target repo; `kb_scaffold.py` copies it verbatim and writes one JSON file, `src/test/resources/kb-runtime.json`, that carries every repo-specific value. `Containers.java` reads that file, starts the topology lazily from `karate-config.js`, and substitutes `{{db.host}}`-style tokens into the app's environment. The Python scripts follow Plan 1's conventions: flat direct-path modules with `kb_` basenames, `argparse` subcommands, pinned output files, shared exit codes in `kb_common.py`, no LLM calls anywhere in scripts or tests.

**Tech Stack:** Python 3.11+ with `pyyaml`; pytest, ruff, mypy strict. Java 17 release level compiled on JDK 21: Karate 1.5.2, Testcontainers 1.21.4, WireMock 3.13.2 image over its admin REST API, Qpid JMS 1.17.0 (AMQP 1.0), PostgreSQL JDBC 42.7.13, Nimbus JOSE 9.37.3, Jackson 2.17.2, JUnit 5.10.3, Surefire 3.2.5, Maven wrapper 3.3.2 (only-script) on Maven 3.9.9.

**Spec:** `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` at commit `3c99756` (sections 3 H1 to H8, 4.2, 4.3, 5.5 to 5.8, 9, 10, 12 were amended for this plan on 2026-09-05 and approved).

**Phasing:** Plan 1 (analysis core) landed as PR #7. This is Plan 2 of 4 (spec decision H8). Plan 3 covers skill assembly: `SKILL.md`, `prompts/*.md`, `reference/*.md`, `kb_check_skill.py`, the dry-run eval. Plan 4 covers the three fixture apps with db-manager images and container-backed end-to-end evals. This plan supersedes the draft committed as `5e84d6c`, which was written before the harness brainstorm and spike; that file is overwritten by this one.

## Guardrails

Surfaced from better-memory (planning and implementation phases), the `standards/ralph-runtime.md` knowledge document, and this session's Plan 1 execution before any task was drafted. Tasks reference these by anchor.

- **[[planning-memory-first]]** (reflection mem-34049f47, confidence 0.9, used 29x): planning and implementation memories plus the standards document were retrieved before drafting. This section is the output of that retrieval, not a retrofit.
- **[[confidence-gate]]** (standards, non-skippable): every task carries a confidence percentage with the evidence that earns it. Nothing in this plan sits below 90%. The evidence is either a fact proven in today's JVM spike or a code site read at plan-write time; the summary table names which.
- **[[docs-in-sync]]** (reflection mem-f3ce58e6, confidence 0.95, evidence 7, used 30x): a CLI flag, output file or exit code that is added or renamed is updated in the module docstring and in the spec command line in the same task. Every script task ends with a step that runs the exact spec command's `--help` so the flags in spec sections 5.5 to 5.8 provably exist. `SKILL.md` does not exist yet; Plan 3's `kb_check_skill.py` lints it later.
- **[[spec-code-lint]]** (standards): copied test or script code is not lint-clean by default. Every task ends with `ruff check .` and `mypy` before commit. Watch F401 unused imports, UP017 (`datetime.UTC`), B905 (`zip(strict=...)`), SIM108, and E501 at 100 columns.
- **[[cross-read]]** (standards): prose and code blocks in this plan were cross-read in self-review. Where a code block and a sentence disagree, the code block wins and the sentence is the bug: report it, do not pick silently.
- **[[stage-by-path]]** (Plan 1 incident, 2026-09-05): a fix-round commit swept `.superpowers/brainstorm/**` into git because the worktree's `.gitignore` predated the rule. `git add` names explicit paths only. Never `git add -A`, `git add .`, or `git commit -a`.
- **[[unique-module-names]]** (Plan 1, spec section 9): both skills' `tests/conftest.py` put their `scripts/` directory on one `sys.path`, and `mypy_path` lists both. Every new module here is `kb_`-prefixed: `kb_features.py`, `kb_scaffold.py`, `kb_report.py`, `kb_iterate.py`, `kb_checkpoint.py`; tests are `test_kb_*.py`. No `__init__.py` under `skills/karate-bootstrap/tests/`.
- **[[worktree-git]]** (Plan 1 execution): the Bash tool's worktree guard refuses compound commands that contain `git -C`, `cd ... && git`, or shell variables next to `git`. Run plain `git ...` commands, one per invocation, from the worktree root `C:\Users\gethi\source\claude-skills\.claude\worktrees\karate-testcontainers`.
- **[[maven-needs-java-home]]** (spike, 2026-09-05): `mvnw.cmd` exits 1 with `The JAVA_HOME environment variable is not defined correctly` when `JAVA_HOME` is unset, even on a machine with a JDK installed. On this machine the JDK is `C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot`. The Maven-marked pytest fails fast with that text rather than skipping; set `JAVA_HOME` before running it.
- **[[verify-red]]** (reflection mem-66b096bf, confidence 0.75): before claiming a test fails, confirm the failure is the expected one (`ImportError` or `AttributeError` for missing code, an assertion on the new behaviour for a regression), not a typo. Task 1 names the one test that is a regression guard rather than a true red.

Dismissed as not applicable, with reasons: Playwright text matching (no browser tests); `tempfile.mkstemp` fd leak (no temp files are opened by fd; `kb_checkpoint.py` shells out to git only); TypeScript `Partial<T>` (no TypeScript); paired enter/exit freeze logging (no hang risk in pure-data scripts); "ralph-queue means ralph builds it" (the user is executing this plan interactively, not queueing it).

## Task confidence summary

| Task | Deliverable | Confidence | Evidence and embedded mitigation |
|------|-------------|-----------:|----------------------------------|
| 1 | Plan 1 backlog fixes | 93% | Each code site (`kb_common.py:49`, `discover.py:376`, `kb_rules.py:156`) read at plan time; each fix has a failing test first; the one regression-guard test is named as such |
| 2 | `kb_features.py`, `flow_map.py set-auth`, parallel-safety gate | 92% | Pure text parsing pinned by tests; `set-auth` mirrors the existing `mark` subcommand; the traced gate already emits the unconfirmed-switch gap this command clears |
| 3 | Template Maven module, Maven-marked pytest, CI job | 92% | Every file compiled and ran green today in the spike on JDK 21 (dynamic CSV outline, `rules/` as root-level test resource, cucumber JSON and JUnit XML emitted); the pytest wrapper is a subprocess call |
| 4 | Harness classes: `Containers`, `Db`, `Jms`, `Stubs`, `Jwt`, `reset.feature`, JUnit tests | 93% | The exact Java in this task compiled and its 13 JUnit tests plus the 6-scenario smoke feature passed today in the spike (`mvn clean test -Dkb.skipContainers=true`, exit 0), including `reset.feature` called with and without arguments; the lift caught and fixed one wrong ordering assertion in `JmsTest`. Residual risk is the live topology, which Plan 4 exercises by design |
| 5 | `kb_scaffold.py` | 93% | The code and 23 of its tests in this plan ran today against the real `env-map.json` and seeded `flow-map.yaml` that Plan 1's scripts produce for `spring-mini` and `dotnet-mini`; the copy rules ran against a stand-in template. Only the CLI test that needs the Task 3 template was not run |
| 6 | `kb_report.py parse` and `summary`, `README.md.tmpl` | 92% | Cucumber JSON, `karate-summary-json.txt` and JUnit XML shapes captured from a real failing run today; the test fixture in this plan mirrors those fields exactly |
| 7 | `kb_iterate.py next`, `log`, `check-stop` | 91% | Pure data over the report JSON and a JSONL log; no external calls |
| 8 | `kb_checkpoint.py begin` and `commit` | 93% | The exact git sequence ran today on throwaway repos with `main` and `master` defaults on this machine's Windows git; every exit code and output the code relies on was observed |

All eight tasks are at or above 90%, so no task carries a Step 0 spike. Three tasks started at 90% and were lifted by executing their code before this plan was presented (Tasks 4, 5, 8); the evidence is in the Assumptions section at the end of this plan and in spec section 12.

## Global Constraints

Copied from the spec; every task's requirements include this section.

- Python floor `>=3.11`; ruff `target-version = "py311"` with `E,F,I,B,UP,SIM`, line length 100; mypy `python_version = "3.11"`, strict. Only runtime dependency: `pyyaml>=6.0`.
- Scripts are direct-path invocable (`python skills/karate-bootstrap/scripts/<name>.py`), import siblings flatly (`from kb_common import ...`), and carry the `kb_` basename prefix (spec section 9).
- Exit codes (spec section 9, `kb_common.py`): 0 ok, 2 validation failure, 3 unsupported stack, 4 no schema source, 5 missing expected output, 6 stopped by stop condition, 7 container runtime or JDK missing.
- Java: `maven.compiler.release` 17. Pins (spec 5.5): `io.karatelabs:karate-junit5` 1.5.2; `org.testcontainers:testcontainers-bom` 1.21.4 importing `testcontainers`, `junit-jupiter`, `postgresql`; `org.postgresql:postgresql` 42.7.13; `org.apache.qpid:qpid-jms-client` 1.17.0; `com.nimbusds:nimbus-jose-jwt` 9.37.3; `com.fasterxml.jackson.core:jackson-databind` 2.17.2; `org.junit.jupiter:junit-jupiter` 5.10.3; `maven-surefire-plugin` 3.2.5 including `**/*Test.java` and `**/KarateRunner.java`; `ch.qos.logback:logback-classic` 1.5.6. Images: `postgres:16-alpine`, `apache/activemq-artemis:2.44.0-alpine`, `wiremock/wiremock:3.13.2-alpine`. Wrapper 3.3.2 only-script on Apache Maven 3.9.9.
- Java sources are never templated. `src/test/resources/kb-runtime.json` (schema in spec 5.5) is the only repo-specific file. `README.md.tmpl` is the one `string.Template` file.
- Harness package is `kb.harness`. Network aliases and ports: `db:5432`, `artemis:5672` (AMQP) and `61616` (core), `wiremock:8080`; `{{stubs.url}}` = `http://wiremock:8080`, `{{auth.url}}` = `http://wiremock:8080/auth`.
- WireMock admin calls (spec 5.5): `POST /__admin/reset`, `POST /__admin/mappings/import` with `{"mappings":[...]}`, `POST /__admin/requests/count` with a request pattern returning `{"count":n}`, `GET /__admin/requests/unmatched`, `GET /__admin/requests/unmatched/near-misses`, `GET /__admin/health`.
- Runner: `Runner.path("classpath:features").tags("~@known-defect").outputCucumberJson(true).outputJunitXml(true).parallel(Integer.getInteger("kb.threads", 4))`. `-Dkb.skipContainers=true` runs container-free features only.
- Report JSON contract (spec 5.7): `{"passed": int, "skipped": int, "failed": [{"feature", "scenario", "tags", "step", "error"}]}`; `flow_map.py validate --phase green` consumes it unchanged.
- `defects.md` entries are `## DEF-NNN: <title>` blocks with `status`, `slug`, `severity`, `category`, `entry_point`, `scenario`, `evidence`, `root_cause`, `suggested_fix` lines (spec section 7).
- Isolation by data (spec 5.6): suite-level stubs under `stubs/<downstream>/*.json`; a scenario that calls `Stubs.reset`, `Stubs.load` or `Db.truncate`, or passes `stubs:` or `truncate:` to `reset.feature`, must carry `@parallel=false`.
- The skill commits (via `kb_checkpoint.py`) but never pushes. Commits stage `karate-tests/` only.
- Commit messages: Conventional Commits, scope `karate-bootstrap`, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never bypass hooks. [[stage-by-path]] applies to every commit in this plan.
- Work happens on branch `feat/karate-bootstrap-plan-2` in the worktree named under [[worktree-git]].

---

## File Structure

```
skills/karate-bootstrap/
  scripts/
    kb_common.py          (modify: TEST_TREE_NAMES)                          Task 1
    discover.py           (modify: _CLASS_DECL_RE)                           Task 1
    kb_rules.py           (modify: _fluent_statements)                       Task 1
    kb_features.py        (new: grep-level Gherkin blocks, tags, exclusive-state scan)   Task 2
    flow_map.py           (modify: set-auth subcommand, parallel-safety gap in generated gate)  Task 2
    kb_scaffold.py        (new: copy template, write kb-runtime.json)        Task 5
    kb_report.py          (new: parse cucumber JSON, render README)          Task 6
    kb_iterate.py         (new: failure groups, iteration log, stop rules)   Task 7
    kb_checkpoint.py      (new: branch + commit karate-tests/)               Task 8
  templates/karate-tests/                                                    Task 3 unless noted
    pom.xml  mvnw  mvnw.cmd  .mvn/wrapper/maven-wrapper.properties  .gitignore
    azure-pipelines.karate.yml  defects.md
    README.md.tmpl                                                           Task 6
    rules/harness-smoke.csv  stubs/.gitkeep  seed/.gitkeep
    src/test/java/kb/harness/KbRuntime.java  KarateRunner.java
    src/test/java/kb/harness/Containers.java  Db.java  Jms.java  Stubs.java  Jwt.java              Task 4
    src/test/java/kb/harness/ContainersTest.java  JmsTest.java  JwtTest.java  StubsTest.java       Task 4
    src/test/resources/karate-config.js  kb-runtime.json  logback-test.xml  testcontainers.properties
    src/test/resources/common/mutate.js
    src/test/resources/common/reset.feature                                  Task 4
    src/test/resources/features/harness-smoke.feature                        Task 3 (Task 4 appends one scenario)
  tests/
    test_kb_common.py  test_kb_discover.py  test_kb_rules.py  (modify)      Task 1
    test_kb_features.py  test_kb_flow_map.py (modify)                        Task 2
    test_kb_template.py                                                      Task 3 (Tasks 4 and 6 extend the file list)
    test_kb_scaffold.py                                                      Task 5
    test_kb_report.py  fixtures/karate-reports/*.json  fixtures/features-known-defect/*.feature   Task 6
    test_kb_iterate.py                                                       Task 7
    test_kb_checkpoint.py                                                    Task 8
pyproject.toml            (modify: maven marker, addopts)                    Task 3
.github/workflows/test.yml (modify: karate-templates job)                    Task 3
docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md (touch only if a task finds a spec defect; report it, do not defer)
```

Responsibilities: `kb_features.py` is the one place that knows what a Gherkin block, tag line or exclusive-state call looks like; `flow_map.py` and `kb_report.py` import it. `kb_scaffold.py` is the only writer of `kb-runtime.json`; `Containers.java` is its only reader (through `KbRuntime.java`). `kb_report.py` owns the report JSON contract; `kb_iterate.py` and `flow_map.py --phase green` consume it. The five harness classes are one task because they form a compile cycle (`Containers.start` calls `Jwt.publishJwks`; the helpers call `Containers` accessors); one Maven run is the only gate that can prove any of them, so splitting them would give a reviewer nothing to approve or reject independently.

Task order and dependencies: 1 (backlog) and 2 (`kb_features`, `set-auth`, gate) are independent of the template; 3 creates the module and the Maven gate; 4 completes the Java and is proven by the Task 3 gate; 5 copies the Task 3 template; 6 consumes `kb_features` from Task 2; 7 consumes Task 6's report contract; 8 is independent. No task creates a file that an earlier task imports.

---

### Task 1: Plan 1 backlog fixes

**Confidence:** 93%. Three regressions found by Plan 1's reviewers, each pinned by a failing test first, plus one regression guard for behaviour that is already correct.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/kb_common.py:49` (`TEST_TREE_NAMES`)
- Modify: `skills/karate-bootstrap/scripts/discover.py:376-379` (`_CLASS_DECL_RE`)
- Modify: `skills/karate-bootstrap/scripts/kb_rules.py:156-176` (`_fluent_statements`)
- Test: `skills/karate-bootstrap/tests/test_kb_common.py`, `tests/test_kb_discover.py`, `tests/test_kb_rules.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no signature changes. `_class_prefix(stack, lines) -> tuple[str, int]` becomes importable in tests (it already exists in `discover.py`).

- [ ] **Step 1: Replace the test-tree test in `tests/test_kb_common.py`**

Replace the whole function `test_iter_files_skips_test_trees_only_when_asked` with:

```python
def test_iter_files_skips_test_trees_only_when_asked(tmp_path: Path) -> None:
    _make(tmp_path, "src/main/java/A.java", "src/test/java/ATest.java", "tests/B.java",
          "Deals.Tests/C.java", "spec/D.java", "__tests__/E.java")
    assert "src/test" in TEST_TREE_NAMES
    # A spec/ directory holds OpenAPI or BDD specifications in our repos, not tests.
    assert "spec" not in TEST_TREE_NAMES
    skipped = [rel(p, tmp_path) for p in iter_files(tmp_path, (".java",), skip_test_trees=True)]
    assert skipped == ["spec/D.java", "src/main/java/A.java"]
    assert len(list(iter_files(tmp_path, (".java",)))) == 6
```

- [ ] **Step 2: Add the class-declaration and jwks tests to `tests/test_kb_discover.py`**

Add `_class_prefix` to the `from discover import (...)` list (keep the list alphabetical: it goes first, before `assign_role`). Append:

```python
def test_class_prefix_handles_annotation_on_the_class_line() -> None:
    lines = [
        "package com.acme;",
        '@RestController @RequestMapping("/api/shipments") public class ShipmentController {',
        '    @GetMapping("/{id}")',
        '    public String get() { return "x"; }',
        "}",
    ]
    assert _class_prefix("spring", lines) == ("/api/shipments", 1)


def test_class_prefix_handles_csharp_attribute_on_the_class_line() -> None:
    lines = [
        "namespace Deals.Api.Controllers;",
        '[ApiController] [Route("api/[controller]")] public class DealsController : ControllerBase',
        "{",
        "}",
    ]
    assert _class_prefix("aspnetcore", lines) == ("api/deals", 1)


def test_detect_auth_jwks_dedupes_manifest_and_config_spellings() -> None:
    # Regression guard: detect_auth already sorts a set. It passes before any change.
    result = detect_auth(_keys(
        ("AUTH_ISSUER_URI", "https://login.example/realms/acme", "AUTH_ISSUER_URI"),
        ("spring.security.oauth2.resourceserver.jwt.issuer-uri", "${AUTH_ISSUER_URI}",
         "AUTH_ISSUER_URI"),
    ), "spring-security")
    assert result == {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}
```

- [ ] **Step 3: Add the FluentValidation test to `tests/test_kb_rules.py`**

```python
def test_extract_fluent_validation_ignores_semicolons_inside_strings() -> None:
    text = (
        "public class V : AbstractValidator<Req>\n"
        "{\n"
        "    public V()\n"
        "    {\n"
        "        RuleFor(x => x.Note)\n"
        '            .WithMessage("no;semi")\n'
        "            .MaximumLength(10);\n"
        "    }\n"
        "}\n"
    )
    rows = extract_fluent_validation(text, "V.cs")
    assert [(r["field"], r["mutation"], r["value"], r["source"]) for r in rows] == [
        ("Note", "too_long", "11", "V.cs:5"),
    ]
```

- [ ] **Step 4: Run the new tests and confirm the expected failures**

Run: `pytest skills/karate-bootstrap/tests/test_kb_common.py::test_iter_files_skips_test_trees_only_when_asked skills/karate-bootstrap/tests/test_kb_discover.py -k "class_prefix or dedupes" skills/karate-bootstrap/tests/test_kb_rules.py::test_extract_fluent_validation_ignores_semicolons_inside_strings -v`

Expected ([[verify-red]]): the `kb_common` test fails on `assert "spec" not in TEST_TREE_NAMES`; both `class_prefix` tests fail with `assert (..., -1) == (..., 1)`; the FluentValidation test fails with `[] == [("Note", ...)]` because the `;` inside `"no;semi"` closes the statement early; the jwks dedupe test passes (regression guard, as its comment says).

- [ ] **Step 5: Fix `kb_common.py`**

Replace line 49:

```python
TEST_TREE_NAMES: Final[tuple[str, ...]] = ("test", "tests", "src/test", "__tests__")
```

- [ ] **Step 6: Fix `_CLASS_DECL_RE` in `discover.py`**

Replace the regex at lines 376 to 379 with one that tolerates Java annotations and C# attributes before the modifiers on the same line:

```python
_CLASS_DECL_RE = re.compile(
    r"^\s*(?:(?:@\w+(?:\([^)]*\))?|\[[^\]]*\])\s+)*"
    r"(?:(?:public|private|protected|final|abstract|static|sealed|partial|internal)\s+)*"
    r"(?:class|interface|record)\s+(\w+)"
)
```

- [ ] **Step 7: Fix `_fluent_statements` in `kb_rules.py`**

Insert this helper immediately above `_fluent_statements` and change the statement-end test inside the loop from `if ";" in line:` to `if _ends_statement(line):`.

```python
def _ends_statement(line: str) -> bool:
    """True when ``line`` holds a ``;`` outside every double-quoted string literal."""
    in_string = False
    escaped = False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == ";":
            return True
    return False
```

- [ ] **Step 8: Run the whole suite, lint and types**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: all pass, no findings. [[spec-code-lint]]

- [ ] **Step 9: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_common.py skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/scripts/kb_rules.py skills/karate-bootstrap/tests/test_kb_common.py skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_rules.py
git commit -m "fix(karate-bootstrap): plan 1 backlog: spec dirs, same-line class annotations, semicolons in strings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `kb_features.py`, `flow_map.py set-auth`, parallel-safety gate

**Confidence:** 92%. Pure text handling with exact expected outputs. `set-auth` clears the unconfirmed-switch gap that `_validate_traced` already emits (`flow_map.py:262-266`); the gate addition slots into the existing per-feature loop in `_validate_generated` (`flow_map.py:274-333`).

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_features.py`
- Modify: `skills/karate-bootstrap/scripts/flow_map.py` (docstring, imports, `_validate_generated`, new `set_auth`, `_cmd_set_auth`, parser)
- Test: `skills/karate-bootstrap/tests/test_kb_features.py` (new), `tests/test_kb_flow_map.py` (extend)

**Interfaces:**
- Consumes: `flow_map.load_ledger`, `save_ledger`, `KbError`, `EXIT_OK` (Plan 1).
- Produces for Task 7: `kb_features.parse_feature(text: str) -> ParsedFeature`, `ParsedFeature.scenarios() -> list[Block]`, `ParsedFeature.effective_tags(block) -> set[str]`, `Block.kind`, `Block.name`, `Block.tags`, `Block.body: list[str]`, `known_defect_scenario_count(text: str) -> int`, constants `PARALLEL_FALSE_TAG = "@parallel=false"`, `KNOWN_DEFECT_TAG = "@known-defect"`.
- Produces for the skill (Plan 3): `python scripts/flow_map.py set-auth --ledger PATH --mode {disabled,jwks,none,blocked} [--key K --value V] [--issuer-keys A,B]`.

- [ ] **Step 1: Write `tests/test_kb_features.py`**

```python
from __future__ import annotations

from kb_features import (
    KNOWN_DEFECT_TAG,
    PARALLEL_FALSE_TAG,
    known_defect_scenario_count,
    parse_feature,
    unsafe_parallel_scenarios,
)

FEATURE = """@smoke @amq
Feature: POST /api/deals

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['deal.created'] }

Scenario: creates a deal
  Given url appBaseUrl
  When method post
  Then status 201

@error @parallel=false
Scenario: pricing outage returns 503
  * Stubs.load('classpath:stubs/pricing/outage.json')
  Then status 503
  * Stubs.reset()

@error
Scenario: stale reset without the tag
  * Stubs.reset()

@known-defect
Scenario: quarantined
  Then status 500

@rules
Scenario Outline: validation rule <rule_id> on <field>
  Then status <expected_status>

  Examples:
    | read('classpath:rules/post-api-deals.csv') |
"""


def test_parse_feature_splits_tags_background_and_blocks() -> None:
    parsed = parse_feature(FEATURE)
    assert parsed.tags == {"@smoke", "@amq"}
    assert [b.kind for b in parsed.blocks] == [
        "Background", "Scenario", "Scenario", "Scenario", "Scenario", "Scenario Outline",
    ]
    names = [b.name for b in parsed.scenarios()]
    assert names == ["creates a deal", "pricing outage returns 503", "stale reset without the tag",
                     "quarantined", "validation rule <rule_id> on <field>"]
    outage = parsed.scenarios()[1]
    assert outage.tags == {"@error", PARALLEL_FALSE_TAG}
    assert parsed.effective_tags(outage) == {"@smoke", "@amq", "@error", PARALLEL_FALSE_TAG}
    assert "Stubs.load('classpath:stubs/pricing/outage.json')" in outage.text()
    assert "reset.feature" in parsed.background_text()


def test_unsafe_parallel_scenarios_names_untagged_exclusive_calls_only() -> None:
    assert unsafe_parallel_scenarios(FEATURE) == ["stale reset without the tag"]


def test_unsafe_parallel_scenarios_blames_every_scenario_for_an_unsafe_background() -> None:
    text = (
        "Feature: x\n\nBackground:\n"
        "  * call read('classpath:common/reset.feature') { truncate: ['deals'] }\n\n"
        "Scenario: a\n  Then status 200\n\n@parallel=false\nScenario: b\n  Then status 200\n"
    )
    assert unsafe_parallel_scenarios(text) == ["a"]
    tagged = "@parallel=false\n" + text
    assert unsafe_parallel_scenarios(tagged) == []


def test_unsafe_parallel_scenarios_ignores_data_only_features() -> None:
    text = "Feature: y\n\nScenario: read\n  * def row = Db.row('deals', { id: uid })\n"
    assert unsafe_parallel_scenarios(text) == []


def test_known_defect_scenario_count_counts_scenario_and_feature_tags() -> None:
    assert KNOWN_DEFECT_TAG == "@known-defect"
    assert known_defect_scenario_count(FEATURE) == 1
    assert known_defect_scenario_count("@known-defect\nFeature: z\n\nScenario: a\n\n"
                                       "Scenario Outline: b\n") == 2
    assert known_defect_scenario_count("Feature: clean\n\nScenario: a\n") == 0
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_features.py -v`
Expected: `ModuleNotFoundError: No module named 'kb_features'`.

- [ ] **Step 3: Create `scripts/kb_features.py`**

```python
"""Grep-level Gherkin structure shared by flow_map.py and kb_report.py.

``parse_feature`` splits a feature file into its feature-level tags and its
``Background``, ``Scenario`` and ``Scenario Outline`` blocks. It is deliberately
not a Gherkin parser: the generated gate and the report only need tags, names
and body text (spec 5.6, "grep-level checks by design").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

PARALLEL_FALSE_TAG: Final[str] = "@parallel=false"
KNOWN_DEFECT_TAG: Final[str] = "@known-defect"

# Helpers and reset.feature arguments that mutate shared state. A scenario using
# any of them must carry @parallel=false (spec 5.6, isolation by data).
EXCLUSIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"Stubs\.reset\(|Stubs\.load\(|Db\.truncate\(|\btruncate:|\bstubs:"
)

_TAG_LINE_RE = re.compile(r"^\s*@\S")
_FEATURE_RE = re.compile(r"^\s*Feature:")
_BLOCK_RE = re.compile(r"^\s*(Background|Scenario Outline|Scenario):\s*(.*?)\s*$")


@dataclass
class Block:
    kind: str  # "Background", "Scenario" or "Scenario Outline"
    name: str
    tags: set[str]
    body: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.body)


@dataclass
class ParsedFeature:
    tags: set[str]
    blocks: list[Block]

    def scenarios(self) -> list[Block]:
        return [b for b in self.blocks if b.kind != "Background"]

    def background_text(self) -> str:
        return "\n".join(b.text() for b in self.blocks if b.kind == "Background")

    def effective_tags(self, block: Block) -> set[str]:
        return self.tags | block.tags


def parse_feature(text: str) -> ParsedFeature:
    feature_tags: set[str] = set()
    pending: set[str] = set()
    blocks: list[Block] = []
    current: Block | None = None
    for line in text.splitlines():
        if _TAG_LINE_RE.match(line):
            pending |= set(line.split())
            continue
        if _FEATURE_RE.match(line):
            feature_tags, pending = pending, set()
            continue
        match = _BLOCK_RE.match(line)
        if match:
            current = Block(match.group(1), match.group(2), pending)
            pending = set()
            blocks.append(current)
            continue
        if current is not None:
            current.body.append(line)
    return ParsedFeature(feature_tags, blocks)


def unsafe_parallel_scenarios(text: str) -> list[str]:
    """Names of scenarios that touch exclusive state without ``@parallel=false``.

    An unsafe Background taints every scenario in the feature unless the feature
    itself carries the tag.
    """
    parsed = parse_feature(text)
    background_unsafe = bool(EXCLUSIVE_RE.search(parsed.background_text()))
    return [
        block.name or block.kind
        for block in parsed.scenarios()
        if PARALLEL_FALSE_TAG not in parsed.effective_tags(block)
        and (background_unsafe or EXCLUSIVE_RE.search(block.text()))
    ]


def known_defect_scenario_count(text: str) -> int:
    """Scenarios (outlines count once, not per example row) quarantined with ``@known-defect``."""
    parsed = parse_feature(text)
    return sum(1 for b in parsed.scenarios() if KNOWN_DEFECT_TAG in parsed.effective_tags(b))
```

- [ ] **Step 4: Run the feature tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_features.py -v`
Expected: 5 passed.

- [ ] **Step 5: Add the gate and `set-auth` tests to `tests/test_kb_flow_map.py`**

Add `set_auth` to the `from flow_map import (...)` list (alphabetical, after `save_ledger`). Append:

```python
UNSAFE_FEATURE = GOOD_FEATURE + """
@error
Scenario: outage without the tag
  * Stubs.load('classpath:stubs/pricing/outage.json')
  Then status 503
  * Stubs.reset()

@error @parallel=false
Scenario: outage with the tag
  * Stubs.load('classpath:stubs/pricing/outage.json')
  Then status 503
  * Stubs.reset()
"""


def test_validate_generated_requires_parallel_false_for_exclusive_state(
    spring_ledger: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, UNSAFE_FEATURE)
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert gaps == [
        "POST /api/shipments: features/post-api-shipments.feature scenario "
        "'outage without the tag' uses exclusive state without @parallel=false",
        "GET /api/shipments/{id}: features/post-api-shipments.feature scenario "
        "'outage without the tag' uses exclusive state without @parallel=false",
        "amq shipment.requested: features/post-api-shipments.feature scenario "
        "'outage without the tag' uses exclusive state without @parallel=false",
    ]


def test_set_auth_records_each_mode(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    assert set_auth(ledger, "disabled", key="AUTH_MODE", value="mock") == {
        "mode": "disabled", "key": "AUTH_MODE", "value": "mock", "confirmed": True,
    }
    assert set_auth(ledger, "jwks", issuer_keys=["JWKS_URL", "AUTH_ISSUER_URI", "JWKS_URL"]) == {
        "mode": "jwks", "keys": ["AUTH_ISSUER_URI", "JWKS_URL"],
    }
    assert set_auth(ledger, "none") == {"mode": "none"}
    assert set_auth(ledger, "blocked") == {"mode": "blocked"}
    assert ledger["app"]["auth"] == {"mode": "blocked"}


def test_set_auth_rejects_incomplete_input(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    with pytest.raises(KbError, match="--key and --value"):
        set_auth(ledger, "disabled", key="AUTH_MODE")
    with pytest.raises(KbError, match="--issuer-keys"):
        set_auth(ledger, "jwks")
    with pytest.raises(KbError, match="unknown auth mode"):
        set_auth(ledger, "basic")


def test_cli_set_auth_clears_the_unconfirmed_switch_gap(
    spring_ledger: tuple[Path, dict[str, Any]], capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_path, ledger = spring_ledger
    ledger["app"]["auth"] = {"mode": "disabled", "key": "AUTH_MODE", "value": "disabled",
                             "confirmed": False}
    save_ledger(ledger_path, ledger)
    assert any("unconfirmed" in g for g in validate(load_ledger(ledger_path), "traced", SPRING,
                                                    None, None, None, None))
    assert run_cli(main, ["set-auth", "--ledger", str(ledger_path), "--mode", "disabled",
                          "--key", "AUTH_MODE", "--value", "mock"]) == 0
    assert '"confirmed": true' in capsys.readouterr().out
    reloaded = load_ledger(ledger_path)
    assert reloaded["app"]["auth"] == {"mode": "disabled", "key": "AUTH_MODE", "value": "mock",
                                       "confirmed": True}
    assert not any("unconfirmed" in g for g in validate(reloaded, "traced", SPRING, None, None,
                                                        None, None))
    assert run_cli(main, ["set-auth", "--ledger", str(ledger_path), "--mode", "jwks"]) == 2
```

- [ ] **Step 6: Run the new flow_map tests and confirm the expected failures**

Run: `pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -k "parallel_false or set_auth" -v`
Expected: `ImportError: cannot import name 'set_auth'` ([[verify-red]]: an import error at collection time fails the whole module; that is the expected red for this step).

- [ ] **Step 7: Modify `scripts/flow_map.py`**

Docstring: add these lines to the subcommand list, after `mark`:

```
    set-auth    --ledger PATH --mode disabled|jwks|none|blocked [--key K --value V]
                [--issuer-keys A,B]
                records the confirmed auth mode on app.auth (spec 5.2)
```

Imports: add `from kb_features import PARALLEL_FALSE_TAG, unsafe_parallel_scenarios` after the `from kb_common import (...)` block. Add a module constant after `_REQUIRED_EXIT_FIELDS`:

```python
AUTH_MODES = ("disabled", "jwks", "none", "blocked")
```

In `_validate_generated`, replace the feature-reading loop

```python
        texts: list[str] = []
        for feature in features:
            path = resources / feature
            if not path.is_file():
                gaps.append(f"{eid}: feature {feature} does not exist")
            else:
                texts.append(read_text(path))
```

with

```python
        texts: list[str] = []
        for feature in features:
            path = resources / feature
            if not path.is_file():
                gaps.append(f"{eid}: feature {feature} does not exist")
                continue
            feature_text = read_text(path)
            texts.append(feature_text)
            for name in unsafe_parallel_scenarios(feature_text):
                gaps.append(
                    f"{eid}: {feature} scenario {name!r} uses exclusive state "
                    f"without {PARALLEL_FALSE_TAG}"
                )
```

Add after `mark_entry`:

```python
def set_auth(ledger: dict[str, Any], mode: str, key: str | None = None,
             value: str | None = None, issuer_keys: list[str] | None = None) -> dict[str, Any]:
    """Record the confirmed auth mode on ``app.auth`` (spec 5.2)."""
    if mode not in AUTH_MODES:
        raise KbError(f"unknown auth mode {mode!r}; expected one of {AUTH_MODES}")
    auth: dict[str, Any]
    if mode == "disabled":
        if not key or value is None:
            raise KbError("auth mode disabled needs --key and --value")
        auth = {"mode": "disabled", "key": key, "value": value, "confirmed": True}
    elif mode == "jwks":
        if not issuer_keys:
            raise KbError("auth mode jwks needs --issuer-keys")
        auth = {"mode": "jwks", "keys": sorted(set(issuer_keys))}
    else:
        auth = {"mode": mode}
    ledger.setdefault("app", {})["auth"] = auth
    return auth
```

Add after `_cmd_mark`:

```python
def _cmd_set_auth(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    keys = None
    if args.issuer_keys:
        keys = [k.strip() for k in args.issuer_keys.split(",") if k.strip()]
    auth = set_auth(ledger, args.mode, args.key, args.value, keys)
    save_ledger(args.ledger, ledger)
    print(f"app.auth: {json.dumps(auth)}")
    return EXIT_OK
```

In `build_parser`, after the `mark` block:

```python
    auth = sub.add_parser("set-auth", help="Record the confirmed auth mode on app.auth")
    auth.add_argument("--ledger", type=Path, required=True)
    auth.add_argument("--mode", choices=AUTH_MODES, required=True)
    auth.add_argument("--key", default=None, help="switch env var (mode disabled)")
    auth.add_argument("--value", default=None, help="switch value that turns auth off")
    auth.add_argument("--issuer-keys", default=None,
                      help="comma-separated issuer or JWKS env vars (mode jwks)")
    auth.set_defaults(func=_cmd_set_auth)
```

- [ ] **Step 8: Run tests, lint, types, and the spec command's help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/flow_map.py set-auth --help`
Expected: all green; the help text lists `--ledger`, `--mode {disabled,jwks,none,blocked}`, `--key`, `--value`, `--issuer-keys`. [[docs-in-sync]]

- [ ] **Step 9: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_features.py skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/tests/test_kb_features.py skills/karate-bootstrap/tests/test_kb_flow_map.py
git commit -m "feat(karate-bootstrap): flow_map set-auth and the parallel-safety gate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Template Maven module, Maven-marked pytest, CI job

**Confidence:** 92%. Every file below is byte-for-byte what compiled and ran green in today's spike (JDK 21, wrapper-downloaded Maven 3.9.9; 5 Karate scenarios, dynamic CSV outline from a root-level `rules/` test resource, cucumber JSON and JUnit XML emitted). New in this task: the pytest that copies the template to a temp dir and runs the wrapper, the `maven` marker, and the GitHub Actions job. Risk that remains: Maven Central reachability from the executing machine. If `./mvnw` cannot download, stop with BLOCKED and the wrapper's error text; do not edit the wrapper or the pins.

**Files:**
- Create under `skills/karate-bootstrap/templates/karate-tests/`: `pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, `.gitignore`, `defects.md`, `azure-pipelines.karate.yml`, `rules/harness-smoke.csv`, `stubs/.gitkeep`, `seed/.gitkeep`, `src/test/java/kb/harness/KbRuntime.java`, `src/test/java/kb/harness/KarateRunner.java`, `src/test/resources/karate-config.js`, `src/test/resources/kb-runtime.json`, `src/test/resources/logback-test.xml`, `src/test/resources/testcontainers.properties`, `src/test/resources/common/mutate.js`, `src/test/resources/features/harness-smoke.feature`
- Create: `skills/karate-bootstrap/tests/test_kb_template.py`
- Modify: `pyproject.toml` (`markers`, `addopts`), `.github/workflows/test.yml` (new job)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"` (used by Task 5's `kb_scaffold.py`); the `maven` pytest marker and `KB_MAVEN=1` opt-in used by Task 4 to compile its Java; `KbRuntime` accessors used by Task 4: `load()`, `repo()`, `stack()`, `repoRootRel()`, `dockerfileRel()`, `appPort()`, `readinessPath()` (nullable), `serverless()`, `startupTimeoutSeconds()`, `env() -> List<Map<String,String>>` with keys `name`, `role`, `value`, `dbName()`, `dbUser()`, `dbPassword()`, `migrationsStrategy()`, `migrationsImage()` (nullable), `migrationsEnv() -> Map<String,String>`, `amqUser()`, `amqPassword()`, `amqQueues()`, `amqTopics()`, `downstreamNames()`, `authMode()`, `authKey()`, `authValue()`, `authIssuerKeys()`.

- [ ] **Step 1: Write `tests/test_kb_template.py`**

```python
"""The Karate template is a real Maven project. These tests pin its shape; the
``maven``-marked test compiles and smoke-runs it (opt in with ``KB_MAVEN=1``)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
NS = {"m": "http://maven.apache.org/POM/4.0.0"}

REQUIRED_FILES = [
    "pom.xml",
    "mvnw",
    "mvnw.cmd",
    ".mvn/wrapper/maven-wrapper.properties",
    ".gitignore",
    "defects.md",
    "azure-pipelines.karate.yml",
    "rules/harness-smoke.csv",
    "stubs/.gitkeep",
    "seed/.gitkeep",
    "src/test/java/kb/harness/KbRuntime.java",
    "src/test/java/kb/harness/KarateRunner.java",
    "src/test/resources/karate-config.js",
    "src/test/resources/kb-runtime.json",
    "src/test/resources/logback-test.xml",
    "src/test/resources/testcontainers.properties",
    "src/test/resources/common/mutate.js",
    "src/test/resources/features/harness-smoke.feature",
]

# Spec 5.5 pins. A change here is a spec change first.
PINNED_PROPERTIES = {
    "maven.compiler.release": "17",
    "karate.version": "1.5.2",
    "testcontainers.version": "1.21.4",
    "postgresql.version": "42.7.13",
    "qpid.version": "1.17.0",
    "nimbus.version": "9.37.3",
    "jackson.version": "2.17.2",
    "junit.version": "5.10.3",
    "logback.version": "1.5.6",
    "surefire.version": "3.2.5",
}


def test_template_files_present() -> None:
    missing = [rel for rel in REQUIRED_FILES if not (TEMPLATE / rel).is_file()]
    assert missing == []


def test_pom_pins_match_spec() -> None:
    root = ET.parse(TEMPLATE / "pom.xml").getroot()
    properties = root.find("m:properties", NS)
    assert properties is not None
    props = {child.tag.split("}")[1]: (child.text or "").strip() for child in properties}
    for name, value in PINNED_PROPERTIES.items():
        assert props.get(name) == value, name
    artifacts = {
        dep.findtext("m:artifactId", default="", namespaces=NS)
        for dep in root.iterfind("m:dependencies/m:dependency", NS)
    }
    assert {"karate-junit5", "testcontainers", "junit-jupiter", "postgresql", "qpid-jms-client",
            "nimbus-jose-jwt", "jackson-databind", "logback-classic"} <= artifacts
    assert "mockserver" not in " ".join(artifacts)
    surefire = ".//m:plugin/m:configuration/m:includes/m:include"
    includes = [i.text for i in root.iterfind(surefire, NS)]
    assert includes == ["**/*Test.java", "**/KarateRunner.java"]
    resources = ".//m:testResource/m:includes/m:include"
    assert [i.text for i in root.iterfind(resources, NS)] == ["rules/**", "stubs/**", "seed/**"]


def test_wrapper_is_pinned_only_script() -> None:
    props = (TEMPLATE / ".mvn/wrapper/maven-wrapper.properties").read_text(encoding="utf-8")
    assert "wrapperVersion=3.3.2" in props
    assert "distributionType=only-script" in props
    assert "apache-maven-3.9.9-bin.zip" in props
    assert (TEMPLATE / "mvnw").read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert "@REM" in (TEMPLATE / "mvnw.cmd").read_text(encoding="utf-8")[:400]


def test_runtime_template_is_valid_v1_with_neutral_defaults() -> None:
    runtime = json.loads((TEMPLATE / "src/test/resources/kb-runtime.json").read_text("utf-8"))
    assert runtime["version"] == 1
    assert runtime["app"]["readinessPath"] is None
    assert runtime["env"] == []
    assert runtime["migrations"]["image"] is None
    assert runtime["auth"] == {"mode": "none"}


def test_java_sources_carry_no_template_tokens() -> None:
    # Java is copied verbatim (spec 5.5). "${" is string.Template's marker; the harness's own
    # "{{db.host}}" runtime tokens are substituted at container start and are allowed.
    for path in (TEMPLATE / "src/test/java").rglob("*.java"):
        assert "${" not in path.read_text(encoding="utf-8"), path


def _wrapper() -> list[str]:
    return ["mvnw.cmd"] if os.name == "nt" else ["./mvnw"]


@pytest.mark.maven
@pytest.mark.skipif(os.environ.get("KB_MAVEN") != "1",
                    reason="set KB_MAVEN=1 to compile the template with Maven (needs JDK 17+)")
def test_template_compiles_and_smoke_runs(tmp_path: Path) -> None:
    module = tmp_path / "karate-tests"
    shutil.copytree(TEMPLATE, module)
    if os.name != "nt":
        (module / "mvnw").chmod(0o755)
    proc = subprocess.run(
        [*_wrapper(), "-B", "-q", "test", "-Dkb.skipContainers=true"],
        cwd=module, capture_output=True, text=True, shell=(os.name == "nt"),
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    reports = module / "target" / "karate-reports"
    assert (reports / "features.harness-smoke.json").is_file()
    summary = json.loads((reports / "karate-summary-json.txt").read_text(encoding="utf-8"))
    assert summary["scenariosfailed"] == 0
    assert summary["scenariosPassed"] >= 5
    assert (module / "target" / "surefire-reports" / "TEST-kb.harness.KarateRunner.xml").is_file()
```

- [ ] **Step 2: Run it to confirm the template does not exist yet**

Run: `pytest skills/karate-bootstrap/tests/test_kb_template.py -v`
Expected: `test_template_files_present` fails listing all 18 files; the pom test errors with `FileNotFoundError`; the maven test is skipped (`KB_MAVEN` unset). Also expected: a `PytestUnknownMarkWarning` for `maven` until Step 3.

- [ ] **Step 3: Register the marker in `pyproject.toml`**

Replace the `markers` and `addopts` lines under `[tool.pytest.ini_options]` with:

```toml
markers = [
  "live: hits a real LLM (off by default)",
  "maven: compiles and smoke-runs the Karate template with Maven (needs JDK 17+; opt in with KB_MAVEN=1)",
]
addopts = "-m 'not live and not maven'"
```

- [ ] **Step 4: Download the pinned wrapper scripts**

```bash
mkdir -p skills/karate-bootstrap/templates/karate-tests/.mvn/wrapper
curl -fsSL -o skills/karate-bootstrap/templates/karate-tests/mvnw https://raw.githubusercontent.com/apache/maven-wrapper/maven-wrapper-3.3.2/maven-wrapper-distribution/src/resources/only-mvnw
curl -fsSL -o skills/karate-bootstrap/templates/karate-tests/mvnw.cmd https://raw.githubusercontent.com/apache/maven-wrapper/maven-wrapper-3.3.2/maven-wrapper-distribution/src/resources/only-mvnw.cmd
head -1 skills/karate-bootstrap/templates/karate-tests/mvnw
wc -c skills/karate-bootstrap/templates/karate-tests/mvnw skills/karate-bootstrap/templates/karate-tests/mvnw.cmd
```

Expected: first line `#!/bin/sh`; sizes 10679 and 6926 bytes (the spike's downloads of the same tag). A different size means a different tag or a proxy page: stop and report.

- [ ] **Step 5: Write `.mvn/wrapper/maven-wrapper.properties`**

```properties
wrapperVersion=3.3.2
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

- [ ] **Step 6: Write `pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>kb.generated</groupId>
  <artifactId>karate-tests</artifactId>
  <version>0.0.1</version>
  <packaging>jar</packaging>
  <description>Karate integration tests generated by karate-bootstrap. Repo-specific values live in src/test/resources/kb-runtime.json.</description>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <karate.version>1.5.2</karate.version>
    <testcontainers.version>1.21.4</testcontainers.version>
    <postgresql.version>42.7.13</postgresql.version>
    <qpid.version>1.17.0</qpid.version>
    <nimbus.version>9.37.3</nimbus.version>
    <jackson.version>2.17.2</jackson.version>
    <junit.version>5.10.3</junit.version>
    <logback.version>1.5.6</logback.version>
    <surefire.version>3.2.5</surefire.version>
  </properties>

  <dependencyManagement>
    <dependencies>
      <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-bom</artifactId>
        <version>${testcontainers.version}</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
    </dependencies>
  </dependencyManagement>

  <dependencies>
    <dependency><groupId>io.karatelabs</groupId><artifactId>karate-junit5</artifactId><version>${karate.version}</version><scope>test</scope></dependency>
    <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>${junit.version}</version><scope>test</scope></dependency>
    <dependency><groupId>org.testcontainers</groupId><artifactId>testcontainers</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.testcontainers</groupId><artifactId>junit-jupiter</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.testcontainers</groupId><artifactId>postgresql</artifactId><scope>test</scope></dependency>
    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId><version>${postgresql.version}</version><scope>test</scope></dependency>
    <dependency><groupId>org.apache.qpid</groupId><artifactId>qpid-jms-client</artifactId><version>${qpid.version}</version><scope>test</scope></dependency>
    <dependency><groupId>com.nimbusds</groupId><artifactId>nimbus-jose-jwt</artifactId><version>${nimbus.version}</version><scope>test</scope></dependency>
    <dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId><version>${jackson.version}</version><scope>test</scope></dependency>
    <dependency><groupId>ch.qos.logback</groupId><artifactId>logback-classic</artifactId><version>${logback.version}</version><scope>test</scope></dependency>
  </dependencies>

  <build>
    <testResources>
      <testResource><directory>src/test/resources</directory></testResource>
      <testResource>
        <directory>${project.basedir}</directory>
        <includes><include>rules/**</include><include>stubs/**</include><include>seed/**</include></includes>
      </testResource>
    </testResources>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>${surefire.version}</version>
        <configuration>
          <includes><include>**/*Test.java</include><include>**/KarateRunner.java</include></includes>
          <trimStackTrace>false</trimStackTrace>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

- [ ] **Step 7: Write `.gitignore`, `defects.md`, `rules/harness-smoke.csv`, `stubs/.gitkeep`, `seed/.gitkeep`**

`.gitignore`:

```
target/
```

`defects.md`:

```markdown
# Suspected application defects

Scenarios that expose a suspected defect in the application are tagged `@known-defect`
and excluded from the run. Each is recorded here in the format from the karate-bootstrap
design spec (section 7): a `## DEF-NNN: <title>` heading followed by `status`, `slug`,
`severity`, `category`, `entry_point`, `scenario`, `evidence`, `root_cause` and
`suggested_fix` lines. None recorded yet.
```

`rules/harness-smoke.csv` (data for the harness self-test only; the generated gate ignores CSVs the ledger does not reference):

```csv
rule_id,field,mutation,value,expected
R001,a,too_long,3,'xxx'
R002,b,out_of_range,0,0
R003,a,invalid_format,,'!!'
```

`stubs/.gitkeep` and `seed/.gitkeep`: empty files.

- [ ] **Step 8: Write `src/test/java/kb/harness/KbRuntime.java`**

```java
package kb.harness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Typed view over {@code kb-runtime.json}, the only repo-specific file in this module.
 * Written by karate-bootstrap's kb_scaffold.py; schema version 1 (design spec 5.5).
 */
public final class KbRuntime {

    public static final String RESOURCE = "/kb-runtime.json";
    private static volatile KbRuntime instance;
    private final JsonNode root;

    private KbRuntime(JsonNode root) {
        this.root = root;
    }

    public static KbRuntime load() {
        KbRuntime local = instance;
        if (local == null) {
            synchronized (KbRuntime.class) {
                local = instance;
                if (local == null) {
                    try (InputStream in = KbRuntime.class.getResourceAsStream(RESOURCE)) {
                        if (in == null) {
                            throw new IllegalStateException(RESOURCE + " not on the test classpath");
                        }
                        local = new KbRuntime(new ObjectMapper().readTree(in));
                        instance = local;
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                }
            }
        }
        return local;
    }

    public String repo() { return root.path("repo").asText("unknown"); }
    public String stack() { return root.path("stack").asText("unknown"); }
    public String repoRootRel() { return root.path("app").path("repoRootRel").asText(".."); }
    public String dockerfileRel() { return root.path("app").path("dockerfileRel").asText("Dockerfile"); }
    public int appPort() { return root.path("app").path("port").asInt(8080); }

    /** Readiness path, or null when the harness must fall back to a port wait. */
    public String readinessPath() {
        JsonNode node = root.path("app").path("readinessPath");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public boolean serverless() { return root.path("app").path("serverless").asBoolean(false); }
    public int startupTimeoutSeconds() { return root.path("app").path("startupTimeoutSeconds").asInt(120); }

    /** Env entries as ordered maps with keys name, role, value (value still holds runtime tokens such as db.host). */
    public List<Map<String, String>> env() {
        List<Map<String, String>> out = new ArrayList<>();
        for (JsonNode item : root.path("env")) {
            Map<String, String> entry = new LinkedHashMap<>();
            entry.put("name", item.path("name").asText());
            entry.put("role", item.path("role").asText("passthrough"));
            entry.put("value", item.path("value").asText(""));
            out.add(entry);
        }
        return out;
    }

    public String dbName() { return root.path("db").path("name").asText("app"); }
    public String dbUser() { return root.path("db").path("user").asText("app"); }
    public String dbPassword() { return root.path("db").path("password").asText("app"); }
    public String migrationsStrategy() { return root.path("migrations").path("strategy").asText("migration-container"); }

    public String migrationsImage() {
        JsonNode node = root.path("migrations").path("image");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public Map<String, String> migrationsEnv() {
        Map<String, String> out = new LinkedHashMap<>();
        root.path("migrations").path("env").fields().forEachRemaining(e -> out.put(e.getKey(), e.getValue().asText()));
        return out;
    }

    public String amqUser() { return root.path("amq").path("user").asText("artemis"); }
    public String amqPassword() { return root.path("amq").path("password").asText("artemis"); }
    public List<String> amqQueues() { return texts(root.path("amq").path("queues")); }
    public List<String> amqTopics() { return texts(root.path("amq").path("topics")); }

    public List<String> downstreamNames() {
        List<String> out = new ArrayList<>();
        for (JsonNode item : root.path("downstreams")) {
            out.add(item.path("name").asText());
        }
        return out;
    }

    public String authMode() { return root.path("auth").path("mode").asText("none"); }
    public String authKey() { return root.path("auth").path("key").asText(null); }
    public String authValue() { return root.path("auth").path("value").asText(null); }
    public List<String> authIssuerKeys() { return texts(root.path("auth").path("issuerKeys")); }

    private static List<String> texts(JsonNode array) {
        List<String> out = new ArrayList<>();
        for (JsonNode item : array) {
            out.add(item.asText());
        }
        return out;
    }
}
```

- [ ] **Step 9: Write `src/test/java/kb/harness/KarateRunner.java`**

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.intuit.karate.Results;
import com.intuit.karate.Runner;
import org.junit.jupiter.api.Test;

/** JUnit 5 entry point. -Dkb.threads=N (default 4), -Dkb.skipContainers=true for container-free runs. */
class KarateRunner {

    @Test
    void karate() {
        int threads = Integer.getInteger("kb.threads", 4);
        Results results = Runner.path("classpath:features")
            .tags("~@known-defect")
            .outputCucumberJson(true)
            .outputJunitXml(true)
            .parallel(threads);
        assertEquals(0, results.getFailCount(), results.getErrorMessages());
    }
}
```

- [ ] **Step 10: Write the test resources**

`src/test/resources/karate-config.js`:

```javascript
function fn() {
  var skip = karate.properties['kb.skipContainers'] === 'true';
  var config = { skipContainers: skip };
  config.mutate = karate.read('classpath:common/mutate.js');
  if (!skip) {
    var Containers = Java.type('kb.harness.Containers');
    Containers.start();
    config.appBaseUrl = Containers.appBaseUrl();
    config.Db = Java.type('kb.harness.Db');
    config.Jms = Java.type('kb.harness.Jms');
    config.Stubs = Java.type('kb.harness.Stubs');
    config.Jwt = Java.type('kb.harness.Jwt');
  }
  karate.configure('connectTimeout', 10000);
  karate.configure('readTimeout', 30000);
  return config;
}
```

`src/test/resources/kb-runtime.json` (neutral template values; `kb_scaffold.py` overwrites this file):

```json
{
  "version": 1,
  "repo": "template",
  "stack": "template",
  "app": { "repoRootRel": "..", "dockerfileRel": "Dockerfile", "port": 8080,
           "readinessPath": null, "serverless": false, "startupTimeoutSeconds": 120 },
  "env": [],
  "db": { "name": "app", "user": "app", "password": "app" },
  "migrations": { "strategy": "migration-container", "image": null, "env": {} },
  "amq": { "user": "artemis", "password": "artemis", "queues": [], "topics": [] },
  "downstreams": [],
  "auth": { "mode": "none" }
}
```

`src/test/resources/logback-test.xml`:

```xml
<configuration>
  <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} %-5level %logger{24} - %msg%n</pattern>
    </encoder>
  </appender>
  <logger name="org.testcontainers" level="INFO"/>
  <logger name="com.github.dockerjava" level="WARN"/>
  <logger name="com.intuit.karate" level="INFO"/>
  <root level="WARN">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

`src/test/resources/testcontainers.properties`:

```properties
# Podman and rootless engines need Ryuk privileged; disable Ryuk with
# TESTCONTAINERS_RYUK_DISABLED=true if your engine refuses it (README, "Podman").
ryuk.container.privileged=true
```

`src/test/resources/common/mutate.js`:

```javascript
function fn(base, field, mutation, value) {
  var copy = JSON.parse(JSON.stringify(base));
  var v = (value === undefined || value === null) ? '' : String(value);
  var n = parseInt(v, 10);
  switch (mutation) {
    case 'missing':
      delete copy[field];
      break;
    case 'null':
      copy[field] = null;
      break;
    case 'empty':
      copy[field] = '';
      break;
    case 'too_long':
      copy[field] = 'x'.repeat(isNaN(n) ? 1 : n);
      break;
    case 'too_short':
      copy[field] = 'x'.repeat(isNaN(n) || n < 0 ? 0 : n);
      break;
    case 'invalid_format':
      copy[field] = v === '' ? '!!' : v;
      break;
    case 'out_of_range':
      copy[field] = (v !== '' && !isNaN(Number(v))) ? Number(v) : v;
      break;
    case 'invalid_enum':
      copy[field] = v === '' ? 'NOT_A_VALUE' : v;
      break;
    case 'cross_field':
      copy[field] = v;
      break;
    default:
      throw new Error('unknown mutation: ' + mutation);
  }
  return copy;
}
```

`src/test/resources/features/harness-smoke.feature`:

```gherkin
@harness
Feature: harness self-test that needs no containers

Scenario: mutate helper covers every mutation kind
  * def base = { name: 'abc', qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'missing', '') == { qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'null', '') == { name: null, qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'empty', '') == { name: '', qty: 5, kind: 'A' }
  * match mutate(base, 'name', 'too_long', '4').name == 'xxxx'
  * match mutate(base, 'name', 'too_short', '2').name == 'xx'
  * match mutate(base, 'name', 'invalid_format', '').name == '!!'
  * match mutate(base, 'qty', 'out_of_range', '0').qty == 0
  * match mutate(base, 'kind', 'invalid_enum', '').kind == 'NOT_A_VALUE'
  * match mutate(base, 'qty', 'cross_field', 'gt:limit').qty == 'gt:limit'

Scenario: runtime configuration is on the classpath
  * def Runtime = Java.type('kb.harness.KbRuntime')
  * def rt = Runtime.load()
  * match rt.repo() == '#string'
  * match rt.appPort() == '#number'
  * match skipContainers == true

Scenario Outline: dynamic outline from csv works: <rule_id>
  * def payload = mutate({ a: 'x', b: 2 }, '<field>', '<mutation>', '<value>')
  * match payload.<field> == <expected>

  Examples:
    | read('classpath:rules/harness-smoke.csv') |
```

- [ ] **Step 11: Write `azure-pipelines.karate.yml`**

```yaml
# Reusable Azure DevOps job for the generated Karate suite (design spec section 10).
# Include from the service pipeline:
#   - template: karate-tests/azure-pipelines.karate.yml
#     parameters: { imageTag: $(imageTag) }      # omit to let the harness build the app image
parameters:
  - name: imageTag
    type: string
    default: ''
  - name: workingDirectory
    type: string
    default: karate-tests

jobs:
  - job: karate
    displayName: Karate integration tests (Testcontainers)
    pool:
      vmImage: ubuntu-latest
    steps:
      - task: JavaToolInstaller@0
        inputs:
          versionSpec: '21'
          jdkArchitectureOption: x64
          jdkSourceOption: PreInstalled
      - ${{ if eq(parameters.imageTag, '') }}:
          - script: ./mvnw -B test
            workingDirectory: ${{ parameters.workingDirectory }}
            displayName: mvnw test (harness builds the app image from the Dockerfile)
      - ${{ if ne(parameters.imageTag, '') }}:
          - script: ./mvnw -B test -Dapp.image=${{ parameters.imageTag }}
            workingDirectory: ${{ parameters.workingDirectory }}
            displayName: mvnw test against the prebuilt image
      - task: PublishTestResults@2
        condition: always()
        inputs:
          testResultsFormat: JUnit
          testResultsFiles: '${{ parameters.workingDirectory }}/target/karate-reports/*.xml'
          testRunTitle: karate
      - task: PublishBuildArtifacts@1
        condition: always()
        inputs:
          pathToPublish: '${{ parameters.workingDirectory }}/target/karate-reports'
          artifactName: karate-reports
```

- [ ] **Step 12: Run the shape tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_template.py -v`
Expected: 5 passed, 1 skipped (the Maven test).

- [ ] **Step 13: Compile and smoke-run the template with Maven**

PowerShell on this machine (set `JAVA_HOME` first, see [[maven-needs-java-home]]):

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"; $env:KB_MAVEN = "1"; pytest -m maven -v
```

bash or CI:

```bash
KB_MAVEN=1 pytest -m maven -v
```

Expected: `test_template_compiles_and_smoke_runs PASSED` (first run downloads Maven 3.9.9 and dependencies; 2 to 5 minutes). If it fails, the assertion message carries the Maven tail: report it verbatim as BLOCKED rather than editing pins.

- [ ] **Step 14: Add the CI job to `.github/workflows/test.yml`**

Append under `jobs:`:

```yaml
  karate-templates:
    name: Karate template compiles and smoke-runs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - run: pip install -e ".[dev]"
      - run: KB_MAVEN=1 pytest -m maven -v
```

- [ ] **Step 15: Full suite, lint, types**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green; the default run still skips the Maven test because of `addopts`.

- [ ] **Step 16: Commit, marking `mvnw` executable in the index**

```bash
git add pyproject.toml .github/workflows/test.yml skills/karate-bootstrap/tests/test_kb_template.py skills/karate-bootstrap/templates/karate-tests
git update-index --chmod=+x skills/karate-bootstrap/templates/karate-tests/mvnw
git commit -m "feat(karate-bootstrap): Karate template module compiled and smoke-run in CI

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

`git add` of the directory is acceptable here because every file under `templates/karate-tests` was created by this task; confirm with `git status --short` that nothing outside those paths is staged before committing ([[stage-by-path]]).

---

### Task 4: Harness classes: `Containers`, `Db`, `Jms`, `Stubs`, `Jwt`, `reset.feature`, JUnit tests

**Confidence:** 93%. The exact sources and tests in this task were compiled and run today in the spike (`mvnw clean test -Dkb.skipContainers=true`, exit 0): `ContainersTest` 4, `JmsTest` 4, `JwtTest` 2, `StubsTest` 2, and the smoke feature's 6 scenarios including the one that calls `reset.feature` with and without arguments. Testcontainers 1.21.4 calls used: `Network.newNetwork()`, `PostgreSQLContainer<>(DockerImageName)`, `GenericContainer` with `withNetwork`, `withNetworkAliases`, `withExposedPorts`, `withEnv`, `waitingFor`, `withLogConsumer`, `withStartupCheckStrategy`; `Wait.forHttp(path).forPort(p).forStatusCode(200).withStartupTimeout(Duration)`, `Wait.forListeningPort()`, `Wait.forLogMessage(regex, 1)`; `OneShotStartupCheckStrategy().withTimeout(Duration)`; `ImageFromDockerfile(name, false).withFileFromPath(".", Path).withDockerfilePath(String)`; Qpid `JmsConnectionFactory(user, password, "amqp://host:port")` with `javax.jms`; WireMock admin calls over `java.net.http`; Nimbus `RSAKeyGenerator`, `RSASSASigner`, `JWKSet`. The lift run caught one wrong assertion (FIFO order after `Jms.takeMatching` requeues skipped messages); the corrected test is below. The five classes are one task because they form a compile cycle (`Containers.start` calls `Jwt.publishJwks`; the helpers call `Containers` accessors), so one Maven run is the only gate that can prove any of them. The remaining 7% is the live topology, which no test here can reach: Plan 4 starts the containers by design (spec 12).

**Files:**
- Create under `skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness/`: `Containers.java`, `Db.java`, `Jms.java`, `Stubs.java`, `Jwt.java`, `ContainersTest.java`, `JmsTest.java`, `JwtTest.java`, `StubsTest.java`
- Create: `skills/karate-bootstrap/templates/karate-tests/src/test/resources/common/reset.feature`
- Modify: `skills/karate-bootstrap/templates/karate-tests/src/test/resources/features/harness-smoke.feature` (append one scenario)
- Modify: `skills/karate-bootstrap/tests/test_kb_template.py` (`REQUIRED_FILES`)

**Interfaces:**
- Consumes: `KbRuntime` (Task 3).
- Produces for `karate-config.js` (Task 3): `Containers.start()`, `Containers.appBaseUrl()`.
- Produces for generated features (the names spec 5.6 uses): `Db.run(path)`, `Db.row(table, where)`, `Db.awaitRow(table, where, timeoutMs)`, `Db.count(table, where)`, `Db.truncate(tables)`; `Jms.watch(dest)`, `Jms.await(dest, timeoutMs)`, `Jms.await(dest, timeoutMs, matchMap)`, `Jms.publish(dest, body, headers)`; `Stubs.reset()`, `Stubs.load(path)`, `Stubs.verify(method, urlPath, times)`, `Stubs.verify(method, urlPath, bodyContains, times)`, `Stubs.unmatched()`; `Jwt.token(claims)`; `call read('classpath:common/reset.feature') { watch: [...], seed: '...', stubs: [...], truncate: [...] }`.
- Produces for `kb_iterate.py` (Task 7): `target/app.log`, `target/db-manager.log`, `target/postgres.log`, `target/artemis.log`, `target/wiremock.log`, `target/stubs-unmatched.json`.
- Package-private for tests: `Containers.substitute(String, Map)`, `Containers.tokenValues(KbRuntime)`, `Containers.artemisExtraArgs(List, List)`, `Containers.appWait(String, int, int, boolean)`, `Stubs.countBody(method, urlPath, bodyContains)`, `Stubs.readCount(json)`, `Jwt.mapping(urlPath, jsonBody)`, `Jwt.mappings(items...)`, `Jwt.tokenFor(issuer, claims)`, `Jwt.key()`, `Jms.matches(body, matchMap)`, `Jms.takeMatching(queue, deadlineMillis, matchMap)`.

- [ ] **Step 1: Write the four JUnit test classes**

`ContainersTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.wait.strategy.HostPortWaitStrategy;
import org.testcontainers.containers.wait.strategy.HttpWaitStrategy;

/** Pure helpers only: nothing here talks to a container engine. */
class ContainersTest {

    @Test
    void substituteReplacesEveryKnownTokenAndLeavesUnknownOnes() {
        Map<String, String> values = Map.of("db.host", "db", "db.port", "5432", "db.name", "shipments");
        assertEquals("jdbc:postgresql://db:5432/shipments",
            Containers.substitute("jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}", values));
        assertEquals("{{unknown}} stays", Containers.substitute("{{unknown}} stays", values));
        assertEquals("false", Containers.substitute("false", values));
    }

    @Test
    void tokenValuesCoverTheSpecTokens() {
        Map<String, String> values = Containers.tokenValues(KbRuntime.load());
        assertEquals("db", values.get("db.host"));
        assertEquals("5432", values.get("db.port"));
        assertEquals("artemis", values.get("amq.host"));
        assertEquals("5672", values.get("amq.amqpPort"));
        assertEquals("61616", values.get("amq.corePort"));
        assertEquals("61613", values.get("amq.stompPort"));
        assertEquals("http://wiremock:8080", values.get("stubs.url"));
        assertEquals("http://wiremock:8080/auth", values.get("auth.url"));
    }

    @Test
    void artemisExtraArgsListQueuesAsAnycastAndTopicsAsMulticast() {
        assertEquals("--http-host 0.0.0.0 --relax-jolokia --queues a,b --addresses t",
            Containers.artemisExtraArgs(List.of("a", "b"), List.of("t")));
        assertEquals("--http-host 0.0.0.0 --relax-jolokia",
            Containers.artemisExtraArgs(List.of(), List.of()));
    }

    @Test
    void appWaitFallsBackToAPortWaitWithoutAReadinessPath() {
        assertInstanceOf(HostPortWaitStrategy.class, Containers.appWait(null, 8080, 120, false));
        assertInstanceOf(HttpWaitStrategy.class, Containers.appWait("/health/ready", 8080, 120, true));
    }
}
```

`JwtTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.nimbusds.jose.JWSVerifier;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.SignedJWT;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JwtTest {

    @Test
    void mappingWrapsBodyAsAWireMockStub() throws Exception {
        JsonNode node = new ObjectMapper().readTree(Jwt.mapping("/auth/x", "{\"a\":1}"));
        assertEquals("/auth/x", node.at("/request/urlPath").asText());
        assertEquals("GET", node.at("/request/method").asText());
        assertEquals(200, node.at("/response/status").asInt());
        assertEquals(1, node.at("/response/jsonBody/a").asInt());
        assertTrue(Jwt.mappings(Jwt.mapping("/a", "{}"), Jwt.mapping("/b", "{}")).startsWith("{\"mappings\":["));
    }

    @Test
    void tokenIsSignedByTheTestKeyWithTheGivenIssuer() throws Exception {
        SignedJWT jwt = SignedJWT.parse(Jwt.tokenFor("http://test/auth", Map.of("sub", "alice")));
        JWSVerifier verifier = new RSASSAVerifier(Jwt.key().toRSAPublicKey());
        assertTrue(jwt.verify(verifier));
        assertEquals("alice", jwt.getJWTClaimsSet().getSubject());
        assertEquals("kb-test-key", jwt.getHeader().getKeyID());
        assertEquals("http://test/auth", jwt.getJWTClaimsSet().getIssuer());
    }
}
```

`StubsTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class StubsTest {

    @Test
    void countBodyIsAWireMockRequestPattern() {
        assertEquals("{\"method\":\"GET\",\"urlPath\":\"/pricing/rates/GB\"}",
            Stubs.countBody("GET", "/pricing/rates/GB", null));
        assertEquals("{\"method\":\"POST\",\"urlPath\":\"/pricing/quotes\","
                + "\"bodyPatterns\":[{\"contains\":\"EXT-\\\"quoted\\\"\"}]}",
            Stubs.countBody("POST", "/pricing/quotes", "EXT-\"quoted\""));
    }

    @Test
    void readCountReadsTheCountField() {
        assertEquals(3, Stubs.readCount("{\"count\":3}"));
        assertEquals(-1, Stubs.readCount("{}"));
    }
}
```

`JmsTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import org.junit.jupiter.api.Test;

/** Inbox logic only: no broker is involved. */
class JmsTest {

    private static Map<String, Object> message(String dealId) {
        return Map.of("body", Map.of("dealId", dealId), "properties", Map.of(), "messageId", "id-" + dealId);
    }

    @Test
    void matchesRequiresEveryKeyAndValue() {
        Map<String, Object> body = Map.of("dealId", "d-1", "status", "PENDING", "n", 2);
        assertTrue(Jms.matches(body, Map.of("dealId", "d-1")));
        assertTrue(Jms.matches(body, Map.of("dealId", "d-1", "n", 2)));
        assertFalse(Jms.matches(body, Map.of("dealId", "d-2")));
        assertFalse(Jms.matches(body, Map.of("missing", "x")));
        assertFalse(Jms.matches("not a map", Map.of("dealId", "d-1")));
        assertTrue(Jms.matches(List.of(1), Map.of()));
    }

    @Test
    void takeMatchingReturnsTheMatchingMessageAndRequeuesTheOthers() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        queue.add(message("d-2"));
        queue.add(message("d-3"));
        Map<String, Object> found = Jms.takeMatching(queue, System.currentTimeMillis() + 1000, Map.of("dealId", "d-2"));
        assertEquals("id-d-2", found.get("messageId"));
        // Skipped messages go back behind anything that arrived meanwhile; order is not preserved,
        // which is fine because every scenario matches by content, never by position.
        assertEquals(2, queue.size());
        Set<Object> remaining = new HashSet<>();
        remaining.add(queue.poll().get("messageId"));
        remaining.add(queue.poll().get("messageId"));
        assertEquals(Set.of("id-d-1", "id-d-3"), remaining);
    }

    @Test
    void takeMatchingTimesOutWithNullAndKeepsTheInbox() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        assertNull(Jms.takeMatching(queue, System.currentTimeMillis() + 150, Map.of("dealId", "zzz")));
        assertEquals(1, queue.size());
    }

    @Test
    void takeMatchingWithoutAMapTakesTheFirstMessage() {
        BlockingQueue<Map<String, Object>> queue = new LinkedBlockingQueue<>();
        queue.add(message("d-1"));
        queue.add(message("d-2"));
        assertEquals("id-d-1", Jms.takeMatching(queue, System.currentTimeMillis() + 1000, null).get("messageId"));
        assertEquals(1, queue.size());
    }
}
```

- [ ] **Step 2: Extend `REQUIRED_FILES` in `tests/test_kb_template.py` and see it fail**

Insert after the `KarateRunner.java` line:

```python
    "src/test/java/kb/harness/Containers.java",
    "src/test/java/kb/harness/Db.java",
    "src/test/java/kb/harness/Jms.java",
    "src/test/java/kb/harness/Stubs.java",
    "src/test/java/kb/harness/Jwt.java",
    "src/test/java/kb/harness/ContainersTest.java",
    "src/test/java/kb/harness/JmsTest.java",
    "src/test/java/kb/harness/JwtTest.java",
    "src/test/java/kb/harness/StubsTest.java",
    "src/test/resources/common/reset.feature",
```

Run: `pytest skills/karate-bootstrap/tests/test_kb_template.py::test_template_files_present -v`
Expected: fails listing `Containers.java`, `Db.java`, `Jms.java`, `Stubs.java`, `Jwt.java` and `reset.feature` (the four test classes exist from Step 1).

- [ ] **Step 3: Write `Containers.java`**

```java
package kb.harness;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.output.OutputFrame;
import org.testcontainers.containers.output.Slf4jLogConsumer;
import org.testcontainers.containers.startupcheck.OneShotStartupCheckStrategy;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.containers.wait.strategy.WaitStrategy;
import org.testcontainers.images.builder.ImageFromDockerfile;
import org.testcontainers.utility.DockerImageName;

/**
 * The test topology (design spec 4.2): one network; Postgres, Artemis, WireMock, the one-shot
 * db-manager, then the app built from the repo's Dockerfile. Started once per JVM, lazily,
 * from karate-config.js. Every value that differs between repos comes from kb-runtime.json.
 */
public final class Containers {

    private static final Logger LOG = LoggerFactory.getLogger(Containers.class);

    static final String DB_ALIAS = "db";
    static final String AMQ_ALIAS = "artemis";
    static final String STUBS_ALIAS = "wiremock";
    static final String APP_ALIAS = "app";
    static final int DB_PORT = 5432;
    static final int AMQ_CORE_PORT = 61616;
    static final int AMQ_AMQP_PORT = 5672;
    static final int AMQ_STOMP_PORT = 61613;
    static final int AMQ_HTTP_PORT = 8161;
    static final int STUBS_PORT = 8080;

    static final DockerImageName POSTGRES_IMAGE = DockerImageName.parse("postgres:16-alpine");
    static final DockerImageName ARTEMIS_IMAGE = DockerImageName.parse("apache/activemq-artemis:2.44.0-alpine");
    static final DockerImageName WIREMOCK_IMAGE = DockerImageName.parse("wiremock/wiremock:3.13.2-alpine");

    private static final Path TARGET = Paths.get("target");

    private static boolean started;
    private static Network network;
    private static PostgreSQLContainer<?> postgres;
    private static GenericContainer<?> artemis;
    private static GenericContainer<?> wiremock;
    private static GenericContainer<?> app;
    private static KbRuntime runtime;

    private Containers() {
    }

    public static synchronized void start() {
        if (started) {
            return;
        }
        runtime = KbRuntime.load();
        network = Network.newNetwork();

        postgres = new PostgreSQLContainer<>(POSTGRES_IMAGE)
            .withNetwork(network)
            .withNetworkAliases(DB_ALIAS)
            .withDatabaseName(runtime.dbName())
            .withUsername(runtime.dbUser())
            .withPassword(runtime.dbPassword())
            .withLogConsumer(fileLog("postgres"));
        postgres.start();

        artemis = new GenericContainer<>(ARTEMIS_IMAGE)
            .withNetwork(network)
            .withNetworkAliases(AMQ_ALIAS)
            .withExposedPorts(AMQ_CORE_PORT, AMQ_AMQP_PORT, AMQ_STOMP_PORT, AMQ_HTTP_PORT)
            .withEnv("ARTEMIS_USER", runtime.amqUser())
            .withEnv("ARTEMIS_PASSWORD", runtime.amqPassword())
            .withEnv("ANONYMOUS_LOGIN", "false")
            .withEnv("EXTRA_ARGS", artemisExtraArgs(runtime.amqQueues(), runtime.amqTopics()))
            .waitingFor(Wait.forLogMessage(".*AMQ221007.*\\n", 1).withStartupTimeout(Duration.ofSeconds(120)))
            .withLogConsumer(fileLog("artemis"));
        artemis.start();

        wiremock = new GenericContainer<>(WIREMOCK_IMAGE)
            .withNetwork(network)
            .withNetworkAliases(STUBS_ALIAS)
            .withExposedPorts(STUBS_PORT)
            .waitingFor(Wait.forHttp("/__admin/health").forPort(STUBS_PORT).forStatusCode(200))
            .withLogConsumer(fileLog("wiremock"));
        wiremock.start();
        if ("jwks".equals(runtime.authMode())) {
            Jwt.publishJwks();
        }

        runMigrations();

        Map<String, String> tokens = tokenValues(runtime);
        app = buildApp()
            .withNetwork(network)
            .withNetworkAliases(APP_ALIAS)
            .withExposedPorts(runtime.appPort())
            .waitingFor(appWait(runtime.readinessPath(), runtime.appPort(),
                runtime.startupTimeoutSeconds(), runtime.serverless()))
            .withLogConsumer(fileLog("app"))
            .withLogConsumer(new Slf4jLogConsumer(LOG).withPrefix("app"));
        for (Map<String, String> entry : runtime.env()) {
            app.withEnv(entry.get("name"), substitute(entry.get("value"), tokens));
        }
        app.start();
        started = true;
        LOG.info("topology up: app={} db={} jms={}", appBaseUrl(), jdbcUrl(), jmsUrl());
    }

    public static String appBaseUrl() { return "http://" + app.getHost() + ":" + app.getMappedPort(runtime.appPort()); }
    public static String jdbcUrl() { return postgres.getJdbcUrl(); }
    public static String dbUser() { return runtime.dbUser(); }
    public static String dbPassword() { return runtime.dbPassword(); }
    public static String jmsUrl() { return "amqp://" + artemis.getHost() + ":" + artemis.getMappedPort(AMQ_AMQP_PORT); }
    public static String amqUser() { return runtime.amqUser(); }
    public static String amqPassword() { return runtime.amqPassword(); }
    public static String stubsHost() { return wiremock.getHost(); }
    public static int stubsPort() { return wiremock.getMappedPort(STUBS_PORT); }
    public static String stubsInternalUrl() { return "http://" + STUBS_ALIAS + ":" + STUBS_PORT; }
    public static String authInternalUrl() { return stubsInternalUrl() + "/auth"; }
    public static Path appLogPath() { return TARGET.resolve("app.log"); }

    /** Queue unless the ledger listed the destination as a topic. */
    public static boolean isQueue(String destination) {
        KbRuntime rt = runtime != null ? runtime : KbRuntime.load();
        return rt.amqQueues().contains(destination) || !rt.amqTopics().contains(destination);
    }

    /** Values for the {{token}} placeholders kb_scaffold.py writes into kb-runtime.json (spec 5.5). */
    static Map<String, String> tokenValues(KbRuntime rt) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("db.host", DB_ALIAS);
        values.put("db.port", Integer.toString(DB_PORT));
        values.put("db.name", rt.dbName());
        values.put("db.user", rt.dbUser());
        values.put("db.password", rt.dbPassword());
        values.put("amq.host", AMQ_ALIAS);
        values.put("amq.corePort", Integer.toString(AMQ_CORE_PORT));
        values.put("amq.amqpPort", Integer.toString(AMQ_AMQP_PORT));
        values.put("amq.stompPort", Integer.toString(AMQ_STOMP_PORT));
        values.put("amq.user", rt.amqUser());
        values.put("amq.password", rt.amqPassword());
        values.put("stubs.url", stubsInternalUrl());
        values.put("auth.url", authInternalUrl());
        return values;
    }

    static String substitute(String template, Map<String, String> values) {
        String out = template;
        for (Map.Entry<String, String> e : values.entrySet()) {
            out = out.replace("{{" + e.getKey() + "}}", e.getValue());
        }
        return out;
    }

    /** artemis create arguments: --queues are anycast, --addresses multicast. */
    static String artemisExtraArgs(List<String> queues, List<String> topics) {
        StringBuilder args = new StringBuilder("--http-host 0.0.0.0 --relax-jolokia");
        if (!queues.isEmpty()) {
            args.append(" --queues ").append(String.join(",", queues));
        }
        if (!topics.isEmpty()) {
            args.append(" --addresses ").append(String.join(",", topics));
        }
        return args.toString();
    }

    /** Readiness probe from the ledger, port wait when there is none; serverless doubles the timeout. */
    static WaitStrategy appWait(String readinessPath, int port, int timeoutSeconds, boolean serverless) {
        Duration timeout = Duration.ofSeconds((long) timeoutSeconds * (serverless ? 2 : 1));
        if (readinessPath == null || readinessPath.isBlank()) {
            return Wait.forListeningPort().withStartupTimeout(timeout);
        }
        return Wait.forHttp(readinessPath).forPort(port).forStatusCode(200).withStartupTimeout(timeout);
    }

    private static void runMigrations() {
        if (!"migration-container".equals(runtime.migrationsStrategy())) {
            return;
        }
        String image = runtime.migrationsImage();
        if (image == null) {
            throw new IllegalStateException("kb-runtime.json has no migrations.image (design spec 5.5)");
        }
        Map<String, String> tokens = tokenValues(runtime);
        GenericContainer<?> manager = new GenericContainer<>(DockerImageName.parse(image))
            .withNetwork(network)
            .withStartupCheckStrategy(new OneShotStartupCheckStrategy().withTimeout(Duration.ofMinutes(5)))
            .withLogConsumer(fileLog("db-manager"));
        for (Map.Entry<String, String> e : runtime.migrationsEnv().entrySet()) {
            manager.withEnv(e.getKey(), substitute(e.getValue(), tokens));
        }
        try {
            manager.start();
        } catch (RuntimeException e) {
            throw new IllegalStateException("db-manager " + image + " did not exit 0; see target/db-manager.log", e);
        }
    }

    private static GenericContainer<?> buildApp() {
        String prebuilt = System.getProperty("app.image");
        if (prebuilt != null && !prebuilt.isBlank()) {
            return new GenericContainer<>(DockerImageName.parse(prebuilt));
        }
        Path repoRoot = Paths.get(System.getProperty("user.dir")).resolve(runtime.repoRootRel()).normalize();
        ImageFromDockerfile image = new ImageFromDockerfile("kb-app-" + runtime.repo().toLowerCase(), false)
            .withFileFromPath(".", repoRoot)
            .withDockerfilePath(runtime.dockerfileRel());
        return new GenericContainer<>(image);
    }

    private static Consumer<OutputFrame> fileLog(String name) {
        Path file = TARGET.resolve(name + ".log");
        try {
            Files.createDirectories(TARGET);
            Files.deleteIfExists(file);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        return frame -> {
            String text = frame.getUtf8String();
            if (text == null || text.isEmpty()) {
                return;
            }
            try {
                Files.writeString(file, text, StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        };
    }
}
```

- [ ] **Step 4: Write `Db.java`**

```java
package kb.harness;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** Postgres helpers exposed to Karate as {@code Db}. Identifiers are validated, values are bound. */
public final class Db {

    private static final Pattern IDENT = Pattern.compile("^[A-Za-z_][A-Za-z0-9_]*$");

    private Db() {
    }

    /** Runs a seed script; statements are split on a ';' at end of line. Seeds are inserts, not functions. */
    public static void run(String path) {
        String sql = readText(path);
        try (Connection c = connect(); Statement st = c.createStatement()) {
            for (String statement : sql.split(";\\s*\\r?\\n")) {
                String trimmed = statement.trim();
                if (!trimmed.isEmpty() && !trimmed.startsWith("--")) {
                    st.execute(trimmed);
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.run failed for " + path + ": " + e.getMessage(), e);
        }
    }

    public static Map<String, Object> row(String table, Map<String, Object> where) {
        List<Map<String, Object>> rows = select(table, where, 1);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public static Map<String, Object> awaitRow(String table, Map<String, Object> where, long timeoutMs) {
        long deadline = System.currentTimeMillis() + timeoutMs;
        while (true) {
            Map<String, Object> found = row(table, where);
            if (found != null) {
                return found;
            }
            if (System.currentTimeMillis() > deadline) {
                throw new AssertionError("no row in " + table + " matching " + where + " within " + timeoutMs + "ms");
            }
            sleep(250);
        }
    }

    public static long count(String table, Map<String, Object> where) {
        checkIdent(table);
        StringBuilder sql = new StringBuilder("SELECT COUNT(*) FROM ").append(table);
        List<Object> params = whereClause(sql, where);
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(sql.toString())) {
            bind(ps, params);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.count failed: " + e.getMessage(), e);
        }
    }

    /** Exclusive state: callers carry @parallel=false (spec 5.6). */
    public static void truncate(List<String> tables) {
        if (tables == null || tables.isEmpty()) {
            return;
        }
        tables.forEach(Db::checkIdent);
        String sql = "TRUNCATE TABLE " + String.join(", ", tables) + " RESTART IDENTITY CASCADE";
        try (Connection c = connect(); Statement st = c.createStatement()) {
            st.execute(sql);
        } catch (SQLException e) {
            throw new IllegalStateException("Db.truncate failed: " + e.getMessage(), e);
        }
    }

    private static List<Map<String, Object>> select(String table, Map<String, Object> where, int limit) {
        checkIdent(table);
        StringBuilder sql = new StringBuilder("SELECT * FROM ").append(table);
        List<Object> params = whereClause(sql, where);
        sql.append(" LIMIT ").append(limit);
        List<Map<String, Object>> out = new ArrayList<>();
        try (Connection c = connect(); PreparedStatement ps = c.prepareStatement(sql.toString())) {
            bind(ps, params);
            try (ResultSet rs = ps.executeQuery()) {
                ResultSetMetaData meta = rs.getMetaData();
                while (rs.next()) {
                    Map<String, Object> rowMap = new LinkedHashMap<>();
                    for (int i = 1; i <= meta.getColumnCount(); i++) {
                        rowMap.put(meta.getColumnLabel(i), rs.getObject(i));
                    }
                    out.add(rowMap);
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Db.select failed: " + e.getMessage(), e);
        }
        return out;
    }

    private static List<Object> whereClause(StringBuilder sql, Map<String, Object> where) {
        List<Object> params = new ArrayList<>();
        if (where == null || where.isEmpty()) {
            return params;
        }
        sql.append(" WHERE ");
        boolean first = true;
        for (Map.Entry<String, Object> e : where.entrySet()) {
            checkIdent(e.getKey());
            if (!first) {
                sql.append(" AND ");
            }
            first = false;
            if (e.getValue() == null) {
                sql.append(e.getKey()).append(" IS NULL");
            } else {
                sql.append(e.getKey()).append(" = ?");
                params.add(e.getValue());
            }
        }
        return params;
    }

    private static void bind(PreparedStatement ps, List<Object> params) throws SQLException {
        for (int i = 0; i < params.size(); i++) {
            ps.setObject(i + 1, params.get(i));
        }
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(Containers.jdbcUrl(), Containers.dbUser(), Containers.dbPassword());
    }

    private static void checkIdent(String name) {
        if (name == null || !IDENT.matcher(name).matches()) {
            throw new IllegalArgumentException("invalid SQL identifier: " + name);
        }
    }

    /** Reads classpath:x or a filesystem path; shared with Stubs.load. */
    static String readText(String path) {
        String clean = path.startsWith("classpath:") ? path.substring("classpath:".length()) : path;
        try (InputStream in = Db.class.getResourceAsStream("/" + clean)) {
            if (in != null) {
                return new String(in.readAllBytes(), StandardCharsets.UTF_8);
            }
            Path file = Paths.get(clean);
            if (Files.isRegularFile(file)) {
                return Files.readString(file, StandardCharsets.UTF_8);
            }
            throw new IllegalArgumentException("not found on classpath or filesystem: " + path);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }
}
```

- [ ] **Step 5: Write `Jms.java`**

```java
package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import javax.jms.Connection;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.qpid.jms.JmsConnectionFactory;

/**
 * Artemis over AMQP 1.0 (Qpid JMS), exposed to Karate as {@code Jms}. One consumer per destination
 * for the whole JVM; every scenario takes its own message by content with the match form of await.
 */
public final class Jms {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Map<String, BlockingQueue<Map<String, Object>>> INBOX = new ConcurrentHashMap<>();
    private static final Map<String, MessageConsumer> CONSUMERS = new ConcurrentHashMap<>();
    private static Connection connection;
    private static Session session;

    private Jms() {
    }

    /** Subscribes once per destination. Idempotent: later calls do not drop queued messages. */
    public static synchronized void watch(String destination) {
        try {
            ensureSession();
            INBOX.computeIfAbsent(destination, d -> new LinkedBlockingQueue<>());
            if (!CONSUMERS.containsKey(destination)) {
                MessageConsumer consumer = session.createConsumer(destinationFor(destination));
                consumer.setMessageListener(message -> INBOX.get(destination).offer(toMap(message)));
                CONSUMERS.put(destination, consumer);
            }
        } catch (JMSException e) {
            throw new IllegalStateException("Jms.watch failed for " + destination + ": " + e.getMessage(), e);
        }
    }

    /** Next message on the destination. Parallel scenarios use the match form instead. */
    public static Map<String, Object> await(String destination, long timeoutMs) {
        return await(destination, timeoutMs, null);
    }

    /**
     * The first message whose body contains every key and value of {@code matchMap}; other messages
     * go back to the inbox for other scenarios. Returns {body, properties, messageId}.
     */
    public static Map<String, Object> await(String destination, long timeoutMs, Map<String, Object> matchMap) {
        BlockingQueue<Map<String, Object>> queue = INBOX.get(destination);
        if (queue == null) {
            throw new IllegalStateException("Jms.await(" + destination + ") called without Jms.watch first");
        }
        Map<String, Object> found = takeMatching(queue, System.currentTimeMillis() + timeoutMs, matchMap);
        if (found == null) {
            throw new AssertionError("no message on " + destination
                + (matchMap == null ? "" : " matching " + matchMap) + " within " + timeoutMs + "ms");
        }
        return found;
    }

    /**
     * Polls {@code queue} until {@code deadlineMillis} for a message matching {@code matchMap} (any
     * message when null). Non-matching messages are put back behind whatever arrived meanwhile;
     * order is not preserved. Returns null on timeout.
     */
    static Map<String, Object> takeMatching(BlockingQueue<Map<String, Object>> queue, long deadlineMillis,
                                            Map<String, Object> matchMap) {
        List<Map<String, Object>> others = new ArrayList<>();
        try {
            while (true) {
                long remaining = deadlineMillis - System.currentTimeMillis();
                Map<String, Object> message = remaining > 0 ? queue.poll(remaining, TimeUnit.MILLISECONDS) : null;
                if (message == null) {
                    queue.addAll(others);
                    return null;
                }
                if (matchMap == null || matches(message.get("body"), matchMap)) {
                    queue.addAll(others);
                    return message;
                }
                others.add(message);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static synchronized void publish(String destination, Object body, Map<String, Object> headers) {
        try {
            ensureSession();
            String text = body instanceof String ? (String) body : JSON.writeValueAsString(body);
            TextMessage message = session.createTextMessage(text);
            if (headers != null) {
                for (Map.Entry<String, Object> h : headers.entrySet()) {
                    message.setObjectProperty(h.getKey(), h.getValue());
                }
            }
            try (MessageProducer producer = session.createProducer(destinationFor(destination))) {
                producer.send(message);
            }
        } catch (JMSException | JsonProcessingException e) {
            throw new IllegalStateException("Jms.publish failed for " + destination + ": " + e.getMessage(), e);
        }
    }

    /** True when {@code body} is a map holding every entry of {@code matchMap} with an equal value. */
    static boolean matches(Object body, Map<String, Object> matchMap) {
        if (matchMap == null || matchMap.isEmpty()) {
            return true;
        }
        if (!(body instanceof Map)) {
            return false;
        }
        Map<?, ?> map = (Map<?, ?>) body;
        for (Map.Entry<String, Object> expected : matchMap.entrySet()) {
            if (!map.containsKey(expected.getKey())) {
                return false;
            }
            Object actual = map.get(expected.getKey());
            if (!Objects.equals(String.valueOf(actual), String.valueOf(expected.getValue()))) {
                return false;
            }
        }
        return true;
    }

    private static void ensureSession() throws JMSException {
        if (session != null) {
            return;
        }
        JmsConnectionFactory factory = new JmsConnectionFactory(Containers.amqUser(), Containers.amqPassword(), Containers.jmsUrl());
        connection = factory.createConnection();
        connection.start();
        session = connection.createSession(false, Session.AUTO_ACKNOWLEDGE);
    }

    private static Destination destinationFor(String name) throws JMSException {
        return Containers.isQueue(name) ? session.createQueue(name) : session.createTopic(name);
    }

    private static Map<String, Object> toMap(Message message) {
        Map<String, Object> out = new LinkedHashMap<>();
        try {
            Object body = message instanceof TextMessage ? ((TextMessage) message).getText() : message.getBody(Object.class);
            if (body instanceof String) {
                String text = (String) body;
                try {
                    body = JSON.readValue(text, Object.class);
                } catch (JsonProcessingException notJson) {
                    body = text;
                }
            }
            out.put("body", body);
            Map<String, Object> properties = new LinkedHashMap<>();
            Enumeration<?> names = message.getPropertyNames();
            while (names.hasMoreElements()) {
                String name = String.valueOf(names.nextElement());
                properties.put(name, message.getObjectProperty(name));
            }
            out.put("properties", properties);
            out.put("messageId", message.getJMSMessageID());
        } catch (JMSException e) {
            throw new IllegalStateException(e);
        }
        return out;
    }
}
```

- [ ] **Step 6: Write `Stubs.java`**

```java
package kb.harness;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** WireMock helpers exposed to Karate as {@code Stubs}, driven over the admin REST API (spec 5.5). */
public final class Stubs {

    private static final HttpClient HTTP = HttpClient.newHttpClient();
    private static final ObjectMapper JSON = new ObjectMapper();

    private Stubs() {
    }

    /** Removes every mapping and the request journal. Exclusive state: @parallel=false. */
    public static void reset() {
        expect2xx(post("/__admin/reset", ""), "reset");
    }

    /** Imports a {"mappings":[...]} document from classpath:... or the filesystem. Exclusive state. */
    public static void load(String path) {
        expect2xx(post("/__admin/mappings/import", Db.readText(path)), "import " + path);
    }

    /** Exactly {@code times} journal entries match method + urlPath. */
    public static boolean verify(String method, String urlPath, int times) {
        return verify(method, urlPath, null, times);
    }

    /** Exactly {@code times} journal entries match method + urlPath and a body containing {@code bodyContains}. */
    public static boolean verify(String method, String urlPath, String bodyContains, int times) {
        HttpResponse<String> response = post("/__admin/requests/count", countBody(method, urlPath, bodyContains));
        expect2xx(response, "count");
        int count = readCount(response.body());
        if (count == times) {
            return true;
        }
        throw new AssertionError("Stubs.verify " + method + " " + urlPath
            + (bodyContains == null ? "" : " body~" + bodyContains) + ": expected " + times
            + " request(s), WireMock recorded " + count);
    }

    /** Writes unmatched requests and their near misses to target/stubs-unmatched.json for kb_iterate.py. */
    public static Path unmatched() {
        String requests = get("/__admin/requests/unmatched").body();
        String nearMisses = get("/__admin/requests/unmatched/near-misses").body();
        Path file = Paths.get("target", "stubs-unmatched.json");
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, "{\"unmatched\":" + requests + ",\"nearMisses\":" + nearMisses + "}",
                StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        return file;
    }

    static String countBody(String method, String urlPath, String bodyContains) {
        ObjectNode node = JSON.createObjectNode().put("method", method).put("urlPath", urlPath);
        if (bodyContains != null) {
            node.putArray("bodyPatterns").addObject().put("contains", bodyContains);
        }
        return node.toString();
    }

    static int readCount(String body) {
        try {
            JsonNode node = JSON.readTree(body);
            return node.path("count").asInt(-1);
        } catch (IOException e) {
            throw new IllegalStateException("unreadable count response: " + body, e);
        }
    }

    static String baseUrl() {
        return "http://" + Containers.stubsHost() + ":" + Containers.stubsPort();
    }

    static HttpResponse<String> post(String path, String body) {
        return send(HttpRequest.newBuilder(URI.create(baseUrl() + path))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build());
    }

    static HttpResponse<String> get(String path) {
        return send(HttpRequest.newBuilder(URI.create(baseUrl() + path)).GET().build());
    }

    private static HttpResponse<String> send(HttpRequest request) {
        try {
            return HTTP.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (IOException e) {
            throw new IllegalStateException("WireMock call failed: " + request.uri(), e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    private static void expect2xx(HttpResponse<String> response, String what) {
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException("WireMock " + what + " failed: " + response.statusCode() + " " + response.body());
        }
    }
}
```

- [ ] **Step 7: Write `Jwt.java`**

```java
package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.util.Date;
import java.util.Map;

/** Test issuer: one RSA key per JVM; discovery and JWKS served by WireMock under /auth (spec 5.5). */
public final class Jwt {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final RSAKey KEY = generate();

    private Jwt() {
    }

    /** RS256 bearer token with iss = the WireMock auth URL the app was configured with. */
    public static String token(Map<String, Object> claims) {
        return tokenFor(Containers.authInternalUrl(), claims);
    }

    static String tokenFor(String issuer, Map<String, Object> claims) {
        try {
            JWTClaimsSet.Builder builder = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .issueTime(new Date())
                .expirationTime(new Date(System.currentTimeMillis() + 3_600_000L));
            if (claims != null) {
                claims.forEach(builder::claim);
            }
            SignedJWT jwt = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(KEY.getKeyID()).build(), builder.build());
            jwt.sign(new RSASSASigner(KEY));
            return jwt.serialize();
        } catch (JOSEException e) {
            throw new IllegalStateException("Jwt.token failed", e);
        }
    }

    /** Imports /auth/.well-known/openid-configuration and /auth/.well-known/jwks.json into WireMock. */
    public static void publishJwks() {
        String issuer = Containers.authInternalUrl();
        String jwks = new JWKSet(KEY.toPublicJWK()).toString();
        ObjectNode discovery = JSON.createObjectNode()
            .put("issuer", issuer)
            .put("jwks_uri", issuer + "/.well-known/jwks.json");
        discovery.putArray("id_token_signing_alg_values_supported").add("RS256");
        Stubs.post("/__admin/mappings/import", mappings(
            mapping("/auth/.well-known/openid-configuration", discovery.toString()),
            mapping("/auth/.well-known/jwks.json", jwks)));
    }

    static String mappings(String... items) {
        return "{\"mappings\":[" + String.join(",", items) + "]}";
    }

    /** A priority-1 GET stub returning {@code jsonBody} (a JSON document) as application/json. */
    static String mapping(String urlPath, String jsonBody) {
        try {
            ObjectNode node = JSON.createObjectNode().put("priority", 1);
            node.putObject("request").put("method", "GET").put("urlPath", urlPath);
            ObjectNode response = node.putObject("response").put("status", 200);
            response.putObject("headers").put("Content-Type", "application/json");
            response.set("jsonBody", JSON.readTree(jsonBody));
            return node.toString();
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("mapping body is not JSON: " + jsonBody, e);
        }
    }

    static RSAKey key() {
        return KEY;
    }

    private static RSAKey generate() {
        try {
            return new RSAKeyGenerator(2048).keyUse(KeyUse.SIGNATURE).keyID("kb-test-key").generate();
        } catch (JOSEException e) {
            throw new IllegalStateException("cannot generate test RSA key", e);
        }
    }
}
```

- [ ] **Step 8: Write `src/test/resources/common/reset.feature`**

```gherkin
@ignore
Feature: per-scenario setup shared by every generated feature

  Called as: call read('classpath:common/reset.feature') { watch: ['deal.created'], seed: 'classpath:seed/x.sql' }
  Arguments: watch (destinations to subscribe before the request), seed (additive SQL, parallel-safe),
  stubs (mapping documents to import) and truncate (tables). stubs and truncate mutate shared state,
  so the calling scenario must carry @parallel=false (design spec 5.6).

Scenario:
  * def args = __arg || {}
  * def watch = args.watch || []
  * def stubs = args.stubs || []
  * karate.forEach(watch, function(d){ Jms.watch(d) })
  * eval if (args.seed) Db.run(args.seed)
  * karate.forEach(stubs, function(p){ Stubs.load(p) })
  * eval if (args.truncate) Db.truncate(args.truncate)
```

`eval` rather than Karate's `* if (...) <step>` form so the whole statement is parsed by the JS engine even when the condition is false; that is what lets the smoke run below prove the syntax without `Db`, `Jms` or `Stubs` existing.

- [ ] **Step 8b: Append the reset smoke scenario to `src/test/resources/features/harness-smoke.feature`**

Append to the end of the file:

```gherkin

Scenario: reset feature accepts empty arguments without containers
  * def bare = call read('classpath:common/reset.feature')
  * match bare.watch == []
  * def empty = call read('classpath:common/reset.feature') { watch: [], stubs: [] }
  * match empty.stubs == []
```

- [ ] **Step 9: Shape tests, then compile and run the JUnit tests through Maven**

Run: `pytest skills/karate-bootstrap/tests/test_kb_template.py -v`
Expected: 5 passed, 1 skipped.

PowerShell on this machine ([[maven-needs-java-home]]):

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.12.101-hotspot"; $env:KB_MAVEN = "1"; pytest -m maven -v
```

bash or CI:

```bash
KB_MAVEN=1 pytest -m maven -v
```

Expected: PASSED. Surefire runs `ContainersTest` (4 tests), `JmsTest` (4), `JwtTest` (2), `StubsTest` (2) and `KarateRunner` (6 scenarios, `scenariosPassed` 6 in `karate-summary-json.txt`); `reset.feature` is `@ignore` and runs only through the smoke scenario's `call`. Update the smoke test's `summary["scenariosPassed"] >= 5` assertion to `>= 6`. A compile error surfaces in the assertion message with the Maven tail; fix only Java written in this task.

- [ ] **Step 10: Lint, types, commit**

Run: `ruff check .` then `mypy`
Expected: clean.

```bash
git add skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness skills/karate-bootstrap/templates/karate-tests/src/test/resources/common/reset.feature skills/karate-bootstrap/templates/karate-tests/src/test/resources/features/harness-smoke.feature skills/karate-bootstrap/tests/test_kb_template.py
git status --short
git commit -m "feat(karate-bootstrap): Testcontainers harness: Containers, Db, Jms, Stubs, Jwt

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

`git status --short` must show only the twelve files this task created or modified (nine Java sources and tests, `reset.feature`, `harness-smoke.feature`, `test_kb_template.py`) before the commit runs ([[stage-by-path]]).

---

### Task 5: `kb_scaffold.py`

**Confidence:** 93%. Pure Python over Plan 1 outputs plus a file copy. The module and test file below were extracted from this plan and run today against the real `env-map.json` and seeded `flow-map.yaml` that `detect.py` and `discover.py` produce for `spring-mini` and `dotnet-mini`: 23 tests passed (the `env_value` table, `env_name`, `db_name_from_env`, both `build_runtime` goldens, the central-config merge, the exit-4 path) and the copy rules were checked against a stand-in template. The two tests that need the Task 3 template on disk (`test_copy_template_never_overwrites_generated_content`, `test_cli_scaffolds_and_rewrites_runtime`) are the only ones not yet executed; they exercise the same `copy_template` that passed the stand-in check.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_scaffold.py`
- Test: `skills/karate-bootstrap/tests/test_kb_scaffold.py`

**Interfaces:**
- Consumes: `flow_map.load_ledger`, `kb_common.{read_json, read_yaml, require_file, write_json, run_cli, KbError, EXIT_OK, EXIT_NO_SCHEMA, EXIT_MISSING_OUTPUT}`; the template directory from Task 3; ledger fields `repo`, `stack.framework`, `app.{dockerfile, port, serverless, readiness.path, migrations.strategy, auth}`, `entry_points[].{kind, destination, type, exits[]}`; env-map fields `manifest.source`, `keys[].{key, role, placeholder, source, env_var}`.
- Produces: `kb-runtime.json` v1 (spec 5.5), read by `KbRuntime.java`. Python API used by tests only: `env_name(stack, key, env_var) -> str | None`, `env_value(stack, name, role, placeholder, source, manifest_source, auth) -> str | None`, `db_name_from_env(env_map) -> str`, `select_db_manager(config, name) -> tuple[str, dict] | None`, `build_runtime(ledger, env_map, service_root, out_dir, config, migrations_image) -> dict`, `copy_template(template_dir, out_dir, force) -> dict[str, list[str]]`, `load_central_config(path) -> dict`, constants `TEMPLATE_DIR`, `RUNTIME_REL`.
- CLI (spec 5.5): `python scripts/kb_scaffold.py <repo> --ledger PATH --env PATH --out DIR [--service-dir SUB] [--migrations-image REF] [--config PATH] [--force]`.

- [ ] **Step 1: Write `tests/test_kb_scaffold.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import load_ledger
from kb_common import EXIT_NO_SCHEMA, KbError, read_json, run_cli
from kb_scaffold import (
    RUNTIME_REL,
    TEMPLATE_DIR,
    build_runtime,
    copy_template,
    db_name_from_env,
    env_name,
    env_value,
    load_central_config,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures"
IMAGE = "registry.example/db-manager:1"
DISABLED = {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false", "confirmed": True}
JWKS = {"mode": "jwks", "keys": ["AUTH_ISSUER_URI", "AUTH_JWKS_URL"]}
DEFAULT_MIGRATION_ENV = {
    "PGHOST": "{{db.host}}", "PGPORT": "{{db.port}}", "PGDATABASE": "{{db.name}}",
    "PGUSER": "{{db.user}}", "PGPASSWORD": "{{db.password}}",
}

SPRING_ENV = [
    {"name": "AUTH_ISSUER_URI", "role": "auth", "value": "https://login.example/realms/acme"},
    {"name": "PRICING_BASE_URL", "role": "downstream:pricing", "value": "{{stubs.url}}/pricing"},
    {"name": "SPRING_ARTEMIS_BROKER_URL", "role": "amq",
     "value": "tcp://{{amq.host}}:{{amq.corePort}}"},
    {"name": "SPRING_DATASOURCE_URL", "role": "db",
     "value": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"},
    {"name": "APP_SECURITY_ENABLED", "role": "auth", "value": "false"},
    {"name": "SPRING_DATASOURCE_PASSWORD", "role": "db", "value": "{{db.password}}"},
    {"name": "SPRING_DATASOURCE_USERNAME", "role": "db", "value": "{{db.user}}"},
]
DOTNET_ENV = [
    {"name": "Amq__Password", "role": "amq", "value": "{{amq.password}}"},
    {"name": "Amq__Url", "role": "amq", "value": "amqp://{{amq.host}}:{{amq.amqpPort}}"},
    {"name": "Amq__User", "role": "amq", "value": "{{amq.user}}"},
    {"name": "Auth__Audience", "role": "auth", "value": "deals-api"},
    {"name": "Auth__Authority", "role": "auth", "value": "https://login.example/realms/acme"},
    {"name": "Auth__Enabled", "role": "auth", "value": "false"},
    {"name": "ConnectionStrings__Deals", "role": "db",
     "value": "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
              "Username={{db.user}};Password={{db.password}}"},
    {"name": "Pricing__BaseUrl", "role": "downstream:pricing", "value": "{{stubs.url}}/pricing"},
]


def _analysed(tmp_path: Path,
              fixture: str) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    root = FIXTURES / fixture
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return root, ledger, env, load_ledger(ledger), read_json(env)


def test_env_name_follows_each_stacks_convention() -> None:
    assert env_name("spring", "spring.datasource.password", None) == "SPRING_DATASOURCE_PASSWORD"
    assert env_name("quarkus", "quarkus.datasource.jdbc.url", None) == "QUARKUS_DATASOURCE_JDBC_URL"
    assert env_name("aspnetcore", "Amq__User", None) == "Amq__User"
    assert env_name("python", "database_url", None) is None
    assert env_name("python", "database_url", "DATABASE_URL") == "DATABASE_URL"


@pytest.mark.parametrize(("stack", "name", "role", "placeholder", "source", "expected"), [
    ("spring", "SPRING_DATASOURCE_URL", "db", "", "deployment.yml",
     "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"),
    ("aspnetcore", "ConnectionStrings__Deals", "db", "", "deployment.yml",
     "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
     "Username={{db.user}};Password={{db.password}}"),
    ("python", "DATABASE_URL", "db", "", "deployment.yml",
     "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}"),
    ("spring", "SPRING_DATASOURCE_USERNAME", "db", "${X:shipments}", "application.yml",
     "{{db.user}}"),
    ("aspnetcore", "PGHOST", "db", "", "deployment.yml", "{{db.host}}"),
    ("spring", "SPRING_ARTEMIS_BROKER_URL", "amq", "tcp://artemis:61616", "deployment.yml",
     "tcp://{{amq.host}}:{{amq.corePort}}"),
    ("aspnetcore", "Amq__Url", "amq", "amqp://artemis:5672", "deployment.yml",
     "amqp://{{amq.host}}:{{amq.amqpPort}}"),
    ("python", "AMQ_URL", "amq", "", "deployment.yml", "amqp://{{amq.host}}:{{amq.amqpPort}}"),
    ("python", "STOMP_URL", "amq", "stomp://amq:61613", "deployment.yml",
     "stomp://{{amq.host}}:{{amq.stompPort}}"),
    ("aspnetcore", "Amq__Password", "amq", "artemis", "appsettings.json", "{{amq.password}}"),
    ("spring", "PRICING_BASE_URL", "downstream:pricing", "http://pricing:8080", "deployment.yml",
     "{{stubs.url}}/pricing"),
    ("spring", "APP_SECURITY_ENABLED", "auth", "${APP_SECURITY_ENABLED:true}", "application.yml",
     "false"),
    ("spring", "AUTH_ISSUER_URI", "auth", "https://login.example/realms/acme", "deployment.yml",
     "https://login.example/realms/acme"),
    ("spring", "AUTH_ISSUER_URI", "auth", "${AUTH_ISSUER_URI}", "application.yml", None),
    ("spring", "SPRING_PROFILES_ACTIVE", "passthrough", "prod", "deployment.yml", "prod"),
    ("spring", "JAVA_OPTS", "passthrough", "-Xmx512m", "Dockerfile", None),
    ("spring", "spring.jpa.hibernate.ddl-auto", "passthrough", "validate", "application.yml", None),
])
def test_env_value_rules(stack: str, name: str, role: str, placeholder: str, source: str,
                         expected: str | None) -> None:
    assert env_value(stack, name, role, placeholder, source, "deployment.yml", DISABLED) == expected


def test_env_value_jwks_mode_points_issuer_and_jwks_keys_at_wiremock() -> None:
    assert env_value("spring", "AUTH_ISSUER_URI", "auth", "", "deployment.yml", "deployment.yml",
                     JWKS) == "{{auth.url}}"
    assert env_value("spring", "AUTH_JWKS_URL", "auth", "", "deployment.yml", "deployment.yml",
                     JWKS) == "{{auth.url}}/.well-known/jwks.json"


def test_db_name_from_env_prefers_explicit_names() -> None:
    def keys(*items: tuple[str, str, str]) -> dict[str, Any]:
        return {"keys": [{"key": k, "role": r, "placeholder": p} for k, r, p in items]}
    assert db_name_from_env(keys(("ConnectionStrings__Deals", "db",
                                  "Host=localhost;Database=deals;Username=u"))) == "deals"
    assert db_name_from_env(keys(("SPRING_DATASOURCE_URL", "db",
                                  "jdbc:postgresql://db:5432/shipments"))) == "shipments"
    assert db_name_from_env(keys(("DATABASE_URL", "db",
                                  "postgresql://u:p@h:5432/orders"))) == "orders"
    assert db_name_from_env(keys(("ConnectionStrings__Deals", "db", ""))) == "deals"
    assert db_name_from_env(keys(("SPRING_DATASOURCE_URL", "db", ""))) == "app"


def test_build_runtime_spring_mini(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "spring-mini")
    out = tmp_path / "karate-tests"
    runtime = build_runtime(ledger, env_map, root, out, load_central_config(None), IMAGE)
    assert runtime["version"] == 1
    assert runtime["repo"] == "spring-mini"
    assert runtime["stack"] == "spring"
    assert (out / runtime["app"]["repoRootRel"]).resolve() == root.resolve()
    assert runtime["app"] | {"repoRootRel": ""} == {
        "repoRootRel": "", "dockerfileRel": "Dockerfile", "port": 8080,
        "readinessPath": "/actuator/health/readiness", "serverless": True,
        "startupTimeoutSeconds": 120,
    }
    assert runtime["env"] == SPRING_ENV
    assert runtime["db"] == {"name": "app", "user": "app", "password": "app"}
    assert runtime["migrations"] == {"strategy": "migration-container", "image": IMAGE,
                                     "env": DEFAULT_MIGRATION_ENV}
    assert runtime["amq"] == {"user": "artemis", "password": "artemis",
                              "queues": ["shipment.requested"], "topics": []}
    assert runtime["downstreams"] == [{"name": "pricing", "envVar": "PRICING_BASE_URL"}]
    assert runtime["auth"] == {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false"}


def test_build_runtime_dotnet_mini_and_central_config(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "dotnet-mini")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "db_managers:\n"
        "  deals:\n"
        "    image: registry.example/db-manager-deals:latest\n"
        "    env:\n"
        "      DB_HOST_KEY: PGHOST\n"
        "      DB_PORT_KEY: PGPORT\n"
        "      DB_NAME_KEY: DBNAME\n"
        "      DB_USER_KEY: PGUSER\n"
        "      DB_PASSWORD_KEY: PGPASSWORD\n"
        "    database: deals\n"
        "    extra_env:\n"
        "      FLYWAY_SCHEMAS: public\n",
        encoding="utf-8",
    )
    config = load_central_config(config_path)
    runtime = build_runtime(ledger, env_map, root, tmp_path / "karate-tests", config, None)
    assert runtime["stack"] == "aspnetcore"
    assert runtime["env"] == DOTNET_ENV
    assert runtime["db"]["name"] == "deals"
    assert runtime["migrations"] == {
        "strategy": "migration-container", "image": "registry.example/db-manager-deals:latest",
        "env": {"PGHOST": "{{db.host}}", "PGPORT": "{{db.port}}", "DBNAME": "{{db.name}}",
                "PGUSER": "{{db.user}}", "PGPASSWORD": "{{db.password}}",
                "FLYWAY_SCHEMAS": "public"},
    }
    assert runtime["app"]["readinessPath"] == "/health/ready"
    assert runtime["app"]["serverless"] is False
    assert runtime["auth"] == {"mode": "disabled", "key": "Auth__Enabled", "value": "false"}
    overridden = build_runtime(ledger, env_map, root, tmp_path / "karate-tests", config, IMAGE)
    assert overridden["migrations"]["image"] == IMAGE
    assert overridden["migrations"]["env"]["DBNAME"] == "{{db.name}}"


def test_build_runtime_exits_4_without_a_schema_source(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "spring-mini")
    with pytest.raises(KbError) as excinfo:
        build_runtime(ledger, env_map, root, tmp_path / "karate-tests",
                      load_central_config(None), None)
    assert excinfo.value.exit_code == EXIT_NO_SCHEMA
    assert "--migrations-image" in str(excinfo.value)


def test_copy_template_never_overwrites_generated_content(tmp_path: Path) -> None:
    out = tmp_path / "karate-tests"
    first = copy_template(TEMPLATE_DIR, out, force=False)
    assert "pom.xml" in first["written"]
    assert RUNTIME_REL not in first["written"]  # written by main, not by the copy
    assert (out / "rules/harness-smoke.csv").is_file()
    (out / "pom.xml").write_text("edited", encoding="utf-8")
    (out / "rules/harness-smoke.csv").write_text("edited", encoding="utf-8")
    smoke = out / "src/test/resources/features/harness-smoke.feature"
    smoke.write_text("edited", encoding="utf-8")
    (out / "defects.md").write_text("edited", encoding="utf-8")
    second = copy_template(TEMPLATE_DIR, out, force=False)
    assert second["written"] == [] and second["overwritten"] == []
    assert {"pom.xml", "rules/harness-smoke.csv", "defects.md",
            "src/test/resources/features/harness-smoke.feature"} <= set(second["kept"])
    third = copy_template(TEMPLATE_DIR, out, force=True)
    assert "pom.xml" in third["overwritten"]
    assert (out / "pom.xml").read_text(encoding="utf-8") != "edited"
    for kept in ("rules/harness-smoke.csv", "defects.md",
                 "src/test/resources/features/harness-smoke.feature"):
        assert (out / kept).read_text(encoding="utf-8") == "edited", kept


def test_cli_scaffolds_and_rewrites_runtime(tmp_path: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    root, ledger_path, env_path, _, _ = _analysed(tmp_path, "spring-mini")
    out = tmp_path / "karate-tests"
    argv = [str(root), "--ledger", str(ledger_path), "--env", str(env_path), "--out", str(out),
            "--migrations-image", IMAGE, "--config", str(tmp_path / "absent.yaml")]
    assert run_cli(main, argv) == 0
    assert "scaffolded" in capsys.readouterr().out
    runtime = read_json(out / RUNTIME_REL)
    assert runtime["repo"] == "spring-mini"
    assert (out / "mvnw").is_file() and (out / "src/test/java/kb/harness/Containers.java").is_file()
    (out / RUNTIME_REL).write_text("{}", encoding="utf-8")
    assert run_cli(main, argv) == 0
    assert read_json(out / RUNTIME_REL)["env"] == SPRING_ENV
    assert run_cli(main, argv[:-4] + ["--config", str(tmp_path / "absent.yaml")]) == EXIT_NO_SCHEMA
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_scaffold.py -v`
Expected: `ModuleNotFoundError: No module named 'kb_scaffold'`.

- [ ] **Step 3: Create `scripts/kb_scaffold.py`**

```python
"""Phase 4 of karate-bootstrap: scaffold the Karate module into a repo.

Copies ``templates/karate-tests/`` (a real Maven project, compiled in this repo's CI)
into ``--out`` and writes ``src/test/resources/kb-runtime.json``, the only file that
carries repo-specific values (design spec 5.5). Java sources are copied verbatim.

Usage:
    python scripts/kb_scaffold.py <repo> --ledger karate-tests/flow-map.yaml \
        --env karate-tests/env-map.json --out karate-tests [--service-dir SUB] \
        [--migrations-image REF] [--config ~/.karate-bootstrap/config.yaml] [--force]

Copy rules: generated content (rules/, stubs/, seed/, src/test/resources/features/,
defects.md, README.md) is never overwritten; harness files are overwritten only with
``--force``; kb-runtime.json is always rewritten; nothing is deleted.

Exit codes: 0 ok, 4 when the strategy is migration-container and no db-manager image can
be resolved from ``--migrations-image`` or the central config, 5 when an input is missing.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from flow_map import load_ledger
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_NO_SCHEMA,
    EXIT_OK,
    KbError,
    read_json,
    read_yaml,
    require_file,
    run_cli,
    write_json,
)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
RUNTIME_REL = "src/test/resources/kb-runtime.json"
DEFAULT_CONFIG = Path.home() / ".karate-bootstrap" / "config.yaml"
RUNTIME_VERSION = 1
STARTUP_TIMEOUT_SECONDS = 120

# Never overwritten once present: the generate phase and the developer own these.
GENERATED_PREFIXES = ("rules/", "stubs/", "seed/", "src/test/resources/features/")
GENERATED_FILES = ("defects.md", "README.md")

# Central config ``env`` keys name the db-manager's own variables (spec 5.5).
MIGRATION_ENV_TOKENS = {
    "DB_HOST_KEY": "{{db.host}}",
    "DB_PORT_KEY": "{{db.port}}",
    "DB_NAME_KEY": "{{db.name}}",
    "DB_USER_KEY": "{{db.user}}",
    "DB_PASSWORD_KEY": "{{db.password}}",
}
DEFAULT_MIGRATION_ENV = {
    "PGHOST": "{{db.host}}",
    "PGPORT": "{{db.port}}",
    "PGDATABASE": "{{db.name}}",
    "PGUSER": "{{db.user}}",
    "PGPASSWORD": "{{db.password}}",
}

DB_URL_BY_STACK = {
    "spring": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}",
    "quarkus": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}",
    "aspnetcore": "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
                  "Username={{db.user}};Password={{db.password}}",
    "python": "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}",
}
_DB_URL_NEEDLES = ("url", "jdbc", "connectionstring")
_DB_PART_TOKENS = (
    ("password", "{{db.password}}"),
    ("user", "{{db.user}}"),
    ("host", "{{db.host}}"),
    ("port", "{{db.port}}"),
    ("database", "{{db.name}}"),
    ("dbname", "{{db.name}}"),
    ("db_name", "{{db.name}}"),
)
_AMQ_PART_TOKENS = (
    ("password", "{{amq.password}}"),
    ("user", "{{amq.user}}"),
    ("host", "{{amq.host}}"),
    ("port", "{{amq.amqpPort}}"),
)
_CORE_SCHEMES = ("tcp://", "activemq:", "failover:")
_DB_NAME_RES = (
    re.compile(r"Database=(\w+)", re.IGNORECASE),
    re.compile(r"jdbc:postgresql://[^/\s]+/(\w+)"),
    re.compile(r"postgres(?:ql)?://[^/\s]+/(\w+)"),
)
_CONNECTION_STRING_KEY_RE = re.compile(r"^ConnectionStrings__(\w+)$")


# --- env entries ----------------------------------------------------------------------


def env_name(stack: str, key: str, env_var: str | None) -> str | None:
    """The environment variable the app reads for ``key``; None when the stack has no rule."""
    if env_var:
        return env_var
    if stack in ("spring", "quarkus"):
        return re.sub(r"[.\-]", "_", key).upper()
    if stack == "aspnetcore":
        return key
    return None


def env_value(stack: str, name: str, role: str, placeholder: str, source: str,
              manifest_source: str | None, auth: dict[str, Any]) -> str | None:
    """Template value for one env var, or None when the harness must not set it."""
    lowered = name.lower()
    if role == "db":
        if any(needle in lowered for needle in _DB_URL_NEEDLES):
            return DB_URL_BY_STACK.get(stack, DB_URL_BY_STACK["python"])
        for needle, token in _DB_PART_TOKENS:
            if needle in lowered:
                return token
        return DB_URL_BY_STACK.get(stack, DB_URL_BY_STACK["python"])
    if role == "amq":
        for needle, token in _AMQ_PART_TOKENS:
            if needle in lowered:
                return token
        scheme = placeholder.lower()
        if scheme.startswith(_CORE_SCHEMES):
            return "tcp://{{amq.host}}:{{amq.corePort}}"
        if scheme.startswith("stomp://"):
            return "stomp://{{amq.host}}:{{amq.stompPort}}"
        return "amqp://{{amq.host}}:{{amq.amqpPort}}"
    if role.startswith("downstream:"):
        return "{{stubs.url}}/" + role.split(":", 1)[1]
    if role == "auth":
        if auth.get("mode") == "disabled" and name == auth.get("key"):
            return str(auth.get("value"))
        if auth.get("mode") == "jwks" and name in auth.get("keys", []):
            return "{{auth.url}}/.well-known/jwks.json" if "jwks" in lowered else "{{auth.url}}"
        return placeholder if placeholder and "${" not in placeholder else None
    # passthrough: only literal runtime knobs from the manifest travel into the container
    if manifest_source and source == manifest_source and placeholder and "${" not in placeholder:
        return placeholder
    return None


def env_block(stack: str, env_map: dict[str, Any], auth: dict[str, Any]) -> list[dict[str, str]]:
    manifest_source = (env_map.get("manifest") or {}).get("source")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in env_map["keys"]:
        name = env_name(stack, str(key["key"]), key.get("env_var"))
        if name is None or name in seen:
            continue
        value = env_value(stack, name, str(key["role"]), str(key.get("placeholder") or ""),
                          str(key.get("source") or ""), manifest_source, auth)
        if value is None:
            continue
        seen.add(name)
        out.append({"name": name, "role": str(key["role"]), "value": value})
    return out


def downstreams_block(stack: str, env_map: dict[str, Any]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in env_map["keys"]:
        role = str(key["role"])
        if not role.startswith("downstream:"):
            continue
        name = role.split(":", 1)[1]
        env = env_name(stack, str(key["key"]), key.get("env_var"))
        if name in seen or env is None:
            continue
        seen.add(name)
        out.append({"name": name, "envVar": env})
    return out


# --- database and migrations -----------------------------------------------------------


def db_name_from_env(env_map: dict[str, Any]) -> str:
    """Database name from a db placeholder, else a ConnectionStrings__<Name> key, else ``app``."""
    for key in env_map["keys"]:
        if key.get("role") != "db":
            continue
        placeholder = str(key.get("placeholder") or "")
        for pattern in _DB_NAME_RES:
            match = pattern.search(placeholder)
            if match:
                return match.group(1)
    for key in env_map["keys"]:
        match = _CONNECTION_STRING_KEY_RE.match(str(key["key"]))
        if match:
            return match.group(1).lower()
    return "app"


def load_central_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"db_managers": {}}
    data = read_yaml(path)
    managers = data.get("db_managers") or {}
    return {"db_managers": managers if isinstance(managers, dict) else {}}


def select_db_manager(config: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
    managers: dict[str, Any] = config.get("db_managers", {})
    if isinstance(managers.get(name), dict):
        return name, managers[name]
    for key, entry in managers.items():
        if isinstance(entry, dict) and str(entry.get("database", "")) == name:
            return str(key), entry
    return None


def migrations_block(ledger: dict[str, Any], image_flag: str | None,
                     entry: dict[str, Any] | None) -> dict[str, Any]:
    strategy = str((ledger["app"].get("migrations") or {}).get("strategy") or "migration-container")
    image = image_flag or ((entry or {}).get("image"))
    if strategy == "migration-container" and not image:
        raise KbError(
            "no db-manager image: pass --migrations-image or add a db_managers entry for this "
            "database to the central config (design spec 5.5)",
            EXIT_NO_SCHEMA,
        )
    env = dict(DEFAULT_MIGRATION_ENV)
    if entry:
        mapped: dict[str, str] = {}
        for role_key, token in MIGRATION_ENV_TOKENS.items():
            var = (entry.get("env") or {}).get(role_key)
            if var:
                mapped[str(var)] = token
        if mapped:
            env = mapped
        env.update({str(k): str(v) for k, v in (entry.get("extra_env") or {}).items()})
    return {"strategy": strategy, "image": image, "env": env}


# --- messaging, auth, app --------------------------------------------------------------


def amq_block(ledger: dict[str, Any]) -> dict[str, Any]:
    queues: set[str] = set()
    topics: set[str] = set()
    for entry in ledger["entry_points"]:
        if entry.get("kind") == "amq-subscribe" and entry.get("destination"):
            (topics if entry.get("type") == "topic" else queues).add(str(entry["destination"]))
        for item in entry.get("exits", []):
            if item.get("kind") == "amq-publish" and item.get("destination"):
                (topics if item.get("type") == "topic" else queues).add(str(item["destination"]))
    return {"user": "artemis", "password": "artemis", "queues": sorted(queues),
            "topics": sorted(topics)}


def auth_block(ledger: dict[str, Any]) -> dict[str, Any]:
    auth = ledger["app"].get("auth") or {"mode": "none"}
    mode = str(auth.get("mode", "none"))
    if mode == "disabled":
        return {"mode": "disabled", "key": auth.get("key"), "value": str(auth.get("value"))}
    if mode == "jwks":
        return {"mode": "jwks", "issuerKeys": list(auth.get("keys", []))}
    return {"mode": mode}


def app_block(ledger: dict[str, Any], service_root: Path, out_dir: Path) -> dict[str, Any]:
    app = ledger["app"]
    readiness = app.get("readiness") or {}
    try:
        repo_root_rel = Path(os.path.relpath(service_root.resolve(), out_dir.resolve())).as_posix()
    except ValueError:  # different drives on Windows
        repo_root_rel = service_root.resolve().as_posix()
    return {
        "repoRootRel": repo_root_rel,
        "dockerfileRel": app.get("dockerfile") or "Dockerfile",
        "port": int(app.get("port") or 8080),
        "readinessPath": readiness.get("path"),
        "serverless": bool(app.get("serverless", False)),
        "startupTimeoutSeconds": STARTUP_TIMEOUT_SECONDS,
    }


def build_runtime(ledger: dict[str, Any], env_map: dict[str, Any], service_root: Path,
                  out_dir: Path, config: dict[str, Any],
                  migrations_image: str | None) -> dict[str, Any]:
    stack = str(ledger["stack"]["framework"])
    derived = db_name_from_env(env_map)
    selected = select_db_manager(config, derived)
    entry = selected[1] if selected else None
    db_name = str(entry.get("database") or selected[0]) if selected and entry else derived
    return {
        "version": RUNTIME_VERSION,
        "repo": ledger["repo"],
        "stack": stack,
        "app": app_block(ledger, service_root, out_dir),
        "env": env_block(stack, env_map, ledger["app"].get("auth") or {}),
        "db": {"name": db_name, "user": "app", "password": "app"},
        "migrations": migrations_block(ledger, migrations_image, entry),
        "amq": amq_block(ledger),
        "downstreams": downstreams_block(stack, env_map),
        "auth": auth_block(ledger),
    }


# --- copy -----------------------------------------------------------------------------


def copy_template(template_dir: Path, out_dir: Path, force: bool) -> dict[str, list[str]]:
    """Copy the template; returns the relative paths written, overwritten and kept."""
    result: dict[str, list[str]] = {"written": [], "overwritten": [], "kept": []}
    for src in sorted(p for p in template_dir.rglob("*") if p.is_file()):
        rel = src.relative_to(template_dir).as_posix()
        if rel == RUNTIME_REL:
            continue  # always written from the ledger, never copied
        dest = out_dir / rel
        if dest.exists():
            generated = rel.startswith(GENERATED_PREFIXES) or rel in GENERATED_FILES
            if generated or not force:
                result["kept"].append(rel)
                continue
            result["overwritten"].append(rel)
        else:
            result["written"].append(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return result


# --- CLI ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold the Karate module and kb-runtime.json")
    parser.add_argument("repo", type=Path, help="repository root")
    parser.add_argument("--ledger", type=Path, required=True, help="flow-map.yaml")
    parser.add_argument("--env", type=Path, required=True, help="env-map.json")
    parser.add_argument("--out", type=Path, required=True, help="karate-tests directory to create")
    parser.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    parser.add_argument("--migrations-image", default=None, help="db-manager image reference")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="db_managers config, default ~/.karate-bootstrap/config.yaml")
    parser.add_argument("--force", action="store_true",
                        help="overwrite harness files (never generated content)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service_root: Path = args.repo / args.service_dir if args.service_dir else args.repo
    ledger = load_ledger(args.ledger)
    env_map = read_json(require_file(args.env, "env-map.json"))
    if not TEMPLATE_DIR.is_dir():
        raise KbError(f"template missing at {TEMPLATE_DIR}", EXIT_MISSING_OUTPUT)
    config = load_central_config(args.config)
    runtime = build_runtime(ledger, env_map, service_root, args.out, config,
                            args.migrations_image)
    summary = copy_template(TEMPLATE_DIR, args.out, args.force)
    write_json(args.out / RUNTIME_REL, runtime)
    print(f"scaffolded {args.out}: {len(summary['written'])} written, "
          f"{len(summary['overwritten'])} overwritten, {len(summary['kept'])} kept; "
          f"runtime -> {args.out / RUNTIME_REL}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the scaffold tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_scaffold.py -v`
Expected: all pass. If `test_build_runtime_spring_mini` disagrees on `env`, print `runtime["env"]` and compare against the `env-map.json` the fixture produced; the expected list in this plan follows the env-map's sorted key order (uppercase manifest keys first, then config-file keys).

- [ ] **Step 5: Full suite, lint, types, spec command help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_scaffold.py --help`
Expected: green; help lists `repo`, `--ledger`, `--env`, `--out`, `--service-dir`, `--migrations-image`, `--config`, `--force` (the flags in spec 5.5). [[docs-in-sync]]

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_scaffold.py skills/karate-bootstrap/tests/test_kb_scaffold.py
git commit -m "feat(karate-bootstrap): kb_scaffold copies the template and writes kb-runtime.json

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `kb_report.py parse` and `summary`, `README.md.tmpl`

**Confidence:** 92%. The cucumber JSON shape below was captured from a real failing run today (Karate 1.5.2): one file per feature named `<packageQualifiedName>.json` holding a one-element list; `uri` is `features/<name>.feature`; `elements[]` carry `name`, `type: "scenario"`, `keyword` (`Scenario` or `Scenario Outline`, with outline rows already expanded and `<placeholders>` substituted in `name`), `tags[].name`, `steps[].{keyword, name, line, result.{status, error_message}}`; `@known-defect` scenarios are absent from the JSON because the runner's tag filter removes them first, which is why `skipped` is counted from the feature files. The fixture files in this task mirror those fields.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_report.py`
- Create: `skills/karate-bootstrap/templates/karate-tests/README.md.tmpl`
- Create fixtures: `skills/karate-bootstrap/tests/fixtures/karate-reports/features.failing-probe.json`, `features.harness-smoke.json`, `karate-summary-json.txt`; `skills/karate-bootstrap/tests/fixtures/features-known-defect/failing-probe.feature`
- Test: `skills/karate-bootstrap/tests/test_kb_report.py`
- Modify: `skills/karate-bootstrap/tests/test_kb_template.py` (`REQUIRED_FILES` gains `README.md.tmpl`)

**Interfaces:**
- Consumes: `kb_features.known_defect_scenario_count` (Task 2), `flow_map.load_ledger`, `kb_common.{read_text, read_json, write_json, require_file, run_cli, KbError, EXIT_OK, EXIT_MISSING_OUTPUT}`.
- Produces: report JSON `{"passed": int, "skipped": int, "failed": [{"feature": str, "scenario": str, "outline": bool, "tags": list[str], "step": str, "error": str}]}` consumed by `flow_map.py validate --phase green` (which reads `feature`, `scenario`, `tags`) and by `kb_iterate.py` (Task 7, which also reads `outline`, `step`, `error`). Python API: `parse_reports(reports_dir, features_dir) -> dict`, `summary_values(ledger, defects_text, report) -> dict[str, str]`, `render_summary(template_text, values) -> str`, `counts_table(values) -> str`, `defect_titles(defects_text) -> list[str]`.
- CLI (spec 5.7 and 5.8): `python scripts/kb_report.py parse --reports DIR --out PATH [--features DIR]` and `python scripts/kb_report.py summary --ledger PATH --defects PATH --report PATH --template PATH --out PATH`.

- [ ] **Step 1: Write the report fixtures**

`tests/fixtures/karate-reports/features.failing-probe.json`:

```json
[{"line":2,"elements":[
 {"start_timestamp":"2026-09-05T20:15:36.000Z","line":4,"name":"a failing match","description":"","id":"a-failing-match","type":"scenario","keyword":"Scenario",
  "steps":[
   {"name":"def x = { a: 1 }","result":{"duration":48394500,"status":"passed"},"match":{"location":"karate"},"keyword":"*","line":5},
   {"name":"match x == { a: 2 }","result":{"duration":16206300,"status":"failed","error_message":"match failed: EQUALS\n  $ | not equal | match failed for name: 'a' (MAP:MAP)\n  {\"a\":1}\n  {\"a\":2}\n\n    $.a | not equal (NUMBER:NUMBER)\n    1\n    2\n\nclasspath:features/failing-probe.feature:6"},"match":{"location":"karate"},"keyword":"*","line":6}],
  "tags":[{"name":"@probe","line":1}]},
 {"start_timestamp":"2026-09-05T20:15:36.100Z","line":17,"name":"outline row R1","description":"","id":"outline-row-r1","type":"scenario","keyword":"Scenario Outline",
  "steps":[{"name":"match 1 == 1","result":{"duration":1000000,"status":"passed"},"match":{"location":"karate"},"keyword":"*","line":13}],
  "tags":[{"name":"@probe","line":1}]},
 {"start_timestamp":"2026-09-05T20:15:36.100Z","line":18,"name":"outline row R2","description":"","id":"outline-row-r2","type":"scenario","keyword":"Scenario Outline",
  "steps":[{"name":"match 1 == 3","result":{"duration":1000000,"status":"failed","error_message":"match failed: EQUALS\n  $ | not equal (NUMBER:NUMBER)\n  1\n  3\n\nclasspath:features/failing-probe.feature:13"},"match":{"location":"karate"},"keyword":"*","line":13}],
  "tags":[{"name":"@probe","line":1}]}
 ],"name":"features/failing-probe.feature","description":"probe failure shapes","id":"probe-failure-shapes","keyword":"Feature","uri":"features/failing-probe.feature","tags":[{"name":"@probe","line":1}]}]
```

`tests/fixtures/karate-reports/features.harness-smoke.json`:

```json
[{"line":2,"elements":[
 {"start_timestamp":"2026-09-05T20:15:36.000Z","line":4,"name":"runtime configuration is on the classpath","description":"","id":"runtime-configuration-is-on-the-classpath","type":"scenario","keyword":"Scenario",
  "steps":[{"name":"match skipContainers == true","result":{"duration":1000000,"status":"passed"},"match":{"location":"karate"},"keyword":"*","line":5}],
  "tags":[{"name":"@harness","line":1}]}
 ],"name":"features/harness-smoke.feature","description":"harness self-test that needs no containers","id":"harness-self-test-that-needs-no-containers","keyword":"Feature","uri":"features/harness-smoke.feature","tags":[{"name":"@harness","line":1}]}]
```

`tests/fixtures/karate-reports/karate-summary-json.txt` (Karate writes this next to the cucumber JSON; the parser must ignore it):

```json
{"efficiency":0.035,"totalTime":501.0,"threads":4,"resultDate":"2026-09-05 09:15:36 pm","env":null,"version":"1.5.2","scenariosfailed":2,"featureSummary":[{"failedCount":2,"packageQualifiedName":"features.failing-probe","relativePath":"features/failing-probe.feature","scenarioCount":3,"name":"probe failure shapes","description":"","durationMillis":83.9,"passedCount":1,"failed":true},{"failedCount":0,"packageQualifiedName":"features.harness-smoke","relativePath":"features/harness-smoke.feature","scenarioCount":1,"name":"harness self-test that needs no containers","description":"","durationMillis":416.7,"passedCount":1,"failed":false}],"featuresPassed":1,"featuresFailed":1,"featuresSkipped":0,"scenariosPassed":2,"elapsedTime":3566.0}
```

`tests/fixtures/features-known-defect/failing-probe.feature`:

```gherkin
@probe
Feature: probe failure shapes

Scenario: a failing match
  * def x = { a: 1 }
  * match x == { a: 2 }

@known-defect
Scenario: quarantined scenario is removed by the tag filter
  * match 1 == 2

Scenario Outline: outline row <rule_id>
  * match <a> == <b>

  Examples:
    | rule_id | a | b |
    | R1      | 1 | 1 |
    | R2      | 1 | 3 |
```

- [ ] **Step 2: Write `tests/test_kb_report.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger
from kb_common import EXIT_MISSING_OUTPUT, KbError, read_json, run_cli
from kb_report import (
    counts_table,
    defect_titles,
    main,
    parse_reports,
    render_summary,
    summary_values,
)

FIXTURES = Path(__file__).parent / "fixtures"
REPORTS = FIXTURES / "karate-reports"
FEATURES = FIXTURES / "features-known-defect"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests" / "README.md.tmpl"
DEFECTS = (
    "# Suspected application defects\n\n"
    "## DEF-001: POST /api/shipments returns 500 for an unknown carrier\n"
    "status: pending\nslug: post-api-shipments-500-unknown-carrier\nseverity: high\n"
    "category: app-defect\nentry_point: POST /api/shipments\n"
    "scenario: features/post-api-shipments.feature:40\n"
    "evidence: |\n  response: 500\nroot_cause: ShipmentService.java:33 dereferences null\n"
    "suggested_fix: return 422\n\n"
    "## DEF-002: GET /api/shipments/{id} leaks stack trace\n"
    "status: pending\nentry_point: GET /api/shipments/{id}\n"
)


def test_parse_reports_reads_every_cucumber_json_and_counts_known_defects() -> None:
    report = parse_reports(REPORTS, FEATURES)
    assert report["passed"] == 2
    assert report["skipped"] == 1
    assert [f["scenario"] for f in report["failed"]] == ["a failing match", "outline row R2"]
    first = report["failed"][0]
    assert first == {
        "feature": "features/failing-probe.feature",
        "scenario": "a failing match",
        "outline": False,
        "tags": ["@probe"],
        "step": "* match x == { a: 2 }",
        "error": first["error"],
    }
    assert first["error"].startswith("match failed: EQUALS")
    assert first["error"].endswith("classpath:features/failing-probe.feature:6")
    assert report["failed"][1]["outline"] is True
    assert report["failed"][1]["step"] == "* match 1 == 3"


def test_parse_reports_without_features_dir_reports_zero_skipped(tmp_path: Path) -> None:
    assert parse_reports(REPORTS, tmp_path / "absent")["skipped"] == 0
    assert parse_reports(REPORTS, None)["skipped"] == 0


def test_parse_reports_requires_cucumber_json(tmp_path: Path) -> None:
    (tmp_path / "karate-summary-json.txt").write_text("{}", encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        parse_reports(tmp_path, None)
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT


def _spring_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = FIXTURES / "spring-mini"
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return ledger, load_ledger(ledger)


def test_defect_titles_reads_headings() -> None:
    assert defect_titles(DEFECTS) == [
        "DEF-001: POST /api/shipments returns 500 for an unknown carrier",
        "DEF-002: GET /api/shipments/{id} leaks stack trace",
    ]
    assert defect_titles("") == []


def test_summary_values_and_render(tmp_path: Path) -> None:
    _, ledger = _spring_ledger(tmp_path)
    post = find_entry(ledger, "POST /api/shipments")
    post["exits"] = [
        {"kind": "db-write", "table": "shipments", "op": "insert", "via": "x:1"},
        {"kind": "amq-publish", "destination": "shipment.created", "type": "queue", "via": "x:2"},
        {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET", "path": "/rates/{c}",
         "via": "x:3"},
    ]
    post["rules"].update({"file": "rules/post-api-shipments.csv", "count": 12})
    post["observed_overrides"] = [{"scenario": "happy", "field": "status", "old": 201, "new": 200}]
    ledger["app"]["migrations"]["image"] = "registry.example/db-manager:1"
    failure = {"feature": "f", "scenario": "s", "outline": False, "tags": [], "step": "x",
               "error": "e"}
    report = {"passed": 9, "skipped": 1, "failed": [failure]}
    values = summary_values(ledger, DEFECTS, report)
    assert values["repo"] == "spring-mini"
    assert values["stack"] == "spring (java)"
    assert values["entry_points"] == "3"
    assert (values["exits_db"], values["exits_amq"], values["exits_http"]) == ("1", "1", "1")
    assert values["scenarios"] == "11"
    assert values["rules_rows"] == "12"
    assert (values["passing"], values["failing"], values["quarantined"]) == ("9", "1", "1")
    assert values["auth_mode"] == "disabled"
    assert values["migrations_image"] == "registry.example/db-manager:1"
    assert values["readiness"] == "/actuator/health/readiness"
    assert "POST /api/shipments" in values["overrides"] and '"old": 201' in values["overrides"]
    assert values["defects"].splitlines() == [
        "- DEF-001: POST /api/shipments returns 500 for an unknown carrier",
        "- DEF-002: GET /api/shipments/{id} leaks stack trace",
    ]
    assert values["notes"] == "- none"
    readme = render_summary(TEMPLATE.read_text(encoding="utf-8"), values)
    assert "# Karate tests for spring-mini" in readme
    assert "| Entry points | 3 |" in readme
    assert "- DEF-001:" in readme
    assert "$" not in readme.replace("${XDG_RUNTIME_DIR}", "")
    table = counts_table(values)
    assert "Entry points" in table and "Quarantined" in table


def test_summary_values_notes_fallbacks(tmp_path: Path) -> None:
    _, ledger = _spring_ledger(tmp_path)
    ledger["app"]["readiness"] = {"path": None, "port": 8080, "source": "fallback"}
    ledger["app"]["auth"] = {"mode": "blocked"}
    ledger["app"]["migrations"]["also_on_boot"] = True
    values = summary_values(ledger, "", {"passed": 0, "skipped": 0, "failed": []})
    assert values["readiness"] == "port 8080 (fallback)"
    assert values["defects"] == "- none"
    assert values["overrides"] == "- none"
    notes = values["notes"].splitlines()
    assert any("readiness" in n for n in notes)
    assert any("blocked" in n for n in notes)
    assert any("boot" in n for n in notes)


def test_cli_parse_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "report.json"
    assert run_cli(main, ["parse", "--reports", str(REPORTS), "--out", str(out),
                          "--features", str(FEATURES)]) == 0
    report = read_json(out)
    assert (report["passed"], report["skipped"], len(report["failed"])) == (2, 1, 2)
    assert "passed: 2" in capsys.readouterr().out
    ledger_path, _ = _spring_ledger(tmp_path)
    defects = tmp_path / "defects.md"
    defects.write_text(DEFECTS, encoding="utf-8")
    readme = tmp_path / "README.md"
    assert run_cli(main, ["summary", "--ledger", str(ledger_path), "--defects", str(defects),
                          "--report", str(out), "--template", str(TEMPLATE),
                          "--out", str(readme)]) == 0
    text = readme.read_text(encoding="utf-8")
    assert "# Karate tests for spring-mini" in text and "- DEF-002:" in text
    assert "Entry points" in capsys.readouterr().out
    assert run_cli(main, ["parse", "--reports", str(tmp_path / "nope"), "--out", str(out)]) == 5


def test_parse_default_features_dir_is_the_module_layout(tmp_path: Path) -> None:
    module = tmp_path / "karate-tests"
    reports = module / "target" / "karate-reports"
    reports.mkdir(parents=True)
    for name in ("features.failing-probe.json", "features.harness-smoke.json"):
        (reports / name).write_text((REPORTS / name).read_text(encoding="utf-8"), encoding="utf-8")
    features = module / "src/test/resources/features"
    features.mkdir(parents=True)
    (features / "x.feature").write_text((FEATURES / "failing-probe.feature").read_text("utf-8"),
                                        encoding="utf-8")
    out = module / "target" / "report.json"
    assert run_cli(main, ["parse", "--reports", str(reports), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["skipped"] == 1
```

- [ ] **Step 3: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_report.py -v`
Expected: `ModuleNotFoundError: No module named 'kb_report'`.

- [ ] **Step 4: Write `templates/karate-tests/README.md.tmpl`**

The file uses `string.Template` syntax: `$name` placeholders, `$$` for a literal dollar.

````markdown
# Karate tests for $repo

Generated by karate-bootstrap for a $stack service. These tests document observed behaviour.
Suspected application defects are quarantined with `@known-defect` and listed in `defects.md`,
not fixed.

## Run

```bash
cd karate-tests
mvn test                            # JDK 17 or newer plus a container engine (docker or podman)
mvn test -Dkb.threads=1             # sequential fallback if parallel scenarios interfere
mvn test -Dkb.skipContainers=true   # harness self-test, no containers
mvn test -Dkarate.options="--tags @smoke"
mvn test -Dapp.image=<tag>          # test a prebuilt image instead of building the Dockerfile
```

Podman: `export DOCKER_HOST=unix://$${XDG_RUNTIME_DIR}/podman/podman.sock` on Linux, or the socket
path from `podman machine inspect` on Windows or macOS. Set `TESTCONTAINERS_RYUK_DISABLED=true` if
Ryuk cannot run privileged. Azure DevOps: include `azure-pipelines.karate.yml` from the service
pipeline.

## What is covered

| Item | Count |
|------|------:|
| Entry points | $entry_points |
| DB write exits | $exits_db |
| AMQ publish exits | $exits_amq |
| Outbound HTTP exits | $exits_http |
| Scenarios | $scenarios |
| Validation rule rows | $rules_rows |
| Passing | $passing |
| Failing | $failing |
| Quarantined (`@known-defect`) | $quarantined |

Auth mode: $auth_mode. Schema: db-manager image `$migrations_image` runs before the app starts.
Readiness: $readiness.

## Observed-behaviour overrides

$overrides

## Quarantined suspected defects

$defects

## Notes

$notes
````

Add `"README.md.tmpl",` to `REQUIRED_FILES` in `tests/test_kb_template.py` after the `defects.md` line.

- [ ] **Step 5: Create `scripts/kb_report.py`**

```python
"""Phases 6 and 7 of karate-bootstrap: parse Karate reports, render the README.

``parse`` reads Karate's cucumber JSON (one ``<packageQualifiedName>.json`` per feature under
``target/karate-reports``) into the report contract the green gate and kb_iterate.py consume:
``{"passed", "skipped", "failed": [{"feature", "scenario", "outline", "tags", "step", "error"}]}``.
``skipped`` counts ``@known-defect`` scenarios in the features directory, because the runner's
tag filter removes them before any report is written.

``summary`` fills ``README.md.tmpl`` from the ledger, defects.md and the report, and prints the
counts table.

Usage:
    python scripts/kb_report.py parse --reports karate-tests/target/karate-reports \
        --out karate-tests/target/report.json [--features karate-tests/src/test/resources/features]
    python scripts/kb_report.py summary --ledger karate-tests/flow-map.yaml \
        --defects karate-tests/defects.md --report karate-tests/target/report.json \
        --template <skill>/templates/karate-tests/README.md.tmpl --out karate-tests/README.md

Exit codes: 0 ok, 5 when the reports directory holds no cucumber JSON or an input is missing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from string import Template
from typing import Any

from flow_map import load_ledger
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_OK,
    KbError,
    read_json,
    read_text,
    require_file,
    run_cli,
    write_json,
)
from kb_features import known_defect_scenario_count

_DEFECT_HEADING_RE = re.compile(r"^## (DEF-\d+:.*?)\s*$", re.MULTILINE)


# --- parse ------------------------------------------------------------------------------


def cucumber_files(reports_dir: Path) -> list[Path]:
    """Karate writes ``<packageQualifiedName>.json`` per feature; the summary is a ``.txt``."""
    return sorted(p for p in reports_dir.glob("*.json") if p.is_file())


def _failed_entry(uri: str, element: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    result = step.get("result", {})
    return {
        "feature": uri,
        "scenario": str(element.get("name", "")),
        "outline": element.get("keyword") == "Scenario Outline",
        "tags": [str(t["name"]) for t in element.get("tags", []) if "name" in t],
        "step": f"{str(step.get('keyword', '*')).strip()} {step.get('name', '')}".strip(),
        "error": str(result.get("error_message", "")),
    }


def parse_reports(reports_dir: Path, features_dir: Path | None) -> dict[str, Any]:
    files = cucumber_files(reports_dir)
    if not files:
        raise KbError(f"no cucumber JSON under {reports_dir}; run mvn test first",
                      EXIT_MISSING_OUTPUT)
    passed = 0
    failed: list[dict[str, Any]] = []
    for path in files:
        data = json.loads(read_text(path))
        if not isinstance(data, list):
            continue
        for feature in data:
            uri = str(feature.get("uri") or feature.get("name") or path.stem)
            for element in feature.get("elements", []):
                if element.get("type") != "scenario":
                    continue
                failing = next(
                    (s for s in element.get("steps", [])
                     if s.get("result", {}).get("status") == "failed"),
                    None,
                )
                if failing is None:
                    passed += 1
                else:
                    failed.append(_failed_entry(uri, element, failing))
    skipped = 0
    if features_dir is not None and features_dir.is_dir():
        skipped = sum(known_defect_scenario_count(read_text(f))
                      for f in sorted(features_dir.rglob("*.feature")))
    return {"passed": passed, "skipped": skipped, "failed": failed}


def default_features_dir(reports_dir: Path) -> Path | None:
    """The module's features directory when reports live at ``<module>/target/karate-reports``."""
    module = reports_dir.resolve().parent.parent
    candidate = module / "src" / "test" / "resources" / "features"
    return candidate if candidate.is_dir() else None


# --- summary ----------------------------------------------------------------------------


def defect_titles(defects_text: str) -> list[str]:
    return _DEFECT_HEADING_RE.findall(defects_text)


def summary_values(ledger: dict[str, Any], defects_text: str,
                   report: dict[str, Any]) -> dict[str, str]:
    entries: list[dict[str, Any]] = ledger["entry_points"]
    exits = [e for entry in entries for e in entry.get("exits", [])]
    app = ledger["app"]
    readiness = app.get("readiness") or {}
    auth = app.get("auth") or {}
    migrations = app.get("migrations") or {}
    overrides = [
        f"- {entry['id']}: {json.dumps(item, sort_keys=True)}"
        for entry in entries for item in entry.get("observed_overrides", [])
    ]
    notes: list[str] = []
    if readiness.get("source") == "fallback":
        notes.append("- readiness: no manifest probe; the harness waits for the container port")
    if auth.get("mode") == "blocked":
        notes.append("- auth: blocked (no switch, no configurable issuer); 401/403 not exercised")
    if auth.get("mode") == "disabled" and auth.get("confirmed") is False:
        notes.append(f"- auth: switch {auth.get('key')} was never confirmed")
    if migrations.get("also_on_boot"):
        notes.append("- migrations: the app also migrates on boot; the db-manager image runs first")
    failing = len(report.get("failed", []))
    scenarios = int(report.get("passed", 0)) + int(report.get("skipped", 0)) + failing

    def count(kind: str) -> str:
        return str(sum(1 for e in exits if e.get("kind") == kind))

    return {
        "repo": str(ledger["repo"]),
        "stack": f"{ledger['stack'].get('framework')} ({ledger['stack'].get('language')})",
        "entry_points": str(len(entries)),
        "exits_db": count("db-write"),
        "exits_amq": count("amq-publish"),
        "exits_http": count("http-out"),
        "scenarios": str(scenarios),
        "rules_rows": str(sum(int((entry.get("rules") or {}).get("count") or 0)
                              for entry in entries)),
        "passing": str(report.get("passed", 0)),
        "failing": str(failing),
        "quarantined": str(report.get("skipped", 0)),
        "auth_mode": str(auth.get("mode", "none")),
        "migrations_image": str(migrations.get("image") or "not set"),
        "readiness": str(readiness.get("path") or f"port {app.get('port')} (fallback)"),
        "overrides": "\n".join(overrides) or "- none",
        "defects": "\n".join(f"- {title}" for title in defect_titles(defects_text)) or "- none",
        "notes": "\n".join(notes) or "- none",
    }


def render_summary(template_text: str, values: dict[str, str]) -> str:
    return Template(template_text).safe_substitute(values)


def counts_table(values: dict[str, str]) -> str:
    rows = (
        ("Entry points", values["entry_points"]),
        ("DB write exits", values["exits_db"]),
        ("AMQ publish exits", values["exits_amq"]),
        ("Outbound HTTP exits", values["exits_http"]),
        ("Scenarios", values["scenarios"]),
        ("Validation rule rows", values["rules_rows"]),
        ("Passing", values["passing"]),
        ("Failing", values["failing"]),
        ("Quarantined", values["quarantined"]),
    )
    return "\n".join(f"{label:<22} {value:>6}" for label, value in rows)


# --- CLI --------------------------------------------------------------------------------


def _cmd_parse(args: argparse.Namespace) -> int:
    features = args.features if args.features is not None else default_features_dir(args.reports)
    report = parse_reports(args.reports, features)
    write_json(args.out, report)
    print(f"passed: {report['passed']}  skipped: {report['skipped']}  "
          f"failed: {len(report['failed'])} -> {args.out}")
    return EXIT_OK


def _cmd_summary(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    defects_text = read_text(args.defects) if args.defects.is_file() else ""
    report = read_json(require_file(args.report, "report.json"))
    template_text = read_text(require_file(args.template, "README.md.tmpl"))
    values = summary_values(ledger, defects_text, report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_summary(template_text, values), encoding="utf-8")
    print(counts_table(values))
    print(f"README -> {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Karate reports and render the README")
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="Cucumber JSON -> report.json")
    parse.add_argument("--reports", type=Path, required=True, help="target/karate-reports")
    parse.add_argument("--out", type=Path, required=True, help="report.json to write")
    parse.add_argument("--features", type=Path, default=None,
                       help="features dir for the @known-defect count (default: module layout)")
    parse.set_defaults(func=_cmd_parse)

    summary = sub.add_parser("summary", help="Render README.md from the ledger, defects and report")
    summary.add_argument("--ledger", type=Path, required=True)
    summary.add_argument("--defects", type=Path, required=True)
    summary.add_argument("--report", type=Path, required=True)
    summary.add_argument("--template", type=Path, required=True, help="README.md.tmpl")
    summary.add_argument("--out", type=Path, required=True)
    summary.set_defaults(func=_cmd_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 6: Run the report and template tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/test_kb_template.py -v`
Expected: all pass (the Maven test still skipped).

- [ ] **Step 7: Full suite, lint, types, spec command help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_report.py parse --help` then `python skills/karate-bootstrap/scripts/kb_report.py summary --help`
Expected: green; `parse` lists `--reports`, `--out`, `--features`; `summary` lists `--ledger`, `--defects`, `--report`, `--template`, `--out`. [[docs-in-sync]]

- [ ] **Step 8: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_report.py skills/karate-bootstrap/templates/karate-tests/README.md.tmpl skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/test_kb_template.py skills/karate-bootstrap/tests/fixtures/karate-reports skills/karate-bootstrap/tests/fixtures/features-known-defect
git commit -m "feat(karate-bootstrap): kb_report parses cucumber JSON and renders the README

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `kb_iterate.py next`, `log`, `check-stop`

**Confidence:** 91%. Pure data over the report JSON (Task 6's contract), a JSONL log and the harness log files that `Containers.java` writes (`target/app.log`, `target/db-manager.log`, `target/stubs-unmatched.json`). Nothing external is called.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_iterate.py`
- Test: `skills/karate-bootstrap/tests/test_kb_iterate.py`

**Interfaces:**
- Consumes: report JSON from Task 6 (`failed[].{feature, scenario, outline, step, error, tags}`); `kb_common.{read_json, read_text, require_file, run_cli, KbError, EXIT_OK, EXIT_STOPPED}`.
- Produces for the skill (Plan 3's `SKILL.md`): the three commands in spec 5.7. Python API for tests: `error_class(error) -> str`, `signature(failure) -> str`, `group_failures(report) -> list[dict]`, `evidence(tests_dir) -> dict`, `append_log(path, record) -> int`, `read_log(path) -> list[dict]`, `check_stop(records, report, max_iterations) -> str`, constants `CLASSIFICATIONS`, `REPEAT_LIMIT`.
- CLI (spec 5.7): `next --report PATH --tests-dir DIR`, `log --log PATH --signature SIG --hypothesis TEXT --change TEXT --classification {infra,stub-or-seed,expectation,app-defect} [--unfixable]`, `check-stop --log PATH --report PATH --max-iterations N` (exit 0 with `continue` or `done`, exit 6 with `stop:<reason>`).

- [ ] **Step 1: Write `tests/test_kb_iterate.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from kb_common import EXIT_STOPPED, KbError, run_cli
from kb_iterate import (
    CLASSIFICATIONS,
    REPEAT_LIMIT,
    append_log,
    check_stop,
    error_class,
    evidence,
    group_failures,
    main,
    read_log,
    signature,
)

ERROR = ("match failed: EQUALS\n  $ | not equal | match failed for name: 'a' (MAP:MAP)\n"
         "  {\"a\":1}\n  {\"a\":2}\n\nclasspath:features/failing-probe.feature:6")


def _failure(scenario: str, outline: bool = False, error: str = ERROR,
             step: str = "* match x == { a: 2 }",
             feature: str = "features/f.feature") -> dict[str, Any]:
    return {"feature": feature, "scenario": scenario, "outline": outline, "tags": ["@rules"],
            "step": step, "error": error}


def test_error_class_normalises_numbers_quotes_and_urls() -> None:
    assert error_class(ERROR) == "match failed: EQUALS"
    assert error_class("status code was: 500, expected: 201, response: http://app:8080/api/x") == (
        "status code was: N, expected: N, response: URL"
    )
    assert error_class("no row in deals matching {external_id='EXT-42'} within 5000ms") == (
        "no row in deals matching {external_id='?'} within Nms"
    )
    assert error_class("") == ""


def test_signature_collapses_outline_rows_but_not_plain_scenarios() -> None:
    plain_a = signature(_failure("a"))
    plain_b = signature(_failure("b"))
    assert plain_a != plain_b
    assert signature(_failure("rule R001 on x", outline=True)) == signature(
        _failure("rule R002 on y", outline=True)
    )
    assert signature(_failure("a")) == (
        "features/f.feature|a|* match x == { a: 2 }|match failed: EQUALS"
    )


def test_group_failures_orders_by_count_then_first_seen() -> None:
    report = {"passed": 1, "skipped": 0, "failed": [
        _failure("only once"),
        _failure("rule R001", outline=True),
        _failure("rule R002", outline=True),
        _failure("rule R003", outline=True),
        _failure("other", error="status code was: 500"),
    ]}
    groups = group_failures(report)
    assert [g["count"] for g in groups] == [3, 1, 1]
    assert groups[0]["scenario"] == "rule R001"
    assert groups[0]["error_class"] == "match failed: EQUALS"
    assert groups[1]["scenario"] == "only once"
    assert groups[2]["error_class"] == "status code was: N"


def test_evidence_reads_logs_and_unmatched_when_present(tmp_path: Path) -> None:
    assert evidence(tmp_path) == {"app_log_tail": None, "db_manager_log_tail": None,
                                  "stubs_unmatched": None}
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.log").write_text("\n".join(f"line {i}" for i in range(100)), encoding="utf-8")
    (target / "db-manager.log").write_text("migrated", encoding="utf-8")
    (target / "stubs-unmatched.json").write_text(
        json.dumps({"unmatched": {"requests": [{"url": "/pricing/rates/GB"}]}, "nearMisses": {}}),
        encoding="utf-8")
    bundle = evidence(tmp_path)
    assert bundle["app_log_tail"].splitlines()[0] == "line 20"
    assert bundle["app_log_tail"].splitlines()[-1] == "line 99"
    assert bundle["db_manager_log_tail"] == "migrated"
    assert bundle["stubs_unmatched"]["unmatched"]["requests"][0]["url"] == "/pricing/rates/GB"


def test_log_appends_numbered_records(tmp_path: Path) -> None:
    log = tmp_path / ".iterations.log"
    assert read_log(log) == []
    assert append_log(log, {"signature": "s1", "hypothesis": "h", "change": "c",
                            "classification": "infra", "unfixable": False}) == 1
    assert append_log(log, {"signature": "s2", "hypothesis": "h", "change": "c",
                            "classification": "expectation", "unfixable": False}) == 2
    records = read_log(log)
    assert [r["iteration"] for r in records] == [1, 2]
    assert records[0]["signature"] == "s1" and "at" in records[0]
    with pytest.raises(KbError):
        append_log(log, {"signature": "s3", "classification": "nope"})


def test_check_stop_rules() -> None:
    failing = {"passed": 1, "skipped": 0, "failed": [_failure("a")]}
    green = {"passed": 2, "skipped": 0, "failed": []}
    rec = [{"iteration": i, "signature": s, "classification": "expectation", "unfixable": False}
           for i, s in enumerate(["s1", "s2", "s3"], start=1)]
    assert check_stop([], failing, 15) == "continue"
    assert check_stop(rec, failing, 15) == "continue"
    assert check_stop(rec, green, 15) == "done"
    assert check_stop(rec, failing, 3) == "stop:iteration-cap 3"
    same = [dict(r, signature="same") for r in rec]
    assert REPEAT_LIMIT == 3
    assert check_stop(same, failing, 15) == "stop:repeated-signature same"
    assert check_stop(same[:2], failing, 15) == "continue"
    stuck = rec + [{"iteration": 4, "signature": "s4", "classification": "infra",
                    "unfixable": True}]
    assert check_stop(stuck, failing, 15) == "stop:infra-unfixable"
    assert set(CLASSIFICATIONS) == {"infra", "stub-or-seed", "expectation", "app-defect"}


def test_cli_next_log_check_stop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tests_dir = tmp_path / "karate-tests"
    (tests_dir / "target").mkdir(parents=True)
    (tests_dir / "target" / "app.log").write_text("boom", encoding="utf-8")
    report = tests_dir / "target" / "report.json"
    report.write_text(json.dumps({"passed": 0, "skipped": 0, "failed": [
        _failure("rule R001", outline=True), _failure("rule R002", outline=True),
    ]}), encoding="utf-8")
    assert run_cli(main, ["next", "--report", str(report), "--tests-dir", str(tests_dir)]) == 0
    top = json.loads(capsys.readouterr().out)
    assert top["count"] == 2 and top["groups"] == 1
    assert top["evidence"]["app_log_tail"] == "boom"
    log = tests_dir / ".iterations.log"
    for _ in range(3):
        assert run_cli(main, ["log", "--log", str(log), "--signature", top["signature"],
                              "--hypothesis", "mutation value off by one", "--change", "rules csv",
                              "--classification", "expectation"]) == 0
    capsys.readouterr()
    assert run_cli(main, ["check-stop", "--log", str(log), "--report", str(report),
                          "--max-iterations", "15"]) == EXIT_STOPPED
    assert capsys.readouterr().out.startswith("stop:repeated-signature")
    report.write_text(json.dumps({"passed": 5, "skipped": 0, "failed": []}), encoding="utf-8")
    assert run_cli(main, ["check-stop", "--log", str(log), "--report", str(report),
                          "--max-iterations", "15"]) == 0
    assert capsys.readouterr().out.strip() == "done"
    assert run_cli(main, ["next", "--report", str(report), "--tests-dir", str(tests_dir)]) == 0
    assert json.loads(capsys.readouterr().out) == {"done": True}
    with pytest.raises(SystemExit) as excinfo:  # argparse rejects a value outside choices
        main(["log", "--log", str(log), "--signature", "x", "--hypothesis", "h",
              "--change", "c", "--classification", "bogus"])
    assert excinfo.value.code == 2
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_iterate.py -v`
Expected: `ModuleNotFoundError: No module named 'kb_iterate'`.

- [ ] **Step 3: Create `scripts/kb_iterate.py`**

```python
"""Phase 6 of karate-bootstrap: bookkeeping for the fix loop (design spec 5.7).

``next`` groups the failures in report.json by signature and prints the largest group with
its evidence bundle. ``log`` appends one iteration record (hypothesis, change, classification)
to a JSONL log; it is written before the change is made. ``check-stop`` applies the stop
conditions and prints ``done`` (no failures), ``continue``, or ``stop:<reason>`` with exit 6.

Usage:
    python scripts/kb_iterate.py next --report karate-tests/target/report.json \
        --tests-dir karate-tests
    python scripts/kb_iterate.py log --log karate-tests/.iterations.log --signature <sig> \
        --hypothesis "..." --change "..." \
        --classification infra|stub-or-seed|expectation|app-defect [--unfixable]
    python scripts/kb_iterate.py check-stop --log karate-tests/.iterations.log \
        --report karate-tests/target/report.json --max-iterations 15

Signature: feature | scenario (collapsed to <outline> for Scenario Outline rows) | first failing
step | error class (first error line with numbers, quoted strings and URLs normalised).

Exit codes: 0 continue or done, 2 bad input, 5 missing report, 6 stop condition met.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kb_common import (
    EXIT_OK,
    EXIT_STOPPED,
    KbError,
    read_json,
    read_text,
    require_file,
    run_cli,
)

CLASSIFICATIONS = ("infra", "stub-or-seed", "expectation", "app-defect")
REPEAT_LIMIT = 3
LOG_TAIL_LINES = 80

_URL_RE = re.compile(r"https?://\S+")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_NUMBER_RE = re.compile(r"\d+")


# --- signatures --------------------------------------------------------------------------


def error_class(error: str) -> str:
    """First non-empty error line with URLs, quoted strings and numbers normalised."""
    first = next((line.strip() for line in error.splitlines() if line.strip()), "")
    first = _URL_RE.sub("URL", first)
    first = _QUOTED_RE.sub("'?'", first)
    return _NUMBER_RE.sub("N", first)[:160]


def signature(failure: dict[str, Any]) -> str:
    scenario = "<outline>" if failure.get("outline") else str(failure.get("scenario", ""))
    return "|".join([str(failure.get("feature", "")), scenario, str(failure.get("step", "")),
                     error_class(str(failure.get("error", "")))])


def group_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Failure groups, largest first; ties keep first-seen order (sorted is stable)."""
    groups: dict[str, dict[str, Any]] = {}
    for failure in report.get("failed", []):
        sig = signature(failure)
        group = groups.setdefault(sig, {
            "signature": sig,
            "count": 0,
            "feature": failure.get("feature"),
            "scenario": failure.get("scenario"),
            "outline": bool(failure.get("outline")),
            "step": failure.get("step"),
            "error_class": error_class(str(failure.get("error", ""))),
            "error": failure.get("error", ""),
            "tags": list(failure.get("tags", [])),
        })
        group["count"] += 1
    return sorted(groups.values(), key=lambda g: -int(g["count"]))


# --- evidence ----------------------------------------------------------------------------


def _tail(path: Path, lines: int = LOG_TAIL_LINES) -> str | None:
    if not path.is_file():
        return None
    return "\n".join(read_text(path).splitlines()[-lines:])


def evidence(tests_dir: Path) -> dict[str, Any]:
    """Evidence bundle from the files Containers.java and Stubs.unmatched() write under target/."""
    target = tests_dir / "target"
    unmatched_path = target / "stubs-unmatched.json"
    unmatched: Any = None
    if unmatched_path.is_file():
        try:
            unmatched = json.loads(read_text(unmatched_path))
        except json.JSONDecodeError:
            unmatched = read_text(unmatched_path)
    return {
        "app_log_tail": _tail(target / "app.log"),
        "db_manager_log_tail": _tail(target / "db-manager.log"),
        "stubs_unmatched": unmatched,
    }


# --- iteration log -----------------------------------------------------------------------


def read_log(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in read_text(path).splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def append_log(path: Path, record: dict[str, Any]) -> int:
    """Append one iteration; returns its 1-based number."""
    if record.get("classification") not in CLASSIFICATIONS:
        raise KbError(
            f"unknown classification {record.get('classification')!r}; "
            f"expected one of {CLASSIFICATIONS}"
        )
    records = read_log(path)
    number = len(records) + 1
    full = {"iteration": number, "at": datetime.now(UTC).isoformat(timespec="seconds"), **record}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(full) + "\n")
    return number


def check_stop(records: list[dict[str, Any]], report: dict[str, Any], max_iterations: int) -> str:
    if not report.get("failed"):
        return "done"
    if len(records) >= max_iterations:
        return f"stop:iteration-cap {max_iterations}"
    if records and records[-1].get("unfixable"):
        return "stop:infra-unfixable"
    recent = records[-REPEAT_LIMIT:]
    if len(recent) == REPEAT_LIMIT and len({str(r.get("signature")) for r in recent}) == 1:
        return f"stop:repeated-signature {recent[-1].get('signature')}"
    return "continue"


# --- CLI ---------------------------------------------------------------------------------


def _cmd_next(args: argparse.Namespace) -> int:
    report = read_json(require_file(args.report, "report.json"))
    groups = group_failures(report)
    if not groups:
        print(json.dumps({"done": True}))
        return EXIT_OK
    top = dict(groups[0])
    top["groups"] = len(groups)
    top["evidence"] = evidence(args.tests_dir)
    print(json.dumps(top, indent=2))
    return EXIT_OK


def _cmd_log(args: argparse.Namespace) -> int:
    number = append_log(args.log, {
        "signature": args.signature,
        "hypothesis": args.hypothesis,
        "change": args.change,
        "classification": args.classification,
        "unfixable": bool(args.unfixable),
    })
    print(f"iteration {number} logged -> {args.log}")
    return EXIT_OK


def _cmd_check_stop(args: argparse.Namespace) -> int:
    report = read_json(require_file(args.report, "report.json"))
    verdict = check_stop(read_log(args.log), report, args.max_iterations)
    print(verdict)
    return EXIT_STOPPED if verdict.startswith("stop:") else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fix-loop bookkeeping for karate-bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="Print the largest failure group with its evidence")
    nxt.add_argument("--report", type=Path, required=True,
                     help="report.json from kb_report.py parse")
    nxt.add_argument("--tests-dir", type=Path, required=True, help="karate-tests directory")
    nxt.set_defaults(func=_cmd_next)

    log = sub.add_parser("log", help="Record one iteration before making the change")
    log.add_argument("--log", type=Path, required=True, help=".iterations.log (JSONL)")
    log.add_argument("--signature", required=True)
    log.add_argument("--hypothesis", required=True)
    log.add_argument("--change", required=True)
    log.add_argument("--classification", choices=CLASSIFICATIONS, required=True)
    log.add_argument("--unfixable", action="store_true",
                     help="infra failure not fixable from karate-tests/; check-stop stops")
    log.set_defaults(func=_cmd_log)

    stop = sub.add_parser("check-stop", help="Apply the stop conditions")
    stop.add_argument("--log", type=Path, required=True)
    stop.add_argument("--report", type=Path, required=True)
    stop.add_argument("--max-iterations", type=int, default=15)
    stop.set_defaults(func=_cmd_check_stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the iterate tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_iterate.py -v`
Expected: 7 passed. The last CLI assertion catches `SystemExit(2)` directly because `argparse` rejects a value outside `choices` before `run_cli` sees a `KbError`.

- [ ] **Step 5: Full suite, lint, types, spec command help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_iterate.py next --help` then `... log --help` then `... check-stop --help`
Expected: green; flags match the spec 5.7 command block: `next` has `--report`, `--tests-dir`; `log` has `--log`, `--signature`, `--hypothesis`, `--change`, `--classification`, `--unfixable`; `check-stop` has `--log`, `--report`, `--max-iterations`. [[docs-in-sync]]

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_iterate.py skills/karate-bootstrap/tests/test_kb_iterate.py
git commit -m "feat(karate-bootstrap): kb_iterate groups failures, logs iterations, applies stop rules

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `kb_checkpoint.py begin` and `commit`

**Confidence:** 93%. The exact git command sequence below was executed today on throwaway repos with `main` and `master` default branches on this machine's git: `symbolic-ref --short refs/remotes/origin/HEAD` exits 128 with no remote, `rev-parse --verify --quiet refs/heads/<name>` exits 1 for a missing branch and prints the sha for a present one, `branch --show-current` prints the name, `add -- karate-tests` stages only that tree, `diff --cached --name-only` is empty when there is nothing to commit, `add -- missing-dir` exits 128 with `pathspec ... did not match`, and `rev-parse --is-inside-work-tree` exits 128 outside a repo. Tests build their repos with `git init -q -b main` and set a local identity, so they pass on a machine without a global git identity.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_checkpoint.py`
- Test: `skills/karate-bootstrap/tests/test_kb_checkpoint.py`

**Interfaces:**
- Consumes: `kb_common.{KbError, EXIT_OK, EXIT_VALIDATION, run_cli}`.
- Produces for the skill (Plan 3): `python scripts/kb_checkpoint.py begin --repo PATH [--branch karate-bootstrap] [--no-commit]` and `python scripts/kb_checkpoint.py commit --repo PATH --phase N --message TEXT [--tests-dir karate-tests] [--no-commit]`. Python API for tests: `is_repo(repo) -> bool`, `current_branch(repo) -> str`, `default_branch(repo) -> str`, `begin(repo, branch) -> dict`, `commit(repo, phase, message, tests_dir) -> dict`.

- [ ] **Step 1: Write `tests/test_kb_checkpoint.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from kb_checkpoint import begin, commit, current_branch, default_branch, is_repo, main
from kb_common import EXIT_VALIDATION, KbError, run_cli


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _repo(tmp_path: Path, default: str = "main") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", default)
    _git(repo, "config", "user.email", "kb@example.com")
    _git(repo, "config", "user.name", "kb")
    (repo / "README.md").write_text("app\n", encoding="utf-8")
    _git(repo, "add", "--", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_is_repo_and_branches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert is_repo(repo) is True
    assert is_repo(tmp_path) is False
    assert current_branch(repo) == "main"
    assert default_branch(repo) == "main"
    master = _repo(tmp_path / "m", default="master")
    assert default_branch(master) == "master"


def test_begin_creates_the_branch_on_the_default_branch_only(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": True,
                                               "switched": True}
    assert current_branch(repo) == "karate-bootstrap"
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": False,
                                               "switched": False}
    _git(repo, "checkout", "-q", "main")
    assert begin(repo, "karate-bootstrap") == {"branch": "karate-bootstrap", "created": False,
                                               "switched": True}
    _git(repo, "checkout", "-q", "-b", "ralph/PBI-42")
    assert begin(repo, "karate-bootstrap") == {"branch": "ralph/PBI-42", "created": False,
                                               "switched": False}


def test_commit_stages_only_the_tests_dir(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "pom.xml").write_text("<project/>", encoding="utf-8")
    (repo / "unrelated.txt").write_text("x", encoding="utf-8")
    result = commit(repo, 4, "scaffold the Karate module", "karate-tests")
    assert result["committed"] is True
    assert result["files"] == ["karate-tests/pom.xml"]
    assert len(result["sha"]) >= 7
    assert _git(repo, "log", "-1", "--pretty=%s") == (
        "test(karate-bootstrap): phase 4: scaffold the Karate module"
    )
    assert _git(repo, "status", "--short") == "?? unrelated.txt"
    assert commit(repo, 5, "nothing new", "karate-tests") == {"committed": False, "sha": None,
                                                              "files": []}


def test_commit_and_begin_reject_a_non_repo(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        begin(tmp_path, "karate-bootstrap")
    assert excinfo.value.exit_code == EXIT_VALIDATION
    with pytest.raises(KbError):
        commit(tmp_path, 1, "x", "karate-tests")


def test_cli_and_no_commit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert run_cli(main, ["begin", "--repo", str(repo)]) == 0
    assert '"branch": "karate-bootstrap"' in capsys.readouterr().out
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "flow-map.yaml").write_text("version: 1\n", encoding="utf-8")
    assert run_cli(main, ["commit", "--repo", str(repo), "--phase", "2",
                          "--message", "ledger traced"]) == 0
    assert '"committed": true' in capsys.readouterr().out
    assert run_cli(main, ["commit", "--repo", str(tmp_path), "--phase", "3", "--message", "x",
                          "--no-commit"]) == 0
    assert "no-commit" in capsys.readouterr().out
    assert run_cli(main, ["begin", "--repo", str(tmp_path)]) == EXIT_VALIDATION
```

- [ ] **Step 2: Run it to confirm the import fails**

Run: `pytest skills/karate-bootstrap/tests/test_kb_checkpoint.py -v`
Expected: `ModuleNotFoundError: No module named 'kb_checkpoint'`.

- [ ] **Step 3: Create `scripts/kb_checkpoint.py`**

```python
"""Git checkpoints for karate-bootstrap (design spec section 9).

``begin`` makes sure the run lands on a feature branch: on the repo's default branch it
creates (or checks out) ``karate-bootstrap``; on any other branch, such as a ralph-managed
``ralph/<PBI-id>`` branch, it changes nothing. ``commit`` stages ``karate-tests/`` only and
commits with a phase-tagged message. Both print JSON. Both are no-ops with ``--no-commit``.
The skill never pushes.

Usage:
    python scripts/kb_checkpoint.py begin --repo <repo> [--branch karate-bootstrap] [--no-commit]
    python scripts/kb_checkpoint.py commit --repo <repo> --phase N --message "..." \
        [--tests-dir karate-tests] [--no-commit]

Exit codes: 0 ok (including nothing to commit), 2 when the repo is not a git work tree or
a git command fails.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from kb_common import EXIT_OK, KbError, run_cli

DEFAULT_BRANCH_NAME = "karate-bootstrap"
DEFAULT_TESTS_DIR = "karate-tests"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise KbError(f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc


def is_repo(repo: Path) -> bool:
    if not repo.is_dir():
        return False
    proc = _git(repo, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _require_repo(repo: Path) -> None:
    if not is_repo(repo):
        raise KbError(f"{repo} is not a git work tree")


def current_branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current").stdout.strip()


def _branch_exists(repo: Path, name: str) -> bool:
    proc = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", check=False)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def default_branch(repo: Path) -> str:
    """origin/HEAD when a remote is configured, else main or master, else the current branch."""
    proc = _git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    ref = proc.stdout.strip()
    if proc.returncode == 0 and ref.startswith("origin/"):
        return ref[len("origin/"):]
    for name in ("main", "master"):
        if _branch_exists(repo, name):
            return name
    return current_branch(repo)


def begin(repo: Path, branch: str = DEFAULT_BRANCH_NAME) -> dict[str, Any]:
    _require_repo(repo)
    current = current_branch(repo)
    if current != default_branch(repo):
        return {"branch": current, "created": False, "switched": False}
    exists = _branch_exists(repo, branch)
    if exists:
        _git(repo, "checkout", "-q", branch)
    else:
        _git(repo, "checkout", "-q", "-b", branch)
    return {"branch": branch, "created": not exists, "switched": True}


def commit(repo: Path, phase: int, message: str,
           tests_dir: str = DEFAULT_TESTS_DIR) -> dict[str, Any]:
    _require_repo(repo)
    _git(repo, "add", "--", tests_dir)
    staged = _git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return {"committed": False, "sha": None, "files": []}
    _git(repo, "commit", "-q", "-m", f"test(karate-bootstrap): phase {phase}: {message}")
    sha = _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    return {"committed": True, "sha": sha, "files": staged.splitlines()}


def _cmd_begin(args: argparse.Namespace) -> int:
    if args.no_commit:
        print(json.dumps({"skipped": "no-commit"}))
        return EXIT_OK
    print(json.dumps(begin(args.repo, args.branch)))
    return EXIT_OK


def _cmd_commit(args: argparse.Namespace) -> int:
    if args.no_commit:
        print(json.dumps({"skipped": "no-commit"}))
        return EXIT_OK
    print(json.dumps(commit(args.repo, args.phase, args.message, args.tests_dir)))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Git checkpoints for karate-bootstrap runs")
    sub = parser.add_subparsers(dest="command", required=True)

    begin_p = sub.add_parser(
        "begin", help="Create or check out the feature branch when on the default branch"
    )
    begin_p.add_argument("--repo", type=Path, required=True)
    begin_p.add_argument("--branch", default=DEFAULT_BRANCH_NAME)
    begin_p.add_argument("--no-commit", action="store_true", help="never touch git")
    begin_p.set_defaults(func=_cmd_begin)

    commit_p = sub.add_parser("commit", help="Stage karate-tests/ and commit a phase checkpoint")
    commit_p.add_argument("--repo", type=Path, required=True)
    commit_p.add_argument("--phase", type=int, required=True)
    commit_p.add_argument("--message", required=True)
    commit_p.add_argument("--tests-dir", default=DEFAULT_TESTS_DIR,
                          help="directory to stage, relative to the repo")
    commit_p.add_argument("--no-commit", action="store_true", help="never touch git")
    commit_p.set_defaults(func=_cmd_commit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the checkpoint tests**

Run: `pytest skills/karate-bootstrap/tests/test_kb_checkpoint.py -v`
Expected: 5 passed.

- [ ] **Step 5: Full suite, lint, types, spec command help**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_checkpoint.py begin --help` then `python skills/karate-bootstrap/scripts/kb_checkpoint.py commit --help`
Expected: green; `begin` lists `--repo`, `--branch`, `--no-commit`; `commit` lists `--repo`, `--phase`, `--message`, `--tests-dir`, `--no-commit` (spec section 9). [[docs-in-sync]]

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_checkpoint.py skills/karate-bootstrap/tests/test_kb_checkpoint.py
git commit -m "feat(karate-bootstrap): kb_checkpoint branches and commits karate-tests only

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Assumptions

Surfaced in the three buckets the standards document asks for. **Real concerns: 2.** Both carry a recommended option; execution proceeds on the recommendation unless the user picks otherwise at the handoff.

### Real concerns

| # | Concern | Options | Recommendation |
|---|---------|---------|----------------|
| P2-C1 | `kb-runtime.json` fixes the database user and password as `app`/`app` and the harness injects them through the app's own user and password env vars. An app whose DB user is hard-coded in a config file with no env override would fail to connect. | A: keep `app`/`app` and inject (simple, deterministic, the db-manager and the app share one identity). B: parse defaults out of placeholders such as `${SPRING_DATASOURCE_USERNAME:shipments}` and create that role in Postgres too (more moving parts, only helps the hard-coded case). | A. Every fixture and every ROSA manifest seen so far takes DB credentials from the environment. If Plan 4 finds a repo that does not, B is a `kb_scaffold.py` change plus one `PostgreSQLContainer.withUsername` call. |
| P2-C2 | The template ships `rules/harness-smoke.csv` into the target repo's `rules/` directory so the smoke feature proves that root-level `rules/**` is on the classpath. The generated gate ignores CSVs the ledger does not reference, so it is harmless, but a developer will see one file in `rules/` that is not a validation rule set. | A: keep it in `rules/` (the proof travels with every repo). B: move it to `src/test/resources/smoke/` and lose the proof that the target repo's `rules/` is a Maven test resource. | A. The gate already ignores it; the README template can name it in Notes if the user wants. |

### Verified safe

- Every Java file in Task 4 compiled and its JUnit tests passed today in the spike, as written in this plan (13 tests: `ContainersTest` 4, `JmsTest` 4, `JwtTest` 2, `StubsTest` 2, `KarateRunner` 1 with 6 scenarios). The first run of the lift caught one wrong assertion in `JmsTest` (requeued messages do not keep FIFO order); the test in this plan is the corrected one.
- `reset.feature` executes under Karate 1.5.2 with no arguments and with empty lists: `__arg || {}`, `karate.forEach`, and `eval if (...)` are accepted, and the `Db`, `Jms`, `Stubs` references are not evaluated when the branch is false. The smoke scenario that proves it ships in the template.
- Task 5's `env_value` table, `env_name`, `db_name_from_env`, `build_runtime` for both fixtures, the exit-4 path and the copy rules ran today against the real `env-map.json` and seeded ledger that Plan 1's scripts produce for `spring-mini` and `dotnet-mini` (23 tests plus a copy-rule check). Every expected string in the plan came from those runs.
- Task 8's git sequence ran today on repos whose default branch is `main` and `master`, on Windows git; exit codes and outputs are as the code expects.
- Karate cucumber JSON, `karate-summary-json.txt` and JUnit XML shapes for passing, failing and outline scenarios were captured from a real run today; `@known-defect` scenarios do not appear in any report file, which is why `skipped` is counted from the feature files.
- Maven wrapper 3.3.2 only-script downloads and runs Maven 3.9.9 from the pinned `distributionUrl`; the first run needs Maven Central.
- All artifact coordinates and image tags were checked against Maven Central and Docker Hub on 2026-09-05 (spec section 12).

### Minor, accepted

- Live container start (`Containers.start()`) is compile-checked here and first exercised by Plan 4's end-to-end fixtures, as the spec states. Plan 4 is also where `kb.threads=1` becomes the default if isolation by data proves flaky (spec H7).
- `Jms.await` scans the inbox under its monitor and leaves non-matching messages in place, in order.
- `Db.run` splits seed SQL on `;` at end of line; seeds are inserts, not functions (spec 12).
- The Maven-marked pytest needs `JAVA_HOME` (or a JDK on `PATH` for the Unix wrapper) and Maven Central; on this machine `JAVA_HOME` must be set explicitly ([[maven-needs-java-home]]).
- `kb_report.py parse` counts a quarantined `Scenario Outline` once, not per example row; the README table calls the column "Quarantined".
- `kb_checkpoint.py` does not create a git identity; a machine without one fails at `git commit` with git's own message, exit 2.
- `Jwt.token` signs with a 2048-bit RSA key generated once per JVM (about 100 ms at class load).

## Plan 2 exit criteria

- `pytest -q`, `ruff check .` and `mypy` are green on the branch; `KB_MAVEN=1 pytest -m maven -v` is green locally and the `karate-templates` CI job is green on the PR.
- Every command in spec sections 5.5 to 5.8 and 9 runs with `--help` and accepts exactly the flags the spec shows.
- The repo contains no `templates/karate-tests/target/` output and no `.superpowers/` files ([[stage-by-path]]).
- A memory sweep has recorded: any reviewer finding that led to a fix commit; the `JmsTest` ordering finding from the lift; the `mvnw.cmd` `JAVA_HOME` gotcha if not already recorded.
- Handoff through `superpowers:finishing-a-development-branch` (push the feature branch, open the PR against `main`).

## Self-review record

Run after the plan was written, against spec commit `3c99756`.

1. **Spec coverage.** 5.5 scaffold command, copy rules, `kb-runtime.json` schema, env token rules, db-manager resolution, pins, harness classes, `reset.feature`, `testcontainers.properties`, `azure-pipelines.karate.yml`, `defects.md`: Tasks 3, 4, 5. 5.6 isolation-by-data gate (`@parallel=false`): Task 2. 5.2 `set-auth`: Task 2. 5.7 commands, report contract, signature, evidence, stop conditions: Tasks 6 and 7. 5.8 summary and README contents: Task 6. 9 script list, `kb_` prefix, checkpoint commands: Tasks 5 to 8. 10 local run flags, podman notes, CI job: Tasks 3 and 6. 12 spike facts: reflected in the confidence table. Not in this plan by design: `SKILL.md`, prompts, cheat sheets, `kb_check_skill.py` (Plan 3); fixture apps, db-manager images, live runs (Plan 4).
2. **Placeholder scan.** No TBD, TODO, "similar to Task N", or "add error handling". Every code step carries the code.
3. **Type and name consistency.** `kb_features.parse_feature`, `Block`, `ParsedFeature`, `known_defect_scenario_count`, `unsafe_parallel_scenarios`, `PARALLEL_FALSE_TAG` are used with the same names in Tasks 2 and 6. Report keys `feature`, `scenario`, `outline`, `tags`, `step`, `error` are identical in Tasks 6 and 7 and match what `flow_map._validate_green` reads. `Containers.tokenValues`, `substitute`, `artemisExtraArgs`, `appWait`, `Stubs.countBody(method, urlPath, bodyContains)`, `Jms.takeMatching`, `Jms.matches`, `Jwt.mapping`, `Jwt.mappings`, `Jwt.tokenFor`, `Jwt.key` match between the Java sources and the JUnit tests. `RUNTIME_REL`, `TEMPLATE_DIR`, `build_runtime`, `copy_template` match between `kb_scaffold.py` and its tests. Forward references: none; the one compile cycle (Containers and its helpers) lives inside a single task.
4. **Cross-read.** The `Jms.await` prose in Task 4 says order is not preserved, matching the corrected test. The `kb_report` docstring and the report contract in Global Constraints list the same keys (`outline` is an addition the green gate ignores).

## Post-execution amendments

Changes made while executing this plan that the task bodies above do not describe. The plan text
is left as written; this list is the record of what the branch actually landed.

- `_CLASS_DECL_RE` in `discover.py` rewritten as a linear regex, no catastrophic backtracking (1cba5e4).
- The Maven-marked template test launches the wrapper by absolute path (b6d95ee).
- One JMS session per listener-driven consumer, with a separate producer session (ca2d4fc).
- `kb_checkpoint` test asserts that `begin` on a non-default branch reports the current branch (ddc00a4).
- Final-review fix wave (199e78f): the smoke feature asserts `skipContainers == '#boolean'` and
  `kb_scaffold.HARNESS_FILES` lets `--force` refresh it (C1); `KarateRunner` ANDs `@harness` under
  `-Dkb.skipContainers=true` (I1) and writes `target/stubs-unmatched.json` after a containerised run
  (I7); `reset.feature` applies watch, truncate, seed, stubs (I2); `Db.stripComments` keeps a
  statement under a leading `--` comment (I3); `Jms` scans a monitor-guarded `Inbox` in place instead
  of parking other scenarios' messages (I4); a failed `Containers.start()` is remembered, not retried
  (I5); a JVM shutdown hook stops the topology and closes JMS, and `Jms.ensureConnection` assigns the
  field only after `start()` succeeds (I8); `env_value` returns `None` for db-role keys naming no part
  of the connection (I6); the ADO job runs `sh mvnw` and `kb_checkpoint` marks `karate-tests/mvnw`
  `100755` (I9). Minors: `Jwt.publishJwks` checks the import response, `README.md.tmpl` is no longer
  copied into the target repo, and the built app image name is sanitised.
