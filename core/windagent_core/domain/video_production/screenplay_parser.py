"""
Screenplay Parser & Serializer (Stage C — UI11 & UI12).

Provides deterministic Fountain-compatible screenplay serialization and parsing.
Outputs candidate structured models with line/range diagnostic codes and confidence scores.
Preserves entity IDs using sidecar comments (/* id: scene_xyz */) during text edits.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DiagnosticIssue(BaseModel):
    code: str
    message: str
    line: int
    severity: str = "WARNING"  # "ERROR" | "WARNING" | "INFO"
    range: Dict[str, int] = Field(default_factory=lambda: {"start_col": 0, "end_col": 80})
    confidence_score: float = 1.0


class ParseResultDTO(BaseModel):
    success: bool
    requires_review: bool = False
    candidate_screenplay: Dict[str, Any]
    diagnostics: List[DiagnosticIssue] = Field(default_factory=list)


class ScreenplaySerializer:
    """Deterministic converter from structured Screenplay DTO to Fountain text format."""

    @staticmethod
    def serialize(screenplay: Dict[str, Any]) -> str:
        lines: List[str] = []

        title = screenplay.get("title", "UNTITLED SCREENPLAY")
        logline = screenplay.get("logline", "")

        lines.append(f"Title: {title.upper()}")
        if logline:
            lines.append(f"Logline: {logline}")
        lines.append("")
        lines.append("===")
        lines.append("")

        scenes = screenplay.get("scenes", [])
        for sc in sorted(scenes, key=lambda s: s.get("order", 1)):
            sc_id = sc.get("scene_id", f"scene_{uuid.uuid4().hex[:6]}")
            heading = sc.get("title", "INT. UNKNOWN LOCATION - DAY").upper()
            action = sc.get("action_description", "")

            lines.append(f"{heading} /* id: {sc_id} */")
            if action:
                lines.append(action)
            lines.append("")

            dialogue_lines = sc.get("dialogue_lines", [])
            for dlg in sorted(dialogue_lines, key=lambda d: d.get("order", 1)):
                dlg_id = dlg.get("dialogue_id", f"dlg_{uuid.uuid4().hex[:6]}")
                char_name = dlg.get("character_name", "UNKNOWN").upper()
                delivery = dlg.get("delivery", "").strip()
                text = dlg.get("text", "").strip()

                lines.append(f"{char_name} /* id: {dlg_id} */")
                if delivery:
                    lines.append(f"({delivery})")
                lines.append(text)
                lines.append("")

        return "\n".join(lines)


class ScreenplayParser:
    """Parses Fountain text format into a structured candidate model with diagnostics."""

    @staticmethod
    def parse(text: str, base_screenplay_id: str = "sp_parsed") -> ParseResultDTO:
        diagnostics: List[DiagnosticIssue] = []
        raw_lines = text.splitlines()

        title = "UNTITLED SCREENPLAY"
        logline = ""
        scenes: List[Dict[str, Any]] = []

        current_scene: Optional[Dict[str, Any]] = None
        current_dialogue: Optional[Dict[str, Any]] = None
        current_char_name: Optional[str] = None
        current_char_id: Optional[str] = None
        requires_review = False

        scene_heading_regex = re.compile(r"^(INT\.|EXT\.|INT/EXT\.|EST\.|I/E\.)\s+(.+)$", re.IGNORECASE)
        id_sidecar_regex = re.compile(r"/\*\s*id:\s*([a-zA-Z0-9_\-]+)\s*\*/")

        line_num = 0
        scene_order = 0

        for line in raw_lines:
            line_num += 1
            stripped = line.strip()

            if not stripped:
                continue

            # Header metadata parsing
            if stripped.startswith("Title:"):
                title = stripped[6:].strip()
                continue
            if stripped.startswith("Logline:"):
                logline = stripped[8:].strip()
                continue
            if stripped == "===":
                continue

            # Scene heading detection
            if scene_heading_regex.match(stripped) or stripped.isupper() and any(stripped.startswith(p) for p in ["INT", "EXT"]):
                scene_order += 1
                sidecar_match = id_sidecar_regex.search(stripped)
                scene_id = sidecar_match.group(1) if sidecar_match else f"scene_{uuid.uuid4().hex[:6]}"
                clean_heading = id_sidecar_regex.sub("", stripped).strip()

                current_scene = {
                    "scene_id": scene_id,
                    "order": scene_order,
                    "title": clean_heading,
                    "location_id": f"loc_{scene_id}",
                    "location_name": clean_heading.split("-")[0].replace("INT.", "").replace("EXT.", "").strip() or "LOCATION",
                    "character_ids": [],
                    "action_description": "",
                    "time_of_day": "DAY" if "DAY" in clean_heading else ("NIGHT" if "NIGHT" in clean_heading else "DAY"),
                    "estimated_duration_seconds": 15,
                    "dialogue_lines": [],
                }
                scenes.append(current_scene)
                current_dialogue = None
                continue

            # Character cue detection (all caps line or with sidecar comment)
            char_sidecar_match = id_sidecar_regex.search(stripped)
            clean_line_no_comment = id_sidecar_regex.sub("", stripped).strip()

            if current_scene is not None and (clean_line_no_comment.isupper() and len(clean_line_no_comment.split()) <= 4 and not clean_line_no_comment.startswith("(")):
                current_char_name = clean_line_no_comment
                current_char_id = char_sidecar_match.group(1) if char_sidecar_match else f"dlg_{uuid.uuid4().hex[:6]}"
                if f"char_{current_char_name.lower()}" not in current_scene["character_ids"]:
                    current_scene["character_ids"].append(f"char_{current_char_name.lower()}")
                continue

            # Dialogue text line
            if current_scene is not None and current_char_name is not None:
                dlg_order = len(current_scene["dialogue_lines"]) + 1
                delivery = ""

                if stripped.startswith("(") and stripped.endswith(")"):
                    delivery = stripped[1:-1].strip()
                    continue

                dlg_dto = {
                    "dialogue_id": current_char_id or f"dlg_{uuid.uuid4().hex[:6]}",
                    "scene_id": current_scene["scene_id"],
                    "character_id": f"char_{current_char_name.lower()}",
                    "character_name": current_char_name,
                    "order": dlg_order,
                    "text": stripped,
                    "delivery": delivery,
                }
                current_scene["dialogue_lines"].append(dlg_dto)
                current_char_name = None
                current_char_id = None
                continue

            # Action description
            if current_scene is not None:
                if current_scene["action_description"]:
                    current_scene["action_description"] += " " + stripped
                else:
                    current_scene["action_description"] = stripped

        if not scenes:
            diagnostics.append(
                DiagnosticIssue(
                    code="EMPTY_SCREENPLAY",
                    message="No valid scenes were recognized in the screenplay text.",
                    line=1,
                    severity="ERROR",
                    confidence_score=0.2,
                )
            )
            requires_review = True

        candidate_screenplay = {
            "screenplay_id": base_screenplay_id,
            "title": title,
            "logline": logline,
            "status": "DRAFT",
            "scenes": scenes,
        }

        return ParseResultDTO(
            success=len([d for d in diagnostics if d.severity == "ERROR"]) == 0,
            requires_review=requires_review,
            candidate_screenplay=candidate_screenplay,
            diagnostics=diagnostics,
        )
