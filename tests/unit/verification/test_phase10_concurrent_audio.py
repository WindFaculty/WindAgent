"""Unit tests for Concurrent Audio Production (stage_e.md Phase 10).

Covers the nine backlog items as a fail-closed matrix: provider capability
metadata (1), versioned voice identity (2), canonical request hashing (3),
fail-closed TTS output validation (4), forced alignment + alignment hash (5),
typed line-timing proposals (6), persisted concurrency/resume state (7),
per-provider retry/cancellation policy (8), and dialogue/voice-vs-BGM
invalidation (9). All checks are offline and deterministic.
"""

from __future__ import annotations

import hashlib
import pytest

from windagent_core.domain.video_production.audio import TtsAudioAsset
from windagent_core.domain.video_production.concurrent_audio import (
    ALIGNMENT_CONFIDENCE_FLOOR,
    AlignmentRequest,
    AlignmentResult,
    AudioConcurrencyState,
    AudioDagNode,
    AudioValidationReceipt,
    ConcurrencyPolicy,
    LineTimingResolver,
    TimingResolutionIssue,
    TtsProviderCapability,
    TtsSynthesisRequest,
    VoiceBinding,
    align,
    compute_alignment_hash,
    ensure_final_voice,
    invalidate_audio_scope,
    redact_secrets,
    reuseable_audio,
    validate_tts_output,
)
from windagent_core.domain.video_production.enums import (
    AudioInvalidationScope,
    AudioNodeStatus,
    AudioValidationIssueCode,
    LineTimingProposalType,
    VoiceRightsState,
    TtsCapabilityFeature,
    TtsMode,
)
from windagent_core.domain.video_production.errors import (
    LowConfidenceAlignmentError,
    OverlongLineError,
    TtsEmptyOutputError,
    TtsInvalidOutputError,
    UnsupportedLocaleError,
    VoiceConsentMissingError,
)
from windagent_core.domain.video_production.ids import (
    AlignmentReceiptId,
    AudioConcurrencyStateId,
    AudioNodeExecutionId,
    AudioSynthesisRunId,
    AudioValidationReceiptId,
    CharacterVoiceProfileId,
    ForcedAlignRunId,
    LineTimingResolutionId,
    TtsAudioAssetId,
    TtsProviderId,
)

PH = TtsProviderId
SH = "a" * 64  # canonical 64-char sha256 placeholder
RH = "b" * 64


@pytest.fixture
def capability() -> TtsProviderCapability:
    return TtsProviderCapability(
        provider_id=PH("p1"),
        name="fake-tts",
        supported_locales=["vi-VN", "en-US"],
        modes=[TtsMode.API],
        sample_rates=[22050, 44100],
        channels=["mono", "stereo"],
        features=[TtsCapabilityFeature.WORD_TIMESTAMPS, TtsCapabilityFeature.TOKEN_TIMESTAMPS],
        emotion_labels=["neutral", "happy"],
    )


@pytest.fixture
def binding() -> VoiceBinding:
    return VoiceBinding(
        binding_id=CharacterVoiceProfileId("vb-1"),
        character_id="char-mai",
        display_name="Mai",
        provider="prov",
        model="vm",
        voice_id="real:mai-v1",
        voice_version="v1",
        locale="vi-VN",
        rights_state=VoiceRightsState.CONSENTED,
        approved=True,
        approval_actor="audio-dir",
        preview_only=False,
    )


def _req(**over) -> TtsSynthesisRequest:
    base = dict(
        run_id=AudioSynthesisRunId("run-1"),
        provider_id=PH("p1"),
        character_id="char-mai",
        text="Xin chào",
        locale="vi-VN",
        language="vi-VN",
        sample_rate=22050,
        emotion="neutral",
        voice_profile_hash=SH,
        dialogue_revision_hash=RH,
        target_duration_seconds=4.0,
    )
    base.update(over)
    return TtsSynthesisRequest(**base)


# --- backlog 1: provider capability metadata ---------------------------------
def test_capability_advertises_locale_sample_rate_feature_modes(capability):
    assert capability.supports_locale("vi-VN")
    assert capability.supports_locale("en-US")
    assert not capability.supports_locale("fr-FR")
    assert capability.supports_feature(TtsCapabilityFeature.WORD_TIMESTAMPS)
    assert not capability.supports_feature(TtsCapabilityFeature.PHONEME_TIMING)
    assert capability.supports_sample_rate(44100)
    assert not capability.supports_sample_rate(8000)
    assert capability.modes == [TtsMode.API]


def test_capability_never_assumes_unadvertised_feature(capability):
    # A provider with no phoneme timing must never be treated as having it for
    # alignment DAG planning (stage_e risk: forced aligner is separate adapter).
    assert TtsCapabilityFeature.PHONEME_TIMING not in capability.features
    assert TtsCapabilityFeature.EMOTION not in capability.features


