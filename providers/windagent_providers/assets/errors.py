"""
Typed rejection re-exports for the Universal Asset Gateway (VP3D Phase 5).

All typed resolution failures live in the CORE domain
(``windagent_core.domain.video_production.asset_resolution.errors``) so the
port contract, adapters and consumers share ONE failure taxonomy. This module
re-exports them at the provider package root.
"""

from windagent_core.domain.video_production.asset_resolution import (
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

__all__ = [
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
]
