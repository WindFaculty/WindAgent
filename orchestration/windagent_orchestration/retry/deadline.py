"""
Deadline and Timeout Evaluator for Orchestration V2 Tasks & Workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from windagent_core.errors.exceptions import DomainError


class TimeoutEvaluator:
    @staticmethod
    def is_expired(deadline: Optional[datetime]) -> bool:
        if not deadline:
            return False
        now = datetime.now(timezone.utc)
        return now >= deadline

    @staticmethod
    def assert_within_deadline(deadline: Optional[datetime], operation_name: str = "operation") -> None:
        if TimeoutEvaluator.is_expired(deadline):
            raise DomainError(
                message=f"Execution deadline exceeded for [{operation_name}].",
                code="WINDAGENT_ERR_DEADLINE_EXCEEDED",
                details={"deadline": deadline.isoformat() if deadline else None},
            )
