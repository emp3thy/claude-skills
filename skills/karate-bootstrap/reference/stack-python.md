# Python web cheat sheet

Loaded for `stack.framework: python` (FastAPI, Flask or Django). Marker regexes live in
`scripts/markers.py`; this sheet explains them for a tracer and lists the tokens the
`verify-refs` gate accepts.

## Entry points

- FastAPI: `@app.get("/path")`, `@app.post`, `@app.put`, `@app.delete`, `@app.patch`, and the
  same on an `APIRouter` (`@router.post`) whose `prefix=` joins the path. Path parameters stay
  as `{id}`.
- Flask: `@app.route("/path", methods=[...])`, `@bp.route`; one entry per method listed.
- Django: patterns in `urls.py` mapped to views; report each pattern with the view's line as
  the handler.
- Entry id: `<METHOD> <full path>`.

## Exits: database writes

- SQLAlchemy: `session.add`, `add_all`, `delete`, `merge`, then `commit` or `flush`. Point `via`
  at the `add`/`delete` line (the `commit` line is also accepted); `op` from the call.
- psycopg or asyncpg: `cursor.execute("INSERT ...")` and `UPDATE`/`DELETE` text; `op` from the
  statement.
- Django ORM: `Model.save()`, `objects.create`, `update`, `delete`.

## Exits: message publish

- qpid-proton: `container.send`, `sender.send(Message(...))`; the destination is the address
  the sender was created with (`create_sender(conn, "name")`).
- stomp.py: `conn.send(destination="/queue/name", body=...)`; `/queue/` is a queue,
  `/topic/` a topic.

## Subscriptions

- qpid-proton: `create_receiver(conn, "name")` and `on_message` handlers; stomp.py:
  `conn.subscribe(destination="/queue/name", ...)`. Entry id `amq <name>` without the
  `/queue/` or `/topic/` prefix; `type` from the prefix.

## Exits: outbound HTTP

- `httpx.get/post/...`, `httpx.Client`, `httpx.AsyncClient`, `requests.get/post/...`,
  `aiohttp.ClientSession`. `host_key` is the env var read for the base URL (`os.environ`,
  `os.getenv`, a settings module attribute).

## Reads

- SQLAlchemy `session.get`, `query(...)`, `select(...)` executions; psycopg `SELECT`; Django
  `objects.get/filter`. Record `db-read` with the table. Consumed HTTP responses are
  `http-in` reads.

## Table and destination names

- SQLAlchemy `__tablename__` on the model; Django `Meta.db_table` else `<app>_<model>`.
- Destinations are the literal addresses; strip stomp prefixes.

## Config keys and roles

- Sources: `settings.py`, `config.py` attributes read from `os.environ`/`os.getenv`, and
  `.env.example`. Only keys read from the environment carry an env var; a settings attribute
  without one cannot be injected by the harness.
- `db`: `assign_role` gives `db` only when the key contains one of `datasource`,
  `connectionstrings`, `database_url`, `jdbc`, `db_url`, `db-url`, `hibernate.connection`,
  `pghost`, `pgdatabase`, `db_host`, `db_port`, `db_name`, `db_user`, `db_password`, `pgport`,
  `pguser`, `pgpassword`, or the placeholder value matches `jdbc:`, `postgres`, or `host=`. That
  covers `DATABASE_URL`, `PGHOST`, `PGDATABASE`, and a bare `DB_HOST`/`DB_PORT` pair along with
  its `DB_NAME`/`DB_USER`/`DB_PASSWORD` siblings; the scaffold turns a part key into the single
  token it names (`{{db.host}}`, `{{db.port}}`, `{{db.name}}`, `{{db.user}}`,
  `{{db.password}}`) and a URL key into the full `postgresql://` template.
- `amq`: `AMQ_*`, `BROKER_*`, `ARTEMIS_*`, `STOMP_*`, any `amqp://` or `stomp://` placeholder.
  `auth`: keys containing `JWT`, `OIDC`, `ISSUER`, `JWKS`, `AUTH`. `downstream:<name>`: other `*_URL` and
  `*_BASE_URL` keys, named after the prefix (`PRICING_BASE_URL` becomes `pricing`).

## Readiness

- Manifest probe when present; otherwise a port wait (the default port is 8000 for uvicorn
  unless the Dockerfile exposes another).
- `discover.py` does not exempt this path from entry-point detection: a readiness route is an
  ordinary `@app.get`/`@router.get`/`@app.route` handler like any other, so it is picked up and
  must be traced with no exits; FastAPI, Flask and Django have no framework health-check
  middleware to fall back on, so this cannot be sidestepped the way it can in ASP.NET Core or
  Spring.

## Auth switches

- A settings flag such as `AUTH_ENABLED`, `AUTH_MODE=mock`, `DISABLE_AUTH` guarding the
  dependency or middleware that validates tokens.
- jwks mode: `JWKS_URL`, `OIDC_ISSUER`, `AUTH_ISSUER` read by PyJWT, python-jose or Authlib;
  the harness serves `http://wiremock:8080/auth/.well-known/jwks.json`.

## Validation

- Pydantic models: `Field(..., min_length=, max_length=, gt=, ge=, lt=, le=, pattern=)`,
  `constr`, `conint`, `confloat`, `conlist`, `condecimal`, `EmailStr`, `@validator` and
  `@field_validator` methods. FastAPI answers 422 with a `detail` array; Flask and Django code
  usually returns 400 explicitly.
- Imperative checks raise `HTTPException(status_code=...)` or return error responses; read the
  handler and service for them.

## Migrations and boot behaviour

- Alembic under `alembic/versions`, Django under `migrations/`; `Base.metadata.create_all(`
  at startup means `also_on_boot`.

## Marker tokens verify-refs accepts

A `via` line, or any line within three lines before or after it, must contain one of these
literal tokens for its exit kind.

- entry-http: `@app.`, `@router.`, `.route(`
- entry-amq: `create_receiver(`, `.subscribe(`
- db-write: `session.add(`, `session.add_all(`, `session.delete(`, `session.merge(`, `.commit(`, `.flush(`, `.execute(`
- amq-publish: `.send(`, `.publish(`
- http-out: `httpx.`, `requests.`, `aiohttp.`
- validation: `Field(`, `validator`, `constr(`, `conint(`, `confloat(`, `conlist(`, `condecimal(`