# --- backlog 2: versioned voice identity ---------------------------------------
def test_rename_display_name_does_not_change_binding_key(binding):
    renamed = binding.model_copy(update={"display_name": "Mai (renamed)"})
    assert renamed.identity_key() == binding.identity_key()


def test_voice_version_change_creates_new_identity(binding):
    bumped = binding.model_copy(update={"voice_version": "v2"})
    assert bumped.identity_key() != binding.identity_key()


def test_voice_revision_new_artifact_new_request_hash(binding):
    a = _req(voice_profile_hash=SH).request_hash()
    b = _req(voice_profile_hash=SH.replace("a", "c")).request_hash()
    assert a != b


def test_preview_voice_never_final(binding):
    preview = binding.model_copy(update={"preview_only": True})
    with pytest.raises(VoiceConsentMissingError):
        ensure_final_voice(binding=preview)


def test_real_voice_without_consent_never_final(binding):
    noconsent = binding.model_copy(update={"rights_state": VoiceRightsState.UNKNOWN})
    with pytest.raises(VoiceConsentMissingError):
        ensure_final_voice(binding=noconsent)


def test_real_voice_approved_consented_is_final(binding):
    assert ensure_final_voice(binding=binding) is binding


# --- backlog 3: canonical request hash (idempotent retry) ----------------------
def test_request_hash_stable_across_identical_inputs():
    assert _req().request_hash() == _req().request_hash()


def test_request_hash_changes_when_dialogue_revision_changes():
    assert _req(dialogue_revision_hash=RH).request_hash() != _req(
        dialogue_revision_hash=RH.replace("b", "d")
    ).request_hash()


def test_request_hash_drives_resume_reuse():
    # two distinct lines share nothing; identical lines share everything
    assert _req(text="a").request_hash() != _req(text="b").request_hash()


# --- backlog 4: fail-closed TTS output validation ------------------------------
def _bytes(payload: str = b"RIFF1234WAVE") -> bytes:
    return (payload.encode("utf-8") if isinstance(payload, str) else b"RIFF1234WAVE")


def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_tts_valid_output_passes(capability):
    data = b"RIFF1234WAVE"
    receipt = validate_tts_output(
        receipt_id=AudioValidationReceiptId("ar-1"),
        run_id=AudioSynthesisRunId("run-1"),
        audio_bytes=data,
        declared_sample_rate=22050,
        declared_channel_layout="mono",
        provider_expected_sample_rate=22050,
        expected_content_hash=_h(data),
        decode_ok=True,
        declared_duration_seconds=3.2,
    )
    assert receipt.valid
    assert receipt.sample_rate == 22050
    assert receipt.channel_layout == "mono"
    assert receipt.duration_seconds == 3.2
    assert receipt.content_hash == _h(data)


def test_tts_empty_output_fails_closed():
    with pytest.raises(TtsEmptyOutputError):
        validate_tts_output(
            receipt_id=AudioValidationReceiptId("ar-2"),
            run_id=AudioSynthesisRunId("run-1"),
            audio_bytes=b"",
            declared_sample_rate=22050,
            declared_channel_layout="mono",
            provider_expected_sample_rate=22050,
            expected_content_hash="",
            decode_ok=True,
            declared_duration_seconds=2.0,
        )


def test_tts_bad_sample_rate_fails_closed():
    data = b"RIFF1234WAVE"
    with pytest.raises(TtsInvalidOutputError) as ei:
        validate_tts_output(
            receipt_id=AudioValidationReceiptId("ar-3"),
            run_id=AudioSynthesisRunId("run-1"),
            audio_bytes=data,
            declared_sample_rate=8000,
            declared_channel_layout="mono",
            provider_expected_sample_rate=22050,
            expected_content_hash=_h(data),
            decode_ok=True,
            declared_duration_seconds=2.0,
        )
    assert AudioValidationIssueCode.SAMPLE_RATE_INVALID.value in ei.value.details["issues"]


def test_tts_bad_hash_fails_closed():
    data = b"RIFF1234WAVE"
    with pytest.raises(TtsInvalidOutputError) as ei:
        validate_tts_output(
            receipt_id=AudioValidationReceiptId("ar-4"),
            run_id=AudioSynthesisRunId("run-1"),
            audio_bytes=data,
            declared_sample_rate=22050,
            declared_channel_layout="mono",
            provider_expected_sample_rate=22050,
            expected_content_hash="f" * 64,
            decode_ok=True,
            declared_duration_seconds=2.0,
        )
    assert AudioValidationIssueCode.CONTENT_HASH_MISMATCH.value in ei.value.details["issues"]


