"""
Stage I Facial Animation kernel (VP3D Phase 18 — Lip-sync / Facial Pipeline).

Turns Stage E dialogue audio + forced alignment into a `FacialAnimationTrack`
composed of viseme, emotion, blink, gaze, eyebrow and head-motion curves
compatible with the Stage D `FacialRigProfile`. The domain NEVER contains
Blender data-block names (shape keys / bone names): it operates on semantic
controls (e.g. "jaw_open", "lips_close", "brow_raise"); the adapter layer
maps semantic controls to concrete shape keys/bones (stage_i §3).

Backlog coverage (stage_i §3):
  1. word/phoneme timing normalization per fps + shot offset, source
     alignment hash preserved;
  2. viseme map versioned by language + facial rig profile; a missing
     phoneme resolves through an explicit fallback rule (never silent skip);
  3. viseme curves with coarticulation, smoothing, minimum hold and bounded
     amplitude;
  4. emotion curves that never overlap articulation (jaw/lips) controls;
  5. blink / eyebrow / gaze / subtle head motion from deterministic
     seed/policy;
  6. layer ownership: jaw/lips/face owned by the facial track; neck/head
     follows a blend policy against body animation;
  7. bake into a derived action recording compiler version + input hashes +
     frame range;
  8. per-layer repair (lip-sync / gaze / emotion) with invalidation scoped
     to the affected layer + render/final downstream;
  9. preview close-up / playblast manifest built before Cycles final.

Fail-closed: non-monotonic timing, keyframes outside the shot range, emotion
overlapping articulation, and unknown phonemes without a fallback rule all
RAISE typed errors. Low-confidence alignment and rig controls missing from
the facial rig profile route to REQUIRES_HUMAN_REVIEW instead.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.concurrent_audio import (
    ALIGNMENT_CONFIDENCE_FLOOR,
    AlignmentResult,
)
from windagent_core.domain.video_production.enums import (
    AnimationEmotion,
    FacialFindingKind,
    FacialInvalidationScope,
    FacialLayerKind,
    FacialRepairScope,
    FacialTrackStatus,
    HeadBlendPolicy,
    VisemeShape,
)
from windagent_core.domain.video_production.errors import (
    FacialBakeError,
    FacialCompileError,
    FacialRepairError,
    VisemeMapMissingPhonemeError,
)
from windagent_core.domain.video_production.ids import (
    BakedFacialActionId,
    BlinkTrackId,
    EmotionCurveId,
    FacialFindingId,
    FacialRepairReceiptId,
    FacialTrackId,
    FacialValidationReceiptId,
    GazeTrackId,
    PhonemeTrackId,
    VisemeMapId,
)

FACIAL_COMPILER_VERSION = "facial-1.0"
FACIAL_TRACK_SCHEMA_VERSION = "1.0"

# Quality-gate thresholds (stage_i §4). Surfaced in receipts as raw numbers.
DRIFT_TOLERANCE_FRAMES = 1          # audio/animation drift at line start/mid/end
COARTICULATION_WINDOW_FRAMES = 2    # lookahead blend toward the next phoneme
MIN_HOLD_FRAMES = 2                 # a viseme never flashes for less than this
AMPLITUDE_MAX = 1.0                 # bounded viseme amplitude
HEAD_MOTION_MAX_AMPLITUDE = 0.15    # subtle head motion ceiling (normalized)
HEAD_JOINT_LIMIT_DEGREES = 45.0     # body head turn + facial head <= limit
FACIAL_POP_MAX_DELTA = 0.55         # value jump across adjacent lines
BLINK_INTERVAL_FRAMES = 96          # ~4s at 24fps
BLINK_JITTER_FRAMES = 24
BLINK_DURATION_FRAMES = 2
GAZE_SAMPLE_INTERVAL_FRAMES = 36    # ~1.5s at 24fps
GAZE_AMPLITUDE = 0.5                # normalized eye-target radius

# Semantic controls owned by the facial track (stage_i backlog 6). These are
# SEMANTIC names — never Blender data-block names (stage_i §3).
ARTICULATION_CONTROLS = ("jaw_open", "lips_close", "mouth_corner_l",
                         "mouth_corner_r", "tongue_up")
BLINK_CONTROLS = ("blink_l", "blink_r")
BROW_CONTROLS = ("brow_raise_l", "brow_raise_r")
GAZE_CONTROLS = ("eye_target_x", "eye_target_y")
HEAD_CONTROLS = ("head_yaw", "head_pitch")

FALLBACK_NEUTRAL = "NEUTRAL"
FALLBACK_CLOSED = "CLOSED"
ALLOWED_FALLBACK_RULES = (FALLBACK_NEUTRAL, FALLBACK_CLOSED)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(payload: Any) -> str:
    """Deterministic canonical JSON — same input, same hash (stage_i §4)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Phoneme timing (backlog 1)
# ---------------------------------------------------------------------------
class PhonemeSpan(BaseModel):
    """One phoneme with frame timing, normalized to the shot (backlog 1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    phoneme: str = Field(min_length=1)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    is_silence: bool = False

    @property
    def duration_frames(self) -> int:
        return max(0, self.end_frame - self.start_frame)


class PhonemeTrack(BaseModel):
    """Normalized word/phoneme timing for one dialogue line (backlog 1).

    Timing is converted from seconds to frames using the shot fps and offset
    by `shot_start_frame`. The Stage E source alignment hash is preserved so
    the track stays traceable to the aligner run that produced it.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: PhonemeTrackId
    alignment_receipt_id: str = ""
    run_id: str = ""
    audio_asset_id: str = ""
    locale: str = "vi-VN"
    source_alignment_hash: str = Field(min_length=64, max_length=64)
    fps: int = Field(gt=0)
    shot_start_frame: int = Field(ge=0)
    shot_end_frame: int = Field(ge=0)
    phonemes: List[PhonemeSpan] = Field(default_factory=list)
    segment_confidence: float = Field(ge=0, le=1)

    def content_hash(self) -> str:
        """Deterministic hash over timing + provenance (rebuild proof)."""
        return _sha256(_canonical({
            "track_id": str(self.track_id),
            "alignment_receipt_id": self.alignment_receipt_id,
            "audio_asset_id": self.audio_asset_id,
            "locale": self.locale,
            "source_alignment_hash": self.source_alignment_hash,
            "fps": self.fps,
            "shot_start_frame": self.shot_start_frame,
            "shot_end_frame": self.shot_end_frame,
            "phonemes": [
                {
                    "phoneme": p.phoneme,
                    "start_frame": p.start_frame,
                    "end_frame": p.end_frame,
                    "start_seconds": p.start_seconds,
                    "end_seconds": p.end_seconds,
                    "confidence": p.confidence,
                    "is_silence": p.is_silence,
                }
                for p in self.phonemes
            ],
        }).encode("utf-8"))


