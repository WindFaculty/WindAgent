"""B1 outline/beat: duration math, causality, coverage, boundaries."""

from __future__ import annotations

from windagent_core.domain.story.ids import (
    BeatId,
    BeatSheetId,
    EpisodeOutlineId,
    OutlineSceneId,
    StoryCharacterId,
    StoryLocationId,
)
from windagent_core.domain.story.outline import (
    MAX_EPISODE_SECONDS,
    MIN_EPISODE_SECONDS,
    Beat,
    BeatSheet,
    EpisodeOutline,
    OutlineScene,
    duration_issues,
    estimate_scene_seconds,
    estimate_text_seconds,
    validate_beat_sheet,
    validate_episode_outline,
)

RABBIT = StoryCharacterId("ch_rabbit")
KITE = StoryCharacterId("ch_kite")
FIELD = StoryLocationId("loc_field")


def _beat_sheet() -> BeatSheet:
    return BeatSheet(
        beat_sheet_id=BeatSheetId.generate("bs"),
        title="Con thỏ và cánh diều",
        total_target_seconds=240,
        beats=[
            Beat(beat_id=BeatId("b1"), order=1, role="hook", description="Thỏ nhặt cánh diều rơi", target_seconds=40, character_ids=[RABBIT], location_id=FIELD),
            Beat(beat_id=BeatId("b2"), order=2, role="rising", description="Thỏ tập thả diều và gặp trở ngại", target_seconds=80, character_ids=[RABBIT, KITE], location_id=FIELD),
            Beat(beat_id=BeatId("b3"), order=3, role="climax", description="Cơn gió lớn, diều sắp bay mất", target_seconds=60, character_ids=[RABBIT, KITE], location_id=FIELD),
            Beat(beat_id=BeatId("b4"), order=4, role="resolution", description="Diều bay cao, thỏ vui", target_seconds=60, character_ids=[RABBIT, KITE], location_id=FIELD),
        ],
    )


def _outline() -> EpisodeOutline:
    return EpisodeOutline(
        outline_id=EpisodeOutlineId.generate("ol"),
        title="Con thỏ và cánh diều",
        target_duration_seconds=240,
        scenes=[
            OutlineScene(scene_id=OutlineSceneId("s1"), order=1, intent="Giới thiệu thỏ và cánh diều", location_id=FIELD, character_ids=[RABBIT], estimated_seconds=40, beat_refs=[BeatId("b1")]),
            OutlineScene(scene_id=OutlineSceneId("s2"), order=2, intent="Thỏ tập thả diều", location_id=FIELD, character_ids=[RABBIT, KITE], estimated_seconds=80, beat_refs=[BeatId("b2")]),
            OutlineScene(scene_id=OutlineSceneId("s3"), order=3, intent="Cơn gió lớn", location_id=FIELD, character_ids=[RABBIT, KITE], estimated_seconds=60, beat_refs=[BeatId("b3")]),
            OutlineScene(scene_id=OutlineSceneId("s4"), order=4, intent="Diều bay cao", location_id=FIELD, character_ids=[RABBIT, KITE], estimated_seconds=60, beat_refs=[BeatId("b4")]),
        ],
    )


def test_duration_formula_deterministic():
    assert estimate_text_seconds("X" * 70) == 20  # 70 / 3.5
    assert estimate_text_seconds("") == 0
    a = estimate_scene_seconds(action_description="Mô tả ngắn", dialogue_texts=["Chào bạn!", "Cánh diều đẹp quá!"])
    assert a == estimate_scene_seconds(action_description="Mô tả ngắn", dialogue_texts=["Chào bạn!", "Cánh diều đẹp quá!"])
    assert a >= 1


def test_duration_issues_outside_tolerance():
    findings = duration_issues(total_seconds=200, target_seconds=240, tolerance_seconds=15)
    assert findings and findings[0]["code"] == "DURATION_SUM"
    assert duration_issues(total_seconds=235, target_seconds=240, tolerance_seconds=15) == []
    bounds = duration_issues(total_seconds=120, target_seconds=240, tolerance_seconds=15, enforce_bounds=True)
    assert any(f["code"] == "DURATION_BOUND" for f in bounds)


def test_beat_sheet_validation_passes():
    report = validate_beat_sheet(_beat_sheet())
    assert report.is_pass(), report.summary()


def test_beat_order_must_start_at_one():
    beat_sheet = _beat_sheet().model_copy(update={
        "beats": [b.model_copy(update={"order": b.order + 1}) for b in _beat_sheet().beats]
    })
    report = validate_beat_sheet(beat_sheet)
    assert any(i.code == "ORDER_SEQUENCE" for i in report.issues)


def test_beat_duration_sum_mismatch_blocks():
    beat_sheet = _beat_sheet().model_copy(update={
        "beats": [b.model_copy(update={"target_seconds": b.target_seconds + 100}) for b in _beat_sheet().beats]
    })
    report = validate_beat_sheet(beat_sheet)
    assert any(i.code == "DURATION_SUM" for i in report.issues)


def test_outline_passes_and_fits_bounds():
    report = validate_episode_outline(_outline())
    assert report.is_pass(), report.summary()
    assert MIN_EPISODE_SECONDS <= _outline().total_estimated_seconds <= MAX_EPISODE_SECONDS


def test_outline_duration_outside_180_300_blocks():
    outline = _outline().model_copy(update={
        "scenes": [s.model_copy(update={"estimated_seconds": s.estimated_seconds * 3}) for s in _outline().scenes]
    })
    report = validate_episode_outline(outline)
    assert any(i.code == "DURATION_BOUND" for i in report.issues)


def test_orphan_beat_warns():
    outline = _outline().model_copy(update={
        "scenes": [s.model_copy(update={"beat_refs": []}) for s in _outline().scenes]
    })
    report = validate_episode_outline(outline, beat_sheet=_beat_sheet())
    assert any(i.code == "BEAT_ORPHAN" for i in report.issues)


def test_causal_order_violation_warns():
    outline = _outline().model_copy(update={
        "scenes": [s.model_copy(update={"beat_refs": [BeatId("b4")]}) if s.scene_id == OutlineSceneId("s1") else s for s in _outline().scenes]
    })
    report = validate_episode_outline(outline, beat_sheet=_beat_sheet())
    assert any(i.code == "CAUSAL_ORDER" for i in report.issues)


def test_unknown_location_reference_blocks():
    from windagent_core.domain.story.bibles import RecurringLocation, WorldBible
    from windagent_core.domain.story.ids import WorldBibleId

    world = WorldBible(
        world_id=WorldBibleId.generate("w"),
        setting="Làng ven sông",
        recurring_locations=[RecurringLocation(location_id=StoryLocationId("loc_river"), name="Dòng sông")],
    )
    report = validate_episode_outline(_outline(), world=world)
    assert any(i.code == "REF_MISSING" for i in report.issues)


def test_scene_id_uniqueness_blocks():
    outline = _outline().model_copy(update={
        "scenes": [s.model_copy(update={"scene_id": OutlineSceneId("dup")}) for s in _outline().scenes]
    })
    report = validate_episode_outline(outline)
    assert any(i.code == "ID_UNIQUE" for i in report.issues)
