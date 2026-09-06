# karate-bootstrap Plan 4 of 4: fixture apps and the first live runs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build three runnable fixture services, each with a Flyway db-manager image and one planted defect, and prove the skill's pinned command chain end to end against real containers in CI.

**Architecture:** Three self-contained services live under `skills/karate-bootstrap/tests/fixtures/live/`, one per stack the spec names (Spring Boot, ASP.NET Core, FastAPI). Each carries its own `Dockerfile`, a `db-manager/` Flyway image, a deployment manifest, and a `expected/` directory holding the canned subagent replies and generated test artefacts a run needs, because no test in this repo may call a model. One pytest module drives the same commands `SKILL.md` pins, in order, with real Postgres, Artemis, WireMock and application containers and a real Maven run, then asserts the suite goes green, the planted defect lands in `defects.md`, and the ledger matches the fixture's `expected-flow-map.yaml`. A new `containers` pytest marker keeps that module out of the default suite; a CI job matrix on `ubuntu-latest` runs one fixture per job.

**Tech Stack:** Python 3.11+ (pytest, ruff, mypy), Java 17 on JDK 21 (Karate 1.5.2, Testcontainers 1.21.4), Spring Boot 3.3.2, ASP.NET Core 8.0, FastAPI with SQLAlchemy and python-qpid-proton, Flyway 10 for the db-manager images, Docker on GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` (sections 5.5, 5.7, 5.8, 10, 11 and 12 bind this plan)

## Guardrails carried into this plan

Retrieved before drafting, with their confidence and evidence counts visible.

- **[[confidence-gate]]** (`standards/ralph-runtime.md`, non-skippable): every task carries a confidence percentage and the evidence that earns it; nothing below 90% ships without an embedded mitigation. This plan's mitigation for container behaviour is Task 2, a CI spike whose recorded output the later tasks quote.
- **[[verify-before-commit]]** (`standards/ralph-runtime.md`): every API, flag and constant named below was read in the source at plan-write time. Where a fact could only be checked by running a container, the plan says so and Task 2 checks it.
- **[[docs-in-sync]]** (mem-f3ce58e6, confidence 0.95, evidence 7): a behaviour change drags its documentation with it in the same commit. Task 1 changes `discover.assign_role`, so it also rewrites the sentence in `reference/stack-python.md` that documents the old behaviour.
- **[[verify-red]]** (mem-66b096bf, confidence 0.75): confirm each red is the predicted failure before implementing. Task 1's role change is the risky one: the existing sheet sentence documents the current output, so its test fails for the right reason only after the sentence changes too.
- **[[spec-code-lint]]** (`standards/ralph-runtime.md`): code blocks in this plan are not lint-clean by assumption. Run `ruff check .` and `mypy` before every commit; the plan's Python blocks were written against the repo's `E,F,I,B,UP,SIM` preset and 100-column limit.
- **[[cross-read]]** (`standards/ralph-runtime.md`): prose and example code in this plan must agree. Each fixture's application source, its `expected-flow-map.yaml` and its canned trace reply describe the same exits; a change to one is a change to all three.
- **[[branch-at-start]]** (`standards/ralph-runtime.md`): `feat/karate-bootstrap-plan-4` was created from the merged `main` (b64fa28) before this plan was written.

Dismissed as not applicable, with reasons: ralph-queue ownership (the user executes this plan interactively); Playwright text matching (no browser tests); TypeScript `Partial<T>` (no TypeScript); `tempfile.mkstemp` fd leak (no fd-level temp files in this plan).

## Task confidence summary

| Task | Deliverable | Confidence | Evidence and embedded mitigation |
|------|-------------|-----------:|----------------------------------|
| 1 | Carry-forward fixes from Plan 3's reviews (`discover` db-part roles, startup signature line, union clears `exits_none_reason`, three `SKILL.md` wording gaps, two help strings) | 96% | Every change is a few lines in code this plan read at write time (`discover.py:296-325`, `kb_report.py:73-108`, `flow_map.py:189-300`, `SKILL.md:170-205`), each with a unit test on an existing fixture. No containers involved |
| 2 | CI image spike: one workflow job that proves the Flyway wrapper, the Artemis destination arguments and the `python-qpid-proton` wheel behave as Tasks 3 to 5 assume, and records the output | 92% | This machine has no container runtime, so these are the only facts the plan cannot verify locally. The task is deliberately small and its whole purpose is to turn them into recorded evidence before any fixture depends on them; a red run costs one workflow round-trip and nothing else |
| 3 | `spring-shipments` fixture (app, Dockerfile, db-manager, manifest, canned artefacts) and the live-run harness `test_kb_live_run.py` plus its CI matrix job | 93% | The harness drives the same commands the green dry run already executes (`test_kb_dry_run.py`), with the container-dependent facts pinned by Task 2. The app is a 170-line Spring Boot service whose shape matches the frozen `spring-mini` analysis fixture the discovery regexes already parse |
| 4 | `dotnet-deals` fixture and its canned artefacts | 92% | Reuses Task 3's harness unchanged; the app mirrors the frozen `dotnet-mini` fixture, whose markers `verify-refs` already accepts. The new risk is the .NET AMQP client's behaviour against Artemis, which Task 2 measures |
| 5 | `fastapi-orders` fixture, its canned artefacts, and the `ImageFromDockerfile` path exercised without `--app-image` | 91% | Same harness again. Two new surfaces: the in-container image build (slower, otherwise identical) and `DB_HOST`/`DB_PORT` environment variables, which exist precisely to prove Task 1's role fix against a running database. `python-qpid-proton` install is Task 2's third measurement |
| 6 | Spec section 11 fixture-run criteria marked met, the eval record, README and `SKILL.md` caveat updates | 96% | Documentation over facts the earlier tasks produced; a heading test and the existing `kb_check_skill.py` linter gate it |

All six tasks are at or above 90%. Task 2 is the Step 0 spike that lifts Tasks 3, 4 and 5; without it each of them would sit near 80% on image behaviour alone.

**What this plan cannot verify on this machine.** `docker` and `podman` are both absent here (checked at plan-write time). Every container-touching step is therefore verified in GitHub Actions, and each of Tasks 2 to 5 ends by pushing the branch and reading the job log. Executors should expect CI round-trips to be the test cycle for those tasks, and should not simulate a green run locally.

## Global Constraints

Copied from the spec; every task's requirements include this section.

- Python floor `>=3.11`; ruff `target-version = "py311"` with `E,F,I,B,UP,SIM`, line length 100; mypy `python_version = "3.11"`, strict over `skills/karate-bootstrap/scripts`. Only runtime dependency: `pyyaml>=6.0`.
- Scripts are direct-path invocable (`python skills/karate-bootstrap/scripts/<name>.py`), import siblings flatly (`from kb_common import ...`), and new basenames carry the `kb_` prefix.
- Exit codes (spec section 9, `kb_common.py`): 0 ok, 2 validation failure, 3 unsupported stack, 4 no schema source, 5 missing expected output, 6 stopped by stop condition, 7 container runtime or JDK missing.
- Every script takes the repository root as its positional argument and resolves `--service-dir` itself; never pass a joined path. `<tests>` is `<repo-path>/<sub>/karate-tests`, and `kb_checkpoint.py commit` stages `--tests-dir` relative to the repository root.
- Ledger entry shape (spec section 6): `id, kind, method|destination, path|type, handler, auth, request, responses, reads, exits, rules{file,count,sources}, features, stubs, seeds, observed_overrides, status{traced,stubbed,tested,passing}`. Exit kinds `db-write` (`table`, `op`), `amq-publish` (`destination`, `type`), `http-out` (`host_key`, `method`, `path`); every exit needs `via: file:line`. Read kinds `db-read`, `http-in`.
- Rules CSV header is exactly `rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source`; mutations `missing, null, empty, too_long, too_short, invalid_format, out_of_range, invalid_enum, cross_field`.
- Isolation by data (spec 5.6): suite-level stubs under `stubs/<downstream>/*.json`; a unique id per scenario; `Jms.await` with a match map; `Stubs.verify` by unique path or body; `@parallel=false` for `Stubs.reset`, `Stubs.load`, `Db.truncate` and `reset.feature`'s `stubs:`/`truncate:` arguments; `reset.feature` applies `watch, truncate, seed, stubs` in that order.
- Report JSON contract (spec 5.7): `{"passed", "skipped", "failed": [{"feature", "scenario", "outline", "tags", "step", "error"}]}`; `feature` values are `features/<name>.feature`.
- `defects.md` entries (spec section 7): `## DEF-NNN: <title>` then `status`, `slug`, `severity`, `category`, `entry_point`, `scenario`, `evidence`, `root_cause`, `suggested_fix`.
- Harness images are pinned by the template and must not change here: `postgres:16-alpine`, `apache/activemq-artemis:2.44.0-alpine`, `wiremock/wiremock:3.13.2-alpine`. Network aliases are `db`, `artemis`, `wiremock`, `app`; the AMQP port is 5672 and WireMock listens on 8080.
- The `*-mini` fixtures under `skills/karate-bootstrap/tests/fixtures/` are frozen analysis fixtures: existing tests pin their content and line positions. This plan adds new trees under `tests/fixtures/live/` and never edits a `-mini` file.
- No test in this repo calls a model (spec 11). Every subagent reply a live run needs is a checked-in file under the fixture's `expected/` directory.
- Commits: Conventional Commits, scope `karate-bootstrap`, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Stage by path; never `git add -A`. Never bypass hooks.

## File structure

```
skills/karate-bootstrap/
  scripts/
    discover.py            (modify: db-part env keys take the db role)                    Task 1
    kb_report.py           (modify: a fixed signature line ahead of the startup log tail)  Task 1
    flow_map.py            (modify: --union clears a stale exits_none_reason; help text)   Task 1
  reference/
    stack-python.md        (modify: the DB_HOST sentence follows the code)                 Task 1
  SKILL.md                 (modify: focus ordering, one --focus round per disagreement)    Task 1
  tests/
    test_kb_discover.py    (modify: db-part role rows)                                     Task 1
    test_kb_report.py      (modify: the signature line)                                    Task 1
    test_kb_flow_map.py    (modify: union clears the reason)                               Task 1
    test_kb_reference.py   (modify: the python sheet sentence)                             Task 1
    test_kb_images.py      (create: the container image spike, marker `containers`)        Task 2
    test_kb_live_run.py    (create: the live chain, marker `containers`)                   Task 3
    live_recipes.py        (create: one Recipe per fixture, consumed by the live run)      Task 3
    fixtures/live/
      spring-shipments/    (create: runnable Spring Boot service + db-manager + expected)  Task 3
      dotnet-deals/        (create: runnable ASP.NET Core service + db-manager + expected) Task 4
      fastapi-orders/      (create: runnable FastAPI service + db-manager + expected)      Task 5
  evals/
    live-run-results.md    (create: what each fixture run proved, with dates)              Task 6
.github/workflows/test.yml (modify: the karate-live job matrix)                            Tasks 2, 3, 4, 5
pyproject.toml             (modify: the `containers` marker)                               Task 2
README.md                  (modify: the fixture and live-run section)                      Task 6
docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md (modify: section 11 status)    Task 6
```

Each fixture directory has the same shape, so the harness can treat them uniformly:

```
tests/fixtures/live/<name>/
  Dockerfile                  the application image
  deployment.yml              or deploymentserverless.yml; the manifest discover.py reads
  db-manager/Dockerfile       Flyway image with an entrypoint that builds FLYWAY_URL from PG* vars
  db-manager/sql/V1__init.sql the schema
  <application sources>
  expected/
    expected-flow-map.yaml    the ledger the analysis must produce (spec 11 pass criterion)
    traces/<slug>.json        one canned trace subagent reply per entry point
    rules/<slug>-1.rows.csv   one canned rules subagent reply per validation source
    generated/features/*.feature, generated/stubs/**/*.json, generated/seed/*
                              the canned generate subagent output, copied into <tests>
    defects.md                the defect entry the fix loop must produce for the planted 500
```

---

### Task 1: Carry-forward fixes from Plan 3's reviews

**Confidence:** 96%. Six changes, each a few lines in code this plan read at write time, each with a test on an existing fixture and no container involvement. The one that needs care is the `discover` role change, because `reference/stack-python.md` currently documents the behaviour being changed ([[docs-in-sync]]), and Task 5's fixture will prove the fix against a running database.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/discover.py` (`_DB_PART_KEY`, `assign_role`)
- Modify: `skills/karate-bootstrap/scripts/kb_report.py` (`STARTUP_SIGNATURE`, `startup_failure_report`)
- Modify: `skills/karate-bootstrap/scripts/flow_map.py` (`merge_entry` union branch, two `--repo` help strings)
- Modify: `skills/karate-bootstrap/reference/stack-python.md` (the `db` role bullet)
- Modify: `skills/karate-bootstrap/SKILL.md` (Step 3 ordering sentence, the disagreement bound)
- Test: `skills/karate-bootstrap/tests/test_kb_discover.py`, `tests/test_kb_report.py`, `tests/test_kb_flow_map.py`, `tests/test_kb_reference.py`

**Interfaces:**
- Consumes: `discover.assign_role(key, placeholder) -> str`; `kb_report.startup_failure_report(target_dir) -> dict`; `flow_map.merge_entry(ledger, traced, union=False) -> int` (all landed in Plans 1 to 3).
- Produces for Tasks 3 to 5: `assign_role` returns `db` for `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` and `DB_PASSWORD`, which `kb_scaffold.env_value` already turns into `{{db.host}}`, `{{db.port}}`, `{{db.name}}`, `{{db.user}}` and `{{db.password}}` through its existing `_DB_PART_TOKENS` table; `kb_report.STARTUP_SIGNATURE = "startup: no karate reports"` as the first line of every synthetic startup failure.

- [ ] **Step 1: Add the failing role rows to `tests/test_kb_discover.py`**

Find the parametrised role test (it exercises `assign_role` with `(key, placeholder, expected)` rows) and append these rows to its parameter list:

```python
    ("DB_HOST", "", "db"),
    ("DB_PORT", "", "db"),
    ("DB_NAME", "", "db"),
    ("DB_USER", "", "db"),
    ("DB_PASSWORD", "", "db"),
    ("PGPORT", "", "db"),
    ("INVENTORY_HOST", "", "downstream:inventory"),
```

The last row is the guard that the change does not swallow every `*_HOST` key: only the `db`-prefixed ones move.

- [ ] **Step 2: Add the startup-signature test to `tests/test_kb_report.py`**

```python
def test_startup_failure_error_starts_with_a_stable_signature(tmp_path: Path) -> None:
    target = tmp_path / "target"
    (target / "karate-reports").mkdir(parents=True)
    (target / "app.log").write_text("boot line one\nCaused by: connection refused\n",
                                    encoding="utf-8")
    report = parse_reports(target / "karate-reports", None)
    error = report["failed"][0]["error"]
    assert error.splitlines()[0] == STARTUP_SIGNATURE
    assert "connection refused" in error
    (target / "app.log").write_text("boot line one\na different tail\n", encoding="utf-8")
    second = parse_reports(target / "karate-reports", None)
    assert second["failed"][0]["error"].splitlines()[0] == STARTUP_SIGNATURE
```

Add `STARTUP_SIGNATURE` to the `from kb_report import (...)` list in that module (imports stay alphabetical).

- [ ] **Step 3: Add the union test to `tests/test_kb_flow_map.py`**

```python
def test_union_clears_a_stale_exits_none_reason(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    read_only = {"id": "GET /api/shipments/{id}", "exits": [],
                 "exits_none_reason": "read-only lookup", "responses": [{"status": 200}]}
    merge_entry(ledger, read_only)
    entry = find_entry(ledger, "GET /api/shipments/{id}")
    assert entry["exits_none_reason"] == "read-only lookup"
    second = {"id": "GET /api/shipments/{id}",
              "exits": [{"kind": "db-read-through-cache", "table": "shipments", "op": "update",
                         "via": f"{SERVICE}:52"}]}
    second["exits"][0]["kind"] = "db-write"
    merge_entry(ledger, second, union=True)
    assert entry["exits"], "the union added the exit the second trace found"
    assert not entry.get("exits_none_reason"), "an entry with exits cannot also claim it has none"
```

- [ ] **Step 4: Add the python-sheet sentence test to `tests/test_kb_reference.py`**

```python
def test_python_sheet_documents_db_part_keys_as_db_role() -> None:
    text = (REFERENCE / "stack-python.md").read_text(encoding="utf-8")
    assert "`DB_HOST`/`DB_PORT` pair" in text
    assert "downstream:db" not in text, "the sheet still documents the old misclassification"
```

- [ ] **Step 5: Run the four test files and confirm the predicted failures**

Run: `pytest skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/test_kb_flow_map.py skills/karate-bootstrap/tests/test_kb_reference.py -q`

Expected ([[verify-red]]): the five `DB_*` rows fail with `downstream:db` or `passthrough` instead of `db`; `PGPORT` fails with `passthrough`; `test_kb_report.py` fails at collection with `ImportError` on `STARTUP_SIGNATURE`; the union test fails on the second assertion (the reason survives); the reference test fails on `downstream:db` still being present. `INVENTORY_HOST` passes already — it is a guard, not a red.

- [ ] **Step 6: Make db-part keys take the db role in `scripts/discover.py`**

Add beside `_DB_KEY`:

```python
# Individual connection parts. ``assign_role`` must claim these before the URL-suffix rule,
# or ``DB_HOST`` reads as a downstream service and the scaffold points the app at WireMock.
_DB_PART_KEY = ("db_host", "db-host", "db_port", "db-port", "db_name", "db-name",
                "db_user", "db-user", "db_password", "db-password",
                "pgport", "pguser", "pgpassword")
```

and widen the db test in `assign_role`:

```python
    if any(s in v for s in _DB_VAL) or any(s in k for s in _DB_KEY + _DB_PART_KEY):
        return "db"
```

- [ ] **Step 7: Give the synthetic startup failure a stable first line in `scripts/kb_report.py`**

Add beside `NO_REPORTS_ERROR`:

```python
# The first line of every synthetic startup failure. ``kb_iterate.error_class`` keys on the
# first non-empty line, so a drifting log tail must not change the signature between runs.
STARTUP_SIGNATURE = "startup: no karate reports"
```

and build the error from it in `startup_failure_report`:

```python
            "error": f"{STARTUP_SIGNATURE}\n{startup_log_tail(target_dir)}",
```

- [ ] **Step 8: Clear a stale `exits_none_reason` in the union branch of `scripts/flow_map.py`**

Inside `merge_entry`, at the end of the `if union:` block:

```python
        if entry["exits"]:
            entry.pop("exits_none_reason", None)
```

- [ ] **Step 9: Correct the two `--repo` help strings in `scripts/flow_map.py`**

`validate` and `verify-refs` both take the repository root and resolve `--service-dir` themselves. In `build_parser`, change the `validate` parser's `--repo` help from `"service root"` to `"repository root"`, and give `verify-refs` the same help text on its `--repo` argument:

```python
    refs.add_argument("--repo", type=Path, required=True, help="repository root")
```

- [ ] **Step 10: Rewrite the `db` bullet in `reference/stack-python.md`**

Replace the sentence that says a bare `DB_HOST`/`DB_PORT` pair is classified `downstream:db` with:

```markdown
  covers `DATABASE_URL`, `PGHOST`, `PGDATABASE`, and the individual `DB_HOST`/`DB_PORT`/
  `DB_NAME`/`DB_USER`/`DB_PASSWORD` parts; the scaffold turns a part key into the single
  token it names (`{{db.host}}`, `{{db.port}}`, `{{db.name}}`, `{{db.user}}`,
  `{{db.password}}`) and a URL key into the full `postgresql://` template.
```

Keep every heading and marker token in the file: `tests/test_kb_reference.py` pins them.

- [ ] **Step 11: Close the two `SKILL.md` gaps**

In Step 3, the `unresolved` bullet and the `incomplete:` bullet can both apply to one reply. Add this sentence to the end of the `incomplete:` bullet:

```markdown
  When a reply is both unresolved and incomplete, follow the unresolved bullet first: its
  `--focus` location is the specific line the tracer stopped at, and a re-trace from there
  usually resolves both.
```

In the `--double-trace` paragraph, bound the disagreement loop. Add to the end of the sentence that tells the agent to re-trace every `disagreement:` line:

```markdown
  One `--focus` round per disagreement is the cap: merge each result with `--union`, then run
  the gate. A `via` still seen by only one trace after that round is a disagreement the gate's
  `verify-refs` check adjudicates, not grounds for a third trace.
```

- [ ] **Step 12: Run the four test files and confirm they pass**

Run: `pytest skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/test_kb_flow_map.py skills/karate-bootstrap/tests/test_kb_reference.py -q`
Expected: PASS.

- [ ] **Step 13: Full gate**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_check_skill.py`
Expected: green, the linter prints ok. If `test_kb_scaffold.py` or `test_kb_dry_run.py` fails on an env value that moved from `downstream:db` to `db`, that is the fix working: update the expectation to the `{{db.*}}` token the scaffold now writes and say so in your report.

- [ ] **Step 14: Commit**

```bash
git add skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/scripts/kb_report.py skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/reference/stack-python.md skills/karate-bootstrap/SKILL.md skills/karate-bootstrap/tests/test_kb_discover.py skills/karate-bootstrap/tests/test_kb_report.py skills/karate-bootstrap/tests/test_kb_flow_map.py skills/karate-bootstrap/tests/test_kb_reference.py
git commit -m "fix(karate-bootstrap): db-part env keys, startup signature, union reason, procedure gaps

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: CI image spike

**Confidence:** 92%. This machine has no `docker` and no `podman` (checked at plan-write time), so three facts Tasks 3 to 5 depend on cannot be established locally: that a Flyway image driven by `PG*` environment variables migrates a database, that Artemis creates the destinations `Containers.artemisExtraArgs` names, and that `python-qpid-proton` installs from a wheel on `python:3.12-slim` without build tools. This task turns each into recorded evidence with a single workflow run. It is small on purpose: it adds one test module, one pytest marker and one CI job, and nothing else depends on it until Task 3.

**Files:**
- Create: `skills/karate-bootstrap/tests/test_kb_images.py`
- Create: `skills/karate-bootstrap/evals/live-run-results.md`
- Modify: `pyproject.toml` (the `containers` marker and `addopts`)
- Modify: `.github/workflows/test.yml` (the `karate-live` job)

**Interfaces:**
- Produces for Tasks 3 to 5: the `containers` pytest marker, opted into with `KB_CONTAINERS=1`; the `karate-live` CI job that runs `pytest -m containers`; helper `docker(*args, check=True, timeout=600) -> subprocess.CompletedProcess[str]` in `test_kb_images.py`, re-exported for the live-run module by import.
- Consumes: nothing from earlier tasks.

- [ ] **Step 1: Add the `containers` marker to `pyproject.toml`**

In `[tool.pytest.ini_options]`, add the marker and exclude it by default:

```toml
markers = [
  "live: hits a real LLM (off by default)",
  "maven: compiles and smoke-runs the Karate template with Maven (needs JDK 17+; opt in with KB_MAVEN=1)",
  "containers: starts real containers (needs Docker or Podman; opt in with KB_CONTAINERS=1)",
]
addopts = "-m 'not live and not maven and not containers'"
```

- [ ] **Step 2: Write `tests/test_kb_images.py`**

```python
"""Container-image facts the live fixtures depend on, measured rather than assumed.

This machine had no container runtime when Plan 4 was written, so three assumptions could
not be checked locally: a Flyway image driven by ``PG*`` variables migrates a database, an
Artemis container creates the destinations ``Containers.artemisExtraArgs`` names, and
``python-qpid-proton`` installs from a wheel on ``python:3.12-slim``. Each is a test here.

Opt in with ``KB_CONTAINERS=1``; CI runs it in the ``karate-live`` job.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.containers,
    pytest.mark.skipif(os.environ.get("KB_CONTAINERS") != "1",
                       reason="set KB_CONTAINERS=1 to run containers"),
]

ARTEMIS_IMAGE = "apache/activemq-artemis:2.44.0-alpine"
POSTGRES_IMAGE = "postgres:16-alpine"
PYTHON_IMAGE = "python:3.12-slim"
QPID_PROTON = "python-qpid-proton==0.39.0"


def docker(*args: str, check: bool = True,
           timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Run the docker CLI, capturing output. Raises on a non-zero exit when ``check``."""
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"docker {' '.join(args)} exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


@pytest.fixture()
def network() -> str:
    name = f"kb-spike-{uuid.uuid4().hex[:8]}"
    docker("network", "create", name)
    try:
        yield name
    finally:
        docker("network", "rm", name, check=False)


def _run_detached(image: str, name: str, network_name: str, *extra: str) -> None:
    docker("run", "-d", "--rm", "--name", name, "--network", network_name,
           "--network-alias", name, *extra, image)


def _stop(name: str) -> None:
    docker("rm", "-f", name, check=False)


def test_flyway_wrapper_migrates_from_pg_environment(tmp_path: Path, network: str) -> None:
    """The db-manager shape every fixture uses: PG* in, a migrated schema out."""
    build = tmp_path / "db-manager"
    (build / "sql").mkdir(parents=True)
    (build / "sql" / "V1__init.sql").write_text(
        "CREATE TABLE spike (id integer primary key);\n", encoding="utf-8")
    (build / "entrypoint.sh").write_text(
        "#!/bin/sh\nset -eu\n"
        'exec flyway -url="jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}" '
        '-user="${PGUSER}" -password="${PGPASSWORD}" -locations=filesystem:/flyway/sql '
        "-connectRetries=20 migrate\n",
        encoding="utf-8", newline="\n")
    (build / "Dockerfile").write_text(
        "FROM flyway/flyway:10.17.3-alpine\n"
        "COPY sql /flyway/sql\n"
        "COPY entrypoint.sh /entrypoint.sh\n"
        "USER root\n"
        "RUN chmod +x /entrypoint.sh\n"
        "USER flyway\n"
        'ENTRYPOINT ["/entrypoint.sh"]\n',
        encoding="utf-8", newline="\n")
    tag = f"kb-spike-dbm-{uuid.uuid4().hex[:8]}"
    docker("build", "-t", tag, str(build))
    db = f"kb-spike-db-{uuid.uuid4().hex[:8]}"
    try:
        _run_detached(POSTGRES_IMAGE, db, network,
                      "-e", "POSTGRES_DB=spike", "-e", "POSTGRES_USER=app",
                      "-e", "POSTGRES_PASSWORD=app")
        docker("run", "--rm", "--network", network,
               "-e", f"PGHOST={db}", "-e", "PGPORT=5432", "-e", "PGDATABASE=spike",
               "-e", "PGUSER=app", "-e", "PGPASSWORD=app", tag)
        check = docker("exec", db, "psql", "-U", "app", "-d", "spike", "-tAc",
                       "select count(*) from spike")
        assert check.stdout.strip() == "0", check.stdout
    finally:
        _stop(db)
        docker("image", "rm", "-f", tag, check=False)


def test_artemis_creates_the_destinations_the_harness_asks_for(network: str) -> None:
    """``artemisExtraArgs`` builds ``--queues a,b --addresses c``; both must exist."""
    name = f"kb-spike-mq-{uuid.uuid4().hex[:8]}"
    extra_args = ("--http-host 0.0.0.0 --relax-jolokia "
                  "--queues spike.requested --addresses spike.created")
    try:
        _run_detached(ARTEMIS_IMAGE, name, network,
                      "-e", "ARTEMIS_USER=artemis", "-e", "ARTEMIS_PASSWORD=artemis",
                      "-e", "ANONYMOUS_LOGIN=false", "-e", f"EXTRA_ARGS={extra_args}")
        deadline = 180
        wait = (f"for i in $(seq 1 {deadline}); do "
                "grep -q AMQ221007 /var/lib/artemis-instance/log/artemis.log && exit 0; "
                "sleep 1; done; exit 1")
        proc = docker("exec", name, "sh", "-c", wait, check=False, timeout=deadline + 60)
        assert proc.returncode == 0, "artemis never logged AMQ221007 (the harness waits on it)"
        queues = docker("exec", name, "/var/lib/artemis-instance/bin/artemis", "queue", "stat",
                        "--user", "artemis", "--password", "artemis")
        assert "spike.requested" in queues.stdout, queues.stdout
        addresses = docker("exec", name, "/var/lib/artemis-instance/bin/artemis", "address",
                           "show", "--user", "artemis", "--password", "artemis")
        assert "spike.created" in addresses.stdout, addresses.stdout
    finally:
        _stop(name)


def test_qpid_proton_installs_from_a_wheel_on_slim_python() -> None:
    """``fastapi-orders`` consumes AMQP 1.0 with proton; a source build would need cmake."""
    proc = docker("run", "--rm", PYTHON_IMAGE, "pip", "install", "--only-binary", ":all:",
                  "--no-cache-dir", QPID_PROTON, check=False, timeout=600)
    assert proc.returncode == 0, (
        f"{QPID_PROTON} has no usable wheel on {PYTHON_IMAGE}; Task 5 must add build "
        f"dependencies to the fixture image instead.\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    )
```

- [ ] **Step 3: Add the `karate-live` job to `.github/workflows/test.yml`**

Append this job after `karate-templates`:

```yaml
  karate-live:
    name: Live containers
    runs-on: ubuntu-latest
    timeout-minutes: 45
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
      - run: docker version
      - run: KB_CONTAINERS=1 pytest -m containers -v
```

- [ ] **Step 4: Run the default suite locally and confirm the spike is excluded**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green, and the run reports the three new tests as deselected (they carry the `containers` marker). Do not try to run them here: this machine has no container runtime, and `KB_CONTAINERS=1 pytest -m containers` would fail on a missing `docker` executable rather than on anything real.

- [ ] **Step 5: Commit and push, then read the CI job**

```bash
git add pyproject.toml .github/workflows/test.yml skills/karate-bootstrap/tests/test_kb_images.py
git commit -m "test(karate-bootstrap): measure the container images the live fixtures need

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feat/karate-bootstrap-plan-4
```

Then watch the `Live containers` job. This is the task's real test cycle: it runs where Docker exists.

- [ ] **Step 6: Record what the run measured in `skills/karate-bootstrap/evals/live-run-results.md`**

Write the file with the run's actual output, not the expected output:

```markdown
# Live run results

Run: `KB_CONTAINERS=1 pytest -m containers -v` in the `karate-live` job of
`.github/workflows/test.yml`. Recorded from workflow run <URL>, <date>.

| Assumption | Result | Evidence |
|---|---|---|
| A Flyway image with an entrypoint that builds `FLYWAY_URL` from `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` migrates a database and exits 0 | <pass or fail> | <the test's assertion or the failure text> |
| `EXTRA_ARGS=--http-host 0.0.0.0 --relax-jolokia --queues <q> --addresses <t>` creates both destinations and logs `AMQ221007` | <pass or fail> | <`artemis queue stat` and `artemis address show` output, trimmed> |
| `pip install --only-binary :all: python-qpid-proton==0.39.0` succeeds on `python:3.12-slim` | <pass or fail> | <pip's resolution line> |

Times observed: Flyway image build <n>s, Artemis to `AMQ221007` <n>s, proton install <n>s.

Consequences for the fixtures: <one line per row, saying what Tasks 3 to 5 may now assume,
or what they must do differently>.
```

If any row failed, fix the fixture design here, not later: a failed Flyway row means the
db-manager needs a different base image, a failed Artemis row means the destination arguments
need adjusting in the spike (never in `Containers.java`, which Plan 2 pinned), and a failed
proton row means Task 5's image installs `gcc`, `cmake` and `libssl-dev` before pip. Re-run the
job until the file records three passes.

- [ ] **Step 7: Commit the record**

```bash
git add skills/karate-bootstrap/evals/live-run-results.md
git commit -m "docs(karate-bootstrap): record what the image spike measured

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `spring-shipments` fixture and the live-run harness

**Confidence:** 93%. The harness executes the same commands `test_kb_dry_run.py` already runs green, with three additions: a real `docker build`, a real `mvn test`, and a fix-loop round. The container facts it relies on are Task 2's recorded output. The application is a 170-line Spring Boot service whose class and method shapes copy the frozen `spring-mini` analysis fixture, so `discover.py`'s entry-point regexes and `markers.py`'s `verify-refs` tokens already match it.

**Files:**
- Create: `skills/karate-bootstrap/tests/fixtures/live/spring-shipments/` (application, `Dockerfile`, `deploymentserverless.yml`, `db-manager/`, `expected/`)
- Create: `skills/karate-bootstrap/tests/live_recipes.py`
- Create: `skills/karate-bootstrap/tests/test_kb_live_run.py`
- Modify: `.github/workflows/test.yml` (the `karate-live` job gains a fixture matrix)

**Interfaces:**
- Consumes: `docker` from `tests/test_kb_images.py`; every script CLI as `SKILL.md` pins it; `kb_helpers.line_of` (Plan 1) for content-located `via` lines.
- Produces for Tasks 4 and 5: `live_recipes.Recipe` with fields `name, fixture, stack, service_dir, app_port, entries, rules_sources, migrations_db, planted_defect, app_image` and `RECIPES: dict[str, Recipe]`; the parametrised test `test_live_chain_goes_green[<name>]` that a new recipe joins by adding one dictionary entry and one fixture directory.

- [ ] **Step 1: Write the application sources**

`tests/fixtures/live/spring-shipments/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>shipments</artifactId>
  <version>1.0.0</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.2</version>
    <relativePath/>
  </parent>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>org.springframework</groupId><artifactId>spring-jms</artifactId></dependency>
    <dependency><groupId>org.apache.qpid</groupId><artifactId>qpid-jms-client</artifactId><version>1.17.0</version></dependency>
    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>
  </dependencies>
  <build>
    <finalName>shipments</finalName>
    <plugins>
      <plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId></plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/com/acme/shipments/ShipmentsApplication.java`:

```java
package com.acme.shipments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.web.client.RestTemplate;

@SpringBootApplication
@EnableJms
public class ShipmentsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShipmentsApplication.class, args);
    }

    @Bean
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

`src/main/java/com/acme/shipments/JmsConfig.java`:

```java
package com.acme.shipments;

import jakarta.jms.ConnectionFactory;
import org.apache.qpid.jms.JmsConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.core.JmsTemplate;

/** AMQP 1.0 over Qpid JMS, the protocol the real services speak (design spec 11). */
@Configuration
public class JmsConfig {
    @Bean
    ConnectionFactory connectionFactory(@Value("${amq.url}") String url,
                                        @Value("${amq.user}") String user,
                                        @Value("${amq.password}") String password) {
        JmsConnectionFactory factory = new JmsConnectionFactory(url);
        factory.setUsername(user);
        factory.setPassword(password);
        return factory;
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        return new JmsTemplate(connectionFactory);
    }
}
```

`src/main/java/com/acme/shipments/Shipment.java`:

```java
package com.acme.shipments;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "shipments")
public class Shipment {
    @Id
    @GeneratedValue
    private UUID id;
    @Column(name = "reference", nullable = false, unique = true)
    private String reference;
    @Column(name = "country_code", nullable = false)
    private String countryCode;
    @Column(name = "weight_kg", nullable = false)
    private double weightKg;
    @Column(name = "destination", nullable = false)
    private String destination;
    @Column(name = "status", nullable = false)
    private String status;
    @Column(name = "rate", nullable = false)
    private double rate;

