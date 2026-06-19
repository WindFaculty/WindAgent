"""Agent-S3 health endpoint.

Exposes the full integration status. Always returns 200 so the
desktop app can poll it cheaply; the ``mode`` field tells the client
what's actually available.

Response shape (always JSON):

    {
      "mode": "disabled" | "package" | "external" | "misconfigured",
      "enabled": bool,
      "source": "package" | "external",
      "package_available": bool,
      "external_repo_available": bool,
      "config_missing": ["WINDAGENT_AGENT_S3_PROVIDER", ...],
      "last_error": null | "<reason>",
      "config": {
        "external_path": "...",
        "provider": "openai",
        "model": "...",
        "ground_provider": "...",
        "ground_model": "...",
        "enable_local_env": false,
        "notes": [],
        "adapter_initialised": bool,
        "last_actions": [...]
      }
    }
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from services.agent_s3_health import build_status, status_to_dict


router = APIRouter(prefix="/agent-s3", tags=["agent-s3"])


@router.get("/health")
async def agent_s3_health(request: Request) -> Dict[str, Any]:
    """Snapshot of every Agent-S3 healthcheck field."""
    cfg = getattr(request.app.state, "agent_s3_config", None)
    adapter = getattr(request.app.state, "agent_s3_adapter", None)

    if cfg is None:
        # Lifespan didn't run yet (rare; e.g. test mis-wiring).
        return {
            "mode": "disabled",
            "enabled": False,
            "source": "package",
            "package_available": False,
            "external_repo_available": False,
            "config_missing": [],
            "last_error": "lifespan has not initialised Agent-S3 state",
            "config": {},
        }

    status = build_status(cfg, adapter)
    return status_to_dict(status)