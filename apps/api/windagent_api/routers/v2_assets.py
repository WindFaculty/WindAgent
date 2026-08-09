"""
API V2 Universal Production Asset Router (Stage D — Universal Production Asset Domain).

Exposes endpoints for:
- Asset library listing with cursor pagination, multi-faceted filtering, and search
- Asset aggregate detail, revision lineage, validation reports, provenance, bindings, and dependencies
- Mutating command dispatch (upload, import, approve, reject, license update, revision creation, binding)
- Version replacement impact analysis and revision diff comparison
- Authorized artifact token access
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.asset_command_handlers import AssetCommandHandler
from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_core.domain.video_production.asset_query_service import AssetQueryService
from windagent_core.domain.video_production.enums import (
    AssetProcessingState,
    AssetSourceType,
    LicenseState,
    MediaType,
    ProductionAssetKind,
)
from windagent_core.domain.video_production.production_asset import (
    AssetRevision,
    ProductionAsset,
)
from windagent_core.domain.video_production.workspace import (
    WorkspaceCommandRequest,
    WorkspaceCommandType,
)

router = APIRouter(prefix="/api/v2/video-production/assets", tags=["production-assets"])

# Global in-memory asset store for V2 Asset Domain
_ASSET_STORE: Dict[str, ProductionAsset] = {}
_REVISION_STORE: Dict[str, AssetRevision] = {}


def _seed_demo_assets_if_empty() -> None:
    if _ASSET_STORE:
        return
    # Seed baseline assets for dev / testing
    a1 = ProductionAsset(
        asset_id="ast_hero_01",
        kind=ProductionAssetKind.CHARACTER,
        name="Hero Character Model",
        description="Main protagonist 3D character model",
        lifecycle_state=AssetLifecycleState.APPROVED,
        processing_state=AssetProcessingState.IDLE,
        license_state=LicenseState.LICENSED,
        source_type=AssetSourceType.UPLOADED,
        project_bindings=["prj_default"],
        tags=["hero", "3d", "character"],
    )
    r1 = AssetRevision(
        revision_id="rev_hero_v1",
        asset_id="ast_hero_01",
        content_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        media_type=MediaType.MODEL_3D,
        mime_type="model/gltf-binary",
        size_bytes=10485760,
        preview_artifacts={"glb_uri": "/api/v2/video-production/assets/ast_hero_01/artifacts/glb"},
        provenance={"author": "ArtTeam", "license": "Proprietary"},
    )
    a1.set_active_revision(r1.revision_id)

    a2 = ProductionAsset(
        asset_id="ast_bgm_01",
        kind=ProductionAssetKind.MUSIC,
        name="Epic Theme Track",
        description="Orchestral soundtrack for climax scene",
        lifecycle_state=AssetLifecycleState.APPROVED,
        processing_state=AssetProcessingState.IDLE,
        license_state=LicenseState.CREATIVE_COMMONS,
        source_type=AssetSourceType.INTERNET,
        project_bindings=["prj_default"],
        tags=["music", "soundtrack"],
    )
    r2 = AssetRevision(
        revision_id="rev_bgm_v1",
        asset_id="ast_bgm_01",
        content_hash="a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
        media_type=MediaType.AUDIO,
        mime_type="audio/mp3",
        size_bytes=5242880,
        preview_artifacts={"waveform_uri": "/api/v2/video-production/assets/ast_bgm_01/artifacts/waveform"},
        provenance={"source_url": "https://example.com/audio.mp3", "license": "CC-BY-4.0"},
    )
    a2.set_active_revision(r2.revision_id)

    _ASSET_STORE[a1.asset_id] = a1
    _REVISION_STORE[r1.revision_id] = r1
    _ASSET_STORE[a2.asset_id] = a2
    _REVISION_STORE[r2.revision_id] = r2


_seed_demo_assets_if_empty()


class AssetCommandSchema(BaseModel):
    command_type: str
    project_id: str
    target_revision_id: str
    entity_id: str
    reason: str = ""
    idempotency_key: str = Field(default_factory=lambda: f"idemp_{uuid.uuid4().hex[:12]}")
    payload: Dict[str, Any] = Field(default_factory=dict)
    client_context: Dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=Dict[str, Any])
async def list_assets(
    project_id: Optional[str] = Query(None, description="Filter by bound VideoProject ID"),
    kind: Optional[str] = Query(None, description="Filter by ProductionAssetKind"),
    lifecycle_state: Optional[str] = Query(None, description="Filter by AssetLifecycleState"),
    processing_state: Optional[str] = Query(None, description="Filter by AssetProcessingState"),
    license_state: Optional[str] = Query(None, description="Filter by LicenseState"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    q: Optional[str] = Query(None, description="Free-text search term"),
    cursor: int = Query(0, ge=0, description="Pagination offset cursor"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> Dict[str, Any]:
    """List production assets with multi-attribute filtering and pagination (UI22)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    return qs.list_assets(
        project_id=project_id,
        kind=kind,
        lifecycle_state=lifecycle_state,
        processing_state=processing_state,
        license_state=license_state,
        tag=tag,
        query=q,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{asset_id}", response_model=Dict[str, Any])
async def get_asset_detail(asset_id: str) -> Dict[str, Any]:
    """Get full aggregate details for an asset (UI25 Overview tab)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    detail = qs.get_asset_detail(asset_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_FOUND", "message": f"Asset '{asset_id}' not found."},
        )
    return detail


@router.get("/{asset_id}/revisions", response_model=Dict[str, Any])
async def get_asset_revisions(asset_id: str) -> Dict[str, Any]:
    """Get revision lineage list (UI25 Versions tab)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    revisions = qs.get_asset_revisions(asset_id)
    return {"asset_id": asset_id, "revisions": revisions}


@router.get("/{asset_id}/provenance", response_model=Dict[str, Any])
async def get_asset_provenance(asset_id: str) -> Dict[str, Any]:
    """Get provenance evidence (UI25 Provenance tab)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    return qs.get_asset_provenance(asset_id)


@router.get("/{asset_id}/dependencies", response_model=Dict[str, Any])
async def get_asset_dependencies(asset_id: str) -> Dict[str, Any]:
    """Get asset dependency graph (UI32)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    return qs.get_asset_dependencies(asset_id)


@router.post("/commands", response_model=Dict[str, Any])
async def execute_asset_command(body: AssetCommandSchema) -> Dict[str, Any]:
    """Execute a mutating asset command (UI23)."""
    handler = AssetCommandHandler(_ASSET_STORE, _REVISION_STORE)
    req = WorkspaceCommandRequest(
        command_id=f"cmd_{uuid.uuid4().hex[:12]}",
        command_type=WorkspaceCommandType(body.command_type) if body.command_type in WorkspaceCommandType.__members__ else body.command_type,
        project_id=body.project_id,
        target_revision_id=body.target_revision_id,
        entity_id=body.entity_id,
        reason=body.reason,
        idempotency_key=body.idempotency_key,
        payload=body.payload,
        client_context=body.client_context,
    )
    result = handler.handle(req)
    if result.get("status") == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "ASSET_COMMAND_FAILED", "message": result.get("message")},
        )
    return result


