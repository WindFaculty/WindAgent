"""
Story pipeline services (Plan B, B2+).

Subpackages (frozen by B0 registry freeze): ``ideation``, ``bibles``,
``outline``, ``screenplay``, ``review``, ``prompts``, ``runtime_handlers``.
``prompts`` holds the prompt catalog + structured model boundary (B2); the
stage packages land with their phases (B3+). Canonical stages declare their
prompts in the catalog and call the provider only through
``StoryModelBoundary`` — never through tolerant free-text parsing.
"""

from __future__ import annotations

from windagent_intelligence.story.ideation import (  # noqa: F401
    DEFAULT_TARGET_CANDIDATE_COUNT,
    IdeaEvaluationResult,
    IdeaEvaluationService,
    IdeaGenerationResult,
    IdeaGenerationService,
    IdeaValidationFailure,
)
from windagent_intelligence.story.bibles import (  # noqa: F401
    BibleGenerationResult,
    BibleGenerationService,
    BibleValidationFailure,
)
from windagent_intelligence.story.outline import (  # noqa: F401
    BeatGenerationResult,
    BeatGenerationService,
    OutlineGenerationResult,
    OutlineGenerationService,
    OutlineValidationFailure,
)
from windagent_intelligence.story.screenplay import (  # noqa: F401
    ScreenplayGenerationResult,
    ScreenplayGenerationService,
    ScreenplayValidationFailure,
    render_screenplay_text,
)
from windagent_intelligence.story.prompts import (  # noqa: F401
    PROMPT_SCHEMA_VERSION,
    STORY_PROMPT_REGISTRY,
    StoryModelBoundary,
    prompt_manifest,
    registered_prompt_ids,
    validate_registry_invariants,
)
from windagent_intelligence.story.review import (  # noqa: F401
    DEFAULT_MAXIMUM_ITERATIONS,
    DIMENSION_THRESHOLD,
    REVIEW_POLICY_VERSION,
    ReviewResult,
    ReviewService,
    ReviewValidationFailure,
    RevisionResult,
    ReviseService,
    ReviseValidationFailure,
)
from windagent_intelligence.story.runtime_handlers import (  # noqa: F401
    HANDLER_REGISTRY,
    BeatGenerateHandler,
    BibleGenerateHandler,
    IdeaEvaluateHandler,
    IdeaGenerateHandler,
    OutlineGenerateHandler,
    ScreenplayGenerateHandler,
    ReviewHandler,
    ReviseHandler,
    registered_story_task_types,
)

__all__ = [
    "PROMPT_SCHEMA_VERSION",
    "STORY_PROMPT_REGISTRY",
    "StoryModelBoundary",
    "prompt_manifest",
    "registered_prompt_ids",
    "validate_registry_invariants",
    "DEFAULT_TARGET_CANDIDATE_COUNT",
    "IdeaValidationFailure",
    "IdeaGenerationResult",
    "IdeaEvaluationResult",
    "IdeaGenerationService",
    "IdeaEvaluationService",
    "BibleValidationFailure",
    "BibleGenerationResult",
    "BibleGenerationService",
    "OutlineValidationFailure",
    "BeatGenerationResult",
    "OutlineGenerationResult",
    "BeatGenerationService",
    "OutlineGenerationService",
    "ScreenplayValidationFailure",
    "ScreenplayGenerationResult",
    "ScreenplayGenerationService",
    "render_screenplay_text",
    "REVIEW_POLICY_VERSION",
    "DIMENSION_THRESHOLD",
    "DEFAULT_MAXIMUM_ITERATIONS",
    "ReviewValidationFailure",
    "ReviewResult",
    "ReviewService",
    "ReviseValidationFailure",
    "RevisionResult",
    "ReviseService",
    "IdeaGenerateHandler",
    "IdeaEvaluateHandler",
    "BibleGenerateHandler",
    "BeatGenerateHandler",
    "OutlineGenerateHandler",
    "ScreenplayGenerateHandler",
    "ReviewHandler",
    "ReviseHandler",
    "HANDLER_REGISTRY",
    "registered_story_task_types",
]
