"""Prepared-action dispatch routers (/api/v3/live-record/plans/{id}/actions).

Phase 3 + Phase 7 (ban_ke_hoach_v1.md Sections 7, 13, 14):

- ``prepare``         → resolves one frozen action into a desktop dispatch
  ticket (CODE_PLAYBACK carries the operator's own prepared payload text;
  browser / command actions carry only resolved parameters).
- ``execute``         → server-side execution for RUN_COMMAND / TOOL_RUN via
  SafeShellRunner.
- ``execute-browser`` → server-side execution for BROWSER_NAVIGATION /
  BROWSER_ACTION through the existing browser session service (Section 14:
  reuse the browser execution layer). Every parameter is resolved from the
  frozen plan's payload bundle — never from request args — and verified
  against ``expected_after.url_contains`` when present.
- ``result``          → verifies the desktop-reported outcome (CODE_PLAYBACK
  hash verification) and appends the timeline event.

The Gemini director never calls these endpoints directly — the desktop tool
executor does, with action ids that the dispatcher has already gated against
the frozen plan.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from windagent_api.routers.v3.live_record.dependencies import (
    get_live_record_service,
    require_idempotency_key,
)
from windagent_api.services.live_record_application_service import (
    LiveRecordApplicationService,
)

router = APIRouter(prefix="/live-record/plans", tags=["live-record"])

#: Server-side command execution ceiling — recording actions are short.
MAX_COMMAND_TIMEOUT_SECONDS = 120.0

#: Recording-scoped browser sessions are namespaced per plan so a take reuses
#: one daemon across its actions and never touches UI browser sessions.
RECORDING_SESSION_PREFIX = "live-record"


class ActionResultRequest(BaseModel):
    take_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    status: str = Field(pattern="^(SUCCESS|FAILURE)$")
    execution_id: str = Field(min_length=1)
    t: float = Field(ge=0)
    detail: str = ""
    before_hash_observed: Optional[str] = None
    after_hash_observed: Optional[str] = None
    observed: Dict[str, Any] = Field(default_factory=dict)
    scene_id: Optional[str] = None
    cue_id: Optional[str] = None


class ActionExecuteRequest(BaseModel):
    """Server-side execution envelope (RUN_COMMAND / TOOL_RUN)."""

    cwd: Optional[str] = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=MAX_COMMAND_TIMEOUT_SECONDS)


def _require_action_type(action: Dict[str, Any], allowed: set[str], action_id: str) -> None:
    from windagent_core.contracts.live_record.errors import (
        LiveRecordValidationError,
    )

    if action["type"] not in allowed:
        raise LiveRecordValidationError(
            f"ACTION_NOT_SERVER_EXECUTABLE: '{action['type']}' executes on the "
            "desktop (code playback), not on the API host.",
            details={"action_id": action_id, "type": action["type"]},
        )


@router.post("/{plan_id}/actions/{action_id}/prepare")
async def prepare_action(
    plan_id: str = Path(..., min_length=1),
    action_id: str = Path(..., min_length=1),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Resolve a frozen prepared action into a desktop dispatch ticket."""
    return await service.prepare_action_dispatch(
        plan_id_raw=plan_id, action_id_raw=action_id
    )


