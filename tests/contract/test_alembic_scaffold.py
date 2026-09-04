"""Alembic scaffold is executable offline and rejects legacy URLs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

V2_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(
    *args: str,
    environment: str,
    database_url: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "WINDAGENT_ENVIRONMENT": environment}
    if database_url is None:
        env.pop("WINDAGENT_DATABASE_URL", None)
    else:
        env["WINDAGENT_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=V2_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_alembic_offline_upgrade_head_succeeds() -> None:
    """The chain starting at the clean 0001_v2_foundation renders offline."""
    result = _run_alembic("upgrade", "head", "--sql", environment="development")
    assert result.returncode == 0, result.stderr
    assert "0001" in result.stdout
    assert "0003" in result.stdout
    assert "0004" in result.stdout
    assert "platform_jobs" in result.stdout
    assert "platform_job_attempts" in result.stdout
    assert "trace_id" in result.stdout


@pytest.mark.parametrize("environment", ["development", "production"])
def test_alembic_refuses_sqlite_outside_tests(environment: str) -> None:
    result = _run_alembic(
        "current",
        environment=environment,
        database_url="sqlite+aiosqlite:///x.db",
    )
    assert result.returncode != 0
    assert "SQLite is not a supported V2 database" in result.stderr + result.stdout
