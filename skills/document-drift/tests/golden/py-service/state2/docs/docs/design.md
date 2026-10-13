# Design

## Storage

Every command opens the database through `storage.open_store`, which creates the file on first use.

Items live in one SQLite table, `items`, keyed by a string.

Expired rows are purged nightly by `Store.purge`.

## Durability

<!-- drift-unverified: 2nd notice, run 2026-01-09-bf13, block 368ee08c. NEEDS A HUMAN DECISION: name what this describes, add drift-ignore: <reason>, or rewrite it. The next drift run removes this block otherwise. -->
Writes go to disk before the reply returns, so a crash loses no acknowledged write.

## Upgrades

[The legacy helper](../src/svc/legacy.py) counts the free pages of databases
written by older releases.
