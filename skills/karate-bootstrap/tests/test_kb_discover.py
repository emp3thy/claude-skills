from __future__ import annotations

from pathlib import Path

from detect import detect
from detect import main as detect_main
from discover import (
    _CLASS_DECL_RE,
    _class_prefix,
    assign_role,
    build_env_map,
    detect_auth,
    detect_auth_switch,
    detect_migrations,
    downstream_name,
    find_dockerfile,
    find_entry_points,
    find_manifests,
    join_path,
    main,
    parse_app_config,
    parse_dockerfile,
    parse_manifest,
    seed_ledger,
)
from flow_map import new_entry
from kb_common import read_yaml
from kb_helpers import line_of

FIXTURES = Path(__file__).parent / "fixtures"


def test_find_manifests_prefers_named_files() -> None:
    spring = find_manifests(FIXTURES / "spring-mini")
    assert [(p.name, s) for p, s in spring] == [("deploymentserverless.yml", True)]
    quarkus = find_manifests(FIXTURES / "quarkus-mini")
    assert [(p.name, s) for p, s in quarkus] == [("deployment.yml", False)]


def test_find_manifests_prefers_serverless_when_both_exist(tmp_path: Path) -> None:
    body = ("apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n"
            "      containers:\n        - name: x\n")
    (tmp_path / "deployment.yml").write_text(body, encoding="utf-8")
    (tmp_path / "deploymentserverless.yml").write_text(body, encoding="utf-8")
    assert find_manifests(tmp_path)[0] == (tmp_path / "deploymentserverless.yml", True)


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


