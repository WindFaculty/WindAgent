"""
Phase 8 director fixtures: three golden VideoProductionPackage fixtures
(short cartoon, two-character dialogue, multi-scene drama) plus a pinned,
deterministic planner output for each.

The pinned planner output is DERIVED from the package content deterministically
(same package -> same JSON), so running `VideoDirectorService` twice yields the
same plan hash. A `DeterministicDirectorModel` port returns these pinned JSON
answers — the fake never performs a network call.
"""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.character import CharacterBible
from windagent_core.domain.video_production.enums import (
    AssetSourceType,
    CameraMovement,
    CharacterRole,
    LicenseState,
    MediaType,
    ScreenplayStatus,
    ShotType,
    TimeOfDay,
    TransitionType,
)
# Legacy-shaped pinned planner output keeps `generation_mode` keys ONLY as
# backward-compatible extra fields (ShotPlan/Shot tolerate them via
# extra="allow"); the canonical runtime never reads them (legacy_v1/SUNSET.md).
from windagent_core.domain.video_production.legacy_v1 import GenerationMode
from windagent_core.domain.video_production.ids import (
    CharacterId,
    CreativeBriefId,
    DialogueLineId,
    LocationId,
    ProductionRevisionId,
    ReferenceAssetId,
    SceneId,
    ScreenplayId,
    StoryConceptId,
    VideoProjectId,
)
from windagent_core.domain.video_production.location import LocationBible
from windagent_core.domain.video_production.package import (
    PackageProvenance,
    VideoProductionPackage,
)
from windagent_core.domain.video_production.scene import Scene
from windagent_core.domain.video_production.screenplay import (
    CreativeBrief,
    DialogueLine,
    Screenplay,
    StoryConcept,
)
from windagent_core.domain.video_production.shot import Shot
from windagent_intelligence.video.director.duration import DurationBudgetPolicy
from windagent_intelligence.video.ports import (
    ModelCompletionRequest,
    ModelCompletionResult,
)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _asset(asset_id: str, seed: str, location_id: str = "") -> ReferenceAsset:
    return ReferenceAsset(
        asset_id=ReferenceAssetId(asset_id),
        content_hash=sha256_hex(f"director-fixture::{seed}"),
        media_type=MediaType.IMAGE,
        mime_type="image/png",
        size_bytes=1024,
        source_type=AssetSourceType.GENERATED,
        license_state=LicenseState.LICENSED,
        metadata={"usage": "identity/location reference", "seed": seed, "location_id": location_id},
    )


# ---------------------------------------------------------------------------
# Fixture 1: short cartoon (1 scene, 1 character, 1 location, 2 dialogue lines)
# ---------------------------------------------------------------------------
def build_short_cartoon_package() -> VideoProductionPackage:
    project_id = "vp_phase8_short_cartoon"
    revision_id = "rev_phase8_short_cartoon_1"
    char_id = CharacterId("chr_doudou")
    loc_id = LocationId("loc_forest")
    scene_id = SceneId("scn_01")
    dlg1 = DialogueLineId("dlg_short_01")
    dlg2 = DialogueLineId("dlg_short_02")
    asset_char = _asset("ast_doudou", "doudou-portrait")
    asset_loc = _asset("ast_forest", "forest-reference", str(loc_id))

    scenes = [
        Scene(
            scene_id=scene_id,
            order=1,
            title="The Lost Fox",
            location_id=loc_id,
            character_ids=[char_id],
            dialogue_line_ids=[dlg1, dlg2],
            action_description="Doudou the fox wanders through the forest and finds a way home.",
            time_of_day=TimeOfDay.DAY,
        )
    ]
    dialogue = [
        DialogueLine(dialogue_id=dlg1, scene_id=scene_id, character_id=char_id, order=1,
                     text="I am lost! Where is my den?"),
        DialogueLine(dialogue_id=dlg2, scene_id=scene_id, character_id=char_id, order=2,
                     text="There it is! Home at last."),
    ]
    return _package(
        project_id=project_id,
        revision_id=revision_id,
        title="Mùa hè của Doudou",
        target_duration_seconds=20,
        aspect_ratio="16:9",
        scenes=scenes,
        dialogue=dialogue,
        characters=[CharacterBible(character_id=char_id, name="Doudou", role=CharacterRole.LEAD,
                                   portrait_asset_ids=[ReferenceAssetId(str(asset_char.asset_id))])],
        locations=[LocationBible(location_id=loc_id, name="Forest",
                                 reference_asset_ids=[ReferenceAssetId(str(asset_loc.asset_id))])],
        assets=[asset_char, asset_loc],
    )


