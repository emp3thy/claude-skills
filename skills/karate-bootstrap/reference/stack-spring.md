# Spring Boot cheat sheet

Loaded for `stack.framework: spring`. Marker regexes live in `scripts/markers.py`; this sheet
explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- `@RestController` classes; the class-level `@RequestMapping("/prefix")` prefixes every method
  path.
- Methods: `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`, `@PatchMapping`, with
  the path in `value` or `path` or as the bare string; `@RequestMapping(method = ...)` also
  counts. Path variables stay as `{id}` in the entry id.
- Entry id: `<METHOD> <full path>`, for example `POST /api/shipments`. Handler is the annotated
  method's line.

## Exits: database writes

- Spring Data repositories: `save`, `saveAll`, `saveAndFlush`, `delete`, `deleteById`,
  `deleteAll`, `deleteAllById`; `op` is `insert` for a new entity, `update` for a loaded one,
  `delete` for the delete family.
- JPA: `EntityManager.persist`, `merge`, `remove`; `@Modifying @Query` methods (`op` from the
  query verb).
- JDBC: `JdbcTemplate.update`, `batchUpdate` (`op` from the SQL verb).
- Hibernate `Session.save/update/delete` in older code.

## Exits: message publish

- `JmsTemplate.convertAndSend(destination, payload)` and `send(destination, creator)`; the
  destination is the first argument or a `@Value` config key. Spring's default is a queue;
  `spring.jms.pub-sub-domain=true` makes every destination a topic.

## Subscriptions

- `@JmsListener(destination = "name")` methods are `amq-subscribe` entries with id
  `amq <name>`; `containerFactory` with pub-sub enabled means `type: topic`.

## Exits: outbound HTTP

- `RestTemplate` (`getForObject`, `postForEntity`, `exchange`), `WebClient`, `RestClient`,
  `@FeignClient` interfaces. `host_key` is the env var behind the base URL (`@Value`,
  `@ConfigurationProperties`, or the Feign `url` attribute). Path as the literal with
  `{placeholders}`.

## Reads

- Repository `findBy*`, `findById`, `existsBy*`, `count*`; `EntityManager.find`; JDBC
  `query*`. Record `db-read` with the table.
- The response of any outbound call the code consumes is an `http-in` read.

## Table and destination names

- Entity classes: `@Table(name = "...")` wins; otherwise Spring's default naming turns
  `ShipmentAudit` into `shipment_audit`. `@Entity(name)` names the entity, not the table.
- Destinations: literal strings or config keys under `spring.artemis.*` and custom
  `*.queue`/`*.topic` keys.

## Config keys and roles

- Files: `application.yml`, `application.yaml`, `application.properties` (base profile only;
  `application-<profile>.*` and `src/test` variants are ignored). Manifest env wins over the
  Dockerfile which wins over config placeholders.
- `db`: `assign_role` gives `db` only when the key contains one of `datasource`,
  `connectionstrings`, `database_url`, `jdbc`, `db_url`, `db-url`, `hibernate.connection`,
  `pghost`, `pgdatabase`, or the placeholder value matches `jdbc:`, `postgres`, or `host=`. That
  covers `spring.datasource.url|username|password` and any `hibernate.connection.*` key; most of
  `spring.jpa.*` does not qualify — `spring.jpa.show-sql` and `spring.jpa.hibernate.ddl-auto` are
  `passthrough`.
- `amq`: `spring.artemis.broker-url|user|password`, `spring.jms.*`,
  any `tcp://`, `amqp://` or `failover:` placeholder. `auth`: keys containing `security`,
  `oauth2`, `jwt`, `issuer`, `jwks`, `oidc`. `downstream:<name>`: any other key ending in
  `url`, `uri`, `base-url`, `endpoint` or `host`, named after the key (`pricing.base-url` and
  `PRICING_BASE_URL` both become `pricing`).
- Env var for a config key: relaxed binding, `spring.datasource.url` is
  `SPRING_DATASOURCE_URL`; a `${VAR:default}` placeholder names it directly.

## Readiness

- Manifest `readinessProbe.httpGet.path` when present; Spring Boot's own paths are
  `/actuator/health/readiness` or `/actuator/health`. Fallback: port wait.
- `discover.py` does not exempt this path from entry-point detection: a readiness route written
  as an ordinary `@RestController` handler is picked up like any other and must be traced with
  no exits, while Spring Boot Actuator's own health endpoints avoid this because they carry no
  `@GetMapping`/`@RequestMapping` for the marker regex to match.

## Auth switches

- A boolean under `app.security.*`, `security.enabled`, `auth.enabled` guarding the
  `SecurityFilterChain` bean; a profile such as `noauth` on the security config.
- jwks mode: `spring.security.oauth2.resourceserver.jwt.issuer-uri` or `jwk-set-uri`; the
  harness answers both under `http://wiremock:8080/auth`.

## Validation

- Bean Validation on the request DTO: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`,
  `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@PositiveOrZero`,
  `@Negative`, `@NegativeOrZero`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`, activated by
  `@Valid` on the parameter. Default status 400 (`MethodArgumentNotValidException`).
- Imperative checks in services throw `IllegalArgumentException` or custom exceptions mapped by
  `@ControllerAdvice`; read the advice for the status and error code.

## Migrations and boot behaviour

- Flyway under `src/main/resources/db/migration`, Liquibase under `src/main/resources/db/changelog`.
  `spring.jpa.hibernate.ddl-auto` in `create`, `create-drop`, `update` means the app also
  migrates on boot (`also_on_boot`).

## Marker tokens verify-refs accepts

A `via` line, or any line within three lines before or after it, must contain one of these
literal tokens for its exit kind.

- entry-http: `Mapping`
- entry-amq: `@JmsListener`
- db-write: `.save(`, `.saveAll(`, `.saveAndFlush(`, `.delete`, `.persist(`, `.merge(`, `.remove(`, `@Modifying`, `jdbcTemplate.update(`, `jdbcTemplate.batchUpdate(`
- amq-publish: `convertAndSend(`, `.send(`
- http-out: `restTemplate.`, `RestTemplate`, `WebClient`, `webClient.`, `@FeignClient`, `RestClient`
- validation: `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Min`, `@Max`, `@DecimalMin`, `@DecimalMax`, `@Pattern`, `@Email`, `@Positive`, `@Negative`, `@Past`, `@Future`, `@Digits`, `@AssertTrue`
