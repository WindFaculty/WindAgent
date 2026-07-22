"""
Route Lock Data Structure for WindAgent Architecture V2.
Binds a task/run to a specific model routing decision, fallback chain, and audit log.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import TaskId, RunId, SessionId


def default_utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RouteLock:
    session_id: SessionId
    task_id: TaskId
    canonical_model: str
    provider_name: str
    fallback_chain: List[str] = field(default_factory=list)
    selection_reasons: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    policy_version: str = "2.0"
    created_at: datetime = field(default_factory=default_utc_now)
    run_id: Optional[RunId] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "task_id": str(self.task_id),
            "canonical_model": self.canonical_model,
            "provider_name": self.provider_name,
            "fallback_chain": self.fallback_chain,
            "selection_reasons": self.selection_reasons,
            "estimated_cost": self.estimated_cost,
            "policy_version": self.policy_version,
            "created_at": self.created_at.isoformat(),
            "run_id": str(self.run_id) if self.run_id else None,
        }
