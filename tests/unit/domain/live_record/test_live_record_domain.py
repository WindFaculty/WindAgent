"""Live Record domain tests (live_record.contract/v0.1, ban_ke_hoach_v1.md Phase 1).

Covers:
- plan status state machine: legal transitions, frozen immutability,
  terminal STALE/INVALID states,
- LiveExecutionPlan aggregate: canonical plan hash stability, lineage
  validation, edit-before-freeze / reject-after-freeze, staleness vs the
  episode's current revision (Principle A),
- PreparedAction payload guard: only artifact:// refs are accepted
  (Principle C — no inline payloads in tool calls).
"""

from __future__ import annotations

import pytest

from windagent_core.contracts.live_record.errors import (
    LiveRecordInvalidTransitionError,
    LiveRecordNotFrozenError,
    LiveRecordPlanFrozenError,
    LiveRecordValidationError,
)
from windagent_core.contracts.live_record.ids import LiveExecutionPlanId
from windagent_core.domain.live_record.lifecycle import (
    LiveExecutionPlanStatus,
    PlanStatusStateMachine,
)
from windagent_core.domain.live_record.plan import (
    ExpectedVisualState,
    LiveExecutionPlan,
    PreparedAction,
    RecordingCue,
    RecordingProfile,
    RecordingScene,
)

HASH_A = "a" * 64


def _action(action_id: str = "act_1", scene_id: str = "sc_1", **overrides) -> PreparedAction:
    base = {
        "action_id": action_id,
        "type": "CODE_PLAYBACK",
        "scene_id": scene_id,
        "payload_ref": "artifact://bundles/act_1.py",
        "idempotency_key": f"idem_{action_id}",
    }
    base.update(overrides)
    return PreparedAction.model_validate(base)


def _scene(scene_id: str = "sc_1", **overrides) -> RecordingScene:
    base = {"scene_id": scene_id, "index": 0, "title": "Scene one"}
    base.update(overrides)
    return RecordingScene.model_validate(base)


def _plan(**overrides) -> LiveExecutionPlan:
    base = {
        "plan_id": LiveExecutionPlanId("plan_alpha_1"),
        "episode_id": "ep_alpha",
        "episode_revision_id": "rev_alpha_7",
        "scenes": [_scene()],
        "actions": [_action()],
    }
    base.update(overrides)
    return LiveExecutionPlan.model_validate(base)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_frozen_plan_only_transitions_to_stale():
    assert PlanStatusStateMachine.TRANSITIONS[LiveExecutionPlanStatus.FROZEN] == frozenset(
        {LiveExecutionPlanStatus.STALE}
    )


def test_terminal_states_have_no_successors():
    for terminal in (LiveExecutionPlanStatus.STALE, LiveExecutionPlanStatus.INVALID):
        assert PlanStatusStateMachine.TRANSITIONS[terminal] == frozenset()
        with pytest.raises(LiveRecordInvalidTransitionError):
            PlanStatusStateMachine.transition(terminal, LiveExecutionPlanStatus.DRAFT)


@pytest.mark.parametrize(
    "current,target",
    [
        ("DRAFT", "FROZEN"),  # must pass through VALIDATED
        ("DRAFT", "VALIDATED"),
        ("PREPARED", "DRAFT"),
        ("FROZEN", "PREPARED"),
        ("STALE", "INVALID"),
        ("INVALID", "STALE"),
    ],
)
def test_illegal_transitions_rejected(current: str, target: str):
    assert not PlanStatusStateMachine.can_transition(
        LiveExecutionPlanStatus[current], LiveExecutionPlanStatus[target]
    )
    with pytest.raises(LiveRecordInvalidTransitionError):
        PlanStatusStateMachine.transition(
            LiveExecutionPlanStatus[current], LiveExecutionPlanStatus[target]
        )


def test_full_lifecycle_draft_to_frozen():
    plan = _plan().mark_prepared().mark_validated().freeze()
    assert plan.status == LiveExecutionPlanStatus.FROZEN
    assert len(plan.plan_hash) == 64
    assert plan.frozen_at is not None


# ---------------------------------------------------------------------------
# PreparedAction payload guard (Principle C)
# ---------------------------------------------------------------------------


def test_action_payload_must_be_artifact_uri():
    with pytest.raises(LiveRecordValidationError, match="PAYLOAD_REF_MUST_BE_ARTIFACT_URI"):
        _action(payload_ref="print('hello')")


def test_audio_locked_off_in_profile():
    profile = RecordingProfile()
    assert profile.audio_enabled is False
    with pytest.raises(Exception):
        RecordingProfile.model_validate({**profile.model_dump(), "audio_enabled": True})


