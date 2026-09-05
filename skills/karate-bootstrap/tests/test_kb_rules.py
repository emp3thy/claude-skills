from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pytest
from detect import main as detect_main
from discover import main as discover_main
from flow_map import find_entry, load_ledger, merge_entry, save_ledger
from kb_common import KbError
from rules import (
    CSV_HEADER,
    add_rows,
    extract_bean_validation,
    extract_data_annotations,
    extract_fluent_validation,
    extract_for_entry,
    extract_pydantic,
    main,
    mark_scanned,
    slug_for,
    write_candidates,
)

FIXTURES = Path(__file__).parent / "fixtures"


def rows_by_field(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["field"], r["mutation"]): r for r in rows}


def test_slug_for() -> None:
    assert slug_for("POST /api/deals") == "post-api-deals"
    assert slug_for("GET /api/orders/{order_id}") == "get-api-orders-order-id"
    assert slug_for("amq deal.requested") == "amq-deal-requested"


def test_extract_bean_validation_spring_request() -> None:
    src = "src/main/java/com/acme/shipments/ShipmentRequest.java"
    text = (FIXTURES / "spring-mini" / src).read_text(encoding="utf-8")
    rows = extract_bean_validation(text, src)
    got = rows_by_field(rows)
    assert ("reference", "missing") in got and ("reference", "empty") in got
    assert got[("reference", "too_long")]["value"] == "51"
    assert ("weightKg", "missing") in got
    assert got[("weightKg", "out_of_range")]["value"] == "0"
    assert got[("countryCode", "invalid_format")]["value"] == "!!"
    assert got[("destination", "too_short")]["value"] == "2"
    assert got[("destination", "too_long")]["value"] == "121"
    assert all(r["expected_status"] == "400" for r in rows)
    assert all(r["source"].startswith(src + ":") for r in rows)
    # reference: missing, empty, too_long (3); weightKg: missing, out_of_range (2);
    # countryCode: missing, invalid_format (2); destination: too_short, too_long (2) = 9
    assert len(rows) == 9


def test_extract_bean_validation_decimal_min() -> None:
    src = "src/main/java/com/acme/invoices/InvoiceRequest.java"
    text = (FIXTURES / "quarkus-mini" / src).read_text(encoding="utf-8")
    rows = extract_bean_validation(text, src)
    got = rows_by_field(rows)
    assert got[("amount", "out_of_range")]["value"] == "0"
    assert got[("currency", "too_long")]["value"] == "4"
    # orderId: missing (1); amount: missing, out_of_range (2);
    # currency: missing, empty, too_long (3) = 6
    assert len(rows) == 6


def test_extract_bean_validation_ignores_class_level_annotations() -> None:
    text = (
        "@Entity\n@NotNull\npublic class Req {\n"
        "    private String reference;\n\n    @NotBlank\n    private String name;\n}\n"
    )
    rows = extract_bean_validation(text, "Req.java")
    assert [(r["field"], r["mutation"]) for r in rows] == [("name", "missing"), ("name", "empty")]


def test_extract_fluent_validation() -> None:
    src = "Validators/DealRequestValidator.cs"
    text = (FIXTURES / "dotnet-mini" / src).read_text(encoding="utf-8")
    rows = extract_fluent_validation(text, src)
    got = rows_by_field(rows)
    assert ("CounterpartyId", "missing") in got and ("CounterpartyId", "empty") in got
    assert got[("Volume", "out_of_range")]["value"] == "0"
    assert got[("Product", "too_long")]["value"] == "21"
    assert got[("ExternalId", "invalid_format")]["value"] == "!!"
    # CounterpartyId: missing, empty (2); Volume: out_of_range (1);
    # Product: missing, empty, too_long (3); ExternalId: invalid_format (1) = 7
    assert len(rows) == 7


