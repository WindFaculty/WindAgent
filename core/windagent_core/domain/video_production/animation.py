"""
Stage H Animation Layer V1 domain (VP3D Phase 15 — Animation Layer V1:
Library + Mocap).

Frozen, engine-neutral DTOs for animation intent, the versioned clip library,
retarget receipts, bounded time-warp, blend transitions and episode pins.
No ``bpy``, no provider SDK, no transport object ever appears here: the
compiler layer (`intelligence/windagent_intelligence/video/animation/`)
resolves the Director's `AnimationIntent` against the library, retargets
through a Stage D profile, and emits an immutable `AnimationTrack` the Scene
Compiler can consume. Intent stays neutral so Stage Q can map the same intent
to Unreal (stage_h §1/§7).

Semantics (stage_h §3):
- `AnimationIntent(actor, action, emotion, destination, duration, fps,
  skeleton_profile_id)` is what the Director means (backlog 1/3). Resolution
  is by actor/action/emotion/destination/duration + compatible skeleton —
  NEVER by display name.
- The minimal library (idle, walk, run, jump, sit, stand, talk, laugh, cry,
  point, wave, pick-up, put-down) is versioned; every clip carries typed
  provenance and a deterministic content hash (backlog 1/2).
- Retarget (backlog 4) normalizes fps, root motion and units through a Stage D
  retarget profile; non-resamplable clips and missing semantic bones fail
  closed with `ClipRetargetError`.
- Time-warp (backlog 5) is bounded [MIN_WARP_RATIO, MAX_WARP_RATIO];
  out-of-range requests fail closed — pick another clip or request a plan
  revision.
- Blend transitions (backlog 6) keep stable frame boundaries; overlap beyond
  the blend window fails closed (OVERLAP_CONFLICT).
- Episode pins (backlog 7) lock a clip revision so library updates never
  change locked production.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    AnimationAction,
    AnimationEmotion,
    ClipSource,
    CompatibilityVerdict,
    LicenseState,
    SemanticBone,
)
from windagent_core.domain.video_production.ids import (
    AnimationClipId,
    AnimationFindingId,
    AnimationIntentId,
    AnimationTrackId,
    BlendTransitionId,
    EpisodePinId,
    RetargetReceiptId,
    RetargetProfileId,
    SkeletonProfileId,
)

ANIMATION_COMPILER_VERSION = "1.0.0"
ANIMATION_LIBRARY_SCHEMA_VERSION = "1.0.0"
ANIMATION_TRACK_SCHEMA_VERSION = "1.0.0"

# Time-warp bounds (backlog 5): a clip may play from half speed to double
# speed. Outside that band the compiler must pick another clip or request a
# plan revision — never silently stretch.
MIN_WARP_RATIO = 0.5
MAX_WARP_RATIO = 2.0
# Root drift tolerance: time-warp preserves root displacement, so a track
# whose displacement deviates more than 10% from the clip is broken.
ROOT_DRIFT_TOLERANCE = 0.10
# Duration match tolerance in frames at the track fps (backlog 5 / §6).
DURATION_TOLERANCE_FRAMES = 1


def _stable_hash(*parts: str) -> str:
    canonical = json.dumps(list(parts), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Intent / library / provenance
# ---------------------------------------------------------------------------
class AnimationIntent(BaseModel):
    """What the Director means for one actor's body animation (stage_h §3).

    `skeleton_profile_id` is the Stage D target skeleton; `episode_id` locks
    the production so library updates cannot drift a locked episode
    (backlog 7). Resolution keys on action/emotion/skeleton, never on names.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    intent_id: AnimationIntentId
    actor_id: str = Field(min_length=1)
    action: AnimationAction
    emotion: AnimationEmotion = AnimationEmotion.NEUTRAL
    destination: Optional[str] = None
    duration_seconds: Optional[float] = Field(default=None, gt=0)
    fps: int = Field(default=24, ge=1)
    skeleton_profile_id: SkeletonProfileId
    episode_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ClipProvenance(BaseModel):
    """Where a clip came from + its license (stage_h §3 backlog 1, §7 risk).

    `imported_at` is recording provenance and is excluded from the content
    hash so the same imported motion always yields the same hash.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    source: ClipSource = ClipSource.LIBRARY
    provider: str = ""
    recording_session: str = ""
    license: LicenseState = LicenseState.UNKNOWN
    imported_at: str = ""


class AnimationClip(BaseModel):
    """One versioned clip in the animation library (backlog 1/2).

    `name` is a display label and is NEVER a resolution key (backlog 3).
    `required_bones` are the semantic bone roles (Stage D) the target
    skeleton must provide; `compatible_skeleton_ids` names skeletons the clip
    was retargeted/validated against. `resamplable=False` marks clips whose
    contact timing (footsteps, pick-ups) forbids fps resampling.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    clip_id: AnimationClipId
    name: str = ""
    action: AnimationAction
    emotion: AnimationEmotion = AnimationEmotion.NEUTRAL
    skeleton_profile_id: SkeletonProfileId
    compatible_skeleton_ids: List[SkeletonProfileId] = Field(default_factory=list)
    required_bones: List[SemanticBone] = Field(default_factory=list)
    duration_seconds: float = Field(gt=0)
    fps: int = Field(ge=1)
    root_motion_meters: float = Field(ge=0)
    resamplable: bool = True
    requires_destination: bool = False
    version: str = "1.0.0"
    provenance: ClipProvenance = Field(default_factory=ClipProvenance)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        """Deterministic content hash (same clip -> same hash, §5)."""
        payload = json.loads(
            self.model_dump_json(
                exclude={"metadata": True,
                         "provenance": {"imported_at": True}}))
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ClipCompatibility(BaseModel):
    """Verdict of one clip against a target skeleton (backlog 3, §6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: CompatibilityVerdict = CompatibilityVerdict.NOT_TESTED
    reason: str = ""
    missing_bones: List[SemanticBone] = Field(default_factory=list)
    fps_delta: float = 0.0


# ---------------------------------------------------------------------------
# Retarget / warp / blend / pin
# ---------------------------------------------------------------------------
class RetargetReceipt(BaseModel):
    """Evidence that a clip was retargeted through a Stage D profile (backlog 4).

    Records the fps resample, normalized root motion and unit normalization.
    Root displacement is invariant under retarget and time-warp; the
    validator's ROOT_DRIFT check compares against `root_motion_meters`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    receipt_id: RetargetReceiptId
    clip_id: AnimationClipId
    source_fps: int = Field(ge=1)
    target_fps: int = Field(ge=1)
    resample_ratio: float = Field(gt=0)
    root_motion_meters: float = Field(ge=0)
    root_motion_mps: float = Field(ge=0)
    units_normalized: bool = True
    semantic_bones_mapped: List[SemanticBone] = Field(default_factory=list)
    retarget_profile_id: Optional[RetargetProfileId] = None
    retarget_profile_hash: str = ""


