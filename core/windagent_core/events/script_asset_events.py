"""
Stage E — Script ↔ Asset Integration Events (UI34–UI36).

Defines event types and schemas for asset bindings, asset requirements,
eligibility changes, and screenplay validation updates.
"""

from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, ConfigDict


class ScriptAssetEventCatalog:
    """Canonical event catalog for Script ↔ Asset Integration."""

    ASSET_REQUIREMENT_CREATED = "script_asset.requirement_created"
    ASSET_REQUIREMENT_UPDATED = "script_asset.requirement_updated"
    ASSET_BINDING_CREATED = "script_asset.binding_created"
    ASSET_BINDING_REMOVED = "script_asset.binding_removed"
    ASSET_BINDING_INVALIDATED = "script_asset.binding_invalidated"
    ASSET_ELIGIBILITY_CHANGED = "script_asset.eligibility_changed"
    SCREENPLAY_VALIDATION_UPDATED = "script_asset.screenplay_validation_updated"


class AssetBindingCreatedPayload(BaseModel):
    """Payload for ASSET_BINDING_CREATED event."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: str
    project_id: str
    production_revision_id: str
    screenplay_entity_type: str
    screenplay_entity_id: str
    role_key: str
    asset_id: str
    asset_revision_id: str
    actor: str = "user"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "project_id": self.project_id,
            "production_revision_id": self.production_revision_id,
            "screenplay_entity_type": self.screenplay_entity_type,
            "screenplay_entity_id": self.screenplay_entity_id,
            "role_key": self.role_key,
            "asset_id": self.asset_id,
            "asset_revision_id": self.asset_revision_id,
            "actor": self.actor,
        }


class AssetBindingRemovedPayload(BaseModel):
    """Payload for ASSET_BINDING_REMOVED event."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: str
    project_id: str
    production_revision_id: str
    screenplay_entity_id: str
    asset_id: str
    reason: str = "user_unbound"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "project_id": self.project_id,
            "production_revision_id": self.production_revision_id,
            "screenplay_entity_id": self.screenplay_entity_id,
            "asset_id": self.asset_id,
            "reason": self.reason,
        }


class AssetRequirementUpdatedPayload(BaseModel):
    """Payload for ASSET_REQUIREMENT_UPDATED event."""

    model_config = ConfigDict(frozen=True, extra="allow")

    requirement_id: str
    project_id: str
    revision_id: str
    screenplay_entity_id: str
    status: str
    candidate_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "screenplay_entity_id": self.screenplay_entity_id,
            "status": self.status,
            "candidate_count": self.candidate_count,
        }


__all__ = [
    "ScriptAssetEventCatalog",
    "AssetBindingCreatedPayload",
    "AssetBindingRemovedPayload",
    "AssetRequirementUpdatedPayload",
]
