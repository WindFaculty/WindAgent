"""Telemetry contracts, intentionally independent of a vendor SDK."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

type TelemetryValue = str | int | float | bool
type TelemetryAttributes = Mapping[str, TelemetryValue]


@runtime_checkable
class TelemetrySpan(Protocol):
    """An active span controlled by a telemetry implementation."""

    def set_attribute(self, name: str, value: TelemetryValue) -> None:
        """Attach a structured attribute to the active span."""

    def record_exception(self, error: BaseException) -> None:
        """Record an exception without deciding how it is exported."""

    def end(self) -> None:
        """Finish the span exactly once according to the implementation."""


@runtime_checkable
class Telemetry(Protocol):
    """Vendor-neutral structured logging, metrics, and tracing boundary."""

    def start_span(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> TelemetrySpan:
        """Start a trace span for an operation."""

    def emit_event(
        self, name: str, *, attributes: TelemetryAttributes | None = None
    ) -> None:
        """Emit a structured operational event."""

    def increment_counter(
        self, name: str, *, value: int = 1, attributes: TelemetryAttributes | None = None
    ) -> None:
        """Increase a named counter."""

    def observe_histogram(
        self, name: str, value: float, *, attributes: TelemetryAttributes | None = None
    ) -> None:
        """Record a numeric observation."""
