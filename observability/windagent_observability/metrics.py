"""
Metrics collection and aggregation for WindAgent Observability (Phase 11).
Tracks 13 core performance, cost, and reliability metrics.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class MetricsSnapshot:
    """Snapshot containing values for all 13 core system metrics."""
    total_tasks: int = 0
    successful_tasks: int = 0
    accepted_tasks: int = 0
    first_pass_successes: int = 0
    recoveries_attempted: int = 0
    recoveries_successful: int = 0
    tool_failures: int = 0
    provider_failures: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_latency_sec: float = 0.0
    human_interventions: int = 0
    total_retries: int = 0
    average_context_size_tokens: float = 0.0
    verification_failures: int = 0

    @property
    def task_success_rate(self) -> float:
        return (self.successful_tasks / self.total_tasks) if self.total_tasks > 0 else 0.0

    @property
    def accepted_task_rate(self) -> float:
        return (self.accepted_tasks / self.total_tasks) if self.total_tasks > 0 else 0.0

    @property
    def first_pass_success_rate(self) -> float:
        return (self.first_pass_successes / self.total_tasks) if self.total_tasks > 0 else 0.0

    @property
    def recovery_success_rate(self) -> float:
        return (self.recoveries_successful / self.recoveries_attempted) if self.recoveries_attempted > 0 else 0.0


class MetricsCollector:
    """Collects system execution events and aggregates the 13 core metrics."""

    def __init__(self) -> None:
        self._snapshot = MetricsSnapshot()
        self._context_sizes: List[int] = []

    def record_task_completion(
        self,
        success: bool,
        accepted: bool,
        first_pass: bool,
        cost_usd: float,
        latency_sec: float,
        tokens: int,
        context_size: int,
        retries: int = 0,
        human_intervention: bool = False
    ) -> None:
        """Records completion metrics for a task execution."""
        self._snapshot.total_tasks += 1
        if success:
            self._snapshot.successful_tasks += 1
        if accepted:
            self._snapshot.accepted_tasks += 1
        if first_pass:
            self._snapshot.first_pass_successes += 1

        self._snapshot.total_cost_usd += cost_usd
        self._snapshot.total_latency_sec += latency_sec
        self._snapshot.total_tokens += tokens
        self._snapshot.total_retries += retries

        if human_intervention:
            self._snapshot.human_interventions += 1

        self._context_sizes.append(context_size)
        self._snapshot.average_context_size_tokens = (
            sum(self._context_sizes) / len(self._context_sizes)
        )

    def record_recovery(self, success: bool) -> None:
        """Records task recovery attempt."""
        self._snapshot.recoveries_attempted += 1
        if success:
            self._snapshot.recoveries_successful += 1

    def record_tool_failure(self) -> None:
        """Increments tool failure count."""
        self._snapshot.tool_failures += 1

    def record_provider_failure(self) -> None:
        """Increments model provider failure count."""
        self._snapshot.provider_failures += 1

    def record_verification_failure(self) -> None:
        """Increments verification gate failure count."""
        self._snapshot.verification_failures += 1

    def get_snapshot(self) -> MetricsSnapshot:
        """Returns current metrics snapshot."""
        return self._snapshot
