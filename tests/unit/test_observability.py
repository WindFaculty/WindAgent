"""Phase 10 observability context, logging, metrics, and tracing tests."""

from __future__ import annotations

import json
import logging

import pytest
from windagent.kernel.ids import ActorId, CausationId, CorrelationId
from windagent.platform.observability import (
    InMemoryTelemetry,
    JsonLogFormatter,
    MetricRegistry,
    OperationContext,
    TraceParent,
    bind_operation_context,
    current_operation_context,
    redact,
)


def test_traceparent_continues_trace_with_a_new_local_span() -> None:
    parent = TraceParent.parse(
        "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    )
    assert parent is not None

    context = OperationContext.root(
        trace_parent=parent,
        correlation_id=CorrelationId.new(),
        causation_id=CausationId.new(),
    )

    assert context.trace_id == parent.trace_id
    assert context.parent_span_id == parent.parent_id
    assert context.span_id != parent.parent_id
    assert context.traceparent.startswith(f"00-{parent.trace_id}-{context.span_id}-")


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "00-short-00f067aa0ba902b7-01",
        "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
        "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    ],
)
def test_untrusted_traceparent_values_are_ignored(value: str | None) -> None:
    assert TraceParent.parse(value) is None


def test_operation_context_is_task_local_and_restored() -> None:
    context = OperationContext.root(
        correlation_id=CorrelationId.new(), actor_id=ActorId.new()
    )
    assert current_operation_context() is None
    with bind_operation_context(context):
        assert current_operation_context() == context
        child = context.child()
        assert child.trace_id == context.trace_id
        assert child.parent_span_id == context.span_id
    assert current_operation_context() is None


def test_metric_registry_aggregates_and_bounds_series() -> None:
    metrics = MetricRegistry(max_series=2)
    metrics.increment("http.server.requests", attributes={"method": "GET"})
    metrics.increment("http.server.requests", value=2, attributes={"method": "GET"})
    metrics.observe("http.server.duration_ms", 12.5, attributes={"method": "GET"})
    metrics.increment("worker.jobs", attributes={"outcome": "succeeded"})

    assert metrics.counters()[0].value == 3
    assert metrics.histograms()[0].count == 1
    assert metrics.dropped_series == 1
    document = metrics.render_prometheus()
    assert 'http_server_requests_total{method="GET"} 3' in document
    assert 'http_server_duration_ms_sum{method="GET"} 12.5' in document
    assert "windagent_metrics_dropped_series_total 1" in document


def test_runtime_telemetry_attaches_context_and_ends_span_once() -> None:
    telemetry = InMemoryTelemetry()
    context = OperationContext.root(correlation_id=CorrelationId.new())
    with bind_operation_context(context):
        span = telemetry.start_span("test.operation", attributes={"kind": "unit"})
        span.set_attribute("outcome", "ok")
        telemetry.emit_event("test.completed", attributes={"count": 1})
        span.end()
        span.end()

    assert len(telemetry.spans) == 1
    assert telemetry.spans[0].attributes["trace_id"] == context.trace_id
    assert telemetry.spans[0].attributes["outcome"] == "ok"
    assert telemetry.events[0].attributes["correlation_id"] == str(
        context.correlation_id
    )


def test_json_logging_redacts_secrets_and_includes_causal_context() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        "windagent.test", logging.INFO, __file__, 1, "handled", (), None
    )
    record.windagent_attributes = {
        "authorization": "Bearer hidden",
        "nested": {"api_key": "hidden", "safe": "visible"},
    }
    context = OperationContext.root(correlation_id=CorrelationId.new())
    with bind_operation_context(context):
        document = json.loads(formatter.format(record))

    assert document["trace_id"] == context.trace_id
    assert document["attributes"]["authorization"] == "[REDACTED]"
    assert document["attributes"]["nested"]["api_key"] == "[REDACTED]"
    assert document["attributes"]["nested"]["safe"] == "visible"
    assert redact({"password": "hidden"}) == {"password": "[REDACTED]"}
