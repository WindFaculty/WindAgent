"""VP3D Phase 17 — AI Motion Adapter unit tests (stage_h §5/§6).

Covers the §5 backlog and §6 matrix:
- capability contract (backlog 1): fps/duration/skeleton/format/seed outside
  the provider's declared capability fails closed (CAPABILITY_MISMATCH,
  FPS_OUT_OF_RANGE, DURATION_OUT_OF_RANGE, FORMAT_UNSUPPORTED);
- request provenance (backlog 2): deterministic request hash over
  provider/model/version + prompt hash + seed + fps + duration; prompt hash
  is sha256(prompt); every artifact records cost + provider provenance;
- quarantine (backlog 3): raw output is inert data with no track; the
  only track-producing path is approve; any direct import attempt raises
  MotionQuarantineViolationError;
- fair validation (backlog 4): the SAME thresholds as library/mocap —
  foot sliding, joint limit, collision, balance, root drift, fps/duration
  mismatch — are DETECTED and blocking; malicious provider metadata
  (stage_h §6) is flagged and never executed nor copied into the track;
- fallback without bypass (backlog 5): a failing artifact is REJECTED and
  approve raises — library/procedural/human review is the only fallback;
- retry (backlog 6): only TRANSIENT_PROVIDER retries within budget;
  budget exhaustion raises MotionRetryBudgetExceededError; a different
  seed is a NEW candidate, existing candidates are never overwritten.
"""

from __future__ import annotations

import hashlib

import pytest
from windagent_core.domain.video_production.ai_motion import (
    MALICIOUS_METADATA_MARKERS,
    MotionCandidateStatus,
    MotionFindingKind,
    MotionValidator,
)
from windagent_core.domain.video_production.animation import AnimationIntent
from windagent_core.domain.video_production.enums import (
    AnimationAction,
    ClipSource,
    LicenseState,
    MotionOutputFormat,
    MotionRetryKind,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    MotionCapabilityMismatchError,
    MotionGenerationError,
    MotionQuarantineViolationError,
    MotionRetryBudgetExceededError,
)
from windagent_core.domain.video_production.ids import (
    AnimationIntentId,
    SkeletonProfileId,
)
from windagent_intelligence.video.ai_motion import (
    AiMotionAdapter,
    FakeMotionAdapter,
    MotionGenerationPort,
    TextToMotionPort,
    TransientProviderError,
    VideoToMotionPort,
)
from windagent_intelligence.video.ai_motion.fake_adapter import (
    COST_PER_SECOND,
    FAKE_PROVIDER,
)
from windagent_intelligence.video.animation.library import REQUIRED_HUMANOID_BONES
from windagent_intelligence.video.errors import ValidationFailureError

SKELETON = SkeletonProfileId("skel_humanoid_standard")


@pytest.fixture
def adapter():
    return AiMotionAdapter(port=FakeMotionAdapter())


def _intent(action: AnimationAction = AnimationAction.WALK,
            actor: str = "char_01") -> AnimationIntent:
    return AnimationIntent(
        intent_id=AnimationIntentId(f"ai-p17-{actor}"),
        actor_id=actor,
        action=action,
        fps=24,
        skeleton_profile_id=SKELETON,
        episode_id="ep-17",
    )


def _request(adapter, prompt: str = "character walks forward", seed: int = 42,
             **kw):
    kw.setdefault("fps", 24)
    kw.setdefault("duration_seconds", 2.0)
    return adapter.build_request(
        prompt=prompt, actor_id="char_01", seed=seed, **kw)


def _artifact(adapter, prompt: str = "character walks forward",
              seed: int = 42):
    req = _request(adapter, prompt=prompt, seed=seed)
    return req, adapter.generate(req)


# ---------------------------------------------------------------------------
# Backlog 1 — capability contract (fail-closed)
# ---------------------------------------------------------------------------
def test_capability_contract_declared(adapter):
    cap = adapter.capability()
    assert cap.provider == FAKE_PROVIDER
    assert cap.fps_min == 24 and cap.fps_max == 60
    assert cap.supports_seed is True
    assert LicenseState.LICENSED in cap.licenses
    assert cap.max_retry_budget >= 1