@router.post("/{asset_id}/compare", response_model=Dict[str, Any])
async def compare_asset_revisions(
    asset_id: str,
    old_revision_id: str = Query(...),
    new_revision_id: str = Query(...),
) -> Dict[str, Any]:
    """Compare asset revisions and compute version replacement impact (UI33)."""
    qs = AssetQueryService(_ASSET_STORE, _REVISION_STORE)
    return qs.compare_revisions(asset_id, old_revision_id, new_revision_id)


@router.get("/{asset_id}/artifacts/{artifact_key}")
async def get_authorized_artifact(asset_id: str, artifact_key: str) -> Dict[str, Any]:
    """Get authorized access token / metadata for preview derivative delivery (UI27, UI28)."""
    asset = _ASSET_STORE.get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Server-side license governance enforcement (UI26)
    if not asset.is_eligible_for_production() and artifact_key not in ("thumbnail", "preview"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "LICENSE_BLOCKED",
                "message": f"Asset '{asset_id}' has license state '{asset.license_state.value}' and cannot be delivered for production.",
            },
        )

    return {
        "asset_id": asset_id,
        "artifact_key": artifact_key,
        "download_url": f"https://cdn.windagent.io/artifacts/{asset_id}_{artifact_key}.bin",
        "expires_in_seconds": 3600,
        "content_type": "application/octet-stream",
    }


__all__ = ["router"]
