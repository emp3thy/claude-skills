"""One recipe per live fixture: what the chain runs and what the run must produce.

The live-run harness (``test_kb_live_run.py``) is fixture-agnostic; everything specific to a
service lives here and under ``tests/fixtures/live/<fixture>/expected/``.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "live"


class Recipe(NamedTuple):
    """A live fixture and the facts the harness needs to drive it."""

    name: str
    fixture: Path
    stack: str
    app_port: int
    auth_key: str
    auth_off_value: str
    entries: tuple[str, ...]
    rules_sources: tuple[tuple[str, str], ...]
    marks: dict[str, tuple[tuple[str, str], ...]]
    planted_scenario: str
    planted_feature: str
    prebuild_app_image: bool


SPRING = Recipe(
    name="spring-shipments",
    fixture=FIXTURES / "spring-shipments",
    stack="spring",
    app_port=8080,
    auth_key="APP_SECURITY_ENABLED",
    auth_off_value="false",
    entries=("POST /api/shipments", "GET /api/shipments/{id}", "amq shipment.requested"),
    rules_sources=(
        ("POST /api/shipments", "src/main/java/com/acme/shipments/ShipmentRequest.java"),
        ("POST /api/shipments", "src/main/java/com/acme/shipments/ShipmentService.java"),
    ),
    marks={
        "POST /api/shipments": (("--stub", "stubs/pricing/default.json"),
                                ("--seed", "seed/examples/post-api-shipments.json")),
        "GET /api/shipments/{id}": (),
        "amq shipment.requested": (("--seed", "seed/examples/amq-shipment-requested.json"),),
    },
    planted_scenario="rejects a shipment over the weight limit",
    planted_feature="features/post-api-shipments.feature",
    prebuild_app_image=True,
)

DOTNET = Recipe(
    name="dotnet-deals",
    fixture=FIXTURES / "dotnet-deals",
    stack="aspnetcore",
    app_port=8080,
    auth_key="Auth__Enabled",
    auth_off_value="false",
    entries=("POST /api/deals", "GET /api/deals/{id}", "amq deal.requested"),
    rules_sources=(
        ("POST /api/deals", "Validators/DealRequestValidator.cs"),
        ("POST /api/deals", "Services/DealService.cs"),
    ),
    marks={
        "POST /api/deals": (("--stub", "stubs/pricing/default.json"),
                            ("--seed", "seed/examples/post-api-deals.json")),
        "GET /api/deals/{id}": (),
        "amq deal.requested": (("--seed", "seed/examples/amq-deal-requested.json"),),
    },
    planted_scenario="rejects a deal over the quantity limit",
    planted_feature="features/post-api-deals.feature",
    prebuild_app_image=True,
)

FASTAPI = Recipe(
    name="fastapi-orders",
    fixture=FIXTURES / "fastapi-orders",
    stack="python",
    app_port=8000,
    auth_key="AUTH_ENABLED",
    auth_off_value="false",
    entries=("GET /healthz", "POST /api/orders", "GET /api/orders/{order_id}",
             "amq order.requested"),
    rules_sources=(
        ("POST /api/orders", "app/schemas.py"),
        ("POST /api/orders", "app/service.py"),
    ),
    marks={
        "GET /healthz": (),
        "POST /api/orders": (("--stub", "stubs/inventory/default.json"),
                             ("--seed", "seed/examples/post-api-orders.json")),
        "GET /api/orders/{order_id}": (),
        "amq order.requested": (("--seed", "seed/examples/amq-order-requested.json"),),
    },
    planted_scenario="rejects an order over the quantity limit",
    planted_feature="features/post-api-orders.feature",
    prebuild_app_image=False,
)

RECIPES: dict[str, Recipe] = {r.name: r for r in (SPRING, DOTNET, FASTAPI)}