def test_tts_undecodable_or_zero_duration_fails_closed():
    data = b"RIFF1234WAVE"
    with pytest.raises(TtsInvalidOutputError) as ei:
        validate_tts_output(
            receipt_id=AudioValidationReceiptId("ar-5"),
            run_id=AudioSynthesisRunId("run-1"),
            audio_bytes=data,
            declared_sample_rate=22050,
            declared_channel_layout="mono",
            provider_expected_sample_rate=22050,
            expected_content_hash=_h(data),
            decode_ok=False,
            declared_duration_seconds=-1.0,
        )
    codes = ei.value.details["issues"]
    assert AudioValidationIssueCode.DECODE_FAILED.value in codes
    assert AudioValidationIssueCode.ZERO_DURATION.value in codes


# --- backlog 5: forced alignment + alignment hash ------------------------------
def _audio_asset() -> TtsAudioAsset:
    return TtsAudioAsset(
        asset_id=TtsAudioAssetId("ta-1"),
        content_hash="a" * 64,
        sample_rate=22050,
        channel_layout="mono",
        duration_seconds=3.0,
        byte_size=1000,
        source_request_hash="b" * 64,
    )


def _align_req() -> AlignmentRequest:
    return AlignmentRequest(
        run_id=ForcedAlignRunId("fa-1"),
        audio_asset_id=TtsAudioAssetId("ta-1"),
        text="Xin chào bạn",
        locale="vi-VN",
    )


def test_alignment_low_confidence_fails_closed():
    with pytest.raises(LowConfidenceAlignmentError):
        align(
            receipt_id=AlignmentReceiptId("al-1"),
            request=_align_req(),
            words=[{"word": "xin", "start": 0.0, "end": 0.3, "confidence": 0.4}],
            phonemes=[],
            segment_confidence=ALIGNMENT_CONFIDENCE_FLOOR - 0.05,
            aligner_name="aligner",
            aligner_version="1.0",
            model_name="m1",
            model_version="v1",
            audio_content_hash=("a" * 64),
        )


def test_alignment_high_confidence_passes_and_hash_stable():
    words = [{"word": "xin", "start": 0.0, "end": 0.3, "confidence": 0.95}]
    r1 = align(
        receipt_id=AlignmentReceiptId("al-2"),
        request=_align_req(),
        words=words,
        phonemes=[],
        segment_confidence=0.9,
        aligner_name="aligner",
        aligner_version="1.0",
        model_name="m1",
        model_version="v1",
        audio_content_hash=("a" * 64),
    )
    r2 = align(
        receipt_id=AlignmentReceiptId("al-3"),
        request=_align_req(),
        words=words,
        phonemes=[],
        segment_confidence=0.9,
        aligner_name="aligner",
        aligner_version="1.0",
        model_name="m1",
        model_version="v1",
        audio_content_hash=("a" * 64),
    )
    assert isinstance(r1, AlignmentResult)
    assert r1.alignment_hash == r2.alignment_hash  # deterministic
    assert r1.segment_confidence == 0.9
    assert r1.aligner_name == "aligner"


def test_alignment_hash_changes_with_text_or_audio():
    h1 = compute_alignment_hash(audio_content_hash="a" * 64, text="xin chào", locale="vi-VN", timestamps=[])
    h2 = compute_alignment_hash(audio_content_hash="a" * 64, text="chào again", locale="vi-VN", timestamps=[])
    h3 = compute_alignment_hash(audio_content_hash="c" * 64, text="xin chào", locale="vi-VN", timestamps=[])
    assert h1 == h1
    assert h1 != h2
    assert h1 != h3


# --- backlog 6: typed line-timing proposals (never silently cut) ---------------
def _resolver_proposal(**kw):
    return LineTimingResolver.resolve(
        resolution_id=LineTimingResolutionId("t-1"),
        run_id=AudioSynthesisRunId("run-1"),
        line_seconds=kw.get("line", 5.0),
        shot_seconds=kw.get("shot", 2.0),
        can_extend_shot=kw.get("extend", False),
        can_shorten_text=kw.get("shorten", False),
        can_change_pacing=kw.get("pace", False),
    )


def test_overlong_line_never_auto_cut():
    p = _resolver_proposal(line=5.0, shot=2.0)
    assert isinstance(p, TimingResolutionIssue)
    # default (no mechanical option) -> human review, never a silent cut
    assert p.proposal == LineTimingProposalType.HUMAN_REVIEW
    assert p.line_seconds == 5.0 and p.shot_seconds == 2.0


def test_resolver_prefers_extend_then_shorten_then_pacing():
    assert _resolver_proposal(extend=True).proposal == LineTimingProposalType.EXTEND_SHOT
    assert _resolver_proposal(shorten=True).proposal == LineTimingProposalType.SHORTEN_TEXT
    assert _resolver_proposal(pace=True).proposal == LineTimingProposalType.CHANGE_PACING


