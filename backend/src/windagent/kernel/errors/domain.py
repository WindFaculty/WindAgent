"""Structured errors with no transport or framework dependency."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar


class DomainError(Exception):
    """A stable, expected failure that may be returned in a ``Result``.

    ``code`` is intentionally transport-neutral; API layers decide later how
    it maps to HTTP, RPC, or UI error representations.
    """

    default_code: ClassVar[str] = "domain_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        normalized_message = _required_text(message, "message")
        normalized_code = _required_text(code or self.default_code, "code")
        if context is not None and not isinstance(context, Mapping):
            raise TypeError("error context must be a mapping")
        if context is not None and not all(isinstance(key, str) for key in context):
            raise TypeError("error context keys must be strings")

        self.code = normalized_code
        self.message = normalized_message
        self.context: Mapping[str, object] = MappingProxyType(dict(context or {}))
        super().__init__(normalized_message)

    def to_dict(self) -> dict[str, object]:
        """Return a transport-neutral, serializable error representation."""

        return {"code": self.code, "message": self.message, "context": dict(self.context)}


class ValidationError(DomainError):
    """A generic validation failure for a kernel contract."""

    default_code = "validation_error"


class ResultUnwrapError(RuntimeError):
    """Raised only when a caller unwraps the wrong ``Result`` variant."""


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized
