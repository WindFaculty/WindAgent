"""Plan B B3 contract tests over the committed ideation fixtures.

Every committed fixture must match live behavior: the prompt catalog entry
for ``story.ideation.generate``, the golden evaluated candidate set, the
invalid-output corpus results re-run through the real service, the
selection-policy matrix, and the handler/task-type surface. This is the
fixture-side half of IDEA_GATE.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verification.produce_b3_evidence import (
    GOLDEN_BRIEF,
    IDEA_CORPUS,
    golden_evaluated_set,
    policy_matrix,
    run_corpus,
)

from windagent_core.contracts.studio.commands import SelectIdeaCommand
from windagent_core.contracts.studio.models import StudioTaskType
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
IDEATION_DIR = (
    REPO_ROOT
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
    / "story_ideation"
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
    return json.loads((IDEATION_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Prompt catalog entry
# ---------------------------------------------------------------------------


def test_ideation_prompt_registered_non_legacy_schema_first():
    entry = prompt_for("story.ideation.generate")
    assert entry.version == "1.0.0"
    assert entry.legacy is False
    assert entry.output_format == "json"
    assert entry.output_schema["title"] == "IdeaGenerationOutput"
    assert entry.output_schema["properties"]["candidates"]["minItems"] == 3
    assert entry.output_schema["properties"]["candidates"]["maxItems"] == 5
    assert validate_registry_invariants() == []


def test_ideation_prompt_in_committed_manifest():
    committed = json.loads((PROMPTS_DIR / "prompt_manifest.json").read_text(encoding="utf-8"))
    live = json.loads(_canonical_bytes(prompt_manifest()))
    assert committed == live
    row = committed["entries"]["story.ideation.generate"]
    assert row["legacy"] is False
    assert row["output_schema_ref"] == "schemas/IdeaGenerationOutput.json"
    schema_path = PROMPTS_DIR / "schemas" / "IdeaGenerationOutput.json"
    assert schema_path.exists()
    assert row["content_hash"] == prompt_for("story.ideation.generate").content_hash


def test_manifest_checksum_matches_committed_file():
    checksums = load("checksums.json")
    raw = (PROMPTS_DIR / "prompt_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == checksums["prompt_manifest"]


# ---------------------------------------------------------------------------
# Golden evaluated set
# ---------------------------------------------------------------------------


def test_golden_fixture_matches_live_generation_and_evaluation():
    committed = load("idea_candidates_golden.json")
    live = golden_evaluated_set()
    assert committed == live
    assert len(committed["candidates"]) == 4
    assert committed["scoring_rubric_version"] == "score_rubric/v1"
    assert committed["recommended_candidate_id"]
    assert len(committed["set_content_hash"]) == 64
    assert committed["generation_provenance"]["prompt_id"] == "story.ideation.generate"


def test_golden_set_is_age_safe_vietnamese():
    committed = load("idea_candidates_golden.json")
    assert all(c["safety_ok"] for c in committed["candidates"])
    assert all(c["age_fit"] >= 0.5 for c in committed["candidates"])
    for candidate in committed["candidates"]:
        assert any(term in candidate["title"] for term in ("diều", "Thỏ", "thỏ"))  # rabbit/kite slice


# ---------------------------------------------------------------------------
# Invalid-output corpus
# ---------------------------------------------------------------------------


def test_corpus_results_match_live_behavior():
    committed = load("invalid_output_corpus_results.json")
    live = run_corpus()
    assert committed == live


def test_every_corpus_case_has_expected_outcome():
    results = {r["case"]: r for r in load("invalid_output_corpus_results.json")["results"]}
    for case in IDEA_CORPUS:
        row = results[case["case"]]
        if case["expect"] == "ok":
            assert row["outcome"] == "ok", case["case"]
        elif case["expect"] == "IDEA_VALIDATION_FAILURE":
            assert row["code"] == "IDEA_VALIDATION_FAILURE", case["case"]
            assert set(row["issue_codes"]) == set(case["issue_codes"]), case["case"]
        else:
            assert row["code"] == case["expect"], case["case"]


def test_corpus_checksums_match_committed():
    checksums = load("checksums.json")
    assert hashlib.sha256(_canonical_bytes(IDEA_CORPUS)).hexdigest() == checksums["corpus"]
    assert hashlib.sha256(_canonical_bytes(run_corpus())).hexdigest() == checksums["results"]


# ---------------------------------------------------------------------------
# Selection policy matrix
# ---------------------------------------------------------------------------


def test_policy_matrix_matches_live_logic():
    committed = load("selection_policy_matrix.json")
    live = policy_matrix()
    assert committed == live
    by_policy = {}
    for row in committed["rows"]:
        by_policy.setdefault(row["selection_policy"], []).append(row)
    human = by_policy["HUMAN_REQUIRED"][0]
    assert human["auto_selection_allowed"] is False
    assert by_policy["UNKNOWN_POLICY"][0]["auto_selection_allowed"] is False
    auto_evaluated = next(r for r in by_policy["AUTO_WHEN_POLICY_ALLOWS"] if r["evaluated"])
    assert auto_evaluated["auto_selection_allowed"] is True
    auto_raw = next(r for r in by_policy["AUTO_WHEN_POLICY_ALLOWS"] if not r["evaluated"])
    assert auto_raw["auto_selection_allowed"] is False


# ---------------------------------------------------------------------------
# Handler surface + selection command contract
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


def test_selection_command_binds_candidate_to_hash():
    command = SelectIdeaCommand(
        idempotency_key="k1",
        episode_id="ep_1",
        revision_id="rev_1",
        candidate_id="c_rabbit_kite",
        expected_content_hash="a" * 64,
    )
    assert command.candidate_id == "c_rabbit_kite"
    assert len(command.expected_content_hash) == 64
    assert command.schema_version == "studio.command/v1"


def test_handlers_import_no_infrastructure():
    import inspect

    from windagent_intelligence.story import runtime_handlers as module

    source = inspect.getsource(module)
    for forbidden in ("sqlalchemy", "storage", "queue", "WorkflowEngine", "alembic"):
        assert forbidden not in source, f"handler surface leaks {forbidden}"
    idea_source = inspect.getsource(module.idea)
    assert "StoryModelBoundary" in idea_source
    assert "FixtureModelPort" not in idea_source  # fakes stay in tests


def test_generate_handler_roundtrip_via_fixture_port():
    import asyncio

    from windagent_intelligence.story import IdeaGenerateHandler
    from windagent_intelligence.story.prompts import FixtureModelPort

    response = {
        "language": "vi",
        "candidates": [
            {"candidate_id": "c1", "title": "A", "summary": "s", "premise": "p", "logline": "l",
             "themes": [], "age_fit": 0.9, "estimated_seconds": 240, "scene_count": 5,
             "character_count": 2, "location_count": 2, "safety_ok": True},
            {"candidate_id": "c2", "title": "B", "summary": "s", "premise": "p", "logline": "l",
             "themes": [], "age_fit": 0.9, "estimated_seconds": 240, "scene_count": 5,
             "character_count": 2, "location_count": 2, "safety_ok": True},
            {"candidate_id": "c3", "title": "C", "summary": "s", "premise": "p", "logline": "l",
             "themes": [], "age_fit": 0.9, "estimated_seconds": 240, "scene_count": 5,
             "character_count": 2, "location_count": 2, "safety_ok": True},
        ],
    }
    port = FixtureModelPort(responses={"ideation": json.dumps(response, ensure_ascii=False)})
    handler = IdeaGenerateHandler(port)
    result = asyncio.run(handler.handle(GOLDEN_BRIEF))
    assert result.candidate_set.candidate_count == 3
    assert handler.task_type == StudioTaskType.IDEA_GENERATE
