# Command line

The package installs one console script, `svc`.

| Command | What it does |
|---|---|
| `serve` | Run the HTTP service. |
| `check` | Verify the database file. |
| `export` | Write every item as JSON lines. |

## `svc serve`

| Flag | Meaning |
|---|---|
| `--host` | Address to bind (default `127.0.0.1`). |
| `--port` | Port to listen on. |
| `--workers` | Number of worker processes (default 2). |

## `svc check`

`--db` names the database file to verify; `--repair` rebuilds a damaged file.

## `svc export`

`--output` names the file to write; `-`, the default, writes to standard output.
