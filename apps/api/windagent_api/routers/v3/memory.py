"""
V3 Memory Router — Canonical Memory Authority (Phase 13C).

Memory is NOT the database: MemoryRecord is a scoped, retrievable knowledge
record (conversation/project/agent/global) with embedding state. Backed by
SqlMemoryRecordRepository (storage layer) over the memory_records table.
Zero static fixture datasets — records are created at runtime and retrieved
by scope or keyword search.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_api.dependencies import get_uow
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork

router = APIRouter(prefix="/api/v3/memory", tags=["Memory V3"])

MEMORY_SCOPES = {"conversation", "project", "agent", "global"}
MEMORY_TYPES = {"working", "short_term", "long_term"}


class MemoryRecordResource(BaseModel):
    id: str
    scope: str = "global"
    owner: Optional[str] = None
    type: str = "short_term"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding_state: str = "NOT_EMBEDDED"  # NOT_EMBEDDED | INDEXED
    created_at: str
    last_accessed_at: str
    version: int = 1


class CreateMemoryRequest(BaseModel):
    scope: str = "global"
    owner: Optional[str] = None
    type: str = "short_term"
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    scope: Optional[str] = None
    owner: Optional[str] = None
    query: str = Field(default="", max_length=2_000)
    limit: int = Field(default=20, ge=1, le=100)


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _to_resource(orm: Any) -> MemoryRecordResource:
    try:
        metadata: Dict[str, Any] = json.loads(orm.value_json) if orm.value_json else {}
        content = metadata.pop("content", "") if isinstance(metadata, dict) else ""
    except (ValueError, AttributeError):
        metadata = {}
        content = ""
    if not content and isinstance(metadata, dict):
        content = str(metadata.get("key", ""))
    return MemoryRecordResource(
        id=orm.id,
        scope=orm.memory_type if orm.memory_type in MEMORY_SCOPES else "global",
        owner=orm.session_id,
        type=orm.memory_type if orm.memory_type in MEMORY_TYPES else "short_term",
        content=content,
        metadata=metadata,
        embedding_state="INDEXED" if metadata.get("indexed") else "NOT_EMBEDDED",
        created_at=_iso(orm.created_at),
        last_accessed_at=_iso(orm.updated_at),
        version=1,
    )


def _repo(uow: SqlUnitOfWork):
    """Session-bound memory repository from the unit of work (no direct
    adapter construction outside the composition root)."""
    return uow.memory_records


@router.get("", response_model=List[MemoryRecordResource], operation_id="memory.list")
async def list_memory(
    scope: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    memory_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[MemoryRecordResource]:
    """List memory records filtered by scope/owner/type. Real DB-backed records only."""
    async with uow:
        rows = await _repo(uow).list_records(
            scope=scope if scope in MEMORY_SCOPES else None,
            owner=owner,
            memory_type=memory_type if memory_type in MEMORY_TYPES else None,
            limit=limit,
        )
    return [_to_resource(row) for row in rows]


@router.get("/{memory_id}", response_model=MemoryRecordResource, operation_id="memory.get")
async def get_memory(memory_id: str, uow: SqlUnitOfWork = Depends(get_uow)) -> MemoryRecordResource:
    async with uow:
        row = await _repo(uow).get_record(memory_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory record not found")
        row.updated_at = datetime.now(timezone.utc)
        await uow.commit()
        return _to_resource(row)


@router.post("", response_model=MemoryRecordResource, operation_id="memory.create")
async def create_memory(
    body: CreateMemoryRequest,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> MemoryRecordResource:
    """Persist a new memory record scoped to conversation/project/agent/global."""
    if body.scope not in MEMORY_SCOPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid scope: {body.scope}")
    if body.type not in MEMORY_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid type: {body.type}")
    record_id = f"mem-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    payload = dict(body.metadata)
    payload["content"] = body.content
    async with uow:
        orm = await _repo(uow).create_record(
            record_id=record_id,
            session_id=body.owner,
            memory_type=body.scope,
            key=body.type,
            value_json=json.dumps(payload),
            now=now,
        )
        await uow.commit()
    return _to_resource(orm)


@router.post("/search", response_model=List[MemoryRecordResource], operation_id="memory.search")
async def search_memory(
    body: MemorySearchRequest,
    uow: SqlUnitOfWork = Depends(get_uow),
) -> List[MemoryRecordResource]:
    """Keyword retrieval over memory records. Semantic placeholder is explicit:
    embeddings are not faked — records without a vector are still retrievable
    by content match; embedding_state stays truthful.
    """
    async with uow:
        rows = await _repo(uow).search_records(
            scope=body.scope if body.scope in MEMORY_SCOPES else None,
            owner=body.owner,
            limit=body.limit,
        )
    query_lower = body.query.strip().lower()
    results = []
    for row in rows:
        if not query_lower:
            results.append(_to_resource(row))
            continue
        try:
            meta = json.loads(row.value_json) if row.value_json else {}
            haystack = f"{meta.get('content', '')} {row.key} {row.session_id or ''}".lower()
        except ValueError:
            haystack = f"{row.key} {row.session_id or ''}".lower()
        if query_lower in haystack:
            results.append(_to_resource(row))
    return results[: body.limit]