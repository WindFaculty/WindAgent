"""
Automation Rate Calculator (Phase 24 — plan 06 §24.2).

Calculates automation rate (shots completed without manual media editing / total planned shots)
and verifies threshold adherence (>= 80%).
"""

from __future__ import annotations

from windagent_core.domain.video_production.e2e_poc import (
    AutomationRateMetric,
)


class AutomationCalculator:
    """Calculates automation rate metrics."""

    def calculate_automation_rate(
        self, total_planned_shots: int = 6, manual_edits_count: int = 0
    ) -> AutomationRateMetric:
        """Compute AutomationRateMetric object."""
        return AutomationRateMetric(
            total_planned_shots=total_planned_shots,
            manual_media_edits_count=manual_edits_count,
        )
