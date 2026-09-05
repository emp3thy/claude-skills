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

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kb_common import (
    EXIT_OK,
    LEDGER_VERSION,
    KbError,
    iter_files,
    read_json,
    read_text,
    read_yaml_docs,
    rel,
    require_file,
    run_cli,
    write_json,
    write_yaml,
)
from markers import CHEAT_SHEET, SOURCE_SUFFIXES, markers_of_kind

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


_BASE_CONFIG_NAMES = ("application.yml", "application.yaml", "application.properties",
                      "appsettings.json")


def _config_rank(path: Path) -> int:
    """0 for a base config file, 1 for a profile variant, 2 for everything else.

    ``_record`` keeps the first value seen, so the base file has to be read
    before ``application-prod.yml`` or ``appsettings.Development.json``.
    """
    name = path.name
    if name in _BASE_CONFIG_NAMES:
        return 0
    if name.startswith("application-") and path.suffix in (".yml", ".yaml", ".properties"):
        return 1
    if name.startswith("appsettings.") and path.suffix == ".json":
        return 1
    return 2


def parse_app_config(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    candidates = sorted(
        iter_files(root, (".yml", ".yaml", ".properties", ".json", ".py", ".xml", ".example"),
                   skip_test_trees=True),
        key=lambda p: (_config_rank(p), rel(p, root)),
    )
    for path in candidates:
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
    jwks_keys = sorted(
        str(info.get("env_var") or key)
        for key, info in keys.items()
        if info.get("role") == "auth"
        and re.search(r"jwks|issuer|authority|auth-server-url|oidc.*url", key.lower())
    )
    if jwks_keys:
        return {"mode": "jwks", "keys": jwks_keys}
    if stack_auth is None:
        return {"mode": "none"}
    return {"mode": "blocked"}


# --- entry points -----------------------------------------------------------------

_SPRING_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?"([^"]*)"'
)
_JAXRS_PATH_RE = re.compile(r'@Path\s*\(\s*"([^"]*)"\s*\)')
_CLASS_DECL_RE = re.compile(r"\b(?:class|interface|record)\s+(\w+)")
_ASPNET_ROUTE_RE = re.compile(r'\[Route\s*\(\s*"([^"]*)"\s*\)\]')
_ASPNET_CLASS_RE = re.compile(r"\bclass\s+(\w+?)(Controller)?\b")
_FASTAPI_PREFIX_RE = re.compile(r"APIRouter\s*\([^)]*prefix\s*=\s*[\"']([^\"']+)[\"']")
_FLASK_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]+)\]")
_ROUTE_CONSTRAINT_RE = re.compile(r"\{(\w+):[^}]+\}")


def join_path(prefix: str, path: str) -> str:
    combined = "/".join(part for part in (prefix, path) if part)
    combined = _ROUTE_CONSTRAINT_RE.sub(r"{\1}", combined)
    segments = [s for s in combined.split("/") if s]
    return "/" + "/".join(segments)


def _class_prefix(stack: str, lines: list[str]) -> tuple[str, int]:
    """Return (route prefix, index of the class declaration line) for one source file."""
    class_index = next((i for i, ln in enumerate(lines) if _CLASS_DECL_RE.search(ln)), -1)
    head = "\n".join(lines[: class_index + 1] if class_index >= 0 else lines)
    if stack == "spring":
        match = _SPRING_CLASS_MAPPING_RE.search(head)
        return (match.group(1) if match else ""), class_index
    if stack == "quarkus":
        match = _JAXRS_PATH_RE.search(head)
        return (match.group(1) if match else ""), class_index
    if stack == "aspnetcore":
        route = _ASPNET_ROUTE_RE.search(head)
        if not route:
            return "", class_index
        prefix = route.group(1)
        if "[controller]" in prefix:
            klass = _ASPNET_CLASS_RE.search(head)
            name = klass.group(1).lower() if klass else "controller"
            prefix = prefix.replace("[controller]", name)
        return prefix, class_index
    match = _FASTAPI_PREFIX_RE.search("\n".join(lines))
    return (match.group(1) if match else ""), class_index


def _quarkus_method_path(lines: list[str], index: int, class_index: int) -> str:
    for offset in (1, 2, -1, -2):
        j = index + offset
        if 0 <= j < len(lines) and j > class_index:
            match = _JAXRS_PATH_RE.search(lines[j])
            if match:
                return match.group(1)
    return ""


def _resolve_channel(config: dict[str, dict[str, Any]], channel: str) -> str:
    info = config.get(f"mp.messaging.incoming.{channel}.address")
    return str(info["placeholder"]) if info and info.get("placeholder") else channel


