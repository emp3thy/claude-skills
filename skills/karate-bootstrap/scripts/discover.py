"""Phase 1 of karate-bootstrap: discover what the harness must know before tracing.

Deterministic reads, in order: the OpenShift manifest (``deployment.yml`` then
``deploymentserverless.yml``, generic Deployment as fallback), the Dockerfile,
application config files, and route declarations from ``markers.py``. Writes
``env-map.json`` (config keys with roles, port, readiness, auth mode) and a
seeded ``flow-map.yaml`` with one untraced entry per entry point.

Usage:
    python scripts/discover.py <repo> --stack karate-tests/stack.json \
        --out-env karate-tests/env-map.json --out-ledger karate-tests/flow-map.yaml \
        [--service-dir SUB]

Exit codes: 0 ok, 2 when no manifest, Dockerfile or entry point can be found,
5 when stack.json is missing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kb_common import KbError, iter_files, read_text, read_yaml_docs, rel

# Task 6 extends this import block with: argparse, sys, EXIT_OK, LEDGER_VERSION,
# read_json, require_file, run_cli, write_json, write_yaml from kb_common and
# CHEAT_SHEET, SOURCE_SUFFIXES, markers_of_kind from markers.

MANIFEST_NAMES: tuple[tuple[str, bool], ...] = (
    ("deployment.yml", False),
    ("deploymentserverless.yml", True),
)
DOCKERFILE_CANDIDATES = (
    "Dockerfile",
    "Containerfile",
    "docker/Dockerfile",
    "src/main/docker/Dockerfile.jvm",
    "src/main/docker/Dockerfile.native",
)
DEFAULT_PORT = {"python": 8000}

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.\-]*)(?::([^}]*))?\}")
_ENV_READ_RE = re.compile(
    r"^(\w+)\s*=\s*os\.(?:environ\[|environ\.get\(|getenv\()\s*[\"'](\w+)[\"']"
    r"(?:\s*,\s*[\"']([^\"']*)[\"'])?"
)
_XML_PROP_RE = re.compile(r'<property\s+name="([^"]+)"(?:\s+value="([^"]*)")?\s*/?>([^<]*)')
_DOCKER_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(\d+)", re.IGNORECASE)
_DOCKER_ENV_RE = re.compile(r"^\s*ENV\s+([A-Za-z_][A-Za-z0-9_]*)(?:=|\s+)(.*)$", re.IGNORECASE)


# --- manifests -----------------------------------------------------------------


def _find_containers(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        containers = node.get("containers")
        if isinstance(containers, list) and containers and isinstance(containers[0], dict):
            return [c for c in containers if isinstance(c, dict)]
        for value in node.values():
            found = _find_containers(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_containers(item)
            if found:
                return found
    return []


def _is_workload(doc: dict[str, Any]) -> bool:
    kind = str(doc.get("kind", ""))
    api = str(doc.get("apiVersion", ""))
    return kind in {"Deployment", "DeploymentConfig", "StatefulSet"} or (
        kind == "Service" and api.startswith("serving.knative.dev")
    )


def find_manifests(root: Path) -> list[tuple[Path, bool]]:
    found: list[tuple[Path, bool]] = []
    for name, serverless in MANIFEST_NAMES:
        direct = root / name
        if direct.is_file():
            found.append((direct, serverless))
            continue
        for candidate in iter_files(root, (".yml", ".yaml")):
            if candidate.name == name:
                found.append((candidate, serverless))
                break
    if found:
        return found
    for candidate in iter_files(root, (".yml", ".yaml")):
        try:
            docs = read_yaml_docs(candidate)
        except Exception:  # any unparsable YAML is simply not a manifest
            continue
        for doc in docs:
            if _is_workload(doc):
                knative = str(doc.get("apiVersion", "")).startswith("serving.knative.dev")
                return [(candidate, knative)]
    return []


def parse_manifest(path: Path, root: Path, serverless: bool) -> dict[str, Any]:
    containers: list[dict[str, Any]] = []
    for doc in read_yaml_docs(path):
        containers = _find_containers(doc)
        if containers:
            break
    if not containers:
        raise KbError(f"{rel(path, root)}: no containers found")
    container = containers[0]
    ports = [p for p in container.get("ports", []) if isinstance(p, dict)]
    port_by_name = {p.get("name"): p.get("containerPort") for p in ports if p.get("name")}
    port = next((int(p["containerPort"]) for p in ports if "containerPort" in p), None)

    readiness: dict[str, Any] | None = None
    probe = container.get("readinessProbe") or {}
    http_get = probe.get("httpGet") if isinstance(probe, dict) else None
    if isinstance(http_get, dict) and "path" in http_get:
        raw_port = http_get.get("port", port)
        resolved = port_by_name.get(raw_port, raw_port) if isinstance(raw_port, str) else raw_port
        readiness = {
            "path": str(http_get["path"]),
            "port": int(resolved) if resolved is not None else port,
            "source": rel(path, root),
        }

    env: dict[str, str | None] = {}
    for item in container.get("env", []) or []:
        if isinstance(item, dict) and "name" in item:
            value = item.get("value")
            env[str(item["name"])] = None if value is None else str(value)
    env_from: list[str] = []
    for item in container.get("envFrom", []) or []:
        if not isinstance(item, dict):
            continue
        for ref_key in ("configMapRef", "secretRef"):
            ref = item.get(ref_key)
            if isinstance(ref, dict) and "name" in ref:
                env_from.append(str(ref["name"]))
    return {
        "source": rel(path, root),
        "serverless": serverless,
        "port": port,
        "readiness": readiness,
        "env": env,
        "env_from": env_from,
    }


# --- Dockerfile ------------------------------------------------------------------


def find_dockerfile(root: Path) -> Path | None:
    for candidate in DOCKERFILE_CANDIDATES:
        path = root / candidate
        if path.is_file():
            return path
    return None


def parse_dockerfile(path: Path) -> dict[str, Any]:
    expose: int | None = None
    env: dict[str, str] = {}
    for line in read_text(path).splitlines():
        exposed = _DOCKER_EXPOSE_RE.match(line)
        if exposed and expose is None:
            expose = int(exposed.group(1))
            continue
        env_match = _DOCKER_ENV_RE.match(line)
        if env_match:
            env[env_match.group(1)] = env_match.group(2).strip().strip('"').strip("'")
    return {"expose": expose, "env": env}


# --- application config ----------------------------------------------------------


def _flatten(prefix: str, node: Any, sep: str, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten(f"{prefix}{sep}{key}" if prefix else str(key), value, sep, out)
    elif isinstance(node, list):
        out[prefix] = json.dumps(node)
    elif isinstance(node, bool):
        out[prefix] = "true" if node else "false"
    elif node is None:
        out[prefix] = ""
    else:
        out[prefix] = str(node)


def _env_var_of(placeholder: str) -> str | None:
    match = _PLACEHOLDER_RE.search(placeholder)
    return match.group(1) if match else None


def _record(out: dict[str, dict[str, Any]], key: str, placeholder: str, source: str,
            env_var: str | None = None) -> None:
    if key in out:
        return
    out[key] = {
        "placeholder": placeholder,
        "source": source,
        "env_var": env_var if env_var is not None else _env_var_of(placeholder),
    }


def parse_app_config(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in iter_files(root, (".yml", ".yaml", ".properties", ".json", ".py", ".xml",
                                  ".example")):
        name = path.name
        source = rel(path, root)
        if name.startswith("application") and path.suffix in (".yml", ".yaml"):
            flat: dict[str, str] = {}
            for doc in read_yaml_docs(path):
                _flatten("", doc, ".", flat)
            for key, value in flat.items():
                _record(out, key, value, source)
        elif name.startswith("application") and path.suffix == ".properties":
            for line in read_text(path).splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                _record(out, key.strip(), value.strip(), source)
        elif name.startswith("appsettings") and path.suffix == ".json":
            flat = {}
            _flatten("", json.loads(read_text(path)), "__", flat)
            for key, value in flat.items():
                _record(out, key, value, source)
        elif name == "settings.py" or name == "config.py":
            for line in read_text(path).splitlines():
                match = _ENV_READ_RE.match(line.strip())
                if match:
                    _record(out, match.group(2), match.group(3) or "", source, match.group(2))
        elif name == ".env.example":
            for line in read_text(path).splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    _record(out, key.strip(), value.strip(), source, key.strip())
        elif name in ("hibernate.cfg.xml", "persistence.xml"):
            for match in _XML_PROP_RE.finditer(read_text(path)):
                value = match.group(2) if match.group(2) is not None else match.group(3).strip()
                _record(out, match.group(1), value, source)
    return out


# --- roles and auth ---------------------------------------------------------------

_DB_KEY = ("datasource", "connectionstrings", "database_url", "jdbc", "db_url", "db-url",
           "hibernate.connection", "pghost", "pgdatabase")
_DB_VAL = ("jdbc:", "postgres", "host=")
_AMQ_KEY = ("artemis", "amqp", "activemq", "broker", "jms", "amq_", "amq__", "amq.",
            "mp.messaging", "stomp")
_AMQ_VAL = ("amqp://", "amqps://", "tcp://", "activemq:", "failover:", "stomp://")
_AUTH_KEY = ("oidc", "jwt", "jwks", "issuer", "authority", "auth", "security", "oauth")
_URL_SUFFIX = ("url", "uri", "baseurl", "base-url", "base_url", "endpoint", "host")
_NAME_NOISE = {"quarkus", "spring", "app", "rest", "client", "rest-client", "api", "base",
               "url", "uri", "baseurl", "endpoint", "host", "service", "svc", ""}
# Runtime knobs that look like URLs or hosts but only describe the app's own listener.
_PASSTHROUGH_KEYS = {"aspnetcore_urls", "aspnetcore_http_ports", "java_opts", "java_tool_options",
                     "port", "server_port", "server.port", "quarkus.http.port", "quarkus_http_port",
                     "uvicorn_port", "host", "server.address"}


def assign_role(key: str, placeholder: str) -> str:
    k = key.lower()
    v = placeholder.lower()
    if k in _PASSTHROUGH_KEYS:
        return "passthrough"
    if any(s in v for s in _DB_VAL) or any(s in k for s in _DB_KEY):
        return "db"
    if any(s in v for s in _AMQ_VAL) or any(s in k for s in _AMQ_KEY):
        return "amq"
    if any(s in k for s in _AUTH_KEY):
        return "auth"
    if v.startswith(("http://", "https://")) or any(k.endswith(s) for s in _URL_SUFFIX):
        return f"downstream:{downstream_name(key)}"
    return "passthrough"


def downstream_name(key: str) -> str:
    parts = re.split(r"__|[._:/]|(?<=[a-z])(?=[A-Z])", key)
    words: list[str] = []
    for part in parts:
        for word in part.split("_"):
            lowered = word.lower()
            if lowered not in _NAME_NOISE:
                words.append(lowered)
    return "-".join(words) if words else key.lower()


def detect_auth_switch(keys: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key, info in keys.items():
        k = re.sub(r"[-_.]", "", key.lower())
        if not re.search(r"auth|security|oidc|jwt", k):
            continue
        env_key = str(info.get("env_var") or key)
        if k.endswith("enabled"):
            return {"mode": "disabled", "key": env_key, "value": "false", "confirmed": True}
        if k.endswith("disabled"):
            return {"mode": "disabled", "key": env_key, "value": "true", "confirmed": True}
        if k.endswith("mode"):
            return {"mode": "disabled", "key": env_key, "value": "disabled", "confirmed": False}
    return None


def detect_auth(keys: dict[str, dict[str, Any]], stack_auth: str | None) -> dict[str, Any]:
    switch = detect_auth_switch(keys)
    if switch is not None:
        return switch
    if stack_auth is None:
        return {"mode": "none"}
    jwks_keys = sorted(
        str(info.get("env_var") or key)
        for key, info in keys.items()
        if info.get("role") == "auth"
        and re.search(r"jwks|issuer|authority|auth-server-url|oidc.*url", key.lower())
    )
    if jwks_keys:
        return {"mode": "jwks", "keys": jwks_keys}
    return {"mode": "blocked"}
