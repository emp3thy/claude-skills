# Podman with Testcontainers

Dev laptops use podman or the docker CLI, not Docker Desktop. Testcontainers talks to whatever
socket `DOCKER_HOST` names.

## Linux

Rootless podman:

```bash
systemctl --user enable --now podman.socket
export DOCKER_HOST=unix://${XDG_RUNTIME_DIR}/podman/podman.sock
```

## Windows and macOS

Podman runs in a machine (WSL2 on Windows). After `podman machine start`, read the socket
from `podman machine inspect --format '{{.ConnectionInfo.PodmanSocket.Path}}'` and export it
as `DOCKER_HOST` (on Windows, a named pipe such as `npipe:////./pipe/podman-machine-default`).
Setting it once in the user environment avoids repeating it per shell.

## Ryuk

Testcontainers starts Ryuk to reap containers. Podman needs it privileged, which the module's
`src/test/resources/testcontainers.properties` sets (`ryuk.container.privileged=true`). If the
engine still refuses, set `TESTCONTAINERS_RYUK_DISABLED=true`; the harness's shutdown hook then
stops the containers itself when the JVM exits normally.

## Verify

```bash
cd karate-tests
mvn -B test -Dkb.skipContainers=true   # no engine needed: the harness self-test
mvn -B test -Dkarate.options="--tags @smoke"   # first live run, happy paths only
```

`target/app.log` and `target/db-manager.log` show where a first run stops.
