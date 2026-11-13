"""Command line: ``python -m kc_seal {serve,seed,hash-token}``."""

import argparse
import getpass
import hashlib
import sys

from .audit import AuditLog
from .config import Settings
from .seed import seed
from .store import RecordStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kc_seal")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the API (local prototype only)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    sub.add_parser("seed", help="load the clearly labelled TEST records")
    sub.add_parser(
        "hash-token", help="print SHA-256 of an admin token read from stdin/prompt"
    )
    args = parser.parse_args(argv)

    if args.cmd == "hash-token":
        token = (
            getpass.getpass("Admin token: ")
            if sys.stdin.isatty()
            else sys.stdin.readline().strip()
        )
        print(hashlib.sha256(token.encode()).hexdigest())
        return 0

    settings = Settings.from_env()
    if args.cmd == "seed":
        created = seed(
            RecordStore(settings.data_dir / "records.json"),
            AuditLog(settings.data_dir / "audit" / "audit.jsonl"),
        )
        print("created TEST records:", ", ".join(created) or "(already present)")
        return 0

    import uvicorn

    from .api import create_app

    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port,
        proxy_headers=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
