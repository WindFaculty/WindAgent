"""
Port and Protocol Definitions for Orchestration V2 Subsystem.
Defines abstract contracts for storage, execution runtimes, worker registry, and eventing.
Pure Python protocols with ZERO framework (FastAPI/HTTP/Hermes) dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from windagent_core.domain.types import TaskId, SessionId, RunId, StepId


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


@runtime_checkable
class WorkerRegistryPort(Protocol):
    """Port for worker registration and heartbeat monitoring."""

    async def register_worker(self, worker_id: str, runtime_type: str, metadata: Dict[str, Any]) -> None:
        ...

    async def heartbeat(self, worker_id: str, active_leases: int) -> bool:
        ...

    async def list_active_workers(self) -> List[Dict[str, Any]]:
        ...

    async def mark_worker_unhealthy(self, worker_id: str, reason: str) -> None:
        ...


@runtime_checkable
class TaskRepositoryPort(Protocol):
    """Port for durable task and execution facts storage."""

    async def get_facts(self, task_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def save_facts(self, facts: Dict[str, Any], expected_version: int) -> int:
        ...

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        ...


@runtime_checkable
class WorkflowRepositoryPort(Protocol):
    """Port for durable workflow runs and step runs storage."""

    async def save_run(self, run_data: Dict[str, Any]) -> None:
        ...

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def update_step_status(
        self,
        step_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        ...


@runtime_checkable
class LeaseRepositoryPort(Protocol):
    """Port for atomic execution lease management and deduplication."""

    async def acquire_lease(
        self,
        lease_id: str,
        step_id: str,
        run_id: str,
        worker_id: str,
        ttl_seconds: float,
        idempotency_key: str,
    ) -> bool:
        ...

    async def renew_lease(self, lease_id: str, worker_id: str, extension_seconds: float) -> bool:
        ...

    async def release_lease(self, lease_id: str, worker_id: str) -> bool:
        ...

    async def reclaim_expired_leases(self) -> List[str]:
        ...


@runtime_checkable
class CheckpointRepositoryPort(Protocol):
    """Port for workflow execution state checkpoints."""

    async def save_checkpoint(
        self,
        run_id: str,
        step_id: str,
        state_data: Dict[str, Any],
        cursor: int,
    ) -> None:
        ...

    async def get_latest_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        ...


@runtime_checkable
class CancellationPort(Protocol):
    """Port for durable cancellation request management."""

    async def request_cancellation(self, target_id: str, target_type: str, reason: str) -> None:
        ...

    async def is_cancelled(self, target_id: str) -> bool:
        ...
