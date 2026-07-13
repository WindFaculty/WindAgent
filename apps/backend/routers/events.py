"""Phase 7 — durable event replay + recovery control surface.

  GET  /events/{session_id}?after_seq=N   -> events missed since seq N
  GET  /events/{session_id}/last_seq      -> last persisted seq
  POST /recover                           -> reconcile in-flight runs
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/events", tags=["events"])


def _recovery(request: Request):
    return request.app.state.recovery_manager


@router.get("/{session_id}")
async def replay(
    session_id: str, request: Request, after_seq: int = Query(0, ge=0)
) -> Dict[str, Any]:
    rec = _recovery(request)
    events = await rec.replay_after(session_id, after_seq)
    return {
        "session_id": session_id,
        "after_seq": after_seq,
        "count": len(events),
        "events": [e.model_dump(mode="json") for e in events],
    }


@router.get("/{session_id}/last_seq")
async def last_seq(session_id: str, request: Request) -> Dict[str, Any]:
    rec = _recovery(request)
    return {"session_id": session_id, "last_seq": await rec.seed_seq(session_id)}


recover_router = APIRouter(tags=["events"])


@recover_router.post("/recover")
async def recover(request: Request) -> Dict[str, Any]:
    return await _recovery(request).recover()
