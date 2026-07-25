"""Provider subsystem stream-event re-export module (Phase 5).

Canonical capability/descriptor schemas now live in
``windagent_core.contracts.providers.capabilities``; this module re-exports
them so provider-internal modules keep a single import site.
"""

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
from windagent_core.contracts.providers import (
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)

__all__ = [
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
    "ProviderRequest",
    "ProviderResponse",
    "ProviderUsage",
]
