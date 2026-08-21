"""
Core contracts for Code Video Renderer types.

Pure data contracts for visual theme and graphics catalog.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SafeInsets:
    """Safe area inset bounds in percentage and pixels for 2560x1440 canvas."""
    action_safe_pct: float = 0.05
    title_safe_pct: float = 0.10
    canvas_width: int = 2560
    canvas_height: int = 1440

    @property
    def action_safe_dx(self) -> int:
        return int(self.canvas_width * self.action_safe_pct)

    @property
    def action_safe_dy(self) -> int:
        return int(self.canvas_height * self.action_safe_pct)

    @property
    def title_safe_dx(self) -> int:
        return int(self.canvas_width * self.title_safe_pct)

    @property
    def title_safe_dy(self) -> int:
        return int(self.canvas_height * self.title_safe_pct)

    @property
    def action_safe_box(self) -> Tuple[int, int, int, int]:
        return (
            self.action_safe_dx,
            self.action_safe_dy,
            self.canvas_width - self.action_safe_dx,
            self.canvas_height - self.action_safe_dy,
        )

    @property
    def title_safe_box(self) -> Tuple[int, int, int, int]:
        return (
            self.title_safe_dx,
            self.title_safe_dy,
            self.canvas_width - self.title_safe_dx,
            self.canvas_height - self.title_safe_dy,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "action_safe_pct": self.action_safe_pct,
            "title_safe_pct": self.title_safe_pct,
            "action_safe_box": list(self.action_safe_box),
            "title_safe_box": list(self.title_safe_box),
        }


@dataclass(frozen=True)
class TypographyScale:
    """Typography minimum pixel sizes for 2560x1440 video resolution."""
    hero_title_font_px: int = 64
    section_heading_font_px: int = 44
    card_title_font_px: int = 36
    table_item_font_px: int = 32
    body_font_px: int = 28
    minimum_body_font_px: int = 24
    badge_font_px: int = 24
    font_family_sans: str = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    font_family_mono: str = "'JetBrains Mono', 'Fira Code', Consolas, monospace"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StudioColorPalette:
    """Dark high-contrast color palette optimized for code video production."""
    canvas_bg: str = "#0d1117"
    card_bg: str = "#161b22"
    card_bg_active: str = "#1f242c"
    card_border: str = "#30363d"
    card_border_active: str = "#58a6ff"
    text_primary: str = "#f0f6fc"
    text_secondary: str = "#c9d1d9"
    text_muted: str = "#8b949e"
    primary: str = "#58a6ff"
    success: str = "#7ee787"
    warning: str = "#d29922"
    danger: str = "#f85149"
    concept: str = "#f0883e"
    output: str = "#a371f7"
    dimmed_inactive: str = "rgba(48, 54, 61, 0.45)"
    dimmed_text: str = "#484f58"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CodeVideoVisualTheme:
    """Central styling authority for diagrams, title cards, checklists, and overlays."""

    def __init__(
        self,
        insets: Optional[SafeInsets] = None,
        typography: Optional[TypographyScale] = None,
        palette: Optional[StudioColorPalette] = None,
    ) -> None:
        self.insets = insets or SafeInsets()
        self.typography = typography or TypographyScale()
        self.palette = palette or StudioColorPalette()

    def get_config_hash(self) -> str:
        """Computes deterministic SHA-256 hash of all visual theme parameters."""
        import hashlib
        import json
        data = {
            "insets": self.insets.to_dict(),
            "typography": self.typography.to_dict(),
            "palette": self.palette.to_dict(),
        }
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insets": self.insets.to_dict(),
            "typography": self.typography.to_dict(),
            "palette": self.palette.to_dict(),
            "config_hash": self.get_config_hash(),
        }

    @staticmethod
    def calculate_relative_luminance(hex_color: str) -> float:
        """Calculates WCAG relative luminance for a given hex color."""
        clean_hex = hex_color.lstrip("#")
        if len(clean_hex) == 3:
            clean_hex = "".join([c * 2 for c in clean_hex])
        if len(clean_hex) != 6:
            return 0.5
        r = int(clean_hex[0:2], 16) / 255.0
        g = int(clean_hex[2:4], 16) / 255.0
        b = int(clean_hex[4:6], 16) / 255.0

        def srgb_to_linear(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r_lin = srgb_to_linear(r)
        g_lin = srgb_to_linear(g)
        b_lin = srgb_to_linear(b)
        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    @classmethod
    def calculate_contrast_ratio(cls, hex_fg: str, hex_bg: str) -> float:
        """Calculates WCAG contrast ratio between foreground and background colors."""
        try:
            lum1 = cls.calculate_relative_luminance(hex_fg)
            lum2 = cls.calculate_relative_luminance(hex_bg)
            lighter = max(lum1, lum2)
            darker = min(lum1, lum2)
            return (lighter + 0.05) / (darker + 0.05)
        except Exception:
            return 7.0

    def validate_text_element(self, font_size_px: int, fg_color: str, bg_color: Optional[str] = None) -> List[str]:
        """Validates typography minimum size and color contrast against WCAG AA."""
        issues: List[str] = []
        if font_size_px < self.typography.minimum_body_font_px:
            issues.append(
                f"Font size {font_size_px}px is below minimum required {self.typography.minimum_body_font_px}px"
            )
        bg = bg_color or self.palette.canvas_bg
        ratio = self.calculate_contrast_ratio(fg_color, bg)
        required_ratio = 3.0 if font_size_px >= 32 else 4.5
        if ratio < required_ratio:
            issues.append(
                f"Contrast ratio {ratio:.2f}:1 between '{fg_color}' and '{bg}' is below required {required_ratio}:1"
            )
        return issues


# Graphics Catalog types
class AssetClassification(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    DERIVED = "DERIVED"


class AssetCategory(str, Enum):
    DIAGRAM = "DIAGRAM"
    TITLE_CARD = "TITLE_CARD"
    CHECKLIST = "CHECKLIST"
    OVERLAY = "OVERLAY"


class GraphicTransitionType(str, Enum):
    CUT = "CUT"
    FADE = "FADE"
    SLIDE_UP = "SLIDE_UP"
    DISSOLVE = "DISSOLVE"
    ZOOM_IN = "ZOOM_IN"


class AnimationType(str, Enum):
    NONE = "NONE"
    PULSE = "PULSE"
    GLOW = "GLOW"
    DIM_INACTIVE = "DIM_INACTIVE"
    TYPEWRITER = "TYPEWRITER"


@dataclass
class GraphicsCatalogEntry:
    """Canonical record of a visual asset bound to the video timeline."""
    asset_id: str
    classification: AssetClassification
    category: AssetCategory
    scene_id: str
    entry_ms: int
    exit_ms: int
    duration_ms: int
    transition_in: GraphicTransitionType
    transition_out: GraphicTransitionType
    animation: AnimationType
    filename: str
    content: str
    source_hash: str
    render_config_hash: str
    output_hash: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "classification": self.classification.value,
            "category": self.category.value,
            "scene_id": self.scene_id,
            "entry_ms": self.entry_ms,
            "exit_ms": self.exit_ms,
            "duration_ms": self.duration_ms,
            "transition_in": self.transition_in.value,
            "transition_out": self.transition_out.value,
            "animation": self.animation.value,
            "filename": self.filename,
            "source_hash": self.source_hash,
            "render_config_hash": self.render_config_hash,
            "output_hash": self.output_hash,
            "description": self.description,
        }
