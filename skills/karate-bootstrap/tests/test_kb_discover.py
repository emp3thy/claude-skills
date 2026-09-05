from __future__ import annotations

from pathlib import Path

from discover import (
    assign_role,
    detect_auth,
    detect_auth_switch,
    downstream_name,
    find_dockerfile,
    find_manifests,
    parse_app_config,
    parse_dockerfile,
    parse_manifest,
)
from kb_helpers import line_of as line_of  # re-exported for tasks appended in Task 6

FIXTURES = Path(__file__).parent / "fixtures"


def test_find_manifests_prefers_named_files() -> None:
    spring = find_manifests(FIXTURES / "spring-mini")
    assert [(p.name, s) for p, s in spring] == [("deploymentserverless.yml", True)]
    quarkus = find_manifests(FIXTURES / "quarkus-mini")
    assert [(p.name, s) for p, s in quarkus] == [("deployment.yml", False)]


def test_find_manifests_generic_fallback(tmp_path: Path) -> None:
    k8s = tmp_path / "k8s"
    k8s.mkdir()
    (k8s / "svc.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n"
        "      containers:\n        - name: x\n          ports:\n"
        "            - containerPort: 9000\n",
        encoding="utf-8",
    )
    assert [(p.name, s) for p, s in find_manifests(tmp_path)] == [("svc.yaml", False)]


def test_parse_knative_manifest() -> None:
    root = FIXTURES / "spring-mini"
    result = parse_manifest(root / "deploymentserverless.yml", root, serverless=True)
    assert result["serverless"] is True
    assert result["port"] == 8080
    assert result["readiness"] == {
        "path": "/actuator/health/readiness",
        "port": 8080,
        "source": "deploymentserverless.yml",
    }
    assert result["env"]["SPRING_DATASOURCE_URL"] is None
    assert result["env"]["SPRING_ARTEMIS_BROKER_URL"] == "tcp://artemis:61616"
    assert result["env_from"] == ["shipments-config"]


def test_parse_deployment_resolves_named_probe_port() -> None:
    root = FIXTURES / "quarkus-mini"
    result = parse_manifest(root / "deployment.yml", root, serverless=False)
    assert result["readiness"]["port"] == 8080
    assert result["readiness"]["path"] == "/q/health/ready"
    assert result["env"]["AMQP_PORT"] == "5672"


def test_find_and_parse_dockerfile() -> None:
    spring = find_dockerfile(FIXTURES / "spring-mini")
    assert spring is not None and spring.name == "Dockerfile"
    quarkus = find_dockerfile(FIXTURES / "quarkus-mini")
    assert quarkus is not None and quarkus.name == "Dockerfile.jvm"
    parsed = parse_dockerfile(FIXTURES / "dotnet-mini" / "Dockerfile")
    assert parsed == {"expose": 8080, "env": {"ASPNETCORE_URLS": "http://+:8080"}}
    spring_parsed = parse_dockerfile(FIXTURES / "spring-mini" / "Dockerfile")
    assert spring_parsed["env"] == {"JAVA_OPTS": "-Xmx512m"}


def test_parse_app_config_spring_yaml_extracts_env_vars() -> None:
    keys = parse_app_config(FIXTURES / "spring-mini")
    assert keys["spring.datasource.url"]["env_var"] == "SPRING_DATASOURCE_URL"
    assert keys["spring.datasource.username"]["env_var"] == "SPRING_DATASOURCE_USERNAME"
    assert keys["spring.jpa.hibernate.ddl-auto"]["placeholder"] == "validate"
    assert keys["app.security.enabled"]["env_var"] == "APP_SECURITY_ENABLED"
    assert keys["app.security.enabled"]["source"] == "src/main/resources/application.yml"


def test_parse_app_config_quarkus_properties() -> None:
    keys = parse_app_config(FIXTURES / "quarkus-mini")
    assert keys["quarkus.oidc.enabled"]["env_var"] == "OIDC_ENABLED"
    assert keys["mp.messaging.incoming.order-completed.address"]["placeholder"] == "order.completed"
    assert keys["quarkus.hibernate-orm.database.generation"]["placeholder"] == "none"


