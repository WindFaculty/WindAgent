"""
Asset Query Service (Stage D UI22, UI25, UI32, UI33).

Provides query projections for:
- Asset library listing with cursor pagination, multi-faceted filtering, and deterministic sorting
- Detail inspection (overview, revisions lineage, validation report, provenance evidence, bindings, dependencies)
- Usage and dependency graph calculation (project -> scene -> shot)
- Revision diff and version impact analysis
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.production_asset import (
    AssetRevision,
    ProductionAsset,
)


class AssetQueryService:
    """Read-model query service for the Universal Production Asset Library."""

    def __init__(self, asset_store: Dict[str, ProductionAsset], revision_store: Dict[str, AssetRevision]) -> None:
        self.asset_store = asset_store
        self.revision_store = revision_store

    def list_assets(
        self,
        *,
        project_id: Optional[str] = None,
        kind: Optional[str] = None,
        lifecycle_state: Optional[str] = None,
        processing_state: Optional[str] = None,
        license_state: Optional[str] = None,
        tag: Optional[str] = None,
        query: Optional[str] = None,
        cursor: Optional[int] = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List assets with cursor pagination and multi-attribute filters (UI22)."""
        filtered: List[ProductionAsset] = []

        for asset in self.asset_store.values():
            if asset.metadata.get("archived") is True:
                continue
            if project_id and project_id not in asset.project_bindings:
                continue
            if kind and asset.kind.value != kind and asset.kind.name != kind:
                continue
            if lifecycle_state and asset.lifecycle_state.value != lifecycle_state:
                continue
            if processing_state and asset.processing_state.value != processing_state:
                continue
            if license_state and asset.license_state.value != license_state:
                continue
            if tag and tag not in asset.tags:
                continue
            if query:
                q = query.lower()
                if q not in asset.name.lower() and q not in asset.description.lower():
                    continue
            filtered.append(asset)

        # Deterministic sort by updated_at desc, asset_id asc
        filtered.sort(key=lambda a: (a.updated_at.timestamp(), a.asset_id), reverse=True)

        offset = cursor or 0
        page = filtered[offset : offset + limit]
        next_cursor = offset + limit if offset + limit < len(filtered) else None

        items = []
        for a in page:
            active_rev = self.revision_store.get(a.active_revision_id) if a.active_revision_id else None
            items.append({
                "asset_id": a.asset_id,
                "kind": a.kind.value,
                "name": a.name,
                "description": a.description,
                "lifecycle_state": a.lifecycle_state.value,
                "processing_state": a.processing_state.value,
                "license_state": a.license_state.value,
                "source_type": a.source_type.value,
                "active_revision_id": a.active_revision_id,
                "content_hash": active_rev.content_hash if active_rev else None,
                "media_type": active_rev.media_type.value if active_rev else "unknown",
                "preview_artifacts": active_rev.preview_artifacts if active_rev else {},
                "project_bindings": a.project_bindings,
                "tags": a.tags,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
            })

        return {
            "items": items,
            "total_count": len(filtered),
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
        }

    def get_asset_detail(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get consolidated aggregate detail for inspector Overview tab (UI25)."""
        asset = self.asset_store.get(asset_id)
        if not asset:
            return None

        revisions = [
            rev.model_dump(mode="json")
            for rev in self.revision_store.values()
            if rev.asset_id == asset_id
        ]
        revisions.sort(key=lambda r: r.get("created_at", ""), reverse=True)

        active_rev = self.revision_store.get(asset.active_revision_id) if asset.active_revision_id else None

        return {
            "asset": asset.model_dump(mode="json"),
            "active_revision": active_rev.model_dump(mode="json") if active_rev else None,
            "revisions_count": len(revisions),
            "is_eligible_for_production": asset.is_eligible_for_production(),
        }

    def get_asset_revisions(self, asset_id: str) -> List[Dict[str, Any]]:
        """Get revision lineage list (UI25 Versions tab)."""
        revisions = [
            rev.model_dump(mode="json")
            for rev in self.revision_store.values()
            if rev.asset_id == asset_id
        ]
        revisions.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return revisions

    def get_asset_provenance(self, asset_id: str) -> Dict[str, Any]:
        """Get provenance evidence (UI25 Provenance tab)."""
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {}
        active_rev = self.revision_store.get(asset.active_revision_id) if asset.active_revision_id else None
        return {
            "asset_id": asset_id,
            "source_type": asset.source_type.value,
            "license_state": asset.license_state.value,
            "provenance": active_rev.provenance if active_rev else {},
        }

    def get_asset_dependencies(self, asset_id: str) -> Dict[str, Any]:
        """Get asset dependency graph nodes and edges (UI32)."""
        asset = self.asset_store.get(asset_id)
        if not asset:
            return {"nodes": [], "edges": []}

        nodes = [{"id": asset.asset_id, "label": asset.name, "kind": asset.kind.value}]
        edges = []

        for dep_id in asset.dependencies:
            dep_asset = self.asset_store.get(dep_id)
            if dep_asset:
                nodes.append({"id": dep_asset.asset_id, "label": dep_asset.name, "kind": dep_asset.kind.value})
                edges.append({"source": asset.asset_id, "target": dep_asset.asset_id, "type": "DEPENDS_ON"})

        return {"nodes": nodes, "edges": edges}

    def compare_revisions(self, asset_id: str, old_revision_id: str, new_revision_id: str) -> Dict[str, Any]:
        """Compare old and candidate asset revisions for version replacement (UI33)."""
        old_rev = self.revision_store.get(old_revision_id)
        new_rev = self.revision_store.get(new_revision_id)
        asset = self.asset_store.get(asset_id)

        if not old_rev or not new_rev or not asset:
            return {"error": "REVISION_NOT_FOUND", "message": "One or both revisions do not exist."}

        # Impacted project bindings
        impacted_projects = list(asset.project_bindings)

        return {
            "asset_id": asset_id,
            "old_revision": old_rev.model_dump(mode="json"),
            "new_revision": new_rev.model_dump(mode="json"),
            "hash_changed": old_rev.content_hash != new_rev.content_hash,
            "size_diff_bytes": new_rev.size_bytes - old_rev.size_bytes,
            "impacted_projects_count": len(impacted_projects),
            "impacted_projects": impacted_projects,
        }


__all__ = ["AssetQueryService"]
