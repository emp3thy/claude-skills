# Internals

Commands open the database with `open_store` at `src/svc/storage.py:12`, which applies the schema on first use.

A server process wraps that connection in a `Store` at `src/svc/cli.py:45` before the routes see it.

| Stage | Where |
|---|---|
| Startup | `src/svc/cli.py:42-47` |
