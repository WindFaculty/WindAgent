"""
Execution Runtime Port and Contract Definitions for WindAgent Architecture V2.
Defines abstract contracts for execution requests, handles, runtime status, and results.
Pure Python protocols with ZERO framework or infrastructure dependencies.
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


@runtime_checkable
class ExecutionRuntimePort(Protocol):
    """Port interface for executing workflow steps via downstream runtimes."""

    async def dispatch(self, request: ExecutionRequest) -> ExecutionHandle:
        """Dispatches execution request to downstream runtime."""
        ...

    async def get_status(self, handle: ExecutionHandle) -> RuntimeStatus:
        """Queries current runtime execution status."""
        ...

    async def cancel(self, handle: ExecutionHandle) -> None:
        """Cancels running execution on downstream runtime."""
        ...

    async def get_result(self, handle: ExecutionHandle) -> ExecutionResult:
        """Retrieves terminal execution result."""
        ...

    async def reattach(self, runtime_run_id: str) -> ExecutionHandle | None:
        """Reattaches to existing runtime handle after engine restart."""
        ...