def test_fps_out_of_range_fails_closed(adapter):
    with pytest.raises(MotionCapabilityMismatchError) as exc:
        _request(adapter, fps=12)
    assert "FPS_OUT_OF_RANGE" in exc.value.details["kinds"]
    with pytest.raises(MotionCapabilityMismatchError):
        _request(adapter, fps=120)


def test_duration_out_of_range_fails_closed(adapter):
    with pytest.raises(MotionCapabilityMismatchError) as exc:
        _request(adapter, duration_seconds=20.0)
    assert "DURATION_OUT_OF_RANGE" in exc.value.details["kinds"]


def test_format_unsupported_fails_closed(adapter):
    with pytest.raises(MotionCapabilityMismatchError) as exc:
        _request(adapter, output_format=MotionOutputFormat.BVH)
    assert "FORMAT_UNSUPPORTED" in exc.value.details["kinds"]


def test_unsupported_skeleton_fails_closed(adapter):
    with pytest.raises(MotionCapabilityMismatchError) as exc:
        _request(adapter, skeleton_profile_id=SkeletonProfileId("skel_quadruped"))
    assert "CAPABILITY_MISMATCH" in exc.value.details["kinds"]


def test_seed_unsupported_fails_closed():
    no_seed_cap = AiMotionAdapter(
        port=FakeMotionAdapter()).capability().model_copy(
            update={"supports_seed": False})

    class NoSeedPort:
        def capability(self):
            return no_seed_cap

        def generate(self, request):
            raise AssertionError("must never generate")

    with pytest.raises(MotionCapabilityMismatchError) as exc:
        AiMotionAdapter(port=NoSeedPort()).build_request(
            prompt="wave", actor_id="char_01", seed=7)
    assert "CAPABILITY_MISMATCH" in exc.value.details["kinds"]


# ---------------------------------------------------------------------------
# Backlog 2 — request provenance
# ---------------------------------------------------------------------------
def test_request_hash_deterministic_and_sensitive(adapter):
    a = _request(adapter, prompt="walk", seed=42)
    b = _request(adapter, prompt="walk", seed=42)
    assert a.request_hash == b.request_hash
    assert a.request_hash != _request(adapter, prompt="walk", seed=43).request_hash
    assert a.request_hash != _request(adapter, prompt="run", seed=42).request_hash
    # provider/model/version participate in the hash
    other = a.model_copy(update={"model": "other-model"})
    assert other.compute_stable_hash() != a.request_hash


def test_prompt_hash_is_sha256_of_prompt(adapter):
    req = _request(adapter, prompt="character waves hello")
    assert req.prompt_hash == hashlib.sha256(
        "character waves hello".encode("utf-8")).hexdigest()


def test_artifact_records_cost_and_provenance(adapter):
    _, artifact = _artifact(adapter)
    assert artifact.provider == FAKE_PROVIDER
    assert artifact.model
    assert artifact.model_version
    assert artifact.prompt_hash
    assert artifact.seed == 42
    assert artifact.cost == pytest.approx(2.0 * COST_PER_SECOND)
    assert artifact.license == LicenseState.LICENSED


# ---------------------------------------------------------------------------
# Backlog 3 — quarantine: no direct-to-scene path
# ---------------------------------------------------------------------------
def test_raw_artifact_is_quarantined_inert_data(adapter):
    _, artifact = _artifact(adapter)
    # inert: no track, no approved flag, no execution of its payload
    fields = type(artifact).model_fields
    assert "track" not in fields
    assert "approved" not in fields


def test_direct_import_always_raises_quarantine_violation(adapter):
    _, artifact = _artifact(adapter)
    with pytest.raises(MotionQuarantineViolationError) as exc:
        adapter.import_artifact(artifact)
    assert exc.value.details["artifact_id"] == str(artifact.artifact_id)


def test_approve_is_the_only_track_producing_path(adapter):
    from windagent_core.domain.video_production.animation import AnimationTrack
    # public surface: only approve produces a track; everything else returns
    # artifacts/receipts/reports/candidates
    assert hasattr(adapter, "approve")
    req = _request(adapter)
    art = adapter.generate(req)
    assert not isinstance(art, AnimationTrack)
    # import_artifact is the explicit quarantine boundary (always raises)
    with pytest.raises(MotionQuarantineViolationError):
        adapter.import_artifact(art)


