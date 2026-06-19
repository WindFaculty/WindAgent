"""Shared fixtures for the backend test suite.

Each test gets:
  - An isolated in-memory SQLite DB (or a temp file DB for the WS
    real-server fixture, where the engine must be reachable across an
    ASGI boundary inside the same process).
  - A TestClient whose lifespan has fired the FastAPI startup.
  - Direct handles on the singletons in app.state for unit tests.

Phase 3: force WINDAGENT_MOCK_GUI=1 so pyautogui is never imported
during tests. The lifespan will install a MockGuiAdapter on
app.state.gui.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure `apps/backend` is on sys.path so `from services.X import Y` works
# regardless of where pytest is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Phase 3: force MockGuiAdapter for every test session.
os.environ["WINDAGENT_MOCK_GUI"] = "1"

# Phase 4: force MockModelClient for every test session so the suite does
# not depend on a running Ollama daemon.
os.environ["WINDAGENT_MODEL_BACKEND"] = "mock"

# Force every lifespan in this test session to use a temp file DB.
_DB_FD, _DB_PATH = tempfile.mkstemp(prefix="windagent-test-", suffix=".db")
os.close(_DB_FD)
os.environ["WINDAGENT_DB_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"


@pytest.fixture
def lifespan_client():
    """A TestClient whose __enter__ has fired the FastAPI lifespan.

    Also resets the SQLite DB before yielding so tests don't see each
    other's data.
    """
    from fastapi.testclient import TestClient
    from main import app
    from db.models import Base
    import sqlalchemy.ext.asyncio as sa_asyncio

    async def _reset_db() -> None:
        engine = sa_asyncio.create_async_engine(os.environ["WINDAGENT_DB_URL"])
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    import anyio
    anyio.run(_reset_db)

    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(lifespan_client):
    return lifespan_client


@pytest.fixture
def app_state(lifespan_client):
    return lifespan_client.app.state


@pytest.fixture
def event_bus(app_state):
    return app_state.event_bus


@pytest.fixture
def session_service(app_state):
    return app_state.session_service


@pytest.fixture
def workflow_service(app_state):
    return app_state.workflow_service


@pytest.fixture
def db(app_state):
    return app_state.db


@pytest.fixture
def gui(app_state):
    """The MockGuiAdapter installed by the lifespan when WINDAGENT_MOCK_GUI=1."""
    return app_state.gui


@pytest.fixture
def tool_executor(app_state):
    return app_state.tool_executor


@pytest.fixture
def planner_service(app_state):
    return app_state.planner_service


@pytest.fixture
def model_client(app_state):
    return app_state.model_client


@pytest.fixture
def permission_service(app_state):
    return app_state.permission_service


@pytest.fixture
def grounding_service(app_state):
    return app_state.grounding_service
