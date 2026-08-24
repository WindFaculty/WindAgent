"""Neutral model capability/profile types owned by Core (Phase 3 — Dependency Inversion).

These are implementation-independent capability schemas used by the
intelligence model-router policy. Core owns them so application code never
depends on provider adapters. Provider packages re-export them as
backward-compatible shims.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ModelCapability(str, Enum):
    CHAT = "chat"
    REASONING = "reasoning"
    CODING = "coding"
    TOOL_USE = "tool_use"
    VISION = "vision"
    EMBEDDING = "embedding"
    STRUCTURED_OUTPUT = "structured_output"
    LONG_CONTEXT = "long_context"
    STREAMING = "streaming"
    COMPUTER_USE = "computer_use"
    PROMPT_CACHING = "prompt_caching"
    # Live Record — Gemini Live Director (ban_ke_hoach_v1.md Section 9)
    # LIVE_API + VIDEO_INPUT + TEXT_OUTPUT (CHAT) + FUNCTION_CALLING (TOOL_USE)
    LIVE_API = "live_api"
    VIDEO_INPUT = "video_input"


@dataclass
class ModelCapabilityProfile:
    model_id: str
    provider_name: str
    capabilities: List[ModelCapability]
    context_window: int = 128000
    cost_per_1k_prompt_tokens: float = 0.0
    cost_per_1k_completion_tokens: float = 0.0
    recommended_for: List[str] = field(default_factory=list)

    def supports_all(self, required: List[ModelCapability]) -> bool:
        return all(cap in self.capabilities for cap in required)

    def supports_any(self, capabilities: List[ModelCapability]) -> bool:
        return any(cap in self.capabilities for cap in capabilities)


KNOWN_MODEL_PROFILES: Dict[str, ModelCapabilityProfile] = {
    "mock-gpt-4o": ModelCapabilityProfile(
        model_id="mock-gpt-4o",
        provider_name="mock",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.STREAMING,
        ],
        context_window=128000,
        cost_per_1k_prompt_tokens=0.0025,
        cost_per_1k_completion_tokens=0.010,
        recommended_for=["coding", "reasoning", "general"],
    ),
    "gpt-4o": ModelCapabilityProfile(
        model_id="gpt-4o",
        provider_name="openai",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.STREAMING,
            ModelCapability.PROMPT_CACHING,
        ],
        context_window=128000,
        cost_per_1k_prompt_tokens=0.0025,
        cost_per_1k_completion_tokens=0.010,
        recommended_for=["coding", "complex_reasoning", "tool_use"],
    ),
    "claude-3-5-sonnet": ModelCapabilityProfile(
        model_id="claude-3-5-sonnet",
        provider_name="anthropic",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.STREAMING,
            ModelCapability.COMPUTER_USE,
            ModelCapability.PROMPT_CACHING,
        ],
        context_window=200000,
        cost_per_1k_prompt_tokens=0.0030,
        cost_per_1k_completion_tokens=0.015,
        recommended_for=["coding", "architecture", "computer_use"],
    ),
    "gemini-1.5-pro": ModelCapabilityProfile(
        model_id="gemini-1.5-pro",
        provider_name="google",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.REASONING,
            ModelCapability.CODING,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.STREAMING,
        ],
        context_window=2000000,
        cost_per_1k_prompt_tokens=0.00125,
        cost_per_1k_completion_tokens=0.0050,
        recommended_for=["long_context", "multimodal", "analysis"],
    ),
    "ollama/llama3.1": ModelCapabilityProfile(
        model_id="ollama/llama3.1",
        provider_name="ollama",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.CODING,
            ModelCapability.TOOL_USE,
            ModelCapability.STREAMING,
        ],
        context_window=128000,
        cost_per_1k_prompt_tokens=0.0,
        cost_per_1k_completion_tokens=0.0,
        recommended_for=["privacy", "offline", "local"],
    ),
    # ── Live Director — Gemini 3.1 Flash Live Preview (ban_ke_hoach_v1.md Section 1)
    # UI displays "Gemini 3 Flash Live"; routing resolves to gemini-3.1-flash-live-preview
    # which supports Live API + video_input + text_output + function_calling.
    "gemini-3.1-flash-live-preview": ModelCapabilityProfile(
        model_id="gemini-3.1-flash-live-preview",
        provider_name="google",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.STREAMING,
            ModelCapability.LIVE_API,
            ModelCapability.VIDEO_INPUT,
        ],
        context_window=1000000,
        cost_per_1k_prompt_tokens=0.0005,
        cost_per_1k_completion_tokens=0.002,
        recommended_for=["live_director", "realtime", "video_input"],
    ),
    # Alias displayed in UI — same capabilities, maps to live preview at runtime
    "gemini-3-flash-preview": ModelCapabilityProfile(
        model_id="gemini-3-flash-preview",
        provider_name="google",
        capabilities=[
            ModelCapability.CHAT,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
            ModelCapability.STREAMING,
            ModelCapability.LIVE_API,
            ModelCapability.VIDEO_INPUT,
        ],
        context_window=1000000,
        cost_per_1k_prompt_tokens=0.0005,
        cost_per_1k_completion_tokens=0.002,
        recommended_for=["live_director", "realtime", "video_input"],
    ),
}


# ── Live Director capability gate (ban_ke_hoach_v1.md Section 9) ─────────────

LIVE_DIRECTOR_REQUIRED_CAPABILITIES = [
    ModelCapability.LIVE_API,
    ModelCapability.VIDEO_INPUT,
    ModelCapability.CHAT,  # text_output
    ModelCapability.TOOL_USE,  # function_calling
]


def is_live_director_capable(profile: ModelCapabilityProfile) -> bool:
    """Return True iff the model satisfies all four LIVE_DIRECTOR gates."""
    return profile.supports_all(LIVE_DIRECTOR_REQUIRED_CAPABILITIES)


def resolve_live_director_model(
    candidates: Dict[str, ModelCapabilityProfile] | None = None,
) -> ModelCapabilityProfile | None:
    """Resolve the canonical LIVE_DIRECTOR model from known profiles.

    Preference: gemini-3.1-flash-live-preview (real Live API) over alias.
    """
    registry = candidates if candidates is not None else KNOWN_MODEL_PROFILES
    # Exact live preview first
    live = registry.get("gemini-3.1-flash-live-preview")
    if live is not None and is_live_director_capable(live):
        return live
    # Fall back to alias if someone registered it
    alias = registry.get("gemini-3-flash-preview")
    if alias is not None and is_live_director_capable(alias):
        return alias
    # Generic fallback: any profile that satisfies the gate
    for profile in registry.values():
        if is_live_director_capable(profile):
            return profile
    return None


__all__ = [
    "ModelCapability",
    "ModelCapabilityProfile",
    "KNOWN_MODEL_PROFILES",
    "LIVE_DIRECTOR_REQUIRED_CAPABILITIES",
    "is_live_director_capable",
    "resolve_live_director_model",
]
