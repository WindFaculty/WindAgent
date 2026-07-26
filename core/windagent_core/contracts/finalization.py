"""
Task Finalization Contracts for WindAgent V2 (Phase 2).
Defines atomic task execution finalization data structures, exceptions, and ports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class StaleResultRejectedError(Exception):
    """Raised when a late or stale worker task finalization is rejected by CAS check."""

    def __init__(self, task_id: str, fencing_token: str, expected_version: int):
        super().__init__(
            f"STALE_RESULT_REJECTED: task={task_id}, fencing_token={fencing_token}, expected_version={expected_version}"
        )
        self.task_id = task_id
        self.fencing_token = fencing_token
        self.expected_version = expected_version


@dataclass
class FinalizeTaskExecutionRequest:
    """Input payload for atomic task execution finalization."""

    task_id: str
    worker_id: str
    lease_id: str
    fencing_token: str
    expected_task_version: int
    execution_result: Dict[str, Any]
    result_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    terminal_event: Optional[Dict[str, Any]] = None
    attempt_id: Optional[str] = None
    fencing_generation: int = 1
    terminal_state: str = "completed"

    @property
    def idempotency_key(self) -> str:
        attempt = self.attempt_id or "att-1"
        return f"{self.task_id}:{attempt}:{self.terminal_state}:{self.fencing_generation}"


@dataclass
class FinalizeTaskExecutionResult:
    """Output result of atomic task execution finalization."""

    status: str  # "COMPLETED" | "REJECTED_STALE" | "FAILED"
    task_id: str
    new_version: int
    idempotency_key: str
    error_message: Optional[str] = None
    already_finalized: bool = False


@runtime_checkable
class TaskFinalizationPort(Protocol):
    """Port for executing atomic task completion, event persistence, and lease release."""

    def finalize_task_execution(
        self, request: FinalizeTaskExecutionRequest
    ) -> FinalizeTaskExecutionResult:
        ...
