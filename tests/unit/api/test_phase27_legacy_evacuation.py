"""
Phase 27 Unit Tests: Legacy Backend Evacuation — Canonical Migration Verification.
Verifies that all legacy backend functionality has been migrated to canonical V2 packages,
apps/backend imports have been eliminated from non-backend code,
AST scan finds zero import boundary violations across V2 packages,
and canonical service classes are importable from their correct namespaces.
"""

from __future__ import annotations

import ast
import sys
import subprocess
import tomllib
from pathlib import Path

from windagent_api.main import app as v2_app
from windagent_execution.registry import ExecutionRuntimeRegistry
from windagent_orchestration.task_manager.service import TaskManager
from windagent_providers.registry.canonical_registry import CanonicalModelRegistryService
from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
from windagent_tools.registry import ToolRegistry
from windagent_tools.security.permission_engine import PermissionEngine


ROOT = Path(__file__).resolve().parents[3]
CANONICAL_SOURCE_ROOTS = (
    "apps/api",
    "apps/worker",
    "apps/cli",
    "core",
    "orchestration",
    "execution",
    "intelligence",
    "providers",
    "tools",
    "workflows",
    "verification",
    "context",
    "memory",
    "storage",
    "observability",
    "evals",
    "plugins",
    "skills",
)


def test_canonical_api_app_importable():
    """Verify windagent_api.main:app (V2 canonical) is importable and is a FastAPI app."""
    from fastapi import FastAPI
    assert isinstance(v2_app, FastAPI), "windagent_api.main:app must be a FastAPI application"


def test_canonical_services_importable():
    """Verify all core V2 service classes are importable from their canonical namespaces."""
    # These should all succeed without any apps.backend intermediary
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
    assert SqlUnitOfWork is not None


def test_ast_import_scan_zero_boundary_violations():
    """Verify check_architecture_imports.py AST scan returns 0 violations.

    This is the canonical acceptance gate for Phase 6:
    LEGACY_BACKEND_RUNTIME_REMOVED requires zero architecture violations.
    """
    checker_script = ROOT / "scripts" / "check_architecture_imports.py"
    assert checker_script.exists(), f"Architecture checker not found at {checker_script}"

    res = subprocess.run([sys.executable, str(checker_script)], capture_output=True, text=True)
    assert res.returncode == 0, (
        f"Architecture check failed with {res.returncode} violations:\n"
        f"{res.stdout}\n{res.stderr}"
    )
    assert "Zero boundary violations detected" in res.stdout


def test_no_apps_backend_imports_in_canonical_code():
    """AST-scan every canonical production package for legacy imports."""
    violations: list[str] = []
    for source_root in CANONICAL_SOURCE_ROOTS:
        for source in (ROOT / source_root).rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in source.parts):
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    if module == "apps.backend" or module.startswith("apps.backend."):
                        relative = source.relative_to(ROOT).as_posix()
                        violations.append(f"{relative}:{node.lineno}: {module}")

    assert violations == [], (
        f"Found {len(violations)} legacy import(s) in canonical code:\n"
        + "\n".join(violations)
    )


def test_legacy_runtime_tree_and_compatibility_shims_removed():
    """Only ignored local caches may remain under the retired filesystem path."""
    legacy = ROOT / "apps" / "backend"
    forbidden_files = (
        "pyproject.toml",
        "uv.lock",
        "main.py",
        "compatibility_shim.py",
        "compatibility/services_shim.py",
        "db/models.py",
        "db/database.py",
    )
    assert [path for name in forbidden_files if (path := legacy / name).exists()] == []

    python_sources = [
        source
        for source in legacy.rglob("*.py")
        if ".venv" not in source.parts
        and "__pycache__" not in source.parts
        and ".pytest_cache" not in source.parts
    ]
    assert python_sources == []


def test_workspace_and_pythonpath_exclude_legacy_backend():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    members = config["tool"]["uv"]["workspace"]["members"]
    pythonpath = config["tool"]["pytest"]["ini_options"]["pythonpath"]
    assert "apps/backend" not in members
    assert "apps/backend" not in pythonpath
    assert {"apps/api", "apps/worker", "apps/cli"}.issubset(members)


def test_runtime_launchers_and_ci_use_canonical_api():
    active_files = [
        ROOT / "run.ps1",
        ROOT / "scripts" / "dev_api.ps1",
        ROOT / "scripts" / "dev_desktop.ps1",
        ROOT / "scripts" / "dev_frontend.ps1",
        ROOT / "scripts" / "healthcheck.ps1",
        ROOT / "scripts" / "verify_phase14_cutover.py",
        ROOT / ".github" / "workflows" / "ci.yaml",
        ROOT / ".github" / "workflows" / "phase14_multi_replica_fencing.yml",
        ROOT / "apps" / "desktop" / "src-tauri" / "src" / "main.rs",
    ]
    violations: list[str] = []
    for path in active_files:
        text = path.read_text(encoding="utf-8")
        if "apps/backend" in text or "apps\\backend" in text or "dev_backend" in text:
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []

    launcher = (ROOT / "scripts" / "dev_api.ps1").read_text(encoding="utf-8")
    assert "windagent_api.main:app" in launcher
    assert "WINDAGENT_DATABASE_URL" in launcher


def test_desktop_and_web_clients_do_not_call_api_v1():
    violations: list[str] = []
    for client_root in (ROOT / "apps" / "desktop" / "src", ROOT / "apps" / "web" / "src"):
        for source in client_root.rglob("*"):
            if source.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
                continue
            if "/api/v1" in source.read_text(encoding="utf-8"):
                violations.append(source.relative_to(ROOT).as_posix())
    assert violations == []
