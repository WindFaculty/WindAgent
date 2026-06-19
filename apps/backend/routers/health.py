"""Health check router. Used by scripts/healthcheck.ps1 and the desktop app."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from services.agent_s3_health import build_status, health_summary

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> Dict[str, Any]:
    """Liveness probe.

    Always returns 200 -- the ``status`` field tells the caller
    whether the backend is healthy. ``agent_s3`` block is the summary
    of the optional Agent-S3 integration; full snapshot lives at
    ``GET /agent-s3/health``.
    """
    base: Dict[str, Any] = {
        "status": "ok",
        "service": "windagent-backend",
    }

    cfg = getattr(request.app.state, "agent_s3_config", None)
    adapter = getattr(request.app.state, "agent_s3_adapter", None)
    if cfg is not None:
        status = build_status(cfg, adapter)
        base.update(health_summary(status))

    return base