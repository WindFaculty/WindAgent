"""Transport-neutral error code to HTTP status mapping.

``DomainError.code`` is deliberately transport-neutral (kernel contract);
this mapper is the single place in the API that decides what a code means on
the wire.  Unmapped codes fail closed with 500 so a new domain code can never
silently masquerade as a client error.
"""

from __future__ import annotations

from typing import Final

from windagent.kernel.errors.domain import DomainError

_MIN_STATUS = 400
_MAX_STATUS = 599

DEFAULT_CODE_STATUS: Final[dict[str, int]] = {
    "unauthorized": 401,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
    "validation_error": 400,
    "rate_limited": 429,
}

DEFAULT_STATUS: Final[int] = 500


def status_for_domain_error(error: DomainError) -> int:
    """Return the HTTP status for ``error`` using the default code map."""
    return DEFAULT_CODE_STATUS.get(error.code, DEFAULT_STATUS)


class DomainErrorStatusMapper:
    """Extensible code-to-status mapping owned by the composition root."""

    def __init__(self, statuses: dict[str, int] | None = None) -> None:
        self._statuses: dict[str, int] = dict(DEFAULT_CODE_STATUS)
        if statuses is not None:
            for code, status in statuses.items():
                self.register(code, status)

    def register(self, code: str, status: int) -> None:
        """Bind one stable domain code to one HTTP status."""
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must be non-empty text")
        if not _MIN_STATUS <= status <= _MAX_STATUS:
            raise ValueError(f"status must be between {_MIN_STATUS} and {_MAX_STATUS}")
        self._statuses[code.strip()] = status

    def status_for(self, error: DomainError) -> int:
        """Return the HTTP status for ``error``, failing closed on 500."""
        return self._statuses.get(error.code, DEFAULT_STATUS)
