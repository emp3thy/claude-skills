"""AMQP 1.0 publish over Qpid Proton's blocking client.

The connection opens lazily, on the first publish, rather than at import time: a broker that
is not reachable yet must not be able to block the application from starting (the same
startup-ordering trap an earlier live fixture hit with an eager broker connection in a
service constructor). ``app.consumer`` uses the reactive API instead, for the same reason.

The body is sent as a JSON-encoded string, not a native AMQP map: the harness's own ``Jms``
helper (Qpid JMS) maps an AMQP message whose body is an amqp-value string onto a JMS
``TextMessage`` and JSON-decodes it, the same wire shape an earlier live fixture's Spring
``MessageConverter`` was added to match.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from proton import Message
from proton.utils import BlockingConnection

from app.settings import settings

_lock = threading.Lock()
_connection: BlockingConnection | None = None


def _connection_for_publish() -> BlockingConnection:
    global _connection
    with _lock:
        if _connection is None:
            _connection = BlockingConnection(
                settings.amqp_url, user=settings.amqp_user, password=settings.amqp_password)
        return _connection


def publish(destination: str, body: dict[str, Any]) -> None:
    sender = _connection_for_publish().create_sender(destination)
    sender.send(Message(body=json.dumps(body)))
    sender.close()
