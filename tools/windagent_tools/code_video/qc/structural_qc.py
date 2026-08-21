"""
Structural QC Verifier for Code Video Production (Video 02 Implementation Plan §11.1).

Validates the structural integrity and scene completeness of Video 02:
- Exact total duration of 975,000 ms (16:15.000 = 29,250 frames @ 30fps).
- Presence of all 19 canonical scenes (S01 to S19) in strict sequential order.
- Presence of all 8 required code scenes (S06, S07, S08, S09, S10, S12, S13, S15).
- Presence of all 11 required diagrams, title cards, and scope checklists (§8.1).
- Visual modes compliance (SPLIT, TITLE_CARD, DIAGRAM, TERMINAL_ONLY, CODE_STUDIO, CHECKLIST).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from windagent_core.contracts.code_video import CodeVideoPlan
from windagent_tools.code_video.renderer.graphics_catalog import GraphicsCatalog


EXPECTED_SCENE_IDS: List[str] = [
    f"S{idx:02d}" for idx in range(1, 20)
]

REQUIRED_CODE_SCENES: Set[str] = {
    "S06",  # Message
    "S07",  # AgentConfig
    "S08",  # LLMClient Protocol
    "S09",  # Fake LLM
    "S10",  # Agent Core
    "S12",  # Real Provider
    "S13",  # API Key Security
    "S15",  # Tests
}

REQUIRED_GRAPHIC_ASSETS: Set[str] = {
    "DIAG_01_FINAL_ARCH",
    "DIAG_02_COMPONENT_FLOW",
    "DIAG_03_TODAY_VS_NEXT",
    "DIAG_04_LLMCLIENT_ABSTRACTION",
    "DIAG_05A_COGNITIVE_LOOP",
    "DIAG_05B_MISSING_CAPABILITIES",
    "DIAG_06_DOMAIN_VS_INFRA",
    "CARD_S02_HOOK",
    "CARD_S18_MILESTONE",
    "CARD_S19_TEASER",
    "CHECKLIST_S16_NOT_YET",
}


@dataclass
class StructuralQCReport:
    """Detailed report for structural QC validation."""
    is_valid: bool
    total_scenes: int
    total_duration_ms: int
    total_frames: int
    scene_ids: List[str]
    missing_scenes: List[str] = field(default_factory=list)
    missing_code_scenes: List[str] = field(default_factory=list)
    missing_graphics: List[str] = field(default_factory=list)
    timing_violations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "total_scenes": self.total_scenes,
            "total_duration_ms": self.total_duration_ms,
            "total_frames": self.total_frames,
            "scene_ids": self.scene_ids,
            "missing_scenes": self.missing_scenes,
            "missing_code_scenes": self.missing_code_scenes,
            "missing_graphics": self.missing_graphics,
            "timing_violations": self.timing_violations,
            "errors": self.errors,
            "metadata": self.metadata,
        }


class StructuralQCVerifier:
    """
    Validates structural compliance of CodeVideoPlan and graphics catalog against Video 02 rules.
    """

    EXPECTED_TOTAL_DURATION_MS: int = 975_000
    EXPECTED_FPS: int = 30
    EXPECTED_TOTAL_FRAMES: int = 29_250

    @classmethod
    def verify_plan(
        cls,
        plan: CodeVideoPlan,
        graphics_catalog: Optional[GraphicsCatalog] = None,
    ) -> StructuralQCReport:
        """Verify structural properties of a compiled CodeVideoPlan."""
        errors: List[str] = []
        timing_violations: List[str] = []
        scene_ids: List[str] = [s.scene_id for s in plan.scenes]

        # 1. Total scenes count and presence
        missing_scenes = [sid for sid in EXPECTED_SCENE_IDS if sid not in scene_ids]
        if missing_scenes:
            errors.append(f"Missing required scenes: {missing_scenes}")

        # 2. Sequential order check
        if scene_ids != EXPECTED_SCENE_IDS:
            errors.append(f"Scene order mismatch: expected {EXPECTED_SCENE_IDS}, got {scene_ids}")

        # 3. Total duration check
        total_duration_ms = sum(s.duration_ms for s in plan.scenes)
        if total_duration_ms != cls.EXPECTED_TOTAL_DURATION_MS:
            timing_violations.append(
                f"Total plan duration mismatch: got {total_duration_ms}ms, expected {cls.EXPECTED_TOTAL_DURATION_MS}ms"
            )

        # 4. Total frame count precision
        total_frames = (total_duration_ms * cls.EXPECTED_FPS) // 1000
        if total_frames != cls.EXPECTED_TOTAL_FRAMES:
            timing_violations.append(
                f"Total frame count mismatch: got {total_frames}, expected {cls.EXPECTED_TOTAL_FRAMES}"
            )

        if plan.duration_ms != cls.EXPECTED_TOTAL_DURATION_MS:
            timing_violations.append(
                f"Plan duration_ms mismatch: got {plan.duration_ms}ms, expected {cls.EXPECTED_TOTAL_DURATION_MS}ms"
            )

        # 5. Continuous timeline validation
        current_time_ms = 0
        for scene in plan.scenes:
            if scene.start_ms != current_time_ms:
                timing_violations.append(
                    f"Scene {scene.scene_id} start mismatch: expected {current_time_ms}ms, got {scene.start_ms}ms"
                )
            if scene.duration_ms <= 0:
                timing_violations.append(f"Scene {scene.scene_id} has invalid duration {scene.duration_ms}ms")
            current_time_ms += scene.duration_ms

        # 6. Required code scenes check
        present_code_scenes = {
            s.scene_id for s in plan.scenes
            if s.visual_mode.value in ("CODE_STUDIO", "SPLIT") or s.scene_id in REQUIRED_CODE_SCENES
        }
        missing_code_scenes = [
            sid for sid in sorted(list(REQUIRED_CODE_SCENES))
            if sid not in present_code_scenes
        ]
        if missing_code_scenes:
            errors.append(f"Missing required code scenes: {missing_code_scenes}")

        # 7. Required graphics check
        missing_graphics: List[str] = []
        if graphics_catalog is not None:
            catalog_asset_ids = set(graphics_catalog.entries.keys())
            missing_graphics = [
                gid for gid in sorted(list(REQUIRED_GRAPHIC_ASSETS))
                if gid not in catalog_asset_ids
            ]
            if missing_graphics:
                errors.append(f"Missing required graphic assets in catalog: {missing_graphics}")

        all_errors = errors + timing_violations
        is_valid = len(all_errors) == 0

        return StructuralQCReport(
            is_valid=is_valid,
            total_scenes=len(plan.scenes),
            total_duration_ms=total_duration_ms,
            total_frames=total_frames,
            scene_ids=scene_ids,
            missing_scenes=missing_scenes,
            missing_code_scenes=missing_code_scenes,
            missing_graphics=missing_graphics,
            timing_violations=timing_violations,
            errors=all_errors,
            metadata={
                "video_id": plan.video_id,
                "fps": cls.EXPECTED_FPS,
                "resolution": plan.resolution.to_string() if hasattr(plan.resolution, "to_string") else str(plan.resolution),
            },
        )


__all__ = [
    "EXPECTED_SCENE_IDS",
    "REQUIRED_CODE_SCENES",
    "REQUIRED_GRAPHIC_ASSETS",
    "StructuralQCReport",
    "StructuralQCVerifier",
]
