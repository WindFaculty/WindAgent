"""Unit tests for the Tool Registry (pure data, no DB / GUI)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.tool_registry import (
    TOOL_REGISTRY,
    get_tool,
    list_tool_names,
    validate_params,
)


EXPECTED_TOOLS = {
    "open_app",
    "open_url",
    "type_text",
    "hotkey",
    "press_key",
    "click_xy",
    "click_target",  # Phase 8 — vision-grounded click
    "scroll",
    "screenshot",
    "wait",
    "agent_s3_step",  # Phase 12 — Agent-S3 proposal driver
}


def test_registry_has_all_mvp_tools():
    assert set(TOOL_REGISTRY) == EXPECTED_TOOLS


def test_list_tool_names_returns_sorted_unique():
    names = list_tool_names()
    assert names == sorted(set(names))
    assert set(names) == EXPECTED_TOOLS


def test_get_tool_known_returns_metadata():
    info = get_tool("open_app")
    assert info.name == "open_app"
    assert info.risk_level in {"safe", "medium", "high"}
    assert info.params_model is not None


def test_get_tool_unknown_raises_keyerror():
    with pytest.raises(KeyError) as exc:
        get_tool("definitely_not_a_real_tool")
    assert "Whitelist" in str(exc.value)


# ---------- Param validation ----------

def test_open_app_accepts_known_app():
    p = validate_params("open_app", {"app": "notepad"})
    assert p.app == "notepad"


def test_open_app_rejects_unknown_app():
    with pytest.raises(ValidationError):
        validate_params("open_app", {"app": "definitely_notepad"})


def test_open_url_requires_http_scheme():
    p = validate_params("open_url", {"url": "https://example.com"})
    assert str(p.url) == "https://example.com/"

    with pytest.raises(ValidationError):
        validate_params("open_url", {"url": "ftp://example.com"})

    with pytest.raises(ValidationError):
        validate_params("open_url", {"url": "not a url"})


def test_type_text_defaults_to_paste_method():
    p = validate_params("type_text", {"text": "hello"})
    assert p.method == "paste"


def test_type_text_accepts_vietnamese():
    p = validate_params("type_text", {"text": "Xin chào bạn"})
    assert p.text == "Xin chào bạn"


def test_type_text_rejects_empty():
    with pytest.raises(ValidationError):
        validate_params("type_text", {"text": ""})


def test_hotkey_requires_at_least_one_key():
    p = validate_params("hotkey", {"keys": ["ctrl", "c"]})
    assert p.keys == ["ctrl", "c"]

    with pytest.raises(ValidationError):
        validate_params("hotkey", {"keys": []})


def test_click_xy_default_button_is_left():
    p = validate_params("click_xy", {"x": 100, "y": 200})
    assert p.button == "left"


def test_click_xy_rejects_unknown_button():
    with pytest.raises(ValidationError):
        validate_params("click_xy", {"x": 0, "y": 0, "button": "ear"})


def test_scroll_direction_enum():
    p = validate_params("scroll", {"clicks": 3, "direction": "down"})
    assert p.direction == "down"
    with pytest.raises(ValidationError):
        validate_params("scroll", {"clicks": 3, "direction": "sideways"})


def test_wait_requires_positive_seconds():
    p = validate_params("wait", {"seconds": 0.5})
    assert p.seconds == 0.5
    with pytest.raises(ValidationError):
        validate_params("wait", {"seconds": 0})
    with pytest.raises(ValidationError):
        validate_params("wait", {"seconds": -1})


def test_screenshot_name_optional():
    p = validate_params("screenshot", {})
    assert p.name is None
    p2 = validate_params("screenshot", {"name": "before-typing"})
    assert p2.name == "before-typing"


# ---------- Risk levels ----------

def test_click_xy_is_high_risk():
    """click_xy clicks at absolute coords — must require confirmation."""
    info = get_tool("click_xy")
    assert info.risk_level == "high"
    assert info.requires_confirmation is True


def test_type_text_is_medium_risk():
    info = get_tool("type_text")
    assert info.risk_level == "medium"
    assert info.requires_confirmation is True


def test_screenshot_and_wait_are_safe():
    assert get_tool("screenshot").risk_level == "safe"
    assert get_tool("wait").risk_level == "safe"
    assert get_tool("screenshot").requires_confirmation is False
    assert get_tool("wait").requires_confirmation is False
