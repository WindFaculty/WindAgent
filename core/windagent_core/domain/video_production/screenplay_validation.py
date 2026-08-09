"""
Screenplay Validation Gate Engine (Stage C — UI18).

Performs authoritative screenplay integrity validation.
Blocks revision lock commands when blocking_count > 0.
Generates AssetRequirement[] outputs for Stage E asset discovery integration.
"""

from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class ValidationIssueDTO(BaseModel):
    code: str
    severity: str  # "BLOCKING" | "WARNING" | "INFO"
    entity_type: str  # "SCENE" | "DIALOGUE" | "CHARACTER" | "LOCATION" | "SCREENPLAY"
    entity_id: str
    message: str
    remediation_hint: str = ""


class AssetRequirementDTO(BaseModel):
    requirement_id: str
    asset_type: str  # "CHARACTER" | "LOCATION" | "PROP"
    ref_id: str
    display_name: str
    required_in_scenes: List[str] = Field(default_factory=list)


class ScreenplayValidationReportDTO(BaseModel):
    project_id: str
    revision_id: str
    is_lockable: bool
    total_issues: int
    blocking_count: int
    warning_count: int
    info_count: int
    issues: List[ValidationIssueDTO] = Field(default_factory=list)
    asset_requirements: List[AssetRequirementDTO] = Field(default_factory=list)


class ScreenplayValidationGate:
    """Authoritative validation rules engine for screenplay lock gating."""

    @staticmethod
    def validate_screenplay(project_id: str, screenplay: Dict[str, Any]) -> ScreenplayValidationReportDTO:
        issues: List[ValidationIssueDTO] = []
        asset_requirements: List[AssetRequirementDTO] = []

        rev_id = screenplay.get("revision_id", "rev_unknown")
        scenes = screenplay.get("scenes", [])

        if not scenes:
            issues.append(
                ValidationIssueDTO(
                    code="NO_SCENES_PRESENT",
                    severity="BLOCKING",
                    entity_type="SCREENPLAY",
                    entity_id=screenplay.get("screenplay_id", "sp_01"),
                    message="Screenplay must contain at least one scene.",
                    remediation_hint="Add a scene heading (e.g. INT. LIVING ROOM - DAY) to the screenplay.",
                )
            )

        known_characters: set[str] = {"char_hero", "char_mentor", "char_antagonist"}
        location_map: Dict[str, List[str]] = {}

        seen_orders: set[int] = set()

        for sc in scenes:
            sc_id = sc.get("scene_id", "scene_unknown")
            sc_order = sc.get("order", 1)
            title = sc.get("title", "")
            loc_id = sc.get("location_id", f"loc_{sc_id}")
            loc_name = sc.get("location_name", "UNKNOWN LOCATION")

            # Scene ordering check
            if sc_order in seen_orders:
                issues.append(
                    ValidationIssueDTO(
                        code="DUPLICATE_SCENE_ORDER",
                        severity="BLOCKING",
                        entity_type="SCENE",
                        entity_id=sc_id,
                        message=f"Duplicate scene order index {sc_order} found in '{title}'.",
                        remediation_hint="Re-order scenes so each scene has a unique integer index.",
                    )
                )
            seen_orders.add(sc_order)

            # Location tracking
            if loc_id not in location_map:
                location_map[loc_id] = []
                asset_requirements.append(
                    AssetRequirementDTO(
                        requirement_id=f"req_loc_{loc_id}",
                        asset_type="LOCATION",
                        ref_id=loc_id,
                        display_name=loc_name,
                        required_in_scenes=[sc_id],
                    )
                )
            else:
                location_map[loc_id].append(sc_id)

            # Character references check
            for char_id in sc.get("character_ids", []):
                if char_id not in known_characters and not char_id.startswith("char_"):
                    issues.append(
                        ValidationIssueDTO(
                            code="UNKNOWN_CHARACTER_REF",
                            severity="WARNING",
                            entity_type="CHARACTER",
                            entity_id=char_id,
                            message=f"Unregistered character reference '{char_id}' in scene '{title}'.",
                            remediation_hint="Create character profile in Character Master Bible.",
                        )
                    )

            # Dialogue checks
            dialogue_lines = sc.get("dialogue_lines", [])
            for dlg in dialogue_lines:
                dlg_id = dlg.get("dialogue_id", "dlg_unknown")
                char_id = dlg.get("character_id", "")
                text = dlg.get("text", "").strip()

                if not text:
                    issues.append(
                        ValidationIssueDTO(
                            code="EMPTY_DIALOGUE_TEXT",
                            severity="BLOCKING",
                            entity_type="DIALOGUE",
                            entity_id=dlg_id,
                            message=f"Dialogue line {dlg_id} by '{dlg.get('character_name')}' has empty text.",
                            remediation_hint="Provide dialogue text or remove dialogue line.",
                        )
                    )

        blocking_count = len([i for i in issues if i.severity == "BLOCKING"])
        warning_count = len([i for i in issues if i.severity == "WARNING"])
        info_count = len([i for i in issues if i.severity == "INFO"])
        is_lockable = (blocking_count == 0)

        return ScreenplayValidationReportDTO(
            project_id=project_id,
            revision_id=rev_id,
            is_lockable=is_lockable,
            total_issues=len(issues),
            blocking_count=blocking_count,
            warning_count=warning_count,
            info_count=info_count,
            issues=issues,
            asset_requirements=asset_requirements,
        )
