"""Unit tests for WorkflowService, including the intent parser."""
from __future__ import annotations

import uuid

import pytest

from services.event_bus import drain
from services.workflow_service import WorkflowService, parse_intent


# ---------- Pure parser tests ----------

def test_parser_notepad_demo():
    draft = parse_intent("Mở Notepad và gõ Hello")
    assert len(draft.steps) == 2
    assert draft.steps[0] == {
        "name": "Open Notepad",
        "tool_name": "open_app",
        "params": {"app": "notepad"},
    }
    assert draft.steps[1]["tool_name"] == "type_text"
    assert draft.steps[1]["params"]["text"] == "Hello"


def test_parser_notepad_full_demo_phrase():
    draft = parse_intent("Mở Notepad và gõ Hello from local AI agent.")
    assert len(draft.steps) == 2
    assert draft.steps[1]["params"]["text"] == "Hello from local AI agent"


def test_parser_notepad_default_text_when_missing():
    draft = parse_intent("Open Notepad")
    assert draft.warning is not None  # defaulted
    assert draft.steps[1]["params"]["text"] == "Hello"


def test_parser_edge_with_url():
    draft = parse_intent("Mở trang google.com trên Edge")
    assert len(draft.steps) == 2
    assert draft.steps[0]["tool_name"] == "open_app"
    assert draft.steps[0]["params"]["app"] == "edge"
    assert draft.steps[1]["tool_name"] == "open_url"
    assert draft.steps[1]["params"]["url"].startswith("https://")


def test_parser_edge_with_explicit_https():
    draft = parse_intent("Mở https://example.com trên Edge")
    assert draft.steps[1]["params"]["url"] == "https://example.com"


def test_parser_edge_without_url_warns():
    draft = parse_intent("Mở Edge")
    assert "edge requested but no URL detected" in (draft.warning or "")


def test_parser_unknown_intent_empty():
    draft = parse_intent("Đặt lịch họp lúc 9h sáng mai")
    assert draft.steps == []
    assert draft.warning is not None


def test_parser_empty_text():
    draft = parse_intent("")
    assert draft.steps == []
    assert draft.warning == "empty message"


# ---------- Service-level tests ----------

@pytest.mark.asyncio
async def test_create_for_message_emits_full_event_sequence(event_bus, workflow_service):
    sid = uuid.uuid4()
    mid = uuid.uuid4()
    q = await event_bus.subscribe(str(sid))

    wf = await workflow_service.create_for_message(
        session_id=sid, message_id=mid, content="Mở Notepad và gõ Hello"
    )

    events = await drain(q)
    names = [e.event for e in events]
    assert names == ["planning_started", "planning_finished", "workflow_created"]

    # planning_finished carries model metadata. With the PlannerService
    # wired (Phase 4+), the MockModelClient handles this phrase directly
    # so used_fallback=False and model == "mock:...". The default
    # WorkflowService (no planner) would still report
    # used_fallback=True and model == "fallback-rule-based".
    pf = next(e for e in events if e.event == "planning_finished")
    assert pf.data["used_fallback"] is False
    assert pf.data["model"].startswith("mock:")
    assert isinstance(pf.data["latency_ms"], int)

    # workflow_created carries step_count == 2
    wc = next(e for e in events if e.event == "workflow_created")
    assert wc.data["step_count"] == 2
    assert wc.data["session_id"] == str(sid)
    assert wc.data["workflow_id"] == str(wf.workflow_id)


@pytest.mark.asyncio
async def test_get_for_session_returns_none_before_create(workflow_service):
    assert await workflow_service.get_for_session(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_workflow_steps_match_parser(event_bus, workflow_service):
    sid = uuid.uuid4()
    q = await event_bus.subscribe(str(sid))
    wf = await workflow_service.create_for_message(
        session_id=sid, message_id=uuid.uuid4(), content="Mở Notepad và gõ X"
    )
    await drain(q)  # discard events

    assert [s.tool_name for s in wf.steps] == ["open_app", "type_text"]
    assert [s.order for s in wf.steps] == [1, 2]
    assert all(s.status == "pending" for s in wf.steps)
    fetched = await workflow_service.get_for_session(sid)
    assert fetched is not None
    assert fetched.workflow_id == wf.workflow_id