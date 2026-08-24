"""Shared contract-test fixtures for the V3 API.

Phase 4: demo seeding is opt-in via ``WINDAGENT_PROFILE=demo``. Default
development/test/production startup never installs demo records. The legacy V3
sample-data contract tests (Phase 8–16) rely on the demo seed, so this shared
``client`` fixture explicitly enables the demo profile before entering the
lifespan. Unrelated tests that do not request this fixture are never forced
into demo mode.

P1.0 truth repair: each test runs against a FRESH temporary database. Every
TestClient lifespan re-applies the idempotent demo seed, so a test always sees
pristine canonical state instead of mutations leaked by other suites through
the shared repo-root ``windagent.db`` file.
"""

from __future__ import annotations

import pytest

from tests.support.api import isolated_api_client


@pytest.fixture
def client(monkeypatch, tmp_path):
    """TestClient with the explicit demo profile enabled on an isolated temp DB.

    Legacy V3 sample-data contract tests depend on the demo seed. The demo
    profile is opt-in (``WINDAGENT_PROFILE=demo``); default startup never seeds.
    ``WINDAGENT_DATABASE_URL`` pins the lifespan container to a per-test SQLite
    file so contract state never leaks between tests or into local dev data.

    Delegates to ``tests.support.api.isolated_api_client`` (T1) so the
    hermetic semantics stay in one place.
    """
    yield from isolated_api_client(monkeypatch, tmp_path, profile="demo")


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    """Alias for ``client`` — preferred name for new contract tests."""
    yield from isolated_api_client(monkeypatch, tmp_path, profile="demo")


@pytest.fixture
def no_demo_client(monkeypatch, tmp_path):
    """TestClient without demo seeding — for contract tests that must not see demo data."""
    yield from isolated_api_client(monkeypatch, tmp_path, profile=None)
