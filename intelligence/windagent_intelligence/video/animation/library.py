"""
Animation library registry (VP3D Phase 15, stage_h §3 backlog 1/2/3).

The minimal library — idle, walk, run, jump, sit, stand, talk, laugh, cry,
point, wave, pick-up and put-down — is versioned; every clip carries typed
provenance (source provider, license) and a deterministic content hash.

Resolution keys on action + emotion + skeleton compatibility (backlog 3):
a clip is a candidate when its action matches, its emotion matches exactly
(or falls back to NEUTRAL), every required semantic bone exists in the target
skeleton, and a destination is supplied for anchor-bound clips. Display names
are NEVER a resolution key — a clip named "walk" with action=IDLE is only
resolvable as IDLE.
"""

from __future__ import annotations

from typing import List, Optional

from windagent_core.domain.video_production.animation import (
    AnimationClip,
    ClipProvenance,
)
from windagent_core.domain.video_production.enums import (
    AnimationAction,
    AnimationEmotion,
    ClipSource,
    LicenseState,
    SemanticBone,
)
from windagent_core.domain.video_production.errors import AnimationCompileError
from windagent_core.domain.video_production.ids import (
    AnimationClipId,
    SkeletonProfileId,
)
from windagent_intelligence.video.ids import StableIdFactory

ANIMATION_LIBRARY_VERSION = "1.0.0"

# The library clips were captured/retargeted for the standard humanoid; they
# are compatible with any skeleton carrying the same semantic roles.
LIBRARY_SKELETON = SkeletonProfileId("skel_library_humanoid")
COMPATIBLE_SKELETONS = [
    SkeletonProfileId("skel_humanoid_standard"),
    SkeletonProfileId("skel_mixamo_retargeted"),
]

REQUIRED_HUMANOID_BONES: List[SemanticBone] = [
    SemanticBone.ROOT,
    SemanticBone.PELVIS,
    SemanticBone.SPINE,
    SemanticBone.CHEST,
    SemanticBone.NECK,
    SemanticBone.HEAD,
    SemanticBone.SHOULDER_L,
    SemanticBone.SHOULDER_R,
    SemanticBone.ARM_UPPER_L,
    SemanticBone.ARM_UPPER_R,
    SemanticBone.ARM_LOWER_L,
    SemanticBone.ARM_LOWER_R,
    SemanticBone.HAND_L,
    SemanticBone.HAND_R,
    SemanticBone.THIGH_L,
    SemanticBone.THIGH_R,
    SemanticBone.SHIN_L,
    SemanticBone.SHIN_R,
    SemanticBone.FOOT_L,
    SemanticBone.FOOT_R,
]

_ID_FACTORY = StableIdFactory()


def _clip(
    action: AnimationAction,
    *,
    duration_seconds: float,
    root_motion_meters: float,
    emotion: AnimationEmotion = AnimationEmotion.NEUTRAL,
    name: str = "",
    requires_destination: bool = False,
    provider: str = "library",
    license: LicenseState = LicenseState.LICENSED,
    fps: int = 30,
) -> AnimationClip:
    """One library clip entry; id is content-derived, never name-derived."""
    clip_id = _ID_FACTORY.animation_clip_id(action.value, emotion.value,
                                            ANIMATION_LIBRARY_VERSION)
    return AnimationClip(
        clip_id=AnimationClipId(clip_id),
        name=name or action.value.lower(),
        action=action,
        emotion=emotion,
        skeleton_profile_id=LIBRARY_SKELETON,
        compatible_skeleton_ids=list(COMPATIBLE_SKELETONS),
        required_bones=list(REQUIRED_HUMANOID_BONES),
        duration_seconds=duration_seconds,
        fps=fps,
        root_motion_meters=root_motion_meters,
        requires_destination=requires_destination,
        version=ANIMATION_LIBRARY_VERSION,
        provenance=ClipProvenance(
            source=ClipSource.MOCAP_CAPTURE,
            provider=provider,
            recording_session=f"lib-{action.value.lower()}",
            license=license,
        ),
    )


