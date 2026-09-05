# karate-bootstrap Plan 2 of 4: Harness and Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything the skill needs to turn a traced ledger into a runnable, self-checking Karate module: the Maven scaffold and Java harness templates, the report parser, the iteration loop bookkeeping, the git checkpoint script, and the ledger additions Plan 1's review deferred.

**Architecture:** The rendered `karate-tests/` module is a real Maven project that lives verbatim under `skills/karate-bootstrap/templates/karate-tests/` and compiles as-is in this repo, so template bugs are caught by `./mvnw test-compile` before any target repo sees them. Repo-specific values never go into Java; `kb_scaffold.py` writes them to `src/test/resources/kb-runtime.json` and the harness reads that file at start-up. Python scripts keep the Plan 1 conventions: direct-path invocable, `kb_` prefixed basenames, `argparse` subcommands, pinned outputs, exit codes from `kb_common`.

**Tech Stack:** Python 3.11+ (`pyyaml` only), pytest, ruff, mypy strict. Java 17 release level, Maven wrapper 3.3.2 (only-script) pinned to Apache Maven 3.9.9. Karate 1.5.2 (`io.karatelabs:karate-junit5`), Testcontainers BOM 1.21.4 (`testcontainers`, `junit-jupiter`, `postgresql`, `mockserver`), MockServer client 5.15.0 with image `mockserver/mockserver:mockserver-5.15.0`, Postgres image `postgres:16-alpine`, Artemis image `apache/activemq-artemis:2.44.0-alpine` with `artemis-jms-client` 2.44.0, `org.postgresql:postgresql` 42.7.13, `nimbus-jose-jwt` 9.37.3, `jackson-databind` 2.17.2, `junit-jupiter` 5.10.3, `logback-classic` 1.5.6, `maven-surefire-plugin` 3.2.5. Every coordinate and image tag was checked against Maven Central or Docker Hub on 2026-09-05.

**Spec:** `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` (sections 4.3, 5.5, 5.6, 5.7, 5.8, 9, 10)

**Phasing (renumbered):** Plan 1 landed as PR #7 (analysis core). This is Plan 2: harness and loop. Plan 3: skill assembly (subagent prompt files, per-stack cheat sheets, `SKILL.md`, `kb_check_skill.py`, README section, dry-run eval through the generated gate without containers). Plan 4: fixture apps with db-manager images and end-to-end evals on a container runtime. Each plan leaves the repo green on `ruff check .`, `mypy`, `pytest -q`.

## Guardrails

Surfaced from the standards document, high-confidence reflections and Plan 1's final review before drafting.

