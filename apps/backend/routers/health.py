"""Health check router. Used by scripts/healthcheck.ps1 and the desktop app."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> Dict[str, Any]:
    """Liveness probe. Does not check external dependencies yet (Phase 4 adds Ollama)."""
    return {
        "status": "ok",
        "phase": 1,
        "service": "windagent-backend",
    }