# Live run results

Run: `KB_CONTAINERS=1 pytest -m containers -v` in the `karate-live` job of
`.github/workflows/test.yml`. Two workflow runs were needed. The first,
[run 34034833130](https://github.com/emp3thy/claude-skills/actions/runs/34034833130)
(2026-09-06, commit `92d8a9a`), surfaced two wrong assumptions. The Dockerfile and the
proton test were corrected in commit `096d104` and re-run as
[run 34035182342](https://github.com/emp3thy/claude-skills/actions/runs/34035182342)
(2026-09-06, commit `096d104`, PR #11), which is the run this table records.

| Assumption | Result | Evidence |
|---|---|---|
| A Flyway image with an entrypoint that builds `FLYWAY_URL` from `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` migrates a database and exits 0 | pass (after one fix) | Run 34034833130 failed before the entrypoint ever ran: `docker: Error response from daemon: unable to find user flyway: no matching entries in passwd file` (exit 125). `flyway/flyway:10.17.3-alpine` is built from `eclipse-temurin:17-jre-alpine` with no `USER` instruction anywhere in the upstream Dockerfile (checked against `flyway/flyway-docker` on GitHub), so it has no `flyway` account and runs as root by default. The spike's Dockerfile dropped its `USER root`/`USER flyway` pair. Run 34035182342: `test_flyway_wrapper_migrates_from_pg_environment` PASSED — the migration container exited 0 and `select count(*) from spike` returned `"0"`. |
| `EXTRA_ARGS=--http-host 0.0.0.0 --relax-jolokia --queues <q> --addresses <t>` creates both destinations and logs `AMQ221007` | pass (first try) | `test_artemis_creates_the_destinations_the_harness_asks_for` PASSED on both runs. The test asserts `AMQ221007` appears in `artemis.log` and that `artemis queue stat` output contains `spike.requested` and `artemis address show` output contains `spike.created`; pytest does not capture stdout for a passing test under plain `-v`, so the literal CLI text is not in the CI log, but both substring assertions passed on real broker output in run 34035182342. |
| `pip install --only-binary :all: python-qpid-proton==0.39.0` succeeds on `python:3.12-slim` | fail — assumption was wrong; test rewritten, replacement passes | Run 34034833130: `ERROR: Could not find a version that satisfies the requirement python-qpid-proton==0.39.0 (from versions: none)`. Checked PyPI's JSON API directly (`pypi.org/pypi/python-qpid-proton/0.39.0/json` and `.../json` for the latest release, 0.40.0): `python-qpid-proton` ships `bdist_wheel` only for macOS (`cp38-abi3-macosx_11_0_x86_64`) and Windows (`cp38-abi3-win_amd64`), plus an `sdist`. It has never published a manylinux/Linux wheel, at 0.39.0 or the current 0.40.0, so `--only-binary :all:` can never succeed on `python:3.12-slim`. The test was rewritten to `test_qpid_proton_builds_from_source_on_slim_python`, which installs `gcc cmake swig libssl-dev python3-dev` via `apt-get`, then `pip install python-qpid-proton==0.40.0` (a source build) and runs `python -c 'import proton; print(proton.VERSION)'`. Run 34035182342: PASSED, importing successfully and printing a version tuple. |

Times observed (from run 34035182342's per-test pytest timestamps; each figure is that
test's full wall time, not an isolated sub-step): Flyway test (image build, Postgres
startup, migration run, verification query) ~16s, Artemis test (container start to
`AMQ221007`, `queue stat`, `address show`) ~12s, proton source-build test (`apt-get
install` plus `pip install` compiling the C core) ~33s. Whole job: `3 passed, 734
deselected in 63.18s`.

Consequences for the fixtures: Tasks 3 to 5's db-manager Dockerfile must not add a
`USER flyway` (or any named non-root user) step — `flyway/flyway:*-alpine` has no such
account, and a one-shot migration container works fine as the image's default (root)
user. Tasks 3 to 5 may assume the `--http-host 0.0.0.0 --relax-jolokia --queues <q>
--addresses <t>` shape of `EXTRA_ARGS` reliably creates both destinations and logs
`AMQ221007`, so the harness's wait-for-`AMQ221007` pattern needs no change. Task 5's
`fastapi-orders` fixture image must never rely on a `python-qpid-proton` wheel on Linux —
none exists at any published version — and must instead install `gcc`, `cmake`, `swig`,
`libssl-dev` and `python3-dev` before `pip install`ing it, budgeting for a compile step
(observed ~33s for a bare install; a fuller fixture image may take longer).
