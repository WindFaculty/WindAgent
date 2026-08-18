"""
Code Video Renderer Subsystem.

Provides deterministic renderers and catalogs for:
- Code Editor (syntax highlighting, typing, selection, highlights, zoom)
- Terminal (PowerShell execution playback, stdout/stderr, exit code badges)
- Architecture & Flow Diagrams (DIAG_01 to DIAG_08, 1440p Master)
- Title Cards, Scope Checklists, Outro Teasers (S02, S16, S18, S19)
- B-roll Overlays & Security Callouts (OVR_S06 to OVR_S19)
- Visual Theme & Safe Insets (CodeVideoVisualTheme)
- Graphics Catalog & Verification (GraphicsCatalog, GraphicsVerifier)
- Master Code Studio Layout
"""

from windagent_tools.code_video.renderer.code_renderer import (
    CodeEditorRenderer,
    CodeEditorState,
    CodeToken,
    PYTHON_BUILTINS,
    PYTHON_KEYWORDS,
    PythonSyntaxHighlighter,
    PythonTokenType,
)
from windagent_tools.code_video.renderer.diagram_renderer import (
    DiagramEdge,
    DiagramNode,
    DiagramRenderer,
    DiagramState,
    NodeCategory,
)
from windagent_tools.code_video.renderer.graphics_catalog import (
    AnimationType,
    AssetCategory,
    AssetClassification,
    GRAPHIC_TIMING_CONFLICT,
    GraphicsCatalog,
    GraphicsCatalogEntry,
    TransitionType,
)
from windagent_tools.code_video.renderer.graphics_verifier import (
    AssetVerificationResult,
    GraphicsVerificationReport,
    GraphicsVerifier,
)
from windagent_tools.code_video.renderer.overlay_renderer import (
    OverlayCardState,
    OverlayPosition,
    OverlayRenderer,
)
from windagent_tools.code_video.renderer.studio_renderer import (
    CodeStudioRenderer,
    FileTreeItem,
    FileTreeState,
    StudioLayoutState,
)
from windagent_tools.code_video.renderer.terminal_renderer import (
    TerminalLine,
    TerminalLineType,
    TerminalRenderer,
    TerminalState,
)
from windagent_tools.code_video.renderer.theme import (
    CodeVideoVisualTheme,
    SafeInsets,
    StudioColorPalette,
    TypographyScale,
)
from windagent_tools.code_video.renderer.title_renderer import (
    ChecklistItem,
    ChecklistItemStatus,
    ChecklistState,
    OutroCardState,
    TitleCardState,
    TitleRenderer,
)

__all__ = [
    "PythonTokenType",
    "PYTHON_KEYWORDS",
    "PYTHON_BUILTINS",
    "CodeToken",
    "PythonSyntaxHighlighter",
    "CodeEditorState",
    "CodeEditorRenderer",
    "TerminalLineType",
    "TerminalLine",
    "TerminalState",
    "TerminalRenderer",
    "NodeCategory",
    "DiagramNode",
    "DiagramEdge",
    "DiagramState",
    "DiagramRenderer",
    "ChecklistItemStatus",
    "ChecklistItem",
    "TitleCardState",
    "ChecklistState",
    "OutroCardState",
    "TitleRenderer",
    "OverlayPosition",
    "OverlayCardState",
    "OverlayRenderer",
    "SafeInsets",
    "TypographyScale",
    "StudioColorPalette",
    "CodeVideoVisualTheme",
    "AssetClassification",
    "AssetCategory",
    "TransitionType",
    "AnimationType",
    "GraphicsCatalogEntry",
    "GraphicsCatalog",
    "GRAPHIC_TIMING_CONFLICT",
    "AssetVerificationResult",
    "GraphicsVerificationReport",
    "GraphicsVerifier",
    "FileTreeItem",
    "FileTreeState",
    "StudioLayoutState",
    "CodeStudioRenderer",
]
