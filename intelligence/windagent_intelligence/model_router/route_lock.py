"""
Route Lock Data Structure for WindAgent Intelligence (Phase 9 Adoption).
Binds a task/run to a specific model routing decision using CanonicalModelId and RouteLockId.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from windagent_core.domain.types import (
    TaskId, RunId, SessionId, CanonicalModelId, ProviderId, RouteLockId
)
from windagent_core.domain.lifecycle import utc_now


@dataclass
class RouteLock:
    session_id: SessionId
    task_id: TaskId
    canonical_model: CanonicalModelId
    provider_name: ProviderId
    lock_id: RouteLockId = field(default_factory=RouteLockId.generate)
    fallback_chain: List[str] = field(default_factory=list)
    selection_reasons: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    policy_version: str = "2.0"
    created_at: datetime = field(default_factory=utc_now)
    run_id: Optional[RunId] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lock_id": str(self.lock_id),
            "session_id": str(self.session_id),
            "task_id": str(self.task_id),
            "canonical_model": str(self.canonical_model),
            "provider_name": str(self.provider_name),
            "fallback_chain": self.fallback_chain,
            "selection_reasons": self.selection_reasons,
            "estimated_cost": self.estimated_cost,
            "policy_version": self.policy_version,
            "created_at": self.created_at.isoformat(),
            "run_id": str(self.run_id) if self.run_id else None,
        }