def _write(root: Path, relpath: str, text: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_parse_app_config_base_profile_wins_over_variants_and_test_tree(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/resources/application.yml",
           "spring:\n  datasource:\n    url: ${SPRING_DATASOURCE_URL}\n")
    _write(tmp_path, "src/main/resources/application-prod.yml",
           "spring:\n  datasource:\n    url: jdbc:postgresql://prod-db:5432/app\n")
    _write(tmp_path, "src/test/resources/application.yml",
           "spring:\n  datasource:\n    url: jdbc:h2:mem:test\n")
    keys = parse_app_config(tmp_path)
    assert keys["spring.datasource.url"]["env_var"] == "SPRING_DATASOURCE_URL"
    assert keys["spring.datasource.url"]["source"] == "src/main/resources/application.yml"


def test_find_entry_points_ignores_test_trees(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/java/com/acme/ShipmentController.java",
           'package com.acme;\n\n@RestController\n@RequestMapping("/api/shipments")\n'
           'public class ShipmentController {\n    @GetMapping("/{id}")\n'
           '    public String get() { return "x"; }\n}\n')
    _write(tmp_path, "src/test/java/com/acme/ShipmentControllerTest.java",
           'package com.acme;\n\npublic class ShipmentControllerTest {\n'
           '    @GetMapping("/test-only")\n    public void t() { }\n}\n')
    assert {e["id"] for e in find_entry_points(tmp_path, "spring", {})} == {
        "GET /api/shipments/{id}"
    }


def test_detect_migrations_ignores_test_profile_ddl_auto(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/resources/application.yml",
           "spring:\n  jpa:\n    hibernate:\n      ddl-auto: validate\n")
    _write(tmp_path, "src/test/resources/application.yml",
           "spring:\n  jpa:\n    hibernate:\n      ddl-auto: create-drop\n")
    config = parse_app_config(tmp_path)
    assert config["spring.jpa.hibernate.ddl-auto"]["placeholder"] == "validate"
    assert detect_migrations(tmp_path, "spring", config)["also_on_boot"] is False


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
    assert assign_role("pricing.base-url", "") == "downstream:pricing"
    assert assign_role("quarkus.rest-client.orders-api.url", "") == "downstream:orders"
    assert assign_role("INVENTORY_URL", "") == "downstream:inventory"
    assert assign_role("spring.jpa.hibernate.ddl-auto", "validate") == "passthrough"
    assert assign_role("JAVA_OPTS", "-Xmx512m") == "passthrough"


def test_downstream_name_strips_noise() -> None:
    assert downstream_name("Pricing__BaseUrl") == "pricing"
    assert downstream_name("PRICING_BASE_URL") == "pricing"
    assert downstream_name("quarkus.rest-client.orders-api.url") == "orders"
    assert downstream_name("INVENTORY_URL") == "inventory"


def test_downstream_name_matches_across_hyphen_and_underscore_spellings() -> None:
    assert downstream_name("pricing.base-url") == "pricing"
    assert downstream_name("pricing.base-url") == downstream_name("PRICING_BASE_URL")


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


def _config(repo: str) -> dict[str, dict[str, object]]:
    return parse_app_config(FIXTURES / repo)


def test_join_path_normalises() -> None:
    assert join_path("/api/shipments", "") == "/api/shipments"
    assert join_path("/api/shipments", "/{id}") == "/api/shipments/{id}"
    assert join_path("api/deals", "{id:guid}") == "/api/deals/{id}"
    assert join_path("", "/healthz") == "/healthz"
    assert join_path("/api/", "/x/") == "/api/x"


def test_spring_entry_points() -> None:
    root = FIXTURES / "spring-mini"
    entries = find_entry_points(root, "spring", _config("spring-mini"))
    by_id = {e["id"]: e for e in entries}
    controller = root / "src/main/java/com/acme/shipments/ShipmentController.java"
    listener = root / "src/main/java/com/acme/shipments/ShipmentEventsListener.java"
    assert set(by_id) == {
        "POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"
    }
    assert by_id["POST /api/shipments"]["handler"] == (
        "src/main/java/com/acme/shipments/ShipmentController.java:"
        f"{line_of(controller, '@PostMapping')}"
    )
    assert by_id["amq shipment.requested"]["handler"].endswith(
        f":{line_of(listener, '@JmsListener')}"
    )
    assert by_id["amq shipment.requested"]["kind"] == "amq-subscribe"


def test_class_prefix_survives_a_javadoc_that_mentions_the_word_class(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/java/com/acme/ShipmentController.java",
           "package com.acme;\n\n/** REST controller class for shipments. */\n"
           '@RestController\n@RequestMapping("/api/shipments")\n'
           'public class ShipmentController {\n    @GetMapping("/{id}")\n'
           '    public String get() { return "x"; }\n}\n')
    assert {e["id"] for e in find_entry_points(tmp_path, "spring", {})} == {
        "GET /api/shipments/{id}"
    }


def test_amq_entry_points_are_id_first_and_queue_by_default() -> None:
    root = FIXTURES / "spring-mini"
    entries = find_entry_points(root, "spring", _config("spring-mini"))
    entry = next(e for e in entries if e["id"] == "amq shipment.requested")
    assert next(iter(entry)) == "id"
    assert entry["type"] == "queue"


def test_quarkus_entry_points_resolve_channel_address() -> None:
    root = FIXTURES / "quarkus-mini"
    entries = find_entry_points(root, "quarkus", _config("quarkus-mini"))
    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == {"POST /api/invoices", "GET /api/invoices/{id}", "amq order.completed"}
    assert by_id["amq order.completed"]["channel"] == "order-completed"
    resource = root / "src/main/java/com/acme/invoices/InvoiceResource.java"
    assert by_id["GET /api/invoices/{id}"]["handler"].endswith(f":{line_of(resource, '@GET')}")


def test_dotnet_entry_points_expand_controller_token() -> None:
    root = FIXTURES / "dotnet-mini"
    entries = find_entry_points(root, "aspnetcore", _config("dotnet-mini"))
    by_id = {e["id"]: e for e in entries}
    assert set(by_id) == {"POST /api/deals", "GET /api/deals/{id}", "amq deal.requested"}
    consumer = root / "Messaging/DealRequestedConsumer.cs"
    needle = 'GetQueue("deal.requested")'
    assert by_id["amq deal.requested"]["handler"].endswith(f":{line_of(consumer, needle)}")


def test_fastapi_entry_points() -> None:
    root = FIXTURES / "fastapi-mini"
    entries = find_entry_points(root, "python", _config("fastapi-mini"))
    assert {e["id"] for e in entries} == {
        "GET /healthz",
        "POST /api/orders",
        "GET /api/orders/{order_id}",
        "amq order.requested",
    }


def test_detect_migrations_per_fixture() -> None:
    spring = detect_migrations(FIXTURES / "spring-mini", "spring", _config("spring-mini"))
    assert spring["strategy"] == "migration-container"
    assert spring["repo_migrations"] == ["src/main/resources/db/migration"]
    assert spring["also_on_boot"] is False
    dotnet = detect_migrations(FIXTURES / "dotnet-mini", "aspnetcore", _config("dotnet-mini"))
    assert dotnet["repo_migrations"] == ["Data/Migrations"]
    fastapi = detect_migrations(FIXTURES / "fastapi-mini", "python", _config("fastapi-mini"))
    assert fastapi["repo_migrations"] == ["alembic/versions"]


def test_detect_migrations_flags_on_boot(tmp_path: Path) -> None:
    config = {"spring.jpa.hibernate.ddl-auto": {"placeholder": "update", "source": "x",
                                                 "env_var": None}}
    assert detect_migrations(tmp_path, "spring", config)["also_on_boot"] is True


def test_build_env_map_dotnet() -> None:
    root = FIXTURES / "dotnet-mini"
    stack_info = detect(root)
    manifest = parse_manifest(root / "deployment.yml", root, serverless=False)
    dockerfile = parse_dockerfile(root / "Dockerfile")
    env_map = build_env_map(stack_info, manifest, dockerfile, _config("dotnet-mini"))
    roles = {k["key"]: k["role"] for k in env_map["keys"]}
    assert roles["ConnectionStrings__Deals"] == "db"
    assert roles["Amq__Url"] == "amq"
    assert roles["Pricing__BaseUrl"] == "downstream:pricing"
    assert roles["ASPNETCORE_URLS"] == "passthrough"
    assert env_map["port"] == 8080
    assert env_map["readiness"]["path"] == "/health/ready"
    assert env_map["auth"] == {"mode": "disabled", "key": "Auth__Enabled", "value": "false",
                               "confirmed": True}


def test_build_env_map_falls_back_to_dockerfile_port_and_port_wait(tmp_path: Path) -> None:
    stack_info = {"framework": "python", "auth": None}
    dockerfile = {"expose": 9001, "env": {}}
    env_map = build_env_map(stack_info, None, dockerfile, {})
    assert env_map["port"] == 9001
    assert env_map["readiness"] == {"path": None, "port": 9001, "source": "fallback"}
    assert env_map["manifest"] is None


def test_cli_writes_env_map_and_seeded_ledger(tmp_path: Path) -> None:
    root = FIXTURES / "spring-mini"
    stack_path = tmp_path / "stack.json"

    assert detect_main([str(root), "--out", str(stack_path), "--skip-toolchain"]) == 0
    env_path = tmp_path / "env-map.json"
    ledger_path = tmp_path / "flow-map.yaml"
    code = main([str(root), "--stack", str(stack_path), "--out-env", str(env_path),
                 "--out-ledger", str(ledger_path)])
    assert code == 0
    ledger = read_yaml(ledger_path)
    assert ledger["version"] == 1
    assert ledger["repo"] == "spring-mini"
    assert ledger["stack"]["framework"] == "spring"
    assert ledger["app"]["serverless"] is True
    assert ledger["app"]["dockerfile"] == "Dockerfile"
    assert ledger["app"]["readiness"]["path"] == "/actuator/health/readiness"
    assert ledger["app"]["migrations"]["strategy"] == "migration-container"
    assert ledger["app"]["auth"]["key"] == "APP_SECURITY_ENABLED"
    ids = [e["id"] for e in ledger["entry_points"]]
    assert ids == ["POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"]
    first = ledger["entry_points"][0]
    assert first["status"] == {"traced": False, "stubbed": False, "tested": False,
                               "passing": False}
    assert first["exits"] == [] and first["rules"] == {"file": None, "count": 0, "sources": []}
    assert ledger["unresolved"] == []


def test_class_prefix_handles_annotation_on_the_class_line() -> None:
    lines = [
        "package com.acme;",
        '@RestController @RequestMapping("/api/shipments") public class ShipmentController {',
        '    @GetMapping("/{id}")',
        '    public String get() { return "x"; }',
        "}",
    ]
    assert _class_prefix("spring", lines) == ("/api/shipments", 1)


def test_class_prefix_handles_csharp_attribute_on_the_class_line() -> None:
    lines = [
        "namespace Deals.Api.Controllers;",
        '[ApiController] [Route("api/[controller]")] public class DealsController : ControllerBase',
        "{",
        "}",
    ]
    assert _class_prefix("aspnetcore", lines) == ("api/deals", 1)


def test_detect_auth_jwks_dedupes_manifest_and_config_spellings() -> None:
    # Regression guard: detect_auth already sorts a set. It passes before any change.
    result = detect_auth(_keys(
        ("AUTH_ISSUER_URI", "https://login.example/realms/acme", "AUTH_ISSUER_URI"),
        ("spring.security.oauth2.resourceserver.jwt.issuer-uri", "${AUTH_ISSUER_URI}",
         "AUTH_ISSUER_URI"),
    ), "spring-security")
    assert result == {"mode": "jwks", "keys": ["AUTH_ISSUER_URI"]}


def test_class_decl_regex_is_linear_on_long_attribute_lines() -> None:
    # A bracketed run that never reaches a class keyword must fail fast, not backtrack
    # exponentially: discovery scans every line of every source file with this regex.
    for length in (30, 200, 2000):
        assert _CLASS_DECL_RE.search("[" + "a" * length + "] somethingElse") is None
        assert _CLASS_DECL_RE.search("[" + "a" * length) is None
        assert _CLASS_DECL_RE.search('[Route("' + "x" * length + '")] public class C {') is not None


def test_seed_ledger_entries_match_new_entry_shape() -> None:
    root = FIXTURES / "spring-mini"
    stack_info = detect(root)
    config = parse_app_config(root)
    env_map = build_env_map(stack_info, None, None, config)
    entries = find_entry_points(root, "spring", config)
    ledger = seed_ledger(stack_info, env_map, entries, detect_migrations(root, "spring", config),
                        "spring-mini", "Dockerfile")
    for seeded, base in zip(ledger["entry_points"], entries, strict=True):
        assert seeded == new_entry(base)
