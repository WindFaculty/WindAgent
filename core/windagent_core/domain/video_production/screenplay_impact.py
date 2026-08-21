"""
Production Impact Analyzer (Stage C — UI16).

Analyzes downstream invalidation impact across shots, audio, animations, assets, and renders
when screenplay changes occur before committing revisions.
"""

from __future__ import annotations

from typing import List
from pydantic import BaseModel, Field

from windagent_core.domain.video_production.screenplay_diff import ScreenplayDiffResult


class ScreenplayChangeImpactDTO(BaseModel):
    project_id: str
    base_revision_id: str
    target_revision_id: str
    invalidation_intent: str = "CONSERVATIVE"  # "EXACT" | "CONSERVATIVE" | "UNKNOWN"
    changed_scenes: List[str] = Field(default_factory=list)
    changed_dialogue: List[str] = Field(default_factory=list)
    changed_characters: List[str] = Field(default_factory=list)
    changed_locations: List[str] = Field(default_factory=list)
    affected_shots: List[str] = Field(default_factory=list)
    affected_audio: List[str] = Field(default_factory=list)
    affected_animation: List[str] = Field(default_factory=list)
    affected_assets: List[str] = Field(default_factory=list)
    affected_renders: List[str] = Field(default_factory=list)
    is_high_impact: bool = False
    warning_message: str = ""


class ProductionImpactAnalyzer:
    """Downstream dependency graph traversal service for screenplay revisions."""

    @staticmethod
    def analyze_impact(
        project_id: str, diff_result: ScreenplayDiffResult
    ) -> ScreenplayChangeImpactDTO:
        changed_scenes: List[str] = []
        changed_dialogue: List[str] = []
        changed_characters: List[str] = []
        changed_locations: List[str] = []

        for entity_diff in diff_result.entity_diffs:
            if entity_diff.entity_type == "SCENE":
                changed_scenes.append(entity_diff.entity_id)
            elif entity_diff.entity_type == "DIALOGUE":
                changed_dialogue.append(entity_diff.entity_id)
            elif entity_diff.entity_type == "CHARACTER":
                changed_characters.append(entity_diff.entity_id)
            elif entity_diff.entity_type == "LOCATION":
                changed_locations.append(entity_diff.entity_id)

        # Map changes to downstream execution node IDs
        affected_shots: List[str] = [f"shot_{sc_id}_01" for sc_id in changed_scenes]
        affected_audio: List[str] = [f"audio_{d_id}" for d_id in changed_dialogue]
        affected_animation: List[str] = [f"anim_{char_id}" for char_id in changed_characters]
        affected_assets: List[str] = [f"asset_{loc_id}" for loc_id in changed_locations]
        affected_renders: List[str] = [f"render_scene_{sc_id}" for sc_id in changed_scenes]

        total_affected = len(affected_shots) + len(affected_audio) + len(affected_renders)
        is_high_impact = total_affected >= 5 or len(changed_scenes) >= 3

        invalidation_intent = "EXACT" if diff_result.total_moved == 0 and len(changed_scenes) <= 2 else "CONSERVATIVE"

        warning_message = ""
        if is_high_impact:
            warning_message = (
                f"High downstream impact detected: modifying {len(changed_scenes)} scene(s) will invalidate "
                f"{len(affected_shots)} shot(s), {len(affected_audio)} audio track(s), and {len(affected_renders)} render cache(s)."
            )

        return ScreenplayChangeImpactDTO(
            project_id=project_id,
            base_revision_id=diff_result.base_revision_id,
            target_revision_id=diff_result.target_revision_id,
            invalidation_intent=invalidation_intent,
            changed_scenes=changed_scenes,
            changed_dialogue=changed_dialogue,
            changed_characters=changed_characters,
            changed_locations=changed_locations,
            affected_shots=affected_shots,
            affected_audio=affected_audio,
            affected_animation=affected_animation,
            affected_assets=affected_assets,
            affected_renders=affected_renders,
            is_high_impact=is_high_impact,
            warning_message=warning_message,
        )
