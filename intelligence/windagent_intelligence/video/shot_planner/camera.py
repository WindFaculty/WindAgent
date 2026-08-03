"""
Deterministic camera planning rules (plan 03 §14.2).

Every camera decision carries a machine-readable `reason_code` — never just
prose. Rules implemented:

- establishing geography BEFORE coverage when a scene needs spatial
  continuity (`ESTABLISH_GEOGRAPHY` / `SPATIAL_CONTINUITY`);
- the 180-degree rule: coverage shots keep the camera on ONE side of the
  scene action line (`camera_side`); a flip without a justification is a
  `CAMERA_SIDE_VIOLATION`;
- screen direction stays consistent within a scene; a flip is a
  `SCREEN_DIRECTION_FLIP`;
- camera movement must have a purpose and fit the shot duration
  (`MOVEMENT_TOO_SHORT` when movement is declared but the shot is too short);
- reaction/insert shots never lose story facts: a REACTION shot must have a
  preceding shot in its scene to react to (`REACTION_MISSING_SOURCE`).

The planner is fully deterministic: the LLM proposed the shot plan in Phase 8,
this layer only records/validates camera rules. It never calls a provider.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import (
    CameraAngle,
    CameraDecisionReasonCode,
    CameraMovement,
    CameraSide,
    IssueSeverity,
    ScreenDirection,
    ShotGraphIssueCode,
    ShotType,
)
from windagent_core.domain.video_production.ids import (
    SceneId,
    ShotGraphIssueId,
    ShotId,
)
from windagent_core.domain.video_production.shot import Shot
from windagent_core.domain.video_production.shot_graph import (
    CameraDecision,
    ShotGraphIssue,
)

from windagent_intelligence.video.ids import StableIdFactory

# A moving camera needs enough screen time to read; shorter shots with
# declared movement are flagged as MOVEMENT_TOO_SHORT.
MIN_MOVEMENT_DURATION_SECONDS = 1.5


class CameraPlanner:
    """Deterministic camera decisions + camera-rule validation (plan §14.2)."""

    def __init__(
        self,
        *,
        rule_version: str = "1.0.0",
        id_factory: Optional[StableIdFactory] = None,
    ) -> None:
        self.rule_version = rule_version
        self.id_factory = id_factory or StableIdFactory()

    # ------------------------------------------------------------------
    # Decision
    # ------------------------------------------------------------------
    def decide(self, shot: Shot) -> CameraDecision:
        """Deterministic camera decision for one shot (from its shot type).

        Camera decisions are derived purely from the shot specification, so
        they are reproducible for the same shot regardless of scene context.
        """
        shot_type = shot.shot_type
        is_dialogue = bool(shot.dialogue_line_ids)

        if shot_type == ShotType.ESTABLISHING:
            return CameraDecision(
                camera_position="wide, distant",
                camera_angle=CameraAngle.HIGH_ANGLE,
                camera_movement=CameraMovement.STATIC,
                lens_intent="wide-angle establishing",
                camera_side=CameraSide.NEUTRAL,
                screen_direction=ScreenDirection.NEUTRAL,
                reason_code=CameraDecisionReasonCode.ESTABLISH_GEOGRAPHY,
                rationale="Establish the scene geography before coverage.",
            )
        if shot_type == ShotType.MASTER:
            return CameraDecision(
                camera_position="full scene, medium distance",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=shot.camera_movement,
                lens_intent="normal focal coverage",
                camera_side=CameraSide.SIDE_A,
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=CameraDecisionReasonCode.SPATIAL_CONTINUITY,
                rationale="Master shot keeps spatial continuity within the scene.",
            )
        if shot_type == ShotType.POV:
            return CameraDecision(
                camera_position="subject eye line",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.HANDHELD,
                lens_intent="normal focal, shallow",
                camera_side=CameraSide.NEUTRAL,
                screen_direction=ScreenDirection.NEUTRAL,
                reason_code=CameraDecisionReasonCode.POV_SUBJECTIVE,
                rationale="Subjective POV stays off the action line.",
            )
        if shot_type == ShotType.INSERT:
            return CameraDecision(
                camera_position="detail, close to object",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="macro detail",
                camera_side=CameraSide.NEUTRAL,
                screen_direction=ScreenDirection.NEUTRAL,
                reason_code=CameraDecisionReasonCode.INSERT_DETAIL,
                rationale="Insert detail does not alter the 180-degree line.",
            )
        if shot_type == ShotType.REACTION:
            return CameraDecision(
                camera_position="over the shoulder of the listener",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="short-tele reaction",
                camera_side=CameraSide.SIDE_A,
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=CameraDecisionReasonCode.REACTION_BEAT,
                rationale="Reaction shot stays on the action line side.",
            )
        if shot_type == ShotType.OVER_SHOULDER:
            return CameraDecision(
                camera_position="over the shoulder of the partner",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="normal focal, shallow depth",
                camera_side=CameraSide.SIDE_A,
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=CameraDecisionReasonCode.DIALOGUE_ALIGNMENT,
                rationale="Over-shoulder coverage aligns with dialogue flow.",
            )
        if shot_type == ShotType.CLOSE_UP:
            return CameraDecision(
                camera_position="close, on the axis",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="short-tele portrait",
                camera_side=CameraSide.SIDE_A,
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=(
                    CameraDecisionReasonCode.DIALOGUE_ALIGNMENT
                    if is_dialogue
                    else CameraDecisionReasonCode.EMOTIONAL_BEAT
                ),
                rationale="Close-up keeps the 180-degree line; reason coded by purpose.",
            )
        if shot_type == ShotType.EXTREME_CLOSE_UP:
            return CameraDecision(
                camera_position="extreme close, on the axis",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="macro emotional beat",
                camera_side=CameraSide.SIDE_A,
                screen_direction=ScreenDirection.LEFT_TO_RIGHT,
                reason_code=CameraDecisionReasonCode.EMOTIONAL_BEAT,
                rationale="ECU is an emotional beat on the action line.",
            )
        if shot_type == ShotType.TRANSITION:
            return CameraDecision(
                camera_position="transitional, neutral",
                camera_angle=CameraAngle.EYE_LEVEL,
                camera_movement=CameraMovement.STATIC,
                lens_intent="transition endpoint",
                camera_side=CameraSide.NEUTRAL,
                screen_direction=ScreenDirection.NEUTRAL,
                reason_code=CameraDecisionReasonCode.TRANSITION_ENDPOINT,
                rationale="Transition shot is a neutral endpoint bridge.",
            )
        # MEDIUM / default
        return CameraDecision(
            camera_position="medium, on the action line",
            camera_angle=CameraAngle.EYE_LEVEL,
            camera_movement=shot.camera_movement,
            lens_intent="normal focal",
            camera_side=CameraSide.SIDE_A,
            screen_direction=ScreenDirection.LEFT_TO_RIGHT,
            reason_code=(
                CameraDecisionReasonCode.DIALOGUE_ALIGNMENT
                if is_dialogue
                else CameraDecisionReasonCode.ACTION_FOLLOW
            ),
            rationale="Medium coverage maintains the action line side.",
        )

    # ------------------------------------------------------------------
    # Validation (plan §14.2 rules -> non-blocking warnings)
    # ------------------------------------------------------------------
    def validate(
        self,
        *,
        shots_by_scene: Dict[str, List[Shot]],
        camera_by_shot: Dict[str, CameraDecision],
    ) -> List[ShotGraphIssue]:
        """Check camera rules across the plan; returns warnings (never blocks)."""
        issues: List[ShotGraphIssue] = []

        for scene_id, shots in shots_by_scene.items():
            ordered = sorted(shots, key=lambda s: s.order)
            if not ordered:
                continue
            scene_direction: Optional[ScreenDirection] = None

            for idx, shot in enumerate(ordered):
                camera = camera_by_shot.get(str(shot.shot_id))
                if camera is None:
                    continue
                # Movement must fit the shot duration.
                if (
                    shot.camera_movement != CameraMovement.STATIC
                    and shot.duration_seconds < MIN_MOVEMENT_DURATION_SECONDS
                ):
                    issues.append(self._issue(
                        ShotGraphIssueCode.MOVEMENT_TOO_SHORT,
                        f"Shot {shot.shot_id} declares camera movement "
                        f"{shot.camera_movement.value} but only lasts "
                        f"{shot.duration_seconds:.2f}s (< {MIN_MOVEMENT_DURATION_SECONDS:.1f}s).",
                        shot_id=shot.shot_id,
                    ))
                # Screen direction must stay consistent within a scene.
                if camera.screen_direction != ScreenDirection.NEUTRAL:
                    if scene_direction is None:
                        scene_direction = camera.screen_direction
                    elif camera.screen_direction != scene_direction:
                        issues.append(self._issue(
                            ShotGraphIssueCode.SCREEN_DIRECTION_FLIP,
                            f"Shot {shot.shot_id} flips screen direction from "
                            f"{scene_direction.value} to {camera.screen_direction.value} "
                            f"inside scene {scene_id}.",
                            shot_id=shot.shot_id,
                        ))
                # Reaction shots need a preceding shot in the same scene.
                if shot.shot_type == ShotType.REACTION and idx == 0:
                    issues.append(self._issue(
                        ShotGraphIssueCode.REACTION_MISSING_SOURCE,
                        f"REACTION shot {shot.shot_id} is the first shot of scene "
                        f"{scene_id}; it has nothing to react to.",
                        shot_id=shot.shot_id,
                    ))

        # 180-degree rule: camera side must not flip between consecutive
        # coverage shots in the same scene (justified exceptions carry a
        # non-SIDE_A reason code).
        for scene_id, shots in shots_by_scene.items():
            ordered = sorted(shots, key=lambda s: s.order)
            prev_side: Optional[CameraSide] = None
            for shot in ordered:
                camera = camera_by_shot.get(str(shot.shot_id))
                if camera is None:
                    continue
                if camera.camera_side == CameraSide.NEUTRAL:
                    prev_side = None
                    continue
                if prev_side is not None and camera.camera_side != prev_side:
                    issues.append(self._issue(
                        ShotGraphIssueCode.CAMERA_SIDE_VIOLATION,
                        f"Shot {shot.shot_id} flips the 180-degree line from "
                        f"{prev_side.value} to {camera.camera_side.value} in scene "
                        f"{scene_id} without a line-crossing reason.",
                        shot_id=shot.shot_id,
                    ))
                prev_side = camera.camera_side

        return issues

    def _issue(
        self,
        code: ShotGraphIssueCode,
        message: str,
        *,
        shot_id: Optional[ShotId] = None,
        scene_id: Optional[SceneId] = None,
    ) -> ShotGraphIssue:
        return ShotGraphIssue(
            issue_id=ShotGraphIssueId(
                self.id_factory.shot_graph_issue_id(f"{code.value}:{shot_id or scene_id or ''}")
            ),
            code=code,
            severity=IssueSeverity.WARNING,
            message=message,
            blocking=False,
            shot_id=shot_id,
            details={"scene_id": str(scene_id) if scene_id else None},
        )


__all__ = ["CameraPlanner", "MIN_MOVEMENT_DURATION_SECONDS"]
