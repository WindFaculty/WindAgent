"""Unit tests for the Phase 6 video pre-production kernel.

Covers the canonical kernel's typed failures, deterministic identity, and
offline capability behavior using the deterministic model port pattern
(no network, no upstream).
"""

import json

import pytest

from windagent_intelligence.video.errors import (
    EmptyResponseError,
    MissingModelConfigError,
    ResponseParseError,
)
from windagent_intelligence.video.ids import StableIdFactory


class DeterministicPort:
    """Minimal deterministic fake implementing PreproductionModelPort."""

    def __init__(self, responses: dict) -> None:
        self._responses = responses

    async def complete(self, request):
        from windagent_intelligence.video.ports import ModelCompletionResult

        content = self._responses.get(request.capability, "")
        return ModelCompletionResult(
            capability=request.capability,
            content=content,
            provider="test-fake",
        )


SCREENPLAY_TEXT = (
    "## Episode 1\n\n"
    "## Scene 1 | DAY | INTERIOR | Forest\n"
    "Characters: Doudou\n\n"
    "Doudou: Where am I?\n"
    "<action>Doudou looks around.</action>\n\n"
    "## Scene 2 | NIGHT | EXTERIOR | Lake Shore\n"
    "Characters: Doudou, Abu\n\n"
    "Abu: Are you lost?\n"
    "Doudou: Yes, I cannot find home.\n"
    "<action>Abu flies Doudou over the forest.</action>\n\n"
    "THE END\n"
)

@pytest.fixture
def ids():
    return StableIdFactory(seed="phase6-unit-test")


# ---------------------------------------------------------------------------
# Typed failures (DEF-001 / DEF-002 / DEF-005 surface, never silent None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brief_expander_empty_response_raises_typed_error(ids):
    from windagent_intelligence.video.ideation.brief_expander import (
        CreativeBriefExpander,
    )

    expander = CreativeBriefExpander(
        DeterministicPort({"brief_expansion": ""}), id_factory=ids
    )
    with pytest.raises(EmptyResponseError):
        await expander.expand("an idea")


@pytest.mark.asyncio
async def test_brief_expander_broken_json_raises_typed_error(ids):
    from windagent_intelligence.video.ideation.brief_expander import (
        CreativeBriefExpander,
    )

    expander = CreativeBriefExpander(
        DeterministicPort({"brief_expansion": "not json {{"}), id_factory=ids
    )
    with pytest.raises(ResponseParseError):
        await expander.expand("an idea")


@pytest.mark.asyncio
async def test_brief_expander_missing_model_fails_fast(ids):
    from windagent_intelligence.video.ideation.brief_expander import (
        CreativeBriefExpander,
    )

    expander = CreativeBriefExpander(
        DeterministicPort({}), id_factory=ids, canonical_model=None
    )
    with pytest.raises(MissingModelConfigError):
        await expander.expand("an idea")


def test_entity_extractor_missing_characters_raises_typed_error():
    from windagent_intelligence.video.entity_extraction.extractor import (
        EntityExtractor,
    )

    extractor = EntityExtractor(id_factory=StableIdFactory(seed="phase6-test"))
    screenplay = _make_screenplay()
    with pytest.raises(ResponseParseError):
        extractor.extract(
            screenplay,
            json.dumps({"title": "X", "settings": []}),
        )


# ---------------------------------------------------------------------------
# Deterministic identity (DEF-003 / NONDET-005)
# ---------------------------------------------------------------------------


def test_stable_id_factory_never_merges_duplicate_display_names(ids):
    a0 = ids.character_id("豆豆", 0)
    a1 = ids.character_id("豆豆", 1)
    assert a0 != a1


def test_stable_id_factory_is_deterministic(ids):
    first = ids.character_id("Doudou", 0)
    second = StableIdFactory(seed="phase6-unit-test").character_id("Doudou", 0)
    assert first == second


# ---------------------------------------------------------------------------
# Parsing (DEF-002 / DEF-005): Unicode / Vietnamese / CJK tolerant
# ---------------------------------------------------------------------------


