#!/usr/bin/env python3
"""Verify a real database dialect and optionally initialize the test schema."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _run(
    *,
    database_url: str,
    required_dialect: str,
    initialize_schema: bool,
) -> dict[str, object]:
    engine = create_async_engine(database_url)
    try:
        dialect = engine.dialect.name
        if dialect != required_dialect:
            raise RuntimeError(
                f"Database dialect {dialect!r} != {required_dialect!r}"
            )
        async with engine.begin() as connection:
            version_query = (
                "SELECT version()"
                if dialect == "postgresql"
                else "SELECT sqlite_version()"
                if dialect == "sqlite"
                else "SELECT 1"
            )
            server_version = (
                await connection.execute(text(version_query))
            ).scalar_one()
            if initialize_schema:
                from windagent_storage.orm.models import BaseORM
                import windagent_storage.orm.v2_orchestration_models  # noqa: F401
                import windagent_storage.orm.v3_models  # noqa: F401

                await connection.run_sync(BaseORM.metadata.create_all)
        return {
            "dialect": dialect,
            "server_version": str(server_version),
            "schema_operation": (
                "create_all_test_schema" if initialize_schema else "none"
            ),
            "verdict": "PASS",
        }
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=os.environ.get("WINDAGENT_DATABASE_URL"),
    )
    parser.add_argument("--require-dialect", required=True)
    parser.add_argument("--initialize-schema", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or WINDAGENT_DATABASE_URL is required")

    try:
        report = asyncio.run(
            _run(
                database_url=args.database_url,
                required_dialect=args.require_dialect,
                initialize_schema=args.initialize_schema,
            )
        )
        exit_code = 0
    except Exception as exc:
        report = {
            "dialect": None,
            "server_version": None,
            "schema_operation": "not_run",
            "verdict": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
