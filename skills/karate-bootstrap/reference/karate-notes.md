# Karate notes (1.5.2)

## Runner flags

`KarateRunner` runs `classpath:features` excluding `@known-defect`, writes cucumber JSON and
JUnit XML, with `kb.threads` (default 4) parallel scenarios. Under `-Dkb.skipContainers=true`
it also requires `@harness`. `-Dkarate.options="..."` accepts Karate's own CLI options: a
feature path, `--tags @smoke`, `--tags ~@rules`.

## Tags

- `@smoke` happy path, `@error` failure paths, `@rules` validation outline, `@amq` AMQ-driven
  feature, `@known-defect` quarantined (excluded from every run), `@harness` container-free
  self-test, `@parallel=false` Karate's built-in tag that serialises a scenario or feature.
- `@ignore` on `common/reset.feature` keeps it out of the run; it only executes through `call`.

## Data-driven outlines

`Examples:` with a single cell `| read('classpath:rules/<slug>.csv') |` expands the outline to
one scenario per CSV row; column names become `<placeholders>`. The CSV is a Maven test
resource because `pom.xml` registers `rules/`, `stubs/` and `seed/` at the module root. Row
names appear in reports as the outline name with placeholders substituted.

## Calling reset.feature

`* call read('classpath:common/reset.feature') { watch: ['deal.created'], seed: 'classpath:seed/x.sql' }`
applies `watch`, `truncate`, `seed`, `stubs` in that order. `watch` subscribes before the
request so no message is missed. `seed` is additive and parallel-safe. `truncate` and `stubs`
change shared state: the calling scenario needs `@parallel=false`. Variables the call defines
(`args`, `watch`, `stubs`) leak into the caller when the call has no `def`; do not reuse those
names.

## Java helpers

Exposed by `karate-config.js` as `mutate`, `checkError` and `skipContainers` unconditionally;
`appBaseUrl`, `Db`, `Jms`, `Stubs` and `Jwt` only when containers start (not under
`-Dkb.skipContainers=true`). JavaScript maps pass to Java as `Map<String, Object>`; arrays as
`List`. `Jms.await(dest, ms, { key: value })` matches on message body fields by string
comparison and leaves other messages in the inbox in order. `Stubs.verify(method, urlPath,
times)` counts journal entries; the four-argument form adds a body `contains` clause. Failures
raise `AssertionError` with the expected and recorded counts.

## Reports

`target/karate-reports/<package.qualified.name>.json` per feature (cucumber JSON: `uri`
`features/<name>.feature`, `elements[]` with `keyword` `Scenario` or `Scenario Outline`,
`tags[].name`, `steps[].result.status` and `error_message`), `<name>.xml` JUnit,
`karate-summary-json.txt` with counts, `karate-summary.html`. `@known-defect` scenarios never
appear in these files; `kb_report.py parse` counts them from the feature files instead.