# ---------------------------------------------------------------------------
# Fake adapter determinism (backlog 2/6)
# ---------------------------------------------------------------------------
def test_same_prompt_seed_same_artifact_hash(adapter):
    # same prompt+seed across independent adapters -> identical artifact
    a = _artifact(adapter, prompt="walk", seed=42)[1]
    other = AiMotionAdapter(port=FakeMotionAdapter())
    b = _artifact(other, prompt="walk", seed=42)[1]
    assert a.content_hash == b.content_hash
    assert str(a.artifact_id) == str(b.artifact_id)


def test_different_seed_different_artifact(adapter):
    req_a = _request(adapter, prompt="walk", seed=42)
    req_b = _request(adapter, prompt="walk", seed=43)
    a = adapter.generate(req_a)
    b = adapter.generate(req_b)
    assert a.content_hash != b.content_hash
    assert str(a.artifact_id) != str(b.artifact_id)


def test_adapter_implements_all_three_ports(adapter):
    assert isinstance(adapter.port, MotionGenerationPort)
    assert isinstance(adapter.port, TextToMotionPort)
    assert isinstance(adapter.port, VideoToMotionPort)


# ---------------------------------------------------------------------------
# Approve — the full safety chain (backlog 5)
# ---------------------------------------------------------------------------
def test_approve_clean_walk_emits_ai_motion_track(adapter):
    req, artifact = _artifact(adapter, prompt="character walks forward",
                              seed=42)
    receipt = adapter.approve(intent=_intent(), request=req,
                              artifact=artifact,
                              target_bones=REQUIRED_HUMANOID_BONES,
                              start_frame=0)
    track = receipt.track
    assert receipt.validation.ok
    assert track.fps == 24
    assert track.frame_count == 48
    assert track.root_motion_meters == pytest.approx(1.6)
    # provenance: ClipSource.AI_MOTION + allow-listed metadata only
    assert receipt.clip.provenance.source == ClipSource.AI_MOTION
    assert receipt.clip.provenance.provider == FAKE_PROVIDER
    meta = track.metadata["ai_motion"]
    assert meta["artifact_id"] == str(artifact.artifact_id)
    assert meta["request_id"] == str(req.request_id)
    assert meta["seed"] == 42
    assert meta["cost"] == artifact.cost
    assert meta["license"] == "LICENSED"
    # raw provider metadata never enters the track
    assert "generator_note" not in track.metadata
    assert "injected" not in track.metadata
    # retarget receipt present (Stage D profile path)
    assert receipt.remap.ok
    assert receipt.remap.mapped_bones
    assert receipt.candidate.status == MotionCandidateStatus.APPROVED


def test_approve_track_passes_phase15_track_validation(adapter):
    req, artifact = _artifact(adapter, prompt="character walks forward")
    receipt = adapter.approve(intent=_intent(), request=req,
                              artifact=artifact,
                              target_bones=REQUIRED_HUMANOID_BONES)
    assert receipt.validation.ok
    assert receipt.track.content_hash


# ---------------------------------------------------------------------------
# Backlog 4 — same validation metrics as library/mocap (fail-closed)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("prompt,kinds", [
    ("character walks fail:foot", [MotionFindingKind.FOOT_SLIDING]),
    ("character walks fail:joint", [MotionFindingKind.JOINT_LIMIT_VIOLATED]),
    ("character walks fail:collision", [MotionFindingKind.COLLISION]),
    ("character walks fail:balance", [MotionFindingKind.BALANCE_VIOLATED]),
    ("character walks fail:drift", [MotionFindingKind.ROOT_DRIFT]),
    ("character walks fail:fps", [MotionFindingKind.FPS_MISMATCH]),
    ("character walks fail:duration", [MotionFindingKind.DURATION_MISMATCH]),
])
def test_failing_artifact_rejected_no_bypass(adapter, prompt, kinds):
    req, artifact = _artifact(adapter, prompt=prompt)
    with pytest.raises(ValidationFailureError) as exc:
        adapter.approve(intent=_intent(), request=req, artifact=artifact,
                        target_bones=REQUIRED_HUMANOID_BONES)
    for kind in kinds:
        assert kind in exc.value.details["kinds"]
    # candidate REJECTED; fallback is library/procedural/human review
    candidates = adapter.candidates(str(req.request_id))
    rejected = [c for c in candidates
                if c.artifact_id == artifact.artifact_id]
    assert rejected and rejected[0].status == MotionCandidateStatus.REJECTED
    assert "Fallback" in str(exc.value)


