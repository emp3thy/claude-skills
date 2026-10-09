# drift-cli

A command line tool that reports documentation drift.

Requires Go 1.22 or later.

## Reporters

- `internal/report/json.go` writes JSON
- `internal/report/table.go` prints a table

Version 1 flags are translated by `internal/compat/v1shim.go` before parsing.

Persistence code lives in `internal/storage/`.

## Make targets

```sh
make build
make test
```

## Notes

Each run records its cursor in `state.json`.

A future reporter would go in `internal/report/xml.go`.

Roughly `4/5` runs finish in under a second.

`internal/report/csv.go` was removed; convert the JSON output instead.