def test_extract_data_annotations() -> None:
    text = (
        "public class Req\n{\n    [Required]\n    [StringLength(10, MinimumLength = 2)]\n"
        "    public string Name { get; set; }\n    [Range(1, 5)]\n"
        "    public int Stars { get; set; }\n"
        "    [EmailAddress]\n    public string Email { get; set; }\n}\n"
    )
    rows = extract_data_annotations(text, "Req.cs")
    got = rows_by_field(rows)
    assert ("Name", "missing") in got
    assert got[("Name", "too_long")]["value"] == "11"
    assert got[("Name", "too_short")]["value"] == "1"
    assert got[("Stars", "out_of_range")]["value"] == "0"
    assert got[("Email", "invalid_format")]["value"] == "!!"
    # Name: missing, too_long, too_short (3); Stars: out_of_range (1);
    # Email: invalid_format (1) = 5
    assert len(rows) == 5


def test_extract_data_annotations_ignores_attributes_on_non_properties() -> None:
    text = (
        "public class Req\n{\n    [Required]\n    public Req() { }\n\n"
        "    public string Sku { get; set; }\n    [Required]\n"
        "    public string Name { get; set; }\n}\n"
    )
    rows = extract_data_annotations(text, "Req.cs")
    assert [(r["field"], r["mutation"]) for r in rows] == [("Name", "missing")]


def test_extract_pydantic() -> None:
    src = "app/schemas.py"
    rows = extract_pydantic((FIXTURES / "fastapi-mini" / src).read_text(encoding="utf-8"), src)
    got = rows_by_field(rows)
    assert ("sku", "missing") in got
    assert got[("sku", "too_short")]["value"] == "2"
    assert got[("sku", "too_long")]["value"] == "21"
    assert got[("quantity", "out_of_range")]["value"] == "0"
    assert got[("customer_email", "invalid_format")]["value"] == "!!"
    assert ("note", "missing") not in got  # optional with default
    assert all(r["expected_status"] == "422" for r in rows)
    assert all(r["field"] not in {"id", "status"} for r in rows)  # OrderOut is not a request
    # sku: missing, too_short, too_long (3); quantity: missing, out_of_range (2);
    # customer_email: missing, invalid_format (2) = 7
    assert len(rows) == 7


