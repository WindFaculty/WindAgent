"""
Stage E — Script ↔ Asset Projection Engine.

Maintains convergent read-model projections for Script Inspector binding summary
and Asset Manager usage projection from the event stream.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.script_asset_binding import (
    BindingStatus,
    ProductionAssetBinding,
    ScreenplayEntityType,
)


class ScriptInspectorBindingSummary(BaseModel):
    """Read-model projection for Script Inspector entity binding panel."""

    model_config = ConfigDict(frozen=True, extra="allow")

    project_id: str
    revision_id: str
    bound_character_count: int = 0
    missing_character_count: int = 0
    bound_location_count: int = 0
    missing_location_count: int = 0
    bound_prop_count: int = 0
    missing_prop_count: int = 0
    total_requirements: int = 0
    fulfilled_requirements: int = 0
    bindings: List[ProductionAssetBinding] = Field(default_factory=list)

    @property
    def completion_percentage(self) -> float:
        if self.total_requirements == 0:
            return 100.0
        return round((self.fulfilled_requirements / self.total_requirements) * 100.0, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "bound_character_count": self.bound_character_count,
            "missing_character_count": self.missing_character_count,
            "bound_location_count": self.bound_location_count,
            "missing_location_count": self.missing_location_count,
            "bound_prop_count": self.bound_prop_count,
            "missing_prop_count": self.missing_prop_count,
            "total_requirements": self.total_requirements,
            "fulfilled_requirements": self.fulfilled_requirements,
            "completion_percentage": self.completion_percentage,
            "bindings": [b.to_dict() for b in self.bindings],
        }


class AssetUsageProjection(BaseModel):
    """Read-model projection tracking which screenplay entities consume a specific asset."""

    model_config = ConfigDict(frozen=True, extra="allow")

    asset_id: str
    bound_project_ids: List[str] = Field(default_factory=list)
    bound_revisions: List[str] = Field(default_factory=list)
    bound_entity_ids: List[str] = Field(default_factory=list)
    usage_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "bound_project_ids": self.bound_project_ids,
            "bound_revisions": self.bound_revisions,
            "bound_entity_ids": self.bound_entity_ids,
            "usage_count": self.usage_count,
        }


class ScriptAssetProjectionEngine:
    """Projector processing events to maintain convergent read-models."""

    def __init__(self) -> None:
        self._bindings_store: Dict[str, ProductionAssetBinding] = {}

    def apply_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Apply a single domain event idempotently."""
        if event_type in ("script_asset.binding_created", "ASSET_BINDING_CREATED"):
            binding = ProductionAssetBinding(
                binding_id=payload["binding_id"],
                project_id=payload["project_id"],
                production_revision_id=payload["production_revision_id"],
                screenplay_entity_type=ScreenplayEntityType(payload["screenplay_entity_type"]),
                screenplay_entity_id=payload["screenplay_entity_id"],
                role_key=payload.get("role_key", "primary"),
                asset_id=payload["asset_id"],
                asset_revision_id=payload["asset_revision_id"],
                status=BindingStatus.ACTIVE,
                created_by=payload.get("actor", "user"),
            )
            self._bindings_store[binding.binding_id] = binding

        elif event_type in ("script_asset.binding_removed", "ASSET_BINDING_REMOVED"):
            binding_id = payload.get("binding_id")
            if binding_id and binding_id in self._bindings_store:
                existing = self._bindings_store[binding_id]
                updated = ProductionAssetBinding(
                    **{
                        **existing.model_dump(),
                        "status": BindingStatus.UNBOUND,
                        "unbound_at": payload.get("timestamp"),
                    }
                )
                self._bindings_store[binding_id] = updated

    def build_inspector_summary(
        self, project_id: str, revision_id: str, total_requirements: int = 0
    ) -> ScriptInspectorBindingSummary:
        """Build inspector summary for target project revision."""
        rev_bindings = [
            b
            for b in self._bindings_store.values()
            if b.project_id == project_id
            and b.production_revision_id == revision_id
            and b.status == BindingStatus.ACTIVE
        ]

        bound_chars = sum(1 for b in rev_bindings if b.screenplay_entity_type == ScreenplayEntityType.CHARACTER)
        bound_locs = sum(1 for b in rev_bindings if b.screenplay_entity_type == ScreenplayEntityType.LOCATION)
        bound_props = sum(1 for b in rev_bindings if b.screenplay_entity_type == ScreenplayEntityType.PROP)

        fulfilled = len(rev_bindings)
        total_reqs = max(total_requirements, fulfilled)

        return ScriptInspectorBindingSummary(
            project_id=project_id,
            revision_id=revision_id,
            bound_character_count=bound_chars,
            missing_character_count=max(0, total_reqs - bound_chars),
            bound_location_count=bound_locs,
            missing_location_count=max(0, total_reqs - bound_locs),
            bound_prop_count=bound_props,
            missing_prop_count=max(0, total_reqs - bound_props),
            total_requirements=total_reqs,
            fulfilled_requirements=fulfilled,
            bindings=rev_bindings,
        )

    def build_asset_usage(self, asset_id: str) -> AssetUsageProjection:
        """Build asset usage projection across all active bindings."""
        asset_bindings = [
            b for b in self._bindings_store.values() if b.asset_id == asset_id and b.status == BindingStatus.ACTIVE
        ]

        project_ids = list({b.project_id for b in asset_bindings})
        revisions = list({b.production_revision_id for b in asset_bindings})
        entity_ids = list({b.screenplay_entity_id for b in asset_bindings})

        return AssetUsageProjection(
            asset_id=asset_id,
            bound_project_ids=project_ids,
            bound_revisions=revisions,
            bound_entity_ids=entity_ids,
            usage_count=len(asset_bindings),
        )


__all__ = [
    "ScriptInspectorBindingSummary",
    "AssetUsageProjection",
    "ScriptAssetProjectionEngine",
]
