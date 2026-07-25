"""Durable task queue port and claimed task models."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from windagent_core.domain.types import TaskId, WorkerId


@dataclass
class ClaimedTask:
    """Represents an atomically claimed task instance bound to a worker lease."""
    task_id: str
    worker_id: str
    lease_id: str
    fencing_token: str
    lease_generation: int
    tool_name: str
    prompt: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    acquired_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


@runtime_checkable
class DurableTaskQueuePort(Protocol):
    """Port for atomic task claiming and pending queue management."""
    async def claim_next(
        self,
        worker_id: str,
        lease_ttl_seconds: int = 30,
    ) -> Optional[ClaimedTask]:
        ...


__all__ = ["ClaimedTask", "DurableTaskQueuePort"]
