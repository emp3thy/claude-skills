# svc

A small HTTP service with background tasks.

Requires Python 3.10+.

## Layout

- `src/svc/app.py` builds the application
- `src/svc/routes.py` maps URLs to views
- `src/svc/legacy_cache.py` caches responses in memory
- `src/svc/storage.py` persists records

Read the [local setup steps](docs/setup.md#local-setup) before running anything.

Authentication is handled by [the auth module](src/svc/old_auth.py) for every request.

Digest emails are sent by `src/svc/mailer_v1.py` once a day.

## Commands

```bash
make install
make lint
make test
```

## Notes

The service writes `state.json` next to the process for crash recovery.

Probes call `/health` every ten seconds.

Operators trigger a release with the `/deploy` chat command.

Retries back off after `3/5` failed attempts.

A future module such as `src/svc/handlers_admin.py` would sit beside the others.

The build steps create `out/` for the wheels.

<!-- drift-ignore: kept until the 1.x branch is retired -->

The `src/svc/compat_shim.py` module keeps 1.x imports working.

`src/svc/legacy_cache.py` was removed; the storage layer caches responses now.