def test_fallback_never_bypasses_validation(adapter):
    # validation failure is always blocking — there is no unchecked path
    req, artifact = _artifact(adapter, prompt="character walks fail:collision")
    with pytest.raises(ValidationFailureError):
        adapter.approve(intent=_intent(), request=req, artifact=artifact,
                        target_bones=REQUIRED_HUMANOID_BONES)
    # a different seed is a NEW candidate, still gated by the same chain
    req2, art2 = _artifact(adapter, prompt="character walks fail:collision",
                           seed=7)
    with pytest.raises(ValidationFailureError):
        adapter.approve(intent=_intent(), request=req2, artifact=art2,
                        target_bones=REQUIRED_HUMANOID_BONES)


def test_skeleton_remap_fails_closed_on_missing_bones(adapter):
    req = _request(adapter, prompt="character walks", seed=42)
    art = adapter.generate(req)
    incomplete = art.model_copy(update={
        "motion_metrics": {
            **art.motion_metrics,
            "claimed_bones": ["ROOT", "PELVIS", "SPINE", "HEAD"]}})
    remap = adapter.remap(artifact=incomplete, target_skeleton=SKELETON,
                          target_bones=REQUIRED_HUMANOID_BONES)
    assert not remap.ok
    assert SemanticBone.FOOT_L in remap.missing_bones
    with pytest.raises(ValidationFailureError) as exc:
        adapter.approve(intent=_intent(), request=req, artifact=incomplete,
                        target_bones=REQUIRED_HUMANOID_BONES)
    assert MotionFindingKind.SKELETON_REMAP_FAILED in exc.value.details["kinds"]


def test_license_blocked_fails_closed(adapter):
    req = _request(adapter, prompt="character walks", seed=42)
    art = adapter.generate(req)
    unlicensed = art.model_copy(update={"license": LicenseState.UNKNOWN})
    with pytest.raises(ValidationFailureError) as exc:
        adapter.approve(intent=_intent(), request=req, artifact=unlicensed,
                        target_bones=REQUIRED_HUMANOID_BONES)
    assert MotionFindingKind.LICENSE_BLOCKED in exc.value.details["kinds"]


# ---------------------------------------------------------------------------
# §6 — malicious metadata never executed, never imported
# ---------------------------------------------------------------------------
def test_malicious_metadata_flagged_and_inert(adapter):
    req, artifact = _artifact(adapter, prompt="malicious walk")
    injected = artifact.metadata["injected"]
    assert any(m in injected for m in MALICIOUS_METADATA_MARKERS)
    # the string is inert data — the process survives and the value is the
    # literal string, proving nothing was executed
    assert isinstance(injected, str)
    assert "__import__" in injected
    report = adapter.validate(artifact=artifact)
    assert MotionFindingKind.MALICIOUS_METADATA in report.blocking_kinds
    with pytest.raises(ValidationFailureError) as exc:
        adapter.approve(intent=_intent(), request=req, artifact=artifact,
                        target_bones=REQUIRED_HUMANOID_BONES)
    assert MotionFindingKind.MALICIOUS_METADATA in exc.value.details["kinds"]
    # nothing malicious reached any candidate/track state
    candidates = adapter.candidates(str(req.request_id))
    assert all(c.status == MotionCandidateStatus.REJECTED
               or c.validation_ok is False for c in candidates
               if c.artifact_id == artifact.artifact_id)


def test_clean_artifact_track_metadata_is_allow_listed_only(adapter):
    req, artifact = _artifact(adapter, prompt="character waves", seed=9)
    receipt = adapter.approve(intent=_intent(action=AnimationAction.WAVE),
                              request=req, artifact=artifact,
                              target_bones=REQUIRED_HUMANOID_BONES)
    meta = receipt.track.metadata["ai_motion"]
    assert set(meta) == {"artifact_id", "request_id", "provider", "model",
                         "model_version", "prompt_hash", "seed", "cost",
                         "license"}
    # provider's own metadata keys never appear
    for key in artifact.metadata:
        assert key not in receipt.track.metadata