def test_line_within_shot_is_not_a_proposal():
    with pytest.raises(OverlongLineError):
        _resolver_proposal(line=1.0, shot=2.0)


# --- backlog 7: persisted concurrency state + resume ---------------------------
def _node(exec_id: str, req_hash: str, status: AudioNodeStatus, asset: TtsAudioAssetId | None) -> AudioDagNode:
    return AudioDagNode(
        execution_id=AudioNodeExecutionId(exec_id),
        provider_id="p1",
        line_key="char-mai:rev1",
        status=status,
        request_hash=req_hash,
        completed_audio_asset_id=asset,
    )


def test_resume_reuses_completed_audio():
    hash_a = "a" * 64
    state = AudioConcurrencyState(
        state_id=AudioConcurrencyStateId("cs-1"),
        revision_hash=RH,
        nodes=[_node("e1", hash_a, AudioNodeStatus.COMPLETED, TtsAudioAssetId("ta-x"))],
    )
    assert reuseable_audio(state=state, request_hash=hash_a)
    assert not reuseable_audio(state=state, request_hash="f" * 64)


def test_cancelled_or_failed_node_never_reused():
    hash_a = "a" * 64
    state = AudioConcurrencyState(
        state_id=AudioConcurrencyStateId("cs-2"),
        revision_hash=RH,
        nodes=[
            _node("e1", hash_a, AudioNodeStatus.CANCELLED, None),
            _node("e2", "b" * 64, AudioNodeStatus.FAILED, None),
        ],
    )
    assert not reuseable_audio(state=state, request_hash=hash_a)
    assert not reuseable_audio(state=state, request_hash="b" * 64)


def test_state_mark_is_immutable():
    state = AudioConcurrencyState(state_id=AudioConcurrencyStateId("cs-3"), revision_hash=RH, nodes=[])
    new = state.mark(_node("e1", "a" * 64, AudioNodeStatus.COMPLETED, TtsAudioAssetId("ta-x")))
    assert len(state.nodes) == 0  # original untouched
    assert len(new.nodes) == 1
    assert new.nodes[0].status == AudioNodeStatus.COMPLETED


def test_models_are_immutable():
    s = AudioConcurrencyState(state_id=AudioConcurrencyStateId("cs-4"), revision_hash=RH, nodes=[])
    with pytest.raises(ValueError):
        s.revision_hash = "f" * 64


# --- backlog 8: per-provider concurrency / retry budget ------------------------
def test_concurrency_policy_enforces_positive_retry_slot():
    p = ConcurrencyPolicy(
        provider_id=PH("p1"), max_concurrency=4, retry_budget=2, timeout_seconds=30.0,
        cancellation_grace_seconds=5.0,
    )
    assert p.max_concurrency == 4
    assert p.retry_budget == 2
    with pytest.raises(ValueError):
        ConcurrencyPolicy(
            provider_id=PH("p1"), max_concurrency=0, retry_budget=1, timeout_seconds=10.0,
            cancellation_grace_seconds=0.0,
        )


# --- backlog 9: dialogue/voice vs BGM invalidation -----------------------------
def test_dialogue_change_invalidates_track_alignment_facial_mix():
    scope = invalidate_audio_scope(changed="dialogue", voice_profile_hash="", asset=None)
    assert scope == AudioInvalidationScope.TRACK_AND_MIX


def test_voice_change_invalidates_track_facial_mix():
    scope = invalidate_audio_scope(changed="voice", voice_profile_hash=SH, asset=None)
    assert scope == AudioInvalidationScope.TRACK_AND_MIX


def test_bgm_change_invalidates_mix_only():
    from windagent_core.domain.video_production.audio import AudioMixPlan
    from windagent_core.domain.video_production.ids import AudioMixPlanId, ProductionRevisionId, VideoProjectId

    mix = AudioMixPlan(
        mix_id=AudioMixPlanId("mix-1"),
        project_id=VideoProjectId("proj-1"),
        revision_id=ProductionRevisionId("rev-1"),
    )
    scope = invalidate_audio_scope(changed="BGM", voice_profile_hash="", asset=mix)
    assert scope == AudioInvalidationScope.MIX_ONLY


# --- secret redaction in receipts ---------------------------------------------
def test_secrets_redacted_from_receipt():
    receipt = {"provider_token": "sk-secret123", "ok": "fine", "nested": {"api_key": "abc"}, "arr": [{"bearer": "x"}]}
    out = redact_secrets(receipt)
    assert out["provider_token"] == "<redacted>"
    assert out["nested"]["api_key"] == "<redacted>"
    assert out["arr"][0]["bearer"] == "<redacted>"
    assert out["ok"] == "fine"
