"""Tests for /permissions endpoints (Phase 7).

These tests use FastAPI's TestClient (sync) and the live PermissionService
on app.state. To exercise the async resolve path reliably we drive the
service from the same event loop the TestClient uses via anyio.run.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import anyio
import pytest


# ---------- REST contract ----------

def test_get_config_returns_current(client):
    r = client.get("/permissions/config")
    assert r.status_code == 200
    body = r.json()
    assert "safe_mode" in body
    assert "confirm_before_type" in body
    assert "confirm_before_click" in body
    assert "type_text_length_threshold" in body


def test_patch_config_updates_one_field(client):
    r = client.patch(
        "/permissions/config",
        json={"safe_mode": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["safe_mode"] is True
    # Other fields untouched.
    assert body["confirm_before_type"] is True


def test_patch_config_multiple_fields(client):
    r = client.patch(
        "/permissions/config",
        json={"safe_mode": True, "confirm_before_click": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["safe_mode"] is True
    assert body["confirm_before_click"] is False


def test_patch_config_with_invalid_value_returns_422(client):
    r = client.patch(
        "/permissions/config",
        json={"type_text_length_threshold": 0},  # ge=1
    )
    assert r.status_code == 422


def test_decide_unknown_request_returns_404(client):
    r = client.post(
        f"/permissions/{uuid.uuid4()}/decide",
        json={"decision": "granted"},
    )
    assert r.status_code == 404


def test_decide_invalid_decision_returns_422(client):
    fake_id = uuid.uuid4()
    r = client.post(
        f"/permissions/{fake_id}/decide",
        json={"decision": "maybe"},
    )
    assert r.status_code == 422


def test_decide_missing_decision_returns_422(client):
    r = client.post(
        f"/permissions/{uuid.uuid4()}/decide",
        json={},
    )
    assert r.status_code == 422


# ---------- Round-trip: real pending request -> REST decide ----------

def _wait_runner_pending(permission_service, timeout: float = 2.0):
    """Block (in an event loop) until exactly one pending request exists.
    Returns the request_id. Raises if timeout."""
    async def _wait():
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if len(permission_service._pending) == 1:
                return next(iter(permission_service._pending.keys()))
            await asyncio.sleep(0.01)
        raise AssertionError(
            f"no pending request after {timeout}s "
            f"(have {permission_service.pending_count()})"
        )

    return _wait()


def test_decision_via_rest_unblocks_pending_request(client, app_state):
    """REST POST /permissions/{id}/decide resolves a real pending
    request created via the service."""
    from services.tool_registry import get_tool

    info = get_tool("type_text")
    sid = uuid.uuid4()
    step = uuid.uuid4()

    # Drive the service from the same loop as the TestClient.
    async def setup():
        granted, _ = await app_state.permission_service.request_permission(
            session_id=sid,
            step_id=step,
            tool_info=info,
            params={"text": "x" * 25, "method": "paste"},
        )
        return granted

    async def main():
        # Submit the request; it will block until we resolve it via REST.
        runner_task = asyncio.create_task(setup())
        request_id = await _wait_runner_pending(app_state.permission_service)
        # REST call from a thread — sync TestClient is fine, app.state
        # is shared across loops.
        r = client.post(
            f"/permissions/{request_id}/decide",
            json={"decision": "granted"},
        )
        assert r.status_code == 202
        assert r.json()["status"] == "resolved"
        # Waiter should now unblock with granted=True.
        granted = await asyncio.wait_for(runner_task, timeout=2.0)
        return granted

    granted = anyio.run(main)
    assert granted is True
    assert app_state.permission_service.pending_count() == 0


def test_decision_via_rest_deny_unblocks_pending_request(client, app_state):
    from services.tool_registry import get_tool

    info = get_tool("type_text")
    sid = uuid.uuid4()
    step = uuid.uuid4()

    async def setup():
        granted, _ = await app_state.permission_service.request_permission(
            session_id=sid,
            step_id=step,
            tool_info=info,
            params={"text": "x" * 25, "method": "paste"},
        )
        return granted

    async def main():
        runner_task = asyncio.create_task(setup())
        request_id = await _wait_runner_pending(app_state.permission_service)
        r = client.post(
            f"/permissions/{request_id}/decide",
            json={"decision": "denied"},
        )
        assert r.status_code == 202
        granted = await asyncio.wait_for(runner_task, timeout=2.0)
        return granted

    granted = anyio.run(main)
    assert granted is False


def test_double_decide_second_call_returns_404(client, app_state):
    from services.tool_registry import get_tool

    info = get_tool("type_text")

    async def main():
        sid, step = uuid.uuid4(), uuid.uuid4()
        # Use nowait to avoid the runner blocking for the default 60s
        # request timeout.
        granted, request_id = await app_state.permission_service.request_permission(
            session_id=sid, step_id=step, tool_info=info,
            params={"text": "x" * 25, "method": "paste"},
            nowait=True,
        )
        # nowait denies immediately and clears the pending entry.
        assert granted is False
        return request_id

    request_id = anyio.run(main)
    # The request was auto-denied; pending is empty.
    assert app_state.permission_service.pending_count() == 0
    # Any decision call returns 404.
    r = client.post(
        f"/permissions/{request_id}/decide",
        json={"decision": "granted"},
    )
    assert r.status_code == 404