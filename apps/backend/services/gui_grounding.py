"""Phase 8 prep — GUI grounding service stub.

The real implementation (per `ban_ke_hoach.md` §Phase 8) will use
Qwen2.5-VL to find a screen element by description and return its
screen coordinates. This module ships the **interface** plus a
deterministic mock implementation so the ToolExecutor, the workflow
runner, and the frontend can all be developed and tested without a
running vision model.

Wire-up (Phase 8 full implementation, not in this stub):
  - The frontend captures / asks the user to capture a screenshot
    before each `click_xy` call.
  - The runner asks `GuiGroundingService.locate(screenshot, target)` to
    resolve a textual target like "Submit button" into (x, y).
  - The ToolExecutor highlights the resolved point for confirmation,
    then calls the GUI adapter's `click_xy` with the coordinates.

For now (Phase 6 enhancement), the mock returns canned coordinates and
the ToolExecutor still accepts direct (x, y) params. This module
exposes the protocol only — callers (e.g. runner) can inject the
service via app.state and use it when they want to highlight a target.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


log = logging.getLogger(__name__)


# ---------- Data ----------

@dataclass(frozen=True)
class GuiPoint:
    """A resolved screen coordinate plus confidence + method."""
    x: int
    y: int
    confidence: float
    method: str  # "vision_model" | "manual" | "mock"


# ---------- Protocol ----------

@runtime_checkable
class GuiGroundingService(Protocol):
    """Resolve a textual target to a screen point.

    The MVP contract is small: take a target description and optional
    screenshot, return a GuiPoint. Implementations may ignore the
    screenshot if they don't need it.
    """

    name: str

    async def locate(
        self,
        target: str,
        *,
        screenshot_path: Optional[str] = None,
    ) -> GuiPoint:
        ...


# ---------- Mock implementation ----------

class MockGuiGroundingService:
    """Deterministic fake — returns a stable point for any target.

    - Coordinates are derived from a hash of the target so the same
      target always returns the same (x, y) (helps tests / dev).
    - Confidence is fixed high so the runner doesn't refuse to click
      during MVP testing.
    - Optional `fail_on` lets tests simulate a vision service error.
    """

    name = "mock"

    def __init__(
        self,
        *,
        default_x: int = 500,
        default_y: int = 500,
        spread: int = 200,
        confidence: float = 0.95,
        latency_ms: int = 50,
        fail_on: Optional[str] = None,
    ) -> None:
        self.default_x = default_x
        self.default_y = default_y
        self.spread = spread
        self.confidence = confidence
        self.latency_ms = latency_ms
        self._fail_on = fail_on
        self.calls: List[str] = []

    async def locate(
        self,
        target: str,
        *,
        screenshot_path: Optional[str] = None,
    ) -> GuiPoint:
        self.calls.append(target)
        # Simulate model latency.
        await asyncio.sleep(self.latency_ms / 1000.0)

        if self._fail_on == target:
            raise RuntimeError(f"mock-induced grounding failure on {target!r}")

        # Stable pseudo-random offset based on the target string.
        h = abs(hash(target))
        dx = h % self.spread
        dy = (h // self.spread) % self.spread
        return GuiPoint(
            x=self.default_x + dx,
            y=self.default_y + dy,
            confidence=self.confidence,
            method="mock",
        )

    async def health(self) -> Dict[str, Any]:
        """Cheap liveness probe — used by /models/health or a future
        /grounding/health endpoint."""
        return {
            "provider": self.name,
            "online": self._fail_on is None,
            "default_confidence": self.confidence,
        }


# ---------- Future real impl placeholder ----------

class VisionModelGroundingService:
    """Stub for the real Qwen2.5-VL grounded click implementation.

    This class is intentionally not implemented. It exists so the
    `main.py` lifespan can choose between mock and a future real
    backend without changing the call sites. Selecting it via env
    var WINDAGENT_GROUNDING_BACKEND=vision will raise NotImplementedError
    until Phase 8 wires the actual model call.
    """

    name = "vision_model"

    async def locate(
        self,
        target: str,
        *,
        screenshot_path: Optional[str] = None,
    ) -> GuiPoint:
        raise NotImplementedError(
            "VisionModelGroundingService is not implemented in this phase. "
            "Use WINDAGENT_GROUNDING_BACKEND=mock for now."
        )