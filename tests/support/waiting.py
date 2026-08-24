"""Deterministic waiting / polling helpers.

Replaces ``time.sleep`` / ``asyncio.sleep`` hard-waits that cause flakiness
in CI (especially on Windows runners). All helpers are clock-agnostic and
use monotonic deadlines with short polling intervals.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable


def poll_until(
    condition: Callable[[], bool],
    *,
    timeout: float = 2.0,
    interval: float = 0.05,
    message: str = "poll_until timed out",
) -> None:
    """Block until ``condition()`` is truthy or ``timeout`` expires.

    Raises ``AssertionError`` on timeout so pytest reports a clear failure
    instead of a silent pass.
    """
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if condition():
                return
        except Exception as exc:  # noqa: BLE001 — condition may be flaky
            last_exc = exc
        time.sleep(interval)
    if last_exc is not None:
        raise AssertionError(f"{message} (last error: {last_exc})") from last_exc
    raise AssertionError(message)


async def async_poll_until(
    condition: Callable[[], Any],
    *,
    timeout: float = 5.0,
    interval: float = 0.05,
    message: str = "async_poll_until timed out",
) -> None:
    """Async variant — ``condition`` may be sync or async."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = condition()
            if asyncio.iscoroutine(result):
                result = await result
            if result:
                return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        await asyncio.sleep(interval)
    if last_exc is not None:
        raise AssertionError(f"{message} (last error: {last_exc})") from last_exc
    raise AssertionError(message)


def wait_for_value(
    getter: Callable[[], Any],
    expected: Any,
    *,
    timeout: float = 2.0,
    interval: float = 0.05,
    message: str | None = None,
) -> Any:
    """Poll ``getter()`` until it equals ``expected`` and return the value.

    Useful for ``len(queue) == n`` or ``row.status == 'completed'`` checks.
    """
    result: Any = None

    def _check() -> bool:
        nonlocal result
        result = getter()
        return result == expected

    poll_until(
        _check,
        timeout=timeout,
        interval=interval,
        message=message or f"wait_for_value timed out: expected {expected!r}, got {result!r}",
    )
    return result


def deterministic_sleep(seconds: float, interval: float = 0.01) -> None:
    """Bounded deterministic sleep — delegates to monotonic polling.

    Use sparingly and only for TTL/lease expiry simulation where a
    ``FakeClock`` is not wired. The helper is centrally allowed (see
    ``check_test_architecture.py``) so direct ``time.sleep`` in test bodies
    remains forbidden. Has bounded timeout and monotonic deadline.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        time.sleep(interval)


async def async_deterministic_sleep(seconds: float, interval: float = 0.01) -> None:
    """Async bounded sleep — delegates to ``asyncio.sleep`` via helper.

    Centrally allowed helper for async TTL/lease tests. Has bounded timeout
    and monotonic deadline with clear failure semantics.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(interval)
