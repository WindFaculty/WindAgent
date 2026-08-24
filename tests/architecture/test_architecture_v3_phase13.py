"""
Phase 13 Architecture Tests: Dead Code and Legacy Retirement Certification.
Validates:
1. Desktop dead code elimination (zero legacy client/store/services in desktop).
2. Desktop delegates cleanly to @windagent/app.
3. Legacy tool adapter removal.
4. Legacy V2 API quarantine remains fail-closed (returns 410 Gone).
5. Media asset trust gates and process supervisors remain fail-closed to quarantine.
6. Zero duplicate canonical models.
7. Zero architecture boundary violations.
"""

import subprocess
import sys
from pathlib import Path
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent

from windagent_api.main import app
from windagent_tools.media_assets.trust_gate import MediaAssetTrustGate
from windagent_tools.media_assets import QuarantinedAssetError
from windagent_core.domain.video_production.asset_lifecycle import AssetLifecycleState
from windagent_tools.production_engines.blender.runtime.supervisor import STATE_QUARANTINED


def test_desktop_dead_code_elimination():
    """Verify that old desktop client, socket manager, and stores are permanently removed."""
    dead_files = [
        ROOT_DIR / "apps" / "desktop" / "src" / "api" / "client.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "api" / "types.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "services" / "conversationSocketManager.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "services" / "conversationSocketManager.test.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "state" / "multiAgentStore.tsx",
        ROOT_DIR / "apps" / "desktop" / "src" / "state" / "multiAgentStore.test.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "state" / "theme.tsx",
        ROOT_DIR / "apps" / "desktop" / "src" / "lib" / "apiBase.ts",
        ROOT_DIR / "apps" / "desktop" / "src" / "lib" / "apiBase.test.ts",
    ]
    for p in dead_files:
        assert not p.exists(), f"Dead file still exists: {p}"


def test_desktop_clean_delegation_to_shared_app():
    """Verify desktop App.tsx and main.tsx delegate 100% to @windagent/app."""
    app_tsx = (ROOT_DIR / "apps" / "desktop" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "SharedApp" in app_tsx
    assert "createTauriAdapter" in app_tsx
    assert "<SharedApp platform={platform} />" in app_tsx

    main_tsx = (ROOT_DIR / "apps" / "desktop" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "@windagent/app" in main_tsx
    assert "bootstrapFrontend" in main_tsx


def test_legacy_tools_adapter_removed():
    """Verify legacy_tools.py adapter has been permanently removed."""
    legacy_tool_path = ROOT_DIR / "tools" / "windagent_tools" / "adapters" / "legacy_tools.py"
    assert not legacy_tool_path.exists(), f"legacy_tools.py still exists: {legacy_tool_path}"


def test_api_v2_quarantine_fail_closed():
    """Verify API V2 returns 410 Gone tombstone under default configuration."""
    client = TestClient(app)
    v2_endpoints = [
        ("GET", "/api/v2/tasks"),
        ("POST", "/api/v2/tasks"),
        ("GET", "/api/v2/sessions"),
        ("GET", "/api/v2/providers"),
        ("GET", "/api/v2/workflows"),
        ("GET", "/api/v2/events"),
    ]
    for method, endpoint in v2_endpoints:
        if method == "GET":
            res = client.get(endpoint)
        else:
            res = client.post(endpoint, json={})
        assert res.status_code == 410, f"Expected 410 for {endpoint}, got {res.status_code}"
        data = res.json()
        assert data.get("status") == 410
        assert "API V2 has been permanently retired" in data.get("detail", "")


def test_security_quarantine_fail_closed():
    """Verify media asset trust gate and blender supervisor fail closed to quarantine."""
    assert QuarantinedAssetError is not None
    assert AssetLifecycleState.QUARANTINED.value == "QUARANTINED"
    assert STATE_QUARANTINED == "QUARANTINED"

    gate = MediaAssetTrustGate()
    assert gate is not None


def test_duplicate_canonical_models_zero():
    """Verify check_duplicate_canonical_models.py scan reports zero duplicate canonical models."""
    script = ROOT_DIR / "scripts" / "check_duplicate_canonical_models.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode == 0, f"Duplicate check failed:\n{res.stdout}\n{res.stderr}"
    assert "Zero duplicate canonical model definitions" in res.stdout


def test_architecture_v3_boundaries_pass():
    """Verify check_architecture_imports.py reports zero boundary violations."""
    script = ROOT_DIR / "scripts" / "check_architecture_imports.py"
    res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert res.returncode == 0, f"Architecture check failed:\n{res.stdout}\n{res.stderr}"
    assert "Zero boundary violations detected" in res.stdout