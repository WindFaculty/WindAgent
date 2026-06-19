"""Tests for PermissionService (Phase 7).

Covers:
  - PermissionConfig.needs_confirmation() rules per tool
  - PermissionService.request_permission() emit + wait + resolve
  - nowait mode (test helper)
  - timeout defaulting to deny
  - config_dict / update_config
  - whitelist enforcement (unknown tool not in registry)
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from schemas.event import (
    EventEnvelope,
    PermissionRequestData,
)
from services.event_bus import EventBus, drain
from services.permission_service import PermissionConfig, PermissionService
from services.tool_registry import get_tool


# ---------- Pure config tests ----------

def test_safe_tool_never_confirms():
    cfg = PermissionConfig(safe_mode=True)  # even safe_mode doesn't matter
    for tool_name in ("screenshot", "wait"):
        info = get_tool(tool_name)
        assert cfg.needs_confirmation(info, {}) is False


def test_open_app_does_not_confirm_under_default_config():
    cfg = PermissionConfig()
    info = get_tool("open_app")
    assert cfg.needs_confirmation(info, {"app": "notepad"}) is False


def test_open_url_does_not_confirm_under_default_config():
    cfg = PermissionConfig()
    info = get_tool("open_url")
    assert cfg.needs_confirmation(
        info, {"url": "https://google.com"}
    ) is False


def test_type_text_short_does_not_confirm():
    cfg = PermissionConfig()
    info = get_tool("type_text")
    assert cfg.needs_confirmation(
        info, {"text": "Hello", "method": "paste"}
    ) is False


def test_type_text_long_confirms():
    cfg = PermissionConfig()
    info = get_tool("type_text")
    long_text = "x" * 25
    assert cfg.needs_confirmation(
        info, {"text": long_text, "method": "paste"}
    ) is True


def test_type_text_with_password_confirms():
    cfg = PermissionConfig()
    info = get_tool("type_text")
    assert cfg.needs_confirmation(
        info, {"text": "my password is hunter2", "method": "paste"}
    ) is True


def test_type_text_with_token_confirms():
    cfg = PermissionConfig()
    info = get_tool("type_text")
    assert cfg.needs_confirmation(
        info, {"text": "token=abc123", "method": "paste"}
    ) is True


def test_type_text_disabled_does_not_confirm():
    cfg = PermissionConfig(confirm_before_type=False)
    info = get_tool("type_text")
    long_text = "x" * 100
    assert cfg.needs_confirmation(
        info, {"text": long_text, "method": "paste"}
    ) is False


def test_click_xy_confirms_under_default_config():
    cfg = PermissionConfig()
    info = get_tool("click_xy")
    assert cfg.needs_confirmation(
        info, {"x": 100, "y": 200}
    ) is True


def test_click_xy_disabled_does_not_confirm():
    cfg = PermissionConfig(confirm_before_click=False)
    info = get_tool("click_xy")
    assert cfg.needs_confirmation(info, {"x": 100, "y": 200}) is False


def test_safe_mode_force_confirms_medium_with_requires_confirmation():
    cfg = PermissionConfig(safe_mode=True, confirm_before_type=False)
    info = get_tool("type_text")
    # safe_mode overrides confirm_before_type
    assert cfg.needs_confirmation(info, {"text": "short", "method": "paste"}) is True


# ---------- Service behavior ----------

@pytest.mark.asyncio
async def test_request_permission_emits_permission_request_event():
    bus = EventBus()
    svc = PermissionService(bus)
    sid = uuid.uuid4()
    step = uuid.uuid4()
    q = await bus.subscribe(str(sid))

    info = get_tool("type_text")

    async def grant_soon():
        await asyncio.sleep(0.05)
        # Pending request should exist.
        assert svc.pending_count() == 1
        # Find the request_id and resolve it.
        pending_id = list(svc._pending.keys())[0]
        await svc.resolve_permission(pending_id, granted=True)

    asyncio.create_task(grant_soon())
    granted, request_id = await svc.request_permission(
        session_id=sid,
        step_id=step,
        tool_info=info,
        params={"text": "x" * 25, "method": "paste"},
    )
    assert granted is True
    events = await drain(q)
    event_names = [e.event for e in events]
    assert "permission_request" in event_names
    assert "permission_granted" in event_names


@pytest.mark.asyncio
async def test_request_permission_nowait_returns_denied():
    bus = EventBus()
    svc = PermissionService(bus)
    sid = uuid.uuid4()
    step = uuid.uuid4()
    q = await bus.subscribe(str(sid))

    info = get_tool("type_text")
    granted, request_id = await svc.request_permission(
        session_id=sid,
        step_id=step,
        tool_info=info,
        params={"text": "x" * 25, "method": "paste"},
        nowait=True,
    )
    assert granted is False
    assert request_id is not None
    events = await drain(q)
    names = [e.event for e in events]
    assert "permission_request" in names
    assert "permission_denied" in names


@pytest.mark.asyncio
async def test_request_permission_timeout_defaults_to_deny():
    bus = EventBus()
    cfg = PermissionConfig(request_timeout_s=0.05)
    svc = PermissionService(bus, cfg)
    sid = uuid.uuid4()
    step = uuid.uuid4()
    q = await bus.subscribe(str(sid))

    info = get_tool("type_text")
    granted, _ = await svc.request_permission(
        session_id=sid, step_id=step, tool_info=info,
        params={"text": "x" * 25, "method": "paste"},
    )
    assert granted is False
    events = await drain(q)
    last = events[-1]
    assert last.event == "permission_denied"
    assert last.data["reason"] == "timeout"


@pytest.mark.asyncio
async def test_resolve_unknown_request_returns_false():
    bus = EventBus()
    svc = PermissionService(bus)
    ok = await svc.resolve_permission(uuid.uuid4(), granted=True)
    assert ok is False


@pytest.mark.asyncio
async def test_resolve_same_request_twice_only_first_wakes():
    bus = EventBus()
    svc = PermissionService(bus)
    sid = uuid.uuid4()
    step = uuid.uuid4()
    q = await bus.subscribe(str(sid))

    info = get_tool("type_text")

    async def grant():
        await asyncio.sleep(0.02)
        pending_id = list(svc._pending.keys())[0]
        # Resolve once — first call wakes the waiter.
        ok1 = await svc.resolve_permission(pending_id, granted=True)
        # Second call should be a no-op.
        ok2 = await svc.resolve_permission(pending_id, granted=False)
        assert ok1 is True
        assert ok2 is False

    asyncio.create_task(grant())
    granted, _ = await svc.request_permission(
        session_id=sid, step_id=step, tool_info=info,
        params={"text": "x" * 25, "method": "paste"},
    )
    assert granted is True
    # Only one decision event should have been published (from the first resolve).
    decision_events = [
        e for e in await drain(q) if e.event == "permission_granted"
    ]
    assert len(decision_events) == 1


@pytest.mark.asyncio
async def test_pending_count_per_session():
    bus = EventBus()
    svc = PermissionService(bus)
    info = get_tool("type_text")

    # Kick off three nowait requests across two sessions.
    sid_a, sid_b = uuid.uuid4(), uuid.uuid4()
    for sid, step in (
        (sid_a, uuid.uuid4()),
        (sid_a, uuid.uuid4()),
        (sid_b, uuid.uuid4()),
    ):
        await svc.request_permission(
            session_id=sid, step_id=step, tool_info=info,
            params={"text": "x"}, nowait=True,
        )
    # nowait auto-denies → pending cleared immediately.
    assert svc.pending_count() == 0


def test_config_dict_and_update_config():
    bus = EventBus()
    svc = PermissionService(bus)
    cfg_dict = svc.config_dict()
    assert cfg_dict["safe_mode"] is False
    assert cfg_dict["confirm_before_type"] is True

    svc.update_config(safe_mode=True, confirm_before_click=False)
    assert svc.config.safe_mode is True
    assert svc.config.confirm_before_click is False


def test_update_config_rejects_unknown_key():
    bus = EventBus()
    svc = PermissionService(bus)
    with pytest.raises(AttributeError):
        svc.update_config(unknown_key=True)


def test_whitelist_unknown_tool_raises_in_registry():
    """Defence in depth — runner / planner both validate, but the
    registry itself raises on unknown names."""
    with pytest.raises(KeyError):
        get_tool("delete_all_files")
    with pytest.raises(KeyError):
        get_tool("shell_command")