"""Rate limiting: a sliding-window limiter keyed by opaque strings.

The limiter is deliberately in-process (plan section 13 keeps the foundation
simple); a PostgreSQL-backed distributed limiter can implement the same
``RateLimiter`` protocol later without touching call sites.  Time comes from
``time.monotonic`` so wall-clock adjustments never extend or shorten windows.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Protocol, runtime_checkable

DEFAULT_MAX_TRACKED_KEYS: Final[int] = 10_000


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of one rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_s: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("limit must be an integer")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        if isinstance(self.remaining, bool) or not isinstance(self.remaining, int):
            raise TypeError("remaining must be an integer")
        if self.remaining < 0:
            raise ValueError("remaining must be non-negative")
        if not self.allowed and self.retry_after_s is None:
            raise ValueError("denied decisions must carry retry_after_s")


@runtime_checkable
class RateLimiter(Protocol):
    """Checks and counts one operation against a keyed budget."""

    async def check(self, key: str) -> RateLimitDecision:
        """Record the attempt for ``key`` and return the decision."""


@dataclass(slots=True)
class SlidingWindowRateLimiter:
    """Allows at most ``limit`` attempts per ``window_s`` per key."""

    limit: int
    window_s: float
    monotonic: Callable[[], float] = time.monotonic
    max_tracked_keys: int = DEFAULT_MAX_TRACKED_KEYS
    _windows: dict[str, deque[float]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int):
            raise TypeError("limit must be an integer")
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        if isinstance(self.window_s, bool) or not isinstance(self.window_s, (int, float)):
            raise TypeError("window_s must be a number")
        if self.window_s <= 0:
            raise ValueError("window_s must be positive")
        if isinstance(self.max_tracked_keys, bool) or not isinstance(
            self.max_tracked_keys, int
        ):
            raise TypeError("max_tracked_keys must be an integer")
        if self.max_tracked_keys < 1:
            raise ValueError("max_tracked_keys must be at least 1")

    async def check(self, key: str) -> RateLimitDecision:
        if not isinstance(key, str) or not key:
            raise ValueError("key must be non-empty text")
        now = self.monotonic()
        window = self._window_for(key)
        self._prune(window, now)
        if len(window) < self.limit:
            window.append(now)
            return RateLimitDecision(
                allowed=True, limit=self.limit, remaining=self.limit - len(window)
            )
        retry_after = self.window_s - (now - window[0])
        return RateLimitDecision(
            allowed=False,
            limit=self.limit,
            remaining=0,
            retry_after_s=max(0.0, retry_after),
        )

    def _window_for(self, key: str) -> deque[float]:
        window = self._windows.get(key)
        if window is None:
            if len(self._windows) >= self.max_tracked_keys:
                # Bounded memory: drop the oldest-tracked key (FIFO by
                # insertion).  An attacker rotating keys cannot grow the
                # map without evicting previous entries.
                oldest = next(iter(self._windows))
                del self._windows[oldest]
            window = deque()
            self._windows[key] = window
        return window

    def _prune(self, window: deque[float], now: float) -> None:
        while window and now - window[0] >= self.window_s:
            window.popleft()
