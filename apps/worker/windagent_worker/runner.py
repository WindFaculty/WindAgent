"""
Background Worker Runner for WindAgent Architecture V2.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("windagent.worker")


class WorkerRunner:
    def __init__(self, name: str = "default-worker"):
        self.name = name
        self._running = False
        self._ready = False
        self._task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def start(self) -> None:
        logger.info(f"Starting Worker [{self.name}]...")
        self._running = True
        self._ready = True
        logger.info(f"Worker [{self.name}] ready.")

    async def stop(self) -> None:
        logger.info(f"Stopping Worker [{self.name}]...")
        self._ready = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._running = False
        logger.info(f"Worker [{self.name}] stopped.")

    async def cancel(self) -> None:
        logger.warning(f"Cancelling tasks for Worker [{self.name}]...")
        if self._task and not self._task.done():
            self._task.cancel()

    async def noop_consumer_tick(self) -> dict:
        """Executes a single no-op tick for consumer verification."""
        if not self._ready:
            raise RuntimeError(f"Worker [{self.name}] is not ready.")
        logger.debug(f"Worker [{self.name}] no-op consumer tick.")
        return {"status": "ok", "processed": 0}
