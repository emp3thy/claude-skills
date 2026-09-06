# Testcontainers harness notes

What the Java harness under `karate-tests/src/test/java/kb/harness/` does, for the agent running
the suite and the developer reading it afterwards. Nothing here is templated per repo.

## Topology

One Docker network, started lazily by `karate-config.js` on the first scenario unless
`-Dkb.skipContainers=true`:

1. Postgres `postgres:16-alpine`, alias `db`, port 5432, database, user and password from
   `kb-runtime.json`.
2. Artemis `apache/activemq-artemis:2.44.0-alpine`, alias `artemis`, AMQP on 5672 (core 61616,
   STOMP 61613, console 8161). Queues (anycast) and topics (multicast) are pre-created from
   the runtime file through `EXTRA_ARGS --queues ... --addresses ...`. Ready when the log shows
   `AMQ221007`.
3. WireMock `wiremock/wiremock:3.13.2-alpine`, alias `wiremock`, port 8080, ready on
   `GET /__admin/health`. In `jwks` auth mode the harness imports discovery and JWKS mappings
   under `/auth` before the app starts.
4. The db-manager image from `migrations.image`, one-shot (`OneShotStartupCheckStrategy`, five
   minute cap), must exit 0; its output is `target/db-manager.log`.
5. The app, built with `ImageFromDockerfile` from the service root and `app.dockerfileRel`, or
   `-Dapp.image=<tag>` to skip the build. Env from the runtime file with tokens substituted.
   Readiness from `app.readinessPath`, else a port wait; serverless doubles the timeout.

A failed start is remembered and rethrown by every later scenario instead of retried. A JVM
shutdown hook stops the containers and closes the JMS connection (needed when Ryuk is off).

## kb-runtime.json

`src/test/resources/kb-runtime.json`, written by `kb_scaffold.py`, schema version 1: `app`
(`repoRootRel`, `dockerfileRel`, `port`, `readinessPath`, `serverless`,
`startupTimeoutSeconds`), `env[]` (`name`, `role`, `value` with tokens), `db`, `migrations`
(`strategy`, `image`, `env`), `amq` (`user`, `password`, `queues`, `topics`), `downstreams[]`
(`name`, `envVar`), `auth` (`mode`, and `key`/`value` or `issuerKeys`). Re-running the scaffold
rewrites it; nothing else in the module is repo-specific.

## Tokens

Substituted by `Containers` at start: `{{db.host}}`=`db`, `{{db.port}}`=`5432`,
`{{db.name}}`, `{{db.user}}`, `{{db.password}}`, `{{amq.host}}`=`artemis`,
`{{amq.amqpPort}}`=`5672`, `{{amq.corePort}}`=`61616`, `{{amq.stompPort}}`=`61613`,
`{{amq.user}}`, `{{amq.password}}`, `{{stubs.url}}`=`http://wiremock:8080`,
`{{auth.url}}`=`http://wiremock:8080/auth`. Each downstream is reached as
`{{stubs.url}}/<name>`, so every stub `urlPath` starts with `/<name>`.

## Waits and timeouts

- Artemis: log message, 120 s. WireMock: HTTP health. db-manager: exit 0 within 5 minutes.
- App: `startupTimeoutSeconds` (default 120, doubled when serverless) on the readiness path or
  the listening port. A slow first image build counts against it only after the build.
- `Jms.await` default 5000 ms in generated features; `Db.awaitRow` polls every 250 ms.

## Logs and evidence files

Under `karate-tests/target/`: `postgres.log`, `artemis.log`, `wiremock.log`, `db-manager.log`,
`app.log` (also echoed through SLF4J with prefix `app`), `stubs-unmatched.json` (WireMock's
unmatched requests and near misses, written by the runner after a containerised run),
`karate-reports/` (cucumber JSON per feature, JUnit XML, HTML), `surefire-reports/`.

## Running

- `mvn -B test` from `karate-tests/` (JDK 17 or newer, a container engine). `./mvnw -B test`
  when Maven is not installed.
- `-Dkb.skipContainers=true` runs only `@harness` features (the smoke self-test).
- `-Dkb.threads=1` runs scenarios sequentially; `-Dapp.image=<tag>` uses a prebuilt image;
  `-Dkarate.options="--tags @smoke"` or `"classpath:features/x.feature"` narrows the run.
- Ryuk needs `ryuk.container.privileged=true` (set in `testcontainers.properties`); podman users
  read `podman.md`.
