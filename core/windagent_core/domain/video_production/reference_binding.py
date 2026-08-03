"""
Phase 11 — Reference binding domain (plan 03 §24.1, §24.5).

A `ReferenceBinding` binds ONE approved, content-addressed asset to ONE shot
for a specific role (identity, location, prop, style, first/last frame,
ingredient, predecessor clip). Only assets that are APPROVED and belong to
the correct revision may be bound — a candidate, rejected, stale (hash
mismatch) or wrong-revision asset is BLOCKING and never compiles into a
GenerationRequest (fail closed).

The binding plan is immutable and deterministic: the same shot graph +
package always produces the same plan and the same `binding_hash`, which is
tied to the source graph/plan/package hashes so a reference change produces a
new hash (plan §24.5 invalidation semantics reused at the binding level).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_core.domain.video_production.enums import (
    IssueSeverity,
    ReferenceBindingIssueCode,
    ReferenceBindingRole,
)
from windagent_core.domain.video_production.ids import (
    ProductionRevisionId,
    ReferenceAssetId,
    ReferenceBindingId,
    ReferenceBindingIssueId,
    ReferenceBindingPlanId,
    ShotId,
    VideoProjectId,
)


class ReferenceBinding(BaseModel):
    """One approved asset bound to one shot for one role (plan §24.1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    binding_id: ReferenceBindingId
    shot_id: ShotId
    asset_id: ReferenceAssetId
    asset_hash: str = Field(min_length=64, max_length=64)
    role: ReferenceBindingRole = ReferenceBindingRole.IDENTITY
    required: bool = True
    source_revision: ProductionRevisionId
    crop_usage_intent: str = ""
    approval_state: AssetLifecycleState = AssetLifecycleState.APPROVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": str(self.binding_id),
            "shot_id": str(self.shot_id),
            "asset_id": str(self.asset_id),
            "asset_hash": self.asset_hash,
            "role": self.role.value,
            "required": self.required,
            "source_revision": str(self.source_revision),
            "crop_usage_intent": self.crop_usage_intent,
            "approval_state": self.approval_state.value,
        }


