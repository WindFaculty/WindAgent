"""
V3 Assets Router — Canonical Asset Authority with Provenance Chain.
Migrates from /api/v2/video-production/assets to /api/v3/assets.
Every asset has full provenance: source, generator, model, prompt, job_id, content_hash, parent_revision.

Phase 4: assets and their revision history are persisted through the
namespaced durable V3 resource authority. No module-level RAM stores.

P1.3 Asset Authority: Asset Requirements are separated from Assets,
content hashes are SHA-256 over the ACTUAL asset bytes (HASH_UNVERIFIED
otherwise, and never pinnable), the asset lifecycle follows
REQUIRED -> SOURCING/GENERATING/UPLOADING -> DRAFT -> REVIEW -> APPROVED ->
PINNED with honest failure paths, and approval pins a SPECIFIC revision.
"""
from __future__ import annotations
import base64
import binascii
import hashlib
import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from windagent_core.domain.lifecycle import utc_now
from windagent_api.dependencies import get_v3_resource_service
from windagent_api.services.v3_resource_service import V3ResourceService
from windagent_api.services.v3_demo_seed import NS_ASSETS, NS_ASSET_REVISIONS
from windagent_api.services.character_canon_authority import (
    PreproductionAuthorityError,
)
from windagent_api.services.asset_requirement_authority import (
    NS_ASSET_REQUIREMENTS,
    build_asset_requirements,
)

router = APIRouter(prefix="/api/v3/assets", tags=["Assets V3"])
req_router = APIRouter(prefix="/api/v3", tags=["Assets V3"])

# P1.3.2 asset lifecycle (plan order + honest failure paths).
ASSET_STATUS_REQUIRED = "REQUIRED"
ASSET_STATUS_SOURCING = "SOURCING"
ASSET_STATUS_GENERATING = "GENERATING"
ASSET_STATUS_UPLOADING = "UPLOADING"
ASSET_STATUS_DRAFT = "DRAFT"
ASSET_STATUS_REVIEW = "REVIEW"
ASSET_STATUS_APPROVED = "APPROVED"
ASSET_STATUS_PINNED = "PINNED"
ASSET_STATUS_REJECTED = "REJECTED"
ASSET_STATUS_SUPERSEDED = "SUPERSEDED"
ASSET_STATUS_UNAVAILABLE = "UNAVAILABLE"

# Forward ladder; SOURCING/GENERATING/UPLOADING are interchangeable lanes.
_ASSET_LADDER = [
    ASSET_STATUS_REQUIRED,
    (ASSET_STATUS_SOURCING, ASSET_STATUS_GENERATING, ASSET_STATUS_UPLOADING),
    ASSET_STATUS_DRAFT,
    ASSET_STATUS_REVIEW,
    ASSET_STATUS_APPROVED,
    ASSET_STATUS_PINNED,
]
_FAILURE_STATUSES = (ASSET_STATUS_REJECTED, ASSET_STATUS_SUPERSEDED, ASSET_STATUS_UNAVAILABLE)
_ASSET_STATUSES = [
    s for step in _ASSET_LADDER for s in (step if isinstance(step, tuple) else (step,))
] + list(_FAILURE_STATUSES)

HASH_VERIFIED = "VERIFIED"
HASH_UNVERIFIED = "HASH_UNVERIFIED"


def _allowed_transitions(current: str) -> set:
    """Forward ladder one step at a time; failure paths from any active state."""
    allowed = set()
    for idx, step in enumerate(_ASSET_LADDER):
        states = step if isinstance(step, tuple) else (step,)
        if current in states:
            next_step = _ASSET_LADDER[idx + 1] if idx + 1 < len(_ASSET_LADDER) else ()
            next_states = next_step if isinstance(next_step, tuple) else (next_step,)
            allowed.update(s for s in next_states if s)
            break
    allowed.update(_FAILURE_STATUSES)
    allowed.discard(current)
    return allowed


class AssetProvenance(BaseModel):
    source: str = Field(..., description="GENERATED | UPLOADED | IMPORTED | REFERENCE")
    generator: Optional[str] = Field(None, description="Which AI system produced this asset")
    model: Optional[str] = Field(None, description="Model version identifier")
    prompt: Optional[str] = None
    reference_ids: List[str] = Field(default_factory=list)
    job_id: Optional[str] = None
    content_hash: str = ""
    hash_status: str = HASH_UNVERIFIED
    parent_revision_id: Optional[str] = None
    created_at: str = ""


