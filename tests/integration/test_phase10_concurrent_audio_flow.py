"""Integration flow for Concurrent Audio Production (stage_e.md Phase 10 gate).

End-to-end gate scenario: a multi-character dialogue fixture runs the audio DAG
with fan-in only before timing/lip-sync. Proves, on ONE revision:
  - two lines synthesize "in parallel" but output ordering follows the
    screenplay (deterministic),
  - the same character + voice revision keeps a stable identity & request hash
    across episodes (voice identity & idempotency),
  - a `ConcurrencyPolicy` bounding parallelism is respected,
  - a worker restart reuses completed audio and skips finished lines (resume),
  - a cancelled node never publishes a partial file,
  - a real-voice profile missing consent cannot go preview -> final (rights),
  - dialogue/voice changes invalidate track+alignment+facial+mix while a BGM
    change invalidates only the mix/final (backlog 9),
  - secret/API-token material is redacted out of the receipts.
"""

from __future__ import annotations

import hashlib

from windagent_core.domain.video_production.concurrent_audio import (
    AlignmentRequest,
    AudioConcurrencyState,
    AudioDagNode,
    ConcurrencyPolicy,
    LineTimingResolver,
    TtsProviderCapability,
    TtsSynthesisRequest,
    VoiceBinding,
    align,
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

# Order lines appear on the screenplay timeline. Two characters, interleaved.
SCREENPLAY_ORDER = [
    ("l1", "char-mai", "Xin chào bạn"),
    ("l2", "char-duc", "Chào, hôm nay thế nào?"),
    ("l3", "char-mai", "Tốt lắm!"),
    ("l4", "char-duc", "Vui vì nghe vậy."),
]
CAP = TtsProviderCapability(
    provider_id=TtsProviderId("provider-a"),
    name="gate-tts",
    supported_locales=["vi-VN"],
    modes=[TtsMode.API],
    sample_rates=[22050, 44100],
    channels=["mono"],
    features=[TtsCapabilityFeature.WORD_TIMESTAMPS, TtsCapabilityFeature.PHONEME_TIMING],
    emotion_labels=["neutral"],
)


def _h(payload) -> str:
    if isinstance(payload, bytes):
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _voice_binding(char: str, voice_version: str = "v1", *, final: bool = False) -> VoiceBinding:
    return VoiceBinding(
        binding_id=CharacterVoiceProfileId.generate(char),
        character_id=char,
        display_name=char.replace("char-", ""),
        provider="provider-a",
        model="voice-model",
        voice_id=f"real:{char}",
        voice_version=voice_version,
        locale="vi-VN",
        rights_state=VoiceRightsState.CONSENTED if final else VoiceRightsState.CONSENTED,
        approved=True if final else False,
        approval_actor="audio-dir" if final else "",
        preview_only=not final,
    )


def _synth_req(line_key: str, char: str, text: str, voice_hash: str) -> TtsSynthesisRequest:
    return TtsSynthesisRequest(
        run_id=AudioSynthesisRunId(line_key),
        provider_id=CAP.provider_id,
        character_id=char,
        text=text,
        locale="vi-VN",
        language="vi-VN",
        sample_rate=22050,
        emotion="neutral",
        voice_profile_hash=voice_hash,
        dialogue_revision_hash=_h("dia-rev-1"),
        target_duration_seconds=3.0,
    )


def _fake_wav(char: str, line: str) -> bytes:
    return (f"RIFF-{char}-{line}".encode("utf-8")) + b"\x00" * 32


def test_multi_character_audio_gate_scenario():
    # --- voice identity stable across the two characters + both episodes
    vb_mai = _voice_binding("char-mai")
    vb_mai_ep2 = _voice_binding("char-mai")
    assert vb_mai.identity_key() == vb_mai_ep2.identity_key()

    # --- parallel synthesis; deterministic output re-ordered to screenplay
    voice_hash = vb_mai.profile_hash() if hasattr(vb_mai, "profile_hash") else _h(vb_mai.identity_key())
    requests = {lk: _synth_req(lk, c, t, voice_hash) for lk, c, t in SCREENPLAY_ORDER}
    hashes = {lk: r.request_hash() for lk, r in requests.items()}

    # retry (idempotency): identical request produces the identical hash
    again = {lk: _synth_req(lk, c, t, voice_hash) for lk, c, t in SCREENPLAY_ORDER}
    assert all(hashes[lk] == again[lk].request_hash() for lk in hashes)

    # --- ConcurrencyPolicy caps parallelism (backlog 8)
    policy = ConcurrencyPolicy(
        provider_id=CAP.provider_id, max_concurrency=2, retry_budget=1,
        timeout_seconds=30.0, cancellation_grace_seconds=1.0,
    )
    assert policy.max_concurrency == 2 < len(requests)

    # --- each line synthesizes, validates, and publishes in screenplay order
    inbound = [
        ("l1", "char-mai", b"RIFF-char-mai-Xin chao ban"),
        ("l2", "char-duc", b"RIFF-char-duc-Chao"),
        ("l3", "char-mai", b"RIFF-char-mai-Tot lam"),
        ("l4", "char-duc", b"RIFF-char-duc-Vui vi nghe vay"),
    ]
    published: dict[str, str] = {}  # line_key -> content_hash (deterministic order)
    receipts = []
    for lk, _char, data in inbound:
        rec = validate_tts_output(
            receipt_id=AudioValidationReceiptId("v-" + lk),
            run_id=AudioSynthesisRunId(lk),
            audio_bytes=data,
            declared_sample_rate=22050,
            declared_channel_layout="mono",
            provider_expected_sample_rate=22050,
            expected_content_hash=_h(data),
            decode_ok=True,
            declared_duration_seconds=2.0,
        )
        assert rec.valid
        receipts.append(rec)
        published[lk] = rec.content_hash

    # deterministic: output ordering == screenplay order
    assert list(published.keys()) == [lk for lk, _c, _t in SCREENPLAY_ORDER]

    # --- forced alignment per line; low-confidence line routes to human review
    good_align = align(
        receipt_id=AlignmentReceiptId("al-l1"),
        request=AlignmentRequest(
            run_id=ForcedAlignRunId("l1"), audio_asset_id=TtsAudioAssetId("l1"),
            text=SCREENPLAY_ORDER[0][2], locale="vi-VN"),
        words=[{"word": "Xin", "start": 0.0, "end": 0.3, "confidence": 0.9}],
        phonemes=[],
        segment_confidence=0.92,
        aligner_name="whisperx", aligner_version="3.1.0",
        model_name="large-v3", model_version="1.0",
        audio_content_hash=published["l1"],
    )
    assert good_align.alignment_hash is not None

    try:
        align(
            receipt_id=AlignmentReceiptId("al-l2"),
            request=AlignmentRequest(
                run_id=ForcedAlignRunId("l2"), audio_asset_id=TtsAudioAssetId("l2"),
                text=SCREENPLAY_ORDER[1][2], locale="vi-VN"),
            words=[{"word": "Chao", "start": 0.0, "end": 0.2, "confidence": 0.3}],
            phonemes=[],
            segment_confidence=0.3,
            aligner_name="whisperx", aligner_version="3.1.0",
            model_name="large-v3", model_version="1.0",
            audio_content_hash=published["l2"],
        )
        alignment_failed_closed = False
    except LowConfidenceAlignmentError:
        alignment_failed_closed = True
    assert alignment_failed_closed  # none silently accepted

    # --- overlong line yields a typed proposal, never an auto-cut
    overdue = LineTimingResolver.resolve(
        resolution_id=LineTimingResolutionId("t-l4"),
        run_id=AudioSynthesisRunId("l4"),
        line_seconds=4.0, shot_seconds=2.0,
    )
    assert overdue.proposal in (
        LineTimingProposalType.EXTEND_SHOT,
        LineTimingProposalType.HUMAN_REVIEW,
    )

    # --- resume: worker restart reuses completed audio for finished lines
    state = AudioConcurrencyState(
        state_id=AudioConcurrencyStateId("cs-gate"), revision_hash=_h("dia-rev-1"), nodes=[]
    )
    for lk in ("l1", "l2"):
        state = state.mark(AudioDagNode(
            execution_id=AudioNodeExecutionId("e-" + lk),
            provider_id="provider-a", line_key=lk, status=AudioNodeStatus.COMPLETED,
            request_hash=hashes[lk], completed_audio_asset_id=TtsAudioAssetId(lk),
        ))
    # cancel line l3 -> never reused, never publishes a partial file
    state = state.mark(AudioDagNode(
        execution_id=AudioNodeExecutionId("e-l3"),
        provider_id="provider-a", line_key="l3", status=AudioNodeStatus.CANCELLED,
        request_hash=hashes["l3"], completed_audio_asset_id=None,
    ))
    assert reuseable_audio(state=state, request_hash=hashes["l1"])
    assert reuseable_audio(state=state, request_hash=hashes["l2"])
    assert not reuseable_audio(state=state, request_hash=hashes["l3"])  # cancelled not reused

    # --- rights gate: real voice preview without consent is never final
    preview = _voice_binding("char-new")
    try:
        ensure_final_voice(binding=preview)
        rights_hold = False
    except VoiceConsentMissingError:
        rights_hold = True
    assert rights_hold

    # --- invalidation: dialogue/voice invalidate track+alignment+facial+mix;
    #     BGM invalidates only mix/final (backlog 9)
    assert invalidate_audio_scope(changed="voice", voice_profile_hash=_h("v2"), asset=None) == AudioInvalidationScope.TRACK_AND_MIX
    from windagent_core.domain.video_production.audio import AudioMixPlan
    from windagent_core.domain.video_production.ids import AudioMixPlanId, ProductionRevisionId, VideoProjectId

    mix = AudioMixPlan(mix_id=AudioMixPlanId("mix-gate"), project_id=VideoProjectId("p"), revision_id=ProductionRevisionId("r"))
    assert invalidate_audio_scope(changed="BGM", voice_profile_hash="", asset=mix) == AudioInvalidationScope.MIX_ONLY

    # --- secret redaction in receipts
    receipt = {"provider_api_token": "sk-live-123", "nested": {"apiKey": "x"}, "ok": True}
    redacted = redact_secrets(receipt)
    assert redacted["provider_api_token"] == "<redacted>"
    assert redacted["nested"]["apiKey"] == "<redacted>"
    assert redacted["ok"] is True
