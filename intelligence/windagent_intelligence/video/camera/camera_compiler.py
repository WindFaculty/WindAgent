"""
Camera compiler (VP3D Phase 13, stage_g §3) — orchestrator.

Maps the Director's `CameraIntent` onto a deterministic, versioned
`CameraRigPlan`:

- rig primitive resolution (backlog 1) via `resolve_primitive`;
- lens/sensor/DOF/focus/look-at/path/easing/safe framing compile (backlog 2) —
  the compiler emits typed data only, NEVER `bpy`;
- shot start/end frame from duration/fps + dialogue timing constraints
  (backlog 3) — a dialogue line outside the shot's frame range fails closed;
- validation (180-degree rule, head/look room, subject visibility, lens
  bounds, path continuity, motion speed — backlog 4) via `CameraValidator`;
- occlusion preflight (backlog 5) via `OcclusionPreflight` (scene proxy,
  multi-frame sampling for moving cameras);
- manual camera override pin (backlog 7) — an active override pins a track
  revision; a drifted track fails closed with `CameraOverridePinMismatchError`.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import List, Optional

from windagent_core.domain.video_production.cinematography import (
    CameraFinding,
    CameraFindingKind,
    CameraIntent,
    CameraKeyframe,
    CameraOverride,
    CameraRigPlan,
    CameraValidationReport,
    CameraValidator,
)
from windagent_core.domain.video_production.errors import (
    CameraOverridePinMismatchError,
)
from windagent_core.domain.video_production.ids import (
    CameraFindingId,
    CameraRigPlanId,
    ShotId,
)
from windagent_core.domain.video_production.set_dressing import (
    Aabb,
    ForbiddenVolume,
    Vec3,
)
from windagent_intelligence.video.camera.rig_primitives import (
    resolve_primitive,
)
from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory

CAMERA_COMPILER_LAYER_VERSION = "1.0.0"
DEFAULT_START_FRAME = 1


class CameraCompileReceipt:
    """Result of one camera compile: plan + validation + invalidation scope."""

    def __init__(
        self,
        *,
        plan: CameraRigPlan,
        validation: CameraValidationReport,
        occlusion_findings: Optional[List[CameraFinding]] = None,
        invalidated_shot_ids: Optional[List[str]] = None,
        cleaned_ok: bool = True,
    ) -> None:
        self.plan = plan
        self.validation = validation
        self.occlusion_findings = occlusion_findings or []
        self.invalidated_shot_ids = invalidated_shot_ids or []
        self.cleaned_ok = cleaned_ok

    @property
    def plan_hash(self) -> str:
        return self.plan.plan_hash

    @property
    def all_findings(self) -> List[CameraFinding]:
        return [*self.validation.findings, *self.occlusion_findings]

    @property
    def blocking_kinds(self) -> List[str]:
        kinds = {f.kind for f in self.validation.blocking_findings}
        kinds |= {f.kind for f in self.occlusion_findings if f.blocking}
        return sorted(kinds)


class CameraCompiler:
    """Deterministic camera-intent -> rig-plan compiler (stage_g §3)."""

    compiler_version = CAMERA_COMPILER_LAYER_VERSION

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[CameraValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or CameraValidator()

    # ------------------------------------------------------------------
    def compile(
        self,
        *,
        intent: CameraIntent,
        previous_intent: Optional[CameraIntent] = None,
        subject_bounds: Optional[Aabb] = None,
        subject_facing: Optional[Vec3] = None,
        forbidden_volumes: Optional[List[ForbiddenVolume]] = None,
        override: Optional[CameraOverride] = None,
        track_revision: str = "",
        start_frame: Optional[int] = None,
        occlusion_preflight=None,
        require_clean: bool = True,
        prior_plan_hash: Optional[str] = None,
    ) -> CameraCompileReceipt:
        """Compile one shot's camera intent into a typed rig plan.

        ``track_revision`` is the CameraTrack's current content revision;
        ``override`` (Stage N manual placement) pins a revision — mismatch
        fails closed (backlog 7).
        """
        if override is not None and override.active:
            if track_revision and override.pinned_track_revision != track_revision:
                raise CameraOverridePinMismatchError(
                    "manual camera override pins a drifted track revision",
                    details={
                        "shot_id": str(intent.shot_id),
                        "pinned": override.pinned_track_revision,
                        "current": track_revision,
                    },
                )
            intent = self._apply_override(intent, override)

        primitive = resolve_primitive(intent.movement)
        start = start_frame or DEFAULT_START_FRAME
        end = start + max(1, math.ceil(intent.duration_seconds * intent.fps)) - 1

        plan = CameraRigPlan(
            plan_id=CameraRigPlanId(
                self.id_factory.camera_rig_plan_id(intent.shot_id)),
            shot_id=intent.shot_id,
            scene_id=intent.scene_id,
            movement=intent.movement,
            primitive_id=primitive.primitive_id,
            primitive_version=primitive.version,
            lens=intent.lens,
            focus=intent.focus,
            framing=intent.framing,
            path=intent.path,
            start_frame=start,
            end_frame=end,
            fps=intent.fps,
            intent_hash=self._intent_hash(intent),
            override_id=str(override.override_id)
            if override is not None and override.active else "",
        )
        plan = plan.model_copy(update={"plan_hash": plan.compute_stable_hash()})

        # backlog 3: dialogue timing must fit inside the shot's frame range
        dialogue_findings = self._check_dialogue_timing(intent, start, end)

        # backlog 4: automatic validation
        report = self.validator.validate(
            intent=intent,
            previous_intent=previous_intent,
            subject_bounds=subject_bounds,
            subject_facing=subject_facing,
            forbidden_volumes=forbidden_volumes,
            finding_prefix=self.id_factory.camera_finding_id(intent.shot_id),
        )
        report = report.model_copy(
            update={"findings": [*report.findings, *dialogue_findings]})

        # backlog 5: occlusion preflight (scene proxy, sampled frames)
        occlusion_findings: List[CameraFinding] = []
        if occlusion_preflight is not None and subject_bounds is not None:
            occlusion_findings = occlusion_preflight.preflight(
                plan=plan,
                subject_bounds=subject_bounds,
                forbidden_volumes=forbidden_volumes or [],
            )

        blocking = (
            report.blocking_findings
            or [f for f in occlusion_findings if f.blocking]
        )
        if require_clean and blocking:
            raise ValidationFailureError(
                "Camera intent failed validation; no rig plan is published.",
                details={
                    "shot_id": str(intent.shot_id),
                    "blocking_count": len(blocking),
                    "kinds": sorted({f.kind for f in blocking}),
                },
            )

        return CameraCompileReceipt(
            plan=plan,
            validation=report,
            occlusion_findings=occlusion_findings,
            invalidated_shot_ids=self._invalidation_scope(
                plan.plan_hash, prior_plan_hash, intent.shot_id),
            cleaned_ok=not blocking,
        )

    # ------------------------------------------------------------------
    def _check_dialogue_timing(self, intent: CameraIntent, start: int,
                               end: int) -> List[CameraFinding]:
        """Backlog 3: dialogue lines must fit inside [start, end] frames."""
        findings: List[CameraFinding] = []
        shot_start_s = (start - 1) / intent.fps
        shot_end_s = end / intent.fps
        for timing in intent.dialogue_timing:
            if (timing.start_second < shot_start_s - 1e-9
                    or timing.end_second > shot_end_s + 1e-9):
                findings.append(CameraFinding(
                    finding_id=CameraFindingId(
                        f"{intent.intent_id}:dlg:{timing.line_id}"),
                    kind=CameraFindingKind.DIALOGUE_TIMING_VIOLATION,
                    shot_id=intent.shot_id,
                    detail=(
                        f"dialogue {timing.line_id} [{timing.start_second:.2f}, "
                        f"{timing.end_second:.2f}]s outside shot "
                        f"[{shot_start_s:.2f}, {shot_end_s:.2f}]s"
                    ),
                    blocking=True,
                    measured={
                        "line_start_s": timing.start_second,
                        "line_end_s": timing.end_second,
                        "shot_start_s": shot_start_s,
                        "shot_end_s": shot_end_s,
                    },
                ))
        return findings

    @staticmethod
    def _apply_override(intent: CameraIntent, override: CameraOverride) -> CameraIntent:
        """Backlog 7: override placement wins over intent path start."""
        if override.position is None and override.look_at is None:
            return intent
        keys = list(intent.path.sorted_keyframes())
        if not keys:
            keys = [CameraKeyframe(
                frame=0, position=override.position or Vec3(),
                look_at=override.look_at or Vec3(),
            )]
        else:
            first = keys[0]
            keys[0] = CameraKeyframe(
                frame=first.frame,
                position=override.position or first.position,
                look_at=override.look_at or first.look_at,
                easing=first.easing,
            )
        return intent.model_copy(update={"path": intent.path.model_copy(
            update={"keyframes": keys})})

    @staticmethod
    def _intent_hash(intent: CameraIntent) -> str:
        payload = json.loads(intent.model_dump_json())
        payload["path"] = sorted(
            (k.frame, k.position.as_tuple(), k.look_at.as_tuple(), k.easing.value)
            for k in intent.path.keyframes
        )
        canonical = json.dumps(payload, sort_keys=True,
                               separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _invalidation_scope(current_hash: str, prior_hash: Optional[str],
                            shot_id: ShotId) -> List[str]:
        """Unchanged plan -> nothing invalidated; changed -> only this shot.

        No prior artifact means a fresh compile — nothing stale to invalidate.
        stage_g §5: changing the camera invalidates preview/render of the shot,
        never asset/rig/audio (they carry their own revision hashes).
        """
        if prior_hash is None:
            return []
        if prior_hash == current_hash:
            return []
        return [str(shot_id)]


__all__ = [
    "CAMERA_COMPILER_LAYER_VERSION",
    "CameraCompileReceipt",
    "CameraCompiler",
]
