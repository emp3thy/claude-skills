# ADR 0001: append-only ledger

Status: accepted, 2024-10-05.

We store ledger entries as JSON lines in `src/pay/ledger.py` and never rewrite
history; reversals are new entries.
