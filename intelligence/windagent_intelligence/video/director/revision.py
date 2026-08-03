"""
Script revision proposal factory (plan §9.3).

The Director never mutates a screenplay. When it finds a problem it emits a
`DirectorialIssue`; this factory converts blocking issues into
`ScriptRevisionProposal`s carrying the target scene/line, reason, suggested
change, impact, and the source plan hash. A rejected proposal changes nothing
in the package; an approved proposal leads to a NEW screenplay revision and a
regenerated plan.
"""

from __future__ import annotations

from typing import Dict, List

from windagent_core.domain.video_production.director import (
    DirectorialIssue,
    ScriptRevisionProposal,
)
from windagent_core.domain.video_production.enums import (
    DirectorialIssueCategory,
)
from windagent_core.domain.video_production.ids import (
    DialogueLineId,
    ScriptRevisionProposalId,
)
from windagent_core.domain.video_production.package import VideoProductionPackage

from windagent_intelligence.video.ids import StableIdFactory

# Suggested-change templates keyed by issue category. Each proposal is
# deterministic and derived purely from the issue + package facts.
_SUGGESTIONS: Dict[DirectorialIssueCategory, str] = {
    DirectorialIssueCategory.DURATION_OVERFLOW: (
        "Trim or reallocate shot durations so the total timeline stays within "
        "the production constraint tolerance."
    ),
    DirectorialIssueCategory.DIALOGUE_DURATION_MISMATCH: (
        "Extend the shot duration or shorten/merge the dialogue line; the "
        "dialogue must fit its shot without being silently cut."
    ),
    DirectorialIssueCategory.UNKNOWN_REFERENCE: (
        "Fix the entity/reference ID so every referenced character, location, "
        "dialogue, or asset exists in the package."
    ),
    DirectorialIssueCategory.MISSING_COVERAGE: (
        "Add a shot to cover the scene or bind every dialogue line to a shot."
    ),
    DirectorialIssueCategory.CONSTRAINT_VIOLATION: (
        "Adjust the plan so it respects the production constraints."
    ),
}


class ScriptRevisionProposalFactory:
    """Builds proposals from issues; never mutates the package."""

    def __init__(self, *, id_factory: StableIdFactory) -> None:
        self.id_factory = id_factory

    def build(
        self,
        package: VideoProductionPackage,
        issues: List[DirectorialIssue],
        *,
        source_plan_hash: str,
    ) -> List[ScriptRevisionProposal]:
        """Create one proposal per blocking issue (non-blocking are recorded only)."""
        dialogue_by_id: Dict[str, DialogueLineId] = {}
        if package.screenplay:
            for scene in package.screenplay.scenes:
                for dlg_id in scene.dialogue_line_ids:
                    dialogue_by_id.setdefault(str(dlg_id), dlg_id)

        proposals: List[ScriptRevisionProposal] = []
        for seq, issue in enumerate(issues):
            if not issue.blocking:
                continue
            target_scene_id = issue.scene_id
            if target_scene_id is None and issue.shot_id is not None:
                # Best-effort: derive scene from shot metadata when present.
                target_scene_id = issue.details.get("scene_id")
            if target_scene_id is None:
                target_scene_id = next(
                    iter(package.screenplay.scene_ids), None
                ) if package.screenplay else None
            if target_scene_id is None:
                continue  # cannot target a proposal without a scene

            suggestion = _SUGGESTIONS.get(issue.category, _SUGGESTIONS[DirectorialIssueCategory.CONSTRAINT_VIOLATION])
            proposals.append(
                ScriptRevisionProposal(
                    proposal_id=ScriptRevisionProposalId(
                        self.id_factory.proposal_id(str(issue.issue_id), seq)
                    ),
                    source_issue_id=issue.issue_id,
                    target_scene_id=target_scene_id,
                    target_line=None,
                    reason=issue.message,
                    suggested_change=suggestion,
                    impact=(
                        "A new screenplay revision is required; the cinematic "
                        "plan must be regenerated after approval."
                    ),
                    source_plan_hash=source_plan_hash,
                )
            )
        return proposals


__all__ = ["ScriptRevisionProposalFactory"]
