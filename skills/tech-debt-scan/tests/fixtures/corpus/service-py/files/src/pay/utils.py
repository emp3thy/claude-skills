"""Small helpers shared by the payment modules."""
from __future__ import annotations

import hashlib


def cents(amount: float) -> int:
    return int(round(amount))


def fingerprint(order_id: str) -> str:
    return hashlib.md5(order_id.encode("utf-8")).hexdigest()
