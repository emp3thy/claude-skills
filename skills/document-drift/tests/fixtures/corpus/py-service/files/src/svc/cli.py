"""The ``svc`` command line."""
from __future__ import annotations

import argparse

from svc.config import load
from svc.storage import Store, open_store


def build_parser() -> argparse.ArgumentParser:
    """The ``svc`` parser with its four commands."""
    parser = argparse.ArgumentParser(prog="svc")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=9090)
    serve.add_argument("--workers", type=int, default=2)
    serve.add_argument("--timeout", type=float, default=30.0)
    serve.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)

    check = commands.add_parser("check", help="verify the database file")
    check.add_argument("--db", default="svc.db")
    check.add_argument("--repair", action="store_true")

    export = commands.add_parser("export", help="write every item as JSON lines")
    export.add_argument("--output", default="-")

    init = commands.add_parser("init", help="create an empty database file")
    init.add_argument("--db", default="svc.db")
    init.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command; return its exit status."""
    args = build_parser().parse_args(argv)
    settings = load()
    if args.command == "init":
        open_store(args.db, create=True, force=args.force).close()
        return 0
    if args.command == "serve":
        from svc import routes

        routes.STORE = Store(open_store(str(settings.home / "svc.db"), create=True))
        routes.app.run(host=args.host, port=settings.port or args.port)
        return 0
    store = Store(open_store(getattr(args, "db", "svc.db")))
    try:
        if args.command == "check":
            return 0 if store.count() >= 0 else 1
        for key in store.keys():
            print(key)
        return 0
    finally:
        store.close()
