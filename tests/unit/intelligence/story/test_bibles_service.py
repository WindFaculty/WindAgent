"""Plan B B4 unit tests: BibleGenerationService + handler behavior."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.verification.produce_b4_evidence import (
    GOLDEN_BIBLE_RESPONSE,
    GOLDEN_SELECTED_IDEA,
)

from windagent_core.domain.story.ideation import SelectedIdea
from windagent_core.domain.story.ids import SelectedIdeaId
from windagent_intelligence.story.bibles.service import (
    BibleGenerationService,
    BibleValidationFailure,
)
from windagent_intelligence.story.prompts import (
    FixtureModelPort,
    StoryModelBoundary,
)
from windagent_intelligence.story.prompts.structured import StorySchemaFailure


def _service(response: str) -> BibleGenerationService:
    return BibleGenerationService(
        StoryModelBoundary(FixtureModelPort(responses={"bibles": response}))
    )


def _run(coro):
    return asyncio.run(coro)


def test_happy_path_builds_three_artifacts():
    service = _service(json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False))
    result = _run(service.generate(GOLDEN_SELECTED_IDEA))
    assert result.story_bible.title == "Con thỏ và cánh diều"
    assert result.world_bible.setting
    assert result.character_canon.character_count == 2
    assert result.validation["pass"] is True
    assert result.provenance.prompt_id == "story.bibles.generate"
    assert result.provenance.repair_count == 0


def test_idempotent_same_inputs_same_set_hash():
    service = _service(json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False))
    first = _run(service.generate(GOLDEN_SELECTED_IDEA))
    second = _run(service.generate(GOLDEN_SELECTED_IDEA))
    assert first.story_bible.content_hash() == second.story_bible.content_hash()
    assert first.world_bible.content_hash() == second.world_bible.content_hash()
    assert first.character_canon.content_hash() == second.character_canon.content_hash()


def test_markdown_fenced_json_repaired_once():
    response = "```json\n" + json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False) + "\n```"
    result = _run(_service(response).generate(GOLDEN_SELECTED_IDEA))
    assert result.provenance.repair_count == 1


def test_trailing_commentary_after_json_repaired_once():
    response = (
        json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False)
        + "\nĐây là bộ canon hoàn chỉnh cho tập phim."
    )
    result = _run(_service(response).generate(GOLDEN_SELECTED_IDEA))
    assert result.provenance.repair_count == 1


def test_not_json_fails_schema():
    with pytest.raises(StorySchemaFailure):
        _run(_service("just prose").generate(GOLDEN_SELECTED_IDEA))


def test_missing_world_bible_fails_schema():
    response = json.dumps(
        {"story_bible": GOLDEN_BIBLE_RESPONSE["story_bible"], "character_canon": GOLDEN_BIBLE_RESPONSE["character_canon"]},
        ensure_ascii=False,
    )
    with pytest.raises(StorySchemaFailure):
        _run(_service(response).generate(GOLDEN_SELECTED_IDEA))


def _mutated_characters(mutate) -> str:
    characters = json.loads(json.dumps(GOLDEN_BIBLE_RESPONSE["character_canon"]["characters"], ensure_ascii=False))
    mutate(characters)
    response = json.loads(json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False))
    response["character_canon"]["characters"] = characters
    return json.dumps(response, ensure_ascii=False)


def test_duplicate_character_ids_blocks():
    response = _mutated_characters(lambda chars: chars.__setitem__(1, {**chars[1], "character_id": "ch_rabbit"}))
    with pytest.raises(BibleValidationFailure) as exc:
        _run(_service(response).generate(GOLDEN_SELECTED_IDEA))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "ID_UNIQUE" in codes


def test_self_loop_relationship_blocks():
    response = _mutated_characters(
        lambda chars: chars.__setitem__(
            0, {**chars[0], "relationships": [{"from_id": "ch_rabbit", "to_id": "ch_rabbit", "kind": "friend"}]}
        )
    )
    with pytest.raises(BibleValidationFailure) as exc:
        _run(_service(response).generate(GOLDEN_SELECTED_IDEA))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "RELATIONSHIP_CYCLE" in codes


def test_relationship_to_unknown_character_blocks():
    response = _mutated_characters(
        lambda chars: chars.__setitem__(
            0, {**chars[0], "relationships": [{"from_id": "ch_rabbit", "to_id": "ch_ghost", "kind": "friend"}]}
        )
    )
    with pytest.raises(BibleValidationFailure) as exc:
        _run(_service(response).generate(GOLDEN_SELECTED_IDEA))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "REF_MISSING" in codes


def test_age_band_outside_audience_blocks():
    response = _mutated_characters(lambda chars: chars.__setitem__(0, {**chars[0], "age_band": "10-12"}))
    with pytest.raises(BibleValidationFailure) as exc:
        _run(_service(response).generate(GOLDEN_SELECTED_IDEA, audience_min_age=5))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "SAFETY_AGE_UNSUITABLE" in codes


def test_age_band_check_skipped_without_audience_constraint():
    response = _mutated_characters(lambda chars: chars.__setitem__(0, {**chars[0], "age_band": "10-12"}))
    result = _run(_service(response).generate(GOLDEN_SELECTED_IDEA, audience_min_age=0))
    assert result.validation["pass"] is True


def test_world_rule_conflict_blocks():
    response = json.loads(json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False))
    response["world_bible"]["physical_rules"] = [
        {"rule_id": "r1", "statement": "Diều bay khi có gió", "kind": "physics"},
        {"rule_id": "r9", "statement": "Diều bay khi có gió", "kind": "physics"},
    ]
    with pytest.raises(BibleValidationFailure) as exc:
        _run(_service(json.dumps(response, ensure_ascii=False)).generate(GOLDEN_SELECTED_IDEA))
    codes = {i["code"] for i in exc.value.details["issues"]}
    assert "WORLD_RULE_COMPLIANCE" in codes


def test_stale_selected_idea_rejected_before_provider_call():
    stale = SelectedIdea(
        selected_idea_id=SelectedIdeaId("sel_stale"),
        source_set_id="set_stale",
        candidate_id="c_rabbit_kite",
        title="Chú thỏ và cánh diều giấy",
        selection_policy="NOT_A_POLICY",  # unknown policy fails closed
    )
    port = FixtureModelPort(responses={"bibles": json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False)})
    service = BibleGenerationService(StoryModelBoundary(port))
    with pytest.raises(BibleValidationFailure):
        _run(service.generate(stale))
    assert port.requests == []  # fail closed: provider never called


def test_unicode_vietnamese_content_preserved():
    result = _run(_service(json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False)).generate(GOLDEN_SELECTED_IDEA))
    assert result.story_bible.premise == GOLDEN_BIBLE_RESPONSE["story_bible"]["premise"]
    assert "thỏ" in result.story_bible.premise.lower()
