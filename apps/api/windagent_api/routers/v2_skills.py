"""
API V2 Skills Router for WindAgent Architecture V2 (Phase 25 Cutover).
Endpoints for querying installed skills and manifests.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v2/skills", tags=["Skills V2"])


class SkillResponse(BaseModel):
    skill_id: str
    name: str
    version: str
    status: str
    manifest: Dict[str, Any] = Field(default_factory=dict)
    installed_at: str


@router.get("", response_model=List[SkillResponse])
async def list_skills() -> List[SkillResponse]:
    now_iso = utc_now().isoformat()
    return [
        SkillResponse(
            skill_id="skill_code_refactoring",
            name="Code Refactoring Assistant",
            version="1.2.0",
            status="active",
            manifest={"description": "Refactors Python modules according to V2 architecture"},
            installed_at=now_iso,
        )
    ]
