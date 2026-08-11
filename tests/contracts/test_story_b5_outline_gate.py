"""Plan B B5 contract tests over the committed outline fixtures.

Every committed fixture must match live behavior: the prompt catalog entries
(``story.beats.generate`` + ``story.outline.structured``), the golden
BeatSheet/EpisodeOutline set, the invalid-output corpora results re-run
through the real services, and the handler/task-type surface. This is the
fixture-side half of OUTLINE_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.verification.produce_b5_evidence import (
    BEATS_CORPUS,
    OUTLINE_CORPUS,
    golden_outline_set,
    run_beats_corpus,
    run_outline_corpus,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.bibles import CharacterCanon, WorldBible
from windagent_core.domain.story.outline import (
    BeatSheet,
    EpisodeOutline,
    validate_beat_sheet,
    validate_episode_outline,
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
OUTLINE_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_outline"
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
    return json.loads((OUTLINE_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt catalog entries
# ---------------------------------------------------------------------------


def test_outline_prompts_registered_non_legacy_schema_first():
    beats = prompt_for("story.beats.generate")
    assert beats.version == "1.0.0"
    assert beats.legacy is False
    assert beats.output_format == "json"
    assert beats.output_schema["title"] == "BeatGenerationOutput"
    assert beats.output_schema["properties"]["beats"]["minItems"] == 4

    outline = prompt_for("story.outline.structured")
    assert outline.version == "1.0.0"
    assert outline.legacy is False
    assert outline.output_format == "json"
    assert outline.output_schema["title"] == "OutlineGenerationOutput"
    assert outline.output_schema["properties"]["scenes"]["maxItems"] == 12
    assert validate_registry_invariants() == []


def test_outline_prompts_in_committed_manifest():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    for prompt_id, schema_name in (
        ("story.beats.generate", "BeatGenerationOutput.json"),
        ("story.outline.structured", "OutlineGenerationOutput.json"),
    ):
        row = committed["entries"][prompt_id]
        assert row["legacy"] is False
        assert row["output_schema_ref"] == f"schemas/{schema_name}"
        assert (PROMPTS_DIR / "schemas" / schema_name).exists()
        assert row["content_hash"] == prompt_for(prompt_id).content_hash


def test_manifest_checksum_matches_committed_file():
    checksums = load("checksums.json")
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["prompt_manifest"]


# ---------------------------------------------------------------------------
# Golden outline set
# ---------------------------------------------------------------------------


def test_golden_fixture_matches_live_generation():
    committed = load("outline_set_golden.json")
    live = golden_outline_set()
    assert committed == live
    assert committed["beat_sheet"]["beat_sheet_id"] == "bs_rabbit_kite"
    assert committed["episode_outline"]["outline_id"] == "ol_rabbit_kite"
    assert committed["beat_validation"]["pass"] is True
    assert committed["outline_validation"]["pass"] is True
    assert committed["beats_provenance"]["prompt_id"] == "story.beats.generate"
    assert committed["outline_provenance"]["prompt_id"] == "story.outline.structured"


def test_golden_set_validates_and_traces_canon():
    from scripts.verification.produce_b5_evidence import GOLDEN_CANON, GOLDEN_WORLD

    committed = load("outline_set_golden.json")
    beat_sheet = BeatSheet(**committed["beat_sheet"])
    outline = EpisodeOutline(**committed["episode_outline"])
    assert validate_beat_sheet(beat_sheet, canon=GOLDEN_CANON).is_pass()
    assert validate_episode_outline(
        outline, beat_sheet=beat_sheet, canon=GOLDEN_CANON, world=GOLDEN_WORLD
    ).is_pass()

    char_ids = {c.character_id for c in GOLDEN_CANON.characters}
    loc_ids = {loc.location_id for loc in GOLDEN_WORLD.recurring_locations}
    beat_ids = {b.beat_id for b in beat_sheet.beats}
    for scene in outline.scenes:
        assert scene.location_id in loc_ids
        assert set(scene.character_ids) <= char_ids
        assert set(scene.beat_refs) <= beat_ids
        assert scene.beat_refs  # no orphan scenes
    assert {b.beat_id for b in beat_sheet.beats} == {r for s in outline.scenes for r in s.beat_refs}


def test_golden_set_fits_180_300_seconds():
    committed = load("outline_set_golden.json")
    outline = EpisodeOutline(**committed["episode_outline"])
    assert 180 <= outline.total_estimated_seconds <= 300
    assert abs(outline.total_estimated_seconds - outline.target_duration_seconds) <= outline.tolerance_seconds
    beat_sheet = BeatSheet(**committed["beat_sheet"])
    assert abs(beat_sheet.allocated_seconds - beat_sheet.total_target_seconds) <= beat_sheet.tolerance_seconds


# ---------------------------------------------------------------------------
# Invalid-output corpora
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    committed = load("invalid_output_corpus_results.json")
    assert committed["beats"] == run_beats_corpus()
    assert committed["outline"] == run_outline_corpus()


def test_every_beats_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["beats"]["results"]}
    for case in BEATS_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
        elif case["expect"] == "OUTLINE_VALIDATION_FAILURE":
            assert row["code"] == "OUTLINE_VALIDATION_FAILURE", case["case"]
            assert set(row["issue_codes"]) == set(case["issue_codes"]), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_every_outline_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["outline"]["results"]}
    for case in OUTLINE_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
        elif case["expect"] == "OUTLINE_VALIDATION_FAILURE":
            assert row["code"] == "OUTLINE_VALIDATION_FAILURE", case["case"]
            assert set(row["issue_codes"]) == set(case["issue_codes"]), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(BEATS_CORPUS)).hexdigest() == checksums["beats_corpus"]
    assert hashlib.sha256(_canonical_bytes(OUTLINE_CORPUS)).hexdigest() == checksums["outline_corpus"]
    combined = {"beats": run_beats_corpus(), "outline": run_outline_corpus()}
    assert hashlib.sha256(_canonical_bytes(combined)).hexdigest() == checksums["results"]


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
        StudioTaskType.LOCK.value,
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
        StudioTaskType.LOCK,
    }


def test_outline_handlers_import_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    source = inspect.getsource(module.outline)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic"):
        assert forbidden not in source, f"outline handlers leak {forbidden}"
    assert "StoryModelBoundary" in source
    assert "FixtureModelPort" not in source


def test_beat_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b5_evidence import GOLDEN_BEAT_SHEET, GOLDEN_CANON, GOLDEN_STORY, GOLDEN_WORLD
    from windagent_intelligence.story import BeatGenerateHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    port = FixtureModelPort(responses={"beats": json.dumps(GOLDEN_BEAT_SHEET, ensure_ascii=False)})
    handler = BeatGenerateHandler(port)
    result = asyncio.run(handler.handle(GOLDEN_STORY, GOLDEN_WORLD, GOLDEN_CANON))
    assert result.beat_sheet.beat_count == 4
    assert handler.task_type == StudioTaskType.BEATS_GENERATE


def test_outline_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b5_evidence import (
        GOLDEN_BEAT_SHEET,
        GOLDEN_CANON,
        GOLDEN_EPISODE_OUTLINE,
        GOLDEN_WORLD,
    )
    from windagent_core.domain.story.outline import BeatSheet
    from windagent_intelligence.story import OutlineGenerateHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    beat_sheet = BeatSheet(**GOLDEN_BEAT_SHEET)
    port = FixtureModelPort(responses={"outline": json.dumps(GOLDEN_EPISODE_OUTLINE, ensure_ascii=False)})
    handler = OutlineGenerateHandler(port)
    result = asyncio.run(handler.handle(beat_sheet, canon=GOLDEN_CANON, world=GOLDEN_WORLD))
    assert result.episode_outline.scene_count == 4
    assert handler.task_type == StudioTaskType.OUTLINE_GENERATE
