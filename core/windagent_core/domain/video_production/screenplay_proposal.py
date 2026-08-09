"""
AI Screenplay Proposal Service (Stage C — UI17).

Provides human-in-the-loop AI script refactoring proposals.
Guarantees AI cannot directly mutate canonical screenplay state without explicit human APPROVE action.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.screenplay_diff import ScreenplayDiffEngine, ScreenplayDiffResult
from windagent_core.domain.video_production.screenplay_impact import ProductionImpactAnalyzer, ScreenplayChangeImpactDTO


class ScriptRevisionProposalDTO(BaseModel):
    proposal_id: str
    project_id: str
    target_revision_id: str
    action_type: str  # "REWRITE" | "SHORTEN" | "EXPAND" | "CHANGE_TONE" | "POLISH_DIALOGUE"
    instruction: str
    target_scene_id: Optional[str] = None
    status: str = "PENDING"  # "PENDING" | "APPROVED" | "REJECTED"
    candidate_screenplay: Dict[str, Any]
    diff_result: ScreenplayDiffResult
    change_impact: ScreenplayChangeImpactDTO


class AIScreenplayProposalService:
    """Generates and manages ScriptRevisionProposals."""

    @staticmethod
    def create_proposal(
        project_id: str,
        base_model: Dict[str, Any],
        action_type: str,
        instruction: str,
        target_scene_id: Optional[str] = None,
    ) -> ScriptRevisionProposalDTO:
        proposal_id = f"prop_{uuid.uuid4().hex[:8]}"

        # Deep copy base model to construct proposed candidate
        candidate = copy.deepcopy(base_model)
        target_rev_id = base_model.get("revision_id", "rev_base")

        scenes = candidate.get("scenes", [])
        for sc in scenes:
            if target_scene_id is None or sc.get("scene_id") == target_scene_id:
                if action_type == "REWRITE":
                    sc["action_description"] = f"[AI Proposal] {sc.get('action_description', '')} (Polished with tone: '{instruction}')"
                elif action_type == "SHORTEN":
                    if len(sc.get("action_description", "")) > 20:
                        sc["action_description"] = sc["action_description"][:25] + "..."
                elif action_type == "POLISH_DIALOGUE":
                    for dlg in sc.get("dialogue_lines", []):
                        dlg["text"] = f"[AI] {dlg.get('text', '')}"
                        dlg["delivery"] = "enhanced"

        diff_result = ScreenplayDiffEngine.compare(base_model, candidate)
        impact = ProductionImpactAnalyzer.analyze_impact(project_id, diff_result)

        return ScriptRevisionProposalDTO(
            proposal_id=proposal_id,
            project_id=project_id,
            target_revision_id=target_rev_id,
            action_type=action_type,
            instruction=instruction,
            target_scene_id=target_scene_id,
            status="PENDING",
            candidate_screenplay=candidate,
            diff_result=diff_result,
            change_impact=impact,
        )
