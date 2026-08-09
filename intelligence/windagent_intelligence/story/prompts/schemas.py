"""
Story prompt catalog output schemas (B2, frozen location: B0 registry freeze).

JSON Schema (Draft 2020-12) for every JSON-output prompt in the catalog and
declarative text-format specs for legacy text-output prompts. The registry
entry's ``output_schema`` MUST be one of the dicts below (or an inline schema
with the same shape) so the structured model boundary can validate untrusted
provider output before domain construction.

Legacy text prompts (screenplay writing / continuation) declare a text-format
spec instead of a JSON Schema: the boundary enforces size/safety only and the
stage performs its own structural parsing. Canonical Roadmap 1 stages (B3+)
always declare JSON Schemas; text-format output is retired with the legacy
stages (B6 structured screenplay).
"""

from __future__ import annotations

from typing import Any, Dict

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# ---------------------------------------------------------------------------
# JSON output schemas (extracted from the legacy video pipeline contracts)
# ---------------------------------------------------------------------------

BRIEF_EXPANSION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "BriefExpansionOutput",
    "description": "Creative brief expansion output (legacy brief_expansion stage).",
    "type": "object",
    "required": ["title", "logline", "genre", "tone", "audience", "target_duration_seconds"],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "logline": {"type": "string"},
        "genre": {"type": "string"},
        "tone": {"type": "string"},
        "audience": {"type": "string"},
        "target_duration_seconds": {"type": "integer", "minimum": 1},
        "aspect_ratio": {"type": "string"},
        "production_constraints": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
    "additionalProperties": True,
}

OUTLINE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "OutlineOutput",
    "description": "Story outline output (legacy story_outline stage).",
    "type": "object",
    "required": ["title", "premise", "synopsis", "themes", "beats"],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "premise": {"type": "string"},
        "synopsis": {"type": "string"},
        "themes": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
        },
        "beats": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": True,
}

# ---------------------------------------------------------------------------
# Text-format specs (legacy text-output prompts, not JSON Schemas)
# ---------------------------------------------------------------------------

SCREENPLAY_TEXT_SPEC: Dict[str, Any] = {
    "format": "canonical_screenplay_text_v1",
    "version": "1.0.0",
    "description": (
        "Legacy canonical screenplay text format (## Episode <N>, "
        "## Scene <N> | <TIME> | <SPACE> | <Location>, Characters:, "
        "Name: dialogue, <action>narration</action>). Replaced by the "
        "structured ScreenplayDraft JSON at B6."
    ),
}

CONTINUATION_TEXT_SPEC: Dict[str, Any] = {
    "format": "canonical_screenplay_text_v1",
    "version": "1.0.0",
    "description": (
        "Legacy continuation output: next episode(s) in the canonical "
        "screenplay text format. Replaced by structured revision at B6/B7."
    ),
}

__all__ = [
    "JSON_SCHEMA_DIALECT",
    "BRIEF_EXPANSION_OUTPUT_SCHEMA",
    "OUTLINE_OUTPUT_SCHEMA",
    "SCREENPLAY_TEXT_SPEC",
    "CONTINUATION_TEXT_SPEC",
]
