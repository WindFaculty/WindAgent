"""
Legacy Compatibility Cutover Shim for WindAgent Backend (Phase 14).
Delegates legacy backend requests to Architecture V2 application core without code duplication.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional

from windagent_api.bootstrap.feature_flags import FeatureFlagsManager
from windagent_api.composition import ApplicationContainer
from windagent_core.contracts.workers.models import WorkSubmission
from windagent_core.domain.lifecycle import utc_now
from windagent_core.domain.types import SessionId, TaskId

flags_manager = FeatureFlagsManager()


class LegacyCompatibilityShim:
    """Cutover shim for legacy backend endpoints."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        self._db_url = db_url or "sqlite+aiosqlite:///windagent.db"

    async def handle_task_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Routes task creation through V2 TaskService when V2 cutover is active."""
        if flags_manager.is_v2_enabled():
            container = ApplicationContainer(db_url=self._db_url)
            await container.bootstrap()
            try:
                task_id = TaskId.generate()
                try:
                    session_id = SessionId(payload.get("session_id", ""))
                except Exception:
                    session_id = SessionId.generate()
                workflow_name = payload.get("workflow_name", "bugfix")
                idempotency_key = payload.get("idempotency_key") or f"idem_{TaskId.generate()}"

                await container.task_submission.submit(
                    WorkSubmission(
                        task_id=str(task_id),
                        session_id=str(session_id),
                        prompt=payload.get("prompt", ""),
                        workflow_name=workflow_name,
                        tool_name="read_file",
                        parameters=payload.get("parameters", {}),
                        idempotency_key=idempotency_key,
                    )
                )
                facts = container.task_manager.get_or_create_facts(task_id, session_id)
                facts.metadata["prompt"] = payload.get("prompt", "")
                facts.metadata["workflow_name"] = workflow_name
                facts.metadata["idempotency_key"] = idempotency_key
                now_iso = utc_now().isoformat()
                return {
                    "task_id": str(task_id),
                    "session_id": str(session_id),
                    "prompt": payload.get("prompt", ""),
                    "status": "pending",
                    "workflow_name": workflow_name,
                    "created_at": now_iso,
                    "updated_at": now_iso,
                    "idempotency_key": idempotency_key,
                    "result": None,
                }
            finally:
                await container.shutdown()
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
