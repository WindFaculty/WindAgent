"""
Stateful Execution Runtime Contracts for WindAgent Architecture V3 (Phase 3).

Defines pure typed protocol/value objects for the eight Phase 3 operations:
create_session / attach_session / execute / checkpoint / restore / inspect / cancel / terminate.

Zero framework, storage, provider, or orchestration dependencies. All types are
JSON-serializable or explicitly opaque dict state that remains serializable.
Authoritative host concerns (credentials, provider routing, scheduling,
memory-learning, promotion) are intentionally absent from this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StatefulSessionStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    CANCELLED = "cancelled"
    TERMINATED = "terminated"
    LOST = "lost"


@dataclass
class CreateSessionRequest:
    workflow_run_id: str
    session_id: Optional[str] = None
    fencing_token: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AttachSessionRequest:
    session_id: str
    fencing_token: str = ""


@dataclass
class StatefulExecuteRequest:
    session_id: str
    step_run_id: str
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    attempt_id: str = "att_1"
    fencing_token: str = ""


@dataclass
class CheckpointRequest:
    session_id: str
    checkpoint_id: Optional[str] = None
    fencing_token: str = ""


@dataclass
class RestoreRequest:
    checkpoint_id: str
    target_session_id: Optional[str] = None
    fencing_token: str = ""


@dataclass
class InspectRequest:
    session_id: str
    fencing_token: str = ""


@dataclass
class CancelRequest:
    session_id: Optional[str] = None
    handle_id: Optional[str] = None
    fencing_token: str = ""
    reason: Optional[str] = None


@dataclass
class TerminateRequest:
    session_id: str
    fencing_token: str = ""
    reason: Optional[str] = None


@dataclass
class StatefulSessionHandle:
    session_id: str
    runtime_session_id: str
    workflow_run_id: str
    status: StatefulSessionStatus
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    fencing_token: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionCheckpoint:
    checkpoint_id: str
    session_id: str
    runtime_state: Dict[str, Any]
    created_at: datetime
    fencing_token: str = ""


@dataclass
class SessionInspection:
    session_id: str
    status: StatefulSessionStatus
    created_at: datetime
    last_activity_at: Optional[datetime] = None
    active_handle_ids: List[str] = field(default_factory=list)
    checkpoint_ids: List[str] = field(default_factory=list)
    runtime_state_summary: Optional[Dict[str, Any]] = None
    fencing_token: str = ""


@runtime_checkable
class StatefulExecutionRuntime(Protocol):
    async def create_session(self, request: CreateSessionRequest) -> StatefulSessionHandle:
        ...

    async def attach_session(self, request: AttachSessionRequest) -> StatefulSessionHandle:
        ...

    async def execute(self, request: StatefulExecuteRequest) -> Any:
        ...

    async def checkpoint(self, request: CheckpointRequest) -> SessionCheckpoint:
        ...

    async def restore(self, request: RestoreRequest) -> StatefulSessionHandle:
        ...

    async def inspect(self, request: InspectRequest) -> SessionInspection:
        ...

    async def cancel(self, request: CancelRequest) -> StatefulSessionHandle | None:
        ...

    async def terminate(self, request: TerminateRequest) -> None:
        ...


__all__ = [
    "StatefulSessionStatus",
    "CreateSessionRequest",
    "AttachSessionRequest",
    "StatefulExecuteRequest",
    "CheckpointRequest",
    "RestoreRequest",
    "InspectRequest",
    "CancelRequest",
    "TerminateRequest",
    "StatefulSessionHandle",
    "SessionCheckpoint",
    "SessionInspection",
    "StatefulExecutionRuntime",
]
