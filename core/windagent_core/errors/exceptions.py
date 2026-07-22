"""
Structured Error Hierarchy for WindAgent Architecture V2.
All errors feature stable error codes, retryability flags, and sanitized metadata.
"""

from __future__ import annotations
from typing import Any, Dict, Optional


class WindAgentError(Exception):
    """Base exception for all WindAgent domain errors."""
    code: str = "WINDAGENT_ERR_GENERIC"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        retryable: Optional[bool] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r}, retryable={self.retryable})"


class DomainError(WindAgentError):
    """Raised when a business domain rule is violated."""
    code = "WINDAGENT_ERR_DOMAIN"


class ValidationError(WindAgentError):
    """Raised when request payload or entity fields fail validation."""
    code = "WINDAGENT_ERR_VALIDATION"
    retryable = False


class ConflictError(WindAgentError):
    """Raised when a resource or state conflict occurs."""
    code = "WINDAGENT_ERR_CONFLICT"
    retryable = False


class NotFoundError(WindAgentError):
    """Raised when a requested resource or entity is not found."""
    code = "WINDAGENT_ERR_NOT_FOUND"
    retryable = False


class PermissionDeniedError(WindAgentError):
    """Raised when an operation or tool execution is denied by security policies."""
    code = "WINDAGENT_ERR_PERMISSION_DENIED"
    retryable = False


class RetryableError(WindAgentError):
    """Base class for errors that can be safely retried."""
    code = "WINDAGENT_ERR_RETRYABLE"
    retryable = True


class NonRetryableError(WindAgentError):
    """Base class for fatal, non-retryable errors."""
    code = "WINDAGENT_ERR_NON_RETRYABLE"
    retryable = False


class ProviderError(WindAgentError):
    """Raised when an LLM provider or external service encounters an error."""
    code = "WINDAGENT_ERR_PROVIDER"

    def __init__(
        self,
        message: str,
        provider_name: str,
        status_code: Optional[int] = None,
        retryable: bool = True,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        merged_details["provider_name"] = provider_name
        if status_code is not None:
            merged_details["status_code"] = status_code
        super().__init__(message, code=self.code, retryable=retryable, details=merged_details)


class ToolError(WindAgentError):
    """Raised when a tool execution fails or encounters a execution error."""
    code = "WINDAGENT_ERR_TOOL"

    def __init__(
        self,
        message: str,
        tool_name: str,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged_details = details or {}
        merged_details["tool_name"] = tool_name
        super().__init__(message, code=self.code, retryable=retryable, details=merged_details)


class IntegrityError(WindAgentError):
    """Raised when system invariant or storage integrity fails."""
    code = "WINDAGENT_ERR_INTEGRITY"
    retryable = False
