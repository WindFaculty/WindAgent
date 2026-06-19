"""Tool Registry — metadata + parameter schema for the 10 MVP tools.

Shape MUST match docs/event_protocol.md §6 + §7.

The registry is a dict from tool name -> ToolInfo. Tools themselves
live in `services.tool_executor`; this module is pure data so it can
be imported cheaply in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Type

from pydantic import BaseModel, Field, HttpUrl


# ---------- Risk levels ----------
RiskLevel = Literal["safe", "medium", "high"]


# ---------- Per-tool param models ----------

class OpenAppParams(BaseModel):
    app: Literal["notepad", "calc", "mspaint", "edge", "explorer"]


class OpenUrlParams(BaseModel):
    url: HttpUrl


class TypeTextParams(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)
    method: Literal["type", "paste"] = "paste"


class HotkeyParams(BaseModel):
    keys: List[str] = Field(..., min_length=1)


class PressKeyParams(BaseModel):
    key: str = Field(..., min_length=1)


class ClickXyParams(BaseModel):
    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"


class ClickTargetParams(BaseModel):
    """Phase 8 — describe an element to click instead of giving x/y.

    The runner takes a screenshot, asks `GuiGroundingService.locate()`
    to resolve the target, then either clicks (real vision) or surfaces
    the resolved coords to the user (stub mode).
    """

    target: str = Field(..., min_length=1, max_length=200)
    screenshot_name: Optional[str] = None


class ScrollParams(BaseModel):
    clicks: int = Field(..., ge=1, le=100)
    direction: Literal["up", "down", "left", "right"]


class ScreenshotParams(BaseModel):
    name: Optional[str] = None


class WaitParams(BaseModel):
    seconds: float = Field(..., gt=0, le=60)


# ---------- Tool metadata ----------

@dataclass(frozen=True)
class ToolInfo:
    """Metadata about a single tool. Pure data, no behaviour."""
    name: str
    description: str
    risk_level: RiskLevel
    requires_confirmation: bool
    params_model: Type[BaseModel]


# ---------- Registry ----------

TOOL_REGISTRY: Dict[str, ToolInfo] = {
    "open_app": ToolInfo(
        name="open_app",
        description="Open a Windows application by short alias (notepad/calc/mspaint/edge/explorer).",
        risk_level="medium",
        requires_confirmation=False,
        params_model=OpenAppParams,
    ),
    "open_url": ToolInfo(
        name="open_url",
        description="Open an http(s) URL in Microsoft Edge.",
        risk_level="medium",
        requires_confirmation=False,
        params_model=OpenUrlParams,
    ),
    "type_text": ToolInfo(
        name="type_text",
        description="Type or paste text into the currently focused window.",
        risk_level="medium",
        requires_confirmation=True,
        params_model=TypeTextParams,
    ),
    "hotkey": ToolInfo(
        name="hotkey",
        description="Press a keyboard combination (e.g. ctrl+c).",
        risk_level="medium",
        requires_confirmation=False,
        params_model=HotkeyParams,
    ),
    "press_key": ToolInfo(
        name="press_key",
        description="Press a single key (e.g. Enter, Escape).",
        risk_level="medium",
        requires_confirmation=False,
        params_model=PressKeyParams,
    ),
    "click_xy": ToolInfo(
        name="click_xy",
        description="Click at absolute screen coordinates.",
        risk_level="high",
        requires_confirmation=True,
        params_model=ClickXyParams,
    ),
    "click_target": ToolInfo(
        name="click_target",
        description=(
            "Phase 8 — describe a screen element (e.g. 'Submit button') "
            "and the runner will resolve it via the GUI grounding service. "
            "Falls back to a stub that returns a deterministic point + "
            "a clear 'vision not supported' message until Qwen2.5-VL ships."
        ),
        risk_level="high",
        requires_confirmation=True,
        params_model=ClickTargetParams,
    ),
    "scroll": ToolInfo(
        name="scroll",
        description="Scroll the mouse wheel up/down/left/right.",
        risk_level="medium",
        requires_confirmation=False,
        params_model=ScrollParams,
    ),
    "screenshot": ToolInfo(
        name="screenshot",
        description="Capture the screen to a PNG file under artifacts/runs/<sid>/screenshots/.",
        risk_level="safe",
        requires_confirmation=False,
        params_model=ScreenshotParams,
    ),
    "wait": ToolInfo(
        name="wait",
        description="Pause execution for N seconds (0 < N <= 60).",
        risk_level="safe",
        requires_confirmation=False,
        params_model=WaitParams,
    ),
}


# ---------- Helpers ----------

def get_tool(name: str) -> ToolInfo:
    """Return ToolInfo or raise KeyError if tool name not in whitelist."""
    try:
        return TOOL_REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown tool {name!r}. "
            f"Whitelist: {sorted(TOOL_REGISTRY)}"
        ) from None


def validate_params(name: str, params: Dict[str, Any]) -> BaseModel:
    """Validate raw dict against the tool's params model.

    Returns the parsed model instance. Raises pydantic.ValidationError
    on bad input.
    """
    info = get_tool(name)
    return info.params_model.model_validate(params)


def list_tool_names() -> List[str]:
    return sorted(TOOL_REGISTRY)


__all__ = [
    "TOOL_REGISTRY",
    "ToolInfo",
    "RiskLevel",
    "get_tool",
    "validate_params",
    "list_tool_names",
]
