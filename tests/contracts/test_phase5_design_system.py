"""
Contract and Verification Tests for Phase 5 — Design System Extraction & Convergence.
Validates token authority, primitive catalog integrity, desktop & web re-export compatibility, and Phase 5 artifacts.
"""

import json
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE_5_DIR = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "phase_05"
FRONTEND_UI_DIR = WORKSPACE_ROOT / "frontend" / "packages" / "ui"
DESKTOP_UI_INDEX = WORKSPACE_ROOT / "apps" / "desktop" / "src" / "components" / "ui" / "index.ts"

def test_design_tokens_authority_and_domains():
    """Verify that design tokens are modularized into standard domains with a single authority index."""
    tokens_dir = FRONTEND_UI_DIR / "src" / "tokens"
    assert (tokens_dir / "index.css").exists()
    assert (tokens_dir / "colors.css").exists()
    assert (tokens_dir / "typography.css").exists()
    assert (tokens_dir / "spacing.css").exists()
    assert (tokens_dir / "radius.css").exists()
    assert (tokens_dir / "shadows.css").exists()
    assert (tokens_dir / "z-index.css").exists()
    assert (tokens_dir / "motion.css").exists()
    assert (tokens_dir / "layout.css").exists()

def test_shared_ui_components_exist():
    """Verify that shared primitive components exist in @windagent/ui."""
    components_dir = FRONTEND_UI_DIR / "src" / "components"
    required = [
        "Button.tsx", "IconButton.tsx", "Badge.tsx", "StatusBadge.tsx",
        "Card.tsx", "Panel.tsx", "EmptyState.tsx", "Tabs.tsx",
        "ProgressBar.tsx", "Skeleton.tsx", "Alert.tsx", "Dropdown.tsx",
        "Tooltip.tsx", "Input.tsx", "Textarea.tsx", "Select.tsx",
        "Checkbox.tsx", "Switch.tsx", "Modal.tsx", "Spinner.tsx", "Table.tsx"
    ]
    for comp in required:
        assert (components_dir / comp).exists(), f"Component missing: {comp}"

def test_desktop_ui_reexports_shared_ui():
    """Verify that apps/desktop/src/components/ui/index.ts re-exports from @windagent/ui."""
    assert DESKTOP_UI_INDEX.exists()
    content = DESKTOP_UI_INDEX.read_text(encoding="utf-8")
    assert "from '@windagent/ui'" in content or 'from "@windagent/ui"' in content

def test_phase5_verdict_and_manifests():
    """Verify Phase 5 manifests and final verdict."""
    final_verdict_file = PHASE_5_DIR / "final_verdict.json"
    assert final_verdict_file.exists(), "Phase 5 final_verdict.json missing"
    
    with open(final_verdict_file, "r", encoding="utf-8") as f:
        verdict = json.load(f)
        assert verdict.get("phase") == "5"
        assert verdict.get("verdict") == "FEV3_P5_DESIGN_SYSTEM_VERIFIED"
        assert verdict.get("status") == "PASS"
        criteria = verdict.get("criteria", {})
        assert criteria.get("shared_tokens_package_pass") is True
        assert criteria.get("shared_primitives_pass") is True
        assert criteria.get("desktop_consumes_shared_ui") is True
        assert criteria.get("web_consumes_same_ui") is True
        assert criteria.get("unintentional_visual_change") == 0