    public UUID getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }

    public double getWeightKg() {
        return weightKg;
    }

    public void setWeightKg(double weightKg) {
        this.weightKg = weightKg;
    }

    public String getDestination() {
        return destination;
    }

    public void setDestination(String destination) {
        this.destination = destination;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public double getRate() {
        return rate;
    }

    public void setRate(double rate) {
        this.rate = rate;
    }
}
```

`src/main/java/com/acme/shipments/ShipmentRepository.java`:

```java
package com.acme.shipments;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ShipmentRepository extends JpaRepository<Shipment, UUID> {
    Optional<Shipment> findByReference(String reference);
}
```

`src/main/java/com/acme/shipments/ShipmentRequest.java`:

```java
package com.acme.shipments;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public class ShipmentRequest {
    @NotBlank(message = "reference is required")
    @Size(max = 50, message = "reference must be at most 50")
    private String reference;
    @Positive(message = "weight must be positive")
    private double weightKg;
    @NotBlank(message = "countryCode is required")
    @Pattern(regexp = "[A-Z]{2}", message = "countryCode must match [A-Z]{2}")
    private String countryCode;
    @NotBlank(message = "destination is required")
    @Size(min = 3, max = 120, message = "destination must be 3 to 120 characters")
    private String destination;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }

    public double getWeightKg() {
        return weightKg;
    }

    public void setWeightKg(double weightKg) {
        this.weightKg = weightKg;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public void setCountryCode(String countryCode) {
        this.countryCode = countryCode;
    }

    public String getDestination() {
        return destination;
    }

    public void setDestination(String destination) {
        this.destination = destination;
    }
}
```

`src/main/java/com/acme/shipments/ShipmentController.java`:

```java
package com.acme.shipments;

