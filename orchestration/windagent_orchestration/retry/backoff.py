"""
Exponential Backoff Strategy for Orchestration V2 Retry Policy.
Computes exponential delay with cap and optional jitter.
"""

from __future__ import annotations

import random


class ExponentialBackoff:
    def __init__(
        self,
        initial_delay_seconds: float = 1.0,
        max_delay_seconds: float = 30.0,
        backoff_factor: float = 2.0,
        jitter: bool = False,
    ):
        self.initial_delay_seconds = initial_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.backoff_factor = backoff_factor
        self.jitter = jitter

    def compute_delay(self, attempt: int) -> float:
        """Computes exponential backoff delay for the given attempt index (1-indexed)."""
        if attempt <= 1:
            delay = self.initial_delay_seconds
        else:
            delay = self.initial_delay_seconds * (self.backoff_factor ** (attempt - 1))
            delay = min(delay, self.max_delay_seconds)

        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return round(delay, 2)
