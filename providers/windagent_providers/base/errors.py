"""
Normalized Error Taxonomy for WindAgent Provider Routing Subsystem V3.
Eliminates string-matching error classification in application layers.
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from windagent_core.errors.exceptions import ProviderError
from windagent_providers.base.secret_redaction import redact_text


class ProviderFailure(ProviderError):
    """Root Exception for all Provider Subsystem V3 failures, extending windagent_core ProviderError."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        status_code: Optional[int] = None,
        raw_error: Optional[Any] = None,
        retryable: bool = False,
    ):
        clean_msg = redact_text(message)
        self.provider_id = provider_id
        self.model_id = model_id
        self.endpoint_id = endpoint_id
        self.status_code = status_code
        self.raw_error = raw_error
        super().__init__(
            message=clean_msg,
            provider_name=provider_id or "unknown",
            status_code=status_code,
            retryable=retryable,
            details={
                "model_id": model_id,
                "endpoint_id": endpoint_id,
                "status_code": status_code,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "endpoint_id": self.endpoint_id,
            "status_code": self.status_code,
            "retryable": self.retryable,
        }


class AuthenticationFailure(ProviderFailure):
    """401 Unauthorized / Invalid API key."""

    def __init__(
        self,
        message: str = "Invalid authentication credentials or API key",
        **kwargs: Any,
    ):
        kwargs.setdefault("status_code", 401)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class PermissionFailure(ProviderFailure):
    """403 Forbidden / Insufficient permissions for model or operation."""

    def __init__(
        self,
        message: str = "Permission denied for requested model or endpoint",
        **kwargs: Any,
    ):
        kwargs.setdefault("status_code", 403)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class RateLimitFailure(ProviderFailure):
    """429 Too Many Requests / RPM/TPM limit exceeded."""

    def __init__(
        self, message: str = "Provider rate limit exceeded (429)", **kwargs: Any
    ):
        kwargs.setdefault("status_code", 429)
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class QuotaExhaustedFailure(ProviderFailure):
    """Quota or credit balance exhausted."""

    def __init__(
        self,
        message: str = "Provider quota or credit balance has been exhausted",
        **kwargs: Any,
    ):
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class ModelNotFoundFailure(ProviderFailure):
    """404 / Model not found on target endpoint."""

    def __init__(
        self,
        message: str = "Target model not found on provider endpoint",
        **kwargs: Any,
    ):
        kwargs.setdefault("status_code", 404)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class InvalidRequestFailure(ProviderFailure):
    """400 Bad Request / Invalid payload schema."""

    def __init__(
        self, message: str = "Invalid request payload parameters", **kwargs: Any
    ):
        kwargs.setdefault("status_code", 400)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class ContextOverflowFailure(ProviderFailure):
    """Prompt tokens exceed context window limit."""

    def __init__(self, message: str = "Context window length exceeded", **kwargs: Any):
        kwargs.setdefault("status_code", 400)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class ContentPolicyFailure(ProviderFailure):
    """Safety / Content policy violation block."""

    def __init__(
        self,
        message: str = "Request or completion blocked by content policy filter",
        **kwargs: Any,
    ):
        kwargs.setdefault("status_code", 400)
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class ProviderUnavailableFailure(ProviderFailure):
    """503 Service Unavailable / Endpoint outage."""

    def __init__(
        self,
        message: str = "Provider service unavailable or server error (5xx)",
        **kwargs: Any,
    ):
        kwargs.setdefault("status_code", 503)
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class NetworkFailure(ProviderFailure):
    """Connection error / DNS resolution failure."""

    def __init__(
        self,
        message: str = "Network connection failure to provider endpoint",
        **kwargs: Any,
    ):
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class TimeoutFailure(ProviderFailure):
    """Request timed out waiting for response."""

    def __init__(self, message: str = "Request execution timed out", **kwargs: Any):
        kwargs.setdefault("status_code", 408)
        kwargs.setdefault("retryable", True)
        super().__init__(message, **kwargs)


class ProtocolMismatchFailure(ProviderFailure):
    """Endpoint returned response not adhering to expected protocol (e.g. HTML instead of JSON)."""

    def __init__(
        self,
        message: str = "Protocol mismatch detected during transport execution",
        **kwargs: Any,
    ):
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class MalformedResponseFailure(ProviderFailure):
    """Failed to parse response JSON or stream chunks."""

    def __init__(
        self,
        message: str = "Malformed or unparseable response payload from provider",
        **kwargs: Any,
    ):
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class CancellationFailure(ProviderFailure):
    """Call was cancelled via cancellation token."""

    def __init__(self, message: str = "Model execution was cancelled", **kwargs: Any):
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)


class SameModelEndpointExhausted(ProviderFailure):
    """Raised when ALL exact-equivalent endpoints for the locked canonical model are unavailable/failed."""

    def __init__(
        self,
        message: str = "All exact-equivalent endpoints for the locked canonical model are exhausted",
        **kwargs: Any,
    ):
        kwargs.setdefault("retryable", False)
        super().__init__(message, **kwargs)
