"""Plan B B5 unit tests: Beat/Outline generation services + handlers."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.verification.produce_b5_evidence import (
    GOLDEN_BEAT_SHEET,
    GOLDEN_CANON,
    GOLDEN_EPISODE_OUTLINE,
    GOLDEN_STORY,
    GOLDEN_WORLD,
)

from windagent_core.domain.story.outline import BeatSheet
from windagent_intelligence.story.outline.service import (
    BeatGenerationService,
    OutlineGenerationService,
    OutlineValidationFailure,
)
from windagent_intelligence.story.prompts import (
    FixtureModelPort,
    StoryModelBoundary,
)
from windagent_intelligence.story.prompts.structured import StorySchemaFailure


def _run(coro):
    return asyncio.run(coro)


def _beat_service(response: str) -> BeatGenerationService:
    return BeatGenerationService(StoryModelBoundary(FixtureModelPort(responses={"beats": response})))


def _outline_service(response: str) -> OutlineGenerationService:
    return OutlineGenerationService(StoryModelBoundary(FixtureModelPort(responses={"outline": response})))


def test_beat_happy_path():
    result = _run(_beat_service(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False)).generate(
        GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
    ))
    assert result.beat_sheet.beat_count == 4
    assert result.beat_sheet.allocated_seconds == 240
    assert result.validation["pass"] is True
    assert result.provenance.prompt_id == "story.beats.generate"


def test_outline_happy_path():
    beat_sheet = BeatSheet(**GOLDEN_BEAT_SHEET)
    result = _run(_outline_service(json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False)).generate(
        beat_sheet, canon=GOLDEN_CANON, world=GOLDEN_WORLD
    ))
    assert result.episode_outline.scene_count == 4
    assert result.episode_outline.total_estimated_seconds == 240
    assert result.validation["pass"] is True
    assert result.provenance.prompt_id == "story.outline.structured"


def test_outline_prompt_carries_exact_allowed_canon_ids():
    port = FixtureModelPort(
        responses={"outline": json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False)}
    )
    service = OutlineGenerationService(StoryModelBoundary(port))
    _run(
        service.generate(
            BeatSheet(**GOLDEN_BEAT_SHEET),
            canon=GOLDEN_CANON,
            world=GOLDEN_WORLD,
        )
    )

    rendered = port.requests[0].user
    for character in GOLDEN_CANON.characters:
        assert character.character_id.value in rendered
    for location in GOLDEN_WORLD.recurring_locations:
        assert location.location_id.value in rendered


def test_beat_generation_is_idempotent():
    first = _run(_beat_service(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False)).generate(
        GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
    ))
    second = _run(_beat_service(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False)).generate(
        GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
    ))
    assert first.beat_sheet.content_hash() == second.beat_sheet.content_hash()


def test_markdown_fence_repaired_once():
    response = "```json\n" + json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False) + "\n```"
    result = _run(_beat_service(response).generate(GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON))
    assert result.provenance.repair_count == 1


def test_not_json_fails_schema():
    with pytest.raises(StorySchemaFailure):
        _run(_beat_service("prose").generate(GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON))


def test_invalid_canon_rejected_before_provider_call():
    port = FixtureModelPort(responses={"beats": json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False)})
    service = BeatGenerationService(StoryModelBoundary(port))
    # Canon with a relationship to an unknown character fails cross-validation.
    from windagent_core.domain.story.bibles import CharacterRelationship

    bad_canon = GOLDEN_CANON.model_copy(update={
        "characters": [
            entry.model_copy(update={
                "relationships": [CharacterRelationship(
                    from_id=entry.character_id, to_id="ch_ghost", kind="friend"
                )]
            }) if entry.character_id.value == "ch_rabbit" else entry
            for entry in GOLDEN_CANON.characters
        ]
    })
    with pytest.raises(OutlineValidationFailure):
        _run(service.generate(GOLDEN_STORY, GOLDEN_WORLD, bad_canon))
    assert port.requests == []  # fail closed: provider never called


def test_beat_duration_outside_tolerance_blocks():
    data = json.loads(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False))
    data["beats"][0]["target_seconds"] = 300  # total 500 vs target 240
    with pytest.raises(OutlineValidationFailure) as exc:
        _run(_beat_service(json.dumps(data, ensure_ascii=False)).generate(
            GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
        ))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "DURATION_SUM" in codes


def test_beat_unknown_character_ref_blocks():
    data = json.loads(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False))
    data["beats"][0]["character_ids"] = ["ch_ghost"]
    with pytest.raises(OutlineValidationFailure) as exc:
        _run(_beat_service(json.dumps(data, ensure_ascii=False)).generate(
            GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
        ))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "REF_MISSING" in codes


def test_beat_missing_or_unknown_location_ref_blocks():
    for location_id in (None, "loc_ghost"):
        data = json.loads(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False))
        data["beats"][0]["location_id"] = location_id
        expected_exception = StorySchemaFailure if location_id is None else OutlineValidationFailure
        with pytest.raises(expected_exception) as exc:
            _run(
                _beat_service(json.dumps(data, ensure_ascii=False)).generate(
                    GOLDEN_STORY,
                    GOLDEN_WORLD,
                    GOLDEN_CANON,
                )
            )
        if isinstance(exc.value, OutlineValidationFailure):
            codes = {issue["code"] for issue in exc.value.details["issues"]}
            assert "REF_MISSING" in codes


def test_outline_orphan_beat_blocks():
    data = json.loads(json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False))
    for scene in data["scenes"]:
        scene["beat_refs"] = ["b1"]  # b2-b4 orphaned everywhere
    with pytest.raises(OutlineValidationFailure) as exc:
        _run(_outline_service(json.dumps(data, ensure_ascii=False)).generate(
            BeatSheet(**GOLDEN_BEAT_SHEET), canon=GOLDEN_CANON, world=GOLDEN_WORLD
        ))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "BEAT_ORPHAN" in codes


def test_outline_causal_order_violation_blocks():
    data = json.loads(json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False))
    data["scenes"][1]["beat_refs"] = ["b4"]
    data["scenes"][2]["beat_refs"] = ["b2"]
    with pytest.raises(OutlineValidationFailure) as exc:
        _run(_outline_service(json.dumps(data, ensure_ascii=False)).generate(
            BeatSheet(**GOLDEN_BEAT_SHEET), canon=GOLDEN_CANON, world=GOLDEN_WORLD
        ))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "CAUSAL_ORDER" in codes


def test_three_five_minute_boundaries():
    # 180s and 300s targets pass when the outline fits; 240s baseline already covered.
    for target, factor in ((180, 0.75), (300, 1.25)):
        data = json.loads(json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False))
        data["target_duration_seconds"] = target
        for scene in data["scenes"]:
            scene["estimated_seconds"] = int(scene["estimated_seconds"] * factor)
        total = sum(s["estimated_seconds"] for s in data["scenes"])
        if abs(total - target) <= 15 and 180 <= total <= 300:
            result = _run(_outline_service(json.dumps(data, ensure_ascii=False)).generate(
                BeatSheet(**GOLDEN_BEAT_SHEET), canon=GOLDEN_CANON, world=GOLDEN_WORLD
            ))
            assert result.validation["pass"] is True


def test_outline_duration_bound_blocks():
    data = json.loads(json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False))
    for scene in data["scenes"]:
        scene["estimated_seconds"] = 30  # total 120 < 180
    with pytest.raises(OutlineValidationFailure) as exc:
        _run(_outline_service(json.dumps(data, ensure_ascii=False)).generate(
            BeatSheet(**GOLDEN_BEAT_SHEET), canon=GOLDEN_CANON, world=GOLDEN_WORLD
        ))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "DURATION_BOUND" in codes
    assert "DURATION_SUM" in codes


def test_unicode_vietnamese_preserved():
    data = json.loads(json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False))
    data["beats"][0]["description"] = "Thỏ ơi — ạ, ẻ, ồ, ư: nhặt diều bên sông."
    result = _run(_beat_service(json.dumps(data, ensure_ascii=False)).generate(
        GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON
    ))
    assert result.beat_sheet.beats[0].description == data["beats"][0]["description"]
