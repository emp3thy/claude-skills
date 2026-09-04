"""Ledger and refund records."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Entry:
    account: str
    amount_cents: int
    reason: str = ""


@dataclass
class Refund:
    order_id: str
    amount_cents: int
    reason_code: str = "other"
