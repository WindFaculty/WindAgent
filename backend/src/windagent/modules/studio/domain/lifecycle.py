"""Canonical Studio episode lifecycle (ported from the frozen
``windagent_core.domain.studio.lifecycle``).

The state machine is frozen per
``docs/plans/studio_roadmap_01/01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md``:
``DRAFT -> *_REVIEW -> LOCKED -> READY_FOR_PRODUCTION`` is the only success
path; ``FAILED`` and ``CANCELLED`` are isolated terminal failures.
Approval checkpoints advance strictly in order and the lock transition is an
idempotently resumable two-command sequence (see ``Episode``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class EpisodeState(StrEnum):
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


TERMINAL_SUCCESS_STATES: Final[frozenset[EpisodeState]] = frozenset(
    {EpisodeState.READY_FOR_PRODUCTION}
)
TERMINAL_FAILURE_STATES: Final[frozenset[EpisodeState]] = frozenset(
    {EpisodeState.FAILED, EpisodeState.CANCELLED}
)
TERMINAL_STATES: Final[frozenset[EpisodeState]] = TERMINAL_SUCCESS_STATES | TERMINAL_FAILURE_STATES
LOCKED_STATES: Final[frozenset[EpisodeState]] = frozenset(
    {EpisodeState.LOCKED, EpisodeState.READY_FOR_PRODUCTION}
)


class ApprovalCheckpoint(StrEnum):
    IDEA = "IDEA"
    STORY_BIBLE = "STORY_BIBLE"
    OUTLINE = "OUTLINE"
    SCREENPLAY = "SCREENPLAY"


CHECKPOINT_ORDER: Final[dict[ApprovalCheckpoint, int]] = {
    ApprovalCheckpoint.IDEA: 0,
    ApprovalCheckpoint.STORY_BIBLE: 1,
    ApprovalCheckpoint.OUTLINE: 2,
    ApprovalCheckpoint.SCREENPLAY: 3,
}


class ApprovalMode(StrEnum):
    AUTO = "AUTO"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    QUALITY_GATE_ONLY = "QUALITY_GATE_ONLY"


CHECKPOINT_TO_REVIEW_STATE: Final[dict[ApprovalCheckpoint, EpisodeState]] = {
    ApprovalCheckpoint.IDEA: EpisodeState.IDEA_REVIEW,
    ApprovalCheckpoint.STORY_BIBLE: EpisodeState.STORY_BIBLE_REVIEW,
    ApprovalCheckpoint.OUTLINE: EpisodeState.OUTLINE_REVIEW,
    ApprovalCheckpoint.SCREENPLAY: EpisodeState.SCREENPLAY_REVIEW,
}


class EpisodeStateMachine:
    """Enforces the frozen transition table."""

    TRANSITIONS: Final[dict[EpisodeState, frozenset[EpisodeState]]] = {
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
            from .errors import StudioInvalidTransitionError

            raise StudioInvalidTransitionError(
                f"Illegal episode transition {current.value} -> {target.value}.",
                context={"current_state": current.value, "target_state": target.value},
            )
        return target

    @classmethod
    def is_terminal(cls, state: EpisodeState) -> bool:
        return state in TERMINAL_STATES

    @classmethod
    def is_terminal_success(cls, state: EpisodeState) -> bool:
        return state in TERMINAL_SUCCESS_STATES

    @classmethod
    def awaiting_checkpoint(cls, state: EpisodeState) -> ApprovalCheckpoint | None:
        for checkpoint, review_state in CHECKPOINT_TO_REVIEW_STATE.items():
            if review_state == state:
                return checkpoint
        return None


__all__ = [
    "ApprovalCheckpoint",
    "ApprovalMode",
    "CHECKPOINT_ORDER",
    "CHECKPOINT_TO_REVIEW_STATE",
    "EpisodeState",
    "EpisodeStateMachine",
    "LOCKED_STATES",
    "TERMINAL_FAILURE_STATES",
    "TERMINAL_STATES",
    "TERMINAL_SUCCESS_STATES",
]

