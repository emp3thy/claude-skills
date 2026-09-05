# karate-bootstrap Plan 1 of 3: Analysis Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic analysis scripts for the `karate-bootstrap` skill: stack detection, manifest and config discovery, the `flow-map.yaml` ledger with its validators, and validation-rule extraction, all unit-tested against four miniature fixture repos.

**Architecture:** Direct-path-invocable Python scripts under `skills/karate-bootstrap/scripts/`, mirroring `tech-debt-scan`: flat top-level modules, `argparse` CLIs, pinned output files, exit codes from one shared module. Per-stack regex marker tables live in `markers.py` and are the single source for entry-point discovery, exit-reference verification and rules extraction. No LLM calls in any script or test.

**Tech Stack:** Python 3.11+, `pyyaml` (only runtime dependency), pytest, ruff (E,F,I,B,UP,SIM, line length 100), mypy `--strict`.

**Spec:** `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md`

**Phasing:** This is Plan 1 of 3. Plan 2 covers scaffold, templates, the Java harness, report and iterate scripts, the git checkpoint script, prompts, cheat sheets and `SKILL.md`. Plan 3 covers the three fixture apps with db-manager images and the end-to-end evals on a container runtime. Each plan leaves the repo green on `ruff check .`, `mypy`, `pytest -v`.

## Guardrails

Surfaced from the project's standards document and high-confidence reflections before drafting. Tasks reference these by anchor.

- **[[confidence-gate]]** (standards, non-skippable): every task carries a confidence percentage. Tasks below 90% embed their mitigation in the task body. Nothing below 90% is executed without the mitigation.
- **[[docs-in-sync]]** (reflection mem-f3ce58e6, confidence 0.95, used 28x): when a CLI flag, output file or exit code is added or renamed, update `pyproject.toml`, the module docstring and, in Plan 2, `SKILL.md` and `README.md` in the same task. Plan 2's `check_skill.py` lints `SKILL.md` commands against `--help`.
- **[[no-improvisation]]** (repo convention from `tech-debt-scan`): scripts fail with a defined exit code when an expected input is missing. They never guess.
- **[[spec-code-lint]]** (standards): copied test or script code is not lint-clean by default. Every task ends with `ruff check` and `mypy` on the touched files before commit. Watch for F401 unused imports, UP017 (`datetime.UTC`), B905 (`zip(strict=...)`), SIM rules.
- **[[verify-red]]** (reflection mem-66b096bf, confidence 0.8): before claiming a test fails, confirm the failure is the expected one (`ModuleNotFoundError` or `AttributeError` for missing code, not a fixture path typo).
- **[[unique-module-names]]** (discovered while planning): both skills' `tests/conftest.py` put their `scripts/` dir on `sys.path` in one pytest session. Module basenames must be unique across `skills/*/scripts/` and `skills/*/tests/`. This plan uses `kb_common.py`, `markers.py`, `detect.py`, `discover.py`, `flow_map.py`, `rules.py`, and test files prefixed `test_kb_`. Do not add `__init__.py` to `skills/karate-bootstrap/tests/`.

Dismissed as not applicable to this plan: Playwright text matching, tempfile fd leak (no temp files here), TypeScript Partial, freeze localisation logging.

## Task confidence summary

| Task | Deliverable | Confidence | Mitigation embedded in the task |
|------|-------------|-----------:|----------------------------------|
| 1 | Skeleton, `kb_common.py`, pyproject wiring | 95% | Root `pytest` run proves no module-name collision with `tech-debt-scan` |
| 2 | Four fixture mini-repos | 95% | Inventory test lists every required file; tests locate lines by content, not number |
| 3 | `markers.py` | 90% | Every regex tested against the exact fixture lines it must match and one it must not |
| 4 | `detect.py` | 92% | Toolchain check isolated behind `--skip-toolchain`; per-fixture expectations pinned |
| 5 | `discover.py` part A | 88% | Parsers are pure functions; roles ordered and pinned per fixture; unknown keys fall through to passthrough |
| 6 | `discover.py` part B | 85% | Per-stack prefix handling as separate functions; exact entry-id sets per fixture |
| 7 | `flow_map.py` part A | 92% | Merge contract pinned by tests, including unresolved handling |
| 8 | `flow_map.py` part B | 88% | Input contracts for Plan 2 artefacts fixed here with hand-built minimal artefacts |
| 9 | `rules.py` | 85% | One extractor per library, exact expected rows; candidates kept separate from confirmed rows |

No task is below 85%. Tasks under 90% carry their mitigation inside the task body as required by [[confidence-gate]].

## Global Constraints

- Python floor `>=3.11`, ruff `target-version = "py311"`, mypy `python_version = "3.11"`, strict.
- Only runtime dependency: `pyyaml>=6.0`.
- Scripts are direct-path invocable: `python skills/karate-bootstrap/scripts/<name>.py`. Sibling imports are flat (`from kb_common import ...`), resolved by `tests/conftest.py` and `mypy_path`.
- Exit codes (spec section 9): 0 ok, 2 validation failure, 3 unsupported stack, 4 no schema source, 5 missing expected output, 6 stopped by stop condition, 7 container runtime or JDK missing.
- Supported stacks: `spring`, `quarkus`, `aspnetcore`, `python`. DB: `postgres` only.
- Manifest filenames checked first: `deployment.yml`, then `deploymentserverless.yml` (sets `serverless: true`).
- All paths written into JSON or YAML outputs are POSIX-relative to the service root.
- Ledger schema is spec section 6. Rules CSV header is exactly `rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source`.
- Mutation enum: `missing, null, empty, too_long, too_short, invalid_format, out_of_range, invalid_enum, cross_field`.
- Commit messages follow Conventional Commits, scope `karate-bootstrap`, and end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never bypass git hooks.

---

## File Structure

```
skills/karate-bootstrap/
  scripts/
    kb_common.py      exit codes, KbError, JSON/YAML IO, file walking, CLI wrapper
    markers.py        per-stack marker tables and verify-refs token lists
    detect.py         Phase 0: build files -> stack.json
    discover.py       Phase 1: manifests, Dockerfile, config, routes -> env-map.json, seeded flow-map.yaml
    flow_map.py       ledger: next, merge, mark, validate, verify-refs
    rules.py          Phase 3: extract, add, mark-scanned -> rules/*.csv
  tests/
    conftest.py
    fixtures/
      spring-mini/      Spring Boot, serverless manifest, JPA, spring-jms, RestTemplate, Bean Validation
      quarkus-mini/     Quarkus, JAX-RS, Panache, SmallRye messaging, RestClient
      dotnet-mini/      ASP.NET Core controllers, EF Core, Apache.NMS.AMQP, HttpClient, FluentValidation, auth switch
      fastapi-mini/     FastAPI, SQLAlchemy, qpid-proton, httpx, Pydantic
    test_kb_common.py
    test_kb_fixtures.py
    test_kb_markers.py
    test_kb_detect.py
    test_kb_discover.py
    test_kb_flow_map.py
    test_kb_rules.py
pyproject.toml        testpaths, mypy files and mypy_path extended
```

Responsibilities are one per file. `discover.py` is the largest; it is split internally into manifest parsing, config parsing, role assignment, auth detection and entry-point discovery, each a pure function with its own tests.

---

### Task 1: Skill skeleton, repo wiring and `kb_common.py`

**Confidence:** 95%. Pure Python, patterns copied from `tech-debt-scan`. Risk is the pytest module-name collision described in [[unique-module-names]], mitigated by the naming rule and by running the full root `pytest` in Step 8.

**Files:**
- Create: `skills/karate-bootstrap/scripts/kb_common.py`
- Create: `skills/karate-bootstrap/tests/conftest.py`
- Create: `skills/karate-bootstrap/tests/test_kb_common.py`
- Modify: `pyproject.toml` (testpaths, mypy files, mypy_path)

**Interfaces:**
- Produces:
  - Exit code constants `EXIT_OK=0, EXIT_VALIDATION=2, EXIT_UNSUPPORTED_STACK=3, EXIT_NO_SCHEMA=4, EXIT_MISSING_OUTPUT=5, EXIT_STOPPED=6, EXIT_TOOLCHAIN=7`.
  - `class KbError(Exception)` with `.exit_code: int` (default 2).
  - `read_json(path: Path) -> dict[str, Any]`, `write_json(path: Path, data: Mapping[str, Any]) -> None`.
  - `read_yaml(path: Path) -> dict[str, Any]`, `write_yaml(path: Path, data: Mapping[str, Any]) -> None`, `read_yaml_docs(path: Path) -> list[dict[str, Any]]`.
  - `read_text(path: Path) -> str` (UTF-8, `errors="replace"`).
  - `require_file(path: Path, what: str) -> Path` raising `KbError(..., EXIT_MISSING_OUTPUT)`.
  - `rel(path: Path, root: Path) -> str` POSIX relative string.
  - `iter_files(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]` honouring `DEFAULT_IGNORE`.
  - `run_cli(main: Callable[[list[str] | None], int], argv: list[str] | None = None) -> int` that catches `KbError`, prints `error: <message>` to stderr and returns its exit code.

- [ ] **Step 1: Create the conftest**

```python
# skills/karate-bootstrap/tests/conftest.py
"""Pytest path setup so scripts/ imports work in tests."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
```

- [ ] **Step 2: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_common.py
from __future__ import annotations

from pathlib import Path

import pytest

import kb_common
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_VALIDATION,
    KbError,
    iter_files,
    read_json,
    read_yaml,
    read_yaml_docs,
    rel,
    require_file,
    run_cli,
    write_json,
    write_yaml,
)


def test_exit_codes_match_spec() -> None:
    assert kb_common.EXIT_OK == 0
    assert kb_common.EXIT_VALIDATION == 2
    assert kb_common.EXIT_UNSUPPORTED_STACK == 3
    assert kb_common.EXIT_NO_SCHEMA == 4
    assert kb_common.EXIT_MISSING_OUTPUT == 5
    assert kb_common.EXIT_STOPPED == 6
    assert kb_common.EXIT_TOOLCHAIN == 7


def test_kberror_defaults_to_validation_exit() -> None:
    err = KbError("bad")
    assert err.exit_code == EXIT_VALIDATION
    assert str(err) == "bad"


def test_json_roundtrip_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "out" / "nested" / "x.json"
    write_json(target, {"b": 1, "a": [1, 2]})
    assert read_json(target) == {"b": 1, "a": [1, 2]}
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_yaml_roundtrip_preserves_key_order(tmp_path: Path) -> None:
    target = tmp_path / "ledger.yaml"
    write_yaml(target, {"version": 1, "entry_points": [{"id": "GET /x"}], "unresolved": []})
    text = target.read_text(encoding="utf-8")
    assert text.index("version") < text.index("entry_points") < text.index("unresolved")
    assert read_yaml(target)["entry_points"][0]["id"] == "GET /x"


def test_read_yaml_docs_splits_multi_document(tmp_path: Path) -> None:
    target = tmp_path / "multi.yml"
    target.write_text("kind: A\n---\nkind: B\n", encoding="utf-8")
    assert [d["kind"] for d in read_yaml_docs(target)] == ["A", "B"]


