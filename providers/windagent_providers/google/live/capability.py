"""Live capability detection — Phase 4 (ban_ke_hoach_v1.md Section 9).

Model routing must know: live_api, video_input, text_output, function_calling.
Only models satisfying all four may be selected for role=LIVE_DIRECTOR.

UI may display "Gemini 3 Flash Live" but routing resolves to the concrete
Live API model ID: gemini-3.1-flash-live-preview (supports video input,
text output and function calling).
"""

from __future__ import annotations

# Canonical Live API model per Google AI docs (gemini-3-flash-preview itself
# does NOT support Live API; the Live variant is gemini-3.1-flash-live-preview).
LIVE_DIRECTOR_MODEL_ID = "gemini-3.1-flash-live-preview"

# Display name used in UI role chips
LIVE_DIRECTOR_DISPLAY_NAME = "Gemini 3 Flash Live"

# Capability gate as required by Section 9 — these four must all be present
LIVE_DIRECTOR_REQUIRED_CAPS = frozenset(
    {"live_api", "video_input", "text_output", "function_calling"}
)

# Alias mapping: UI-facing ID → wire ID
LIVE_MODEL_ALIASES = {
    "gemini-3-flash-preview": LIVE_DIRECTOR_MODEL_ID,
    "gemini-3-flash-live": LIVE_DIRECTOR_MODEL_ID,
    "gemini-3.1-flash-live": LIVE_DIRECTOR_MODEL_ID,
    LIVE_DIRECTOR_MODEL_ID: LIVE_DIRECTOR_MODEL_ID,
}


def canonical_live_model_id(model_id: str) -> str:
    """Normalize any alias to the canonical Live API model ID."""
    return LIVE_MODEL_ALIASES.get(model_id, model_id)


def is_live_model(model_id: str) -> bool:
    """True iff the model is a known Live API variant."""
    return canonical_live_model_id(model_id) == LIVE_DIRECTOR_MODEL_ID


def model_supports_live_director(capabilities: set[str] | list[str]) -> bool:
    """Check the four-capability gate (case-insensitive, tool→function)."""
    caps = {c.lower() for c in capabilities}
    # function_calling is exposed as tool_use in our capability matrix
    if "tool_use" in caps:
        caps.add("function_calling")
    if "chat" in caps:
        caps.add("text_output")
    return LIVE_DIRECTOR_REQUIRED_CAPS.issubset(caps)
