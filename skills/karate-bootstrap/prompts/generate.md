# Generate the Karate feature for $entry_id

You are a test author working for the karate-bootstrap skill. Write the feature file, stub
mappings, seed data and example request for one entry point, under `$tests_dir` only. The suite
documents observed behaviour of the application as it is today; it does not judge it. You never
touch application source, the Dockerfile or anything outside the tests directory.

## Inputs

- Repository root: `$repo`
- Tests directory: `$tests_dir`
- Entry point, fully traced:

```json
$entry_json
```

- Validation rules file: `$rules_file` ($rules_count rows). When it is `none`, write no `@rules`
  outline.
- Downstream services the app calls, each stubbed by WireMock under
  `http://wiremock:8080/<name>`: $downstreams
- Auth: $auth_instruction
- Entry kind: $entry_instruction

## Files to write

| File | Content |
|------|---------|
| `src/test/resources/$feature_file` | the feature below. Features live on the test classpath under `src/test/resources/`; `stubs/`, `seed/` and `rules/` sit at the tests root, which the `pom.xml` also puts on the classpath, so `read('classpath:...')` reaches all of them |
| `$example_file` | a valid base request body as JSON (for AMQ entries, a valid message body); omit it when the entry's `request` is `null` (a GET or DELETE with no body) and leave it out of the reply |
| `$seed_file` | SQL inserts the feature needs beyond what it creates itself (reference rows the handler reads); additive only, unique keys, `-- comments` allowed |
| `$stubs_dir/<downstream>/default.json` | WireMock mappings for every `http-out` exit and `http-in` read, one file per downstream, `{"mappings":[...]}`; add or extend, never delete another entry's mappings |
| `$stubs_dir/<downstream>/<error>.json` | only when a failure path needs a different downstream answer and cannot be driven by request data |

## Rules that keep the suite green in parallel (design spec 5.6)

1. Scenarios run four at a time against one app, one database, one broker and one WireMock.
   Nothing may depend on a global reset.
2. Every scenario derives a unique value in its Background (`* def uid = java.util.UUID.randomUUID() + ''`),
   puts it in the request, and asserts rows and messages by it.
3. Stubs are suite-level and discriminate by request data (path parameter, query, body) with
   `priority`. A failure path is driven by a reserved input the mapping documents, for example a
   product code `ERR-500` answered with a 500 by a low-priority mapping. Every `urlPath` starts
   with `/<downstream>`.
4. Messages are matched by content: `Jms.await('deal.created', 5000, { dealId: response.id })`.
5. Downstream calls are verified by unique data: `Stubs.verify('GET', '/pricing/rates/' + uid, 1)`
   when the path carries it, else `Stubs.verify('POST', '/pricing/quotes', base.externalId, 1)`
   which matches on the request body.
6. A scenario that must reset shared state (`Stubs.reset`, `Stubs.load`, `Db.truncate`, or the
   `stubs:`/`truncate:` arguments of `reset.feature`) carries `@parallel=false` and restores the
   default stubs before it ends. The generated gate rejects such calls without the tag.
7. Validation outlines never write; they read `$rules_file` through the `mutate` helper.
8. Do not write scenarios for 401 or 403 unless the auth instruction above says tokens are in
   play. Do not write a scenario for a response the trace did not record.

## Harness API (globals in every feature)

- `appBaseUrl`; `mutate(base, field, mutation, value)`; `checkError(response, code, messageContains)`
  returns `[]` when the serialised body contains both values, skipping a check whose argument is
  empty (so empty CSV cells pass); `skipContainers`.
- `Db.run(path)`, `Db.row(table, where)`, `Db.awaitRow(table, where, timeoutMs)`,
  `Db.count(table, where)`, `Db.truncate(tables)`.
- `Jms.watch(dest)`, `Jms.await(dest, timeoutMs)`, `Jms.await(dest, timeoutMs, matchMap)`,
  `Jms.publish(dest, body, headers)`.
- `Stubs.reset()`, `Stubs.load(path)`, `Stubs.verify(method, urlPath, times)`,
  `Stubs.verify(method, urlPath, bodyContains, times)`.
- `Jwt.token(claims)`.
- `call read('classpath:common/reset.feature') { watch: [...], truncate: [...], seed: 'classpath:seed/x.sql', stubs: [...] }`
  applied in that order; `seed` is additive and parallel-safe, `truncate` and `stubs` need
  `@parallel=false`.

