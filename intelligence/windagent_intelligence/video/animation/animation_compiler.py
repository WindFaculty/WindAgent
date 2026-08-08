"""
Animation compiler (VP3D Phase 15, stage_h §3) — orchestrator.

Maps the Director's `AnimationIntent` onto an immutable `AnimationTrack`:

- resolution (backlog 1/3): library lookup by action/emotion/skeleton
  compatibility — NEVER display name; pinned episodes (backlog 7) resolve
  only against the pinned clip revision and fail closed with
  `AnimationPinMismatchError` on any other revision;
- retarget (backlog 4): `RetargetService` normalizes fps, root motion and
  units through a Stage D profile; non-resamplable clips and missing
  semantic bones fail closed with `ClipRetargetError`;
- time-warp (backlog 5): bounded [0.5, 2.0]; outside the band the compile
  fails closed (WARP_OUT_OF_BOUNDS) — pick another clip or request a plan
  revision;
- blend (backlog 6): `BlendPlanner` plans transitions with stable frame
  boundaries; overlap beyond the window fails closed (OVERLAP_CONFLICT);
- validation (stage_h §6): fps/duration mismatch, root drift, warp bounds
  and overlap conflicts are blocking; a track with any blocking finding is
  never published (all-or-nothing);
- invalidation (§6): a changed body track invalidates ONLY its dependent
  animation preview — never assets, rigs or audio; a facial/audio companion
  change with unchanged timing leaves the body track hash untouched.

The intent/track stay engine-neutral (stage_h §1) so Stage Q can map the
same intent to Unreal.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from windagent_core.domain.video_production.animation import (
    AnimationTrack,
    AnimationValidationReport,
    AnimationValidator,
    ClipCompatibility,
    EpisodePin,
    TimeWarp,
)
from windagent_core.domain.video_production.enums import (
    AnimationAction,
    AnimationEmotion,
    CompatibilityVerdict,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import (
    AnimationCompileError,
    AnimationPinMismatchError,
)
from windagent_core.domain.video_production.ids import (
    AnimationTrackId,
    EpisodePinId,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.animation.blend import (
    BLEND_DEFAULT_WINDOW_FRAMES,
    BlendPlanner,
    BlendTransition,
)
from windagent_intelligence.video.animation.library import (
    ANIMATION_LIBRARY_VERSION,
    AnimationLibrary,
)
from windagent_intelligence.video.animation.retarget import RetargetService
from windagent_intelligence.video.animation.warp import WarpService

ANIMATION_COMPILER_LAYER_VERSION = "1.0.0"


class AnimationCompileReceipt:
    """Result of one animation compile: track + provenance + invalidation."""

    def __init__(
        self,
        *,
        track: AnimationTrack,
        validation: AnimationValidationReport,
        clip,
        compatibility: ClipCompatibility,
        retarget,
        warp: TimeWarp,
        invalidated_artifacts: Optional[List[str]] = None,
        cleaned_ok: bool = True,
    ) -> None:
        self.track = track
        self.validation = validation
        self.clip = clip
        self.compatibility = compatibility
        self.retarget = retarget
        self.warp = warp
        self.invalidated_artifacts = invalidated_artifacts or []
        self.cleaned_ok = cleaned_ok

    @property
    def track_hash(self) -> str:
        return self.track.content_hash

    @property
    def blocking_kinds(self) -> List[str]:
        return self.validation.blocking_kinds


class AnimationCompiler:
    """Deterministic animation-intent -> animation-track compiler (stage_h §3)."""

    compiler_version = ANIMATION_COMPILER_LAYER_VERSION
    library_version = ANIMATION_LIBRARY_VERSION

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        library: Optional[AnimationLibrary] = None,
        validator: Optional[AnimationValidator] = None,
        retarget_service: Optional[RetargetService] = None,
        warp_service: Optional[WarpService] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.library = library or AnimationLibrary()
        self.validator = validator or AnimationValidator()
        self.retarget_service = retarget_service or RetargetService(
            id_factory=self.id_factory)
        self.warp_service = warp_service or WarpService()
        self.blend_planner = BlendPlanner(id_factory=self.id_factory)

    # ------------------------------------------------------------------
    def resolve_clip(
        self,
        *,
        intent,
        target_bones: List[SemanticBone],
    ):
        """Backlog 3: resolve by action/emotion/skeleton — never by name."""
        clip = self.library.resolve(
            action=intent.action,
            emotion=intent.emotion,
            target_bones=target_bones,
            destination=intent.destination)
        missing = [b for b in clip.required_bones if b not in target_bones]
        compatibility = ClipCompatibility(
            verdict=(CompatibilityVerdict.APPROVED if not missing
                     else CompatibilityVerdict.FAILED),
            reason=("all required semantic bones present"
                    if not missing else "missing semantic bones"),
            missing_bones=missing,
            fps_delta=abs(clip.fps - intent.fps))
        return clip, compatibility

    # ------------------------------------------------------------------
    def compile(
        self,
        *,
        intent,
        target_bones: List[SemanticBone],
        start_frame: int = 0,
        previous_track: Optional[AnimationTrack] = None,
        pin: Optional[EpisodePin] = None,
        pinned_clip=None,
        blend_in_frames: int = 0,
        blend_out_frames: int = 0,
        prior_track_hash: Optional[str] = None,
        require_clean: bool = True,
    ) -> AnimationCompileReceipt:
        """Compile one animation intent into an immutable track.

        ``pin`` + ``pinned_clip`` enforce backlog 7: a pinned episode may
        only consume the pinned clip revision. ``prior_track_hash`` enables
        invalidation scoping (§6).
        """
        clip = self._resolve_with_pin(intent, pin, pinned_clip, target_bones)

        retarget = self.retarget_service.build_receipt(
            clip=clip, target_fps=intent.fps, target_bones=target_bones)

        natural_duration = clip.duration_seconds
        target_duration = (
            intent.duration_seconds
            if intent.duration_seconds is not None else natural_duration)
        warp = self.warp_service.apply(
            clip_duration_seconds=natural_duration,
            target_duration_seconds=target_duration,
            fps=intent.fps)
        end_frame = start_frame + warp.applied_frames

        companion_refs = intent.metadata.get("companion_refs", {})
        if not isinstance(companion_refs, dict):
            companion_refs = {}

        track = AnimationTrack(
            track_id=AnimationTrackId(
                self.id_factory.animation_track_id(
                    intent.actor_id, start_frame)),
            episode_id=intent.episode_id,
            actor_id=intent.actor_id,
            intent_id=intent.intent_id,
            clip_id=clip.clip_id,
            clip_version=clip.version,
            clip_hash=clip.content_hash(),
            retarget=retarget,
            warp_ratio=warp.ratio,
            start_frame=start_frame,
            end_frame=end_frame,
            duration_seconds=target_duration,
            fps=intent.fps,
            root_motion_meters=clip.root_motion_meters,
            blend_in_frames=blend_in_frames,
            blend_out_frames=blend_out_frames,
            companion_refs=dict(companion_refs),
            pin_id=str(pin.pin_id) if pin else "",
            compiler_version=self.compiler_version,
        )
        track = track.model_copy(update={
            "content_hash": track.compute_stable_hash()})

        report = self.validator.validate_track(
            intent=intent, clip=clip, track=track,
            previous_track=previous_track,
            finding_prefix=self.id_factory.animation_finding_id(
                intent.actor_id))

        if require_clean and report.blocking_findings:
            raise ValidationFailureError(
                "Animation track failed validation; no track is published.",
                details={
                    "actor_id": intent.actor_id,
                    "action": intent.action.value,
                    "blocking_count": len(report.blocking_findings),
                    "kinds": report.blocking_kinds,
                })

        _, compatibility = self.resolve_clip(
            intent=intent, target_bones=target_bones)
        return AnimationCompileReceipt(
            track=track,
            validation=report,
            clip=clip,
            compatibility=compatibility,
            retarget=retarget,
            warp=warp,
            invalidated_artifacts=self._invalidation_scope(
                prior_track_hash, track.content_hash, track.track_id),
            cleaned_ok=not report.blocking_findings,
        )

    # ------------------------------------------------------------------
    def pin(self, *, episode_id: str, actor_id: str, clip) -> EpisodePin:
        """Backlog 7: lock one clip revision for an episode+actor."""
        return EpisodePin(
            pin_id=EpisodePinId(self.id_factory.episode_pin_id(
                episode_id, actor_id)),
            episode_id=episode_id,
            actor_id=actor_id,
            clip_id=clip.clip_id,
            clip_version=clip.version,
        )

    def plan_blend(
        self,
        *,
        track_a: AnimationTrack,
        track_b: AnimationTrack,
        blend_window_frames: int = BLEND_DEFAULT_WINDOW_FRAMES,
    ) -> BlendTransition:
        """Backlog 6: plan a blend with a stable frame boundary."""
        return self.blend_planner.plan(
            track_a=track_a, track_b=track_b,
            blend_window_frames=blend_window_frames)

    # ------------------------------------------------------------------
    def _resolve_with_pin(self, intent, pin, pinned_clip, target_bones):
        """Backlog 7: pinned episodes resolve ONLY against the pinned revision."""
        if pin is not None:
            if pinned_clip is None:
                raise AnimationPinMismatchError(
                    "pinned episode requires the pinned clip revision",
                    details={"episode_id": pin.episode_id,
                             "actor_id": pin.actor_id})
            if (str(pinned_clip.clip_id) != str(pin.clip_id)
                    or pinned_clip.version != pin.clip_version):
                raise AnimationPinMismatchError(
                    "clip does not match the episode's pinned revision",
                    details={
                        "episode_id": pin.episode_id,
                        "actor_id": pin.actor_id,
                        "pinned_clip": str(pin.clip_id),
                        "pinned_version": pin.clip_version,
                        "given_clip": str(pinned_clip.clip_id),
                        "given_version": pinned_clip.version,
                    })
            return pinned_clip
        if pinned_clip is not None:
            raise AnimationPinMismatchError(
                "pinned clip supplied without an episode pin",
                details={"actor_id": intent.actor_id,
                         "clip": str(pinned_clip.clip_id)})
        return self.library.resolve(
            action=intent.action,
            emotion=intent.emotion,
            target_bones=target_bones,
            destination=intent.destination)

    @staticmethod
    def _invalidation_scope(prior_hash: Optional[str], current_hash: str,
                            track_id) -> List[str]:
        """Unchanged track -> nothing invalidated; changed -> preview only.

        §6: changing a body track invalidates ONLY its dependent animation
        preview — never assets, rigs or audio (they carry their own revision
        hashes).
        """
        if prior_hash is None:
            return []
        if prior_hash == current_hash:
            return []
        return [f"animation/preview:{track_id}"]


__all__ = [
    "ANIMATION_COMPILER_LAYER_VERSION",
    "AnimationCompileReceipt",
    "AnimationCompiler",
]