def test_require_file_raises_missing_output(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        require_file(tmp_path / "nope.json", "stack.json")
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT
    assert "stack.json" in str(excinfo.value)


def test_rel_is_posix(tmp_path: Path) -> None:
    child = tmp_path / "src" / "A.java"
    assert rel(child, tmp_path) == "src/A.java"


def test_iter_files_skips_ignored_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.java").write_text("x", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "B.java").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "c.py").write_text("x", encoding="utf-8")
    found = sorted(rel(p, tmp_path) for p in iter_files(tmp_path, (".java", ".py")))
    assert found == ["src/A.java"]


def test_run_cli_maps_kberror_to_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    def failing(_argv: list[str] | None) -> int:
        raise KbError("no stack", EXIT_MISSING_OUTPUT)

    assert run_cli(failing, []) == EXIT_MISSING_OUTPUT
    assert "error: no stack" in capsys.readouterr().err
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_common.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'kb_common'` ([[verify-red]]: the error must be about the module, not the conftest path).

- [ ] **Step 4: Implement `kb_common.py`**

```python
# skills/karate-bootstrap/scripts/kb_common.py
"""Shared helpers for karate-bootstrap scripts.

Exit codes (spec section 9): 0 ok, 2 validation failure, 3 unsupported
stack, 4 no schema source, 5 missing expected output, 6 stopped by a stop
condition, 7 container runtime or JDK missing.

Every script is direct-path invocable and imports this module flatly
(``from kb_common import ...``). Tests resolve the import through
``tests/conftest.py``; mypy through ``mypy_path`` in ``pyproject.toml``.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, Final, cast

import yaml

EXIT_OK: Final[int] = 0
EXIT_VALIDATION: Final[int] = 2
EXIT_UNSUPPORTED_STACK: Final[int] = 3
EXIT_NO_SCHEMA: Final[int] = 4
EXIT_MISSING_OUTPUT: Final[int] = 5
EXIT_STOPPED: Final[int] = 6
EXIT_TOOLCHAIN: Final[int] = 7

LEDGER_VERSION: Final[int] = 1

DEFAULT_IGNORE: Final[tuple[str, ...]] = (
    ".git",
    ".idea",
    ".vscode",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "bin",
    "obj",
    "target",
    "build",
    "dist",
    "karate-tests",
)


class KbError(Exception):
    """A user-facing failure with a defined process exit code."""

    def __init__(self, message: str, exit_code: int = EXIT_VALIDATION) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(read_text(path))
    if not isinstance(data, dict):
        raise KbError(f"{path}: expected a JSON object at top level")
    return cast(dict[str, Any], data)


def write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(data), indent=2) + "\n", encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(read_text(path))
    if not isinstance(data, dict):
        raise KbError(f"{path}: expected a YAML mapping at top level")
    return cast(dict[str, Any], data)


def read_yaml_docs(path: Path) -> list[dict[str, Any]]:
    docs = yaml.safe_load_all(read_text(path))
    return [cast(dict[str, Any], d) for d in docs if isinstance(d, dict)]


def write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")


def require_file(path: Path, what: str) -> Path:
    if not path.is_file():
        raise KbError(f"expected {what} at {path}; it does not exist", EXIT_MISSING_OUTPUT)
    return path


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def iter_files(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    """Yield files under ``root`` with one of ``suffixes``, skipping DEFAULT_IGNORE dirs."""
    stack = [root]
    while stack:
        current = stack.pop()
        for child in sorted(current.iterdir()):
            if child.is_dir():
                if child.name not in DEFAULT_IGNORE:
                    stack.append(child)
            elif child.suffix in suffixes:
                yield child


def run_cli(main: Callable[[list[str] | None], int], argv: list[str] | None = None) -> int:
    try:
        return main(argv)
    except KbError as err:
        print(f"error: {err}", file=sys.stderr)
        return err.exit_code
```

- [ ] **Step 5: Wire `pyproject.toml`**

Edit the three settings. Final values:

```toml
[tool.pytest.ini_options]
testpaths = ["skills/tech-debt-scan/tests", "skills/karate-bootstrap/tests"]
markers = ["live: hits a real LLM (off by default)"]
addopts = "-m 'not live'"

[tool.mypy]
python_version = "3.11"
strict = true
files = ["skills/tech-debt-scan/scripts", "skills/karate-bootstrap/scripts"]
# scripts/ are direct-path-invocable (no package), so sibling imports like
# `from validation import ...` need the scripts dir on the mypy search path.
mypy_path = "skills/tech-debt-scan/scripts,skills/karate-bootstrap/scripts"
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_common.py -q`
Expected: `9 passed`.

- [ ] **Step 7: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: `All checks passed!` and `Success: no issues found`. Fix anything reported before continuing ([[spec-code-lint]]).

- [ ] **Step 8: Run the whole repo suite to prove no collision**

Run: `python -m pytest -q`
Expected: `133 passed` (124 existing plus 9). Any "import file mismatch" means a basename collision; rename the offending test file, do not add `__init__.py`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml skills/karate-bootstrap/scripts/kb_common.py skills/karate-bootstrap/tests/conftest.py skills/karate-bootstrap/tests/test_kb_common.py
git commit -m "feat(karate-bootstrap): skill skeleton with shared exit codes and file IO

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 2: Fixture mini-repos for the four stacks

**Confidence:** 95%. Data only. Copy the files verbatim and do not reformat. The parenthetical line-number notes after some files are advisory for the implementer's sanity check; later tests never hard-code them and instead locate lines with a `line_of(path, needle)` helper, so a one-line drift cannot break a test.

**Files:**
- Create: `skills/karate-bootstrap/tests/fixtures/spring-mini/**`
- Create: `skills/karate-bootstrap/tests/fixtures/quarkus-mini/**`
- Create: `skills/karate-bootstrap/tests/fixtures/dotnet-mini/**`
- Create: `skills/karate-bootstrap/tests/fixtures/fastapi-mini/**`
- Create: `skills/karate-bootstrap/tests/test_kb_fixtures.py`

**Interfaces:**
- Produces: the four directories below. Tasks 4 to 9 assert on their exact contents and paths.

- [ ] **Step 1: Write the failing fixture-inventory test**

```python
# skills/karate-bootstrap/tests/test_kb_fixtures.py
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

REQUIRED = {
    "spring-mini": [
        "pom.xml",
        "Dockerfile",
        "deploymentserverless.yml",
        "src/main/resources/application.yml",
        "src/main/resources/db/migration/V1__init.sql",
        "src/main/java/com/acme/shipments/ShipmentController.java",
        "src/main/java/com/acme/shipments/ShipmentRequest.java",
        "src/main/java/com/acme/shipments/ShipmentService.java",
        "src/main/java/com/acme/shipments/ShipmentRepository.java",
        "src/main/java/com/acme/shipments/Shipment.java",
        "src/main/java/com/acme/shipments/ShipmentEventsListener.java",
    ],
    "quarkus-mini": [
        "pom.xml",
        "src/main/docker/Dockerfile.jvm",
        "deployment.yml",
        "src/main/resources/application.properties",
        "src/main/java/com/acme/invoices/InvoiceResource.java",
        "src/main/java/com/acme/invoices/InvoiceRequest.java",
        "src/main/java/com/acme/invoices/InvoiceService.java",
        "src/main/java/com/acme/invoices/Invoice.java",
        "src/main/java/com/acme/invoices/OrderEventsConsumer.java",
    ],
    "dotnet-mini": [
        "Deals.Api.csproj",
        "Dockerfile",
        "deployment.yml",
        "appsettings.json",
        "Program.cs",
        "Controllers/DealsController.cs",
        "Validators/DealRequestValidator.cs",
        "Services/DealService.cs",
        "Messaging/DealRequestedConsumer.cs",
        "Data/DealsDbContext.cs",
        "Data/Deal.cs",
        "Data/Migrations/20260101000000_Init.cs",
    ],
    "fastapi-mini": [
        "pyproject.toml",
        "Dockerfile",
        "deployment.yml",
        "app/settings.py",
        "app/main.py",
        "app/schemas.py",
        "app/service.py",
        "app/consumer.py",
        "app/models.py",
        "alembic/versions/0001_init.py",
    ],
}


def test_fixture_files_present() -> None:
    missing = [
        f"{repo}/{relpath}"
        for repo, files in REQUIRED.items()
        for relpath in files
        if not (FIXTURES / repo / relpath).is_file()
    ]
    assert missing == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_fixtures.py -q`
Expected: FAIL with the assertion listing all 42 missing paths.

- [ ] **Step 3: Create `spring-mini`**

`skills/karate-bootstrap/tests/fixtures/spring-mini/pom.xml`
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
  </parent>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
    <dependency><groupId>org.postgresql</groupId><artifactId>postgresql</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-artemis</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-oauth2-resource-server</artifactId></dependency>
    <dependency><groupId>org.flywaydb</groupId><artifactId>flyway-core</artifactId></dependency>
  </dependencies>
</project>
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/Dockerfile`
```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/shipments.jar app.jar
ENV JAVA_OPTS="-Xmx512m"
EXPOSE 8080
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/deploymentserverless.yml`
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
            initialDelaySeconds: 10
          env:
            - name: SPRING_DATASOURCE_URL
              valueFrom:
                secretKeyRef:
                  name: shipments-db
                  key: url
            - name: SPRING_ARTEMIS_BROKER_URL
              value: tcp://artemis:61616
            - name: PRICING_BASE_URL
              value: http://pricing:8080
            - name: AUTH_ISSUER_URI
              value: https://login.example/realms/acme
          envFrom:
            - configMapRef:
                name: shipments-config
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/resources/application.yml`
```yaml
spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    username: ${SPRING_DATASOURCE_USERNAME:shipments}
    password: ${SPRING_DATASOURCE_PASSWORD:shipments}
  jpa:
    hibernate:
      ddl-auto: validate
  artemis:
    broker-url: ${SPRING_ARTEMIS_BROKER_URL}
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${AUTH_ISSUER_URI}
app:
  security:
    enabled: ${APP_SECURITY_ENABLED:true}
pricing:
  base-url: ${PRICING_BASE_URL}
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/resources/db/migration/V1__init.sql`
```sql
create table shipments (id uuid primary key, reference varchar(50) not null, weight_kg numeric not null, country_code char(2) not null, status varchar(20) not null);
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/ShipmentController.java`
```java
package com.acme.shipments;

import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {
    private final ShipmentService service;

    public ShipmentController(ShipmentService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Shipment> create(@Valid @RequestBody ShipmentRequest request) {
        return ResponseEntity.status(201).body(service.create(request));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Shipment> get(@PathVariable UUID id) {
        return ResponseEntity.of(service.find(id));
    }
}
```
(`@PostMapping` is line 17, `@GetMapping("/{id}")` is line 22.)

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/ShipmentRequest.java`
```java
package com.acme.shipments;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public class ShipmentRequest {
    @NotBlank
    @Size(max = 50)
    private String reference;

    @NotNull
    @Positive
    private BigDecimal weightKg;

    @NotNull
    @Pattern(regexp = "^[A-Z]{2}$")
    private String countryCode;

    @Size(min = 3, max = 120)
    private String destination;
}
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/ShipmentService.java`
```java
package com.acme.shipments;

import java.math.BigDecimal;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class ShipmentService {
    private final ShipmentRepository repository;
    private final JmsTemplate jmsTemplate;
    private final RestTemplate restTemplate;

    @Value("${pricing.base-url}")
    private String pricingBaseUrl;

    public ShipmentService(ShipmentRepository repository, JmsTemplate jmsTemplate, RestTemplate restTemplate) {
        this.repository = repository;
        this.jmsTemplate = jmsTemplate;
        this.restTemplate = restTemplate;
    }

    public Shipment create(ShipmentRequest request) {
        if (request.getWeightKg().compareTo(new BigDecimal("1000")) > 0) {
            throw new IllegalArgumentException("weight exceeds 1000kg");
        }
        Rate rate = restTemplate.getForObject(pricingBaseUrl + "/rates/" + request.getCountryCode(), Rate.class);
        Shipment shipment = Shipment.from(request, rate);
        repository.save(shipment);
        jmsTemplate.convertAndSend("shipment.created", shipment.toEvent());
        return shipment;
    }

    public Optional<Shipment> find(UUID id) {
        return repository.findById(id);
    }
}
```
(`restTemplate.getForObject` is line 30, `repository.save(shipment)` is line 32, `jmsTemplate.convertAndSend` is line 33.)

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/ShipmentRepository.java`
```java
package com.acme.shipments;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ShipmentRepository extends JpaRepository<Shipment, UUID> {
}
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/Shipment.java`
```java
package com.acme.shipments;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "shipments")
public class Shipment {
    @Id
    private UUID id;
    private String reference;
    private String status;

    static Shipment from(ShipmentRequest request, Rate rate) {
        return new Shipment();
    }

    Object toEvent() {
        return this;
    }
}
```

`skills/karate-bootstrap/tests/fixtures/spring-mini/src/main/java/com/acme/shipments/ShipmentEventsListener.java`
```java
package com.acme.shipments;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class ShipmentEventsListener {
    private final ShipmentRepository repository;

    public ShipmentEventsListener(ShipmentRepository repository) {
        this.repository = repository;
    }

    @JmsListener(destination = "shipment.requested")
    public void onRequested(ShipmentRequest request) {
        repository.save(Shipment.from(request, null));
    }
}
```
(`@JmsListener` is line 14, `repository.save` is line 16.)

- [ ] **Step 4: Create `quarkus-mini`**

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/pom.xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.acme</groupId>
  <artifactId>invoices</artifactId>
  <version>1.0.0</version>
  <properties>
    <quarkus.platform.version>3.13.0</quarkus.platform.version>
  </properties>
  <dependencies>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-resteasy-reactive-jackson</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-hibernate-orm-panache</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-jdbc-postgresql</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-smallrye-reactive-messaging-amqp</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-hibernate-validator</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-rest-client-reactive-jackson</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-oidc</artifactId></dependency>
    <dependency><groupId>io.quarkus</groupId><artifactId>quarkus-smallrye-health</artifactId></dependency>
  </dependencies>
</project>
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/docker/Dockerfile.jvm`
```dockerfile
FROM registry.access.redhat.com/ubi9/openjdk-21:1.20
COPY target/quarkus-app/ /deployments/
EXPOSE 8080
USER 185
ENTRYPOINT ["java", "-jar", "/deployments/quarkus-run.jar"]
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/deployment.yml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoices
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: invoices
          image: registry.example/invoices:latest
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /q/health/ready
              port: http
          env:
            - name: QUARKUS_DATASOURCE_JDBC_URL
              value: jdbc:postgresql://db:5432/invoices
            - name: AMQP_HOST
              value: artemis
            - name: AMQP_PORT
              value: "5672"
            - name: ORDERS_API_URL
              value: http://orders:8080
            - name: OIDC_URL
              value: https://login.example/realms/acme
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/resources/application.properties`
```properties
quarkus.datasource.db-kind=postgresql
quarkus.datasource.jdbc.url=${QUARKUS_DATASOURCE_JDBC_URL}
quarkus.hibernate-orm.database.generation=none
amqp-host=${AMQP_HOST}
amqp-port=${AMQP_PORT}
mp.messaging.outgoing.invoice-created.connector=smallrye-amqp
mp.messaging.outgoing.invoice-created.address=invoice.created
mp.messaging.incoming.order-completed.connector=smallrye-amqp
mp.messaging.incoming.order-completed.address=order.completed
quarkus.rest-client.orders-api.url=${ORDERS_API_URL}
quarkus.oidc.enabled=${OIDC_ENABLED:true}
quarkus.oidc.auth-server-url=${OIDC_URL}
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/java/com/acme/invoices/InvoiceResource.java`
```java
package com.acme.invoices;

import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.Response;

@Path("/api/invoices")
public class InvoiceResource {
    @Inject
    InvoiceService service;

    @POST
    public Response create(@Valid InvoiceRequest request) {
        return Response.status(201).entity(service.create(request)).build();
    }

    @GET
    @Path("/{id}")
    public Invoice get(@PathParam("id") Long id) {
        return service.find(id);
    }
}
```
(`@POST` is line 13, `@GET` is line 18, its `@Path("/{id}")` is line 19.)

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/java/com/acme/invoices/InvoiceRequest.java`
```java
package com.acme.invoices;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public class InvoiceRequest {
    @NotNull
    public Long orderId;

    @NotNull
    @DecimalMin("0.01")
    public BigDecimal amount;

    @NotBlank
    @Size(max = 3)
    public String currency;
}
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/java/com/acme/invoices/InvoiceService.java`
```java
package com.acme.invoices;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.inject.Inject;
import jakarta.transaction.Transactional;
import org.eclipse.microprofile.reactive.messaging.Channel;
import org.eclipse.microprofile.reactive.messaging.Emitter;
import org.eclipse.microprofile.rest.client.inject.RestClient;

@ApplicationScoped
public class InvoiceService {
    @Inject
    @Channel("invoice-created")
    Emitter<InvoiceEvent> emitter;

    @Inject
    @RestClient
    OrdersClient ordersClient;

    @Transactional
    public Invoice create(InvoiceRequest request) {
        Order order = ordersClient.getOrder(request.orderId);
        if (order == null) {
            throw new NotFoundException("order " + request.orderId);
        }
        Invoice invoice = Invoice.from(request, order);
        invoice.persist();
        emitter.send(InvoiceEvent.of(invoice));
        return invoice;
    }

    public Invoice find(Long id) {
        return Invoice.findById(id);
    }
}
```
(`ordersClient.getOrder` is line 22, `invoice.persist()` is line 27, `emitter.send` is line 28.)

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/java/com/acme/invoices/Invoice.java`
```java
package com.acme.invoices;

import io.quarkus.hibernate.orm.panache.PanacheEntity;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice extends PanacheEntity {
    public Long orderId;
    public String currency;

    static Invoice from(InvoiceRequest request, Order order) {
        return new Invoice();
    }
}
```

`skills/karate-bootstrap/tests/fixtures/quarkus-mini/src/main/java/com/acme/invoices/OrderEventsConsumer.java`
```java
package com.acme.invoices;

import jakarta.enterprise.context.ApplicationScoped;
import jakarta.transaction.Transactional;
import org.eclipse.microprofile.reactive.messaging.Incoming;

@ApplicationScoped
public class OrderEventsConsumer {
    @Incoming("order-completed")
    @Transactional
    public void onOrderCompleted(OrderCompleted event) {
        Invoice invoice = Invoice.findById(event.invoiceId);
        invoice.currency = event.currency;
        invoice.persist();
    }
}
```
(`@Incoming` is line 9, `invoice.persist()` is line 14.)

- [ ] **Step 5: Create `dotnet-mini`**

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Deals.Api.csproj`
```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.8" />
    <PackageReference Include="Npgsql.EntityFrameworkCore.PostgreSQL" Version="8.0.4" />
    <PackageReference Include="Apache.NMS.AMQP" Version="2.2.0" />
    <PackageReference Include="FluentValidation.AspNetCore" Version="11.3.0" />
    <PackageReference Include="Microsoft.AspNetCore.Authentication.JwtBearer" Version="8.0.8" />
  </ItemGroup>
</Project>
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Dockerfile`
```dockerfile
FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY publish/ .
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080
ENTRYPOINT ["dotnet", "Deals.Api.dll"]
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/deployment.yml`
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
            - name: Pricing__BaseUrl
              value: http://pricing:8080
            - name: Auth__Enabled
              value: "true"
            - name: Auth__Authority
              value: https://login.example/realms/acme
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/appsettings.json`
```json
{
  "ConnectionStrings": {
    "Deals": "Host=localhost;Database=deals;Username=deals;Password=deals"
  },
  "Amq": {
    "Url": "amqp://localhost:5672",
    "User": "artemis",
    "Password": "artemis"
  },
  "Pricing": {
    "BaseUrl": "http://localhost:9010"
  },
  "Auth": {
    "Enabled": true,
    "Authority": "https://login.example/realms/acme",
    "Audience": "deals-api"
  }
}
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Program.cs`
```csharp
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddDbContext<DealsDbContext>(o => o.UseNpgsql(builder.Configuration.GetConnectionString("Deals")));
if (builder.Configuration.GetValue<bool>("Auth:Enabled"))
{
    builder.Services.AddAuthentication().AddJwtBearer(o => o.Authority = builder.Configuration["Auth:Authority"]);
}
var app = builder.Build();
app.MapHealthChecks("/health/ready");
app.MapControllers();
app.Run();
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Controllers/DealsController.cs`
```csharp
using Microsoft.AspNetCore.Mvc;

namespace Deals.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
public class DealsController : ControllerBase
{
    private readonly DealService _service;

    public DealsController(DealService service) => _service = service;

    [HttpPost]
    public async Task<ActionResult<Deal>> Create(DealRequest request)
    {
        var deal = await _service.CreateAsync(request);
        return CreatedAtAction(nameof(Get), new { id = deal.Id }, deal);
    }

    [HttpGet("{id:guid}")]
    public async Task<ActionResult<Deal>> Get(Guid id)
    {
        var deal = await _service.FindAsync(id);
        return deal is null ? NotFound() : Ok(deal);
    }
}
```
(`[HttpPost]` is line 13, `[HttpGet("{id:guid}")]` is line 20.)

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Validators/DealRequestValidator.cs`
```csharp
using FluentValidation;

namespace Deals.Api.Validators;

public class DealRequestValidator : AbstractValidator<DealRequest>
{
    public DealRequestValidator()
    {
        RuleFor(x => x.CounterpartyId).NotEmpty();
        RuleFor(x => x.Volume).GreaterThan(0);
        RuleFor(x => x.Product).NotEmpty().MaximumLength(20);
        RuleFor(x => x.ExternalId).Matches("^EXT-[0-9]{6}$");
    }
}
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Services/DealService.cs`
```csharp
using System.Net.Http.Json;
using Apache.NMS;

namespace Deals.Api.Services;

public class DealService
{
    private readonly DealsDbContext _db;
    private readonly HttpClient _http;
    private readonly IMessageProducer _producer;

    public DealService(DealsDbContext db, HttpClient http, IMessageProducer producer)
    {
        _db = db;
        _http = http;
        _producer = producer;
    }

    public async Task<Deal> CreateAsync(DealRequest request)
    {
        if (request.Volume > 1_000_000)
        {
            throw new InvalidOperationException("volume exceeds desk limit");
        }
        var price = await _http.GetFromJsonAsync<Price>($"/prices/{request.Product}");
        var deal = Deal.From(request, price);
        _db.Deals.Add(deal);
        await _db.SaveChangesAsync();
        _producer.Send(_producer.CreateTextMessage(deal.ToEventJson()));
        return deal;
    }

    public Task<Deal?> FindAsync(Guid id) => _db.Deals.FindAsync(id).AsTask();
}
```
(`GetFromJsonAsync` is line 25, `_db.Deals.Add` is line 27, `SaveChangesAsync` is line 28, `_producer.Send` is line 29.)

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Messaging/DealRequestedConsumer.cs`
```csharp
using Apache.NMS;

namespace Deals.Api.Messaging;

public class DealRequestedConsumer : BackgroundService
{
    private readonly ISession _session;
    private readonly DealsDbContext _db;

    public DealRequestedConsumer(ISession session, DealsDbContext db)
    {
        _session = session;
        _db = db;
    }

    protected override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var queue = _session.GetQueue("deal.requested");
        var consumer = _session.CreateConsumer(queue);
        consumer.Listener += OnMessage;
        return Task.CompletedTask;
    }

    private void OnMessage(IMessage message)
    {
        var deal = Deal.FromMessage(message);
        _db.Deals.Update(deal);
        _db.SaveChanges();
    }
}
```
(`_session.GetQueue("deal.requested")` is line 18, `consumer.Listener +=` is line 20, `_db.Deals.Update` is line 27, `SaveChanges()` is line 28.)

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Data/DealsDbContext.cs`
```csharp
using Microsoft.EntityFrameworkCore;

namespace Deals.Api.Data;

public class DealsDbContext : DbContext
{
    public DealsDbContext(DbContextOptions<DealsDbContext> options) : base(options) { }

    public DbSet<Deal> Deals => Set<Deal>();
}
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Data/Deal.cs`
```csharp
using System.ComponentModel.DataAnnotations.Schema;

namespace Deals.Api.Data;

[Table("deals")]
public class Deal
{
    public Guid Id { get; set; }
    public string CounterpartyId { get; set; } = "";
    public decimal Volume { get; set; }
    public string Product { get; set; } = "";
    public string ExternalId { get; set; } = "";

    public static Deal From(DealRequest request, Price? price) => new();
    public static Deal FromMessage(Apache.NMS.IMessage message) => new();
    public string ToEventJson() => "{}";
}
```

`skills/karate-bootstrap/tests/fixtures/dotnet-mini/Data/Migrations/20260101000000_Init.cs`
```csharp
using Microsoft.EntityFrameworkCore.Migrations;

namespace Deals.Api.Data.Migrations;

public partial class Init : Migration
{
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.CreateTable(name: "deals", columns: table => new { });
    }
}
```

- [ ] **Step 6: Create `fastapi-mini`**

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/pyproject.toml`
```toml
[project]
name = "orders"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.112",
  "uvicorn>=0.30",
  "sqlalchemy>=2.0",
  "psycopg[binary]>=3.2",
  "python-qpid-proton>=0.39",
  "httpx>=0.27",
  "pydantic>=2.8",
  "alembic>=1.13",
  "pyjwt>=2.9",
]
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/deployment.yml`
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
            - name: DATABASE_URL
              value: postgresql://orders:orders@db:5432/orders
            - name: AMQP_URL
              value: amqp://artemis:5672
            - name: INVENTORY_URL
              value: http://inventory:8080
            - name: AUTH_MODE
              value: jwt
            - name: JWKS_URL
              value: https://login.example/realms/acme/protocol/openid-connect/certs
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/settings.py`
```python
import os

DATABASE_URL = os.environ["DATABASE_URL"]
AMQP_URL = os.getenv("AMQP_URL", "amqp://localhost:5672")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:9020")
AUTH_MODE = os.getenv("AUTH_MODE", "jwt")
JWKS_URL = os.getenv("JWKS_URL", "")
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/main.py`
```python
from fastapi import FastAPI

from app import service
from app.schemas import OrderIn, OrderOut

app = FastAPI()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/orders", status_code=201)
def create_order(order: OrderIn) -> OrderOut:
    return service.create(order)


@app.get("/api/orders/{order_id}")
def get_order(order_id: int) -> OrderOut:
    return service.find(order_id)
```
(`@app.get("/healthz")` is line 9, `@app.post("/api/orders"...)` is line 14, `@app.get("/api/orders/{order_id}")` is line 19.)

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/schemas.py`
```python
from pydantic import BaseModel, Field


class OrderIn(BaseModel):
    sku: str = Field(..., min_length=3, max_length=20)
    quantity: int = Field(..., gt=0, le=100)
    customer_email: str = Field(..., pattern=r"^.+@.+$")
    note: str | None = None


class OrderOut(BaseModel):
    id: int
    sku: str
    quantity: int
    status: str
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/service.py`
```python
import httpx
from fastapi import HTTPException
from proton import Message

from app import settings
from app.models import Order
from app.schemas import OrderIn, OrderOut
from app.db import SessionLocal
from app.messaging import sender


def create(order_in: OrderIn) -> OrderOut:
    stock = httpx.get(f"{settings.INVENTORY_URL}/stock/{order_in.sku}").json()
    if stock["available"] < order_in.quantity:
        raise HTTPException(status_code=409, detail="insufficient stock")
    if order_in.quantity > 50 and not stock.get("bulk_allowed"):
        raise HTTPException(status_code=400, detail="bulk orders need approval")
    with SessionLocal() as session:
        order = Order(sku=order_in.sku, quantity=order_in.quantity, status="NEW")
        session.add(order)
        session.commit()
        sender.send(Message(body={"order_id": order.id, "sku": order.sku}))
        return OrderOut(id=order.id, sku=order.sku, quantity=order.quantity, status=order.status)


def find(order_id: int) -> OrderOut:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        return OrderOut(id=order.id, sku=order.sku, quantity=order.quantity, status=order.status)
```
(`httpx.get` is line 13, `session.add(order)` is line 20, `session.commit()` is line 21, `sender.send` is line 22.)

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/consumer.py`
```python
from proton.handlers import MessagingHandler
from proton.reactor import Container

from app import settings
from app.db import SessionLocal
from app.models import Order


class OrderRequestedHandler(MessagingHandler):
    def on_start(self, event):
        conn = event.container.connect(settings.AMQP_URL)
        event.container.create_receiver(conn, "order.requested")

    def on_message(self, event):
        payload = event.message.body
        with SessionLocal() as session:
            order = session.get(Order, payload["order_id"])
            order.status = "REQUESTED"
            session.commit()


def run() -> None:
    Container(OrderRequestedHandler()).run()
```
(`create_receiver(conn, "order.requested")` is line 12, `session.commit()` is line 19.)

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/app/models.py`
```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str]
    quantity: Mapped[int]
    status: Mapped[str]
```

`skills/karate-bootstrap/tests/fixtures/fastapi-mini/alembic/versions/0001_init.py`
```python
"""init"""

revision = "0001"
down_revision = None


def upgrade() -> None:
    pass
```

- [ ] **Step 7: Run the inventory test to verify it passes**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_fixtures.py -q`
Expected: `1 passed`.

- [ ] **Step 8: Check that ruff ignores fixture Python**

Run: `python -m ruff check skills/karate-bootstrap`
Expected: fixture `.py` files may be flagged (unused imports in `service.py`, missing annotations in `consumer.py`). Add to `pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["skills/*/tests/fixtures"]
```

Re-run. Expected: `All checks passed!`. Also confirm `python -m mypy` still passes (mypy `files` does not include tests, so fixtures are not checked).

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml skills/karate-bootstrap/tests
git commit -m "test(karate-bootstrap): four miniature fixture repos covering the supported stacks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: `markers.py` per-stack marker tables

**Confidence:** 90%. Regexes are the risk. Mitigation is in the tests: every regex is exercised against the exact fixture lines it must match and against one line it must not match. Later tasks reuse these tables, so any regex gap surfaces in Task 6, 8 or 9 tests, which point back here.

**Files:**
- Create: `skills/karate-bootstrap/scripts/markers.py`
- Create: `skills/karate-bootstrap/tests/test_kb_markers.py`

**Interfaces:**
- Produces:
  - `STACKS: tuple[str, ...] = ("spring", "quarkus", "aspnetcore", "python")`.
  - `KINDS: tuple[str, ...] = ("entry-http", "entry-amq", "db-write", "amq-publish", "http-out", "validation")`.
  - `@dataclass(frozen=True) class Marker: kind: str; pattern: re.Pattern[str]; tokens: tuple[str, ...]`.
  - `SOURCE_SUFFIXES: dict[str, tuple[str, ...]]`, `CHEAT_SHEET: dict[str, str]` (relative path under the skill dir, e.g. `reference/stack-spring.md`).
  - `markers_for(stack: str) -> tuple[Marker, ...]` raising `KbError(..., EXIT_UNSUPPORTED_STACK)` for unknown stacks.
  - `markers_of_kind(stack: str, kind: str) -> tuple[Marker, ...]`.
  - `tokens_for(stack: str, kind: str) -> tuple[str, ...]` (flattened tokens for verify-refs).

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_markers.py
from __future__ import annotations

import pytest

from kb_common import EXIT_UNSUPPORTED_STACK, KbError
from markers import (
    CHEAT_SHEET,
    KINDS,
    SOURCE_SUFFIXES,
    STACKS,
    markers_for,
    markers_of_kind,
    tokens_for,
)


def _matches(stack: str, kind: str, line: str) -> bool:
    return any(m.pattern.search(line) for m in markers_of_kind(stack, kind))


def test_every_stack_has_every_kind_and_metadata() -> None:
    for stack in STACKS:
        kinds = {m.kind for m in markers_for(stack)}
        assert kinds == set(KINDS), stack
        assert SOURCE_SUFFIXES[stack]
        assert CHEAT_SHEET[stack].startswith("reference/stack-")
        for kind in KINDS:
            assert tokens_for(stack, kind), (stack, kind)


def test_unknown_stack_raises_unsupported() -> None:
    with pytest.raises(KbError) as excinfo:
        markers_for("cobol")
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


@pytest.mark.parametrize(
    ("stack", "kind", "line"),
    [
        ("spring", "entry-http", "    @PostMapping"),
        ("spring", "entry-http", '    @GetMapping("/{id}")'),
        ("spring", "entry-amq", '    @JmsListener(destination = "shipment.requested")'),
        ("spring", "db-write", "        repository.save(shipment);"),
        ("spring", "amq-publish", '        jmsTemplate.convertAndSend("shipment.created", ev);'),
        ("spring", "http-out", "        Rate rate = restTemplate.getForObject(url, Rate.class);"),
        ("spring", "validation", "    @NotBlank"),
        ("quarkus", "entry-http", "    @POST"),
        ("quarkus", "entry-amq", '    @Incoming("order-completed")'),
        ("quarkus", "db-write", "        invoice.persist();"),
        ("quarkus", "amq-publish", "        emitter.send(InvoiceEvent.of(invoice));"),
        ("quarkus", "http-out", "    @RestClient"),
        ("quarkus", "validation", '    @DecimalMin("0.01")'),
        ("aspnetcore", "entry-http", "    [HttpPost]"),
        ("aspnetcore", "entry-http", '    [HttpGet("{id:guid}")]'),
        ("aspnetcore", "entry-http", 'app.MapGet("/ping", () => "pong");'),
        ("aspnetcore", "entry-amq", '        var queue = _session.GetQueue("deal.requested");'),
        ("aspnetcore", "db-write", "        await _db.SaveChangesAsync();"),
        ("aspnetcore", "db-write", "        _db.Deals.Add(deal);"),
        ("aspnetcore", "amq-publish", "        _producer.Send(_producer.CreateTextMessage(json));"),
        ("aspnetcore", "http-out", '        var price = await _http.GetFromJsonAsync<Price>($"/prices/{p}");'),
        ("aspnetcore", "validation", "        RuleFor(x => x.Volume).GreaterThan(0);"),
        ("python", "entry-http", '@app.post("/api/orders", status_code=201)'),
        ("python", "entry-http", '@router.get("/items/{item_id}")'),
        ("python", "entry-amq", '        event.container.create_receiver(conn, "order.requested")'),
        ("python", "db-write", "        session.add(order)"),
        ("python", "amq-publish", "        sender.send(Message(body=payload))"),
        ("python", "http-out", '    stock = httpx.get(f"{settings.INVENTORY_URL}/stock/{sku}").json()'),
        ("python", "validation", "    sku: str = Field(..., min_length=3, max_length=20)"),
    ],
)
def test_marker_matches_fixture_line(stack: str, kind: str, line: str) -> None:
    assert _matches(stack, kind, line)


@pytest.mark.parametrize(
    ("stack", "kind", "line"),
    [
        ("spring", "entry-http", "    private final ShipmentService service;"),
        ("spring", "db-write", "        return repository.findById(id);"),
        ("aspnetcore", "db-write", "    public Task<Deal?> FindAsync(Guid id) => _db.Deals.FindAsync(id).AsTask();"),
        ("python", "entry-http", "app = FastAPI()"),
        ("python", "db-write", "        order = session.get(Order, order_id)"),
    ],
)
def test_marker_ignores_non_matching_line(stack: str, kind: str, line: str) -> None:
    assert not _matches(stack, kind, line)


def test_spring_entry_http_captures_method_and_path() -> None:
    marker = markers_of_kind("spring", "entry-http")[0]
    match = marker.pattern.search('    @GetMapping("/{id}")')
    assert match is not None
    assert match.group(1) == "Get"
    assert match.group(2) == "/{id}"


def test_aspnetcore_entry_http_captures_attribute_route() -> None:
    marker = markers_of_kind("aspnetcore", "entry-http")[0]
    match = marker.pattern.search('    [HttpGet("{id:guid}")]')
    assert match is not None
    assert match.group(1) == "Get"
    assert match.group(2) == "{id:guid}"


def test_python_entry_http_captures_method_and_path() -> None:
    marker = markers_of_kind("python", "entry-http")[0]
    match = marker.pattern.search('@app.post("/api/orders", status_code=201)')
    assert match is not None
    assert match.group(1) == "post"
    assert match.group(2) == "/api/orders"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_markers.py -q`
Expected: `ModuleNotFoundError: No module named 'markers'`.

- [ ] **Step 3: Implement `markers.py`**

```python
# skills/karate-bootstrap/scripts/markers.py
"""Per-stack source markers shared by discover.py, flow_map.py and rules.py.

Each stack has one or more ``Marker`` per kind:

  entry-http   route declarations (group 1 = method, group 2 = path where the
               framework puts it on the same line; Quarkus paths come from a
               separate ``@Path`` line that discover.py resolves)
  entry-amq    message-listener declarations (group 1.. = destination)
  db-write     ORM or SQL write calls
  amq-publish  message-send calls
  http-out     outbound HTTP client use
  validation   declarative validation constraints

``tokens`` are plain substrings ``flow_map.py verify-refs`` accepts on or near
a ``via: file:line`` reference. They are deliberately looser than the regex so
a subagent's exit reference survives small formatting differences.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from kb_common import EXIT_UNSUPPORTED_STACK, KbError

STACKS: Final[tuple[str, ...]] = ("spring", "quarkus", "aspnetcore", "python")
KINDS: Final[tuple[str, ...]] = (
    "entry-http",
    "entry-amq",
    "db-write",
    "amq-publish",
    "http-out",
    "validation",
)

SOURCE_SUFFIXES: Final[dict[str, tuple[str, ...]]] = {
    "spring": (".java", ".kt"),
    "quarkus": (".java", ".kt"),
    "aspnetcore": (".cs",),
    "python": (".py",),
}

CHEAT_SHEET: Final[dict[str, str]] = {
    "spring": "reference/stack-spring.md",
    "quarkus": "reference/stack-quarkus.md",
    "aspnetcore": "reference/stack-aspnetcore.md",
    "python": "reference/stack-python.md",
}


@dataclass(frozen=True)
class Marker:
    kind: str
    pattern: re.Pattern[str]
    tokens: tuple[str, ...]


def _m(kind: str, pattern: str, *tokens: str) -> Marker:
    return Marker(kind, re.compile(pattern), tokens)


_BEAN_VALIDATION = (
    r"@(NotNull|NotBlank|NotEmpty|Size|Min|Max|DecimalMin|DecimalMax|Pattern|Email|"
    r"Positive|PositiveOrZero|Negative|NegativeOrZero|Past|Future|Digits|AssertTrue)\b"
)
_BEAN_TOKENS = (
    "@NotNull", "@NotBlank", "@NotEmpty", "@Size", "@Min", "@Max", "@DecimalMin",
    "@DecimalMax", "@Pattern", "@Email", "@Positive", "@Negative", "@Past", "@Future",
    "@Digits", "@AssertTrue",
)

MARKERS: Final[dict[str, tuple[Marker, ...]]] = {
    "spring": (
        _m(
            "entry-http",
            r'@(Get|Post|Put|Delete|Patch)Mapping(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?"([^"]*)")?',
            "Mapping",
        ),
        _m("entry-amq", r'@JmsListener\s*\(\s*destination\s*=\s*"([^"]+)"', "@JmsListener"),
        _m(
            "db-write",
            r"\.(save|saveAll|saveAndFlush|delete|deleteById|deleteAll|deleteAllById|persist|"
            r"merge|remove)\s*\(|@Modifying|jdbcTemplate\.(update|batchUpdate)\s*\(",
            ".save(", ".saveAll(", ".saveAndFlush(", ".delete", ".persist(", ".merge(",
            ".remove(", "@Modifying", "jdbcTemplate.update(", "jdbcTemplate.batchUpdate(",
        ),
        _m(
            "amq-publish",
            r"\.(convertAndSend|send)\s*\(",
            "convertAndSend(", ".send(",
        ),
        _m(
            "http-out",
            r"restTemplate\.|\bRestTemplate\b|\bWebClient\b|webClient\.|@FeignClient|\bRestClient\b",
            "restTemplate.", "RestTemplate", "WebClient", "webClient.", "@FeignClient",
            "RestClient",
        ),
        _m("validation", _BEAN_VALIDATION, *_BEAN_TOKENS),
    ),
    "quarkus": (
        _m("entry-http", r"@(GET|POST|PUT|DELETE|PATCH)\b", "@GET", "@POST", "@PUT",
           "@DELETE", "@PATCH"),
        _m("entry-amq", r'@Incoming\s*\(\s*"([^"]+)"', "@Incoming"),
        _m(
            "db-write",
            r"\.(persist|persistAndFlush|delete|deleteById|deleteAll|merge|remove)\s*\(|"
            r"\.update\s*\(\s*\"",
            ".persist(", ".persistAndFlush(", ".delete(", ".deleteById(", ".deleteAll(",
            ".merge(", ".remove(", ".update(",
        ),
        _m("amq-publish", r"\.send\s*\(|@Outgoing\s*\(", ".send(", "@Outgoing("),
        _m(
            "http-out",
            r"@RestClient\b|RestClientBuilder|\bWebClient\b|Client\.\w+\s*\(",
            "@RestClient", "RestClientBuilder", "WebClient", "Client.",
        ),
        _m("validation", _BEAN_VALIDATION, *_BEAN_TOKENS),
    ),
    "aspnetcore": (
        _m(
            "entry-http",
            r'\[Http(Get|Post|Put|Delete|Patch)(?:\s*\(\s*"([^"]*)"\s*\))?\]|'
            r'\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"',
            "[Http", ".Map",
        ),
        _m(
            "entry-amq",
            r'GetQueue\s*\(\s*"([^"]+)"|GetTopic\s*\(\s*"([^"]+)"|'
            r'ReceiveEndpoint\s*\(\s*"([^"]+)"|IConsumer<(\w+)>',
            "GetQueue(", "GetTopic(", "ReceiveEndpoint(", "IConsumer<", "Listener +=",
        ),
        _m(
            "db-write",
            r"SaveChanges(Async)?\s*\(|\.(Add|AddAsync|AddRange|AddRangeAsync|Update|"
            r"UpdateRange|Remove|RemoveRange)\s*\(|ExecuteSql(Raw|Interpolated)|"
            r"ExecuteUpdate|ExecuteDelete",
            "SaveChanges", ".Add(", ".AddAsync(", ".AddRange(", ".Update(", ".Remove(",
            ".RemoveRange(", "ExecuteSql", "ExecuteUpdate", "ExecuteDelete",
        ),
        _m(
            "amq-publish",
            r"\.(Send|SendAsync|Publish|PublishAsync)\s*\(|CreateProducer\s*\(",
            ".Send(", ".SendAsync(", ".Publish(", ".PublishAsync(", "CreateProducer(",
        ),
        _m(
            "http-out",
            r"\bHttpClient\b|\.(GetAsync|PostAsync|PutAsync|DeleteAsync|SendAsync|"
            r"GetFromJsonAsync|PostAsJsonAsync|PutAsJsonAsync|GetStringAsync)\s*[<(]",
            "HttpClient", ".GetAsync(", ".PostAsync(", ".PutAsync(", ".DeleteAsync(",
            ".SendAsync(", "FromJsonAsync", "AsJsonAsync", "GetStringAsync(",
        ),
        _m(
            "validation",
            r"RuleFor\s*\(|\[(Required|StringLength|Range|RegularExpression|MaxLength|"
            r"MinLength|EmailAddress|Url|Phone|Compare)\b",
            "RuleFor(", "[Required", "[StringLength", "[Range", "[RegularExpression",
            "[MaxLength", "[MinLength", "[EmailAddress", "[Url", "[Phone", "[Compare",
        ),
    ),
    "python": (
        _m(
            "entry-http",
            r"@\w+\.(get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)[\"']|"
            r"@\w+\.route\s*\(\s*[\"']([^\"']+)[\"']",
            "@app.", "@router.", ".route(",
        ),
        _m(
            "entry-amq",
            r"create_receiver\s*\([^,]+,\s*[\"']([^\"']+)[\"']|"
            r"\.subscribe\s*\(\s*destination\s*=\s*[\"']([^\"']+)[\"']",
            "create_receiver(", ".subscribe(",
        ),
        _m(
            "db-write",
            r"session\.(add|add_all|delete|merge|commit|flush)\s*\(|"
            r"\.execute\s*\(\s*[\"'](INSERT|UPDATE|DELETE)|\.commit\s*\(",
            "session.add(", "session.add_all(", "session.delete(", "session.merge(",
            ".commit(", ".flush(", ".execute(",
        ),
        _m("amq-publish", r"\.send\s*\(|\.publish\s*\(", ".send(", ".publish("),
        _m(
            "http-out",
            r"\b(httpx|requests|aiohttp)\.|\bhttpx\.(Async)?Client\b",
            "httpx.", "requests.", "aiohttp.",
        ),
        _m(
            "validation",
            r"\bField\s*\(|@(field_)?validator\b|\b(constr|conint|confloat|conlist|condecimal)\s*\(",
            "Field(", "validator", "constr(", "conint(", "confloat(", "conlist(", "condecimal(",
        ),
    ),
}


def markers_for(stack: str) -> tuple[Marker, ...]:
    try:
        return MARKERS[stack]
    except KeyError as err:
        raise KbError(
            f"unsupported stack {stack!r}; expected one of {', '.join(STACKS)}",
            EXIT_UNSUPPORTED_STACK,
        ) from err


def markers_of_kind(stack: str, kind: str) -> tuple[Marker, ...]:
    return tuple(m for m in markers_for(stack) if m.kind == kind)


def tokens_for(stack: str, kind: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for marker in markers_of_kind(stack, kind):
        tokens.extend(marker.tokens)
    return tuple(tokens)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_markers.py -q`
Expected: all pass. If a parametrised match case fails, fix the regex, not the test: the test lines are copied from the fixtures.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. Ruff E501 on a regex line means split it with implicit string concatenation as shown above.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/markers.py skills/karate-bootstrap/tests/test_kb_markers.py
git commit -m "feat(karate-bootstrap): per-stack source marker tables

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `detect.py` (Phase 0)

**Confidence:** 92%. Keyword detection over build files is simple. The toolchain check shells out to `shutil.which`, which is deterministic; tests bypass it with `--skip-toolchain`.

**Files:**
- Create: `skills/karate-bootstrap/scripts/detect.py`
- Create: `skills/karate-bootstrap/tests/test_kb_detect.py`

**Interfaces:**
- Consumes: `kb_common` (`KbError`, exit codes, `write_json`, `iter_files`, `rel`, `read_text`, `run_cli`).
- Produces:
  - `find_build_files(root: Path) -> list[Path]`.
  - `detect(root: Path) -> dict[str, Any]` returning keys `language, framework, build, orm, db, messaging, http_client, validation, auth, build_files` (framework is one of `STACKS`).
  - `check_toolchain() -> dict[str, Any]` returning `{"container_cli": "docker"|"podman", "java": True, "maven": True}` or raising `KbError(..., EXIT_TOOLCHAIN)`.
  - CLI: `python scripts/detect.py <repo> [--service-dir SUB] --out PATH [--skip-toolchain]`. Writes `stack.json` = `detect()` result plus `service_dir` and `toolchain`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_detect.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from detect import detect, find_build_files, main
from kb_common import EXIT_TOOLCHAIN, EXIT_UNSUPPORTED_STACK, KbError

FIXTURES = Path(__file__).parent / "fixtures"


def test_spring_mini() -> None:
    result = detect(FIXTURES / "spring-mini")
    assert result["framework"] == "spring"
    assert result["language"] == "java"
    assert result["build"] == "maven"
    assert result["orm"] == "hibernate-jpa"
    assert result["db"] == "postgres"
    assert result["messaging"] == "artemis-jms"
    assert result["http_client"] == "resttemplate"
    assert result["validation"] == "bean-validation"
    assert result["auth"] == "spring-security"
    assert result["build_files"] == ["pom.xml"]


def test_quarkus_mini() -> None:
    result = detect(FIXTURES / "quarkus-mini")
    assert result["framework"] == "quarkus"
    assert result["orm"] == "panache"
    assert result["db"] == "postgres"
    assert result["messaging"] == "smallrye-amqp"
    assert result["http_client"] == "quarkus-rest-client"
    assert result["validation"] == "bean-validation"
    assert result["auth"] == "quarkus-oidc"


def test_dotnet_mini() -> None:
    result = detect(FIXTURES / "dotnet-mini")
    assert result["framework"] == "aspnetcore"
    assert result["language"] == "csharp"
    assert result["build"] == "dotnet"
    assert result["orm"] == "efcore"
    assert result["db"] == "postgres"
    assert result["messaging"] == "nms-amqp"
    assert result["http_client"] == "httpclient"
    assert result["validation"] == "fluentvalidation"
    assert result["auth"] == "jwt-bearer"
    assert result["build_files"] == ["Deals.Api.csproj"]


def test_fastapi_mini() -> None:
    result = detect(FIXTURES / "fastapi-mini")
    assert result["framework"] == "python"
    assert result["language"] == "python"
    assert result["build"] == "pip"
    assert result["orm"] == "sqlalchemy"
    assert result["db"] == "postgres"
    assert result["messaging"] == "qpid-proton"
    assert result["http_client"] == "httpx"
    assert result["validation"] == "pydantic"
    assert result["auth"] == "pyjwt"


def test_unsupported_repo_raises(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/x\n", encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        detect(tmp_path)
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


def test_java_without_spring_or_quarkus_is_unsupported(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project><artifactId>lib</artifactId></project>", encoding="utf-8")
    with pytest.raises(KbError) as excinfo:
        detect(tmp_path)
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


def test_find_build_files_skips_ignored_and_deep_dirs(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "pom.xml").write_text("<project/>", encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert [p.name for p in find_build_files(tmp_path)] == ["pom.xml"]


def test_cli_writes_stack_json_with_service_dir(tmp_path: Path) -> None:
    out = tmp_path / "karate-tests" / "stack.json"
    code = main(
        [str(FIXTURES), "--service-dir", "dotnet-mini", "--out", str(out), "--skip-toolchain"]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["framework"] == "aspnetcore"
    assert data["service_dir"] == "dotnet-mini"
    assert data["toolchain"] == {"skipped": True}


def test_cli_toolchain_missing_exits_7(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import detect as detect_module

    monkeypatch.setattr(detect_module.shutil, "which", lambda _name: None)
    out = tmp_path / "stack.json"
    with pytest.raises(KbError) as excinfo:
        main([str(FIXTURES / "spring-mini"), "--out", str(out)])
    assert excinfo.value.exit_code == EXIT_TOOLCHAIN
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_detect.py -q`
Expected: `ModuleNotFoundError: No module named 'detect'`.

- [ ] **Step 3: Implement `detect.py`**

```python
# skills/karate-bootstrap/scripts/detect.py
"""Phase 0 of karate-bootstrap: preflight and stack detection.

Reads build files (pom.xml, build.gradle(.kts), *.csproj, pyproject.toml,
requirements*.txt) no deeper than three directories below the service root
and classifies the service by keyword. Writes ``stack.json``.

Usage:
    python scripts/detect.py <repo> [--service-dir SUB] --out karate-tests/stack.json
                             [--skip-toolchain]

Exit codes: 0 ok, 3 unsupported stack, 7 container runtime, java or mvn missing.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from kb_common import (
    DEFAULT_IGNORE,
    EXIT_OK,
    EXIT_TOOLCHAIN,
    EXIT_UNSUPPORTED_STACK,
    KbError,
    read_text,
    rel,
    run_cli,
    write_json,
)

BUILD_FILE_NAMES = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
)
MAX_DEPTH = 3


def find_build_files(root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                if child.name not in DEFAULT_IGNORE and depth < MAX_DEPTH:
                    walk(child, depth + 1)
            elif child.name in BUILD_FILE_NAMES or child.suffix == ".csproj":
                found.append(child)

    walk(root, 0)
    return found


def _first(text: str, table: tuple[tuple[str, str], ...], default: str | None) -> str | None:
    for needle, label in table:
        if needle in text:
            return label
    return default


def detect(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise KbError(f"service root not found: {root}")
    files = find_build_files(root)
    if not files:
        raise KbError(f"no supported build file under {root}", EXIT_UNSUPPORTED_STACK)
    text = "\n".join(read_text(f) for f in files).lower()
    names = {f.name for f in files}
    has_java = bool(names & {"pom.xml", "build.gradle", "build.gradle.kts"})
    has_csproj = any(f.suffix == ".csproj" for f in files)
    has_python = bool(names & {"pyproject.toml", "requirements.txt", "requirements-dev.txt",
                               "requirements.in"})

    if has_java and "quarkus" in text:
        framework, language = "quarkus", "java"
        build = "gradle" if "build.gradle" in " ".join(names) else "maven"
    elif has_java and "spring-boot" in text:
        framework, language = "spring", "java"
        build = "gradle" if "build.gradle" in " ".join(names) else "maven"
    elif has_csproj and ("microsoft.net.sdk.web" in text or "aspnetcore" in text):
        framework, language, build = "aspnetcore", "csharp", "dotnet"
    elif has_python and any(k in text for k in ("fastapi", "flask", "django")):
        framework, language, build = "python", "python", "pip"
    else:
        raise KbError(
            "no supported framework found (spring, quarkus, aspnetcore, python web)",
            EXIT_UNSUPPORTED_STACK,
        )

    orm = _first(text, (
        ("quarkus-hibernate-orm-panache", "panache"),
        ("hibernate", "hibernate-jpa"),
        ("spring-boot-starter-data-jpa", "hibernate-jpa"),
        ("entityframeworkcore", "efcore"),
        ("sqlalchemy", "sqlalchemy"),
        ("django", "django-orm"),
    ), None)
    db = _first(text, (
        ("postgresql", "postgres"),
        ("npgsql", "postgres"),
        ("psycopg", "postgres"),
        ("asyncpg", "postgres"),
    ), None)
    messaging = _first(text, (
        ("smallrye-reactive-messaging-amqp", "smallrye-amqp"),
        ("quarkus-artemis", "artemis-jms"),
        ("spring-boot-starter-artemis", "artemis-jms"),
        ("artemis-jms-client", "artemis-jms"),
        ("spring-jms", "artemis-jms"),
        ("apache.nms.amqp", "nms-amqp"),
        ("apache.nms.activemq", "nms-openwire"),
        ("amqpnetlite", "amqpnetlite"),
        ("masstransit", "masstransit"),
        ("python-qpid-proton", "qpid-proton"),
        ("stomp.py", "stomp"),
        ("stomp-py", "stomp"),
    ), None)
    http_default = {"spring": "resttemplate", "aspnetcore": "httpclient"}.get(framework)
    http_client = _first(text, (
        ("quarkus-rest-client", "quarkus-rest-client"),
        ("openfeign", "feign"),
        ("spring-boot-starter-webflux", "webclient"),
        ("httpx", "httpx"),
        ("requests", "requests"),
        ("aiohttp", "aiohttp"),
    ), http_default)
    validation_default = {"aspnetcore": "data-annotations"}.get(framework)
    validation = _first(text, (
        ("quarkus-hibernate-validator", "bean-validation"),
        ("spring-boot-starter-validation", "bean-validation"),
        ("fluentvalidation", "fluentvalidation"),
        ("pydantic", "pydantic"),
    ), validation_default)
    auth = _first(text, (
        ("quarkus-oidc", "quarkus-oidc"),
        ("spring-boot-starter-oauth2-resource-server", "spring-security"),
        ("spring-boot-starter-security", "spring-security"),
        ("authentication.jwtbearer", "jwt-bearer"),
        ("pyjwt", "pyjwt"),
        ("python-jose", "python-jose"),
        ("authlib", "authlib"),
    ), None)

    return {
        "language": language,
        "framework": framework,
        "build": build,
        "orm": orm,
        "db": db,
        "messaging": messaging,
        "http_client": http_client,
        "validation": validation,
        "auth": auth,
        "build_files": [rel(f, root) for f in files],
    }


def check_toolchain() -> dict[str, Any]:
    container_cli = next((c for c in ("docker", "podman") if shutil.which(c)), None)
    missing: list[str] = []
    if container_cli is None:
        missing.append("docker or podman")
    if not shutil.which("java"):
        missing.append("java")
    if not shutil.which("mvn"):
        missing.append("mvn")
    if missing:
        raise KbError("toolchain missing: " + ", ".join(missing), EXIT_TOOLCHAIN)
    return {"container_cli": container_cli, "java": True, "maven": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect the service stack and write stack.json")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-toolchain", action="store_true",
                        help="Do not check for docker/podman, java and mvn")
    args = parser.parse_args(argv)

    root = args.repo / args.service_dir if args.service_dir else args.repo
    toolchain = {"skipped": True} if args.skip_toolchain else check_toolchain()
    result = detect(root)
    result["service_dir"] = args.service_dir
    result["toolchain"] = toolchain
    write_json(args.out, result)
    print(f"stack: {result['framework']} ({result['language']}) -> {args.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_detect.py -q`
Expected: `9 passed`. Note `test_cli_toolchain_missing_exits_7` calls `main` directly so `KbError` propagates; `run_cli` is what maps it to exit 7 at the process boundary.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/detect.py skills/karate-bootstrap/tests/test_kb_detect.py
git commit -m "feat(karate-bootstrap): detect.py stack detection and toolchain preflight

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 5: `discover.py` part A: manifests, Dockerfile, app config, roles, auth

**Confidence:** 88%. Risk is the variety of config formats. Mitigation: every parser is a pure function tested against the four fixtures, and unknown keys fall through to `passthrough` rather than failing. The role heuristics are ordered (db, amq, auth, downstream, passthrough) and the tests pin one key per role per fixture, so a reordering regression is caught.

**Files:**
- Create: `skills/karate-bootstrap/scripts/discover.py` (part A functions only; Task 6 appends the rest)
- Create: `skills/karate-bootstrap/tests/test_kb_discover.py` (part A tests; Task 6 appends)

**Interfaces:**
- Consumes: `kb_common` (`read_yaml_docs`, `read_text`, `iter_files`, `rel`, `KbError`).
- Produces (all pure, all take the service root as `root: Path`):
  - `find_manifests(root) -> list[tuple[Path, bool]]` ordered `deployment.yml`, `deploymentserverless.yml`, generic fallback; bool is `serverless`.
  - `parse_manifest(path, root, serverless) -> dict[str, Any]` with keys `source, serverless, port, readiness, env, env_from`. `readiness` is `{"path", "port", "source"}` or `None`. `env` maps name to value or `None` when `valueFrom` is used.
  - `find_dockerfile(root) -> Path | None`, `parse_dockerfile(path) -> dict[str, Any]` with `expose: int | None`, `env: dict[str, str]`.
  - `parse_app_config(root) -> dict[str, dict[str, Any]]` mapping config key to `{"placeholder": str, "source": str, "env_var": str | None}`.
  - `assign_role(key: str, placeholder: str) -> str` returning `db | amq | auth | downstream:<name> | passthrough`.
  - `downstream_name(key: str) -> str`.
  - `detect_auth_switch(keys) -> dict[str, Any] | None` and `detect_auth(keys, stack_auth: str | None) -> dict[str, Any]` where `keys` is the merged `{key: {"placeholder", "source", "env_var", "role"}}` mapping. Result modes: `disabled`, `jwks`, `none`, `blocked`.

- [ ] **Step 1: Write the failing tests (part A)**

```python
# skills/karate-bootstrap/tests/test_kb_discover.py
from __future__ import annotations

from pathlib import Path

from discover import (
    assign_role,
    detect_auth,
    detect_auth_switch,
    downstream_name,
    find_dockerfile,
    find_manifests,
    parse_app_config,
    parse_dockerfile,
    parse_manifest,
)

FIXTURES = Path(__file__).parent / "fixtures"


def line_of(path: Path, needle: str) -> int:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found in {path}")


def test_find_manifests_prefers_named_files() -> None:
    spring = find_manifests(FIXTURES / "spring-mini")
    assert [(p.name, s) for p, s in spring] == [("deploymentserverless.yml", True)]
    quarkus = find_manifests(FIXTURES / "quarkus-mini")
    assert [(p.name, s) for p, s in quarkus] == [("deployment.yml", False)]


def test_find_manifests_generic_fallback(tmp_path: Path) -> None:
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "svc.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n"
        "      containers:\n        - name: x\n          ports:\n            - containerPort: 9000\n",
        encoding="utf-8",
    )
    assert [(p.name, s) for p, s in find_manifests(tmp_path)] == [("svc.yaml", False)]


def test_parse_knative_manifest() -> None:
    root = FIXTURES / "spring-mini"
    result = parse_manifest(root / "deploymentserverless.yml", root, serverless=True)
    assert result["serverless"] is True
    assert result["port"] == 8080
    assert result["readiness"] == {
        "path": "/actuator/health/readiness",
        "port": 8080,
        "source": "deploymentserverless.yml",
    }
    assert result["env"]["SPRING_DATASOURCE_URL"] is None
    assert result["env"]["SPRING_ARTEMIS_BROKER_URL"] == "tcp://artemis:61616"
    assert result["env_from"] == ["shipments-config"]


def test_parse_deployment_resolves_named_probe_port() -> None:
    root = FIXTURES / "quarkus-mini"
    result = parse_manifest(root / "deployment.yml", root, serverless=False)
    assert result["readiness"]["port"] == 8080
    assert result["readiness"]["path"] == "/q/health/ready"
    assert result["env"]["AMQP_PORT"] == "5672"


def test_find_and_parse_dockerfile() -> None:
    spring = find_dockerfile(FIXTURES / "spring-mini")
    assert spring is not None and spring.name == "Dockerfile"
    quarkus = find_dockerfile(FIXTURES / "quarkus-mini")
    assert quarkus is not None and quarkus.name == "Dockerfile.jvm"
    parsed = parse_dockerfile(FIXTURES / "dotnet-mini" / "Dockerfile")
    assert parsed == {"expose": 8080, "env": {"ASPNETCORE_URLS": "http://+:8080"}}
    spring_parsed = parse_dockerfile(FIXTURES / "spring-mini" / "Dockerfile")
    assert spring_parsed["env"] == {"JAVA_OPTS": "-Xmx512m"}


def test_parse_app_config_spring_yaml_extracts_env_vars() -> None:
    keys = parse_app_config(FIXTURES / "spring-mini")
    assert keys["spring.datasource.url"]["env_var"] == "SPRING_DATASOURCE_URL"
    assert keys["spring.datasource.username"]["env_var"] == "SPRING_DATASOURCE_USERNAME"
    assert keys["spring.jpa.hibernate.ddl-auto"]["placeholder"] == "validate"
    assert keys["app.security.enabled"]["env_var"] == "APP_SECURITY_ENABLED"
    assert keys["app.security.enabled"]["source"] == "src/main/resources/application.yml"


def test_parse_app_config_quarkus_properties() -> None:
    keys = parse_app_config(FIXTURES / "quarkus-mini")
    assert keys["quarkus.oidc.enabled"]["env_var"] == "OIDC_ENABLED"
    assert keys["mp.messaging.incoming.order-completed.address"]["placeholder"] == "order.completed"
    assert keys["quarkus.hibernate-orm.database.generation"]["placeholder"] == "none"


def test_parse_app_config_appsettings_uses_double_underscore() -> None:
    keys = parse_app_config(FIXTURES / "dotnet-mini")
    assert keys["ConnectionStrings__Deals"]["placeholder"].startswith("Host=localhost")
    assert keys["Auth__Enabled"]["placeholder"] == "true"
    assert keys["Pricing__BaseUrl"]["placeholder"] == "http://localhost:9010"


def test_parse_app_config_python_settings_reads_environ() -> None:
    keys = parse_app_config(FIXTURES / "fastapi-mini")
    assert keys["DATABASE_URL"]["env_var"] == "DATABASE_URL"
    assert keys["AMQP_URL"]["placeholder"] == "amqp://localhost:5672"
    assert keys["AUTH_MODE"]["placeholder"] == "jwt"


def test_assign_role_covers_each_role() -> None:
    assert assign_role("SPRING_DATASOURCE_URL", "") == "db"
    assert assign_role("ConnectionStrings__Deals", "Host=localhost;Database=deals") == "db"
    assert assign_role("DATABASE_URL", "postgresql://x") == "db"
    assert assign_role("SPRING_ARTEMIS_BROKER_URL", "tcp://artemis:61616") == "amq"
    assert assign_role("Amq__Url", "amqp://localhost:5672") == "amq"
    assert assign_role("AMQP_PORT", "5672") == "amq"
    assert assign_role("mp.messaging.incoming.order-completed.address", "order.completed") == "amq"
    assert assign_role("AUTH_ISSUER_URI", "https://login.example/realms/acme") == "auth"
    assert assign_role("quarkus.oidc.auth-server-url", "") == "auth"
    assert assign_role("JWKS_URL", "") == "auth"
    assert assign_role("PRICING_BASE_URL", "http://pricing:8080") == "downstream:pricing"
    assert assign_role("quarkus.rest-client.orders-api.url", "") == "downstream:orders-api"
    assert assign_role("INVENTORY_URL", "") == "downstream:inventory"
    assert assign_role("spring.jpa.hibernate.ddl-auto", "validate") == "passthrough"
    assert assign_role("JAVA_OPTS", "-Xmx512m") == "passthrough"


def test_downstream_name_strips_noise() -> None:
    assert downstream_name("Pricing__BaseUrl") == "pricing"
    assert downstream_name("PRICING_BASE_URL") == "pricing"
    assert downstream_name("quarkus.rest-client.orders-api.url") == "orders-api"
    assert downstream_name("INVENTORY_URL") == "inventory"


def _keys(*items: tuple[str, str, str | None]) -> dict[str, dict[str, object]]:
    return {
        key: {"placeholder": placeholder, "source": "test", "env_var": env_var,
              "role": assign_role(key, placeholder)}
        for key, placeholder, env_var in items
    }


def test_detect_auth_switch_prefers_env_var_and_flips_enabled() -> None:
    switch = detect_auth_switch(_keys(("app.security.enabled", "${APP_SECURITY_ENABLED:true}",
                                       "APP_SECURITY_ENABLED")))
    assert switch == {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false",
                      "confirmed": True}


def test_detect_auth_switch_mode_key_is_unconfirmed() -> None:
    switch = detect_auth_switch(_keys(("AUTH_MODE", "jwt", "AUTH_MODE")))
    assert switch == {"mode": "disabled", "key": "AUTH_MODE", "value": "disabled",
                      "confirmed": False}


def test_detect_auth_jwks_when_no_switch() -> None:
    result = detect_auth(_keys(("AUTH_ISSUER_URI", "https://login.example", "AUTH_ISSUER_URI")),
                         "spring-security")
    assert result == {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}


def test_detect_auth_none_without_library() -> None:
    assert detect_auth(_keys(("PRICING_BASE_URL", "http://p", None)), None) == {"mode": "none"}


def test_detect_auth_blocked_when_library_but_no_keys() -> None:
    assert detect_auth(_keys(("PRICING_BASE_URL", "http://p", None)), "jwt-bearer") == {
        "mode": "blocked"
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_discover.py -q`
Expected: `ModuleNotFoundError: No module named 'discover'`.

- [ ] **Step 3: Implement part A of `discover.py`**

```python
# skills/karate-bootstrap/scripts/discover.py
"""Phase 1 of karate-bootstrap: discover what the harness must know before tracing.

Deterministic reads, in order: the OpenShift manifest (``deployment.yml`` then
``deploymentserverless.yml``, generic Deployment as fallback), the Dockerfile,
application config files, and route declarations from ``markers.py``. Writes
``env-map.json`` (config keys with roles, port, readiness, auth mode) and a
seeded ``flow-map.yaml`` with one untraced entry per entry point.

Usage:
    python scripts/discover.py <repo> --stack karate-tests/stack.json \
        --out-env karate-tests/env-map.json --out-ledger karate-tests/flow-map.yaml \
        [--service-dir SUB]

Exit codes: 0 ok, 2 when no manifest, Dockerfile or entry point can be found,
5 when stack.json is missing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kb_common import KbError, iter_files, read_text, read_yaml_docs, rel

# Task 6 extends this import block with: argparse, sys, EXIT_OK, LEDGER_VERSION,
# read_json, require_file, run_cli, write_json, write_yaml from kb_common and
# CHEAT_SHEET, SOURCE_SUFFIXES, markers_of_kind from markers.

MANIFEST_NAMES: tuple[tuple[str, bool], ...] = (
    ("deployment.yml", False),
    ("deploymentserverless.yml", True),
)
DOCKERFILE_CANDIDATES = (
    "Dockerfile",
    "Containerfile",
    "docker/Dockerfile",
    "src/main/docker/Dockerfile.jvm",
    "src/main/docker/Dockerfile.native",
)
DEFAULT_PORT = {"python": 8000}

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.\-]*)(?::([^}]*))?\}")
_ENV_READ_RE = re.compile(
    r"^(\w+)\s*=\s*os\.(?:environ\[|environ\.get\(|getenv\()\s*[\"'](\w+)[\"']"
    r"(?:\s*,\s*[\"']([^\"']*)[\"'])?"
)
_XML_PROP_RE = re.compile(r'<property\s+name="([^"]+)"(?:\s+value="([^"]*)")?\s*/?>([^<]*)')
_DOCKER_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(\d+)", re.IGNORECASE)
_DOCKER_ENV_RE = re.compile(r"^\s*ENV\s+([A-Za-z_][A-Za-z0-9_]*)(?:=|\s+)(.*)$", re.IGNORECASE)


# --- manifests -----------------------------------------------------------------


def _find_containers(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        containers = node.get("containers")
        if isinstance(containers, list) and containers and isinstance(containers[0], dict):
            return [c for c in containers if isinstance(c, dict)]
        for value in node.values():
            found = _find_containers(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_containers(item)
            if found:
                return found
    return []


def _is_workload(doc: dict[str, Any]) -> bool:
    kind = str(doc.get("kind", ""))
    api = str(doc.get("apiVersion", ""))
    return kind in {"Deployment", "DeploymentConfig", "StatefulSet"} or (
        kind == "Service" and api.startswith("serving.knative.dev")
    )


def find_manifests(root: Path) -> list[tuple[Path, bool]]:
    found: list[tuple[Path, bool]] = []
    for name, serverless in MANIFEST_NAMES:
        direct = root / name
        if direct.is_file():
            found.append((direct, serverless))
            continue
        for candidate in iter_files(root, (".yml", ".yaml")):
            if candidate.name == name:
                found.append((candidate, serverless))
                break
    if found:
        return found
    for candidate in iter_files(root, (".yml", ".yaml")):
        try:
            docs = read_yaml_docs(candidate)
        except Exception:  # any unparsable YAML is simply not a manifest
            continue
        for doc in docs:
            if _is_workload(doc):
                knative = str(doc.get("apiVersion", "")).startswith("serving.knative.dev")
                return [(candidate, knative)]
    return []


def parse_manifest(path: Path, root: Path, serverless: bool) -> dict[str, Any]:
    containers: list[dict[str, Any]] = []
    for doc in read_yaml_docs(path):
        containers = _find_containers(doc)
        if containers:
            break
    if not containers:
        raise KbError(f"{rel(path, root)}: no containers found")
    container = containers[0]
    ports = [p for p in container.get("ports", []) if isinstance(p, dict)]
    port_by_name = {p.get("name"): p.get("containerPort") for p in ports if p.get("name")}
    port = next((int(p["containerPort"]) for p in ports if "containerPort" in p), None)

    readiness: dict[str, Any] | None = None
    probe = container.get("readinessProbe") or {}
    http_get = probe.get("httpGet") if isinstance(probe, dict) else None
    if isinstance(http_get, dict) and "path" in http_get:
        raw_port = http_get.get("port", port)
        resolved = port_by_name.get(raw_port, raw_port) if isinstance(raw_port, str) else raw_port
        readiness = {
            "path": str(http_get["path"]),
            "port": int(resolved) if resolved is not None else port,
            "source": rel(path, root),
        }

    env: dict[str, str | None] = {}
    for item in container.get("env", []) or []:
        if isinstance(item, dict) and "name" in item:
            value = item.get("value")
            env[str(item["name"])] = None if value is None else str(value)
    env_from: list[str] = []
    for item in container.get("envFrom", []) or []:
        if not isinstance(item, dict):
            continue
        for ref_key in ("configMapRef", "secretRef"):
            ref = item.get(ref_key)
            if isinstance(ref, dict) and "name" in ref:
                env_from.append(str(ref["name"]))
    return {
        "source": rel(path, root),
        "serverless": serverless,
        "port": port,
        "readiness": readiness,
        "env": env,
        "env_from": env_from,
    }


# --- Dockerfile ------------------------------------------------------------------


def find_dockerfile(root: Path) -> Path | None:
    for candidate in DOCKERFILE_CANDIDATES:
        path = root / candidate
        if path.is_file():
            return path
    return None


def parse_dockerfile(path: Path) -> dict[str, Any]:
    expose: int | None = None
    env: dict[str, str] = {}
    for line in read_text(path).splitlines():
        exposed = _DOCKER_EXPOSE_RE.match(line)
        if exposed and expose is None:
            expose = int(exposed.group(1))
            continue
        env_match = _DOCKER_ENV_RE.match(line)
        if env_match:
            env[env_match.group(1)] = env_match.group(2).strip().strip('"').strip("'")
    return {"expose": expose, "env": env}


# --- application config ----------------------------------------------------------


def _flatten(prefix: str, node: Any, sep: str, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten(f"{prefix}{sep}{key}" if prefix else str(key), value, sep, out)
    elif isinstance(node, list):
        out[prefix] = json.dumps(node)
    elif isinstance(node, bool):
        out[prefix] = "true" if node else "false"
    elif node is None:
        out[prefix] = ""
    else:
        out[prefix] = str(node)


def _env_var_of(placeholder: str) -> str | None:
    match = _PLACEHOLDER_RE.search(placeholder)
    return match.group(1) if match else None


def _record(out: dict[str, dict[str, Any]], key: str, placeholder: str, source: str,
            env_var: str | None = None) -> None:
    if key in out:
        return
    out[key] = {
        "placeholder": placeholder,
        "source": source,
        "env_var": env_var if env_var is not None else _env_var_of(placeholder),
    }


def parse_app_config(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in iter_files(root, (".yml", ".yaml", ".properties", ".json", ".py", ".xml",
                                  ".example")):
        name = path.name
        source = rel(path, root)
        if name.startswith("application") and path.suffix in (".yml", ".yaml"):
            flat: dict[str, str] = {}
            for doc in read_yaml_docs(path):
                _flatten("", doc, ".", flat)
            for key, value in flat.items():
                _record(out, key, value, source)
        elif name.startswith("application") and path.suffix == ".properties":
            for line in read_text(path).splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                _record(out, key.strip(), value.strip(), source)
        elif name.startswith("appsettings") and path.suffix == ".json":
            flat = {}
            _flatten("", json.loads(read_text(path)), "__", flat)
            for key, value in flat.items():
                _record(out, key, value, source)
        elif name == "settings.py" or name == "config.py":
            for line in read_text(path).splitlines():
                match = _ENV_READ_RE.match(line.strip())
                if match:
                    _record(out, match.group(2), match.group(3) or "", source, match.group(2))
        elif name == ".env.example":
            for line in read_text(path).splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    _record(out, key.strip(), value.strip(), source, key.strip())
        elif name in ("hibernate.cfg.xml", "persistence.xml"):
            for match in _XML_PROP_RE.finditer(read_text(path)):
                value = match.group(2) if match.group(2) is not None else match.group(3).strip()
                _record(out, match.group(1), value, source)
    return out


# --- roles and auth ---------------------------------------------------------------

_DB_KEY = ("datasource", "connectionstrings", "database_url", "jdbc", "db_url", "db-url",
           "hibernate.connection", "pghost", "pgdatabase")
_DB_VAL = ("jdbc:", "postgres", "host=")
_AMQ_KEY = ("artemis", "amqp", "activemq", "broker", "jms", "amq_", "amq__", "amq.",
            "mp.messaging", "stomp")
_AMQ_VAL = ("amqp://", "amqps://", "tcp://", "activemq:", "failover:", "stomp://")
_AUTH_KEY = ("oidc", "jwt", "jwks", "issuer", "authority", "auth", "security", "oauth")
_URL_SUFFIX = ("url", "uri", "baseurl", "base-url", "base_url", "endpoint", "host")
_NAME_NOISE = {"quarkus", "spring", "app", "rest", "client", "rest-client", "api", "base",
               "url", "uri", "baseurl", "endpoint", "host", "service", "svc", ""}
# Runtime knobs that look like URLs or hosts but only describe the app's own listener.
_PASSTHROUGH_KEYS = {"aspnetcore_urls", "aspnetcore_http_ports", "java_opts", "java_tool_options",
                     "port", "server_port", "server.port", "quarkus.http.port", "quarkus_http_port",
                     "uvicorn_port", "host", "server.address"}


def assign_role(key: str, placeholder: str) -> str:
    k = key.lower()
    v = placeholder.lower()
    if k in _PASSTHROUGH_KEYS:
        return "passthrough"
    if any(s in v for s in _DB_VAL) or any(s in k for s in _DB_KEY):
        return "db"
    if any(s in v for s in _AMQ_VAL) or any(s in k for s in _AMQ_KEY):
        return "amq"
    if any(s in k for s in _AUTH_KEY):
        return "auth"
    if v.startswith(("http://", "https://")) or any(k.endswith(s) for s in _URL_SUFFIX):
        return f"downstream:{downstream_name(key)}"
    return "passthrough"


def downstream_name(key: str) -> str:
    parts = re.split(r"__|[._:/]|(?<=[a-z])(?=[A-Z])", key)
    words: list[str] = []
    for part in parts:
        for word in part.split("_"):
            lowered = word.lower()
            if lowered not in _NAME_NOISE:
                words.append(lowered)
    return "-".join(words) if words else key.lower()


def detect_auth_switch(keys: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key, info in keys.items():
        k = re.sub(r"[-_.]", "", key.lower())
        if not re.search(r"auth|security|oidc|jwt", k):
            continue
        env_key = str(info.get("env_var") or key)
        if k.endswith("enabled"):
            return {"mode": "disabled", "key": env_key, "value": "false", "confirmed": True}
        if k.endswith("disabled"):
            return {"mode": "disabled", "key": env_key, "value": "true", "confirmed": True}
        if k.endswith("mode"):
            return {"mode": "disabled", "key": env_key, "value": "disabled", "confirmed": False}
    return None


def detect_auth(keys: dict[str, dict[str, Any]], stack_auth: str | None) -> dict[str, Any]:
    switch = detect_auth_switch(keys)
    if switch is not None:
        return switch
    if stack_auth is None:
        return {"mode": "none"}
    jwks_keys = sorted(
        str(info.get("env_var") or key)
        for key, info in keys.items()
        if info.get("role") == "auth"
        and re.search(r"jwks|issuer|authority|auth-server-url|oidc.*url", key.lower())
    )
    if jwks_keys:
        return {"mode": "jwks", "keys": jwks_keys}
    return {"mode": "blocked"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_discover.py -q`
Expected: all pass. `test_find_manifests_prefers_named_files` proves the Knative path; `test_parse_deployment_resolves_named_probe_port` proves named-port resolution.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. The part-A import block above only names what part A uses, so no F401 is expected. If ruff reports one, remove the import rather than adding `# noqa`.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/tests/test_kb_discover.py
git commit -m "feat(karate-bootstrap): discover manifests, Dockerfile, app config, roles and auth mode

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: `discover.py` part B: entry points, migrations, env-map, seeded ledger, CLI

**Confidence:** 85%. Entry-point discovery needs per-stack prefix handling (Spring `@RequestMapping`, JAX-RS class `@Path`, ASP.NET `[Route("api/[controller]")]`, FastAPI router prefix) and Quarkus channel-to-address resolution. Mitigation: each is a small function with a fixture test, and the ledger seeding test checks the exact id set per fixture so a missed or duplicated route fails loudly.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/discover.py` (append)
- Modify: `skills/karate-bootstrap/tests/test_kb_discover.py` (append)

**Interfaces:**
- Consumes: Task 5 functions, `markers.markers_of_kind`, `markers.SOURCE_SUFFIXES`, `markers.CHEAT_SHEET`.
- Produces:
  - `join_path(prefix: str, path: str) -> str` (normalised, leading slash, route constraints stripped).
  - `find_entry_points(root: Path, stack: str, config: dict[str, dict[str, Any]]) -> list[dict[str, Any]]`. HTTP entries: `{"id": "POST /api/x", "kind": "http", "method", "path", "handler": "rel:line"}`. AMQ entries: `{"id": "amq <destination>", "kind": "amq-subscribe", "destination", "channel" (optional), "handler"}`.
  - `detect_migrations(root, stack, config) -> dict[str, Any]` with `strategy: "migration-container"`, `image: None`, `source: None`, `repo_migrations: list[str]`, `also_on_boot: bool`.
  - `build_env_map(stack_info, manifest, dockerfile, config) -> dict[str, Any]` with keys `manifest, port, readiness, auth, keys` (`keys` is a list sorted by key of `{key, role, placeholder, source, env_var}`).
  - `seed_ledger(stack_info, env_map, entries, migrations, repo_name, dockerfile_rel) -> dict[str, Any]` per spec section 6 with every status flag `False`.
  - CLI `main(argv) -> int`.

- [ ] **Step 1: Append the failing tests (part B)**

```python
# append to skills/karate-bootstrap/tests/test_kb_discover.py
from detect import detect  # noqa: E402
from discover import (  # noqa: E402
    build_env_map,
    detect_migrations,
    find_entry_points,
    join_path,
    main,
    seed_ledger,
)
from kb_common import read_yaml  # noqa: E402


def _config(repo: str) -> dict[str, dict[str, object]]:
    return parse_app_config(FIXTURES / repo)


def test_join_path_normalises() -> None:
    assert join_path("/api/shipments", "") == "/api/shipments"
    assert join_path("/api/shipments", "/{id}") == "/api/shipments/{id}"
    assert join_path("api/deals", "{id:guid}") == "/api/deals/{id}"
    assert join_path("", "/healthz") == "/healthz"
    assert join_path("/api/", "/x/") == "/api/x"


def test_spring_entry_points() -> None:
    root = FIXTURES / "spring-mini"
    entries = find_entry_points(root, "spring", _config("spring-mini"))
    by_id = {e["id"]: e for e in entries}
    controller = root / "src/main/java/com/acme/shipments/ShipmentController.java"
    listener = root / "src/main/java/com/acme/shipments/ShipmentEventsListener.java"
    assert set(by_id) == {"POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"}
    assert by_id["POST /api/shipments"]["handler"] == (
        f"src/main/java/com/acme/shipments/ShipmentController.java:{line_of(controller, '@PostMapping')}"
    )
    assert by_id["amq shipment.requested"]["handler"].endswith(
        f":{line_of(listener, '@JmsListener')}"
    )
    assert by_id["amq shipment.requested"]["kind"] == "amq-subscribe"


def test_quarkus_entry_points_resolve_channel_address() -> None:
    root = FIXTURES / "quarkus-mini"
    entries = find_entry_points(root, "quarkus", _config("quarkus-mini"))
    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == {"POST /api/invoices", "GET /api/invoices/{id}", "amq order.completed"}
    assert by_id["amq order.completed"]["channel"] == "order-completed"
    resource = root / "src/main/java/com/acme/invoices/InvoiceResource.java"
    assert by_id["GET /api/invoices/{id}"]["handler"].endswith(f":{line_of(resource, '@GET')}")


def test_dotnet_entry_points_expand_controller_token() -> None:
    root = FIXTURES / "dotnet-mini"
    entries = find_entry_points(root, "aspnetcore", _config("dotnet-mini"))
    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == {"POST /api/deals", "GET /api/deals/{id}", "amq deal.requested"}
    consumer = root / "Messaging/DealRequestedConsumer.cs"
    assert by_id["amq deal.requested"]["handler"].endswith(
        f":{line_of(consumer, 'GetQueue(\"deal.requested\")')}"
    )


def test_fastapi_entry_points() -> None:
    root = FIXTURES / "fastapi-mini"
    entries = find_entry_points(root, "python", _config("fastapi-mini"))
    assert {e["id"] for e in entries} == {
        "GET /healthz",
        "POST /api/orders",
        "GET /api/orders/{order_id}",
        "amq order.requested",
    }


def test_detect_migrations_per_fixture() -> None:
    spring = detect_migrations(FIXTURES / "spring-mini", "spring", _config("spring-mini"))
    assert spring["strategy"] == "migration-container"
    assert spring["repo_migrations"] == ["src/main/resources/db/migration"]
    assert spring["also_on_boot"] is False
    dotnet = detect_migrations(FIXTURES / "dotnet-mini", "aspnetcore", _config("dotnet-mini"))
    assert dotnet["repo_migrations"] == ["Data/Migrations"]
    fastapi = detect_migrations(FIXTURES / "fastapi-mini", "python", _config("fastapi-mini"))
    assert fastapi["repo_migrations"] == ["alembic/versions"]


def test_detect_migrations_flags_on_boot(tmp_path: Path) -> None:
    config = {"spring.jpa.hibernate.ddl-auto": {"placeholder": "update", "source": "x",
                                                 "env_var": None}}
    assert detect_migrations(tmp_path, "spring", config)["also_on_boot"] is True


def test_build_env_map_dotnet() -> None:
    root = FIXTURES / "dotnet-mini"
    stack_info = detect(root)
    manifest = parse_manifest(root / "deployment.yml", root, serverless=False)
    dockerfile = parse_dockerfile(root / "Dockerfile")
    env_map = build_env_map(stack_info, manifest, dockerfile, _config("dotnet-mini"))
    roles = {k["key"]: k["role"] for k in env_map["keys"]}
    assert roles["ConnectionStrings__Deals"] == "db"
    assert roles["Amq__Url"] == "amq"
    assert roles["Pricing__BaseUrl"] == "downstream:pricing"
    assert roles["ASPNETCORE_URLS"] == "passthrough"
    assert env_map["port"] == 8080
    assert env_map["readiness"]["path"] == "/health/ready"
    assert env_map["auth"] == {"mode": "disabled", "key": "Auth__Enabled", "value": "false",
                               "confirmed": True}


def test_build_env_map_falls_back_to_dockerfile_port_and_port_wait(tmp_path: Path) -> None:
    stack_info = {"framework": "python", "auth": None}
    dockerfile = {"expose": 9001, "env": {}}
    env_map = build_env_map(stack_info, None, dockerfile, {})
    assert env_map["port"] == 9001
    assert env_map["readiness"] == {"path": None, "port": 9001, "source": "fallback"}
    assert env_map["manifest"] is None


def test_cli_writes_env_map_and_seeded_ledger(tmp_path: Path) -> None:
    root = FIXTURES / "spring-mini"
    stack_path = tmp_path / "stack.json"
    from detect import main as detect_main

    assert detect_main([str(root), "--out", str(stack_path), "--skip-toolchain"]) == 0
    env_path = tmp_path / "env-map.json"
    ledger_path = tmp_path / "flow-map.yaml"
    code = main([str(root), "--stack", str(stack_path), "--out-env", str(env_path),
                 "--out-ledger", str(ledger_path)])
    assert code == 0
    ledger = read_yaml(ledger_path)
    assert ledger["version"] == 1
    assert ledger["repo"] == "spring-mini"
    assert ledger["stack"]["framework"] == "spring"
    assert ledger["app"]["serverless"] is True
    assert ledger["app"]["dockerfile"] == "Dockerfile"
    assert ledger["app"]["readiness"]["path"] == "/actuator/health/readiness"
    assert ledger["app"]["migrations"]["strategy"] == "migration-container"
    assert ledger["app"]["auth"]["key"] == "APP_SECURITY_ENABLED"
    ids = [e["id"] for e in ledger["entry_points"]]
    assert ids == ["POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"]
    first = ledger["entry_points"][0]
    assert first["status"] == {"traced": False, "stubbed": False, "tested": False,
                               "passing": False}
    assert first["exits"] == [] and first["rules"] == {"file": None, "count": 0, "sources": []}
    assert ledger["unresolved"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_discover.py -q`
Expected: `ImportError: cannot import name 'build_env_map' from 'discover'`.

- [ ] **Step 3: Append part B to `discover.py`**

```python
# append to skills/karate-bootstrap/scripts/discover.py

# --- entry points -----------------------------------------------------------------

_SPRING_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?"([^"]*)"'
)
_JAXRS_PATH_RE = re.compile(r'@Path\s*\(\s*"([^"]*)"\s*\)')
_CLASS_DECL_RE = re.compile(r"\b(?:class|interface|record)\s+(\w+)")
_ASPNET_ROUTE_RE = re.compile(r'\[Route\s*\(\s*"([^"]*)"\s*\)\]')
_ASPNET_CLASS_RE = re.compile(r"\bclass\s+(\w+?)(Controller)?\b")
_FASTAPI_PREFIX_RE = re.compile(r"APIRouter\s*\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']")
_FLASK_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]+)\]")
_ROUTE_CONSTRAINT_RE = re.compile(r"\{(\w+):[^}]+\}")


