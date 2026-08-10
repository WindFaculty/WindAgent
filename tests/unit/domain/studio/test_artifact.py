"""A2 domain tests: artifact envelope identity/hash and content validation.

Every artifact is immutable and content-addressed; the envelope hash must
match the canonical hash of its own content; candidate sets enforce the
frozen 3-5 count rule; serialization round trips are lossless.
"""

import pytest
from pydantic import ValidationError

from windagent_core.contracts.studio.errors import StudioValidationError
from windagent_core.contracts.studio.ids import (
    ArtifactId,
    EpisodeId,
    SeriesProjectId,
)
from windagent_core.domain.studio.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactType,
    IdeaCandidate,
    IdeaCandidateSet,
    StoryArtifactEnvelope,
)
from windagent_core.domain.studio.revision import canonical_content_hash

SERIES = SeriesProjectId.generate("ser")
EPISODE = EpisodeId.generate("ep")


def _candidate(i: int) -> IdeaCandidate:
    return IdeaCandidate(candidate_id=f"cand_{i}", title=f"Title {i}", score=0.7)


def test_build_derives_content_addressed_hash():
    envelope = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.SELECTED_IDEA,
        series_id=SERIES,
        episode_id=EPISODE,
        content={"idea": "pilot"},
    )
    assert envelope.content_hash == canonical_content_hash(
        content={"idea": "pilot"}, schema_version=ARTIFACT_SCHEMA_VERSION
    )
    assert envelope.is_detached()
    assert len(envelope.artifact_id.value) > 0


def test_build_embeds_provenance_fields():
    envelope = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.SCREENPLAY_DRAFT,
        series_id=SERIES,
        episode_id=EPISODE,
        content={"text": "..."},
        prompt_id="prompt_1",
        provider_id="openrouter",
        model_id="deepseek-v4-flash",
    )
    assert envelope.prompt_id == "prompt_1"
    assert envelope.provider_id == "openrouter"
    assert envelope.model_id == "deepseek-v4-flash"


def test_build_with_explicit_hash_marks_detached_false():
    envelope = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.STORY_BIBLE,
        series_id=SERIES,
        episode_id=EPISODE,
        content={"text": "x"},
    )
    forged = envelope.model_copy(
        update={"content_hash": "b" * 64, "content": {"text": "different"}}
    )
    assert not forged.is_detached()


def test_envelope_rejects_malformed_hash():
    # pydantic min_length constraint fires before the domain validator
    with pytest.raises(ValidationError):
        StoryArtifactEnvelope(
            artifact_id=ArtifactId.generate("art"),
            artifact_type=ArtifactType.STORY_BIBLE,
            series_id=SERIES,
            episode_id=EPISODE,
            content_hash="short",
            content={},
        )


def test_envelope_round_trip_is_lossless():
    envelope = StoryArtifactEnvelope.build(
        artifact_type=ArtifactType.REVIEW_REPORT,
        series_id=SERIES,
        episode_id=EPISODE,
        content={"score": 0.9, "notes": ["a", "b"]},
        input_artifact_refs=[ArtifactId.generate("art")],
        created_by="bob",
    )
    restored = StoryArtifactEnvelope.model_validate(envelope.model_dump())
    assert restored == envelope


def test_candidate_set_requires_3_to_5_candidates():
    with pytest.raises(StudioValidationError):
        IdeaCandidateSet(candidates=[_candidate(1), _candidate(2)])
    ok = IdeaCandidateSet(candidates=[_candidate(i) for i in range(4)])
    assert len(ok.candidates) == 4
    with pytest.raises(StudioValidationError):
        IdeaCandidateSet(candidates=[_candidate(i) for i in range(6)])


def test_candidate_set_round_trip():
    cs = IdeaCandidateSet(candidates=[_candidate(i) for i in range(3)])
    restored = IdeaCandidateSet.model_validate(cs.model_dump())
    assert restored == cs
