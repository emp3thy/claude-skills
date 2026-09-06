# Quarkus cheat sheet

Loaded for `stack.framework: quarkus`. Marker regexes live in `scripts/markers.py`; this sheet
explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- JAX-RS resources: class-level `@Path("/prefix")` plus method `@GET`, `@POST`, `@PUT`,
  `@DELETE`, `@PATCH`; the method's own `@Path` sits on the line before or after the verb
  annotation. Reactive routes (`@Route`) are rare in these repos; report them as unresolved
  with the file:line if you meet one.
- Entry id: `<METHOD> <full path>`. Handler is the verb annotation's line.

## Exits: database writes

- Panache: `persist`, `persistAndFlush`, `delete`, `deleteById`, `deleteAll`, `update("...")`
  on entities or repositories; `op` from the call (update statements: read the JPQL verb).
- JPA: `EntityManager.persist`, `merge`, `remove`.
- `@Transactional` on a method does not itself write; find the statement inside.

## Exits: message publish

- SmallRye Reactive Messaging: `Emitter<T>.send(payload)` on a field annotated
  `@Channel("name")`; `@Outgoing("name")` methods. The destination is
  `mp.messaging.outgoing.<name>.address` when set, else the channel name. Topic when the
  connector config says so; default queue.

## Subscriptions

- `@Incoming("name")` methods are `amq-subscribe` entries; the ledger id uses the resolved
  address (`mp.messaging.incoming.<name>.address` when set, else the channel name).

## Exits: outbound HTTP

- MicroProfile REST clients: interfaces with `@RegisterRestClient(configKey = "...")`, injected
  with `@RestClient`; `RestClientBuilder`; Vert.x `WebClient`. `host_key` is the env var behind
  `quarkus.rest-client.<configKey>.url` or the client's URL config. Path from the interface's
  `@Path` plus the method's.

## Reads

- Panache `findById`, `find(...)`, `list(...)`, `count(...)`; `EntityManager.find`; record
  `db-read` with the table. Consumed REST client responses are `http-in` reads.

## Table and destination names

- `@Table(name = "...")` wins; Quarkus' default physical naming keeps the entity name as-is
  unless `quarkus.hibernate-orm.physical-naming-strategy` is set. Check `persistence.xml` or
  `import.sql` for explicit names.
- Destinations resolve through `mp.messaging.*.address`, then the channel name.

## Config keys and roles

- Files: `application.properties`, `application.yml`, `application.yaml` (base profile;
  `%dev.` and `%test.` prefixed keys are ignored).
- `db`: `assign_role` gives `db` only when the key contains one of `datasource`,
  `connectionstrings`, `database_url`, `jdbc`, `db_url`, `db-url`, `hibernate.connection`,
  `pghost`, `pgdatabase`, or the placeholder value matches `jdbc:`, `postgres`, or `host=`. That
  covers `quarkus.datasource.jdbc.url` and `quarkus.datasource.username|password` (both contain
  `datasource`); most of `quarkus.hibernate-orm.*` does not qualify —
  `quarkus.hibernate-orm.database.generation` is `passthrough`.
- `amq`: `quarkus.qpid-jms.url|username|password`, `amqp-host`,
  `amqp-port`, `mp.messaging.*`, any `amqp://` placeholder. `auth`: `quarkus.oidc.*`, keys
  containing `jwt`, `issuer`, `jwks`. `downstream:<name>`: `quarkus.rest-client.<name>.url`
  and other `*.url` keys, named after the key.
- Env var: `quarkus.datasource.jdbc.url` is `QUARKUS_DATASOURCE_JDBC_URL`; `${VAR:default}`
  placeholders name it directly.

## Readiness

- Manifest probe when present; Quarkus' own paths are `/q/health/ready` and `/q/health`.
  Fallback: port wait.

## Auth switches

- `quarkus.oidc.enabled=false` removes OIDC; `quarkus.http.auth.*` policies can be set
  permissive by config; a `%test` profile is ignored by the skill, so look for a plain key.
- jwks mode: `quarkus.oidc.auth-server-url` (issuer) and optional `quarkus.oidc.jwks-path`;
  the harness serves discovery at `http://wiremock:8080/auth/.well-known/openid-configuration`.

## Validation

- Hibernate Validator annotations on the request type, the same set as Spring; `@Valid` on the
  parameter. Default status 400 with a `violations` array in the body unless an
  `ExceptionMapper` changes it.

## Migrations and boot behaviour

- Flyway under `src/main/resources/db/migration`; `quarkus.hibernate-orm.database.generation`
  in `drop-and-create`, `update`, `create` means `also_on_boot`.

## Marker tokens verify-refs accepts

- entry-http: `@GET`, `@POST`, `@PUT`, `@DELETE`, `@PATCH`
- entry-amq: `@Incoming`
- db-write: `.persist(`, `.persistAndFlush(`, `.delete(`, `.deleteById(`, `.deleteAll(`, `.merge(`, `.remove(`, `.update(`
- amq-publish: `.send(`, `@Outgoing(`
- http-out: `@RestClient`, `RestClientBuilder`, `WebClient`, `Client.`
- validation: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@Negative`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`