# ---------------------------------------------------------------------------
# Fixture 2: two-character dialogue (1 scene, dialogue-heavy)
# ---------------------------------------------------------------------------
def build_two_character_dialogue_package() -> VideoProductionPackage:
    project_id = "vp_phase8_two_character_dialogue"
    revision_id = "rev_phase8_two_character_dialogue_1"
    char_a = CharacterId("chr_minh")
    char_b = CharacterId("chr_linh")
    loc_id = LocationId("loc_cafe")
    scene_id = SceneId("scn_01")
    dialogue_ids = [DialogueLineId(f"dlg_tcd_{i:02d}") for i in range(1, 5)]
    asset_a = _asset("ast_minh", "minh-portrait")
    asset_b = _asset("ast_linh", "linh-portrait")
    asset_loc = _asset("ast_cafe", "cafe-reference", str(loc_id))

    scenes = [
        Scene(
            scene_id=scene_id,
            order=1,
            title="Cà phê đêm",
            location_id=loc_id,
            character_ids=[char_a, char_b],
            dialogue_line_ids=list(dialogue_ids),
            action_description="Two old friends talk over coffee late at night.",
            time_of_day=TimeOfDay.NIGHT,
        )
    ]
    dialogue = [
        DialogueLine(dialogue_id=dialogue_ids[0], scene_id=scene_id, character_id=char_a, order=1,
                     text="You are really leaving tomorrow?"),
        DialogueLine(dialogue_id=dialogue_ids[1], scene_id=scene_id, character_id=char_b, order=2,
                     text="The train leaves at dawn. I have to go."),
        DialogueLine(dialogue_id=dialogue_ids[2], scene_id=scene_id, character_id=char_a, order=3,
                     text="Stay. This city needs you, and I need you too."),
        DialogueLine(dialogue_id=dialogue_ids[3], scene_id=scene_id, character_id=char_b, order=4,
                     text="Some part of me will always stay right here."),
    ]
    return _package(
        project_id=project_id,
        revision_id=revision_id,
        title="Cà phê đêm",
        target_duration_seconds=30,
        aspect_ratio="16:9",
        scenes=scenes,
        dialogue=dialogue,
        characters=[
            CharacterBible(character_id=char_a, name="Minh", role=CharacterRole.LEAD,
                           portrait_asset_ids=[ReferenceAssetId(str(asset_a.asset_id))]),
            CharacterBible(character_id=char_b, name="Linh", role=CharacterRole.LEAD,
                           portrait_asset_ids=[ReferenceAssetId(str(asset_b.asset_id))]),
        ],
        locations=[LocationBible(location_id=loc_id, name="Night Cafe",
                                 reference_asset_ids=[ReferenceAssetId(str(asset_loc.asset_id))])],
        assets=[asset_a, asset_b, asset_loc],
    )


# ---------------------------------------------------------------------------
# Fixture 3: multi-scene drama (3 scenes, fast paced)
# ---------------------------------------------------------------------------
def build_multi_scene_drama_package() -> VideoProductionPackage:
    project_id = "vp_phase8_multi_scene_drama"
    revision_id = "rev_phase8_multi_scene_drama_1"
    char_id = CharacterId("chr_keeper")
    loc_storm = LocationId("loc_storm")
    loc_tower = LocationId("loc_tower")
    scene1, scene2, scene3 = SceneId("scn_01"), SceneId("scn_02"), SceneId("scn_03")
    dlg1 = DialogueLineId("dlg_drama_01")
    dlg2 = DialogueLineId("dlg_drama_02")
    dlg3 = DialogueLineId("dlg_drama_03")
    asset_char = _asset("ast_keeper", "keeper-portrait")
    asset_storm = _asset("ast_storm", "storm-reference", str(loc_storm))
    asset_tower = _asset("ast_tower", "tower-reference", str(loc_tower))

    scenes = [
        Scene(scene_id=scene1, order=1, title="The Lighthouse", location_id=loc_tower,
              character_ids=[char_id], dialogue_line_ids=[dlg1],
              action_description="The keeper notices the main lamp has gone dark.",
              time_of_day=TimeOfDay.NIGHT),
        Scene(scene_id=scene2, order=2, title="Into the Storm", location_id=loc_storm,
              character_ids=[char_id], dialogue_line_ids=[dlg2],
              action_description="He fights through wind and rain toward the tower stairs.",
              time_of_day=TimeOfDay.NIGHT),
        Scene(scene_id=scene3, order=3, title="Reignite", location_id=loc_tower,
              character_ids=[char_id], dialogue_line_ids=[dlg3],
              action_description="He relights the lamp and saves the fishing boats.",
              time_of_day=TimeOfDay.NIGHT),
    ]
    dialogue = [
        DialogueLine(dialogue_id=dlg1, scene_id=scene1, character_id=char_id, order=1,
                     text="The main lamp is out!"),
        DialogueLine(dialogue_id=dlg2, scene_id=scene2, character_id=char_id, order=2,
                     text="Hold on, old lighthouse!"),
        DialogueLine(dialogue_id=dlg3, scene_id=scene3, character_id=char_id, order=3,
                     text="Light the way home."),
    ]
    return _package(
        project_id=project_id,
        revision_id=revision_id,
        title="Ngọn đèn cuối cùng",
        target_duration_seconds=30,
        aspect_ratio="21:9",
        scenes=scenes,
        dialogue=dialogue,
        characters=[CharacterBible(character_id=char_id, name="Keeper", role=CharacterRole.LEAD,
                                   portrait_asset_ids=[ReferenceAssetId(str(asset_char.asset_id))])],
        locations=[
            LocationBible(location_id=loc_tower, name="Lighthouse Tower",
                          reference_asset_ids=[ReferenceAssetId(str(asset_tower.asset_id))]),
            LocationBible(location_id=loc_storm, name="Storm Coast",
                          reference_asset_ids=[ReferenceAssetId(str(asset_storm.asset_id))]),
        ],
        assets=[asset_char, asset_storm, asset_tower],
    )


