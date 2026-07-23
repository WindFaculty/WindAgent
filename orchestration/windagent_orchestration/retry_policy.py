"""
Retry Policy & Backoff Strategy for WindAgent Orchestration Engine.
Calculates backoff delays and evaluates error retryability.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

from windagent_core.errors.exceptions import WindAgentError, NonRetryableError

logger = logging.getLogger("windagent.orchestration.retry")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_factor: float = 2.0

    def should_retry(self, exc: Exception, attempt: int) -> bool:
        """Determines if a failure should be retried based on attempt count and error classification."""
        if attempt >= self.max_attempts:
            logger.info(f"Max retry attempts ({self.max_attempts}) reached. No further retries.")
            return False

        if isinstance(exc, NonRetryableError):
            logger.info(f"Error [{type(exc).__name__}] is non-retryable.")
            return False

        if isinstance(exc, WindAgentError):
            return exc.retryable

        # Default fallback for unclassified exceptions
        return True

    def compute_delay(self, attempt: int) -> float:
        """Computes exponential backoff delay for the given attempt index (1-indexed)."""
        if attempt <= 1:
            return self.initial_delay_seconds

        delay = self.initial_delay_seconds * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay_seconds)
