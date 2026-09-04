"""Canonical asset lifecycle state machine (Phase 16).

Every acquired asset moves through a strict lifecycle:

    DISCOVERED -> DOWNLOADED -> VALIDATED
    VALIDATED  -> LICENSE_UNKNOWN | APPROVED | REJECTED
    LICENSE_UNKNOWN -> QUARANTINED | APPROVED | REJECTED
    QUARANTINED -> APPROVED | REJECTED  (requires fresh review)
    APPROVED   -> BOUND_TO_PROJECT
    REJECTED   -> APPROVED (only with new review)
    BOUND_TO_PROJECT -> terminal
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class AssetLifecycleState(StrEnum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    VALIDATED = "VALIDATED"
    LICENSE_UNKNOWN = "LICENSE_UNKNOWN"
    QUARANTINED = "QUARANTINED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BOUND_TO_PROJECT = "BOUND_TO_PROJECT"


_ALLOWED_TRANSITIONS: Final[dict[AssetLifecycleState, frozenset[AssetLifecycleState]]] = {
    AssetLifecycleState.DISCOVERED: frozenset({AssetLifecycleState.DOWNLOADED}),
    AssetLifecycleState.DOWNLOADED: frozenset({AssetLifecycleState.VALIDATED}),
    AssetLifecycleState.VALIDATED: frozenset(
        {
            AssetLifecycleState.LICENSE_UNKNOWN,
            AssetLifecycleState.QUARANTINED,
            AssetLifecycleState.APPROVED,
            AssetLifecycleState.REJECTED,
        }
    ),
    AssetLifecycleState.LICENSE_UNKNOWN: frozenset(
        {
            AssetLifecycleState.QUARANTINED,
            AssetLifecycleState.APPROVED,
            AssetLifecycleState.REJECTED,
        }
    ),
    AssetLifecycleState.QUARANTINED: frozenset({AssetLifecycleState.APPROVED, AssetLifecycleState.REJECTED}),
    AssetLifecycleState.APPROVED: frozenset({AssetLifecycleState.BOUND_TO_PROJECT}),
    AssetLifecycleState.REJECTED: frozenset({AssetLifecycleState.APPROVED}),
    AssetLifecycleState.BOUND_TO_PROJECT: frozenset(),
}


class AssetStateMachine:
    @staticmethod
    def allowed_transitions(state: AssetLifecycleState) -> frozenset[AssetLifecycleState]:
        return _ALLOWED_TRANSITIONS[state]

    @classmethod
    def can_transition(
        cls,
        current: AssetLifecycleState,
        target: AssetLifecycleState,
        *,
        new_review_record: bool = False,
    ) -> bool:
        allowed = target in _ALLOWED_TRANSITIONS[current]
        if current in (AssetLifecycleState.REJECTED, AssetLifecycleState.QUARANTINED) and target == AssetLifecycleState.APPROVED:
            return allowed and new_review_record
        return allowed

    @classmethod
    def require_transition(
        cls,
        current: AssetLifecycleState,
        target: AssetLifecycleState,
        *,
        new_review_record: bool = False,
    ) -> None:
        if not cls.can_transition(current, target, new_review_record=new_review_record):
            from ..errors import ProductionValidationError

            raise ProductionValidationError(
                f"Illegal asset lifecycle transition {current.value} -> {target.value}.",
                context={"current": current.value, "target": target.value},
            )


__all__ = ["AssetLifecycleState", "AssetStateMachine"]
