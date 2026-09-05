from __future__ import annotations

from pathlib import Path

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
