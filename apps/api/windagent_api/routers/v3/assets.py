"""
V3 Assets Router — Canonical Asset Authority with Provenance Chain.
Migrates from /api/v2/video-production/assets to /api/v3/assets.
Every asset has full provenance: source, generator, model, prompt, job_id, content_hash, parent_revision.
"""
from __future__ import annotations
import hashlib
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now

router = APIRouter(prefix="/api/v3/assets", tags=["Assets V3"])


class AssetProvenance(BaseModel):
    source: str = Field(..., description="GENERATED | UPLOADED | IMPORTED")
    generator: Optional[str] = Field(None, description="Which AI system produced this asset")
    model: Optional[str] = Field(None, description="Model version identifier")
    prompt: Optional[str] = None
    reference_ids: List[str] = Field(default_factory=list)
    job_id: Optional[str] = None
    content_hash: str = ""
    parent_revision_id: Optional[str] = None
    created_at: str = ""


class AssetRevisionResource(BaseModel):
    revision_id: str
    asset_id: str
    version: int
    status: str = "DRAFT"
    media_url: Optional[str] = None
    provenance: AssetProvenance
    created_at: str = ""


class AssetResource(BaseModel):
    id: str
    name: str
    type: str = "IMAGE"
    episode_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    current_revision_id: Optional[str] = None
    status: str = "DRAFT"
    provenance: AssetProvenance
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class CreateAssetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    type: str = Field("IMAGE", description="IMAGE | AUDIO | VIDEO | MODEL_3D | REFERENCE")
    episode_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    source: str = Field("GENERATED", description="GENERATED | UPLOADED | IMPORTED")
    generator: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    job_id: Optional[str] = None
    parent_revision_id: Optional[str] = None
    media_url: Optional[str] = None


class ApproveAssetRequest(BaseModel):
    revision_id: str = Field(..., description="Pinned revision ID to approve")
    reason: str = Field("", max_length=2000)
    approved_by: str = Field(..., min_length=1)


class RejectAssetRequest(BaseModel):
    revision_id: str = Field(..., description="Pinned revision ID to reject")
    reason: str = Field("", max_length=2000)
    rejected_by: str = Field(..., min_length=1)


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


_ASSETS: Dict[str, Dict[str, Any]] = {
    "asset-concept-cb-001-01": {
        "id": "asset-concept-cb-001-01",
        "name": "Concept Art - Phát Hiện Tín Hiệu",
        "type": "IMAGE",
        "episode_id": "ep-cb-001",
        "project_id": "proj-cyberpunk-01",
        "scene_id": "scene-cb-001-01",
        "character_id": None,
        "current_revision_id": "rev-asset-001-v1",
        "status": "DRAFT",
        "provenance": {
            "source": "GENERATED",
            "generator": "Imagen",
            "model": "imagen-3.5-generate",
            "prompt": "Cyberpunk interior, holographic keyboard, neon blue light through rain-streaked window, high contrast, cinematic, neo-noir",
            "reference_ids": ["char-kaelen-01", "loc-tầng-404-01"],
            "job_id": None,
            "content_hash": _compute_content_hash("scene-cb-001-01-concept-v1"),
            "parent_revision_id": None,
            "created_at": "2026-08-14T00:00:00Z",
        },
        "version": 1,
        "created_at": "2026-08-14T00:00:00Z",
        "updated_at": "2026-08-14T00:00:00Z",
    },
}

_ASSET_REVISIONS: Dict[str, List[Dict[str, Any]]] = {
    "asset-concept-cb-001-01": [
        {
            "revision_id": "rev-asset-001-v1",
            "asset_id": "asset-concept-cb-001-01",
            "version": 1,
            "status": "DRAFT",
            "media_url": None,
            "provenance": {
                "source": "GENERATED",
                "generator": "Imagen",
                "model": "imagen-3.5-generate",
                "prompt": "Cyberpunk interior, holographic keyboard, neon blue light",
                "reference_ids": [],
                "job_id": None,
                "content_hash": _compute_content_hash("scene-cb-001-01-concept-v1"),
                "parent_revision_id": None,
                "created_at": "2026-08-14T00:00:00Z",
            },
            "created_at": "2026-08-14T00:00:00Z",
        },
    ],
}


def _asset_to_resource(a: Dict[str, Any]) -> AssetResource:
    return AssetResource(
        id=a["id"],
        name=a["name"],
        type=a["type"],
        episode_id=a.get("episode_id"),
        project_id=a.get("project_id"),
        scene_id=a.get("scene_id"),
        character_id=a.get("character_id"),
        current_revision_id=a.get("current_revision_id"),
        status=a["status"],
        provenance=AssetProvenance(**a["provenance"]),
        version=a["version"],
        created_at=a["created_at"],
        updated_at=a["updated_at"],
    )


