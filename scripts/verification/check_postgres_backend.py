#!/usr/bin/env python3
"""PostgreSQL backend attestation for certification jobs (T7).

Fail-closed: exits non-zero unless ``WINDAGENT_TEST_POSTGRES_URL`` is set,
points at a live PostgreSQL server, and the server reports the expected
major version. Writes a JSON attestation recording ``database_backend``
and ``postgres_version`` so certification evidence can prove real
PostgreSQL execution (no SQLite fallback, no silent skip).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

EXPECTED_MAJOR = 16


def _asyncpg_dsn(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _check(url: str) -> dict:
    import asyncpg

    async def _run() -> dict:
        conn = await asyncpg.connect(_asyncpg_dsn(url), timeout=10)
        try:
            row = await conn.fetchrow("SELECT version() AS version")
        finally:
            await conn.close()
        full = str(row["version"])
        if not full.lower().startswith("postgresql"):
            raise RuntimeError(f"backend is not PostgreSQL: {full!r}")
        major = full.split()[1].split(".")[0]
        return {
            "database_backend": "postgresql",
            "postgres_version": major,
            "server_version_full": full,
        }

    return asyncio.run(_run())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="attestation JSON path")
    args = parser.parse_args()

    url = __import__("os").environ.get("WINDAGENT_TEST_POSTGRES_URL", "").strip()
    if not url:
        print(
            "FAIL: WINDAGENT_TEST_POSTGRES_URL is not set — "
            "PostgreSQL certification must run against real PostgreSQL",
            file=sys.stderr,
        )
        return 1

    try:
        attestation = _check(url)
    except Exception as exc:  # noqa: BLE001 — fail closed on any backend error
        print(f"FAIL: PostgreSQL backend attestation error: {exc}", file=sys.stderr)
        return 1

    if attestation["postgres_version"] != str(EXPECTED_MAJOR):
        print(
            f"FAIL: expected PostgreSQL {EXPECTED_MAJOR}, got "
            f"{attestation['postgres_version']} ({attestation['server_version_full']})",
            file=sys.stderr,
        )
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
    print(
        f"OK: database_backend={attestation['database_backend']} "
        f"postgres_version={attestation['postgres_version']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
