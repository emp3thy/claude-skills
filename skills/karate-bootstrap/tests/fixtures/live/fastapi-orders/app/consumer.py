"""Background consumer for ``order.requested``: one row per message.

Runs a Proton reactive ``Container`` on its own daemon thread, started from FastAPI's
lifespan startup hook rather than at import time. ``Container.connect`` retries on its own
(reconnect is on by default), so a broker that is not reachable yet cannot block uvicorn from
binding its port the way a synchronous, eagerly-opened connection did for an earlier live
fixture's consumer.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from proton.handlers import MessagingHandler
from proton.reactor import Container

from app.db import SessionLocal
from app.models import Order
from app.settings import settings

DESTINATION = "order.requested"


class _OrderRequestedHandler(MessagingHandler):  # type: ignore[misc]
    def on_start(self, event: Any) -> None:
        conn = event.container.connect(
            settings.amqp_url, user=settings.amqp_user, password=settings.amqp_password)
        event.container.create_receiver(conn, "order.requested")

    def on_message(self, event: Any) -> None:
        body = json.loads(event.message.body)
        with SessionLocal() as session:
            session.add(Order(reference=body["reference"], sku=body.get("sku", "AAA-0001"),
                              quantity=int(body.get("quantity", 1)), status="QUEUED"))
            session.commit()


def _run() -> None:
    Container(_OrderRequestedHandler()).run()


def start() -> None:
    threading.Thread(target=_run, name="order-requested", daemon=True).start()
