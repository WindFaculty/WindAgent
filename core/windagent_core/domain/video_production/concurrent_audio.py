""""
Concurrent Audio Production kernel (VP3D Phase 10, Stage E).

Implements the stage_e Phase 10 backlog that the legacy `audio.py` models
(created plan 06 Phase 21) do not cover: provider capability metadata, versioned
voice identity, canonical request hashing (idempotent retry), fail-closed TTS
output validation, forced alignment with a dedicated port + alignment hash,
typed line-timing proposals, persisted DAG concurrency state with resume, and
a dialogue/voice-vs-BGM invalidation map.

Design rules (mirror character_master.py / rigging.py):
  - immutable Pydantic models (`ConfigDict(frozen=True, extra="allow")`);
  - deterministic SHA-256 hashing over canonical JSON (`json.dumps(sort_keys,
    separators=(",",":"), ensure_ascii=False)`) — same input -> same hash;
  - fail-closed services raise typed errors; nothing invalid is published;
  - secret/API-token material is redacted before it enters any receipt.

Dependencies: only `windagent_core` (domain enums/ids/errors + `audio.py`).
Never imports providers/tools/intelligence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.audio import (
    TtsAudioAsset,
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

AUDIO_DAG_VERSION = "1.0.0"

# Alignment confidence floor below which timing never reaches facial/lip-sync.
ALIGNMENT_CONFIDENCE_FLOOR = 0.6
# Shot-duration tolerance before a line is flagged overlong (backlog 6).
LINE_DURATION_TOLERANCE = 0.0
# Sample rate bytes-per-sample map used for the decode/size sanity check.
_CHANNEL_LAYOUT_CHANNEL_COUNT = {"mono": 1, "stereo": 2, "5.1": 6}
_SECRET_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|bearer|password|authorization|credential)",
    re.IGNORECASE,
)


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def redact_secrets(obj: Dict[str, Any], keys: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Deep-redact any secret-looking values before they enter a receipt.

    The backstage test requires secret/API-token material to be redacted out of
    receipts (stage_e §4). Any key whose name matches a secret pattern, or any
    key listed in `keys`, is replaced with "<redacted>" — recursively.
    """
    redacted_keys = keys or {}
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if str(k) in redacted_keys or _SECRET_PATTERN.search(str(k)):
            out[str(k)] = "<redacted>"
        elif isinstance(v, (dict, list)):
            out[str(k)] = redact_secrets(v)
        else:
            out[str(k)] = v
    return out


class TtsProviderCapability(BaseModel):
    """Concrete capability metadata a TTS engine advertises (stage_e backlog 1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    provider_id: TtsProviderId
    name: str = Field(min_length=1)
    supported_locales: List[str] = Field(default_factory=list)
    modes: List[TtsMode] = Field(default_factory=lambda: [TtsMode.API])
    sample_rates: List[int] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=lambda: ["mono"])
    features: List[TtsCapabilityFeature] = Field(default_factory=list)
    emotion_labels: List[str] = Field(default_factory=list)

    def supports_locale(self, locale: str) -> bool:
        return locale in self.supported_locales

    def supports_feature(self, feature: TtsCapabilityFeature) -> bool:
        return feature in self.features

    def supports_sample_rate(self, rate: int) -> bool:
        return rate in self.sample_rates

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": str(self.provider_id),
            "name": self.name,
            "supported_locales": self.supported_locales,
            "modes": [m.value for m in self.modes],
            "sample_rates": self.sample_rates,
            "channels": self.channels,
            "features": [f.value for f in self.features],
            "emotion_labels": self.emotion_labels,
        }


class TtsSynthesisRequest(BaseModel):
    """One voice line synthesis request (stage_e backlog 3)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: AudioSynthesisRunId
    provider_id: TtsProviderId
    character_id: str  # bound to character, never display name
    text: str = Field(min_length=1)
    locale: str = "vi-VN"
    language: str = "vi-VN"
    sample_rate: int = Field(gt=0)
    emotion: str = ""
    voice_profile_hash: str = Field(min_length=64, max_length=64)
    dialogue_revision_hash: str = Field(min_length=64, max_length=64)
    target_duration_seconds: float = Field(gt=0)

    def request_hash(self) -> str:
        """Canonical synthesis request hash (stage_e backlog 3).

        Derived from dialogue revision + voice profile hash + synthesis params.
        Two identical requests (same revision, same voice, same params) yield
        the SAME hash so retry reuses the artifact instead of re-synthesizing.
        """
        return _hash(
            {
                "dialogue_revision_hash": self.dialogue_revision_hash,
                "voice_profile_hash": self.voice_profile_hash,
                "provider_id": str(self.provider_id),
                "text": self.text,
                "locale": self.locale,
                "language": self.language,
                "sample_rate": self.sample_rate,
                "emotion": self.emotion,
            }
        )


