# Live run results

These are the container facts the live fixtures depend on, measured in GitHub Actions because the machine the plan was written on has no container runtime. The command `KB_CONTAINERS=1 pytest -m containers -v` runs in the `karate-live` job of `.github/workflows/test.yml`.

## Image spike

Results from workflow run [34035182342](https://github.com/emp3thy/claude-skills/actions/runs/34035182342), 2026-09-06, all three passing in 63 seconds total:

| Assumption | Result | Evidence |
|-----------|--------|----------|
| A Flyway image whose entrypoint builds the JDBC URL from `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` migrates a database and exits 0 | **pass, after a correction** | The first run (34034833130) failed with `docker: Error response from daemon: unable to find user flyway: no matching entries in passwd file`, exit 125: the `flyway/flyway:10.17.3-alpine` image ships no `flyway` account, so the `USER root` / `USER flyway` pair in the Dockerfile is invalid. `flyway/flyway:*-alpine` is built from `eclipse-temurin:17-jre-alpine` with no `USER` instruction anywhere in the upstream Dockerfile — checked against `flyway/flyway-docker` on GitHub — so it runs as root by default and has no `flyway` account to switch to. Removing both lines and running the one-shot container as the image's default user makes it pass. About 18 seconds including the image build. |
| `EXTRA_ARGS=--http-host 0.0.0.0 --relax-jolokia --queues <queue> --addresses <address>` creates both destinations and logs `AMQ221007` | **pass first time** | pytest does not capture a passing test's stdout under plain `-v`, so the literal `artemis queue stat` and `artemis address show` output text is not in the CI log; what is proven is that the test's `spike.requested` and `spike.created` substring assertions both passed against real broker output. About 12 seconds. |
| `python-qpid-proton` installs on `python:3.12-slim` | **the original assumption was wrong** | `pip install --only-binary :all: python-qpid-proton==0.39.0` failed with `Could not find a version that satisfies the requirement ... (from versions: none)`. `python-qpid-proton` has never published a Linux (manylinux) wheel at any version — not merely at 0.39.0, the version first tried: PyPI's current release, 0.40.0, publishes only a macOS cp312 wheel, a Windows cp313 wheel and a source distribution, so a Linux image must always build it from source. The test now measures that path (apt `gcc`, `cmake`, `swig`, `libssl-dev`, `python3-dev`, then `pip install python-qpid-proton==0.40.0` and an `import proton` check) and passes in about 33 seconds; only this source build at 0.40.0 was proven — 0.39.0 was never build-tested, only its wheel-only install, which failed. |

## Consequences for the fixtures

- Every fixture's `db-manager/Dockerfile` copies the spike's shape without any `USER` line: `flyway/flyway:*-alpine` has no `flyway` account and runs as root by default, so a named-user step would fail the same way the spike's first run did.
- The Artemis destination arguments need no change, and the ledger's destinations drive them.
- **The verified pin is `python-qpid-proton==0.40.0`, not the `0.39.0` in Task 5's brief.** The `fastapi-orders` image must install `gcc`, `cmake`, `swig`, `libssl-dev` and `python3-dev` — all five packages, not the three (`gcc`, `cmake`, `libssl-dev`) Task 5's brief lists — before `pip install python-qpid-proton==0.40.0`; its build costs roughly half a minute, so the in-run image build stays within the job budget. This version and this package list supersede the ones printed in Task 5's own brief: only `0.40.0`'s source build was proven here; `0.39.0` was never build-tested, only its wheel-only install, which failed.

## Fixture runs (design spec section 11)

Rows are added as each fixture's live run goes green.

| Fixture | Stack | Entry points | Scenarios green | Planted defect | App image | Run |
|---------|-------|--------------|-----------------|----------------|-----------|-----|
| spring-shipments | spring | 3 (`POST /api/shipments`, `GET /api/shipments/{id}`, `amq shipment.requested`) | 21 of 22 (1 quarantined) | DEF-001: weight over 1000kg answers 500, not 400 | pre-built via `docker build` before the Karate run (`-Dapp.image=kb-live-app-spring-shipments-<hash>`) | [34038461187](https://github.com/emp3thy/claude-skills/actions/runs/34038461187), 2026-09-06, job wall-clock 2m7s |
| dotnet-deals | aspnetcore | 3 (`POST /api/deals`, `GET /api/deals/{id}`, `amq deal.requested`) | 20 of 21 (1 quarantined) | DEF-001: quantity over 10000 answers 500, not 400 | pre-built via `docker build` before the Karate run (`-Dapp.image=kb-live-app-dotnet-deals-<hash>`) | [34042475664](https://github.com/emp3thy/claude-skills/actions/runs/34042475664), 2026-09-06, job wall-clock 2m0s |
| fastapi-orders | python | 4 (`GET /healthz`, `POST /api/orders`, `GET /api/orders/{order_id}`, `amq order.requested`) | 21 of 22 (1 quarantined) | DEF-001: quantity over 500 answers 500, not 422 | built in-run from the fixture's `Dockerfile` (`-Dapp.image` not used; `prebuild_app_image=False`) | [34044805100](https://github.com/emp3thy/claude-skills/actions/runs/34044805100), 2026-09-06, job wall-clock 2m25s (pytest 127.84s), after a first red run at [34044513286](https://github.com/emp3thy/claude-skills/actions/runs/34044513286) |

Pass criteria, from the spec: the second Maven run exits 0, every entry in
`expected-flow-map.yaml` is present in the ledger, zero unresolved, and `defects.md` carries
the planted defect. All four hold for every row above.

Not covered by these runs, and why:

- **A Podman host.** All three jobs ran on `ubuntu-latest` with Docker; `reference/podman.md`'s
  `DOCKER_HOST` and rootless-socket instructions are documented, not exercised here.
- **The ADO pipeline.** `azure-pipelines.karate.yml` ships a reusable job; no hosted ADO agent
  has run it in this plan.
- **A multi-service repository.** All three fixtures are single-service repos discovered at
  their root; `--service-dir` is untested by these runs.
- **The Quarkus stack.** It has a cheat sheet (`reference/stack-quarkus.md`) but no live
  fixture in v1, so its regex and mapping have never run against a real container.
- **Authentication.** No fixture implements it, so `flow_map.py set-auth --mode disabled` is
  exercised only as a ledger mutation, and `auth.mode: jwks`, `Jwt.token()` and the WireMock
  JWKS mappings have never run against a real container.
- **`kb_rules.py extract`'s own detection.** The harness runs it and asserts its exit code, but
  its candidate rows are immediately overwritten by the canned `rows.csv` files, so extraction's
  actual rule detection is unproven by these runs.

## Known limitation: `discover.py` can mistake a readiness route for an entry point

`discover.py`'s `parse_manifest` reads the deployment manifest's `readinessProbe.httpGet.path`
into `env_map["readiness"]`, but `find_entry_points` never cross-checks that path: it scans
source files for HTTP route markers with no exemption for whatever route the manifest names as
the readiness check. An application whose readiness route is an ordinary mapped handler — not
framework health-check middleware — is therefore detected as a spurious extra entry point that
then has to be traced, ruled and scaffolded like any other.

Two of the three live fixtures — dotnet-deals and fastapi-orders — hit this, with different
outcomes:

- **dotnet-deals sidesteps it.** `Program.cs` wires up ASP.NET Core's built-in health-check
  middleware (`AddHealthChecks()` / `app.MapHealthChecks("/health/ready")`) instead of a
  `[Route]`-attributed controller action or a `.MapGet`/`.MapPost`/... minimal-API call, so the
  `aspnetcore` `entry-http` marker — which only matches `.Map(Get|Post|Put|Delete|Patch)` — never
  fires on it, and the manifest's `/health/ready` never becomes an entry point.
- **fastapi-orders cannot.** FastAPI has no framework health-check middleware to fall back on;
  `@app.get("/healthz")` is an ordinary route and matches the `python` `entry-http` marker like
  any other handler. The fixture's `app/main.py` documents the choice inline and declares
  `GET /healthz` as a real entry point with no exits rather than hide it from discovery.

Neither workaround is a fix in `discover.py` itself: exempting the manifest's readiness path in
`find_entry_points` needs its own test and a cheat-sheet note across all four stacks, and is out
of scope this late in the plan. A future fixture author, or a user running the skill against a
real repository, should expect an ordinary readiness handler to surface as an entry point unless
the framework's own health-check middleware hides it the way ASP.NET Core's does.

## Deferred, noted for a future plan

- `dotnet-deals`'s `Deals.Api.csproj` pins `Apache.NMS.AMQP` at `2.2.0`, which carries a NuGet
  security advisory; bumping to `2.4.0` or later would clear the `dotnet restore` warning.
- This file's proton line above (under "Consequences for the fixtures") doesn't say that
  `apt-get update` must run before the package install; the proven command does run it, and so
  does `fastapi-orders/Dockerfile`.
- Karate 1.5.2's feature-level `@parallel=false` did not reliably serialise a tagged feature
  against other tagged features in practice (see spring-shipments item 5 below); the fixtures
  isolate by data instead of relying on it.

### spring-shipments: what the first red run forced

Confidence going in was 93%; it took seven pushes to `Live containers (spring-shipments)` to go green, all fixes to the fixture itself, never to the harness under `templates/`:

1. **`qpid-jms-client:1.17.0` does not compile against Spring Boot 3.3.2.** That version's `JmsConnectionFactory` implements `javax.jms.ConnectionFactory`; Spring Boot 3.x needs `jakarta.jms.ConnectionFactory`. Fixed by bumping the *application's own* `pom.xml` to `qpid-jms-client:2.11.0` (confirmed against the `apache/qpid-jms` source at that tag) — the harness template's own `qpid.version=1.17.0` pin is untouched, since `Jms.java` uses the `javax.jms` API directly in a non-Spring module.
2. **No `MessageConverter` bean.** `@JmsListener` fell back to a messaging-layer converter that cannot resolve a plain JSON `TextMessage` to a `Map` without a `__TypeId__` header. Added a `MessageConverter` bean that always round-trips through Jackson as plain JSON text, matching the harness's own `Jms.java` wire format, and wired it into the app's `JmsTemplate`; Spring Boot auto-wires the same bean into the listener container factory.
3. **WireMock stub never loaded.** `common/reset.feature` only imports a stub mapping when the caller passes `stubs: [...]`; the generated features omitted it, so every downstream call 404'd with "no stub mappings in this WireMock instance." Added `stubs: ['classpath:stubs/pricing/default.json']` to both features whose scenarios (or Background setup) call the pricing downstream.
4. **Exclusive-state gate.** Adding `stubs:` tripped `flow_map.py`'s generated-phase gate (`uses exclusive state without @parallel=false`); added `@parallel=false` as a feature-level tag on both features.
5. **`Stubs.verify` flaked in both directions.** First an over-count (both features' successful POST hit the same seeded `/pricing/rates/GB`, so the never-cleared WireMock journal recorded 2 for one feature's exact-count assertion); a same-session fix of calling `Stubs.reset()` per scenario then produced an under-count (0), because karate 1.5.2's feature-level `@parallel=false` does not fully serialize a tagged feature against other tagged features in practice, so a concurrently-running scenario's reset could wipe a just-recorded entry before its own verify ran. The durable fix was to never reset the shared journal and instead give the GET feature's setup POST a disjoint country code (`FR` vs the seed's `GB`), so each feature's verified path is exclusively its own.
6. **False-positive template-leftover check.** `README.md.tmpl` escapes one literal shell-variable reference as `$${XDG_RUNTIME_DIR}` so `string.Template` renders it verbatim; the harness's own assertion checked the *rendered* text for the pre-render `$${` escape, which no longer exists post-render, so the intentional literal always tripped it. Fixed in `test_kb_live_run.py` (not under `templates/`) by excluding that one known literal explicitly.
7. **Invalid YAML in the fixture's own `expected-flow-map.yaml`.** `path: /rates/{countryCode}` unquoted inside a YAML flow mapping (`{ kind: http-out, ..., path: /rates/{countryCode} }`) is a parse error — an unescaped `{` starts a nested flow collection in flow context (block-context values with the same substring, such as an entry `id`, parse fine). Quoted the value.

None of these were design flaws in the skill's procedure: every fix was local to the fixture (`tests/fixtures/live/spring-shipments/`) or to `test_kb_live_run.py`'s own assertions, and none touched `templates/`.

### dotnet-deals: what the first red runs forced

Confidence going in was 92%. Extensive local pre-verification — `dotnet build`/`dotnet run` against the local .NET 9 SDK (net8.0 target), running `detect.py` and `discover.py` for real, and a full non-container dry run of every script the harness calls through the "generated" phase gate — caught one fixture bug before any push (an `app.MapGet("/health/ready", ...)` minimal-API health endpoint that `discover.py`'s aspnetcore regex picked up as a spurious fourth entry point, fixed by switching to `AddHealthChecks()`/`MapHealthChecks()`, which the regex does not match) and confirmed as correct several things the brief only asserted: `FluentValidation.AspNetCore` 11.3.0 really does expose `AddFluentValidationAutoValidation()`, ASP.NET Core's default JSON casing and `GetFromJsonAsync` case-insensitivity need no adjustment, an unhandled exception with no `ASPNETCORE_ENVIRONMENT` set answers a bare 500 with no custom exception handler needed, and the exact `host_key` discovery assigns `Pricing:BaseUrl` is `Pricing__BaseUrl`. None of the three failure modes the brief predicted (connection string shape, queue existence, EF Core column mapping) occurred — all three were already correct. It took two pushes to `Live containers (dotnet-deals)` to go green, both fixes to the fixture's application code, never to the harness under `templates/`:

1. **The container never started: `target/app.log` was completely empty.** `DealPublisher`'s constructor called Apache.NMS.AMQP's `_connection.Start()` synchronously. `DealPublisher` is a singleton the generic host must construct to build `DealRequestedConsumer` (an `IHostedService`), and .NET resolves all hosted services before `Host.StartAsync()` begins — so the AMQP handshake (Apache.NMS.AMQP's own docs: the client waits indefinitely by default on synchronous interactions such as opening a connection) blocked Kestrel from ever binding, and Testcontainers' HTTP readiness probe timed out at exactly its configured window with no output ever captured. Fixed by making `DealPublisher.Connection` lazy (connect on first use) and wrapping `DealRequestedConsumer.ExecuteAsync`'s connect-and-consume loop in a catch-and-retry, with `await Task.Yield()` as the first line so a *fast* synchronous failure (proven locally against no broker at all) cannot fault `BackgroundService.StartAsync`'s synchronous-completion check either — both paths otherwise abort the whole host before Kestrel starts. Verified locally end to end: with zero broker reachable, the app now binds and answers 200 on `/health/ready` within seconds and stays healthy indefinitely while retrying in the background.
2. **Every request that should have succeeded came back 500.** `app.log` showed the app requesting `http://wiremock:8080/quotes/{currency}` instead of `http://wiremock:8080/pricing/quotes/{currency}` — WireMock had no stub for that path, so `PricingClient.PriceAsync` threw on `EnsureSuccessStatusCode()`. `HttpClient.BaseAddress` plus a relative request URI follow RFC 3986 reference resolution: a relative reference starting with `/` replaces the *entire* `BaseAddress` path, not just its last segment, so `Pricing__BaseUrl` = `http://wiremock:8080/pricing` (`kb_scaffold.py`'s downstream template, no trailing slash) combined with `GetFromJsonAsync("/quotes/...")` drops `/pricing` outright. Reproduced and confirmed the fix (a trailing slash on `BaseAddress`, no leading slash on the relative path) with a throwaway `HttpListener` stub before pushing. This is a generic .NET `HttpClient` gotcha, not specific to this application, and would recur in any future aspnetcore fixture built the same way.

Neither was a design flaw in the skill's procedure: both fixes are local to the fixture (`tests/fixtures/live/dotnet-deals/`), and neither touched `templates/` or `test_kb_live_run.py`.

### fastapi-orders: what the first red run forced

Confidence going in was 91%. This fixture is the first to exercise two things at once: the app image is built in-run from the fixture's own `Dockerfile` (`prebuild_app_image=False`, so `Containers.buildApp` in the frozen harness runs `ImageFromDockerfile` against the repo root as the build context) rather than pre-built with `docker build`, and the database is configured as five separate parts (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`) rather than a URL, which is exactly the shape Plan 4 Task 1's `discover.assign_role` fix classifies. Extensive offline pre-verification — installing `python-qpid-proton==0.40.0` and `fastapi`/`pydantic`/`httpx` into throwaway virtualenvs to confirm real API signatures and exact validation-error text against the pinned versions, then running `detect.py`, `discover.py`, every `flow_map.py` phase gate, `kb_rules.py`, and `kb_scaffold.py` for real (everything short of Maven and Docker) against a copy of the fixture — confirmed the entire non-container path end to end before any push: all 4 entry points discovered with the exact expected ids and handlers, every `DB_*` key classified `db` (proving Task 1's fix), `also_on_boot: false` (no stray `create_all(` call), the traced and generated phase gates both passing, the combined rules CSV assembling to the expected 5 rows, and `kb-runtime.json`'s env templating turning `DB_*` into `{{db.*}}` tokens and `INVENTORY_URL` into `{{stubs.url}}/inventory`. That last detail is exactly what the live run caught: a fixture bug the offline dry run had no way to exercise, because it only manifests once a real HTTP call leaves the container.

It took one push to `Live containers (fastapi-orders)` to go green, one fix, local to the fixture, never to the harness under `templates/`:

1. **Every successful-path `POST /api/orders` answered 500, not just the planted-defect one.** `app.log` showed `json.decoder.JSONDecodeError: Expecting value: line 2 column 48` from `response.json()` in `service.create_order`, for requests with entirely valid bodies. `wiremock.log` showed why: `[path regex] /stock/[A-Z]{3}-[0-9]{4} | /inventory/stock/AAA-0001 <<<<< URL does not match`. `kb_scaffold.py` templates a downstream env var as `{{stubs.url}}/<downstream-name>` (confirmed in the dry-run `kb-runtime.json`: `INVENTORY_URL` = `{{stubs.url}}/inventory`), so the app's real outgoing request is `.../inventory/stock/{sku}` even though the app's own code, and the flow-map/trace `path` field, only ever mention the app-relative `/stock/{sku}` (the same convention dotnet-deals' `/pricing/quotes/{currency}` and spring-shipments' pricing stub already followed, and which this fixture's stub and `Stubs.verify` call were written without). Fixed by prefixing both `stubs/inventory/default.json`'s `urlPathPattern` and the feature's `Stubs.verify` call with `/inventory`; no application code changed. The planted-defect scenario (`rejects an order over the quantity limit`, expecting 422 against the app's real 500) was quarantined as designed and is DEF-001 in `expected/defects.md`.

Not a design flaw in the skill's procedure: the fix is local to the fixture (`tests/fixtures/live/fastapi-orders/expected/generated/`), and did not touch `templates/` or `test_kb_live_run.py` beyond the one harness assertion Task 5 was scoped to add (the `DB_*` role check immediately after `discover.py`, which passed on the first run).
