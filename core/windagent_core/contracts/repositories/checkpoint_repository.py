"""Workflow checkpoint repository port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class CheckpointRepositoryPort(Protocol):
    """Durable workflow checkpoint persistence for state resume."""

    async def save_checkpoint(
        self,
        checkpoint_id: str,
        run_id: str,
        step_id: str,
        cursor: int,
        state_data: Dict[str, Any],
    ) -> None:
        ...

    async def get_latest_checkpoint(self, run_id: str) -> Optional[Dict[str, Any]]:
        ...