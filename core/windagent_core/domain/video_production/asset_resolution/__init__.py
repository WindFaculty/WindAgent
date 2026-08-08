"""
Universal Asset Gateway — provider-neutral domain (VP3D Phase 5, Stage C).

The gateway normalizes every 3D asset acquisition channel (local library,
Internet search, Mesh API, Mesh MCP, future generator) behind ONE canonical
request/result surface. Director and Scene Compiler never talk to a provider
directly; they only consume ``AssetRequirement`` -> ``AssetResolutionResult``
through ``AssetResolverPort``.

Rules enforced by this domain:

- ``AssetCandidate`` is a DISCOVERED result only — it is never an approved
  or usable asset on its own (discover is separated from acquire).
- ``AssetRequirement.canonical_hash`` is the idempotency key: the same
  requirement content resolved by the same adapter/version must produce the
  same cached outcome; lookup happens BEFORE any network/generation.
- Credentials never appear in requests, candidates, or receipts; providers
  only reference secrets by redacted reference.
- Any provider that cannot serve a requirement returns a typed rejection
  (``CapabilityRejectedError`` / ``NoCapableAdapterError``) instead of a
  partial or silent result.
"""

from windagent_core.domain.video_production.asset_resolution.enums import (
    AdapterKind,
    AssetKind,
    AssetResolutionStatus,
    AssetStyle,
    LicenseConstraint,
    ProviderAvailability,
    RigRequirement,
    TextureResolution,
    TopologyPolicy,
)
from windagent_core.domain.video_production.asset_resolution.errors import (
    AssetResolutionError,
    CapabilityRejectedError,
    CircuitOpenError,
    GenerationNotEnabledError,
    NoCapableAdapterError,
    ProviderExecutionError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ResolutionCancelledError,
    RetryBudgetExhaustedError,
    SecretLeakError,
)
from windagent_core.domain.video_production.asset_resolution.models import (
    AssetBudget,
    AssetCandidate,
    AssetProviderCapability,
    AssetRequirement,
    AssetResolutionAttempt,
    AssetResolutionRequest,
    AssetResolutionResult,
    AssetTrustEvidence,
    AssetTrustVerdict,
)

__all__ = [
    # enums
    "AdapterKind",
    "AssetKind",
    "AssetResolutionStatus",
    "AssetStyle",
    "LicenseConstraint",
    "ProviderAvailability",
    "RigRequirement",
    "TextureResolution",
    "TopologyPolicy",
    # errors
    "AssetResolutionError",
    "CapabilityRejectedError",
    "NoCapableAdapterError",
    "ProviderUnavailableError",
    "ProviderExecutionError",
    "ProviderTimeoutError",
    "CircuitOpenError",
    "RetryBudgetExhaustedError",
    "ResolutionCancelledError",
    "GenerationNotEnabledError",
    "SecretLeakError",
    # models
    "AssetBudget",
    "AssetRequirement",
    "AssetProviderCapability",
    "AssetCandidate",
    "AssetResolutionRequest",
    "AssetResolutionAttempt",
    "AssetTrustEvidence",
    "AssetTrustVerdict",
    "AssetResolutionResult",
]
