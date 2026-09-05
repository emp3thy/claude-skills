"""Phase 0 of karate-bootstrap: preflight and stack detection.

Reads build files (pom.xml, build.gradle(.kts), *.csproj, pyproject.toml,
requirements*.txt) no deeper than three directories below the service root
and classifies the service by keyword. Writes ``stack.json``.

Usage:
    python scripts/detect.py <repo> [--service-dir SUB] --out karate-tests/stack.json
                             [--skip-toolchain]

Exit codes: 0 ok, 3 unsupported stack, 7 container runtime or mvn missing, or
java missing or older than 17.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from kb_common import (
    DEFAULT_IGNORE,
    EXIT_OK,
    EXIT_TOOLCHAIN,
    EXIT_UNSUPPORTED_STACK,
    KbError,
    read_text,
    rel,
    run_cli,
    write_json,
)

BUILD_FILE_NAMES = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.in",
)
MAX_DEPTH = 3
MIN_JAVA_MAJOR = 17

# (needle, label, framework the row applies to or None for every framework).
# Gating matters because build files carry prose: a Spring pom whose description
# mentions "requests" must not report the Python ``requests`` client.
Row = tuple[str, str, str | None]


def find_build_files(root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        for child in sorted(directory.iterdir()):
            if child.is_dir():
                if child.name not in DEFAULT_IGNORE and depth < MAX_DEPTH:
                    walk(child, depth + 1)
            elif child.name in BUILD_FILE_NAMES or child.suffix == ".csproj":
                found.append(child)

    walk(root, 0)
    return found


def _first(text: str, table: tuple[Row, ...], default: str | None, framework: str) -> str | None:
    for needle, label, only_for in table:
        if only_for is not None and only_for != framework:
            continue
        if needle in text:
            return label
    return default


def detect(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise KbError(f"service root not found: {root}")
    files = find_build_files(root)
    if not files:
        raise KbError(f"no supported build file under {root}", EXIT_UNSUPPORTED_STACK)
    text = "\n".join(read_text(f) for f in files).lower()
    names = {f.name for f in files}
    has_java = bool(names & {"pom.xml", "build.gradle", "build.gradle.kts"})
    has_csproj = any(f.suffix == ".csproj" for f in files)
    has_python = bool(names & {"pyproject.toml", "requirements.txt", "requirements-dev.txt",
                               "requirements.in"})

    if has_java and "quarkus" in text:
        framework, language = "quarkus", "java"
        build = "gradle" if "build.gradle" in " ".join(names) else "maven"
    elif has_java and "spring-boot" in text:
        framework, language = "spring", "java"
        build = "gradle" if "build.gradle" in " ".join(names) else "maven"
    elif has_csproj and ("microsoft.net.sdk.web" in text or "aspnetcore" in text):
        framework, language, build = "aspnetcore", "csharp", "dotnet"
    elif has_python and any(k in text for k in ("fastapi", "flask", "django")):
        framework, language, build = "python", "python", "pip"
    else:
        raise KbError(
            "no supported framework found (spring, quarkus, aspnetcore, python web)",
            EXIT_UNSUPPORTED_STACK,
        )

    orm = _first(text, (
        ("quarkus-hibernate-orm-panache", "panache", None),
        ("quarkus-hibernate-orm", "hibernate-jpa", None),
        ("spring-boot-starter-data-jpa", "hibernate-jpa", None),
        ("hibernate-core", "hibernate-jpa", None),
        ("hibernate-orm", "hibernate-jpa", None),
        ("entityframeworkcore", "efcore", None),
        ("sqlalchemy", "sqlalchemy", None),
        ("django", "django-orm", "python"),
    ), None, framework)
    db = _first(text, (
        ("postgresql", "postgres", None),
        ("npgsql", "postgres", None),
        ("psycopg", "postgres", None),
        ("asyncpg", "postgres", None),
    ), None, framework)
    messaging = _first(text, (
        ("smallrye-reactive-messaging-amqp", "smallrye-amqp", None),
        ("quarkus-artemis", "artemis-jms", None),
        ("spring-boot-starter-artemis", "artemis-jms", None),
        ("artemis-jms-client", "artemis-jms", None),
        ("spring-jms", "artemis-jms", None),
        ("apache.nms.amqp", "nms-amqp", None),
        ("apache.nms.activemq", "nms-openwire", None),
        ("amqpnetlite", "amqpnetlite", None),
        ("masstransit", "masstransit", None),
        ("python-qpid-proton", "qpid-proton", None),
        ("stomp.py", "stomp", None),
        ("stomp-py", "stomp", None),
    ), None, framework)
    http_default = {"spring": "resttemplate", "aspnetcore": "httpclient"}.get(framework)
    http_client = _first(text, (
        ("quarkus-rest-client", "quarkus-rest-client", None),
        ("openfeign", "feign", None),
        ("spring-boot-starter-webflux", "webclient", None),
        ("httpx", "httpx", "python"),
        ("requests", "requests", "python"),
        ("aiohttp", "aiohttp", "python"),
    ), http_default, framework)
    validation_default = {"aspnetcore": "data-annotations"}.get(framework)
    validation = _first(text, (
        ("quarkus-hibernate-validator", "bean-validation", None),
        ("spring-boot-starter-validation", "bean-validation", None),
        ("fluentvalidation", "fluentvalidation", None),
        ("pydantic", "pydantic", "python"),
    ), validation_default, framework)
    auth = _first(text, (
        ("quarkus-oidc", "quarkus-oidc", None),
        ("spring-boot-starter-oauth2-resource-server", "spring-security", None),
        ("spring-boot-starter-security", "spring-security", None),
        ("authentication.jwtbearer", "jwt-bearer", None),
        ("pyjwt", "pyjwt", "python"),
        ("python-jose", "python-jose", "python"),
        ("authlib", "authlib", "python"),
    ), None, framework)

    return {
        "language": language,
        "framework": framework,
        "build": build,
        "orm": orm,
        "db": db,
        "messaging": messaging,
        "http_client": http_client,
        "validation": validation,
        "auth": auth,
        "build_files": [rel(f, root) for f in files],
    }


_JAVA_VERSION_RE = re.compile(r'"(\d+)(?:\.(\d+))?')


def _java_major() -> int | None:
    """Major version reported by ``java -version`` (on stderr), or None if unreadable."""
    try:
        result = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    match = _JAVA_VERSION_RE.search((result.stderr or "") + (result.stdout or ""))
    if match is None:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2) is not None:
        return int(match.group(2))  # legacy 1.8-style version strings
    return major


def check_toolchain() -> dict[str, Any]:
    container_cli = next((c for c in ("docker", "podman") if shutil.which(c)), None)
    missing: list[str] = []
    if container_cli is None:
        missing.append("docker or podman")
    if not shutil.which("java"):
        missing.append("java")
    if not shutil.which("mvn"):
        missing.append("mvn")
    if missing:
        raise KbError("toolchain missing: " + ", ".join(missing), EXIT_TOOLCHAIN)
    major = _java_major()
    if major is None:
        raise KbError(
            f"toolchain: java {MIN_JAVA_MAJOR} or newer required, found unknown", EXIT_TOOLCHAIN
        )
    if major < MIN_JAVA_MAJOR:
        raise KbError(
            f"toolchain: java {MIN_JAVA_MAJOR} or newer required, found {major}", EXIT_TOOLCHAIN
        )
    return {"container_cli": container_cli, "java": major, "maven": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect the service stack and write stack.json")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-toolchain", action="store_true",
                        help="Do not check for docker/podman, java and mvn")
    args = parser.parse_args(argv)

    root = args.repo / args.service_dir if args.service_dir else args.repo
    toolchain = {"skipped": True} if args.skip_toolchain else check_toolchain()
    result = detect(root)
    result["service_dir"] = args.service_dir
    result["toolchain"] = toolchain
    write_json(args.out, result)
    print(f"stack: {result['framework']} ({result['language']}) -> {args.out}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
