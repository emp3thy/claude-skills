# Live run results

These are the container facts the live fixtures depend on, measured in GitHub Actions because the machine the plan was written on has no container runtime. The command `KB_CONTAINERS=1 pytest -m containers -v` runs in the `karate-live` job of `.github/workflows/test.yml`.

## Image spike

Results from workflow run [34035182342](https://github.com/emp3thy/claude-skills/actions/runs/34035182342), 2026-09-06, all three passing in 63 seconds total:

| Assumption | Result | Evidence |
|-----------|--------|----------|
| A Flyway image whose entrypoint builds the JDBC URL from `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` migrates a database and exits 0 | **pass, after a correction** | The first run (34034833130) failed with `docker: Error response from daemon: unable to find user flyway: no matching entries in passwd file`, exit 125: the `flyway/flyway:10.17.3-alpine` image ships no `flyway` account, so the `USER root` / `USER flyway` pair in the Dockerfile is invalid. Removing both lines and running the one-shot container as the image's default user makes it pass. About 18 seconds including the image build. |
| `EXTRA_ARGS=--http-host 0.0.0.0 --relax-jolokia --queues <queue> --addresses <address>` creates both destinations and logs `AMQ221007` | **pass first time** | `artemis queue stat` lists the queue and `artemis address show` lists the address. About 12 seconds. |
| `python-qpid-proton` installs on `python:3.12-slim` | **the original assumption was wrong** | `pip install --only-binary :all: python-qpid-proton==0.39.0` failed with `Could not find a version that satisfies the requirement ... (from versions: none)`. PyPI's current release is 0.40.0 and publishes only a macOS cp312 wheel, a Windows cp313 wheel and a source distribution: there is no manylinux wheel, so a Linux image must build it from source. The test now measures that path (apt `gcc`, `cmake`, `swig`, `libssl-dev`, `python3-dev`, then `pip install python-qpid-proton==0.40.0` and an `import proton` check) and passes in about 33 seconds. |

## Consequences for the fixtures

- Every fixture's `db-manager/Dockerfile` copies the spike's shape without any `USER` line.
- The Artemis destination arguments need no change, and the ledger's destinations drive them.
- The `fastapi-orders` image installs the five build dependencies before `pip install python-qpid-proton==0.40.0`, and its build costs roughly half a minute, so the in-run image build stays within the job budget.

## Fixture runs (design spec section 11)

Rows are added as each fixture's live run goes green.

| Fixture | Stack | Entry points | Scenarios green | Planted defect | App image | Run |