def test_parse_app_config_appsettings_uses_double_underscore() -> None:
    keys = parse_app_config(FIXTURES / "dotnet-mini")
    assert keys["ConnectionStrings__Deals"]["placeholder"].startswith("Host=localhost")
    assert keys["Auth__Enabled"]["placeholder"] == "true"
    assert keys["Pricing__BaseUrl"]["placeholder"] == "http://localhost:9010"


def test_parse_app_config_python_settings_reads_environ() -> None:
    keys = parse_app_config(FIXTURES / "fastapi-mini")
    assert keys["DATABASE_URL"]["env_var"] == "DATABASE_URL"
    assert keys["AMQP_URL"]["placeholder"] == "amqp://localhost:5672"
    assert keys["AUTH_MODE"]["placeholder"] == "jwt"


def test_assign_role_covers_each_role() -> None:
    assert assign_role("SPRING_DATASOURCE_URL", "") == "db"
    assert assign_role("ConnectionStrings__Deals", "Host=localhost;Database=deals") == "db"
    assert assign_role("DATABASE_URL", "postgresql://x") == "db"
    assert assign_role("SPRING_ARTEMIS_BROKER_URL", "tcp://artemis:61616") == "amq"
    assert assign_role("Amq__Url", "amqp://localhost:5672") == "amq"
    assert assign_role("AMQP_PORT", "5672") == "amq"
    assert assign_role("mp.messaging.incoming.order-completed.address", "order.completed") == "amq"
    assert assign_role("AUTH_ISSUER_URI", "https://login.example/realms/acme") == "auth"
    assert assign_role("quarkus.oidc.auth-server-url", "") == "auth"
    assert assign_role("JWKS_URL", "") == "auth"
    assert assign_role("PRICING_BASE_URL", "http://pricing:8080") == "downstream:pricing"
    assert assign_role("quarkus.rest-client.orders-api.url", "") == "downstream:orders-api"
    assert assign_role("INVENTORY_URL", "") == "downstream:inventory"
    assert assign_role("spring.jpa.hibernate.ddl-auto", "validate") == "passthrough"
    assert assign_role("JAVA_OPTS", "-Xmx512m") == "passthrough"


def test_downstream_name_strips_noise() -> None:
    assert downstream_name("Pricing__BaseUrl") == "pricing"
    assert downstream_name("PRICING_BASE_URL") == "pricing"
    assert downstream_name("quarkus.rest-client.orders-api.url") == "orders-api"
    assert downstream_name("INVENTORY_URL") == "inventory"


def _keys(*items: tuple[str, str, str | None]) -> dict[str, dict[str, object]]:
    return {
        key: {"placeholder": placeholder, "source": "test", "env_var": env_var,
              "role": assign_role(key, placeholder)}
        for key, placeholder, env_var in items
    }


def test_detect_auth_switch_prefers_env_var_and_flips_enabled() -> None:
    switch = detect_auth_switch(_keys(("app.security.enabled", "${APP_SECURITY_ENABLED:true}",
                                       "APP_SECURITY_ENABLED")))
    assert switch == {"mode": "disabled", "key": "APP_SECURITY_ENABLED", "value": "false",
                      "confirmed": True}


def test_detect_auth_switch_mode_key_is_unconfirmed() -> None:
    switch = detect_auth_switch(_keys(("AUTH_MODE", "jwt", "AUTH_MODE")))
    assert switch == {"mode": "disabled", "key": "AUTH_MODE", "value": "disabled",
                      "confirmed": False}


def test_detect_auth_jwks_when_no_switch() -> None:
    result = detect_auth(_keys(("AUTH_ISSUER_URI", "https://login.example", "AUTH_ISSUER_URI")),
                         "spring-security")
    assert result == {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}


def test_detect_auth_none_without_library() -> None:
    assert detect_auth(_keys(("PRICING_BASE_URL", "http://p", None)), None) == {"mode": "none"}


def test_detect_auth_jwks_wins_over_none_when_issuer_key_exists() -> None:
    result = detect_auth(_keys(("JWKS_URL", "https://login.example/certs", "JWKS_URL")), None)
    assert result == {"mode": "jwks", "keys": ["JWKS_URL"]}


def test_detect_auth_blocked_when_library_but_no_keys() -> None:
    assert detect_auth(_keys(("PRICING_BASE_URL", "http://p", None)), "jwt-bearer") == {
        "mode": "blocked"
    }
