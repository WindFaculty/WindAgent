"""WindAgent V2 CLI entrypoint.

Phase 1 ships a single ``info`` command that reports the resolved runtime
configuration without connecting to anything.  Migration and parity commands
are added in later phases.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from windagent import __version__ as WINDAGENT_VERSION
from windagent.platform.configuration.settings import (
    Settings,
    SQLiteNotAllowedError,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="windagent", description="WindAgent V2 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="print version and resolved configuration")
    return parser


def cmd_info() -> int:
    try:
        settings = Settings()
    except SQLiteNotAllowedError as exc:
        print(f"STARTUP_ERROR: {exc}", file=sys.stderr)
        return 2
    scheme = settings.database_url.split("://", 1)[0]
    print(f"windagent {WINDAGENT_VERSION}")
    print(f"environment={settings.environment} database_driver={scheme}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "info":
        return cmd_info()
    parser.error(f"unknown command: {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
