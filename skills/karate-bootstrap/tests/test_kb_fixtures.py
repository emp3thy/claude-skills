from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from kb_rules import slug_for
from live_recipes import RECIPES

FIXTURES = Path(__file__).parent / "fixtures"

REQUIRED = {
    "spring-mini": [
        "pom.xml",
        "Dockerfile",
        "deploymentserverless.yml",
        "src/main/resources/application.yml",
        "src/main/resources/db/migration/V1__init.sql",
        "src/main/java/com/acme/shipments/ShipmentController.java",
        "src/main/java/com/acme/shipments/ShipmentRequest.java",
        "src/main/java/com/acme/shipments/ShipmentService.java",
        "src/main/java/com/acme/shipments/ShipmentRepository.java",
        "src/main/java/com/acme/shipments/Shipment.java",
        "src/main/java/com/acme/shipments/ShipmentEventsListener.java",
    ],
    "quarkus-mini": [
        "pom.xml",
        "src/main/docker/Dockerfile.jvm",
        "deployment.yml",
        "src/main/resources/application.properties",
        "src/main/java/com/acme/invoices/InvoiceResource.java",
        "src/main/java/com/acme/invoices/InvoiceRequest.java",
        "src/main/java/com/acme/invoices/InvoiceService.java",
        "src/main/java/com/acme/invoices/Invoice.java",
        "src/main/java/com/acme/invoices/OrderEventsConsumer.java",
    ],
    "dotnet-mini": [
        "Deals.Api.csproj",
        "Dockerfile",
        "deployment.yml",
        "appsettings.json",
        "Program.cs",
        "Controllers/DealsController.cs",
        "Validators/DealRequestValidator.cs",
        "Services/DealService.cs",
        "Messaging/DealRequestedConsumer.cs",
        "Data/DealsDbContext.cs",
        "Data/Deal.cs",
        "Data/Migrations/20260101000000_Init.cs",
    ],
    "fastapi-mini": [
        "pyproject.toml",
        "Dockerfile",
        "deployment.yml",
        "app/settings.py",
        "app/main.py",
        "app/schemas.py",
        "app/service.py",
        "app/consumer.py",
        "app/models.py",
        "alembic/versions/0001_init.py",
    ],
}


def test_fixture_files_present() -> None:
    missing = [
        f"{repo}/{relpath}"
        for repo, files in REQUIRED.items()
        for relpath in files
        if not (FIXTURES / repo / relpath).is_file()
    ]
    assert missing == []


LIVE_REQUIRED = (
    "Dockerfile",
    "db-manager/Dockerfile",
    "db-manager/entrypoint.sh",
    "expected/expected-flow-map.yaml",
    "expected/defects.md",
)


@pytest.mark.parametrize("recipe", list(RECIPES.values()), ids=lambda r: r.name)
def test_live_fixture_carries_everything_the_harness_needs(recipe: Any) -> None:
    missing = [rel for rel in LIVE_REQUIRED if not (recipe.fixture / rel).is_file()]
    assert missing == [], f"{recipe.name} is missing {missing}"
    manifests = list(recipe.fixture.glob("deployment*.yml"))
    assert manifests, f"{recipe.name} has no deployment manifest for discover.py to read"
    for entry_id in recipe.entries:
        slug = slug_for(entry_id)
        assert (recipe.fixture / "expected" / "traces" / f"{slug}.json").is_file(), slug
        feature = recipe.fixture / "expected" / "generated" / "features" / f"{slug}.feature"
        assert feature.is_file(), slug
    for number, (entry_id, source) in enumerate(recipe.rules_sources, start=1):
        slug = slug_for(entry_id)
        rows = recipe.fixture / "expected" / "rules" / f"{slug}-{number}.rows.csv"
        assert rows.is_file(), rows
        assert (recipe.fixture / source).is_file(), f"{recipe.name}: {source} does not exist"
    planted = recipe.fixture / "expected" / "generated" / recipe.planted_feature
    assert recipe.planted_scenario in planted.read_text(encoding="utf-8")
    assert set(recipe.marks) == set(recipe.entries), recipe.name
    # Every stub and seed file `flow_map.py mark` will pass through to the ledger must already
    # exist under expected/generated/: a fixture missing one still passes detect/discover/trace,
    # and only fails once a container job actually runs the generated feature against it.
    for entry_id, marks in recipe.marks.items():
        for flag, value in marks:
            path = recipe.fixture / "expected" / "generated" / value
            assert path.is_file(), f"{recipe.name}: {entry_id} names {flag} {value}, missing"
