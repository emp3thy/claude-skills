import os

DATABASE_URL = os.environ["DATABASE_URL"]
AMQP_URL = os.getenv("AMQP_URL", "amqp://localhost:5672")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:9020")
AUTH_MODE = os.getenv("AUTH_MODE", "jwt")
JWKS_URL = os.getenv("JWKS_URL", "")
