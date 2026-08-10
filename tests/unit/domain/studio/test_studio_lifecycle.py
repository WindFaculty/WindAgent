"""A2 domain tests: frozen episode lifecycle (studio.contract/v0.1).

Exhaustive state-transition matrix (property-style, stdlib only), checkpoint
awaiting, terminal/locked-state invariants, and idempotent lock sequence.
"""

from itertools import product

import pytest

from windagent_core.domain.studio.lifecycle import (
    CHECKPOINT_ORDER,
    CHECKPOINT_TO_REVIEW_STATE,
    ApprovalCheckpoint,
    EpisodeState,
    EpisodeStateMachine,
    LOCKED_STATES,
    TERMINAL_FAILURE_STATES,
    TERMINAL_STATES,
    TERMINAL_SUCCESS_STATES,
)
from windagent_core.contracts.studio.errors import StudioInvalidTransitionError

ALL_STATES = list(EpisodeState)

# Frozen v0.1 transition table (docs/plans/studio_roadmap_01/01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md).
# Hardcoded here as the independent contract; TRANSITIONS must match exactly.
EXPECTED_TRANSITIONS: dict[EpisodeState, set[EpisodeState]] = {
    EpisodeState.DRAFT: {
        EpisodeState.IDEA_REVIEW,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.IDEA_REVIEW: {
        EpisodeState.DRAFT,
        EpisodeState.STORY_BIBLE_REVIEW,
        EpisodeState.REVISING,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.STORY_BIBLE_REVIEW: {
        EpisodeState.DRAFT,
        EpisodeState.OUTLINE_REVIEW,
        EpisodeState.REVISING,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.OUTLINE_REVIEW: {
        EpisodeState.DRAFT,
        EpisodeState.SCREENPLAY_REVIEW,
        EpisodeState.REVISING,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.SCREENPLAY_REVIEW: {
        EpisodeState.DRAFT,
        EpisodeState.LOCKED,
        EpisodeState.REVISING,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.REVISING: {
        EpisodeState.IDEA_REVIEW,
        EpisodeState.STORY_BIBLE_REVIEW,
        EpisodeState.OUTLINE_REVIEW,
        EpisodeState.SCREENPLAY_REVIEW,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.LOCKED: {
        EpisodeState.READY_FOR_PRODUCTION,
        EpisodeState.FAILED,
        EpisodeState.CANCELLED,
    },
    EpisodeState.READY_FOR_PRODUCTION: set(),
    EpisodeState.FAILED: set(),
    EpisodeState.CANCELLED: set(),
}


def test_transition_table_matches_frozen_contract():
    """TRANSITIONS must equal the hardcoded v0.1 contract table exactly."""
    for state in ALL_STATES:
        assert set(EpisodeStateMachine.TRANSITIONS[state]) == EXPECTED_TRANSITIONS[state]


def test_exhaustive_transition_matrix_matches_table():
    """Property: every (current, target) pair is allowed iff in the contract table."""
    for current, target in product(ALL_STATES, ALL_STATES):
        allowed = target in EXPECTED_TRANSITIONS[current]
        assert EpisodeStateMachine.can_transition(current, target) is allowed
        if allowed:
            assert EpisodeStateMachine.transition(current, target) is target
        else:
            with pytest.raises(StudioInvalidTransitionError):
                EpisodeStateMachine.transition(current, target)


def test_terminal_states_have_no_outgoing_transitions():
    for state in TERMINAL_STATES:
        assert EpisodeStateMachine.TRANSITIONS[state] == frozenset()
        assert EpisodeStateMachine.is_terminal(state)
        assert not EpisodeStateMachine.can_transition(state, EpisodeState.DRAFT)


def test_terminal_partitions_are_disjoint_and_exhaustive():
    assert TERMINAL_SUCCESS_STATES == {EpisodeState.READY_FOR_PRODUCTION}
    assert TERMINAL_FAILURE_STATES == {EpisodeState.FAILED, EpisodeState.CANCELLED}
    assert TERMINAL_STATES == TERMINAL_SUCCESS_STATES | TERMINAL_FAILURE_STATES
    assert TERMINAL_SUCCESS_STATES.isdisjoint(TERMINAL_FAILURE_STATES)


def test_locked_states_match_frozen_contract():
    assert LOCKED_STATES == {EpisodeState.LOCKED, EpisodeState.READY_FOR_PRODUCTION}


def test_checkpoint_order_is_strict_and_complete():
    assert list(CHECKPOINT_ORDER) == [
        ApprovalCheckpoint.IDEA,
        ApprovalCheckpoint.STORY_BIBLE,
        ApprovalCheckpoint.OUTLINE,
        ApprovalCheckpoint.SCREENPLAY,
    ]
    assert sorted(CHECKPOINT_ORDER.values()) == [0, 1, 2, 3]


def test_review_state_maps_one_to_one_to_checkpoints():
    assert set(CHECKPOINT_TO_REVIEW_STATE.values()) == {
        EpisodeState.IDEA_REVIEW,
        EpisodeState.STORY_BIBLE_REVIEW,
        EpisodeState.OUTLINE_REVIEW,
        EpisodeState.SCREENPLAY_REVIEW,
    }
    for checkpoint, state in CHECKPOINT_TO_REVIEW_STATE.items():
        assert EpisodeStateMachine.awaiting_checkpoint(state) is checkpoint


def test_awaiting_checkpoint_none_for_non_review_states():
    non_review = [
        s for s in ALL_STATES if s not in CHECKPOINT_TO_REVIEW_STATE.values()
    ]
    for state in non_review:
        assert EpisodeStateMachine.awaiting_checkpoint(state) is None


def test_lock_sequence_is_two_step_and_terminal():
    # SCREENPLAY_REVIEW -> LOCKED -> READY_FOR_PRODUCTION
    assert EpisodeStateMachine.can_transition(
        EpisodeState.SCREENPLAY_REVIEW, EpisodeState.LOCKED
    )
    assert EpisodeStateMachine.can_transition(
        EpisodeState.LOCKED, EpisodeState.READY_FOR_PRODUCTION
    )
    assert not EpisodeStateMachine.can_transition(
        EpisodeState.SCREENPLAY_REVIEW, EpisodeState.READY_FOR_PRODUCTION
    )
    assert EpisodeStateMachine.is_terminal_success(EpisodeState.READY_FOR_PRODUCTION)


def test_revising_can_return_to_any_review_state():
    revising = EpisodeState.REVISING
    review_states = {
        EpisodeState.IDEA_REVIEW,
        EpisodeState.STORY_BIBLE_REVIEW,
        EpisodeState.OUTLINE_REVIEW,
        EpisodeState.SCREENPLAY_REVIEW,
    }
    for state in review_states:
        assert EpisodeStateMachine.can_transition(revising, state)


def test_approval_checkpoints_are_unique_values():
    values = [c.value for c in ApprovalCheckpoint]
    assert len(values) == len(set(values))
