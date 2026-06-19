"""Tool Executor — runs a single tool call and audits it.

Pipeline per call:
  1. Validate tool name (must be in TOOL_REGISTRY).
  2. Validate params (Pydantic).
  3. Emit `tool_call_started`.
  4. Run the GUI adapter in a worker thread.
  5. Emit `tool_call_finished` (success/failed).
  6. Write a `tool_calls` row in the DB.
  7. Return {status, output | error, duration_ms}.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from db.database import Database
from db.models import ToolCallORM
from schemas.event import (
    EventEnvelope,
    StepErrorInfo,
    ToolCallFinishedData,
    ToolCallStartedData,
)
from services.event_bus import EventBus
from services.gui_adapter import GuiAdapter
from services.gui_grounding import GuiGroundingService, GuiPoint
from services.tool_registry import get_tool, validate_params


log = logging.getLogger(__name__)


# Where screenshot artifacts are written.
DEFAULT_ARTIFACTS_ROOT = Path("artifacts") / "runs"


class ToolExecutor:
    def __init__(
        self,
        event_bus: EventBus,
        db: Optional[Database],
        gui: GuiAdapter,
        *,
        artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT,
        grounding_service: Optional[GuiGroundingService] = None,
    ) -> None:
        self._bus = event_bus
        self._db = db
        self._gui = gui
        self._artifacts_root = artifacts_root
        self._grounding = grounding_service

    # ---------- Public API ----------

    async def execute(
        self,
        session_id: UUID,
        step_id: Optional[UUID],
        tool_name: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run one tool. Returns the public result dict.

        Never raises — errors are converted into status="failed"
        with an `error` payload.
        """
        # 1+2: validate
        try:
            info = get_tool(tool_name)
            validated = validate_params(tool_name, params)
        except (KeyError, Exception) as exc:
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_name,
                params=params,
                status="failed",
                output=None,
                error=StepErrorInfo(
                    type="validation_error",
                    message=str(exc),
                    code="INVALID_TOOL_OR_PARAMS",
                ).model_dump(mode="json"),
                duration_ms=0,
            )

        # 3: started event
        await self._bus.publish(
            str(session_id),
            EventEnvelope(
                event="tool_call_started",
                data=ToolCallStartedData(
                    session_id=session_id,
                    step_id=step_id,
                    tool_name=info.name,
                    input=params,
                ).model_dump(mode="json"),
            ),
        )

        # 4a: Phase 8 — `click_target` needs the grounding service.
        # Handle it separately from the generic sync path because it
        # is async (vision model) and the result is "did we click or
        # did we surface a stub-mode error to the user?".
        if info.name == "click_target":
            return await self._execute_click_target(
                session_id=session_id,
                step_id=step_id,
                params=params,
                validated=validated,
            )

        # 4: run adapter in worker thread
        start = time.perf_counter()
        try:
            output = await asyncio.to_thread(
                self._run, info.name, validated, session_id
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name=info.name,
                params=params,
                status="success",
                output=output,
                error=None,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.exception("tool %s failed", info.name)
            err = StepErrorInfo(
                type=type(exc).__name__,
                message=str(exc),
                code="TOOL_EXECUTION_FAILED",
            ).model_dump(mode="json")
            tb = traceback.format_exc()
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name=info.name,
                params=params,
                status="failed",
                output=None,
                error=err,
                duration_ms=duration_ms,
                traceback_text=tb,
            )

    # ---------- Internal ----------

    def _run(
        self,
        tool_name: str,
        validated_params: Any,
        session_id: UUID,
    ) -> Dict[str, Any]:
        """Sync dispatch into the GUI adapter. Runs in worker thread."""
        if tool_name == "open_app":
            return self._gui.open_app(app=validated_params.app)
        if tool_name == "open_url":
            return self._gui.open_url(url=str(validated_params.url))
        if tool_name == "type_text":
            return self._gui.type_text(
                text=validated_params.text,
                method=validated_params.method,
            )
        if tool_name == "hotkey":
            return self._gui.hotkey(keys=list(validated_params.keys))
        if tool_name == "press_key":
            return self._gui.press_key(key=validated_params.key)
        if tool_name == "click_xy":
            return self._gui.click_xy(
                x=validated_params.x,
                y=validated_params.y,
                button=validated_params.button,
            )
        if tool_name == "scroll":
            return self._gui.scroll(
                clicks=validated_params.clicks,
                direction=validated_params.direction,
            )
        if tool_name == "screenshot":
            out_dir = (
                self._artifacts_root / str(session_id) / "screenshots"
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            return self._gui.screenshot(
                name=validated_params.name,
                out_dir=out_dir,
            )
        if tool_name == "wait":
            return self._gui.wait(seconds=validated_params.seconds)
        raise ValueError(f"unhandled tool {tool_name!r}")

    # ---------- Phase 8: click_target (vision-grounded) ----------

    async def _execute_click_target(
        self,
        *,
        session_id: UUID,
        step_id: Optional[UUID],
        params: Dict[str, Any],
        validated: Any,
    ) -> Dict[str, Any]:
        """Resolve a screen element to coordinates via the grounding
        service, then either click (real vision) or surface a clear
        stub-mode error so the user can fall back to click_xy with
        manual coordinates.

        Acceptance criterion (ban_ke_hoach.md §Phase 8): "Khi gặp step
        `click_target`, hệ thống báo rõ chưa hỗ trợ vision thật thay vì
        click bừa." When the grounding service returns method !=
        "vision_model", the step fails with code VISION_STUB_MODE and
        a message that includes the resolved point + confidence so the
        user can copy x/y into a click_xy call.
        """
        start = time.perf_counter()
        if self._grounding is None:
            duration_ms = int((time.perf_counter() - start) * 1000)
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name="click_target",
                params=params,
                status="failed",
                output=None,
                error=StepErrorInfo(
                    type="vision_unavailable",
                    message=(
                        "GUI grounding service is not configured. "
                        "Use click_xy with manual coordinates for MVP."
                    ),
                    code="VISION_NOT_CONFIGURED",
                ).model_dump(mode="json"),
                duration_ms=duration_ms,
            )

        # 1. Take a fresh screenshot.
        try:
            out_dir = (
                self._artifacts_root / str(session_id) / "screenshots"
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            shot = await asyncio.to_thread(
                self._gui.screenshot,
                validated.screenshot_name,
                out_dir,
            )
            screenshot_path = shot.get("path")
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.exception("click_target: screenshot failed")
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name="click_target",
                params=params,
                status="failed",
                output=None,
                error=StepErrorInfo(
                    type="screenshot_failed",
                    message=str(exc),
                    code="SCREENSHOT_FAILED",
                ).model_dump(mode="json"),
                duration_ms=duration_ms,
            )

        # 2. Ask the grounding service where the target is.
        try:
            point: GuiPoint = await self._grounding.locate(
                validated.target,
                screenshot_path=screenshot_path,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log.exception("click_target: grounding failed")
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name="click_target",
                params=params,
                status="failed",
                output=None,
                error=StepErrorInfo(
                    type="vision_failed",
                    message=(
                        f"grounding failed for target={validated.target!r}: "
                        f"{exc}. Use click_xy with manual coordinates."
                    ),
                    code="GROUNDING_FAILED",
                ).model_dump(mode="json"),
                duration_ms=duration_ms,
            )

        # 3. Real vision → click. Stub / mock → fail with helpful msg.
        if point.method == "vision_model":
            try:
                output = await asyncio.to_thread(
                    self._gui.click_xy, point.x, point.y, "left"
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - start) * 1000)
                return await self._emit_and_persist(
                    session_id=session_id,
                    step_id=step_id,
                    tool_name="click_target",
                    params=params,
                    status="failed",
                    output=None,
                    error=StepErrorInfo(
                        type="click_failed",
                        message=str(exc),
                        code="CLICK_FAILED",
                    ).model_dump(mode="json"),
                    duration_ms=duration_ms,
                )
            duration_ms = int((time.perf_counter() - start) * 1000)
            output["resolved_point"] = {
                "x": point.x,
                "y": point.y,
                "confidence": point.confidence,
                "method": point.method,
            }
            return await self._emit_and_persist(
                session_id=session_id,
                step_id=step_id,
                tool_name="click_target",
                params=params,
                status="success",
                output=output,
                error=None,
                duration_ms=duration_ms,
            )

        # Stub / mock mode: do NOT click. Surface the resolved point
        # so the user can use it with click_xy.
        duration_ms = int((time.perf_counter() - start) * 1000)
        return await self._emit_and_persist(
            session_id=session_id,
            step_id=step_id,
            tool_name="click_target",
            params=params,
            status="failed",
            output={
                "resolved_point": {
                    "x": point.x,
                    "y": point.y,
                    "confidence": point.confidence,
                    "method": point.method,
                },
                "screenshot_path": screenshot_path,
            },
            error=StepErrorInfo(
                type="vision_stub_mode",
                message=(
                    f"GUI grounding returned method={point.method!r} "
                    f"(confidence={point.confidence:.2f}) at "
                    f"({point.x}, {point.y}). MVP chưa hỗ trợ vision thật — "
                    f"hãy nhập tọa độ hoặc dùng click_xy với x={point.x}, y={point.y}."
                ),
                code="VISION_STUB_MODE",
            ).model_dump(mode="json"),
            duration_ms=duration_ms,
        )

    async def _emit_and_persist(
        self,
        *,
        session_id: UUID,
        step_id: Optional[UUID],
        tool_name: str,
        params: Dict[str, Any],
        status: str,
        output: Optional[Dict[str, Any]],
        error: Optional[Dict[str, Any]],
        duration_ms: int,
        traceback_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Emit finished event.
        env = EventEnvelope(
            event="tool_call_finished",
            data=ToolCallFinishedData(
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_name,
                status=status,  # type: ignore[arg-type]
                output=output,
                duration_ms=duration_ms,
                error=(
                    StepErrorInfo(**error) if error and status == "failed" else None
                ),
            ).model_dump(mode="json"),
        )
        await self._bus.publish(str(session_id), env)

        # Persist tool_calls row(s).
        if self._db is not None:
            input_json = json.dumps(params, ensure_ascii=False)
            base_row = dict(
                session_id=str(session_id),
                step_id=str(step_id) if step_id else None,
                tool_name=tool_name,
                input_json=input_json,
            )
            try:
                async with self._db.session() as s:
                    # Primary row: status = success | failed
                    s.add(ToolCallORM(
                        id=str(uuid4()),
                        status=status,
                        output_json=json.dumps(
                            output if status == "success" else (error or {}),
                            ensure_ascii=False,
                        ),
                        created_at=env.timestamp,
                        **base_row,
                    ))
                    # If failed, also stash traceback in a sibling row so the
                    # primary output_json stays machine-readable.
                    if status == "failed" and traceback_text:
                        s.add(ToolCallORM(
                            id=str(uuid4()),
                            status="traceback",
                            output_json=json.dumps(
                                {"error": error, "traceback": traceback_text},
                                ensure_ascii=False,
                            ),
                            created_at=env.timestamp,
                            **base_row,
                        ))
            except Exception:
                log.exception("failed to persist tool_call row")

        return {
            "status": status,
            "output": output,
            "error": error,
            "duration_ms": duration_ms,
        }
