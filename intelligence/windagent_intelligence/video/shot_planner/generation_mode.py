"""
Generation mode decision matrix (plan 03 §14.3).

Decision matrix (minimum):

| Condition                                        | Preferred mode                  |
|---|---|
| No mandatory reference, independent shot          | TEXT_TO_VIDEO                  |
| Identity / location reference mandatory           | IMAGE_TO_VIDEO / INGREDIENTS_TO_VIDEO |
| Needs defined start/end frames                    | FRAMES_TO_VIDEO                |
| Continues motion / scene from predecessor         | VIDEO_EXTENSION                |
| Transforms an existing clip                       | VIDEO_TO_VIDEO                 |

The decider RECORDS the preferred mode and acceptable fallbacks. The mode
must be inside the runtime provider's capability set; the Director never
calls the provider itself (plan §14.3).
"""

from __future__ import annotations

from typing import List

from windagent_core.domain.video_production.enums import (
    DependencyType,
    GenerationMode,
    GenerationModeReasonCode,
    RequiredArtifactType,
    ShotType,
)
from windagent_core.domain.video_production.ids import ReferenceAssetId
from windagent_core.domain.video_production.shot import (
    Shot,
    ShotDependency,
)
from windagent_core.domain.video_production.shot_graph import (
    GenerationModeDecision,
)


class GenerationModeDecider:
    """Deterministic generation mode decision per shot (plan §14.3)."""

    def __init__(self, *, version: str = "1.0.0") -> None:
        self.version = version

    def decide(
        self,
        *,
        shot: Shot,
        incoming: List[ShotDependency],
        scene_character_asset_ids: List[ReferenceAssetId],
        scene_location_asset_ids: List[ReferenceAssetId],
    ) -> GenerationModeDecision:
        """Return the preferred mode + acceptable fallbacks for one shot.

        Priority (first match wins):
        1. TRANSITION shots transform the two endpoint clips -> VIDEO_TO_VIDEO.
        2. Mandatory identity reference (character portrait bound) ->
           IMAGE_TO_VIDEO (fallback INGREDIENTS_TO_VIDEO).
        3. Defined start/end needed (FRAMES/transition dependency, or a
           TRANSITION dependency requiring both endpoints) -> FRAMES_TO_VIDEO.
        4. Motion/scene continuation (blocking CONTINUITY edge) ->
           VIDEO_EXTENSION.
        5. Mandatory location reference (coverage shot with location binding)
           -> IMAGE_TO_VIDEO (fallback INGREDIENTS_TO_VIDEO).
        6. Independent shot with no mandatory reference -> TEXT_TO_VIDEO.
        """
        # Rule 1: transition shot transforms the two endpoint clips.
        if shot.shot_type == ShotType.TRANSITION:
            return GenerationModeDecision(
                preferred_mode=GenerationMode.VIDEO_TO_VIDEO,
                acceptable_fallback_modes=[
                    GenerationMode.FRAMES_TO_VIDEO,
                    GenerationMode.IMAGE_TO_VIDEO,
                ],
                reason_code=GenerationModeReasonCode.CLIP_TRANSFORMATION,
                rationale=(
                    "A TRANSITION shot is built by transforming the two endpoint "
                    "clips into the transition."
                ),
            )

        # Rule 2: mandatory identity reference.
        identity_bound = [
            a for a in shot.reference_asset_ids if a in scene_character_asset_ids
        ]
        if identity_bound:
            return GenerationModeDecision(
                preferred_mode=GenerationMode.IMAGE_TO_VIDEO,
                acceptable_fallback_modes=[GenerationMode.INGREDIENTS_TO_VIDEO],
                reason_code=GenerationModeReasonCode.IDENTITY_REFERENCE_REQUIRED,
                rationale=(
                    "Character identity references are mandatory; the character "
                    "must be bound from a portrait/ingredient image."
                ),
            )

        # Rule 3: defined start/end frames needed.
        needs_frames = any(
            d.dependency_type == DependencyType.TRANSITION
            or d.required_artifact_type
            in (RequiredArtifactType.FIRST_FRAME, RequiredArtifactType.LAST_FRAME)
            for d in incoming
        )
        if needs_frames:
            return GenerationModeDecision(
                preferred_mode=GenerationMode.FRAMES_TO_VIDEO,
                acceptable_fallback_modes=[GenerationMode.IMAGE_TO_VIDEO],
                reason_code=GenerationModeReasonCode.FRAMES_REQUIRED,
                rationale=(
                    "This shot needs a defined start/end frame from its "
                    "predecessor dependency."
                ),
            )

        # Rule 4: motion / scene continuation from a blocking predecessor.
        continues = any(
            d.blocking
            and d.dependency_type == DependencyType.CONTINUITY
            and d.required_artifact_type == RequiredArtifactType.TAIL_FRAME
            for d in incoming
        )
        if continues:
            return GenerationModeDecision(
                preferred_mode=GenerationMode.VIDEO_EXTENSION,
                acceptable_fallback_modes=[
                    GenerationMode.FRAMES_TO_VIDEO,
                    GenerationMode.IMAGE_TO_VIDEO,
                ],
                reason_code=GenerationModeReasonCode.MOTION_CONTINUATION,
                rationale=(
                    "This shot continues the predecessor's motion/scene; "
                    "extend from its approved tail frame."
                ),
            )

        # Rule 5: mandatory location reference on a coverage shot.
        location_bound = [
            a for a in shot.reference_asset_ids if a in scene_location_asset_ids
        ]
        if location_bound and shot.shot_type not in (ShotType.ESTABLISHING,):
            return GenerationModeDecision(
                preferred_mode=GenerationMode.IMAGE_TO_VIDEO,
                acceptable_fallback_modes=[GenerationMode.INGREDIENTS_TO_VIDEO],
                reason_code=GenerationModeReasonCode.LOCATION_REFERENCE_REQUIRED,
                rationale=(
                    "Coverage shot requires the scene location identity; bind "
                    "the approved location reference."
                ),
            )

        # Rule 6: independent shot with no mandatory reference.
        return GenerationModeDecision(
            preferred_mode=GenerationMode.TEXT_TO_VIDEO,
            acceptable_fallback_modes=[],
            reason_code=GenerationModeReasonCode.NO_MANDATORY_REFERENCE,
            rationale=(
                "No mandatory reference; an independent shot can be generated "
                "from text alone."
            ),
        )


__all__ = ["GenerationModeDecider"]
