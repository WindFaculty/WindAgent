"""
Event protocol tests for the WindAgent Video Production domain (Phase 3).

Covers valid/invalid transitions and idempotency semantics.
"""

from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    VideoProjectId,
)
from windagent_core.events.video_production import (
    VideoProductionEventCatalog,
    VideoProductionEventEnvelope,
    VideoProductionEventTransitions,
    EventIdempotencyGuard,
)


def _event(event_type: str) -> VideoProductionEventEnvelope:
    return VideoProductionEventEnvelope(
        event_type=event_type,
        project_id=VideoProjectId("vp_01"),
        revision_id=ProductionRevisionId("rev_01"),
        aggregate_id="vp_01",
    )


class TestEventTransitions:
    def test_valid_sequence(self):
        sequence = [
            VideoProductionEventCatalog.PROJECT_CREATED,
            VideoProductionEventCatalog.CONCEPT_APPROVED,
            VideoProductionEventCatalog.SCREENPLAY_GENERATED,
            VideoProductionEventCatalog.SCREENPLAY_LOCKED,
            VideoProductionEventCatalog.CINEMATIC_PLAN_GENERATED,
            VideoProductionEventCatalog.SHOT_PLAN_LOCKED,
            VideoProductionEventCatalog.GENERATION_SUBMITTED,
            VideoProductionEventCatalog.GENERATION_COMPLETED,
            VideoProductionEventCatalog.SEQUENCE_COMPLETED,
            VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED,
        ]
        assert VideoProductionEventTransitions.validate_sequence(sequence) is None

    def test_invalid_transition_detected(self):
        sequence = [
            VideoProductionEventCatalog.PROJECT_CREATED,
            VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED,
        ]
        error = VideoProductionEventTransitions.validate_sequence(sequence)
        assert error is not None

    def test_terminal_event(self):
        assert VideoProductionEventTransitions.is_terminal(
            VideoProductionEventCatalog.FINAL_VIDEO_PUBLISHED
        )


class TestEventIdempotency:
    def test_event_id_stability(self):
        env = _event(VideoProductionEventCatalog.GENERATION_SUBMITTED)
        guard = EventIdempotencyGuard()
        assert guard.process(env) is True
        assert guard.process(env) is False

    def test_duplicate_generation_not_submitted_twice(self):
        guard = EventIdempotencyGuard()
        submit = _event(VideoProductionEventCatalog.GENERATION_SUBMITTED)
        assert guard.process(submit) is True
        # A replayed duplicate of the same generation event must not re-submit.
        assert guard.process(submit) is False
