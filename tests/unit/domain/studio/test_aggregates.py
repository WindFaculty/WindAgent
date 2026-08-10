"""A2 domain tests: SeriesProject / Episode aggregate invariants.

Stale-write protection, lifecycle transition enforcement on the aggregate,
lock sequence idempotency/resumability, revision attachment rules, and
serialization round trips.
"""

import pytest

from windagent_core.contracts.studio.errors import (
    StudioInvalidTransitionError,
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import (
    EpisodeId,
    ProductionRevisionId,
    SeriesProjectId,
    StudioRunId,
)
from windagent_core.domain.studio.episode import Episode
from windagent_core.domain.studio.lifecycle import EpisodeState, EpisodeStateMachine
from windagent_core.domain.studio.series import SeriesProject

SERIES = SeriesProjectId.generate("ser")
EPISODE = EpisodeId.generate("ep")


def _series(**overrides) -> SeriesProject:
    base = dict(series_id=SERIES, title="Test Series")
    base.update(overrides)
    return SeriesProject(**base)


def _episode(**overrides) -> Episode:
    base = dict(
        episode_id=EPISODE,
        series_id=SERIES,
        title="Pilot",
        episode_number=1,
    )
    base.update(overrides)
    return Episode(**base)


# ---- SeriesProject -------------------------------------------------------------


def test_series_title_cannot_be_blank():
    with pytest.raises(StudioValidationError):
        SeriesProject(series_id=SERIES, title="   ")


def test_series_with_episode_is_idempotent():
    series = _series()
    once = series.with_episode(EPISODE)
    twice = once.with_episode(EPISODE)
    assert once.episode_ids == (EPISODE,)
    assert twice is once or twice.episode_ids == (EPISODE,)
    assert series.episode_ids == ()  # original immutable


def test_series_with_episode_appends_in_order():
    e2 = EpisodeId.generate("ep")
    series = _series().with_episode(EPISODE).with_episode(e2)
    assert series.episode_ids == (EPISODE, e2)


# ---- Episode transitions -------------------------------------------------------


def test_episode_transition_enforces_state_machine():
    ep = _episode()
    with pytest.raises(StudioInvalidTransitionError):
        ep.transition_to(EpisodeState.LOCKED)  # DRAFT -> LOCKED illegal
    advanced = ep.transition_to(EpisodeState.IDEA_REVIEW)
    assert advanced.state == EpisodeState.IDEA_REVIEW
    assert advanced.awaiting_checkpoint == "IDEA"


def test_episode_transition_bumps_optimistic_version():
    ep = _episode()
    advanced = ep.transition_to(EpisodeState.IDEA_REVIEW)
    assert advanced.optimistic_version == 1
    assert ep.optimistic_version == 0  # immutable original


def test_episode_stale_transition_rejected():
    ep = _episode(optimistic_version=2)
    with pytest.raises(StudioStaleRevisionError):
        ep.transition_to(EpisodeState.IDEA_REVIEW, expected_version=1)


def test_episode_terminal_state_rejects_any_transition():
    ep = _episode(state=EpisodeState.READY_FOR_PRODUCTION)
    assert ep.is_terminal
    with pytest.raises(StudioInvalidTransitionError):
        ep.transition_to(EpisodeState.DRAFT)


def test_episode_attach_revision_updates_current_link():
    rev = ProductionRevisionId.generate("rev")
    ep = _episode()
    attached = ep.attach_revision(rev, expected_version=0)
    assert attached.current_revision_id == rev
    assert attached.optimistic_version == 1


def test_episode_attach_revision_rejected_when_locked():
    rev = ProductionRevisionId.generate("rev")
    ep = _episode(state=EpisodeState.LOCKED)
    with pytest.raises(StudioStaleRevisionError):
        ep.attach_revision(rev)


def test_episode_bind_run():
    run = StudioRunId.generate("run")
    ep = _episode()
    bound = ep.bind_run(run)
    assert bound.active_run_id == run


# ---- lock sequence (idempotently resumable) ------------------------------------


def test_start_lock_sequence_requires_review_state():
    ep = _episode()
    with pytest.raises(StudioInvalidTransitionError):
        ep.start_lock_sequence()


def test_lock_sequence_full_path():
    ep = _episode(state=EpisodeState.SCREENPLAY_REVIEW)
    locked = ep.start_lock_sequence()
    assert locked.state == EpisodeState.LOCKED
    assert locked.is_locked
    ready = locked.finalize_lock()
    assert ready.state == EpisodeState.READY_FOR_PRODUCTION
    assert EpisodeStateMachine.is_terminal_success(ready.state)


def test_lock_sequence_is_resumable_after_crash():
    # crash between the two commands: LOCKED is safe to re-enter
    ep = _episode(state=EpisodeState.SCREENPLAY_REVIEW)
    locked = ep.start_lock_sequence()
    again = locked.start_lock_sequence()
    assert again.state == EpisodeState.LOCKED
    ready = again.finalize_lock()
    assert ready.state == EpisodeState.READY_FOR_PRODUCTION
    # finalize is idempotent too
    assert ready.finalize_lock().state == EpisodeState.READY_FOR_PRODUCTION


def test_episode_stale_version_rejected_during_lock_sequence():
    ep = _episode(state=EpisodeState.SCREENPLAY_REVIEW, optimistic_version=4)
    with pytest.raises(StudioStaleRevisionError):
        ep.start_lock_sequence(expected_version=3)


# ---- serialization -------------------------------------------------------------


def test_episode_round_trip_is_lossless():
    ep = _episode(
        state=EpisodeState.OUTLINE_REVIEW,
        current_revision_id=ProductionRevisionId.generate("rev"),
        metadata={"tags": ["a", "b"]},
    )
    restored = Episode.model_validate(ep.model_dump())
    assert restored == ep


def test_series_round_trip_is_lossless():
    series = _series().with_episode(EPISODE)
    restored = SeriesProject.model_validate(series.model_dump())
    assert restored == series
