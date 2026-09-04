"""Canonical Live Record lifecycles (Phase 17).

Extracted from ``core/domain/live_record/lifecycle.py``: plan states
DRAFT→PREPARED→VALIDATED→FROZEN→(STALE|INVALID), and take/director session
states. The plan lifecycle is frozen — content is immutable after FROZEN.
Only STALE may be observed onto a FROZEN plan.
"""

from __future__ import annotations

from enum import StrEnum

from .errors import LiveRecordInvalidTransitionError


class LiveExecutionPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    VALIDATED = "VALIDATED"
    FROZEN = "FROZEN"
    STALE = "STALE"
    INVALID = "INVALID"


RECORDABLE_STATES: frozenset[LiveExecutionPlanStatus] = frozenset({LiveExecutionPlanStatus.FROZEN})
TERMINAL_STATES: frozenset[LiveExecutionPlanStatus] = frozenset({LiveExecutionPlanStatus.STALE, LiveExecutionPlanStatus.INVALID})


class PlanStatusStateMachine:
    TRANSITIONS: dict[LiveExecutionPlanStatus, frozenset[LiveExecutionPlanStatus]] = {
        LiveExecutionPlanStatus.DRAFT: frozenset({LiveExecutionPlanStatus.PREPARED, LiveExecutionPlanStatus.INVALID}),
        LiveExecutionPlanStatus.PREPARED: frozenset({LiveExecutionPlanStatus.VALIDATED, LiveExecutionPlanStatus.STALE, LiveExecutionPlanStatus.INVALID}),
        LiveExecutionPlanStatus.VALIDATED: frozenset({LiveExecutionPlanStatus.FROZEN, LiveExecutionPlanStatus.PREPARED, LiveExecutionPlanStatus.STALE, LiveExecutionPlanStatus.INVALID}),
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
                context={"current_status": current.value, "target_status": target.value},
            )
        return target

    @classmethod
    def is_content_editable(cls, status: LiveExecutionPlanStatus) -> bool:
        return status in (LiveExecutionPlanStatus.DRAFT, LiveExecutionPlanStatus.PREPARED, LiveExecutionPlanStatus.VALIDATED)

    @classmethod
    def is_frozen(cls, status: LiveExecutionPlanStatus) -> bool:
        return status == LiveExecutionPlanStatus.FROZEN

    @classmethod
    def is_recordable(cls, status: LiveExecutionPlanStatus) -> bool:
        return status in RECORDABLE_STATES


class TakeSessionStatus(StrEnum):
    IDLE = "IDLE"
    PREPARING = "PREPARING"
    PREFLIGHT = "PREFLIGHT"
    READY = "READY"
    RECORDING = "RECORDING"
    PAUSED = "PAUSED"
    DIRECTOR_DEGRADED = "DIRECTOR_DEGRADED"
    RECOVERING = "RECOVERING"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class TakeStatusStateMachine:
    TRANSITIONS: dict[TakeSessionStatus, frozenset[TakeSessionStatus]] = {
        TakeSessionStatus.IDLE: frozenset({TakeSessionStatus.PREPARING, TakeSessionStatus.FAILED, TakeSessionStatus.BLOCKED}),
        TakeSessionStatus.PREPARING: frozenset({TakeSessionStatus.PREFLIGHT, TakeSessionStatus.FAILED, TakeSessionStatus.BLOCKED}),
        TakeSessionStatus.PREFLIGHT: frozenset({TakeSessionStatus.READY, TakeSessionStatus.BLOCKED, TakeSessionStatus.FAILED}),
        TakeSessionStatus.READY: frozenset({TakeSessionStatus.RECORDING, TakeSessionStatus.FAILED}),
        TakeSessionStatus.RECORDING: frozenset({TakeSessionStatus.PAUSED, TakeSessionStatus.DIRECTOR_DEGRADED, TakeSessionStatus.FINALIZING, TakeSessionStatus.FAILED}),
        TakeSessionStatus.PAUSED: frozenset({TakeSessionStatus.RECORDING, TakeSessionStatus.FINALIZING, TakeSessionStatus.FAILED}),
        TakeSessionStatus.DIRECTOR_DEGRADED: frozenset({TakeSessionStatus.RECOVERING, TakeSessionStatus.FAILED, TakeSessionStatus.FINALIZING}),
        TakeSessionStatus.RECOVERING: frozenset({TakeSessionStatus.RECORDING, TakeSessionStatus.FAILED, TakeSessionStatus.FINALIZING}),
        TakeSessionStatus.FINALIZING: frozenset({TakeSessionStatus.COMPLETED, TakeSessionStatus.FAILED}),
        TakeSessionStatus.COMPLETED: frozenset(),
        TakeSessionStatus.FAILED: frozenset({TakeSessionStatus.IDLE}),
        TakeSessionStatus.BLOCKED: frozenset({TakeSessionStatus.IDLE}),
    }

    @classmethod
    def can_transition(cls, current: TakeSessionStatus, target: TakeSessionStatus) -> bool:
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: TakeSessionStatus, target: TakeSessionStatus) -> TakeSessionStatus:
        if not cls.can_transition(current, target):
            raise LiveRecordInvalidTransitionError(
                f"Illegal take transition {current.value} -> {target.value}.",
                context={"current_status": current.value, "target_status": target.value},
            )
        return target


__all__ = [
    "LiveExecutionPlanStatus",
    "PlanStatusStateMachine",
    "RECORDABLE_STATES",
    "TERMINAL_STATES",
    "TakeSessionStatus",
    "TakeStatusStateMachine",
]
