"""Sliding-window rate limiter contracts."""

from __future__ import annotations

import pytest
from windagent.platform.security import (
    RateLimitDecision,
    SlidingWindowRateLimiter,
)


class FakeMonotonic:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _limiter(limit: int = 3, window_s: float = 10.0) -> tuple[SlidingWindowRateLimiter, FakeMonotonic]:
    clock = FakeMonotonic()
    return SlidingWindowRateLimiter(limit=limit, window_s=window_s, monotonic=clock), clock


async def test_allows_up_to_the_limit_then_denies() -> None:
    limiter, _ = _limiter(limit=3)
    for remaining in (2, 1, 0):
        decision = await limiter.check("client-a")
        assert decision.allowed
        assert decision.remaining == remaining
    decision = await limiter.check("client-a")
    assert not decision.allowed
    assert decision.remaining == 0
    assert decision.retry_after_s is not None


async def test_windows_slide_with_elapsed_time() -> None:
    limiter, clock = _limiter(limit=2, window_s=10.0)
    await limiter.check("client-a")
    await limiter.check("client-a")
    assert not (await limiter.check("client-a")).allowed
    clock.now += 10.0  # oldest attempts fall out of the window
    decision = await limiter.check("client-a")
    assert decision.allowed


async def test_keys_are_isolated() -> None:
    limiter, _ = _limiter(limit=1)
    assert (await limiter.check("client-a")).allowed
    decision = await limiter.check("client-b")
    assert decision.allowed


async def test_retry_after_never_goes_negative_at_boundary() -> None:
    limiter, clock = _limiter(limit=1, window_s=10.0)
    await limiter.check("client-a")
    clock.now += 9.999
    decision = await limiter.check("client-a")
    assert not decision.allowed
    assert decision.retry_after_s is not None and decision.retry_after_s > 0


async def test_tracked_keys_are_bounded() -> None:
    limiter, _ = _limiter(limit=1)
    limiter.max_tracked_keys = 2
    await limiter.check("a")
    await limiter.check("b")
    await limiter.check("c")  # evicts the oldest tracked key
    assert set(limiter._windows) == {"b", "c"}


async def test_denied_decisions_must_carry_retry_after() -> None:
    with pytest.raises(ValueError):
        RateLimitDecision(allowed=False, limit=1, remaining=0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0, "window_s": 10.0},
        {"limit": 3, "window_s": 0.0},
        {"limit": True, "window_s": 10.0},
    ],
)
def test_limiter_validates_configuration(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        SlidingWindowRateLimiter(**kwargs)  # type: ignore[arg-type]


async def test_empty_keys_are_rejected() -> None:
    limiter, _ = _limiter()
    with pytest.raises(ValueError):
        await limiter.check("")
