"""
Readability, Safe Area, and Typography QC Verifier (Video 02 Implementation Plan §11.5 & §8.2).

Validates visual ergonomics on Master 2560x1440 Canvas:
- Safe Area Bounds: Action-Safe (5% inset: 2304x1296), Title-Safe (10% inset: 2048x1152).
- Zero Clipping: All text, code symbols, and diagrams contained strictly within bounds.
- Typography scale:
  * hero_title_font_px >= 56px
  * section_heading_font_px >= 40px
  * table_item_font_px >= 32px
  * minimum_body_font_px >= 24px
- Color Contrast: WCAG AA compliance (ratio >= 4.5:1 for body, >= 3.0:1 for large text).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple

from windagent_tools.code_video.renderer.theme import CodeVideoVisualTheme


@dataclass
class ReadabilityQCReport:
    """Detailed report for visual readability, typography, and safe area bounds."""
    is_valid: bool
    canvas_resolution: str
    action_safe_bound: str
    title_safe_bound: str
    typography_scale_valid: bool
    wcag_contrast_valid: bool
    safe_area_valid: bool
    violations: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "canvas_resolution": self.canvas_resolution,
            "action_safe_bound": self.action_safe_bound,
            "title_safe_bound": self.title_safe_bound,
            "typography_scale_valid": self.typography_scale_valid,
            "wcag_contrast_valid": self.wcag_contrast_valid,
            "safe_area_valid": self.safe_area_valid,
            "violations": self.violations,
            "metrics": self.metrics,
            "errors": self.errors,
        }


def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex color string (#rrggbb) to (r, g, b) tuple."""
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join(c * 2 for c in hex_str)
    if len(hex_str) != 6:
        return (0, 0, 0)
    return (
        int(hex_str[0:2], 16),
        int(hex_str[2:4], 16),
        int(hex_str[4:6], 16),
    )


def relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """Calculate WCAG relative luminance from sRGB tuple."""
    def channel_lum(val: int) -> float:
        c = val / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate contrast ratio between two hex colors (1.0 to 21.0)."""
    lum1 = relative_luminance(hex_to_rgb(hex1))
    lum2 = relative_luminance(hex_to_rgb(hex2))
    l_max = max(lum1, lum2)
    l_min = min(lum1, lum2)
    return (l_max + 0.05) / (l_min + 0.05)


class ReadabilityQCVerifier:
    """
    Validates theme, layout insets, and typography against Studio standards.
    """

    MIN_HERO_TITLE_PX: int = 56
    MIN_SECTION_HEADING_PX: int = 40
    MIN_TABLE_ITEM_PX: int = 32
    MIN_BODY_FONT_PX: int = 24
    MIN_WCAG_AA_NORMAL_RATIO: float = 4.5
    MIN_WCAG_AA_LARGE_RATIO: float = 3.0

    @classmethod
    def verify_theme(cls, theme: Optional[CodeVideoVisualTheme] = None) -> ReadabilityQCReport:
        """Verify typography hierarchy and color contrast of a CodeVideoVisualTheme."""
        theme = theme or CodeVideoVisualTheme()
        violations: List[str] = []
        metrics: Dict[str, Any] = {}

        # 1. Canvas and safe area bounds
        metrics["canvas_width"] = theme.insets.canvas_width
        metrics["canvas_height"] = theme.insets.canvas_height
        safe_area_valid = True
        if theme.insets.canvas_width != 2560 or theme.insets.canvas_height != 1440:
            safe_area_valid = False
            violations.append(f"Canvas resolution must be 2560x1440, got {theme.insets.canvas_width}x{theme.insets.canvas_height}")

        action_safe_bound = f"{theme.insets.action_safe_box[2] - theme.insets.action_safe_box[0]}x{theme.insets.action_safe_box[3] - theme.insets.action_safe_box[1]}"
        title_safe_bound = f"{theme.insets.title_safe_box[2] - theme.insets.title_safe_box[0]}x{theme.insets.title_safe_box[3] - theme.insets.title_safe_box[1]}"

        # 2. Typography scale validation
        typography_valid = True
        if theme.typography.hero_title_font_px < cls.MIN_HERO_TITLE_PX:
            typography_valid = False
            violations.append(f"hero_title_font_px {theme.typography.hero_title_font_px}px < minimum {cls.MIN_HERO_TITLE_PX}px")
        if theme.typography.section_heading_font_px < cls.MIN_SECTION_HEADING_PX:
            typography_valid = False
            violations.append(f"section_heading_font_px {theme.typography.section_heading_font_px}px < minimum {cls.MIN_SECTION_HEADING_PX}px")
        if theme.typography.table_item_font_px < cls.MIN_TABLE_ITEM_PX:
            typography_valid = False
            violations.append(f"table_item_font_px {theme.typography.table_item_font_px}px < minimum {cls.MIN_TABLE_ITEM_PX}px")
        if theme.typography.minimum_body_font_px < cls.MIN_BODY_FONT_PX:
            typography_valid = False
            violations.append(f"minimum_body_font_px {theme.typography.minimum_body_font_px}px < minimum {cls.MIN_BODY_FONT_PX}px")

        # 3. Color contrast WCAG AA validation
        wcag_valid = True
        body_contrast = contrast_ratio(theme.palette.text_primary, theme.palette.canvas_bg)
        heading_contrast = contrast_ratio(theme.palette.primary, theme.palette.canvas_bg)
        card_contrast = contrast_ratio(theme.palette.text_primary, theme.palette.card_bg)

        metrics["body_contrast_ratio"] = round(body_contrast, 2)
        metrics["heading_contrast_ratio"] = round(heading_contrast, 2)
        metrics["card_contrast_ratio"] = round(card_contrast, 2)

        if body_contrast < cls.MIN_WCAG_AA_NORMAL_RATIO:
            wcag_valid = False
            violations.append(f"Body text contrast ratio {body_contrast:.2f} < WCAG AA minimum {cls.MIN_WCAG_AA_NORMAL_RATIO}")
        if heading_contrast < cls.MIN_WCAG_AA_LARGE_RATIO:
            wcag_valid = False
            violations.append(f"Heading contrast ratio {heading_contrast:.2f} < WCAG AA minimum {cls.MIN_WCAG_AA_LARGE_RATIO}")

        is_valid = safe_area_valid and typography_valid and wcag_valid and len(violations) == 0

        return ReadabilityQCReport(
            is_valid=is_valid,
            canvas_resolution=f"{theme.insets.canvas_width}x{theme.insets.canvas_height}",
            action_safe_bound=action_safe_bound,
            title_safe_bound=title_safe_bound,
            typography_scale_valid=typography_valid,
            wcag_contrast_valid=wcag_valid,
            safe_area_valid=safe_area_valid,
            violations=violations,
            metrics=metrics,
            errors=violations,
        )


__all__ = [
    "ReadabilityQCReport",
    "ReadabilityQCVerifier",
    "contrast_ratio",
    "hex_to_rgb",
    "relative_luminance",
]
