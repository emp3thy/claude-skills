"""The HTTP routes."""
from __future__ import annotations

from flask import Flask, abort, jsonify

from svc._internal import _helper

app = Flask("svc")
STORE = None


@app.get("/health")
def health():
    """Liveness probe."""
    return jsonify(status="ok")


@app.get("/items/<key>")
def get_item(key: str):
    """One stored value, or 404."""
    value = STORE.get(_helper(key)) if STORE is not None else None
    if value is None:
        abort(404)
    return value


@app.get("/stats")
def stats():
    """How many items are stored."""
    return jsonify(items=len(STORE.keys()) if STORE is not None else 0)
