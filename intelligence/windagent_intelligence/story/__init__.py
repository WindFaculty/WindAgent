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

from windagent_intelligence.story.prompts import (  # noqa: F401
    PROMPT_SCHEMA_VERSION,
    STORY_PROMPT_REGISTRY,
    StoryModelBoundary,
    prompt_manifest,
    registered_prompt_ids,
    validate_registry_invariants,
)

__all__ = [
    "PROMPT_SCHEMA_VERSION",
    "STORY_PROMPT_REGISTRY",
    "StoryModelBoundary",
    "prompt_manifest",
    "registered_prompt_ids",
    "validate_registry_invariants",
]
