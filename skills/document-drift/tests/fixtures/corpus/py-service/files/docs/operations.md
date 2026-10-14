# Operations

Behind a proxy that drops idle connections, pass `--timeout` to `svc serve` so a slow request gives up first.

On first start the service opens its database through `src/svc/storage.py:12-20` (`open_store`), so the home directory must be writable.

## serve

| Flag | Default | Notes |
|---|---|---|
| `--port` | `8080` | The port to listen on. |
| `--debug` | off | Verbose request logging. |
| `--worker` | 2 | Worker processes behind the listener. |
