"""B1 screenplay: format validity, attribution, coverage, duration, V2 adapter."""

from __future__ import annotations

from windagent_core.domain.story.ids import (
    BeatId,
    DialogueLineId,
    DraftSceneId,
    OutlineSceneId,
    ScreenplayDraftId,
    StoryCharacterId,
    StoryLocationId,
)
from windagent_core.domain.story.outline import Beat, BeatSheet, EpisodeOutline, OutlineScene
from windagent_core.domain.story.screenplay import (
    DraftDialogueLine,
    DraftScene,
    ScreenplayDraft,
    from_video_screenplay,
    validate_screenplay_draft,
)
from windagent_core.domain.story.ids import BeatSheetId, EpisodeOutlineId
from windagent_core.domain.video_production.screenplay import (
    DialogueLine as VideoDialogueLine,
    Screenplay as VideoScreenplay,
)
from windagent_core.domain.video_production.ids import (
    CharacterId as VideoCharacterId,
    DialogueLineId as VideoDialogueLineId,
    LocationId as VideoLocationId,
    SceneId as VideoSceneId,
    ScreenplayId as VideoScreenplayId,
)

RABBIT = StoryCharacterId("ch_rabbit")
KITE = StoryCharacterId("ch_kite")
FIELD = StoryLocationId("loc_field")


def _scenes() -> list:
    s1 = DraftScene(
        scene_id=DraftSceneId("dscn_1"), order=1, outline_scene_id=OutlineSceneId("s1"),
        location_id=FIELD, character_ids=[RABBIT],
        action_description="Thỏ con nhặt cánh diều giấy bên bờ sông.",
        dialogue=[
            DraftDialogueLine(
                dialogue_id=DialogueLineId("dl_1"), scene_id=DraftSceneId("dscn_1"),
                character_id=RABBIT, order=1, text="Ồ, cánh diều đẹp quá!",
            )
        ],
        estimated_seconds=40, source_beat_ids=[BeatId("b1")],
    )
    s2 = DraftScene(
        scene_id=DraftSceneId("dscn_2"), order=2, outline_scene_id=OutlineSceneId("s2"),
        location_id=FIELD, character_ids=[RABBIT, KITE],
        action_description="Thỏ và diều cùng tập thả trên cánh đồng.",
        dialogue=[
            DraftDialogueLine(
                dialogue_id=DialogueLineId("dl_2"), scene_id=DraftSceneId("dscn_2"),
                character_id=KITE, order=1, text="Nắm chặt dây diều nhé!",
            ),
            DraftDialogueLine(
                dialogue_id=DialogueLineId("dl_3"), scene_id=DraftSceneId("dscn_2"),
                character_id=RABBIT, order=2, text="Mình sẽ cố gắng!",
            ),
        ],
        estimated_seconds=80, source_beat_ids=[BeatId("b2")],
    )
    s3 = DraftScene(
        scene_id=DraftSceneId("dscn_3"), order=3, outline_scene_id=OutlineSceneId("s3"),
        location_id=FIELD, character_ids=[RABBIT, KITE],
        action_description="Cơn gió lớn thổi, cánh diều chao đảo.",
        dialogue=[
            DraftDialogueLine(
                dialogue_id=DialogueLineId("dl_4"), scene_id=DraftSceneId("dscn_3"),
                character_id=RABBIT, order=1, text="Ôi, gió to quá!",
            )
        ],
        estimated_seconds=60, source_beat_ids=[BeatId("b3")],
    )
    s4 = DraftScene(
        scene_id=DraftSceneId("dscn_4"), order=4, outline_scene_id=OutlineSceneId("s4"),
        location_id=FIELD, character_ids=[RABBIT, KITE],
        action_description="Cánh diều bay cao vút, thỏ con vui sướng.",
        estimated_seconds=60, source_beat_ids=[BeatId("b4")],
    )
    return [s1, s2, s3, s4]


def _draft() -> ScreenplayDraft:
    return ScreenplayDraft(
        draft_id=ScreenplayDraftId.generate("draft"),
        title="Con thỏ và cánh diều",
        target_duration_seconds=240,
        scenes=_scenes(),
    )


def _beat_sheet() -> BeatSheet:
    return BeatSheet(
        beat_sheet_id=BeatSheetId.generate("bs"),
        title="Con thỏ và cánh diều",
        total_target_seconds=240,
        beats=[
            Beat(beat_id=BeatId(f"b{i}"), order=i, role="rising", description=f"Beat {i}", target_seconds=60)
            for i in range(1, 5)
        ],
    )


