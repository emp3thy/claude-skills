# ASP.NET Core cheat sheet

Loaded for `stack.framework: aspnetcore`. Marker regexes live in `scripts/markers.py`; this
sheet explains them for a tracer and lists the tokens the `verify-refs` gate accepts.

## Entry points

- Controllers: `[ApiController]` classes with `[Route("api/[controller]")]`; `[controller]`
  expands to the class name without the `Controller` suffix, lower-cased. Methods carry
  `[HttpGet]`, `[HttpPost]`, `[HttpPut]`, `[HttpDelete]`, `[HttpPatch]` with an optional route
  template; route constraints such as `{id:guid}` become `{id}` in the entry id.
- Minimal APIs: `app.MapGet("/path", ...)`, `MapPost`, `MapPut`, `MapDelete`, `MapPatch` in
  `Program.cs` or extension methods; the handler line is the `Map*` call.
- Entry id: `<METHOD> <full path>` with a leading slash.

## Exits: database writes

- EF Core: `DbSet.Add`, `AddAsync`, `AddRange`, `AddRangeAsync`, `Update`, `UpdateRange`,
  `Remove`, `RemoveRange`, followed by `SaveChanges` or `SaveChangesAsync`. Point `via` at the
  `SaveChanges*` line; `op` from the `DbSet` call that precedes it.
- Raw SQL: `ExecuteSqlRaw`, `ExecuteSqlInterpolated`, `ExecuteUpdate`, `ExecuteDelete` (`op`
  from the statement).
- Dapper `Execute` with INSERT/UPDATE/DELETE text.

## Exits: message publish

- Apache.NMS (AMQP): `IMessageProducer.Send(message)` and `SendAsync`; the producer is created
  with `session.CreateProducer(destination)`, where the destination came from
  `session.GetQueue("name")` or `GetTopic("name")`. Follow the producer field back to its
  creation to find the name.
- MassTransit: `IPublishEndpoint.Publish<T>`, `ISendEndpoint.Send`; the destination is the
  message type's mapped name or the `ReceiveEndpoint` name.

## Subscriptions

- NMS: `session.GetQueue("name")` or `GetTopic("name")` followed by `CreateConsumer` and
  `consumer.Listener += handler` in a `BackgroundService`; the entry id is `amq <name>` and
  the handler line is the `GetQueue`/`GetTopic` call.
- MassTransit: `IConsumer<T>` implementations and `ReceiveEndpoint("name", ...)`.

## Exits: outbound HTTP

- `HttpClient` and typed clients (`IHttpClientFactory`, `AddHttpClient<T>`): `GetAsync`,
  `PostAsync`, `PutAsync`, `DeleteAsync`, `SendAsync`, `GetFromJsonAsync`, `PostAsJsonAsync`,
  `PutAsJsonAsync`, `GetStringAsync`. `host_key` is the env var behind the client's
  `BaseAddress` (a `Pricing__BaseUrl` style configuration key). YARP routes are outbound
  proxies: record them as `http-out` with the cluster's destination key.

## Reads

- EF: `Find`, `FindAsync`, `FirstOrDefault*`, `SingleOrDefault*`, `ToList*`, `Any*`, `Count*`
  on a `DbSet`; record `db-read` with the table. Consumed HTTP responses are `http-in` reads.

## Table and destination names

- `[Table("name")]` on the entity wins; else the `DbSet<T>` property name in the `DbContext`;
  else the class name. Check `OnModelCreating` for `ToTable(...)`.
- Queue and topic names are the literals passed to `GetQueue`/`GetTopic` or configuration keys
  under `Amq__*`.

## Config keys and roles

- Files: `appsettings.json` (base only; `appsettings.<Environment>.json` is ignored). Keys are
  flattened with `__`: `ConnectionStrings:Deals` is `ConnectionStrings__Deals`, and that is
  also the env var name.
- `db`: `ConnectionStrings__*`, any `Host=` placeholder. `amq`: `Amq__*`, `ActiveMq__*`,
  `Artemis__*`, any `amqp://`, `activemq:` or `failover:` placeholder. `auth`: `Auth__*`,
  `Authentication__*`, `Jwt__*`, keys containing `Authority`, `Issuer`, `Jwks`.
  `downstream:<name>`: `<Name>__BaseUrl`, `<Name>__Url`, named after the first segment
  (`Pricing__BaseUrl` becomes `pricing`).

## Readiness

- Manifest probe when present; common app paths are `/health/ready`, `/health`, `/healthz`.
  Fallback: port wait.

## Auth switches

- `Auth__Enabled=false` (or `Authentication__Enabled`) guarding `AddAuthentication` and
  `UseAuthentication` in `Program.cs`; a `RequireAuthorization()` toggle.
- jwks mode: `Auth__Authority` (issuer) with JWT bearer; the harness's issuer is plain HTTP, so
  the app must set `RequireHttpsMetadata = false` for tests, and the README notes it when the
  code does not.

## Validation

- FluentValidation: `AbstractValidator<T>` classes with `RuleFor(x => x.Field)` chains
  (`NotEmpty`, `NotNull`, `MaximumLength`, `MinimumLength`, `Length`, `GreaterThan`,
  `GreaterThanOrEqualTo`, `LessThan`, `LessThanOrEqualTo`, `InclusiveBetween`,
  `ExclusiveBetween`, `Matches`, `EmailAddress`); status 400 with a `ValidationProblemDetails`
  body unless a filter changes it.
- Data annotations on the request type: `[Required]`, `[StringLength]`, `[Range]`,
  `[RegularExpression]`, `[MaxLength]`, `[MinLength]`, `[EmailAddress]`, `[Url]`, `[Phone]`,
  `[Compare]`; `[ApiController]` returns 400 automatically.

## Migrations and boot behaviour

- EF migrations under a `Migrations/` directory; `db.Database.Migrate()` at startup means
  `also_on_boot`.

## Marker tokens verify-refs accepts

A `via` line, or any line within three lines before or after it, must contain one of these
literal tokens for its exit kind.

- entry-http: `[Http`, `.Map`
- entry-amq: `GetQueue(`, `GetTopic(`, `ReceiveEndpoint(`, `IConsumer<`, `Listener +=`
- db-write: `SaveChanges`, `.Add(`, `.AddAsync(`, `.AddRange(`, `.Update(`, `.Remove(`, `.RemoveRange(`, `ExecuteSql`, `ExecuteUpdate`, `ExecuteDelete`
- amq-publish: `.Send(`, `.SendAsync(`, `.Publish(`, `.PublishAsync(`, `CreateProducer(`
- http-out: `HttpClient`, `.GetAsync(`, `.PostAsync(`, `.PutAsync(`, `.DeleteAsync(`, `.SendAsync(`, `FromJsonAsync`, `AsJsonAsync`, `GetStringAsync(`
- validation: `RuleFor(`, `[Required`, `[StringLength`, `[Range`, `[RegularExpression`, `[MaxLength`, `[MinLength`, `[EmailAddress`, `[Url`, `[Phone`, `[Compare`
