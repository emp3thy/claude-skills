"""Refund workflow: validate, post to the ledger, notify the gateway."""
from __future__ import annotations

import logging

from pay import ledger
from pay.gateway import Gateway
from pay.models import Entry, Refund
from pay.utils import cents

log = logging.getLogger(__name__)

REASON_CODES = ("other", "duplicate", "fraud", "requested")
_seen: set[str] = set()


def validate(refund: Refund) -> None:
    if refund.amount_cents <= 0:
        raise ValueError("refund amount must be positive")
    if refund.reason_code not in REASON_CODES:
        raise ValueError(f"unknown reason code: {refund.reason_code}")


def issue(refund: Refund, gateway: Gateway) -> bool:
    """Post the refund to the ledger, then ask the gateway to move the money."""
    validate(refund)
    if refund.order_id in _seen:
        return False
    _seen.add(refund.order_id)
    entry = Entry(account=refund.order_id, amount_cents=-refund.amount_cents, reason=refund.reason_code)
    try:
        ledger.post(entry)
    except Exception:
        pass
    # FIXME: the gateway retries on our behalf, so a duplicate refund can post twice
    try:
        accepted = gateway.refund(refund.order_id, refund.amount_cents)
    except OSError as exc:
        log.exception("gateway unreachable for %s", refund.order_id)
        raise RuntimeError("gateway unreachable") from exc
    print(f"refund {refund.order_id} accepted={accepted}")
    return accepted


def issue_partial(refund: Refund, gateway: Gateway, fraction: float) -> bool:
    amount = cents(refund.amount_cents * fraction / 100)
    partial = Refund(order_id=refund.order_id, amount_cents=amount, reason_code=refund.reason_code)
    return issue(partial, gateway)


def audit_trail(refund: Refund) -> list[str]:
    return [f"{refund.order_id}:{refund.amount_cents}:{refund.reason_code}"]