@router.get("", response_model=List[AssetResource], operation_id="assets.list")
async def list_assets(
    episode_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    scene_id: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> List[AssetResource]:
    """List assets with provenance filtering."""
    assets = list(_ASSETS.values())
    if episode_id:
        assets = [a for a in assets if a.get("episode_id") == episode_id]
    if project_id:
        assets = [a for a in assets if a.get("project_id") == project_id]
    if scene_id:
        assets = [a for a in assets if a.get("scene_id") == scene_id]
    if type_filter:
        assets = [a for a in assets if a["type"] == type_filter]
    if status_filter:
        assets = [a for a in assets if a["status"] == status_filter]
    return [_asset_to_resource(a) for a in assets]


@router.post("", response_model=AssetResource, status_code=status.HTTP_201_CREATED, operation_id="assets.create")
async def create_asset(body: CreateAssetRequest = ...) -> AssetResource:
    """Create an asset record with full provenance chain."""
    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    rev_id = f"rev-{asset_id}-v1"
    now = utc_now().isoformat()
    content_hash = _compute_content_hash(f"{asset_id}-{body.prompt or ''}-{now}")
    provenance_data: Dict[str, Any] = {
        "source": body.source,
        "generator": body.generator,
        "model": body.model,
        "prompt": body.prompt,
        "reference_ids": [],
        "job_id": body.job_id,
        "content_hash": content_hash,
        "parent_revision_id": body.parent_revision_id,
        "created_at": now,
    }
    new_asset: Dict[str, Any] = {
        "id": asset_id,
        "name": body.name,
        "type": body.type,
        "episode_id": body.episode_id,
        "project_id": body.project_id,
        "scene_id": body.scene_id,
        "character_id": body.character_id,
        "current_revision_id": rev_id,
        "status": "DRAFT",
        "provenance": provenance_data,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    _ASSETS[asset_id] = new_asset
    _ASSET_REVISIONS[asset_id] = [{
        "revision_id": rev_id,
        "asset_id": asset_id,
        "version": 1,
        "status": "DRAFT",
        "media_url": body.media_url,
        "provenance": provenance_data,
        "created_at": now,
    }]
    return _asset_to_resource(new_asset)


@router.get("/{asset_id}", response_model=AssetResource, operation_id="assets.get")
async def get_asset(asset_id: str = Path(...)) -> AssetResource:
    """Get full asset detail including current provenance."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    return _asset_to_resource(_ASSETS[asset_id])


@router.get("/{asset_id}/revisions", response_model=List[AssetRevisionResource], operation_id="assets.listRevisions")
async def list_asset_revisions(asset_id: str = Path(...)) -> List[AssetRevisionResource]:
    """Retrieve full revision history of an asset."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revs = _ASSET_REVISIONS.get(asset_id, [])
    return [AssetRevisionResource(**r) for r in revs]


@router.get("/{asset_id}/provenance", response_model=AssetProvenance, operation_id="assets.getProvenance")
async def get_asset_provenance(asset_id: str = Path(...)) -> AssetProvenance:
    """Get the provenance chain for an asset."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    return AssetProvenance(**_ASSETS[asset_id]["provenance"])


@router.get("/{asset_id}/dependencies", response_model=List[str], operation_id="assets.getDependencies")
async def get_asset_dependencies(asset_id: str = Path(...)) -> List[str]:
    """Get downstream asset IDs that depend on this asset (e.g., composited renders)."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    # In-memory: find assets with parent_revision_id matching any revision of this asset
    my_revisions = {r["revision_id"] for r in _ASSET_REVISIONS.get(asset_id, [])}
    deps = [
        a["id"] for a in _ASSETS.values()
        if a.get("provenance", {}).get("parent_revision_id") in my_revisions and a["id"] != asset_id
    ]
    return deps


@router.post("/{asset_id}/actions/approve", response_model=AssetResource, operation_id="assets.approve")
async def approve_asset(asset_id: str = Path(...), body: ApproveAssetRequest = ...) -> AssetResource:
    """Approve an asset at a specific revision. Cannot approve a mutable (un-versioned) asset."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    # Verify the revision exists
    revisions = _ASSET_REVISIONS.get(asset_id, [])
    rev_ids = {r["revision_id"] for r in revisions}
    if body.revision_id not in rev_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    _ASSETS[asset_id]["status"] = "APPROVED"
    _ASSETS[asset_id]["version"] += 1
    _ASSETS[asset_id]["updated_at"] = now

    for r in revisions:
        if r["revision_id"] == body.revision_id:
            r["status"] = "APPROVED"
            break

    return _asset_to_resource(_ASSETS[asset_id])


@router.post("/{asset_id}/actions/reject", response_model=AssetResource, operation_id="assets.reject")
async def reject_asset(asset_id: str = Path(...), body: RejectAssetRequest = ...) -> AssetResource:
    """Reject an asset at a specific revision with feedback."""
    if asset_id not in _ASSETS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = _ASSET_REVISIONS.get(asset_id, [])
    rev_ids = {r["revision_id"] for r in revisions}
    if body.revision_id not in rev_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    _ASSETS[asset_id]["status"] = "REJECTED"
    _ASSETS[asset_id]["version"] += 1
    _ASSETS[asset_id]["updated_at"] = now

    for r in revisions:
        if r["revision_id"] == body.revision_id:
            r["status"] = "REJECTED"
            break

    return _asset_to_resource(_ASSETS[asset_id])
