"""Plan B B6 unit tests: ScreenplayGenerationService + text renderer."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.verification.produce_b5_evidence import (
    GOLDEN_BEAT_SHEET,
    GOLDEN_EPISODE_OUTLINE,
)
from scripts.verification.produce_b6_evidence import (
    GOLDEN_CANON,
    GOLDEN_SCREENPLAY_DRAFT,
    GOLDEN_WORLD,
)

from windagent_core.domain.story.outline import (
    BeatSheet,
    EpisodeOutline,
    OutlineScene,
)
from windagent_intelligence.story.prompts import (
    FixtureModelPort,
    StoryModelBoundary,
)
from windagent_intelligence.story.prompts.structured import (
    StoryEmptyResponseError,
    StorySchemaFailure,
)
from windagent_intelligence.story.screenplay.renderer import render_screenplay_text
from windagent_intelligence.story.screenplay.service import (
    ScreenplayGenerationService,
    ScreenplayValidationFailure,
)

GOLDEN_OUTLINE = EpisodeOutline(**GOLDEN_EPISODE_OUTLINE)
GOLDEN_BEATS = BeatSheet(**GOLDEN_BEAT_SHEET)


def _run(coro):
    return asyncio.run(coro)


def _service(response: str) -> ScreenplayGenerationService:
    return ScreenplayGenerationService(
        StoryModelBoundary(FixtureModelPort(responses={"screenplay": response}))
    )


def _valid_response() -> str:
    return json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False)


def _mutated_scenes(first: dict, rest=None):
    scenes = [first]
    scenes.extend(rest or GOLDEN_SCREENPLAY_DRAFT["scenes"][1:])
    data = json.loads(_valid_response())
    data["scenes"] = scenes
    return json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_screenplay_happy_path():
    result = _run(_service(_valid_response()).generate(
        GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS, canon=GOLDEN_CANON, world=GOLDEN_WORLD
    ))
    assert result.draft.scene_count == 4
    assert result.draft.total_estimated_seconds == 240
    assert result.draft.dialogue_count == 7
    assert result.validation["pass"] is True
    assert result.provenance.prompt_id == "story.screenplay.structured"
    assert result.rendered_text.startswith("## Episode 1 | Con thỏ và cánh diều")


def test_screenplay_generation_is_idempotent():
    first = _run(_service(_valid_response()).generate(GOLDEN_OUTLINE))
    second = _run(_service(_valid_response()).generate(GOLDEN_OUTLINE))
    assert first.draft.content_hash() == second.draft.content_hash()
    assert first.rendered_text == second.rendered_text


def test_screenplay_prompt_uses_a_valid_json_structural_ledger():
    port = FixtureModelPort(responses={"screenplay": _valid_response()})
    service = ScreenplayGenerationService(StoryModelBoundary(port))

    _run(service.generate(GOLDEN_OUTLINE))

    prompt = port.requests[0].user
    assert '"outline_scene_id":"s1"' in prompt
    assert '"source_beat_ids":["b1"]' in prompt
    assert r'{\"draft_id\"' not in prompt
    assert '"draft_id": "dscn_<invent a fresh id' in prompt
    assert '"dialogue_id": "dlg_001"' in prompt
    assert "Output ONLY the raw JSON object" in prompt


def test_markdown_fence_repaired_once():
    response = "```json\n" + _valid_response() + "\n```"
    result = _run(_service(response).generate(GOLDEN_OUTLINE))
    assert result.provenance.repair_count == 1


def test_empty_response_is_transient():
    with pytest.raises(StoryEmptyResponseError):
        _run(_service("").generate(GOLDEN_OUTLINE))


def test_not_json_fails_schema():
    with pytest.raises(StorySchemaFailure):
        _run(_service("just prose").generate(GOLDEN_OUTLINE))


# ---------------------------------------------------------------------------
# Fail closed BEFORE the provider call (invalid outline)
# ---------------------------------------------------------------------------


def test_invalid_outline_fails_before_provider_call():
    port = FixtureModelPort(responses={"screenplay": _valid_response()})
    service = ScreenplayGenerationService(StoryModelBoundary(port))
    bad_outline = EpisodeOutline(
        **{
            **GOLDEN_EPISODE_OUTLINE,
            "scenes": [
                OutlineScene(**{**GOLDEN_EPISODE_OUTLINE["scenes"][0], "beat_refs": []}),
                *[OutlineScene(**s) for s in GOLDEN_EPISODE_OUTLINE["scenes"][1:]],
            ],
        }
    )
    with pytest.raises(ScreenplayValidationFailure) as exc:
        _run(service.generate(bad_outline, beat_sheet=GOLDEN_BEATS))
    assert port.requests == []  # never called the provider
    codes = {i["code"] for i in (exc.value.details or {}).get("issues", [])}
    assert "BEAT_ORPHAN" in codes


# ---------------------------------------------------------------------------
# Fail closed AFTER the provider call (schema-valid but domain-invalid draft)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case_name", "mutate", "expected_codes"),
    [
        ("empty_scene", lambda s: {**s, "action_description": "", "dialogue": [], "narration": ""}, ["FIELD_EMPTY"]),
        ("duplicate_ids", lambda s: {**s, "scene_id": "dscn2"}, ["ID_STABILITY", "ID_UNIQUE"]),
        ("order_gap", lambda s: {**s, "order": 2}, ["ID_STABILITY", "ORDER_SEQUENCE"]),
        ("unknown_location", lambda s: {**s, "location_id": "loc_ghost"}, ["ID_STABILITY", "REF_MISSING"]),
        ("unknown_outline_scene", lambda s: {**s, "outline_scene_id": "s9"}, ["ID_STABILITY", "REF_MISSING"]),
        ("unknown_beat", lambda s: {**s, "source_beat_ids": ["b9"]}, ["BEAT_COVERAGE", "ID_STABILITY"]),
        ("orphan_beat", lambda s: {**s, "source_beat_ids": []}, ["BEAT_COVERAGE", "ID_STABILITY"]),
        ("bad_transition", lambda s: {**s, "transition": "SMASH CUT:"}, ["FORMAT_VALIDITY"]),
        ("bad_attribution", lambda s: {**s, "dialogue": [{**s["dialogue"][0], "character_id": "ch_kite"}]}, ["DIALOGUE_ATTRIBUTION"]),
        ("dialogue_foreign_scene", lambda s: {**s, "dialogue": [{**s["dialogue"][0], "scene_id": "dscn2"}]}, ["ID_STABILITY"]),
    ],
)
def test_domain_invalid_draft_fails_closed(case_name, mutate, expected_codes):
    first = mutate(json.loads(json.dumps(GOLDEN_SCREENPLAY_DRAFT["scenes"][0], ensure_ascii=False)))
    port = FixtureModelPort(responses={"screenplay": _mutated_scenes(first)})
    service = ScreenplayGenerationService(StoryModelBoundary(port))
    with pytest.raises(ScreenplayValidationFailure) as exc:
        _run(service.generate(GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS, canon=GOLDEN_CANON, world=GOLDEN_WORLD))
    assert len(port.requests) == 1  # provider called, output rejected
    codes = {i["code"] for i in (exc.value.details or {}).get("issues", [])}
    assert set(codes) == set(expected_codes), (case_name, codes)


def test_duration_outside_180_300_fails_closed():
    # Cut ALL scenes (30+40+40+40=150s) to trip both DURATION_BOUND and DURATION_SUM.
    scenes = [
        {**json.loads(json.dumps(s, ensure_ascii=False)), "estimated_seconds": est}
        for s, est in zip(GOLDEN_SCREENPLAY_DRAFT["scenes"], (30, 40, 40, 40))
    ]
    port = FixtureModelPort(responses={"screenplay": _mutated_scenes(scenes[0], scenes[1:])})
    service = ScreenplayGenerationService(StoryModelBoundary(port))
    with pytest.raises(ScreenplayValidationFailure) as exc:
        _run(service.generate(GOLDEN_OUTLINE, beat_sheet=GOLDEN_BEATS))
    codes = {i["code"] for i in (exc.value.details or {}).get("issues", [])}
    assert set(codes) == {"DURATION_BOUND", "DURATION_SUM", "ID_STABILITY"}


# ---------------------------------------------------------------------------
# Renderer (derived text view)
# ---------------------------------------------------------------------------


def test_renderer_is_deterministic():
    result = _run(_service(_valid_response()).generate(GOLDEN_OUTLINE, canon=GOLDEN_CANON, world=GOLDEN_WORLD))
    assert render_screenplay_text(result.draft) == render_screenplay_text(result.draft)


def test_renderer_uses_canon_names_and_falls_back_to_ids():
    draft = _run(_service(_valid_response()).generate(GOLDEN_OUTLINE)).draft
    text = render_screenplay_text(
        draft,
        character_names={"ch_rabbit": "Thỏ con"},
        location_names={"loc_river": "Dòng sông"},
    )
    assert "Thỏ con: Ơ, cánh diều xinh quá!" in text
    assert "## Scene 1 | Dòng sông" in text
    # Unknown ids fall back verbatim.
    bare = render_screenplay_text(draft)
    assert "ch_kite: Thả nhẹ tay thôi, thỏ ơi!" in bare


def test_renderer_orders_dialogue_and_keeps_unicode():
    draft = _run(_service(_valid_response()).generate(GOLDEN_OUTLINE)).draft
    text = render_screenplay_text(draft)
    dlg2 = text.index("Thả nhẹ tay thôi, thỏ ơi!")
    dlg3 = text.index("Mình sẽ cố gắng thật kiên trì!")
    assert dlg2 < dlg3
    assert "<Cánh diều nhẹ nhàng bay lên theo từng bước chạy của thỏ.>" in text
    assert "FADE OUT:" in text
    assert "# Duration: 240s / target 240s" in text


def test_renderer_matches_service_rendered_text():
    with_names = {
        "character_names": {c.character_id.value: c.name for c in GOLDEN_CANON.characters},
        "location_names": {
            location.location_id.value: location.name
            for location in GOLDEN_WORLD.recurring_locations
        },
    }
    result = _run(_service(_valid_response()).generate(
        GOLDEN_OUTLINE, canon=GOLDEN_CANON, world=GOLDEN_WORLD
    ))
    assert result.rendered_text == render_screenplay_text(result.draft, **with_names)