def _outline() -> EpisodeOutline:
    return EpisodeOutline(
        outline_id=EpisodeOutlineId.generate("ol"),
        title="Con thỏ và cánh diều",
        target_duration_seconds=240,
        scenes=[
            OutlineScene(scene_id=OutlineSceneId(f"s{i}"), order=i, intent=f"Scene {i}",
                         location_id=FIELD, character_ids=[RABBIT, KITE], estimated_seconds=60)
            for i in range(1, 5)
        ],
    )


def test_valid_draft_passes_all_dimensions():
    report = validate_screenplay_draft(_draft(), beat_sheet=_beat_sheet(), outline=_outline())
    assert report.is_pass(), report.summary()


def test_dialogue_attribution_blocks():
    draft = _draft().model_copy(update={
        "scenes": [
            s.model_copy(update={"character_ids": [RABBIT]}) if s.scene_id == DraftSceneId("dscn_2") else s
            for s in _draft().scenes
        ]
    })
    report = validate_screenplay_draft(draft)
    assert any(i.code == "DIALOGUE_ATTRIBUTION" for i in report.issues)


def test_dialogue_scene_binding_stability():
    draft = _draft().model_copy(update={
        "scenes": [
            s.model_copy(update={
                "dialogue": [l.model_copy(update={"scene_id": DraftSceneId("other")}) for l in s.dialogue]
            }) for s in _draft().scenes
        ]
    })
    report = validate_screenplay_draft(draft)
    assert any(i.code == "ID_STABILITY" for i in report.issues)


def test_empty_dialogue_text_blocks():
    draft = _draft().model_copy(update={
        "scenes": [
            s.model_copy(update={
                "dialogue": [l.model_copy(update={"text": "   "}) for l in s.dialogue]
            }) for s in _draft().scenes
        ]
    })
    report = validate_screenplay_draft(draft)
    assert any(i.code == "DIALOGUE_EMPTY" for i in report.issues)


def test_beat_coverage_blocks():
    draft = _draft().model_copy(update={
        "scenes": [s.model_copy(update={"source_beat_ids": []}) for s in _draft().scenes]
    })
    report = validate_screenplay_draft(draft, beat_sheet=_beat_sheet())
    assert any(i.code == "BEAT_COVERAGE" for i in report.issues)


def test_duration_bound_blocks():
    draft = _draft().model_copy(update={
        "scenes": [s.model_copy(update={"estimated_seconds": s.estimated_seconds * 4}) for s in _draft().scenes]
    })
    report = validate_screenplay_draft(draft)
    assert any(i.code == "DURATION_BOUND" for i in report.issues)


def test_scene_order_stability():
    draft = _draft().model_copy(update={
        "scenes": [s.model_copy(update={"order": 9 - s.order}) for s in _draft().scenes]
    })
    report = validate_screenplay_draft(draft)
    assert any(i.code == "ORDER_SEQUENCE" for i in report.issues)


def test_unknown_outline_scene_blocks():
    draft = _draft().model_copy(update={
        "scenes": [s.model_copy(update={"outline_scene_id": OutlineSceneId("ghost")}) for s in _draft().scenes]
    })
    report = validate_screenplay_draft(draft, outline=_outline())
    assert any(i.code == "REF_MISSING" for i in report.issues)


def test_from_video_screenplay_reports_loss():
    video = VideoScreenplay(
        screenplay_id=VideoScreenplayId("vsp_1"),
        title="Con thỏ và cánh diều",
        logline="Một chú thỏ học cách thả diều.",
        scenes=[
            __import__("windagent_core.domain.video_production.scene", fromlist=["Scene"]).Scene(
                scene_id=VideoSceneId("vscn_1"), order=1, location_id=VideoLocationId("vloc_1"),
                character_ids=[VideoCharacterId("vch_1")],
                action_description="Thỏ nhặt diều.",
            )
        ],
    )
    lines = [
        VideoDialogueLine(
            dialogue_id=VideoDialogueLineId("vdl_1"), scene_id=VideoSceneId("vscn_1"),
            character_id=VideoCharacterId("vch_1"), order=1, text="Ồ, cánh diều!",
        )
    ]
    draft, loss = from_video_screenplay(
        video, dialogue_lines=lines,
        character_id_mapping={"vch_1": "ch_rabbit"},
        location_id_mapping={"vloc_1": "loc_field"},
    )
    assert draft.title == "Con thỏ và cánh diều"
    assert len(draft.scenes) == 1
    assert draft.scenes[0].dialogue[0].text == "Ồ, cánh diều!"
    assert draft.scenes[0].character_ids == [StoryCharacterId("ch_rabbit")]
    assert loss["warnings"], "conversion must report assumptions"
    assert "estimated_seconds" in loss["assumed"]
