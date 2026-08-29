"""
Execution Runtime Port and Contract Definitions for WindAgent Architecture V2.
Defines abstract contracts for execution requests, handles, runtime status, and results.
Pure Python protocols with ZERO framework or infrastructure dependencies.

Phase 3 extension: adds StatefulExecutionRuntime protocol plus typed
session/checkpoint/inspection request/result values. Keeps the existing
ExecutionRuntimePort backward compatible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class RuntimeStatusEnum(str, Enum):
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    LOST = "lost"
    UNKNOWN = "unknown"


class SessionStatusEnum(str, Enum):
    ACTIVE = "active"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


FORBIDDEN_RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        "credentials",
        "credential",
        "api_key",
        "apikey",
        "secret",
        "secrets",
        "provider_routing",
        "provider",
        "model_routing",
        "schedule",
        "scheduling",
        "memory_write",
        "memory_learning",
        "learning",
        "promotion",
        "lifecycle",
        "authoritative",
        "host_authority",
    }
)


@dataclass
class ExecutionRequest:
    step_run_id: str
    workflow_run_id: str
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    attempt_id: str = "att_1"
    lease_generation: int = 1
    fencing_token: str = ""
    is_destructive: bool = False
    context: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionHandle:
    handle_id: str
    runtime_run_id: str
    step_run_id: str
    attempt_id: str
    fencing_token: str
    runtime_session_id: Optional[str] = None


@dataclass
class RuntimeStatus:
    handle_id: str
    status: RuntimeStatusEnum
    heartbeat_at: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    handle_id: str
    step_run_id: str
    status: RuntimeStatusEnum
    result_data: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None
    error: Optional[str] = None
    error_metadata: Optional[Dict[str, Any]] = None


@dataclass
class RuntimeSession:
    session_id: str
    status: SessionStatusEnum
    created_at: datetime
    last_active_at: datetime
    runtime_name: str = "default"
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class CreateSessionRequest:
    session_id_hint: Optional[str] = None
    workflow_run_id: Optional[str] = None
    runtime_name: Optional[str] = None
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class CreateSessionResult:
    session: RuntimeSession


@dataclass
class AttachSessionRequest:
    session_id: str


@dataclass
class AttachSessionResult:
    session: RuntimeSession
    reattached: bool = True


@dataclass
class CheckpointRequest:
    session_id: str
    checkpoint_id_hint: Optional[str] = None
    opaque_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class CheckpointResult:
    checkpoint_id: str
    session_id: str
    created_at: datetime
    snapshot_ref: Optional[str] = None


@dataclass
class RestoreRequest:
    session_id: str
    checkpoint_id: str


@dataclass
class RestoreResult:
    session_id: str
    checkpoint_id: str
    restored_at: datetime
    opaque_snapshot: Optional[Dict[str, Any]] = None


@dataclass
class InspectRequest:
    session_id: Optional[str] = None
    handle_id: Optional[str] = None


@dataclass
class InspectResult:
    session_id: Optional[str]
    status: SessionStatusEnum
    handles: List[ExecutionHandle] = field(default_factory=list)
    checkpoint_ids: List[str] = field(default_factory=list)
    opaque_summary: Dict[str, Any] = field(default_factory=dict)
    last_active_at: Optional[datetime] = None


@dataclass
class TerminateRequest:
    session_id: str


@dataclass
class TerminateResult:
    session_id: str
    terminated_at: datetime
    status: SessionStatusEnum


@runtime_checkable
class ExecutionRuntimePort(Protocol):
    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle: ...
    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus: ...
    async def cancel(self, handle: ExecutionHandle) -> None: ...
    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult: ...
    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None: ...

@runtime_checkable
class StatefulExecutionRuntime(ExecutionRuntimePort, Protocol):
    async def create_session(self, request: CreateSessionRequest) -> RuntimeSession: ...
    async def attach_session(self, request: AttachSessionRequest) -> RuntimeSession | None: ...
    async def execute(self, request: ExecutionRequest) -> ExecutionHandle: ...
    async def checkpoint(self, request: CheckpointRequest) -> CheckpointResult: ...
    async def restore(self, request: RestoreRequest) -> RestoreResult: ...
    async def inspect(self, request: InspectRequest) -> InspectResult: ...
    async def terminate(self, request: TerminateRequest) -> TerminateResult: ...
