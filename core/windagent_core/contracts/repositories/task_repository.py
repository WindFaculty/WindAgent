"""Task run repository port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class TaskRunRepositoryPort(Protocol):
    """Durable task run facts persistence with optimistic concurrency."""

    async def get_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        ...

    async def save_facts(
        self,
        task_id: str,
        session_id: str,
        state: str,
        version: int,
        facts: Dict[str, Any],
    ) -> int:
        ...

    async def list_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        ...