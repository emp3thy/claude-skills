"""Order creation: price from inventory, a row, then an event.

The planted defect is the ``RuntimeError``: a quantity over 500 is a business rule nothing
maps to a client status, so FastAPI answers 500 instead of 422.
"""
from __future__ import annotations

import httpx

from app import messaging
from app.db import SessionLocal
from app.models import Order
from app.schemas import OrderRequest
from app.settings import settings


def create_order(request: OrderRequest) -> Order:
    if request.quantity > 500:
        raise RuntimeError("quantity exceeds the 500 limit")
    response = httpx.get(f"{settings.inventory_url}/stock/{request.sku}", timeout=10.0)
    unit_price = float(response.json().get("unitPrice", 0))
    order = Order(reference=request.reference, sku=request.sku, quantity=request.quantity,
                  status="PENDING", unit_price=unit_price)
    with SessionLocal() as session:
        session.add(order)
        session.commit()
        session.refresh(order)
    messaging.publish("order.created", {"id": str(order.id), "reference": order.reference,
                                        "status": order.status})
    return order
