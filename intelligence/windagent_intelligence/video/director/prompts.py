"""
Versioned, hashed planning prompts for the Director layer (Phase 8).

The planner prompt asks for a STRUCTURED JSON plan (`PlannerOutput` schema).
The LLM proposes; the deterministic `DirectorPlanValidator` decides validity.
The prompt version + content hash are recorded on every plan so each plan is
traceable to the exact prompt that produced it.

Note: the template intentionally contains NO literal curly braces other than
the `{package_json}` / `{schema_hint}` slots (PromptSpec.render uses
str.format_map, which would choke on embedded JSON braces). The full schema
example is injected at render time via `schema_hint`.
"""

from __future__ import annotations

from windagent_intelligence.video.prompts import PromptSpec

DIRECTOR_PLANNING_PROMPT_V1 = PromptSpec(
    capability="cinematic_planning",
    version="1.0.0",
    description=(
        "Propose a structured cinematic plan (scene objectives, beats, and "
        "shots) for a locked VideoProductionPackage. Output STRICT JSON only."
    ),
    template=(
        "You are a film director planning shots for an approved production.\n"
        "Input is a canonical VideoProductionPackage (JSON).\n"
        "Produce a STRICT JSON object matching the schema below. No markdown, "
        "no prose outside the JSON.\n\n"
        "SCHEMA EXAMPLE (field names and allowed enum values):\n"
        "{schema_hint}\n\n"
        "RULES:\n"
        "- Use ONLY scene/dialogue/asset IDs that exist in the package.\n"
        "- Every scene must have at least one shot; every dialogue line must "
        "be bound to exactly one shot.\n"
        "- Dialogue duration must fit its shot (do not silently cut dialogue).\n"
        "- Respect the target duration and production constraints.\n\n"
        "PACKAGE (JSON):\n{package_json}"
    ),
)

# Schema hint injected at render time (JSON with braces is safe here).
_DIRECTOR_SCHEMA_HINT = (
    '{"schema_version": "1.0.0", "planner_version": "1.0.0", '
    '"scene_objectives": [{"scene_id": "<existing scene id>", '
    '"objective": "<narrative goal>", '
    '"beats": [{"beat_order": 1, "objective": "<beat>", "source": "scene.action"}], '
    '"required_story_facts": ["<fact>"]}], '
    '"shots": [{"scene_id": "<existing scene id>", "order": 1, '
    '"shot_type": "ESTABLISHING|MASTER|MEDIUM|CLOSE_UP|EXTREME_CLOSE_UP|'
    'OVER_SHOULDER|POV|INSERT|REACTION|TRANSITION", '
    '"camera_movement": "STATIC|PAN|TILT|DOLLY|TRACK|CRANE|HANDHELD", '
    '"camera_angle": "eye-level|high-angle|low-angle|dutch", '
    '"duration_seconds": <positive number>, '
    '"framing_description": "<framing>", '
    '"transition_type": "CUT|FADE|DISSOLVE|WIPE|MATCH_CUT", '
    '"generation_mode": "TEXT_TO_VIDEO|IMAGE_TO_VIDEO|FRAMES_TO_VIDEO|'
    'INGREDIENTS_TO_VIDEO|VIDEO_EXTENSION|VIDEO_TO_VIDEO", '
    '"dialogue_line_ids": ["<existing dialogue id>"], '
    '"reference_asset_ids": ["<existing approved asset id>"], '
    '"narrative_purpose": "<why this shot>"}]}'
)

__all__ = ["DIRECTOR_PLANNING_PROMPT_V1", "_DIRECTOR_SCHEMA_HINT"]
