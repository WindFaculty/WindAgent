"""Runtime execution repository port for WindAgent Core (Phase 3)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class RuntimeExecutionRepositoryPort(Protocol):
    """Persistence for runtime execution handles and fencing-token status updates."""

    async def create_execution(
        self,
        execution_id: str,
        runtime_run_id: str,
        attempt_id: str,
        step_run_id: str,
        lease_generation: int,
        fencing_token: str,
        runtime_session_id: Optional[str] = None,
    ) -> Any:
        ...

    async def update_status_by_fencing_token(
        self,
        step_run_id: str,
        fencing_token: str,
        status: str,
        result_ref: Optional[str] = None,
        error_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        ...

    async def get_by_step_run_id(self, step_run_id: str) -> Optional[Any]:
        ...