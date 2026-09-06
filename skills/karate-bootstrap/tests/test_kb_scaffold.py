from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import load_ledger
from kb_common import EXIT_NO_SCHEMA, KbError, read_json, run_cli
from kb_scaffold import (
    RUNTIME_REL,
    TEMPLATE_DIR,
    build_runtime,
    copy_template,
    db_name_from_env,
    env_name,
    env_value,
    load_central_config,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures"
IMAGE = "registry.example/db-manager:1"
DISABLED = {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false", "confirmed": True}
JWKS = {"mode": "jwks", "keys": ["AUTH_ISSUER_URI", "AUTH_JWKS_URL"]}
DEFAULT_MIGRATION_ENV = {
    "PGHOST": "{{db.host}}", "PGPORT": "{{db.port}}", "PGDATABASE": "{{db.name}}",
    "PGUSER": "{{db.user}}", "PGPASSWORD": "{{db.password}}",
}

SPRING_ENV = [
    {"name": "AUTH_ISSUER_URI", "role": "auth", "value": "https://login.example/realms/acme"},
    {"name": "PRICING_BASE_URL", "role": "downstream:pricing", "value": "{{stubs.url}}/pricing"},
    {"name": "SPRING_ARTEMIS_BROKER_URL", "role": "amq",
     "value": "tcp://{{amq.host}}:{{amq.corePort}}"},
    {"name": "SPRING_DATASOURCE_URL", "role": "db",
     "value": "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"},
    {"name": "APP_SECURITY_ENABLED", "role": "auth", "value": "false"},
    {"name": "SPRING_DATASOURCE_PASSWORD", "role": "db", "value": "{{db.password}}"},
    {"name": "SPRING_DATASOURCE_USERNAME", "role": "db", "value": "{{db.user}}"},
]
DOTNET_ENV = [
    {"name": "Amq__Password", "role": "amq", "value": "{{amq.password}}"},
    {"name": "Amq__Url", "role": "amq", "value": "amqp://{{amq.host}}:{{amq.amqpPort}}"},
    {"name": "Amq__User", "role": "amq", "value": "{{amq.user}}"},
    {"name": "Auth__Audience", "role": "auth", "value": "deals-api"},
    {"name": "Auth__Authority", "role": "auth", "value": "https://login.example/realms/acme"},
    {"name": "Auth__Enabled", "role": "auth", "value": "false"},
    {"name": "ConnectionStrings__Deals", "role": "db",
     "value": "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
              "Username={{db.user}};Password={{db.password}}"},
    {"name": "Pricing__BaseUrl", "role": "downstream:pricing", "value": "{{stubs.url}}/pricing"},
]


def _analysed(tmp_path: Path,
              fixture: str) -> tuple[Path, Path, Path, dict[str, Any], dict[str, Any]]:
    root = FIXTURES / fixture
    stack = tmp_path / "stack.json"
    env = tmp_path / "env-map.json"
    ledger = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env", str(env),
                          "--out-ledger", str(ledger)]) == 0
    return root, ledger, env, load_ledger(ledger), read_json(env)


def test_env_name_follows_each_stacks_convention() -> None:
    assert env_name("spring", "spring.datasource.password", None) == "SPRING_DATASOURCE_PASSWORD"
    assert env_name("quarkus", "quarkus.datasource.jdbc.url", None) == "QUARKUS_DATASOURCE_JDBC_URL"
    assert env_name("aspnetcore", "Amq__User", None) == "Amq__User"
    assert env_name("python", "database_url", None) is None
    assert env_name("python", "database_url", "DATABASE_URL") == "DATABASE_URL"


