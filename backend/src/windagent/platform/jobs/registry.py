"""Deterministic single-owner registry for job handlers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import JobHandler
from .errors import DuplicateJobHandlerError, UnknownJobTypeError


def _job_type_of(handler: JobHandler) -> str:
    value = handler.job_type
    if not isinstance(value, str) or not value.strip():
        raise ValueError("handler.job_type must be non-empty text")
    if not callable(getattr(handler, "handle", None)):
        raise TypeError("handler must expose an async handle method")
    return value.strip()


@dataclass(slots=True)
class JobHandlerRegistry:
    """Own the one-to-one mapping used by every worker process."""

    _handlers: dict[str, JobHandler] = field(default_factory=dict, init=False)

    def register(self, handler: JobHandler, *, job_type: str | None = None) -> None:
        key = _job_type_of(handler) if job_type is None else job_type.strip()
        if not key:
            raise ValueError("job_type must be non-empty text")
        if key in self._handlers:
            raise DuplicateJobHandlerError(f"job type {key!r} already has a handler")
        self._handlers[key] = handler

    def get(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type.strip())

    def require(self, job_type: str) -> JobHandler:
        handler = self.get(job_type)
        if handler is None:
            raise UnknownJobTypeError(f"no handler registered for job type {job_type!r}")
        return handler

    def all_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
