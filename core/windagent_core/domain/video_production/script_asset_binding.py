"""
Stage E — Production Asset Binding Domain Model.

Represents immutable binding entities between Screenplay Entities (Character, Location, Prop)
and Production Assets, pinned to specific production revisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class ScreenplayEntityType(str, Enum):
    """Types of screenplay entities that can bind to assets."""
    CHARACTER = "CHARACTER"
    LOCATION = "LOCATION"
    PROP = "PROP"
    SCENE = "SCENE"
    SHOT = "SHOT"


class BindingStatus(str, Enum):
    """Lifecycle status of a ProductionAssetBinding."""
    ACTIVE = "ACTIVE"
    UNBOUND = "UNBOUND"
    SUPERSEDED = "SUPERSEDED"
    INVALID = "INVALID"


class ProductionAssetBinding(BaseModel):
    """Entity binding connecting a Screenplay Entity to a Production Asset revision."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    production_revision_id: str = Field(min_length=1)
    screenplay_entity_type: ScreenplayEntityType
    screenplay_entity_id: str = Field(min_length=1)
    role_key: str = Field(default="primary", min_length=1)
    asset_id: str = Field(min_length=1)
    asset_revision_id: str = Field(min_length=1)
    status: BindingStatus = BindingStatus.ACTIVE
    created_by: str = Field(default="user")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supersedes_binding_id: Optional[str] = None
    unbound_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "project_id": self.project_id,
            "production_revision_id": self.production_revision_id,
            "screenplay_entity_type": self.screenplay_entity_type.value,
            "screenplay_entity_id": self.screenplay_entity_id,
            "role_key": self.role_key,
            "asset_id": self.asset_id,
            "asset_revision_id": self.asset_revision_id,
            "status": self.status.value,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "supersedes_binding_id": self.supersedes_binding_id,
            "unbound_at": self.unbound_at,
        }


__all__ = [
    "ScreenplayEntityType",
    "BindingStatus",
    "ProductionAssetBinding",
]
