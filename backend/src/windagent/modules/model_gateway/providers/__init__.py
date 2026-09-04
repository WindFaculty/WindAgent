"""Provider protocol adapters (EXTRACT_LOGIC of the frozen ``providers/*``)."""

from .anthropic import AnthropicProviderAdapter
from .contracts import (
    DiscoveredModel,
    FinishReason,
    HealthReport,
    ImagePart,
    ProviderAdapter,
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    ProviderToolCall,
    ProviderUsage,
    StreamEventType,
)
from .google import GoogleGeminiProviderAdapter
from .ollama import OllamaProviderAdapter
from .openai_compatible import (
    MistralProviderAdapter,
    NvidiaNimAdapter,
    OpenAICompatibleTransport,
    OpenAIProviderAdapter,
    OpenRouterAdapter,
)
from .resolver import SUPPORTED_PROTOCOLS, DefaultAdapterFactory

__all__ = [
    "AnthropicProviderAdapter",
    "DefaultAdapterFactory",
    "DiscoveredModel",
    "FinishReason",
    "GoogleGeminiProviderAdapter",
    "HealthReport",
    "ImagePart",
    "MistralProviderAdapter",
    "NvidiaNimAdapter",
    "OllamaProviderAdapter",
    "OpenAICompatibleTransport",
    "OpenAIProviderAdapter",
    "OpenRouterAdapter",
    "ProviderAdapter",
    "ProviderMessage",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStreamEvent",
    "ProviderToolCall",
    "ProviderUsage",
    "SUPPORTED_PROTOCOLS",
    "StreamEventType",
]
