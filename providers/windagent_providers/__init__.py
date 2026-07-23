"""
WindAgent Providers Package (Architecture V3 Rebuild).
Modular model provider contracts, adapters, error taxonomy, and ports.
"""

from windagent_providers.base import (
    # Errors
    ProviderFailure,
    AuthenticationFailure,
    PermissionFailure,
    RateLimitFailure,
    QuotaExhaustedFailure,
    ModelNotFoundFailure,
    InvalidRequestFailure,
    ContextOverflowFailure,
    ContentPolicyFailure,
    ProviderUnavailableFailure,
    NetworkFailure,
    TimeoutFailure,
    ProtocolMismatchFailure,
    MalformedResponseFailure,
    CancellationFailure,
    SameModelEndpointExhausted,
    # Contracts
    FinishReason,
    CacheDirective,
    ProviderUsage,
    ProviderHealth,
    QuotaState,
    RateLimitState,
    ProviderCapabilities,
    ModelDescriptor,
    DiscoveredModel,
    ConnectionTestResult,
    ProtocolDetectionResult,
    ProviderRequest,
    ProviderResponse,
    ProviderStreamEvent,
    # Ports
    EndpointRegistryPort,
    CanonicalModelRegistryPort,
    RouteLockPort,
    RouteAttemptPort,
    QuotaStatePort,
    EndpointStatePort,
    CachePort,
    UsageLedgerPort,
    # Capabilities & Redaction
    ModelCapability,
    ModelCapabilityProfile,
    KNOWN_MODEL_PROFILES,
    redact_text,
    redact_dict,
)
from windagent_providers.base import BaseModelProvider, QuotaSnapshot, ModelChunk

# V3 Canonical Model Registry & Equivalence Engine
from windagent_providers.registry import (
    normalize_model_id,
    NormalizedModelInfo,
    classify_equivalence,
    EquivalenceLevel,
    EquivalenceAssessment,
    CanonicalModelRegistryService,
)

# V3 Protocol Detection & Test Connect
from windagent_providers.detection import (
    EndpointDetector,
    ProbePlanRunner,
    sanitize_url,
)

# V3 OpenAI Compatible Transports and Vendor Adapters
from windagent_providers.openai_compatible import OpenAICompatibleTransport
from windagent_providers.openai import OpenAIProviderAdapter
from windagent_providers.openrouter import OpenRouterAdapter
from windagent_providers.nvidia import NvidiaNimAdapter
from windagent_providers.mistral import MistralProviderAdapter

# V3 Native Vendor Adapters
from windagent_providers.anthropic import AnthropicProviderAdapter
from windagent_providers.google import GoogleGeminiProviderAdapter
from windagent_providers.ollama import OllamaProviderAdapter
from windagent_providers.local import LocalOllamaManager

# V3 Provider Caches & Singleflight
from windagent_providers.cache import (
    InMemoryCacheBackend,
    InMemorySingleFlight,
    ResponseCacheService,
    DiscoveryCacheService,
    HealthCacheService,
    RouteLockCacheService,
    CacheNamespace,
    CacheTags,
)

# Legacy V2 Adapters
from windagent_providers.adapters.mock import MockProviderAdapter
from windagent_providers.adapters.openai_compatible import (
    OpenAICompatibleProviderAdapter,
)
from windagent_providers.adapters.anthropic import (
    AnthropicProviderAdapter as LegacyAnthropicAdapter,
)
from windagent_providers.adapters.google_gemini import (
    GoogleGeminiProviderAdapter as LegacyGoogleAdapter,
)
from windagent_providers.adapters.ollama import (
    OllamaProviderAdapter as LegacyOllamaAdapter,
)

__version__ = "3.0.0"

__all__ = [
    "ProviderFailure",
    "AuthenticationFailure",
    "PermissionFailure",
    "RateLimitFailure",
    "QuotaExhaustedFailure",
    "ModelNotFoundFailure",
    "InvalidRequestFailure",
    "ContextOverflowFailure",
    "ContentPolicyFailure",
    "ProviderUnavailableFailure",
    "NetworkFailure",
    "TimeoutFailure",
    "ProtocolMismatchFailure",
    "MalformedResponseFailure",
    "CancellationFailure",
    "SameModelEndpointExhausted",
    "FinishReason",
    "CacheDirective",
    "ProviderUsage",
    "ProviderHealth",
    "QuotaState",
    "RateLimitState",
    "ProviderCapabilities",
    "ModelDescriptor",
    "DiscoveredModel",
    "ConnectionTestResult",
    "ProtocolDetectionResult",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStreamEvent",
    "EndpointRegistryPort",
    "CanonicalModelRegistryPort",
    "RouteLockPort",
    "RouteAttemptPort",
    "QuotaStatePort",
    "EndpointStatePort",
    "CachePort",
    "UsageLedgerPort",
    "ModelCapability",
    "ModelCapabilityProfile",
    "KNOWN_MODEL_PROFILES",
    "redact_text",
    "redact_dict",
    "BaseModelProvider",
    "QuotaSnapshot",
    "ModelChunk",
    "normalize_model_id",
    "NormalizedModelInfo",
    "classify_equivalence",
    "EquivalenceLevel",
    "EquivalenceAssessment",
    "CanonicalModelRegistryService",
    "EndpointDetector",
    "ProbePlanRunner",
    "sanitize_url",
    "OpenAICompatibleTransport",
    "OpenAIProviderAdapter",
    "OpenRouterAdapter",
    "NvidiaNimAdapter",
    "MistralProviderAdapter",
    "AnthropicProviderAdapter",
    "GoogleGeminiProviderAdapter",
    "OllamaProviderAdapter",
    "LocalOllamaManager",
    "InMemoryCacheBackend",
    "InMemorySingleFlight",
    "ResponseCacheService",
    "DiscoveryCacheService",
    "HealthCacheService",
    "RouteLockCacheService",
    "CacheNamespace",
    "CacheTags",
    "MockProviderAdapter",
    "OpenAICompatibleProviderAdapter",
    "LegacyAnthropicAdapter",
    "LegacyGoogleAdapter",
    "LegacyOllamaAdapter",
]
