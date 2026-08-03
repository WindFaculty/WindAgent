"""
ShotDependencyGraph builder (plan 03 §13, §14.4).

Builds typed dependency edges between shots with full Phase 9 semantics:

- TEMPORAL: in-scene shot order (non-blocking scheduling hint);
- DIALOGUE: consecutive dialogue flow within a scene (blocking when the
  successor needs the predecessor's delivered line to react to);
- CONTINUITY: same-subject shots keep identity/motion continuity (blocking,
  requires the predecessor's TAIL_FRAME);
- TRANSITION: a non-CUT transition needs BOTH endpoint clips (blocking,
  requires FULL_CLIP);
- VISUAL_REFERENCE: a shot whose framing composes from a predecessor's
  established geography (non-blocking advisory);
- ASSET: shots that share approved reference assets (non-blocking advisory).

The builder is fully deterministic: the LLM proposed the shot plan in
Phase 8; this layer only derives typed edges from the plan + package facts.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.enums import (
    DependencyType,
    RequiredArtifactType,
    ShotType,
    TransitionType,
)
from windagent_core.domain.video_production.ids import (
    ReferenceAssetId,
    ShotDependencyId,
    ShotId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.scene import Scene
from windagent_core.domain.video_production.shot import (
    Shot,
    ShotDependency,
    ShotDependencyGraph,
)

from windagent_intelligence.video.ids import StableIdFactory


class ShotGraphBuilder:
    """Deterministic typed-edge builder over a planned shot set."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()

    def build(
        self,
        package: VideoProductionPackage,
        shots: List[Shot],
    ) -> ShotDependencyGraph:
        """Build the typed dependency graph from the plan shots."""
        by_scene = _group_by_scene(shots)
        scenes_by_id = (
            {str(s.scene_id): s for s in package.screenplay.scenes}
            if package.screenplay
            else {}
        )

        dependencies: List[ShotDependency] = []
        for scene_id, scene_shots in by_scene.items():
            scene = scenes_by_id.get(scene_id)
            ordered = sorted(scene_shots, key=lambda s: s.order)
            if not ordered:
                continue
            # TEMPORAL: in-scene shot order (non-blocking scheduling hint).
            for prev, curr in zip(ordered, ordered[1:]):
                dependencies.append(self._edge(
                    DependencyType.TEMPORAL,
                    prev.shot_id,
                    curr.shot_id,
                    required_artifact_type=RequiredArtifactType.NONE,
                    reason="in-scene shot order",
                    blocking=False,
                ))
            # DIALOGUE: consecutive dialogue flow; successor reacts to the
            # predecessor's delivered line (blocking).
            for prev, curr in zip(ordered, ordered[1:]):
                if prev.dialogue_line_ids and curr.dialogue_line_ids:
                    dependencies.append(self._edge(
                        DependencyType.DIALOGUE,
                        prev.shot_id,
                        curr.shot_id,
                        required_artifact_type=RequiredArtifactType.FULL_CLIP,
                        reason="dialogue flow; successor reacts to the delivered line",
                        blocking=True,
                    ))
            # CONTINUITY: shots that share a character subject must preserve
            # identity/motion continuity (blocking, TAIL_FRAME).
            character_assets = _scene_character_assets(package, scene)
            for i, prev in enumerate(ordered):
                for curr in ordered[i + 1:]:
                    if _share_character(prev, curr, character_assets):
                        dependencies.append(self._edge(
                            DependencyType.CONTINUITY,
                            prev.shot_id,
                            curr.shot_id,
                            required_artifact_type=RequiredArtifactType.TAIL_FRAME,
                            reason="shared subject; continuity needs the predecessor tail frame",
                            blocking=True,
                        ))
            # TRANSITION: a non-CUT transition needs BOTH endpoint clips.
            for prev, curr in zip(ordered, ordered[1:]):
                if prev.transition_type != TransitionType.CUT:
                    dependencies.append(self._edge(
                        DependencyType.TRANSITION,
                        prev.shot_id,
                        curr.shot_id,
                        required_artifact_type=RequiredArtifactType.FULL_CLIP,
                        reason="transition requires both endpoint clips",
                        blocking=True,
                    ))
            # VISUAL_REFERENCE: establishing -> coverage composition (advisory).
            if scene is not None and any(
                s.shot_type == ShotType.ESTABLISHING for s in ordered
            ):
                establishing = next(
                    s for s in ordered if s.shot_type == ShotType.ESTABLISHING
                )
                for curr in ordered:
                    if curr.shot_id == establishing.shot_id:
                        continue
                    dependencies.append(self._edge(
                        DependencyType.VISUAL_REFERENCE,
                        establishing.shot_id,
                        curr.shot_id,
                        required_artifact_type=RequiredArtifactType.REFERENCE_IMAGE,
                        reason="coverage composes from the established geography",
                        blocking=False,
                    ))
            # ASSET: shots sharing approved reference assets (advisory).
            for i, prev in enumerate(ordered):
                for curr in ordered[i + 1:]:
                    shared = set(prev.reference_asset_ids) & set(curr.reference_asset_ids)
                    if shared and prev.dialogue_line_ids and curr.dialogue_line_ids:
                        dependencies.append(self._edge(
                            DependencyType.ASSET,
                            prev.shot_id,
                            curr.shot_id,
                            required_artifact_type=RequiredArtifactType.REFERENCE_IMAGE,
                            reason="shared approved reference asset binding",
                            blocking=False,
                        ))

        return ShotDependencyGraph(shots=list(shots), dependencies=dependencies)

    def _edge(
        self,
        dep_type: DependencyType,
        from_shot_id: ShotId,
        to_shot_id: ShotId,
        *,
        required_artifact_type: RequiredArtifactType,
        reason: str,
        blocking: bool,
    ) -> ShotDependency:
        return ShotDependency(
            dependency_id=ShotDependencyId(
                self.id_factory.shot_dependency_id(
                    dep_type.value.lower(), from_shot_id, to_shot_id
                )
            ),
            from_shot_id=from_shot_id,
            to_shot_id=to_shot_id,
            dependency_type=dep_type,
            required_artifact_type=required_artifact_type,
            reason=reason,
            blocking=blocking,
        )


def _group_by_scene(shots: List[Shot]) -> Dict[str, List[Shot]]:
    by_scene: Dict[str, List[Shot]] = {}
    for shot in shots:
        by_scene.setdefault(str(shot.scene_id), []).append(shot)
    return by_scene


def _scene_character_assets(
    package: VideoProductionPackage, scene: Optional[Scene]
) -> List[ReferenceAssetId]:
    if scene is None:
        return []
    scene_char_ids = {str(c) for c in scene.character_ids}
    assets: List[ReferenceAssetId] = []
    for char in package.characters:
        if str(char.character_id) in scene_char_ids:
            assets.extend(char.portrait_asset_ids)
    return assets


def _share_character(
    prev: Shot,
    curr: Shot,
    character_assets: List[ReferenceAssetId],
) -> bool:
    """True when both shots bind at least one common character identity."""
    prev_assets = set(str(a) for a in prev.reference_asset_ids)
    curr_assets = set(str(a) for a in curr.reference_asset_ids)
    char_asset_keys = set(str(a) for a in character_assets)
    return bool(
        (prev_assets & char_asset_keys) and (curr_assets & char_asset_keys)
    )


__all__ = ["ShotGraphBuilder"]
