"""
Route Lock — persistent sticky-model record for Phase 7.

A RouteLockRecord represents the first-turn canonical model selection for a
scope (session / task / workflow).  Once created it must not change the
canonical_model_id for the lifetime of the scope.

Locks are designed to survive process restart: the service serialises them
to a dict that can be persisted to DB or distributed cache, and reconstructs
them on the next read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class LockScope(str, Enum):
    """Granularity of the route lock."""

    SESSION = "session"
    TASK = "task"
    WORKFLOW = "workflow"


class LockStatus(str, Enum):
    """Lifecycle state of a route lock."""

    ACTIVE = "active"
    RELEASED = "released"


@dataclass
class RoutingSnapshot:
    """
    Captures which rule produced the canonical model selection.
    Stored inside the lock so that later rule updates do not confuse callers.
    """

    rule_id: str
    rule_version: int
    canonical_model_id: str
    selected_at: float = field(default_factory=time.time)
    reason: str = ""


@dataclass
class RouteLockRecord:
    """
    Persistent record of a canonical-model lock for one scope.

    Fields
    ------
    lock_id             : Unique lock identifier.
    scope               : LockScope enum value.
    scope_id            : Application-level scope identifier (session_id, task_id …).
    canonical_model_id  : Locked model.  MUST NOT change after creation.
    routing_snapshot    : Preserves which rule/version made the decision.
    status              : ACTIVE or RELEASED.
    created_at          : Unix timestamp.
    released_at         : Unix timestamp if released.
    reselection_count   : How many explicit reselections have occurred.
    """

    lock_id: str
    scope: str
    scope_id: str
    canonical_model_id: str
    routing_snapshot: RoutingSnapshot

    status: str = LockStatus.ACTIVE.value
    created_at: float = field(default_factory=time.time)
    released_at: Optional[float] = None
    reselection_count: int = 0

    # ------------------------------------------------------------------ #
    # Convenience predicates
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        return self.status == LockStatus.ACTIVE.value

    # ------------------------------------------------------------------ #
    # Serialisation (for persistence / distributed cache)
    # ------------------------------------------------------------------ #

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "scope": self.scope,
            "scope_id": self.scope_id,
            "canonical_model_id": self.canonical_model_id,
            "routing_snapshot": {
                "rule_id": self.routing_snapshot.rule_id,
                "rule_version": self.routing_snapshot.rule_version,
                "canonical_model_id": self.routing_snapshot.canonical_model_id,
                "selected_at": self.routing_snapshot.selected_at,
                "reason": self.routing_snapshot.reason,
            },
            "status": self.status,
            "created_at": self.created_at,
            "released_at": self.released_at,
            "reselection_count": self.reselection_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RouteLockRecord":
        snap_d = d["routing_snapshot"]
        snapshot = RoutingSnapshot(
            rule_id=snap_d["rule_id"],
            rule_version=snap_d["rule_version"],
            canonical_model_id=snap_d["canonical_model_id"],
            selected_at=snap_d["selected_at"],
            reason=snap_d.get("reason", ""),
        )
        return cls(
            lock_id=d["lock_id"],
            scope=d["scope"],
            scope_id=d["scope_id"],
            canonical_model_id=d["canonical_model_id"],
            routing_snapshot=snapshot,
            status=d["status"],
            created_at=d["created_at"],
            released_at=d.get("released_at"),
            reselection_count=d.get("reselection_count", 0),
        )


# Alias for public API clarity
RouteLock = RouteLockRecord
