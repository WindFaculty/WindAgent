"""Per-request causal context, tracing, metrics, and propagation headers."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from windagent.kernel.ids import CausationId, CorrelationId
from windagent.platform.observability import (
    TRACE_ID_HEADER as OBSERVABILITY_TRACE_ID_HEADER,
)
from windagent.platform.observability import (
    TRACEPARENT_HEADER as OBSERVABILITY_TRACEPARENT_HEADER,
)
from windagent.platform.observability import (
    OperationContext,
    Telemetry,
    TraceParent,
    bind_operation_context,
)

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_ID_HEADER = "x-correlation-id"
CAUSATION_ID_HEADER = "x-causation-id"
TRACE_ID_HEADER = OBSERVABILITY_TRACE_ID_HEADER
TRACEPARENT_HEADER = OBSERVABILITY_TRACEPARENT_HEADER

_REQUEST_CONTEXT_ATTR = "windagent_request_context"
_MAX_REQUEST_ID_LENGTH = 128


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Immutable identity attached to one HTTP request."""

    request_id: str
    trace_id: str
    correlation_id: CorrelationId
    causation_id: CausationId | None = None


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Normalize identity headers and stamp them onto request and response.

    An incoming ``X-Request-Id`` is honored verbatim (bounded to a sane
    length); otherwise a fresh identifier is generated.  Correlation and
    causation headers must be valid UUIDs and are ignored when they are not,
    so a malformed client can never poison downstream tracing.
    """

    def __init__(self, app: ASGIApp, telemetry: Telemetry) -> None:
        super().__init__(app)
        self._telemetry = telemetry

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        raw_request_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = (
            raw_request_id.strip()[:_MAX_REQUEST_ID_LENGTH]
            if raw_request_id and raw_request_id.strip()
            else uuid4().hex
        )
        correlation_id = _correlation_or_none(
            request.headers.get(CORRELATION_ID_HEADER)
        ) or CorrelationId.new()
        causation_id = _causation_or_none(request.headers.get(CAUSATION_ID_HEADER))
        operation_context = OperationContext.root(
            trace_parent=TraceParent.parse(request.headers.get(TRACEPARENT_HEADER)),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        context = RequestContext(
            request_id=request_id,
            trace_id=operation_context.trace_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        setattr(request.state, _REQUEST_CONTEXT_ATTR, context)
        started = perf_counter()
        base_attributes = {
            "http.request.method": request.method,
            "url.path": request.url.path,
        }
        with bind_operation_context(operation_context):
            span = self._telemetry.start_span(
                "http.server.request", attributes=base_attributes
            )
            try:
                response = await call_next(request)
            except BaseException as error:
                span.record_exception(error)
                self._telemetry.increment_counter(
                    "http.server.requests",
                    attributes={"method": request.method, "status_class": "5xx"},
                )
                self._telemetry.emit_event(
                    "http.request.failed",
                    attributes={"method": request.method, "path": request.url.path},
                )
                raise
            else:
                route = request.scope.get("route")
                route_path = getattr(route, "path", request.url.path)
                status_class = f"{response.status_code // 100}xx"
                metric_attributes = {
                    "method": request.method,
                    "route": str(route_path),
                    "status_class": status_class,
                }
                self._telemetry.increment_counter(
                    "http.server.requests", attributes=metric_attributes
                )
                self._telemetry.observe_histogram(
                    "http.server.duration_ms",
                    (perf_counter() - started) * 1_000.0,
                    attributes=metric_attributes,
                )
                span.set_attribute("http.response.status_code", response.status_code)
                self._telemetry.emit_event(
                    "http.request.completed",
                    attributes={
                        "method": request.method,
                        "route": str(route_path),
                        "status_code": response.status_code,
                    },
                )
            finally:
                span.end()
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[TRACEPARENT_HEADER] = operation_context.traceparent
        response.headers[TRACE_ID_HEADER] = operation_context.trace_id
        response.headers[CORRELATION_ID_HEADER] = str(operation_context.correlation_id)
        if operation_context.causation_id is not None:
            response.headers[CAUSATION_ID_HEADER] = str(operation_context.causation_id)
        return response


def get_request_context(request: Request) -> RequestContext:
    """Return the context created by :class:`RequestContextMiddleware`."""
    context = getattr(request.state, _REQUEST_CONTEXT_ATTR, None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("request context middleware is not installed")
    return context


def _correlation_or_none(value: str | None) -> CorrelationId | None:
    if not value:
        return None
    try:
        return CorrelationId(value.strip())
    except (TypeError, ValueError):
        return None


def _causation_or_none(value: str | None) -> CausationId | None:
    if not value:
        return None
    try:
        return CausationId(value.strip())
    except (TypeError, ValueError):
        return None
