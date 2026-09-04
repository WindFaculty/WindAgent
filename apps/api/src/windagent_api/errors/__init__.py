"""Canonical API error envelope and domain-to-HTTP mapping."""

from .handlers import ApiError, error_envelope, install_error_handlers
from .mapping import DomainErrorStatusMapper, status_for_domain_error

__all__ = [
    "ApiError",
    "DomainErrorStatusMapper",
    "error_envelope",
    "install_error_handlers",
    "status_for_domain_error",
]
