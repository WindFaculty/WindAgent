"""
WindAgent Providers Package (V2 Architecture).
Modular model provider adapters, base contract, and capability matrix.
"""

from windagent_providers.capabilities import (
    ModelCapability, ModelCapabilityProfile, KNOWN_MODEL_PROFILES
)
from windagent_providers.base import (
    BaseModelProvider, ProviderHealth, QuotaSnapshot, ModelChunk
)
from windagent_providers.adapters.mock import MockProviderAdapter
from windagent_providers.adapters.openai_compatible import OpenAICompatibleProviderAdapter
from windagent_providers.adapters.anthropic import AnthropicProviderAdapter
from windagent_providers.adapters.google_gemini import GoogleGeminiProviderAdapter
from windagent_providers.adapters.ollama import OllamaProviderAdapter

__version__ = "0.3.0"

__all__ = [
    "ModelCapability", "ModelCapabilityProfile", "KNOWN_MODEL_PROFILES",
    "BaseModelProvider", "ProviderHealth", "QuotaSnapshot", "ModelChunk",
    "MockProviderAdapter",
    "OpenAICompatibleProviderAdapter",
    "AnthropicProviderAdapter",
    "GoogleGeminiProviderAdapter",
    "OllamaProviderAdapter",
]
