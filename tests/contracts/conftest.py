"""Shared contract-test fixtures for the V3 API.

Phase 4: demo seeding is opt-in via ``WINDAGENT_PROFILE=demo``. Default
development/test/production startup never installs demo records. The legacy V3
sample-data contract tests (Phase 8–16) rely on the demo seed, so this shared
``client`` fixture explicitly enables the demo profile before entering the
lifespan. Unrelated tests that do not request this fixture are never forced
into demo mode.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from windagent_api.main import app


@pytest.fixture
def client(monkeypatch):
    """TestClient with the explicit demo profile enabled.

    Legacy V3 sample-data contract tests depend on the demo seed. The demo
    profile is opt-in (``WINDAGENT_PROFILE=demo``); default startup never seeds.
    """
    monkeypatch.setenv("WINDAGENT_PROFILE", "demo")
    with TestClient(app) as test_client:
        yield test_client
