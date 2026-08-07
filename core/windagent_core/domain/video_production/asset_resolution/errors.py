"""
Typed failures for the Universal Asset Gateway (VP3D Phase 5).

Every provider outcome that is not a successful resolution is a TYPED
rejection/error so the gateway and its callers can classify deterministically:
- capability mismatch is a typed ``CapabilityRejectedError`` (never a silent
  partial result);
- provider not configured/available is ``ProviderUnavailableError``;
- network/execution failures carry retryability and circuit-breaker semantics;
- any credential appearing in a request/artifact payload raises
  ``SecretLeakError`` (fail closed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.errors import VideoProductionProtocolError


class AssetResolutionError(VideoProductionProtocolError):
    """Base error for the Universal Asset Gateway boundary."""

    code = "ASSET_RESOLUTION_ERROR"
    category = "ASSET_RESOLUTION"

    def __init__(self, message: str, *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message, details=details)


class CapabilityRejectedError(AssetResolutionError):
    """Typed rejection: a provider does not support the requirement.

    Raised BEFORE any provider call — capability matching always precedes
    network/generation. ``reasons`` lists every unsatisfied constraint.
    """

    code = "ASSET_CAPABILITY_REJECTED"
    retryable = False

    def __init__(self, provider_id: str, reasons: List[str]) -> None:
        super().__init__(
            f"Provider {provider_id} cannot serve the requirement.",
            details={"provider_id": provider_id, "reasons": reasons},
        )


class NoCapableAdapterError(AssetResolutionError):
    """No registered adapter can satisfy the requirement (typed rejection)."""

    code = "ASSET_NO_CAPABLE_ADAPTER"
    retryable = False


class ProviderUnavailableError(AssetResolutionError):
    """Provider is not configured or not reachable (fail closed)."""

    code = "ASSET_PROVIDER_UNAVAILABLE"
    retryable = True


class ProviderExecutionError(AssetResolutionError):
    """Unexpected provider failure (treated as retryable).

    Generic adapter/transport failures are retried within the retry budget
    instead of being silently accepted or rejected at first attempt.
    """

    code = "ASSET_PROVIDER_EXECUTION"
    retryable = True


class ProviderTimeoutError(AssetResolutionError):
    """Provider call exceeded the request timeout budget."""

    code = "ASSET_PROVIDER_TIMEOUT"
    retryable = True


class CircuitOpenError(AssetResolutionError):
    """Provider circuit breaker is OPEN; the call was rejected before execution."""

    code = "ASSET_CIRCUIT_OPEN"
    retryable = True


class RetryBudgetExhaustedError(AssetResolutionError):
    """All retry attempts were consumed without success."""

    code = "ASSET_RETRY_BUDGET_EXHAUSTED"
    retryable = False


class ResolutionCancelledError(AssetResolutionError):
    """Resolution was cancelled before completion (no side effect published)."""

    code = "ASSET_RESOLUTION_CANCELLED"
    retryable = False


class GenerationNotEnabledError(AssetResolutionError):
    """A generator adapter was invoked but generation is not enabled.

    Typed rejection for the future generator slot: capabilities may advertise
    ``supports_generation``, but without an enabled generation backend the
    adapter refuses (fail closed) instead of fabricating an asset.
    """

    code = "ASSET_GENERATION_NOT_ENABLED"
    retryable = False


class SecretLeakError(AssetResolutionError):
    """A credential-like value leaked into a request/artifact payload.

    Requests, candidates and receipts must never carry credentials — only
    redacted secret references. This error is raised by the redaction guard
    before any payload is accepted or persisted.
    """

    code = "ASSET_SECRET_LEAK"
    retryable = False


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
