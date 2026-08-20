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
from windagent_core.contracts.providers.model_capabilities import (
    KNOWN_MODEL_PROFILES,
    ModelCapability,
    ModelCapabilityProfile,
)
from windagent_core.contracts.providers.ports import (
    CachePort,
    CanonicalModelRegistryPort,
    EndpointRegistryPort,
    EndpointStatePort,
    ModelExecutionPort,
    ModelRegistryPort,
    ProviderDiscoveryPort,
    ProviderHealthPort,
    QuotaStatePort,
    RouteAttemptPort,
    RouteLockPort,
    RoutingAuditPort,
    UsageLedgerPort,
)
from windagent_core.contracts.providers.provider_management import (
    ModelRuleRecord,
    ProviderAuditEvent,
    ProviderCredentialRecord,
    ProviderEndpointRecord,
    ProviderManagementRepositoryPort,
    ProviderProbeMaterial,
    ProviderProbeResult,
    ProviderVendorRecord,
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
    "ModelCapability",
    "ModelCapabilityProfile",
    "KNOWN_MODEL_PROFILES",
    "CachePort",
    "CanonicalModelRegistryPort",
    "EndpointRegistryPort",
    "EndpointStatePort",
    "QuotaStatePort",
    "RouteAttemptPort",
    "RouteLockPort",
    "UsageLedgerPort",
    "ModelExecutionPort",
    "ModelRegistryPort",
    "ProviderHealthPort",
    "ProviderDiscoveryPort",
    "RoutingAuditPort",
    "ProviderVendorRecord",
    "ProviderCredentialRecord",
    "ProviderEndpointRecord",
    "ModelRuleRecord",
    "ProviderProbeMaterial",
    "ProviderProbeResult",
    "ProviderAuditEvent",
    "ProviderManagementRepositoryPort",
]
