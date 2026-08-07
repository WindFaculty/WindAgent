"""
Canonical asset lifecycle state machine (plan 02 §21.5).

Every acquired asset moves through a strict lifecycle:

    DISCOVERED → DOWNLOADED → VALIDATED
    VALIDATED  → LICENSE_UNKNOWN | APPROVED | REJECTED
    LICENSE_UNKNOWN → APPROVED | REJECTED
    APPROVED   → BOUND_TO_PROJECT

### Forbidden transitions (fail closed):
- DOWNLOADED → BOUND_TO_PROJECT (asset must be validated before binding);
- REJECTED  → APPROVED without a new review record (a rejection can only be
  overturned by a fresh review, never by silent re-approval);
- QUARANTINED → APPROVED without a new human review record + evidence (an
  untrusted asset cannot promote itself on provider metadata alone);
- any transition out of BOUND_TO_PROJECT.

The state machine is a pure domain rule — search/download/validation services
in `tools` drive it, but the policy lives here so it is testable and reusable
across workflow layers.

Asset trust (stage_c Phase 6):
- an asset whose license is UNKNOWN, which has no verified checksum, or which
  lacks commercial-use rights moves to QUARANTINED (fail closed);
- the only way out of QUARANTINED is a fresh human review promoting it to
  APPROVED, or a hard REJECTED.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class AssetLifecycleState(str, Enum):
    """Lifecycle state of an acquired asset (plan 02 §21.5)."""

    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    VALIDATED = "VALIDATED"
    LICENSE_UNKNOWN = "LICENSE_UNKNOWN"
    QUARANTINED = "QUARANTINED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BOUND_TO_PROJECT = "BOUND_TO_PROJECT"


# Valid transitions: source -> set of allowed targets.
_ALLOWED_TRANSITIONS: Dict[AssetLifecycleState, FrozenSet[AssetLifecycleState]] = {
    AssetLifecycleState.DISCOVERED: frozenset({AssetLifecycleState.DOWNLOADED}),
    AssetLifecycleState.DOWNLOADED: frozenset({AssetLifecycleState.VALIDATED}),
    AssetLifecycleState.VALIDATED: frozenset({
        AssetLifecycleState.LICENSE_UNKNOWN,
        AssetLifecycleState.QUARANTINED,
        AssetLifecycleState.APPROVED,
        AssetLifecycleState.REJECTED,
    }),
    AssetLifecycleState.LICENSE_UNKNOWN: frozenset({
        AssetLifecycleState.QUARANTINED,
        AssetLifecycleState.APPROVED,
        AssetLifecycleState.REJECTED,
    }),
    # An untrusted/quarantined asset may only be promoted by a fresh human
    # review record (new_review_record=True) — provider metadata is never
    # sufficient on its own (fail closed).
    AssetLifecycleState.QUARANTINED: frozenset({
        AssetLifecycleState.APPROVED,
        AssetLifecycleState.REJECTED,
    }),
    AssetLifecycleState.APPROVED: frozenset({AssetLifecycleState.BOUND_TO_PROJECT}),
    # Overturn IS allowed but only with a new review record (plan 02 §21.5).
    AssetLifecycleState.REJECTED: frozenset({AssetLifecycleState.APPROVED}),
    AssetLifecycleState.BOUND_TO_PROJECT: frozenset(),
}


class AssetStateMachine:
    """Pure transition rule engine for the asset lifecycle."""

    @staticmethod
    def allowed_transitions(state: AssetLifecycleState) -> FrozenSet[AssetLifecycleState]:
        return _ALLOWED_TRANSITIONS[state]

    @classmethod
    def can_transition(
        cls,
        current: AssetLifecycleState,
        target: AssetLifecycleState,
        *,
        new_review_record: bool = False,
    ) -> bool:
        """Return whether a transition is allowed.

        `new_review_record` models the requirement that a REJECTED asset may
        only become APPROVED via a fresh review record (plan 02 §21.5). It is
        ignored for every other transition.
        """
        allowed = target in _ALLOWED_TRANSITIONS[current]
        if (
            current in (AssetLifecycleState.REJECTED, AssetLifecycleState.QUARANTINED)
            and target == AssetLifecycleState.APPROVED
        ):
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
        """Raise if a transition is invalid; otherwise do nothing."""
        if not cls.can_transition(current, target, new_review_record=new_review_record):
            from windagent_core.domain.video_production.errors import (
                VideoProductionProtocolError,
            )

            raise VideoProductionProtocolError(
                f"Illegal asset lifecycle transition {current.value} -> "
                f"{target.value}.",
                details={"current": current.value, "target": target.value},
            )


__all__ = ["AssetLifecycleState", "AssetStateMachine"]
