# Operations

Behind a proxy that drops idle connections, pass `--timeout` to `svc serve` so a slow request gives up first.

On first start the service opens its database through `src/svc/storage.py:13-21` (`open_store`), so the home directory must be writable.

## serve

| Flag | Default | Notes |
|---|---|---|
| `--port` | `9090` | The port to listen on. |
| `--debug` | off | Verbose request logging. |
| `--worker` | 2 | Worker processes behind the listener. |
