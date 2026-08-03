"""
Cancellation management for the Durable Production Workflow (plan 05 §8.6).

Rules enforced here:

- cancel stops NEW scheduling (the engine/scheduler stop producing steps);
- an active provider operation transitions to cancel/reconcile according to
  REAL provider capability — WindAgent never claims the external job stopped
  without evidence;
- artifacts that already completed keep their provenance but are NOT
  auto-published;
- cancel reason / actor / timestamp are audited in an append-only log.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from windagent_core.errors.exceptions import DomainError

from windagent_orchestration.production.states import ProductionRunState


@dataclass
class CancelAuditEntry:
    cancel_id: str
    run_id: str
    actor: str
    reason: str
    requested_at: float
    provider_cancel_confirmed: bool = False
    provider_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cancel_id": self.cancel_id,
            "run_id": self.run_id,
            "actor": self.actor,
            "reason": self.reason,
            "requested_at": self.requested_at,
            "provider_cancel_confirmed": self.provider_cancel_confirmed,
            "provider_evidence": self.provider_evidence,
        }


class CancellationAuditLog:
    """Append-only audit log for cancellation requests (plan 05 §8.6)."""

    def __init__(self, entries: Optional[List[CancelAuditEntry]] = None) -> None:
        self._entries: List[CancelAuditEntry] = list(entries or [])

    def entries(self) -> List[CancelAuditEntry]:
        return list(self._entries)

    def append(self, entry: CancelAuditEntry) -> None:
        self._entries.append(entry)

    def to_dict(self) -> Dict[str, Any]:
        return {"cancellations": [e.to_dict() for e in self._entries]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CancellationAuditLog":
        entries = []
        for raw in data.get("cancellations", []):
            entries.append(
                CancelAuditEntry(
                    cancel_id=raw["cancel_id"],
                    run_id=raw["run_id"],
                    actor=raw["actor"],
                    reason=raw["reason"],
                    requested_at=raw.get("requested_at", 0.0),
                    provider_cancel_confirmed=raw.get("provider_cancel_confirmed", False),
                    provider_evidence=raw.get("provider_evidence", ""),
                )
            )
        return cls(entries)


class ProductionCancellation:
    """Cancellation policy — pure decision making, side-effect free."""

    @staticmethod
    def request(
        *,
        run_id: str,
        actor: str,
        reason: str,
        audit_log: CancellationAuditLog,
        clock: Optional[Callable[[], float]] = None,
    ) -> CancelAuditEntry:
        """Record a cancellation request in the append-only audit log."""
        entry = CancelAuditEntry(
            cancel_id=str(uuid.uuid4()),
            run_id=run_id,
            actor=actor,
            reason=reason,
            requested_at=(clock() if clock else time.time()),
        )
        audit_log.append(entry)
        return entry

    @staticmethod
    def stops_new_scheduling() -> bool:
        """Cancel always stops new scheduling."""
        return True

    @staticmethod
    def provider_cancel_transition(
        *,
        provider_cancel_confirmed: bool,
        evidence: str = "",
    ) -> ProductionRunState:
        """Transition for an active provider operation during cancel.

        When the provider CANNOT confirm cancellation (no evidence), the run
        must land in a state that keeps it observable for reconciliation —
        never a claim of external cancellation.
        """
        if provider_cancel_confirmed and evidence:
            return ProductionRunState.CANCELLED
        return ProductionRunState.WAITING_PROVIDER

    @staticmethod
    def artifact_publish_allowed(cancel_requested: bool) -> bool:
        """Completed artifacts keep provenance but are NOT auto-published."""
        return not cancel_requested

    @staticmethod
    def ensure_cancellable(current: ProductionRunState) -> None:
        if current == ProductionRunState.COMPLETED:
            raise DomainError(
                message="Cannot cancel a completed production run; archive it instead.",
                code="WINDAGENT_ERR_CANCELLATION",
                details={"run_state": current.value},
            )


__all__ = [
    "CancelAuditEntry",
    "CancellationAuditLog",
    "ProductionCancellation",
]
