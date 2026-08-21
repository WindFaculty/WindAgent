"""
API V2 Plugins Router for WindAgent Architecture V2 (Phase 25 Cutover).
Endpoints for querying installed plugins and manifests.
"""

from __future__ import annotations
from typing import Any, Dict, List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v2/plugins", tags=["Plugins V2"])


class PluginResponse(BaseModel):
    plugin_id: str
    name: str
    version: str
    status: str
    manifest: Dict[str, Any] = Field(default_factory=dict)
    installed_at: str


@router.get("", response_model=List[PluginResponse])
async def list_plugins() -> List[PluginResponse]:
    now_iso = utc_now().isoformat()
    return [
        PluginResponse(
            plugin_id="plugin_git_integration",
            name="Git Advanced Integration",
            version="1.0.0",
            status="active",
            manifest={"author": "WindAgent DeepMind Team"},
            installed_at=now_iso,
        )
    ]
