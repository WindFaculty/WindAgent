"""
Stage E — Asset Eligibility Service.

Evaluates whether a Production Asset (and specific Asset Revision) is eligible
to be bound to a Screenplay Entity (Character, Location, Prop) under project context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_core.domain.video_production.enums import LicenseState
from windagent_core.domain.video_production.production_asset import AssetRevision, ProductionAsset
from windagent_core.domain.video_production.script_asset_binding import ScreenplayEntityType


class AssetEligibilityResult(BaseModel):
    """Evaluation result for asset binding eligibility."""

    model_config = ConfigDict(frozen=True, extra="allow")

    is_eligible: bool
    asset_id: str
    asset_revision_id: str
    entity_type: ScreenplayEntityType
    entity_id: str
    blocking_reasons: List[str] = Field(default_factory=list)
    warning_reasons: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_eligible": self.is_eligible,
            "asset_id": self.asset_id,
            "asset_revision_id": self.asset_revision_id,
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "blocking_reasons": self.blocking_reasons,
            "warning_reasons": self.warning_reasons,
        }


# Kind compatibility mappings per entity type
ENTITY_KIND_COMPATIBILITY: Dict[ScreenplayEntityType, List[str]] = {
    ScreenplayEntityType.CHARACTER: [
        "CHARACTER",
        "MODEL_3D",
        "RIG",
        "FACIAL_PROFILE",
        "VOICE_PROFILE",
        "REFERENCE_IMAGE",
        "OTHER",
    ],
    ScreenplayEntityType.LOCATION: [
        "ENVIRONMENT",
        "MODEL_3D",
        "REFERENCE_IMAGE",
        "OTHER",
    ],
    ScreenplayEntityType.PROP: [
        "PROP",
        "MODEL_3D",
        "TEXTURE",
        "MATERIAL",
        "REFERENCE_IMAGE",
        "OTHER",
    ],
    ScreenplayEntityType.SCENE: [
        "ENVIRONMENT",
        "REFERENCE_IMAGE",
        "STORYBOARD",
        "MUSIC",
        "SFX",
        "OTHER",
    ],
    ScreenplayEntityType.SHOT: [
        "CHARACTER",
        "PROP",
        "MODEL_3D",
        "ANIMATION",
        "REFERENCE_IMAGE",
        "OTHER",
    ],
}

ALLOWED_LIFECYCLE_STATES = {
    AssetLifecycleState.APPROVED,
    AssetLifecycleState.BOUND_TO_PROJECT,
}

INELIGIBLE_LICENSE_STATES = {
    LicenseState.UNKNOWN,
    LicenseState.REJECTED,
}


class AssetEligibilityService:
    """Evaluates binding rules between screenplay entities and production assets."""

    def evaluate_eligibility(
        self,
        *,
        asset: ProductionAsset,
        revision: Optional[AssetRevision] = None,
        entity_type: ScreenplayEntityType,
        entity_id: str,
        project_id: str,
        target_revision_id: str,
        strict_license: bool = True,
    ) -> AssetEligibilityResult:
        blocking: List[str] = []
        warnings: List[str] = []

        rev_id = revision.revision_id if revision else (asset.active_revision_id or "rev_unknown")

        # 1. Lifecycle State Check
        if asset.lifecycle_state not in ALLOWED_LIFECYCLE_STATES:
            blocking.append(
                f"Asset '{asset.asset_id}' lifecycle state is '{asset.lifecycle_state.value}'. "
                "Only APPROVED or BOUND_TO_PROJECT assets are eligible."
            )

        # 2. Archived Check
        if asset.metadata.get("archived", False):
            blocking.append(f"Asset '{asset.asset_id}' is archived and cannot be bound.")

        # 3. Kind & Media Compatibility Check
        allowed_kinds = ENTITY_KIND_COMPATIBILITY.get(entity_type, [])
        asset_kind_val = asset.kind.value if hasattr(asset.kind, "value") else str(asset.kind)
        if allowed_kinds and asset_kind_val not in allowed_kinds:
            warnings.append(
                f"Asset kind '{asset_kind_val}' may not fully match requirements for entity type '{entity_type.value}'."
            )

        # 4. License Check
        license_val = asset.license_state
        if strict_license and license_val in INELIGIBLE_LICENSE_STATES:
            blocking.append(
                f"Asset '{asset.asset_id}' license state is '{license_val.value}'. "
                "Valid commercial license required for binding."
            )

        # 5. Active Revision Existence
        if not asset.active_revision_id and not revision:
            blocking.append(f"Asset '{asset.asset_id}' has no active revision.")

        is_eligible = len(blocking) == 0

        return AssetEligibilityResult(
            is_eligible=is_eligible,
            asset_id=asset.asset_id,
            asset_revision_id=rev_id,
            entity_type=entity_type,
            entity_id=entity_id,
            blocking_reasons=blocking,
            warning_reasons=warnings,
        )


__all__ = [
    "AssetEligibilityResult",
    "AssetEligibilityService",
    "ENTITY_KIND_COMPATIBILITY",
]