def _build_library() -> List[AnimationClip]:
    """The minimal 13-clip library (stage_h §3 backlog 2)."""
    return [
        _clip(AnimationAction.IDLE, duration_seconds=4.0,
              root_motion_meters=0.0),
        _clip(AnimationAction.WALK, duration_seconds=2.0,
              root_motion_meters=1.6),
        _clip(AnimationAction.RUN, duration_seconds=1.2,
              root_motion_meters=2.4),
        _clip(AnimationAction.JUMP, duration_seconds=0.8,
              root_motion_meters=0.9),
        _clip(AnimationAction.SIT, duration_seconds=1.5,
              root_motion_meters=0.3),
        _clip(AnimationAction.STAND, duration_seconds=1.5,
              root_motion_meters=0.3),
        _clip(AnimationAction.TALK, duration_seconds=3.0,
              root_motion_meters=0.05),
        _clip(AnimationAction.LAUGH, duration_seconds=2.4,
              root_motion_meters=0.1, emotion=AnimationEmotion.HAPPY),
        _clip(AnimationAction.CRY, duration_seconds=3.2,
              root_motion_meters=0.05, emotion=AnimationEmotion.SAD),
        _clip(AnimationAction.POINT, duration_seconds=1.2,
              root_motion_meters=0.0),
        _clip(AnimationAction.WAVE, duration_seconds=1.4,
              root_motion_meters=0.0, emotion=AnimationEmotion.HAPPY),
        _clip(AnimationAction.PICK_UP, duration_seconds=2.2,
              root_motion_meters=0.4, requires_destination=True),
        _clip(AnimationAction.PUT_DOWN, duration_seconds=2.2,
              root_motion_meters=0.4, requires_destination=True),
    ]


class AnimationLibrary:
    """Versioned clip library with name-free, fail-closed resolution."""

    def __init__(self, clips: Optional[List[AnimationClip]] = None) -> None:
        self._clips = list(clips) if clips is not None else _build_library()

    # ------------------------------------------------------------------
    def all_clips(self) -> List[AnimationClip]:
        return list(self._clips)

    def get_clip(self, clip_id: str,
                 version: Optional[str] = None) -> Optional[AnimationClip]:
        for clip in self._clips:
            if str(clip.clip_id) == clip_id and (
                    version is None or clip.version == version):
                return clip
        return None

    def resolve(
        self,
        *,
        action: AnimationAction,
        emotion: AnimationEmotion = AnimationEmotion.NEUTRAL,
        target_bones: List[SemanticBone],
        destination: Optional[str] = None,
    ) -> AnimationClip:
        """Resolve one clip by action/emotion/skeleton — never display name.

        Fail-closed reasons (stage_h §6): MISSING_ACTION when no clip exists
        for the action, INCOMPATIBLE_SKELETON when none of the candidates'
        required bones fit the target skeleton, MISSING_DESTINATION when the
        only candidates are anchor-bound and no destination was given.
        """
        action_candidates = [
            c for c in self._clips if c.action == action
        ]
        if not action_candidates:
            raise AnimationCompileError(
                f"no library clip for action {action.value}",
                details={"kind": "MISSING_ACTION", "action": action.value})

        exact = [c for c in action_candidates if c.emotion == emotion]
        candidates = exact or [
            c for c in action_candidates
            if c.emotion == AnimationEmotion.NEUTRAL]
        if not candidates:
            raise AnimationCompileError(
                f"no {action.value} clip for emotion {emotion.value}",
                details={"kind": "MISSING_ACTION",
                         "action": action.value,
                         "emotion": emotion.value})

        target_set = set(target_bones)
        compatible = [
            c for c in candidates
            if all(b in target_set for b in c.required_bones)]
        if not compatible:
            raise AnimationCompileError(
                f"no {action.value} clip compatible with target skeleton "
                f"({len(target_bones)} bones given)",
                details={"kind": "INCOMPATIBLE_SKELETON",
                         "action": action.value,
                         "missing_bones": sorted(
                             {str(b) for b in candidates[0].required_bones
                              if b not in target_set})})

        anchored = [c for c in compatible if c.requires_destination]
        if anchored and not destination:
            raise AnimationCompileError(
                f"clip {compatible[0].clip_id} requires a destination",
                details={"kind": "MISSING_DESTINATION",
                         "action": action.value,
                         "clip_id": str(compatible[0].clip_id)})

        # deterministic pick: content-derived id, stable across runs
        chosen = sorted(compatible, key=lambda c: str(c.clip_id))[0]
        return chosen


# module-level conveniences (mirror the lighting preset registry API)
def all_clips() -> List[AnimationClip]:
    return AnimationLibrary().all_clips()


def get_clip(clip_id: str,
             version: Optional[str] = None) -> Optional[AnimationClip]:
    return AnimationLibrary().get_clip(clip_id, version)


def resolve_clip(
    *,
    action: AnimationAction,
    emotion: AnimationEmotion = AnimationEmotion.NEUTRAL,
    target_bones: List[SemanticBone],
    destination: Optional[str] = None,
) -> AnimationClip:
    return AnimationLibrary().resolve(
        action=action, emotion=emotion, target_bones=target_bones,
        destination=destination)


def supported_clip_actions() -> List[str]:
    return [a.value for a in AnimationAction]


__all__ = [
    "ANIMATION_LIBRARY_VERSION",
    "LIBRARY_SKELETON",
    "COMPATIBLE_SKELETONS",
    "REQUIRED_HUMANOID_BONES",
    "AnimationLibrary",
    "all_clips",
    "get_clip",
    "resolve_clip",
    "supported_clip_actions",
]
