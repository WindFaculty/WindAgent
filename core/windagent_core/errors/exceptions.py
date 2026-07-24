"""
Structured Error Hierarchy for WindAgent Architecture V2 (Phase 6).
All errors feature stable error codes, retryability flags, category taxonomy, and sanitized metadata.
"""

from __future__ import annotations
import re
from typing import Any, Dict, Optional


_SENSITIVE_KEY_REGEX = re.compile(r"(?i)(key|secret|token|password|auth|credential)")


def sanitize_error_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize error details dictionary by masking sensitive fields."""
    sanitized: Dict[str, Any] = {}
    for k, v in details.items():
        if isinstance(v, dict):
            sanitized[k] = sanitize_error_details(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_error_details(item) if isinstance(item, dict) else item
                for item in v
            ]
        elif _SENSITIVE_KEY_REGEX.search(k):
            sanitized[k] = "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized


class WindAgentError(Exception):
    """Base exception for all WindAgent domain errors."""
    code: str = "WINDAGENT_ERR_GENERIC"
    category: str = "GENERIC"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        retryable: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = sanitize_error_details(details or {})
        self.cause_type = cause.__class__.__name__ if cause else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
            "cause_type": self.cause_type,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, retryable={self.retryable})"


class DomainError(WindAgentError):
    """Raised when a business domain rule is violated."""
    code = "WINDAGENT_ERR_DOMAIN"
    category = "DOMAIN"


class ValidationError(WindAgentError):
    """Raised when request payload or entity fields fail validation."""
    code = "WINDAGENT_ERR_VALIDATION"
    category = "VALIDATION"
    retryable = False


class IdentityValidationError(ValidationError):
    """Raised when an identifier fails UUID or Opaque ID validation."""
    code = "WINDAGENT_ERR_IDENTITY_VALIDATION"
    category = "IDENTITY_VALIDATION"
    retryable = False


class ConflictError(WindAgentError):
    """Raised when a resource or state conflict occurs."""
    code = "WINDAGENT_ERR_CONFLICT"
    category = "CONFLICT"
    retryable = False


class InvalidStateTransitionError(DomainError):
    """Raised when an illegal lifecycle state transition is attempted."""
    code = "WINDAGENT_ERR_INVALID_STATE_TRANSITION"
    category = "STATE_TRANSITION"
    retryable = False


class TerminalStateMutationError(DomainError):
    """Raised when a mutation is attempted on a terminal aggregate state."""
    code = "WINDAGENT_ERR_TERMINAL_STATE_MUTATION"
    category = "STATE_TRANSITION"
    retryable = False


class ConcurrentStateConflictError(ConflictError):
    """Raised when an expected state version does not match during state transition."""
    code = "WINDAGENT_ERR_CONCURRENT_STATE_CONFLICT"
    category = "CONCURRENCY"
    retryable = True


class NotFoundError(WindAgentError):
    """Raised when a requested resource or entity is not found."""
    code = "WINDAGENT_ERR_NOT_FOUND"
    category = "NOT_FOUND"
    retryable = False


class PermissionDeniedError(WindAgentError):
    """Raised when an operation or tool execution is denied by security policies."""
    code = "WINDAGENT_ERR_PERMISSION_DENIED"
    category = "SECURITY"
    retryable = False


class ApprovalRequiredError(WindAgentError):
    """Raised when an operation requires explicit user or admin approval."""
    code = "WINDAGENT_ERR_APPROVAL_REQUIRED"
    category = "SECURITY"
    retryable = False


class ExecutionError(WindAgentError):
    """Raised when a step or runtime execution fails."""
    code = "WINDAGENT_ERR_EXECUTION"
    category = "EXECUTION"
    retryable = False


class RuntimeLostError(ExecutionError):
    """Raised when an execution worker or runtime lease is lost."""
    code = "WINDAGENT_ERR_RUNTIME_LOST"
    category = "EXECUTION"
    retryable = True


class ProviderError(WindAgentError):
    """Raised when an LLM provider or external service encounters an error."""
    code = "WINDAGENT_ERR_PROVIDER"
    category = "PROVIDER"

    def __init__(
        self,
        message: str,
        provider_name: str = "unknown",
        status_code: Optional[int] = None,
        retryable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        merged_details["provider_name"] = provider_name
        if status_code is not None:
            merged_details["status_code"] = status_code
        super().__init__(message, code=self.code, retryable=retryable, details=merged_details)


class RateLimitError(ProviderError):
    """Raised when an LLM provider rate limit is exceeded."""
    code = "WINDAGENT_ERR_RATE_LIMIT"
    category = "PROVIDER"
    retryable = True


class QuotaExhaustedError(ProviderError):
    """Raised when provider credit or quota is exhausted."""
    code = "WINDAGENT_ERR_QUOTA_EXHAUSTED"
    category = "PROVIDER"
    retryable = False


class AuthenticationError(ProviderError):
    """Raised when provider API key or authentication credentials fail."""
    code = "WINDAGENT_ERR_AUTHENTICATION"
    category = "PROVIDER"
    retryable = False


class TimeoutError(WindAgentError):
    """Raised when an operation or request exceeds its configured deadline."""
    code = "WINDAGENT_ERR_TIMEOUT"
    category = "TIMEOUT"
    retryable = True


class ToolError(WindAgentError):
    """Raised when a tool execution fails or encounters an execution error."""
    code = "WINDAGENT_ERR_TOOL"
    category = "TOOL"

    def __init__(
        self,
        message: str,
        tool_name: str = "unknown",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        merged_details["tool_name"] = tool_name
        super().__init__(message, code=self.code, retryable=retryable, details=merged_details)


class ToolExecutionError(ToolError):
    """Raised when tool execution fails."""
    pass


class SerializationError(WindAgentError):
    """Raised when serialization or deserialization of domain entities fails."""
    code = "WINDAGENT_ERR_SERIALIZATION"
    category = "SERIALIZATION"
    retryable = False


class IntegrityError(WindAgentError):
    """Raised when system invariant or storage integrity fails."""
    code = "WINDAGENT_ERR_INTEGRITY"
    category = "INTEGRITY"
    retryable = False


class ConfigurationError(WindAgentError):
    """Raised when system or application configuration is invalid or missing."""
    code = "WINDAGENT_ERR_CONFIGURATION"
    category = "CONFIGURATION"
    retryable = False


class RetryableError(WindAgentError):
    """Base class for errors that can be safely retried."""
    code = "WINDAGENT_ERR_RETRYABLE"
    category = "RETRYABLE"
    retryable = True


class NonRetryableError(WindAgentError):
    """Base class for fatal, non-retryable errors."""
    code = "WINDAGENT_ERR_NON_RETRYABLE"
    category = "NON_RETRYABLE"
    retryable = False
