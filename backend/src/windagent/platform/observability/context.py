"""Causal operation context shared by HTTP, jobs, logs, and traces.

The context is deliberately vendor-neutral.  Trace identifiers follow the
W3C Trace Context wire format, while business causality keeps using the
kernel's nominal correlation, causation, and actor identifiers.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from secrets import token_hex
from typing import Self

from windagent.kernel.ids import ActorId, CausationId, CorrelationId
from windagent.kernel.types import validate_span_id, validate_trace_id

TRACEPARENT_HEADER = "traceparent"
TRACE_ID_HEADER = "x-trace-id"

_FLAGS_RE = re.compile(r"^[0-9a-f]{2}$")
_VERSION_RE = re.compile(r"^[0-9a-f]{2}$")


def new_trace_id() -> str:
    """Return a non-zero 128-bit W3C trace identifier."""
    return token_hex(16)


def new_span_id() -> str:
    """Return a non-zero 64-bit W3C span identifier."""
    return token_hex(8)


@dataclass(frozen=True, slots=True)
class TraceParent:
    """Parsed W3C ``traceparent`` header."""

    trace_id: str
    parent_id: str
    trace_flags: str = "01"
    version: str = "00"

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", validate_trace_id(self.trace_id))
        object.__setattr__(self, "parent_id", validate_span_id(self.parent_id))
        flags = self.trace_flags.strip().lower()
        version = self.version.strip().lower()
        if not _FLAGS_RE.fullmatch(flags):
            raise ValueError("trace_flags must be two lowercase hexadecimal characters")
        if not _VERSION_RE.fullmatch(version) or version == "ff":
            raise ValueError("traceparent version must be supported hexadecimal text")
        object.__setattr__(self, "trace_flags", flags)
        object.__setattr__(self, "version", version)

    @classmethod
    def parse(cls, value: str | None) -> Self | None:
        """Parse a header, returning ``None`` for malformed/untrusted input."""
        if not value:
            return None
        parts = value.strip().lower().split("-")
        if len(parts) != 4:
            return None
        try:
            return cls(
                version=parts[0],
                trace_id=parts[1],
                parent_id=parts[2],
                trace_flags=parts[3],
            )
        except (TypeError, ValueError):
            return None

    def __str__(self) -> str:
        return f"{self.version}-{self.trace_id}-{self.parent_id}-{self.trace_flags}"


@dataclass(frozen=True, slots=True)
class OperationContext:
    """Identity attached to one observable unit of work."""

    trace_id: str
    span_id: str
    correlation_id: CorrelationId
    causation_id: CausationId | None = None
    actor_id: ActorId | None = None
    parent_span_id: str | None = None
    trace_flags: str = "01"
    job_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trace_id", validate_trace_id(self.trace_id))
        object.__setattr__(self, "span_id", validate_span_id(self.span_id))
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("correlation_id must be a CorrelationId")
        if self.causation_id is not None and not isinstance(
            self.causation_id, CausationId
        ):
            raise TypeError("causation_id must be a CausationId or None")
        if self.actor_id is not None and not isinstance(self.actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId or None")
        if self.parent_span_id is not None:
            object.__setattr__(
                self, "parent_span_id", validate_span_id(self.parent_span_id)
            )
        flags = self.trace_flags.strip().lower()
        if not _FLAGS_RE.fullmatch(flags):
            raise ValueError("trace_flags must be two lowercase hexadecimal characters")
        object.__setattr__(self, "trace_flags", flags)
        for name in ("job_id", "run_id", "task_id"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _bounded_text(value, name))

    @classmethod
    def root(
        cls,
        *,
        trace_parent: TraceParent | None = None,
        trace_id: str | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationId | None = None,
        actor_id: ActorId | None = None,
        job_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> Self:
        """Create a local operation, continuing a remote trace when supplied."""
        if trace_parent is not None and trace_id is not None:
            raise ValueError("provide trace_parent or trace_id, not both")
        return cls(
            trace_id=(
                trace_parent.trace_id
                if trace_parent is not None
                else validate_trace_id(trace_id) if trace_id is not None else new_trace_id()
            ),
            span_id=new_span_id(),
            parent_span_id=trace_parent.parent_id if trace_parent is not None else None,
            trace_flags=trace_parent.trace_flags if trace_parent is not None else "01",
            correlation_id=correlation_id or CorrelationId.new(),
            causation_id=causation_id,
            actor_id=actor_id,
            job_id=job_id,
            run_id=run_id,
            task_id=task_id,
        )

    @property
    def traceparent(self) -> str:
        """Serialize the current span as a W3C propagation header."""
        return str(
            TraceParent(
                trace_id=self.trace_id,
                parent_id=self.span_id,
                trace_flags=self.trace_flags,
            )
        )

    def child(self) -> Self:
        """Create a child span while retaining all causal operation fields."""
        return replace(
            self,
            span_id=new_span_id(),
            parent_span_id=self.span_id,
        )

    def with_actor(self, actor_id: ActorId) -> Self:
        """Attach a verified actor without changing trace or causal identity."""
        if not isinstance(actor_id, ActorId):
            raise TypeError("actor_id must be an ActorId")
        return replace(self, actor_id=actor_id)

    def to_attributes(self) -> dict[str, str]:
        """Return low-cardinality-safe context fields for logs and spans."""
        attributes = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "correlation_id": str(self.correlation_id),
        }
        optional = {
            "parent_span_id": self.parent_span_id,
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
        }
        attributes.update({name: value for name, value in optional.items() if value})
        return attributes


_CURRENT_OPERATION: ContextVar[OperationContext | None] = ContextVar(
    "windagent_operation_context", default=None
)


def current_operation_context() -> OperationContext | None:
    """Return the context bound to the current async/task execution flow."""
    return _CURRENT_OPERATION.get()


@contextmanager
def bind_operation_context(context: OperationContext) -> Iterator[OperationContext]:
    """Bind a context and reliably restore the previous one afterwards."""
    if not isinstance(context, OperationContext):
        raise TypeError("context must be an OperationContext")
    token = _CURRENT_OPERATION.set(context)
    try:
        yield context
    finally:
        _CURRENT_OPERATION.reset(token)


def _bounded_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{name} must be non-empty text")
    if len(candidate) > 255:
        raise ValueError(f"{name} must not exceed 255 characters")
    return candidate
