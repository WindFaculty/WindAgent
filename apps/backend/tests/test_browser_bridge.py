"""Tests for the Browser Bridge (Phase 6)."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient

from db.database import Database
from services.browser_service import BrowserService
from services.event_bus import EventBus
from main import app


@pytest.fixture
def temp_artifacts_root(tmp_path) -> Path:
    return tmp_path / "artifacts"


@pytest.mark.asyncio
async def test_browser_service_fallback_rendering(temp_artifacts_root):
    bus = EventBus()
    svc = BrowserService(bus, temp_artifacts_root)
    await svc.start()
    
    session_id = str(uuid4())
    
    # Get or create initial state
    state = await svc.get_or_create_browser(session_id)
    assert state["session_id"] == session_id
    assert state["url"] == "about:blank"
    assert os.path.exists(state["screenshot_path"])
    
    # Test navigation
    nav_state = await svc.navigate(session_id, "https://google.com")
    assert nav_state["url"] == "https://google.com"
    assert "google.com" in nav_state["title"].lower()
    assert os.path.exists(nav_state["screenshot_path"])
    
    # Test click
    click_state = await svc.click(session_id, x=100, y=200)
    assert click_state["url"] == "https://google.com"
    
    # Test type
    type_state = await svc.type_text(session_id, "hello input", selector="input")
    assert type_state["url"] == "https://google.com"
    
    # Test control toggle
    control_state = await svc.set_control(session_id, "user")
    assert control_state["controlled_by"] == "user"
    
    await svc.close_all()


def test_browser_api_routes(db):
    from unittest.mock import MagicMock
    
    # Mock browser service
    mock_service = MagicMock()
    mock_service.get_state.return_value = {
        "session_id": "test-session",
        "url": "https://example.com",
        "title": "Example",
        "loading": False,
        "screenshot_path": "test_screenshot.png",
        "controlled_by": "agent",
        "console_logs": [],
        "errors": [],
    }
    
    async def mock_get_or_create(session_id):
        return mock_service.get_state(session_id)
    mock_service.get_or_create_browser = mock_get_or_create

    async def mock_navigate(session_id, url):
        return {"session_id": session_id, "url": url, "title": "Navigated"}
    mock_service.navigate = mock_navigate

    async def mock_click(session_id, selector, x, y):
        return {"session_id": session_id, "url": "https://example.com", "title": "Clicked"}
    mock_service.click = mock_click

    async def mock_type(session_id, text, selector):
        return {"session_id": session_id, "url": "https://example.com", "title": "Typed"}
    mock_service.type_text = mock_type

    async def mock_control(session_id, mode):
        return {"session_id": session_id, "url": "https://example.com", "controlled_by": mode}
    mock_service.set_control = mock_control

    with TestClient(app) as client:
        # Override browser service in app state
        client.app.state.browser_service = mock_service
        
        sess_id = str(uuid4())
        
        # Create a session in DB first to satisfy websocket/sessions requirements
        # (Though router endpoint is hit directly)
        
        # 1. GET browser state
        resp = client.get(f"/api/v1/sessions/{sess_id}/browser")
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://example.com"
        
        # 2. POST navigate
        resp = client.post(f"/api/v1/sessions/{sess_id}/browser/navigate", json={"url": "https://example.com/test"})
        assert resp.status_code == 202
        assert resp.json()["url"] == "https://example.com/test"
        
        # 3. POST click
        resp = client.post(f"/api/v1/sessions/{sess_id}/browser/click", json={"x": 50, "y": 60})
        assert resp.status_code == 202
        assert resp.json()["title"] == "Clicked"
        
        # 4. POST type
        resp = client.post(f"/api/v1/sessions/{sess_id}/browser/type", json={"text": "search terms"})
        assert resp.status_code == 202
        
        # 5. POST control
        resp = client.post(f"/api/v1/sessions/{sess_id}/browser/control", json={"control": "user"})
        assert resp.status_code == 202
        assert resp.json()["controlled_by"] == "user"
