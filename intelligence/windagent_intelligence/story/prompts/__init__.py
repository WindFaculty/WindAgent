"""
Story prompt catalog + structured model boundary (Plan B, B2).

The prompt catalog is the ONLY source of prompt definitions for canonical
Story stages; the structured model boundary enforces schema-first responses
through the frozen provider-neutral ``PreproductionModelPort`` seam.
"""

from __future__ import annotations

from windagent_intelligence.story.prompts.fixture import (
    FIXTURE_PROVIDER,
    FixtureModelPort,
    assert_not_fixture,
    is_fixture_provider,
)
from windagent_intelligence.story.prompts.registry import (
    OUTPUT_FORMAT_JSON,
    OUTPUT_FORMAT_TEXT,
    PROMPT_SCHEMA_VERSION,
    STORY_PROMPT_REGISTRY,
    SafetyConstraints,
    StoryPromptEntry,
    prompt_for,
    prompt_manifest,
    register_prompt,
    registered_prompt_ids,
    validate_registry_invariants,
)
from windagent_intelligence.story.prompts.schemas import (
    BIBLE_GENERATION_OUTPUT_SCHEMA,
    BEATS_GENERATION_OUTPUT_SCHEMA,
    BRIEF_EXPANSION_OUTPUT_SCHEMA,
    CONTINUATION_TEXT_SPEC,
    JSON_SCHEMA_DIALECT,
    OUTLINE_GENERATION_OUTPUT_SCHEMA,
    OUTLINE_OUTPUT_SCHEMA,
    SCREENPLAY_TEXT_SPEC,
)
from windagent_intelligence.story.prompts.structured import (
    StoryEmptyResponseError,
    StoryModelBoundary,
    StoryModelError,
    StoryModelProvenance,
    StoryParseTransientError,
    StoryProviderTransientError,
    StorySafetyFailure,
    StorySchemaFailure,
    StructuredModelResult,
    story_error_code,
)

__all__ = [
    "PROMPT_SCHEMA_VERSION",
    "OUTPUT_FORMAT_JSON",
    "OUTPUT_FORMAT_TEXT",
    "JSON_SCHEMA_DIALECT",
    "SafetyConstraints",
    "StoryPromptEntry",
    "STORY_PROMPT_REGISTRY",
    "register_prompt",
    "prompt_for",
    "registered_prompt_ids",
    "prompt_manifest",
    "validate_registry_invariants",
    "BRIEF_EXPANSION_OUTPUT_SCHEMA",
    "OUTLINE_OUTPUT_SCHEMA",
    "SCREENPLAY_TEXT_SPEC",
    "CONTINUATION_TEXT_SPEC",
    "BIBLE_GENERATION_OUTPUT_SCHEMA",
    "BEATS_GENERATION_OUTPUT_SCHEMA",
    "OUTLINE_GENERATION_OUTPUT_SCHEMA",
    "StoryModelError",
    "StoryProviderTransientError",
    "StoryEmptyResponseError",
    "StoryParseTransientError",
    "StorySchemaFailure",
    "StorySafetyFailure",
    "story_error_code",
    "StoryModelProvenance",
    "StructuredModelResult",
    "StoryModelBoundary",
    "FixtureModelPort",
    "FIXTURE_PROVIDER",
    "is_fixture_provider",
    "assert_not_fixture",
]
