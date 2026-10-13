# Design

## Storage

Every command opens the database through `storage.connect`, which creates the file on first use.

Items live in one SQLite table, `items`, keyed by a string.

Expired rows are purged nightly.

## Durability

Writes go to disk before the reply returns, so a crash loses no acknowledged write.

## Upgrades

[The legacy helper](../src/svc/legacy.py) counts the free pages of databases
written by older releases.
