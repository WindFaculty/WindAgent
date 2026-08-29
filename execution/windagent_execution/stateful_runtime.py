"""
Stateful Runtime / Session Adapter for WindAgent V3 Phase 3.

Implements the eight operations defined in
``windagent_core.contracts.stateful_execution.StatefulExecutionRuntime``
over the existing execution contracts. Checkpoints are JSON-serializable
opaque runtime state; restored sessions preserve runtime state but never
host authority (credentials, provider routing, scheduling, memory-learning,
promotion). No storage/provider credential handling lives here.

This is an in-memory adapter suitable for unit/component tests and as the
V1 substrate for future PersistentPython/WASM/Container adapters.
"""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from windagent_core.contracts.execution import ExecutionHandle
from windagent_core.contracts.stateful_execution import (
    AttachSessionRequest,
    CancelRequest,
    CheckpointRequest,
    CreateSessionRequest,
    InspectRequest,
    RestoreRequest,
    SessionCheckpoint,
    SessionInspection,
    StatefulExecuteRequest,
    StatefulSessionHandle,
    StatefulSessionStatus,
    TerminateRequest,
)


# Host-authority keys that must never be accepted or persisted by the runtime.
_FORBIDDEN_HOST_AUTHORITY_KEYS = {
    "provider_credentials",
    "credentials",
    "credential",
    "api_key",
    "apikey",
    "secret",
    "secrets",
    "provider_call",
    "provider_routing",
    "provider_token",
    "schedule",
    "scheduling",
    "memory_write",
    "memory_writes",
    "learning_promotion",
    "promotion",
    "host_authority",
    "authority",
    "session_lifecycle_authority",
    "session_lifecycle",
    "privileged",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _contains_forbidden(data: Any, _depth: int = 0) -> str | None:
    """Recursively detect forbidden host-authority keys. Returns offending key or None."""
    if _depth > 10:
        return None
    if isinstance(data, dict):
        for k, v in data.items():
            kl = str(k).lower()
            if kl in _FORBIDDEN_HOST_AUTHORITY_KEYS:
                return str(k)
            inner = _contains_forbidden(v, _depth + 1)
            if inner:
                return inner
    elif isinstance(data, (list, tuple)):
        for item in data:
            inner = _contains_forbidden(item, _depth + 1)
            if inner:
                return inner
    return None


def _assert_no_host_authority(payload: Dict[str, Any] | None, context: str = "payload") -> None:
    if not payload:
        return
    offending = _contains_forbidden(payload)
    if offending:
        raise ValueError(
            f"Host authority field '{offending}' is not allowed in {context}; "
            f"runtime is only a substrate and must never accept or persist host authority."
        )


def _ensure_json_serializable(obj: Any, context: str = "checkpoint runtime_state") -> None:
    try:
        json.dumps(obj)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be JSON-serializable (opaque): {exc}") from exc


def _sanitize_runtime_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep-copied state with any forbidden host-authority keys stripped."""
    cleaned = copy.deepcopy(state)

    def _strip(d: Any) -> Any:
        if isinstance(d, dict):
            out: Dict[str, Any] = {}
            for kk, vv in d.items():
                if str(kk).lower() in _FORBIDDEN_HOST_AUTHORITY_KEYS:
                    continue
                out[kk] = _strip(vv)
            return out
        if isinstance(d, list):
            return [_strip(x) for x in d]
        return d

    return _strip(cleaned)


@dataclass
class _SessionRecord:
    session_id: str
    runtime_session_id: str
    workflow_run_id: str
    status: StatefulSessionStatus
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    fencing_token: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    runtime_state: Dict[str, Any] = field(default_factory=dict)
    handle_ids: List[str] = field(default_factory=list)
    checkpoint_ids: List[str] = field(default_factory=list)


class StatefulExecutionRuntime:
    """In-memory stateful runtime adapter implementing the 8-op protocol.

    Args:
        store: Optional shared backing store ``{"sessions":{}, "checkpoints":{}, "handles":{}}``.
               When the same dict is passed to two runtime instances, sessions
               survive manager recreation and can be re-attached.
        execution_adapter: Optional underlying ``ExecutionRuntimePort`` to which
               ``execute`` is delegated. When absent, execution is simulated
               in-memory while preserving handle contracts.
    """

    def __init__(
        self,
        *,
        store: Optional[Dict[str, Dict[str, Any]]] = None,
        execution_adapter: Any | None = None,
    ) -> None:
        if store is None:
            store = {"sessions": {}, "checkpoints": {}, "handles": {}}
        store.setdefault("sessions", {})
        store.setdefault("checkpoints", {})
        store.setdefault("handles", {})
        self._store = store
        self._sessions: Dict[str, _SessionRecord] = store["sessions"]  # type: ignore[assignment]
        self._checkpoints: Dict[str, SessionCheckpoint] = store["checkpoints"]  # type: ignore[assignment]
        self._handles: Dict[str, ExecutionHandle] = store["handles"]  # type: ignore[assignment]
        self._execution_adapter = execution_adapter

    def _require_session(self, session_id: str) -> _SessionRecord:
        rec = self._sessions.get(session_id)
        if rec is None:
            raise KeyError(f"unknown session: {session_id}")
        if rec.status == StatefulSessionStatus.TERMINATED:
            raise RuntimeError(f"session [{session_id}] is terminated and cannot be used")
        return rec

    def _to_handle(self, rec: _SessionRecord) -> StatefulSessionHandle:
        return StatefulSessionHandle(
            session_id=rec.session_id,
            runtime_session_id=rec.runtime_session_id,
            workflow_run_id=rec.workflow_run_id,
            status=rec.status,
            created_at=rec.created_at,
            last_activity_at=rec.last_activity_at,
            fencing_token=rec.fencing_token,
            metadata=copy.deepcopy(rec.metadata),
        )

    async def create_session(self, request: CreateSessionRequest) -> StatefulSessionHandle:
        _assert_no_host_authority(request.capabilities, "capabilities")
        _assert_no_host_authority(request.metadata, "metadata")
        session_id = request.session_id or f"sess_{uuid.uuid4().hex[:10]}"
        if session_id in self._sessions and self._sessions[session_id].status != StatefulSessionStatus.TERMINATED:
            raise ValueError(f"session [{session_id}] already exists and is not terminated")
        now = _utc_now()
        rec = _SessionRecord(
            session_id=session_id,
            runtime_session_id=f"rt_{uuid.uuid4().hex[:10]}",
            workflow_run_id=request.workflow_run_id,
            status=StatefulSessionStatus.ACTIVE,
            created_at=now,
            last_activity_at=now,
            fencing_token=request.fencing_token,
            metadata=copy.deepcopy(request.metadata or {}),
            capabilities=copy.deepcopy(request.capabilities or {}),
            runtime_state={
                "execution_count": 0,
                "history": [],
                "capabilities_snapshot": copy.deepcopy(request.capabilities or {}),
            },
        )
        rec.metadata = _sanitize_runtime_state(rec.metadata)
        rec.capabilities = _sanitize_runtime_state(rec.capabilities)
        rec.runtime_state = _sanitize_runtime_state(rec.runtime_state)
        self._sessions[session_id] = rec
        return self._to_handle(rec)

    async def attach_session(self, request: AttachSessionRequest) -> StatefulSessionHandle:
        rec = self._require_session(request.session_id)
        rec.last_activity_at = _utc_now()
        if rec.status == StatefulSessionStatus.IDLE:
            rec.status = StatefulSessionStatus.ACTIVE
        if request.fencing_token:
            rec.fencing_token = request.fencing_token
        return self._to_handle(rec)

    async def execute(self, request: StatefulExecuteRequest) -> ExecutionHandle:
        _assert_no_host_authority(request.parameters, "parameters")
        rec = self._require_session(request.session_id)
        if rec.status == StatefulSessionStatus.CANCELLED:
            raise RuntimeError(f"session [{request.session_id}] is cancelled; execute is not allowed")
        rec.runtime_state["execution_count"] = int(rec.runtime_state.get("execution_count", 0)) + 1
        history = rec.runtime_state.setdefault("history", [])
        history.append(
            {
                "step_run_id": request.step_run_id,
                "tool_name": request.tool_name,
                "attempt_id": request.attempt_id,
                "at": _utc_now().isoformat(),
            }
        )
        rec.last_activity_at = _utc_now()
        rec.runtime_state = _sanitize_runtime_state(rec.runtime_state)

        if self._execution_adapter is not None and hasattr(self._execution_adapter, "dispatch"):
            from windagent_core.contracts.execution import ExecutionRequest

            exec_req = ExecutionRequest(
                step_run_id=request.step_run_id,
                workflow_run_id=rec.workflow_run_id,
                tool_name=request.tool_name,
                parameters=copy.deepcopy(request.parameters or {}),
                attempt_id=request.attempt_id,
                fencing_token=request.fencing_token or rec.fencing_token,
                context={"runtime_session_id": rec.runtime_session_id},
            )
            handle = await self._execution_adapter.dispatch(exec_req)
            if not handle.runtime_session_id:
                handle.runtime_session_id = rec.runtime_session_id
            self._handles[handle.handle_id] = handle
            rec.handle_ids.append(handle.handle_id)
            return handle

        handle_id = f"hdl_{uuid.uuid4().hex[:8]}"
        runtime_run_id = f"run_{uuid.uuid4().hex[:8]}"
        handle = ExecutionHandle(
            handle_id=handle_id,
            runtime_run_id=runtime_run_id,
            step_run_id=request.step_run_id,
            attempt_id=request.attempt_id,
            fencing_token=request.fencing_token or rec.fencing_token,
            runtime_session_id=rec.runtime_session_id,
        )
        self._handles[handle_id] = handle
        rec.handle_ids.append(handle_id)
        return handle

    async def checkpoint(self, request: CheckpointRequest) -> SessionCheckpoint:
        rec = self._require_session(request.session_id)
        runtime_state = _sanitize_runtime_state(copy.deepcopy(rec.runtime_state))
        _ensure_json_serializable(runtime_state, "checkpoint runtime_state")
        checkpoint_id = request.checkpoint_id or f"ckpt_{uuid.uuid4().hex[:8]}"
        if checkpoint_id in self._checkpoints:
            raise ValueError(f"checkpoint [{checkpoint_id}] already exists")
        now = _utc_now()
        ckpt = SessionCheckpoint(
            checkpoint_id=checkpoint_id,
            session_id=rec.session_id,
            runtime_state=copy.deepcopy(runtime_state),
            created_at=now,
            fencing_token=request.fencing_token or rec.fencing_token,
        )
        _ensure_json_serializable(
            {"checkpoint_id": ckpt.checkpoint_id, "session_id": ckpt.session_id, "runtime_state": ckpt.runtime_state},
            "checkpoint envelope",
        )
        # Store a deep copy so mutating the returned object does not affect the store (immutability)
        stored = SessionCheckpoint(
            checkpoint_id=ckpt.checkpoint_id,
            session_id=ckpt.session_id,
            runtime_state=copy.deepcopy(ckpt.runtime_state),
            created_at=ckpt.created_at,
            fencing_token=ckpt.fencing_token,
        )
        self._checkpoints[checkpoint_id] = stored
        rec.checkpoint_ids.append(checkpoint_id)
        rec.last_activity_at = now
        # Return a deep copy distinct from stored
        return copy.deepcopy(ckpt)

    async def restore(self, request: RestoreRequest) -> StatefulSessionHandle:
        ckpt = self._checkpoints.get(request.checkpoint_id)
        if ckpt is None:
            raise KeyError(f"unknown checkpoint: {request.checkpoint_id}")
        restored_state = _sanitize_runtime_state(copy.deepcopy(ckpt.runtime_state))
        _ensure_json_serializable(restored_state, "restored runtime_state")
        target_id = request.target_session_id or ckpt.session_id
        if target_id in self._sessions:
            rec = self._sessions[target_id]
            if rec.status == StatefulSessionStatus.TERMINATED:
                raise RuntimeError(f"cannot restore into terminated session [{target_id}]")
            rec.runtime_state = copy.deepcopy(restored_state)
            rec.last_activity_at = _utc_now()
            if rec.status == StatefulSessionStatus.CANCELLED:
                rec.status = StatefulSessionStatus.ACTIVE
            if request.fencing_token:
                rec.fencing_token = request.fencing_token
            return self._to_handle(rec)
        orig_rec = self._sessions.get(ckpt.session_id)
        workflow_run_id = orig_rec.workflow_run_id if orig_rec else f"wf_restored_{uuid.uuid4().hex[:6]}"
        now = _utc_now()
        rec = _SessionRecord(
            session_id=target_id,
            runtime_session_id=f"rt_{uuid.uuid4().hex[:10]}",
            workflow_run_id=workflow_run_id,
            status=StatefulSessionStatus.ACTIVE,
            created_at=now,
            last_activity_at=now,
            fencing_token=request.fencing_token or ckpt.fencing_token,
            metadata={},
            capabilities={},
            runtime_state=copy.deepcopy(restored_state),
            handle_ids=[],
            checkpoint_ids=[],
        )
        self._sessions[target_id] = rec
        return self._to_handle(rec)

    async def inspect(self, request: InspectRequest) -> SessionInspection:
        # Allow inspection even for terminated sessions — host needs observability
        rec = self._sessions.get(request.session_id)
        if rec is None:
            raise KeyError(f"unknown session: {request.session_id}")
        summary = _sanitize_runtime_state(copy.deepcopy(rec.runtime_state))
        _ensure_json_serializable(summary, "inspection runtime_state_summary")
        return SessionInspection(
            session_id=rec.session_id,
            status=rec.status,
            created_at=rec.created_at,
            last_activity_at=rec.last_activity_at,
            active_handle_ids=list(rec.handle_ids),
            checkpoint_ids=list(rec.checkpoint_ids),
            runtime_state_summary=copy.deepcopy(summary),
            fencing_token=rec.fencing_token,
        )

    async def cancel(self, request: CancelRequest) -> StatefulSessionHandle | None:
        if request.handle_id:
            h = self._handles.get(request.handle_id)
            if h is None:
                raise KeyError(f"unknown handle: {request.handle_id}")
            for rec in self._sessions.values():
                if request.handle_id in rec.handle_ids:
                    cancelled = rec.runtime_state.setdefault("cancelled_handles", [])
                    if request.handle_id not in cancelled:
                        cancelled.append(request.handle_id)
                    rec.last_activity_at = _utc_now()
                    _ensure_json_serializable(rec.runtime_state, "runtime_state after handle cancel")
                    break
            return None
        if not request.session_id:
            raise ValueError("cancel requires either session_id or handle_id")
        rec = self._require_session(request.session_id)
        if rec.status == StatefulSessionStatus.TERMINATED:
            raise RuntimeError(f"session [{request.session_id}] already terminated")
        rec.status = StatefulSessionStatus.CANCELLED
        rec.last_activity_at = _utc_now()
        return self._to_handle(rec)

    async def terminate(self, request: TerminateRequest) -> None:
        rec = self._sessions.get(request.session_id)
        if rec is None:
            raise KeyError(f"unknown session: {request.session_id}")
        if rec.status == StatefulSessionStatus.TERMINATED:
            return
        rec.status = StatefulSessionStatus.TERMINATED
        rec.last_activity_at = _utc_now()

    def snapshot_store(self) -> Dict[str, Any]:
        return {
            "sessions": copy.deepcopy(self._sessions),
            "checkpoints": copy.deepcopy(self._checkpoints),
            "handles": copy.deepcopy(self._handles),
        }


__all__ = ["StatefulExecutionRuntime", "_SessionRecord"]