import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {
    private final ShipmentService service;

    public ShipmentController(ShipmentService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Shipment> create(@Valid @RequestBody ShipmentRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(service.create(request));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Shipment> get(@PathVariable UUID id) {
        return service.find(id).map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

`src/main/java/com/acme/shipments/ShipmentService.java` — the planted defect is the
`IllegalArgumentException` on line 44: a weight over 1000 kg is a business rule the service
enforces after validation, and nothing maps it, so the application answers 500 where a
reader would expect 400. The suite must document the 500, not fix it.

```java
package com.acme.shipments;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class ShipmentService {
    private final ShipmentRepository repository;
    private final RestTemplate restTemplate;
    private final JmsTemplate jmsTemplate;
    private final String pricingBaseUrl;

    public ShipmentService(ShipmentRepository repository, RestTemplate restTemplate,
                           JmsTemplate jmsTemplate,
                           @Value("${pricing.base-url}") String pricingBaseUrl) {
        this.repository = repository;
        this.restTemplate = restTemplate;
        this.jmsTemplate = jmsTemplate;
        this.pricingBaseUrl = pricingBaseUrl;
    }

    public Optional<Shipment> find(UUID id) {
        return repository.findById(id);
    }

    @SuppressWarnings("unchecked")
    public Shipment create(ShipmentRequest request) {
        if (request.getWeightKg() > 1000) {
            throw new IllegalArgumentException("weight exceeds 1000kg");
        }
        Map<String, Object> rate = restTemplate.getForObject(
            pricingBaseUrl + "/rates/" + request.getCountryCode(), Map.class);
        Shipment shipment = new Shipment();
        shipment.setReference(request.getReference());
        shipment.setCountryCode(request.getCountryCode());
        shipment.setWeightKg(request.getWeightKg());
        shipment.setDestination(request.getDestination());
        shipment.setStatus("PENDING");
        shipment.setRate(rate == null ? 0d : ((Number) rate.getOrDefault("rate", 0)).doubleValue());
        Shipment saved = repository.save(shipment);
        jmsTemplate.convertAndSend("shipment.created", Map.of(
            "id", saved.getId().toString(), "reference", saved.getReference(),
            "status", saved.getStatus()));
        return saved;
    }
}
```

`src/main/java/com/acme/shipments/ShipmentEventsListener.java`:

```java
package com.acme.shipments;

import java.util.Map;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShipmentEventsListener {
    private final ShipmentRepository repository;

    public ShipmentEventsListener(ShipmentRepository repository) {
        this.repository = repository;
    }

    @JmsListener(destination = "shipment.requested")
    public void onRequested(Map<String, Object> message) {
        Shipment shipment = new Shipment();
        shipment.setReference(String.valueOf(message.get("reference")));
        shipment.setCountryCode(String.valueOf(message.getOrDefault("countryCode", "GB")));
        shipment.setWeightKg(Double.parseDouble(String.valueOf(
            message.getOrDefault("weightKg", "1"))));
        shipment.setDestination(String.valueOf(message.getOrDefault("destination", "queued")));
        shipment.setStatus("QUEUED");
        shipment.setRate(0d);
        repository.save(shipment);
    }
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: shipments
  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/shipments}
    username: ${SPRING_DATASOURCE_USERNAME:app}
    password: ${SPRING_DATASOURCE_PASSWORD:app}
  jpa:
    hibernate:
      ddl-auto: none
    open-in-view: false
amq:
  url: ${AMQ_URL:amqp://localhost:5672}
  user: ${AMQ_USER:artemis}
  password: ${AMQ_PASSWORD:artemis}
pricing:
  base-url: ${PRICING_BASE_URL:http://localhost:9090}
app:
  security:
    enabled: ${APP_SECURITY_ENABLED:true}
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
```

- [ ] **Step 2: Write the manifest, Dockerfile and db-manager**

`deploymentserverless.yml`:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: shipments
spec:
  template:
    spec:
      containers:
        - name: shipments
          image: registry.example/shipments:latest
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
          env:
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: shipments-db
                  key: url
            - name: SPRING_DATASOURCE_USERNAME
              value: app
            - name: SPRING_DATASOURCE_PASSWORD
              value: app
            - name: AMQ_URL
              value: amqp://artemis:5672
            - name: AMQ_USER
              value: artemis
            - name: AMQ_PASSWORD
              value: artemis
            - name: PRICING_BASE_URL
              value: http://pricing:8080
            - name: APP_SECURITY_ENABLED
              value: "true"
```

`Dockerfile` — multi-stage so `docker build` needs nothing but Docker, and so the
`ImageFromDockerfile` path Task 5 exercises would work here too:

```dockerfile
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/shipments.jar app.jar
ENV JAVA_OPTS="-Xmx512m"
EXPOSE 8080
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

`db-manager/sql/V1__init.sql`:

```sql
CREATE TABLE shipments (
    id uuid PRIMARY KEY,
    reference varchar(50) NOT NULL UNIQUE,
    country_code varchar(2) NOT NULL,
    weight_kg double precision NOT NULL,
    destination varchar(120) NOT NULL,
    status varchar(20) NOT NULL,
    rate double precision NOT NULL DEFAULT 0
);
```

`db-manager/entrypoint.sh` and `db-manager/Dockerfile` — the exact shape Task 2 measured;
copy them from `tests/test_kb_images.py`'s `test_flyway_wrapper_migrates_from_pg_environment`,
changing only the `sql` contents. Write both with LF endings, and keep the `chmod +x` line:
a file copied from a Windows checkout is not executable in the image without it.

- [ ] **Step 3: Write `tests/live_recipes.py`**

```python
"""One recipe per live fixture: what the chain runs and what the run must produce.

The live-run harness (``test_kb_live_run.py``) is fixture-agnostic; everything specific to a
service lives here and under ``tests/fixtures/live/<fixture>/expected/``.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "live"


class Recipe(NamedTuple):
    """A live fixture and the facts the harness needs to drive it."""

    name: str
    fixture: Path
    stack: str
    app_port: int
    auth_key: str
    auth_off_value: str
    entries: tuple[str, ...]
    rules_sources: tuple[tuple[str, str], ...]
    marks: dict[str, tuple[tuple[str, str], ...]]
    planted_scenario: str
    planted_feature: str
    prebuild_app_image: bool


SPRING = Recipe(
    name="spring-shipments",
    fixture=FIXTURES / "spring-shipments",
    stack="spring",
    app_port=8080,
    auth_key="APP_SECURITY_ENABLED",
    auth_off_value="false",
    entries=("POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"),
    rules_sources=(
        ("POST /api/shipments", "src/main/java/com/acme/shipments/ShipmentRequest.java"),
        ("POST /api/shipments", "src/main/java/com/acme/shipments/ShipmentService.java"),
    ),
    marks={
        "POST /api/shipments": (("--stub", "stubs/pricing/default.json"),
                                ("--seed", "seed/examples/post-api-shipments.json")),
        "GET /api/shipments/{id}": (),
        "amq shipment.requested": (("--seed", "seed/examples/amq-shipment-requested.json"),),
    },
    planted_scenario="rejects a shipment over the weight limit",
    planted_feature="features/post-api-shipments.feature",
    prebuild_app_image=True,
)

RECIPES: dict[str, Recipe] = {SPRING.name: SPRING}
```

- [ ] **Step 4: Write the canned subagent replies under `expected/`**

`expected/traces/post-api-shipments.json` — the `via` values are placeholders the harness
replaces by content, so a source edit cannot rot them (`{{line:<file>:<needle>}}` is resolved
with `kb_helpers.line_of`):

```json
{
  "id": "POST /api/shipments",
  "auth": "required",
  "request": {
    "content_type": "application/json",
    "schema_ref": "src/main/java/com/acme/shipments/ShipmentRequest.java",
    "example": "seed/examples/post-api-shipments.json"
  },
  "responses": [
    { "status": 201, "when": "shipment created" },
    { "status": 400, "when": "request body fails bean validation", "rules": true,
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@NotBlank}}" },
    { "status": 500, "when": "weight over 1000kg throws IllegalArgumentException",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentService.java:weight exceeds}}" },
    { "status": 401, "when": "missing bearer token", "testable": false }
  ],
  "reads": [
    { "kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET",
      "path": "/rates/{countryCode}" }
  ],
  "exits": [
    { "kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET",
      "path": "/rates/{countryCode}",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentService.java:getForObject}}" },
    { "kind": "db-write", "table": "shipments", "op": "insert",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentService.java:repository.save}}" },
    { "kind": "amq-publish", "destination": "shipment.created", "type": "queue",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentService.java:convertAndSend}}" }
  ],
  "rules": {
    "sources": [
      { "file": "src/main/java/com/acme/shipments/ShipmentRequest.java", "scanned": false },
      { "file": "src/main/java/com/acme/shipments/ShipmentService.java", "scanned": false }
    ]
  },
  "unresolved": []
}
```

`expected/traces/get-api-shipments-id.json`:

```json
{
  "id": "GET /api/shipments/{id}",
  "auth": "required",
  "responses": [
    { "status": 200, "when": "shipment found" },
    { "status": 404, "when": "no shipment with that id" }
  ],
  "reads": [
    { "kind": "db-read", "table": "shipments",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentService.java:findById}}" }
  ],
  "exits": [],
  "exits_none_reason": "read-only lookup",
  "unresolved": []
}
```

`expected/traces/amq-shipment-requested.json`:

```json
{
  "id": "amq shipment.requested",
  "auth": "none",
  "type": "queue",
  "request": {
    "content_type": "application/json",
    "schema_ref": "src/main/java/com/acme/shipments/ShipmentEventsListener.java",
    "example": "seed/examples/amq-shipment-requested.json"
  },
  "responses": [],
  "reads": [],
  "exits": [
    { "kind": "db-write", "table": "shipments", "op": "insert",
      "via": "{{line:src/main/java/com/acme/shipments/ShipmentEventsListener.java:repository.save}}" }
  ],
  "unresolved": []
}
```

`expected/rules/post-api-shipments-1.rows.csv` (the `ShipmentRequest.java` pass) — `source`
values carry the same `{{line:...}}` placeholders:

```csv
rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source
,reference,missing,,400,,reference is required,{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@NotBlank(message = "reference}}
,reference,too_long,51,400,,reference must be at most 50,{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@Size(max = 50}}
,weightKg,out_of_range,0,400,,weight must be positive,{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@Positive}}
,countryCode,invalid_format,!!,400,,countryCode must match,{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@Pattern}}
,destination,too_short,2,400,,destination must be 3 to 120,{{line:src/main/java/com/acme/shipments/ShipmentRequest.java:@Size(min = 3}}
```

`expected/rules/post-api-shipments-2.rows.csv` (the `ShipmentService.java` pass, the planted
business rule):

```csv
rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source
,weightKg,out_of_range,1001,500,,,{{line:src/main/java/com/acme/shipments/ShipmentService.java:weight exceeds}}
```

- [ ] **Step 5: Write the canned generate output under `expected/generated/`**

`expected/generated/features/post-api-shipments.feature`:

```gherkin
@smoke
Feature: POST /api/shipments

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['shipment.created'] }
  * def base = read('classpath:seed/examples/post-api-shipments.json')
  * set base.reference = 'REF-' + uid

Scenario: creates a shipment, writes shipments and publishes shipment.created
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 201
  And match response contains { reference: '#(base.reference)', status: 'PENDING' }
  * def row = Db.row('shipments', { reference: base.reference })
  * match row.status == 'PENDING'
  * def msg = Jms.await('shipment.created', 10000, { reference: base.reference })
  * match msg.body.status == 'PENDING'
  * Stubs.verify('GET', '/pricing/rates/' + base.countryCode, 1)

@error
Scenario: rejects a shipment over the weight limit
  * set base.weightKg = 1500
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 400

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/shipments'
  And request payload
  When method post
  Then status <expected_status>
  * match checkError(response, '<expected_code>', '<expected_message_contains>') == []

  Examples:
    | karate.filter(read('classpath:rules/post-api-shipments.csv'), function(r){ return r.mutation != 'cross_field' }) |
```

The `@error` scenario asserts 400 deliberately: the application answers 500, so the first
run fails there and the fix loop quarantines it. That failure is the planted defect this
fixture exists to prove, and `live_recipes.SPRING.planted_scenario` names it.

`expected/generated/features/get-api-shipments-id.feature`:

```gherkin
@smoke
Feature: GET /api/shipments/{id}

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature')
  * def base = read('classpath:seed/examples/post-api-shipments.json')
  * set base.reference = 'REF-' + uid

Scenario: returns a shipment by id
  Given url appBaseUrl
  And path '/api/shipments'
  And request base
  When method post
  Then status 201
  * def created = response
  Given url appBaseUrl
  And path '/api/shipments/' + created.id
  When method get
  Then status 200
  And match response.reference == base.reference

@error
Scenario: returns 404 for an unknown id
  Given url appBaseUrl
  And path '/api/shipments/11111111-2222-3333-4444-555555555555'
  When method get
  Then status 404
```

`expected/generated/features/amq-shipment-requested.feature`:

```gherkin
@amq
Feature: amq shipment.requested

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature')
  * def base = read('classpath:seed/examples/amq-shipment-requested.json')
  * set base.reference = 'REQ-' + uid

Scenario: a requested message writes a queued shipment
  * Jms.publish('shipment.requested', base, {})
  * def row = Db.awaitRow('shipments', { reference: base.reference }, 10000)
  * match row.status == 'QUEUED'
```

`expected/generated/stubs/pricing/default.json`:

```json
{
  "mappings": [
    {
      "priority": 5,
      "request": { "method": "GET", "urlPathPattern": "/pricing/rates/[A-Z]{2}" },
      "response": {
        "status": 200,
        "headers": { "Content-Type": "application/json" },
        "jsonBody": { "rate": 4.25, "currency": "GBP" }
      }
    }
  ]
}
```

`expected/generated/seed/examples/post-api-shipments.json`:

```json
{ "reference": "REF-0001", "weightKg": 12.5, "countryCode": "GB",
  "destination": "1 Test Warehouse Way" }
```

`expected/generated/seed/examples/amq-shipment-requested.json`:

```json
{ "reference": "REQ-0001", "countryCode": "GB", "weightKg": 3.0,
  "destination": "2 Queue Street" }
```

`expected/defects.md` — what the fix loop must leave behind:

```markdown
## DEF-001: POST /api/shipments answers 500 when the weight exceeds 1000kg

- status: open
- slug: post-api-shipments-weight-limit
- severity: medium
- category: error-handling
- entry_point: POST /api/shipments
- scenario: rejects a shipment over the weight limit
- evidence: the scenario expected 400 and the application answered 500
- root_cause: ShipmentService throws IllegalArgumentException and nothing maps it to a status
- suggested_fix: map the business-rule failure to 400 with a problem-details body
```

`expected/expected-flow-map.yaml` — the spec's pass criterion (section 11), compared field by
field by the harness:

```yaml
entry_points:
  - id: POST /api/shipments
    kind: http
    method: POST
    path: /api/shipments
    exits:
      - { kind: http-out, host_key: PRICING_BASE_URL, method: GET, path: /rates/{countryCode} }
      - { kind: db-write, table: shipments, op: insert }
      - { kind: amq-publish, destination: shipment.created, type: queue }
  - id: GET /api/shipments/{id}
    kind: http
    method: GET
    path: /api/shipments/{id}
    exits: []
  - id: amq shipment.requested
    kind: amq-subscribe
    destination: shipment.requested
    exits:
      - { kind: db-write, table: shipments, op: insert }
```

---

- [ ] **Step 6: Write `tests/test_kb_live_run.py`**

```python
"""The skill's pinned chain against real containers, once per live fixture.

``test_kb_dry_run.py`` proves the commands agree with SKILL.md; this module proves the
artefacts they produce actually work: a real image build, a real Maven run against Postgres,
Artemis, WireMock and the application, a fix-loop round that quarantines the fixture's
planted defect, and the green gate over the second run.

Subagent judgement is canned (spec 11 forbids calling a model from a test): each fixture
ships the trace, rules and generate output a real run would have produced under
``fixtures/live/<name>/expected/``. Everything else is the real script.

Opt in with ``KB_CONTAINERS=1``; CI runs it in the ``karate-live`` job, one fixture per job.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from kb_helpers import line_of
from kb_rules import slug_for
from live_recipes import RECIPES, Recipe
from test_kb_images import docker

SKILL = Path(__file__).resolve().parent.parent
TEMPLATE_README = SKILL / "templates" / "karate-tests" / "README.md.tmpl"
LINE_RE = re.compile(r"\{\{line:([^:]+):(.+?)\}\}")

pytestmark = [
    pytest.mark.containers,
    pytest.mark.skipif(os.environ.get("KB_CONTAINERS") != "1",
                       reason="set KB_CONTAINERS=1 to run containers"),
]


def run(*args: str, cwd: Path | None = None, expect_exit: int = 0) -> str:
    """A skill script, exactly as SKILL.md invokes it."""
    proc = subprocess.run([sys.executable, *args], cwd=cwd or SKILL, capture_output=True,
                          text=True)
    assert proc.returncode == expect_exit, (
        f"{' '.join(args)} exited {proc.returncode}\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}"
    )
    return proc.stdout if expect_exit == 0 else proc.stdout + proc.stderr


def resolve_lines(text: str, repo: Path) -> str:
    """Replace ``{{line:<file>:<needle>}}`` with ``<file>:<n>`` located by content.

    Canned replies must not carry hard-coded line numbers: an edit to a fixture source would
    silently point ``verify-refs`` at the wrong statement.
    """
    def replace(match: re.Match[str]) -> str:
        rel, needle = match.group(1), match.group(2)
        return f"{rel}:{line_of(repo / rel, needle)}"

    return LINE_RE.sub(replace, text)


def maven(tests: Path, *args: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    """``./mvnw -B test`` in the scaffolded module, with the app image already built."""
    wrapper = tests / ("mvnw.cmd" if os.name == "nt" else "mvnw")
    if os.name != "nt":
        wrapper.chmod(0o755)
    proc = subprocess.run([str(wrapper), "-B", "test", *args], cwd=tests,
                          capture_output=True, text=True, timeout=1800,
                          shell=(os.name == "nt"))
    if expect_success:
        assert proc.returncode == 0, proc.stdout[-8000:] + proc.stderr[-4000:]
    return proc


def quarantine(feature: Path, scenario: str) -> None:
    """Tag one scenario ``@known-defect``, the fix loop's move for an unfixable failure."""
    lines = feature.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"Scenario: {scenario}":
            indent = line[: len(line) - len(line.lstrip())]
            lines.insert(index, f"{indent}@known-defect")
            feature.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            return
    raise AssertionError(f"scenario {scenario!r} not found in {feature}")


def build_images(recipe: Recipe, repo: Path) -> tuple[str, str]:
    """The db-manager and application images this run uses; both are removed by the caller."""
    suffix = uuid.uuid4().hex[:8]
    migrations = f"kb-live-dbm-{recipe.name}-{suffix}"
    docker("build", "-t", migrations, str(repo / "db-manager"), timeout=900)
    app_image = ""
    if recipe.prebuild_app_image:
        app_image = f"kb-live-app-{recipe.name}-{suffix}"
        docker("build", "-t", app_image, str(repo), timeout=1800)
    return migrations, app_image


def assert_ledger_matches_expected(ledger: dict[str, Any], expected_path: Path) -> None:
    """Spec 11's pass criterion: every entry and exit the fixture declares is in the ledger."""
    expected = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    actual = {entry["id"]: entry for entry in ledger["entry_points"]}
    assert set(actual) == {entry["id"] for entry in expected["entry_points"]}
    for want in expected["entry_points"]:
        got = actual[want["id"]]
        assert got["kind"] == want["kind"], want["id"]
        for field in ("method", "path", "destination"):
            if field in want:
                assert got.get(field) == want[field], f"{want['id']}.{field}"
        got_exits = [{k: v for k, v in exit_.items() if k != "via"} for exit_ in got["exits"]]
        assert got_exits == want["exits"], want["id"]
        assert got["status"]["traced"] and got["status"]["stubbed"], want["id"]


@pytest.mark.parametrize("recipe", list(RECIPES.values()), ids=lambda r: r.name)
def test_live_chain_goes_green(recipe: Recipe, tmp_path: Path) -> None:
    repo = tmp_path / recipe.name
    shutil.copytree(recipe.fixture, repo, ignore=shutil.ignore_patterns("expected"))
    expected = recipe.fixture / "expected"
    tests = repo / "karate-tests"
    tests.mkdir()
    ledger_path = tests / "flow-map.yaml"
    env_path = tests / "env-map.json"
    migrations_image, app_image = build_images(recipe, repo)
    try:
        # Step 0 and 1: preflight and discovery.
        run("scripts/kb_checkpoint.py", "begin", "--repo", str(repo), "--no-commit")
        run("scripts/detect.py", str(repo), "--out", str(tests / "stack.json"))
        run("scripts/discover.py", str(repo), "--stack", str(tests / "stack.json"),
            "--out-env", str(env_path), "--out-ledger", str(ledger_path))

        # Step 2: the auth switch this fixture ships.
        run("scripts/flow_map.py", "set-auth", "--ledger", str(ledger_path),
            "--mode", "disabled", "--key", recipe.auth_key, "--value", recipe.auth_off_value)

        # Step 3: one canned trace per entry, then the traced gate.
        for entry_id in recipe.entries:
            slug = slug_for(entry_id)
            reply = tests / ".prompts" / f"trace-{slug}.json"
            reply.parent.mkdir(parents=True, exist_ok=True)
            reply.write_text(
                resolve_lines((expected / "traces" / f"{slug}.json").read_text(encoding="utf-8"),
                              repo),
                encoding="utf-8")
            assert "unresolved: 0" in run("scripts/flow_map.py", "merge", str(reply),
                                          "--ledger", str(ledger_path))
        assert "phase traced: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "traced", "--ledger", str(ledger_path),
            "--repo", str(repo), "--env", str(env_path))

        # Step 4: rules, one canned rows file per validation source.
        run("scripts/kb_rules.py", "extract", str(repo), "--ledger", str(ledger_path),
            "--out-dir", str(tests))
        for number, (entry_id, source) in enumerate(recipe.rules_sources, start=1):
            slug = slug_for(entry_id)
            rows = tests / "rules" / f"{slug}-{number}.rows.csv"
            rows.parent.mkdir(parents=True, exist_ok=True)
            rows.write_text(
                resolve_lines(
                    (expected / "rules" / f"{slug}-{number}.rows.csv").read_text(encoding="utf-8"),
                    repo),
                encoding="utf-8")
            run("scripts/kb_rules.py", "add", entry_id, str(rows), "--ledger", str(ledger_path),
                "--out-dir", str(tests))
            run("scripts/kb_rules.py", "mark-scanned", entry_id, source,
                "--ledger", str(ledger_path))

        # Step 5: scaffold the module against the db-manager image built above.
        run("scripts/kb_scaffold.py", str(repo), "--ledger", str(ledger_path),
            "--env", str(env_path), "--out", str(tests),
            "--migrations-image", migrations_image)

        # Step 6: the canned generate output, then the generated gate.
        generated = expected / "generated"
        for source in sorted(generated.rglob("*")):
            if source.is_dir():
                continue
            rel = source.relative_to(generated)
            target = tests / ("src/test/resources" / rel if rel.parts[0] == "features" else rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for entry_id in recipe.entries:
            slug = slug_for(entry_id)
            args = ["scripts/flow_map.py", "mark", "--entry", entry_id, "--generated",
                    "--ledger", str(ledger_path), "--feature", f"features/{slug}.feature"]
            for flag, value in recipe.marks[entry_id]:
                args += [flag, value]
            run(*args)
        assert "phase generated: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "generated", "--ledger",
            str(ledger_path), "--repo", str(repo), "--tests-dir", str(tests))

        # Step 7: the first live run. The planted defect makes it red.
        image_args = [f"-Dapp.image={app_image}"] if app_image else []
        first = maven(tests, *image_args, expect_success=False)
        assert first.returncode != 0, "the planted defect must make the first run fail"
        report = tests / "report.json"
        run("scripts/kb_report.py", "parse", "--reports", str(tests / "target" / "karate-reports"),
            "--out", str(report), "--features", str(tests / "src" / "test" / "resources"
                                                    / "features"))
        parsed = json.loads(report.read_text(encoding="utf-8"))
        failures = [f["scenario"] for f in parsed["failed"]]
        assert recipe.planted_scenario in failures, failures

        # Step 8: one fix-loop round. The failure is a defect in the application, so the
        # scenario is quarantined and recorded; the suite documents behaviour, never fixes it.
        run("scripts/kb_iterate.py", "next", "--report", str(report), "--tests-dir", str(tests))
        run("scripts/kb_iterate.py", "log", "--log", str(tests / "iterations.jsonl"),
            "--signature", f"{recipe.planted_feature}:{recipe.planted_scenario}",
            "--hypothesis", "the application answers 500 where the scenario expects 400",
            "--change", "quarantined the scenario and recorded DEF-001",
            "--classification", "app-defect", "--unfixable")
        quarantine(tests / "src" / "test" / "resources" / recipe.planted_feature,
                   recipe.planted_scenario)
        shutil.copy2(expected / "defects.md", tests / "defects.md")

        # Step 7 again: green with the defect quarantined.
        maven(tests, *image_args)
        run("scripts/kb_report.py", "parse", "--reports", str(tests / "target" / "karate-reports"),
            "--out", str(report), "--features", str(tests / "src" / "test" / "resources"
                                                    / "features"))
        parsed = json.loads(report.read_text(encoding="utf-8"))
        assert parsed["failed"] == [], parsed["failed"]
        assert parsed["passed"] >= 4, parsed
        run("scripts/flow_map.py", "record-run", "--ledger", str(ledger_path),
            "--report", str(report))
        assert "phase green: pass" in run(
            "scripts/flow_map.py", "validate", "--phase", "green", "--ledger", str(ledger_path),
            "--repo", str(repo), "--report", str(report), "--defects", str(tests / "defects.md"))

        # Step 9: the summary the user reads.
        run("scripts/kb_report.py", "summary", "--ledger", str(ledger_path),
            "--defects", str(tests / "defects.md"), "--report", str(report),
            "--template", str(TEMPLATE_README), "--out", str(tests / "README.md"))
        readme = (tests / "README.md").read_text(encoding="utf-8")
        assert "DEF-001" in readme and "${" not in readme.replace("$${", "")

        assert_ledger_matches_expected(yaml.safe_load(ledger_path.read_text(encoding="utf-8")),
                                       expected / "expected-flow-map.yaml")
    finally:
        for tag in (migrations_image, app_image):
            if tag:
                docker("image", "rm", "-f", tag, check=False)
```

- [ ] **Step 7: Give the `karate-live` job a fixture matrix**

Replace the `karate-live` job's single pytest step so each fixture runs in its own job and a
failure names the fixture:

```yaml
  karate-live:
    name: Live containers (${{ matrix.target }})
    runs-on: ubuntu-latest
    timeout-minutes: 45
    strategy:
      fail-fast: false
      matrix:
        target: [images, spring-shipments]
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
      - run: docker version
      - name: Image spike
        if: matrix.target == 'images'
        run: KB_CONTAINERS=1 pytest -m containers skills/karate-bootstrap/tests/test_kb_images.py -v
      - name: Live chain
        if: matrix.target != 'images'
        run: KB_CONTAINERS=1 pytest -m containers -k "${{ matrix.target }}" skills/karate-bootstrap/tests/test_kb_live_run.py -v
      - name: Upload run artefacts
        if: failure() && matrix.target != 'images'
        uses: actions/upload-artifact@v4
        with:
          name: live-${{ matrix.target }}
          path: |
            /tmp/pytest-*/**/karate-tests/target/*.log
            /tmp/pytest-*/**/karate-tests/target/karate-reports/*.json
          if-no-files-found: ignore
```

- [ ] **Step 8: Run the default suite locally**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green, with the live test deselected. `mypy` does not cover `tests/`, but keep
`live_recipes.py` and the harness typed as written: Task 4 and Task 5 read them as the
interface.

- [ ] **Step 9: Commit and push, then read the CI job**

```bash
git add skills/karate-bootstrap/tests/fixtures/live/spring-shipments skills/karate-bootstrap/tests/live_recipes.py skills/karate-bootstrap/tests/test_kb_live_run.py .github/workflows/test.yml
git commit -m "test(karate-bootstrap): spring-shipments fixture and the live-run harness

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

Watch `Live containers (spring-shipments)`. Expect to iterate here: this is the first time the
scaffolded module has met a real application. When it fails, read `target/app.log`,
`target/db-manager.log` and `target/karate-reports/` from the uploaded artefact before
changing anything, and fix the fixture or the canned artefacts — never the harness code in
`templates/`, which Plan 2 pinned and Plan 3 verified.

- [ ] **Step 10: Record the run in `skills/karate-bootstrap/evals/live-run-results.md`**

Append a section naming the workflow run, the wall-clock time of the job, the number of
scenarios the second Maven run passed, and any fixture change the first red run forced.

- [ ] **Step 11: Commit the record**

```bash
git add skills/karate-bootstrap/evals/live-run-results.md
git commit -m "docs(karate-bootstrap): record the first live spring run

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `dotnet-deals` fixture

**Confidence:** 92%. The harness is Task 3's, unchanged: this task adds a fixture directory and one `RECIPES` entry. The application mirrors the frozen `dotnet-mini` analysis fixture, whose `[HttpPost]`, `SaveChangesAsync`, `FromJsonAsync` and `.Send(` markers `discover.py` and `verify-refs` already accept. The measured risk is the .NET AMQP client against Artemis, which Task 2's Artemis row covers for destination creation; the client's own behaviour is proven by this task's first CI run.

**Files:**
- Create: `skills/karate-bootstrap/tests/fixtures/live/dotnet-deals/` (application, `Dockerfile`, `deployment.yml`, `db-manager/`, `expected/`)
- Modify: `skills/karate-bootstrap/tests/live_recipes.py` (the `DOTNET` recipe)
- Modify: `.github/workflows/test.yml` (the matrix gains `dotnet-deals`)

**Interfaces:**
- Consumes: `live_recipes.Recipe`, `test_kb_live_run.test_live_chain_goes_green` (Task 3).
- Produces: nothing later tasks import; Task 6 reads its run record.

- [ ] **Step 1: Write the application sources**

`Deals.Api.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>Deals.Api</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.8" />
    <PackageReference Include="Npgsql.EntityFrameworkCore.PostgreSQL" Version="8.0.4" />
    <PackageReference Include="FluentValidation.AspNetCore" Version="11.3.0" />
    <PackageReference Include="Apache.NMS.AMQP" Version="2.2.0" />
  </ItemGroup>
</Project>
```

`Program.cs`:

```csharp
using Deals.Api.Data;
using Deals.Api.Messaging;
using Deals.Api.Services;
using Deals.Api.Validators;
using FluentValidation;
using FluentValidation.AspNetCore;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddFluentValidationAutoValidation();
builder.Services.AddScoped<IValidator<DealRequest>, DealRequestValidator>();
builder.Services.AddDbContext<DealsDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("Deals")));
builder.Services.AddHttpClient<PricingClient>(client =>
    client.BaseAddress = new Uri(builder.Configuration["Pricing:BaseUrl"]!));
builder.Services.AddSingleton<DealPublisher>();
builder.Services.AddScoped<DealService>();
builder.Services.AddHostedService<DealRequestedConsumer>();

var app = builder.Build();
app.MapControllers();
app.MapGet("/health/ready", () => Results.Ok(new { status = "ready" }));
app.Run();
```

`Data/Deal.cs`:

```csharp
namespace Deals.Api.Data;

public class Deal
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public string ExternalId { get; set; } = string.Empty;
    public string Currency { get; set; } = string.Empty;
    public int Quantity { get; set; }
    public string Status { get; set; } = "PENDING";
    public decimal Price { get; set; }
}
```

`Data/DealsDbContext.cs`:

```csharp
using Microsoft.EntityFrameworkCore;

namespace Deals.Api.Data;

public class DealsDbContext : DbContext
{
    public DealsDbContext(DbContextOptions<DealsDbContext> options) : base(options)
    {
    }

    public DbSet<Deal> Deals => Set<Deal>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Deal>().ToTable("deals");
        modelBuilder.Entity<Deal>().Property(d => d.ExternalId).HasColumnName("external_id");
        modelBuilder.Entity<Deal>().Property(d => d.Currency).HasColumnName("currency");
        modelBuilder.Entity<Deal>().Property(d => d.Quantity).HasColumnName("quantity");
        modelBuilder.Entity<Deal>().Property(d => d.Status).HasColumnName("status");
        modelBuilder.Entity<Deal>().Property(d => d.Price).HasColumnName("price");
        modelBuilder.Entity<Deal>().Property(d => d.Id).HasColumnName("id");
    }
}
```

`Validators/DealRequest.cs`:

```csharp
namespace Deals.Api.Validators;

public class DealRequest
{
    public string ExternalId { get; set; } = string.Empty;
    public string Currency { get; set; } = string.Empty;
    public int Quantity { get; set; }
}
```

`Validators/DealRequestValidator.cs`:

```csharp
using FluentValidation;

namespace Deals.Api.Validators;

public class DealRequestValidator : AbstractValidator<DealRequest>
{
    public DealRequestValidator()
    {
        RuleFor(r => r.ExternalId).NotEmpty().WithMessage("externalId is required");
        RuleFor(r => r.ExternalId).MaximumLength(64).WithMessage("externalId must be at most 64");
        RuleFor(r => r.Currency).Matches("^[A-Z]{3}$").WithMessage("currency must match [A-Z]{3}");
        RuleFor(r => r.Quantity).GreaterThan(0).WithMessage("quantity must be positive");
    }
}
```

`Services/PricingClient.cs`:

```csharp
using System.Net.Http.Json;

namespace Deals.Api.Services;

public class PricingClient
{
    private readonly HttpClient _client;

    public PricingClient(HttpClient client)
    {
        _client = client;
    }

    public async Task<decimal> PriceAsync(string currency)
    {
        var quote = await _client.GetFromJsonAsync<Quote>($"/quotes/{currency}");
        return quote?.Price ?? 0m;
    }

    private sealed record Quote(decimal Price);
}
```

`Messaging/DealPublisher.cs`:

```csharp
using System.Text.Json;
using Apache.NMS;
using Apache.NMS.AMQP;

namespace Deals.Api.Messaging;

/// <summary>AMQP 1.0 to Artemis, the protocol the harness listens on.</summary>
public class DealPublisher : IDisposable
{
    private readonly IConnection _connection;

    public DealPublisher(IConfiguration configuration)
    {
        var factory = new NmsConnectionFactory(configuration["Amq:Url"]);
        _connection = factory.CreateConnection(configuration["Amq:User"],
                                               configuration["Amq:Password"]);
        _connection.Start();
    }

    public void Send(string destination, object body)
    {
        using var session = _connection.CreateSession(AcknowledgementMode.AutoAcknowledge);
        using var producer = session.CreateProducer(session.GetQueue(destination));
        producer.Send(session.CreateTextMessage(JsonSerializer.Serialize(body)));
    }

    public IConnection Connection => _connection;

    public void Dispose()
    {
        _connection.Dispose();
        GC.SuppressFinalize(this);
    }
}
```

`Messaging/DealRequestedConsumer.cs`:

```csharp
using System.Text.Json;
using Apache.NMS;
using Deals.Api.Data;

namespace Deals.Api.Messaging;

public class DealRequestedConsumer : BackgroundService
{
    private readonly DealPublisher _publisher;
    private readonly IServiceScopeFactory _scopes;

    public DealRequestedConsumer(DealPublisher publisher, IServiceScopeFactory scopes)
    {
        _publisher = publisher;
        _scopes = scopes;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var mode = AcknowledgementMode.AutoAcknowledge;
        using var session = _publisher.Connection.CreateSession(mode);
        using var consumer = session.CreateConsumer(session.GetQueue("deal.requested"));
        while (!stoppingToken.IsCancellationRequested)
        {
            if (consumer.Receive(TimeSpan.FromSeconds(1)) is not ITextMessage message)
            {
                continue;
            }
            var body = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(message.Text);
            using var scope = _scopes.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<DealsDbContext>();
            db.Deals.Add(new Deal
            {
                ExternalId = body!["externalId"].GetString() ?? string.Empty,
                Currency = "GBP",
                Quantity = 1,
                Status = "QUEUED",
            });
            await db.SaveChangesAsync(stoppingToken);
        }
    }
}
```

`Services/DealService.cs` — the planted defect is the `InvalidOperationException`: a quantity
over 10000 is a business rule nothing maps, so the application answers 500.

```csharp
using Deals.Api.Data;
using Deals.Api.Messaging;
using Deals.Api.Validators;

namespace Deals.Api.Services;

public class DealService
{
    private readonly DealsDbContext _db;
    private readonly PricingClient _pricing;
    private readonly DealPublisher _publisher;

    public DealService(DealsDbContext db, PricingClient pricing, DealPublisher publisher)
    {
        _db = db;
        _pricing = pricing;
        _publisher = publisher;
    }

    public async Task<Deal> CreateAsync(DealRequest request)
    {
        if (request.Quantity > 10000)
        {
            throw new InvalidOperationException("quantity exceeds the 10000 limit");
        }
        var price = await _pricing.PriceAsync(request.Currency);
        var deal = new Deal
        {
            ExternalId = request.ExternalId,
            Currency = request.Currency,
            Quantity = request.Quantity,
            Price = price,
        };
        _db.Deals.Add(deal);
        await _db.SaveChangesAsync();
        _publisher.Send("deal.created", new { id = deal.Id, externalId = deal.ExternalId,
                                              status = deal.Status });
        return deal;
    }

    public Task<Deal?> FindAsync(Guid id) =>
        Task.FromResult(_db.Deals.FirstOrDefault(d => d.Id == id));
}
```

`Controllers/DealsController.cs`:

```csharp
using Deals.Api.Data;
using Deals.Api.Services;
using Deals.Api.Validators;
using Microsoft.AspNetCore.Mvc;

namespace Deals.Api.Controllers;

[ApiController]
[Route("api/deals")]
public class DealsController : ControllerBase
{
    private readonly DealService _service;

    public DealsController(DealService service)
    {
        _service = service;
    }

    [HttpPost]
    public async Task<ActionResult<Deal>> Create([FromBody] DealRequest request)
    {
        var deal = await _service.CreateAsync(request);
        return StatusCode(StatusCodes.Status201Created, deal);
    }

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<Deal>> Get(Guid id)
    {
        var deal = await _service.FindAsync(id);
        return deal is null ? NotFound() : Ok(deal);
    }
}
```

`appsettings.json`:

```json
{
  "ConnectionStrings": { "Deals": "Host=localhost;Port=5432;Database=deals;Username=app;Password=app" },
  "Amq": { "Url": "amqp://localhost:5672", "User": "artemis", "Password": "artemis" },
  "Pricing": { "BaseUrl": "http://localhost:9090" },
  "Auth": { "Enabled": true },
  "Logging": { "LogLevel": { "Default": "Information" } }
}
```

- [ ] **Step 2: Write the manifest, Dockerfile and db-manager**

`deployment.yml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: deals
spec:
  template:
    spec:
      containers:
        - name: deals
          image: registry.example/deals:latest
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
          env:
            - name: ConnectionStrings__Deals
              valueFrom:
                secretKeyRef:
                  name: deals-db
                  key: connectionString
            - name: Amq__Url
              value: amqp://artemis:5672
            - name: Amq__User
              value: artemis
            - name: Amq__Password
              value: artemis
            - name: Pricing__BaseUrl
              value: http://pricing:8080
            - name: Auth__Enabled
              value: "true"
            - name: ASPNETCORE_URLS
              value: http://+:8080
```

`Dockerfile`:

```dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY Deals.Api.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=build /app .
EXPOSE 8080
ENTRYPOINT ["dotnet", "Deals.Api.dll"]
```

`db-manager/sql/V1__init.sql`:

```sql
CREATE TABLE deals (
    id uuid PRIMARY KEY,
    external_id varchar(64) NOT NULL UNIQUE,
    currency varchar(3) NOT NULL,
    quantity integer NOT NULL,
    status varchar(20) NOT NULL,
    price numeric(12, 2) NOT NULL DEFAULT 0
);
```

`db-manager/entrypoint.sh` and `db-manager/Dockerfile`: the same pair Task 2 measured and
Task 3 copied, with this fixture's `sql` directory.

- [ ] **Step 3: Write the canned artefacts under `expected/`**

Follow Task 3's `expected/` layout exactly. The three entry points are `POST /api/deals`,
`GET /api/deals/{id}` and `amq deal.requested`; the `{{line:...}}` needles are `GetFromJsonAsync`
for the http-out exit, `SaveChangesAsync` for both db-write exits, `_publisher.Send` for the
amq-publish exit, `RuleFor` lines for the four validation rows, and `quantity exceeds` for the
planted rule. `expected/expected-flow-map.yaml` lists:

```yaml
entry_points:
  - id: POST /api/deals
    kind: http
    method: POST
    path: /api/deals
    exits:
      - { kind: http-out, host_key: PRICING__BASEURL, method: GET, path: /quotes/{currency} }
      - { kind: db-write, table: deals, op: insert }
      - { kind: amq-publish, destination: deal.created, type: queue }
  - id: GET /api/deals/{id}
    kind: http
    method: GET
    path: /api/deals/{id}
    exits: []
  - id: amq deal.requested
    kind: amq-subscribe
    destination: deal.requested
    exits:
      - { kind: db-write, table: deals, op: insert }
```

Before writing the `host_key` above, run `python skills/karate-bootstrap/scripts/discover.py
skills/karate-bootstrap/tests/fixtures/live/dotnet-deals --stack <stack.json> --out-env
/tmp/env.json --out-ledger /tmp/ledger.yaml` and read the `env_var` the discovery gives
`Pricing:BaseUrl`; use that exact string. The aspnetcore rule keeps the key as written, so the
value is whatever `env_name` returns, and a guessed spelling would fail the generated gate.

The feature files mirror Task 3's three, with `deal.created`, `deals`, `externalId`, a
`@rules` outline over `rules/post-api-deals.csv`, and the planted scenario named
`rejects a deal over the quantity limit` asserting 400 against the application's 500. The
stub file is `stubs/pricing/default.json` with `urlPathPattern` `/pricing/quotes/[A-Z]{3}`.
`expected/defects.md` records `DEF-001: POST /api/deals answers 500 when the quantity exceeds
10000` in the spec's field order.

- [ ] **Step 4: Add the recipe to `tests/live_recipes.py`**

```python
DOTNET = Recipe(
    name="dotnet-deals",
    fixture=FIXTURES / "dotnet-deals",
    stack="aspnetcore",
    app_port=8080,
    auth_key="Auth__Enabled",
    auth_off_value="false",
    entries=("POST /api/deals", "GET /api/deals/{id}", "amq deal.requested"),
    rules_sources=(
        ("POST /api/deals", "Validators/DealRequestValidator.cs"),
        ("POST /api/deals", "Services/DealService.cs"),
    ),
    marks={
        "POST /api/deals": (("--stub", "stubs/pricing/default.json"),
                            ("--seed", "seed/examples/post-api-deals.json")),
        "GET /api/deals/{id}": (),
        "amq deal.requested": (("--seed", "seed/examples/amq-deal-requested.json"),),
    },
    planted_scenario="rejects a deal over the quantity limit",
    planted_feature="features/post-api-deals.feature",
    prebuild_app_image=True,
)

RECIPES: dict[str, Recipe] = {r.name: r for r in (SPRING, DOTNET)}
```

- [ ] **Step 5: Add `dotnet-deals` to the CI matrix**

In `.github/workflows/test.yml`, extend the `karate-live` matrix:

```yaml
        target: [images, spring-shipments, dotnet-deals]
```

- [ ] **Step 6: Run the default suite locally**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green, the live tests deselected. `pytest --collect-only -m containers -q` must now
list two `test_live_chain_goes_green` cases; run it to confirm the recipe is wired.

- [ ] **Step 7: Commit, push, and read the CI job**

```bash
git add skills/karate-bootstrap/tests/fixtures/live/dotnet-deals skills/karate-bootstrap/tests/live_recipes.py .github/workflows/test.yml
git commit -m "test(karate-bootstrap): dotnet-deals live fixture

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

Watch `Live containers (dotnet-deals)`. The likely first failures, in order of probability:
the connection string the scaffold writes does not match Npgsql's expectations, the AMQP
consumer needs the queue to exist before it subscribes (Task 2 proved `--queues` creates it,
and the ledger's destinations drive that argument), and EF Core's column mapping disagrees
with the db-manager schema. All three are fixture problems; fix them in the fixture.

- [ ] **Step 8: Append the run to `skills/karate-bootstrap/evals/live-run-results.md` and commit**

```bash
git add skills/karate-bootstrap/evals/live-run-results.md
git commit -m "docs(karate-bootstrap): record the first live dotnet run

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `fastapi-orders` fixture and the in-container image build

**Confidence:** 91%. Same harness again, with two surfaces no earlier task exercises: the app image is built by `ImageFromDockerfile` inside the run rather than prebuilt (`prebuild_app_image=False`), and the service reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` and `DB_PASSWORD` as separate variables, which is exactly the classification Task 1 fixed. If Task 1's change were wrong, this fixture's application would be handed the WireMock URL as its database host and the run would fail loudly at startup. The `python-qpid-proton` install is Task 2's third measurement; if that row failed, this task's image installs the build dependencies the recorded output names.

**Files:**
- Create: `skills/karate-bootstrap/tests/fixtures/live/fastapi-orders/` (application, `Dockerfile`, `deployment.yml`, `db-manager/`, `expected/`)
- Modify: `skills/karate-bootstrap/tests/live_recipes.py` (the `FASTAPI` recipe)
- Modify: `.github/workflows/test.yml` (the matrix gains `fastapi-orders`)

**Interfaces:**
- Consumes: `live_recipes.Recipe`, `test_kb_live_run.test_live_chain_goes_green` (Task 3); `discover.assign_role`'s db-part classification (Task 1).
- Produces: nothing later tasks import.

- [ ] **Step 1: Write the application sources**

`requirements.txt`:

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
SQLAlchemy==2.0.34
psycopg[binary]==3.2.1
pydantic==2.9.1
httpx==0.27.2
python-qpid-proton==0.39.0
```

`app/settings.py`:

```python
"""Configuration read from the environment, one variable per connection part.

The database is configured as parts rather than a URL on purpose: it is the shape that
proves ``discover.assign_role`` classifies ``DB_HOST`` and its siblings as ``db`` and not as
a downstream service (Plan 4 Task 1).
"""
from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_port = os.environ.get("DB_PORT", "5432")
        self.db_name = os.environ.get("DB_NAME", "orders")
        self.db_user = os.environ.get("DB_USER", "app")
        self.db_password = os.environ.get("DB_PASSWORD", "app")
        self.amqp_url = os.environ.get("AMQP_URL", "amqp://localhost:5672")
        self.amqp_user = os.environ.get("AMQP_USER", "artemis")
        self.amqp_password = os.environ.get("AMQP_PASSWORD", "artemis")
        self.inventory_url = os.environ.get("INVENTORY_URL", "http://localhost:9090")
        self.auth_enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"

    @property
    def database_url(self) -> str:
        return (f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}")


settings = Settings()
```

`app/models.py`:

```python
"""SQLAlchemy models. ``__tablename__`` is what the tracer must report, not the class name."""
from __future__ import annotations

import uuid

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    sku: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
```

`app/schemas.py`:

```python
"""Pydantic request models; FastAPI answers 422 when one of these constraints fails."""
from __future__ import annotations

from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=50)
    sku: str = Field(pattern=r"^[A-Z]{3}-\d{4}$")
    quantity: int = Field(gt=0)
```

`app/db.py`:

```python
"""Engine and session factory, built once from the settings."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
```

`app/messaging.py`:

```python
"""AMQP 1.0 over Qpid Proton: one blocking connection shared by the app."""
from __future__ import annotations

import json
import threading
from typing import Any

from proton import Message
from proton.utils import BlockingConnection

from app.settings import settings

_lock = threading.Lock()
_connection: BlockingConnection | None = None


def connection() -> BlockingConnection:
    global _connection
    with _lock:
        if _connection is None:
            _connection = BlockingConnection(
                settings.amqp_url, user=settings.amqp_user, password=settings.amqp_password)
        return _connection


def publish(destination: str, body: dict[str, Any]) -> None:
    sender = connection().create_sender(destination)
    sender.send(Message(body=json.dumps(body)))
```

`app/consumer.py`:

```python
"""Background consumer for ``order.requested``: one row per message."""
from __future__ import annotations

import json
import threading

from app.db import SessionLocal
from app.messaging import connection
from app.models import Order

DESTINATION = "order.requested"


def _loop() -> None:
    receiver = connection().create_receiver(DESTINATION)
    while True:
        message = receiver.receive()
        body = json.loads(message.body)
        with SessionLocal() as session:
            session.add(Order(reference=body["reference"], sku=body.get("sku", "AAA-0001"),
                              quantity=int(body.get("quantity", 1)), status="QUEUED"))
            session.commit()


def start() -> None:
    threading.Thread(target=_loop, name="order-requested", daemon=True).start()
```

`app/service.py` — the planted defect is the `RuntimeError`: a quantity over 500 is a
business rule nothing maps, so FastAPI answers 500.

```python
"""Order creation: price from inventory, a row, then an event."""
from __future__ import annotations

import httpx

from app.db import SessionLocal
from app.messaging import publish
from app.models import Order
from app.schemas import OrderRequest
from app.settings import settings


def create_order(request: OrderRequest) -> Order:
    if request.quantity > 500:
        raise RuntimeError("quantity exceeds the 500 limit")
    response = httpx.get(f"{settings.inventory_url}/stock/{request.sku}", timeout=10.0)
    unit_price = float(response.json().get("unitPrice", 0))
    order = Order(reference=request.reference, sku=request.sku, quantity=request.quantity,
                  status="PENDING", unit_price=unit_price)
    with SessionLocal() as session:
        session.add(order)
        session.commit()
        session.refresh(order)
    publish("order.created", {"id": str(order.id), "reference": order.reference,
                              "status": order.status})
    return order
```

`app/main.py`:

```python
"""The HTTP surface: two routes plus the readiness probe the manifest names."""
from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException

from app.consumer import start as start_consumer
from app.db import SessionLocal
from app.models import Order
from app.schemas import OrderRequest
from app.service import create_order

app = FastAPI()


@app.on_event("startup")
def _startup() -> None:
    start_consumer()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/orders", status_code=201)
def post_order(request: OrderRequest) -> dict[str, object]:
    order = create_order(request)
    return {"id": str(order.id), "reference": order.reference, "status": order.status,
            "unitPrice": float(order.unit_price)}


@app.get("/api/orders/{order_id}")
def get_order(order_id: uuid.UUID) -> dict[str, object]:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="not found")
        return {"id": str(order.id), "reference": order.reference, "status": order.status,
                "unitPrice": float(order.unit_price)}
```

- [ ] **Step 2: Write the manifest, Dockerfile and db-manager**

`deployment.yml` — the database is configured as parts, which is the point of this fixture:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  template:
    spec:
      containers:
        - name: orders
          image: registry.example/orders:latest
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8000
          env:
            - name: DB_HOST
              value: db.internal
            - name: DB_PORT
              value: "5432"
            - name: DB_NAME
              value: orders
            - name: DB_USER
              value: app
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: password
            - name: AMQP_URL
              value: amqp://artemis:5672
            - name: AMQP_USER
              value: artemis
            - name: AMQP_PASSWORD
              value: artemis
            - name: INVENTORY_URL
              value: http://inventory:8080
            - name: AUTH_ENABLED
              value: "true"
```

`Dockerfile` — this image is built by the harness inside the run, so keep it small:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

If Task 2's proton row recorded a failure, add the build dependencies it named before the
`pip install` line and say so in the eval record:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gcc cmake libssl-dev \
    && rm -rf /var/lib/apt/lists/*
```

`db-manager/sql/V1__init.sql`:

```sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    reference varchar(50) NOT NULL UNIQUE,
    sku varchar(20) NOT NULL,
    quantity integer NOT NULL,
    status varchar(20) NOT NULL,
    unit_price numeric(12, 2) NOT NULL DEFAULT 0
);
```

`db-manager/entrypoint.sh` and `db-manager/Dockerfile`: the pair Task 2 measured, with this
fixture's `sql`.

- [ ] **Step 3: Write the canned artefacts under `expected/`**

Same layout as Task 3. Entry points are `POST /api/orders`, `GET /api/orders/{order_id}` and
`amq order.requested`. The `{{line:...}}` needles are `httpx.get` for the http-out exit,
`session.add` in `app/service.py` and in `app/consumer.py` for the two db-write exits,
`publish("order.created"` for the amq-publish exit, the `Field(` lines in `app/schemas.py`
for the validation rows, and `quantity exceeds` for the planted rule. Validation responses are
**422**, not 400: FastAPI's request-model failure is a 422 and the rules rows must say so.
`expected/expected-flow-map.yaml`:

```yaml
entry_points:
  - id: POST /api/orders
    kind: http
    method: POST
    path: /api/orders
    exits:
      - { kind: http-out, host_key: INVENTORY_URL, method: GET, path: /stock/{sku} }
      - { kind: db-write, table: orders, op: insert }
      - { kind: amq-publish, destination: order.created, type: queue }
  - id: GET /api/orders/{order_id}
    kind: http
    method: GET
    path: /api/orders/{order_id}
    exits: []
  - id: amq order.requested
    kind: amq-subscribe
    destination: order.requested
    exits:
      - { kind: db-write, table: orders, op: insert }
```

The planted scenario is `rejects an order over the quantity limit`, asserting 422 against the
application's 500, and `expected/defects.md` records
`DEF-001: POST /api/orders answers 500 when the quantity exceeds 500`.

- [ ] **Step 4: Add the recipe to `tests/live_recipes.py`**

```python
FASTAPI = Recipe(
    name="fastapi-orders",
    fixture=FIXTURES / "fastapi-orders",
    stack="python",
    app_port=8000,
    auth_key="AUTH_ENABLED",
    auth_off_value="false",
    entries=("POST /api/orders", "GET /api/orders/{order_id}", "amq order.requested"),
    rules_sources=(("POST /api/orders", "app/schemas.py"), ("POST /api/orders", "app/service.py")),
    marks={
        "POST /api/orders": (("--stub", "stubs/inventory/default.json"),
                             ("--seed", "seed/examples/post-api-orders.json")),
        "GET /api/orders/{order_id}": (),
        "amq order.requested": (("--seed", "seed/examples/amq-order-requested.json"),),
    },
    planted_scenario="rejects an order over the quantity limit",
    planted_feature="features/post-api-orders.feature",
    prebuild_app_image=False,
)

RECIPES: dict[str, Recipe] = {r.name: r for r in (SPRING, DOTNET, FASTAPI)}
```

`prebuild_app_image=False` is the point: the harness passes no `-Dapp.image`, so
`Containers.buildApp` builds the image from `Dockerfile` with the repository root as the
build context, the default path a real run takes.

- [ ] **Step 5: Assert the db-part classification in the run**

Add this assertion to `test_kb_live_run.py`, immediately after the `discover.py` call, so the
fixture proves Task 1's fix rather than merely depending on it:

```python
        env_map = json.loads(env_path.read_text(encoding="utf-8"))
        roles = {key["key"]: key["role"] for key in env_map["keys"]}
        for name, role in roles.items():
            if name.upper().startswith("DB_"):
                assert role == "db", f"{name} took the {role} role; the app would be misconfigured"
```

- [ ] **Step 6: Add `fastapi-orders` to the CI matrix**

```yaml
        target: [images, spring-shipments, dotnet-deals, fastapi-orders]
```

- [ ] **Step 7: Run the default suite locally**

Run: `pytest -q` then `ruff check .` then `mypy`
Expected: green, three live cases collected under `-m containers`.

- [ ] **Step 8: Commit, push, and read the CI job**

```bash
git add skills/karate-bootstrap/tests/fixtures/live/fastapi-orders skills/karate-bootstrap/tests/live_recipes.py skills/karate-bootstrap/tests/test_kb_live_run.py .github/workflows/test.yml
git commit -m "test(karate-bootstrap): fastapi-orders live fixture and the in-run image build

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

Watch `Live containers (fastapi-orders)`. Expect the in-run image build to add two to four
minutes; if the job exceeds its 45-minute budget, raise `timeout-minutes` rather than
switching the fixture to a prebuilt image, because the in-run build is what this fixture
exists to exercise.

- [ ] **Step 9: Append the run to the eval record and commit**

```bash
git add skills/karate-bootstrap/evals/live-run-results.md
git commit -m "docs(karate-bootstrap): record the first live fastapi run

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Fixture completeness test, spec status, README and the eval record

**Confidence:** 96%. Documentation over facts Tasks 2 to 5 produced, plus one structural test that runs in the default suite and stops a future fixture from landing half-built. The spec edit records what the fixture runs proved and where they run, which is the only spec claim this plan changes.

**Files:**
- Modify: `skills/karate-bootstrap/tests/test_kb_fixtures.py` (the live-fixture shape test)
- Modify: `skills/karate-bootstrap/evals/live-run-results.md` (the summary table)
- Modify: `README.md` (the fixtures and live-runs section)
- Modify: `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md` (sections 10, 11 and 12)

**Interfaces:**
- Consumes: `live_recipes.RECIPES` (Tasks 3 to 5); the three run records in the eval file.
- Produces: nothing; this is the last task of the last plan.

- [ ] **Step 1: Write the failing fixture-shape test**

Append to `skills/karate-bootstrap/tests/test_kb_fixtures.py`:

```python
from live_recipes import RECIPES

LIVE_REQUIRED = (
    "Dockerfile",
    "db-manager/Dockerfile",
    "db-manager/entrypoint.sh",
    "expected/expected-flow-map.yaml",
    "expected/defects.md",
)


@pytest.mark.parametrize("recipe", list(RECIPES.values()), ids=lambda r: r.name)
def test_live_fixture_carries_everything_the_harness_needs(recipe: Any) -> None:
    missing = [rel for rel in LIVE_REQUIRED if not (recipe.fixture / rel).is_file()]
    assert missing == [], f"{recipe.name} is missing {missing}"
    manifests = list(recipe.fixture.glob("deployment*.yml"))
    assert manifests, f"{recipe.name} has no deployment manifest for discover.py to read"
    for entry_id in recipe.entries:
        slug = slug_for(entry_id)
        assert (recipe.fixture / "expected" / "traces" / f"{slug}.json").is_file(), slug
        feature = recipe.fixture / "expected" / "generated" / "features" / f"{slug}.feature"
        assert feature.is_file(), slug
    for number, (entry_id, source) in enumerate(recipe.rules_sources, start=1):
        slug = slug_for(entry_id)
        rows = recipe.fixture / "expected" / "rules" / f"{slug}-{number}.rows.csv"
        assert rows.is_file(), rows
        assert (recipe.fixture / source).is_file(), f"{recipe.name}: {source} does not exist"
    planted = recipe.fixture / "expected" / "generated" / recipe.planted_feature
    assert recipe.planted_scenario in planted.read_text(encoding="utf-8")
    assert set(recipe.marks) == set(recipe.entries), recipe.name
```

Add `from typing import Any`, `import pytest` and `from kb_rules import slug_for` to that
module's imports if they are not already there, keeping them sorted.

- [ ] **Step 2: Run it and confirm it passes**

Run: `pytest skills/karate-bootstrap/tests/test_kb_fixtures.py -q`
Expected: PASS for all three fixtures. This test is a guard, not a red-to-green step: Tasks 3
to 5 already built what it checks ([[verify-red]] — say so rather than claiming a false red).
If a fixture fails it, the fixture is incomplete and the failure is real.

- [ ] **Step 3: Finish `skills/karate-bootstrap/evals/live-run-results.md`**

Give the file a summary table above the per-run sections, filled from the three workflow runs:

```markdown
## Fixture runs (design spec section 11)

| Fixture | Stack | Entry points | Scenarios green | Planted defect | App image | Run |
|---|---|---:|---:|---|---|---|
| spring-shipments | spring | 3 | <n> | DEF-001 weight over 1000kg answers 500 | prebuilt, `-Dapp.image` | <workflow URL> |
| dotnet-deals | aspnetcore | 3 | <n> | DEF-001 quantity over 10000 answers 500 | prebuilt, `-Dapp.image` | <workflow URL> |
| fastapi-orders | python | 3 | <n> | DEF-001 quantity over 500 answers 500 | built in-run from the Dockerfile | <workflow URL> |

Pass criteria, from the spec: exit 0 on the second run, every entry in
`expected-flow-map.yaml` present in the ledger, zero unresolved, `defects.md` carrying the
planted defect. All four hold for every row above.

Not covered by these runs, and why: <one line each, for example a Podman host, an ADO agent,
a repository with more than one service, or an application whose readiness probe is absent>.
```

- [ ] **Step 4: Update the spec**

In section 10, after the CI paragraph, add:

```markdown
- **This repo's CI, live.** A `karate-live` job matrix on `ubuntu-latest` runs `KB_CONTAINERS=1 pytest -m containers`: one job measures the third-party images, and one job per fixture runs the whole chain against real containers, including a Maven run, a fix-loop round and the green gate. The default `pytest` excludes the `containers` marker, so a machine without Docker runs everything else.
```

In section 11, replace the **Fixture runs** bullet with:

```markdown
- **Fixture runs.** Three runnable fixtures under `tests/fixtures/live/` — `spring-shipments`, `dotnet-deals` and `fastapi-orders` — each with a Flyway `db-manager/` image and one planted 500. `tests/test_kb_live_run.py` drives the pinned chain against them with canned subagent replies and real containers. Pass criteria: the second Maven run exits 0, every entry in `expected-flow-map.yaml` is in the ledger, zero unresolved, and `defects.md` carries the planted defect. Results are recorded in `evals/live-run-results.md`.
```

In section 12, under **Minor, accepted**, add:

```markdown
- The author's machine has no container runtime, so the fixture runs are gated in GitHub Actions rather than locally. A developer with Docker or Podman reproduces them with `KB_CONTAINERS=1 pytest -m containers`.
```

- [ ] **Step 5: Update the repository README**

In the `karate-bootstrap` section, after the paragraph describing the scripts, add:

```markdown
Three runnable fixture services live under `skills/karate-bootstrap/tests/fixtures/live/`, one
per stack the skill supports: a Spring Boot service, an ASP.NET Core service and a FastAPI
service, each with a Flyway `db-manager/` image and one deliberately planted defect. The
`karate-live` CI job runs the skill's whole chain against them with real Postgres, Artemis,
WireMock and application containers, proving the generated suite goes green and the planted
defect is quarantined rather than fixed. Reproduce a run locally with Docker or Podman:

```bash
KB_CONTAINERS=1 pytest -m containers -k spring-shipments -v
```
```

- [ ] **Step 6: Full gate**

Run: `pytest -q` then `ruff check .` then `mypy` then `python skills/karate-bootstrap/scripts/kb_check_skill.py`
Expected: green, the linter prints ok, and the live tests stay deselected.

- [ ] **Step 7: Commit**

```bash
git add skills/karate-bootstrap/tests/test_kb_fixtures.py skills/karate-bootstrap/evals/live-run-results.md README.md docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md
git commit -m "docs(karate-bootstrap): record the fixture runs and how to reproduce them

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

---

## Self-review record

Run after the plan was written, against spec commit `b64fa28`.

1. **Spec coverage.** Section 5.5's `migration-container` strategy and central-config shape: Tasks 3 to 5 each ship a db-manager image driven by the default `PG*` variable names, and Task 2 measures that shape first. Section 5.7's run-and-iterate loop, including `kb_iterate log` and quarantine: the harness performs one real fix-loop round per fixture. Section 5.8's summary and README: asserted at the end of every live run. Section 10's local and CI execution: Task 6 adds the live CI paragraph; the local instructions already exist and Task 6's README section points at them. Section 11's four eval kinds: script tests and the dry run already exist from Plans 1 to 3, the trigger eval is a checked-in document from Plan 3, and this plan supplies the fixture runs. Section 12's assumption buckets gain the no-local-runtime entry. Not in this plan by design: an ADO pipeline run (the template ships the YAML; the user's own agents run it), a Podman-hosted run, and any change to `templates/karate-tests` Java, which Plans 2 and 3 pinned.
2. **Placeholder scan.** No TBD, TODO or "similar to Task N". Three deliberate fill-in-from-the-run spots exist and are marked as such: the eval record's `<n>`, `<URL>` and pass/fail cells, which an executor completes from the workflow output rather than inventing, and the `host_key` in Task 4's expected ledger, which Step 3 tells the executor to read from `discover.py`'s own output rather than guess.
3. **Type and name consistency.** `Recipe`'s fields (`name, fixture, stack, app_port, auth_key, auth_off_value, entries, rules_sources, marks, planted_scenario, planted_feature, prebuild_app_image`) match every use in `test_kb_live_run.py`, in Tasks 4 and 5's recipes, and in Task 6's completeness test. `docker(...)` is defined once in `test_kb_images.py` and imported by the harness. `slug_for` comes from `kb_rules`, `line_of` from `kb_helpers`, both already in the tree. `STARTUP_SIGNATURE` is defined in Task 1 and used only there.
4. **Cross-read.** Each fixture's application source, its `expected-flow-map.yaml`, its canned trace and its feature file name the same exits, tables and destinations; the `{{line:...}}` needles quote text that appears verbatim in the sources this plan writes (`getForObject`, `repository.save`, `convertAndSend`, `GetFromJsonAsync`, `SaveChangesAsync`, `_publisher.Send`, `httpx.get`, `session.add`, `publish("order.created"`). Validation statuses differ by stack on purpose: 400 for Bean Validation and FluentValidation, 422 for Pydantic, and each fixture's rules rows say so.
5. **Ordering.** Task 2 lands the `containers` marker and the `docker` helper that Task 3 imports; Task 3 lands the harness that Tasks 4 and 5 extend by one dictionary entry; Task 6's completeness test imports `RECIPES`, so it must come last. Task 1 has no dependents but comes first because Task 5's fixture would misconfigure its database without it.