class TimeWarp(BaseModel):
    """A bounded time-warp applied to a clip (backlog 5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ratio: float = Field(ge=MIN_WARP_RATIO, le=MAX_WARP_RATIO)
    duration_seconds: float = Field(gt=0)
    applied_frames: int = Field(ge=0)


class BlendTransition(BaseModel):
    """A planned blend between two tracks of the same actor (backlog 6).

    `boundary_frame` is the stable frame boundary (the first track's end
    frame); the blend window straddles it. Overlap beyond the window fails
    closed instead of producing a partial/conflicting transition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    transition_id: BlendTransitionId
    actor_id: str = Field(min_length=1)
    from_track_id: AnimationTrackId
    to_track_id: AnimationTrackId
    boundary_frame: int = Field(ge=0)
    blend_window_frames: int = Field(ge=0)


class EpisodePin(BaseModel):
    """Locks one clip revision for an episode+actor (backlog 7).

    A pinned episode keeps compiling against the pinned revision even after
    the library updates; a mismatched clip fails closed with
    `AnimationPinMismatchError`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    pin_id: EpisodePinId
    episode_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    clip_id: AnimationClipId
    clip_version: str = Field(min_length=1)
    pinned_at: str = ""


# ---------------------------------------------------------------------------
# Track (the compiled, immutable output)
# ---------------------------------------------------------------------------
class AnimationTrack(BaseModel):
    """An immutable, versioned animation track for one actor (stage_h §1).

    `companion_refs` names the facial/audio tracks riding along; it is
    EXCLUDED from the content hash so changing a companion with unchanged
    timing never invalidates the body clip (§6). Publishing is all-or-nothing:
    the compiler raises before any track object exists.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    track_id: AnimationTrackId
    episode_id: str = ""
    actor_id: str = Field(min_length=1)
    intent_id: AnimationIntentId
    clip_id: AnimationClipId
    clip_version: str = Field(min_length=1)
    clip_hash: str = Field(min_length=1)
    retarget: RetargetReceipt
    warp_ratio: float = Field(ge=MIN_WARP_RATIO, le=MAX_WARP_RATIO)
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    fps: int = Field(ge=1)
    root_motion_meters: float = Field(ge=0)
    blend_in_frames: int = Field(default=0, ge=0)
    blend_out_frames: int = Field(default=0, ge=0)
    companion_refs: Dict[str, str] = Field(default_factory=dict)
    pin_id: str = ""
    compiler_version: str = ANIMATION_COMPILER_VERSION
    schema_version: str = ANIMATION_TRACK_SCHEMA_VERSION
    content_hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_stable_hash(self) -> str:
        """Deterministic content hash over everything except provenance.

        `companion_refs`/`metadata`/`pin_id`/`content_hash` are excluded: a
        facial or audio companion change with unchanged timing must NOT
        invalidate the body clip (stage_h §6), and the pin is locking
        provenance, not motion content — a pinned episode recompiled against
        its locked revision yields the identical track hash (§5 determinism);
        the same intent + clip + retarget + warp always produce the same
        track hash.
        """
        payload = json.loads(
            self.model_dump_json(exclude={"content_hash", "companion_refs",
                                          "metadata", "pin_id"}))
        canonical = json.dumps(
            {"schema_version": self.schema_version,
             "compiler_version": self.compiler_version,
             "track": json.loads(json.dumps(payload, sort_keys=True,
                                            default=str))},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def frame_count(self) -> int:
        return max(0, self.end_frame - self.start_frame)


# ---------------------------------------------------------------------------
# Findings + validation (fail-closed)
# ---------------------------------------------------------------------------
class AnimationFindingKind:
    """Typed animation finding kinds (stage_h §3 backlog 3-6 / §6 matrix)."""

    MISSING_ACTION = "MISSING_ACTION"
    INCOMPATIBLE_SKELETON = "INCOMPATIBLE_SKELETON"
    MISSING_DESTINATION = "MISSING_DESTINATION"
    FPS_MISMATCH = "FPS_MISMATCH"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    ROOT_DRIFT = "ROOT_DRIFT"
    WARP_OUT_OF_BOUNDS = "WARP_OUT_OF_BOUNDS"
    OVERLAP_CONFLICT = "OVERLAP_CONFLICT"
    PIN_MISMATCH = "PIN_MISMATCH"


class AnimationFinding(BaseModel):
    """One typed animation finding (blocking or advisory)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    finding_id: AnimationFindingId
    kind: str
    actor_id: str = ""
    detail: str = ""
    blocking: bool = False
    measured: Dict[str, Any] = Field(default_factory=dict)


class AnimationValidationReport(BaseModel):
    """Aggregate result of animation validation over one track."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool = False
    findings: List[AnimationFinding] = Field(default_factory=list)
    checked_entity_count: int = Field(default=0, ge=0)

    @property
    def blocking_findings(self) -> List[AnimationFinding]:
        return [f for f in self.findings if f.blocking]

    @property
    def blocking_kinds(self) -> List[str]:
        return sorted({f.kind for f in self.blocking_findings})


class AnimationValidator:
    """Fail-closed animation validation (stage_h §3/§6).

    Pure math on clips/tracks; never touches bpy or any engine. The compiler
    always produces valid tracks; this validator catches hand-built/edited
    tracks (defense in depth).
    """

    def validate_track(
        self,
        *,
        intent: AnimationIntent,
        clip: AnimationClip,
        track: AnimationTrack,
        previous_track: Optional[AnimationTrack] = None,
        finding_prefix: str = "an",
    ) -> AnimationValidationReport:
        findings: List[AnimationFinding] = []

        # fps: retarget must have normalized the clip to the intent's fps
        if track.fps != intent.fps:
            findings.append(self._finding(
                finding_prefix, AnimationFindingKind.FPS_MISMATCH, track,
                f"track fps {track.fps} != intent fps {intent.fps}",
                blocking=True,
                measured={"track_fps": track.fps, "intent_fps": intent.fps}))

        # duration: when the intent pins a duration, the track must match it
        if intent.duration_seconds is not None:
            target_frames = round(intent.duration_seconds * intent.fps)
            actual_frames = track.frame_count
            if abs(actual_frames - target_frames) > DURATION_TOLERANCE_FRAMES:
                findings.append(self._finding(
                    finding_prefix, AnimationFindingKind.DURATION_MISMATCH,
                    track,
                    f"track {actual_frames} frames != intent "
                    f"{intent.duration_seconds}s -> {target_frames} frames",
                    blocking=True,
                    measured={"actual_frames": actual_frames,
                              "target_frames": target_frames}))

        # root drift: time-warp preserves root displacement
        expected = clip.root_motion_meters
        if expected > 0:
            drift = (abs(track.root_motion_meters - expected) / expected)
            if drift > ROOT_DRIFT_TOLERANCE:
                findings.append(self._finding(
                    finding_prefix, AnimationFindingKind.ROOT_DRIFT, track,
                    f"root motion {track.root_motion_meters:.3f}m vs clip "
                    f"{expected:.3f}m (drift {drift:.1%} > "
                    f"{ROOT_DRIFT_TOLERANCE:.0%})",
                    blocking=True,
                    measured={"track_root_m": track.root_motion_meters,
                              "clip_root_m": expected,
                              "drift": drift}))

        # warp bounds: a hand-built track outside the band is rejected
        if not (MIN_WARP_RATIO <= track.warp_ratio <= MAX_WARP_RATIO):
            findings.append(self._finding(
                finding_prefix, AnimationFindingKind.WARP_OUT_OF_BOUNDS,
                track,
                f"warp ratio {track.warp_ratio} outside "
                f"[{MIN_WARP_RATIO}, {MAX_WARP_RATIO}]",
                blocking=True,
                measured={"warp_ratio": track.warp_ratio}))

        # overlap: same actor, previous track — overlap beyond the blend
        # window is a conflict; adjacency or in-window overlap is fine
        if (previous_track is not None
                and previous_track.actor_id == track.actor_id):
            overlap = previous_track.end_frame - track.start_frame
            allowed = max(previous_track.blend_out_frames,
                          track.blend_in_frames)
            if overlap > allowed:
                findings.append(self._finding(
                    finding_prefix, AnimationFindingKind.OVERLAP_CONFLICT,
                    track,
                    f"overlap {overlap} frames > blend window {allowed} vs "
                    f"previous track {previous_track.track_id}",
                    blocking=True,
                    measured={"overlap_frames": overlap,
                              "allowed_frames": allowed}))

        return AnimationValidationReport(
            ok=not findings, findings=findings,
            checked_entity_count=track.frame_count)

    @staticmethod
    def _finding(prefix: str, kind: str, track: AnimationTrack,
                 detail: str, *, blocking: bool,
                 measured: Dict[str, Any]) -> AnimationFinding:
        return AnimationFinding(
            finding_id=AnimationFindingId(f"{prefix}:{kind}"),
            kind=kind, actor_id=track.actor_id, detail=detail,
            blocking=blocking, measured=measured)


__all__ = [
    "ANIMATION_COMPILER_VERSION",
    "ANIMATION_LIBRARY_SCHEMA_VERSION",
    "ANIMATION_TRACK_SCHEMA_VERSION",
    "MIN_WARP_RATIO",
    "MAX_WARP_RATIO",
    "ROOT_DRIFT_TOLERANCE",
    "DURATION_TOLERANCE_FRAMES",
    "AnimationIntent",
    "ClipProvenance",
    "AnimationClip",
    "ClipCompatibility",
    "RetargetReceipt",
    "TimeWarp",
    "BlendTransition",
    "EpisodePin",
    "AnimationTrack",
    "AnimationFindingKind",
    "AnimationFinding",
    "AnimationValidationReport",
    "AnimationValidator",
]