def _package(
    *,
    project_id: str,
    revision_id: str,
    title: str,
    target_duration_seconds: int,
    aspect_ratio: str,
    scenes: List[Scene],
    dialogue: List[DialogueLine],
    characters: List[CharacterBible],
    locations: List[LocationBible],
    assets: List[ReferenceAsset],
) -> VideoProductionPackage:
    return VideoProductionPackage(
        schema_version="1.0.0",
        project_id=VideoProjectId(project_id),
        revision_id=ProductionRevisionId(revision_id),
        creative_brief=CreativeBrief(
            brief_id=CreativeBriefId(f"brf_{project_id}"),
            title=title,
            target_duration_seconds=target_duration_seconds,
            aspect_ratio=aspect_ratio,
            production_constraints={"style": "director-fixture"},
        ),
        story_concept=StoryConcept(
            concept_id=StoryConceptId(f"cnc_{project_id}"),
            title=title,
            premise="Director fixture premise.",
            synopsis="Director fixture synopsis.",
        ),
        screenplay=Screenplay(
            screenplay_id=ScreenplayId(f"scr_{project_id}"),
            title=title,
            status=ScreenplayStatus.LOCKED,
            scenes=scenes,
        ),
        characters=characters,
        locations=locations,
        dialogue=dialogue,
        assets=assets,
        provenance=PackageProvenance(created_by="phase8-director-fixture"),
    )


# ---------------------------------------------------------------------------
# Deterministic pinned planner output
# ---------------------------------------------------------------------------
def build_pinned_planner_output(package: VideoProductionPackage) -> dict:
    """Deterministically derive a PlannerOutput proposal from a package.

    The proposed shots are chosen so the resulting plan is VALID for the
    happy-path fixtures: every scene gets an establishing shot, every dialogue
    line is bound to exactly one shot with a duration >= its reading time, and
    durations are normalized to land inside the target tolerance.
    """
    policy = DurationBudgetPolicy()
    scenes = package.screenplay.scenes if package.screenplay else []
    dialogue_by_scene: Dict[str, List[DialogueLine]] = {}
    for d in package.dialogue:
        dialogue_by_scene.setdefault(str(d.scene_id), []).append(d)

    objectives: List[dict] = []
    shots: List[dict] = []
    for scene in sorted(scenes, key=lambda s: (s.order, str(s.scene_id))):
        scene_dialogue = sorted(
            dialogue_by_scene.get(str(scene.scene_id), []), key=lambda d: d.order
        )
        objectives.append(
            {
                "scene_id": str(scene.scene_id),
                "objective": f"Advance the story in {scene.title or scene.scene_id}",
                "beats": [
                    {"beat_order": i + 1, "objective": d.text[:60], "source": f"dialogue:{d.dialogue_id}"}
                    for i, d in enumerate(scene_dialogue)
                ],
                "required_story_facts": [],
            }
        )
        # Establishing shot covering the scene geography.
        loc_assets = [
            str(a.asset_id)
            for a in package.assets
            if a.metadata.get("location_id") == str(scene.location_id)
        ]
        char_assets = _scene_character_assets(package, scene.character_ids)
        shots.append(
            {
                "scene_id": str(scene.scene_id),
                "order": 1,
                "shot_type": ShotType.ESTABLISHING.value,
                "camera_movement": CameraMovement.STATIC.value,
                "camera_angle": "eye-level",
                "duration_seconds": 3.0,
                "framing_description": f"Wide establishing view of {scene.title or 'the scene'}",
                "transition_type": TransitionType.CUT.value,
                "generation_mode": GenerationMode.TEXT_TO_VIDEO.value,
                "dialogue_line_ids": [],
                "reference_asset_ids": loc_assets,
                "narrative_purpose": "establish location and geography",
            }
        )
        # One shot per dialogue line.
        for idx, d in enumerate(scene_dialogue):
            dialogue_duration = policy.dialogue_duration(d.text)
            shot_type = (
                ShotType.CLOSE_UP.value if idx % 2 == 0 else ShotType.MEDIUM.value
            )
            shots.append(
                {
                    "scene_id": str(scene.scene_id),
                    "order": idx + 2,
                    "shot_type": shot_type,
                    "camera_movement": CameraMovement.STATIC.value,
                    "camera_angle": "eye-level",
                    "duration_seconds": max(dialogue_duration, 2.0),
                    "framing_description": f"Cover {d.text[:40]}",
                    "transition_type": TransitionType.CUT.value,
                    "generation_mode": GenerationMode.IMAGE_TO_VIDEO.value,
                    "dialogue_line_ids": [str(d.dialogue_id)],
                    "reference_asset_ids": char_assets + loc_assets,
                    "narrative_purpose": f"deliver dialogue line {d.dialogue_id}",
                }
            )

    _normalize_durations_to_target(shots, package, policy)
    return {
        "schema_version": "1.0.0",
        "planner_version": "1.0.0",
        "scene_objectives": objectives,
        "shots": shots,
    }


