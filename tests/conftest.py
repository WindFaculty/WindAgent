"""Root conftest — universal fixtures for the production test architecture (T1).

This file provides the only fixtures that are truly cross-tier:

* ``isolated_tmp_env`` — hermetic TMPDIR/TEMP/TMP per ADR 0006 A5
* ``deterministic_id`` / ``fake_clock`` — deterministic helpers
* ``isolated_db_url`` — hermetic DB URL (lightweight, no engine creation)

Tier-specific fixtures (DB engine, TestClient, process lifecycle) live in
``tests/<tier>/conftest.py`` so that importing ``tests.unit`` never starts a
database or an HTTP server — enforcing the tier boundaries at import time.
"""

from __future__ import annotations

import os
import uuid

import pytest

from tests.support.environment import isolated_tmp_env, FakeClock


@pytest.fixture
def isolated_db_url(tmp_path, monkeypatch) -> str:
    """Hermetic ``sqlite+aiosqlite`` URL per test — never touches repo-root DB."""
    monkeypatch.setenv(
        "WINDAGENT_DATABASE_URL",
        f"sqlite+aiosqlite:///{(tmp_path / f'test_{uuid.uuid4().hex[:8]}.db').as_posix()}",
    )
    isolated_tmp_env(monkeypatch, tmp_path)
    return os.environ["WINDAGENT_DATABASE_URL"]


@pytest.fixture
def fake_clock(monkeypatch) -> FakeClock:
    """Deterministic clock that can be advanced without real sleep."""
    from tests.support.environment import install_fake_clock

    return install_fake_clock(monkeypatch)


@pytest.fixture
def deterministic_id_factory():
    """Factory for short deterministic-looking IDs."""
    from tests.support.environment import deterministic_id

    return deterministic_id


# Ensure no test accidentally writes to the repo-root windagent.db
@pytest.fixture(autouse=False)
def assert_no_repo_root_db_writes_after(tmp_path):
    """Opt-in guard: use ``@pytest.mark.usefixtures('assert_no_repo_root_db_writes_after')``."""
    yield
    from tests.support.assertions import assert_no_repo_root_db_writes

    assert_no_repo_root_db_writes(tmp_path)
