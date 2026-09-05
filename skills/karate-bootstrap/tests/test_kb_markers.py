from __future__ import annotations

import pytest
from kb_common import EXIT_UNSUPPORTED_STACK, KbError
from markers import (
    CHEAT_SHEET,
    KINDS,
    SOURCE_SUFFIXES,
    STACKS,
    markers_for,
    markers_of_kind,
    tokens_for,
)


def _matches(stack: str, kind: str, line: str) -> bool:
    return any(m.pattern.search(line) for m in markers_of_kind(stack, kind))


def test_every_stack_has_every_kind_and_metadata() -> None:
    for stack in STACKS:
        kinds = {m.kind for m in markers_for(stack)}
        assert kinds == set(KINDS), stack
        assert SOURCE_SUFFIXES[stack]
        assert CHEAT_SHEET[stack].startswith("reference/stack-")
        for kind in KINDS:
            assert tokens_for(stack, kind), (stack, kind)


def test_unknown_stack_raises_unsupported() -> None:
    with pytest.raises(KbError) as excinfo:
        markers_for("cobol")
    assert excinfo.value.exit_code == EXIT_UNSUPPORTED_STACK


@pytest.mark.parametrize(
    ("stack", "kind", "line"),
    [
        ("spring", "entry-http", "    @PostMapping"),
        ("spring", "entry-http", '    @GetMapping("/{id}")'),
        ("spring", "entry-amq", '    @JmsListener(destination = "shipment.requested")'),
        ("spring", "db-write", "        repository.save(shipment);"),
        ("spring", "amq-publish", '        jmsTemplate.convertAndSend("shipment.created", ev);'),
        ("spring", "http-out", "        Rate rate = restTemplate.getForObject(url, Rate.class);"),
        ("spring", "validation", "    @NotBlank"),
        ("quarkus", "entry-http", "    @POST"),
        ("quarkus", "entry-amq", '    @Incoming("order-completed")'),
        ("quarkus", "db-write", "        invoice.persist();"),
        ("quarkus", "amq-publish", "        emitter.send(InvoiceEvent.of(invoice));"),
        ("quarkus", "http-out", "    @RestClient"),
        ("quarkus", "validation", '    @DecimalMin("0.01")'),
        ("aspnetcore", "entry-http", "    [HttpPost]"),
        ("aspnetcore", "entry-http", '    [HttpGet("{id:guid}")]'),
        ("aspnetcore", "entry-http", 'app.MapGet("/ping", () => "pong");'),
        ("aspnetcore", "entry-amq", '        var queue = _session.GetQueue("deal.requested");'),
        ("aspnetcore", "db-write", "        await _db.SaveChangesAsync();"),
        ("aspnetcore", "db-write", "        _db.Deals.Add(deal);"),
        (
            "aspnetcore",
            "amq-publish",
            "        _producer.Send(_producer.CreateTextMessage(json));",
        ),
        (
            "aspnetcore",
            "http-out",
            '        var price = await _http.GetFromJsonAsync<Price>($"/prices/{p}");',
        ),
        (
            "aspnetcore",
            "validation",
            "        RuleFor(x => x.Volume).GreaterThan(0);",
        ),
        ("python", "entry-http", '@app.post("/api/orders", status_code=201)'),
        ("python", "entry-http", '@router.get("/items/{item_id}")'),
        ("python", "entry-amq", '        event.container.create_receiver(conn, "order.requested")'),
        ("python", "db-write", "        session.add(order)"),
        ("python", "amq-publish", "        sender.send(Message(body=payload))"),
        (
            "python",
            "http-out",
            '    stock = httpx.get(f"{settings.INVENTORY_URL}/stock/{sku}").json()',
        ),
        (
            "python",
            "validation",
            "    sku: str = Field(..., min_length=3, max_length=20)",
        ),
    ],
)
def test_marker_matches_fixture_line(stack: str, kind: str, line: str) -> None:
    assert _matches(stack, kind, line)


@pytest.mark.parametrize(
    ("stack", "kind", "line"),
    [
        ("spring", "entry-http", "    private final ShipmentService service;"),
        ("spring", "entry-http", '    @GetMappingCustom("/x")'),
        ("spring", "db-write", "        return repository.findById(id);"),
        (
            "aspnetcore",
            "db-write",
            "    public Task<Deal?> FindAsync(Guid id) => _db.Deals.FindAsync(id).AsTask();",
        ),
        ("python", "entry-http", "app = FastAPI()"),
        ("python", "db-write", "        order = session.get(Order, order_id)"),
    ],
)
def test_marker_ignores_non_matching_line(stack: str, kind: str, line: str) -> None:
    assert not _matches(stack, kind, line)


def test_spring_entry_http_captures_method_and_path() -> None:
    marker = markers_of_kind("spring", "entry-http")[0]
    match = marker.pattern.search('    @GetMapping("/{id}")')
    assert match is not None
    assert match.group(1) == "Get"
    assert match.group(2) == "/{id}"


def test_aspnetcore_entry_http_captures_attribute_route() -> None:
    marker = markers_of_kind("aspnetcore", "entry-http")[0]
    match = marker.pattern.search('    [HttpGet("{id:guid}")]')
    assert match is not None
    assert match.group(1) == "Get"
    assert match.group(2) == "{id:guid}"


def test_python_entry_http_captures_method_and_path() -> None:
    marker = markers_of_kind("python", "entry-http")[0]
    match = marker.pattern.search('@app.post("/api/orders", status_code=201)')
    assert match is not None
    assert match.group(1) == "post"
    assert match.group(2) == "/api/orders"