def _scene_character_assets(package: VideoProductionPackage, character_ids) -> List[str]:
    assets: List[str] = []
    for c in package.characters:
        if str(c.character_id) in {str(i) for i in character_ids}:
            assets.extend(str(a) for a in c.portrait_asset_ids)
    return assets


def _normalize_durations_to_target(
    shots: List[dict], package: VideoProductionPackage, policy: DurationBudgetPolicy
) -> None:
    """Scale non-dialogue shot durations so the timeline lands in-budget."""
    target = package.creative_brief.target_duration_seconds if package.creative_brief else 0
    if target <= 0:
        return
    # Budget check uses raw durations + handles + transitions; solve for the
    # establishing shot duration such that the full timeline fits the target.
    dialogue_shots = [s for s in shots if s["dialogue_line_ids"]]
    establishing = [s for s in shots if not s["dialogue_line_ids"]]
    if not establishing:
        return
    fixed_body = sum(s["duration_seconds"] for s in dialogue_shots)
    fixed_count = len(shots)
    transitions = (fixed_count - 1) * policy.transition_seconds_for(TransitionType.CUT)
    handles = fixed_count * 2 * policy.handle_seconds
    per_establishing = (target - fixed_body - handles - transitions) / len(establishing)
    per_establishing = max(per_establishing, 1.0)
    for s in establishing:
        s["duration_seconds"] = policy.round_to_frame(per_establishing)


def timeline_seconds(shots: List[dict], policy: DurationBudgetPolicy) -> float:
    """Mirror of the validator's timeline math for assertion helpers."""
    return policy.total_timeline_seconds(
        [Shot(**{k: v for k, v in s.items()}) for s in shots]
    )


class DeterministicDirectorModel:
    """Fake PreproductionModelPort returning pinned planner JSON.

    Records every capability call so tests can assert the Director never calls
    a media-generation provider (only the planning capability).
    """

    def __init__(self, plan_json: dict) -> None:
        self._plan_json = plan_json
        self.calls: List[str] = []

    async def complete(self, request: ModelCompletionRequest) -> ModelCompletionResult:
        self.calls.append(request.capability)
        return ModelCompletionResult(
            capability=request.capability,
            content=json.dumps(self._plan_json, ensure_ascii=False),
            provider="deterministic-director-fake",
        )


ALL_FIXTURES = {
    "fixture_short_cartoon": build_short_cartoon_package,
    "fixture_two_character_dialogue": build_two_character_dialogue_package,
    "fixture_multi_scene_drama": build_multi_scene_drama_package,
}

__all__ = [
    "sha256_hex",
    "build_short_cartoon_package",
    "build_two_character_dialogue_package",
    "build_multi_scene_drama_package",
    "build_pinned_planner_output",
    "timeline_seconds",
    "DeterministicDirectorModel",
    "ALL_FIXTURES",
]
