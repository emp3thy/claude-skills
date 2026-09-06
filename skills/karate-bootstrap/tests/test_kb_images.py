"""Container-image facts the live fixtures depend on, measured rather than assumed.

This machine had no container runtime when Plan 4 was written, so three assumptions could
not be checked locally: a Flyway image driven by ``PG*`` variables migrates a database, an
Artemis container creates the destinations ``Containers.artemisExtraArgs`` names, and
``python-qpid-proton`` builds from source on ``python:3.12-slim`` (no manylinux wheel is
published for it). Each is a test here.

Opt in with ``KB_CONTAINERS=1``; CI runs it in the ``karate-live`` job.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.containers,
    pytest.mark.skipif(os.environ.get("KB_CONTAINERS") != "1",
                       reason="set KB_CONTAINERS=1 to run containers"),
]

ARTEMIS_IMAGE = "apache/activemq-artemis:2.44.0-alpine"
POSTGRES_IMAGE = "postgres:16-alpine"
PYTHON_IMAGE = "python:3.12-slim"
QPID_PROTON = "python-qpid-proton==0.40.0"
PROTON_BUILD_DEPS = "gcc cmake swig libssl-dev python3-dev"


def docker(*args: str, check: bool = True,
           timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Run the docker CLI, capturing output. Raises on a non-zero exit when ``check``."""
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"docker {' '.join(args)} exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout[-4000:]}\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


@pytest.fixture()
def network() -> Iterator[str]:
    name = f"kb-spike-{uuid.uuid4().hex[:8]}"
    docker("network", "create", name)
    try:
        yield name
    finally:
        docker("network", "rm", name, check=False)


def _run_detached(image: str, name: str, network_name: str, *extra: str) -> None:
    docker("run", "-d", "--rm", "--name", name, "--network", network_name,
           "--network-alias", name, *extra, image)


def _stop(name: str) -> None:
    docker("rm", "-f", name, check=False)


def test_flyway_wrapper_migrates_from_pg_environment(tmp_path: Path, network: str) -> None:
    """The db-manager shape every fixture uses: PG* in, a migrated schema out."""
    build = tmp_path / "db-manager"
    (build / "sql").mkdir(parents=True)
    (build / "sql" / "V1__init.sql").write_text(
        "CREATE TABLE spike (id integer primary key);\n", encoding="utf-8")
    (build / "entrypoint.sh").write_text(
        "#!/bin/sh\nset -eu\n"
        'exec flyway -url="jdbc:postgresql://${PGHOST}:${PGPORT}/${PGDATABASE}" '
        '-user="${PGUSER}" -password="${PGPASSWORD}" -locations=filesystem:/flyway/sql '
        "-connectRetries=20 migrate\n",
        encoding="utf-8", newline="\n")
    (build / "Dockerfile").write_text(
        "FROM flyway/flyway:10.17.3-alpine\n"
        "COPY sql /flyway/sql\n"
        "COPY entrypoint.sh /entrypoint.sh\n"
        "RUN chmod +x /entrypoint.sh\n"
        'ENTRYPOINT ["/entrypoint.sh"]\n',
        encoding="utf-8", newline="\n")
    tag = f"kb-spike-dbm-{uuid.uuid4().hex[:8]}"
    docker("build", "-t", tag, str(build))
    db = f"kb-spike-db-{uuid.uuid4().hex[:8]}"
    try:
        _run_detached(POSTGRES_IMAGE, db, network,
                      "-e", "POSTGRES_DB=spike", "-e", "POSTGRES_USER=app",
                      "-e", "POSTGRES_PASSWORD=app")
        docker("run", "--rm", "--network", network,
               "-e", f"PGHOST={db}", "-e", "PGPORT=5432", "-e", "PGDATABASE=spike",
               "-e", "PGUSER=app", "-e", "PGPASSWORD=app", tag)
        check = docker("exec", db, "psql", "-U", "app", "-d", "spike", "-tAc",
                       "select count(*) from spike")
        assert check.stdout.strip() == "0", check.stdout
    finally:
        _stop(db)
        docker("image", "rm", "-f", tag, check=False)


def test_artemis_creates_the_destinations_the_harness_asks_for(network: str) -> None:
    """``artemisExtraArgs`` builds ``--queues a,b --addresses c``; both must exist."""
    name = f"kb-spike-mq-{uuid.uuid4().hex[:8]}"
    extra_args = ("--http-host 0.0.0.0 --relax-jolokia "
                  "--queues spike.requested --addresses spike.created")
    try:
        _run_detached(ARTEMIS_IMAGE, name, network,
                      "-e", "ARTEMIS_USER=artemis", "-e", "ARTEMIS_PASSWORD=artemis",
                      "-e", "ANONYMOUS_LOGIN=false", "-e", f"EXTRA_ARGS={extra_args}")
        deadline = 180
        wait = (f"for i in $(seq 1 {deadline}); do "
                "grep -q AMQ221007 /var/lib/artemis-instance/log/artemis.log && exit 0; "
                "sleep 1; done; exit 1")
        proc = docker("exec", name, "sh", "-c", wait, check=False, timeout=deadline + 60)
        assert proc.returncode == 0, "artemis never logged AMQ221007 (the harness waits on it)"
        queues = docker("exec", name, "/var/lib/artemis-instance/bin/artemis", "queue", "stat",
                        "--user", "artemis", "--password", "artemis")
        assert "spike.requested" in queues.stdout, queues.stdout
        addresses = docker("exec", name, "/var/lib/artemis-instance/bin/artemis", "address",
                           "show", "--user", "artemis", "--password", "artemis")
        assert "spike.created" in addresses.stdout, addresses.stdout
    finally:
        _stop(name)


def test_qpid_proton_builds_from_source_on_slim_python() -> None:
    """``fastapi-orders`` consumes AMQP 1.0 with proton; no manylinux wheel exists for it, so
    Task 5's fixture image must install build tools and compile the C core from source."""
    install = (
        f"apt-get update && apt-get install -y --no-install-recommends {PROTON_BUILD_DEPS} "
        "&& rm -rf /var/lib/apt/lists/* "
        f"&& pip install --no-cache-dir {QPID_PROTON} "
        "&& python -c 'import proton; print(proton.VERSION)'"
    )
    started = time.monotonic()
    proc = docker("run", "--rm", PYTHON_IMAGE, "sh", "-c", install,
                  check=False, timeout=1200)
    elapsed = time.monotonic() - started
    assert proc.returncode == 0, (
        f"building {QPID_PROTON} from source on {PYTHON_IMAGE} failed after {elapsed:.0f}s\n"
        f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}"
    )
    assert re.search(r"\(\d+,\s*\d+,\s*\d+\)", proc.stdout), (
        f"import line did not print a version tuple after {elapsed:.0f}s\n{proc.stdout[-2000:]}"
    )
