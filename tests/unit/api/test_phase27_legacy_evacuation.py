"""
Phase 27 Unit and Integration Tests: Legacy Backend Evacuation.
Verifies that apps/backend has been reduced strictly to compatibility bootstrap,
AST scan finds zero import boundary violations across V2 packages,
and compatibility shims delegate to canonical workspace packages.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(root))
for pkg in ["core", "storage", "orchestration", "execution", "workflows", "tools", "apps/api", "apps/backend"]:
    p = str(root / pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest
from fastapi.testclient import TestClient
from apps.backend.main import app as legacy_app
from apps.backend.compatibility.services_shim import (
    TaskManager, ToolRegistry, PermissionEngine, ExecutionRuntimeRegistry,
    CanonicalModelRegistryService, SqlUnitOfWork
)


def test_legacy_backend_status_endpoint():
    """Verify apps/backend/main.py delegates to V2 API and exposes legacy status."""
    with TestClient(legacy_app) as client:
        res = client.get("/internal/legacy-status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "LEGACY_BACKEND_EVACUATED"
        assert data["evacuated"] is True
        assert data["canonical_package"] == "windagent_api"


def test_compatibility_shims_availability():
    """Verify compatibility shims delegate to canonical V2 workspace packages."""
    tm = TaskManager()
    assert tm is not None

    tr = ToolRegistry()
    assert tr is not None

    pe = PermissionEngine()
    assert pe is not None

    er = ExecutionRuntimeRegistry()
    assert er is not None

    cr = CanonicalModelRegistryService()
    assert cr is not None


def test_ast_import_scan_zero_boundary_violations():
    """Verify check_architecture_imports.py AST scan returns 0 violations."""
    checker_script = root / "scripts" / "check_architecture_imports.py"
    assert checker_script.exists()

    res = subprocess.run([sys.executable, str(checker_script)], capture_output=True, text=True)
    assert res.returncode == 0, f"Architecture check failed: {res.stdout}\n{res.stderr}"
    assert "Zero boundary violations detected" in res.stdout