@pytest.mark.parametrize(("stack", "name", "role", "placeholder", "source", "expected"), [
    ("spring", "SPRING_DATASOURCE_URL", "db", "", "deployment.yml",
     "jdbc:postgresql://{{db.host}}:{{db.port}}/{{db.name}}"),
    ("aspnetcore", "ConnectionStrings__Deals", "db", "", "deployment.yml",
     "Host={{db.host}};Port={{db.port}};Database={{db.name}};"
     "Username={{db.user}};Password={{db.password}}"),
    ("python", "DATABASE_URL", "db", "", "deployment.yml",
     "postgresql://{{db.user}}:{{db.password}}@{{db.host}}:{{db.port}}/{{db.name}}"),
    ("spring", "SPRING_DATASOURCE_USERNAME", "db", "${X:shipments}", "application.yml",
     "{{db.user}}"),
    ("aspnetcore", "PGHOST", "db", "", "deployment.yml", "{{db.host}}"),
    ("aspnetcore", "PGPORT", "db", "", "deployment.yml", "{{db.port}}"),
    ("aspnetcore", "PGDATABASE", "db", "", "deployment.yml", "{{db.name}}"),
    ("python", "DB_NAME", "db", "", "deployment.yml", "{{db.name}}"),
    # db-role keys that name no part of the connection get no value: a JDBC URL in
    # spring.datasource.driver-class-name or hikari.maximum-pool-size stops the app booting.
    ("spring", "SPRING_DATASOURCE_DRIVER_CLASS_NAME", "db", "org.postgresql.Driver",
     "application.yml", None),
    ("spring", "SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE", "db", "10", "application.yml", None),
    ("quarkus", "QUARKUS_DATASOURCE_DB_KIND", "db", "postgresql", "application.properties", None),
    ("spring", "SPRING_ARTEMIS_BROKER_URL", "amq", "tcp://artemis:61616", "deployment.yml",
     "tcp://{{amq.host}}:{{amq.corePort}}"),
    ("aspnetcore", "Amq__Url", "amq", "amqp://artemis:5672", "deployment.yml",
     "amqp://{{amq.host}}:{{amq.amqpPort}}"),
    ("python", "AMQ_URL", "amq", "", "deployment.yml", "amqp://{{amq.host}}:{{amq.amqpPort}}"),
    ("python", "AMQ_HOST", "amq", "", "deployment.yml", "{{amq.host}}"),
    ("python", "AMQ_PORT", "amq", "", "deployment.yml", "{{amq.amqpPort}}"),
    ("python", "STOMP_URL", "amq", "stomp://amq:61613", "deployment.yml",
     "stomp://{{amq.host}}:{{amq.stompPort}}"),
    ("aspnetcore", "Amq__Password", "amq", "artemis", "appsettings.json", "{{amq.password}}"),
    ("spring", "PRICING_BASE_URL", "downstream:pricing", "http://pricing:8080", "deployment.yml",
     "{{stubs.url}}/pricing"),
    ("spring", "APP_SECURITY_ENABLED", "auth", "${APP_SECURITY_ENABLED:true}", "application.yml",
     "false"),
    ("spring", "AUTH_ISSUER_URI", "auth", "https://login.example/realms/acme", "deployment.yml",
     "https://login.example/realms/acme"),
    ("spring", "AUTH_ISSUER_URI", "auth", "${AUTH_ISSUER_URI}", "application.yml", None),
    ("spring", "SPRING_PROFILES_ACTIVE", "passthrough", "prod", "deployment.yml", "prod"),
    ("spring", "JAVA_OPTS", "passthrough", "-Xmx512m", "Dockerfile", None),
    ("spring", "spring.jpa.hibernate.ddl-auto", "passthrough", "validate", "application.yml", None),
])
def test_env_value_rules(stack: str, name: str, role: str, placeholder: str, source: str,
                         expected: str | None) -> None:
    assert env_value(stack, name, role, placeholder, source, "deployment.yml", DISABLED) == expected


def test_env_value_jwks_mode_points_issuer_and_jwks_keys_at_wiremock() -> None:
    assert env_value("spring", "AUTH_ISSUER_URI", "auth", "", "deployment.yml", "deployment.yml",
                     JWKS) == "{{auth.url}}"
    assert env_value("spring", "AUTH_JWKS_URL", "auth", "", "deployment.yml", "deployment.yml",
                     JWKS) == "{{auth.url}}/.well-known/jwks.json"


def test_db_name_from_env_prefers_explicit_names() -> None:
    def keys(*items: tuple[str, str, str]) -> dict[str, Any]:
        return {"keys": [{"key": k, "role": r, "placeholder": p} for k, r, p in items]}
    assert db_name_from_env(keys(("ConnectionStrings__Deals", "db",
                                  "Host=localhost;Database=deals;Username=u"))) == "deals"
    assert db_name_from_env(keys(("SPRING_DATASOURCE_URL", "db",
                                  "jdbc:postgresql://db:5432/shipments"))) == "shipments"
    assert db_name_from_env(keys(("DATABASE_URL", "db",
                                  "postgresql://u:p@h:5432/orders"))) == "orders"
    assert db_name_from_env(keys(("ConnectionStrings__Deals", "db", ""))) == "deals"
    assert db_name_from_env(keys(("SPRING_DATASOURCE_URL", "db", ""))) == "app"


