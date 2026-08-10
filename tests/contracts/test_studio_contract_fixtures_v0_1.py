"""Validate the frozen studio.contract/v0.1 machine-readable fixtures.

The fixtures are the single coordination artifact shared by Plans A, B, and C
before implementation-specific shapes are invented. This test pins every frozen
value from the contract freeze document
(docs/plans/studio_roadmap_01/01_PARALLEL_BOOTSTRAP_AND_CONTRACT_FREEZE.md) so a
drift either fails here or requires a deliberate contract re-freeze.

These are data-only fixtures; no implementation imports them yet.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "fixtures"
    / "studio_contract_v0.1"
)

EVIDENCE_DIR = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "plans"
    / "studio_roadmap_01"
    / "evidence"
)

CONTRACT_VERSION = "studio.contract/v0.1"
ARTIFACT_SCHEMA_VERSION = "studio.artifact/v1alpha1"
BASELINE_SHA = "9a09375700db02a64315068f008b15e43ba5f42d"


def load(name: str) -> dict:
    path = FIXTURES_DIR / name
    assert path.is_file(), f"missing fixture: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def _fixture_dir_exists():
    assert FIXTURES_DIR.is_dir(), f"fixture directory missing: {FIXTURES_DIR}"
    return FIXTURES_DIR


@pytest.mark.parametrize(
    "name",
    [
        "contract_version.json",
        "ids.json",
        "episode_lifecycle.json",
        "revision_and_approval.json",
        "artifact_envelope.json",
        "tasks.json",
        "events.json",
        "errors.json",
        "ports_and_authority.json",
        "api_surface.json",
    ],
)
def test_fixture_is_valid_json_with_schema_and_version(name: str) -> None:
    data = load(name)
    assert data["schema"].startswith("studio.")
    assert data["schema"].endswith("/v1")
    if name != "contract_version.json":
        assert data["contract_version"] == CONTRACT_VERSION


def test_contract_version_pins_freeze() -> None:
    data = load("contract_version.json")
    assert data["contract"] == CONTRACT_VERSION
    assert data["artifact_schema"] == ARTIFACT_SCHEMA_VERSION
    assert data["baseline_sha"] == BASELINE_SHA


def test_ids_match_frozen_hierarchy() -> None:
    data = load("ids.json")
    assert data["hierarchy"] == ["SeriesProject", "Episode", "ProductionRevision"]
    names = {item["name"] for item in data["identities"]}
    assert names == {
        "SeriesProjectId",
        "EpisodeId",
        "ProductionRevisionId",
        "ArtifactId",
        "StudioRunId",
    }


def test_episode_lifecycle_matches_frozen_states() -> None:
    data = load("episode_lifecycle.json")
    assert data["states"] == [
        "DRAFT",
        "IDEA_REVIEW",
        "STORY_BIBLE_REVIEW",
        "OUTLINE_REVIEW",
        "SCREENPLAY_REVIEW",
        "REVISING",
        "LOCKED",
        "READY_FOR_PRODUCTION",
        "FAILED",
        "CANCELLED",
    ]
    assert data["terminal_success"] == ["READY_FOR_PRODUCTION"]
    assert data["approval_checkpoints"] == ["IDEA", "STORY_BIBLE", "OUTLINE", "SCREENPLAY"]
    assert data["approval_modes"] == ["AUTO", "HUMAN_REQUIRED", "QUALITY_GATE_ONLY"]
    assert data["lock_transition"]["sequence"] == [
        "SCREENPLAY_REVIEW",
        "LOCKED",
        "READY_FOR_PRODUCTION",
    ]


def test_revision_and_approval_fields_are_frozen() -> None:
    data = load("revision_and_approval.json")
    assert "content_hash" in data["production_revision_v0_1_fields"]
    assert "parent_revision_id" in data["production_revision_v0_1_fields"]
    assert "optimistic_version" in data["production_revision_v0_1_fields"]
    assert "artifact_hash" in data["approval_decision_binding"]
    assert data["stale_rejection_rule"] == "A stale hash or revision is rejected."


def test_artifact_envelope_is_frozen() -> None:
    data = load("artifact_envelope.json")
    assert data["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    expected_types = {
        "CreativeBrief",
        "IdeaCandidateSet",
        "SelectedIdea",
        "StoryBible",
        "WorldBible",
        "CharacterCanon",
        "BeatSheet",
        "EpisodeOutline",
        "ScreenplayDraft",
        "ReviewReport",
        "RevisionProposal",
        "LockedScreenplayReceipt",
        "LockedScreenplayPackage",
    }
    assert set(data["artifact_types"]) == expected_types
    assert "content_hash" in data["envelope_fields"]
    assert "input_artifact_refs" in data["envelope_fields"]
    assert data["idea_candidate_set_rule"].startswith("IdeaCandidateSet contains 3-5")


def test_task_types_are_frozen() -> None:
    data = load("tasks.json")
    assert data["task_types"] == [
        "studio.story.idea.generate",
        "studio.story.idea.evaluate",
        "studio.story.bible.generate",
        "studio.story.beats.generate",
        "studio.story.outline.generate",
        "studio.story.screenplay.generate",
        "studio.story.review",
        "studio.story.revise",
        "studio.story.lock",
    ]
    envelope = set(data["studio_task_envelope_minimum_fields"])
    for required in ("contract_version", "task_id", "studio_run_id", "dag_node_id", "idempotency_key"):
        assert required in envelope
    result = set(data["studio_task_result_minimum_fields"])
    for required in ("task_id", "studio_run_id", "output_artifact_refs", "route_provenance"):
        assert required in result


def test_event_types_are_frozen() -> None:
    data = load("events.json")
    assert data["event_types"] == [
        "studio.series.created",
        "studio.episode.created",
        "studio.revision.derived",
        "studio.artifact.created",
        "studio.idea.candidates_generated",
        "studio.idea.selected",
        "studio.approval.requested",
        "studio.approval.recorded",
        "studio.story.review_completed",
        "studio.story.revision_requested",
        "studio.screenplay.locked",
        "studio.episode.ready_for_production",
        "studio.run.failed",
        "studio.run.cancelled",
    ]
    assert "event_id" in data["event_envelope_fields"]
    assert "sequence" in data["event_envelope_fields"]
    assert data["publication_rule"].startswith("Task finalization publishes through the transactional outbox")


def test_error_codes_and_http_mapping_are_frozen() -> None:
    data = load("errors.json")
    by_code = {item["code"]: item for item in data["errors"]}
    assert by_code["NOT_FOUND"]["http_status"] == 404
    assert by_code["VALIDATION_ERROR"]["http_status"] == 422
    for code in ("STALE_REVISION", "ARTIFACT_HASH_MISMATCH", "LOCKED_REVISION", "IDEMPOTENCY_MISMATCH", "INVALID_TRANSITION", "APPROVAL_REQUIRED"):
        assert by_code[code]["http_status"] == 409, code
    assert by_code["CAPABILITY_UNAVAILABLE"]["http_status"] == 503
    assert by_code["PROVIDER_UNAVAILABLE"]["http_status"] == 503
    assert by_code["INTERNAL_ERROR"]["http_status"] == 500
    assert data["idempotency_rule"].startswith("All mutating endpoints require an idempotency key")


def test_ports_and_authority_are_frozen() -> None:
    data = load("ports_and_authority.json")
    assert set(data["ports"]) == {
        "SeriesProjectRepositoryPort",
        "EpisodeRepositoryPort",
        "ProductionRevisionRepositoryPort",
        "StoryArtifactRepositoryPort",
        "ApprovalRepositoryPort",
        "StudioUnitOfWorkPort",
        "StudioRunOrchestratorPort",
        "StudioTaskSubmissionPort",
        "StudioRunQueryPort",
        "StudioEventQueryPort",
        "RuntimeCapabilityPort",
        "PreproductionModelPort",
    }
    legacy_rule = data["authority_rules"][-1]
    assert "WorkflowEngine" in legacy_rule and "ProductionWorkflowEngine" in legacy_rule


def test_api_surface_matches_frozen_contract() -> None:
    data = load("api_surface.json")
    assert data["base_path"] == "/api/v3/studio"
    paths = {(item["method"], item["path"]) for item in data["resources"]}
    assert ("POST", "/series") in paths
    assert ("POST", "/episodes/{episode_id}/runs") in paths
    assert ("POST", "/episodes/{episode_id}/screenplay-lock") in paths
    assert ("POST", "/episodes/{episode_id}/idea-selection") in paths
    assert ("GET", "/runs/{run_id}/events") in paths


def test_a0_manifest_matches_its_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema_path = EVIDENCE_DIR / "a0_bootstrap_manifest.schema.json"
    manifest_path = EVIDENCE_DIR / "a0_bootstrap_manifest.json"
    assert schema_path.is_file(), f"missing manifest schema: {schema_path}"
    assert manifest_path.is_file(), f"missing manifest: {manifest_path}"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    assert manifest["manifest_version"] == "a0/v1"
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["baseline_sha"] == BASELINE_SHA
    preexisting = [item for item in manifest["baseline_failures"]]
    assert len(preexisting) >= 3
    for item in preexisting:
        assert item["classification"] == "pre-existing"
        assert item["owner"]
        assert item["retirement_gate"]
        assert item["retirement_phase"]
    assert manifest["fixture_checksums"]
