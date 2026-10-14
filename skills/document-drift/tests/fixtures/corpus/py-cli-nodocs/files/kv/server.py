"""The HTTP view of the store."""
from __future__ import annotations

from flask import Flask, abort

from kv.config import home
from kv.store import Store

app = Flask(__name__)


@app.route("/items/<key>")
def get_item(key: str) -> bytes:
    """The value stored under ``key``, or 404."""
    value = Store(home()).get(key)
    if value is None:
        abort(404)
    return value
