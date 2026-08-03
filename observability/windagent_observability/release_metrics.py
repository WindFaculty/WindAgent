"""In-process operational metrics for the Phase 9 multi-agent rollout.

The collector intentionally holds counters and a few bounded aggregates only.
Production exporters may poll :meth:`ReleaseTelemetry.snapshot` without
receiving prompts, tool arguments, actor IDs, or provider payloads.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseTelemetrySnapshot:
    route_requests: int
    route_failovers: int
    route_failover_rate: float
    duplicate_tool_executions: int
    orphan_worktree_count: int
    websocket_reconnects: int
    recovery_count: int
    recovery_duration_total_seconds: float
    recovery_duration_max_seconds: float
    database_lock_errors: int
    shadow_comparisons: int
    shadow_mismatches: int


class ReleaseTelemetry:
    """Thread-safe metrics sink shared by API, workers, and recovery code."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._route_requests = 0
        self._route_failovers = 0
        self._duplicate_tool_executions = 0
        self._orphan_worktree_count = 0
        self._websocket_reconnects = 0
        self._recovery_count = 0
        self._recovery_duration_total_seconds = 0.0
        self._recovery_duration_max_seconds = 0.0
        self._database_lock_errors = 0
        self._shadow_comparisons = 0
        self._shadow_mismatches = 0

    def record_route_request(self) -> None:
        with self._lock:
            self._route_requests += 1

    def record_route_failover(self) -> None:
        with self._lock:
            self._route_failovers += 1

    def record_duplicate_tool_execution(self) -> None:
        with self._lock:
            self._duplicate_tool_executions += 1

    def set_orphan_worktree_count(self, count: int) -> None:
        with self._lock:
            self._orphan_worktree_count = max(0, int(count))

    def record_websocket_reconnect(self) -> None:
        with self._lock:
            self._websocket_reconnects += 1

    def record_recovery_duration(self, duration_seconds: float) -> None:
        duration = max(0.0, float(duration_seconds))
        with self._lock:
            self._recovery_count += 1
            self._recovery_duration_total_seconds += duration
            self._recovery_duration_max_seconds = max(
                self._recovery_duration_max_seconds, duration
            )

    def record_database_lock_error(self) -> None:
        with self._lock:
            self._database_lock_errors += 1

    def record_shadow_comparison(self, *, matched: bool) -> None:
        with self._lock:
            self._shadow_comparisons += 1
            if not matched:
                self._shadow_mismatches += 1

    def snapshot(self) -> ReleaseTelemetrySnapshot:
        with self._lock:
            return ReleaseTelemetrySnapshot(
                route_requests=self._route_requests,
                route_failovers=self._route_failovers,
                route_failover_rate=(
                    self._route_failovers / self._route_requests
                    if self._route_requests
                    else 0.0
                ),
                duplicate_tool_executions=self._duplicate_tool_executions,
                orphan_worktree_count=self._orphan_worktree_count,
                websocket_reconnects=self._websocket_reconnects,
                recovery_count=self._recovery_count,
                recovery_duration_total_seconds=self._recovery_duration_total_seconds,
                recovery_duration_max_seconds=self._recovery_duration_max_seconds,
                database_lock_errors=self._database_lock_errors,
                shadow_comparisons=self._shadow_comparisons,
                shadow_mismatches=self._shadow_mismatches,
            )
