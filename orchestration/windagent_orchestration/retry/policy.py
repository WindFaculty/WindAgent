"""
High-Level Retry Policy for WindAgent Orchestration Engine V2.
Calculates backoff delays, attempt budgets, deadlines, and error retryability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from windagent_orchestration.retry.classifier import ErrorClassifier
from windagent_orchestration.retry.backoff import ExponentialBackoff
from windagent_orchestration.retry.deadline import TimeoutEvaluator

logger = logging.getLogger("windagent.orchestration.retry")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = False

    def __post_init__(self):
        self._backoff = ExponentialBackoff(
            initial_delay_seconds=self.initial_delay_seconds,
            max_delay_seconds=self.max_delay_seconds,
            backoff_factor=self.backoff_factor,
            jitter=self.jitter,
        )

    def should_retry(self, exc: Exception, attempt: int, deadline: Optional[datetime] = None) -> bool:
        """Determines if a failure should be retried based on attempt count, deadline, and error classification."""
        if attempt >= self.max_attempts:
            logger.info(f"Max retry attempts ({self.max_attempts}) reached. No further retries.")
            return False

        if deadline and TimeoutEvaluator.is_expired(deadline):
            logger.info("Execution deadline exceeded. No further retries allowed.")
            return False

        return ErrorClassifier.is_retryable(exc)

    def compute_delay(self, attempt: int) -> float:
        """Computes exponential backoff delay for the given attempt index (1-indexed)."""
        return self._backoff.compute_delay(attempt)
