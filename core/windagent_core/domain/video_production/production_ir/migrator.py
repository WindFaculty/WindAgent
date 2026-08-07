"""
VP3D Phase 1 — Legacy-to-IR migrator (reader for the compatibility window).

Field-by-field mapping from the legacy video-production schemas onto the
engine-neutral Production IR (plan §4 backlog items 1-3, 8):

- `VideoProductionPackage v1` + `Shot` -> `ProductionIrDocument` /
  `ShotExecutionIntent` / `SceneDescription`;
- `GenerationModeDecision`        -> NOT carried; only its rationale is kept
  as an advisory execution hint (the engine decides execution);
- `FlowGenerationSpecification`   -> creative prompt + reference hashes are
  extracted; provider/mode fields are DROPPED;
- `GenerationRequest`             -> idempotency identity + parameters are
  extracted; provider/mode fields are DROPPED.

Invariants preserved by design (plan §4 test requirements):
- stable IDs (shot/scene/character/location/prop/dialogue) keep their values;
- ordering (scene order, shot order) is preserved;
- provenance and approval state are carried onto the IR document;
- the IR contains NO `generation_mode` / provider field anywhere.

The migrator is a READER: it never mutates the legacy package. It is the
bounded compatibility path used during Stage A; it is not a permanent
dual-write mechanism.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.enums import MediaType
from windagent_core.domain.video_production.ids import (
    CameraTrackId,
    CharacterInstanceId,
    EnvironmentInstanceId,
    LightRigId,
    PropInstanceId,
    RenderIntentId,
    RenderProfileId,
    SceneDescriptionId,
    ShotExecutionIntentId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.production_ir.enums import IrAssetFormat
from windagent_core.domain.video_production.production_ir.models import (
    DEFAULT_RENDER_PROFILE_ID,
    AssetReference,
    CameraTrack,
    CharacterInstance,
    DialogueTrack,
    EnvironmentInstance,
    LightRig,
    PropInstance,
    ProductionIrDocument,
    RenderIntent,
    RenderProfile,
    SceneDescription,
    ShotExecutionIntent,
)
# Bounded legacy compatibility types — read ONLY by this migrator during the
# Stage A compatibility window (see legacy_v1/SUNSET.md).
from windagent_core.domain.video_production.legacy_v1 import (
    FlowGenerationSpecification,
    GenerationModeDecision,
    LegacyGenerationRequest,
)


class ProductionIrMigrator:
    """Migrate legacy video-production artifacts onto the Production IR."""

    def __init__(self, *, id_factory: Optional[Callable[[str], str]] = None) -> None:
        self._id_factory = id_factory

    # -- id helpers --------------------------------------------------------
    def _id(self, prefix: str, value: str) -> str:
        if self._id_factory is not None:
            return self._id_factory(f"{prefix}:{value}")
        return value  # preserve the legacy ID value by default

    # -- package migration -------------------------------------------------
    def migrate_package(self, package: VideoProductionPackage) -> ProductionIrDocument:
        """Migrate a VideoProductionPackage v1 onto a ProductionIrDocument.

        Preserves project/revision IDs, ordering, provenance and approval
        state; NEVER carries `generation_mode` or provider concepts.
        """
        assets_by_id = {str(a.asset_id): a for a in package.assets}
        scenes = self._migrate_scenes(package, assets_by_id)
        shots = self._migrate_shots(package, assets_by_id)
        profile = self._default_render_profile()
        render_intents = self._migrate_render_intents(scenes, shots, profile)

        approval_ref = ""
        approvals = package.approvals
        if approvals and approvals.approvals:
            approval_ref = approvals.approvals[-1].target_hash

        provenance = package.provenance.model_dump() if package.provenance else {}

        return ProductionIrDocument(
            ir_id=self._ir_id(package),
            project_id=package.project_id,
            revision_id=package.revision_id,
            source_package_hash=package.content_hash(),
            scenes=scenes,
            shots=shots,
            render_profiles=[profile],
            render_intents=render_intents,
            locked=bool(approvals and approvals.locked),
            approval_state_ref=approval_ref,
            provenance=provenance,
        )

    # -- internal ----------------------------------------------------------
    def _ir_id(self, package: VideoProductionPackage) -> str:
        return self._id("ir", f"{package.project_id}_{package.revision_id}")

    def _migrate_scenes(self, package: VideoProductionPackage, assets_by_id: Dict[str, ReferenceAsset]) -> List[SceneDescription]:
        scenes: List[SceneDescription] = []
        screenplay = package.screenplay
        if screenplay is None:
            return scenes

        for scene in screenplay.scenes:
            characters = [
                CharacterInstance(
                    instance_id=CharacterInstanceId(self._id("chr", str(chr_id))),
                    character_id=chr_id,
                    display_name=self._character_name(package, chr_id),
                    mesh=self._asset_ref(chr_id, "CHARACTER_REFERENCE", package, assets_by_id),
                )
                for chr_id in scene.character_ids
            ]
            # Project-wide props are made available in every IR scene; the
            # Director/set-dressing stage narrows per-scene placement later.
            props = [
                PropInstance(
                    instance_id=PropInstanceId(self._id("prp", str(p.prop_id))),
                    prop_id=p.prop_id,
                    asset=self._first_asset_ref(p.reference_asset_ids, "PROP", assets_by_id),
                    placement_hint="",
                )
                for p in package.props
            ]
            env = [
                EnvironmentInstance(
                    instance_id=EnvironmentInstanceId(self._id("env", str(loc.location_id))),
                    location_id=loc.location_id,
                    asset=self._first_asset_ref(loc.reference_asset_ids, "ENVIRONMENT", assets_by_id),
                    environment_style=loc.visual_description,
                )
                for loc in package.locations
                if str(loc.location_id) == str(scene.location_id)
            ]
            scenes.append(
                SceneDescription(
                    scene_id=SceneDescriptionId(self._id("scn", str(scene.scene_id))),
                    screenplay_scene_id=scene.scene_id,
                    characters=characters,
                    props=props,
                    environment=env,
                    light_rigs=[self._default_light_rig(str(scene.scene_id))],
                    action=scene.action_description,
                )
            )
        return scenes

    def _migrate_shots(self, package: VideoProductionPackage, assets_by_id: Dict[str, ReferenceAsset]) -> List[ShotExecutionIntent]:
        shots: List[ShotExecutionIntent] = []
        plan = package.cinematic_plan
        if plan is None:
            return shots

        character_ids_by_scene: Dict[str, List[str]] = {}
        if package.screenplay is not None:
            character_ids_by_scene = {
                str(scene.scene_id): [str(cid) for cid in scene.character_ids]
                for scene in package.screenplay.scenes
            }

        for shot in plan.graph.shots:
            camera = CameraTrack(
                track_id=CameraTrackId(self._id("cam", str(shot.shot_id))),
                shot_type=shot.shot_type,
                movement=shot.camera_movement,
                duration_seconds=shot.duration_seconds,
                transition_type=shot.transition_type,
                metadata={"framing_description": shot.framing_description},
            )
            dialogue_tracks: List[DialogueTrack] = []
            if shot.dialogue_line_ids:
                dialogue_tracks.append(
                    DialogueTrack(
                        dialogue_line_ids=list(shot.dialogue_line_ids),
                        audio_track_ids=[],
                        audio_asset_ids=[],
                    )
                )
            shots.append(
                ShotExecutionIntent(
                    intent_id=ShotExecutionIntentId(self._id("sht", str(shot.shot_id))),
                    shot_id=shot.shot_id,
                    scene_id=SceneDescriptionId(self._id("scn", str(shot.scene_id))),
                    order=shot.order,
                    characters=[
                        self._id("chr", cid)
                        for cid in character_ids_by_scene.get(str(shot.scene_id), [])
                    ],
                    camera=camera,
                    dialogue_tracks=dialogue_tracks,
                    duration_seconds=shot.duration_seconds,
                    render_profile_id=RenderProfileId(DEFAULT_RENDER_PROFILE_ID),
                    creative_prompt=shot.framing_description,
                )
            )
        return shots

    def _migrate_render_intents(
        self,
        scenes: List[SceneDescription],
        shots: List[ShotExecutionIntent],
        profile: RenderProfile,
    ) -> List[RenderIntent]:
        intents: List[RenderIntent] = []
        scene_ids = {str(s.scene_id) for s in scenes}
        for scene in scenes:
            scene_shots = [
                shot.intent_id
                for shot in shots
                if str(shot.scene_id) == str(scene.scene_id)
            ]
            intents.append(
                RenderIntent(
                    intent_id=RenderIntentId(self._id("ri", str(scene.scene_id))),
                    scene_id=scene.scene_id,
                    shot_execution_intent_ids=scene_shots,
                    profile=profile,
                )
            )
        return intents

    def _default_render_profile(self) -> RenderProfile:
        return RenderProfile(profile_id=RenderProfileId(DEFAULT_RENDER_PROFILE_ID))

    def _default_light_rig(self, scene_id: str) -> LightRig:
        return LightRig(rig_id=LightRigId(self._id("light", scene_id)))

    def _asset_ref(
        self,
        character_id: Any,
        role: str,
        package: VideoProductionPackage,
        assets_by_id: Dict[str, ReferenceAsset],
    ) -> Optional[AssetReference]:
        for bible in package.characters:
            if str(bible.character_id) == str(character_id) and bible.portrait_asset_ids:
                return self._first_asset_ref(bible.portrait_asset_ids, role, assets_by_id)
        return None

    @staticmethod
    def _first_asset_ref(
        asset_ids: List[Any],
        role: str,
        assets_by_id: Dict[str, ReferenceAsset],
    ) -> Optional[AssetReference]:
        for asset_id in asset_ids:
            asset = assets_by_id.get(str(asset_id))
            if asset is None:
                continue
            return AssetReference(
                asset_id=asset.asset_id,
                role=role,
                uri=f"asset://{asset.content_hash}",
                format=ProductionIrMigrator._media_to_format(asset.media_type),
                content_hash=asset.content_hash,
                derived=False,
                metadata={"mime_type": asset.mime_type, "license_state": asset.license_state.value},
            )
        return None

    @staticmethod
    def _media_to_format(media_type: MediaType) -> IrAssetFormat:
        mapping = {
            MediaType.IMAGE: IrAssetFormat.PNG,
            MediaType.VIDEO: IrAssetFormat.MP4,
            MediaType.AUDIO: IrAssetFormat.WAV,
            MediaType.DOCUMENT: IrAssetFormat.JSON,
        }
        return mapping.get(media_type, IrAssetFormat.UNKNOWN)

    def _character_name(self, package: VideoProductionPackage, character_id: Any) -> str:
        for bible in package.characters:
            if str(bible.character_id) == str(character_id):
                return bible.name
        return ""

    # -- component migrations (field-by-field mapping proof) ---------------
    @staticmethod
    def migrate_generation_mode_decision(decision: GenerationModeDecision) -> Dict[str, Any]:
        """Map a GenerationModeDecision onto engine-neutral IR semantics.

        The mode itself is DROPPED (never carried into the IR); only the
        advisory rationale is kept so the Director can trace why an intent
        was formed. The engine adapter decides actual execution.
        """
        return {
            "carried": False,
            "generation_mode": "NOT_CARRIED_INTO_IR",
            "advisory_reason_code": decision.reason_code.value if decision.reason_code else "",
            "advisory_rationale": decision.rationale,
        }

    @staticmethod
    def migrate_flow_generation_specification(spec: FlowGenerationSpecification) -> Dict[str, Any]:
        """Extract creative/reference value from a FlowGenerationSpecification.

        The provider-specific `generation_mode` and `model_capability_constraints`
        are DROPPED; the creative prompt text and reference hashes are kept.
        """
        return {
            "carried": True,
            "shot_id": str(spec.shot_id),
            "creative_prompt": spec.prompt.text if spec.prompt else "",
            "reference_hashes": sorted(set(spec.reference_hashes)),
            "generation_mode": "NOT_CARRIED_INTO_IR",
        }

    @staticmethod
    def migrate_generation_request(request: LegacyGenerationRequest) -> Dict[str, Any]:
        """Extract idempotency identity + parameters from a GenerationRequest.

        `generation_mode` and `provider` are DROPPED; the IR is engine-neutral.
        """
        return {
            "carried": True,
            "request_id": str(request.request_id),
            "project_id": str(request.project_id),
            "revision_id": str(request.revision_id),
            "shot_id": str(request.shot_id),
            "prompt_hash": request.prompt_hash,
            "reference_hashes": sorted(set(request.reference_hashes)),
            "parameters": request.parameters,
            "generation_mode": "NOT_CARRIED_INTO_IR",
            "provider": "NOT_CARRIED_INTO_IR",
        }

    @classmethod
    def mapping_table(cls) -> List[Dict[str, str]]:
        """Canonical field-by-field mapping table (used for Phase 1 evidence)."""
        return [
            {"legacy": "VideoProductionPackage.project_id", "ir": "ProductionIrDocument.project_id", "action": "PRESERVE"},
            {"legacy": "VideoProductionPackage.revision_id", "ir": "ProductionIrDocument.revision_id", "action": "PRESERVE"},
            {"legacy": "VideoProductionPackage.content_hash()", "ir": "ProductionIrDocument.source_package_hash", "action": "PRESERVE"},
            {"legacy": "VideoProductionPackage.provenance", "ir": "ProductionIrDocument.provenance", "action": "PRESERVE"},
            {"legacy": "VideoProductionPackage.approvals(.locked/target_hash)", "ir": "ProductionIrDocument.locked / approval_state_ref", "action": "PRESERVE"},
            {"legacy": "Screenplay.scenes[].scene_id / order", "ir": "SceneDescription.scene_id / screenplay_scene_id + shot order", "action": "PRESERVE"},
            {"legacy": "CharacterBible.character_id / portrait_asset_ids", "ir": "CharacterInstance.instance_id(character_id) / mesh(asset ref)", "action": "PRESERVE"},
            {"legacy": "LocationBible.location_id / reference_asset_ids", "ir": "EnvironmentInstance.instance_id / asset", "action": "PRESERVE"},
            {"legacy": "PropBible.prop_id / reference_asset_ids", "ir": "PropInstance.instance_id / asset", "action": "PRESERVE"},
            {"legacy": "Shot.shot_id / order / scene_id", "ir": "ShotExecutionIntent.intent_id / order / scene_id", "action": "PRESERVE"},
            {"legacy": "Shot.shot_type / camera_movement / duration_seconds / transition_type", "ir": "CameraTrack(shoot_type/movement/duration/transition)", "action": "MIGRATE"},
            {"legacy": "Shot.dialogue_line_ids", "ir": "DialogueTrack.dialogue_line_ids", "action": "MIGRATE"},
            {"legacy": "Shot.framing_description", "ir": "ShotExecutionIntent.creative_prompt", "action": "SEPARATE (creative value)"},
            {"legacy": "Shot.generation_mode", "ir": "(absent)", "action": "DROP"},
            {"legacy": "GenerationModeDecision.preferred_mode/fallbacks", "ir": "(absent; advisory rationale only)", "action": "DROP"},
            {"legacy": "FlowGenerationSpecification.generation_mode / model_capability_constraints", "ir": "(absent)", "action": "DROP"},
            {"legacy": "FlowGenerationSpecification.prompt.text / reference_hashes", "ir": "ShotExecutionIntent.creative_prompt / AssetReference hashes", "action": "MIGRATE"},
            {"legacy": "GenerationRequest.provider / generation_mode", "ir": "(absent)", "action": "DROP"},
            {"legacy": "GenerationRequest.parameters / prompt_hash", "ir": "metadata (advisory)", "action": "MIGRATE"},
        ]


__all__ = [
    "ProductionIrMigrator",
]
