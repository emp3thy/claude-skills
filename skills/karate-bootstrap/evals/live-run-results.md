# Live run results

These are the container facts the live fixtures depend on, measured in GitHub Actions because the machine the plan was written on has no container runtime. The command `KB_CONTAINERS=1 pytest -m containers -v` runs in the `karate-live` job of `.github/workflows/test.yml`.

## Image spike

Results from workflow run [34035182342](https://github.com/emp3thy/claude-skills/actions/runs/34035182342), 2026-09-06, all three passing in 63 seconds total:

| Assumption | Result | Evidence |
|-----------|--------|----------|
| A Flyway image whose entrypoint builds the JDBC URL from `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` migrates a database and exits 0 | **pass, after a correction** | The first run (34034833130) failed with `docker: Error response from daemon: unable to find user flyway: no matching entries in passwd file`, exit 125: the `flyway/flyway:10.17.3-alpine` image ships no `flyway` account, so the `USER root` / `USER flyway` pair in the Dockerfile is invalid. Removing both lines and running the one-shot container as the image's default user makes it pass. About 18 seconds including the image build. |
| `EXTRA_ARGS=--http-host 0.0.0.0 --relax-jolokia --queues <queue> --addresses <address>` creates both destinations and logs `AMQ221007` | **pass first time** | `artemis queue stat` lists the queue and `artemis address show` lists the address. About 12 seconds. |
| `python-qpid-proton` installs on `python:3.12-slim` | **the original assumption was wrong** | `pip install --only-binary :all: python-qpid-proton==0.39.0` failed with `Could not find a version that satisfies the requirement ... (from versions: none)`. PyPI's current release is 0.40.0 and publishes only a macOS cp312 wheel, a Windows cp313 wheel and a source distribution: there is no manylinux wheel, so a Linux image must build it from source. The test now measures that path (apt `gcc`, `cmake`, `swig`, `libssl-dev`, `python3-dev`, then `pip install python-qpid-proton==0.40.0` and an `import proton` check) and passes in about 33 seconds. |

## Consequences for the fixtures

- Every fixture's `db-manager/Dockerfile` copies the spike's shape without any `USER` line.
- The Artemis destination arguments need no change, and the ledger's destinations drive them.
- The `fastapi-orders` image installs the five build dependencies before `pip install python-qpid-proton==0.40.0`, and its build costs roughly half a minute, so the in-run image build stays within the job budget.

## Fixture runs (design spec section 11)

Rows are added as each fixture's live run goes green.

| Fixture | Stack | Entry points | Scenarios green | Planted defect | App image | Run |
|---------|-------|--------------|-----------------|----------------|-----------|-----|
| spring-shipments | spring | 3 (`POST /api/shipments`, `GET /api/shipments/{id}`, `amq shipment.requested`) | 21 of 22 (1 quarantined) | DEF-001: weight over 1000kg answers 500, not 400 | built in-run from the fixture's `Dockerfile` (`-Dapp.image` not used) | [34038461187](https://github.com/emp3thy/claude-skills/actions/runs/34038461187), 2026-09-06, job wall-clock 2m7s |

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
