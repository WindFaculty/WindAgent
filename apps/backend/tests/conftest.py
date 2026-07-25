"""
Shared fixtures for the backend compatibility test suite (Phase 27 Evacuation).
Delegates to windagent_api.main:app and canonical V2 composition root.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Force MockGuiAdapter for every test session
os.environ["WINDAGENT_MOCK_GUI"] = "1"
os.environ["WINDAGENT_MODEL_BACKEND"] = "mock"
os.environ["WINDAGENT_HERMES_ENABLED"] = "false"

_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="windagent-test-", suffix=".db")
os.close(_DB_FD)
os.environ["WINDAGENT_DB_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}?timeout=30"


@pytest.fixture
def lifespan_client():
    from fastapi.testclient import TestClient
    from windagent_api.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(lifespan_client):
    return lifespan_client


@pytest.fixture
def app_state(lifespan_client):
    return lifespan_client.app.state
