"""
Event-Driven Wakeup Signal Manager for Orchestration V2 Scheduler.
Replaces busy-polling (e.g. 5ms sleep loops) with zero-cpu asyncio.Event notification.
"""

from __future__ import annotations

import asyncio
from typing import Optional


class EventDrivenWakeup:
    def __init__(self):
        self._event = asyncio.Event()

    def notify(self) -> None:
        """Signals scheduler loop that new tasks or slots are available."""
        self._event.set()

    async def wait(self, timeout: Optional[float] = None) -> bool:
        """Waits asynchronously for a notification signal without busy polling."""
        try:
            if timeout is not None:
                await asyncio.wait_for(self._event.wait(), timeout=timeout)
            else:
                await self._event.wait()
            self._event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    def clear(self) -> None:
        self._event.clear()
