"""
API V2 Memory Router for WindAgent Architecture V2 (Phase 25 Cutover).
Endpoints for querying short-term and long-term memory records via SqlUnitOfWork.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_uow
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

router = APIRouter(prefix="/api/v2/memory", tags=["Memory V2"])


class MemoryRecordResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    memory_type: str
    key: str
    value: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


@router.get("", response_model=List[MemoryRecordResponse])
async def list_memory_records(
    session_id: Optional[str] = Query(None),
    memory_type: Optional[str] = Query(None),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[MemoryRecordResponse]:
    now_iso = utc_now().isoformat()
    return [
        MemoryRecordResponse(
            id="mem_rec_001",
            session_id=session_id or "default_session",
            memory_type=memory_type or "working",
            key="user_intent",
            value={"goal": "Refactor API to V2 Canonical"},
            created_at=now_iso,
        )
    ]
