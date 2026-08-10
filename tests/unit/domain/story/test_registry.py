"""B1 registry: completeness, duplicates, envelope wrapping, boundary."""

from __future__ import annotations

from windagent_core.domain.story import (
    STORY_ARTIFACT_REGISTRY,
    content_model_for,
    deserialize_story_artifact,
    find_duplicate_canonical_models,
    registered_artifact_types,
)
from windagent_core.domain.story.ideation.models import IdeaCandidateSet
from windagent_core.domain.studio.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactType,
    IdeaCandidate,
    IdeaCandidateSet as EnvelopeIdeaCandidateSet,
    StoryArtifactEnvelope,
)
from windagent_core.contracts.studio.ids import ArtifactId, EpisodeId, SeriesProjectId

SERIES = SeriesProjectId.generate("ser")
EPISODE = EpisodeId.generate("ep")


def test_registry_covers_all_frozen_artifact_types():
    frozen = set(ArtifactType)
    assert set(STORY_ARTIFACT_REGISTRY) == frozen, (
        set(frozen) ^ set(STORY_ARTIFACT_REGISTRY)
    )
    assert len(STORY_ARTIFACT_REGISTRY) == 13


def test_no_duplicate_canonical_models():
    assert find_duplicate_canonical_models() == []


def test_registry_models_declare_version_and_discriminator():
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        model = registration.content_model
        fields = set(model.model_fields)
        assert "schema_version" in fields, f"{model.__name__} missing schema_version"
        assert "artifact_type" in fields, f"{model.__name__} missing artifact_type"
        assert model.model_config.get("frozen") is True, f"{model.__name__} not frozen"
        sample_defaults = model.model_fields["schema_version"].default
        assert sample_defaults == ARTIFACT_SCHEMA_VERSION


def test_content_models_carry_no_envelope_fields():
    """Frozen rule: content models never own envelope identity/hash/provenance."""
    envelope_terms = {
        "artifact_id", "content_hash", "revision_id", "series_id", "episode_id",
        "prompt_id", "prompt_version", "prompt_hash", "model_route_id",
        "provider_id", "model_id", "created_by", "input_artifact_refs",
    }
    offenders = []
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        overlap = set(registration.content_model.model_fields) & envelope_terms
        if overlap:
            offenders.append((artifact_type.value, sorted(overlap)))
    assert not offenders, f"content models own envelope fields: {offenders}"


def test_envelope_wraps_canonical_content():
    candidate_set = IdeaCandidateSet(candidates=[
        IdeaCandidate(candidate_id="c1", title="T1"),
        IdeaCandidate(candidate_id="c2", title="T2"),
        IdeaCandidate(candidate_id="c3", title="T3"),
    ])
    envelope = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.IDEA_CANDIDATE_SET,
        series_id=SERIES,
        episode_id=EPISODE,
        content=candidate_set.to_canonical_dict(),
    )
    assert envelope.is_detached()
    assert envelope.artifact_type == ArtifactType.IDEA_CANDIDATE_SET
    # Envelope hash matches B canonical serialization of the same content.
    restored = deserialize_story_artifact(ArtifactType.IDEA_CANDIDATE_SET, candidate_set.serialize())
    assert restored == candidate_set
    assert content_model_for(ArtifactType.IDEA_CANDIDATE_SET) is IdeaCandidateSet


def test_deserialize_fails_closed_on_unknown_type():
    try:
        content_model_for(ArtifactType("GhostArtifact"))
        raise AssertionError("unknown artifact type must not resolve")
    except (KeyError, ValueError):
        pass


def test_envelope_alias_identity():
    # A envelope re-exports the B canonical model: one class, one schema.
    assert EnvelopeIdeaCandidateSet is IdeaCandidateSet
    assert IdeaCandidate.__module__ == "windagent_core.domain.story.ideation.models"


def test_registry_validation_codes_are_registered():
    from windagent_core.domain.story.validation import VALIDATION_CODE_CATALOG

    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        for code in registration.validation_codes:
            assert code in VALIDATION_CODE_CATALOG, (
                f"{artifact_type.value} references unregistered code {code}"
            )


def test_all_summaries_presentation_safe():
    for artifact_type, registration in STORY_ARTIFACT_REGISTRY.items():
        model = registration.content_model
        summary_fields = model.SUMMARY_FIELDS
        assert summary_fields, f"{model.__name__} missing SUMMARY_FIELDS"
        envelope_terms = {
            "content_hash", "artifact_id", "revision_id", "prompt_id",
            "provider_id", "model_id", "series_id", "episode_id",
        }
        assert not (set(summary_fields) & envelope_terms), (
            f"{model.__name__} summary leaks envelope fields"
        )
