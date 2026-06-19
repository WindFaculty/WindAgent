"""Tests for PlannerService (Phase 4).

Covers:
  - JSON validation + repair prompt
  - Fallback to rule-based parser on model offline / bad output
  - Whitelist enforcement
  - System + repair prompt shape
"""
from __future__ import annotations

import json

import pytest

from services.model_client import (
    ChatMessage,
    MockModelClient,
    ModelOfflineError,
    ModelResponseError,
)
from services.planner_service import (
    SYSTEM_PROMPT,
    PlannerService,
    _try_parse,
    _validate,
)


# ---------- Pure helpers ----------

def test_try_parse_strips_markdown_fence():
    assert _try_parse("```json\n{\"a\": 1}\n```") == {"a": 1}


def test_try_parse_handles_plain_json():
    assert _try_parse('{"steps": []}') == {"steps": []}


def test_try_parse_returns_none_on_garbage():
    assert _try_parse("not json at all") is None
    assert _try_parse("") is None


def test_validate_rejects_unknown_tool():
    parsed = {"steps": [{"name": "x", "tool_name": "delete_everything", "params": {}}]}
    assert _validate(parsed) is None


def test_validate_rejects_non_dict_step():
    parsed = {"steps": ["not a dict"]}
    assert _validate(parsed) is None


def test_validate_accepts_valid_step():
    parsed = {
        "steps": [
            {"name": "Open Notepad", "tool_name": "open_app", "params": {"app": "notepad"}}
        ]
    }
    cleaned = _validate(parsed)
    assert cleaned is not None
    assert len(cleaned) == 1
    assert cleaned[0]["tool_name"] == "open_app"


def test_validate_accepts_empty_steps_list():
    """Empty step list is structurally valid JSON; planner decides
    whether to fall back based on emptiness, not validation."""
    parsed = {"steps": []}
    cleaned = _validate(parsed)
    assert cleaned == []


def test_validate_rejects_non_dict_root():
    assert _validate([]) is None
    assert _validate("string") is None


# ---------- Service behavior ----------

@pytest.mark.asyncio
async def test_planner_uses_model_when_response_valid():
    client = MockModelClient()  # returns 2-step Notepad workflow for the demo
    planner = PlannerService(client=client)
    plan = await planner.plan("Mở Notepad và gõ Hello")
    assert plan.used_fallback is False
    assert plan.steps[0]["tool_name"] == "open_app"
    assert plan.steps[1]["tool_name"] == "type_text"
    assert plan.error is None


@pytest.mark.asyncio
async def test_planner_falls_back_when_model_offline():
    client = MockModelClient(fail_with_offline=True)
    planner = PlannerService(client=client)
    plan = await planner.plan("Mở Notepad và gõ Hello")
    assert plan.used_fallback is True
    # Fallback parser still produces 2 steps for the Notepad demo.
    assert len(plan.steps) == 2
    assert plan.steps[0]["tool_name"] == "open_app"
    assert plan.steps[1]["tool_name"] == "type_text"
    assert plan.error is not None


@pytest.mark.asyncio
async def test_planner_falls_back_on_empty_steps_from_model():
    client = MockModelClient()  # default returns {"steps": []} for unknown phrases
    planner = PlannerService(client=client)
    plan = await planner.plan("Mở Notepad và gõ something else")
    # Model said "I don't know" with empty steps; fallback parser
    # produces 2 steps for the Notepad pattern.
    assert plan.used_fallback is True
    assert len(plan.steps) == 2


@pytest.mark.asyncio
async def test_planner_repairs_invalid_json_then_succeeds():
    bad_then_good = [
        "this is not JSON",
        json.dumps({
            "steps": [
                {"name": "Open Edge", "tool_name": "open_app",
                 "params": {"app": "edge"}},
            ]
        }),
    ]
    client = MockModelClient(responses=bad_then_good)
    planner = PlannerService(client=client)
    plan = await planner.plan("Mở Edge")
    assert plan.used_fallback is False
    assert len(plan.steps) == 1
    assert plan.steps[0]["params"]["app"] == "edge"


@pytest.mark.asyncio
async def test_planner_falls_back_when_repair_also_fails():
    client = MockModelClient(responses=[
        "still not json",
        "still not json either",
    ])
    planner = PlannerService(client=client)
    plan = await planner.plan("Mở Notepad và gõ X")
    assert plan.used_fallback is True
    assert len(plan.steps) == 2  # rescued by fallback


@pytest.mark.asyncio
async def test_planner_rejects_unknown_tool_in_model_output_then_repairs():
    """Round 1: model returns a tool name not in the whitelist.
    Round 2: model returns a valid workflow.
    """
    bad = json.dumps({
        "steps": [
            {"name": "delete", "tool_name": "shell_command", "params": {"cmd": "rm -rf /"}}
        ]
    })
    good = json.dumps({
        "steps": [
            {"name": "wait", "tool_name": "wait", "params": {"seconds": 1.0}}
        ]
    })
    client = MockModelClient(responses=[bad, good])
    planner = PlannerService(client=client)
    plan = await planner.plan("Do something")
    assert plan.used_fallback is False
    assert plan.steps[0]["tool_name"] == "wait"


@pytest.mark.asyncio
async def test_planner_health_passthrough():
    client = MockModelClient()
    planner = PlannerService(client=client)
    h = await planner.health()
    assert h["provider"] == "mock"
    assert h["online"] is True


def test_system_prompt_lists_all_9_tools():
    for tool in (
        "open_app", "open_url", "type_text", "hotkey", "press_key",
        "click_xy", "scroll", "screenshot", "wait",
    ):
        assert tool in SYSTEM_PROMPT, f"{tool} missing from system prompt"