- **[[confidence-gate]]** (standards): every task carries a confidence percentage; tasks under 90% embed their mitigation in the task body.
- **[[verify-before-commit]]** (standards): every external coordinate in this plan was checked today (see Tech Stack). The Maven wrapper files are downloaded from a pinned tag, not typed from memory. Karate report file naming was read from Karate's `ReportUtils.java` at v1.5.1: cucumber JSON is `<packageQualifiedName>.json`, JUnit XML is `<baseName>.xml`, both under `reportDir` (default `target/karate-reports`) and only when `outputCucumberJson(true)` / `outputJunitXml(true)` are set on the `Runner` builder.
- **[[docs-in-sync]]** (reflection mem-f3ce58e6, confidence 0.95): every new CLI flag, output file and exit code lands in the module docstring and the spec in the same task. Plan 3's `kb_check_skill.py` will lint `SKILL.md` against `--help`.
- **[[unique-module-names]]** (Plan 1 merge incident, PR #7): both skills' `tests/conftest.py` share one `sys.path` and both `scripts/` dirs sit on `mypy_path`; main already has `rules.py`, `config.py`, `inventory.py`, `patterns.py`, `validation.py`, `evaluate.py`, `redaction.py`, `git_history.py`, `docs_signals.py`, `reference_graph.py`, `promote.py`, `bundle_writer.py`, `design_parser.py`, `design_writer.py`, `categories.py`, `build_synthesis_prompt.py`, `skill_check.py`. Every new karate-bootstrap script is `kb_*.py`; every new test file is `test_kb_*.py`. Run `git ls-files skills/*/scripts skills/*/tests` before naming anything.
- **[[plan-mandated-defects]]** (Plan 1 final review): task-scoped reviews cannot catch defects the plan itself mandates. Every task here that touches parsing or regexes carries one "realistic layout" test that is not derived from the brief's happy path, and the whole-branch review is told to probe with real Karate output and a real Maven build.
- **[[spec-code-lint]]** (standards): copied code is not lint-clean by default; each task ends with `ruff check` and `mypy` on touched Python, and `./mvnw -q test-compile` on touched Java.
- **[[no-improvisation]]**: scripts fail with a defined exit code on missing inputs; they never guess.
- **[[py311-syntax]]** (Plan 1, Task 6): no backslashes inside f-string expressions; ruff targets py311.

Dismissed: PBI/ralph-queue reflection (nothing is being queued), RED-step-illusory reflection (no guards move in this plan), Playwright/TypeScript/tempfile reflections (not applicable).

## Task confidence summary

| Task | Deliverable | Confidence | Mitigation embedded in the task |
|------|-------------|-----------:|----------------------------------|
| 1 | Plan 1 backlog fixes in `kb_rules.py`, `discover.py`, `kb_common.py` | 92% | Each fix has a failing regression test first |
| 2 | `flow_map.py set-auth` | 93% | Contract fixed by Plan 1's unconfirmed-auth gap; tests reuse the fastapi fixture pipeline |
| 3 | Template module skeleton: pom, wrapper, resources, `KbRuntime.java`, `KarateRunner.java`, smoke feature; compiles and runs without containers | 82% | Pinned coordinates verified today; wrapper downloaded from a tag; the task ends with a real `./mvnw test` producing report files that later tasks use as fixtures; Maven-dependent tests are opt-in via `KB_MAVEN=1` so CI without a JDK stays green |
| 4 | `Containers.java` with db-manager, Artemis addresses, MockServer, JWKS publish | 80% | Compile-checked; every Testcontainers API used is named in the task from 1.21.4 docs; runtime behaviour is exercised in Plan 4, not here |
| 5 | `Db.java`, `Jms.java`, `Stubs.java`, `Jwt.java` helpers | 82% | Compile-checked; JWT and Stubs have host-only unit tests (no containers) |
| 6 | `kb_scaffold.py`: render module, `kb-runtime.json`, central config, exit 4 | 88% | Golden-file tests against the spring fixture ledger; idempotence test |
| 7 | `kb_report.py parse` and `summary` | 88% | Fixture is real Karate cucumber JSON from Task 3 plus a hand-written failing feature JSON |
| 8 | `kb_iterate.py next`, `log`, `check-stop` | 90% | Pure data over report JSON and a JSONL log |
| 9 | `kb_checkpoint.py` git behaviour | 90% | tmp git repos in tests; never touches the real repo |
| 10 | CI job for Maven-dependent tests, spec amendments, docs | 92% | Mirrors the existing workflow |

No task is below 80%. Tasks 3, 4 and 5 carry the JVM risk; their mitigation is that the template project is compiled in this repo, so nothing is shipped untested to a target repo.

## Global Constraints

- Exit codes (spec section 9): 0 ok, 2 validation failure, 3 unsupported stack, 4 no schema source, 5 missing expected output, 6 stopped by stop condition, 7 container runtime or JDK missing.
- New scripts: `kb_scaffold.py`, `kb_report.py`, `kb_iterate.py`, `kb_checkpoint.py`. New tests: `test_kb_scaffold.py`, `test_kb_report.py`, `test_kb_iterate.py`, `test_kb_checkpoint.py`, `test_kb_templates.py`. Templates under `skills/karate-bootstrap/templates/karate-tests/`.
- Java package for the harness: `kb.harness`. Java release level 17.
- Report JSON contract (Plan 1, `flow_map._validate_green`): `{"passed": int, "skipped": int, "failed": [{"feature": str, "scenario": str, "tags": [str], "step": str, "error": str}]}` where `feature` is the resources-relative path stored in the ledger's `features` lists, e.g. `features/post-api-shipments.feature`.
- Layout the scaffold produces is spec section 4.3. `rules/`, `stubs/`, `seed/` sit at the module root and the pom registers them as test resources; features live under `src/test/resources/features/`.
- Runtime configuration file: `karate-tests/src/test/resources/kb-runtime.json`, schema in Task 6. Java never contains repo-specific literals.
- Karate runner options: `Runner.path("classpath:features").tags("~@known-defect").outputCucumberJson(true).outputJunitXml(true).parallel(threads)`.
- System properties the harness understands: `kb.skipContainers=true` (features run without any container, used by the smoke feature and by tests), `app.image=<tag>` (skip the Dockerfile build), `kb.threads=<n>` (default 4).
- ruff (E,F,I,B,UP,SIM, line length 100), mypy strict, Python 3.11 syntax. Java formatted plainly, no Lombok, no records with compact constructors that need Java 21.
- Commit messages: Conventional Commits, scope `karate-bootstrap`, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Stage by explicit path; never bypass hooks; never `git add -A`.
- Branch: `feat/karate-bootstrap-plan-2` off `origin/main` at `f269019` (PR #7 merge).

---

## File Structure

```
skills/karate-bootstrap/
  scripts/
    kb_common.py       (Task 1: TEST_TREE_NAMES tweak)
    discover.py        (Task 1: class regex accepts leading annotation)
    kb_rules.py        (Task 1: statement join ignores ; inside strings)
    flow_map.py        (Task 2: set-auth)
    kb_scaffold.py     Phase 4: render templates + kb-runtime.json
    kb_report.py       Phase 6/7: parse Karate cucumber JSON, render README
    kb_iterate.py      Phase 6: failure groups, iteration log, stop conditions
    kb_checkpoint.py   git branch/commit at phase gates
  templates/karate-tests/
    pom.xml
    mvnw  mvnw.cmd  .mvn/wrapper/maven-wrapper.properties
    .gitignore
    azure-pipelines.karate.yml
    README.md.tmpl                      (kb_report.py summary fills it)
    src/test/java/kb/harness/
      KbRuntime.java     reads kb-runtime.json
      Containers.java    topology
      Db.java  Jms.java  Stubs.java  Jwt.java
      KarateRunner.java
    src/test/resources/
      karate-config.js
      testcontainers.properties
      logback-test.xml
      kb-runtime.json                  (template default: skipContainers smoke values)
      common/reset.feature  common/mutate.js
      features/harness-smoke.feature
  tests/
    test_kb_templates.py   (maven-marked compile + smoke run; skipped unless KB_MAVEN=1)
    test_kb_scaffold.py  test_kb_report.py  test_kb_iterate.py  test_kb_checkpoint.py
    fixtures/karate-reports/            real output from the smoke run (Task 3)
    fixtures/karate-reports-failing/    hand-written cucumber JSON with a failure
.github/workflows/test.yml  (Task 10: maven job)
pyproject.toml              (marker `maven`, addopts exclude it by default)
docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md (Task 10 amendments)
```

---

### Task 1: Plan 1 backlog fixes

**Confidence:** 92%. Three small, well-understood regressions with failing tests first.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/kb_rules.py` (`_fluent_statements`)
- Modify: `skills/karate-bootstrap/scripts/discover.py` (`_CLASS_DECL_RE`, `detect_auth` test only)
- Modify: `skills/karate-bootstrap/scripts/kb_common.py` (`TEST_TREE_NAMES`)
- Modify: `skills/karate-bootstrap/tests/test_kb_rules.py`, `tests/test_kb_discover.py`, `tests/test_kb_common.py`

**Interfaces:**
- Consumes: existing functions `extract_fluent_validation(text, source_rel)`, `find_entry_points(root, stack, config)`, `detect_auth(keys, stack_auth)`, `is_test_tree(path)` / `TEST_TREE_NAMES`.
- Produces: no signature changes.

- [ ] **Step 1: Write the failing tests**

Append to `skills/karate-bootstrap/tests/test_kb_rules.py`:

```python
def test_extract_fluent_validation_ignores_semicolons_inside_strings() -> None:
    text = (
        "RuleFor(x => x.Code)\n"
        '    .WithMessage("invalid; retry")\n'
        "    .MaximumLength(5);\n"
    )
    rows = extract_fluent_validation(text, "V.cs")
    assert [(r["field"], r["mutation"], r["value"]) for r in rows] == [("Code", "too_long", "6")]
    assert rows[0]["source"] == "V.cs:1"
```

Append to `skills/karate-bootstrap/tests/test_kb_discover.py`:

```python
def test_class_prefix_survives_same_line_annotation(tmp_path: Path) -> None:
    src = tmp_path / "src/main/java/com/acme/PingController.java"
    src.parent.mkdir(parents=True)
    src.write_text(
        "package com.acme;\n\n"
        '@RequestMapping("/api/ping")\n'
        "@RestController public class PingController {\n"
        "    @GetMapping\n"
        "    public String ping() { return \"pong\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    entries = find_entry_points(tmp_path, "spring", {})
    assert [e["id"] for e in entries] == ["GET /api/ping"]


def test_detect_auth_jwks_keys_are_unique() -> None:
    keys = {
        "OIDC_URL": {"placeholder": "https://x", "source": "deployment.yml", "env_var": "OIDC_URL",
                     "role": "auth"},
        "quarkus.oidc.auth-server-url": {"placeholder": "${OIDC_URL}", "source": "a.properties",
                                         "env_var": "OIDC_URL", "role": "auth"},
    }
    assert detect_auth(keys, "quarkus-oidc") == {"mode": "jwks", "keys": ["OIDC_URL"]}
```

Append to `skills/karate-bootstrap/tests/test_kb_common.py`:

```python
def test_spec_directory_is_not_a_test_tree(tmp_path: Path) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conf.yaml").write_text("x: 1\n", encoding="utf-8")
    found = sorted(rel(p, tmp_path) for p in iter_files(tmp_path, (".yaml",), skip_test_trees=True))
    assert found == ["spec/openapi.yaml"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_rules.py skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_common.py -q -k "semicolons or same_line_annotation or jwks_keys_are_unique or spec_directory"`
Expected: the semicolon test fails (no rows), the same-line annotation test fails (`GET /` or empty prefix), the spec-directory test fails (`spec/openapi.yaml` missing). The jwks test passes already because the fix landed in Plan 1's fix wave; keep it as the regression the final review asked for and say so in the commit body.

- [ ] **Step 3: Fix `kb_rules._fluent_statements`**

Replace the statement-close condition. The joined statement ends only at a `;` that sits outside string literals:

```python
def _ends_statement(line: str) -> bool:
    """True when ``line`` contains a ``;`` outside any double-quoted string literal."""
    in_string = False
    escaped = False
    for ch in line:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == ";":
            return True
    return False
```

and in `_fluent_statements` use `if _ends_statement(line):` where it previously tested `";" in line`.

- [ ] **Step 4: Fix `discover._CLASS_DECL_RE`**

```python
_CLASS_DECL_RE = re.compile(
    r"^\s*(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:(?:public|private|protected|final|abstract|static|sealed|partial|internal)\s+)*"
    r"(?:class|interface|record)\s+(\w+)"
)
```

- [ ] **Step 5: Fix `kb_common.TEST_TREE_NAMES`**

Remove `"spec"` from the tuple. Update the docstring line that lists the names.

- [ ] **Step 6: Run the four test files and the gates**

Run: `python -m pytest skills/karate-bootstrap/tests -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: all pass, clean.

- [ ] **Step 7: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_rules.py skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/scripts/kb_common.py skills/karate-bootstrap/tests/test_kb_rules.py skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_common.py
git commit -m "fix(karate-bootstrap): close the plan 1 review backlog

FluentValidation statements no longer end at a semicolon inside a string,
class declarations may carry a leading annotation on the same line,
spec/ is no longer treated as a test tree, and the jwks de-dupe has a
regression test.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `flow_map.py set-auth`

**Confidence:** 93%.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/flow_map.py`
- Modify: `skills/karate-bootstrap/tests/test_kb_flow_map.py`

**Interfaces:**
- Produces: `set_auth(ledger, mode: str, key: str | None, value: str | None, keys: list[str] | None) -> dict[str, Any]` returning the new `app.auth` block; CLI `set-auth --ledger PATH --mode disabled|jwks|none|blocked [--key K --value V] [--jwks-key K ...]`. `disabled` requires `--key` and `--value` and writes `confirmed: true`. `jwks` requires at least one `--jwks-key`. `none` and `blocked` take no extra flags. Module docstring gains the subcommand.

- [ ] **Step 1: Write the failing tests**

```python
def test_set_auth_disabled_confirms_switch(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    ledger["app"]["auth"] = {"mode": "disabled", "key": "AUTH_MODE", "value": "disabled",
                             "confirmed": False}
    result = set_auth(ledger, "disabled", "AUTH_MODE", "none", None)
    assert result == {"mode": "disabled", "key": "AUTH_MODE", "value": "none", "confirmed": True}
    assert ledger["app"]["auth"] == result
    _trace_all(ledger)
    env_map = {"keys": [{"key": "PRICING_BASE_URL", "env_var": "PRICING_BASE_URL"}]}
    assert not any("unconfirmed" in g for g in validate(ledger, "traced", SPRING, env_map, None, None, None))


def test_set_auth_jwks_and_none(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    assert set_auth(ledger, "jwks", None, None, ["AUTH_ISSUER_URI"]) == {
        "mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}
    assert set_auth(ledger, "none", None, None, None) == {"mode": "none"}
    with pytest.raises(KbError, match="--key"):
        set_auth(ledger, "disabled", None, "false", None)
    with pytest.raises(KbError, match="jwks-key"):
        set_auth(ledger, "jwks", None, None, [])


def test_cli_set_auth(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    path, _ = spring_ledger
    assert main(["set-auth", "--ledger", str(path), "--mode", "disabled", "--key",
                 "APP_SECURITY_ENABLED", "--value", "false"]) == 0
    assert load_ledger(path)["app"]["auth"]["confirmed"] is True
```

Add `set_auth` to the `from flow_map import (...)` block.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q -k set_auth`
Expected: `ImportError: cannot import name 'set_auth'`.

- [ ] **Step 3: Implement**

```python
AUTH_MODES = ("disabled", "jwks", "none", "blocked")


def set_auth(ledger: dict[str, Any], mode: str, key: str | None, value: str | None,
             keys: list[str] | None) -> dict[str, Any]:
    if mode not in AUTH_MODES:
        raise KbError(f"unknown auth mode {mode!r}; expected one of {AUTH_MODES}")
    if mode == "disabled":
        if not key or value is None:
            raise KbError("set-auth disabled needs --key and --value")
        auth: dict[str, Any] = {"mode": "disabled", "key": key, "value": value, "confirmed": True}
    elif mode == "jwks":
        if not keys:
            raise KbError("set-auth jwks needs at least one --jwks-key")
        auth = {"mode": "jwks", "keys": sorted(set(keys))}
    else:
        auth = {"mode": mode}
    ledger.setdefault("app", {})["auth"] = auth
    return auth


def _cmd_set_auth(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    auth = set_auth(ledger, args.mode, args.key, args.value, args.jwks_key)
    save_ledger(args.ledger, ledger)
    print(f"app.auth: {json.dumps(auth)}")
    return EXIT_OK
```

Parser:

```python
    auth = sub.add_parser("set-auth", help="Record the confirmed auth mode in the ledger")
    auth.add_argument("--ledger", type=Path, required=True)
    auth.add_argument("--mode", choices=AUTH_MODES, required=True)
    auth.add_argument("--key", default=None, help="switch env var (mode disabled)")
    auth.add_argument("--value", default=None, help="switch value (mode disabled)")
    auth.add_argument("--jwks-key", action="append", default=None,
                      help="issuer/JWKS env var (mode jwks); repeatable")
    auth.set_defaults(func=_cmd_set_auth)
```

Add `set-auth` to the module docstring's subcommand list.

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: pass, clean.

- [ ] **Step 5: Commit**

```bash
git add skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/tests/test_kb_flow_map.py
git commit -m "feat(karate-bootstrap): flow_map set-auth records the confirmed auth mode

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: Template module skeleton that compiles and runs a smoke feature

**Confidence:** 82%. First JVM task. Risks: wrapper download, Maven Central access, Karate/JUnit wiring. Mitigation: every coordinate was checked today; the wrapper scripts come from a pinned upstream tag; the task ends with a real `./mvnw test` on a feature that needs no containers, and its output becomes the fixture for Task 7. If `./mvnw` cannot reach Maven Central from this machine, stop and report BLOCKED with the wrapper's error text; do not hand-edit the wrapper.

**Files:**
- Create: `skills/karate-bootstrap/templates/karate-tests/pom.xml`
- Create: `skills/karate-bootstrap/templates/karate-tests/mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`
- Create: `skills/karate-bootstrap/templates/karate-tests/.gitignore`
- Create: `skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness/KbRuntime.java`
- Create: `skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness/KarateRunner.java`
- Create: `skills/karate-bootstrap/templates/karate-tests/src/test/resources/karate-config.js`, `testcontainers.properties`, `logback-test.xml`, `kb-runtime.json`, `common/mutate.js`, `features/harness-smoke.feature`
- Create: `skills/karate-bootstrap/tests/test_kb_templates.py`
- Create: `skills/karate-bootstrap/tests/fixtures/karate-reports/` (real smoke output committed)
- Modify: `pyproject.toml` (marker `maven`, default exclusion), `.gitattributes` (LF for `mvnw`, CRLF for `mvnw.cmd`)

**Interfaces:**
- Produces: the `kb-runtime.json` schema (below), read by `KbRuntime.load()`; `mutate(base, field, mutation, value)` JS helper; Karate globals `skipContainers`, `mutate`, and (when containers run) `appBaseUrl`, `Db`, `Jms`, `Stubs`, `Jwt` defined in `karate-config.js`; system properties `kb.skipContainers`, `kb.threads`.
- Later tasks consume: `KbRuntime` getters (Task 4), the module layout (Task 6), the report files under `target/karate-reports/` (Task 7).

**`kb-runtime.json` schema (v1):**

```json
{
  "version": 1,
  "repo": "spring-mini",
  "stack": "spring",
  "app": {
    "repoRootRel": "..",
    "dockerfileRel": "Dockerfile",
    "port": 8080,
    "readinessPath": "/actuator/health/readiness",
    "serverless": false,
    "startupTimeoutSeconds": 120
  },
  "env": [
    { "name": "SPRING_DATASOURCE_URL", "role": "db", "value": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}" },
    { "name": "SPRING_ARTEMIS_BROKER_URL", "role": "amq", "value": "tcp://{{amq.host}}:{{amq.corePort}}" },
    { "name": "PRICING_BASE_URL", "role": "downstream:pricing", "value": "{{stubs.url}}/pricing" },
    { "name": "APP_SECURITY_ENABLED", "role": "auth", "value": "false" }
  ],
  "db": { "name": "app", "user": "app", "password": "app" },
  "migrations": { "strategy": "migration-container", "image": "registry.example/db-manager:latest",
                  "env": { "PGHOST": "{{db.host}}", "PGPORT": "{{db.port}}", "PGDATABASE": "{{db.name}}",
                           "PGUSER": "{{db.user}}", "PGPASSWORD": "{{db.password}}" } },
  "amq": { "user": "artemis", "password": "artemis", "queues": ["shipment.requested"],
           "topics": ["shipment.created"] },
  "downstreams": [ { "name": "pricing", "envVar": "PRICING_BASE_URL" } ],
  "auth": { "mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false" }
}
```

Placeholders `{{db.host}}`, `{{db.port}}`, `{{db.name}}`, `{{db.user}}`, `{{db.password}}`, `{{amq.host}}`, `{{amq.corePort}}`, `{{amq.amqpPort}}`, `{{amq.stompPort}}`, `{{stubs.url}}`, `{{auth.url}}` are substituted by `Containers.java` (Task 4) with network-alias values. `auth.mode` is `disabled` (key/value), `jwks` (`issuerKeys: [..]`), `none`, or `blocked`.

- [ ] **Step 1: Download the Maven wrapper from its pinned tag**

From the worktree root:

```bash
mkdir -p skills/karate-bootstrap/templates/karate-tests/.mvn/wrapper
curl -sSL -o skills/karate-bootstrap/templates/karate-tests/mvnw     https://raw.githubusercontent.com/apache/maven-wrapper/maven-wrapper-3.3.2/maven-wrapper-distribution/src/resources/only-mvnw
curl -sSL -o skills/karate-bootstrap/templates/karate-tests/mvnw.cmd https://raw.githubusercontent.com/apache/maven-wrapper/maven-wrapper-3.3.2/maven-wrapper-distribution/src/resources/only-mvnw.cmd
```

Both files must be non-empty shell/batch scripts (check `head -3` of each). Write `.mvn/wrapper/maven-wrapper.properties`:

```properties
wrapperVersion=3.3.2
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

Append to the repo's `.gitattributes`:

```
skills/karate-bootstrap/templates/karate-tests/mvnw text eol=lf
skills/karate-bootstrap/templates/karate-tests/mvnw.cmd text eol=crlf
skills/karate-bootstrap/templates/karate-tests/**/*.java text eol=lf
skills/karate-bootstrap/templates/karate-tests/**/*.js text eol=lf
skills/karate-bootstrap/templates/karate-tests/**/*.feature text eol=lf
```

After `git add`, run `git update-index --chmod=+x skills/karate-bootstrap/templates/karate-tests/mvnw` so the executable bit is tracked for Linux CI.

- [ ] **Step 2: Write `pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>kb.generated</groupId>
  <artifactId>karate-tests</artifactId>
  <version>0.1.0</version>
  <packaging>jar</packaging>
  <description>Karate ground-truth suite generated by karate-bootstrap; runs the app under Testcontainers.</description>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <karate.version>1.5.2</karate.version>
    <testcontainers.version>1.21.4</testcontainers.version>
    <mockserver.version>5.15.0</mockserver.version>
    <artemis.version>2.44.0</artemis.version>
    <postgresql.version>42.7.13</postgresql.version>
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
    <dependency>
      <groupId>io.karatelabs</groupId>
      <artifactId>karate-junit5</artifactId>
      <version>${karate.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>testcontainers</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>postgresql</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>mockserver</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.mock-server</groupId>
      <artifactId>mockserver-client-java</artifactId>
      <version>${mockserver.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.postgresql</groupId>
      <artifactId>postgresql</artifactId>
      <version>${postgresql.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jms-client</artifactId>
      <version>${artemis.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>com.nimbusds</groupId>
      <artifactId>nimbus-jose-jwt</artifactId>
      <version>${nimbus.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>com.fasterxml.jackson.core</groupId>
      <artifactId>jackson-databind</artifactId>
      <version>${jackson.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>${logback.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <testResources>
      <testResource>
        <directory>src/test/resources</directory>
      </testResource>
      <!-- rules/, stubs/ and seed/ live at the module root so humans find them;
           registering them here makes classpath:rules/... etc. resolve. -->
      <testResource>
        <directory>${project.basedir}</directory>
        <includes>
          <include>rules/**</include>
          <include>stubs/**</include>
          <include>seed/**</include>
        </includes>
      </testResource>
    </testResources>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>${surefire.version}</version>
        <configuration>
          <includes>
            <include>**/KarateRunner.java</include>
          </includes>
          <trimStackTrace>false</trimStackTrace>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`.gitignore` for the module:

```
target/
```

- [ ] **Step 3: Write the Java skeleton**

`src/test/java/kb/harness/KbRuntime.java`:

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
 * Typed view over src/test/resources/kb-runtime.json, the only place repo-specific
 * values live. Written by kb_scaffold.py; never edited by the Java code.
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

    public String repo() {
        return root.path("repo").asText("unknown");
    }

    public String stack() {
        return root.path("stack").asText("unknown");
    }

    public String repoRootRel() {
        return root.path("app").path("repoRootRel").asText("..");
    }

    public String dockerfileRel() {
        return root.path("app").path("dockerfileRel").asText("Dockerfile");
    }

    public int appPort() {
        return root.path("app").path("port").asInt(8080);
    }

    /** Null when the manifest had no HTTP readiness probe (fall back to a port wait). */
    public String readinessPath() {
        JsonNode node = root.path("app").path("readinessPath");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public boolean serverless() {
        return root.path("app").path("serverless").asBoolean(false);
    }

    public int startupTimeoutSeconds() {
        return root.path("app").path("startupTimeoutSeconds").asInt(120);
    }

    /** Ordered env entries as {name, role, value-template}. */
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

    public String dbName() {
        return root.path("db").path("name").asText("app");
    }

    public String dbUser() {
        return root.path("db").path("user").asText("app");
    }

    public String dbPassword() {
        return root.path("db").path("password").asText("app");
    }

    public String migrationsStrategy() {
        return root.path("migrations").path("strategy").asText("migration-container");
    }

    /** Null when no db-manager image is configured. */
    public String migrationsImage() {
        JsonNode node = root.path("migrations").path("image");
        return node.isNull() || node.isMissingNode() ? null : node.asText();
    }

    public Map<String, String> migrationsEnv() {
        Map<String, String> out = new LinkedHashMap<>();
        root.path("migrations").path("env").fields()
            .forEachRemaining(e -> out.put(e.getKey(), e.getValue().asText()));
        return out;
    }

    public String amqUser() {
        return root.path("amq").path("user").asText("artemis");
    }

    public String amqPassword() {
        return root.path("amq").path("password").asText("artemis");
    }

    public List<String> amqQueues() {
        return texts(root.path("amq").path("queues"));
    }

    public List<String> amqTopics() {
        return texts(root.path("amq").path("topics"));
    }

    public List<String> downstreamNames() {
        List<String> out = new ArrayList<>();
        for (JsonNode item : root.path("downstreams")) {
            out.add(item.path("name").asText());
        }
        return out;
    }

    public String authMode() {
        return root.path("auth").path("mode").asText("none");
    }

    public String authKey() {
        return root.path("auth").path("key").asText(null);
    }

    public String authValue() {
        return root.path("auth").path("value").asText(null);
    }

    public List<String> authIssuerKeys() {
        return texts(root.path("auth").path("issuerKeys"));
    }

    private static List<String> texts(JsonNode array) {
        List<String> out = new ArrayList<>();
        for (JsonNode item : array) {
            out.add(item.asText());
        }
        return out;
    }
}
```

`src/test/java/kb/harness/KarateRunner.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.intuit.karate.Results;
import com.intuit.karate.Runner;
import org.junit.jupiter.api.Test;

/**
 * Single JUnit entry point. Containers are started lazily from karate-config.js so a
 * run with -Dkb.skipContainers=true (the harness smoke feature, kb_report fixtures)
 * needs no container runtime at all.
 */
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

- [ ] **Step 4: Write the resources**

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
  karate.configure('logPrettyRequest', true);
  karate.configure('logPrettyResponse', true);
  return config;
}
```

`src/test/resources/common/mutate.js` (one JS function; Karate wraps it):

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
```

`src/test/resources/kb-runtime.json` (template default; `kb_scaffold.py` overwrites it in a target repo):

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

`src/test/resources/testcontainers.properties`:

```properties
# Podman and rootless Docker need a privileged Ryuk; harmless on Docker Desktop-less hosts.
ryuk.container.privileged=true
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
  <logger name="kb.harness" level="INFO"/>
  <root level="WARN">
    <appender-ref ref="STDOUT"/>
  </root>
</configuration>
```

- [ ] **Step 5: Write the Maven-marked test**

`skills/karate-bootstrap/tests/test_kb_templates.py`:

```python
"""Compile the template module and run its container-free smoke feature.

These tests need a JDK 17+ and network access to Maven Central, so they are
opt-in: run with ``KB_MAVEN=1 python -m pytest -m maven``. CI runs them in a
dedicated job with a JDK installed; the default ``pytest`` invocation skips
them via the ``-m 'not live and not maven'`` addopts.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.maven

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"


def _mvnw(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = cwd / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    return subprocess.run(
        [str(script), "-B", "-q", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )


@pytest.fixture(scope="module")
def module_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if os.environ.get("KB_MAVEN") != "1":
        pytest.skip("set KB_MAVEN=1 to run the Maven template tests")
    if shutil.which("java") is None:
        pytest.skip("java not on PATH")
    target = tmp_path_factory.mktemp("karate-tests")
    shutil.copytree(TEMPLATE, target, dirs_exist_ok=True)
    return target


def test_template_compiles(module_copy: Path) -> None:
    result = _mvnw(module_copy, "test-compile")
    assert result.returncode == 0, result.stdout + result.stderr


def test_smoke_feature_runs_without_containers(module_copy: Path) -> None:
    result = _mvnw(module_copy, "test", "-Dkb.skipContainers=true")
    assert result.returncode == 0, result.stdout + result.stderr
    reports = module_copy / "target" / "karate-reports"
    cucumber = [p for p in reports.glob("*.json") if "harness-smoke" in p.name]
    junit = [p for p in reports.glob("*.xml") if "harness-smoke" in p.name]
    assert cucumber, sorted(p.name for p in reports.iterdir())
    assert junit, sorted(p.name for p in reports.iterdir())
    assert '"status": "passed"' in cucumber[0].read_text(encoding="utf-8") or \
        '"status":"passed"' in cucumber[0].read_text(encoding="utf-8")
```

`pyproject.toml` changes:

```toml
[tool.pytest.ini_options]
testpaths = ["skills/tech-debt-scan/tests", "skills/karate-bootstrap/tests"]
markers = [
  "live: hits a real LLM (off by default)",
  "maven: needs a JDK and Maven Central (off by default; KB_MAVEN=1)",
]
addopts = "-m 'not live and not maven'"
```

Keep the existing `norecursedirs`.

- [ ] **Step 6: Run the Maven tests for real**

Run: `KB_MAVEN=1 python -m pytest skills/karate-bootstrap/tests/test_kb_templates.py -m maven -q -s` (PowerShell: `$env:KB_MAVEN='1'; python -m pytest ... -m maven -q -s`).
Expected: both pass. The first run downloads Maven 3.9.9 and the dependencies; allow several minutes. If it fails, read the Maven output: a `Could not resolve` line means a coordinate typo (compare against the Tech Stack list); a compile error means a Java typo; a Karate failure means the smoke feature or `mutate.js` is wrong. Fix and re-run. Do not weaken the assertions.

- [ ] **Step 7: Capture the report fixture**

Copy the smoke run's report files into the repo so Task 7 can test the parser without a JVM:

```bash
mkdir -p skills/karate-bootstrap/tests/fixtures/karate-reports
cp <module_copy>/target/karate-reports/*harness-smoke*.json skills/karate-bootstrap/tests/fixtures/karate-reports/
cp <module_copy>/target/karate-reports/*harness-smoke*.xml  skills/karate-bootstrap/tests/fixtures/karate-reports/
```

(`<module_copy>` is the pytest tmp dir printed by `-s`; alternatively run `./mvnw -q test -Dkb.skipContainers=true` directly inside `templates/karate-tests` and copy from its `target/`, then `rm -rf` that `target/`.) Record the exact file names in the task report; Task 7 uses them.

- [ ] **Step 8: Default pytest and gates stay green**

Run: `python -m pytest -q && python -m ruff check . && python -m mypy`
Expected: the maven tests are skipped by default (count unchanged plus 0), everything else passes, ruff and mypy clean.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitattributes skills/karate-bootstrap/templates skills/karate-bootstrap/tests/test_kb_templates.py skills/karate-bootstrap/tests/fixtures/karate-reports
git update-index --chmod=+x skills/karate-bootstrap/templates/karate-tests/mvnw
git commit -m "feat(karate-bootstrap): Karate module template that compiles and runs a container-free smoke feature

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Confirm `git ls-files -s skills/karate-bootstrap/templates/karate-tests/mvnw` shows mode `100755`.

### Task 4: `Containers.java`

**Confidence:** 80%. Compile-checked here; the first real container start happens in Plan 4. Every Testcontainers call below exists in 1.21.4: `Network.newNetwork()`, `PostgreSQLContainer(DockerImageName)`, `GenericContainer.withNetwork/withNetworkAliases/withEnv/withExposedPorts/waitingFor/withLogConsumer/withStartupCheckStrategy`, `Wait.forHttp(...).forPort(...).forStatusCode(...).withStartupTimeout(...)`, `Wait.forListeningPort()`, `Wait.forLogMessage(regex, times)`, `OneShotStartupCheckStrategy().withTimeout(Duration)`, `ImageFromDockerfile(name, deleteOnExit).withFileFromPath(".", Path).withDockerfilePath(String)`, `MockServerContainer(DockerImageName)` with `getServerPort()`, `getMappedPort`, `getHost`. Artemis readiness is detected by the broker's `AMQ221007` "Server is now active" log line.

**Files:**
- Create: `skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness/Containers.java`

**Interfaces:**
- Consumes: `KbRuntime` getters from Task 3.
- Produces (all `public static`): `start()` idempotent; `appBaseUrl()`; `jdbcUrl()`, `dbUser()`, `dbPassword()`; `jmsUrl()`, `amqUser()`, `amqPassword()`; `mockServerHost()`, `mockServerPort()`; `stubsInternalUrl()` = `http://mockserver:1080`; `authInternalUrl()` = `http://mockserver:1080/auth`; `appLogPath()`; `substitute(String template)` for the `{{...}}` placeholders; `isQueue(String destination)`. Task 5 adds one call (`Jwt.publishJwks()`) after MockServer starts.

- [ ] **Step 1: Write `Containers.java`**

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
import org.testcontainers.containers.MockServerContainer;
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
 * Owns the whole test topology: network, Postgres, Artemis, MockServer, the one-shot
 * db-manager, then the application image built from the repo's own Dockerfile.
 *
 * Start order and every value the containers see come from kb-runtime.json via
 * {@link KbRuntime}. Nothing here is repo-specific.
 */
public final class Containers {

    private static final Logger LOG = LoggerFactory.getLogger(Containers.class);

    static final String DB_ALIAS = "db";
    static final String AMQ_ALIAS = "artemis";
    static final String STUBS_ALIAS = "mockserver";
    static final String APP_ALIAS = "app";
    static final int DB_PORT = 5432;
    static final int AMQ_CORE_PORT = 61616;
    static final int AMQ_AMQP_PORT = 5672;
    static final int AMQ_STOMP_PORT = 61613;
    static final int AMQ_HTTP_PORT = 8161;
    static final int STUBS_PORT = MockServerContainer.PORT;

    static final DockerImageName POSTGRES_IMAGE = DockerImageName.parse("postgres:16-alpine");
    static final DockerImageName ARTEMIS_IMAGE =
        DockerImageName.parse("apache/activemq-artemis:2.44.0-alpine");
    static final DockerImageName MOCKSERVER_IMAGE =
        DockerImageName.parse("mockserver/mockserver:mockserver-5.15.0");

    private static boolean started;
    private static Network network;
    private static PostgreSQLContainer<?> postgres;
    private static GenericContainer<?> artemis;
    private static MockServerContainer mockServer;
    private static GenericContainer<?> app;
    private static KbRuntime runtime;
    private static final Path TARGET = Paths.get("target");

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
            .withEnv("EXTRA_ARGS", artemisExtraArgs(runtime))
            .waitingFor(Wait.forLogMessage(".*AMQ221007.*\\n", 1)
                .withStartupTimeout(Duration.ofSeconds(120)))
            .withLogConsumer(fileLog("artemis"));
        artemis.start();

        mockServer = new MockServerContainer(MOCKSERVER_IMAGE)
            .withNetwork(network)
            .withNetworkAliases(STUBS_ALIAS)
            .withLogConsumer(fileLog("mockserver"));
        mockServer.start();

        runMigrations();

        app = buildApp()
            .withNetwork(network)
            .withNetworkAliases(APP_ALIAS)
            .withExposedPorts(runtime.appPort())
            .waitingFor(appWait())
            .withLogConsumer(fileLog("app"))
            .withLogConsumer(new Slf4jLogConsumer(LOG).withPrefix("app"));
        for (Map<String, String> entry : runtime.env()) {
            app.withEnv(entry.get("name"), substitute(entry.get("value")));
        }
        app.start();

        started = true;
        LOG.info("topology up: app={} db={} jms={} stubs={}:{}", appBaseUrl(), jdbcUrl(), jmsUrl(),
            mockServerHost(), mockServerPort());
    }

    // --- accessors used by karate-config.js and the helpers ------------------------------

    public static String appBaseUrl() {
        return "http://" + app.getHost() + ":" + app.getMappedPort(runtime.appPort());
    }

    public static String jdbcUrl() {
        return postgres.getJdbcUrl();
    }

    public static String dbUser() {
        return runtime.dbUser();
    }

    public static String dbPassword() {
        return runtime.dbPassword();
    }

    public static String jmsUrl() {
        return "tcp://" + artemis.getHost() + ":" + artemis.getMappedPort(AMQ_CORE_PORT);
    }

    public static String amqUser() {
        return runtime.amqUser();
    }

    public static String amqPassword() {
        return runtime.amqPassword();
    }

    public static String mockServerHost() {
        return mockServer.getHost();
    }

    public static int mockServerPort() {
        return mockServer.getServerPort();
    }

    /** URL the application uses to reach MockServer from inside the network. */
    public static String stubsInternalUrl() {
        return "http://" + STUBS_ALIAS + ":" + STUBS_PORT;
    }

    /** Issuer URL served from MockServer when auth mode is jwks. */
    public static String authInternalUrl() {
        return stubsInternalUrl() + "/auth";
    }

    public static Path appLogPath() {
        return TARGET.resolve("app.log");
    }

    public static boolean isQueue(String destination) {
        return runtime.amqQueues().contains(destination) || !runtime.amqTopics().contains(destination);
    }

    static KbRuntime runtime() {
        return runtime;
    }

    // --- internals ----------------------------------------------------------------------

    static String substitute(String template) {
        Map<String, String> values = new LinkedHashMap<>();
        values.put("db.host", DB_ALIAS);
        values.put("db.port", Integer.toString(DB_PORT));
        values.put("db.name", runtime.dbName());
        values.put("db.user", runtime.dbUser());
        values.put("db.password", runtime.dbPassword());
        values.put("amq.host", AMQ_ALIAS);
        values.put("amq.corePort", Integer.toString(AMQ_CORE_PORT));
        values.put("amq.amqpPort", Integer.toString(AMQ_AMQP_PORT));
        values.put("amq.stompPort", Integer.toString(AMQ_STOMP_PORT));
        values.put("amq.user", runtime.amqUser());
        values.put("amq.password", runtime.amqPassword());
        values.put("stubs.url", stubsInternalUrl());
        values.put("auth.url", authInternalUrl());
        String out = template;
        for (Map.Entry<String, String> e : values.entrySet()) {
            out = out.replace("{{" + e.getKey() + "}}", e.getValue());
        }
        return out;
    }

    private static String artemisExtraArgs(KbRuntime rt) {
        StringBuilder args = new StringBuilder("--http-host 0.0.0.0 --relax-jolokia");
        List<String> queues = rt.amqQueues();
        List<String> topics = rt.amqTopics();
        if (!queues.isEmpty()) {
            args.append(" --queues ").append(String.join(",", queues));
        }
        if (!topics.isEmpty()) {
            args.append(" --addresses ").append(String.join(",", topics));
        }
        return args.toString();
    }

    private static void runMigrations() {
        String image = runtime.migrationsImage();
        if (!"migration-container".equals(runtime.migrationsStrategy())) {
            LOG.info("migrations strategy {}: nothing to run before the app", runtime.migrationsStrategy());
            return;
        }
        if (image == null) {
            throw new IllegalStateException(
                "kb-runtime.json has no migrations.image; rerun kb_scaffold.py with --migrations-image "
                    + "or add the db to ~/.karate-bootstrap/config.yaml");
        }
        GenericContainer<?> manager = new GenericContainer<>(DockerImageName.parse(image))
            .withNetwork(network)
            .withStartupCheckStrategy(new OneShotStartupCheckStrategy().withTimeout(Duration.ofMinutes(5)))
            .withLogConsumer(fileLog("db-manager"));
        for (Map.Entry<String, String> e : runtime.migrationsEnv().entrySet()) {
            manager.withEnv(e.getKey(), substitute(e.getValue()));
        }
        try {
            manager.start();
        } catch (RuntimeException e) {
            throw new IllegalStateException(
                "db-manager " + image + " did not exit 0; see target/db-manager.log", e);
        }
        LOG.info("db-manager {} completed", image);
    }

    private static GenericContainer<?> buildApp() {
        String prebuilt = System.getProperty("app.image");
        if (prebuilt != null && !prebuilt.isBlank()) {
            LOG.info("using prebuilt app image {}", prebuilt);
            return new GenericContainer<>(DockerImageName.parse(prebuilt));
        }
        Path repoRoot = Paths.get(System.getProperty("user.dir")).resolve(runtime.repoRootRel()).normalize();
        LOG.info("building app image from {}/{}", repoRoot, runtime.dockerfileRel());
        ImageFromDockerfile image = new ImageFromDockerfile("kb-app-" + runtime.repo().toLowerCase(), false)
            .withFileFromPath(".", repoRoot)
            .withDockerfilePath(runtime.dockerfileRel());
        return new GenericContainer<>(image);
    }

    private static WaitStrategy appWait() {
        Duration timeout = Duration.ofSeconds(
            runtime.startupTimeoutSeconds() * (runtime.serverless() ? 2 : 1));
        String path = runtime.readinessPath();
        if (path == null) {
            return Wait.forListeningPort().withStartupTimeout(timeout);
        }
        return Wait.forHttp(path).forPort(runtime.appPort()).forStatusCode(200).withStartupTimeout(timeout);
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
                Files.writeString(file, text, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        };
    }
}
```

- [ ] **Step 2: Compile**

Run: `KB_MAVEN=1 python -m pytest skills/karate-bootstrap/tests/test_kb_templates.py -m maven -q` (or `./mvnw -q test-compile` inside `templates/karate-tests`, then delete its `target/`).
Expected: compiles; the smoke run still passes because `kb.skipContainers=true` never reaches `Containers.start()`.

Compile errors to expect and how to fix: `withStartupCheckStrategy` and `withLogConsumer` return `SELF`, so chaining on `GenericContainer<?>` needs the local variable typed `GenericContainer<?>` exactly as written; `MockServerContainer.PORT` is a public constant in 1.21.4; `Slf4jLogConsumer.withPrefix` exists. If `PostgreSQLContainer<?>` complains about the raw wildcard on construction, use `new PostgreSQLContainer<>(POSTGRES_IMAGE)` assigned to a `PostgreSQLContainer<?>` field as above.

- [ ] **Step 3: Commit**

```bash
git add skills/karate-bootstrap/templates/karate-tests/src/test/java/kb/harness/Containers.java
git commit -m "feat(karate-bootstrap): Containers.java topology with db-manager, Artemis addresses and MockServer

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `Db.java`, `Jms.java`, `Stubs.java`, `Jwt.java` and `common/reset.feature`

**Confidence:** 82%. Compile-checked; `Jwt` and `Stubs` request-building are unit-testable without containers (JUnit tests under the template, excluded from the Karate run by surefire's include filter but run when Task 3's Maven test invokes `test`... surefire only includes `KarateRunner.java`, so add the helper tests to the include list). MockServer is driven over its REST API with `java.net.http.HttpClient`, so `mockserver-client-java` is dropped from the pom (fewer moving parts; the spec line is amended in Task 10).

**Files:**
- Create: `.../kb/harness/Db.java`, `Jms.java`, `Stubs.java`, `Jwt.java`
- Create: `.../kb/harness/JwtTest.java`, `StubsTest.java` (host-only unit tests)
- Create: `.../src/test/resources/common/reset.feature`
- Modify: `Containers.java` (call `Jwt.publishJwks()` after MockServer starts when auth mode is `jwks`)
- Modify: `pom.xml` (remove `mockserver-client-java`; surefire includes `**/*Test.java` and `**/KarateRunner.java`)

**Interfaces (all `public static`, called from Karate via `Java.type`):**
- `Db.run(String path)` executes a SQL file from the classpath (`seed/x.sql`) or filesystem; `Db.row(String table, Map<String,Object> where)` → `Map<String,Object>` or `null`; `Db.awaitRow(table, where, long timeoutMs)`; `Db.count(table, where)` → `long`; `Db.truncate(List<String> tables)`. Identifiers must match `^[A-Za-z_][A-Za-z0-9_]*$`; values always go through `PreparedStatement`.
- `Jms.watch(String destination)` subscribes before the request; `Jms.await(String destination, long timeoutMs)` → `Map` with `body` (parsed JSON when possible, else string) and `properties`; `Jms.publish(String destination, Object body, Map<String,Object> headers)`.
- `Stubs.reset()`; `Stubs.load(String path)` PUTs the JSON array at `path` to `/mockserver/expectation`; `Stubs.verify(String method, String path, int times)` → `true` or throws `AssertionError` with MockServer's message; `Stubs.dumpRequests()` writes recorded requests to `target/stubs-requests.log`.
- `Jwt.token(Map<String,Object> claims)` → signed RS256 JWT with `iss` = `Containers.authInternalUrl()`, `exp` now+1h, `kid`; `Jwt.publishJwks()` installs `GET /auth/.well-known/openid-configuration` and `GET /auth/.well-known/jwks.json` expectations on MockServer.
- `common/reset.feature` accepts `{ stubs: ['stubs/<f>/<d>.json', ...], seed: 'seed/<f>.sql', truncate: ['t1'], watch: ['dest'] }`.

- [ ] **Step 1: Write `Db.java`**

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

/** JDBC helpers exposed to Karate as {@code Db}. Identifiers are validated, values are bound. */
public final class Db {

    private static final Pattern IDENT = Pattern.compile("^[A-Za-z_][A-Za-z0-9_]*$");

    private Db() {
    }

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

    // --- internals ----------------------------------------------------------------------

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

- [ ] **Step 2: Write `Jms.java`**

```java
package kb.harness;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.Map;
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
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

/**
 * JMS helpers exposed to Karate as {@code Jms}. {@link #watch} must be called before the
 * request that is expected to publish, so multicast (topic) messages are not missed.
 */
public final class Jms {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Map<String, BlockingQueue<Map<String, Object>>> INBOX = new ConcurrentHashMap<>();
    private static final Map<String, MessageConsumer> CONSUMERS = new ConcurrentHashMap<>();
    private static Connection connection;
    private static Session session;

    private Jms() {
    }

    public static synchronized void watch(String destination) {
        try {
            ensureSession();
            INBOX.computeIfAbsent(destination, d -> new LinkedBlockingQueue<>()).clear();
            if (!CONSUMERS.containsKey(destination)) {
                MessageConsumer consumer = session.createConsumer(destinationFor(destination));
                consumer.setMessageListener(message -> INBOX.get(destination).offer(toMap(message)));
                CONSUMERS.put(destination, consumer);
            }
        } catch (JMSException e) {
            throw new IllegalStateException("Jms.watch failed for " + destination + ": " + e.getMessage(), e);
        }
    }

    public static Map<String, Object> await(String destination, long timeoutMs) {
        BlockingQueue<Map<String, Object>> queue = INBOX.get(destination);
        if (queue == null) {
            throw new IllegalStateException("Jms.await(" + destination + ") called without Jms.watch first");
        }
        try {
            Map<String, Object> message = queue.poll(timeoutMs, TimeUnit.MILLISECONDS);
            if (message == null) {
                throw new AssertionError("no message on " + destination + " within " + timeoutMs + "ms");
            }
            return message;
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

    // --- internals ----------------------------------------------------------------------

    private static void ensureSession() throws JMSException {
        if (session != null) {
            return;
        }
        ActiveMQConnectionFactory factory = new ActiveMQConnectionFactory(
            Containers.jmsUrl(), Containers.amqUser(), Containers.amqPassword());
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

`javax.jms` is the API the 2.x `artemis-jms-client` exposes (the `jakarta` variant is a separate artifact); if compilation reports the package missing, switch imports to `jakarta.jms` and the artifact to `artemis-jakarta-client`, and record which one worked in the report.

- [ ] **Step 3: Write `Stubs.java`**

```java
package kb.harness;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/** MockServer helpers exposed to Karate as {@code Stubs}, driven over MockServer's REST API. */
public final class Stubs {

    private static final HttpClient HTTP = HttpClient.newHttpClient();

    private Stubs() {
    }

    public static void reset() {
        put("/mockserver/reset", "");
    }

    /** Loads a JSON array of MockServer expectations from the classpath or filesystem. */
    public static void load(String path) {
        String body = Db.readText(path);
        HttpResponse<String> response = put("/mockserver/expectation", body);
        if (response.statusCode() / 100 != 2) {
            throw new IllegalStateException("MockServer rejected " + path + ": " + response.statusCode()
                + " " + response.body());
        }
    }

    public static boolean verify(String method, String path, int times) {
        String body = "{\"httpRequest\":{\"method\":\"" + method + "\",\"path\":\"" + path + "\"},"
            + "\"times\":{\"atLeast\":" + times + ",\"atMost\":" + times + "}}";
        HttpResponse<String> response = put("/mockserver/verify", body);
        if (response.statusCode() == 202) {
            return true;
        }
        throw new AssertionError("Stubs.verify " + method + " " + path + " x" + times + " failed: "
            + response.body());
    }

    /** Writes every request MockServer recorded to target/stubs-requests.log for the iterate loop. */
    public static Path dumpRequests() {
        HttpResponse<String> response = put("/mockserver/retrieve?type=REQUESTS&format=JSON", "");
        Path file = Paths.get("target", "stubs-requests.log");
        try {
            Files.createDirectories(file.getParent());
            Files.writeString(file, response.body(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        return file;
    }

    static String baseUrl() {
        return "http://" + Containers.mockServerHost() + ":" + Containers.mockServerPort();
    }

    static HttpResponse<String> put(String pathAndQuery, String body) {
        HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl() + pathAndQuery))
            .header("Content-Type", "application/json")
            .PUT(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
            .build();
        try {
            return HTTP.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (IOException e) {
            throw new IllegalStateException("MockServer call failed: " + pathAndQuery, e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    /** Pure helper, unit-tested: builds the verify payload. */
    static String verifyBody(String method, String path, int times) {
        return "{\"httpRequest\":{\"method\":\"" + method + "\",\"path\":\"" + path + "\"},"
            + "\"times\":{\"atLeast\":" + times + ",\"atMost\":" + times + "}}";
    }
}
```

Replace the inline string in `verify` with `verifyBody(method, path, times)` so the helper is the single source.

- [ ] **Step 4: Write `Jwt.java`**

```java
package kb.harness;

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

/** Test issuer: one RSA key per JVM, discovery + JWKS served from MockServer under /auth. */
public final class Jwt {

    private static final RSAKey KEY = generate();

    private Jwt() {
    }

    public static String token(Map<String, Object> claims) {
        try {
            JWTClaimsSet.Builder builder = new JWTClaimsSet.Builder()
                .issuer(Containers.authInternalUrl())
                .issueTime(new Date())
                .expirationTime(new Date(System.currentTimeMillis() + 3_600_000L));
            if (claims != null) {
                claims.forEach(builder::claim);
            }
            SignedJWT jwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(KEY.getKeyID()).build(), builder.build());
            jwt.sign(new RSASSASigner(KEY));
            return jwt.serialize();
        } catch (JOSEException e) {
            throw new IllegalStateException("Jwt.token failed", e);
        }
    }

    /** Installs OIDC discovery and JWKS expectations. Called by Containers when auth mode is jwks. */
    public static void publishJwks() {
        String issuer = Containers.authInternalUrl();
        String jwks = new JWKSet(KEY.toPublicJWK()).toString();
        String discovery = "{\"issuer\":\"" + issuer + "\",\"jwks_uri\":\"" + issuer
            + "/.well-known/jwks.json\",\"id_token_signing_alg_values_supported\":[\"RS256\"]}";
        Stubs.put("/mockserver/expectation", expectation("/auth/.well-known/openid-configuration", discovery));
        Stubs.put("/mockserver/expectation", expectation("/auth/.well-known/jwks.json", jwks));
    }

    static String expectation(String path, String jsonBody) {
        return "[{\"httpRequest\":{\"method\":\"GET\",\"path\":\"" + path + "\"},"
            + "\"httpResponse\":{\"statusCode\":200,\"headers\":{\"Content-Type\":[\"application/json\"]},"
            + "\"body\":" + jsonBody + "},\"priority\":10}]";
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

- [ ] **Step 5: Wire `Jwt.publishJwks()` into `Containers.start()`**

After `mockServer.start();` add:

```java
        if ("jwks".equals(runtime.authMode())) {
            Jwt.publishJwks();
            LOG.info("issuer {} published to MockServer", authInternalUrl());
        }
```

- [ ] **Step 6: Host-only unit tests**

`src/test/java/kb/harness/JwtTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.nimbusds.jose.JWSVerifier;
import com.nimbusds.jose.crypto.RSASSAVerifier;
import com.nimbusds.jwt.SignedJWT;
import java.util.Map;
import org.junit.jupiter.api.Test;

class JwtTest {

    @Test
    void expectationWrapsBodyAsMockServerJson() {
        String json = Jwt.expectation("/auth/x", "{\"a\":1}");
        assertTrue(json.startsWith("[{\"httpRequest\":{\"method\":\"GET\",\"path\":\"/auth/x\"}"));
        assertTrue(json.contains("\"body\":{\"a\":1}"));
    }

    @Test
    void tokenIsSignedByTheTestKey() throws Exception {
        // Containers is not started in this test, so build the claims without the issuer accessor.
        SignedJWT jwt = SignedJWT.parse(JwtTestSupport.tokenWithoutContainers(Map.of("sub", "alice")));
        JWSVerifier verifier = new RSASSAVerifier(Jwt.key().toRSAPublicKey());
        assertTrue(jwt.verify(verifier));
        assertEquals("alice", jwt.getJWTClaimsSet().getSubject());
        assertEquals("kb-test-key", jwt.getHeader().getKeyID());
    }
}
```

Add a small package-private support class so `token()` can be exercised without a running topology:

`src/test/java/kb/harness/JwtTestSupport.java`:

```java
package kb.harness;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.util.Map;

final class JwtTestSupport {
    private JwtTestSupport() {
    }

    static String tokenWithoutContainers(Map<String, Object> claims) throws JOSEException {
        JWTClaimsSet.Builder builder = new JWTClaimsSet.Builder().issuer("http://test/auth");
        claims.forEach(builder::claim);
        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(Jwt.key().getKeyID()).build(), builder.build());
        jwt.sign(new RSASSASigner(Jwt.key()));
        return jwt.serialize();
    }
}
```

`src/test/java/kb/harness/StubsTest.java`:

```java
package kb.harness;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class StubsTest {

    @Test
    void verifyBodyPinsExactCount() {
        assertEquals(
            "{\"httpRequest\":{\"method\":\"GET\",\"path\":\"/prices/BRENT\"},\"times\":{\"atLeast\":1,\"atMost\":1}}",
            Stubs.verifyBody("GET", "/prices/BRENT", 1));
    }
}
```

Surefire config in `pom.xml` becomes:

```xml
          <includes>
            <include>**/*Test.java</include>
            <include>**/KarateRunner.java</include>
          </includes>
```

and remove the `mockserver-client-java` dependency and its `mockserver.version` property.

- [ ] **Step 7: Write `common/reset.feature`**

```gherkin
@ignore
Feature: reset stubs, seed data and message watches before a scenario

Scenario:
  * def stubFiles = karate.get('stubs', [])
  * def seedFile = karate.get('seed', null)
  * def tables = karate.get('truncate', [])
  * def watchList = karate.get('watch', [])
  * Stubs.reset()
  * karate.forEach(stubFiles, function(f){ Stubs.load(f) })
  * if (tables.length > 0) Db.truncate(tables)
  * if (seedFile) Db.run(seedFile)
  * karate.forEach(watchList, function(d){ Jms.watch(d) })
```

Callers pass paths as they appear on the classpath: `stubs: ['stubs/post-api-deals/pricing.json'], seed: 'seed/post-api-deals.sql'`.

- [ ] **Step 8: Compile, run unit tests and the smoke feature**

Run: `KB_MAVEN=1 python -m pytest skills/karate-bootstrap/tests/test_kb_templates.py -m maven -q -s`
Expected: `test-compile` passes; `test -Dkb.skipContainers=true` runs `JwtTest`, `StubsTest` and the Karate smoke feature, all green. If `javax.jms` is missing, apply the `jakarta` switch described under Step 2 and note it.

- [ ] **Step 9: Commit**

```bash
git add skills/karate-bootstrap/templates/karate-tests/pom.xml skills/karate-bootstrap/templates/karate-tests/src
git commit -m "feat(karate-bootstrap): Db, Jms, Stubs and Jwt helpers with the reset feature

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 6: `kb_scaffold.py`

**Confidence:** 88%. Pure Python over Plan 1 outputs plus a file copy. Risk is the env-value templating heuristics; they are pinned by fixture-derived tests for all four stacks.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_scaffold.py`
- Create: `skills/karate-bootstrap/templates/karate-tests/azure-pipelines.karate.yml`, `README.md.tmpl`
- Create: `skills/karate-bootstrap/tests/test_kb_scaffold.py`

**Interfaces:**
- Consumes: `flow_map.load_ledger/save_ledger`, `kb_common` IO, the template tree from Tasks 3 to 5.
- Produces:
  - `TEMPLATE_DIR: Path` (the `templates/karate-tests` directory).
  - `load_central_config(path: Path | None) -> dict[str, Any]` (default `~/.karate-bootstrap/config.yaml`, `{}` when absent).
  - `db_name_from_env(env_map) -> str` (from a db-role placeholder's `Database=` or URL path, else a `ConnectionStrings__<Name>` key name lower-cased, else `app`).
  - `resolve_migrations(ledger, db_name, cli_image, config) -> dict[str, Any]` with `strategy, image, env, source, database` (`database` is the config entry's value or `None`); raises `KbError(..., EXIT_NO_SCHEMA)` when no image can be found.
  - `env_value_template(key: str, role: str, placeholder: str, stack: str, auth: dict) -> str`.
  - `build_runtime(ledger, env_map, migrations, db_name: str, repo_root_rel: str) -> dict[str, Any]` (schema from Task 3). The CLI passes `migrations["database"] or db_name_from_env(env_map)`.
  - `render(out_dir: Path, runtime: dict, force: bool) -> list[str]` returning POSIX-relative paths written.
  - CLI: `python scripts/kb_scaffold.py <repo> --ledger PATH --env PATH --out DIR [--service-dir SUB] [--migrations-image REF] [--config PATH] [--force]`. Exit 4 when no migrations image; exit 5 when ledger or env-map missing.
  - Never overwrites `features/`, `rules/`, `stubs/`, `seed/`, `defects.md`, `README.md`; harness files are overwritten only with `--force`; `kb-runtime.json` is always rewritten; nothing is deleted.

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_scaffold.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from detect import main as detect_main
from discover import main as discover_main
from flow_map import load_ledger
from kb_common import EXIT_NO_SCHEMA, KbError, read_json
from kb_scaffold import (
    TEMPLATE_DIR,
    build_runtime,
    db_name_from_env,
    env_value_template,
    load_central_config,
    main,
    render,
    resolve_migrations,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _pipeline(tmp_path: Path, repo: str) -> tuple[Path, Path, Path]:
    root = FIXTURES / repo
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return root, env, ledger


def test_template_dir_is_the_real_module() -> None:
    assert (TEMPLATE_DIR / "pom.xml").is_file()
    assert (TEMPLATE_DIR / "src/test/java/kb/harness/Containers.java").is_file()
    assert (TEMPLATE_DIR / "mvnw").is_file()


@pytest.mark.parametrize(
    ("key", "role", "placeholder", "stack", "expected"),
    [
        ("SPRING_DATASOURCE_URL", "db", "", "spring", "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"),
        ("SPRING_DATASOURCE_USERNAME", "db", "", "spring", "{{db.user}}"),
        ("SPRING_DATASOURCE_PASSWORD", "db", "", "spring", "{{db.password}}"),
        ("QUARKUS_DATASOURCE_JDBC_URL", "db", "jdbc:postgresql://db:5432/invoices", "quarkus",
         "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"),
        ("ConnectionStrings__Deals", "db", "Host=localhost;Database=deals", "aspnetcore",
         "Host={{db.host}};Port={{db.port}};Database={{db.name}};Username={{db.user}};Password={{db.password}}"),
        ("DATABASE_URL", "db", "postgresql://o:o@db:5432/orders", "python",
         "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}"),
        ("SPRING_ARTEMIS_BROKER_URL", "amq", "tcp://artemis:61616", "spring", "tcp://{{amq.host}}:{{amq.corePort}}"),
        ("AMQP_HOST", "amq", "artemis", "quarkus", "{{amq.host}}"),
        ("AMQP_PORT", "amq", "5672", "quarkus", "{{amq.amqpPort}}"),
        ("Amq__Url", "amq", "amqp://artemis:5672", "aspnetcore", "amqp://{{amq.host}}:{{amq.amqpPort}}"),
        ("Amq__User", "amq", "artemis", "aspnetcore", "{{amq.user}}"),
        ("AMQP_URL", "amq", "amqp://artemis:5672", "python", "amqp://{{amq.host}}:{{amq.amqpPort}}"),
        ("PRICING_BASE_URL", "downstream:pricing", "http://pricing:8080", "spring", "{{stubs.url}}/pricing"),
        ("JAVA_OPTS", "passthrough", "-Xmx512m", "spring", "-Xmx512m"),
        ("ASPNETCORE_URLS", "passthrough", "http://+:8080", "aspnetcore", "http://+:8080"),
    ],
)
def test_env_value_template(key: str, role: str, placeholder: str, stack: str, expected: str) -> None:
    assert env_value_template(key, role, placeholder, stack, {"mode": "none"}) == expected


def test_env_value_template_auth_modes() -> None:
    disabled = {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false"}
    assert env_value_template("APP_SECURITY_ENABLED", "auth", "true", "spring", disabled) == "false"
    assert env_value_template("AUTH_ISSUER_URI", "auth", "https://x", "spring", disabled) == "https://x"
    jwks = {"mode": "jwks", "keys": ["AUTH_ISSUER_URI", "JWKS_URL"]}
    assert env_value_template("AUTH_ISSUER_URI", "auth", "https://x", "spring", jwks) == "{{auth.url}}"
    assert env_value_template("JWKS_URL", "auth", "https://x/certs", "python", jwks) == \
        "{{auth.url}}/.well-known/jwks.json"


def test_db_name_from_env(tmp_path: Path) -> None:
    _, env, _ = _pipeline(tmp_path, "quarkus-mini")
    assert db_name_from_env(read_json(env)) == "invoices"
    assert db_name_from_env({"keys": []}) == "app"
    assert db_name_from_env({"keys": [{"key": "ConnectionStrings__Deals", "role": "db", "placeholder": ""}]}) == "deals"
    _, spring_env, _ = _pipeline(tmp_path / "s", "spring-mini")
    assert db_name_from_env(read_json(spring_env)) == "app"  # only ${...} placeholders, no name anywhere


def test_resolve_migrations_prefers_flag_then_config(tmp_path: Path) -> None:
    _, _, ledger_path = _pipeline(tmp_path, "spring-mini")
    ledger = load_ledger(ledger_path)
    flag = resolve_migrations(ledger, "shipments", "registry.example/dbm:1", {})
    assert flag["image"] == "registry.example/dbm:1" and flag["source"] == "flag"
    assert flag["env"]["PGHOST"] == "{{db.host}}"
    config = {"db_managers": {"shipments": {"image": "registry.example/dbm-ship:2", "database": "shipments",
                                             "env": {"DB_HOST_KEY": "DBHOST", "DB_NAME_KEY": "DBNAME"}}}}
    from_config = resolve_migrations(ledger, "shipments", None, config)
    assert from_config["image"] == "registry.example/dbm-ship:2" and from_config["source"] == "config"
    assert from_config["env"] == {"DBHOST": "{{db.host}}", "DBNAME": "{{db.name}}"}
    assert from_config["database"] == "shipments" and flag["database"] is None
    with pytest.raises(KbError) as excinfo:
        resolve_migrations(ledger, "shipments", None, {})
    assert excinfo.value.exit_code == EXIT_NO_SCHEMA


def test_load_central_config(tmp_path: Path) -> None:
    assert load_central_config(tmp_path / "missing.yaml") == {}
    cfg = tmp_path / "config.yaml"
    cfg.write_text("db_managers:\n  deals:\n    image: r/x:1\n    database: deals\n", encoding="utf-8")
    assert load_central_config(cfg)["db_managers"]["deals"]["image"] == "r/x:1"


def test_build_runtime_spring(tmp_path: Path) -> None:
    _, env, ledger_path = _pipeline(tmp_path, "spring-mini")
    ledger = load_ledger(ledger_path)
    migrations = resolve_migrations(ledger, "shipments", "r/dbm:1", {})
    runtime = build_runtime(ledger, read_json(env), migrations, "shipments", "..")
    assert runtime["version"] == 1
    assert runtime["repo"] == "spring-mini" and runtime["stack"] == "spring"
    assert runtime["app"] == {"repoRootRel": "..", "dockerfileRel": "Dockerfile", "port": 8080,
                              "readinessPath": "/actuator/health/readiness", "serverless": True,
                              "startupTimeoutSeconds": 120}
    by_name = {e["name"]: e for e in runtime["env"]}
    assert by_name["SPRING_DATASOURCE_URL"]["value"] == "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"
    assert by_name["PRICING_BASE_URL"]["value"] == "{{stubs.url}}/pricing"
    assert by_name["APP_SECURITY_ENABLED"] == {"name": "APP_SECURITY_ENABLED", "role": "auth", "value": "false"}
    assert runtime["db"]["name"] == "shipments"  # passed in explicitly; the CLI derives it
    assert runtime["amq"]["queues"] == ["shipment.requested"] and runtime["amq"]["topics"] == []
    assert runtime["downstreams"] == [{"name": "pricing", "envVar": "PRICING_BASE_URL"}]
    assert runtime["auth"] == {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false"}
    assert runtime["migrations"]["image"] == "r/dbm:1"


def test_render_copies_module_and_is_idempotent(tmp_path: Path) -> None:
    _, env, ledger_path = _pipeline(tmp_path, "spring-mini")
    ledger = load_ledger(ledger_path)
    migrations = resolve_migrations(ledger, "shipments", "r/dbm:1", {})
    runtime = build_runtime(ledger, read_json(env), migrations, "shipments", "..")
    out = tmp_path / "karate-tests"
    written = render(out, runtime, force=False)
    assert "pom.xml" in written and "src/test/java/kb/harness/Containers.java" in written
    assert "src/test/resources/kb-runtime.json" in written
    assert json.loads((out / "src/test/resources/kb-runtime.json").read_text(encoding="utf-8"))["repo"] == "spring-mini"
    assert (out / "defects.md").is_file() and (out / "rules").is_dir() and (out / "stubs").is_dir()
    # generated content survives a re-render; harness files survive without --force
    feature = out / "src/test/resources/features/post-api-shipments.feature"
    feature.write_text("Feature: x\n", encoding="utf-8")
    pom = out / "pom.xml"
    pom.write_text("<project/>", encoding="utf-8")
    written_again = render(out, runtime, force=False)
    assert feature.read_text(encoding="utf-8") == "Feature: x\n"
    assert pom.read_text(encoding="utf-8") == "<project/>"
    assert written_again == ["src/test/resources/kb-runtime.json"]
    render(out, runtime, force=True)
    assert pom.read_text(encoding="utf-8").startswith("<?xml")
    assert feature.read_text(encoding="utf-8") == "Feature: x\n"


def test_cli_exit_4_without_image(tmp_path: Path) -> None:
    root, env, ledger_path = _pipeline(tmp_path, "spring-mini")
    with pytest.raises(KbError) as excinfo:
        main([str(root), "--ledger", str(ledger_path), "--env", str(env), "--out", str(tmp_path / "kt"),
              "--config", str(tmp_path / "none.yaml")])
    assert excinfo.value.exit_code == EXIT_NO_SCHEMA


def test_cli_writes_module_and_updates_ledger(tmp_path: Path) -> None:
    root, env, ledger_path = _pipeline(tmp_path, "dotnet-mini")
    out = tmp_path / "karate-tests"
    code = main([str(root), "--ledger", str(ledger_path), "--env", str(env), "--out", str(out),
                 "--migrations-image", "r/dbm-deals:1", "--config", str(tmp_path / "none.yaml")])
    assert code == 0
    runtime = json.loads((out / "src/test/resources/kb-runtime.json").read_text(encoding="utf-8"))
    assert runtime["stack"] == "aspnetcore" and runtime["db"]["name"] == "deals"
    by_name = {e["name"]: e["value"] for e in runtime["env"]}
    assert by_name["ConnectionStrings__Deals"].startswith("Host={{db.host}}")
    assert by_name["Amq__Url"] == "amqp://{{amq.host}}:{{amq.amqpPort}}"
    assert runtime["amq"]["queues"] == ["deal.requested"]
    assert runtime["auth"] == {"mode": "disabled", "key": "Auth__Enabled", "value": "false"}
    ledger = load_ledger(ledger_path)
    assert ledger["app"]["migrations"]["image"] == "r/dbm-deals:1"
    assert ledger["app"]["migrations"]["source"] == "flag"
    assert (out / "azure-pipelines.karate.yml").is_file()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_scaffold.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_scaffold'`.

- [ ] **Step 3: Add the two remaining templates**

`templates/karate-tests/azure-pipelines.karate.yml`:

```yaml
# Reusable job: run the Karate ground-truth suite under Testcontainers.
# Include from the service pipeline with:
#   - template: karate-tests/azure-pipelines.karate.yml
#     parameters:
#       appImage: $(imageTag)      # optional, skips the Dockerfile build inside the tests
parameters:
  - name: appImage
    type: string
    default: ''
  - name: javaVersion
    type: string
    default: '21'

jobs:
  - job: karate_tests
    displayName: Karate ground-truth suite
    pool:
      vmImage: ubuntu-latest
    steps:
      - task: JavaToolInstaller@0
        inputs:
          versionSpec: ${{ parameters.javaVersion }}
          jdkArchitectureOption: x64
          jdkSourceOption: PreInstalled
      - script: |
          cd karate-tests
          chmod +x mvnw
          if [ -n "${{ parameters.appImage }}" ]; then
            ./mvnw -B test -Dapp.image=${{ parameters.appImage }}
          else
            ./mvnw -B test
          fi
        displayName: mvnw test
      - task: PublishTestResults@2
        condition: always()
        inputs:
          testResultsFormat: JUnit
          testResultsFiles: 'karate-tests/target/karate-reports/*.xml'
          testRunTitle: karate
      - task: PublishBuildArtifacts@1
        condition: always()
        inputs:
          pathToPublish: karate-tests/target/karate-reports
          artifactName: karate-reports
```

`templates/karate-tests/README.md.tmpl` (filled by `kb_report.py summary`, Task 7):

```markdown
# Karate ground-truth suite for $repo

Generated by karate-bootstrap on $date. Stack: $stack. Documents existing behaviour; suspected defects are quarantined in `defects.md`.

## Run

```bash
cd karate-tests
./mvnw test                      # everything except @known-defect
./mvnw test -Dkarate.options="--tags @smoke"
./mvnw test -Dapp.image=<tag>    # reuse a built image instead of building from the Dockerfile
```

Needs a JDK 17+, Maven (or the wrapper), and a container runtime. Podman users: see `podman.md` in the skill's reference directory or set `DOCKER_HOST` to the podman socket; `src/test/resources/testcontainers.properties` already sets `ryuk.container.privileged=true`.

## What is covered

$counts_table

Auth mode: $auth_mode. Schema: $migrations. Readiness: $readiness.

## Quarantined suspected defects

$defects_section

## Observed-behaviour overrides

$overrides_section

## Notes

$notes_section
```

- [ ] **Step 4: Implement `kb_scaffold.py`**

```python
# skills/karate-bootstrap/scripts/kb_scaffold.py
"""Phase 4 of karate-bootstrap: render the karate-tests module.

Copies the template module (a real Maven project kept under
``templates/karate-tests``) into the target repo and writes
``src/test/resources/kb-runtime.json``, the only file that carries
repo-specific values. Generated content (features, rules, stubs, seeds,
defects.md, README.md) is never overwritten; harness files are overwritten
only with ``--force``.

Usage:
    python scripts/kb_scaffold.py <repo> --ledger karate-tests/flow-map.yaml \
        --env karate-tests/env-map.json --out karate-tests \
        [--service-dir SUB] [--migrations-image REF] [--config ~/.karate-bootstrap/config.yaml] [--force]

Exit codes: 0 ok, 4 no db-manager image from flag or config, 5 ledger or env-map missing.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from flow_map import load_ledger, save_ledger
from kb_common import EXIT_NO_SCHEMA, EXIT_OK, KbError, read_json, rel, require_file, run_cli, write_json

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
DEFAULT_CONFIG = Path.home() / ".karate-bootstrap" / "config.yaml"
RUNTIME_REL = "src/test/resources/kb-runtime.json"
GENERATED_PREFIXES = ("src/test/resources/features/", "rules/", "stubs/", "seed/")
GENERATED_FILES = ("defects.md", "README.md")
TEMPLATE_SKIP = ("target",)
DEFAULT_DB_MANAGER_ENV = {
    "PGHOST": "{{db.host}}",
    "PGPORT": "{{db.port}}",
    "PGDATABASE": "{{db.name}}",
    "PGUSER": "{{db.user}}",
    "PGPASSWORD": "{{db.password}}",
}
_CONFIG_ENV_KEYS = {
    "DB_HOST_KEY": "{{db.host}}",
    "DB_PORT_KEY": "{{db.port}}",
    "DB_NAME_KEY": "{{db.name}}",
    "DB_USER_KEY": "{{db.user}}",
    "DB_PASSWORD_KEY": "{{db.password}}",
}
_URL_PATH_RE = re.compile(r"://[^/]+/([A-Za-z0-9_\-]+)")
_DATABASE_KV_RE = re.compile(r"(?i)database=([A-Za-z0-9_\-]+)")
_CONNSTR_KEY_RE = re.compile(r"(?i)^connectionstrings__(\w+)$")


def load_central_config(path: Path | None) -> dict[str, Any]:
    target = path or DEFAULT_CONFIG
    if not target.is_file():
        return {}
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise KbError(f"{target}: expected a mapping at top level")
    return data


def db_name_from_env(env_map: dict[str, Any]) -> str:
    db_keys = [item for item in env_map.get("keys", []) if item.get("role") == "db"]
    for item in db_keys:
        placeholder = str(item.get("placeholder") or "")
        kv = _DATABASE_KV_RE.search(placeholder)
        if kv:
            return kv.group(1)
        url = _URL_PATH_RE.search(placeholder)
        if url and not placeholder.startswith("${"):
            return url.group(1)
    for item in db_keys:
        named = _CONNSTR_KEY_RE.match(str(item.get("key", "")))
        if named:
            return named.group(1).lower()
    return "app"


def resolve_migrations(ledger: dict[str, Any], db_name: str, cli_image: str | None,
                       config: dict[str, Any]) -> dict[str, Any]:
    strategy = str(ledger.get("app", {}).get("migrations", {}).get("strategy", "migration-container"))
    if cli_image:
        return {"strategy": strategy, "image": cli_image, "env": dict(DEFAULT_DB_MANAGER_ENV),
                "source": "flag", "database": None}
    managers = config.get("db_managers", {}) or {}
    chosen: dict[str, Any] | None = None
    for name, entry in managers.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("database") == db_name or name == db_name or name == ledger.get("repo"):
            chosen = entry
            break
    if chosen is None and len(managers) == 1:
        chosen = next(iter(managers.values()))
    if chosen is None or not chosen.get("image"):
        raise KbError(
            f"no db-manager image for database {db_name!r}: pass --migrations-image or add a "
            f"db_managers entry to {DEFAULT_CONFIG}",
            EXIT_NO_SCHEMA,
        )
    env: dict[str, str] = {}
    for config_key, template in _CONFIG_ENV_KEYS.items():
        actual = chosen.get("env", {}).get(config_key)
        if actual:
            env[str(actual)] = template
    env.update({str(k): str(v) for k, v in (chosen.get("extra_env") or {}).items()})
    if not env:
        env = dict(DEFAULT_DB_MANAGER_ENV)
    database = chosen.get("database")
    return {"strategy": strategy, "image": str(chosen["image"]), "env": env, "source": "config",
            "database": str(database) if database else None}


def env_value_template(key: str, role: str, placeholder: str, stack: str, auth: dict[str, Any]) -> str:
    k = key.lower()
    p = placeholder or ""
    pl = p.lower()
    if role == "db":
        if "user" in k:
            return "{{db.user}}"
        if "pass" in k:
            return "{{db.password}}"
        if "host" in k:
            return "{{db.host}}"
        if "port" in k:
            return "{{db.port}}"
        if k.endswith(("name", "database", "_db", "-db")):
            return "{{db.name}}"
        if "jdbc:" in pl or stack in ("spring", "quarkus"):
            return "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"
        if stack == "aspnetcore":
            return ("Host={{db.host}};Port={{db.port}};Database={{db.name}};"
                    "Username={{db.user}};Password={{db.password}}")
        return "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}"
    if role == "amq":
        if "user" in k:
            return "{{amq.user}}"
        if "pass" in k:
            return "{{amq.password}}"
        if "host" in k:
            return "{{amq.host}}"
        if "port" in k:
            return "{{amq.corePort}}" if stack in ("spring",) and "amqp" not in k else "{{amq.amqpPort}}"
        if "stomp" in pl or "stomp" in k:
            return "stomp://{{amq.host}}:{{amq.stompPort}}"
        if "failover:" in pl:
            return "failover:(tcp://{{amq.host}}:{{amq.corePort}})"
        if "activemq:" in pl:
            return "activemq:tcp://{{amq.host}}:{{amq.corePort}}"
        if "amqp" in pl or "amqp" in k or stack in ("aspnetcore", "python"):
            return "amqp://{{amq.host}}:{{amq.amqpPort}}"
        return "tcp://{{amq.host}}:{{amq.corePort}}"
    if role.startswith("downstream:"):
        return "{{stubs.url}}/" + role.split(":", 1)[1]
    if role == "auth":
        mode = auth.get("mode")
        if mode == "disabled" and auth.get("key") == key:
            return str(auth.get("value"))
        if mode == "jwks":
            return "{{auth.url}}/.well-known/jwks.json" if "jwks" in k else "{{auth.url}}"
        return "" if p.startswith("${") else p
    return "" if p.startswith("${") else p


def _destinations(ledger: dict[str, Any]) -> tuple[list[str], list[str]]:
    queues: list[str] = []
    topics: list[str] = []

    def add(name: str | None, kind: str) -> None:
        if not name:
            return
        target = topics if kind == "topic" else queues
        if name not in target:
            target.append(name)

    for entry in ledger.get("entry_points", []):
        if entry.get("kind") == "amq-subscribe":
            add(entry.get("destination"), str(entry.get("type", "queue")))
        for item in entry.get("exits", []):
            if item.get("kind") == "amq-publish":
                add(item.get("destination"), str(item.get("type", "queue")))
    return queues, topics


def build_runtime(ledger: dict[str, Any], env_map: dict[str, Any], migrations: dict[str, Any],
                  db_name: str, repo_root_rel: str) -> dict[str, Any]:
    stack = str(ledger.get("stack", {}).get("framework"))
    app = ledger.get("app", {})
    auth = dict(app.get("auth") or {"mode": "none"})
    env_entries: list[dict[str, str]] = []
    seen: set[str] = set()
    downstreams: list[dict[str, str]] = []
    for item in env_map.get("keys", []):
        env_var = item.get("env_var")
        if not env_var or env_var in seen:
            continue
        seen.add(env_var)
        role = str(item.get("role", "passthrough"))
        value = env_value_template(env_var, role, str(item.get("placeholder") or ""), stack, auth)
        env_entries.append({"name": env_var, "role": role, "value": value})
        if role.startswith("downstream:"):
            downstreams.append({"name": role.split(":", 1)[1], "envVar": env_var})
    queues, topics = _destinations(ledger)
    readiness = app.get("readiness") or {}
    runtime_auth: dict[str, Any] = {"mode": auth.get("mode", "none")}
    if auth.get("mode") == "disabled":
        runtime_auth.update({"key": auth.get("key"), "value": auth.get("value")})
    elif auth.get("mode") == "jwks":
        runtime_auth["issuerKeys"] = list(auth.get("keys", []))
    return {
        "version": 1,
        "repo": ledger.get("repo"),
        "stack": stack,
        "app": {
            "repoRootRel": repo_root_rel,
            "dockerfileRel": app.get("dockerfile", "Dockerfile"),
            "port": int(app.get("port") or 8080),
            "readinessPath": readiness.get("path"),
            "serverless": bool(app.get("serverless", False)),
            "startupTimeoutSeconds": 120,
        },
        "env": env_entries,
        "db": {"name": db_name, "user": "app", "password": "app"},
        "migrations": {"strategy": migrations["strategy"], "image": migrations["image"],
                       "env": migrations["env"]},
        "amq": {"user": "artemis", "password": "artemis", "queues": queues, "topics": topics},
        "downstreams": downstreams,
        "auth": runtime_auth,
    }


def _is_generated(rel_path: str) -> bool:
    return rel_path.startswith(GENERATED_PREFIXES) or rel_path in GENERATED_FILES


def render(out_dir: Path, runtime: dict[str, Any], force: bool) -> list[str]:
    written: list[str] = []
    for source in sorted(TEMPLATE_DIR.rglob("*")):
        rel_path = rel(source, TEMPLATE_DIR)
        if source.is_dir() or rel_path.split("/", 1)[0] in TEMPLATE_SKIP:
            continue
        if rel_path == RUNTIME_REL or rel_path == "README.md.tmpl":
            continue
        if rel_path.startswith("src/test/resources/features/") and "harness-smoke" not in rel_path:
            continue
        target = out_dir / rel_path
        if target.exists() and (not force or _is_generated(rel_path)):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(rel_path)
    for directory in ("rules", "stubs", "seed", "seed/examples", "src/test/resources/features"):
        (out_dir / directory).mkdir(parents=True, exist_ok=True)
    defects = out_dir / "defects.md"
    if not defects.exists():
        defects.write_text("# Suspected application defects\n\nNone recorded yet.\n", encoding="utf-8")
        written.append("defects.md")
    write_json(out_dir / RUNTIME_REL, runtime)
    written.append(RUNTIME_REL)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the karate-tests module from the ledger")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--service-dir", default=None)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--env", type=Path, required=True, help="env-map.json")
    parser.add_argument("--out", type=Path, required=True, help="karate-tests directory to write")
    parser.add_argument("--migrations-image", default=None, help="db-manager image reference")
    parser.add_argument("--config", type=Path, default=None, help="central config (default ~/.karate-bootstrap/config.yaml)")
    parser.add_argument("--force", action="store_true", help="overwrite harness files (never generated content)")
    args = parser.parse_args(argv)

    root = args.repo / args.service_dir if args.service_dir else args.repo
    ledger = load_ledger(args.ledger)
    env_map = read_json(require_file(args.env, "env-map.json"))
    config = load_central_config(args.config)
    db_name = db_name_from_env(env_map)
    migrations = resolve_migrations(ledger, db_name, args.migrations_image, config)
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    # The module always sits directly under the service root, so the repo root is one level up.
    repo_root_rel = ".."
    runtime = build_runtime(ledger, env_map, migrations, migrations["database"] or db_name, repo_root_rel)
    written = render(out_dir, runtime, args.force)
    ledger.setdefault("app", {})["migrations"] = {
        **ledger.get("app", {}).get("migrations", {}),
        "strategy": migrations["strategy"],
        "image": migrations["image"],
        "source": migrations["source"],
    }
    save_ledger(args.ledger, ledger)
    print(f"scaffolded {len(written)} file(s) into {out_dir}; db-manager {migrations['image']} "
          f"({migrations['source']}); auth {runtime['auth']['mode']}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

`--service-dir` is honoured by resolving `root`; it only matters because the ledger's `dockerfile` is relative to `root`, which `Containers.java` resolves through `repoRootRel`.

- [ ] **Step 5: Run tests and gates**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_scaffold.py -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: pass, clean. mypy may need `-> None` on the inner `add` closure (already typed) and `str(...)` around `chosen["image"]`.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_scaffold.py skills/karate-bootstrap/tests/test_kb_scaffold.py skills/karate-bootstrap/templates/karate-tests/azure-pipelines.karate.yml skills/karate-bootstrap/templates/karate-tests/README.md.tmpl
git commit -m "feat(karate-bootstrap): kb_scaffold renders the module and kb-runtime.json from the ledger

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `kb_report.py parse` and `summary`

**Confidence:** 88%. The parser is pinned by Task 3's real cucumber JSON fixture plus a hand-written failing feature; the README summary is a `string.Template` fill.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_report.py`
- Create: `skills/karate-bootstrap/tests/test_kb_report.py`
- Create: `skills/karate-bootstrap/tests/fixtures/karate-reports-failing/features.post-api-shipments.json`

**Interfaces:**
- Produces:
  - `normalise_feature(uri: str) -> str` — strips `classpath:`/`file:` prefixes and anything before `features/`; a bare filename becomes `features/<name>`.
  - `parse_reports(report_dir: Path) -> dict[str, Any]` returning the report JSON contract (`passed`, `skipped`, `failed[]` with `feature, scenario, tags, step, error`). Reads every `*.json` cucumber file in `report_dir` (files whose top level is a JSON array whose items have `elements`); ignores `karate-summary-json.txt` and `*.karate-json.txt`.
  - `render_summary(ledger, defects_text, report, template_text, today) -> str`.
  - CLI: `parse --reports DIR --out PATH` (exit 5 when the dir has no cucumber JSON), `summary --ledger PATH --defects PATH --report PATH --template PATH --out PATH`.

- [ ] **Step 1: Write the failing fixture and tests**

`tests/fixtures/karate-reports-failing/features.post-api-shipments.json` (cucumber JSON shape Karate emits; one passing scenario, one failed outline example tagged `@known-defect`, one plain failure):

```json
[
  {
    "line": 2,
    "elements": [
      {
        "line": 8,
        "name": "creates a shipment",
        "description": "",
        "id": "post-api-shipments;creates-a-shipment",
        "type": "scenario",
        "keyword": "Scenario",
        "steps": [
          {"result": {"duration": 12000000, "status": "passed"}, "line": 9, "name": "url appBaseUrl", "keyword": "Given "},
          {"result": {"duration": 900000, "status": "passed"}, "line": 12, "name": "status 201", "keyword": "Then "}
        ],
        "tags": [{"name": "@smoke", "line": 7}]
      },
      {
        "line": 20,
        "name": "over weight",
        "description": "",
        "id": "post-api-shipments;over-weight",
        "type": "scenario",
        "keyword": "Scenario",
        "steps": [
          {"result": {"duration": 12000000, "status": "passed"}, "line": 21, "name": "url appBaseUrl", "keyword": "Given "},
          {"result": {"duration": 900000, "status": "failed", "error_message": "status code was: 500, expected: 400, response time in milliseconds: 41, url: http://localhost:32771/api/shipments"}, "line": 24, "name": "status 400", "keyword": "Then "},
          {"result": {"duration": 0, "status": "skipped"}, "line": 25, "name": "match response.code == 'WEIGHT'", "keyword": "And "}
        ],
        "tags": [{"name": "@error", "line": 19}, {"name": "@known-defect", "line": 19}]
      },
      {
        "line": 30,
        "name": "validation rule R001 on reference",
        "description": "",
        "id": "post-api-shipments;validation-rule-r001-on-reference",
        "type": "scenario",
        "keyword": "Scenario Outline",
        "steps": [
          {"result": {"duration": 900000, "status": "failed", "error_message": "match failed: EQUALS\n  $ | not equal (STRING:STRING)\n  'VALIDATION'\n  'BAD_REQUEST'"}, "line": 36, "name": "match response.code == 'VALIDATION'", "keyword": "And "}
        ],
        "tags": [{"name": "@rules", "line": 29}]
      }
    ],
    "name": "POST /api/shipments",
    "description": "",
    "id": "post-api-shipments",
    "keyword": "Feature",
    "uri": "classpath:features/post-api-shipments.feature",
    "tags": []
  }
]
```

`tests/test_kb_report.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kb_common import EXIT_MISSING_OUTPUT, KbError
from kb_report import main, normalise_feature, parse_reports, render_summary

FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "karate-tests" / "README.md.tmpl"


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("classpath:features/post-api-shipments.feature", "features/post-api-shipments.feature"),
        ("file:/tmp/kt/src/test/resources/features/x.feature", "features/x.feature"),
        ("src/test/resources/features/sub/y.feature", "features/sub/y.feature"),
        ("harness-smoke.feature", "features/harness-smoke.feature"),
    ],
)
def test_normalise_feature(uri: str, expected: str) -> None:
    assert normalise_feature(uri) == expected


def test_parse_real_smoke_report() -> None:
    report = parse_reports(FIXTURES / "karate-reports")
    assert report["failed"] == []
    assert report["passed"] >= 2
    assert report["skipped"] == 0


def test_parse_failing_report_groups_by_scenario() -> None:
    report = parse_reports(FIXTURES / "karate-reports-failing")
    assert report["passed"] == 1
    assert [f["scenario"] for f in report["failed"]] == ["over weight", "validation rule R001 on reference"]
    over = report["failed"][0]
    assert over["feature"] == "features/post-api-shipments.feature"
    assert over["tags"] == ["@error", "@known-defect"]
    assert over["step"] == "Then status 400"
    assert over["error"].startswith("status code was: 500")
    rule = report["failed"][1]
    assert rule["tags"] == ["@rules"]
    assert rule["step"] == "And match response.code == 'VALIDATION'"


def test_parse_ignores_non_cucumber_files(tmp_path: Path) -> None:
    (tmp_path / "karate-summary-json.txt").write_text("{}", encoding="utf-8")
    (tmp_path / "x.karate-json.txt").write_text("{}", encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        parse_reports(tmp_path)
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT


def test_render_summary_fills_every_placeholder() -> None:
    ledger = {
        "repo": "spring-mini",
        "stack": {"framework": "spring"},
        "app": {"auth": {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false"},
                "migrations": {"strategy": "migration-container", "image": "r/dbm:1"},
                "readiness": {"path": "/actuator/health/readiness", "port": 8080, "source": "deploymentserverless.yml"}},
        "entry_points": [
            {"id": "POST /api/shipments", "kind": "http",
             "exits": [{"kind": "db-write"}, {"kind": "amq-publish"}, {"kind": "http-out"}],
             "rules": {"count": 143}, "observed_overrides": [{"note": "409 returned as 400"}],
             "status": {"passing": True}},
            {"id": "amq shipment.requested", "kind": "amq-subscribe", "exits": [{"kind": "db-write"}],
             "rules": {"count": 0}, "observed_overrides": [], "status": {"passing": False}},
        ],
        "unresolved": [],
    }
    defects = "## DEF-001: amq listener 500\nstatus: pending\nentry_point: amq shipment.requested\n"
    report = {"passed": 150, "skipped": 1, "failed": []}
    text = render_summary(ledger, defects, report, TEMPLATE.read_text(encoding="utf-8"), "2026-09-05")
    assert "$" not in text
    assert "spring-mini" in text and "2026-09-05" in text
    assert "| Entry points | 2 |" in text
    assert "| Validation rules | 143 |" in text
    assert "| Scenarios passing | 150 |" in text
    assert "DEF-001" in text
    assert "409 returned as 400" in text
    assert "disabled (APP_SECURITY_ENABLED=false)" in text


def test_cli_parse_and_summary(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    assert main(["parse", "--reports", str(FIXTURES / "karate-reports-failing"), "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["passed"] == 1 and len(data["failed"]) == 2
    ledger_path = tmp_path / "flow-map.yaml"
    ledger_path.write_text(
        "version: 1\nrepo: r\nstack: {framework: spring}\napp: {auth: {mode: none}, migrations: {strategy: x, image: i}, "
        "readiness: {path: /h, port: 8080, source: s}}\nentry_points: []\nunresolved: []\n",
        encoding="utf-8",
    )
    defects_path = tmp_path / "defects.md"
    defects_path.write_text("# none\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    assert main(["summary", "--ledger", str(ledger_path), "--defects", str(defects_path), "--report", str(out),
                 "--template", str(TEMPLATE), "--out", str(readme)]) == 0
    assert readme.read_text(encoding="utf-8").startswith("# Karate ground-truth suite for r")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_report.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_report'`.

- [ ] **Step 3: Implement**

```python
# skills/karate-bootstrap/scripts/kb_report.py
"""Phase 6/7 of karate-bootstrap: read Karate's cucumber JSON, write the README.

``parse`` turns ``target/karate-reports/*.json`` (Karate's cucumber JSON, one file per
feature named ``<packageQualifiedName>.json``) into the report contract the ledger's
green gate consumes::

    {"passed": int, "skipped": int,
     "failed": [{"feature": "features/x.feature", "scenario": str, "tags": [str],
                 "step": str, "error": str}]}

``summary`` fills ``README.md.tmpl`` from the ledger, defects.md and the parsed report.

Usage:
    python scripts/kb_report.py parse --reports karate-tests/target/karate-reports --out karate-tests/target/report.json
    python scripts/kb_report.py summary --ledger karate-tests/flow-map.yaml --defects karate-tests/defects.md \
        --report karate-tests/target/report.json --template <skill>/templates/karate-tests/README.md.tmpl \
        --out karate-tests/README.md

Exit codes: 0 ok, 5 when the reports directory holds no cucumber JSON.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from string import Template
from typing import Any

from flow_map import load_ledger
from kb_common import EXIT_MISSING_OUTPUT, EXIT_OK, KbError, read_text, require_file, run_cli, write_json

_DEFECT_HEADING_RE = re.compile(r"^## (DEF-\d+:.*)$", re.MULTILINE)


def normalise_feature(uri: str) -> str:
    clean = uri
    for prefix in ("classpath:", "file:"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    clean = clean.replace("\\", "/")
    index = clean.find("features/")
    if index >= 0:
        return clean[index:]
    return "features/" + clean.rsplit("/", 1)[-1]


def _load_cucumber(path: Path) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict) or "elements" not in data[0]:
        return None
    return [d for d in data if isinstance(d, dict)]


def parse_reports(report_dir: Path) -> dict[str, Any]:
    passed = 0
    skipped = 0
    failed: list[dict[str, Any]] = []
    found = False
    for path in sorted(report_dir.glob("*.json")):
        features = _load_cucumber(path)
        if features is None:
            continue
        found = True
        for feature in features:
            feature_path = normalise_feature(str(feature.get("uri", path.stem)))
            for element in feature.get("elements", []):
                if element.get("type") not in (None, "scenario"):
                    continue
                steps = element.get("steps", [])
                statuses = [s.get("result", {}).get("status") for s in steps]
                if "failed" in statuses:
                    first = next(s for s in steps if s.get("result", {}).get("status") == "failed")
                    failed.append({
                        "feature": feature_path,
                        "scenario": str(element.get("name", "")),
                        "tags": [str(t.get("name")) for t in element.get("tags", [])],
                        "step": (str(first.get("keyword", "")) + str(first.get("name", ""))).strip(),
                        "error": str(first.get("result", {}).get("error_message", "")),
                    })
                elif statuses and all(s == "skipped" for s in statuses):
                    skipped += 1
                else:
                    passed += 1
    if not found:
        raise KbError(f"no cucumber JSON under {report_dir}; was the runner built with outputCucumberJson(true)?",
                      EXIT_MISSING_OUTPUT)
    return {"passed": passed, "skipped": skipped, "failed": failed}


def _counts_table(ledger: dict[str, Any], report: dict[str, Any]) -> str:
    entries = ledger.get("entry_points", [])
    exits = [e for entry in entries for e in entry.get("exits", [])]
    kinds = {k: sum(1 for e in exits if e.get("kind") == k) for k in ("db-write", "amq-publish", "http-out")}
    rules = sum(int(entry.get("rules", {}).get("count", 0)) for entry in entries)
    quarantined = sum(1 for entry in entries if not entry.get("status", {}).get("passing", False))
    rows = [
        ("Entry points", len(entries)),
        ("DB write exits", kinds["db-write"]),
        ("AMQ publish exits", kinds["amq-publish"]),
        ("Outbound HTTP exits", kinds["http-out"]),
        ("Validation rules", rules),
        ("Scenarios passing", int(report.get("passed", 0))),
        ("Scenarios failing", len(report.get("failed", []))),
        ("Scenarios skipped", int(report.get("skipped", 0))),
        ("Entry points quarantined", quarantined),
    ]
    return "| Measure | Count |\n|---|---:|\n" + "\n".join(f"| {name} | {value} |" for name, value in rows)


def render_summary(ledger: dict[str, Any], defects_text: str, report: dict[str, Any],
                   template_text: str, today: str) -> str:
    app = ledger.get("app", {})
    auth = app.get("auth", {}) or {}
    mode = str(auth.get("mode", "none"))
    if mode == "disabled":
        auth_text = f"disabled ({auth.get('key')}={auth.get('value')})"
    elif mode == "jwks":
        auth_text = "jwks issuer served from MockServer (" + ", ".join(auth.get("keys", [])) + ")"
    else:
        auth_text = mode
    migrations = app.get("migrations", {}) or {}
    readiness = app.get("readiness", {}) or {}
    defects = _DEFECT_HEADING_RE.findall(defects_text or "")
    overrides = [
        f"- {entry['id']}: {o.get('note', json.dumps(o))}"
        for entry in ledger.get("entry_points", [])
        for o in entry.get("observed_overrides", [])
    ]
    notes = [f"- unresolved hop: {u.get('entry')} at {u.get('at')}: {u.get('reason')}"
             for u in ledger.get("unresolved", [])]
    if readiness.get("source") == "fallback":
        notes.append("- no readiness probe found; the harness waits for the port only")
    return Template(template_text).safe_substitute(
        repo=str(ledger.get("repo")),
        date=today,
        stack=str(ledger.get("stack", {}).get("framework")),
        counts_table=_counts_table(ledger, report),
        auth_mode=auth_text,
        migrations=f"{migrations.get('strategy')} via {migrations.get('image')}",
        readiness=f"{readiness.get('path') or 'port wait'} (from {readiness.get('source')})",
        defects_section="\n".join(f"- {d}" for d in defects) or "None.",
        overrides_section="\n".join(overrides) or "None.",
        notes_section="\n".join(notes) or "None.",
    )


def _cmd_parse(args: argparse.Namespace) -> int:
    report = parse_reports(args.reports)
    write_json(args.out, report)
    print(f"passed {report['passed']}, failed {len(report['failed'])}, skipped {report['skipped']} -> {args.out}")
    return EXIT_OK


def _cmd_summary(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    defects_text = read_text(args.defects) if args.defects.is_file() else ""
    report = json.loads(read_text(require_file(args.report, "report.json")))
    template_text = read_text(require_file(args.template, "README.md.tmpl"))
    text = render_summary(ledger, defects_text, report, template_text, dt.date.today().isoformat())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Karate reports and render the README")
    sub = parser.add_subparsers(dest="command", required=True)
    parse = sub.add_parser("parse", help="cucumber JSON -> report.json")
    parse.add_argument("--reports", type=Path, required=True)
    parse.add_argument("--out", type=Path, required=True)
    parse.set_defaults(func=_cmd_parse)
    summary = sub.add_parser("summary", help="ledger + defects + report -> README.md")
    summary.add_argument("--ledger", type=Path, required=True)
    summary.add_argument("--defects", type=Path, required=True)
    summary.add_argument("--report", type=Path, required=True)
    summary.add_argument("--template", type=Path, required=True)
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

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_report.py -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: pass, clean. If `test_parse_real_smoke_report` fails on `feature` naming, inspect the real fixture's `uri` value and adjust `normalise_feature` (never the fixture).

- [ ] **Step 5: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_report.py skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/fixtures/karate-reports-failing
git commit -m "feat(karate-bootstrap): kb_report parses Karate cucumber JSON and renders the README

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 8: `kb_iterate.py next`, `log`, `check-stop`

**Confidence:** 90%. Pure data over the report JSON, the harness log files and a JSONL iteration log.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_iterate.py`
- Create: `skills/karate-bootstrap/tests/test_kb_iterate.py`

**Interfaces:**
- Produces:
  - `signature(failure: dict) -> str` = `"<feature>|<scenario base>|<step>|<error class>"` where scenario base strips a trailing `validation rule R### on <field>` example suffix to `validation rule * on *`, and error class is the first line of `error` with digits, quoted strings and URLs replaced by `#`.
  - `group_failures(report) -> list[dict]` sorted by group size desc then signature; each `{signature, count, examples: [failure, ...] (max 3), tags}`.
  - `evidence(group, tests_dir: Path) -> dict` with `app_log_tail` (last 80 lines of `target/app.log` if present), `stubs_requests` (`target/stubs-requests.log` if present, truncated to 4000 chars), `db_manager_log_tail` (last 40 lines when the group's error mentions `db-manager` or `Containers.start`), `known_defect_candidate: bool` (error contains `status code was: 5` or `Exception` or `stack trace`).
  - `classify_hint(group) -> str` in `infra | stub-or-seed | expectation | app-defect | unknown` from the error text: `Connection refused|ContainerLaunchException|Containers.start|timed out waiting` → infra; `status code was: 404` with a downstream stub path or `violates foreign key|does not exist|no expectation` → stub-or-seed; `status code was: 5` or `NullPointerException|Exception in` → app-defect; `match failed` or `status code was: 4` → expectation.
  - `log_iteration(log_path, entry: dict) -> None` appends one JSON line `{n, signature, hypothesis, change, classification, at}`.
  - `check_stop(log_path, report, max_iterations) -> str` returning `continue` or `stop:<cap|repeat|infra|green>`: `green` when `report.failed` is empty; `cap` when the log has `>= max_iterations` entries; `repeat` when the last three entries share a signature and that signature is still among the current failure groups (the loop is stuck on the same failure); `infra` when every failure classifies as infra and the log already has an infra entry.
  - CLI: `next --report PATH --tests-dir DIR [--out PATH]` (prints JSON), `log --log PATH --signature S --hypothesis H --change C [--classification K]`, `check-stop --log PATH --report PATH [--max-iterations 15]` (exit 0 on `continue`, exit 6 on any `stop:*`, message printed either way).

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_iterate.py
from __future__ import annotations

import json
from pathlib import Path

from kb_common import EXIT_STOPPED
from kb_iterate import (
    check_stop,
    classify_hint,
    evidence,
    group_failures,
    log_iteration,
    main,
    signature,
)


def _failure(scenario: str, error: str, step: str = "Then status 400", tags: list[str] | None = None) -> dict:
    return {"feature": "features/post-api-shipments.feature", "scenario": scenario,
            "tags": tags or ["@rules"], "step": step, "error": error}


def test_signature_collapses_outline_examples_and_numbers() -> None:
    a = signature(_failure("validation rule R001 on reference",
                           "match failed: EQUALS\n  $ | not equal (STRING:STRING)\n  'VALIDATION'\n  'BAD_REQUEST'"))
    b = signature(_failure("validation rule R017 on weightKg",
                           "match failed: EQUALS\n  $ | not equal (STRING:STRING)\n  'VALIDATION'\n  'BAD_REQUEST'"))
    assert a == b
    assert a.startswith("features/post-api-shipments.feature|validation rule * on *|Then status 400|match failed")
    c = signature(_failure("over weight", "status code was: 500, expected: 400, url: http://localhost:32771/api/x"))
    assert "#" in c and "32771" not in c and "http://" not in c


def test_group_failures_orders_by_size() -> None:
    report = {"passed": 3, "skipped": 0, "failed": [
        _failure("validation rule R001 on a", "match failed: EQUALS\n 'VALIDATION'\n 'BAD_REQUEST'"),
        _failure("validation rule R002 on b", "match failed: EQUALS\n 'VALIDATION'\n 'BAD_REQUEST'"),
        _failure("over weight", "status code was: 500, expected: 400", tags=["@error"]),
    ]}
    groups = group_failures(report)
    assert [g["count"] for g in groups] == [2, 1]
    assert groups[0]["tags"] == ["@rules"] and len(groups[0]["examples"]) == 2
    assert groups[1]["examples"][0]["scenario"] == "over weight"


def test_classify_hint() -> None:
    assert classify_hint({"examples": [_failure("x", "status code was: 500, expected: 400")]}) == "app-defect"
    assert classify_hint({"examples": [_failure("x", "match failed: EQUALS")]}) == "expectation"
    assert classify_hint({"examples": [_failure("x", "status code was: 404, expected: 200, url: http://mockserver:1080/pricing/rates/GB")]}) == "stub-or-seed"
    assert classify_hint({"examples": [_failure("x", "java.net.ConnectException: Connection refused")]}) == "infra"
    assert classify_hint({"examples": [_failure("x", "ERROR: insert or update on table violates foreign key constraint")]}) == "stub-or-seed"
    assert classify_hint({"examples": [_failure("x", "something odd")]}) == "unknown"


def test_evidence_reads_harness_logs(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "app.log").write_text("\n".join(f"line {i}" for i in range(200)) + "\n", encoding="utf-8")
    (target / "stubs-requests.log").write_text("[{\"path\":\"/pricing/rates/GB\"}]", encoding="utf-8")
    (target / "db-manager.log").write_text("migrating\nERROR relation exists\n", encoding="utf-8")
    group = group_failures({"failed": [_failure("x", "status code was: 500, expected: 400")]})[0]
    ev = evidence(group, tmp_path)
    assert ev["app_log_tail"].splitlines()[-1] == "line 199" and len(ev["app_log_tail"].splitlines()) == 80
    assert ev["stubs_requests"].startswith("[{")
    assert ev["db_manager_log_tail"] is None
    assert ev["known_defect_candidate"] is True
    infra = group_failures({"failed": [_failure("x", "db-manager r/x did not exit 0; see target/db-manager.log")]})[0]
    assert evidence(infra, tmp_path)["db_manager_log_tail"].endswith("ERROR relation exists")


def test_log_and_check_stop(tmp_path: Path) -> None:
    log = tmp_path / ".iterations.log"
    failing = {"passed": 1, "skipped": 0, "failed": [_failure("x", "match failed: EQUALS")]}
    assert check_stop(log, failing, 15) == "continue"
    assert check_stop(log, {"passed": 5, "skipped": 0, "failed": []}, 15) == "stop:green"
    sig = signature(failing["failed"][0])
    for n in range(3):
        log_iteration(log, {"n": n + 1, "signature": sig, "hypothesis": "h", "change": "c",
                            "classification": "expectation"})
    assert len(log.read_text(encoding="utf-8").splitlines()) == 3
    assert check_stop(log, failing, 15) == "stop:repeat"
    other = {"passed": 1, "skipped": 0, "failed": [_failure("y", "status code was: 500")]}
    assert check_stop(log, other, 3) == "stop:cap"
    assert check_stop(log, other, 15) == "continue"
    infra = {"passed": 0, "skipped": 0, "failed": [_failure("z", "Connection refused")]}
    assert check_stop(log, infra, 15) == "continue"
    log_iteration(log, {"n": 4, "signature": signature(infra["failed"][0]), "hypothesis": "h", "change": "c",
                        "classification": "infra"})
    assert check_stop(log, infra, 15) == "stop:infra"


def test_cli_next_log_check_stop(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"passed": 0, "skipped": 0, "failed": [
        _failure("over weight", "status code was: 500, expected: 400", tags=["@error"])]}), encoding="utf-8")
    (tmp_path / "target").mkdir()
    assert main(["next", "--report", str(report_path), "--tests-dir", str(tmp_path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["group"]["count"] == 1 and printed["hint"] == "app-defect"
    log = tmp_path / ".iterations.log"
    assert main(["log", "--log", str(log), "--signature", printed["group"]["signature"],
                 "--hypothesis", "app NPE", "--change", "quarantine", "--classification", "app-defect"]) == 0
    assert main(["check-stop", "--log", str(log), "--report", str(report_path), "--max-iterations", "1"]) == EXIT_STOPPED
    assert "stop:cap" in capsys.readouterr().out
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_iterate.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_iterate'`.

- [ ] **Step 3: Implement**

```python
# skills/karate-bootstrap/scripts/kb_iterate.py
"""Phase 6 bookkeeping for karate-bootstrap's fix loop.

``next`` groups the parsed report's failures by signature and hands the model the
largest group with an evidence bundle (app log tail, MockServer request log,
db-manager log when relevant) and a classification hint. ``log`` appends the
model's hypothesis and single change for that iteration to ``.iterations.log``
(JSON lines). ``check-stop`` applies the stop conditions from spec 5.7.

Usage:
    python scripts/kb_iterate.py next --report karate-tests/target/report.json --tests-dir karate-tests [--out PATH]
    python scripts/kb_iterate.py log --log karate-tests/.iterations.log --signature S --hypothesis H --change C [--classification K]
    python scripts/kb_iterate.py check-stop --log karate-tests/.iterations.log --report karate-tests/target/report.json [--max-iterations 15]

Exit codes: 0 continue/ok, 6 when check-stop says stop (reason printed), 5 missing report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

from kb_common import EXIT_OK, EXIT_STOPPED, read_text, require_file, run_cli, write_json

CLASSES = ("infra", "stub-or-seed", "expectation", "app-defect", "unknown")
_OUTLINE_RE = re.compile(r"validation rule \S+ on \S+")
_NUM_RE = re.compile(r"\d+")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_URL_RE = re.compile(r"https?://\S+")
_INFRA_RE = re.compile(r"Connection refused|ContainerLaunchException|Containers\.start|timed out waiting|"
                       r"did not exit 0|db-manager", re.IGNORECASE)
_STUB_SEED_RE = re.compile(r"status code was: 404.*mockserver|violates foreign key|no expectation|"
                           r"relation .* does not exist|no row in", re.IGNORECASE)
_APP_DEFECT_RE = re.compile(r"status code was: 5\d\d|NullReferenceException|NullPointerException|"
                            r"Exception in|stack trace|Traceback", re.IGNORECASE)
_EXPECTATION_RE = re.compile(r"match failed|status code was: 4\d\d", re.IGNORECASE)


def error_class(error: str) -> str:
    first = (error or "").strip().splitlines()[0] if (error or "").strip() else ""
    first = _URL_RE.sub("#", first)
    first = _QUOTED_RE.sub("#", first)
    return _NUM_RE.sub("#", first)[:120]


def signature(failure: dict[str, Any]) -> str:
    scenario = _OUTLINE_RE.sub("validation rule * on *", str(failure.get("scenario", "")))
    return "|".join([str(failure.get("feature", "")), scenario, str(failure.get("step", "")),
                     error_class(str(failure.get("error", "")))])


def group_failures(report: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for failure in report.get("failed", []):
        sig = signature(failure)
        group = groups.setdefault(sig, {"signature": sig, "count": 0, "examples": [], "tags": []})
        group["count"] += 1
        if len(group["examples"]) < 3:
            group["examples"].append(failure)
        for tag in failure.get("tags", []):
            if tag not in group["tags"]:
                group["tags"].append(tag)
    return sorted(groups.values(), key=lambda g: (-int(g["count"]), str(g["signature"])))


def classify_hint(group: dict[str, Any]) -> str:
    text = "\n".join(str(e.get("error", "")) for e in group.get("examples", []))
    if _INFRA_RE.search(text):
        return "infra"
    if _STUB_SEED_RE.search(text):
        return "stub-or-seed"
    if _APP_DEFECT_RE.search(text):
        return "app-defect"
    if _EXPECTATION_RE.search(text):
        return "expectation"
    return "unknown"


def _tail(path: Path, lines: int) -> str | None:
    if not path.is_file():
        return None
    content = read_text(path).splitlines()
    return "\n".join(content[-lines:])


def evidence(group: dict[str, Any], tests_dir: Path) -> dict[str, Any]:
    target = tests_dir / "target"
    text = "\n".join(str(e.get("error", "")) for e in group.get("examples", []))
    stubs = target / "stubs-requests.log"
    return {
        "app_log_tail": _tail(target / "app.log", 80),
        "stubs_requests": read_text(stubs)[:4000] if stubs.is_file() else None,
        "db_manager_log_tail": _tail(target / "db-manager.log", 40)
        if re.search(r"db-manager|Containers\.start", text) else None,
        "known_defect_candidate": bool(_APP_DEFECT_RE.search(text)),
    }


def log_iteration(log_path: Path, entry: dict[str, Any]) -> None:
    record = dict(entry)
    record.setdefault("at", dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.is_file():
        return []
    return [json.loads(line) for line in read_text(log_path).splitlines() if line.strip()]


def check_stop(log_path: Path, report: dict[str, Any], max_iterations: int) -> str:
    if not report.get("failed"):
        return "stop:green"
    entries = _read_log(log_path)
    if len(entries) >= max_iterations:
        return "stop:cap"
    groups = group_failures(report)
    current = {g["signature"] for g in groups}
    recent = {e.get("signature") for e in entries[-3:]}
    if len(entries) >= 3 and len(recent) == 1 and recent <= current:
        return "stop:repeat"
    if groups and all(classify_hint(g) == "infra" for g in groups) and \
            any(e.get("classification") == "infra" for e in entries):
        return "stop:infra"
    return "continue"


def _cmd_next(args: argparse.Namespace) -> int:
    report = json.loads(read_text(require_file(args.report, "report.json")))
    groups = group_failures(report)
    if not groups:
        payload: dict[str, Any] = {"done": True, "passed": report.get("passed", 0)}
    else:
        top = groups[0]
        payload = {"group": top, "hint": classify_hint(top), "evidence": evidence(top, args.tests_dir),
                   "remaining_groups": len(groups) - 1}
    if args.out:
        write_json(args.out, payload)
    print(json.dumps(payload, indent=2))
    return EXIT_OK


def _cmd_log(args: argparse.Namespace) -> int:
    entries = _read_log(args.log)
    log_iteration(args.log, {"n": len(entries) + 1, "signature": args.signature, "hypothesis": args.hypothesis,
                             "change": args.change, "classification": args.classification})
    print(f"iteration {len(entries) + 1} logged -> {args.log}")
    return EXIT_OK


def _cmd_check_stop(args: argparse.Namespace) -> int:
    report = json.loads(read_text(require_file(args.report, "report.json")))
    verdict = check_stop(args.log, report, args.max_iterations)
    print(verdict)
    return EXIT_OK if verdict == "continue" else EXIT_STOPPED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fix-loop bookkeeping over the parsed Karate report")
    sub = parser.add_subparsers(dest="command", required=True)
    nxt = sub.add_parser("next", help="Largest failure group with evidence and a classification hint")
    nxt.add_argument("--report", type=Path, required=True)
    nxt.add_argument("--tests-dir", type=Path, required=True)
    nxt.add_argument("--out", type=Path, default=None)
    nxt.set_defaults(func=_cmd_next)
    log = sub.add_parser("log", help="Append this iteration's hypothesis and change")
    log.add_argument("--log", type=Path, required=True)
    log.add_argument("--signature", required=True)
    log.add_argument("--hypothesis", required=True)
    log.add_argument("--change", required=True)
    log.add_argument("--classification", choices=CLASSES, default="unknown")
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

Note `dt.UTC` (Python 3.11+) is what ruff UP017 wants; `dt.timezone.utc` is rejected.

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_iterate.py -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: pass, clean. Note `stop:green` wins over `stop:cap` in `check_stop` (an empty failed list is checked first); the test sequence relies on that order.

- [ ] **Step 5: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_iterate.py skills/karate-bootstrap/tests/test_kb_iterate.py
git commit -m "feat(karate-bootstrap): kb_iterate groups failures, logs hypotheses and applies stop conditions

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `kb_checkpoint.py`

**Confidence:** 90%. Small git wrapper; tests build throwaway repos with `git init` in `tmp_path` and never touch the real repository.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_checkpoint.py`
- Create: `skills/karate-bootstrap/tests/test_kb_checkpoint.py`

**Interfaces:**
- Produces:
  - `default_branch(repo: Path) -> str` from `git symbolic-ref refs/remotes/origin/HEAD`, else `main` if it exists, else `master`, else the current branch.
  - `current_branch(repo: Path) -> str`.
  - `begin(repo: Path, branch: str = "karate-bootstrap", no_commit: bool = False) -> str`: when `no_commit`, returns the current branch untouched; when the current branch is the default branch, creates (or checks out) `branch`; otherwise stays on the current branch. Returns the branch now checked out.
  - `commit(repo: Path, tests_dir: str, phase: str, message: str, no_commit: bool = False) -> str | None`: stages `tests_dir` (explicit path) plus `.gitignore` if modified, commits `chore(karate-bootstrap): phase <phase> - <message>` with the Co-Authored-By trailer when there is anything staged; returns the short SHA or `None` when nothing changed or `no_commit`.
  - CLI: `begin --repo PATH [--branch karate-bootstrap] [--no-commit]`, `commit --repo PATH --tests-dir karate-tests --phase N --message "..." [--no-commit]`. Never pushes.

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_checkpoint.py
from __future__ import annotations

import subprocess
from pathlib import Path

from kb_checkpoint import begin, commit, current_branch, default_branch, main


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def _init(tmp_path: Path, branch: str = "main") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", branch)
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def test_default_branch_prefers_origin_head_then_main(tmp_path: Path) -> None:
    repo = _init(tmp_path, "trunk")
    assert default_branch(repo) == "trunk"
    _git(repo, "branch", "main")
    assert default_branch(repo) == "main"
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "fetch", "-q", "origin")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert default_branch(repo) == "trunk"


def test_begin_creates_branch_only_from_default(tmp_path: Path) -> None:
    repo = _init(tmp_path)
    assert begin(repo) == "karate-bootstrap"
    assert current_branch(repo) == "karate-bootstrap"
    assert begin(repo) == "karate-bootstrap"  # idempotent
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "ralph/PBI-42")
    assert begin(repo) == "ralph/PBI-42"
    _git(repo, "checkout", "-q", "main")
    assert begin(repo, no_commit=True) == "main"


def test_commit_stages_only_the_tests_dir(tmp_path: Path) -> None:
    repo = _init(tmp_path)
    begin(repo)
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "flow-map.yaml").write_text("version: 1\n", encoding="utf-8")
    (repo / "stray.txt").write_text("not staged\n", encoding="utf-8")
    sha = commit(repo, "karate-tests", "1", "discover complete")
    assert sha is not None and len(sha) >= 7
    subject = _git(repo, "log", "-1", "--format=%s")
    assert subject == "chore(karate-bootstrap): phase 1 - discover complete"
    assert "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" in _git(repo, "log", "-1", "--format=%b")
    assert "stray.txt" in _git(repo, "status", "--short")
    assert commit(repo, "karate-tests", "1", "nothing new") is None
    (repo / "karate-tests" / "x.txt").write_text("x\n", encoding="utf-8")
    assert commit(repo, "karate-tests", "2", "skipped", no_commit=True) is None
    assert "karate-tests/x.txt" in _git(repo, "status", "--short")


def test_cli(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    repo = _init(tmp_path)
    assert main(["begin", "--repo", str(repo)]) == 0
    assert capsys.readouterr().out.strip() == "karate-bootstrap"
    (repo / "karate-tests").mkdir()
    (repo / "karate-tests" / "a").write_text("a\n", encoding="utf-8")
    assert main(["commit", "--repo", str(repo), "--tests-dir", "karate-tests", "--phase", "4",
                 "--message", "scaffold"]) == 0
    assert "phase 4" in _git(repo, "log", "-1", "--format=%s")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_checkpoint.py -q`
Expected: `ModuleNotFoundError: No module named 'kb_checkpoint'`.

- [ ] **Step 3: Implement**

```python
# skills/karate-bootstrap/scripts/kb_checkpoint.py
"""Git checkpoints for karate-bootstrap runs (spec section 9, git behaviour).

``begin`` creates and checks out ``karate-bootstrap`` when the repo sits on its
default branch; on any other branch (a ralph-managed ``ralph/<PBI>`` branch, for
example) it stays put. ``commit`` stages only the karate-tests directory and
commits with a phase-tagged message. Nothing here ever pushes. ``--no-commit``
turns both commands into no-ops so the skill can run without touching git.

Usage:
    python scripts/kb_checkpoint.py begin --repo <repo> [--branch karate-bootstrap] [--no-commit]
    python scripts/kb_checkpoint.py commit --repo <repo> --tests-dir karate-tests --phase 4 --message "scaffold" [--no-commit]

Exit codes: 0 ok, 2 when git reports an error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from kb_common import EXIT_OK, KbError, run_cli

TRAILER = "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise KbError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def _branch_exists(repo: Path, name: str) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"],
                          cwd=repo, capture_output=True, text=True, check=False).returncode == 0


def default_branch(repo: Path) -> str:
    head = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False)
    if head.startswith("refs/remotes/origin/"):
        return head[len("refs/remotes/origin/"):]
    for candidate in ("main", "master"):
        if _branch_exists(repo, candidate):
            return candidate
    return current_branch(repo)


def begin(repo: Path, branch: str = "karate-bootstrap", no_commit: bool = False) -> str:
    current = current_branch(repo)
    if no_commit or current != default_branch(repo):
        return current
    if _branch_exists(repo, branch):
        _git(repo, "checkout", "-q", branch)
    else:
        _git(repo, "checkout", "-q", "-b", branch)
    return branch


def commit(repo: Path, tests_dir: str, phase: str, message: str, no_commit: bool = False) -> str | None:
    if no_commit:
        return None
    _git(repo, "add", "--", tests_dir)
    if (repo / ".gitignore").is_file():
        _git(repo, "add", "--", ".gitignore")
    staged = _git(repo, "diff", "--cached", "--name-only")
    if not staged:
        return None
    body = f"chore(karate-bootstrap): phase {phase} - {message}\n\n{TRAILER}\n"
    _git(repo, "commit", "-q", "-m", body)
    return _git(repo, "rev-parse", "--short", "HEAD")


def _cmd_begin(args: argparse.Namespace) -> int:
    print(begin(args.repo, args.branch, args.no_commit))
    return EXIT_OK


def _cmd_commit(args: argparse.Namespace) -> int:
    sha = commit(args.repo, args.tests_dir, args.phase, args.message, args.no_commit)
    print(sha or "nothing committed")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Branch and commit checkpoints for a karate-bootstrap run")
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("begin", help="Create karate-bootstrap when on the default branch")
    start.add_argument("--repo", type=Path, required=True)
    start.add_argument("--branch", default="karate-bootstrap")
    start.add_argument("--no-commit", action="store_true")
    start.set_defaults(func=_cmd_begin)
    save = sub.add_parser("commit", help="Commit the karate-tests directory at a phase gate")
    save.add_argument("--repo", type=Path, required=True)
    save.add_argument("--tests-dir", default="karate-tests")
    save.add_argument("--phase", required=True)
    save.add_argument("--message", required=True)
    save.add_argument("--no-commit", action="store_true")
    save.set_defaults(func=_cmd_commit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run tests and gates**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_checkpoint.py -q && python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: pass, clean. The tests configure `commit.gpgsign false` in the throwaway repos so a global signing key cannot interfere.

- [ ] **Step 5: Commit**

```bash
git add skills/karate-bootstrap/scripts/kb_checkpoint.py skills/karate-bootstrap/tests/test_kb_checkpoint.py
git commit -m "feat(karate-bootstrap): kb_checkpoint creates the run branch and commits at phase gates

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: CI job for the Maven tests, spec amendments, docs

**Confidence:** 92%.

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md`
- Modify: `skills/karate-bootstrap/scripts/discover.py`, `flow_map.py`, `kb_rules.py` docstrings only if any CLI text changed in this plan (check with `--help` and grep)

- [ ] **Step 1: Add the Maven job to CI**

Append a second job to `.github/workflows/test.yml`:

```yaml
  karate-templates:
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
      - run: KB_MAVEN=1 python -m pytest -m maven -v skills/karate-bootstrap/tests/test_kb_templates.py
```

Keep the existing `test` job unchanged (it still runs `pytest -v`, which skips `maven` by default).

- [ ] **Step 2: Amend the spec**

In `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md`:
- Section 5.5 dependency table: remove the `mockserver-client-java` row; add a sentence under the `Stubs.java` bullet: "MockServer is driven over its REST API (`PUT /mockserver/expectation|reset|verify|retrieve`) with `java.net.http.HttpClient`, so no MockServer client library is needed." Replace "1.20.x" with "1.21.4" and "1.5.x" with "1.5.2" and add "MockServer image `mockserver/mockserver:mockserver-5.15.0`, Postgres `postgres:16-alpine`, Artemis `apache/activemq-artemis:2.44.0-alpine`" to the table.
- Section 5.5: add a paragraph "Repo-specific values live in `src/test/resources/kb-runtime.json` (written by `kb_scaffold.py`; schema v1 in the Plan 2 document) and are read by `KbRuntime.java`. Placeholders `{{db.host}}`, `{{amq.corePort}}`, `{{stubs.url}}`, `{{auth.url}}` and friends are substituted by `Containers.java` with network-alias values."
- Section 5.5 `Containers.java` bullet on env: mention `kb.skipContainers=true` and `kb.threads`.
- Section 5.3 (trace loop) and 5.2: mention `flow_map.py set-auth --mode ... --key ... --value ...` as the command that clears the unconfirmed-switch gap.
- Section 5.7: the commands block becomes `mvn -B test`, `python scripts/kb_report.py parse --reports karate-tests/target/karate-reports --out karate-tests/target/report.json`, `python scripts/kb_iterate.py next --report ... --tests-dir karate-tests`, `python scripts/kb_iterate.py log --log karate-tests/.iterations.log --signature ... --hypothesis "..." --change "..."`, targeted rerun `mvn -B test -Dkarate.options="classpath:features/<one>.feature"`, `python scripts/kb_iterate.py check-stop --log ... --report ... --max-iterations 15`. Replace `report.py`/`iterate.py` with the `kb_` names.
- Section 5.8: `python scripts/kb_report.py summary --ledger ... --defects ... --report ... --template <skill>/templates/karate-tests/README.md.tmpl --out karate-tests/README.md`.
- Section 9: script list becomes `detect.py discover.py flow_map.py kb_rules.py kb_scaffold.py kb_report.py kb_iterate.py kb_checkpoint.py kb_check_skill.py`; git behaviour paragraph names `kb_checkpoint.py begin` / `commit`; templates path `templates/karate-tests/` with the file list from this plan's File Structure.
- Section 10 (local): `testcontainers.properties` sets `ryuk.container.privileged=true`; podman needs `DOCKER_HOST` (rootless socket on Linux: `unix://${XDG_RUNTIME_DIR}/podman/podman.sock`; podman machine on Windows/macOS: the socket path from `podman machine inspect`) and, if Ryuk cannot start, `TESTCONTAINERS_RYUK_DISABLED=true`.

- [ ] **Step 3: Cross-check docstrings against `--help`**

Run every script with `--help` and each subcommand with `--help`; confirm the module docstrings' Usage blocks name the same flags. Fix any drift.

- [ ] **Step 4: Gates**

Run: `python -m ruff check . && python -m mypy && python -m pytest -q`
Expected: clean and green (maven tests skipped by default).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/test.yml docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md skills/karate-bootstrap/scripts
git commit -m "docs(karate-bootstrap): CI job for the template module and spec aligned to the plan 2 harness

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Plan 2 exit criteria

- `ruff check .`, `mypy`, `pytest -q` green at the repo root; `KB_MAVEN=1 pytest -m maven` green on this machine (JDK 21, Maven Central reachable).
- The template module under `skills/karate-bootstrap/templates/karate-tests/` compiles and its container-free smoke feature passes; its cucumber JSON and JUnit XML are committed as fixtures.
- `detect → discover → kb_scaffold --migrations-image r/x:1` on `tests/fixtures/spring-mini` produces a module whose `kb-runtime.json` matches Task 6's expectations, and rerunning is idempotent.
- `kb_report.py parse` on the failing fixture yields two failures with tags intact; `kb_iterate.py next` picks the larger group and hints `app-defect`; `check-stop` returns `stop:cap` at the configured cap.
- `kb_checkpoint.py begin` on a throwaway repo creates `karate-bootstrap` from `main` and leaves `ralph/*` branches alone.
- Whole-branch review probes: run the real Maven build once more from a clean copy, and run the full deterministic pipeline (detect, discover, scaffold, then `kb_report parse` on the fixture reports) on all four fixtures.

Plan 3 (skill assembly) picks up from here: `prompts/trace.md`, `rules.md`, `generate.md`, `fix.md`; `reference/stack-*.md`, `testcontainers-notes.md`, `karate-notes.md`, `failure-triage.md`, `podman.md`; `SKILL.md` with the seven phases as pinned commands; `kb_check_skill.py`; the repo README section; and a dry-run eval through the generated gate on `spring-mini` without containers.