def join_path(prefix: str, path: str) -> str:
    combined = "/".join(part for part in (prefix, path) if part)
    combined = _ROUTE_CONSTRAINT_RE.sub(r"{\1}", combined)
    segments = [s for s in combined.split("/") if s]
    return "/" + "/".join(segments)


def _class_prefix(stack: str, lines: list[str]) -> tuple[str, int]:
    """Return (route prefix, index of the class declaration line) for one source file."""
    class_index = next((i for i, l in enumerate(lines) if _CLASS_DECL_RE.search(l)), -1)
    head = "\n".join(lines[: class_index + 1] if class_index >= 0 else lines)
    if stack == "spring":
        match = _SPRING_CLASS_MAPPING_RE.search(head)
        return (match.group(1) if match else ""), class_index
    if stack == "quarkus":
        match = _JAXRS_PATH_RE.search(head)
        return (match.group(1) if match else ""), class_index
    if stack == "aspnetcore":
        route = _ASPNET_ROUTE_RE.search(head)
        if not route:
            return "", class_index
        prefix = route.group(1)
        if "[controller]" in prefix:
            klass = _ASPNET_CLASS_RE.search(head)
            name = klass.group(1).lower() if klass else "controller"
            prefix = prefix.replace("[controller]", name)
        return prefix, class_index
    match = _FASTAPI_PREFIX_RE.search("\n".join(lines))
    return (match.group(1) if match else ""), class_index


