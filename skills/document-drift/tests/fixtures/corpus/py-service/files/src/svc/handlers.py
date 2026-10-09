"""URL rules and their views."""
from __future__ import annotations

from flask import Flask, jsonify


def register(app: Flask) -> None:
    app.add_url_rule("/health", "health", lambda: jsonify(status="ok"))
