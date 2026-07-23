"""
In-memory singleflight for WindAgent Provider Subsystem V3.

Collapses concurrent identical operations (model discovery, health probes,
cacheable requests, quota refresh) so only one upstream call is made.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List

from windagent_providers.cache.contracts import SingleFlightPort


class _InFlight:
    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.result: Any = None
        self.exception: BaseException | None = None
        self.waiter_count = 1


class InMemorySingleFlight(SingleFlightPort):
    """
    Async singleflight implemented with an in-memory dict of asyncio.Event.

    Not distributed: it only collapses flights inside one process.  For multi-
    process deployments a distributed lock should be composed around this port.
    """

    def __init__(self) -> None:
        self._flights: Dict[str, _InFlight] = {}

    async def do(
        self,
        key: str,
        operation: Callable[[], Any],
    ) -> Any:
        flight = self._claim_or_wait(key)
        if flight is None:
            # Wait for the leader.
            return await self._await_leader(key)

        try:
            flight.result = await operation()
            return flight.result
        except BaseException as exc:
            flight.exception = exc
            raise
        finally:
            flight.event.set()
            self._flights.pop(key, None)

    def _claim_or_wait(self, key: str) -> _InFlight | None:
        existing = self._flights.get(key)
        if existing is None:
            flight = _InFlight()
            self._flights[key] = flight
            return flight
        existing.waiter_count += 1
        return None

    async def _await_leader(self, key: str) -> Any:
        flight = self._flights.get(key)
        if flight is None:
            raise RuntimeError("singleflight invariant lost")
        try:
            await flight.event.wait()
        finally:
            flight.waiter_count -= 1
            if flight.waiter_count <= 0 and flight.event.is_set():
                self._flights.pop(key, None)
        if flight.exception is not None:
            raise flight.exception
        return flight.result

    def active_keys(self) -> List[str]:
        """Test/debug helper."""
        return list(self._flights.keys())
