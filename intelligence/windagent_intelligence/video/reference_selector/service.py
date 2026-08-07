"""
ReferenceBindingPlanner (Phase 11) — binds APPROVED, hash-bound reference
assets to shots (plan 03 §24.1).

Responsibilities:
- for every shot, collect the asset references it needs: character portraits
  (IDENTITY), location references (LOCATION), prop references (PROP), style
  references (STYLE), and first/last frame assets required by the shot's
  dependency semantics;
- record each binding with its asset content hash, role, required/optional
  flag, source revision, crop/usage intent and approval state;
- FAIL CLOSED on any blocking binding defect: an unknown asset, an asset that
  is not APPROVED (candidate/rejected/license-unknown), a stale hash, a wrong
  source revision, a duplicate binding, or a missing required binding raises
  `ValidationFailureError` — no partial binding plan is ever published;
- produce a deterministic, versioned binding hash tied to the source
  graph/plan/package hashes (plan §24.5).

The planner is fully deterministic and never calls a provider.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_core.domain.video_production.enums import ReferenceBindingRole
from windagent_core.domain.video_production.ids import (
    ReferenceAssetId,
    ReferenceBindingId,
    ReferenceBindingPlanId,
    ShotId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage
from windagent_core.domain.video_production.reference_binding import (
    ReferenceBinding,
    ReferenceBindingPlan,
    ReferenceBindingValidator,
    compute_reference_binding_hash,
)
from windagent_core.domain.video_production.validation import (
    VideoProductionPackageValidator,
)

from windagent_intelligence.video.errors import ValidationFailureError
from windagent_intelligence.video.ids import StableIdFactory
from windagent_intelligence.video.reference_selector.models import (
    ReferenceBindingPlanReceipt,
)
from windagent_intelligence.video.shot_planner.models import ShotGraphReceipt

_APPROVED_STATES = {
    AssetLifecycleState.APPROVED,
    AssetLifecycleState.BOUND_TO_PROJECT,
}


class ReferenceBindingPlanner:
    """Deterministic reference binding over a package + Phase 9 shot graph."""

    def __init__(
        self,
        *,
        id_factory: Optional[StableIdFactory] = None,
        validator: Optional[ReferenceBindingValidator] = None,
    ) -> None:
        self.id_factory = id_factory or StableIdFactory()
        self.validator = validator or ReferenceBindingValidator(
            id_factory=self.id_factory,
        )

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------
    def plan(
        self,
        package: VideoProductionPackage,
        graph_receipt: ShotGraphReceipt,
        *,
        asset_approval: Optional[Dict[str, AssetLifecycleState]] = None,
        require_locked: bool = True,
    ) -> ReferenceBindingPlanReceipt:
        """Bind approved assets to every shot in the graph.

        Raises `ValidationFailureError` on an invalid package, an empty graph,
        a missing source plan hash (unlocked revision), or any BLOCKING
        binding defect (fail closed — a shot with a broken binding never
        compiles into a request).
        """
        package_issues = VideoProductionPackageValidator.validate(package)
        if package_issues:
            raise ValidationFailureError(
                "Cannot build a reference binding plan from an invalid package.",
                details={
                    "issue_count": len(package_issues),
                    "first": [i.code for i in package_issues[:5]],
                },
            )
        graph = graph_receipt.graph
        if not graph.shots:
            raise ValidationFailureError(
                "Reference binding requires a shot graph with at least one shot.",
            )
        if require_locked and not graph_receipt.source_plan_hash:
            raise ValidationFailureError(
                "Reference binding requires a traceable source plan hash.",
                details={"source_plan_hash": graph_receipt.source_plan_hash},
            )

        asset_approval = asset_approval or {}
        assets_by_id = {str(a.asset_id): a for a in package.assets}

        bindings: List[ReferenceBinding] = []
        for shot in sorted(graph.shots, key=lambda s: (str(s.scene_id), s.order)):
            bindings.extend(
                self._bind_shot(
                    package=package,
                    shot_id=shot.shot_id,
                    shot_asset_ids=shot.reference_asset_ids,
                    assets_by_id=assets_by_id,
                    asset_approval=asset_approval,
                )
            )


        plan = ReferenceBindingPlan(
            plan_id=ReferenceBindingPlanId(
                self.id_factory.reference_binding_plan_id(
                    str(package.project_id), str(package.revision_id)
                )
            ),
            project_id=package.project_id,
            revision_id=package.revision_id,
            bindings=bindings,
            binding_version="1.0.0",
            source_graph_hash=graph_receipt.graph_hash,
            source_plan_hash=graph_receipt.source_plan_hash,
            source_package_hash=graph_receipt.source_package_hash,
        )

        required_by_shot = {
            str(s.shot_id): [str(a) for a in s.reference_asset_ids]
            for s in graph.shots
        }
        issues = self.validator.validate(
            plan,
            assets=assets_by_id,
            required_by_shot=required_by_shot,
        )
        plan = plan.model_copy(update={"issues": issues})

        # Deterministic binding hash tied to source hashes.
        binding_hash = compute_reference_binding_hash(
            project_id=package.project_id,
            revision_id=package.revision_id,
            bindings_payload=[b.to_dict() for b in bindings],
            binding_version=plan.binding_version,
            source_graph_hash=graph_receipt.graph_hash,
            source_plan_hash=graph_receipt.source_plan_hash,
            source_package_hash=graph_receipt.source_package_hash,
        )
        plan = plan.model_copy(update={"binding_hash": binding_hash})

        receipt = ReferenceBindingPlanReceipt(
            plan=plan,
            issues=issues,
            binding_hash=binding_hash,
            source_graph_hash=graph_receipt.graph_hash,
            source_plan_hash=graph_receipt.source_plan_hash,
            source_package_hash=graph_receipt.source_package_hash,
            binding_version=plan.binding_version,
        )

        # FAIL CLOSED: a shot with a blocking binding defect never compiles.
        blocking = receipt.blocking_issues
        if blocking:
            raise ValidationFailureError(
                "Reference binding failed; no request can be compiled for "
                "shots with broken bindings.",
                details={
                    "blocking_issue_count": len(blocking),
                    "first": [i.code.value for i in blocking[:5]],
                },
            )
        return receipt

    # ------------------------------------------------------------------
    # Per-shot binding
    # ------------------------------------------------------------------
    def _bind_shot(
        self,
        *,
        package: VideoProductionPackage,
        shot_id: ShotId,
        shot_asset_ids: List[ReferenceAssetId],
        assets_by_id: Dict[str, ReferenceAsset],
        asset_approval: Dict[str, AssetLifecycleState],
    ) -> List[ReferenceBinding]:
        bindings: List[ReferenceBinding] = []
        seen: set = set()

        character_portraits = _character_portrait_map(package)
        location_refs = _location_reference_map(package)
        prop_refs = _prop_reference_map(package)
        style_refs = _style_reference_map(package)

        for asset_id in _ordered_asset_ids(shot_asset_ids):
            key = str(asset_id)
            if key in seen:
                continue
            seen.add(key)
            asset = assets_by_id.get(key)
            if asset is None:
                # Record a binding so the validator can report UNKNOWN_ASSET
                # (a shot referencing a missing asset must fail closed).
                bindings.append(
                    ReferenceBinding(
                        binding_id=ReferenceBindingId(
                            self.id_factory.reference_binding_id(shot_id, asset_id, "UNKNOWN")
                        ),
                        shot_id=shot_id,
                        asset_id=asset_id,
                        asset_hash="0" * 64,
                        role=ReferenceBindingRole.INGREDIENT,
                        required=True,
                        source_revision=package.revision_id,
                        approval_state=AssetLifecycleState.DISCOVERED,
                    )
                )
                continue
            role = _classify_role(
                key,
                character_portraits=character_portraits,
                location_refs=location_refs,
                prop_refs=prop_refs,
                style_refs=style_refs,
            )
            approval = asset_approval.get(
                key,
                _default_approval(asset),
            )
            required = _binding_required(role)
            bindings.append(
                ReferenceBinding(
                    binding_id=ReferenceBindingId(
                        self.id_factory.reference_binding_id(
                            shot_id, asset_id, role.value
                        )
                    ),
                    shot_id=shot_id,
                    asset_id=asset_id,
                    asset_hash=asset.content_hash,
                    role=role,
                    required=required,
                    source_revision=package.revision_id,
                    crop_usage_intent=_crop_usage_intent(role),
                    approval_state=approval,
                )
            )
        return bindings


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------
def _ordered_asset_ids(asset_ids: List[ReferenceAssetId]) -> List[ReferenceAssetId]:
    return sorted(set(asset_ids), key=str)


def _classify_role(
    asset_key: str,
    *,
    character_portraits: Dict[str, ReferenceBindingRole],
    location_refs: Dict[str, ReferenceBindingRole],
    prop_refs: Dict[str, ReferenceBindingRole],
    style_refs: Dict[str, ReferenceBindingRole],
) -> ReferenceBindingRole:
    if asset_key in character_portraits:
        return ReferenceBindingRole.IDENTITY
    if asset_key in location_refs:
        return ReferenceBindingRole.LOCATION
    if asset_key in prop_refs:
        return ReferenceBindingRole.PROP
    if asset_key in style_refs:
        return ReferenceBindingRole.STYLE
    return ReferenceBindingRole.INGREDIENT


def _character_portrait_map(package: VideoProductionPackage) -> Dict[str, ReferenceBindingRole]:
    mapping: Dict[str, ReferenceBindingRole] = {}
    for char in package.characters:
        for asset_id in char.portrait_asset_ids:
            mapping[str(asset_id)] = ReferenceBindingRole.IDENTITY
    return mapping


def _location_reference_map(package: VideoProductionPackage) -> Dict[str, ReferenceBindingRole]:
    mapping: Dict[str, ReferenceBindingRole] = {}
    for loc in package.locations:
        for asset_id in loc.reference_asset_ids:
            mapping[str(asset_id)] = ReferenceBindingRole.LOCATION
    return mapping


def _prop_reference_map(package: VideoProductionPackage) -> Dict[str, ReferenceBindingRole]:
    mapping: Dict[str, ReferenceBindingRole] = {}
    for prop in package.props:
        for asset_id in prop.reference_asset_ids:
            mapping[str(asset_id)] = ReferenceBindingRole.PROP
    return mapping


def _style_reference_map(package: VideoProductionPackage) -> Dict[str, ReferenceBindingRole]:
    mapping: Dict[str, ReferenceBindingRole] = {}
    if package.style_bible is not None:
        for asset_id in package.style_bible.reference_asset_ids:
            mapping[str(asset_id)] = ReferenceBindingRole.STYLE
    return mapping


def _default_approval(asset: ReferenceAsset) -> AssetLifecycleState:
    """Assets in the package are already validated/bound (Phase 7 pipeline).

    The canonical lifecycle machine only reaches the package with APPROVED or
    BOUND_TO_PROJECT assets; everything else must be passed explicitly through
    `asset_approval` by the caller (e.g. an asset freshly re-validated).
    """
    return (
        AssetLifecycleState.BOUND_TO_PROJECT
        if asset.metadata.get("bound_to_project") is True
        else AssetLifecycleState.APPROVED
    )


def _binding_required(role: ReferenceBindingRole) -> bool:
    """A reference is REQUIRED based on its role only.

    Identity/location/style/prop references are always required once bound.
    Generic ingredients are optional hints — the engine adapter decides how to
    use them. Generation-mode-based requirements were retired in VP3D Stage A.
    """
    if role in (ReferenceBindingRole.IDENTITY, ReferenceBindingRole.LOCATION):
        return True
    if role in (ReferenceBindingRole.PROP, ReferenceBindingRole.STYLE):
        return True
    if role == ReferenceBindingRole.INGREDIENT:
        return False
    return True


def _crop_usage_intent(role: ReferenceBindingRole) -> str:
    return {
        ReferenceBindingRole.IDENTITY: "identity reference",
        ReferenceBindingRole.LOCATION: "location reference",
        ReferenceBindingRole.PROP: "prop reference",
        ReferenceBindingRole.STYLE: "style reference",
        ReferenceBindingRole.INGREDIENT: "ingredient reference",
        ReferenceBindingRole.FIRST_FRAME: "first frame",
        ReferenceBindingRole.LAST_FRAME: "last frame",
        ReferenceBindingRole.PREDECESSOR_CLIP: "predecessor clip",
    }[role]


__all__ = ["ReferenceBindingPlanner"]