class AudioValidationReceipt(BaseModel):
    """Result of validating a raw TTS output before publish (stage_e backlog 4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: AudioValidationReceiptId
    run_id: AudioSynthesisRunId
    content_hash: str = Field(min_length=64, max_length=64)
    sample_rate: int = Field(gt=0)
    channel_layout: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    byte_size: int = Field(ge=0)
    issues: List[AudioValidationIssueCode] = Field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_tts_output(
    *,
    receipt_id: AudioValidationReceiptId,
    run_id: AudioSynthesisRunId,
    audio_bytes: bytes,
    declared_sample_rate: int,
    declared_channel_layout: str,
    provider_expected_sample_rate: int,
    expected_content_hash: str,
    decode_ok: bool,
    declared_duration_seconds: float = 0.0,
) -> AudioValidationReceipt:
    """Fail-closed TTS output validation (stage_e backlog 4).

    Checks, in order: non-empty bytes, a cheap decode probe (`decode_ok`),
    declared duration > 0, sample rate matches the capability expectation,
    channel layout is known, and content hash matches. Any failure is recorded
    as a typed issue; a receipt with issues is never used to publish. Empty
    payload raises `TtsEmptyOutputError`; a non-empty but invalid payload
    raises `TtsInvalidOutputError`.
    """
    issues: List[AudioValidationIssueCode] = []

    if not audio_bytes:
        raise TtsEmptyOutputError(
            "TTS provider returned empty output",
            details={"run_id": str(run_id)},
        )

    if declared_duration_seconds <= 0:
        issues.append(AudioValidationIssueCode.ZERO_DURATION)

    if declared_sample_rate <= 0 or declared_sample_rate != provider_expected_sample_rate:
        issues.append(AudioValidationIssueCode.SAMPLE_RATE_INVALID)

    if declared_channel_layout not in _CHANNEL_LAYOUT_CHANNEL_COUNT:
        issues.append(AudioValidationIssueCode.CHANNEL_LAYOUT_INVALID)

    if not decode_ok:
        issues.append(AudioValidationIssueCode.DECODE_FAILED)

    actual_hash = hashlib.sha256(audio_bytes).hexdigest()
    if expected_content_hash and actual_hash != expected_content_hash:
        issues.append(AudioValidationIssueCode.CONTENT_HASH_MISMATCH)

    duration = declared_duration_seconds if declared_duration_seconds > 0 else declared_sample_rate
    receipt = AudioValidationReceipt(
        receipt_id=receipt_id,
        run_id=run_id,
        content_hash=actual_hash,
        sample_rate=declared_sample_rate,
        channel_layout=declared_channel_layout,
        duration_seconds=duration,
        byte_size=len(audio_bytes),
        issues=issues,
    )
    if not receipt.valid:
        raise TtsInvalidOutputError(
            "TTS output failed validation and is not published",
            details={"run_id": str(run_id), "issues": [i.value for i in issues]},
        )
    return receipt


class VerifiedAudioAsset(BaseModel):
    """A TTS output that passed validation and may be published (backlog 4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    asset: TtsAudioAsset
    validation_receipt: AudioValidationReceipt

    def to_dict(self) -> Dict[str, Any]:
        return {"asset": self.asset.to_dict(), "validation": self.validation_receipt.model_dump()}


class VoiceBinding(BaseModel):
    """Versioned voice identity for a character (stage_e backlog 2)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: CharacterVoiceProfileId
    character_id: str
    display_name: str  # cosmetic only; the bind key is character_id + version
    provider: str
    model: str
    voice_id: str
    voice_version: str
    locale: str
    rights_state: VoiceRightsState = VoiceRightsState.UNKNOWN
    approved: bool = False
    approval_actor: str = ""
    preview_only: bool = True

    def identity_key(self) -> str:
        """The stable bind key: character + provider/model/voice/version.

        A display-name change does NOT change the bind key (backlog 2), so a
        rename never re-casts the voice; a voice/version change DOES create a
        new key and a new artifact.
        """
        return ":".join([self.character_id, self.provider, self.model, self.voice_id, self.voice_version])

    @property
    def usable_as_final(self) -> bool:
        """Real-voice likeness requires consent+approval (stage_e §4).

        A preview profile is never final. A real-voice (non-synthetic) profile
        additionally needs rights consent + an approval actor.
        """
        if self.preview_only:
            return False
        is_real_voice = self.voice_id.startswith("real:")
        if is_real_voice:
            return self.rights_state == VoiceRightsState.CONSENTED and self.approved and bool(self.approval_actor)
        return self.approved


def ensure_final_voice(*, binding: VoiceBinding) -> VoiceBinding:
    """Fail-closed rights gate: preview/real-voice without consent never final.

    Returns the binding unchanged when it is usable as final; otherwise raises
    `VoiceConsentMissingError`. Mirrors stage_e test: real-voice profile missing
    consent cannot go preview -> final.
    """
    if binding.preview_only:
        raise VoiceConsentMissingError(
            "Preview voice profile cannot become final without approval",
            details={"binding_id": str(binding.binding_id), "reason": "preview_only"},
        )
    if binding.voice_id.startswith("real:") and (
        binding.rights_state != VoiceRightsState.CONSENTED
        or not binding.approved
        or not binding.approval_actor
    ):
        raise VoiceConsentMissingError(
            "Real-voice likeness missing rights/consent/approval",
            details={"binding_id": str(binding.binding_id), "reason": "real_voice_missing_consent"},
        )
    return binding


class AlignmentRequest(BaseModel):
    """Input to the forced-alignment port (stage_e backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    run_id: ForcedAlignRunId
    audio_asset_id: TtsAudioAssetId
    text: str = Field(min_length=1)
    locale: str = "vi-VN"
    lexicon_version: str = ""


class AlignmentResult(BaseModel):
    """Validated forced-alignment output (stage_e backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: AlignmentReceiptId
    run_id: ForcedAlignRunId
    audio_asset_id: TtsAudioAssetId
    aligner_name: str = Field(min_length=1)
    aligner_version: str = Field(min_length=1)
    model_name: str = ""
    model_version: str = ""
    word_timestamps: List[Dict[str, Any]] = Field(default_factory=list)
    phoneme_timestamps: List[Dict[str, Any]] = Field(default_factory=list)
    segment_confidence: float = Field(ge=0, le=1)
    alignment_hash: str = Field(min_length=64, max_length=64)


def compute_alignment_hash(*, audio_content_hash: str, text: str, locale: str, timestamps: List[Dict[str, Any]]) -> str:
    """Deterministic alignment hash (stage_e backlog 5).

    Same audio + same text + same timestamps -> same hash, so an alignment is
    reusable across episodes without a re-run.
    """
    return _hash(
        {
            "audio_content_hash": audio_content_hash,
            "text": text,
            "locale": locale,
            "timestamps": timestamps,
        }
    )


def align(
    *,
    receipt_id: AlignmentReceiptId,
    request: AlignmentRequest,
    words: List[Dict[str, Any]],
    phonemes: List[Dict[str, Any]],
    segment_confidence: float,
    aligner_name: str,
    aligner_version: str,
    model_name: str,
    model_version: str,
    audio_content_hash: str,
) -> AlignmentResult:
    """Build a validated AlignmentResult, applying the confidence gate.

    A whole-segment confidence below `ALIGNMENT_CONFIDENCE_FLOOR` is never used
    for facial/lip-sync: it raises `LowConfidenceAlignmentError` instead of
    being silently accepted (stage_e backlog 5).
    """
    if segment_confidence < ALIGNMENT_CONFIDENCE_FLOOR:
        raise LowConfidenceAlignmentError(
            "Alignment confidence below usable floor; route to human review",
            details={
                "receipt_id": str(receipt_id),
                "confidence": segment_confidence,
                "floor": ALIGNMENT_CONFIDENCE_FLOOR,
            },
        )
    alignment_hash = compute_alignment_hash(
        audio_content_hash=audio_content_hash,
        text=request.text,
        locale=request.locale,
        timestamps=words,
    )
    return AlignmentResult(
        receipt_id=receipt_id,
        run_id=request.run_id,
        audio_asset_id=request.audio_asset_id,
        aligner_name=aligner_name,
        aligner_version=aligner_version,
        model_name=model_name,
        model_version=model_version,
        word_timestamps=words,
        phoneme_timestamps=phonemes,
        segment_confidence=segment_confidence,
        alignment_hash=alignment_hash,
    )


class TimingResolutionIssue(BaseModel):
    """Typed resolution for a line longer than its shot (stage_e backlog 6)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    resolution_id: LineTimingResolutionId
    run_id: AudioSynthesisRunId
    proposal: LineTimingProposalType
    line_seconds: float = Field(gt=0)
    shot_seconds: float = Field(gt=0)
    reason: str = ""


class LineTimingResolver:
    """Never silently cuts an overlong line; emits a typed proposal (backlog 6)."""

    @staticmethod
    def resolve(
        *,
        resolution_id: LineTimingResolutionId,
        run_id: AudioSynthesisRunId,
        line_seconds: float,
        shot_seconds: float,
        can_extend_shot: bool = False,
        can_shorten_text: bool = False,
        can_change_pacing: bool = False,
    ) -> TimingResolutionIssue:
        """Produce the safest typed proposal for an overlong line.

        Order of preference (safest mechanical first) then human review:
        EXTEND_SHOT -> SHORTEN_TEXT -> CHANGE_PACING -> HUMAN_REVIEW. A line
        within tolerance yields no resolution (`suma` not raised). If the line
        exceeds the shot by more than a hard margin and no mechanical option is
        available, the proposal is HUMAN_REVIEW — never an auto-cut.
        """
        if line_seconds <= shot_seconds + LINE_DURATION_TOLERANCE:
            raise OverlongLineError(
                "Line fits within shot; no timing proposal needed",
                details={"run_id": str(run_id), "reason": "line_within_shot"},
            )
        if can_extend_shot:
            proposal = LineTimingProposalType.EXTEND_SHOT
        elif can_shorten_text:
            proposal = LineTimingProposalType.SHORTEN_TEXT
        elif can_change_pacing:
            proposal = LineTimingProposalType.CHANGE_PACING
        else:
            proposal = LineTimingProposalType.HUMAN_REVIEW
        return TimingResolutionIssue(
            resolution_id=resolution_id,
            run_id=run_id,
            proposal=proposal,
            line_seconds=line_seconds,
            shot_seconds=shot_seconds,
            reason=f"line {line_seconds:.2f}s exceeds shot {shot_seconds:.2f}s; proposal={proposal.value}",
        )


class ConcurrencyPolicy(BaseModel):
    """Per-provider concurrency, retry budget and cancellation (stage_e backlog 8)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    provider_id: TtsProviderId
    max_concurrency: int = Field(ge=1)
    retry_budget: int = Field(ge=0)
    timeout_seconds: float = Field(gt=0)
    cancellation_grace_seconds: float = Field(ge=0)


class AudioDagNode(BaseModel):
    """One audio DAG node execution record (stage_e backlog 7 & 8)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    execution_id: AudioNodeExecutionId
    provider_id: str
    line_key: str  # dialogue_id:character:revision
    status: AudioNodeStatus = AudioNodeStatus.PENDING
    request_hash: str = Field(min_length=64, max_length=64)
    completed_audio_asset_id: Optional[TtsAudioAssetId] = None
    error_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": str(self.execution_id),
            "provider_id": self.provider_id,
            "line_key": self.line_key,
            "status": self.status.value,
            "request_hash": self.request_hash,
            "completed_audio_asset_id": str(self.completed_audio_asset_id) if self.completed_audio_asset_id else None,
            "error_code": self.error_code,
        }


class AudioConcurrencyState(BaseModel):
    """Persisted audio DAG state for resume across worker restarts (backlog 7)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    state_id: AudioConcurrencyStateId
    revision_hash: str = Field(min_length=64, max_length=64)
    dag_version: str = AUDIO_DAG_VERSION
    nodes: List[AudioDagNode] = Field(default_factory=list)

    def completed_request_hashes(self) -> set:
        return {
            n.request_hash
            for n in self.nodes
            if n.status in (AudioNodeStatus.COMPLETED, AudioNodeStatus.REUSED)
            and n.completed_audio_asset_id is not None
        }

    def status_for_request(self, request_hash: str) -> Optional[AudioNodeStatus]:
        for n in self.nodes:
            if n.request_hash == request_hash:
                return n.status
        return None

    def mark(self, node: AudioDagNode) -> "AudioConcurrencyState":
        """Return a NEW state with `node` upserted (immutable, fail-closed).

        A COMPLETED/REUSED node with an asset id is retained; a CANCELLED or
        FAILED node does not look completed (its request is never reused).
        """
        kept = [n for n in self.nodes if n.execution_id != node.execution_id]
        return AudioConcurrencyState(state_id=self.state_id, revision_hash=self.revision_hash, dag_version=self.dag_version, nodes=kept + [node])


def reuseable_audio(*, state: AudioConcurrencyState, request_hash: str) -> bool:
    """True when a completed node for this request hash can be reused (backlog 7).

    Drive resume: a worker restart reuses audio already completed for the same
    canonical request hash instead of re-synthesizing it (backlog 3 + 7).
    """
    return request_hash in state.completed_request_hashes()


def invalidate_audio_scope(*, changed: str, voice_profile_hash: str, asset: Any) -> AudioInvalidationScope:
    """Track/alignment/facial vs mix-only invalidation (stage_e backlog 9).

    - dialogue / voice (voice profile hash changed) -> invalidates the track,
      its alignment, facial/lip-sync AND the mix/final cut;
    - BGM/SFX change -> invalidates ONLY the mix/final cut, never the visual
      clips (mirrors `AudioMixPlan.invalidated_scope` for the audio branch).
    """

    if changed == "dialogue" or (changed == "voice" and voice_profile_hash):
        return AudioInvalidationScope.TRACK_AND_MIX
    if hasattr(asset, "invalidated_scope"):
        return asset.invalidated_scope(changed)
    # default: standalone BGM/SFX cue -> mix only
    return AudioInvalidationScope.MIX_ONLY


__all__ = [
    "AUDIO_DAG_VERSION",
    "ALIGNMENT_CONFIDENCE_FLOOR",
    "TtsProviderCapability",
    "TtsSynthesisRequest",
    "AudioValidationReceipt",
    "validate_tts_output",
    "VerifiedAudioAsset",
    "VoiceBinding",
    "ensure_final_voice",
    "AlignmentRequest",
    "AlignmentResult",
    "compute_alignment_hash",
    "align",
    "TimingResolutionIssue",
    "LineTimingResolver",
    "ConcurrencyPolicy",
    "AudioDagNode",
    "AudioConcurrencyState",
    "reuseable_audio",
    "invalidate_audio_scope",
    "redact_secrets",
]
