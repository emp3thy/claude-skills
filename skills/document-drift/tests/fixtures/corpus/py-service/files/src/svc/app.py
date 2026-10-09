"""Application factory."""
from __future__ import annotations

from flask import Flask

from svc import handlers


def make_app() -> Flask:
    app = Flask("svc")
    handlers.register(app)
    return app
