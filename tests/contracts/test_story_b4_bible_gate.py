"""Plan B B4 contract tests over the committed canon fixtures.

Every committed fixture must match live behavior: the prompt catalog entry
for ``story.bibles.generate``, the golden bible set (rabbit/kite), the
invalid-output corpus results re-run through the real service, the
cross-validation matrix, and the handler/task-type surface. This is the
fixture-side half of STORY_BIBLE_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verification.produce_b4_evidence import (
    BIBLE_CORPUS,
    GOLDEN_SELECTED_IDEA,
    cross_validation_matrix,
    golden_bible_set,
    run_corpus,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.bibles import (
    CharacterCanon,
    StoryBible,
    WorldBible,
    validate_canon_set,
)
from windagent_intelligence.story import (
    HANDLER_REGISTRY,
    registered_story_task_types,
)
from windagent_intelligence.story.prompts import (
    prompt_for,
    prompt_manifest,
    registered_prompt_ids,
    validate_registry_invariants,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BIBLES_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_bibles"
)
PROMPTS_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_prompts"
)


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def load(name: str):
    return json.loads((BIBLES_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt catalog entry
# ---------------------------------------------------------------------------


def test_bible_prompt_registered_non_legacy_schema_first():
    entry = prompt_for("story.bibles.generate")
    assert entry.version == "1.0.0"
    assert entry.legacy is False
    assert entry.output_format == "json"
    assert entry.output_schema["title"] == "BibleGenerationOutput"
    assert set(entry.output_schema["required"]) == {"story_bible", "world_bible", "character_canon"}
    assert validate_registry_invariants() == []


def test_bible_prompt_in_committed_manifest():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    row = committed["entries"]["story.bibles.generate"]
    assert row["legacy"] is False
    assert row["output_schema_ref"] == "schemas/BibleGenerationOutput.json"
    schema_path = PROMPTS_DIR / "schemas" / "BibleGenerationOutput.json"
    assert schema_path.exists()
    assert row["content_hash"] == prompt_for("story.bibles.generate").content_hash


def test_manifest_checksum_matches_committed_file():
    checksums = load("checksums.json")
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["prompt_manifest"]


# ---------------------------------------------------------------------------
# Golden bible set
# ---------------------------------------------------------------------------


def test_golden_fixture_matches_live_generation():
    committed = load("bible_set_golden.json")
    live = golden_bible_set()
    assert committed == live
    assert committed["story_bible"]["bible_id"] == "bible_rabbit_kite"
    assert committed["world_bible"]["world_id"] == "world_rabbit_kite"
    assert committed["character_canon"]["canon_id"] == "canon_rabbit_kite"
    assert len(committed["set_content_hash"]) == 64
    assert committed["cross_validation"]["pass"] is True
    assert committed["generation_provenance"]["prompt_id"] == "story.bibles.generate"


def test_golden_set_cross_validates_and_uses_canon_ids():
    committed = load("bible_set_golden.json")
    story = StoryBible(**committed["story_bible"])
    world = WorldBible(**committed["world_bible"])
    canon = CharacterCanon(**committed["character_canon"])
    report = validate_canon_set(story, world, canon, audience_min_age=5)
    assert report.is_pass(), report.summary()

    char_ids = {c.character_id.value for c in canon.characters}
    for entry in canon.characters:
        for rel in entry.relationships:
            assert rel.from_id.value in char_ids
            assert rel.to_id.value in char_ids
            assert rel.from_id != rel.to_id
    loc_ids = {loc.location_id.value for loc in world.recurring_locations}
    prop_ids = {obj.prop_id.value for obj in world.recurring_objects}
    assert loc_ids and prop_ids  # downstream references stable IDs, not names alone


def test_golden_set_is_age_safe_vietnamese():
    committed = load("bible_set_golden.json")
    assert committed["story_bible"]["language"] == "vi"
    assert committed["world_bible"]["language"] == "vi"
    assert committed["character_canon"]["language"] == "vi"
    assert all(c["age_band"] == "5-8" for c in committed["character_canon"]["characters"])
    assert all(c["name"] for c in committed["character_canon"]["characters"])


# ---------------------------------------------------------------------------
# Invalid-output corpus
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    committed = load("invalid_output_corpus_results.json")
    live = run_corpus()
    assert committed == live


def test_every_corpus_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["results"]}
    for case in BIBLE_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
        elif case["expect"] == "BIBLE_VALIDATION_FAILURE":
            assert row["code"] == "BIBLE_VALIDATION_FAILURE", case["case"]
            assert set(row["issue_codes"]) == set(case["issue_codes"]), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(BIBLE_CORPUS)).hexdigest() == checksums["corpus"]
    assert hashlib.sha256(_canonical_bytes(run_corpus())).hexdigest() == checksums["results"]


# ---------------------------------------------------------------------------
# Cross-validation matrix
# ---------------------------------------------------------------------------


def test_cross_validation_matrix_matches_live_logic():
    committed = load("cross_validation_matrix.json")
    live = cross_validation_matrix()
    assert committed == live
    by_dimension = {r["dimension"]: r for r in committed["rows"]}
    assert by_dimension["valid_set"]["outcome"] == "ok"
    for dimension in ("relationship_self_loop", "relationship_unknown_character",
                      "age_band_outside_audience", "duplicate_character_ids",
                      "duplicate_character_names", "duplicate_world_rule_id",
                      "world_rule_conflict"):
        assert by_dimension[dimension]["outcome"] == "error", dimension
        assert by_dimension[dimension]["issue_codes"]


# ---------------------------------------------------------------------------
# Handler surface + approval boundary
# ---------------------------------------------------------------------------


def test_handlers_match_frozen_task_types():
    assert set(registered_story_task_types()) == {
        StudioTaskType.IDEA_GENERATE.value,
        StudioTaskType.IDEA_EVALUATE.value,
        StudioTaskType.BIBLE_GENERATE.value,
        StudioTaskType.BEATS_GENERATE.value,
        StudioTaskType.OUTLINE_GENERATE.value,
        StudioTaskType.SCREENPLAY_GENERATE.value,
        StudioTaskType.REVIEW.value,
        StudioTaskType.REVISE.value,
    }
    assert set(HANDLER_REGISTRY) == {
        StudioTaskType.IDEA_GENERATE,
        StudioTaskType.IDEA_EVALUATE,
        StudioTaskType.BIBLE_GENERATE,
        StudioTaskType.BEATS_GENERATE,
        StudioTaskType.OUTLINE_GENERATE,
        StudioTaskType.SCREENPLAY_GENERATE,
        StudioTaskType.REVIEW,
        StudioTaskType.REVISE,
    }


def test_bible_handler_imports_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    bible_source = inspect.getsource(module.bible)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic"):
        assert forbidden not in bible_source, f"bible handler leaks {forbidden}"
    assert "StoryModelBoundary" in bible_source
    assert "FixtureModelPort" not in bible_source  # fakes stay in tests


def test_bible_generate_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b4_evidence import GOLDEN_BIBLE_RESPONSE
    from windagent_intelligence.story import BibleGenerateHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    port = FixtureModelPort(responses={"bibles": json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False)})
    handler = BibleGenerateHandler(port)
    result = asyncio.run(handler.handle(GOLDEN_SELECTED_IDEA))
    assert result.story_bible.bible_id.value == "bible_rabbit_kite"
    assert result.character_canon.character_count == 2
    assert handler.task_type == StudioTaskType.BIBLE_GENERATE


def test_certification_rejects_fixture_provider():
    from windagent_intelligence.story.prompts import FixtureModelPort, assert_not_fixture, is_fixture_provider

    port = FixtureModelPort(responses={"bibles": "{}"})
    assert is_fixture_provider(port)
    with pytest.raises(RuntimeError):
        assert_not_fixture(port)


def test_stale_selected_idea_rejected():
    import asyncio

    from scripts.verification.produce_b4_evidence import GOLDEN_BIBLE_RESPONSE
    from windagent_core.domain.story.ideation import SelectedIdea
    from windagent_core.domain.story.ids import SelectedIdeaId
    from windagent_intelligence.story import BibleGenerateHandler
    from windagent_intelligence.story.bibles.service import BibleValidationFailure
    from windagent_intelligence.story.prompts import FixtureModelPort

    stale = SelectedIdea(
        selected_idea_id=SelectedIdeaId("sel_stale"),
        source_set_id="set_stale",
        candidate_id="c_rabbit_kite",
        title="Chú thỏ và cánh diều giấy",
        selection_policy="NOT_A_POLICY",  # unknown policy fails closed
    )
    port = FixtureModelPort(responses={"bibles": json.dumps(GOLDEN_BIBLE_RESPONSE, ensure_ascii=False)})
    handler = BibleGenerateHandler(port)
    with pytest.raises(BibleValidationFailure):
        asyncio.run(handler.handle(stale))
