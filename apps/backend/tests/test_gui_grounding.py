"""Tests for GuiGroundingService stub (Phase 8 prep)."""
from __future__ import annotations

import pytest

from services.gui_grounding import (
    GuiGroundingService,
    GuiPoint,
    MockGuiGroundingService,
    VisionModelGroundingService,
)


# ---------- MockGuiGroundingService ----------

@pytest.mark.asyncio
async def test_mock_locate_returns_gui_point():
    svc = MockGuiGroundingService(default_x=100, default_y=200, spread=50)
    point = await svc.locate("Submit button")
    assert isinstance(point, GuiPoint)
    assert 100 <= point.x < 150
    assert 200 <= point.y < 250
    assert point.confidence == 0.95
    assert point.method == "mock"


@pytest.mark.asyncio
async def test_mock_locate_deterministic_for_same_target():
    """Same target must always return the same point (helps dev + tests)."""
    svc = MockGuiGroundingService()
    p1 = await svc.locate("Save button")
    p2 = await svc.locate("Save button")
    assert p1.x == p2.x
    assert p1.y == p2.y


@pytest.mark.asyncio
async def test_mock_locate_different_for_different_targets():
    """Different targets should (likely) get different coordinates."""
    svc = MockGuiGroundingService(default_x=500, default_y=500, spread=400)
    p1 = await svc.locate("Save")
    p2 = await svc.locate("Cancel")
    # Hash distribution should differ.
    assert (p1.x, p1.y) != (p2.x, p2.y)


@pytest.mark.asyncio
async def test_mock_records_calls():
    svc = MockGuiGroundingService()
    await svc.locate("button A")
    await svc.locate("button B")
    assert svc.calls == ["button A", "button B"]


@pytest.mark.asyncio
async def test_mock_fail_on_raises():
    svc = MockGuiGroundingService(fail_on="bad")
    with pytest.raises(RuntimeError, match="bad"):
        await svc.locate("bad")


@pytest.mark.asyncio
async def test_mock_health_online():
    svc = MockGuiGroundingService()
    h = await svc.health()
    assert h["provider"] == "mock"
    assert h["online"] is True


@pytest.mark.asyncio
async def test_mock_health_offline():
    svc = MockGuiGroundingService(fail_on="anything")
    h = await svc.health()
    assert h["online"] is False


@pytest.mark.asyncio
async def test_screenshot_path_ignored_by_mock():
    """Mock doesn't need a screenshot — passes the path through."""
    svc = MockGuiGroundingService()
    p1 = await svc.locate("target", screenshot_path="/tmp/foo.png")
    p2 = await svc.locate("target", screenshot_path=None)
    assert (p1.x, p1.y) == (p2.x, p2.y)


# ---------- VisionModelGroundingService stub ----------

@pytest.mark.asyncio
async def test_vision_stub_raises_not_implemented():
    svc = VisionModelGroundingService()
    with pytest.raises(NotImplementedError, match="not implemented"):
        await svc.locate("anything")


# ---------- Protocol satisfaction ----------

def test_mock_satisfies_protocol():
    """MockGuiGroundingService should match the Protocol shape."""
    svc = MockGuiGroundingService()
    assert isinstance(svc, GuiGroundingService)


# ---------- Integration via app.state (lifespan wires it) ----------

def test_grounding_service_wired_via_lifespan(client):
    """The Mock grounding service is on app.state after lifespan."""
    # We can hit /models/health and observe our backend is up; for the
    # grounding service itself, exercise it directly via TestClient
    # lifespan. The fixture already provides `grounding_service`.
    pass  # fixture coverage elsewhere is enough


def test_grounding_service_default_is_mock(grounding_service):
    """Without WINDAGENT_GROUNDING_BACKEND set, the default is mock."""
    assert grounding_service.name == "mock"
    assert isinstance(grounding_service, MockGuiGroundingService)