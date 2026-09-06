# Failure triage

Used in the run-and-iterate phase. One hypothesis and one change per iteration, logged with
`kb_iterate.py log` before the change is made. Evidence per failure group comes from
`kb_iterate.py next`: the failing step and its match diff, the tail of `target/app.log`,
`target/stubs-unmatched.json`, and `target/db-manager.log` when the failure is at startup.

## Classification order

Work down the list; the first class that fits wins.

## 1. Infra

Container did not start, wait timeout, connection refused, db-manager exited non-zero,
`topology failed earlier` on every scenario. Signs: the failure is in the first scenario to run,
`app.log` ends before readiness, `db-manager.log` shows a migration error. Fix inside
`karate-tests/` only: `kb-runtime.json` values (env, readiness path, timeout), the db-manager
image reference, stub mappings the app needs at boot. A Dockerfile that does not build, a
missing base image, or an app that needs a service the harness does not provide is not
fixable here: log the iteration with `--classification infra --unfixable` and let
`check-stop` stop the run.

## 2. Stub or seed missing

WireMock answered 404 (the request appears in `stubs-unmatched.json`, usually with a near miss
naming the closest mapping), a foreign-key violation, an empty read the scenario expected to
find. Add or widen the stub mapping under `stubs/<downstream>/`, or add the reference rows to
the entry's seed file. Keep mappings suite-level and matched by request data.

## 3. Expectation wrong

The app answered consistently and not erroneously, and the generated expectation was the
guess: a 200 where 201 was assumed, a different field name, a message published on a
different destination, a validation message worded differently. Adopt the observed behaviour
in the feature or the rules CSV, and record it with
`flow_map.py override --entry <id> --scenario <name> --field <what> --old <expected> --new <observed> --reason "..."`
so the README lists it.

## 4. Suspected app defect

A 5xx, a stack trace in the response or `app.log`, behaviour contradicting the app's own
validation, data written that the request did not ask for. Do not change the app. Quarantine
the scenario and document it.

## Quarantine procedure

1. Add `@known-defect` to the scenario (or the feature when every scenario is affected).
2. Append an entry to `karate-tests/defects.md` in the spec's format: `## DEF-NNN: <title>`,
   then `status: pending`, `slug`, `severity` (high, medium, low), `category: app-defect`,
   `entry_point: <ledger id>`, `scenario: features/<file>.feature:<line>`, `evidence: |` with
   request, response and the `app.log` lines, `root_cause: <file:line and one sentence>`,
   `suggested_fix: <one sentence>`.
3. Re-run; the green gate accepts the failure only when the owning entry's id appears on an
   `entry_point:` line in `defects.md`.

## Stop conditions

`kb_iterate.py check-stop` stops the run (exit 6) at the iteration cap (default 15), when the
same signature has been logged three iterations in a row, or when the last iteration was logged
`--unfixable`. A stopped run still commits what it has and writes the README with the counts,
so a developer can pull the branch and continue.
