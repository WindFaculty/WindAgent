"""
Approval gates for the Durable Production Workflow (plan 05 §8.2).

Seven canonical approval gates:

    CONCEPT_APPROVAL, SCREENPLAY_APPROVAL, CHARACTER_APPROVAL,
    LOCATION_APPROVAL, SHOT_PLAN_APPROVAL, COST_APPROVAL, FINAL_CUT_APPROVAL

Rules enforced here (plan 05 §8.2):

- every approval points at an exact revision id + content hash;
- when the approved target (revision/hash) changes, the old approval becomes
  STALE and is never reused for the new target;
- approvals are idempotent — a duplicate APPROVED record for the exact same
  (gate, revision_id, target_hash, actor) is not recreated;
- an approval is only "current" when it exists for the exact target hash the
  caller asks about.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import ApprovalDecisionType, ApprovalRole
from windagent_core.domain.video_production.ids import ApprovalId, ProductionRevisionId


class ProductionApprovalGate(str, Enum):
    """Typed approval gates for the production workflow (plan 05 §8.2)."""

    CONCEPT_APPROVAL = "CONCEPT_APPROVAL"
    SCREENPLAY_APPROVAL = "SCREENPLAY_APPROVAL"
    CHARACTER_APPROVAL = "CHARACTER_APPROVAL"
    LOCATION_APPROVAL = "LOCATION_APPROVAL"
    SHOT_PLAN_APPROVAL = "SHOT_PLAN_APPROVAL"
    COST_APPROVAL = "COST_APPROVAL"
    FINAL_CUT_APPROVAL = "FINAL_CUT_APPROVAL"

    @classmethod
    def all_gates(cls) -> list[str]:
        return [g.value for g in cls]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductionApproval(BaseModel):
    """An approval bound to an exact revision + content hash (plan 05 §8.2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    approval_id: ApprovalId
    run_id: str
    gate: ProductionApprovalGate
    project_id: str
    revision_id: ProductionRevisionId
    target_hash: str = Field(min_length=64, max_length=64)
    actor: str = Field(min_length=1)
    role: ApprovalRole = ApprovalRole.OWNER
    decision: ApprovalDecisionType = ApprovalDecisionType.APPROVED
    reason: str = ""
    decided_at: datetime = Field(default_factory=_utc_now)


class ApprovalLedger:
    """Append-only, revision/hash-bound approval ledger for one run (plan 05 §8.2)."""

    def __init__(self, approvals: Optional[List[ProductionApproval]] = None) -> None:
        self._approvals: List[ProductionApproval] = list(approvals or [])

    # -- queries ----------------------------------------------------------------
    def approvals(self) -> List[ProductionApproval]:
        return list(self._approvals)

    def record(self, approval: ProductionApproval) -> bool:
        """Append an approval; returns False when it is a duplicate (idempotent).

        A duplicate is the exact same (gate, revision_id, target_hash, actor,
        decision) — re-recording is a no-op and does not mutate the ledger.
        """
        for existing in self._approvals:
            if (
                existing.gate == approval.gate
                and str(existing.revision_id) == str(approval.revision_id)
                and existing.target_hash == approval.target_hash
                and existing.actor == approval.actor
                and existing.decision == approval.decision
            ):
                return False
        self._approvals.append(approval)
        return True

    def has_current_approval(
        self,
        gate: ProductionApprovalGate,
        *,
        revision_id: ProductionRevisionId | str,
        target_hash: str,
    ) -> bool:
        """True only when an APPROVED approval exists for the exact target."""
        rev = str(revision_id)
        return any(
            a.gate == gate
            and a.decision == ApprovalDecisionType.APPROVED
            and str(a.revision_id) == rev
            and a.target_hash == target_hash
            for a in self._approvals
        )

    def is_stale(
        self,
        gate: ProductionApprovalGate,
        *,
        revision_id: ProductionRevisionId | str,
        target_hash: str,
    ) -> bool:
        """True when an approval exists for this gate but for a different hash.

        When the target changed, the old approval must NOT be reused for the
        new target (plan 05 §8.2).
        """
        rev = str(revision_id)
        for a in self._approvals:
            if a.gate == gate and str(a.revision_id) == rev and a.target_hash != target_hash:
                return True
        return False

    def latest_for_gate(self, gate: ProductionApprovalGate) -> Optional[ProductionApproval]:
        for a in reversed(self._approvals):
            if a.gate == gate:
                return a
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approvals": [
                {
                    "approval_id": str(a.approval_id),
                    "run_id": a.run_id,
                    "gate": a.gate.value,
                    "project_id": a.project_id,
                    "revision_id": str(a.revision_id),
                    "target_hash": a.target_hash,
                    "actor": a.actor,
                    "role": a.role.value,
                    "decision": a.decision.value,
                    "reason": a.reason,
                    "decided_at": a.decided_at.isoformat(),
                }
                for a in self._approvals
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalLedger":
        approvals = []
        for raw in data.get("approvals", []):
            approvals.append(
                ProductionApproval(
                    approval_id=ApprovalId(raw["approval_id"]),
                    run_id=raw["run_id"],
                    gate=ProductionApprovalGate(raw["gate"]),
                    project_id=raw["project_id"],
                    revision_id=ProductionRevisionId(raw["revision_id"]),
                    target_hash=raw["target_hash"],
                    actor=raw["actor"],
                    role=ApprovalRole(raw["role"]),
                    decision=ApprovalDecisionType(raw["decision"]),
                    reason=raw.get("reason", ""),
                )
            )
        return cls(approvals)


__all__ = [
    "ProductionApprovalGate",
    "ProductionApproval",
    "ApprovalLedger",
]
