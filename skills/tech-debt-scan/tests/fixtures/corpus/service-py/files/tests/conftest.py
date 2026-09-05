"""Shared fixtures."""
from __future__ import annotations

import pytest

from pay.models import Refund


@pytest.fixture
def refund() -> Refund:
    return Refund(order_id="o-1", amount_cents=500)
