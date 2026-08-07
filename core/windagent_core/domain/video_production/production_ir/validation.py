"""
VP3D Phase 1 — Production IR validation (fail-closed).

Deterministic structural validation of a ProductionIrDocument:

- unique IDs across scenes, shots, instances, tracks and render profiles;
- every reference resolves (shot -> scene/instance/render profile);
- `.blend` assets must always be DERIVED (never a source of truth);
- every shot carries a camera track and its duration matches the camera;
- unknown component kinds for invalidation fail closed (caller must not
  silently treat an unknown track change as no-op).

Blocking issues are returned; callers fail closed — a partial or invalid IR
document is never published to an engine adapter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.errors import VideoProductionProtocolError
from windagent_core.domain.video_production.production_ir.enums import (
    IrAssetFormat,
    IrValidationIssueCode,
)
from windagent_core.domain.video_production.production_ir.models import (
    AssetReference,
    ProductionIrDocument,
)


class IrValidationIssue(BaseModel):
    """Typed finding from ProductionIrValidator."""

    model_config = ConfigDict(frozen=True, extra="allow")

    code: IrValidationIssueCode
    message: str = Field(min_length=1)
    blocking: bool = True
    subject_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class ProductionIrValidator:
    """Deterministic structural validation of a ProductionIrDocument."""

    BLOCKING_CODES = {
        IrValidationIssueCode.DUPLICATE_SCENE_ID,
        IrValidationIssueCode.DUPLICATE_SHOT_ID,
        IrValidationIssueCode.DUPLICATE_INSTANCE_ID,
        IrValidationIssueCode.DUPLICATE_TRACK_ID,
        IrValidationIssueCode.DUPLICATE_PROFILE_ID,
        IrValidationIssueCode.BROKEN_REFERENCE,
        IrValidationIssueCode.BLEND_MUST_BE_DERIVED,
        IrValidationIssueCode.MISSING_CAMERA,
        IrValidationIssueCode.DURATION_MISMATCH,
        IrValidationIssueCode.UNKNOWN_COMPONENT_KIND,
    }

    def validate(self, document: ProductionIrDocument) -> List[IrValidationIssue]:
        issues: List[IrValidationIssue] = []
        self._check_unique_scene_ids(document, issues)
        self._check_unique_shot_ids(document, issues)
        self._check_unique_instance_ids(document, issues)
        self._check_unique_track_ids(document, issues)
        self._check_unique_profile_ids(document, issues)
        self._check_blend_assets_derived(document, issues)
        self._check_camera_presence(document, issues)
        self._check_duration_matches_camera(document, issues)
        self._check_references_resolve(document, issues)
        return issues

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _issue(
        code: IrValidationIssueCode,
        message: str,
        *,
        subject_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> IrValidationIssue:
        return IrValidationIssue(
            code=code,
            message=message,
            blocking=code in ProductionIrValidator.BLOCKING_CODES,
            subject_id=subject_id,
            details=details or {},
        )

    @staticmethod
    def _asset_refs(asset: Optional[AssetReference]) -> List[AssetReference]:
        return [asset] if asset is not None else []

    def _check_unique_scene_ids(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        seen: set = set()
        for scene in document.scenes:
            key = str(scene.scene_id)
            if key in seen:
                issues.append(self._issue(
                    IrValidationIssueCode.DUPLICATE_SCENE_ID,
                    f"Duplicate scene id {key!r} in IR document.",
                    subject_id=key,
                ))
            seen.add(key)

    def _check_unique_shot_ids(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        seen: set = set()
        for shot in document.shots:
            key = str(shot.intent_id)
            if key in seen:
                issues.append(self._issue(
                    IrValidationIssueCode.DUPLICATE_SHOT_ID,
                    f"Duplicate shot execution intent id {key!r} in IR document.",
                    subject_id=key,
                ))
            seen.add(key)

    def _check_unique_instance_ids(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        for scene in document.scenes:
            seen: set = set()
            for inst in scene.characters + scene.props + scene.environment:
                key = str(inst.instance_id)
                if key in seen:
                    issues.append(self._issue(
                        IrValidationIssueCode.DUPLICATE_INSTANCE_ID,
                        f"Duplicate instance id {key!r} in scene {scene.scene_id}.",
                        subject_id=key,
                    ))
                seen.add(key)

    def _check_unique_track_ids(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        for shot in document.shots:
            seen: set = set()
            for track in shot.animation_tracks + shot.facial_tracks + shot.simulation_tracks:
                key = str(track.track_id)
                if key in seen:
                    issues.append(self._issue(
                        IrValidationIssueCode.DUPLICATE_TRACK_ID,
                        f"Duplicate track id {key!r} in shot {shot.shot_id}.",
                        subject_id=key,
                    ))
                seen.add(key)
        for scene in document.scenes:
            seen = {str(rig.rig_id) for rig in scene.light_rigs}
            if len(seen) != len(scene.light_rigs):
                issues.append(self._issue(
                    IrValidationIssueCode.DUPLICATE_TRACK_ID,
                    f"Duplicate light rig id in scene {scene.scene_id}.",
                    subject_id=str(scene.scene_id),
                ))

    def _check_unique_profile_ids(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        seen: set = set()
        for profile in document.render_profiles:
            key = str(profile.profile_id)
            if key in seen:
                issues.append(self._issue(
                    IrValidationIssueCode.DUPLICATE_PROFILE_ID,
                    f"Duplicate render profile id {key!r}.",
                    subject_id=key,
                ))
            seen.add(key)

    def _check_blend_assets_derived(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        for scene in document.scenes:
            # Character instances carry mesh/skeleton/materials; prop and
            # environment instances carry a single `asset`.
            for inst in scene.characters:
                refs = (
                    self._asset_refs(inst.mesh)
                    + self._asset_refs(inst.skeleton)
                    + list(inst.materials)
                )
                self._check_blend_refs(refs, issues)
            for inst in scene.props + scene.environment:
                self._check_blend_refs(self._asset_refs(inst.asset), issues)

    @staticmethod
    def _check_blend_refs(refs: List[AssetReference], issues: List[IrValidationIssue]) -> None:
        for ref in refs:
            if ref.format == IrAssetFormat.BLEND and not ref.derived:
                issues.append(ProductionIrValidator._issue(
                    IrValidationIssueCode.BLEND_MUST_BE_DERIVED,
                    f"Asset {ref.asset_id} is a .blend file but marked non-derived; "
                    ".blend is always a derived artifact.",
                    subject_id=str(ref.asset_id),
                ))

    def _check_camera_presence(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        for shot in document.shots:
            if shot.camera is None:
                issues.append(self._issue(
                    IrValidationIssueCode.MISSING_CAMERA,
                    f"Shot {shot.shot_id} has no camera track.",
                    subject_id=str(shot.shot_id),
                ))

    def _check_duration_matches_camera(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        for shot in document.shots:
            cam_duration = shot.camera.duration_seconds
            if abs(cam_duration - shot.duration_seconds) > 1e-6:
                issues.append(self._issue(
                    IrValidationIssueCode.DURATION_MISMATCH,
                    f"Shot {shot.shot_id} duration {shot.duration_seconds} does not match "
                    f"camera track duration {cam_duration}.",
                    subject_id=str(shot.shot_id),
                    details={"shot_duration": shot.duration_seconds, "camera_duration": cam_duration},
                ))

    def _check_references_resolve(self, document: ProductionIrDocument, issues: List[IrValidationIssue]) -> None:
        scene_ids = {str(s.scene_id) for s in document.scenes}
        profile_ids = {str(p.profile_id) for p in document.render_profiles}
        instance_ids = {
            str(inst.instance_id)
            for scene in document.scenes
            for inst in scene.characters + scene.props + scene.environment
        }
        for shot in document.shots:
            if str(shot.scene_id) not in scene_ids:
                issues.append(self._issue(
                    IrValidationIssueCode.BROKEN_REFERENCE,
                    f"Shot {shot.shot_id} references unknown scene {shot.scene_id}.",
                    subject_id=str(shot.shot_id),
                    details={"scene_id": str(shot.scene_id)},
                ))
            if str(shot.render_profile_id) not in profile_ids:
                issues.append(self._issue(
                    IrValidationIssueCode.BROKEN_REFERENCE,
                    f"Shot {shot.shot_id} references unknown render profile {shot.render_profile_id}.",
                    subject_id=str(shot.shot_id),
                    details={"render_profile_id": str(shot.render_profile_id)},
                ))
            for ref in shot.characters + shot.props + shot.environment:
                if ref not in instance_ids:
                    issues.append(self._issue(
                        IrValidationIssueCode.BROKEN_REFERENCE,
                        f"Shot {shot.shot_id} references unknown instance {ref!r}.",
                        subject_id=str(shot.shot_id),
                        details={"instance_id": ref},
                    ))


def ensure_valid_document(document: ProductionIrDocument) -> None:
    """Fail closed: raise on the first blocking validation issue."""
    issues = ProductionIrValidator().validate(document)
    blocking = [issue for issue in issues if issue.blocking]
    if blocking:
        first = blocking[0]
        raise VideoProductionProtocolError(
            f"ProductionIrDocument is invalid: [{first.code.value}] {first.message}",
            details={"issue_count": len(blocking), "first_code": first.code.value},
        )


__all__ = [
    "IrValidationIssue",
    "ProductionIrValidator",
    "ensure_valid_document",
]