class ReferenceBindingIssue(BaseModel):
    """Typed finding from reference binding validation (Phase 11)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: ReferenceBindingIssueId
    code: ReferenceBindingIssueCode
    severity: IssueSeverity = IssueSeverity.BLOCKING
    message: str = Field(min_length=1)
    blocking: bool = True
    shot_id: Optional[ShotId] = None
    asset_id: Optional[ReferenceAssetId] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": str(self.issue_id),
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "blocking": self.blocking,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "asset_id": str(self.asset_id) if self.asset_id else None,
            "details": self.details,
        }


class ReferenceBindingPlan(BaseModel):
    """Immutable binding plan for a revision: all shot->asset bindings."""

    model_config = ConfigDict(frozen=True, extra="allow")

    plan_id: ReferenceBindingPlanId
    project_id: VideoProjectId
    revision_id: ProductionRevisionId
    bindings: List[ReferenceBinding] = Field(default_factory=list)
    issues: List[ReferenceBindingIssue] = Field(default_factory=list)
    binding_hash: str = ""
    source_graph_hash: str = ""
    source_plan_hash: str = ""
    source_package_hash: str = ""
    binding_version: str = "1.0.0"

    def bindings_for_shot(self, shot_id: ShotId) -> List[ReferenceBinding]:
        return [b for b in self.bindings if b.shot_id == shot_id]

    @property
    def blocking_issues(self) -> List[ReferenceBindingIssue]:
        return [i for i in self.issues if i.blocking]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": str(self.plan_id),
            "project_id": str(self.project_id),
            "revision_id": str(self.revision_id),
            "bindings": [b.to_dict() for b in self.bindings],
            "issues": [i.to_dict() for i in self.issues],
            "binding_hash": self.binding_hash,
            "source_graph_hash": self.source_graph_hash,
            "source_plan_hash": self.source_plan_hash,
            "source_package_hash": self.source_package_hash,
            "binding_version": self.binding_version,
        }


def compute_reference_binding_hash(
    *,
    project_id: object,
    revision_id: object,
    bindings_payload: List[Dict[str, Any]],
    binding_version: str,
    source_graph_hash: str,
    source_plan_hash: str,
    source_package_hash: str,
) -> str:
    """Deterministic SHA-256 over the canonical binding payload + sources.

    Same inputs always produce the same hash; changing any bound asset,
    role, source hash, or version produces a new hash (plan §24.5).
    """
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "binding_version": binding_version,
            "source_graph_hash": source_graph_hash,
            "source_plan_hash": source_plan_hash,
            "source_package_hash": source_package_hash,
            "bindings": bindings_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_BLOCKING_CODES = {
    ReferenceBindingIssueCode.UNKNOWN_ASSET,
    ReferenceBindingIssueCode.NOT_APPROVED,
    ReferenceBindingIssueCode.STALE_HASH,
    ReferenceBindingIssueCode.WRONG_REVISION,
    ReferenceBindingIssueCode.DUPLICATE_BINDING,
    ReferenceBindingIssueCode.MISSING_REQUIRED_BINDING,
}


class ReferenceBindingValidator:
    """Deterministic reference binding rules (plan §24.1).

    - every bound asset must exist in the package (UNKNOWN_ASSET);
    - the asset must be APPROVED (or BOUND_TO_PROJECT) — candidate / rejected /
      license-unknown assets never bind (NOT_APPROVED);
    - the recorded asset hash must match the package asset's content hash
      (STALE_HASH — a changed reference invalidates the binding);
    - the binding's source revision must equal the plan revision
      (WRONG_REVISION);
    - no duplicate (shot, asset) binding (DUPLICATE_BINDING);
    - every REQUIRED binding for a shot must be present (MISSING_REQUIRED_BINDING).

    Blocking issues are returned; the caller fails closed (no partial binding
    plan is ever published).
    """

    def __init__(self, *, id_factory=None) -> None:
        self._id_factory = id_factory

    def validate(
        self,
        plan: ReferenceBindingPlan,
        *,
        assets: Dict[str, ReferenceAsset],
        required_by_shot: Optional[Dict[str, List[str]]] = None,
    ) -> List[ReferenceBindingIssue]:
        """Validate a binding plan.

        `required_by_shot` maps a shot id to the list of asset ids that shot
        MUST bind (from its `reference_asset_ids`). Every required asset must
        have a binding; a missing one raises `MISSING_REQUIRED_BINDING`.
        """
        issues: List[ReferenceBindingIssue] = []
        seen: set = set()
        bound_by_shot: Dict[str, set] = {}

        for binding in plan.bindings:
            key = (str(binding.shot_id), str(binding.asset_id))
            if key in seen:
                issues.append(
                    self._issue(
                        ReferenceBindingIssueCode.DUPLICATE_BINDING,
                        f"Duplicate binding for shot {binding.shot_id} / asset {binding.asset_id}.",
                        shot_id=binding.shot_id,
                        asset_id=binding.asset_id,
                    )
                )
            seen.add(key)
            bound_by_shot.setdefault(str(binding.shot_id), set()).add(
                str(binding.asset_id)
            )

            asset = assets.get(str(binding.asset_id))
            if asset is None:
                issues.append(
                    self._issue(
                        ReferenceBindingIssueCode.UNKNOWN_ASSET,
                        f"Bound asset {binding.asset_id} does not exist in the package.",
                        shot_id=binding.shot_id,
                        asset_id=binding.asset_id,
                    )
                )
                continue
            if binding.approval_state not in (
                AssetLifecycleState.APPROVED,
                AssetLifecycleState.BOUND_TO_PROJECT,
            ):
                issues.append(
                    self._issue(
                        ReferenceBindingIssueCode.NOT_APPROVED,
                        f"Asset {binding.asset_id} is {binding.approval_state.value}; "
                        "only APPROVED assets may be bound.",
                        shot_id=binding.shot_id,
                        asset_id=binding.asset_id,
                        details={"approval_state": binding.approval_state.value},
                    )
                )
            if binding.asset_hash != asset.content_hash:
                issues.append(
                    self._issue(
                        ReferenceBindingIssueCode.STALE_HASH,
                        f"Asset {binding.asset_id} hash changed; the binding is stale.",
                        shot_id=binding.shot_id,
                        asset_id=binding.asset_id,
                        details={
                            "recorded": binding.asset_hash,
                            "current": asset.content_hash,
                        },
                    )
                )
            if str(binding.source_revision) != str(plan.revision_id):
                issues.append(
                    self._issue(
                        ReferenceBindingIssueCode.WRONG_REVISION,
                        f"Binding {binding.binding_id} targets revision "
                        f"{binding.source_revision} but the plan is revision {plan.revision_id}.",
                        shot_id=binding.shot_id,
                        asset_id=binding.asset_id,
                        details={
                            "source_revision": str(binding.source_revision),
                            "plan_revision": str(plan.revision_id),
                        },
                    )
                )

        # Every required asset of a shot must have a binding (plan §24.1).
        if required_by_shot:
            for shot_key, asset_ids in required_by_shot.items():
                for asset_id in asset_ids:
                    if asset_id not in bound_by_shot.get(shot_key, set()):
                        issues.append(
                            self._issue(
                                ReferenceBindingIssueCode.MISSING_REQUIRED_BINDING,
                                f"Shot {shot_key} requires asset {asset_id} "
                                "but no binding exists.",
                                shot_id=ShotId(shot_key),
                                asset_id=ReferenceAssetId(asset_id),
                            )
                        )

        return issues

    def _issue(
        self,
        code: ReferenceBindingIssueCode,
        message: str,
        *,
        shot_id: Optional[ShotId] = None,
        asset_id: Optional[ReferenceAssetId] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ReferenceBindingIssue:
        seed = f"{code.value}:{shot_id or ''}:{asset_id or ''}"
        if self._id_factory is not None:
            issue_id = self._id_factory.reference_binding_issue_id(seed)
        else:
            issue_id = (
                "rbi_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
            )
        return ReferenceBindingIssue(
            issue_id=ReferenceBindingIssueId(issue_id),
            code=code,
            severity=IssueSeverity.BLOCKING
            if code in _BLOCKING_CODES
            else IssueSeverity.WARNING,
            message=message,
            blocking=code in _BLOCKING_CODES,
            shot_id=shot_id,
            asset_id=asset_id,
            details=details or {},
        )

    @classmethod
    def blocking_issue_codes(cls) -> set:
        return set(_BLOCKING_CODES)


__all__ = [
    "ReferenceBinding",
    "ReferenceBindingIssue",
    "ReferenceBindingPlan",
    "ReferenceBindingValidator",
    "compute_reference_binding_hash",
]