# ---------------------------------------------------------------------------
# Aggregate: hashing + lineage
# ---------------------------------------------------------------------------


def test_plan_hash_deterministic_and_content_sensitive():
    plan = _plan().mark_prepared().mark_validated()
    twin = _plan().mark_prepared().mark_validated()
    assert plan.plan_hash == twin.plan_hash

    other = _plan(actions=[_action(action_id="act_2")]).mark_prepared().mark_validated()
    assert plan.plan_hash != other.plan_hash


def test_validate_lineage_unknown_scene_and_duplicate_action():
    with pytest.raises(LiveRecordValidationError, match="ACTION_SCENE_UNKNOWN"):
        _plan(actions=[_action(scene_id="sc_missing")]).validate_lineage()

    with pytest.raises(LiveRecordValidationError, match="ACTION_DUPLICATE"):
        _plan(actions=[_action(), _action()]).validate_lineage()

    with pytest.raises(LiveRecordValidationError, match="SCENE_ACTION_UNKNOWN"):
        _plan(
            scenes=[_scene(action_ids=["act_ghost"])],
            actions=[_action()],
        ).validate_lineage()


def test_draft_cannot_skip_straight_to_validated():
    with pytest.raises(LiveRecordInvalidTransitionError):
        _plan().mark_validated()


# ---------------------------------------------------------------------------
# Mutations before freeze; immutable after
# ---------------------------------------------------------------------------


def test_edit_before_freeze_bumps_version_and_drops_validation():
    plan = _plan().mark_prepared().mark_validated()
    version_before = plan.optimistic_version

    edited = plan.edit_content(
        actions=[
            _action(),
            _action(
                action_id="act_2",
                expected_after=ExpectedVisualState(state_id="st_green_build"),
            ),
        ]
    )
    assert edited.optimistic_version == version_before + 1
    assert edited.status == LiveExecutionPlanStatus.PREPARED  # validation dropped
    assert "act_2" in edited.allowed_action_ids
    assert "st_green_build" in edited.allowed_state_ids


def test_edit_after_freeze_raises_plan_frozen():
    frozen = _plan().mark_prepared().mark_validated().freeze()
    with pytest.raises(LiveRecordPlanFrozenError):
        frozen.edit_content(scenes=[])


def test_freeze_requires_validated():
    with pytest.raises(LiveRecordInvalidTransitionError, match="PLAN_NOT_VALIDATED"):
        _plan().freeze()


def test_mark_stale_allowed_from_frozen():
    frozen = _plan().mark_prepared().mark_validated().freeze()
    stale = frozen.mark_stale()
    assert stale.status == LiveExecutionPlanStatus.STALE
    with pytest.raises(LiveRecordInvalidTransitionError):
        stale.mark_invalid()


# ---------------------------------------------------------------------------
# Staleness (Principle A)
# ---------------------------------------------------------------------------


def test_staleness_and_usable_for_recording():
    frozen = _plan().mark_prepared().mark_validated().freeze()

    frozen.assert_usable_for_recording(frozen.episode_revision_id)  # no raise

    reason = frozen.staleness_reason("rev_alpha_8")
    assert reason is not None and "RECORDING_PLAN_STALE" in reason
    with pytest.raises(LiveRecordValidationError, match="RECORDING_PLAN_STALE"):
        frozen.assert_usable_for_recording("rev_alpha_8")

    draft = _plan()
    with pytest.raises(LiveRecordNotFrozenError, match="RECORDING_PLAN_NOT_FROZEN"):
        draft.assert_usable_for_recording(draft.episode_revision_id)


# ---------------------------------------------------------------------------
# Round trip: model_dump -> model_validate preserves hash-relevant content
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_plan_hash():
    plan = _plan(
        recording_profile=RecordingProfile(resolution="1280x720", fps=30),
    ).mark_prepared().mark_validated().freeze()

    dumped = plan.model_dump(mode="json")
    restored = LiveExecutionPlan.model_validate(dumped)
    assert restored == plan
    assert restored.compute_plan_hash() == plan.plan_hash


def test_cues_with_expected_state_flow_through_lineage():
    state = ExpectedVisualState(state_id="st_tests_pass", test_should_pass=True)
    cue = RecordingCue(cue_id="cue_1", scene_id="sc_1", index=0, expected_state=state)
    plan = _plan(
        scenes=[_scene(cues=[cue])],
        actions=[_action(expected_after=state)],
    )
    plan.validate_lineage()
    assert plan.allowed_state_ids == frozenset({"st_tests_pass"})
