"""
Durable Execution Facts Data Structure for WindAgent Architecture V2.
Captures task state, step counters, retry counts, errors, and derives UI display status deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from windagent_core.domain.types import TaskId, SessionId
from windagent_orchestration.state_machine import TaskState


@dataclass
class DurableExecutionFacts:
    task_id: TaskId
    session_id: SessionId
    current_state: TaskState = TaskState.RECEIVED
    version: int = 1
    current_step: int = 0
    total_steps: int = 0
    last_sequence: int = 0
    pending_permission: bool = False
    retry_count: int = 0
    last_error: Optional[str] = None
    verification_state: str = "none"
    priority: int = 2
    project_id: Optional[str] = None
    worktree_id: Optional[str] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def derive_ui_status(self) -> str:
        """Derives UI display status deterministically from durable execution facts."""
        if self.current_state == TaskState.WAITING_PERMISSION or self.pending_permission:
            return "waiting_permission"
        if self.current_state == TaskState.PAUSED:
            return "paused"
        if self.current_state == TaskState.RETRY_WAIT:
            return f"retrying (attempt {self.retry_count})"
        if self.current_state == TaskState.VERIFYING:
            return "verifying"
        if self.current_state == TaskState.COMPLETED:
            return "completed"
        if self.current_state in (TaskState.FAILED, TaskState.CANCELLED):
            return self.current_state.value
        return "running"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["task_id"] = str(self.task_id)
        d["session_id"] = str(self.session_id)
        d["current_state"] = self.current_state.value if isinstance(self.current_state, TaskState) else str(self.current_state)
        d["updated_at"] = self.updated_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DurableExecutionFacts:
        state_val = data.get("current_state", "received")
        try:
            state_enum = TaskState(state_val)
        except ValueError:
            state_enum = TaskState.RECEIVED

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            dt = datetime.fromisoformat(updated_at)
        else:
            dt = datetime.now(timezone.utc)

        return cls(
            task_id=TaskId(data["task_id"]) if isinstance(data.get("task_id"), str) else data["task_id"],
            session_id=SessionId(data["session_id"]) if isinstance(data.get("session_id"), str) else data["session_id"],
            current_state=state_enum,
            version=data.get("version", 1),
            current_step=data.get("current_step", 0),
            total_steps=data.get("total_steps", 0),
            last_sequence=data.get("last_sequence", 0),
            pending_permission=data.get("pending_permission", False),
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
            verification_state=data.get("verification_state", "none"),
            priority=data.get("priority", 2),
            project_id=data.get("project_id"),
            worktree_id=data.get("worktree_id"),
            updated_at=dt,
        )
