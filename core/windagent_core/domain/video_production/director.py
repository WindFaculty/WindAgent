"""
Director layer domain models (road_map.md Phase 8).

The Director converts a `VideoProductionPackage` into a provider-agnostic
`CinematicPlan`. It NEVER mutates a locked screenplay: any problem it finds is
surfaced as a `DirectorialIssue`, which a workflow turns into a
`ScriptRevisionProposal`. A rejected proposal changes nothing in the package.

The plan's scene objectives / beat order are recorded on the plan's metadata
as structured `SceneObjective` and `BeatPlan` records, and the deterministic
`plan_hash` ties the plan to its source revision + planner/prompt versions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.enums import (
    DirectorialIssueCategory,
    IssueSeverity,
    ProposalStatus,
)
from windagent_core.domain.video_production.ids import (
    DirectorialIssueId,
    ProductionRevisionId,
    SceneId,
    ScriptRevisionProposalId,
    ShotId,
    VideoProjectId,
)


class SceneObjective(BaseModel):
    """Narrative goal for one scene (plan §9.1)."""

    model_config = ConfigDict(frozen=True, extra="allow")

    scene_id: SceneId
    objective: str = ""
    beats: List[Dict[str, Any]] = Field(default_factory=list)
    required_story_facts: List[str] = Field(default_factory=list)


class DirectorialIssue(BaseModel):
    """A problem found by the Director that must go through a proposal.

    `blocking=True` means the plan cannot proceed to rendering until the
    issue is resolved via an approved `ScriptRevisionProposal`.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    issue_id: DirectorialIssueId
    category: DirectorialIssueCategory
    severity: IssueSeverity = IssueSeverity.WARNING
    message: str = Field(min_length=1)
    blocking: bool = False
    scene_id: Optional[SceneId] = None
    shot_id: Optional[ShotId] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": str(self.issue_id),
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "blocking": self.blocking,
            "scene_id": str(self.scene_id) if self.scene_id else None,
            "shot_id": str(self.shot_id) if self.shot_id else None,
            "details": self.details,
        }


class ScriptRevisionProposal(BaseModel):
    """Proposed screenplay change produced from a DirectorialIssue.

    Contains target scene/line, reason, suggested change, impact, and the
    source plan hash. The proposal does NOT mutate the package; it must be
    approved (human/workflow) before a new screenplay revision is derived.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    proposal_id: ScriptRevisionProposalId
    source_issue_id: DirectorialIssueId
    target_scene_id: SceneId
    target_line: Optional[str] = None
    reason: str = Field(min_length=1)
    suggested_change: str = Field(min_length=1)
    impact: str = ""
    source_plan_hash: str = Field(min_length=1)
    status: ProposalStatus = ProposalStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": str(self.proposal_id),
            "source_issue_id": str(self.source_issue_id),
            "target_scene_id": str(self.target_scene_id),
            "target_line": self.target_line,
            "reason": self.reason,
            "suggested_change": self.suggested_change,
            "impact": self.impact,
            "source_plan_hash": self.source_plan_hash,
            "status": self.status.value,
        }


def compute_plan_hash(
    *,
    project_id: VideoProjectId,
    revision_id: ProductionRevisionId,
    plan_payload: Dict[str, Any],
    planner_version: str,
    prompt_version: str,
    prompt_hash: str,
    source_package_hash: str,
    duration_policy_version: str,
) -> str:
    """Deterministic SHA-256 over the canonical plan payload + versions.

    Same inputs must always yield the same hash; changing any version,
    reference, or plan field produces a new hash (plan §24.5 semantics reused
    for the Phase 8 plan-level hash).
    """
    canonical = json.dumps(
        {
            "project_id": str(project_id),
            "revision_id": str(revision_id),
            "planner_version": planner_version,
            "prompt_version": prompt_version,
            "prompt_hash": prompt_hash,
            "source_package_hash": source_package_hash,
            "duration_policy_version": duration_policy_version,
            "plan": plan_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "SceneObjective",
    "DirectorialIssue",
    "ScriptRevisionProposal",
    "compute_plan_hash",
]
