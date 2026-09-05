from proton.handlers import MessagingHandler
from proton.reactor import Container

from app import settings
from app.db import SessionLocal
from app.models import Order


class OrderRequestedHandler(MessagingHandler):
    def on_start(self, event):
        conn = event.container.connect(settings.AMQP_URL)
        event.container.create_receiver(conn, "order.requested")

    def on_message(self, event):
        payload = event.message.body
        with SessionLocal() as session:
            order = session.get(Order, payload["order_id"])
            order.status = "REQUESTED"
            session.commit()


def run() -> None:
    Container(OrderRequestedHandler()).run()
