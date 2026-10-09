# Cache plan

1. Move caching out of `src/svc/legacy_cache.py` into `src/svc/storage.py`.
2. Delete `src/svc/legacy_cache.py` once nothing imports it.