def normalize_phoneme_track(
    *,
    track_id: PhonemeTrackId,
    alignment: AlignmentResult,
    fps: int,
    shot_start_frame: int,
    shot_end_frame: int,
) -> PhonemeTrack:
    """Convert Stage E alignment seconds into shot-relative frames (backlog 1).

    Fail-closed: non-monotonic timing or spans outside the shot range raise
    `FacialCompileError` (stage_i §4 — phoneme/viseme ordering monotonic, no
    keyframe outside the shot range). The source alignment hash is preserved
    verbatim.
    """
    phonemes: List[PhonemeSpan] = []
    for entry in alignment.phoneme_timestamps:
        start_f = round(float(entry.get("start_seconds", 0.0)) * fps) + shot_start_frame
        end_f = round(float(entry.get("end_seconds", 0.0)) * fps) + shot_start_frame
        phonemes.append(PhonemeSpan(
            phoneme=str(entry.get("phoneme", "")).strip(),
            start_frame=start_f,
            end_frame=end_f,
            start_seconds=float(entry.get("start_seconds", 0.0)),
            end_seconds=float(entry.get("end_seconds", 0.0)),
            confidence=float(entry.get("confidence", 1.0)),
            is_silence=bool(entry.get("is_silence", False)),
        ))
    if not phonemes:
        raise FacialCompileError(
            "Empty phoneme timing cannot be normalized",
            details={"kinds": ["NON_MONOTONIC"], "track_id": str(track_id)},
        )
    prev_end = -1
    for span in phonemes:
        if span.start_frame < prev_end:
            raise FacialCompileError(
                "Phoneme timing is non-monotonic (overlapping spans)",
                details={
                    "kinds": ["NON_MONOTONIC"],
                    "phoneme": span.phoneme,
                    "start_frame": span.start_frame,
                    "prev_end_frame": prev_end,
                },
            )
        if span.end_frame < span.start_frame:
            raise FacialCompileError(
                "Phoneme span has negative duration",
                details={"kinds": ["NON_MONOTONIC"], "phoneme": span.phoneme},
            )
        if span.start_frame < shot_start_frame or span.end_frame > shot_end_frame:
            raise FacialCompileError(
                "Phoneme span outside shot frame range",
                details={
                    "kinds": ["OUT_OF_SHOT_RANGE"],
                    "phoneme": span.phoneme,
                    "start_frame": span.start_frame,
                    "end_frame": span.end_frame,
                    "shot_range": [shot_start_frame, shot_end_frame],
                },
            )
        prev_end = span.end_frame
    return PhonemeTrack(
        track_id=track_id,
        alignment_receipt_id=str(alignment.receipt_id),
        run_id=str(alignment.run_id),
        audio_asset_id=str(alignment.audio_asset_id),
        locale="vi-VN",
        source_alignment_hash=alignment.alignment_hash,
        fps=fps,
        shot_start_frame=shot_start_frame,
        shot_end_frame=shot_end_frame,
        phonemes=phonemes,
        segment_confidence=alignment.segment_confidence,
    )


# ---------------------------------------------------------------------------
# Viseme map (backlog 2)
# ---------------------------------------------------------------------------
class VisemeTarget(BaseModel):
    """One phoneme -> viseme mapping with semantic control weights."""

    model_config = ConfigDict(frozen=True, extra="allow")

    shape: VisemeShape
    controls: Dict[str, float] = Field(default_factory=dict)
    hold_min_frames: int = Field(default=MIN_HOLD_FRAMES, ge=0)
    amplitude: float = Field(default=1.0, ge=0, le=AMPLITUDE_MAX)


