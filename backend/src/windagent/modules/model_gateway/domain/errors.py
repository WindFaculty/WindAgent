"""Model-gateway error taxonomy.

Ported behavior from the frozen ``providers/windagent_providers/base/errors.py``
plus the routing errors of ``route_lock_service`` / ``endpoint_selector``.
Every failure is a kernel ``DomainError``; codes follow the canonical mapped
set (``not_found``, ``conflict``, ``validation_error``, ``rate_limited``) so
the composition-root mapper can translate them without modification, while
diagnostic detail travels in ``context``.
"""

from __future__ import annotations

from typing import ClassVar

from windagent.kernel.errors import DomainError


class ModelGatewayError(DomainError):
    """Base class for every model-gateway domain failure."""

    default_code: ClassVar[str] = "model_gateway_error"

    def __init__(
        self, message: str, *, context: dict[str, object] | None = None
    ) -> None:
        normalized = message if message.strip() else "model gateway failure"
        super().__init__(normalized, context=context)


class ModelGatewayValidationError(ModelGatewayError):
    """A request or registration payload violated a module invariant."""

    default_code = "validation_error"


# --------------------------------------------------------------------------- #
# Registry errors
# --------------------------------------------------------------------------- #


class DuplicateProviderError(ModelGatewayError):
    """A provider with the same identity is already registered."""

    default_code = "conflict"


class ProviderNotFoundError(ModelGatewayError):
    """The referenced provider, endpoint, or credential does not exist."""

    default_code = "not_found"


class ProviderInUseError(ModelGatewayError):
    """A provider cannot be deleted because routing rules still reference it."""

    default_code = "conflict"


class RuleNotFoundError(ModelGatewayError):
    """The referenced routing rule does not exist."""

    default_code = "not_found"


class RuleVersionConflictError(ModelGatewayError):
    """An optimistic rule update lost a race with a concurrent writer."""

    default_code = "conflict"


# --------------------------------------------------------------------------- #
# Routing errors
# --------------------------------------------------------------------------- #


class NoMatchingRuleError(ModelGatewayError):
    """No enabled routing rule matches the request context (fail closed)."""

    default_code = "not_found"


class CanonicalModelDisabledError(ModelGatewayError):
    """The selected canonical model is disabled for routing."""

    default_code = "conflict"


class RouteLockNotFoundError(ModelGatewayError):
    """The referenced route lock does not exist or was already released."""

    default_code = "not_found"


class RoutingUnavailableError(ModelGatewayError):
    """Routing could not produce a usable decision (fail closed, no random model)."""

    default_code = "not_found"


# --------------------------------------------------------------------------- #
# Provider protocol failures (EXTRACT_LOGIC of the old base/errors.py)
# --------------------------------------------------------------------------- #


