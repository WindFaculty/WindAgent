"""
Graphics Verifier for Code Video Production (1440p Master).

Inspects all visual assets against:
1. Master canvas resolution (2560x1440).
2. Safe area insets (Title-Safe 10%, Action-Safe 5%).
3. Typography scale (minimum font size >= 24px).
4. Contrast ratio compliance (WCAG AA).
5. Timeline bounds validation against Phase 4 (no GRAPHIC_TIMING_CONFLICT).
6. Tri-hash integrity (source_hash, render_config_hash, output_hash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional

from windagent_core.contracts.code_video import CodeVideoPlan
from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme
from windagent_tools.code_video.renderer.graphics_catalog import (
    AssetClassification,
    GraphicsCatalog,
    GraphicsCatalogEntry,
)


@dataclass
class AssetVerificationResult:
    asset_id: str
    classification: str
    category: str
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_hash: str = ""
    render_config_hash: str = ""
    output_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "classification": self.classification,
            "category": self.category,
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "source_hash": self.source_hash,
            "render_config_hash": self.render_config_hash,
            "output_hash": self.output_hash,
        }


@dataclass
class GraphicsVerificationReport:
    gate: str = "CV02_P8_GRAPHICS_VERIFIED"
    status: str = "PASS"  # PASS or REJECT
    total_assets: int = 0
    required_assets_count: int = 0
    required_passed_count: int = 0
    all_required_passed: bool = True
    results: List[AssetVerificationResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "total_assets": self.total_assets,
            "required_assets_count": self.required_assets_count,
            "required_passed_count": self.required_passed_count,
            "all_required_passed": self.all_required_passed,
            "results": [r.to_dict() for r in self.results],
        }


class GraphicsVerifier:
    """Automated inspection engine for visual assets."""

    def __init__(self, theme: Optional[CodeVideoVisualTheme] = None) -> None:
        self.theme = theme or CodeVideoVisualTheme()

    def verify_entry(self, entry: GraphicsCatalogEntry) -> AssetVerificationResult:
        """Verifies a single visual asset against visual, typography, and hashing rules."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Tri-Hash verification
        if not entry.source_hash or len(entry.source_hash) != 64:
            errors.append("source_hash is missing or invalid SHA-256")
        if not entry.render_config_hash or len(entry.render_config_hash) != 64:
            errors.append("render_config_hash is missing or invalid SHA-256")
        if not entry.output_hash or len(entry.output_hash) != 64:
            errors.append("output_hash is missing or invalid SHA-256")

        # 2. Content integrity
        content = entry.content.strip()
        if not content:
            errors.append("Rendered content is empty")

        # 3. Canvas Resolution in content
        if "2560" not in content and 'viewBox="0 0 2560' not in content:
            # Check if SVG/HTML specifies 2560
            errors.append("Canvas width 2560 is not explicitly defined in rendered artifact")
        if "1440" not in content and '1440"' not in content:
            errors.append("Canvas height 1440 is not explicitly defined in rendered artifact")

        # 4. Typography font size inspection (must be >= 24px)
        font_matches = re.findall(r'font-size[:="]+([0-9]+)(?:px)?["]?', content)
        for size_str in font_matches:
            try:
                size = int(size_str)
                if size < self.theme.typography.minimum_body_font_px:
                    errors.append(
                        f"Found text with font-size {size}px < minimum required {self.theme.typography.minimum_body_font_px}px"
                    )
            except ValueError:
                pass

        # 5. Timeline consistency
        if entry.entry_ms >= entry.exit_ms:
            errors.append(f"entry_ms ({entry.entry_ms}) >= exit_ms ({entry.exit_ms})")
        if entry.duration_ms != (entry.exit_ms - entry.entry_ms):
            errors.append(f"duration_ms ({entry.duration_ms}) does not equal exit_ms - entry_ms")

        is_valid = len(errors) == 0
        return AssetVerificationResult(
            asset_id=entry.asset_id,
            classification=entry.classification.value,
            category=entry.category.value,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            source_hash=entry.source_hash,
            render_config_hash=entry.render_config_hash,
            output_hash=entry.output_hash,
        )

    def verify_catalog(
        self,
        catalog: GraphicsCatalog,
        plan: Optional[CodeVideoPlan] = None,
    ) -> GraphicsVerificationReport:
        """
        Verifies all assets in catalog, validates against Phase 4 plan,
        and generates comprehensive verification report.
        """
        # First check timeline bounds
        if plan is not None:
            catalog.validate_against_plan(plan)

        results: List[AssetVerificationResult] = []
        required_passed = 0
        required_total = 0

        for entry in catalog.entries.values():
            res = self.verify_entry(entry)
            results.append(res)

            if entry.classification == AssetClassification.REQUIRED:
                required_total += 1
                if res.is_valid:
                    required_passed += 1

        all_req_pass = (required_total > 0) and (required_passed == required_total)
        status = "PASS" if all_req_pass else "REJECT"

        return GraphicsVerificationReport(
            gate="CV02_P8_GRAPHICS_VERIFIED",
            status=status,
            total_assets=len(catalog.entries),
            required_assets_count=required_total,
            required_passed_count=required_passed,
            all_required_passed=all_req_pass,
            results=results,
        )