def test_split_episodes_handles_cjk_and_end_marker():
    from windagent_intelligence.video.parsing import split_episodes

    text = (
        "第1集 豆豆迷路\n\n"
        "**第1集-第1场 日 内 森林\n人物：豆豆\n\n"
        "豆豆：这里是哪里呀？\n"
        "<action>豆豆东张西望。</action>\n\n"
        "完\n"
    )
    eps = split_episodes(text)
    assert len(eps) == 1
    assert eps[0].episode_number == 1
    assert len(eps[0].scenes) == 1
    scene = eps[0].scenes[0]
    assert scene.header.time_of_day == "DAY"
    assert scene.header.space == "INTERIOR"
    assert scene.header.location == "森林"
    assert len(scene.units) == 2


def test_split_episodes_handles_vietnamese_and_multiword_location():
    from windagent_intelligence.video.parsing import split_episodes

    text = (
        "Tập 1: Phần mở đầu\n\n"
        "Cảnh 1 | DAY | INTERIOR | Rừng\n"
        "Nhân vật: Doudou\n\n"
        "Doudou: Chúng ta ở đâu?\n"
    )
    eps = split_episodes(text)
    assert len(eps) == 1
    scene = eps[0].scenes[0]
    assert scene.header.location == "Rừng"
    assert scene.header.time_of_day == "DAY"


def test_action_line_mentioning_scene_is_not_misparsed():
    from windagent_intelligence.video.parsing import split_episodes

    text = (
        "Tập 1\n\n"
        "Cảnh 1 | DAY | EXTERIOR | Rừng\n\n"
        "Doudou: Chúng ta chuyển tới scene 2 nhé!\n"
        "<action>Họ nhìn về phía scene 2.</action>\n"
    )
    eps = split_episodes(text)
    assert len(eps) == 1 and len(eps[0].scenes) == 1


# ---------------------------------------------------------------------------
# Offline capabilities: narration + asset prompts
# ---------------------------------------------------------------------------


def test_dialogue_narrator_attributes_lines_to_stable_characters(ids):
    from windagent_intelligence.video.screenplay.narration import DialogueNarrator

    narrator = DialogueNarrator(id_factory=ids)
    screenplay = _make_screenplay()
    result = narrator.narrate(SCREENPLAY_TEXT, screenplay.scenes)
    assert result["dialogue_lines"], "no dialogue lines extracted"
    assert result["narration_blocks"], "no narration blocks extracted"
    speakers = sorted(result["character_map"].keys())
    assert "Doudou" in speakers and "Abu" in speakers


def test_asset_prompt_specs_are_versioned_and_hashed(ids):
    from windagent_intelligence.video.asset_prompts.builder import (
        AssetPromptSpecBuilder,
    )
    from windagent_intelligence.video.entity_extraction.extractor import (
        EntityExtractor,
    )

    screenplay = _make_screenplay()
    meta = json.dumps({
        "title": "X",
        "characters": [{"name": "Doudou", "description": "a fox"}],
        "settings": [{"name": "Forest", "description": "a forest"}],
    }, ensure_ascii=False)
    extractor = EntityExtractor(id_factory=ids)
    extracted = extractor.extract(screenplay, meta)
    builder = AssetPromptSpecBuilder()
    specs = builder.build_all(
        characters=extracted["characters"],
        locations=extracted["locations"],
        style=_make_style(ids),
    )
    assert specs
    for spec in specs:
        assert spec.prompt_spec.version == "1.0.0"
        assert len(spec.prompt_spec.content_hash) == 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_style(ids: StableIdFactory):
    from windagent_core.domain.video_production.ids import StyleBibleId
    from windagent_core.domain.video_production.location import StyleBible

    return StyleBible(
        style_id=StyleBibleId(ids.style_id("test style")),
        name="test style",
        visual_style="anime",
        color_palette=["#FFD700"],
        lighting_rules=["Warm"],
    )


def _make_screenplay():
    from windagent_core.domain.video_production.enums import ScreenplayStatus
    from windagent_core.domain.video_production.ids import (
        LocationId,
        SceneId,
        ScreenplayId,
    )
    from windagent_core.domain.video_production.screenplay import Screenplay
    from windagent_core.domain.video_production.scene import Scene

    scene = Scene(
        scene_id=SceneId("scn_test_1"),
        order=1,
        title="Forest",
        location_id=LocationId("loc_test_1"),
        metadata={"scene_location": "Forest", "scene_number": 1},
    )
    return Screenplay(
        screenplay_id=ScreenplayId("scr_test_1"),
        title="Test",
        status=ScreenplayStatus.DRAFT,
        scenes=[scene],
        metadata={"episode_count": 1, "characters": ["Doudou"], "locations": ["Forest"]},
    )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
