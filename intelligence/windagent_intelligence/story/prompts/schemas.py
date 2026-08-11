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
# B3 canonical (non-legacy) output schemas
# ---------------------------------------------------------------------------

IDEA_GENERATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "IdeaGenerationOutput",
    "description": (
        "B3 ideation: exactly 3-5 distinct, age-appropriate idea candidates "
        "for one normalized CreativeBrief. Model output is untrusted data; "
        "the boundary validates this schema BEFORE domain construction."
    ),
    "type": "object",
    "required": ["language", "candidates"],
    "properties": {
        "language": {"type": "string", "minLength": 1},
        "notes": {"type": "string"},
        "candidates": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": [
                    "candidate_id",
                    "title",
                    "summary",
                    "premise",
                    "logline",
                    "themes",
                    "age_fit",
                    "estimated_seconds",
                    "scene_count",
                    "character_count",
                    "location_count",
                    "safety_ok",
                ],
                "properties": {
                    "candidate_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "summary": {"type": "string"},
                    "premise": {"type": "string"},
                    "logline": {"type": "string"},
                    "themes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "age_fit": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "estimated_seconds": {"type": "integer", "minimum": 1},
                    "scene_count": {"type": "integer", "minimum": 1},
                    "character_count": {"type": "integer", "minimum": 1},
                    "location_count": {"type": "integer", "minimum": 1},
                    "safety_ok": {"type": "boolean"},
                },
            },
        },
    },
    "additionalProperties": True,
}

BIBLE_GENERATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "BibleGenerationOutput",
    "description": (
        "B4 canon: StoryBible + WorldBible + CharacterCanon as one consistent "
        "set. The three artifacts validate and promote together; downstream "
        "fixtures reference canon IDs, not free-form names alone."
    ),
    "type": "object",
    "required": ["story_bible", "world_bible", "character_canon"],
    "properties": {
        "story_bible": {
            "type": "object",
            "required": ["bible_id", "title", "premise"],
            "properties": {
                "bible_id": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1},
                "premise": {"type": "string", "minLength": 1},
                "theme": {"type": "string"},
                "tone": {"type": "string"},
                "arc_summary": {"type": "string"},
                "stakes": {"type": "string"},
                "story_rules": {"type": "array", "items": {"type": "string"}},
                "language": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "world_bible": {
            "type": "object",
            "required": ["world_id", "setting"],
            "properties": {
                "world_id": {"type": "string", "minLength": 1},
                "setting": {"type": "string", "minLength": 1},
                "physical_rules": {"type": "array", "items": {"$ref": "#/$defs/world_rule"}},
                "story_rules": {"type": "array", "items": {"$ref": "#/$defs/world_rule"}},
                "recurring_locations": {"type": "array", "items": {"$ref": "#/$defs/location"}},
                "recurring_objects": {"type": "array", "items": {"$ref": "#/$defs/object"}},
                "style_constraints": {"type": "object", "additionalProperties": {"type": "string"}},
                "language": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "character_canon": {
            "type": "object",
            "required": ["canon_id", "characters"],
            "properties": {
                "canon_id": {"type": "string", "minLength": 1},
                "language": {"type": "string"},
                "characters": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"$ref": "#/$defs/character"},
                },
            },
            "additionalProperties": True,
        },
    },
    "$defs": {
        "world_rule": {
            "type": "object",
            "required": ["rule_id", "statement"],
            "properties": {
                "rule_id": {"type": "string", "minLength": 1},
                "statement": {"type": "string", "minLength": 1},
                "kind": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "location": {
            "type": "object",
            "required": ["location_id", "name"],
            "properties": {
                "location_id": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
            },
            "additionalProperties": True,
        },
        "object": {
            "type": "object",
            "required": ["prop_id", "name"],
            "properties": {
                "prop_id": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
            },
            "additionalProperties": True,
        },
        "character": {
            "type": "object",
            "required": ["character_id", "name"],
            "properties": {
                "character_id": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
                "role": {"type": "string"},
                "goal": {"type": "string"},
                "traits": {"type": "array", "items": {"type": "string"}},
                "relationships": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/relationship"},
                },
                "age_band": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "relationship": {
            "type": "object",
            "required": ["from_id", "to_id"],
            "properties": {
                "from_id": {"type": "string", "minLength": 1},
                "to_id": {"type": "string", "minLength": 1},
                "kind": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}

BEATS_GENERATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "BeatGenerationOutput",
    "description": (
        "B5: ordered BeatSheet allocating the episode duration budget. "
        "Beats reference canon character/location IDs and use the frozen "
        "beat-role vocabulary."
    ),
    "type": "object",
    "required": ["beat_sheet_id", "title", "beats", "total_target_seconds"],
    "properties": {
        "beat_sheet_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "beats": {
            "type": "array",
            "minItems": 4,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": ["beat_id", "order", "description", "target_seconds"],
                "properties": {
                    "beat_id": {"type": "string", "minLength": 1},
                    "order": {"type": "integer", "minimum": 1},
                    "role": {"type": "string"},
                    "description": {"type": "string", "minLength": 1},
                    "emotional_beat": {"type": "string"},
                    "character_ids": {"type": "array", "items": {"type": "string"}},
                    "location_id": {"type": "string"},
                    "target_seconds": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": True,
            },
        },
        "total_target_seconds": {"type": "integer", "minimum": 1},
        "tolerance_seconds": {"type": "integer", "minimum": 0},
        "duration_formula_version": {"type": "string"},
    },
    "additionalProperties": True,
}

OUTLINE_GENERATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "OutlineGenerationOutput",
    "description": (
        "B5: EpisodeOutline — production-aware scenes fitting the 180-300 s "
        "budget; every scene traces to beats and canon IDs."
    ),
    "type": "object",
    "required": ["outline_id", "title", "target_duration_seconds", "scenes"],
    "properties": {
        "outline_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "language": {"type": "string"},
        "audience_band": {"type": "string"},
        "target_duration_seconds": {"type": "integer", "minimum": 1},
        "tolerance_seconds": {"type": "integer", "minimum": 0},
        "scenes": {
            "type": "array",
            "minItems": 3,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": [
                    "scene_id",
                    "order",
                    "intent",
                    "location_id",
                    "estimated_seconds",
                    "beat_refs",
                ],
                "properties": {
                    "scene_id": {"type": "string", "minLength": 1},
                    "order": {"type": "integer", "minimum": 1},
                    "intent": {"type": "string", "minLength": 1},
                    "location_id": {"type": "string", "minLength": 1},
                    "character_ids": {"type": "array", "items": {"type": "string"}},
                    "conflict_change": {"type": "string"},
                    "visual_action": {"type": "string"},
                    "dialogue_budget_seconds": {"type": "integer", "minimum": 0},
                    "estimated_seconds": {"type": "integer", "minimum": 0},
                    "beat_refs": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
        },
        "duration_formula_version": {"type": "string"},
    },
    "additionalProperties": True,
}

SCREENPLAY_GENERATION_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "ScreenplayGenerationOutput",
    "description": (
        "B6: structured ScreenplayDraft — the authority. Structured JSON scenes "
        "with action/dialogue/transitions/optional narration, per-scene timing, "
        "and stable outline/beat/canon source references. Canonical screenplay "
        "text is a derived view, never the authority."
    ),
    "type": "object",
    "required": ["draft_id", "title", "target_duration_seconds", "scenes"],
    "properties": {
        "draft_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "logline": {"type": "string"},
        "language": {"type": "string"},
        "audience_band": {"type": "string"},
        "target_duration_seconds": {"type": "integer", "minimum": 1},
        "tolerance_seconds": {"type": "integer", "minimum": 0},
        "scenes": {
            "type": "array",
            "minItems": 3,
            "maxItems": 12,
            "items": {
                "type": "object",
                "required": [
                    "scene_id",
                    "order",
                    "outline_scene_id",
                    "location_id",
                ],
                "properties": {
                    "scene_id": {"type": "string", "minLength": 1},
                    "order": {"type": "integer", "minimum": 1},
                    "outline_scene_id": {"type": "string", "minLength": 1},
                    "location_id": {"type": "string", "minLength": 1},
                    "character_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "action_description": {"type": "string"},
                    "dialogue": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": [
                                "dialogue_id",
                                "scene_id",
                                "character_id",
                                "order",
                                "text",
                            ],
                            "properties": {
                                "dialogue_id": {"type": "string", "minLength": 1},
                                "scene_id": {"type": "string", "minLength": 1},
                                "character_id": {"type": "string", "minLength": 1},
                                "order": {"type": "integer", "minimum": 1},
                                "text": {"type": "string", "minLength": 1},
                                "delivery": {"type": "string"},
                                "estimated_seconds": {"type": "integer", "minimum": 0},
                            },
                            "additionalProperties": True,
                        },
                    },
                    "narration": {"type": "string"},
                    "transition": {"type": "string"},
                    "estimated_seconds": {"type": "integer", "minimum": 0},
                    "source_beat_ids": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "additionalProperties": True,
            },
        },
        "duration_formula_version": {"type": "string"},
    },
    "additionalProperties": True,
}

