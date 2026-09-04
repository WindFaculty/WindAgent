"""Route locks: persistent sticky canonical-model records for one scope.

REWRITE of the frozen ``providers/windagent_providers/routing/route_lock.py``.
The canonical model of a lock MUST NOT change after creation; reselection
releases the lock and creates a new one, and model-level fallback creates a
separate pinned lock so the primary lock's decision stays auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from windagent.kernel.time import utc_now


class LockScope(StrEnum):
    """Granularity of the route lock."""

    SESSION = "session"
    TASK = "task"
    WORKFLOW = "workflow"


class LockStatus(StrEnum):
    """Lifecycle state of a route lock."""

    ACTIVE = "active"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class RoutingSnapshot:
    """Which rule (and version) produced the canonical model selection."""

    rule_id: str
    rule_version: int
    canonical_model_id: str
    selected_at: float = field(default_factory=lambda: utc_now().timestamp())
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize for durable storage inside the lock record."""
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "canonical_model_id": self.canonical_model_id,
            "selected_at": self.selected_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RoutingSnapshot:
        """Reconstruct a snapshot from its serialized form."""

        def _int(key: str) -> int:
            value = data.get(key, 0)
            return int(value) if isinstance(value, (int, float)) else 0

        def _float(key: str) -> float:
            value = data.get(key, 0.0)
            return float(value) if isinstance(value, (int, float)) else 0.0

        return cls(
            rule_id=str(data.get("rule_id", "")),
            rule_version=_int("rule_version"),
            canonical_model_id=str(data.get("canonical_model_id", "")),
            selected_at=_float("selected_at"),
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class RouteLockRecord:
    """Persistent record of a canonical-model lock for one scope.

    ``scope_type``/``scope_id`` identify the scope; the durable store
    enforces a single ACTIVE lock per scope.  ``is_fallback`` marks a
    model-level fallback lock created by the executor (P0.3.5).
    """

    lock_id: str
    scope_type: str
    scope_id: str
    canonical_model_id: str
    routing_snapshot: RoutingSnapshot

    status: str = LockStatus.ACTIVE.value
    created_at: float = field(default_factory=lambda: utc_now().timestamp())
    released_at: float | None = None
    reselection_count: int = 0
    is_fallback: bool = False
    source_lock_id: str | None = None

    @property
    def is_active(self) -> bool:
        """True while the lock still pins the canonical model."""
        return self.status == LockStatus.ACTIVE.value

    def to_dict(self) -> dict[str, object]:
        """Serialize for persistence or transport."""
        return {
            "lock_id": self.lock_id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "canonical_model_id": self.canonical_model_id,
            "routing_snapshot": self.routing_snapshot.to_dict(),
            "status": self.status,
            "created_at": self.created_at,
            "released_at": self.released_at,
            "reselection_count": self.reselection_count,
            "is_fallback": self.is_fallback,
            "source_lock_id": self.source_lock_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> RouteLockRecord:
        """Reconstruct a lock from its serialized form."""
        snapshot_data = data.get("routing_snapshot")
        snapshot = (
            RoutingSnapshot.from_dict(snapshot_data)
            if isinstance(snapshot_data, dict)
            else RoutingSnapshot(rule_id="", rule_version=0, canonical_model_id="")
        )
        released = data.get("released_at")

        def _float(key: str) -> float:
            value = data.get(key, 0.0)
            return float(value) if isinstance(value, (int, float)) else 0.0

        def _int(key: str) -> int:
            value = data.get(key, 0)
            return int(value) if isinstance(value, (int, float)) else 0

        return cls(
            lock_id=str(data.get("lock_id", "")),
            scope_type=str(data.get("scope_type", "")),
            scope_id=str(data.get("scope_id", "")),
            canonical_model_id=str(data.get("canonical_model_id", "")),
            routing_snapshot=snapshot,
            status=str(data.get("status", LockStatus.ACTIVE.value)),
            created_at=_float("created_at"),
            released_at=float(released) if isinstance(released, (int, float)) else None,
            reselection_count=_int("reselection_count"),
            is_fallback=bool(data.get("is_fallback", False)),
            source_lock_id=(
                str(data["source_lock_id"]) if data.get("source_lock_id") else None
            ),
        )


VALID_SCOPE_TYPES: Final[frozenset[str]] = frozenset(item.value for item in LockScope)
