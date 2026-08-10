"""A2 domain tests: approval policy modes, checkpoints, and decision binding.

Approval decisions bind to aggregate + revision + artifact hash; stale hash or
stale revision versions are rejected; HUMAN_REQUIRED checkpoints enforce
approver roles.
"""

import pytest
from pydantic import ValidationError

from windagent_core.contracts.studio.errors import (
    StudioArtifactHashMismatchError,
    StudioStaleRevisionError,
    StudioValidationError,
)
from windagent_core.contracts.studio.ids import EpisodeId, ProductionRevisionId
from windagent_core.domain.studio.approval import (
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyService,
    StudioApprovalDecision,
)
from windagent_core.domain.studio.lifecycle import ApprovalCheckpoint, ApprovalMode
from windagent_core.domain.studio.revision import StudioProductionRevision

EPISODE = EpisodeId.generate("ep")


def _revision(**overrides) -> StudioProductionRevision:
    base = dict(
        revision_id=ProductionRevisionId.generate("rev"),
        series_id=__import__("windagent_core.contracts.studio.ids", fromlist=["SeriesProjectId"]).SeriesProjectId.generate("ser"),
        episode_id=EPISODE,
        creator="alice",
        actor="alice",
        content_hash="a" * 64,
    )
    base.update(overrides)
    return StudioProductionRevision(**base)


def _policy(checkpoint_modes=None, **overrides) -> ApprovalPolicy:
    base = dict(
        policy_id="pol_1",
        checkpoint_to_mode_map=checkpoint_modes
        or {
            ApprovalCheckpoint.IDEA: ApprovalMode.QUALITY_GATE_ONLY,
            ApprovalCheckpoint.SCREENPLAY: ApprovalMode.HUMAN_REQUIRED,
        },
    )
    base.update(overrides)
    return ApprovalPolicy(**base)


# ---- policy semantics ----------------------------------------------------------


def test_policy_default_mode_is_quality_gate_only():
    policy = _policy()
    assert (
        policy.mode_for(ApprovalCheckpoint.STORY_BIBLE)
        == ApprovalMode.QUALITY_GATE_ONLY
    )
    assert not policy.requires_human(ApprovalCheckpoint.STORY_BIBLE)


def test_policy_human_required_checkpoint():
    policy = _policy()
    assert policy.requires_human(ApprovalCheckpoint.SCREENPLAY)
    assert not policy.requires_human(ApprovalCheckpoint.IDEA)


def test_policy_rejects_unknown_checkpoint_keys():
    # enum-typed dict key fails pydantic coercion before the domain validator
    with pytest.raises(ValidationError):
        ApprovalPolicy(
            policy_id="pol_x",
            checkpoint_to_mode_map={"NOT_A_CHECKPOINT": ApprovalMode.AUTO},  # type: ignore[dict-item]
        )


def test_policy_quality_thresholds():
    policy = _policy(quality_thresholds={ApprovalCheckpoint.IDEA: 0.8})
    assert policy.quality_threshold_for(ApprovalCheckpoint.IDEA) == 0.8
    assert policy.quality_threshold_for(ApprovalCheckpoint.OUTLINE) is None


# ---- decision binding ----------------------------------------------------------


def test_record_decision_binds_revision_and_hash():
    rev = _revision()
    decision = ApprovalPolicyService.record_decision(
        policy=None,
        revision=rev,
        aggregate_id=EPISODE,
        checkpoint=ApprovalCheckpoint.IDEA,
        actor="bob",
        decision=ApprovalDecisionValue.APPROVED,
    )
    assert isinstance(decision, StudioApprovalDecision)
    assert decision.revision_id == rev.revision_id
    assert decision.artifact_hash == rev.content_hash
    assert decision.checkpoint == ApprovalCheckpoint.IDEA


def test_record_decision_rejects_stale_hash():
    rev = _revision()
    with pytest.raises(StudioArtifactHashMismatchError):
        ApprovalPolicyService.record_decision(
            policy=None,
            revision=rev,
            aggregate_id=EPISODE,
            checkpoint=ApprovalCheckpoint.IDEA,
            actor="bob",
            decision=ApprovalDecisionValue.APPROVED,
            submitted_artifact_hash="b" * 64,
        )


def test_record_decision_rejects_stale_revision_version():
    rev = _revision(optimistic_version=7)
    with pytest.raises(StudioStaleRevisionError):
        ApprovalPolicyService.record_decision(
            policy=None,
            revision=rev,
            aggregate_id=EPISODE,
            checkpoint=ApprovalCheckpoint.IDEA,
            actor="bob",
            decision=ApprovalDecisionValue.APPROVED,
            expected_optimistic_version=6,
        )


def test_record_decision_enforces_approver_role():
    rev = _revision()
    policy = _policy(
        checkpoint_to_mode_map={
            ApprovalCheckpoint.SCREENPLAY: ApprovalMode.HUMAN_REQUIRED
        }
    )
    with pytest.raises(StudioValidationError):
        ApprovalPolicyService.record_decision(
            policy=policy,
            revision=rev,
            aggregate_id=EPISODE,
            checkpoint=ApprovalCheckpoint.SCREENPLAY,
            actor="bob",
            role="VIEWER",
            decision=ApprovalDecisionValue.APPROVED,
        )
    # default OWNER role is allowed
    decision = ApprovalPolicyService.record_decision(
        policy=policy,
        revision=rev,
        aggregate_id=EPISODE,
        checkpoint=ApprovalCheckpoint.SCREENPLAY,
        actor="bob",
        decision=ApprovalDecisionValue.APPROVED,
    )
    assert decision.role == "OWNER"


def test_decision_round_trip():
    rev = _revision()
    decision = ApprovalPolicyService.record_decision(
        policy=None,
        revision=rev,
        aggregate_id=EPISODE,
        checkpoint=ApprovalCheckpoint.IDEA,
        actor="bob",
        decision=ApprovalDecisionValue.REJECTED,
        reason="thin premise",
    )
    restored = StudioApprovalDecision.model_validate(decision.model_dump())
    assert restored == decision
    assert restored.decision == ApprovalDecisionValue.REJECTED
