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


from windagent_core.contracts.execution import (
    RuntimeStatusEnum,
    ExecutionRequest,
    ExecutionHandle,
    RuntimeStatus,
    ExecutionResult,
    ExecutionRuntimePort,
)


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
