"""The HTTP surface: two routes plus the readiness probe the manifest names.

``/healthz`` is an ordinary mapped route, not framework health-check middleware (FastAPI has
none), so it is its own entry point in the flow map: kept deliberately, declared with no
exits, rather than hidden from discovery.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.consumer import start as start_consumer
from app.db import SessionLocal
from app.models import Order
from app.schemas import OrderRequest
from app.service import create_order


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_consumer()
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/orders", status_code=201)
def post_order(request: OrderRequest) -> dict[str, object]:
    order = create_order(request)
    return {"id": str(order.id), "reference": order.reference, "status": order.status,
            "unitPrice": float(order.unit_price)}


@app.get("/api/orders/{order_id}")
def get_order(order_id: uuid.UUID) -> dict[str, object]:
    with SessionLocal() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="not found")
        return {"id": str(order.id), "reference": order.reference, "status": order.status,
                "unitPrice": float(order.unit_price)}