class ProviderFailure(ModelGatewayError):
    """Root failure for every provider transport execution.

    Subclasses declare stable class-level defaults (``kind``, retryable,
    HTTP status, message); the effective values preserve the old taxonomy's
    semantics while remaining overridable at the raise site.  ``kind`` is the
    stable classification string consumed by the failover policy, receipts,
    and endpoint state.
    """

    kind: ClassVar[str] = "provider_failure"
    default_code: ClassVar[str] = "model_invocation_failed"
    default_retryable: ClassVar[bool] = False
    default_status: ClassVar[int | None] = None
    default_message: ClassVar[str] = "Provider execution failed"

    def __init__(
        self,
        message: str | None = None,
        *,
        provider_id: str | None = None,
        model_id: str | None = None,
        endpoint_id: str | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        resolved_message = (
            message if message is not None and message.strip() else self.default_message
        )
        resolved_context: dict[str, object] = dict(context or {})
        resolved_context.setdefault("kind", self.kind)
        if provider_id is not None:
            resolved_context.setdefault("provider_id", provider_id)
        if model_id is not None:
            resolved_context.setdefault("model_id", model_id)
        if endpoint_id is not None:
            resolved_context.setdefault("endpoint_id", endpoint_id)
        resolved_status = status_code if status_code is not None else self.default_status
        if resolved_status is not None:
            resolved_context.setdefault("status_code", resolved_status)
        effective_retryable = self.default_retryable if retryable is None else retryable
        resolved_context.setdefault("retryable", effective_retryable)

        super().__init__(resolved_message, context=resolved_context)
        self.provider_id = provider_id
        self.model_id = model_id
        self.endpoint_id = endpoint_id
        self.status_code = resolved_status
        self.retryable = effective_retryable


class AuthenticationFailure(ProviderFailure):
    """401 Unauthorized / invalid API key."""

    kind = "authentication"
    default_status = 401
    default_message = "Invalid authentication credentials or API key"


class PermissionFailure(ProviderFailure):
    """403 Forbidden / insufficient permissions for the model or operation."""

    kind = "permission"
    default_status = 403
    default_message = "Permission denied for requested model or endpoint"


class RateLimitFailure(ProviderFailure):
    """429 Too Many Requests / RPM or TPM limit exceeded."""

    kind = "rate_limit"
    default_code = "rate_limited"
    default_retryable = True
    default_status = 429
    default_message = "Provider rate limit exceeded (429)"


class QuotaExhaustedFailure(ProviderFailure):
    """Provider quota or credit balance exhausted."""

    kind = "quota_exhausted"
    default_code = "rate_limited"
    default_message = "Provider quota or credit balance has been exhausted"


class ModelNotFoundFailure(ProviderFailure):
    """404 / the target model does not exist on the provider endpoint."""

    kind = "model_not_found"
    default_status = 404
    default_message = "Target model not found on provider endpoint"


class InvalidRequestFailure(ProviderFailure):
    """400 Bad Request / invalid payload schema."""

    kind = "invalid_request"
    default_status = 400
    default_message = "Invalid request payload parameters"


class ContextOverflowFailure(ProviderFailure):
    """Prompt tokens exceed the model context window."""

    kind = "context_overflow"
    default_status = 400
    default_message = "Context window length exceeded"


class ContentPolicyFailure(ProviderFailure):
    """Safety or content-policy violation block."""

    kind = "content_policy"
    default_status = 400
    default_message = "Request or completion blocked by content policy filter"


class ProviderUnavailableFailure(ProviderFailure):
    """5xx / endpoint outage."""

    kind = "provider_unavailable"
    default_retryable = True
    default_status = 503
    default_message = "Provider service unavailable or server error (5xx)"


class NetworkFailure(ProviderFailure):
    """Connection error / DNS resolution failure."""

    kind = "network"
    default_retryable = True
    default_message = "Network connection failure to provider endpoint"


class TimeoutFailure(ProviderFailure):
    """Request timed out waiting for a response."""

    kind = "timeout"
    default_retryable = True
    default_status = 408
    default_message = "Request execution timed out"


class ProtocolMismatchFailure(ProviderFailure):
    """The endpoint response did not adhere to the expected protocol."""

    kind = "protocol_mismatch"
    default_message = "Protocol mismatch detected during transport execution"


class MalformedResponseFailure(ProviderFailure):
    """The response JSON or stream chunks could not be parsed."""

    kind = "malformed_response"
    default_message = "Malformed or unparseable response payload from provider"


class CancellationFailure(ProviderFailure):
    """The call was cancelled by the caller."""

    kind = "cancellation"
    default_message = "Model execution was cancelled"


class SameModelEndpointExhausted(ProviderFailure):
    """Every exact-equivalent endpoint for the locked model is unavailable."""

    kind = "same_model_endpoint_exhausted"
    default_code = "rate_limited"
    default_message = (
        "All exact-equivalent endpoints for the locked canonical model are exhausted"
    )


class ModelInvocationFailed(ModelGatewayError):
    """The invocation exhausted its failover budget without a usable response."""

    default_code = "model_invocation_failed"

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_kind: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        resolved: dict[str, object] = dict(context or {})
        resolved["attempts"] = attempts
        if last_kind is not None:
            resolved["last_error_kind"] = last_kind
        super().__init__(message, context=resolved)
