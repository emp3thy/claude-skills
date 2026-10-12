# Design

## Storage

Every command opens the database through `storage.connect`, which creates the file on first use.

Items live in one SQLite table, `items`, keyed by a string.

Expired rows are purged nightly by `Store.purge`.

## Durability

<!-- drift-unverified: 1st notice, run 2026-01-02-3f03, block 368ee08c. This describes the code but names nothing in it. Name what it describes, or add drift-ignore: <reason>. -->
Writes go to disk before the reply returns, so a crash loses no acknowledged write.
