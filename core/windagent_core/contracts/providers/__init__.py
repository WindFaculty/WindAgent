"""Canonical Provider contracts for WindAgent Core (Phase 5).

Core owns request/response/usage contracts, ports, and implementation-independent
capability schemas. Provider adapters own transport, auth, and vendor specifics.
"""

from windagent_core.contracts.providers.requests import ProviderRequest
from windagent_core.contracts.providers.responses import (
    ProviderResponse,
    ProviderStreamChunk,
    ProviderToolCall,
)
from windagent_core.contracts.providers.usage import ProviderUsage
from windagent_core.contracts.providers.capabilities import (
    CacheDirective,
    ConnectionTestResult,
    DiscoveredModel,
    FinishReason,
    ModelDescriptor,
    ProtocolDetectionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStreamEvent,
    QuotaState,
    RateLimitState,
)
from windagent_core.contracts.providers.ports import (
    CachePort,
    CanonicalModelRegistryPort,
    EndpointRegistryPort,
    EndpointStatePort,
    QuotaStatePort,
    RouteAttemptPort,
    RouteLockPort,
    UsageLedgerPort,
)

__all__ = [
    "ProviderRequest",
    "ProviderResponse",
    "ProviderStreamChunk",
    "ProviderToolCall",
    "ProviderUsage",
    "CacheDirective",
    "ConnectionTestResult",
    "DiscoveredModel",
    "FinishReason",
    "ModelDescriptor",
    "ProtocolDetectionResult",
    "ProviderCapabilities",
    "ProviderHealth",
    "ProviderStreamEvent",
    "QuotaState",
    "RateLimitState",
    "CachePort",
    "CanonicalModelRegistryPort",
    "EndpointRegistryPort",
    "EndpointStatePort",
    "QuotaStatePort",
    "RouteAttemptPort",
    "RouteLockPort",
    "UsageLedgerPort",
]