# ---------------------------------------------------------------------------
# Backlog 6 — retry by cause and budget; candidates never overwritten
# ---------------------------------------------------------------------------
def test_transient_failure_retries_within_budget():
    adapter = AiMotionAdapter(port=FakeMotionAdapter())
    req = adapter.build_request(
        prompt="character walks fail:transient", actor_id="char_01",
        fps=24, duration_seconds=2.0, seed=1)
    with pytest.raises(TransientProviderError):
        adapter.generate(req)
    # retry by cause: transient -> second attempt succeeds
    artifact = adapter.retry(request=req,
                             cause=MotionRetryKind.TRANSIENT_PROVIDER)
    assert artifact.content_hash


def test_retry_budget_exhausted_fails_closed():
    adapter = AiMotionAdapter(port=FakeMotionAdapter())
    req = adapter.build_request(
        prompt="character walks fail:transient-forever", actor_id="char_01",
        fps=24, duration_seconds=2.0, seed=2, retry_budget=1)
    with pytest.raises(TransientProviderError):
        adapter.generate(req)
    with pytest.raises(MotionRetryBudgetExceededError):
        adapter.retry(request=req, cause=MotionRetryKind.TRANSIENT_PROVIDER)


def test_non_retryable_causes_never_retry(adapter):
    for cause in (MotionRetryKind.VALIDATION_FAILED,
                  MotionRetryKind.CAPABILITY_MISMATCH,
                  MotionRetryKind.LICENSE_BLOCKED):
        req = _request(adapter, prompt="walk", seed=5)
        with pytest.raises(MotionGenerationError) as exc:
            adapter.retry(request=req, cause=cause)
        assert exc.value.details["retryable"] is False


def test_different_seed_is_new_candidate_never_overwrite(adapter):
    req42 = _request(adapter, prompt="walk", seed=42)
    req43 = _request(adapter, prompt="walk", seed=43)
    art42 = adapter.generate(req42)
    art43 = adapter.generate(req43)
    assert str(art42.artifact_id) != str(art43.artifact_id)
    # same seed again -> same candidate id -> refused (no overwrite)
    with pytest.raises(MotionGenerationError):
        adapter.generate(req42)
    # approving seed 43 leaves seed 42's candidate intact
    adapter.approve(intent=_intent(), request=req43, artifact=art43,
                    target_bones=REQUIRED_HUMANOID_BONES)
    ids = {str(c.candidate_id) for c in adapter.candidates(str(req42.request_id))}
    ids |= {str(c.candidate_id) for c in adapter.candidates(str(req43.request_id))}
    assert len(ids) == 2


def test_candidate_status_walks_quarantined_to_approved(adapter):
    req = _request(adapter, prompt="walk", seed=11)
    adapter.generate(req)
    quarantined = [c for c in adapter.candidates(str(req.request_id))
                   if c.seed == 11]
    assert quarantined[0].status == MotionCandidateStatus.QUARANTINED


# ---------------------------------------------------------------------------
# VideoToMotionPort + invalidation
# ---------------------------------------------------------------------------
def test_video_to_motion_records_video_ref(adapter):
    req = _request(adapter, prompt="walk", seed=3)
    artifact = adapter.port.generate_video(req, video_ref="ref/cam_01.mp4")
    assert artifact.metadata["video_ref"] == "ref/cam_01.mp4"


def test_invalidation_scoped_to_animation_preview(adapter):
    req, artifact = _artifact(adapter, prompt="walk", seed=21)
    first = adapter.approve(intent=_intent(), request=req, artifact=artifact,
                            target_bones=REQUIRED_HUMANOID_BONES)
    assert first.invalidated_artifacts == []
    # unchanged approve -> nothing invalidated
    same = adapter.approve(intent=_intent(), request=req, artifact=artifact,
                           target_bones=REQUIRED_HUMANOID_BONES,
                           prior_track_hash=first.track_hash)
    assert same.invalidated_artifacts == []
    # different seed -> different track -> preview only
    req2, art2 = _artifact(adapter, prompt="walk", seed=22)
    changed = adapter.approve(intent=_intent(), request=req2, artifact=art2,
                              target_bones=REQUIRED_HUMANOID_BONES,
                              prior_track_hash=first.track_hash)
    assert changed.invalidated_artifacts == [
        f"animation/preview:{changed.track.track_id}"]


def test_motion_validator_is_retryable_policy():
    assert MotionValidator.is_retryable(MotionRetryKind.TRANSIENT_PROVIDER)
    assert not MotionValidator.is_retryable(MotionRetryKind.VALIDATION_FAILED)
