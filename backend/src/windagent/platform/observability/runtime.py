"""Concrete vendor-neutral telemetry runtime used by API and workers."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from time import perf_counter

from .context import OperationContext, current_operation_context
from .contracts import TelemetryAttributes, TelemetrySpan, TelemetryValue
from .metrics import MetricRegistry
from .structured_logging import redact


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    name: str
    occurred_at: datetime
    attributes: Mapping[str, TelemetryValue]


@dataclass(frozen=True, slots=True)
class SpanRecord:
    name: str
    started_at: datetime
    duration_ms: float
    attributes: Mapping[str, TelemetryValue]
    error_type: str | None = None


class RuntimeTelemetry:
    """Logs structured events/spans and aggregates bounded process metrics."""

    def __init__(
        self,
        service_name: str,
        *,
        metrics: MetricRegistry | None = None,
        logger: logging.Logger | None = None,
        record_limit: int = 1_000,
    ) -> None:
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValueError("service_name must be non-empty text")
        if record_limit < 0:
            raise ValueError("record_limit must be non-negative")
        self.service_name = service_name.strip()
        self.metrics = metrics or MetricRegistry()
        self._logger = logger or logging.getLogger(f"windagent.{self.service_name}")
        self._events: deque[TelemetryEvent] = deque(maxlen=record_limit)
        self._spans: deque[SpanRecord] = deque(maxlen=record_limit)
        self._lock = RLock()

    @property
    def events(self) -> tuple[TelemetryEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def spans(self) -> tuple[SpanRecord, ...]:
        with self._lock:
            return tuple(self._spans)

    def start_span(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> TelemetrySpan:
        return _RuntimeSpan(self, _required_name(name), attributes)

    def emit_event(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> None:
        event_name = _required_name(name)
        merged = self._attributes(attributes)
        event = TelemetryEvent(event_name, datetime.now(UTC), merged)
        with self._lock:
            self._events.append(event)
        self._logger.info(
            event_name,
            extra={
                "windagent_service": self.service_name,
                "windagent_event": event_name,
                "windagent_attributes": redact(merged),
            },
        )

    def increment_counter(
        self,
        name: str,
        *,
        value: int = 1,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        self.metrics.increment(name, value=value, attributes=attributes)

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        self.metrics.observe(name, value, attributes=attributes)

    def render_prometheus(self) -> str:
        return self.metrics.render_prometheus()

    def _finish_span(
        self,
        *,
        name: str,
        started_at: datetime,
        started_counter: float,
        attributes: Mapping[str, TelemetryValue],
        error_type: str | None,
    ) -> None:
        duration_ms = max(0.0, (perf_counter() - started_counter) * 1_000.0)
        record = SpanRecord(
            name=name,
            started_at=started_at,
            duration_ms=duration_ms,
            attributes=attributes,
            error_type=error_type,
        )
        with self._lock:
            self._spans.append(record)
        log_attributes: dict[str, TelemetryValue] = dict(attributes)
        log_attributes["duration_ms"] = duration_ms
        if error_type is not None:
            log_attributes["error.type"] = error_type
        self._logger.info(
            "span.finished",
            extra={
                "windagent_service": self.service_name,
                "windagent_event": "span.finished",
                "windagent_attributes": redact(log_attributes),
            },
        )

    def _attributes(
        self, attributes: TelemetryAttributes | None
    ) -> dict[str, TelemetryValue]:
        merged: dict[str, TelemetryValue] = {"service.name": self.service_name}
        context = current_operation_context()
        if context is not None:
            merged.update(context.to_attributes())
        if attributes is not None:
            if not isinstance(attributes, Mapping):
                raise TypeError("telemetry attributes must be a mapping")
            for name, value in attributes.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("telemetry attribute names must be non-empty text")
                if not isinstance(value, (str, int, float, bool)):
                    raise TypeError(f"telemetry attribute {name!r} has an unsupported value")
                merged[name.strip()] = value
        return merged


class InMemoryTelemetry(RuntimeTelemetry):
    """Quiet recorder for tests and embedded runtimes."""

    def __init__(self, service_name: str = "windagent-test") -> None:
        logger = logging.getLogger(f"windagent.null.{id(self)}")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        super().__init__(service_name, logger=logger, record_limit=10_000)


class NoOpTelemetry:
    """Explicit opt-out implementation; useful for narrow unit tests."""

    def start_span(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> TelemetrySpan:
        _required_name(name)
        return _NoOpSpan()

    def emit_event(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> None:
        _required_name(name)

    def increment_counter(
        self,
        name: str,
        *,
        value: int = 1,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        _required_name(name)

    def observe_histogram(
        self,
        name: str,
        value: float,
        *,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        _required_name(name)


class _RuntimeSpan:
    def __init__(
        self,
        telemetry: RuntimeTelemetry,
        name: str,
        attributes: TelemetryAttributes | None,
    ) -> None:
        self._telemetry = telemetry
        self._name = name
        self._started_at = datetime.now(UTC)
        self._started_counter = perf_counter()
        self._attributes = telemetry._attributes(attributes)
        self._error_type: str | None = None
        self._ended = False
        self._lock = RLock()

    def set_attribute(self, name: str, value: TelemetryValue) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("span attribute name must be non-empty text")
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError("span attribute value has an unsupported type")
        with self._lock:
            if self._ended:
                return
            self._attributes[name.strip()] = value

    def record_exception(self, error: BaseException) -> None:
        if not isinstance(error, BaseException):
            raise TypeError("error must be an exception")
        with self._lock:
            if not self._ended:
                self._error_type = type(error).__name__

    def end(self) -> None:
        with self._lock:
            if self._ended:
                return
            self._ended = True
            attributes = dict(self._attributes)
            error_type = self._error_type
        self._telemetry._finish_span(
            name=self._name,
            started_at=self._started_at,
            started_counter=self._started_counter,
            attributes=attributes,
            error_type=error_type,
        )


class _NoOpSpan:
    def set_attribute(self, name: str, value: TelemetryValue) -> None:
        return None

    def record_exception(self, error: BaseException) -> None:
        return None

    def end(self) -> None:
        return None


def operation_attributes(context: OperationContext | None = None) -> dict[str, str]:
    """Expose current causal fields for adapters that need explicit attributes."""
    selected = context or current_operation_context()
    return selected.to_attributes() if selected is not None else {}


def _required_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("telemetry name must be text")
    candidate = value.strip()
    if not candidate:
        raise ValueError("telemetry name must be non-empty text")
    return candidate
