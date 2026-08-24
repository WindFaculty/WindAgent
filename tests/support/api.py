"""API test-client helpers.

Centralises the ``WINDAGENT_PROFILE=demo`` + isolated DB pattern that was
previously duplicated between ``tests/contracts/conftest.py`` and ad-hoc
``unit/api`` tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from fastapi.testclient import TestClient


def isolated_api_client(
    monkeypatch,
    tmp_path: Path,
    *,
    profile: str | None = "demo",
    db_filename: str = "contract.db",
):
    """Create a ``TestClient`` with hermetic DB and optional demo profile.

    Mirrors ``tests/contracts/conftest.py::client`` semantics:

    * ``WINDAGENT_PROFILE=demo`` is set explicitly when ``profile`` is not None.
      Default ``development/test/production`` startup never seeds demo data.
    * ``WINDAGENT_DATABASE_URL`` points at a fresh file under ``tmp_path`` so
      the lifespan seed does not leak through ``windagent.db`` on disk.
    """
    if profile is not None:
        monkeypatch.setenv("WINDAGENT_PROFILE", profile)
    else:
        monkeypatch.delenv("WINDAGENT_PROFILE", raising=False)
    monkeypatch.setenv(
        "WINDAGENT_DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / db_filename).as_posix()}",
    )
    # Ensure writable temp dir per ADR 0006 A5
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    if os.name == "nt":
        monkeypatch.setenv("TMP", str(tmp_path))

    from windagent_api.main import app

    with TestClient(app) as client:
        yield client


def demo_client(monkeypatch, tmp_path: Path) -> Generator[TestClient, None, None]:
    """Shortcut for the legacy demo-seeded contract client."""
    yield from isolated_api_client(monkeypatch, tmp_path, profile="demo")


def no_demo_client(monkeypatch, tmp_path: Path) -> Generator[TestClient, None, None]:
    """Client without demo seeding — for true unit isolation."""
    yield from isolated_api_client(monkeypatch, tmp_path, profile=None)
