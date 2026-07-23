"""
Metrics and Performance Gate Collector for Orchestration V2.
Tracks latency percentiles (p50, p95, p99), gate compliance, and execution counters.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class PerformanceGateMetrics:
    enqueue_durations_ms: List[float] = field(default_factory=list)
    scheduling_durations_ms: List[float] = field(default_factory=list)
    dispatch_claim_durations_ms: List[float] = field(default_factory=list)
    state_transition_durations_ms: List[float] = field(default_factory=list)
    event_persist_durations_ms: List[float] = field(default_factory=list)
    
    duplicate_executions: int = 0
    orphan_leases: int = 0
    lost_terminal_results: int = 0

    def record_enqueue(self, duration_ms: float) -> None:
        self.enqueue_durations_ms.append(duration_ms)

    def record_scheduling(self, duration_ms: float) -> None:
        self.scheduling_durations_ms.append(duration_ms)

    def record_dispatch_claim(self, duration_ms: float) -> None:
        self.dispatch_claim_durations_ms.append(duration_ms)

    def record_state_transition(self, duration_ms: float) -> None:
        self.state_transition_durations_ms.append(duration_ms)

    def record_event_persist(self, duration_ms: float) -> None:
        self.event_persist_durations_ms.append(duration_ms)

    def calculate_percentile(self, values: List[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = int(len(s) * (p / 100.0))
        return round(s[min(idx, len(s) - 1)], 2)

    def generate_summary(self) -> Dict[str, Any]:
        return {
            "enqueue_p95_ms": self.calculate_percentile(self.enqueue_durations_ms, 95),
            "scheduling_p95_ms": self.calculate_percentile(self.scheduling_durations_ms, 95),
            "dispatch_claim_p95_ms": self.calculate_percentile(self.dispatch_claim_durations_ms, 95),
            "state_transition_p95_ms": self.calculate_percentile(self.state_transition_durations_ms, 95),
            "event_persist_p95_ms": self.calculate_percentile(self.event_persist_durations_ms, 95),
            "duplicate_executions": self.duplicate_executions,
            "orphan_leases": self.orphan_leases,
            "lost_terminal_results": self.lost_terminal_results,
        }


# Global metrics instance
metrics = PerformanceGateMetrics()