@pytest.fixture()
def dotnet_ledger(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = FIXTURES / "dotnet-mini"
    stack = tmp_path / "stack.json"
    ledger_path = tmp_path / "flow-map.yaml"
    assert detect_main([str(root), "--out", str(stack), "--skip-toolchain"]) == 0
    assert discover_main([str(root), "--stack", str(stack), "--out-env",
                          str(tmp_path / "env-map.json"), "--out-ledger", str(ledger_path)]) == 0
    ledger = load_ledger(ledger_path)
    merge_entry(ledger, {
        "id": "POST /api/deals", "unresolved": [],
        "request": {"content_type": "application/json", "schema_ref": "Data/Deal.cs"},
        "responses": [{"status": 201, "when": "happy"}, {"status": 400, "when": "validation",
                                                          "rules": True}],
        "exits": [{"kind": "db-write", "table": "deals", "op": "insert",
                   "via": "Services/DealService.cs:27"}],
        "rules": {"sources": [{"file": "Validators/DealRequestValidator.cs", "scanned": False}]},
    })
    save_ledger(ledger_path, ledger)
    return ledger_path, ledger


def test_extract_for_entry_uses_sources_and_writes_candidates(
    dotnet_ledger: tuple[Path, dict[str, Any]], tmp_path: Path
) -> None:
    _, ledger = dotnet_ledger
    entry = find_entry(ledger, "POST /api/deals")
    rows = extract_for_entry(FIXTURES / "dotnet-mini", "aspnetcore", entry)
    assert {r["field"] for r in rows} == {"CounterpartyId", "Volume", "Product", "ExternalId"}
    out_dir = tmp_path / "karate-tests"
    path = write_candidates(out_dir, entry, rows)
    assert path == out_dir / "rules" / "post-api-deals.candidates.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == CSV_HEADER
        assert all(row["rule_id"] == "" for row in reader)


def test_add_rows_appends_dedupes_and_updates_ledger(dotnet_ledger: tuple[Path, dict[str, Any]],
                                                     tmp_path: Path) -> None:
    ledger_path, ledger = dotnet_ledger
    out_dir = tmp_path / "karate-tests"
    incoming = tmp_path / "rows.csv"
    incoming.write_text(
        ",".join(CSV_HEADER) + "\n"
        ",CounterpartyId,missing,,400,VALIDATION,CounterpartyId is required,"
        "Validators/DealRequestValidator.cs:9\n"
        ",Volume,out_of_range,0,400,VALIDATION,Volume must be greater than 0,"
        "Validators/DealRequestValidator.cs:10\n",
        encoding="utf-8",
    )
    assert add_rows(out_dir, ledger, "POST /api/deals", incoming) == 2
    assert add_rows(out_dir, ledger, "POST /api/deals", incoming) == 2  # idempotent
    more = tmp_path / "more.csv"
    more.write_text(
        ",".join(CSV_HEADER) + "\n"
        ",Volume,cross_field,gt:DeskLimit,400,VALIDATION,volume exceeds desk limit,"
        "Services/DealService.cs:21\n",
        encoding="utf-8",
    )
    assert add_rows(out_dir, ledger, "POST /api/deals", more) == 3
    entry = find_entry(ledger, "POST /api/deals")
    assert entry["rules"]["file"] == "rules/post-api-deals.csv"
    assert entry["rules"]["count"] == 3
    with (out_dir / "rules" / "post-api-deals.csv").open(encoding="utf-8", newline="") as handle:
        ids = [row["rule_id"] for row in csv.DictReader(handle)]
    assert ids == ["R001", "R002", "R003"]


def test_add_rows_rejects_bad_header_and_mutation(dotnet_ledger: tuple[Path, dict[str, Any]],
                                                  tmp_path: Path) -> None:
    _, ledger = dotnet_ledger
    bad_header = tmp_path / "bad.csv"
    bad_header.write_text("field,mutation\nx,missing\n", encoding="utf-8")
    with pytest.raises(KbError, match="header"):
        add_rows(tmp_path, ledger, "POST /api/deals", bad_header)
    bad_mutation = tmp_path / "bad2.csv"
    bad_mutation.write_text(",".join(CSV_HEADER) + "\n,x,explode,,400,,,a:1\n", encoding="utf-8")
    with pytest.raises(KbError, match="mutation"):
        add_rows(tmp_path, ledger, "POST /api/deals", bad_mutation)


def test_mark_scanned(dotnet_ledger: tuple[Path, dict[str, Any]]) -> None:
    _, ledger = dotnet_ledger
    mark_scanned(ledger, "POST /api/deals", "Validators/DealRequestValidator.cs")
    assert find_entry(ledger, "POST /api/deals")["rules"]["sources"][0]["scanned"] is True
    mark_scanned(ledger, "POST /api/deals", "Services/DealService.cs")
    files = [s["file"] for s in find_entry(ledger, "POST /api/deals")["rules"]["sources"]]
    assert files == ["Validators/DealRequestValidator.cs", "Services/DealService.cs"]


def test_cli_extract_add_mark(dotnet_ledger: tuple[Path, dict[str, Any]], tmp_path: Path,
                              capsys: pytest.CaptureFixture[str]) -> None:
    ledger_path, _ = dotnet_ledger
    out_dir = tmp_path / "karate-tests"
    assert main(["extract", str(FIXTURES / "dotnet-mini"), "--ledger", str(ledger_path),
                 "--out-dir", str(out_dir)]) == 0
    assert "POST /api/deals: 7 candidate rows" in capsys.readouterr().out
    candidates = out_dir / "rules" / "post-api-deals.candidates.csv"
    assert candidates.is_file()
    assert main(["add", "POST /api/deals", str(candidates), "--ledger", str(ledger_path),
                 "--out-dir", str(out_dir)]) == 0
    assert main(["mark-scanned", "POST /api/deals", "Validators/DealRequestValidator.cs",
                 "--ledger", str(ledger_path)]) == 0
    entry = find_entry(load_ledger(ledger_path), "POST /api/deals")
    assert entry["rules"]["count"] == 7
    assert entry["rules"]["sources"][0]["scanned"] is True