def find_entry_points(root: Path, stack: str,
                      config: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    http_markers = markers_of_kind(stack, "entry-http")
    amq_markers = markers_of_kind(stack, "entry-amq")
    entries: dict[str, dict[str, Any]] = {}
    for path in iter_files(root, SOURCE_SUFFIXES[stack], skip_test_trees=True):
        lines = read_text(path).splitlines()
        prefix, class_index = _class_prefix(stack, lines)
        source = rel(path, root)
        for index, line in enumerate(lines):
            handler = f"{source}:{index + 1}"
            for marker in http_markers:
                match = marker.pattern.search(line)
                if not match:
                    continue
                # ASP.NET minimal-API routes (app.MapGet("/x")) are absolute; attribute
                # routes and every other stack are relative to the class prefix.
                absolute_minimal_api = stack == "aspnetcore" and match.group(3) is not None
                for method, route in _http_routes(stack, match, line, lines, index, class_index):
                    full = join_path("" if absolute_minimal_api else prefix, route)
                    entry_id = f"{method} {full}"
                    entries.setdefault(entry_id, {
                        "id": entry_id, "kind": "http", "method": method, "path": full,
                        "handler": handler,
                    })
            for marker in amq_markers:
                match = marker.pattern.search(line)
                if not match:
                    continue
                destination = next((g for g in match.groups() if g), None)
                if destination is None:
                    continue
                entry: dict[str, Any] = {"kind": "amq-subscribe", "handler": handler}
                if stack == "quarkus":
                    entry["channel"] = destination
                    destination = _resolve_channel(config, destination)
                entry["destination"] = destination
                entry["id"] = f"amq {destination}"
                entries.setdefault(entry["id"], entry)
    return sorted(entries.values(), key=lambda e: (e["handler"].rsplit(":", 1)[0],
                                                   int(e["handler"].rsplit(":", 1)[1])))


def _http_routes(stack: str, match: re.Match[str], line: str, lines: list[str], index: int,
                 class_index: int) -> list[tuple[str, str]]:
    if stack == "spring":
        return [(match.group(1).upper(), match.group(2) or "")]
    if stack == "quarkus":
        return [(match.group(1).upper(), _quarkus_method_path(lines, index, class_index))]
    if stack == "aspnetcore":
        if match.group(1):
            return [(match.group(1).upper(), match.group(2) or "")]
        return [(match.group(3).upper(), "/" + (match.group(4) or "").lstrip("/"))]
    if match.group(1):
        return [(match.group(1).upper(), match.group(2))]
    methods_match = _FLASK_METHODS_RE.search(line)
    methods = (
        [m.strip().strip("\"'").upper() for m in methods_match.group(1).split(",")]
        if methods_match else ["GET"]
    )
    return [(method, match.group(3)) for method in methods]


# --- migrations -------------------------------------------------------------------

_MIGRATION_DIRS = (
    "src/main/resources/db/migration",
    "src/main/resources/db/changelog",
    "alembic/versions",
    "migrations",
)
_ON_BOOT_KEYS = (
    "spring.jpa.hibernate.ddl-auto",
    "quarkus.hibernate-orm.database.generation",
    "hibernate.hbm2ddl.auto",
)
_ON_BOOT_VALUES = {"create", "create-drop", "update", "drop-and-create"}


def detect_migrations(root: Path, stack: str, config: dict[str, dict[str, Any]]) -> dict[str, Any]:
    found: list[str] = [d for d in _MIGRATION_DIRS if (root / d).is_dir()]
    if stack == "aspnetcore":
        found.extend(
            sorted({rel(p.parent, root)
                    for p in iter_files(root, (".cs",), skip_test_trees=True)
                    if p.parent.name == "Migrations"})
        )
    also_on_boot = any(
        str(config.get(k, {}).get("placeholder", "")).lower() in _ON_BOOT_VALUES
        for k in _ON_BOOT_KEYS
    )
    if not also_on_boot and stack == "aspnetcore":
        also_on_boot = any(".Migrate()" in read_text(p)
                           for p in iter_files(root, (".cs",), skip_test_trees=True))
    if not also_on_boot and stack == "python":
        also_on_boot = any("create_all(" in read_text(p)
                           for p in iter_files(root, (".py",), skip_test_trees=True))
    return {
        "strategy": "migration-container",
        "image": None,
        "source": None,
        "repo_migrations": found,
        "also_on_boot": also_on_boot,
    }


# --- env-map and ledger -------------------------------------------------------------


def build_env_map(stack_info: dict[str, Any], manifest: dict[str, Any] | None,
                  dockerfile: dict[str, Any] | None,
                  config: dict[str, dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    if manifest is not None:
        for key, value in manifest["env"].items():
            merged[key] = {"placeholder": value or "", "source": manifest["source"],
                           "env_var": key}
    if dockerfile is not None:
        for key, value in dockerfile["env"].items():
            merged.setdefault(key, {"placeholder": value, "source": "Dockerfile",
                                    "env_var": key})
    for key, info in config.items():
        merged.setdefault(key, dict(info))
    for key, info in merged.items():
        info["role"] = assign_role(key, str(info.get("placeholder") or ""))

    port = (manifest or {}).get("port") or (dockerfile or {}).get("expose") \
        or DEFAULT_PORT.get(str(stack_info.get("framework")), 8080)
    readiness = (manifest or {}).get("readiness") or {
        "path": None, "port": port, "source": "fallback"
    }
    return {
        "manifest": None if manifest is None else {
            "source": manifest["source"], "serverless": manifest["serverless"],
            "env_from": manifest["env_from"],
        },
        "port": port,
        "readiness": readiness,
        "auth": detect_auth(merged, stack_info.get("auth")),
        "keys": [
            {"key": key, "role": info["role"], "placeholder": info.get("placeholder", ""),
             "source": info.get("source", ""), "env_var": info.get("env_var")}
            for key, info in sorted(merged.items())
        ],
    }


def _blank_status() -> dict[str, bool]:
    return {"traced": False, "stubbed": False, "tested": False, "passing": False}


def seed_ledger(stack_info: dict[str, Any], env_map: dict[str, Any],
                entries: list[dict[str, Any]], migrations: dict[str, Any],
                repo_name: str, dockerfile_rel: str | None) -> dict[str, Any]:
    entry_points: list[dict[str, Any]] = []
    for entry in entries:
        item: dict[str, Any] = dict(entry)
        item.update({
            "auth": "unknown",
            "request": None,
            "responses": [],
            "reads": [],
            "exits": [],
            "rules": {"file": None, "count": 0, "sources": []},
            "features": [],
            "stubs": [],
            "seeds": [],
            "observed_overrides": [],
            "status": _blank_status(),
        })
        entry_points.append(item)
    manifest = env_map.get("manifest") or {}
    return {
        "version": LEDGER_VERSION,
        "repo": repo_name,
        "stack": {
            "language": stack_info.get("language"),
            "framework": stack_info.get("framework"),
            "db": stack_info.get("db"),
            "messaging": stack_info.get("messaging"),
            "validation": stack_info.get("validation"),
            "auth": stack_info.get("auth"),
            "cheat_sheet": CHEAT_SHEET[str(stack_info.get("framework"))],
        },
        "app": {
            "dockerfile": dockerfile_rel,
            "port": env_map["port"],
            "serverless": bool(manifest.get("serverless", False)),
            "readiness": env_map["readiness"],
            "migrations": migrations,
            "auth": env_map["auth"],
        },
        "entry_points": entry_points,
        "unresolved": [],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover manifests, config and entry points")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--service-dir", default=None)
    parser.add_argument("--stack", type=Path, required=True, help="stack.json from detect.py")
    parser.add_argument("--out-env", type=Path, required=True)
    parser.add_argument("--out-ledger", type=Path, required=True)
    args = parser.parse_args(argv)

    root = args.repo / args.service_dir if args.service_dir else args.repo
    stack_info = read_json(require_file(args.stack, "stack.json"))
    stack = str(stack_info["framework"])

    manifests = find_manifests(root)
    manifest = parse_manifest(manifests[0][0], root, manifests[0][1]) if manifests else None
    dockerfile_path = find_dockerfile(root)
    if dockerfile_path is None:
        raise KbError(f"no Dockerfile found under {root}; the app image cannot be built")
    dockerfile = parse_dockerfile(dockerfile_path)
    config = parse_app_config(root)
    entries = find_entry_points(root, stack, config)
    if not entries:
        raise KbError(f"no entry points found under {root} for stack {stack}")
    migrations = detect_migrations(root, stack, config)
    env_map = build_env_map(stack_info, manifest, dockerfile, config)
    ledger = seed_ledger(stack_info, env_map, entries, migrations, root.resolve().name,
                         rel(dockerfile_path, root))
    write_json(args.out_env, env_map)
    write_yaml(args.out_ledger, ledger)
    print(f"entry points: {len(entries)}, config keys: {len(env_map['keys'])}, "
          f"auth: {env_map['auth']['mode']} -> {args.out_ledger}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
