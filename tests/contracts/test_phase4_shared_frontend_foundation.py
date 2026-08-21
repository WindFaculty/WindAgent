"""
Contract and Verification Tests for Phase 4 — Shared Frontend Foundation & Canonical Router.
Validates shell architecture cutover, zero Web -> Desktop App imports, TabKeeper removal, and Phase 4 manifests.
"""

import json
import re
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
PHASE_4_DIR = WORKSPACE_ROOT / "artifacts" / "frontend_restructure" / "phase_04"
FRONTEND_APP_DIR = WORKSPACE_ROOT / "frontend" / "app"
WEB_SRC_DIR = WORKSPACE_ROOT / "apps" / "web" / "src"
DESKTOP_SRC_DIR = WORKSPACE_ROOT / "apps" / "desktop" / "src"

def test_web_imports_desktop_app_zero():
    """Verify that apps/web NO LONGER imports @desktop/App directly."""
    import_pattern = re.compile(r'from\s+[\'"]@desktop/App[\'"]')
    violations = []
    
    for p in WEB_SRC_DIR.rglob("*"):
        if p.is_file() and p.suffix in [".ts", ".tsx"]:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), 1):
                if import_pattern.search(line):
                    violations.append(f"{p.relative_to(WORKSPACE_ROOT)}:{line_no}")
                    
    assert len(violations) == 0, f"Found direct @desktop/App imports in apps/web: {violations}"

def test_tabkeeper_authority_eliminated():
    """Verify that TabKeeper has been completely eliminated from App shells."""
    for scan_file in [FRONTEND_APP_DIR / "src" / "app" / "App.tsx", DESKTOP_SRC_DIR / "App.tsx"]:
        if scan_file.exists():
            content = scan_file.read_text(encoding="utf-8", errors="ignore")
            assert "function TabKeeper" not in content, f"TabKeeper found in {scan_file}"
            assert "<TabKeeper" not in content, f"<TabKeeper usage found in {scan_file}"

def test_route_manifest_authority():
    """Verify that routeManifest.ts exists and provides authoritative navigation groups."""
    manifest_file = FRONTEND_APP_DIR / "src" / "app" / "routeManifest.ts"
    assert manifest_file.exists(), "routeManifest.ts missing in frontend/app"
    content = manifest_file.read_text(encoding="utf-8")
    assert "CANONICAL_ROUTE_MANIFEST" in content
    assert "findRouteByPath" in content
    assert "getNavigationGroups" in content

def test_platform_adapters_exist():
    """Verify that PlatformAdapter interface and implementations exist."""
    platform_dir = FRONTEND_APP_DIR / "src" / "platform"
    assert (platform_dir / "platformAdapter.ts").exists()
    assert (platform_dir / "webAdapter.ts").exists()
    assert (platform_dir / "tauriAdapter.ts").exists()
    assert (platform_dir / "PlatformProvider.tsx").exists()

def test_phase4_verdict_and_manifests():
    """Verify Phase 4 artifacts and final verdict."""
    final_verdict_file = PHASE_4_DIR / "final_verdict.json"
    assert final_verdict_file.exists(), "Phase 4 final_verdict.json missing"
    
    with open(final_verdict_file, "r", encoding="utf-8") as f:
        verdict = json.load(f)
        assert verdict.get("phase") == "4"
        assert verdict.get("verdict") == "FEV3_P4_SHARED_FRONTEND_FOUNDATION_VERIFIED"
        assert verdict.get("status") == "PASS"
        criteria = verdict.get("criteria", {})
        assert criteria.get("web_imports_desktop_app") == 0
        assert criteria.get("tabkeeper_route_authority") == 0
        assert criteria.get("route_manifest_authorities") == 1
        assert criteria.get("desktop_build_pass") is True
        assert criteria.get("web_build_pass") is True
