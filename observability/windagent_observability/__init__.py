"""
Logging, tracing, metrics, audit trail, cost tracking for WindAgent (Phase 11).
"""

from windagent_core.version import PRODUCT_VERSION

from windagent_observability.metrics import MetricsSnapshot, MetricsCollector
from windagent_observability.tracing import SpanKind, Span, TraceChain
from windagent_observability.audit import SecretSanitizer, AuditEvent, AuditLogger
from windagent_observability.health import (
    HealthChecker,
    HealthStatus,
    HealthProfile,
    HealthCheckResult,
    ReadinessStatus,
)

__all__ = [
    "MetricsSnapshot",
    "MetricsCollector",
    "SpanKind",
    "Span",
    "TraceChain",
    "SecretSanitizer",
    "AuditEvent",
    "AuditLogger",
    "HealthChecker",
    "HealthStatus",
    "HealthProfile",
    "HealthCheckResult",
    "ReadinessStatus",
]

__version__ = PRODUCT_VERSION