"""
Durable Execution Request definitions for WindAgent Execution Subsystem V2 (Phase 18).
Extends base ExecutionRequest with idempotency key, lease generation, fencing token, deadline, and permission context.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
import uuid


@dataclass
class DurableExecutionRequest:
    step_run_id: str
    workflow_run_id: str
    tool_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    attempt_id: str = "att_1"
    idempotency_key: str = field(default_factory=lambda: f"idem_{uuid.uuid4().hex[:12]}")
    lease_generation: int = 1
    fencing_token: str = field(default_factory=lambda: f"fence_{uuid.uuid4().hex[:12]}")
    deadline_at: Optional[datetime] = None
    is_destructive: bool = False
    permission_context: Dict[str, Any] = field(default_factory=dict)
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_run_id": self.step_run_id,
            "workflow_run_id": self.workflow_run_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "attempt_id": self.attempt_id,
            "idempotency_key": self.idempotency_key,
            "lease_generation": self.lease_generation,
            "fencing_token": self.fencing_token,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "is_destructive": self.is_destructive,
            "permission_context": self.permission_context,
            "context": self.context,
        }