@router.post("/{plan_id}/actions/{action_id}/execute")
async def execute_action(
    plan_id: str = Path(..., min_length=1),
    action_id: str = Path(..., min_length=1),
    body: ActionExecuteRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Server-side execution — RUN_COMMAND / TOOL_RUN via the SafeShellRunner.

    The command line is resolved from the frozen plan's payload bundle, never
    from request args; the caller cannot smuggle arbitrary shell text through
    this endpoint (Constrained Action Gate).
    """
    ticket = await service.prepare_action_dispatch(
        plan_id_raw=plan_id, action_id_raw=action_id
    )
    action = ticket["action"]
    _require_action_type(action, {"RUN_COMMAND", "TOOL_RUN"}, action_id)

    command_line = ticket.get("payload_text") or action.get("command_ref") or ""
    if not command_line:
        from windagent_core.contracts.live_record.errors import (
            LiveRecordValidationError,
        )

        raise LiveRecordValidationError(
            f"COMMAND_PAYLOAD_MISSING: no prepared command line for '{action_id}'.",
            details={"action_id": action_id},
        )

    from windagent_tools.shell.runner import SafeShellRunner

    import os

    workspace_root = os.getenv("WINDAGENT_LIVE_RECORD_WORKSPACE", os.getcwd())
    runner = SafeShellRunner(
        workspace_root=workspace_root,
        default_timeout_seconds=body.timeout_seconds,
    )
    started = time.monotonic()
    returncode, stdout, stderr = await runner.execute_command(
        command_line,
        cwd=body.cwd,
        timeout_seconds=body.timeout_seconds,
    )
    elapsed_ms = (time.monotonic() - started) * 1000.0
    return {
        "action_id": action_id,
        "plan_hash": ticket["plan_hash"],
        "status": "SUCCESS" if returncode == 0 else "FAILURE",
        "exit_code": returncode,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "elapsed_ms": round(elapsed_ms, 3),
    }


class BrowserExecuteRequest(BaseModel):
    """Optional overrides — recording parameters still come from the plan."""

    timeout_seconds: float = Field(default=60.0, gt=0, le=MAX_COMMAND_TIMEOUT_SECONDS)


def _verify_url_contains(state_url: str, url_contains: Optional[str]) -> Optional[bool]:
    if not url_contains:
        return None
    return url_contains.lower() in (state_url or "").lower()


async def _execute_browser_action(
    *,
    request: Request,
    ticket: Dict[str, Any],
    plan_id: str,
    action_id: str,
) -> Dict[str, Any]:
    """Drive the browser session service with frozen-plan parameters only."""
    from windagent_api.browser_sessions import (
        BrowserLaunchOptions,
        BrowserSessionError,
    )
    from windagent_core.contracts.live_record.errors import (
        LiveRecordValidationError,
    )

    action = ticket["action"]
    payload_text = ticket.get("payload_text") or ""
    expected_after = ticket.get("expected_after") or {}
    url_contains = expected_after.get("url_contains")

    params: Dict[str, Any] = {}
    if action["type"] == "BROWSER_ACTION" and payload_text.strip():
        try:
            parsed = json.loads(payload_text)
            if isinstance(parsed, dict):
                params = parsed
        except json.JSONDecodeError:
            params = {}

    browser_service = getattr(request.app.state, "browser_session_service", None)
    if browser_service is None:
        raise LiveRecordValidationError(
            "BROWSER_SURFACE_UNAVAILABLE: no browser session service composed.",
            details={"action_id": action_id},
        )

    # One stable recording-scoped session per plan → a take reuses one daemon.
    session_id = f"{RECORDING_SESSION_PREFIX}-{plan_id}"

    try:
        if action["type"] == "BROWSER_NAVIGATION":
            url = (params.get("url") or payload_text or "").strip()
            if not url.lower().startswith(("http://", "https://")):
                raise LiveRecordValidationError(
                    f"BROWSER_URL_INVALID: prepared navigation target for "
                    f"'{action_id}' must be an http(s) URL.",
                    details={"action_id": action_id},
                )
            state = await browser_service.navigate(
                session_id, url, options=BrowserLaunchOptions()
            )
        else:
            operation = str(params.get("operation", "CLICK")).upper()
            if operation == "CLICK":
                target = (
                    params.get("target")
                    or action.get("browser_semantic_target")
                    or ""
                ).strip()
                if not target:
                    raise LiveRecordValidationError(
                        f"BROWSER_TARGET_MISSING: no prepared click target for "
                        f"'{action_id}'.",
                        details={"action_id": action_id},
                    )
                state = await browser_service.click_semantic(
                    session_id, target, locator=str(params.get("locator", "text"))
                )
            elif operation == "TYPE":
                selector = str(params.get("selector", "")).strip()
                text = str(params.get("text", ""))
                if not selector:
                    raise LiveRecordValidationError(
                        f"BROWSER_SELECTOR_MISSING: no prepared selector for "
                        f"'{action_id}'.",
                        details={"action_id": action_id},
                    )
                state = await browser_service.type_text(session_id, selector, text)
            elif operation == "SCROLL":
                direction = "up" if str(params.get("direction", "down")).lower() == "up" else "down"
                pixels = int(params.get("pixels", 800))
                state = await browser_service.scroll(
                    session_id, direction, pixels, require_user_control=False
                )
            else:
                raise LiveRecordValidationError(
                    f"BROWSER_OPERATION_UNSUPPORTED: operation '{operation}' for "
                    f"'{action_id}'.",
                    details={"action_id": action_id, "operation": operation},
                )
    except LiveRecordValidationError:
        raise
    except BrowserSessionError as exc:
        return {
            "action_id": action_id,
            "plan_hash": ticket["plan_hash"],
            "status": "FAILURE",
            "detail": str(exc)[:400],
            "verification": {"verified": False, "checks": [{"check": "executed", "ok": False}]},
        }

    verified = _verify_url_contains(state.url, url_contains)
    checks: list[Dict[str, Any]] = []
    ok = True
    if verified is not None:
        checks.append({"check": "url_contains", "expected": url_contains, "observed": state.url, "ok": verified})
        ok = verified

    return {
        "action_id": action_id,
        "plan_hash": ticket["plan_hash"],
        "status": "SUCCESS" if ok else "FAILURE",
        "session_id": session_id,
        "url_observed": state.url,
        "title_observed": state.title,
        "error": state.error,
        "verification": {"verified": ok, "checks": checks},
    }


@router.post("/{plan_id}/actions/{action_id}/execute-browser")
async def execute_browser_action_endpoint(
    plan_id: str = Path(..., min_length=1),
    action_id: str = Path(..., min_length=1),
    body: BrowserExecuteRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    request: Request = ...,
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Server-side BROWSER_NAVIGATION / BROWSER_ACTION execution.

    Section 14: reuse the existing browser execution layer. All targets come
    from the frozen plan's payload bundle / semantic fields; the response
    verifies ``expected_after.url_contains`` against the observed URL.
    """
    del body  # reserved for future overrides; parameters stay plan-frozen
    ticket = await service.prepare_action_dispatch(
        plan_id_raw=plan_id, action_id_raw=action_id
    )
    action = ticket["action"]
    _require_action_type(action, {"BROWSER_NAVIGATION", "BROWSER_ACTION"}, action_id)
    return await _execute_browser_action(
        request=request, ticket=ticket, plan_id=plan_id, action_id=action_id
    )


@router.post("/{plan_id}/actions/result")
async def record_action_result(
    plan_id: str = Path(..., min_length=1),
    body: ActionResultRequest = ...,
    idempotency_key: str = Depends(require_idempotency_key),
    service: LiveRecordApplicationService = Depends(get_live_record_service),
) -> dict:
    """Verify a desktop-executed action and append its timeline event."""
    return await service.record_action_result(
        plan_id_raw=plan_id,
        take_id_raw=body.take_id,
        action_id_raw=body.action_id,
        status=body.status,
        execution_id=body.execution_id,
        idempotency_key=idempotency_key,
        t=body.t,
        detail=body.detail,
        before_hash_observed=body.before_hash_observed,
        after_hash_observed=body.after_hash_observed,
        observed=body.observed,
        scene_id=body.scene_id,
        cue_id=body.cue_id,
    )


__all__ = ["router"]
