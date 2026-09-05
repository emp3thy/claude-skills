import httpx
from fastapi import HTTPException
from proton import Message

from app import settings
from app.models import Order
from app.schemas import OrderIn, OrderOut
from app.db import SessionLocal
from app.messaging import sender


def create(order_in: OrderIn) -> OrderOut:
    stock = httpx.get(f"{settings.INVENTORY_URL}/stock/{order_in.sku}").json()
    if stock["available"] < order_in.quantity:
        raise HTTPException(status_code=409, detail="insufficient stock")
    if order_in.quantity > 50 and not stock.get("bulk_allowed"):
        raise HTTPException(status_code=400, detail="bulk orders need approval")
    with SessionLocal() as session:
        order = Order(sku=order_in.sku, quantity=order_in.quantity, status="NEW")
        session.add(order)
        session.commit()
        sender.send(Message(body={"order_id": order.id, "sku": order.sku}))
        return OrderOut(id=order.id, sku=order.sku, quantity=order.quantity, status=order.status)


def find(order_id: int) -> OrderOut:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        return OrderOut(id=order.id, sku=order.sku, quantity=order.quantity, status=order.status)
