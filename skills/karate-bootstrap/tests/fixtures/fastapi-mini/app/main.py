from fastapi import FastAPI

from app import service
from app.schemas import OrderIn, OrderOut

app = FastAPI()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/orders", status_code=201)
def create_order(order: OrderIn) -> OrderOut:
    return service.create(order)


@app.get("/api/orders/{order_id}")
def get_order(order_id: int) -> OrderOut:
    return service.find(order_id)
