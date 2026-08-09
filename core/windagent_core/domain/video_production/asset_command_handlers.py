"""
Asset Command Handlers (Stage D UI23).

Provides domain handler logic for executing universal asset commands:
- IMPORT_ASSET / UPLOAD_ASSET / DISCOVER_ASSET / DOWNLOAD_ASSET
- REQUEST_ASSET_GENERATION
- NORMALIZE_ASSET / VALIDATE_ASSET
- APPROVE_ASSET / REJECT_ASSET / UPDATE_LICENSE
- CREATE_ASSET_REVISION
- BIND_ASSET / UNBIND_ASSET / ARCHIVE_ASSET
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Dict

from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
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
    WorkspaceCommandStatus,
)


class AssetCommandHandler:
    """Domain engine for processing mutating asset commands."""

    def __init__(self, asset_store: Dict[str, ProductionAsset], revision_store: Dict[str, AssetRevision]) -> None:
        self.asset_store = asset_store
        self.revision_store = revision_store

    def handle(self, request: WorkspaceCommandRequest) -> Dict[str, Any]:
        cmd_type = request.command_type.value if hasattr(request.command_type, "value") else str(request.command_type)
        payload = request.payload or {}

        if cmd_type in ("IMPORT_ASSET", "UPLOAD_ASSET", "DISCOVER_ASSET", "DOWNLOAD_ASSET"):
            return self._handle_import_or_upload(request, payload)
        elif cmd_type == "CREATE_ASSET_REVISION":
            return self._handle_create_revision(request, payload)
        elif cmd_type == "APPROVE_ASSET":
            return self._handle_approve_asset(request, payload)
        elif cmd_type == "REJECT_ASSET":
            return self._handle_reject_asset(request, payload)
        elif cmd_type == "UPDATE_LICENSE":
            return self._handle_update_license(request, payload)
        elif cmd_type == "BIND_ASSET":
            return self._handle_bind_asset(request, payload)
        elif cmd_type == "UNBIND_ASSET":
            return self._handle_unbind_asset(request, payload)
        elif cmd_type == "ARCHIVE_ASSET":
            return self._handle_archive_asset(request, payload)
        elif cmd_type == "REQUEST_ASSET_GENERATION":
            return self._handle_request_generation(request, payload)
        else:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Unsupported asset command type: {cmd_type}",
                "payload": {},
            }

    def _handle_import_or_upload(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id or f"ast_{uuid.uuid4().hex[:12]}"
        name = payload.get("name", "Untitled Asset")
        kind_str = payload.get("kind", ProductionAssetKind.OTHER.value)
        kind = ProductionAssetKind(kind_str) if kind_str in ProductionAssetKind.__members__ else ProductionAssetKind.OTHER
        media_type = MediaType(payload.get("media_type", MediaType.IMAGE.value))
        mime_type = payload.get("mime_type", "image/png")
        content_hash = payload.get("content_hash") or hashlib.sha256(name.encode("utf-8")).hexdigest()
        size_bytes = payload.get("size_bytes", 1024)
        license_state = LicenseState(payload.get("license_state", LicenseState.UNKNOWN.value))
        source_type = AssetSourceType(payload.get("source_type", AssetSourceType.UPLOADED.value))

        asset = ProductionAsset(
            asset_id=asset_id,
            kind=kind,
            name=name,
            description=payload.get("description", ""),
            tags=payload.get("tags", []),
            source_type=source_type,
            license_state=license_state,
            lifecycle_state=AssetLifecycleState.DOWNLOADED,
            processing_state=AssetProcessingState.NORMALIZING,
            metadata=payload.get("metadata", {}),
        )

        rev_id = f"rev_{uuid.uuid4().hex[:12]}"
        revision = AssetRevision(
            revision_id=rev_id,
            asset_id=asset_id,
            content_hash=content_hash,
            media_type=media_type,
            mime_type=mime_type,
            size_bytes=size_bytes,
            provenance={
                "source_url": payload.get("source_url"),
                "author": request.client_context.get("user", "system"),
                "imported_at": asset.created_at.isoformat(),
            },
            preview_artifacts=payload.get("preview_artifacts", {}),
        )

        asset.set_active_revision(rev_id)
        self.asset_store[asset_id] = asset
        self.revision_store[rev_id] = revision

        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' imported/uploaded successfully.",
            "payload": {
                "asset_id": asset_id,
                "revision_id": rev_id,
                "lifecycle_state": asset.lifecycle_state.value,
                "processing_state": asset.processing_state.value,
            },
        }

    def _handle_create_revision(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        content_hash = payload.get("content_hash") or hashlib.sha256(f"rev_{uuid.uuid4().hex}".encode("utf-8")).hexdigest()
        rev_id = f"rev_{uuid.uuid4().hex[:12]}"
        revision = AssetRevision(
            revision_id=rev_id,
            asset_id=asset_id,
            supersedes_revision_id=asset.active_revision_id,
            content_hash=content_hash,
            media_type=MediaType(payload.get("media_type", MediaType.IMAGE.value)),
            mime_type=payload.get("mime_type", "image/png"),
            size_bytes=payload.get("size_bytes", 1024),
            provenance=payload.get("provenance", {}),
            preview_artifacts=payload.get("preview_artifacts", {}),
        )

        asset.set_active_revision(rev_id)
        self.revision_store[rev_id] = revision

        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"New revision '{rev_id}' created for asset '{asset_id}'.",
            "payload": {"asset_id": asset_id, "revision_id": rev_id},
        }

    def _handle_approve_asset(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        # Human approval sets review record
        if asset.lifecycle_state == AssetLifecycleState.DOWNLOADED:
            asset.update_lifecycle_state(AssetLifecycleState.VALIDATED)
        asset.update_lifecycle_state(AssetLifecycleState.APPROVED, new_review_record=True)
        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' approved.",
            "payload": {"asset_id": asset_id, "lifecycle_state": asset.lifecycle_state.value},
        }

    def _handle_reject_asset(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        asset.update_lifecycle_state(AssetLifecycleState.REJECTED)
        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' rejected.",
            "payload": {"asset_id": asset_id, "lifecycle_state": asset.lifecycle_state.value},
        }

    def _handle_update_license(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        license_state = LicenseState(payload.get("license_state", LicenseState.UNKNOWN.value))
        asset.license_state = license_state
        if "notes" in payload:
            asset.metadata["license_notes"] = payload["notes"]

        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' license updated to '{license_state.value}'.",
            "payload": {"asset_id": asset_id, "license_state": asset.license_state.value},
        }

    def _handle_bind_asset(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        # Stage E Eligibility Evaluation
        from windagent_core.domain.video_production.asset_eligibility_service import AssetEligibilityService
        from windagent_core.domain.video_production.script_asset_binding import (
            BindingStatus,
            ProductionAssetBinding,
            ScreenplayEntityType,
        )

        entity_type_str = payload.get("screenplay_entity_type", "CHARACTER")
        entity_type = (
            ScreenplayEntityType(entity_type_str)
            if entity_type_str in ScreenplayEntityType.__members__
            else ScreenplayEntityType.CHARACTER
        )
        entity_id = payload.get("screenplay_entity_id", "char_unknown")

        eligibility_svc = AssetEligibilityService()
        eligibility = eligibility_svc.evaluate_eligibility(
            asset=asset,
            revision=self.revision_store.get(asset.active_revision_id or ""),
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=str(request.project_id),
            target_revision_id=str(request.target_revision_id),
        )

        if not eligibility.is_eligible and not payload.get("force", False):
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' is ineligible for binding: {'; '.join(eligibility.blocking_reasons)}",
                "payload": eligibility.to_dict(),
            }

        project_id = str(request.project_id)
        if project_id not in asset.project_bindings:
            asset.project_bindings.append(project_id)

        if asset.lifecycle_state == AssetLifecycleState.APPROVED:
            asset.update_lifecycle_state(AssetLifecycleState.BOUND_TO_PROJECT)

        binding_id = f"bnd_{uuid.uuid4().hex[:12]}"
        binding = ProductionAssetBinding(
            binding_id=binding_id,
            project_id=project_id,
            production_revision_id=str(request.target_revision_id),
            screenplay_entity_type=entity_type,
            screenplay_entity_id=entity_id,
            role_key=payload.get("role_key", "primary"),
            asset_id=asset_id,
            asset_revision_id=asset.active_revision_id or f"rev_{uuid.uuid4().hex[:8]}",
            status=BindingStatus.ACTIVE,
            created_by=request.client_context.get("user", "user") if request.client_context else "user",
        )

        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' bound to entity '{entity_id}' ({entity_type.value}) in project '{project_id}'.",
            "payload": {
                "binding": binding.to_dict(),
                "asset_id": asset_id,
                "project_bindings": asset.project_bindings,
                "eligibility": eligibility.to_dict(),
            },
        }

    def _handle_unbind_asset(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        project_id = str(request.project_id)
        if project_id in asset.project_bindings:
            asset.project_bindings.remove(project_id)

        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' unbound from project '{project_id}'.",
            "payload": {
                "asset_id": asset_id,
                "binding_id": payload.get("binding_id"),
                "screenplay_entity_id": payload.get("screenplay_entity_id"),
                "project_bindings": asset.project_bindings,
            },
        }

    def _handle_archive_asset(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {
                "command_id": request.command_id,
                "status": WorkspaceCommandStatus.FAILED.value,
                "message": f"Asset '{asset_id}' not found.",
                "payload": {},
            }

        asset.metadata["archived"] = True
        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset '{asset_id}' archived.",
            "payload": {"asset_id": asset_id, "archived": True},
        }

    def _handle_request_generation(self, request: WorkspaceCommandRequest, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset_id = request.entity_id or f"ast_{uuid.uuid4().hex[:12]}"
        name = payload.get("name", "Generated Asset")
        kind_str = payload.get("kind", ProductionAssetKind.OTHER.value)
        kind = ProductionAssetKind(kind_str) if kind_str in ProductionAssetKind.__members__ else ProductionAssetKind.OTHER

        asset = ProductionAsset(
            asset_id=asset_id,
            kind=kind,
            name=name,
            description=payload.get("prompt", ""),
            source_type=AssetSourceType.GENERATED,
            lifecycle_state=AssetLifecycleState.DISCOVERED,
            processing_state=AssetProcessingState.PROCESSING,
            metadata={"generation_request": payload},
        )

        self.asset_store[asset_id] = asset
        return {
            "command_id": request.command_id,
            "status": WorkspaceCommandStatus.COMPLETED.value,
            "updated_revision_id": str(request.target_revision_id),
            "message": f"Asset generation requested for asset '{asset_id}'.",
            "payload": {"asset_id": asset_id, "processing_state": asset.processing_state.value},
        }


__all__ = ["AssetCommandHandler"]