def test_build_runtime_spring_mini(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "spring-mini")
    out = tmp_path / "karate-tests"
    runtime = build_runtime(ledger, env_map, root, out, load_central_config(None), IMAGE)
    assert runtime["version"] == 1
    assert runtime["repo"] == "spring-mini"
    assert runtime["stack"] == "spring"
    assert (out / runtime["app"]["repoRootRel"]).resolve() == root.resolve()
    assert runtime["app"] | {"repoRootRel": ""} == {
        "repoRootRel": "", "dockerfileRel": "Dockerfile", "port": 8080,
        "readinessPath": "/actuator/health/readiness", "serverless": True,
        "startupTimeoutSeconds": 120,
    }
    assert runtime["env"] == SPRING_ENV
    assert runtime["db"] == {"name": "app", "user": "app", "password": "app"}
    assert runtime["migrations"] == {"strategy": "migration-container", "image": IMAGE,
                                     "env": DEFAULT_MIGRATION_ENV}
    assert runtime["amq"] == {"user": "artemis", "password": "artemis",
                              "queues": ["shipment.requested"], "topics": []}
    assert runtime["downstreams"] == [{"name": "pricing", "envVar": "PRICING_BASE_URL"}]
    assert runtime["auth"] == {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false"}


def test_build_runtime_dotnet_mini_and_central_config(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "dotnet-mini")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "db_managers:\n"
        "  deals:\n"
        "    image: registry.example/db-manager-deals:latest\n"
        "    env:\n"
        "      DB_HOST_KEY: PGHOST\n"
        "      DB_PORT_KEY: PGPORT\n"
        "      DB_NAME_KEY: DBNAME\n"
        "      DB_USER_KEY: PGUSER\n"
        "      DB_PASSWORD_KEY: PGPASSWORD\n"
        "    database: deals\n"
        "    extra_env:\n"
        "      FLYWAY_SCHEMAS: public\n",
        encoding="utf-8",
    )
    config = load_central_config(config_path)
    runtime = build_runtime(ledger, env_map, root, tmp_path / "karate-tests", config, None)
    assert runtime["stack"] == "aspnetcore"
    assert runtime["env"] == DOTNET_ENV
    assert runtime["db"]["name"] == "deals"
    assert runtime["migrations"] == {
        "strategy": "migration-container", "image": "registry.example/db-manager-deals:latest",
        "env": {"PGHOST": "{{db.host}}", "PGPORT": "{{db.port}}", "DBNAME": "{{db.name}}",
                "PGUSER": "{{db.user}}", "PGPASSWORD": "{{db.password}}",
                "FLYWAY_SCHEMAS": "public"},
    }
    assert runtime["app"]["readinessPath"] == "/health/ready"
    assert runtime["app"]["serverless"] is False
    assert runtime["auth"] == {"mode": "disabled", "key": "Auth__Enabled", "value": "false"}
    overridden = build_runtime(ledger, env_map, root, tmp_path / "karate-tests", config, IMAGE)
    assert overridden["migrations"]["image"] == IMAGE
    assert overridden["migrations"]["env"]["DBNAME"] == "{{db.name}}"


def test_build_runtime_exits_4_without_a_schema_source(tmp_path: Path) -> None:
    root, _, _, ledger, env_map = _analysed(tmp_path, "spring-mini")
    with pytest.raises(KbError) as excinfo:
        build_runtime(ledger, env_map, root, tmp_path / "karate-tests",
                      load_central_config(None), None)
    assert excinfo.value.exit_code == EXIT_NO_SCHEMA
    assert "--migrations-image" in str(excinfo.value)


def test_copy_template_never_overwrites_generated_content(tmp_path: Path) -> None:
    out = tmp_path / "karate-tests"
    first = copy_template(TEMPLATE_DIR, out, force=False)
    assert "pom.xml" in first["written"]
    assert RUNTIME_REL not in first["written"]  # written by main, not by the copy
    assert (out / "rules/harness-smoke.csv").is_file()
    (out / "pom.xml").write_text("edited", encoding="utf-8")
    (out / "rules/harness-smoke.csv").write_text("edited", encoding="utf-8")
    smoke = out / "src/test/resources/features/harness-smoke.feature"
    smoke.write_text("edited", encoding="utf-8")
    (out / "defects.md").write_text("edited", encoding="utf-8")
    second = copy_template(TEMPLATE_DIR, out, force=False)
    assert second["written"] == [] and second["overwritten"] == []
    assert {"pom.xml", "rules/harness-smoke.csv", "defects.md",
            "src/test/resources/features/harness-smoke.feature"} <= set(second["kept"])
    third = copy_template(TEMPLATE_DIR, out, force=True)
    assert "pom.xml" in third["overwritten"]
    assert (out / "pom.xml").read_text(encoding="utf-8") != "edited"
    # The smoke feature is harness content, so --force refreshes it despite its generated prefix.
    assert "src/test/resources/features/harness-smoke.feature" in third["overwritten"]
    assert smoke.read_text(encoding="utf-8") != "edited"
    for kept in ("rules/harness-smoke.csv", "defects.md"):
        assert (out / kept).read_text(encoding="utf-8") == "edited", kept


def test_cli_scaffolds_and_rewrites_runtime(tmp_path: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    root, ledger_path, env_path, _, _ = _analysed(tmp_path, "spring-mini")
    out = tmp_path / "karate-tests"
    argv = [str(root), "--ledger", str(ledger_path), "--env", str(env_path), "--out", str(out),
            "--migrations-image", IMAGE, "--config", str(tmp_path / "absent.yaml")]
    assert run_cli(main, argv) == 0
    assert "scaffolded" in capsys.readouterr().out
    runtime = read_json(out / RUNTIME_REL)
    assert runtime["repo"] == "spring-mini"
    assert (out / "mvnw").is_file() and (out / "src/test/java/kb/harness/Containers.java").is_file()
    # kb_report summary reads README.md.tmpl from the skill, so it never lands in the repo.
    assert not (out / "README.md.tmpl").exists()
    (out / RUNTIME_REL).write_text("{}", encoding="utf-8")
    assert run_cli(main, argv) == 0
    assert read_json(out / RUNTIME_REL)["env"] == SPRING_ENV
    assert run_cli(main, argv[:-4] + ["--config", str(tmp_path / "absent.yaml")]) == EXIT_NO_SCHEMA
