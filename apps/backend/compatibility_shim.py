"""
Legacy Compatibility Cutover Shim for WindAgent Backend (Phase 14).
Delegates legacy backend requests to Architecture V2 application core without code duplication.
"""

from __future__ import annotations
from typing import Any, Dict, List
from windagent_core.config.feature_flags import FeatureFlagsManager

flags_manager = FeatureFlagsManager()


class LegacyCompatibilityShim:
    """Cutover shim for legacy backend endpoints."""

    def __init__(self) -> None:
        pass

    async def handle_task_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Routes task creation through V2 TaskService when V2 cutover is active."""
        if flags_manager.is_v2_enabled():
            from windagent_api.routers.v2_tasks import create_task, CreateTaskRequest
            req = CreateTaskRequest(
                prompt=payload.get("prompt", ""),
                workflow_name=payload.get("workflow_name", "bugfix"),
                session_id=payload.get("session_id", "legacy_session")
            )
            res = await create_task(req)
            return res.model_dump()
        else:
            return {"task_id": "legacy_01", "status": "CREATED", "version": "v1"}

    async def handle_provider_request(self) -> List[Dict[str, Any]]:
        """Routes provider catalogue queries through V2 ProviderService."""
        if flags_manager.is_v2_enabled():
            from windagent_api.routers.v2_providers import list_providers
            res = await list_providers()
            return [p.model_dump() for p in res]
        else:
            return [{"name": "legacy_provider", "status": "HEALTHY"}]