## Feature shape

Adapt this shape to the entry. Tags: `@smoke` on the happy path, `@error` on failure paths,
`@rules` on the validation outline, `@amq` on AMQ-driven features, `@known-defect` never (the
fix loop adds it).

```gherkin
@smoke
Feature: POST /api/deals

Background:
  * def uid = java.util.UUID.randomUUID() + ''
  * call read('classpath:common/reset.feature') { watch: ['deal.created'] }
  * def base = read('classpath:seed/examples/post-api-deals.json')
  * set base.externalId = 'EXT-' + uid

Scenario: creates a deal, writes deals and deal_audit, publishes deal.created
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 201
  And match response contains { id: '#uuid', status: 'PENDING' }
  * def row = Db.row('deals', { external_id: base.externalId })
  * match row.status == 'PENDING'
  * match Db.count('deal_audit', { deal_id: row.id }) == 1
  * def msg = Jms.await('deal.created', 5000, { dealId: response.id })
  * match msg.body.externalId == base.externalId
  * Stubs.verify('POST', '/pricing/quotes', base.externalId, 1)

@error
Scenario: unknown counterparty returns 404
  * set base.counterpartyId = 'CP-MISSING-' + uid
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 404

@rules
Scenario Outline: validation rule <rule_id> on <field>
  * def payload = mutate(base, '<field>', '<mutation>', '<value>')
  Given url appBaseUrl
  And path '/api/deals'
  And request payload
  When method post
  Then status <expected_status>
  * match checkError(response, '<expected_code>', '<expected_message_contains>') == []

  Examples:
    | read('classpath:rules/post-api-deals.csv') |
```

## Cross-field rules

`mutate`'s `cross_field` case cannot turn a symbolic expression such as `before:tradeDate` into
two concrete values, so a `cross_field` row never goes through the outline. When `$rules_file`
holds any such rows, first drop them from the outline's `Examples` cell: `| karate.filter(read('classpath:$rules_file'), function(r){ return r.mutation != 'cross_field' }) |`
(Karate evaluates the cell as a JS expression). Then write one `@rules` scenario by hand for
each dropped row: take `base`, set the row's `field` to a concrete value that violates the
expression against the other field it names (a date earlier than `base.tradeDate` for
`before:tradeDate` on `settlementDate`; a value not greater than `base.limit` for `gt:limit`;
and so on for `after`, `lt`, `eq` and `ne`), send it, and assert the row's literal
`expected_status`, `expected_code` and `expected_message_contains`. Name the rule id in the
scenario title:

```gherkin
@rules
Scenario: validation rule R003 settlementDate before tradeDate
  * set base.settlementDate = '2024-01-01'
  Given url appBaseUrl
  And path '/api/deals'
  And request base
  When method post
  Then status 422
  * match checkError(response, 'DATE_ORDER', 'settlement before trade') == []
```

When `$rules_file` has no `cross_field` rows, the outline stays exactly as the "Feature shape"
section shows.

## Stub mapping shape

One file per downstream, suite-level. `priority` 1 wins over 5.

```json
{
  "mappings": [
    {
      "priority": 5,
      "request": { "method": "POST", "urlPath": "/pricing/quotes" },
      "response": { "status": 200, "headers": { "Content-Type": "application/json" },
                    "jsonBody": { "price": 42.5, "currency": "USD" } }
    },
    {
      "priority": 1,
      "request": { "method": "POST", "urlPath": "/pricing/quotes",
                   "bodyPatterns": [ { "contains": "ERR-500" } ] },
      "response": { "status": 500, "jsonBody": { "error": "pricing unavailable" } }
    }
  ]
}
```

## Reply

After writing the files, reply with the JSON object as raw text (no code fence, no prose),
listing every path you wrote relative to `$tests_dir`; the feature may be listed either as
`$feature_file` or `src/test/resources/$feature_file` (the skill records them on the ledger
with `flow_map.py mark`, which stores features relative to `src/test/resources`):

```json
{
  "features": ["$feature_file"],
  "stubs": ["stubs/pricing/default.json"],
  "seeds": ["$seed_file", "$example_file"],
  "notes": "one line on anything the trace did not cover"
}
```
