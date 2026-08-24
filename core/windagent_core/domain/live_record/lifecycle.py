"""Canonical Live Record plan lifecycle (live_record.contract/v0.1).

Frozen statuses and transition rules (ban_ke_hoach_v1.md Section 4):

- States: DRAFT, PREPARED, VALIDATED, FROZEN, STALE, INVALID.
- After ``FROZEN`` the plan content can NEVER be mutated; the only legal
  successor is ``STALE`` (episode revision moved on) — recovery is deriving a
  new plan, not editing the frozen one (Principle A: Episode is source of truth).
- Only ``FROZEN`` plans may start recording takes.

Mirrors ``LiveExecutionPlanStatus`` in
frontend/app/src/features/live-record/domain/types.ts (Phase 0 frozen).
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet

from windagent_core.contracts.live_record.errors import LiveRecordInvalidTransitionError


class LiveExecutionPlanStatus(str, Enum):
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    VALIDATED = "VALIDATED"
    FROZEN = "FROZEN"
    STALE = "STALE"
    INVALID = "INVALID"


#: States from which a RecordingTake may start. Fail-closed single value.
RECORDABLE_STATES: FrozenSet[LiveExecutionPlanStatus] = frozenset(
    {LiveExecutionPlanStatus.FROZEN}
)

TERMINAL_STATES: FrozenSet[LiveExecutionPlanStatus] = frozenset(
    {LiveExecutionPlanStatus.STALE, LiveExecutionPlanStatus.INVALID}
)


class PlanStatusStateMachine:
    """Enforces frozen plan lifecycle transitions.

    Content mutations are allowed only while DRAFT/PREPARED/VALIDATED;
    ``transition_to_frozen`` stamps the canonical hash. STALE/INVALID are
    terminal — derive a new plan instead of resurrecting this one.
    """

    TRANSITIONS: Dict[LiveExecutionPlanStatus, FrozenSet[LiveExecutionPlanStatus]] = {
        LiveExecutionPlanStatus.DRAFT: frozenset(
            {
                LiveExecutionPlanStatus.PREPARED,
                LiveExecutionPlanStatus.INVALID,
            }
        ),
        LiveExecutionPlanStatus.PREPARED: frozenset(
            {
                LiveExecutionPlanStatus.VALIDATED,
                LiveExecutionPlanStatus.STALE,
                LiveExecutionPlanStatus.INVALID,
            }
        ),
        LiveExecutionPlanStatus.VALIDATED: frozenset(
            {
                LiveExecutionPlanStatus.FROZEN,
                LiveExecutionPlanStatus.PREPARED,  # back to PREPARED when content edited again
                LiveExecutionPlanStatus.STALE,
                LiveExecutionPlanStatus.INVALID,
            }
        ),
        # Immutable after freeze — only staleness may be *observed* onto it.
        LiveExecutionPlanStatus.FROZEN: frozenset({LiveExecutionPlanStatus.STALE}),
        LiveExecutionPlanStatus.STALE: frozenset(),
        LiveExecutionPlanStatus.INVALID: frozenset(),
    }

    @classmethod
    def can_transition(cls, current: LiveExecutionPlanStatus, target: LiveExecutionPlanStatus) -> bool:
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: LiveExecutionPlanStatus, target: LiveExecutionPlanStatus) -> LiveExecutionPlanStatus:
        if not cls.can_transition(current, target):
            raise LiveRecordInvalidTransitionError(
                f"Illegal execution plan transition {current.value} -> {target.value}.",
                details={"current_status": current.value, "target_status": target.value},
            )
        return target

    @classmethod
    def is_content_editable(cls, status: LiveExecutionPlanStatus) -> bool:
        return status in (
            LiveExecutionPlanStatus.DRAFT,
            LiveExecutionPlanStatus.PREPARED,
            LiveExecutionPlanStatus.VALIDATED,
        )

    @classmethod
    def is_frozen(cls, status: LiveExecutionPlanStatus) -> bool:
        return status == LiveExecutionPlanStatus.FROZEN

    @classmethod
    def is_recordable(cls, status: LiveExecutionPlanStatus) -> bool:
        return status in RECORDABLE_STATES


__all__ = [
    "LiveExecutionPlanStatus",
    "RECORDABLE_STATES",
    "TERMINAL_STATES",
    "PlanStatusStateMachine",
]
