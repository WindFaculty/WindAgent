"""Lightweight provider V3 metrics collector.

No external metrics backend by default.  Exposes an in-memory ledger and a
simple Prometheus text formatter for the observability router.  Production can
swap the port for OpenTelemetry or statsd without changing caller code.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MetricSample:
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ProviderV3Metrics:
    """In-memory metrics store with label cardinality guard."""

    MAX_LABEL_VALUE_LEN: int = 128
    MAX_CARDINALITY: int = 1000
    SECRET_LABELS: frozenset[str] = frozenset(
        {"api_key", "apikey", "token", "secret", "credential", "password"}
    )

    def __init__(self) -> None:
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._samples: List[MetricSample] = []
        self._series_count: int = 0
        self._mutex = threading.Lock()

    def _sanitize_label(self, key: str, value: str) -> str:
        if key.lower() in self.SECRET_LABELS:
            return "[REDACTED]"
        v = str(value)
        if len(v) > self.MAX_LABEL_VALUE_LEN:
            return v[: self.MAX_LABEL_VALUE_LEN] + "..."
        return v

    def _series_key(self, name: str, labels: Dict[str, str]) -> str:
        parts = [name]
        for k in sorted(labels):
            parts.append(f"{k}={labels[k]}")
        return "|".join(parts)

    def _bump_series(self, labels: Dict[str, str]) -> None:
        self._series_count += 1
        if self._series_count > self.MAX_CARDINALITY:
            self._series_count -= 1
            raise RuntimeError("metrics cardinality limit exceeded")

    def inc(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        labels = labels or {}
        labels = {k: self._sanitize_label(k, v) for k, v in labels.items()}
        key = self._series_key(name, labels)
        with self._mutex:
            if key not in self._counters:
                self._bump_series(labels)
            self._counters[key] = self._counters.get(key, 0.0) + value
            self._samples.append(MetricSample(name, value, labels))

    def gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        labels = labels or {}
        labels = {k: self._sanitize_label(k, v) for k, v in labels.items()}
        key = self._series_key(name, labels)
        with self._mutex:
            if key not in self._gauges:
                self._bump_series(labels)
            self._gauges[key] = value
            self._samples.append(MetricSample(name, value, labels))

    def record_latency(
        self,
        name: str,
        latency_ms: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        self.gauge(name, latency_ms, labels)

    def to_prometheus(self) -> str:
        lines: List[str] = []
        with self._mutex:
            for key, value in self._counters.items():
                name, *label_parts = key.split("|")
                label_str = self._format_labels(label_parts)
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_str} {value}")
            for key, value in self._gauges.items():
                name, *label_parts = key.split("|")
                label_str = self._format_labels(label_parts)
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{label_str} {value}")
        return "\n".join(lines)

    def _format_labels(self, label_parts: List[str]) -> str:
        if not label_parts:
            return ""
        pairs = []
        for part in label_parts:
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            pairs.append(f'{k}="{v}"')
        return "{" + ",".join(pairs) + "}"

    def snapshot(self) -> Dict[str, Any]:
        with self._mutex:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "series": self._series_count,
            }


# Global default instance. Production composition can override per-coordinator.
_default_metrics: Optional[ProviderV3Metrics] = None
_default_lock = threading.Lock()


def get_provider_v3_metrics() -> ProviderV3Metrics:
    global _default_metrics
    if _default_metrics is None:
        with _default_lock:
            if _default_metrics is None:
                _default_metrics = ProviderV3Metrics()
    return _default_metrics


def with_metrics(
    name: str,
    labels: Optional[Dict[str, str]] = None,
    metrics: Optional[ProviderV3Metrics] = None,
):
    """Decorator to record call count and latency for an async function."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            target = metrics
            if target is None and args:
                # ponytail: if first arg has _metrics attribute, use it (method bound to coordinator)
                target = getattr(args[0], "_metrics", None)
            if target is None:
                target = get_provider_v3_metrics()
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                latency_ms = (time.perf_counter() - start) * 1000.0
                target.inc(f"{name}_total", labels=labels)
                target.record_latency(f"{name}_latency_ms", latency_ms, labels)

        return wrapper

    return decorator
