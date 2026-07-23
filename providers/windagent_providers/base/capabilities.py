"""
Model Capabilities Matrix and Matching Engine for WindAgent Provider Subsystem V3.
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
}
