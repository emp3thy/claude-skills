# kv

`kv` is a small key-value store with a command line and an HTTP view.

## Run

```sh
pip install .
kv init
kv sync --dry-run
```

## Commands

| Command or flag | Of | What it does | Default |
|---|---|---|---|
| `init` | | creates the store directory | |
| `--force` | `init` | deletes an existing store first | off |
| `sync` | | writes every stored key to the sync log | |
| `--dry-run` | `sync` | prints each key and writes nothing | off |

`sync` prints each stored key and, without `--dry-run`, appends it to the sync log through `Store.push`.

## Configuration

| Variable | What it holds | Default |
|---|---|---|
| `KV_HOME` | the store directory | `~/.kv` |
| `KV_TOKEN` | the token `sync` writes to the sync log | empty |

## Interfaces

- `/items/<key>` returns the value stored under the key, or 404.
- `Store` keeps each item as one file under `items/` in the store directory.

## Files read and written

- `load_settings` reads `settings.toml` from the store directory and returns no keys when the file is missing.
- `Store.push` appends the key and the token's first four characters to `log/sync.log`.
