"""
WindAgent Providers Package (Architecture V3 Rebuild).
Modular model provider contracts, adapters, error taxonomy, and ports.
"""

from windagent_providers.base import (
    # Errors
    ProviderFailure, AuthenticationFailure, PermissionFailure, RateLimitFailure,
    QuotaExhaustedFailure, ModelNotFoundFailure, InvalidRequestFailure,
    ContextOverflowFailure, ContentPolicyFailure, ProviderUnavailableFailure,
    NetworkFailure, TimeoutFailure, ProtocolMismatchFailure, MalformedResponseFailure,
    CancellationFailure, SameModelEndpointExhausted,
    # Contracts
    FinishReason, CacheDirective, ProviderUsage, ProviderHealth, QuotaState,
    RateLimitState, ProviderCapabilities, ModelDescriptor, DiscoveredModel,
    ConnectionTestResult, ProtocolDetectionResult, ProviderRequest, ProviderResponse,
    ProviderStreamEvent,
    # Ports
    EndpointRegistryPort, CanonicalModelRegistryPort, RouteLockPort, RouteAttemptPort,
    QuotaStatePort, EndpointStatePort, CachePort, UsageLedgerPort,
    # Capabilities & Redaction
    ModelCapability, ModelCapabilityProfile, KNOWN_MODEL_PROFILES,
    redact_text, redact_dict
)
from windagent_providers.base import BaseModelProvider, QuotaSnapshot, ModelChunk
from windagent_providers.adapters.mock import MockProviderAdapter
from windagent_providers.adapters.openai_compatible import OpenAICompatibleProviderAdapter
from windagent_providers.adapters.anthropic import AnthropicProviderAdapter
from windagent_providers.adapters.google_gemini import GoogleGeminiProviderAdapter
from windagent_providers.adapters.ollama import OllamaProviderAdapter

__version__ = "3.0.0"

__all__ = [
    "ProviderFailure", "AuthenticationFailure", "PermissionFailure", "RateLimitFailure",
    "QuotaExhaustedFailure", "ModelNotFoundFailure", "InvalidRequestFailure",
    "ContextOverflowFailure", "ContentPolicyFailure", "ProviderUnavailableFailure",
    "NetworkFailure", "TimeoutFailure", "ProtocolMismatchFailure", "MalformedResponseFailure",
    "CancellationFailure", "SameModelEndpointExhausted",
    "FinishReason", "CacheDirective", "ProviderUsage", "ProviderHealth", "QuotaState",
    "RateLimitState", "ProviderCapabilities", "ModelDescriptor", "DiscoveredModel",
    "ConnectionTestResult", "ProtocolDetectionResult", "ProviderRequest", "ProviderResponse",
    "ProviderStreamEvent",
    "EndpointRegistryPort", "CanonicalModelRegistryPort", "RouteLockPort", "RouteAttemptPort",
    "QuotaStatePort", "EndpointStatePort", "CachePort", "UsageLedgerPort",
    "ModelCapability", "ModelCapabilityProfile", "KNOWN_MODEL_PROFILES",
    "redact_text", "redact_dict",
    "BaseModelProvider", "QuotaSnapshot", "ModelChunk",
    "MockProviderAdapter", "OpenAICompatibleProviderAdapter",
    "AnthropicProviderAdapter", "GoogleGeminiProviderAdapter", "OllamaProviderAdapter",
]
