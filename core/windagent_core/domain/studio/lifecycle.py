"""
Canonical Studio episode lifecycle (studio.contract/v0.1).

Frozen states, approval checkpoints/modes, and transition rules from
docs/plans/studio_roadmap_01/01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md:

- States: DRAFT, IDEA_REVIEW, STORY_BIBLE_REVIEW, OUTLINE_REVIEW,
  SCREENPLAY_REVIEW, REVISING, LOCKED, READY_FOR_PRODUCTION, FAILED, CANCELLED.
- ``READY_FOR_PRODUCTION`` is the single terminal success enum value for
  Roadmap 1. The externally named milestone may qualify the aggregate as
  ``studio.episode.ready_for_production``; no second state value is introduced.
- Approval checkpoints: IDEA, STORY_BIBLE, OUTLINE, SCREENPLAY.
- Approval modes: AUTO, HUMAN_REQUIRED, QUALITY_GATE_ONLY.
- Lock transition: SCREENPLAY_REVIEW -> LOCKED -> READY_FOR_PRODUCTION.
- Content mutation after lock always derives a new ProductionRevision with the
  locked revision as parent.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Optional

from windagent_core.contracts.studio.errors import StudioInvalidTransitionError

# State enum is intentionally named ``EpisodeState`` (not a lifecycle enum listed
# in the duplicate-canonical checker, which reserves TaskState/WorkflowState/
# StepState/SessionState).
class EpisodeState(str, Enum):
    DRAFT = "DRAFT"
    IDEA_REVIEW = "IDEA_REVIEW"
    STORY_BIBLE_REVIEW = "STORY_BIBLE_REVIEW"
    OUTLINE_REVIEW = "OUTLINE_REVIEW"
    SCREENPLAY_REVIEW = "SCREENPLAY_REVIEW"
    REVISING = "REVISING"
    LOCKED = "LOCKED"
    READY_FOR_PRODUCTION = "READY_FOR_PRODUCTION"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_SUCCESS_STATES: FrozenSet[EpisodeState] = frozenset(
    {EpisodeState.READY_FOR_PRODUCTION}
)
TERMINAL_FAILURE_STATES: FrozenSet[EpisodeState] = frozenset(
    {EpisodeState.FAILED, EpisodeState.CANCELLED}
)
TERMINAL_STATES: FrozenSet[EpisodeState] = TERMINAL_SUCCESS_STATES | TERMINAL_FAILURE_STATES

# States that block content derivation/lock operations because the screenplay is frozen.
LOCKED_STATES: FrozenSet[EpisodeState] = frozenset(
    {EpisodeState.LOCKED, EpisodeState.READY_FOR_PRODUCTION}
)


class ApprovalCheckpoint(str, Enum):
    IDEA = "IDEA"
    STORY_BIBLE = "STORY_BIBLE"
    OUTLINE = "OUTLINE"
    SCREENPLAY = "SCREENPLAY"


# Frozen ordered progression of approval checkpoints.
CHECKPOINT_ORDER: Dict[ApprovalCheckpoint, int] = {
    ApprovalCheckpoint.IDEA: 0,
    ApprovalCheckpoint.STORY_BIBLE: 1,
    ApprovalCheckpoint.OUTLINE: 2,
    ApprovalCheckpoint.SCREENPLAY: 3,
}


class ApprovalMode(str, Enum):
    AUTO = "AUTO"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    QUALITY_GATE_ONLY = "QUALITY_GATE_ONLY"


# Review states keyed by the checkpoint they await approval for.
CHECKPOINT_TO_REVIEW_STATE: Dict[ApprovalCheckpoint, EpisodeState] = {
    ApprovalCheckpoint.IDEA: EpisodeState.IDEA_REVIEW,
    ApprovalCheckpoint.STORY_BIBLE: EpisodeState.STORY_BIBLE_REVIEW,
    ApprovalCheckpoint.OUTLINE: EpisodeState.OUTLINE_REVIEW,
    ApprovalCheckpoint.SCREENPLAY: EpisodeState.SCREENPLAY_REVIEW,
}


class EpisodeStateMachine:
    """Enforces the frozen lifecycle transition rules.

    The lock transition (SCREENPLAY_REVIEW -> LOCKED -> READY_FOR_PRODUCTION)
    is implemented as an idempotently resumable two-command sequence:
    ``derive_locked()`` moves SCREENPLAY_REVIEW -> LOCKED and ``finalize_lock()``
    moves LOCKED -> READY_FOR_PRODUCTION. Both commands record
    ``studio.screenplay.locked`` / ``studio.episode.ready_for_production`` so a
    crash between the two is safely resumable.
    """

    TRANSITIONS: Dict[EpisodeState, FrozenSet[EpisodeState]] = {
        EpisodeState.DRAFT: frozenset(
            {EpisodeState.IDEA_REVIEW, EpisodeState.FAILED, EpisodeState.CANCELLED}
        ),
        EpisodeState.IDEA_REVIEW: frozenset(
            {
                EpisodeState.DRAFT,
                EpisodeState.STORY_BIBLE_REVIEW,
                EpisodeState.REVISING,
                EpisodeState.FAILED,
                EpisodeState.CANCELLED,
            }
        ),
        EpisodeState.STORY_BIBLE_REVIEW: frozenset(
            {
                EpisodeState.DRAFT,
                EpisodeState.OUTLINE_REVIEW,
                EpisodeState.REVISING,
                EpisodeState.FAILED,
                EpisodeState.CANCELLED,
            }
        ),
        EpisodeState.OUTLINE_REVIEW: frozenset(
            {
                EpisodeState.DRAFT,
                EpisodeState.SCREENPLAY_REVIEW,
                EpisodeState.REVISING,
                EpisodeState.FAILED,
                EpisodeState.CANCELLED,
            }
        ),
        EpisodeState.SCREENPLAY_REVIEW: frozenset(
            {
                EpisodeState.DRAFT,
                EpisodeState.LOCKED,
                EpisodeState.REVISING,
                EpisodeState.FAILED,
                EpisodeState.CANCELLED,
            }
        ),
        EpisodeState.REVISING: frozenset(
            {
                EpisodeState.IDEA_REVIEW,
                EpisodeState.STORY_BIBLE_REVIEW,
                EpisodeState.OUTLINE_REVIEW,
                EpisodeState.SCREENPLAY_REVIEW,
                EpisodeState.FAILED,
                EpisodeState.CANCELLED,
            }
        ),
        EpisodeState.LOCKED: frozenset(
            {EpisodeState.READY_FOR_PRODUCTION, EpisodeState.FAILED, EpisodeState.CANCELLED}
        ),
        EpisodeState.READY_FOR_PRODUCTION: frozenset(),
        EpisodeState.FAILED: frozenset(),
        EpisodeState.CANCELLED: frozenset(),
    }

    @classmethod
    def can_transition(cls, current: EpisodeState, target: EpisodeState) -> bool:
        return target in cls.TRANSITIONS.get(current, frozenset())

    @classmethod
    def transition(cls, current: EpisodeState, target: EpisodeState) -> EpisodeState:
        if not cls.can_transition(current, target):
            raise StudioInvalidTransitionError(
                f"Illegal episode transition {current.value} -> {target.value}.",
                details={"current_state": current.value, "target_state": target.value},
            )
        return target

    @classmethod
    def is_terminal_success(cls, state: EpisodeState) -> bool:
        return state in TERMINAL_SUCCESS_STATES

    @classmethod
    def is_terminal(cls, state: EpisodeState) -> bool:
        return state in TERMINAL_STATES

    @classmethod
    def awaiting_checkpoint(cls, state: EpisodeState) -> Optional[ApprovalCheckpoint]:
        """Return the approval checkpoint an episode is waiting on, if any."""
        for checkpoint, review_state in CHECKPOINT_TO_REVIEW_STATE.items():
            if review_state == state:
                return checkpoint
        return None


__all__ = [
    "EpisodeState",
    "ApprovalCheckpoint",
    "ApprovalMode",
    "CHECKPOINT_ORDER",
    "CHECKPOINT_TO_REVIEW_STATE",
    "TERMINAL_SUCCESS_STATES",
    "TERMINAL_FAILURE_STATES",
    "TERMINAL_STATES",
    "LOCKED_STATES",
    "EpisodeStateMachine",
]
