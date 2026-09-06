"""Configuration read from the environment, one variable per connection part.

The database is configured as parts rather than a URL on purpose: it is the shape that
proves ``discover.assign_role`` classifies ``DB_HOST`` and its siblings as ``db`` and not as
a downstream service (Plan 4 Task 1).
"""
from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_port = os.environ.get("DB_PORT", "5432")
        self.db_name = os.environ.get("DB_NAME", "orders")
        self.db_user = os.environ.get("DB_USER", "app")
        self.db_password = os.environ.get("DB_PASSWORD", "app")
        self.amqp_url = os.environ.get("AMQP_URL", "amqp://localhost:5672")
        self.amqp_user = os.environ.get("AMQP_USER", "artemis")
        self.amqp_password = os.environ.get("AMQP_PASSWORD", "artemis")
        self.inventory_url = os.environ.get("INVENTORY_URL", "http://localhost:9090")
        self.auth_enabled = os.environ.get("AUTH_ENABLED", "true").lower() == "true"

    @property
    def database_url(self) -> str:
        return (f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}")


settings = Settings()
