# Architecture

## Source tree

```
src/svc/
├── app.py
├── tasks/
│   ├── cleanup_job.py
│   └── scheduler.py
└── storage.py
```

## Seeding

<!-- embedme scripts/seed_v0.py -->
```bash
python scripts/seed_v0.py
```

## Rationale

The first retry loop in `src/svc/retry_v0.py` was kept simple on purpose.
