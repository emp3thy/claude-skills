"""The kv command line: init and sync, and the old migrate."""
from __future__ import annotations

import argparse
import sys

from kv.config import home, token
from kv.store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kv", description="A small key-value store.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create the store directory")
    init.add_argument("--force", action="store_true",
                      help="delete an existing store first")

    sync = sub.add_parser("sync", help="write every stored key to the sync log")
    sync.add_argument("--dry-run", action="store_true",
                      help="print each key and write nothing")
    sync.add_argument("--legacy", action="store_true", help=argparse.SUPPRESS)
    sync.set_defaults(legacy=False)

    # deprecated: kept for stores written before 0.3
    sub.add_parser("migrate", help="move items of the old flat layout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(home())
    if args.command == "init":
        store.create(force=args.force)
    elif args.command == "sync":
        for key in store.keys():
            print(f"sync {key}")
            if not args.dry_run:
                store.push(key, token())
    else:
        store.migrate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