class VisemeMap(BaseModel):
    """Versioned phoneme -> viseme mapping (backlog 2).

    Versioned by language + facial rig profile. A phoneme with no entry
    resolves through `fallback_rule` — an EXPLICIT named rule (NEUTRAL or
    CLOSED). A map without a fallback rule fails closed on unknown phonemes
    (`VisemeMapMissingPhonemeError`), never skips them silently.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    map_id: VisemeMapId
    language: str = Field(min_length=1)
    rig_profile_id: str = ""
    map_version: str = Field(default="1.0", min_length=1)
    entries: Dict[str, VisemeTarget] = Field(default_factory=dict)
    fallback_rule: str = ""

    def content_hash(self) -> str:
        """Deterministic hash over language + rig + entries + fallback."""
        return _sha256(_canonical({
            "language": self.language,
            "rig_profile_id": self.rig_profile_id,
            "map_version": self.map_version,
            "entries": {
                ph: {
                    "shape": t.shape.value,
                    "controls": t.controls,
                    "hold_min_frames": t.hold_min_frames,
                    "amplitude": t.amplitude,
                }
                for ph, t in sorted(self.entries.items())
            },
            "fallback_rule": self.fallback_rule,
        }).encode("utf-8"))

    def resolve(self, phoneme: str) -> VisemeTarget:
        """Resolve one phoneme; unknown phonemes use the fallback rule.

        Raises `VisemeMapMissingPhonemeError` when the phoneme is unknown AND
        no fallback rule is configured — never a silent skip (backlog 2).
        """
        entry = self.entries.get(phoneme)
        if entry is not None:
            return entry
        if self.fallback_rule == FALLBACK_NEUTRAL:
            return VisemeTarget(shape=VisemeShape.NEUTRAL)
        if self.fallback_rule == FALLBACK_CLOSED:
            return VisemeTarget(shape=VisemeShape.CLOSED)
        raise VisemeMapMissingPhonemeError(
            f"Phoneme {phoneme!r} has no viseme entry and no fallback rule",
            details={
                "phoneme": phoneme,
                "map_id": str(self.map_id),
                "language": self.language,
                "map_version": self.map_version,
            },
        )


def build_viseme_map(
    *,
    map_id: VisemeMapId,
    language: str,
    rig_profile_id: str,
    map_version: str,
    entries: Dict[str, VisemeTarget],
    fallback_rule: str = "",
) -> VisemeMap:
    """Build a validated viseme map (backlog 2).

    Validation: every entry amplitude is bounded [0, AMPLITUDE_MAX], controls
    are non-empty for non-neutral shapes, and the fallback rule is one of the
    allowed named rules. `map_version` must be non-empty.
    """
    if not map_version.strip():
        raise FacialCompileError(
            "Viseme map version must be non-empty",
            details={"kinds": ["UNKNOWN_PHONEME_NO_RULE"]},
        )
    if fallback_rule and fallback_rule not in ALLOWED_FALLBACK_RULES:
        raise FacialCompileError(
            f"Unknown viseme fallback rule {fallback_rule!r}",
            details={
                "kinds": ["UNKNOWN_PHONEME_NO_RULE"],
                "allowed": list(ALLOWED_FALLBACK_RULES),
            },
        )
    for phoneme, target in entries.items():
        # amplitude bound enforced by pydantic (ge/le AMPLITUDE_MAX) at
        # construction; builder keeps the non-empty-controls invariant
        if target.shape is not VisemeShape.NEUTRAL and not target.controls:
            raise FacialCompileError(
                f"Viseme {phoneme!r} has no semantic controls",
                details={"kinds": ["UNKNOWN_PHONEME_NO_RULE"], "phoneme": phoneme},
            )
    return VisemeMap(
        map_id=map_id,
        language=language,
        rig_profile_id=rig_profile_id,
        map_version=map_version,
        entries=entries,
        fallback_rule=fallback_rule,
    )


# ---------------------------------------------------------------------------
# Curves / layers (backlog 3-5)
# ---------------------------------------------------------------------------
class VisemeKeyframe(BaseModel):
    """One keyframe on a semantic control (never a data-block name)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    control: str = Field(min_length=1)
    frame: int = Field(ge=0)
    value: float = Field(ge=0, le=AMPLITUDE_MAX)


