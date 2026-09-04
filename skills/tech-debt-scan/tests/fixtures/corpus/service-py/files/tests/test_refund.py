"""Refund workflow tests."""
from __future__ import annotations

import pytest

from pay import refund as refund_mod
from pay.models import Refund


def test_validate_rejects_zero() -> None:
    with pytest.raises(ValueError):
        refund_mod.validate(Refund(order_id="o-1", amount_cents=0))


def test_audit_trail_format(refund: Refund) -> None:
    assert refund_mod.audit_trail(refund) == ["o-1:500:other"]


@pytest.mark.skip(reason="gateway stub not written yet")
def test_issue_calls_gateway() -> None:
    raise NotImplementedError