REVIEW_OUTPUT_SCHEMA: Dict[str, Any] = {
    "$schema": JSON_SCHEMA_DIALECT,
    "title": "ReviewOutput",
    "description": (
        "B7: model-assisted narrative review dimensions for one ScreenplayDraft. "
        "Deterministic format/duration/continuity findings come from the "
        "validation suite; the model only scores subjective narrative quality "
        "(secondary signal, never the gate authority)."
    ),
    "type": "object",
    "required": ["narrative_score", "age_fit_score", "language_score", "notes"],
    "properties": {
        "narrative_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "age_fit_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "language_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}

#: Revision output is a fresh ScreenplayDraft: same shape as generation, new
#: title so the committed schema file is distinct.
REVISION_OUTPUT_SCHEMA: Dict[str, Any] = {
    **SCREENPLAY_GENERATION_OUTPUT_SCHEMA,
    "title": "ScreenplayRevisionOutput",
    "description": (
        "B7: a NEW immutable ScreenplayDraft produced by the bounded revision "
        "task. Same structured scene shape as generation output; the draft_id "
        "must differ from the reviewed draft (the diff proves the change)."
    ),
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
    "BIBLE_GENERATION_OUTPUT_SCHEMA",
    "BEATS_GENERATION_OUTPUT_SCHEMA",
    "OUTLINE_GENERATION_OUTPUT_SCHEMA",
    "SCREENPLAY_GENERATION_OUTPUT_SCHEMA",
    "REVIEW_OUTPUT_SCHEMA",
    "REVISION_OUTPUT_SCHEMA",
]
