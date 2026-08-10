"""Plan B B6 contract tests over the committed screenplay fixtures.

Every committed fixture must match live behavior: the prompt catalog entry
(``story.screenplay.structured``), the golden ScreenplayDraft set + rendered
text sample, the invalid-output corpus results re-run through the real
service, and the handler/task-type surface. This is the fixture-side half of
SCREENPLAY_DRAFT_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.verification.produce_b6_evidence import (
    SCREENPLAY_CORPUS,
    golden_screenplay_set,
    run_screenplay_corpus,
)

from windagent_core.contracts.studio.models import StudioTaskType
from windagent_core.domain.story.outline import (
    BeatSheet,
    EpisodeOutline,
    validate_episode_outline,
)
from windagent_core.domain.story.screenplay import (
    ScreenplayDraft,
    validate_screenplay_draft,
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
from windagent_intelligence.story.screenplay.renderer import render_screenplay_text

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENPLAY_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_screenplay"
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
    return json.loads((SCREENPLAY_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt catalog entry
# ---------------------------------------------------------------------------


def test_screenplay_prompt_registered_non_legacy_schema_first():
    entry = prompt_for("story.screenplay.structured")
    assert entry.version == "1.0.0"
    assert entry.legacy is False
    assert entry.output_format == "json"
    assert entry.output_schema["title"] == "ScreenplayGenerationOutput"
    assert entry.output_schema["properties"]["scenes"]["minItems"] == 3
    assert entry.output_schema["properties"]["scenes"]["maxItems"] == 12
    assert validate_registry_invariants() == []


def test_screenplay_prompt_in_committed_manifest():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    row = committed["entries"]["story.screenplay.structured"]
    assert row["legacy"] is False
    assert row["output_schema_ref"] == "schemas/ScreenplayGenerationOutput.json"
    assert (PROMPTS_DIR / "schemas" / "ScreenplayGenerationOutput.json").exists()
    assert row["content_hash"] == prompt_for("story.screenplay.structured").content_hash


def test_manifest_checksum_matches_committed_file():
    checksums = load("checksums.json")
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["prompt_manifest"]


# ---------------------------------------------------------------------------
# Golden screenplay set
# ---------------------------------------------------------------------------


def test_golden_fixture_matches_live_generation():
    committed = load("screenplay_set_golden.json")
    live = golden_screenplay_set()
    assert committed == live
    assert committed["draft"]["draft_id"] == "draft_rabbit_kite"
    assert committed["validation"]["pass"] is True
    assert committed["provenance"]["prompt_id"] == "story.screenplay.structured"


def test_golden_draft_validates_and_traces_canon():
    from scripts.verification.produce_b4_evidence import GOLDEN_CHARACTER_CANON, GOLDEN_WORLD_BIBLE
    from scripts.verification.produce_b5_evidence import GOLDEN_BEAT_SHEET, GOLDEN_EPISODE_OUTLINE
    from windagent_core.domain.story.bibles import CharacterCanon, WorldBible

    committed = load("screenplay_set_golden.json")
    draft = ScreenplayDraft(**committed["draft"])
    canon = CharacterCanon(**GOLDEN_CHARACTER_CANON)
    world = WorldBible(**GOLDEN_WORLD_BIBLE)
    beat_sheet = BeatSheet(**GOLDEN_BEAT_SHEET)
    outline = EpisodeOutline(**GOLDEN_EPISODE_OUTLINE)

    assert validate_episode_outline(outline, beat_sheet=beat_sheet, canon=canon, world=world).is_pass()
    assert validate_screenplay_draft(
        draft, outline=outline, beat_sheet=beat_sheet, canon=canon, world=world
    ).is_pass()

    char_ids = {c.character_id for c in canon.characters}
    loc_ids = {loc.location_id for loc in world.recurring_locations}
    beat_ids = {b.beat_id for b in beat_sheet.beats}
    outline_ids = {s.scene_id for s in outline.scenes}
    assert {s.scene_id.value for s in draft.scenes} == {f"dscn{i}" for i in range(1, 5)}
    for scene in draft.scenes:
        assert scene.outline_scene_id in outline_ids
        assert scene.location_id in loc_ids
        assert set(scene.character_ids) <= char_ids
        assert set(scene.source_beat_ids) <= beat_ids
        assert scene.source_beat_ids  # no orphan scenes
        for line in scene.dialogue:
            assert line.scene_id == scene.scene_id
            assert line.character_id in scene.character_ids
            assert line.text.strip()
    assert {b.beat_id for b in beat_sheet.beats} == {r for s in draft.scenes for r in s.source_beat_ids}


def test_golden_draft_fits_180_300_seconds():
    committed = load("screenplay_set_golden.json")
    draft = ScreenplayDraft(**committed["draft"])
    assert 180 <= draft.total_estimated_seconds <= 300
    assert abs(draft.total_estimated_seconds - draft.target_duration_seconds) <= draft.tolerance_seconds


def test_rendered_sample_deterministic_and_committed():
    committed = load("screenplay_set_golden.json")
    sample = (SCREENPLAY_DIR / "rendered_sample.txt").read_text(encoding="utf-8")
    assert sample == committed["rendered_text"]
    assert hashlib.sha256(sample.encode("utf-8")).hexdigest() == committed["rendered_checksum"]
    # Deterministic: rendering the same draft twice yields identical bytes.
    from scripts.verification.produce_b6_evidence import GOLDEN_CANON, GOLDEN_WORLD

    draft = ScreenplayDraft(**committed["draft"])
    first = render_screenplay_text(
        draft,
        character_names={c.character_id.value: c.name for c in GOLDEN_CANON.characters},
        location_names={l.location_id.value: l.name for l in GOLDEN_WORLD.recurring_locations},
    )
    assert first == sample
    assert "## Scene 1 | Dòng sông" in sample
    assert "Thỏ con: Ơ, cánh diều xinh quá!" in sample
    assert "# Duration: 240s / target 240s" in sample


# ---------------------------------------------------------------------------
# Invalid-output corpus
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    committed = load("invalid_output_corpus_results.json")
    assert committed == run_screenplay_corpus()


def test_every_corpus_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["results"]}
    for case in SCREENPLAY_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
        elif case["expect"] == "SCREENPLAY_VALIDATION_FAILURE":
            assert row["code"] == "SCREENPLAY_VALIDATION_FAILURE", case["case"]
            assert set(row["issue_codes"]) == set(case["issue_codes"]), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(SCREENPLAY_CORPUS)).hexdigest() == checksums["screenplay_corpus"]
    assert hashlib.sha256(_canonical_bytes(run_screenplay_corpus())).hexdigest() == checksums["results"]
    assert hashlib.sha256(_canonical_bytes(golden_screenplay_set())).hexdigest() == checksums["golden"]


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
    }
    assert set(HANDLER_REGISTRY) == {
        StudioTaskType.IDEA_GENERATE,
        StudioTaskType.IDEA_EVALUATE,
        StudioTaskType.BIBLE_GENERATE,
        StudioTaskType.BEATS_GENERATE,
        StudioTaskType.OUTLINE_GENERATE,
        StudioTaskType.SCREENPLAY_GENERATE,
    }


def test_screenplay_handler_imports_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    source = inspect.getsource(module.screenplay)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic"):
        assert forbidden not in source, f"screenplay handler leaks {forbidden}"
    assert "StoryModelBoundary" in source
    assert "FixtureModelPort" not in source


def test_screenplay_handler_roundtrip_via_fixture_port():
    import asyncio

    from scripts.verification.produce_b5_evidence import GOLDEN_EPISODE_OUTLINE
    from scripts.verification.produce_b6_evidence import GOLDEN_SCREENPLAY_DRAFT
    from windagent_core.domain.story.outline import EpisodeOutline
    from windagent_intelligence.story import ScreenplayGenerateHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    outline = EpisodeOutline(**GOLDEN_EPISODE_OUTLINE)
    port = FixtureModelPort(responses={"screenplay": json.dumps(GOLDEN_SCREENPLAY_DRAFT, ensure_ascii=False)})
    handler = ScreenplayGenerateHandler(port)
    result = asyncio.run(handler.handle(outline))
    assert result.draft.scene_count == 4
    assert handler.task_type == StudioTaskType.SCREENPLAY_GENERATE
