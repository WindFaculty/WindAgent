"""Phase 10 observability contracts and vendor-neutral runtime."""

from windagent.kernel.types import validate_span_id, validate_trace_id

from .context import (
    TRACE_ID_HEADER,
    TRACEPARENT_HEADER,
    OperationContext,
    TraceParent,
    bind_operation_context,
    current_operation_context,
    new_span_id,
    new_trace_id,
)
from .contracts import Telemetry, TelemetryAttributes, TelemetrySpan, TelemetryValue
from .metrics import (
    CounterSample,
    HistogramSample,
    MetricRegistry,
    MetricsExporter,
)
from .runtime import (
    InMemoryTelemetry,
    NoOpTelemetry,
    RuntimeTelemetry,
    SpanRecord,
    TelemetryEvent,
    operation_attributes,
)
from .structured_logging import JsonLogFormatter, configure_structured_logging, redact

__all__ = [
    "TRACEPARENT_HEADER",
    "TRACE_ID_HEADER",
    "CounterSample",
    "HistogramSample",
    "InMemoryTelemetry",
    "JsonLogFormatter",
    "MetricRegistry",
    "MetricsExporter",
    "NoOpTelemetry",
    "OperationContext",
    "RuntimeTelemetry",
    "SpanRecord",
    "Telemetry",
    "TelemetryAttributes",
    "TelemetryEvent",
    "TelemetrySpan",
    "TelemetryValue",
    "TraceParent",
    "bind_operation_context",
    "configure_structured_logging",
    "current_operation_context",
    "new_span_id",
    "new_trace_id",
    "operation_attributes",
    "redact",
    "validate_span_id",
    "validate_trace_id",
]