class ApprovalPin(BaseModel):
    asset_id: str
    revision_id: str
    content_hash: str
    approved_by: str
    approved_at: str


class AssetRevisionResource(BaseModel):
    revision_id: str
    asset_id: str
    version: int
    status: str = "DRAFT"
    media_url: Optional[str] = None
    provenance: AssetProvenance
    approval_pin: Optional[ApprovalPin] = None
    created_at: str = ""


class AssetResource(BaseModel):
    id: str
    name: str
    type: str = "IMAGE"
    episode_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    requirement_id: Optional[str] = None
    current_revision_id: Optional[str] = None
    status: str = "DRAFT"
    provenance: AssetProvenance
    approval_pin: Optional[ApprovalPin] = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


class AssetRequirementResource(BaseModel):
    requirement_id: str
    project_id: str
    episode_id: str
    type: str
    name: str
    description: str = ""
    scene_usage: List[Any] = Field(default_factory=list)
    mandatory: bool = True
    status: str = "OPEN"
    linked_asset_id: Optional[str] = None
    content_hash: str = ""
    created_at: str = ""
    updated_at: str = ""


class CreateAssetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    type: str = Field("IMAGE", description="IMAGE | AUDIO | VIDEO | MODEL_3D | REFERENCE")
    episode_id: Optional[str] = None
    project_id: Optional[str] = None
    scene_id: Optional[str] = None
    character_id: Optional[str] = None
    requirement_id: Optional[str] = Field(None, description="Asset Requirement this asset fulfils")
    source: str = Field("GENERATED", description="GENERATED | UPLOADED | IMPORTED | REFERENCE")
    generator: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    job_id: Optional[str] = None
    parent_revision_id: Optional[str] = None
    reference_ids: List[str] = Field(default_factory=list)
    media_url: Optional[str] = None
    content_base64: Optional[str] = Field(
        None,
        description="Actual asset bytes (base64). When provided the content hash is "
        "SHA-256 over these bytes and marked VERIFIED; otherwise HASH_UNVERIFIED.",
    )


class AddAssetRevisionRequest(BaseModel):
    media_url: Optional[str] = None
    source: Optional[str] = Field(None, description="GENERATED | UPLOADED | IMPORTED | REFERENCE")
    generator: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    job_id: Optional[str] = None
    parent_revision_id: Optional[str] = None
    reference_ids: List[str] = Field(default_factory=list)
    content_base64: Optional[str] = None


class SetAssetStatusRequest(BaseModel):
    status: str = Field(..., description=f"One of: {', '.join(_ASSET_STATUSES)}")
    expected_version: int = Field(..., description="Optimistic locking version")


class ApproveAssetRequest(BaseModel):
    revision_id: str = Field(..., description="Pinned revision ID to approve")
    reason: str = Field("", max_length=2000)
    approved_by: str = Field(..., min_length=1)


class RejectAssetRequest(BaseModel):
    revision_id: str = Field(..., description="Pinned revision ID to reject")
    reason: str = Field("", max_length=2000)
    rejected_by: str = Field(..., min_length=1)


def _hash_actual_bytes(content_base64: Optional[str]) -> Dict[str, Any]:
    """SHA-256 over the ACTUAL bytes (P1.3.4). No bytes -> HASH_UNVERIFIED."""
    if not content_base64:
        return {"content_hash": "", "hash_status": HASH_UNVERIFIED}
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "INVALID_CONTENT_ENCODING", "message": "content_base64 is not valid base64."},
        )
    return {"content_hash": hashlib.sha256(raw).hexdigest(), "hash_status": HASH_VERIFIED}


