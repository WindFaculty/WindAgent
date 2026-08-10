"""
Plan B canonical Story content models (studio.artifact/v1alpha1).

Provider-neutral immutable content for every frozen Story artifact type,
deterministic validators, scoring rubric, duration formula, presentation-safe
summaries, compatibility adapters, and the artifact registry. Envelope,
identity, hash, and lock invariants are owned by Plan A
(``windagent_core.domain.studio``); this package never imports infrastructure.
"""

from windagent_core.domain.story.canonical import StoryContent, content_hash_of
from windagent_core.domain.story.versions import (
    ARTIFACT_SCHEMA_VERSION,
    SUPPORTED_ARTIFACT_SCHEMA_VERSIONS,
    canonical_json_bytes,
    parse_artifact_schema_version,
    validate_artifact_schema_version,
)
from windagent_core.domain.story.validation import (
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    ValidationSource,
    json_pointer,
)
from windagent_core.domain.story.registry import (
    STORY_ARTIFACT_REGISTRY,
    StoryArtifactRegistration,
    content_model_for,
    deserialize_story_artifact,
    find_duplicate_canonical_models,
    registered_artifact_types,
)
from windagent_core.domain.story import (
    bibles,
    ideation,
    outline,
    review,
    screenplay,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "SUPPORTED_ARTIFACT_SCHEMA_VERSIONS",
    "parse_artifact_schema_version",
    "validate_artifact_schema_version",
    "canonical_json_bytes",
    "StoryContent",
    "content_hash_of",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
    "ValidationSource",
    "json_pointer",
    "STORY_ARTIFACT_REGISTRY",
    "StoryArtifactRegistration",
    "content_model_for",
    "deserialize_story_artifact",
    "find_duplicate_canonical_models",
    "registered_artifact_types",
    "ideation",
    "bibles",
    "outline",
    "screenplay",
    "review",
]