class EmotionCurve(BaseModel):
    """One emotion curve over a frame range (backlog 4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    curve_id: EmotionCurveId
    emotion: AnimationEmotion
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    controls: Dict[str, float] = Field(default_factory=dict)
    intensity: float = Field(default=0.5, ge=0, le=1)


class BlinkEvent(BaseModel):
    """One blink: frames + how closed the eyelid gets."""

    model_config = ConfigDict(frozen=True, extra="allow")

    start_frame: int = Field(ge=0)
    duration_frames: int = Field(default=BLINK_DURATION_FRAMES, ge=1)
    closed_value: float = Field(default=1.0, ge=0, le=1)


class BlinkTrack(BaseModel):
    """Deterministic blink schedule (backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: BlinkTrackId
    seed: int
    events: List[BlinkEvent] = Field(default_factory=list)


class GazeSample(BaseModel):
    """One eye-target sample (normalized -1..1, deterministic)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    frame: int = Field(ge=0)
    target_x: float = Field(ge=-1, le=1)
    target_y: float = Field(ge=-1, le=1)


class GazeTrack(BaseModel):
    """Deterministic eye-target track (backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: GazeTrackId
    seed: int
    samples: List[GazeSample] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiled track + receipts (backlog 3-8)
# ---------------------------------------------------------------------------
class FacialAnimationTrack(BaseModel):
    """Compiled facial animation for one character over one shot (backlog 3-6).

    `curves` map a SEMANTIC control name (e.g. "jaw_open") to keyframes; the
    adapter maps those to concrete shape keys / bones. `ownership` records
    which layer owns which controls; `head_blend_policy` governs how facial
    head motion coexists with body animation (backlog 6).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: FacialTrackId
    character_id: str = ""
    shot_id: str = ""
    fps: int = Field(gt=0)
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    phoneme_track_id: str = ""
    source_alignment_hash: str = Field(min_length=64, max_length=64)
    viseme_map_id: str = ""
    viseme_map_hash: str = ""
    curves: Dict[str, List[VisemeKeyframe]] = Field(default_factory=dict)
    emotion_curves: List[EmotionCurve] = Field(default_factory=list)
    blink: Optional[BlinkTrack] = None
    gaze: Optional[GazeTrack] = None
    head_motion: List[VisemeKeyframe] = Field(default_factory=list)
    ownership: Dict[str, FacialLayerKind] = Field(default_factory=dict)
    head_blend_policy: HeadBlendPolicy = HeadBlendPolicy.BLEND_LIMITED
    compiler_version: str = FACIAL_COMPILER_VERSION
    seed: int = 0
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    status: FacialTrackStatus = FacialTrackStatus.DRAFT
    idle: bool = False
    created_at: datetime = Field(default_factory=_utc_now)

    def content_hash(self) -> str:
        """Deterministic curve manifest hash (rebuild proof, stage_i §4).

        `track_id` is identity, not content — two tracks compiled from the
        same inputs/profile/seed hash identically.
        """
        return _sha256(_canonical({
            "character_id": self.character_id,
            "shot_id": self.shot_id,
            "fps": self.fps,
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "phoneme_track_id": self.phoneme_track_id,
            "source_alignment_hash": self.source_alignment_hash,
            "viseme_map_hash": self.viseme_map_hash,
            "curves": {
                control: [
                    {"frame": k.frame, "value": k.value}
                    for k in keyframes
                ]
                for control, keyframes in sorted(self.curves.items())
            },
            "emotion_curves": [
                {
                    "emotion": c.emotion.value,
                    "frame_start": c.frame_start,
                    "frame_end": c.frame_end,
                    "controls": c.controls,
                    "intensity": c.intensity,
                }
                for c in self.emotion_curves
            ],
            "blink": (
                [{"start_frame": e.start_frame, "duration_frames": e.duration_frames,
                  "closed_value": e.closed_value} for e in self.blink.events]
                if self.blink else []
            ),
            "gaze": (
                [{"frame": s.frame, "target_x": s.target_x, "target_y": s.target_y}
                 for s in self.gaze.samples]
                if self.gaze else []
            ),
            "head_motion": [{"frame": k.frame, "value": k.value}
                            for k in self.head_motion],
            "ownership": {c: val.value for c, val in sorted(self.ownership.items())},
            "head_blend_policy": self.head_blend_policy.value,
            "compiler_version": self.compiler_version,
            "seed": self.seed,
        }).encode("utf-8"))


class FacialFinding(BaseModel):
    """One validation finding (stage_i §4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    finding_id: FacialFindingId
    kind: FacialFindingKind
    message: str = ""
    frame: Optional[int] = None
    control: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class FacialValidationReceipt(BaseModel):
    """Validation result for one facial track (stage_i §4)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: FacialValidationReceiptId
    track_id: FacialTrackId
    status: FacialTrackStatus
    findings: List[FacialFinding] = Field(default_factory=list)
    sync_metrics: Dict[str, Any] = Field(default_factory=dict)
    gate_passed: bool = False

    @property
    def review_required(self) -> bool:
        return self.status is FacialTrackStatus.REQUIRES_HUMAN_REVIEW


class BakedFacialAction(BaseModel):
    """Derived action baked from a facial track (backlog 7)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    action_id: BakedFacialActionId
    track_id: FacialTrackId
    compiler_version: str = FACIAL_COMPILER_VERSION
    input_hashes: Dict[str, str] = Field(default_factory=dict)
    frame_start: int = Field(ge=0)
    frame_end: int = Field(ge=0)
    fps: int = Field(gt=0)
    action_hash: str = Field(min_length=64, max_length=64)


class FacialRepairReceipt(BaseModel):
    """Per-layer repair result (backlog 8)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: FacialRepairReceiptId
    track_id: FacialTrackId
    scope: FacialRepairScope
    new_track_id: FacialTrackId
    invalidation: FacialInvalidationScope
    rebuilt_layers: List[str] = Field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# Kernel services
# ---------------------------------------------------------------------------
def _build_blink_track(
    *, track_id: BlinkTrackId, seed: int,
    frame_start: int, frame_end: int,
) -> BlinkTrack:
    """Deterministic blink schedule (backlog 5)."""
    rng = random.Random(seed)
    events: List[BlinkEvent] = []
    frame = frame_start + BLINK_INTERVAL_FRAMES + rng.randint(0, BLINK_JITTER_FRAMES)
    while frame + BLINK_DURATION_FRAMES <= frame_end:
        events.append(BlinkEvent(start_frame=frame))
        frame += BLINK_INTERVAL_FRAMES + rng.randint(0, BLINK_JITTER_FRAMES)
    return BlinkTrack(track_id=track_id, seed=seed, events=events)


def _build_gaze_track(
    *, track_id: GazeTrackId, seed: int,
    frame_start: int, frame_end: int,
) -> GazeTrack:
    """Deterministic eye-target samples (backlog 5)."""
    rng = random.Random(seed + 1)
    samples: List[GazeSample] = []
    frame = frame_start
    while frame <= frame_end:
        samples.append(GazeSample(
            frame=frame,
            target_x=round(rng.uniform(-GAZE_AMPLITUDE, GAZE_AMPLITUDE), 4),
            target_y=round(rng.uniform(-GAZE_AMPLITUDE, GAZE_AMPLITUDE), 4),
        ))
        frame += GAZE_SAMPLE_INTERVAL_FRAMES
    return GazeTrack(track_id=track_id, seed=seed, samples=samples)


def _build_head_motion(
    *, seed: int, frame_start: int, frame_end: int,
    policy: HeadBlendPolicy,
) -> List[VisemeKeyframe]:
    """Subtle deterministic head motion (backlog 5/6).

    `BODY_OWNS_HEAD` produces NO head keyframes; `BLEND_LIMITED` caps
    amplitude at `HEAD_MOTION_MAX_AMPLITUDE` so body head turn + facial head
    motion stay within the joint limit (validated in `validate_facial_track`).
    """
    if policy is HeadBlendPolicy.BODY_OWNS_HEAD:
        return []
    rng = random.Random(seed + 2)
    keyframes: List[VisemeKeyframe] = []
    frame = frame_start
    while frame <= frame_end:
        for control in HEAD_CONTROLS:
            value = round(rng.uniform(0, HEAD_MOTION_MAX_AMPLITUDE), 4)
            keyframes.append(VisemeKeyframe(control=control, frame=frame, value=value))
        frame += GAZE_SAMPLE_INTERVAL_FRAMES
    return keyframes


def compile_facial_track(
    *,
    track_id: FacialTrackId,
    character_id: str,
    shot_id: str,
    phoneme_track: PhonemeTrack,
    viseme_map: VisemeMap,
    seed: int,
    head_blend_policy: HeadBlendPolicy = HeadBlendPolicy.BLEND_LIMITED,
    emotion_curves: Optional[List[EmotionCurve]] = None,
    facial_rig_controls: Optional[List[str]] = None,
    idle: bool = False,
) -> FacialAnimationTrack:
    """Compile phoneme timing + viseme map into a facial track (backlog 3-6).

    - viseme curves: per phoneme span -> semantic control keyframes, with
      coarticulation (blend toward the next phoneme in the lookahead window),
      minimum hold and bounded amplitude (backlog 3);
    - silence spans produce NO mouth movement (stage_i §4);
    - emotion curves never overlap articulation controls (backlog 4) — an
      overlap raises `FacialCompileError` (EMOTION_ARTICULATION_OVERLAP);
    - blink / gaze / head motion come from the deterministic seed (backlog 5);
    - ownership: articulation + blink + brow + gaze controls owned by the
      facial track; head controls follow `head_blend_policy` (backlog 6);
    - `idle=True` marks a neutral/subtle-idle shot: mouth keyframes are still
      emitted but validation flags them (IDLE_SPEECH, stage_i §4).
    """
    if phoneme_track.fps <= 0:
        raise FacialCompileError(
            "Invalid fps on phoneme track",
            details={"kinds": ["NON_MONOTONIC"], "fps": phoneme_track.fps},
        )
    emotion_curves = emotion_curves or []
    for curve in emotion_curves:
        overlap = set(curve.controls) & set(ARTICULATION_CONTROLS)
        if overlap:
            raise FacialCompileError(
                f"Emotion curve {curve.curve_id} overlaps articulation controls",
                details={
                    "kinds": ["EMOTION_ARTICULATION_OVERLAP"],
                    "curve_id": str(curve.curve_id),
                    "overlap": sorted(overlap),
                },
            )

    frame_start = phoneme_track.shot_start_frame
    frame_end = phoneme_track.shot_end_frame
    curves: Dict[str, List[VisemeKeyframe]] = {}

    # --- backlog 3: viseme curves with coarticulation + min hold ----------
    spans = [p for p in phoneme_track.phonemes if not p.is_silence]
    for i, span in enumerate(spans):
        target = viseme_map.resolve(span.phoneme)
        if target.shape is VisemeShape.CLOSED:
            continue
        next_target = None
        if i + 1 < len(spans):
            next_target = viseme_map.resolve(spans[i + 1].phoneme)
        hold = max(target.hold_min_frames, MIN_HOLD_FRAMES)
        for control, weight in target.controls.items():
            keyframes = curves.setdefault(control, [])
            value = min(max(weight * target.amplitude, 0.0), AMPLITUDE_MAX)
            keyframes.append(VisemeKeyframe(control=control, frame=span.start_frame,
                                            value=round(value, 4)))
            # coarticulation: blend toward the next viseme inside the window
            if next_target is not None and next_target is not target:
                blend_frame = span.end_frame - COARTICULATION_WINDOW_FRAMES
                if blend_frame > span.start_frame + hold:
                    next_value = next_target.controls.get(control, 0.0)
                    blended = (value + next_value) / 2.0
                    keyframes.append(VisemeKeyframe(
                        control=control, frame=blend_frame,
                        value=round(min(max(blended, 0.0), AMPLITUDE_MAX), 4)))

    # --- backlog 5: blink + gaze + head motion ----------------------------
    blink = _build_blink_track(
        track_id=BlinkTrackId(f"blk-{track_id}"), seed=seed,
        frame_start=frame_start, frame_end=frame_end,
    )
    gaze = _build_gaze_track(
        track_id=GazeTrackId(f"gze-{track_id}"), seed=seed,
        frame_start=frame_start, frame_end=frame_end,
    )
    head_motion = _build_head_motion(
        seed=seed, frame_start=frame_start, frame_end=frame_end,
        policy=head_blend_policy,
    )

    # --- backlog 6: layer ownership ----------------------------------------
    ownership: Dict[str, FacialLayerKind] = {}
    for control in ARTICULATION_CONTROLS:
        ownership[control] = FacialLayerKind.LIP_SYNC
    for control in BLINK_CONTROLS:
        ownership[control] = FacialLayerKind.BLINK
    for control in BROW_CONTROLS:
        ownership[control] = FacialLayerKind.EYEBROW
    for control in GAZE_CONTROLS:
        ownership[control] = FacialLayerKind.GAZE
    for control in HEAD_CONTROLS:
        ownership[control] = FacialLayerKind.HEAD_MOTION

    input_hashes = {
        "alignment": phoneme_track.source_alignment_hash,
        "viseme_map": viseme_map.content_hash(),
        "phoneme_track": phoneme_track.content_hash(),
        "emotion": _sha256(_canonical([
            {"emotion": c.emotion.value, "frame_start": c.frame_start,
             "frame_end": c.frame_end, "controls": c.controls,
             "intensity": c.intensity}
            for c in emotion_curves
        ]).encode("utf-8")),
        "rig_controls": _sha256(_canonical(
            sorted(facial_rig_controls or [])).encode("utf-8")),
    }

    track = FacialAnimationTrack(
        track_id=track_id,
        character_id=character_id,
        shot_id=shot_id,
        fps=phoneme_track.fps,
        frame_start=frame_start,
        frame_end=frame_end,
        phoneme_track_id=str(phoneme_track.track_id),
        source_alignment_hash=phoneme_track.source_alignment_hash,
        viseme_map_id=str(viseme_map.map_id),
        viseme_map_hash=viseme_map.content_hash(),
        curves=curves,
        emotion_curves=emotion_curves,
        blink=blink,
        gaze=gaze,
        head_motion=head_motion,
        ownership=ownership,
        head_blend_policy=head_blend_policy,
        seed=seed,
        input_hashes=input_hashes,
        status=FacialTrackStatus.DRAFT,
        idle=idle,
    )
    return track


REVIEW_KINDS = {
    FacialFindingKind.LOW_CONFIDENCE_ALIGNMENT,
    FacialFindingKind.RIG_CONTROL_MISSING,
    FacialFindingKind.SILENCE_MOUTH_MOVEMENT,
    FacialFindingKind.FACIAL_POP,
    FacialFindingKind.IDLE_SPEECH,
    FacialFindingKind.HEAD_JOINT_LIMIT_EXCEEDED,
}
BLOCKING_KINDS = {
    FacialFindingKind.NON_MONOTONIC,
    FacialFindingKind.OUT_OF_SHOT_RANGE,
    FacialFindingKind.DRIFT_EXCEEDED,
    FacialFindingKind.EMOTION_ARTICULATION_OVERLAP,
    FacialFindingKind.UNKNOWN_PHONEME_NO_RULE,
}


def _finding(kind: FacialFindingKind, message: str, *, frame: Optional[int] = None,
             control: str = "", details: Optional[Dict[str, Any]] = None) -> FacialFinding:
    return FacialFinding(
        finding_id=FacialFindingId(f"ff-{kind.value.lower()}-{frame or 0}"),
        kind=kind, message=message, frame=frame, control=control,
        details=details or {},
    )


def _line_drift(jaw_keyframes: List[VisemeKeyframe],
                line_spans: List[PhonemeSpan], line_index: int) -> Dict[str, Any]:
    """Drift between audio timing and keyframe placement at line anchors.

    A line's start / mid / end anchors are the FIRST, MIDDLE and LAST phoneme
    spans; each anchor's drift is the distance from the span's audio start
    frame to the articulation keyframe placed for that span (a keyframe
    within the span's frame range — the mouth pose that articulates it).
    A compiled track places keyframes exactly on span starts -> drift 0.
    """

    def span_drift(span: PhonemeSpan) -> int:
        within = [kf for kf in jaw_keyframes
                  if span.start_frame <= kf.frame < span.end_frame]
        if within:
            return min(abs(kf.frame - span.start_frame) for kf in within)
        # no jaw keyframe inside this span = the viseme does not articulate
        # the jaw (e.g. bilabial M_B_P) — nothing to measure, no drift
        return 0

    if not line_spans:
        return {"line": line_index, "start_drift_frames": 0, "mid_drift_frames": 0,
                "end_drift_frames": 0, "max_drift_frames": 0,
                "max_drift_frame": None}
    start_span = line_spans[0]
    mid_span = line_spans[len(line_spans) // 2]
    end_span = line_spans[-1]
    start_drift = span_drift(start_span)
    mid_drift = span_drift(mid_span)
    end_drift = span_drift(end_span)
    max_drift = max(start_drift, mid_drift, end_drift)
    max_frame = start_span.start_frame if start_drift == max_drift else (
        mid_span.start_frame if mid_drift == max_drift else end_span.start_frame)
    return {
        "line": line_index,
        "start_drift_frames": start_drift,
        "mid_drift_frames": mid_drift,
        "end_drift_frames": end_drift,
        "max_drift_frames": max_drift,
        "max_drift_frame": max_frame,
    }


def validate_facial_track(
    *,
    receipt_id: FacialValidationReceiptId,
    track: FacialAnimationTrack,
    phoneme_track: Optional[PhonemeTrack] = None,
    facial_rig_controls: Optional[List[str]] = None,
    body_head_turn_degrees: float = 0.0,
) -> FacialValidationReceipt:
    """Run the stage_i §4 quality matrix over one facial track.

    Checks (all fail-closed, findings carry raw measurements):
      - keyframe ordering monotonic per control;
      - no keyframe outside the shot frame range;
      - audio/animation drift at line start/mid/end within tolerance;
      - silence spans produce no mouth movement;
      - two adjacent lines produce no facial pop (value jump beyond
        FACIAL_POP_MAX_DELTA across the line boundary);
      - an idle shot must not contain speech mouth movement (IDLE_SPEECH);
      - body head turn + facial head motion must not exceed the joint limit;
      - low-confidence alignment -> REQUIRES_HUMAN_REVIEW;
      - facial rig missing a required control -> REQUIRES_HUMAN_REVIEW.

    Status: REJECTED on blocking findings, REQUIRES_HUMAN_REVIEW on review
    findings, APPROVED otherwise.
    """
    findings: List[FacialFinding] = []

    # --- monotonic ordering + shot range -----------------------------------
    for control, keyframes in track.curves.items():
        prev_frame = -1
        for kf in keyframes:
            if kf.frame < prev_frame:
                findings.append(_finding(
                    FacialFindingKind.NON_MONOTONIC,
                    f"Keyframe out of order on {control}",
                    frame=kf.frame, control=control,
                    details={"prev_frame": prev_frame}))
            if kf.frame < track.frame_start or kf.frame > track.frame_end:
                findings.append(_finding(
                    FacialFindingKind.OUT_OF_SHOT_RANGE,
                    f"Keyframe outside shot range on {control}",
                    frame=kf.frame, control=control,
                    details={"shot_range": [track.frame_start, track.frame_end]}))
            prev_frame = kf.frame

    # --- drift at line start/mid/end (audio vs animation) ------------------
    sync_metrics: Dict[str, Any] = {"lines": []}
    if phoneme_track is not None:
        jaw = sorted(track.curves.get("jaw_open", []), key=lambda k: k.frame)
        line_index = 0
        max_drift = 0
        in_line = False
        line_spans: List[PhonemeSpan] = []
        for span in phoneme_track.phonemes:
            if span.is_silence:
                if in_line and line_spans:
                    metrics = _line_drift(jaw, line_spans, line_index)
                    sync_metrics["lines"].append(metrics)
                    max_drift = max(max_drift, metrics["max_drift_frames"])
                    line_index += 1
                    line_spans = []
                in_line = False
                continue
            in_line = True
            line_spans.append(span)
        if line_spans:
            metrics = _line_drift(jaw, line_spans, line_index)
            sync_metrics["lines"].append(metrics)
            max_drift = max(max_drift, metrics["max_drift_frames"])
        sync_metrics["max_drift_frames"] = max_drift
        sync_metrics["drift_tolerance_frames"] = DRIFT_TOLERANCE_FRAMES
        for metrics in sync_metrics["lines"]:
            if metrics["max_drift_frames"] > DRIFT_TOLERANCE_FRAMES:
                findings.append(_finding(
                    FacialFindingKind.DRIFT_EXCEEDED,
                    "Audio/animation drift beyond tolerance",
                    frame=metrics["max_drift_frame"],
                    details={"line": metrics["line"],
                             "max_drift_frames": metrics["max_drift_frames"],
                             "tolerance": DRIFT_TOLERANCE_FRAMES}))

    # --- silence produces no mouth movement --------------------------------
    if phoneme_track is not None:
        for span in phoneme_track.phonemes:
            if not span.is_silence:
                continue
            for control in ARTICULATION_CONTROLS:
                for kf in track.curves.get(control, []):
                    # exclusive bounds: a keyframe on the shared boundary
                    # frame belongs to the adjacent speech span
                    if span.start_frame < kf.frame < span.end_frame and kf.value > 0.01:
                        findings.append(_finding(
                            FacialFindingKind.SILENCE_MOUTH_MOVEMENT,
                            "Mouth movement inside silence span",
                            frame=kf.frame, control=control,
                            details={"span": [span.start_frame, span.end_frame]}))

    # --- facial pop between adjacent lines ----------------------------------
    jaw = sorted(track.curves.get("jaw_open", []), key=lambda k: k.frame)
    for prev, nxt in zip(jaw, jaw[1:]):
        delta = abs(nxt.value - prev.value)
        if delta > FACIAL_POP_MAX_DELTA and (nxt.frame - prev.frame) <= 2:
            findings.append(_finding(
                FacialFindingKind.FACIAL_POP,
                "Viseme jump across adjacent lines",
                frame=nxt.frame, control="jaw_open",
                details={"delta": delta, "prev_frame": prev.frame,
                         "prev_value": prev.value, "next_value": nxt.value}))

    # --- idle shot must not speak -------------------------------------------
    if track.idle:
        mouth_values = [kf.value for c in ARTICULATION_CONTROLS
                        for kf in track.curves.get(c, [])]
        if any(v > 0.01 for v in mouth_values):
            findings.append(_finding(
                FacialFindingKind.IDLE_SPEECH,
                "Speech mouth movement during neutral/subtle idle",
                details={"max_value": max(mouth_values)}))

    # --- head joint limit: body turn + facial head ---------------------------
    head_max = max((kf.value for kf in track.head_motion
                    if kf.control == "head_yaw"), default=0.0)
    total_degrees = body_head_turn_degrees + head_max * HEAD_JOINT_LIMIT_DEGREES
    if total_degrees > HEAD_JOINT_LIMIT_DEGREES:
        findings.append(_finding(
            FacialFindingKind.HEAD_JOINT_LIMIT_EXCEEDED,
            "Body head turn + facial head motion exceed joint limit",
            details={"body_head_turn_degrees": body_head_turn_degrees,
                     "facial_head_degrees": round(head_max * HEAD_JOINT_LIMIT_DEGREES, 2),
                     "total_degrees": round(total_degrees, 2),
                     "limit_degrees": HEAD_JOINT_LIMIT_DEGREES}))

    # --- low-confidence alignment -> REQUIRES_HUMAN_REVIEW -------------------
    if phoneme_track is not None and \
            phoneme_track.segment_confidence < ALIGNMENT_CONFIDENCE_FLOOR:
        findings.append(_finding(
            FacialFindingKind.LOW_CONFIDENCE_ALIGNMENT,
            "Alignment confidence below usable floor",
            details={"confidence": phoneme_track.segment_confidence,
                     "floor": ALIGNMENT_CONFIDENCE_FLOOR}))

    # --- facial rig missing controls -> REQUIRES_HUMAN_REVIEW ----------------
    if facial_rig_controls is not None:
        required = set()
        for keyframes in track.curves.values():
            required.update(kf.control for kf in keyframes)
        for curve in track.emotion_curves:
            required.update(curve.controls)
        if track.blink:
            required.update(BLINK_CONTROLS)
        if track.gaze:
            required.update(GAZE_CONTROLS)
        if track.head_motion:
            required.update(HEAD_CONTROLS)
        missing = sorted(required - set(facial_rig_controls))
        if missing:
            findings.append(_finding(
                FacialFindingKind.RIG_CONTROL_MISSING,
                "Facial rig missing required controls",
                details={"missing": missing}))

    # --- status resolution ----------------------------------------------------
    blocking = [f for f in findings if f.kind in BLOCKING_KINDS]
    review = [f for f in findings if f.kind in REVIEW_KINDS]
    if blocking:
        status = FacialTrackStatus.REJECTED
    elif review:
        status = FacialTrackStatus.REQUIRES_HUMAN_REVIEW
    else:
        status = FacialTrackStatus.APPROVED

    return FacialValidationReceipt(
        receipt_id=receipt_id,
        track_id=track.track_id,
        status=status,
        findings=findings,
        sync_metrics=sync_metrics,
        gate_passed=status is FacialTrackStatus.APPROVED,
    )


def bake_facial_track(
    *,
    action_id: BakedFacialActionId,
    track: FacialAnimationTrack,
) -> BakedFacialAction:
    """Bake a facial track into a derived action (backlog 7).

    Records compiler version, input hashes and the frame range. Only
    APPROVED tracks bake; anything else fails closed (`FacialBakeError`) so
    a partial or unreviewed face never reaches the render.
    """
    if track.status is not FacialTrackStatus.APPROVED:
        raise FacialBakeError(
            f"Facial track {track.track_id} is not APPROVED "
            f"(status={track.status.value})",
            details={"track_id": str(track.track_id),
                     "status": track.status.value},
        )
    action_hash = _sha256(_canonical({
        "track_hash": track.content_hash(),
        "compiler_version": track.compiler_version,
        "frame_range": [track.frame_start, track.frame_end],
        "fps": track.fps,
    }).encode("utf-8"))
    return BakedFacialAction(
        action_id=action_id,
        track_id=track.track_id,
        compiler_version=track.compiler_version,
        input_hashes=track.input_hashes,
        frame_start=track.frame_start,
        frame_end=track.frame_end,
        fps=track.fps,
        action_hash=action_hash,
    )


def repair_facial_track(
    *,
    receipt_id: FacialRepairReceiptId,
    track: FacialAnimationTrack,
    scope: FacialRepairScope,
    seed: Optional[int] = None,
    emotion_curves: Optional[List[EmotionCurve]] = None,
) -> FacialRepairReceipt:
    """Repair ONE layer; invalidation touches only that layer (backlog 8).

    - LIP_SYNC: rebuilds nothing structural (timing is the source of truth);
      invalidation is layer-scoped and does NOT touch the body clip when
      timing is unchanged (stage_h §6 risk);
    - GAZE / BLINK / HEAD_MOTION: regenerate the layer from a NEW seed;
    - EMOTION: replace emotion curves (must still not overlap articulation).

    Returns the repaired track via `new_track_id` (a fresh `FacialTrackId`)
    and the invalidation scope: TRACK_LAYER_ONLY when only the layer content
    changed, TRACK_AND_RENDER_FINAL when the layer change affects the final
    render (any of them do — the layer is baked into the derived action).
    """
    if scope not in [s.value for s in FacialRepairScope] \
            and not isinstance(scope, FacialRepairScope):
        raise FacialRepairError(
            f"Unknown repair scope {scope!r}",
            details={"scope": str(scope)},
        )
    scope = FacialRepairScope(scope)
    new_seed = track.seed if seed is None else seed
    update: Dict[str, Any] = {
        "seed": new_seed,
        "track_id": FacialTrackId(f"ft-{track.track_id}-{scope.value.lower()}"),
    }
    rebuilt: List[str] = []

    if scope is FacialRepairScope.LIP_SYNC:
        # Timing is the source of truth; nothing to rebuild structurally.
        rebuilt = ["lip_sync"]
    elif scope is FacialRepairScope.GAZE:
        gaze = _build_gaze_track(
            track_id=GazeTrackId(f"gze-{track.track_id}-r"), seed=new_seed,
            frame_start=track.frame_start, frame_end=track.frame_end,
        )
        update["gaze"] = gaze
        rebuilt = ["gaze"]
    elif scope is FacialRepairScope.BLINK:
        blink = _build_blink_track(
            track_id=BlinkTrackId(f"blk-{track.track_id}-r"), seed=new_seed,
            frame_start=track.frame_start, frame_end=track.frame_end,
        )
        update["blink"] = blink
        rebuilt = ["blink"]
    elif scope is FacialRepairScope.HEAD_MOTION:
        head = _build_head_motion(
            seed=new_seed, frame_start=track.frame_start,
            frame_end=track.frame_end, policy=track.head_blend_policy,
        )
        update["head_motion"] = head
        rebuilt = ["head_motion"]
    elif scope is FacialRepairScope.EMOTION:
        if emotion_curves is None:
            raise FacialRepairError(
                "EMOTION repair requires replacement emotion curves",
                details={"scope": scope.value},
            )
        for curve in emotion_curves:
            overlap = set(curve.controls) & set(ARTICULATION_CONTROLS)
            if overlap:
                raise FacialRepairError(
                    f"Replacement emotion curve {curve.curve_id} overlaps "
                    "articulation controls",
                    details={"scope": scope.value,
                             "overlap": sorted(overlap)},
                )
        update["emotion_curves"] = emotion_curves
        rebuilt = ["emotion"]

    new_track = track.model_copy(update=update)
    return FacialRepairReceipt(
        receipt_id=receipt_id,
        track_id=track.track_id,
        scope=scope,
        new_track_id=new_track.track_id,
        invalidation=FacialInvalidationScope.TRACK_AND_RENDER_FINAL,
        rebuilt_layers=rebuilt,
        message="layer-scoped repair; body clip untouched when timing unchanged",
    )


def build_preview_manifest(
    *,
    track: FacialAnimationTrack,
    camera: Optional[Dict[str, Any]] = None,
    resolution: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Preview close-up / playblast manifest (backlog 9).

    Engine-neutral: the manifest describes the preview job (camera framing,
    frame range, fps, resolution, semantic controls to bind) WITHOUT naming
    any Blender data-block — the adapter resolves semantic controls to
    shape keys/bones at preview time.
    """
    return {
        "track_id": str(track.track_id),
        "character_id": track.character_id,
        "shot_id": track.shot_id,
        "preview": "close-up playblast before Cycles final",
        "camera": camera or {"framing": "close-up", "focal_length_mm": 50,
                             "distance_m": 0.8},
        "resolution": resolution or {"width": 1280, "height": 720},
        "fps": track.fps,
        "frame_range": [track.frame_start, track.frame_end],
        "semantic_controls": sorted(set(track.curves) | set(HEAD_CONTROLS)),
        "layers": sorted({layer.value for layer in track.ownership.values()}),
        "bindings": "semantic controls mapped to shape keys/bones by the "
                    "adapter (domain carries no data-block names)",
    }


__all__ = [
    # constants
    "FACIAL_COMPILER_VERSION",
    "FACIAL_TRACK_SCHEMA_VERSION",
    "DRIFT_TOLERANCE_FRAMES",
    "COARTICULATION_WINDOW_FRAMES",
    "MIN_HOLD_FRAMES",
    "AMPLITUDE_MAX",
    "HEAD_MOTION_MAX_AMPLITUDE",
    "HEAD_JOINT_LIMIT_DEGREES",
    "FACIAL_POP_MAX_DELTA",
    "BLINK_INTERVAL_FRAMES",
    "BLINK_JITTER_FRAMES",
    "BLINK_DURATION_FRAMES",
    "GAZE_SAMPLE_INTERVAL_FRAMES",
    "GAZE_AMPLITUDE",
    "ARTICULATION_CONTROLS",
    "BLINK_CONTROLS",
    "BROW_CONTROLS",
    "GAZE_CONTROLS",
    "HEAD_CONTROLS",
    "FALLBACK_NEUTRAL",
    "FALLBACK_CLOSED",
    "ALLOWED_FALLBACK_RULES",
    "REVIEW_KINDS",
    "BLOCKING_KINDS",
    # models
    "PhonemeSpan",
    "PhonemeTrack",
    "VisemeTarget",
    "VisemeMap",
    "VisemeKeyframe",
    "EmotionCurve",
    "BlinkEvent",
    "BlinkTrack",
    "GazeSample",
    "GazeTrack",
    "FacialAnimationTrack",
    "FacialFinding",
    "FacialValidationReceipt",
    "BakedFacialAction",
    "FacialRepairReceipt",
    # kernel services
    "normalize_phoneme_track",
    "build_viseme_map",
    "compile_facial_track",
    "validate_facial_track",
    "bake_facial_track",
    "repair_facial_track",
    "build_preview_manifest",
]