def _asset_to_resource(a: Dict[str, Any]) -> AssetResource:
    provenance = dict(a.get("provenance") or {})
    provenance.setdefault("hash_status", HASH_UNVERIFIED)
    return AssetResource(
        id=a["id"],
        name=a["name"],
        type=a.get("type", "IMAGE"),
        episode_id=a.get("episode_id"),
        project_id=a.get("project_id"),
        scene_id=a.get("scene_id"),
        character_id=a.get("character_id"),
        requirement_id=a.get("requirement_id"),
        current_revision_id=a.get("current_revision_id"),
        status=a.get("status", "DRAFT"),
        provenance=AssetProvenance(**provenance),
        approval_pin=ApprovalPin(**a["approval_pin"]) if a.get("approval_pin") else None,
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
    """Create an asset record with full provenance chain.

    P1.3.4: the content hash is SHA-256 over the ACTUAL bytes when
    ``content_base64`` is provided; without verifiable content the asset is
    marked HASH_UNVERIFIED and can never be PINNED.
    """
    if body.requirement_id:
        requirement = await service.get(NS_ASSET_REQUIREMENTS, body.requirement_id)
        if requirement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "REQUIREMENT_NOT_FOUND", "message": f"Asset requirement '{body.requirement_id}' not found."},
            )

    asset_id = f"asset-{uuid.uuid4().hex[:8]}"
    rev_id = f"rev-{asset_id}-v1"
    now = utc_now().isoformat()
    hash_result = _hash_actual_bytes(body.content_base64)
    provenance_data: Dict[str, Any] = {
        "source": body.source,
        "generator": body.generator,
        "model": body.model,
        "prompt": body.prompt,
        "reference_ids": list(body.reference_ids),
        "job_id": body.job_id,
        "content_hash": hash_result["content_hash"],
        "hash_status": hash_result["hash_status"],
        "parent_revision_id": body.parent_revision_id,
        "created_at": now,
    }
    initial_status = ASSET_STATUS_DRAFT
    new_asset: Dict[str, Any] = {
        "id": asset_id,
        "name": body.name,
        "type": body.type,
        "episode_id": body.episode_id,
        "project_id": body.project_id,
        "scene_id": body.scene_id,
        "character_id": body.character_id,
        "requirement_id": body.requirement_id,
        "current_revision_id": rev_id,
        "status": initial_status,
        "provenance": provenance_data,
        "created_at": now,
        "updated_at": now,
    }
    created = await service.create(NS_ASSETS, asset_id, new_asset)
    await service.create(NS_ASSET_REVISIONS, rev_id, {
        "revision_id": rev_id,
        "asset_id": asset_id,
        "version": 1,
        "status": initial_status,
        "media_url": body.media_url,
        "provenance": provenance_data,
        "created_at": now,
    })
    if body.requirement_id:
        requirement = await service.get(NS_ASSET_REQUIREMENTS, body.requirement_id)
        req_updates = dict(requirement)
        req_updates["linked_asset_id"] = asset_id
        req_updates["status"] = "FULFILLED"
        req_updates["updated_at"] = now
        await service.update(NS_ASSET_REQUIREMENTS, body.requirement_id, req_updates, requirement.get("version", 1))
    return _asset_to_resource(created)


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


