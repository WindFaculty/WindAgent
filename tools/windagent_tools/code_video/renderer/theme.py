"""
Code Video Visual Theme & Styling Tokens.

Canonical definitions moved to core/windagent_core/contracts/code_video/renderer.py.
This module re-exports for backward compatibility.
"""

from windagent_core.contracts.code_video.renderer import (
    SafeInsets,
    TypographyScale,
    StudioColorPalette,
    CodeVideoVisualTheme,
)

__all__ = [
    "SafeInsets",
    "TypographyScale",
    "StudioColorPalette",
    "CodeVideoVisualTheme",
]
