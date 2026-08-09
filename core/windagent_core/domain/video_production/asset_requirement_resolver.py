"""
Stage E — Asset Requirement Domain and Resolver (UI36).

Provides missing asset requirement models, deterministic requirement generation
from screenplay entities, candidate eligibility ranking, and automated status transitions.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.production_asset import ProductionAsset
from windagent_core.domain.video_production.script_asset_binding import (
    ProductionAssetBinding,
    ScreenplayEntityType,
)


class RequirementSeverity(str, Enum):
    """Severity of a missing asset requirement."""
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


class RequirementStatus(str, Enum):
    """Resolution status of an asset requirement."""
    OPEN = "OPEN"
    RESOLVING = "RESOLVING"
    FULFILLED = "FULFILLED"
    STALE = "STALE"


class AssetRequirement(BaseModel):
    """Typed domain requirement representing a missing asset for a screenplay entity."""

    model_config = ConfigDict(frozen=True, extra="allow")

    requirement_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    screenplay_entity_id: str = Field(min_length=1)
    screenplay_entity_type: ScreenplayEntityType
    role_key: str = Field(default="primary")
    required_kind: str = Field(default="OTHER")
    required_media: str = Field(default="IMAGE")
    description: str = Field(default="")
    severity: RequirementSeverity = RequirementSeverity.BLOCKING
    status: RequirementStatus = RequirementStatus.OPEN
    candidate_asset_ids: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "screenplay_entity_id": self.screenplay_entity_id,
            "screenplay_entity_type": self.screenplay_entity_type.value,
            "role_key": self.role_key,
            "required_kind": self.required_kind,
            "required_media": self.required_media,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status.value,
            "candidate_asset_ids": self.candidate_asset_ids,
        }


def compute_requirement_id(
    project_id: str,
    revision_id: str,
    entity_type: ScreenplayEntityType,
    entity_id: str,
    role_key: str = "primary",
) -> str:
    """Compute a deterministic requirement ID."""
    seed = f"{project_id}:{revision_id}:{entity_type.value}:{entity_id}:{role_key}"
    return f"req_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


class AssetRequirementResolver:
    """Engine for generating and resolving missing asset requirements."""

    def generate_requirements(
        self,
        *,
        project_id: str,
        revision_id: str,
        screenplay_read_model: Dict[str, Any],
        active_bindings: List[ProductionAssetBinding],
    ) -> List[AssetRequirement]:
        """Generate deterministic missing asset requirements for a screenplay revision."""
        requirements: List[AssetRequirement] = []

        # Index active bindings by (entity_type, entity_id, role_key)
        bound_keys = {
            (b.screenplay_entity_type.value, b.screenplay_entity_id, b.role_key)
            for b in active_bindings
            if b.status.value == "ACTIVE"
        }

        # 1. Characters
        characters = screenplay_read_model.get("characters", [])
        for char in characters:
            char_id = char.get("character_id") or char.get("id")
            char_name = char.get("name") or char_id
            if not char_id:
                continue
            if ("CHARACTER", char_id, "primary") not in bound_keys:
                req_id = compute_requirement_id(project_id, revision_id, ScreenplayEntityType.CHARACTER, char_id)
                requirements.append(
                    AssetRequirement(
                        requirement_id=req_id,
                        project_id=project_id,
                        revision_id=revision_id,
                        screenplay_entity_id=char_id,
                        screenplay_entity_type=ScreenplayEntityType.CHARACTER,
                        role_key="primary",
                        required_kind="CHARACTER",
                        required_media="IMAGE",
                        description=f"Missing asset for character '{char_name}'",
                        severity=RequirementSeverity.BLOCKING,
                        status=RequirementStatus.OPEN,
                    )
                )

        # 2. Locations
        locations = screenplay_read_model.get("locations", [])
        for loc in locations:
            loc_id = loc.get("location_id") or loc.get("id")
            loc_name = loc.get("name") or loc_id
            if not loc_id:
                continue
            if ("LOCATION", loc_id, "primary") not in bound_keys:
                req_id = compute_requirement_id(project_id, revision_id, ScreenplayEntityType.LOCATION, loc_id)
                requirements.append(
                    AssetRequirement(
                        requirement_id=req_id,
                        project_id=project_id,
                        revision_id=revision_id,
                        screenplay_entity_id=loc_id,
                        screenplay_entity_type=ScreenplayEntityType.LOCATION,
                        role_key="primary",
                        required_kind="ENVIRONMENT",
                        required_media="IMAGE",
                        description=f"Missing asset for location '{loc_name}'",
                        severity=RequirementSeverity.BLOCKING,
                        status=RequirementStatus.OPEN,
                    )
                )

        # 3. Props
        props = screenplay_read_model.get("props", [])
        for prop in props:
            prop_id = prop.get("prop_id") or prop.get("id")
            prop_name = prop.get("name") or prop_id
            if not prop_id:
                continue
            if ("PROP", prop_id, "primary") not in bound_keys:
                req_id = compute_requirement_id(project_id, revision_id, ScreenplayEntityType.PROP, prop_id)
                requirements.append(
                    AssetRequirement(
                        requirement_id=req_id,
                        project_id=project_id,
                        revision_id=revision_id,
                        screenplay_entity_id=prop_id,
                        screenplay_entity_type=ScreenplayEntityType.PROP,
                        role_key="primary",
                        required_kind="PROP",
                        required_media="IMAGE",
                        description=f"Missing asset for prop '{prop_name}'",
                        severity=RequirementSeverity.WARNING,
                        status=RequirementStatus.OPEN,
                    )
                )

        return requirements

    def rank_candidates(
        self,
        requirement: AssetRequirement,
        available_assets: List[ProductionAsset],
    ) -> List[Dict[str, Any]]:
        """Rank candidate assets by compatibility score (0-100)."""
        ranked: List[Dict[str, Any]] = []

        for asset in available_assets:
            score = 0
            reasons: List[str] = []

            # Kind match
            asset_kind_val = asset.kind.value if hasattr(asset.kind, "value") else str(asset.kind)
            if asset_kind_val == requirement.required_kind:
                score += 50
                reasons.append("Exact kind match")
            elif asset_kind_val in ("IMAGE", "MODEL_3D", "CONCEPT_ART", "OTHER"):
                score += 25
                reasons.append("Compatible generic media type")

            # Lifecycle approval
            if asset.lifecycle_state.value == "APPROVED":
                score += 30
                reasons.append("Asset is approved")
            elif asset.lifecycle_state.value == "BOUND_TO_PROJECT":
                score += 20
                reasons.append("Asset bound to project")

            # Name similarity check
            if requirement.screenplay_entity_id.lower() in asset.name.lower():
                score += 20
                reasons.append("Name match")

            if score > 0:
                ranked.append(
                    {
                        "asset_id": asset.asset_id,
                        "asset_name": asset.name,
                        "score": min(score, 100),
                        "reasons": reasons,
                        "lifecycle_state": asset.lifecycle_state.value,
                    }
                )

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked


__all__ = [
    "RequirementSeverity",
    "RequirementStatus",
    "AssetRequirement",
    "compute_requirement_id",
    "AssetRequirementResolver",
]
