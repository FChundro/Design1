"""Command-line entry point: ``python -m free_claude_code.automations.composio``."""

import argparse
import sys

from loguru import logger

from .client import build_client, verify
from .config import load_settings
from .handlers import selected_automations
from .runner import run


def _cmd_run(_: argparse.Namespace) -> int:
    run()
    return 0


def _cmd_list(_: argparse.Namespace) -> int:
    settings = load_settings()
    for auto in selected_automations(settings):
        print(f"{auto.name:16} <- {auto.trigger_slug}")
    return 0


def _cmd_verify(_: argparse.Namespace) -> int:
    settings = load_settings()
    report = verify(build_client(settings), settings)
    if report.ok:
        print("All configured Composio slugs resolved.")
        return 0
    for slug in report.missing_actions:
        print(f"MISSING action:  {slug}", file=sys.stderr)
    for slug in report.missing_triggers:
        print(f"MISSING trigger: {slug}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="free_claude_code.automations.composio")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="arm triggers and dispatch events").set_defaults(
        func=_cmd_run
    )
    sub.add_parser("list", help="print enabled automations").set_defaults(
        func=_cmd_list
    )
    sub.add_parser(
        "verify", help="check configured slugs against the account"
    ).set_defaults(func=_cmd_verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # present a clean CLI error
        logger.error("{}", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
