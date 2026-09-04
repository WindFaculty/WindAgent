"""Bounded in-process metrics with a Prometheus text export boundary."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from threading import RLock
from typing import Protocol, runtime_checkable

from .contracts import TelemetryAttributes, TelemetryValue

_METRIC_NAME_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:.-]*$")
_LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

type LabelSet = tuple[tuple[str, TelemetryValue], ...]


@dataclass(frozen=True, slots=True)
class CounterSample:
    name: str
    value: int
    attributes: LabelSet


@dataclass(frozen=True, slots=True)
class HistogramSample:
    name: str
    count: int
    total: float
    minimum: float
    maximum: float
    attributes: LabelSet


@runtime_checkable
class MetricsExporter(Protocol):
    """Exports a point-in-time metrics snapshot."""

    def render_prometheus(self) -> str:
        """Return Prometheus text exposition format."""


class MetricRegistry:
    """Thread-safe, bounded metric aggregation.

    New series are dropped after ``max_series`` to prevent user-controlled
    labels from growing process memory without bound.  Callers should still
    only use stable labels such as method, route template, status class, job
    type, and terminal outcome.
    """

    def __init__(self, *, max_series: int = 2_000, max_labels: int = 12) -> None:
        if max_series < 1:
            raise ValueError("max_series must be at least 1")
        if max_labels < 0:
            raise ValueError("max_labels must be non-negative")
        self._max_series = max_series
        self._max_labels = max_labels
        self._counters: dict[tuple[str, LabelSet], int] = {}
        self._histograms: dict[
            tuple[str, LabelSet], tuple[int, float, float, float]
        ] = {}
        self._dropped_series = 0
        self._lock = RLock()

    @property
    def dropped_series(self) -> int:
        with self._lock:
            return self._dropped_series

    def increment(
        self,
        name: str,
        *,
        value: int = 1,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        metric_name = _metric_name(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("counter value must be an integer")
        if value < 0:
            raise ValueError("counter value must be non-negative")
        key = (metric_name, _labels(attributes, max_labels=self._max_labels))
        with self._lock:
            if key not in self._counters and not self._reserve_series():
                return
            self._counters[key] = self._counters.get(key, 0) + value

    def observe(
        self,
        name: str,
        value: float,
        *,
        attributes: TelemetryAttributes | None = None,
    ) -> None:
        metric_name = _metric_name(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("histogram value must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("histogram value must be finite")
        key = (metric_name, _labels(attributes, max_labels=self._max_labels))
        with self._lock:
            previous = self._histograms.get(key)
            if previous is None:
                if not self._reserve_series():
                    return
                self._histograms[key] = (1, numeric, numeric, numeric)
                return
            count, total, minimum, maximum = previous
            self._histograms[key] = (
                count + 1,
                total + numeric,
                min(minimum, numeric),
                max(maximum, numeric),
            )

    def counters(self) -> tuple[CounterSample, ...]:
        with self._lock:
            return tuple(
                CounterSample(name, value, attributes)
                for (name, attributes), value in sorted(self._counters.items())
            )

    def histograms(self) -> tuple[HistogramSample, ...]:
        with self._lock:
            return tuple(
                HistogramSample(name, count, total, minimum, maximum, attributes)
                for (name, attributes), (count, total, minimum, maximum) in sorted(
                    self._histograms.items()
                )
            )

    def render_prometheus(self) -> str:
        """Render deterministic Prometheus-compatible counter/summary samples."""
        lines: list[str] = []
        for counter_sample in self.counters():
            name = _prometheus_name(counter_sample.name)
            if not name.endswith("_total"):
                name += "_total"
            lines.append(
                f"{name}{_render_labels(counter_sample.attributes)} "
                f"{counter_sample.value}"
            )
        for histogram_sample in self.histograms():
            name = _prometheus_name(histogram_sample.name)
            labels = _render_labels(histogram_sample.attributes)
            lines.append(f"{name}_count{labels} {histogram_sample.count}")
            lines.append(f"{name}_sum{labels} {_number(histogram_sample.total)}")
            lines.append(f"{name}_min{labels} {_number(histogram_sample.minimum)}")
            lines.append(f"{name}_max{labels} {_number(histogram_sample.maximum)}")
        lines.append(f"windagent_metrics_dropped_series_total {self.dropped_series}")
        return "\n".join(lines) + "\n"

    def _reserve_series(self) -> bool:
        if len(self._counters) + len(self._histograms) >= self._max_series:
            self._dropped_series += 1
            return False
        return True


def _metric_name(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("metric name must be text")
    candidate = value.strip()
    if not _METRIC_NAME_RE.fullmatch(candidate):
        raise ValueError(f"invalid metric name: {value!r}")
    return candidate


def _labels(
    attributes: Mapping[str, TelemetryValue] | None, *, max_labels: int
) -> LabelSet:
    if attributes is None:
        return ()
    if not isinstance(attributes, Mapping):
        raise TypeError("metric attributes must be a mapping")
    if len(attributes) > max_labels:
        raise ValueError(f"metric attributes exceed the {max_labels}-label limit")
    labels: list[tuple[str, TelemetryValue]] = []
    for name, value in attributes.items():
        if not isinstance(name, str) or not _LABEL_NAME_RE.fullmatch(name):
            raise ValueError(f"invalid metric label name: {name!r}")
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"metric label {name!r} has an unsupported value")
        labels.append((name, value))
    return tuple(sorted(labels, key=lambda item: item[0]))


def _prometheus_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_:]", "_", value)


def _render_labels(labels: LabelSet) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{name}="{_escape_label(value)}"' for name, value in labels
    )
    return "{" + rendered + "}"


def _escape_label(value: TelemetryValue) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _number(value: float) -> str:
    return format(value, ".15g")
