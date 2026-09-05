"""Phase 0 of karate-bootstrap: preflight and stack detection.

Reads build files (pom.xml, build.gradle(.kts), *.csproj, pyproject.toml,
requirements*.txt) no deeper than three directories below the service root
and classifies the service by keyword. Writes ``stack.json``.

Usage:
    python scripts/detect.py <repo> [--service-dir SUB] --out karate-tests/stack.json
                             [--skip-toolchain]

Exit codes: 0 ok, 3 unsupported stack, 7 container runtime, java or mvn missing.
"""
from __future__ import annotations

import argparse
import shutil
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


def _first(text: str, table: tuple[tuple[str, str], ...], default: str | None) -> str | None:
    for needle, label in table:
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
        ("quarkus-hibernate-orm-panache", "panache"),
        ("quarkus-hibernate-orm", "hibernate-jpa"),
        ("spring-boot-starter-data-jpa", "hibernate-jpa"),
        ("hibernate-core", "hibernate-jpa"),
        ("hibernate-orm", "hibernate-jpa"),
        ("entityframeworkcore", "efcore"),
        ("sqlalchemy", "sqlalchemy"),
        ("django", "django-orm"),
    ), None)
    db = _first(text, (
        ("postgresql", "postgres"),
        ("npgsql", "postgres"),
        ("psycopg", "postgres"),
        ("asyncpg", "postgres"),
    ), None)
    messaging = _first(text, (
        ("smallrye-reactive-messaging-amqp", "smallrye-amqp"),
        ("quarkus-artemis", "artemis-jms"),
        ("spring-boot-starter-artemis", "artemis-jms"),
        ("artemis-jms-client", "artemis-jms"),
        ("spring-jms", "artemis-jms"),
        ("apache.nms.amqp", "nms-amqp"),
        ("apache.nms.activemq", "nms-openwire"),
        ("amqpnetlite", "amqpnetlite"),
        ("masstransit", "masstransit"),
        ("python-qpid-proton", "qpid-proton"),
        ("stomp.py", "stomp"),
        ("stomp-py", "stomp"),
    ), None)
    http_default = {"spring": "resttemplate", "aspnetcore": "httpclient"}.get(framework)
    http_client = _first(text, (
        ("quarkus-rest-client", "quarkus-rest-client"),
        ("openfeign", "feign"),
        ("spring-boot-starter-webflux", "webclient"),
        ("httpx", "httpx"),
        ("requests", "requests"),
        ("aiohttp", "aiohttp"),
    ), http_default)
    validation_default = {"aspnetcore": "data-annotations"}.get(framework)
    validation = _first(text, (
        ("quarkus-hibernate-validator", "bean-validation"),
        ("spring-boot-starter-validation", "bean-validation"),
        ("fluentvalidation", "fluentvalidation"),
        ("pydantic", "pydantic"),
    ), validation_default)
    auth = _first(text, (
        ("quarkus-oidc", "quarkus-oidc"),
        ("spring-boot-starter-oauth2-resource-server", "spring-security"),
        ("spring-boot-starter-security", "spring-security"),
        ("authentication.jwtbearer", "jwt-bearer"),
        ("pyjwt", "pyjwt"),
        ("python-jose", "python-jose"),
        ("authlib", "authlib"),
    ), None)

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
    return {"container_cli": container_cli, "java": True, "maven": True}


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
