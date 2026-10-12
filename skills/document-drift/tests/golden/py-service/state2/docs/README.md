# svc

A small key-value service with an HTTP API and MCP tools.

## Usage

Install the package and start the service with `svc serve`.

The service listens on port 9090 by default; pass `--port` to change it.

Pass `--workers` to run more than one worker process.

Set `SVC_LOG_LEVEL` to `debug` to log every request.

Each command opens the database once and closes it on exit.

## HTTP API

The service registers three HTTP routes in `src/svc/routes.py`.

## Storage

The store **never** blocks: reads and writes return at once.

`store.sync` was removed in 1.2; every write is saved without it.

SQLite's `VACUUM` reclaims the space that purged items leave behind.
