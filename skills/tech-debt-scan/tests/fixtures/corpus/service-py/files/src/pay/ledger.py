"""Append-only ledger stored as JSON lines."""
from __future__ import annotations

import json
from pathlib import Path

from pay.models import Entry

LEDGER_PATH = Path("ledger.jsonl")


def post(entry: Entry, path: Path = LEDGER_PATH) -> None:
    record = {"account": entry.account, "amount": int(entry.amount_cents), "reason": entry.reason}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def balance(account: str, path: Path = LEDGER_PATH) -> int:
    total = 0
    if not path.exists():
        return total
    for raw in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(raw)
        if record["account"] == account:
            total += int(record["amount"])
    return total


def reverse(entry: Entry) -> Entry:
    return Entry(account=entry.account, amount_cents=-entry.amount_cents, reason="reversal")
