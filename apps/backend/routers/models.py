"""Models router — provider health + diagnostics.

Currently exposes:
  GET /models/health   — probe the configured model provider.

Phase 4 wires the Ollama-compatible provider. Future phases may add
GET /models (list pulled models), POST /models/pull, etc.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from services.planner_service import PlannerService


router = APIRouter(prefix="/models", tags=["models"])


def _planner(request: Request) -> PlannerService:
    return request.app.state.planner_service


@router.get("/health")
async def models_health(request: Request) -> Dict[str, Any]:
    """Probe the configured model provider.

    Response 200 (always — frontend interprets `online`):
    {
      "provider": "ollama" | "mock",
      "online": true | false,
      "model": "qwen3:4b-q4",
      "latency_ms": 1234 | null,
      "error": null | "<reason>"
    }
    """
    planner = _planner(request)
    return await planner.health()