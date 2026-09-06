"""Phase 4 of karate-bootstrap: scaffold the Karate module into a repo.

Copies ``templates/karate-tests/`` (a real Maven project, compiled in this repo's CI)
into ``--out`` and writes ``src/test/resources/kb-runtime.json``, the only file that
carries repo-specific values (design spec 5.5). Java sources are copied verbatim.

Usage:
    python scripts/kb_scaffold.py <repo> --ledger karate-tests/flow-map.yaml \
        --env karate-tests/env-map.json --out karate-tests [--service-dir SUB] \
        [--migrations-image REF] [--config ~/.karate-bootstrap/config.yaml] [--force]

Copy rules: generated content (rules/, stubs/, seed/, src/test/resources/features/,
defects.md, README.md) is never overwritten, except the harness smoke feature, which is
harness content and lives under the features prefix only so the runner picks it up;
harness files are overwritten only with ``--force``; kb-runtime.json is always rewritten;
README.md.tmpl stays in the skill; nothing is deleted.

Exit codes: 0 ok, 4 when the strategy is migration-container and no db-manager image can
be resolved from ``--migrations-image`` or the central config, 5 when an input is missing.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from flow_map import load_ledger
from kb_common import (
    EXIT_MISSING_OUTPUT,
    EXIT_NO_SCHEMA,
    EXIT_OK,
    KbError,
    read_json,
    read_yaml,
    require_file,
    run_cli,
    write_json,
)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "karate-tests"
RUNTIME_REL = "src/test/resources/kb-runtime.json"
DEFAULT_CONFIG = Path.home() / ".karate-bootstrap" / "config.yaml"
RUNTIME_VERSION = 1
STARTUP_TIMEOUT_SECONDS = 120

# Never copied into the target repo: written from the ledger, or read from the skill instead.
SKIPPED_FILES = (RUNTIME_REL, "README.md.tmpl")

# Never overwritten once present: the generate phase and the developer own these.
GENERATED_PREFIXES = ("rules/", "stubs/", "seed/", "src/test/resources/features/")
GENERATED_FILES = ("defects.md", "README.md")

# Harness content despite sitting under a generated prefix, so ``--force`` can refresh it.
HARNESS_FILES = ("src/test/resources/features/harness-smoke.feature",)

# Central config ``env`` keys name the db-manager's own variables (spec 5.5).
MIGRATION_ENV_TOKENS = {
    "DB_HOST_KEY": "{{db.host}}",
    "DB_PORT_KEY": "{{db.port}}",
    "DB_NAME_KEY": "{{db.name}}",
    "DB_USER_KEY": "{{db.user}}",
    "DB_PASSWORD_KEY": "{{db.password}}",
}
DEFAULT_MIGRATION_ENV = {
    "PGHOST": "{{db.host}}",
    "PGPORT": "{{db.port}}",
    "PGDATABASE": "{{db.name}}",
    "PGUSER": "{{db.user}}",
    "PGPASSWORD": "{{db.password}}",
}

DB_URL_BY_STACK = {
    "spring": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}",
    "quarkus": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}",
    "aspnetcore": "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
                  "Username={{db.user}};Password={{db.password}}",
    "python": "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}",
}
_DB_URL_NEEDLES = ("url", "jdbc", "connectionstring", "conn", "dsn")
_DB_PART_TOKENS = (
    ("password", "{{db.password}}"),
    ("user", "{{db.user}}"),
    ("host", "{{db.host}}"),
    ("port", "{{db.port}}"),
    ("database", "{{db.name}}"),
    ("dbname", "{{db.name}}"),
    ("db_name", "{{db.name}}"),
)
_AMQ_PART_TOKENS = (
    ("password", "{{amq.password}}"),
    ("user", "{{amq.user}}"),
    ("host", "{{amq.host}}"),
    ("port", "{{amq.amqpPort}}"),
)
_CORE_SCHEMES = ("tcp://", "activemq:", "failover:")
_DB_NAME_RES = (
    re.compile(r"Database=(\w+)", re.IGNORECASE),
    re.compile(r"jdbc:postgresql://[^/\s]+/(\w+)"),
    re.compile(r"postgres(?:ql)?://[^/\s]+/(\w+)"),
)
_CONNECTION_STRING_KEY_RE = re.compile(r"^ConnectionStrings__(\w+)$")


# --- env entries ----------------------------------------------------------------------


def env_name(stack: str, key: str, env_var: str | None) -> str | None:
    """The environment variable the app reads for ``key``; None when the stack has no rule."""
    if env_var:
        return env_var
    if stack in ("spring", "quarkus"):
        return re.sub(r"[.\-]", "_", key).upper()
    if stack == "aspnetcore":
        return key
    return None


def env_value(stack: str, name: str, role: str, placeholder: str, source: str,
              manifest_source: str | None, auth: dict[str, Any]) -> str | None:
    """Template value for one env var, or None when the harness must not set it."""
    lowered = name.lower()
    if role == "db":
        if any(needle in lowered for needle in _DB_URL_NEEDLES):
            return DB_URL_BY_STACK.get(stack, DB_URL_BY_STACK["python"])
        for needle, token in _DB_PART_TOKENS:
            if needle in lowered:
                return token
        # discover.assign_role calls every ``datasource`` key db; a driver class name or a
        # pool size names no part of the connection, so the harness must leave it alone.
        return None
    if role == "amq":
        for needle, token in _AMQ_PART_TOKENS:
            if needle in lowered:
                return token
        scheme = placeholder.lower()
        if scheme.startswith(_CORE_SCHEMES):
            return "tcp://{{amq.host}}:{{amq.corePort}}"
        if scheme.startswith("stomp://"):
            return "stomp://{{amq.host}}:{{amq.stompPort}}"
        return "amqp://{{amq.host}}:{{amq.amqpPort}}"
    if role.startswith("downstream:"):
        return "{{stubs.url}}/" + role.split(":", 1)[1]
    if role == "auth":
        if auth.get("mode") == "disabled" and name == auth.get("key"):
            return str(auth.get("value"))
        if auth.get("mode") == "jwks" and name in auth.get("keys", []):
            return "{{auth.url}}/.well-known/jwks.json" if "jwks" in lowered else "{{auth.url}}"
        return placeholder if placeholder and "${" not in placeholder else None
    # passthrough: only literal runtime knobs from the manifest travel into the container
    if manifest_source and source == manifest_source and placeholder and "${" not in placeholder:
        return placeholder
    return None


def env_block(stack: str, env_map: dict[str, Any], auth: dict[str, Any]) -> list[dict[str, str]]:
    manifest_source = (env_map.get("manifest") or {}).get("source")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in env_map["keys"]:
        name = env_name(stack, str(key["key"]), key.get("env_var"))
        if name is None or name in seen:
            continue
        value = env_value(stack, name, str(key["role"]), str(key.get("placeholder") or ""),
                          str(key.get("source") or ""), manifest_source, auth)
        if value is None:
            continue
        seen.add(name)
        out.append({"name": name, "role": str(key["role"]), "value": value})
    return out


def downstreams_block(stack: str, env_map: dict[str, Any]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for key in env_map["keys"]:
        role = str(key["role"])
        if not role.startswith("downstream:"):
            continue
        name = role.split(":", 1)[1]
        env = env_name(stack, str(key["key"]), key.get("env_var"))
        if name in seen or env is None:
            continue
        seen.add(name)
        out.append({"name": name, "envVar": env})
    return out


# --- database and migrations -----------------------------------------------------------


def db_name_from_env(env_map: dict[str, Any]) -> str:
    """Database name from a db placeholder, else a ConnectionStrings__<Name> key, else ``app``."""
    for key in env_map["keys"]:
        if key.get("role") != "db":
            continue
        placeholder = str(key.get("placeholder") or "")
        for pattern in _DB_NAME_RES:
            match = pattern.search(placeholder)
            if match:
                return match.group(1)
    for key in env_map["keys"]:
        match = _CONNECTION_STRING_KEY_RE.match(str(key["key"]))
        if match:
            return match.group(1).lower()
    return "app"


def load_central_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"db_managers": {}}
    data = read_yaml(path)
    managers = data.get("db_managers") or {}
    return {"db_managers": managers if isinstance(managers, dict) else {}}


def select_db_manager(config: dict[str, Any], name: str) -> tuple[str, dict[str, Any]] | None:
    managers: dict[str, Any] = config.get("db_managers", {})
    if isinstance(managers.get(name), dict):
        return name, managers[name]
    for key, entry in managers.items():
        if isinstance(entry, dict) and str(entry.get("database", "")) == name:
            return str(key), entry
    return None


def migrations_block(ledger: dict[str, Any], image_flag: str | None,
                     entry: dict[str, Any] | None) -> dict[str, Any]:
    strategy = str((ledger["app"].get("migrations") or {}).get("strategy") or "migration-container")
    image = image_flag or ((entry or {}).get("image"))
    if strategy == "migration-container" and not image:
        raise KbError(
            "no db-manager image: pass --migrations-image or add a db_managers entry for this "
            "database to the central config (design spec 5.5)",
            EXIT_NO_SCHEMA,
        )
    env = dict(DEFAULT_MIGRATION_ENV)
    if entry:
        mapped: dict[str, str] = {}
        for role_key, token in MIGRATION_ENV_TOKENS.items():
            var = (entry.get("env") or {}).get(role_key)
            if var:
                mapped[str(var)] = token
        if mapped:
            env = mapped
        env.update({str(k): str(v) for k, v in (entry.get("extra_env") or {}).items()})
    return {"strategy": strategy, "image": image, "env": env}


# --- messaging, auth, app --------------------------------------------------------------


def amq_block(ledger: dict[str, Any]) -> dict[str, Any]:
    queues: set[str] = set()
    topics: set[str] = set()
    for entry in ledger["entry_points"]:
        if entry.get("kind") == "amq-subscribe" and entry.get("destination"):
            (topics if entry.get("type") == "topic" else queues).add(str(entry["destination"]))
        for item in entry.get("exits", []):
            if item.get("kind") == "amq-publish" and item.get("destination"):
                (topics if item.get("type") == "topic" else queues).add(str(item["destination"]))
    return {"user": "artemis", "password": "artemis", "queues": sorted(queues),
            "topics": sorted(topics)}


def auth_block(ledger: dict[str, Any]) -> dict[str, Any]:
    auth = ledger["app"].get("auth") or {"mode": "none"}
    mode = str(auth.get("mode", "none"))
    if mode == "disabled":
        return {"mode": "disabled", "key": auth.get("key"), "value": str(auth.get("value"))}
    if mode == "jwks":
        return {"mode": "jwks", "issuerKeys": list(auth.get("keys", []))}
    return {"mode": mode}


def app_block(ledger: dict[str, Any], service_root: Path, out_dir: Path) -> dict[str, Any]:
    app = ledger["app"]
    readiness = app.get("readiness") or {}
    try:
        repo_root_rel = Path(os.path.relpath(service_root.resolve(), out_dir.resolve())).as_posix()
    except ValueError:  # different drives on Windows
        repo_root_rel = service_root.resolve().as_posix()
    return {
        "repoRootRel": repo_root_rel,
        "dockerfileRel": app.get("dockerfile") or "Dockerfile",
        "port": int(app.get("port") or 8080),
        "readinessPath": readiness.get("path"),
        "serverless": bool(app.get("serverless", False)),
        "startupTimeoutSeconds": STARTUP_TIMEOUT_SECONDS,
    }


def build_runtime(ledger: dict[str, Any], env_map: dict[str, Any], service_root: Path,
                  out_dir: Path, config: dict[str, Any],
                  migrations_image: str | None) -> dict[str, Any]:
    stack = str(ledger["stack"]["framework"])
    derived = db_name_from_env(env_map)
    selected = select_db_manager(config, derived)
    entry = selected[1] if selected else None
    db_name = str(entry.get("database") or selected[0]) if selected and entry else derived
    return {
        "version": RUNTIME_VERSION,
        "repo": ledger["repo"],
        "stack": stack,
        "app": app_block(ledger, service_root, out_dir),
        "env": env_block(stack, env_map, ledger["app"].get("auth") or {}),
        "db": {"name": db_name, "user": "app", "password": "app"},
        "migrations": migrations_block(ledger, migrations_image, entry),
        "amq": amq_block(ledger),
        "downstreams": downstreams_block(stack, env_map),
        "auth": auth_block(ledger),
    }


# --- copy -----------------------------------------------------------------------------


def copy_template(template_dir: Path, out_dir: Path, force: bool) -> dict[str, list[str]]:
    """Copy the template; returns the relative paths written, overwritten and kept."""
    result: dict[str, list[str]] = {"written": [], "overwritten": [], "kept": []}
    for src in sorted(p for p in template_dir.rglob("*") if p.is_file()):
        rel = src.relative_to(template_dir).as_posix()
        if rel in SKIPPED_FILES:
            continue  # kb-runtime.json comes from the ledger; kb_report reads the template
        dest = out_dir / rel
        if dest.exists():
            generated = rel not in HARNESS_FILES and (
                rel.startswith(GENERATED_PREFIXES) or rel in GENERATED_FILES)
            if generated or not force:
                result["kept"].append(rel)
                continue
            result["overwritten"].append(rel)
        else:
            result["written"].append(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return result


# --- CLI ------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold the Karate module and kb-runtime.json")
    parser.add_argument("repo", type=Path, help="repository root")
    parser.add_argument("--ledger", type=Path, required=True, help="flow-map.yaml")
    parser.add_argument("--env", type=Path, required=True, help="env-map.json")
    parser.add_argument("--out", type=Path, required=True, help="karate-tests directory to create")
    parser.add_argument("--service-dir", default=None, help="Sub-directory holding the service")
    parser.add_argument("--migrations-image", default=None, help="db-manager image reference")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="db_managers config, default ~/.karate-bootstrap/config.yaml")
    parser.add_argument("--force", action="store_true",
                        help="overwrite harness files (never generated content)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service_root: Path = args.repo / args.service_dir if args.service_dir else args.repo
    ledger = load_ledger(args.ledger)
    env_map = read_json(require_file(args.env, "env-map.json"))
    if not TEMPLATE_DIR.is_dir():
        raise KbError(f"template missing at {TEMPLATE_DIR}", EXIT_MISSING_OUTPUT)
    config = load_central_config(args.config)
    runtime = build_runtime(ledger, env_map, service_root, args.out, config,
                            args.migrations_image)
    summary = copy_template(TEMPLATE_DIR, args.out, args.force)
    write_json(args.out / RUNTIME_REL, runtime)
    print(f"scaffolded {args.out}: {len(summary['written'])} written, "
          f"{len(summary['overwritten'])} overwritten, {len(summary['kept'])} kept; "
          f"runtime -> {args.out / RUNTIME_REL}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run_cli(main))
