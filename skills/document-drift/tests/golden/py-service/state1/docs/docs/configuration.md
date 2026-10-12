# Configuration

The service reads these environment variables at start-up.

| Variable | Meaning |
|---|---|
| `SVC_HOME` | Directory that holds the database file. |
| `SVC_PORT` | Port to listen on; wins over the command line. |
| `SVC_WORKERS` | Number of worker processes. |
| `SVC_LOG_LEVEL` | Log level, such as `debug`; the default is `info`. |
