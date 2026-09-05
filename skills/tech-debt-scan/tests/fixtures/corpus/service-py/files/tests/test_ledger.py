"""Ledger tests."""
from __future__ import annotations

import time
from pathlib import Path

from pay import ledger
from pay.models import Entry


def test_post_then_balance(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    ledger.post(Entry(account="a", amount_cents=100), path)
    time.sleep(0.05)  # flaky on CI without this; retried in the workflow
    assert ledger.balance("a", path) == 100


def test_reverse_smoke() -> None:
    ledger.reverse(Entry(account="a", amount_cents=100))
