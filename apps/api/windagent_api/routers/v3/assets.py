"""
V3 Assets Router — Canonical Asset Authority with Provenance Chain.
Migrates from /api/v2/video-production/assets to /api/v3/assets.
Every asset has full provenance: source, generator, model, prompt, job_id, content_hash, parent_revision.

Phase 4: assets and their revision history are persisted through the
namespaced durable V3 resource authority. No module-level RAM stores.
"""
from __future__ import annotations
import hashlib
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_ASSETS, NS_ASSET_REVISIONS

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


def _asset_to_resource(a: Dict[str, Any]) -> AssetResource:
    return AssetResource(
        id=a["id"],
        name=a["name"],
        type=a.get("type", "IMAGE"),
        episode_id=a.get("episode_id"),
        project_id=a.get("project_id"),
        scene_id=a.get("scene_id"),
        character_id=a.get("character_id"),
        current_revision_id=a.get("current_revision_id"),
        status=a.get("status", "DRAFT"),
        provenance=AssetProvenance(**a["provenance"]),
        version=a.get("version", 1),
        created_at=a.get("created_at", ""),
        updated_at=a.get("updated_at", ""),
    )


@router.get("", response_model=List[AssetResource], operation_id="assets.list")
async def list_assets(
    episode_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    scene_id: Optional[str] = Query(None),
    type_filter: Optional[str] = Query(None, alias="type"),
    status_filter: Optional[str] = Query(None, alias="status"),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[AssetResource]:
    """List assets with provenance filtering."""
    assets = await service.list(NS_ASSETS)
    if episode_id:
        assets = [a for a in assets if a.get("episode_id") == episode_id]
    if project_id:
        assets = [a for a in assets if a.get("project_id") == project_id]
    if scene_id:
        assets = [a for a in assets if a.get("scene_id") == scene_id]
    if type_filter:
        assets = [a for a in assets if a.get("type") == type_filter]
    if status_filter:
        assets = [a for a in assets if a.get("status") == status_filter]
    return [_asset_to_resource(a) for a in assets]


@router.post("", response_model=AssetResource, status_code=status.HTTP_201_CREATED, operation_id="assets.create")
async def create_asset(
    body: CreateAssetRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
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
        "created_at": now,
        "updated_at": now,
    }
    await service.create(NS_ASSETS, asset_id, new_asset)
    await service.create(NS_ASSET_REVISIONS, rev_id, {
        "revision_id": rev_id,
        "asset_id": asset_id,
        "version": 1,
        "status": "DRAFT",
        "media_url": body.media_url,
        "provenance": provenance_data,
        "created_at": now,
    })
    return _asset_to_resource(new_asset)


@router.get("/{asset_id}", response_model=AssetResource, operation_id="assets.get")
async def get_asset(
    asset_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
    """Get full asset detail including current provenance."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    return _asset_to_resource(asset)


@router.get("/{asset_id}/revisions", response_model=List[AssetRevisionResource], operation_id="assets.listRevisions")
async def list_asset_revisions(
    asset_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[AssetRevisionResource]:
    """Retrieve full revision history of an asset."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revs = await service.list(NS_ASSET_REVISIONS)
    revs = [r for r in revs if r.get("asset_id") == asset_id]
    return [AssetRevisionResource(**r) for r in revs]


@router.get("/{asset_id}/provenance", response_model=AssetProvenance, operation_id="assets.getProvenance")
async def get_asset_provenance(
    asset_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetProvenance:
    """Get the provenance chain for an asset."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    return AssetProvenance(**asset["provenance"])


@router.get("/{asset_id}/dependencies", response_model=List[str], operation_id="assets.getDependencies")
async def get_asset_dependencies(
    asset_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[str]:
    """Get downstream asset IDs that depend on this asset (e.g., composited renders)."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = await service.list(NS_ASSET_REVISIONS)
    my_revisions = {r["revision_id"] for r in revisions if r.get("asset_id") == asset_id}
    assets = await service.list(NS_ASSETS)
    deps = [
        a["id"] for a in assets
        if a.get("provenance", {}).get("parent_revision_id") in my_revisions and a["id"] != asset_id
    ]
    return deps


@router.post("/{asset_id}/actions/approve", response_model=AssetResource, operation_id="assets.approve")
async def approve_asset(
    asset_id: str = Path(...),
    body: ApproveAssetRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
    """Approve an asset at a specific revision. Cannot approve a mutable (un-versioned) asset."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = await service.list(NS_ASSET_REVISIONS)
    revisions = [r for r in revisions if r.get("asset_id") == asset_id]
    rev_ids = {r["revision_id"] for r in revisions}
    if body.revision_id not in rev_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    updates = dict(asset)
    updates["status"] = "APPROVED"
    updates["updated_at"] = now
    updated = await service.update(NS_ASSETS, asset_id, updates, asset["version"])

    for r in revisions:
        if r["revision_id"] == body.revision_id:
            rev_updates = dict(r)
            rev_updates["status"] = "APPROVED"
            await service.update(NS_ASSET_REVISIONS, r["revision_id"], rev_updates, r["version"])
            break

    return _asset_to_resource(updated)


@router.post("/{asset_id}/actions/reject", response_model=AssetResource, operation_id="assets.reject")
async def reject_asset(
    asset_id: str = Path(...),
    body: RejectAssetRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
    """Reject an asset at a specific revision with feedback."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = await service.list(NS_ASSET_REVISIONS)
    revisions = [r for r in revisions if r.get("asset_id") == asset_id]
    rev_ids = {r["revision_id"] for r in revisions}
    if body.revision_id not in rev_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    updates = dict(asset)
    updates["status"] = "REJECTED"
    updates["updated_at"] = now
    updated = await service.update(NS_ASSETS, asset_id, updates, asset["version"])

    for r in revisions:
        if r["revision_id"] == body.revision_id:
            rev_updates = dict(r)
            rev_updates["status"] = "REJECTED"
            await service.update(NS_ASSET_REVISIONS, r["revision_id"], rev_updates, r["version"])
            break

    return _asset_to_resource(updated)
