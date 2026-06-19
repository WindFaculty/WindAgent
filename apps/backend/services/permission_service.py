"""Phase 7 — Permission gate for medium / high risk tools.

Responsibilities:
  - Decide whether a given tool call needs user confirmation, based on
    the tool's static `requires_confirmation` flag plus the runtime
    `PermissionConfig`.
  - Emit `permission_request` over the EventBus and block waiting for
    a user decision (granted / denied). The decision arrives via the
    REST endpoint `POST /permissions/{request_id}/decide` or via a
    WebSocket control message.
  - Audit every decision (granted/denied/timeout) by emitting a
    `permission_granted` / `permission_denied` event that the Phase 2
    hook mirrors into `execution_events`.

The gate is consulted by the WorkflowRunner immediately before calling
`ToolExecutor.execute()`. If denied, the runner marks the step
`cancelled` and continues with the next step (no workflow failure).

Threading note: `request_permission` waits on a `threading.Event`,
which lets `resolve_permission` be called safely from a different
thread or event loop (e.g. the FastAPI sync TestClient thread).
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
from uuid import UUID

from schemas.event import (
    EventEnvelope,
    PermissionDecisionData,
    PermissionRequestData,
)
from services.event_bus import EventBus
from services.tool_registry import ToolInfo


log = logging.getLogger(__name__)


# ---------- Config ----------

@dataclass
class PermissionConfig:
    """User-tunable permission policy. Defaults follow plan §7.2."""

    safe_mode: bool = False
    """When True, every tool with requires_confirmation=True always
    asks for confirmation, regardless of other flags."""

    confirm_before_type: bool = True
    """For type_text: confirm before running."""

    confirm_before_click: bool = True
    """For click_xy: confirm before running."""

    type_text_length_threshold: int = 20
    """type_text messages longer than this many chars are always
    confirmed (regardless of safe_mode)."""

    sensitive_keywords: Tuple[str, ...] = (
        "password", "passwd", "token", "secret",
        "api_key", "apikey", "credential", "private_key",
    )
    """Substrings (lower-case) that always trigger type_text confirm."""

    request_timeout_s: float = 60.0
    """How long to wait for a user decision before defaulting to deny."""

    def needs_confirmation(
        self, tool_info: ToolInfo, params: Dict[str, Any]
    ) -> bool:
        """Return True iff this specific call must be confirmed."""
        if not tool_info.requires_confirmation:
            return False
        if self.safe_mode:
            return True

        if tool_info.name == "type_text":
            if not self.confirm_before_type:
                return False
            text = str(params.get("text", ""))
            if not text:
                return False
            if len(text) > self.type_text_length_threshold:
                return True
            low = text.lower()
            for kw in self.sensitive_keywords:
                if kw in low:
                    return True
            return False  # short + no sensitive keyword → no confirm

        if tool_info.name == "click_xy":
            return self.confirm_before_click

        # Other tools with requires_confirmation=True (e.g. future high-risk).
        return True


# ---------- Pending request record ----------

@dataclass
class _PendingRequest:
    request_id: UUID
    session_id: UUID
    step_id: UUID
    tool_name: str
    event: threading.Event
    granted: bool = False


# ---------- Service ----------

class PermissionService:
    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[PermissionConfig] = None,
    ) -> None:
        self._bus = event_bus
        self._config = config or PermissionConfig()
        self._pending: Dict[UUID, _PendingRequest] = {}
        self._lock = asyncio.Lock()

    @property
    def config(self) -> PermissionConfig:
        return self._config

    def update_config(self, **kwargs: Any) -> None:
        """Replace config fields. Used by /permissions/config."""
        for key, value in kwargs.items():
            if not hasattr(self._config, key):
                raise AttributeError(f"unknown config key {key!r}")
            setattr(self._config, key, value)

    def config_dict(self) -> Dict[str, Any]:
        return {
            "safe_mode": self._config.safe_mode,
            "confirm_before_type": self._config.confirm_before_type,
            "confirm_before_click": self._config.confirm_before_click,
            "type_text_length_threshold": self._config.type_text_length_threshold,
            "request_timeout_s": self._config.request_timeout_s,
        }

    def needs_confirmation(
        self, tool_info: ToolInfo, params: Dict[str, Any]
    ) -> bool:
        return self._config.needs_confirmation(tool_info, params)

    def pending_count(self, session_id: Optional[UUID] = None) -> int:
        if session_id is None:
            return len(self._pending)
        return sum(
            1 for r in self._pending.values() if r.session_id == session_id
        )

    async def request_permission(
        self,
        *,
        session_id: UUID,
        step_id: UUID,
        tool_info: ToolInfo,
        params: Dict[str, Any],
        nowait: bool = False,
    ) -> Tuple[bool, UUID]:
        """Block until the user grants or denies.

        Returns (granted, request_id).
        If `nowait=True` (used by tests), auto-denies after emitting
        the request so the runner does not block.

        Audit: `permission_request` is emitted immediately; the
        resolution (`permission_granted` / `permission_denied`) is
        emitted from `resolve_permission` so the WS subscriber sees
        the same decision that the runner awaits.
        """
        request_id = uuid.uuid4()
        env = EventEnvelope(
            event="permission_request",
            data=PermissionRequestData(
                session_id=session_id,
                step_id=step_id,
                request_id=request_id,
                tool_name=tool_info.name,
                risk_level=tool_info.risk_level,  # type: ignore[arg-type]
                summary=tool_info.description,
                params=dict(params),
            ).model_dump(mode="json"),
        )
        await self._bus.publish(str(session_id), env)

        if nowait:
            # Test helper — never block the runner.
            log.info(
                "permission request %s auto-denied (nowait)",
                request_id,
            )
            await self._publish_decision(
                request_id=request_id,
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_info.name,
                granted=False,
                reason="nowait",
            )
            return False, request_id

        loop = asyncio.get_running_loop()
        event = threading.Event()
        async with self._lock:
            self._pending[request_id] = _PendingRequest(
                request_id=request_id,
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_info.name,
                event=event,
            )

        # `event.wait(timeout)` releases the executor thread on timeout,
        # so the run_in_executor future completes even when nobody
        # resolves the request. Without this the executor thread would
        # hang on event.wait() forever and the loop would never close.
        timeout_s = self._config.request_timeout_s

        def _wait_with_timeout() -> bool:
            return event.wait(timeout=timeout_s)

        timed_out = False
        try:
            await loop.run_in_executor(None, _wait_with_timeout)
            if not event.is_set():
                timed_out = True
                raise asyncio.TimeoutError()
            granted = self._pending[request_id].granted
        except asyncio.TimeoutError:
            timed_out = True
            granted = False
            log.warning(
                "permission request %s timed out, defaulting to deny",
                request_id,
            )
            await self._publish_decision(
                request_id=request_id,
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_info.name,
                granted=False,
                reason="timeout",
            )
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

        return granted, request_id

    async def resolve_permission(
        self,
        request_id: UUID,
        *,
        granted: bool,
    ) -> bool:
        """Resolve a pending request. Returns True if a waiter was woken.

        Idempotent — calling twice is a no-op the second time.
        Safe to call from any thread / event loop.
        """
        async with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            log.warning(
                "resolve_permission: request_id=%s not found (have %s)",
                request_id,
                list(self._pending.keys()),
            )
            return False
        if req.event.is_set():
            return False

        req.granted = granted
        req.event.set()
        await self._publish_decision(
            request_id=request_id,
            session_id=req.session_id,
            step_id=req.step_id,
            tool_name=req.tool_name,
            granted=granted,
            reason=None,
        )
        return True

    async def _publish_decision(
        self,
        *,
        request_id: UUID,
        session_id: UUID,
        step_id: UUID,
        tool_name: str,
        granted: bool,
        reason: Optional[str],
    ) -> None:
        event_name = "permission_granted" if granted else "permission_denied"
        env = EventEnvelope(
            event=event_name,
            data=PermissionDecisionData(
                session_id=session_id,
                step_id=step_id,
                tool_name=tool_name,
                reason=reason,
            ).model_dump(mode="json"),
        )
        await self._bus.publish(str(session_id), env)
        log.info(
            "permission %s request_id=%s step_id=%s tool=%s reason=%s",
            "granted" if granted else "denied",
            request_id,
            step_id,
            tool_name,
            reason or "user",
        )