@router.post("/{asset_id}/revisions", response_model=AssetRevisionResource, status_code=status.HTTP_201_CREATED, operation_id="assets.addRevision")
async def add_asset_revision(
    asset_id: str = Path(...),
    body: AddAssetRevisionRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetRevisionResource:
    """Pin a NEW immutable revision with a hash over its actual bytes."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = [r for r in await service.list(NS_ASSET_REVISIONS) if r.get("asset_id") == asset_id]
    next_version = max((int(r.get("version", 0)) for r in revisions), default=0) + 1
    rev_id = f"rev-{asset_id}-v{next_version}"
    now = utc_now().isoformat()
    hash_result = _hash_actual_bytes(body.content_base64)
    prev_prov = dict(asset.get("provenance") or {})
    provenance_data: Dict[str, Any] = {
        "source": body.source or prev_prov.get("source") or "GENERATED",
        "generator": body.generator or prev_prov.get("generator"),
        "model": body.model or prev_prov.get("model"),
        "prompt": body.prompt if body.prompt is not None else prev_prov.get("prompt"),
        "reference_ids": list(body.reference_ids) or list(prev_prov.get("reference_ids") or []),
        "job_id": body.job_id or prev_prov.get("job_id"),
        "content_hash": hash_result["content_hash"],
        "hash_status": hash_result["hash_status"],
        "parent_revision_id": body.parent_revision_id or asset.get("current_revision_id"),
        "created_at": now,
    }
    revision = {
        "revision_id": rev_id,
        "asset_id": asset_id,
        "version": next_version,
        "status": ASSET_STATUS_DRAFT,
        "media_url": body.media_url,
        "provenance": provenance_data,
        "created_at": now,
    }
    created_rev = await service.create(NS_ASSET_REVISIONS, rev_id, revision)

    # A new revision supersedes a previously approved/pinned state: the asset
    # returns to DRAFT until the new revision is approved again.
    updates = dict(asset)
    updates["current_revision_id"] = rev_id
    updates["status"] = ASSET_STATUS_DRAFT
    updates["provenance"] = provenance_data
    updates["updated_at"] = now
    await service.update(NS_ASSETS, asset_id, updates, asset.get("version", 1))
    return AssetRevisionResource(**created_rev)


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
    revs.sort(key=lambda r: int(r.get("version", 0)))
    out: List[AssetRevisionResource] = []
    for r in revs:
        prov = dict(r.get("provenance") or {})
        prov.setdefault("hash_status", HASH_UNVERIFIED)
        pin = r.get("approval_pin")
        out.append(AssetRevisionResource(
            revision_id=r["revision_id"],
            asset_id=r["asset_id"],
            version=r.get("version", 1),
            status=r.get("status", "DRAFT"),
            media_url=r.get("media_url"),
            provenance=AssetProvenance(**prov),
            approval_pin=ApprovalPin(**pin) if pin else None,
            created_at=r.get("created_at", ""),
        ))
    return out


@router.get("/{asset_id}/provenance", response_model=AssetProvenance, operation_id="assets.getProvenance")
async def get_asset_provenance(
    asset_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetProvenance:
    """Get the provenance chain for an asset."""
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    prov = dict(asset.get("provenance") or {})
    prov.setdefault("hash_status", HASH_UNVERIFIED)
    return AssetProvenance(**prov)


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


@router.post("/{asset_id}/actions/set-status", response_model=AssetResource, operation_id="assets.setStatus")
async def set_asset_status(
    asset_id: str = Path(...),
    body: SetAssetStatusRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
    """Advance the asset lifecycle one step at a time (plan P1.3.2).

    PINNED fails closed unless the current revision is approved AND its
    content hash is VERIFIED — HASH_UNVERIFIED content can never be pinned.
    """
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    if asset["version"] != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict for asset '{asset_id}'. Expected {asset['version']}, got {body.expected_version}.",
        )
    if body.status not in _ASSET_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown asset status '{body.status}'.")

    current = asset.get("status", ASSET_STATUS_DRAFT)
    if body.status != current and body.status not in _allowed_transitions(current):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "INVALID_ASSET_STATUS_TRANSITION",
                "message": (
                    f"Asset '{asset_id}' cannot move from '{current}' to '{body.status}'; "
                    "the lifecycle advances one step at a time."
                ),
            },
        )

    if body.status == ASSET_STATUS_PINNED:
        if asset.get("status") != ASSET_STATUS_APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "ASSET_NOT_APPROVED",
                    "message": f"Asset '{asset_id}' must be APPROVED before it can be PINNED.",
                },
            )
        prov = dict(asset.get("provenance") or {})
        if prov.get("hash_status") != HASH_VERIFIED or not prov.get("content_hash"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "ASSET_HASH_UNVERIFIED",
                    "message": (
                        f"Asset '{asset_id}' content hash is not verified; "
                        "HASH_UNVERIFIED assets can never be PINNED."
                    ),
                },
            )

    now = utc_now().isoformat()
    updates = dict(asset)
    updates["status"] = body.status
    updates["updated_at"] = now
    updated = await service.update(NS_ASSETS, asset_id, updates, asset.get("version", 1))
    return _asset_to_resource(updated or updates)


@router.post("/{asset_id}/actions/approve", response_model=AssetResource, operation_id="assets.approve")
async def approve_asset(
    asset_id: str = Path(...),
    body: ApproveAssetRequest = ...,
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> AssetResource:
    """Approve a SPECIFIC revision (plan P1.3.6) and record its approval pin.

    The pin carries asset_id + revision_id + content_hash + approved_by +
    approved_at — never a floating "latest".
    """
    asset = await service.get(NS_ASSETS, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found.")
    revisions = [r for r in await service.list(NS_ASSET_REVISIONS) if r.get("asset_id") == asset_id]
    target = next((r for r in revisions if r["revision_id"] == body.revision_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    pin = {
        "asset_id": asset_id,
        "revision_id": body.revision_id,
        "content_hash": str((target.get("provenance") or {}).get("content_hash") or ""),
        "approved_by": body.approved_by,
        "approved_at": now,
    }

    updates = dict(asset)
    updates["status"] = ASSET_STATUS_APPROVED
    updates["approval_pin"] = pin
    updates["updated_at"] = now
    updated = await service.update(NS_ASSETS, asset_id, updates, asset["version"])

    rev_updates = dict(target)
    rev_updates["status"] = ASSET_STATUS_APPROVED
    rev_updates["approval_pin"] = pin
    await service.update(NS_ASSET_REVISIONS, target["revision_id"], rev_updates, target.get("version", 1))

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
    revisions = [r for r in await service.list(NS_ASSET_REVISIONS) if r.get("asset_id") == asset_id]
    rev_ids = {r["revision_id"] for r in revisions}
    if body.revision_id not in rev_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Revision '{body.revision_id}' not found for asset '{asset_id}'.")

    now = utc_now().isoformat()
    updates = dict(asset)
    updates["status"] = ASSET_STATUS_REJECTED
    updates["updated_at"] = now
    updated = await service.update(NS_ASSETS, asset_id, updates, asset["version"])

    for r in revisions:
        if r["revision_id"] == body.revision_id:
            rev_updates = dict(r)
            rev_updates["status"] = ASSET_STATUS_REJECTED
            await service.update(NS_ASSET_REVISIONS, r["revision_id"], rev_updates, r.get("version", 1))
            break

    return _asset_to_resource(updated)


# ─────────────────────────────────────────────────────────────────────────────
# P1.3.1 Asset Requirements — deterministic extraction from locked screenplay
# ─────────────────────────────────────────────────────────────────────────────


@req_router.get("/projects/{project_id}/assets/requirements", response_model=List[AssetRequirementResource], operation_id="assets.listProjectRequirements")
async def list_project_requirements(
    project_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[AssetRequirementResource]:
    reqs = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if r.get("project_id") == project_id
    ]
    reqs.sort(key=lambda r: (r.get("type", ""), str(r.get("name", ""))))
    return [AssetRequirementResource(**r) for r in reqs]


@req_router.get("/episodes/{episode_id}/assets/requirements", response_model=List[AssetRequirementResource], operation_id="assets.listEpisodeRequirements")
async def list_episode_requirements(
    episode_id: str = Path(...),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> List[AssetRequirementResource]:
    reqs = [
        r for r in await service.list(NS_ASSET_REQUIREMENTS)
        if r.get("episode_id") == episode_id
    ]
    reqs.sort(key=lambda r: (r.get("type", ""), str(r.get("name", ""))))
    return [AssetRequirementResource(**r) for r in reqs]


@req_router.post("/episodes/{episode_id}/assets/requirements/actions/sync", response_model=Dict[str, Any], operation_id="assets.syncRequirements")
async def sync_asset_requirements(
    episode_id: str = Path(...),
    project_id: Optional[str] = Query(None),
    service: V3ResourceService = Depends(get_v3_resource_service),
) -> Dict[str, Any]:
    """Deterministically extract asset requirements from the locked screenplay.

    Fail closed with 409 SCREENPLAY_NOT_LOCKED when there is no lock.
    Idempotent: existing requirements are never duplicated or mutated.
    """
    ep = await service.get("episodes", episode_id)
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "EPISODE_NOT_FOUND", "message": f"Episode '{episode_id}' not found."},
        )
    resolved_project = project_id or ep.get("project_id")
    if not resolved_project:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "PROJECT_UNRESOLVED", "message": "project_id query parameter is required when the episode has no project."},
        )

    before = {
        (r.get("type"), str(r.get("name", "")).strip().lower())
        for r in await service.list(NS_ASSET_REQUIREMENTS)
        if r.get("episode_id") == episode_id
    }
    try:
        requirements, lineage = await build_asset_requirements(
            service, resolved_project, episode_id, utc_now().isoformat()
        )
    except PreproductionAuthorityError as exc:
        raise HTTPException(status_code=exc.http_status, detail={"error_code": exc.code, "message": exc.message}) from exc

    after = {
        (r.get("type"), str(r.get("name", "")).strip().lower())
        for r in requirements
    }
    created_keys = after - before
    created = [r for r in requirements if (r.get("type"), str(r.get("name", "")).strip().lower()) in created_keys]

    return {
        "episode_id": episode_id,
        "project_id": resolved_project,
        "created": created,
        "created_count": len(created),
        "unchanged_count": len(requirements) - len(created),
        "total_count": len(requirements),
        "lineage": lineage,
    }
