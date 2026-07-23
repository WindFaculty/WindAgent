"""
API V2 Artifacts endpoints for WindAgent (Phase 12).
"""

from __future__ import annotations
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/artifacts", tags=["Artifacts V2"])


class ArtifactInfo(BaseModel):
    artifact_id: str
    name: str
    mime_type: str
    size_bytes: int


@router.get("", response_model=List[ArtifactInfo])
async def list_artifacts() -> List[ArtifactInfo]:
    return [
        ArtifactInfo(artifact_id="art_01", name="implementation_plan.md", mime_type="text/markdown", size_bytes=2450),
        ArtifactInfo(artifact_id="art_02", name="verification_receipt.json", mime_type="application/json", size_bytes=1200),
    ]