def _quarkus_method_path(lines: list[str], index: int, class_index: int) -> str:
    for offset in (1, 2, -1, -2):
        j = index + offset
        if 0 <= j < len(lines) and j > class_index:
            match = _JAXRS_PATH_RE.search(lines[j])
            if match:
                return match.group(1)
    return ""


def _resolve_channel(config: dict[str, dict[str, Any]], channel: str) -> str:
    info = config.get(f"mp.messaging.incoming.{channel}.address")
    return str(info["placeholder"]) if info and info.get("placeholder") else channel


def find_entry_points(root: Path, stack: str,
                      config: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    http_markers = markers_of_kind(stack, "entry-http")
    amq_markers = markers_of_kind(stack, "entry-amq")
    entries: dict[str, dict[str, Any]] = {}
    for path in iter_files(root, SOURCE_SUFFIXES[stack]):
        lines = read_text(path).splitlines()
        prefix, class_index = _class_prefix(stack, lines)
        source = rel(path, root)
        for index, line in enumerate(lines):
            handler = f"{source}:{index + 1}"
            for marker in http_markers:
                match = marker.pattern.search(line)
                if not match:
                    continue
                # ASP.NET minimal-API routes (app.MapGet("/x")) are absolute; attribute
                # routes and every other stack are relative to the class prefix.
                absolute_minimal_api = stack == "aspnetcore" and match.group(3) is not None
                for method, route in _http_routes(stack, match, line, lines, index, class_index):
                    full = join_path("" if absolute_minimal_api else prefix, route)
                    entry_id = f"{method} {full}"
                    entries.setdefault(entry_id, {
                        "id": entry_id, "kind": "http", "method": method, "path": full,
                        "handler": handler,
                    })
            for marker in amq_markers:
                match = marker.pattern.search(line)
                if not match:
                    continue
                destination = next((g for g in match.groups() if g), None)
                if destination is None:
                    continue
                entry: dict[str, Any] = {"kind": "amq-subscribe", "handler": handler}
                if stack == "quarkus":
                    entry["channel"] = destination
                    destination = _resolve_channel(config, destination)
                entry["destination"] = destination
                entry["id"] = f"amq {destination}"
                entries.setdefault(entry["id"], entry)
    return sorted(entries.values(), key=lambda e: (e["handler"].rsplit(":", 1)[0],
                                                   int(e["handler"].rsplit(":", 1)[1])))


def _http_routes(stack: str, match: re.Match[str], line: str, lines: list[str], index: int,
                 class_index: int) -> list[tuple[str, str]]:
    if stack == "spring":
        return [(match.group(1).upper(), match.group(2) or "")]
    if stack == "quarkus":
        return [(match.group(1).upper(), _quarkus_method_path(lines, index, class_index))]
    if stack == "aspnetcore":
        if match.group(1):
            return [(match.group(1).upper(), match.group(2) or "")]
        return [(match.group(3).upper(), "/" + (match.group(4) or "").lstrip("/"))]
    if match.group(1):
        return [(match.group(1).upper(), match.group(2))]
    methods_match = _FLASK_METHODS_RE.search(line)
    methods = (
        [m.strip().strip("\"'").upper() for m in methods_match.group(1).split(",")]
        if methods_match else ["GET"]
    )
    return [(method, match.group(3)) for method in methods]


# --- migrations -------------------------------------------------------------------

_MIGRATION_DIRS = (
    "src/main/resources/db/migration",
    "src/main/resources/db/changelog",
    "alembic/versions",
    "migrations",
)
_ON_BOOT_KEYS = (
    "spring.jpa.hibernate.ddl-auto",
    "quarkus.hibernate-orm.database.generation",
    "hibernate.hbm2ddl.auto",
)
_ON_BOOT_VALUES = {"create", "create-drop", "update", "drop-and-create"}


def detect_migrations(root: Path, stack: str, config: dict[str, dict[str, Any]]) -> dict[str, Any]:
    found: list[str] = [d for d in _MIGRATION_DIRS if (root / d).is_dir()]
    if stack == "aspnetcore":
        found.extend(
            sorted({rel(p.parent, root) for p in iter_files(root, (".cs",))
                    if p.parent.name == "Migrations"})
        )
    also_on_boot = any(
        str(config.get(k, {}).get("placeholder", "")).lower() in _ON_BOOT_VALUES
        for k in _ON_BOOT_KEYS
    )
    if not also_on_boot and stack == "aspnetcore":
        also_on_boot = any(".Migrate()" in read_text(p) for p in iter_files(root, (".cs",)))
    if not also_on_boot and stack == "python":
        also_on_boot = any("create_all(" in read_text(p) for p in iter_files(root, (".py",)))
    return {
        "strategy": "migration-container",
        "image": None,
        "source": None,
        "repo_migrations": found,
        "also_on_boot": also_on_boot,
    }


# --- env-map and ledger -------------------------------------------------------------


def build_env_map(stack_info: dict[str, Any], manifest: dict[str, Any] | None,
                  dockerfile: dict[str, Any] | None,
                  config: dict[str, dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    if manifest is not None:
        for key, value in manifest["env"].items():
            merged[key] = {"placeholder": value or "", "source": manifest["source"],
                           "env_var": key}
    if dockerfile is not None:
        for key, value in dockerfile["env"].items():
            merged.setdefault(key, {"placeholder": value, "source": "Dockerfile",
                                    "env_var": key})
    for key, info in config.items():
        merged.setdefault(key, dict(info))
    for key, info in merged.items():
        info["role"] = assign_role(key, str(info.get("placeholder") or ""))

    port = (manifest or {}).get("port") or (dockerfile or {}).get("expose") \
        or DEFAULT_PORT.get(str(stack_info.get("framework")), 8080)
    readiness = (manifest or {}).get("readiness") or {
        "path": None, "port": port, "source": "fallback"
    }
    return {
        "manifest": None if manifest is None else {
            "source": manifest["source"], "serverless": manifest["serverless"],
            "env_from": manifest["env_from"],
        },
        "port": port,
        "readiness": readiness,
        "auth": detect_auth(merged, stack_info.get("auth")),
        "keys": [
            {"key": key, "role": info["role"], "placeholder": info.get("placeholder", ""),
             "source": info.get("source", ""), "env_var": info.get("env_var")}
            for key, info in sorted(merged.items())
        ],
    }


def _blank_status() -> dict[str, bool]:
    return {"traced": False, "stubbed": False, "tested": False, "passing": False}


def seed_ledger(stack_info: dict[str, Any], env_map: dict[str, Any],
                entries: list[dict[str, Any]], migrations: dict[str, Any],
                repo_name: str, dockerfile_rel: str | None) -> dict[str, Any]:
    entry_points: list[dict[str, Any]] = []
    for entry in entries:
        item: dict[str, Any] = dict(entry)
        item.update({
            "auth": "unknown",
            "request": None,
            "responses": [],
            "reads": [],
            "exits": [],
            "rules": {"file": None, "count": 0, "sources": []},
            "features": [],
            "stubs": [],
            "seeds": [],
            "observed_overrides": [],
            "status": _blank_status(),
        })
        entry_points.append(item)
    manifest = env_map.get("manifest") or {}
    return {
        "version": LEDGER_VERSION,
        "repo": repo_name,
        "stack": {
            "language": stack_info.get("language"),
            "framework": stack_info.get("framework"),
            "db": stack_info.get("db"),
            "messaging": stack_info.get("messaging"),
            "validation": stack_info.get("validation"),
            "auth": stack_info.get("auth"),
            "cheat_sheet": CHEAT_SHEET[str(stack_info.get("framework"))],
        },
        "app": {
            "dockerfile": dockerfile_rel,
            "port": env_map["port"],
            "serverless": bool(manifest.get("serverless", False)),
            "readiness": env_map["readiness"],
            "migrations": migrations,
            "auth": env_map["auth"],
        },
        "entry_points": entry_points,
        "unresolved": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover manifests, config and entry points")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--service-dir", default=None)
    parser.add_argument("--stack", type=Path, required=True, help="stack.json from detect.py")
    parser.add_argument("--out-env", type=Path, required=True)
    parser.add_argument("--out-ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    root = args.repo / args.service_dir if args.service_dir else args.repo
    stack_info = read_json(require_file(args.stack, "stack.json"))
    stack = str(stack_info["framework"])

    manifests = find_manifests(root)
    manifest = parse_manifest(manifests[0][0], root, manifests[0][1]) if manifests else None
    dockerfile_path = find_dockerfile(root)
    if dockerfile_path is None:
        raise KbError(f"no Dockerfile found under {root}; the app image cannot be built")
    dockerfile = parse_dockerfile(dockerfile_path)
    config = parse_app_config(root)
    entries = find_entry_points(root, stack, config)
    if not entries:
        raise KbError(f"no entry points found under {root} for stack {stack}")
    migrations = detect_migrations(root, stack, config)
    env_map = build_env_map(stack_info, manifest, dockerfile, config)
    ledger = seed_ledger(stack_info, env_map, entries, migrations, root.resolve().name,
                         rel(dockerfile_path, root))
    write_json(args.out_env, env_map)
    write_yaml(args.out_ledger, ledger)
    print(f"entry points: {len(entries)}, config keys: {len(env_map['keys'])}, "
          f"auth: {env_map['auth']['mode']} -> {args.out_ledger}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

Also extend the part-A import block at the top of the file so it reads:

```python
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kb_common import (
    EXIT_OK,
    LEDGER_VERSION,
    KbError,
    iter_files,
    read_json,
    read_text,
    read_yaml_docs,
    rel,
    require_file,
    run_cli,
    write_json,
    write_yaml,
)
from markers import CHEAT_SHEET, SOURCE_SUFFIXES, markers_of_kind
```

and remove the "Task 6 extends this import block" comment.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_discover.py -q`
Expected: all pass. If `test_dotnet_entry_points_expand_controller_token` fails on the AMQ handler line, check that `GetQueue(` is the first capturing group hit, not `Listener +=` (which has no group and is token-only).

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. Likely mypy complaints: `match.group(1).upper()` on `str | Any` is fine; `int(...)` on `Any` is fine. If mypy flags `_class_prefix` returning `tuple[str, int]` with `match.group(1)` typed `str | Any`, wrap in `str(...)`.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/discover.py skills/karate-bootstrap/tests/test_kb_discover.py
git commit -m "feat(karate-bootstrap): discover entry points and seed the flow-map ledger

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 7: `flow_map.py` part A: load, save, next, merge, mark

**Confidence:** 92%. Pure data manipulation over the ledger dict. The merge contract (what a trace subagent may overwrite) is the only design decision, and it is pinned by tests.

**Files:**
- Create: `skills/karate-bootstrap/scripts/flow_map.py` (part A; Task 8 appends validate and verify-refs)
- Create: `skills/karate-bootstrap/tests/test_kb_flow_map.py` (part A; Task 8 appends)

**Interfaces:**
- Consumes: `kb_common` (`read_yaml`, `write_yaml`, `read_json`, `require_file`, `KbError`), `markers.tokens_for`.
- Produces:
  - `STATUS_FLAGS = ("traced", "stubbed", "tested", "passing")`, `EXIT_KINDS = ("db-write", "amq-publish", "http-out")`, `READ_KINDS = ("db-read", "http-in")`.
  - `load_ledger(path: Path) -> dict[str, Any]` (raises `KbError` exit 5 when missing, exit 2 on wrong version), `save_ledger(path, ledger) -> None`.
  - `find_entry(ledger, entry_id: str) -> dict[str, Any]`.
  - `next_entry(ledger, phase: str) -> dict[str, Any] | None` where `phase` is `traced` (first entry with `status.traced == False`) or `generated` (first traced entry with `status.stubbed == False`). Returns `{"id", "kind", "handler", "cheat_sheet"}`.
  - `merge_entry(ledger, traced: dict[str, Any]) -> int` returning the number of unresolved hops for that entry. Overwrites `request, responses, reads, exits, exits_none_reason, auth, type` and unions `rules.sources` by file. Replaces this entry's items in top-level `unresolved`. Sets `status.traced = True` only when there are no unresolved hops and the entry has exits or an `exits_none_reason`.
  - `mark_entry(ledger, entry_id, flag: str, value: bool = True) -> None`.
  - `VIA_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)$")` shared with Task 8.
  - CLI subcommands `next`, `merge`, `mark` (Task 8 adds `validate`, `verify-refs`).

- [ ] **Step 1: Write the failing tests (part A)**

```python
# skills/karate-bootstrap/tests/test_kb_flow_map.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from detect import main as detect_main
from discover import main as discover_main
from flow_map import (
    find_entry,
    load_ledger,
    main,
    mark_entry,
    merge_entry,
    next_entry,
    save_ledger,
)
from kb_common import EXIT_MISSING_OUTPUT, KbError

FIXTURES = Path(__file__).parent / "fixtures"
SPRING = FIXTURES / "spring-mini"
SERVICE = "src/main/java/com/acme/shipments/ShipmentService.java"
LISTENER = "src/main/java/com/acme/shipments/ShipmentEventsListener.java"


def line_of(path: Path, needle: str) -> int:
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} not found in {path}")


@pytest.fixture()
def spring_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger_path = tmp_path / "flow-map.yaml"
    assert detect_main([str(SPRING), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(SPRING), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger_path)]) == 0
    return ledger_path, load_ledger(ledger_path)


def post_trace() -> dict[str, Any]:
    return {
        "id": "POST /api/shipments",
        "auth": "required",
        "request": {"content_type": "application/json",
                    "schema_ref": "src/main/java/com/acme/shipments/ShipmentRequest.java",
                    "example": "seed/examples/post-api-shipments.json"},
        "responses": [
            {"status": 201, "when": "happy"},
            {"status": 400, "when": "validation", "rules": True},
            {"status": 400, "when": "weight over 1000kg",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'weight exceeds')}"},
        ],
        "reads": [
            {"kind": "http-in", "host_key": "PRICING_BASE_URL", "method": "GET",
             "path": "/rates/{countryCode}"},
        ],
        "exits": [
            {"kind": "db-write", "table": "shipments", "op": "insert",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'repository.save')}"},
            {"kind": "amq-publish", "destination": "shipment.created", "type": "queue",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'convertAndSend')}"},
            {"kind": "http-out", "host_key": "PRICING_BASE_URL", "method": "GET",
             "path": "/rates/{countryCode}",
             "via": f"{SERVICE}:{line_of(SPRING / SERVICE, 'getForObject')}"},
        ],
        "rules": {"sources": [{"file": "src/main/java/com/acme/shipments/ShipmentRequest.java",
                               "scanned": False}]},
        "unresolved": [],
    }


def test_load_ledger_missing_is_exit_5(tmp_path: Path) -> None:
    with pytest.raises(KbError) as excinfo:
        load_ledger(tmp_path / "nope.yaml")
    assert excinfo.value.exit_code == EXIT_MISSING_OUTPUT


def test_load_ledger_rejects_wrong_version(tmp_path: Path) -> None:
    path = tmp_path / "flow-map.yaml"
    path.write_text("version: 99\nentry_points: []\nunresolved: []\n", encoding="utf-8")
    with pytest.raises(KbError, match="version"):
        load_ledger(path)


def test_next_entry_walks_untraced_then_ungenerated(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    first = next_entry(ledger, "traced")
    assert first is not None
    assert first["id"] == "POST /api/shipments"
    assert first["cheat_sheet"] == "reference/stack-spring.md"
    assert first["handler"].startswith("src/main/java/com/acme/shipments/ShipmentController.java:")
    assert next_entry(ledger, "generated") is None  # nothing traced yet
    for entry in ledger["entry_points"]:
        entry["status"]["traced"] = True
    assert next_entry(ledger, "traced") is None
    assert next_entry(ledger, "generated") is not None


def test_merge_entry_sets_traced_and_replaces_fields(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    path, ledger = spring_ledger
    assert merge_entry(ledger, post_trace()) == 0
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is True
    assert [e["kind"] for e in entry["exits"]] == ["db-write", "amq-publish", "http-out"]
    assert entry["rules"]["sources"][0]["file"].endswith("ShipmentRequest.java")
    assert entry["rules"]["count"] == 0  # untouched by merge
    save_ledger(path, ledger)
    assert load_ledger(path)["entry_points"][0]["status"]["traced"] is True


def test_merge_entry_with_unresolved_stays_untraced(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["unresolved"] = [{"at": f"{SERVICE}:31", "reason": "Shipment.from is a static factory"}]
    assert merge_entry(ledger, traced) == 1
    entry = find_entry(ledger, "POST /api/shipments")
    assert entry["status"]["traced"] is False
    assert ledger["unresolved"] == [{"entry": "POST /api/shipments", "at": f"{SERVICE}:31",
                                     "reason": "Shipment.from is a static factory"}]
    # a re-trace that resolves it clears only this entry's unresolved items
    assert merge_entry(ledger, post_trace()) == 0
    assert ledger["unresolved"] == []


def test_merge_entry_requires_exits_or_reason(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = {"id": "GET /api/shipments/{id}", "exits": [], "reads": [
        {"kind": "db-read", "table": "shipments", "via": f"{SERVICE}:37"}], "unresolved": []}
    assert merge_entry(ledger, traced) == 0
    assert find_entry(ledger, "GET /api/shipments/{id}")["status"]["traced"] is False
    traced["exits_none_reason"] = "read-only lookup"
    merge_entry(ledger, traced)
    assert find_entry(ledger, "GET /api/shipments/{id}")["status"]["traced"] is True


def test_merge_entry_validates_exit_shape(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"] = [{"kind": "db-write", "table": "shipments", "op": "insert"}]  # no via
    with pytest.raises(KbError, match="via"):
        merge_entry(ledger, traced)
    traced["exits"] = [{"kind": "db-write", "table": "shipments", "via": f"{SERVICE}:32"}]
    with pytest.raises(KbError, match="missing"):
        merge_entry(ledger, traced)
    traced["exits"] = [{"kind": "teleport", "via": f"{SERVICE}:32"}]
    with pytest.raises(KbError, match="kind"):
        merge_entry(ledger, traced)


def test_merge_entry_unknown_id(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    with pytest.raises(KbError, match="unknown entry"):
        merge_entry(ledger, {"id": "DELETE /nope", "exits": [], "unresolved": []})


def test_mark_entry(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    mark_entry(ledger, "POST /api/shipments", "stubbed")
    assert find_entry(ledger, "POST /api/shipments")["status"]["stubbed"] is True
    with pytest.raises(KbError, match="flag"):
        mark_entry(ledger, "POST /api/shipments", "verified")


def test_cli_next_merge_mark(spring_ledger: tuple[Path, dict[str, Any]],
                             tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path, _ = spring_ledger
    assert main(["next", "--phase", "traced", "--ledger", str(path)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["id"] == "POST /api/shipments"
    trace_file = tmp_path / "entry.json"
    trace_file.write_text(json.dumps(post_trace()), encoding="utf-8")
    assert main(["merge", str(trace_file), "--ledger", str(path)]) == 0
    assert "unresolved: 0" in capsys.readouterr().out
    assert main(["mark", "--entry", "POST /api/shipments", "--generated", "--ledger", str(path)]) == 0
    reloaded = load_ledger(path)
    assert reloaded["entry_points"][0]["status"] == {"traced": True, "stubbed": True,
                                                     "tested": False, "passing": False}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q`
Expected: `ModuleNotFoundError: No module named 'flow_map'`.

- [ ] **Step 3: Implement part A of `flow_map.py`**

```python
# skills/karate-bootstrap/scripts/flow_map.py
"""The flow-map ledger: karate-bootstrap's only memory across phases.

Subcommands:
    next        --phase traced|generated --ledger PATH
                prints JSON {id, kind, handler, cheat_sheet} for the next pending entry,
                or {"done": true}
    merge       ENTRY_JSON --ledger PATH
                merges one trace subagent result into its entry
    mark        --entry ID (--generated|--tested|--passing|--failing) --ledger PATH
    validate    --phase traced|generated|green --ledger PATH --repo ROOT
                [--env PATH] [--tests-dir PATH] [--report PATH] [--defects PATH]
                exit 0 when the phase gate passes, 2 with the gap list otherwise
    verify-refs --ledger PATH --repo ROOT
                exit 2 when any exit ``via`` does not point at a matching marker

Status flags: traced (trace merged, no unresolved), stubbed (features, stubs
and seeds generated), tested (included in a run), passing (green in the last
run).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kb_common import (
    EXIT_OK,
    LEDGER_VERSION,
    KbError,
    read_json,
    read_yaml,
    require_file,
    run_cli,
    write_yaml,
)

# Task 8 adds EXIT_VALIDATION and read_text to the kb_common import and
# ``from markers import tokens_for``.

STATUS_FLAGS = ("traced", "stubbed", "tested", "passing")
EXIT_KINDS = ("db-write", "amq-publish", "http-out")
READ_KINDS = ("db-read", "http-in")
MERGE_FIELDS = ("request", "responses", "reads", "exits", "exits_none_reason", "auth", "type")
VIA_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+)$")

_REQUIRED_EXIT_FIELDS = {
    "db-write": ("table", "op"),
    "amq-publish": ("destination",),
    "http-out": ("host_key", "method", "path"),
}


def load_ledger(path: Path) -> dict[str, Any]:
    ledger = read_yaml(require_file(path, "flow-map.yaml"))
    if ledger.get("version") != LEDGER_VERSION:
        raise KbError(f"{path}: unsupported ledger version {ledger.get('version')!r}")
    ledger.setdefault("entry_points", [])
    ledger.setdefault("unresolved", [])
    return ledger


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    write_yaml(path, ledger)


def find_entry(ledger: dict[str, Any], entry_id: str) -> dict[str, Any]:
    for entry in ledger["entry_points"]:
        if entry.get("id") == entry_id:
            return entry
    raise KbError(f"unknown entry {entry_id!r}")


def _pending(entry: dict[str, Any], phase: str) -> bool:
    status = entry.get("status", {})
    if phase == "traced":
        return not status.get("traced", False)
    if phase == "generated":
        return bool(status.get("traced")) and not status.get("stubbed", False)
    raise KbError(f"unknown phase {phase!r}; expected traced or generated")


def next_entry(ledger: dict[str, Any], phase: str) -> dict[str, Any] | None:
    for entry in ledger["entry_points"]:
        if _pending(entry, phase):
            return {
                "id": entry["id"],
                "kind": entry.get("kind"),
                "handler": entry.get("handler"),
                "cheat_sheet": ledger.get("stack", {}).get("cheat_sheet"),
            }
    return None


def _check_via(owner: str, item: dict[str, Any]) -> None:
    via = item.get("via")
    if not isinstance(via, str) or not VIA_RE.match(via):
        raise KbError(f"{owner}: every exit needs 'via' as file:line, got {via!r}")


def _validate_exits(entry_id: str, exits: list[dict[str, Any]]) -> None:
    for item in exits:
        kind = item.get("kind")
        if kind not in EXIT_KINDS:
            raise KbError(f"{entry_id}: exit kind {kind!r} not one of {EXIT_KINDS}")
        missing = [f for f in _REQUIRED_EXIT_FIELDS[kind] if f not in item]
        if missing:
            raise KbError(f"{entry_id}: {kind} exit missing {missing}")
        _check_via(entry_id, item)
        if kind == "amq-publish":
            item.setdefault("type", "queue")


def merge_entry(ledger: dict[str, Any], traced: dict[str, Any]) -> int:
    entry_id = str(traced.get("id", ""))
    entry = find_entry(ledger, entry_id)
    exits = list(traced.get("exits", []))
    _validate_exits(entry_id, exits)
    for field in MERGE_FIELDS:
        if field in traced:
            entry[field] = traced[field]
    entry["exits"] = exits
    incoming_sources = traced.get("rules", {}).get("sources", [])
    rules = entry.setdefault("rules", {"file": None, "count": 0, "sources": []})
    known = {s["file"] for s in rules["sources"]}
    for source in incoming_sources:
        if source["file"] not in known:
            rules["sources"].append({"file": source["file"], "scanned": bool(source.get("scanned"))})
            known.add(source["file"])
    unresolved = [
        {"entry": entry_id, "at": u["at"], "reason": u.get("reason", "")}
        for u in traced.get("unresolved", [])
    ]
    ledger["unresolved"] = [u for u in ledger["unresolved"] if u.get("entry") != entry_id]
    ledger["unresolved"].extend(unresolved)
    complete = bool(exits) or bool(entry.get("exits_none_reason"))
    entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
    entry["status"]["traced"] = not unresolved and complete
    return len(unresolved)


def mark_entry(ledger: dict[str, Any], entry_id: str, flag: str, value: bool = True) -> None:
    if flag not in STATUS_FLAGS:
        raise KbError(f"unknown status flag {flag!r}; expected one of {STATUS_FLAGS}")
    entry = find_entry(ledger, entry_id)
    entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))
    entry["status"][flag] = value


def _cmd_next(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    pending = next_entry(ledger, args.phase)
    print(json.dumps(pending if pending is not None else {"done": True}))
    return EXIT_OK


def _cmd_merge(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    traced = read_json(require_file(args.entry_json, "trace result"))
    count = merge_entry(ledger, traced)
    save_ledger(args.ledger, ledger)
    print(f"merged {traced['id']}; unresolved: {count}")
    return EXIT_OK


def _cmd_mark(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    if args.generated:
        mark_entry(ledger, args.entry, "stubbed")
    if args.tested:
        mark_entry(ledger, args.entry, "tested")
    if args.passing:
        mark_entry(ledger, args.entry, "passing")
    if args.failing:
        mark_entry(ledger, args.entry, "passing", False)
    save_ledger(args.ledger, ledger)
    print(f"marked {args.entry}: {find_entry(ledger, args.entry)['status']}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate on the karate-bootstrap flow-map ledger")
    sub = parser.add_subparsers(dest="command", required=True)

    nxt = sub.add_parser("next", help="Print the next pending entry for a phase")
    nxt.add_argument("--phase", choices=("traced", "generated"), required=True)
    nxt.add_argument("--ledger", type=Path, required=True)
    nxt.set_defaults(func=_cmd_next)

    merge = sub.add_parser("merge", help="Merge a trace subagent result into the ledger")
    merge.add_argument("entry_json", type=Path)
    merge.add_argument("--ledger", type=Path, required=True)
    merge.set_defaults(func=_cmd_merge)

    mark = sub.add_parser("mark", help="Flip status flags on one entry")
    mark.add_argument("--entry", required=True)
    mark.add_argument("--ledger", type=Path, required=True)
    mark.add_argument("--generated", action="store_true")
    mark.add_argument("--tested", action="store_true")
    mark.add_argument("--passing", action="store_true")
    mark.add_argument("--failing", action="store_true")
    mark.set_defaults(func=_cmd_mark)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. The import block only names what part A uses ([[spec-code-lint]]).

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/tests/test_kb_flow_map.py
git commit -m "feat(karate-bootstrap): flow-map ledger load, next, merge and mark

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: `flow_map.py` part B: `validate` and `verify-refs`

**Confidence:** 88%. The phase gates encode the spec's completeness rules. Risk: the `generated` and `green` phases depend on artefacts Plan 2 produces (feature files, report JSON, `defects.md`). Mitigation: their input shapes are fixed here and the tests build minimal artefacts by hand, so Plan 2 inherits a contract rather than inventing one.

**Files:**
- Modify: `skills/karate-bootstrap/scripts/flow_map.py` (append)
- Modify: `skills/karate-bootstrap/tests/test_kb_flow_map.py` (append)

**Interfaces:**
- Consumes: Task 7 functions, `markers.tokens_for(stack, kind)`.
- Produces:
  - `verify_refs(ledger, repo_root: Path, window: int = 3) -> list[str]` gap messages; resets `status.traced` on entries with bad refs.
  - `validate(ledger, phase: str, repo_root: Path, env_map: dict | None, tests_dir: Path | None, report: dict | None, defects_text: str | None) -> list[str]` gap messages.
  - Report JSON contract consumed by phase `green` (Plan 2's `report.py parse` must emit exactly this): `{"passed": int, "failed": [{"feature": str, "scenario": str, "tags": [str], "step": str, "error": str}], "skipped": int}`.
  - `defects.md` contract consumed by phase `green`: each entry is a `## DEF-NNN:` heading followed by a line `entry_point: <entry id>`.
  - CLI subcommands `validate` and `verify-refs`, exit 2 on gaps.

- [ ] **Step 1: Append the failing tests (part B)**

```python
# append to skills/karate-bootstrap/tests/test_kb_flow_map.py
from flow_map import validate, verify_refs  # noqa: E402
from kb_common import EXIT_VALIDATION, read_json  # noqa: E402


def _trace_all(ledger: dict[str, Any]) -> None:
    merge_entry(ledger, post_trace())
    merge_entry(ledger, {"id": "GET /api/shipments/{id}", "exits": [],
                         "exits_none_reason": "read-only lookup", "unresolved": [],
                         "responses": [{"status": 200, "when": "found"},
                                       {"status": 404, "when": "missing"}]})
    merge_entry(ledger, {
        "id": "amq shipment.requested", "unresolved": [],
        "exits": [{"kind": "db-write", "table": "shipments", "op": "insert",
                   "via": f"{LISTENER}:{line_of(SPRING / LISTENER, 'repository.save')}"}],
    })


def test_verify_refs_passes_for_real_lines(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    assert verify_refs(ledger, SPRING) == []


def test_verify_refs_flags_wrong_line_and_resets_traced(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"][0]["via"] = f"{SERVICE}:1"  # package line, no write marker nearby
    merge_entry(ledger, traced)
    gaps = verify_refs(ledger, SPRING)
    assert len(gaps) == 1 and "db-write" in gaps[0] and f"{SERVICE}:1" in gaps[0]
    assert find_entry(ledger, "POST /api/shipments")["status"]["traced"] is False


def test_verify_refs_flags_missing_file(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    traced = post_trace()
    traced["exits"][0]["via"] = "src/main/java/Nope.java:3"
    merge_entry(ledger, traced)
    gaps = verify_refs(ledger, SPRING)
    assert gaps and "does not exist" in gaps[0]


def test_validate_traced_lists_gaps_then_passes(spring_ledger: tuple[Path, dict[str, Any]],
                                                tmp_path: Path) -> None:
    path, ledger = spring_ledger
    env_map = read_json(path.parent / "env-map.json")
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert len(gaps) == 3 and all("not traced" in g for g in gaps)
    _trace_all(ledger)
    assert validate(ledger, "traced", SPRING, env_map, None, None, None) == []


def test_validate_traced_flags_unknown_host_key_and_unscanned_rules(
    spring_ledger: tuple[Path, dict[str, Any]],
) -> None:
    path, ledger = spring_ledger
    env_map = read_json(path.parent / "env-map.json")
    _trace_all(ledger)
    entry = find_entry(ledger, "POST /api/shipments")
    entry["exits"][2]["host_key"] = "NOT_A_KEY"
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert any("NOT_A_KEY" in g for g in gaps)
    entry["exits"][2]["host_key"] = "PRICING_BASE_URL"
    entry["rules"]["sources"][0]["scanned"] = False
    gaps = validate(ledger, "traced", SPRING, env_map, None, None, None)
    assert gaps == []  # scanned is a Phase 3 concern, checked in the generated gate


def _fake_generated(tmp_path: Path, ledger: dict[str, Any], feature_text: str) -> Path:
    tests_dir = tmp_path / "karate-tests"
    features = tests_dir / "src/test/resources/features"
    features.mkdir(parents=True)
    (features / "post-api-shipments.feature").write_text(feature_text, encoding="utf-8")
    (tests_dir / "stubs/post-api-shipments").mkdir(parents=True)
    (tests_dir / "stubs/post-api-shipments/pricing.json").write_text("[]", encoding="utf-8")
    (tests_dir / "rules").mkdir()
    (tests_dir / "rules/post-api-shipments.csv").write_text(
        "rule_id,field,mutation,value,expected_status,expected_code,expected_message_contains,source\n"
        "R001,reference,missing,,400,VALIDATION,,x:1\n",
        encoding="utf-8",
    )
    entry = find_entry(ledger, "POST /api/shipments")
    entry["features"] = ["features/post-api-shipments.feature"]
    entry["stubs"] = ["stubs/post-api-shipments/pricing.json"]
    entry["rules"].update({"file": "rules/post-api-shipments.csv", "count": 1})
    entry["rules"]["sources"][0]["scanned"] = True
    entry["status"]["stubbed"] = True
    for other in ("GET /api/shipments/{id}", "amq shipment.requested"):
        o = find_entry(ledger, other)
        o["features"] = ["features/post-api-shipments.feature"]
        o["status"]["stubbed"] = True
    return tests_dir


GOOD_FEATURE = """Feature: POST /api/shipments
Scenario: happy
  * def row = Db.row('shipments', { reference: 'x' })
  * def msg = Jms.await('shipment.created', 5000)
  * Stubs.verify('GET', '/rates/GB', 1)
"""


def test_validate_generated_passes_with_markers(spring_ledger: tuple[Path, dict[str, Any]],
                                                tmp_path: Path) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, GOOD_FEATURE)
    assert validate(ledger, "generated", SPRING, None, tests_dir, None, None) == []


def test_validate_generated_flags_missing_assertions_and_count(
    spring_ledger: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    tests_dir = _fake_generated(tmp_path, ledger, "Feature: POST /api/shipments\nScenario: x\n")
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert any("Db." in g and "shipments" in g for g in gaps)
    assert any("Jms." in g and "shipment.created" in g for g in gaps)
    assert any("Stubs.verify" in g for g in gaps)
    find_entry(ledger, "POST /api/shipments")["rules"]["count"] = 5
    gaps = validate(ledger, "generated", SPRING, None, tests_dir, None, None)
    assert any("rules" in g and "5" in g and "1" in g for g in gaps)


def test_validate_green(spring_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = spring_ledger
    _trace_all(ledger)
    for entry in ledger["entry_points"]:
        entry["status"].update({"stubbed": True, "tested": True, "passing": True})
    report = {"passed": 10, "skipped": 1, "failed": []}
    assert validate(ledger, "green", SPRING, None, None, report, "") == []
    report["failed"] = [{"feature": "features/post-api-shipments.feature",
                         "scenario": "over weight", "tags": ["@error"], "step": "status 400",
                         "error": "expected 400 got 500"}]
    gaps = validate(ledger, "green", SPRING, None, None, report, "")
    assert gaps == ["features/post-api-shipments.feature: 'over weight' failed and is not "
                    "quarantined with @known-defect"]
    report["failed"][0]["tags"] = ["@error", "@known-defect"]
    gaps = validate(ledger, "green", SPRING, None, None, report, "")
    assert gaps and "defects.md" in gaps[0]
    defects = "## DEF-001: over weight 500\nstatus: pending\nentry_point: POST /api/shipments\n"
    find_entry(ledger, "POST /api/shipments")["status"]["passing"] = False
    assert validate(ledger, "green", SPRING, None, None, report, defects) == []


def test_cli_validate_and_verify_refs_exit_codes(spring_ledger: tuple[Path, dict[str, Any]],
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    path, ledger = spring_ledger
    env = path.parent / "env-map.json"
    assert main(["validate", "--phase", "traced", "--ledger", str(path), "--repo", str(SPRING),
                 "--env", str(env)]) == EXIT_VALIDATION
    assert "not traced" in capsys.readouterr().out
    _trace_all(ledger)
    save_ledger(path, ledger)
    assert main(["validate", "--phase", "traced", "--ledger", str(path), "--repo", str(SPRING),
                 "--env", str(env)]) == 0
    assert main(["verify-refs", "--ledger", str(path), "--repo", str(SPRING)]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q`
Expected: `ImportError: cannot import name 'validate' from 'flow_map'`.

- [ ] **Step 3: Append part B to `flow_map.py`**

Add `EXIT_VALIDATION` and `read_text` to the `kb_common` import, add `from markers import tokens_for`, delete the "Task 8 adds" comment, then append:

```python
# append to skills/karate-bootstrap/scripts/flow_map.py

# --- verify-refs -----------------------------------------------------------------------


def _split_via(via: str) -> tuple[str, int]:
    match = VIA_RE.match(via)
    if not match:
        raise KbError(f"malformed via {via!r}")
    return match.group("file"), int(match.group("line"))


def verify_refs(ledger: dict[str, Any], repo_root: Path, window: int = 3) -> list[str]:
    stack = str(ledger.get("stack", {}).get("framework"))
    gaps: list[str] = []
    for entry in ledger["entry_points"]:
        bad = False
        for item in entry.get("exits", []):
            kind = str(item.get("kind"))
            file_rel, line_no = _split_via(str(item.get("via")))
            path = repo_root / file_rel
            if not path.is_file():
                gaps.append(f"{entry['id']}: {kind} via {file_rel}:{line_no} does not exist")
                bad = True
                continue
            lines = read_text(path).splitlines()
            if not 1 <= line_no <= len(lines):
                gaps.append(f"{entry['id']}: {kind} via {file_rel}:{line_no} is past end of file")
                bad = True
                continue
            lo, hi = max(0, line_no - 1 - window), min(len(lines), line_no + window)
            snippet = "\n".join(lines[lo:hi])
            if not any(token in snippet for token in tokens_for(stack, kind)):
                gaps.append(
                    f"{entry['id']}: {kind} via {file_rel}:{line_no} has no {kind} marker "
                    f"within {window} lines"
                )
                bad = True
        if bad:
            entry.setdefault("status", dict.fromkeys(STATUS_FLAGS, False))["traced"] = False
    return gaps


# --- validate ----------------------------------------------------------------------------


def _validate_traced(ledger: dict[str, Any], env_map: dict[str, Any] | None) -> list[str]:
    gaps: list[str] = []
    known_keys = {k["key"] for k in (env_map or {}).get("keys", [])} | {
        str(k.get("env_var")) for k in (env_map or {}).get("keys", []) if k.get("env_var")
    }
    for entry in ledger["entry_points"]:
        if not entry.get("status", {}).get("traced"):
            gaps.append(f"{entry['id']}: not traced")
        elif not entry.get("exits") and not entry.get("exits_none_reason"):
            gaps.append(f"{entry['id']}: no exits and no exits_none_reason")
        if env_map is not None:
            for item in list(entry.get("exits", [])) + list(entry.get("reads", [])):
                host_key = item.get("host_key")
                if host_key and host_key not in known_keys:
                    gaps.append(f"{entry['id']}: host_key {host_key!r} not in env-map")
    for item in ledger.get("unresolved", []):
        gaps.append(f"{item.get('entry')}: unresolved hop at {item.get('at')}: {item.get('reason')}")
    return gaps


def _csv_rows(path: Path) -> int:
    lines = [l for l in read_text(path).splitlines() if l.strip()]
    return max(0, len(lines) - 1)


def _validate_generated(ledger: dict[str, Any], tests_dir: Path | None) -> list[str]:
    if tests_dir is None:
        raise KbError("--tests-dir is required for the generated phase")
    resources = tests_dir / "src" / "test" / "resources"
    gaps: list[str] = []
    for entry in ledger["entry_points"]:
        eid = entry["id"]
        if not entry.get("status", {}).get("stubbed"):
            gaps.append(f"{eid}: not generated")
        features = entry.get("features", [])
        if not features:
            gaps.append(f"{eid}: no feature file")
            continue
        texts: list[str] = []
        for feature in features:
            path = resources / feature
            if not path.is_file():
                gaps.append(f"{eid}: feature {feature} does not exist")
            else:
                texts.append(read_text(path))
        text = "\n".join(texts)
        for item in entry.get("exits", []):
            kind = item["kind"]
            if kind == "db-write" and not ("Db." in text and str(item["table"]) in text):
                gaps.append(f"{eid}: db-write on {item['table']} has no Db. assertion")
            if kind == "amq-publish" and not ("Jms." in text and str(item["destination"]) in text):
                gaps.append(f"{eid}: amq-publish to {item['destination']} has no Jms. assertion")
            if kind == "http-out":
                if "Stubs.verify" not in text:
                    gaps.append(f"{eid}: http-out {item['method']} {item['path']} has no Stubs.verify")
                if not entry.get("stubs"):
                    gaps.append(f"{eid}: http-out exit but no stub files")
        for stub in entry.get("stubs", []):
            if not (tests_dir / stub).is_file():
                gaps.append(f"{eid}: stub {stub} does not exist")
        needs_rules = any(r.get("rules") for r in entry.get("responses", []))
        rules = entry.get("rules", {})
        if needs_rules:
            if not rules.get("file"):
                gaps.append(f"{eid}: validation responses but no rules file")
            else:
                rules_path = tests_dir / str(rules["file"])
                if not rules_path.is_file():
                    gaps.append(f"{eid}: rules file {rules['file']} does not exist")
                else:
                    rows = _csv_rows(rules_path)
                    if rows != int(rules.get("count", 0)):
                        gaps.append(
                            f"{eid}: rules count {rules.get('count')} differs from {rows} CSV rows"
                        )
            for source in rules.get("sources", []):
                if not source.get("scanned"):
                    gaps.append(f"{eid}: rules source {source['file']} not scanned")
    return gaps


_DEFECT_ENTRY_RE = re.compile(r"^entry_point:\s*(.+?)\s*$", re.MULTILINE)


def _validate_green(ledger: dict[str, Any], report: dict[str, Any] | None,
                    defects_text: str | None) -> list[str]:
    if report is None:
        raise KbError("--report is required for the green phase")
    gaps: list[str] = []
    quarantined_entries = set(_DEFECT_ENTRY_RE.findall(defects_text or ""))
    for failed in report.get("failed", []):
        label = f"{failed.get('feature')}: {failed.get('scenario')!r}"
        if "@known-defect" not in failed.get("tags", []):
            gaps.append(f"{label} failed and is not quarantined with @known-defect")
        elif not quarantined_entries:
            gaps.append(f"{label} is quarantined but defects.md has no matching entry")
    for entry in ledger["entry_points"]:
        status = entry.get("status", {})
        if not status.get("passing") and entry["id"] not in quarantined_entries:
            gaps.append(f"{entry['id']}: not passing and not listed in defects.md")
    return gaps


def validate(ledger: dict[str, Any], phase: str, repo_root: Path,
             env_map: dict[str, Any] | None, tests_dir: Path | None,
             report: dict[str, Any] | None, defects_text: str | None) -> list[str]:
    if phase == "traced":
        return _validate_traced(ledger, env_map) + verify_refs(ledger, repo_root)
    if phase == "generated":
        return _validate_generated(ledger, tests_dir)
    if phase == "green":
        return _validate_green(ledger, report, defects_text)
    raise KbError(f"unknown phase {phase!r}")


def _cmd_validate(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    env_map = read_json(args.env) if args.env else None
    report = read_json(args.report) if args.report else None
    defects_text = read_text(args.defects) if args.defects and args.defects.is_file() else None
    gaps = validate(ledger, args.phase, args.repo, env_map, args.tests_dir, report, defects_text)
    save_ledger(args.ledger, ledger)  # verify-refs may have reset traced flags
    if gaps:
        print("\n".join(gaps))
        print(f"{len(gaps)} gap(s) in phase {args.phase}")
        return EXIT_VALIDATION
    print(f"phase {args.phase}: pass")
    return EXIT_OK


def _cmd_verify_refs(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    gaps = verify_refs(ledger, args.repo)
    save_ledger(args.ledger, ledger)
    if gaps:
        print("\n".join(gaps))
        return EXIT_VALIDATION
    print("verify-refs: pass")
    return EXIT_OK
```

Then extend `build_parser()` before its `return parser`:

```python
    val = sub.add_parser("validate", help="Run a phase gate")
    val.add_argument("--phase", choices=("traced", "generated", "green"), required=True)
    val.add_argument("--ledger", type=Path, required=True)
    val.add_argument("--repo", type=Path, required=True, help="service root")
    val.add_argument("--env", type=Path, default=None, help="env-map.json (traced phase)")
    val.add_argument("--tests-dir", type=Path, default=None, help="karate-tests dir (generated)")
    val.add_argument("--report", type=Path, default=None, help="parsed report JSON (green)")
    val.add_argument("--defects", type=Path, default=None, help="defects.md (green)")
    val.set_defaults(func=_cmd_validate)

    refs = sub.add_parser("verify-refs", help="Check every exit via points at a marker")
    refs.add_argument("--ledger", type=Path, required=True)
    refs.add_argument("--repo", type=Path, required=True)
    refs.set_defaults(func=_cmd_verify_refs)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_flow_map.py -q`
Expected: all pass. `test_validate_traced_flags_unknown_host_key_and_unscanned_rules` documents that `scanned` is enforced in the `generated` gate, not `traced`, because rules extraction is Phase 3 and runs after the `traced` gate. This is a deliberate correction to the spec's section 5.3 table, and the spec should be amended in the same commit (one line in `docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md`, section 5.3: move "Any rules source not scanned" and "Any response with rules: true lacking a rules file" from the `traced` row to the `generated` row).

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. Ruff E741 may flag the `l` loop variable in `_csv_rows`; rename to `line`.

- [ ] **Step 6: Commit**

```bash
git add skills/karate-bootstrap/scripts/flow_map.py skills/karate-bootstrap/tests/test_kb_flow_map.py docs/superpowers/specs/2026-09-05-karate-bootstrap-design.md
git commit -m "feat(karate-bootstrap): ledger phase gates and exit reference verification

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 9: `rules.py` (Phase 3): extract, add, mark-scanned

**Confidence:** 85%. Declarative-validator parsing across four libraries is the widest surface in this plan. Mitigation: each extractor is a separate function tested against the fixture DTO or validator file with exact expected rows, and unknown constructs are skipped rather than guessed. The candidate file is separate from the confirmed file, so a wrong candidate never reaches a feature without a subagent confirming it through `add`.

**Files:**
- Create: `skills/karate-bootstrap/scripts/rules.py`
- Create: `skills/karate-bootstrap/tests/test_kb_rules.py`

**Interfaces:**
- Consumes: `flow_map.load_ledger/save_ledger/find_entry`, `kb_common`, `markers.markers_of_kind(stack, "validation")` (token presence decides which files are worth parsing).
- Produces:
  - `CSV_HEADER = ("rule_id", "field", "mutation", "value", "expected_status", "expected_code", "expected_message_contains", "source")`, `MUTATIONS` tuple.
  - `slug_for(entry_id: str) -> str`, e.g. `POST /api/deals` becomes `post-api-deals`, `GET /api/orders/{order_id}` becomes `get-api-orders-order-id`, `amq deal.requested` becomes `amq-deal-requested`.
  - `extract_bean_validation(text, source_rel) -> list[dict]`, `extract_fluent_validation(text, source_rel)`, `extract_data_annotations(text, source_rel)`, `extract_pydantic(text, source_rel)`. Each returns rows without `rule_id`, with `expected_status` defaulting to `400` (`422` for Pydantic) and empty `expected_code` and `expected_message_contains`.
  - `extract_for_entry(root, stack, entry) -> list[dict]` choosing extractors by stack and reading `entry.rules.sources` plus `entry.request.schema_ref`.
  - `write_candidates(out_dir, entry, rows) -> Path` writing `rules/<slug>.candidates.csv`.
  - `add_rows(out_dir, ledger, entry_id, rows_csv: Path) -> int` validating header and mutation enum, appending to `rules/<slug>.csv` with sequential `rule_id`, de-duplicating on `(field, mutation, value)`, updating `entry.rules.file` and `entry.rules.count`; returns the new count.
  - `mark_scanned(ledger, entry_id, source_rel) -> None`.
  - CLI: `extract <repo> --ledger PATH --out-dir DIR [--service-dir SUB]`, `add ENTRY_ID ROWS_CSV --ledger PATH --out-dir DIR`, `mark-scanned ENTRY_ID SOURCE --ledger PATH`.

- [ ] **Step 1: Write the failing tests**

```python
# skills/karate-bootstrap/tests/test_kb_rules.py
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest

from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger, merge_entry, save_ledger
from kb_common import KbError
from rules import (
    CSV_HEADER,
    add_rows,
    extract_bean_validation,
    extract_data_annotations,
    extract_fluent_validation,
    extract_for_entry,
    extract_pydantic,
    main,
    mark_scanned,
    slug_for,
    write_candidates,
)

FIXTURES = Path(__file__).parent / "fixtures"


def rows_by_field(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["field"], r["mutation"]): r for r in rows}


def test_slug_for() -> None:
    assert slug_for("POST /api/deals") == "post-api-deals"
    assert slug_for("GET /api/orders/{order_id}") == "get-api-orders-order-id"
    assert slug_for("amq deal.requested") == "amq-deal-requested"


def test_extract_bean_validation_spring_request() -> None:
    src = "src/main/java/com/acme/shipments/ShipmentRequest.java"
    rows = extract_bean_validation((FIXTURES / "spring-mini" / src).read_text(encoding="utf-8"), src)
    got = rows_by_field(rows)
    assert ("reference", "missing") in got and ("reference", "empty") in got
    assert got[("reference", "too_long")]["value"] == "51"
    assert ("weightKg", "missing") in got
    assert got[("weightKg", "out_of_range")]["value"] == "0"
    assert got[("countryCode", "invalid_format")]["value"] == "!!"
    assert got[("destination", "too_short")]["value"] == "2"
    assert got[("destination", "too_long")]["value"] == "121"
    assert all(r["expected_status"] == "400" for r in rows)
    assert all(r["source"].startswith(src + ":") for r in rows)


def test_extract_bean_validation_decimal_min() -> None:
    src = "src/main/java/com/acme/invoices/InvoiceRequest.java"
    rows = extract_bean_validation((FIXTURES / "quarkus-mini" / src).read_text(encoding="utf-8"), src)
    got = rows_by_field(rows)
    assert got[("amount", "out_of_range")]["value"] == "0"
    assert got[("currency", "too_long")]["value"] == "4"


def test_extract_fluent_validation() -> None:
    src = "Validators/DealRequestValidator.cs"
    rows = extract_fluent_validation((FIXTURES / "dotnet-mini" / src).read_text(encoding="utf-8"), src)
    got = rows_by_field(rows)
    assert ("CounterpartyId", "missing") in got and ("CounterpartyId", "empty") in got
    assert got[("Volume", "out_of_range")]["value"] == "0"
    assert got[("Product", "too_long")]["value"] == "21"
    assert got[("ExternalId", "invalid_format")]["value"] == "!!"


def test_extract_data_annotations() -> None:
    text = (
        "public class Req\n{\n    [Required]\n    [StringLength(10, MinimumLength = 2)]\n"
        "    public string Name { get; set; }\n    [Range(1, 5)]\n    public int Stars { get; set; }\n"
        "    [EmailAddress]\n    public string Email { get; set; }\n}\n"
    )
    got = rows_by_field(extract_data_annotations(text, "Req.cs"))
    assert ("Name", "missing") in got
    assert got[("Name", "too_long")]["value"] == "11"
    assert got[("Name", "too_short")]["value"] == "1"
    assert got[("Stars", "out_of_range")]["value"] == "0"
    assert got[("Email", "invalid_format")]["value"] == "!!"


def test_extract_pydantic() -> None:
    src = "app/schemas.py"
    rows = extract_pydantic((FIXTURES / "fastapi-mini" / src).read_text(encoding="utf-8"), src)
    got = rows_by_field(rows)
    assert ("sku", "missing") in got
    assert got[("sku", "too_short")]["value"] == "2"
    assert got[("sku", "too_long")]["value"] == "21"
    assert got[("quantity", "out_of_range")]["value"] == "0"
    assert got[("customer_email", "invalid_format")]["value"] == "!!"
    assert ("note", "missing") not in got  # optional with default
    assert all(r["expected_status"] == "422" for r in rows)
    assert all(r["field"] not in {"id", "status"} for r in rows)  # OrderOut is not a request


@pytest.fixture()
def dotnet_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = FIXTURES / "dotnet-mini"
    stack = tmp_path / "stack.json"
    ledger_path = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env",
                          str(tmp_path / "env-map.json"), "--out-ledger", str(ledger_path)]) == 0
    ledger = load_ledger(ledger_path)
    merge_entry(ledger, {
        "id": "POST /api/deals", "unresolved": [],
        "request": {"content_type": "application/json", "schema_ref": "Data/Deal.cs"},
        "responses": [{"status": 201, "when": "happy"}, {"status": 400, "when": "validation",
                                                          "rules": True}],
        "exits": [{"kind": "db-write", "table": "deals", "op": "insert",
                   "via": "Services/DealService.cs:27"}],
        "rules": {"sources": [{"file": "Validators/DealRequestValidator.cs", "scanned": False}]},
    })
    save_ledger(ledger_path, ledger)
    return ledger_path, ledger


def test_extract_for_entry_uses_sources_and_writes_candidates(
    dotnet_ledger: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, ledger = dotnet_ledger
    entry = find_entry(ledger, "POST /api/deals")
    rows = extract_for_entry(FIXTURES / "dotnet-mini", "aspnetcore", entry)
    assert {r["field"] for r in rows} == {"CounterpartyId", "Volume", "Product", "ExternalId"}
    out_dir = tmp_path / "karate-tests"
    path = write_candidates(out_dir, entry, rows)
    assert path == out_dir / "rules" / "post-api-deals.candidates.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == CSV_HEADER
        assert all(row["rule_id"] == "" for row in reader)


def test_add_rows_appends_dedupes_and_updates_ledger(dotnet_ledger: tuple[Path, dict[str, Any]],
                                                     tmp_path: Path) -> None:
    ledger_path, ledger = dotnet_ledger
    out_dir = tmp_path / "karate-tests"
    incoming = tmp_path / "rows.csv"
    incoming.write_text(
        ",".join(CSV_HEADER) + "\n"
        ",CounterpartyId,missing,,400,VALIDATION,CounterpartyId is required,Validators/DealRequestValidator.cs:9\n"
        ",Volume,out_of_range,0,400,VALIDATION,Volume must be greater than 0,Validators/DealRequestValidator.cs:10\n",
        encoding="utf-8",
    )
    assert add_rows(out_dir, ledger, "POST /api/deals", incoming) == 2
    assert add_rows(out_dir, ledger, "POST /api/deals", incoming) == 2  # idempotent
    more = tmp_path / "more.csv"
    more.write_text(
        ",".join(CSV_HEADER) + "\n"
        ",Volume,cross_field,gt:DeskLimit,400,VALIDATION,volume exceeds desk limit,Services/DealService.cs:21\n",
        encoding="utf-8",
    )
    assert add_rows(out_dir, ledger, "POST /api/deals", more) == 3
    entry = find_entry(ledger, "POST /api/deals")
    assert entry["rules"]["file"] == "rules/post-api-deals.csv"
    assert entry["rules"]["count"] == 3
    with (out_dir / "rules" / "post-api-deals.csv").open(encoding="utf-8", newline="") as handle:
        ids = [row["rule_id"] for row in csv.DictReader(handle)]
    assert ids == ["R001", "R002", "R003"]


def test_add_rows_rejects_bad_header_and_mutation(dotnet_ledger: tuple[Path, dict[str, Any]],
                                                  tmp_path: Path) -> None:
    _, ledger = dotnet_ledger
    bad_header = tmp_path / "bad.csv"
    bad_header.write_text("field,mutation\nx,missing\n", encoding="utf-8")
    with pytest.raises(KbError, match="header"):
        add_rows(tmp_path, ledger, "POST /api/deals", bad_header)
    bad_mutation = tmp_path / "bad2.csv"
    bad_mutation.write_text(",".join(CSV_HEADER) + "\n,x,explode,,400,,,a:1\n", encoding="utf-8")
    with pytest.raises(KbError, match="mutation"):
        add_rows(tmp_path, ledger, "POST /api/deals", bad_mutation)


def test_mark_scanned(dotnet_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = dotnet_ledger
    mark_scanned(ledger, "POST /api/deals", "Validators/DealRequestValidator.cs")
    assert find_entry(ledger, "POST /api/deals")["rules"]["sources"][0]["scanned"] is True
    mark_scanned(ledger, "POST /api/deals", "Services/DealService.cs")
    files = [s["file"] for s in find_entry(ledger, "POST /api/deals")["rules"]["sources"]]
    assert files == ["Validators/DealRequestValidator.cs", "Services/DealService.cs"]


def test_cli_extract_add_mark(dotnet_ledger: tuple[Path, dict[str, Any]], tmp_path: Path,
                              capsys: pytest.CaptureFixture[str]) -> None:
    ledger_path, _ = dotnet_ledger
    out_dir = tmp_path / "karate-tests"
    assert main(["extract", str(FIXTURES / "dotnet-mini"), "--ledger", str(ledger_path),
                 "--out-dir", str(out_dir)]) == 0
    assert "POST /api/deals: 7 candidate rows" in capsys.readouterr().out
    candidates = out_dir / "rules" / "post-api-deals.candidates.csv"
    assert candidates.is_file()
    assert main(["add", "POST /api/deals", str(candidates), "--ledger", str(ledger_path),
                 "--out-dir", str(out_dir)]) == 0
    assert main(["mark-scanned", "POST /api/deals", "Validators/DealRequestValidator.cs",
                 "--ledger", str(ledger_path)]) == 0
    entry = find_entry(load_ledger(ledger_path), "POST /api/deals")
    assert entry["rules"]["count"] == 7
    assert entry["rules"]["sources"][0]["scanned"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_rules.py -q`
Expected: `ModuleNotFoundError: No module named 'rules'`.

- [ ] **Step 3: Implement `rules.py`**

```python
# skills/karate-bootstrap/scripts/rules.py
"""Phase 3 of karate-bootstrap: validation rules as data.

``extract`` parses declarative validators (Bean Validation, FluentValidation,
.NET data annotations, Pydantic) into candidate rows in
``rules/<slug>.candidates.csv``. A rules subagent confirms candidates, adds the
imperative branches, and appends through ``add``, which assigns sequential
``rule_id`` values, de-duplicates on (field, mutation, value) and updates the
ledger's ``rules.file`` and ``rules.count``. ``mark-scanned`` records that a
validation source has been read.

Boundary values follow one convention so the generated Scenario Outline is
predictable: too_long uses max+1, too_short uses min-1, out_of_range uses the
first excluded integer below the minimum (0 for GreaterThan(0), Positive,
DecimalMin, gt=0), invalid_format uses the literal ``!!``.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any

from flow_map import find_entry, load_ledger, save_ledger
from kb_common import EXIT_OK, KbError, read_text, require_file, run_cli

CSV_HEADER = (
    "rule_id",
    "field",
    "mutation",
    "value",
    "expected_status",
    "expected_code",
    "expected_message_contains",
    "source",
)
MUTATIONS = (
    "missing",
    "null",
    "empty",
    "too_long",
    "too_short",
    "invalid_format",
    "out_of_range",
    "invalid_enum",
    "cross_field",
)
INVALID_FORMAT_VALUE = "!!"


def slug_for(entry_id: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", entry_id.lower())).strip("-")


def _row(field: str, mutation: str, value: str, status: str, source: str) -> dict[str, Any]:
    return {
        "rule_id": "",
        "field": field,
        "mutation": mutation,
        "value": value,
        "expected_status": status,
        "expected_code": "",
        "expected_message_contains": "",
        "source": source,
    }


# --- Bean Validation (Spring, Quarkus) -----------------------------------------------------------

_ANNOTATION_RE = re.compile(r"@(\w+)(?:\(([^)]*)\))?")
_JAVA_FIELD_RE = re.compile(r"^\s*(?:private|public|protected)?\s*(?:final\s+)?[\w<>\[\],.? ]+?\s+(\w+)\s*(?:=|;)")
_ARG_RE = re.compile(r"(\w+)\s*=\s*(\"[^\"]*\"|[-\w.]+)")


def _args(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    named = {k: v.strip('"') for k, v in _ARG_RE.findall(raw)}
    if not named and raw.strip():
        named["value"] = raw.strip().strip('"')
    return named


def _first_int(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", value)
    return int(match.group(0)) if match else None


def extract_bean_validation(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending: list[tuple[int, str, dict[str, str]]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _ANNOTATION_RE.finditer(line):
            pending.append((number, match.group(1), _args(match.group(2))))
        field_match = _JAVA_FIELD_RE.match(line)
        if not field_match or not pending:
            if field_match:
                pending = []
            continue
        field = field_match.group(1)
        for ann_line, name, args in pending:
            src = f"{source_rel}:{ann_line}"
            if name in ("NotNull", "NotBlank", "NotEmpty"):
                rows.append(_row(field, "missing", "", "400", src))
                if name in ("NotBlank", "NotEmpty"):
                    rows.append(_row(field, "empty", "", "400", src))
            elif name == "Size":
                mx, mn = _first_int(args.get("max")), _first_int(args.get("min"))
                if mx is not None:
                    rows.append(_row(field, "too_long", str(mx + 1), "400", src))
                if mn is not None and mn > 0:
                    rows.append(_row(field, "too_short", str(mn - 1), "400", src))
            elif name in ("Min", "DecimalMin", "Positive", "PositiveOrZero"):
                mn = _first_int(args.get("value")) if name in ("Min", "DecimalMin") else (
                    0 if name == "Positive" else -1)
                below = (mn - 1) if name == "Min" and mn is not None else (
                    0 if name in ("DecimalMin", "Positive") else -1)
                rows.append(_row(field, "out_of_range", str(below), "400", src))
            elif name in ("Max", "DecimalMax"):
                mx = _first_int(args.get("value"))
                if mx is not None:
                    rows.append(_row(field, "out_of_range", str(mx + 1), "400", src))
            elif name in ("Pattern", "Email"):
                rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
        pending = []
    return rows


# --- FluentValidation (.NET) -----------------------------------------------------------------------

_RULEFOR_RE = re.compile(r"RuleFor\s*\(\s*\w+\s*=>\s*\w+\.(\w+)\s*\)((?:\s*\.\w+\([^)]*\))+)")
_CHAIN_RE = re.compile(r"\.(\w+)\(([^)]*)\)")


def extract_fluent_validation(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in _RULEFOR_RE.finditer(line):
            field, chain = match.group(1), match.group(2)
            src = f"{source_rel}:{number}"
            for call, raw in _CHAIN_RE.findall(chain):
                arg = _first_int(raw)
                if call in ("NotEmpty", "NotNull"):
                    rows.append(_row(field, "missing", "", "400", src))
                    if call == "NotEmpty":
                        rows.append(_row(field, "empty", "", "400", src))
                elif call == "MaximumLength" and arg is not None:
                    rows.append(_row(field, "too_long", str(arg + 1), "400", src))
                elif call == "MinimumLength" and arg is not None and arg > 0:
                    rows.append(_row(field, "too_short", str(arg - 1), "400", src))
                elif call == "Length":
                    parts = [int(p) for p in re.findall(r"-?\d+", raw)]
                    if len(parts) == 2:
                        if parts[0] > 0:
                            rows.append(_row(field, "too_short", str(parts[0] - 1), "400", src))
                        rows.append(_row(field, "too_long", str(parts[1] + 1), "400", src))
                elif call in ("GreaterThan", "GreaterThanOrEqualTo") and arg is not None:
                    below = arg if call == "GreaterThan" else arg - 1
                    rows.append(_row(field, "out_of_range", str(below), "400", src))
                elif call in ("LessThan", "LessThanOrEqualTo") and arg is not None:
                    above = arg if call == "LessThan" else arg + 1
                    rows.append(_row(field, "out_of_range", str(above), "400", src))
                elif call in ("InclusiveBetween", "ExclusiveBetween"):
                    parts = [int(p) for p in re.findall(r"-?\d+", raw)]
                    if len(parts) == 2:
                        rows.append(_row(field, "out_of_range", str(parts[0] - 1), "400", src))
                elif call in ("Matches", "EmailAddress"):
                    rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
                elif call == "IsInEnum":
                    rows.append(_row(field, "invalid_enum", "NOT_A_VALUE", "400", src))
    return rows


# --- .NET data annotations -------------------------------------------------------------------------

_CS_ATTR_RE = re.compile(r"^\s*\[(\w+)(?:\(([^)]*)\))?\]")
_CS_PROP_RE = re.compile(r"^\s*public\s+[\w<>\[\]?]+\s+(\w+)\s*\{")


def extract_data_annotations(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pending: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        attr = _CS_ATTR_RE.match(line)
        if attr:
            pending.append((number, attr.group(1), attr.group(2) or ""))
            continue
        prop = _CS_PROP_RE.match(line)
        if not prop:
            continue
        field = prop.group(1)
        for attr_line, name, raw in pending:
            src = f"{source_rel}:{attr_line}"
            numbers = [int(n) for n in re.findall(r"-?\d+", raw)]
            named = _args(raw)
            if name == "Required":
                rows.append(_row(field, "missing", "", "400", src))
            elif name == "StringLength" and numbers:
                rows.append(_row(field, "too_long", str(numbers[0] + 1), "400", src))
                mn = _first_int(named.get("MinimumLength"))
                if mn is not None and mn > 0:
                    rows.append(_row(field, "too_short", str(mn - 1), "400", src))
            elif name == "MaxLength" and numbers:
                rows.append(_row(field, "too_long", str(numbers[0] + 1), "400", src))
            elif name == "MinLength" and numbers and numbers[0] > 0:
                rows.append(_row(field, "too_short", str(numbers[0] - 1), "400", src))
            elif name == "Range" and len(numbers) >= 1:
                rows.append(_row(field, "out_of_range", str(numbers[0] - 1), "400", src))
            elif name in ("RegularExpression", "EmailAddress", "Url", "Phone"):
                rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "400", src))
        pending = []
    return rows


# --- Pydantic ----------------------------------------------------------------------------------------

_PY_CLASS_RE = re.compile(r"^class\s+(\w+)\s*\(([^)]*)\)\s*:")
_PY_FIELD_RE = re.compile(r"^\s{4}(\w+)\s*:\s*([^=]+?)(?:\s*=\s*(.+))?$")
_PY_KW_RE = re.compile(r"(\w+)\s*=\s*(r?\"[^\"]*\"|r?'[^']*'|[-\w.]+)")


def extract_pydantic(text: str, source_rel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    in_model = False
    for number, line in enumerate(text.splitlines(), start=1):
        klass = _PY_CLASS_RE.match(line)
        if klass:
            bases = klass.group(2)
            in_model = "BaseModel" in bases and not klass.group(1).endswith(("Out", "Response"))
            continue
        if not in_model:
            continue
        field_match = _PY_FIELD_RE.match(line)
        if not field_match:
            continue
        field, annotation, default = field_match.group(1), field_match.group(2), field_match.group(3)
        src = f"{source_rel}:{number}"
        kwargs = dict(_PY_KW_RE.findall(default or ""))
        required = default is None or (default.startswith("Field(") and "..." in default.split(",")[0])
        if required and "None" not in annotation:
            rows.append(_row(field, "missing", "", "422", src))
        mx, mn = _first_int(kwargs.get("max_length")), _first_int(kwargs.get("min_length"))
        if mx is not None:
            rows.append(_row(field, "too_long", str(mx + 1), "422", src))
        if mn is not None and mn > 0:
            rows.append(_row(field, "too_short", str(mn - 1), "422", src))
        gt, ge = _first_int(kwargs.get("gt")), _first_int(kwargs.get("ge"))
        if gt is not None:
            rows.append(_row(field, "out_of_range", str(gt), "422", src))
        elif ge is not None:
            rows.append(_row(field, "out_of_range", str(ge - 1), "422", src))
        lt, le = _first_int(kwargs.get("lt")), _first_int(kwargs.get("le"))
        if lt is not None:
            rows.append(_row(field, "out_of_range", str(lt), "422", src))
        elif le is not None and gt is None and ge is None:
            rows.append(_row(field, "out_of_range", str(le + 1), "422", src))
        if "pattern" in kwargs or "regex" in kwargs or "EmailStr" in annotation:
            rows.append(_row(field, "invalid_format", INVALID_FORMAT_VALUE, "422", src))
    return rows


# --- orchestration -------------------------------------------------------------------------------------

_EXTRACTORS = {
    "spring": (extract_bean_validation,),
    "quarkus": (extract_bean_validation,),
    "aspnetcore": (extract_fluent_validation, extract_data_annotations),
    "python": (extract_pydantic,),
}


def extract_for_entry(root: Path, stack: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [s["file"] for s in entry.get("rules", {}).get("sources", [])]
    schema_ref = (entry.get("request") or {}).get("schema_ref")
    if schema_ref and schema_ref not in sources:
        sources.append(schema_ref)
    rows: list[dict[str, Any]] = []
    for source_rel in sources:
        path = root / source_rel
        if not path.is_file():
            continue
        text = read_text(path)
        for extractor in _EXTRACTORS.get(stack, ()):
            rows.extend(extractor(text, source_rel))
    return rows


def _rules_dir(out_dir: Path) -> Path:
    path = out_dir / "rules"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CSV_HEADER:
            raise KbError(f"{path}: CSV header must be exactly {','.join(CSV_HEADER)}")
        rows = list(reader)
    for row in rows:
        if row["mutation"] not in MUTATIONS:
            raise KbError(f"{path}: unknown mutation {row['mutation']!r}; expected one of {MUTATIONS}")
        if not row["expected_status"].isdigit():
            raise KbError(f"{path}: expected_status must be an integer, got {row['expected_status']!r}")
    return rows


def write_candidates(out_dir: Path, entry: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    path = _rules_dir(out_dir) / f"{slug_for(entry['id'])}.candidates.csv"
    _write_csv(path, rows)
    return path


def add_rows(out_dir: Path, ledger: dict[str, Any], entry_id: str, rows_csv: Path) -> int:
    entry = find_entry(ledger, entry_id)
    incoming = _read_csv(require_file(rows_csv, "rows CSV"))
    target = _rules_dir(out_dir) / f"{slug_for(entry_id)}.csv"
    existing = _read_csv(target) if target.is_file() else []
    seen = {(r["field"], r["mutation"], r["value"]) for r in existing}
    for row in incoming:
        key = (row["field"], row["mutation"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        existing.append(row)
    for index, row in enumerate(existing, start=1):
        row["rule_id"] = f"R{index:03d}"
    _write_csv(target, existing)
    rules = entry.setdefault("rules", {"file": None, "count": 0, "sources": []})
    rules["file"] = f"rules/{target.name}"
    rules["count"] = len(existing)
    return len(existing)


def mark_scanned(ledger: dict[str, Any], entry_id: str, source_rel: str) -> None:
    rules = find_entry(ledger, entry_id).setdefault("rules", {"file": None, "count": 0, "sources": []})
    for source in rules["sources"]:
        if source["file"] == source_rel:
            source["scanned"] = True
            return
    rules["sources"].append({"file": source_rel, "scanned": True})


def _cmd_extract(args: argparse.Namespace) -> int:
    root = args.repo / args.service_dir if args.service_dir else args.repo
    ledger = load_ledger(args.ledger)
    stack = str(ledger["stack"]["framework"])
    for entry in ledger["entry_points"]:
        if not any(r.get("rules") for r in entry.get("responses", [])):
            continue
        rows = extract_for_entry(root, stack, entry)
        path = write_candidates(args.out_dir, entry, rows)
        print(f"{entry['id']}: {len(rows)} candidate rows -> {path}")
    return EXIT_OK


def _cmd_add(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    count = add_rows(args.out_dir, ledger, args.entry_id, args.rows_csv)
    save_ledger(args.ledger, ledger)
    print(f"{args.entry_id}: {count} rules")
    return EXIT_OK


def _cmd_mark_scanned(args: argparse.Namespace) -> int:
    ledger = load_ledger(args.ledger)
    mark_scanned(ledger, args.entry_id, args.source)
    save_ledger(args.ledger, ledger)
    print(f"{args.entry_id}: scanned {args.source}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validation rules as CSV data")
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="Write candidate rows from declarative validators")
    extract.add_argument("repo", type=Path)
    extract.add_argument("--service-dir", default=None)
    extract.add_argument("--ledger", type=Path, required=True)
    extract.add_argument("--out-dir", type=Path, required=True, help="karate-tests directory")
    extract.set_defaults(func=_cmd_extract)

    add = sub.add_parser("add", help="Append confirmed rows to rules/<slug>.csv")
    add.add_argument("entry_id")
    add.add_argument("rows_csv", type=Path)
    add.add_argument("--ledger", type=Path, required=True)
    add.add_argument("--out-dir", type=Path, required=True)
    add.set_defaults(func=_cmd_add)

    scanned = sub.add_parser("mark-scanned", help="Record that a validation source was read")
    scanned.add_argument("entry_id")
    scanned.add_argument("source")
    scanned.add_argument("--ledger", type=Path, required=True)
    scanned.set_defaults(func=_cmd_mark_scanned)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(run_cli(main))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest skills/karate-bootstrap/tests/test_kb_rules.py -q`
Expected: all pass. The count of 7 in `test_cli_extract_add_mark` is: `NotEmpty` on CounterpartyId gives missing and empty (2), `GreaterThan(0)` on Volume gives one out_of_range (1), `NotEmpty().MaximumLength(20)` on Product gives missing, empty and too_long (3), `Matches` on ExternalId gives invalid_format (1). `Data/Deal.cs` carries only a `[Table]` attribute, which the data-annotations extractor ignores, so it adds nothing.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check skills/karate-bootstrap && python -m mypy`
Expected: clean. Likely E501 on the long regex constants; wrap them. If mypy complains that `_EXTRACTORS` values have heterogeneous callable types, annotate: `_EXTRACTORS: dict[str, tuple[Callable[[str, str], list[dict[str, Any]]], ...]]` and import `Callable` from `collections.abc`.

- [ ] **Step 6: Run the full repo gates**

Run: `python -m ruff check . && python -m mypy && python -m pytest -q`
Expected: all clean, all green. This is the Plan 1 exit state.

- [ ] **Step 7: Commit**

```bash
git add skills/karate-bootstrap/scripts/rules.py skills/karate-bootstrap/tests/test_kb_rules.py
git commit -m "feat(karate-bootstrap): rules.py extracts declarative validators into CSV candidates

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Plan 1 exit criteria

- `ruff check .`, `mypy`, `pytest -v` green at the repo root, including the existing `tech-debt-scan` suite.
- `python skills/karate-bootstrap/scripts/detect.py`, `discover.py`, `flow_map.py`, `rules.py` all run direct-path with `--help`.
- Running detect, discover, then `flow_map.py validate --phase traced` against `tests/fixtures/spring-mini` reports exactly three "not traced" gaps and nothing else, proving the pipeline is wired end to end up to the first LLM step.

Plan 2 picks up from here with `scaffold.py`, the Java harness templates, `report.py`, `iterate.py`, the git checkpoint script, subagent prompt files, cheat sheets and `SKILL.md`.

