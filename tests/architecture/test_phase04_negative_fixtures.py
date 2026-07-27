"""Phase 4 - Negative fixture test suite for architecture policy violations.

Each fixture is a minimal repository structure that should trigger exactly one
architecture violation rule, causing the checker to fail with non-zero exit code.
"""

import json
import tempfile
import shutil
from copy import deepcopy
from pathlib import Path
import pytest

from scripts.check_architecture_imports import check


class FixtureRepository:
    """Helper to create temporary fixture repositories."""
    
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="arch_fixture_")
        self.root = Path(self.temp_dir)
    
    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_package(self, name, namespace=None):
        """Create a package structure."""
        pkg_path = self.root / name
        pkg_path.mkdir(parents=True, exist_ok=True)
        ns_path = pkg_path / (namespace or name)
        ns_path.mkdir(parents=True, exist_ok=True)
        (ns_path / "__init__.py").write_text("")
        return ns_path
    
    def create_file(self, path, content=""):
        """Create a file with given content."""
        file_path = self.root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path
    
    def create_pyproject(self, path, dependencies=None):
        """Create a pyproject.toml."""
        deps = dependencies or []
        content = f"""[project]
name = "{path.replace('/', '-')}"
version = "0.1.0"
dependencies = {json.dumps(deps)}
"""
        self.create_file(f"{path}/pyproject.toml", content)


# Minimal policy config for testing
MINIMAL_POLICY = {
    "version": "3.0",
    "workspace": {"root": ".", "members": []},
    "global_rules": {
        "forbid_cross_app_imports": True,
        "forbid_core_framework_imports": True,
        "require_declared_workspace_dependencies": True,
        "forbid_dependency_cycles": True,
        "forbid_public_api_leakage": True,
        "forbid_legacy_backend_imports": True,
        "forbid_production_test_fallbacks": True,
        "enforce_legacy_quarantine": True,
        "forbid_dynamic_imports": True,
        "enforce_composition_root_rule": True,
    },
    "forbidden_patterns": {
        "production_fallback_regex": r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b",
        "test_adapter_paths": ["tests/"],
        "legacy_quarantine": {
            "zone": "apps/backend",
            "allowlist": [],
        },
    },
    "canonical_models": [],
    "required_top_level_packages": [],
    "packages": {},
}


@pytest.fixture
def fixture_repo():
    """Create a temporary fixture repository."""
    repo = FixtureRepository()
    yield repo
    repo.cleanup()


# =============================================================================
# Fixture: Cross-app import
# =============================================================================

@pytest.fixture
def cross_app_import_fixture(fixture_repo):
    """Fixture: apps/api imports from apps/cli."""
    repo = fixture_repo
    
    # Create packages
    api_ns = repo.create_package("apps/api", "windagent_api")
    repo.create_package("apps/cli", "windagent_cli")
    
    # Create cross-app import
    (api_ns / "module.py").write_text("from windagent_cli import something\n")
    
    # Create pyproject files
    repo.create_pyproject("apps/api", ["windagent-cli"])
    repo.create_pyproject("apps/cli")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/api", "apps/cli"]
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
            "allowed_dependencies": ["windagent_cli"],
            "forbidden_dependencies": [],
        },
        "cli": {
            "layer": "app",
            "namespace": "windagent_cli",
            "path": "apps/cli",
            "allowed_dependencies": [],
            "forbidden_dependencies": [],
        },
    }
    
    return repo, policy


def test_cross_app_import_violation(cross_app_import_fixture):
    """Test that cross-app import is detected."""
    repo, policy = cross_app_import_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "cross_app_dependency" for v in report["violations"])


# =============================================================================
# Fixture: Legacy reverse import (canonical -> legacy)
# =============================================================================

@pytest.fixture
def legacy_reverse_import_fixture(fixture_repo):
    """Fixture: canonical package imports from apps/backend."""
    repo = fixture_repo
    
    # Create packages
    repo.create_package("apps/backend", "backend")
    core_ns = repo.create_package("core", "windagent_core")
    
    # Create reverse import
    (core_ns / "module.py").write_text("from backend import legacy_thing\n")
    
    # Create pyproject files
    repo.create_pyproject("apps/backend")
    repo.create_pyproject("core")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/backend", "core"]
    policy["packages"] = {
        "backend": {
            "layer": "legacy",
            "namespace": "backend",
            "path": "apps/backend",
            "allowed_dependencies": [],
            "forbidden_dependencies": [],
            "quarantine": True,
        },
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
            "allowed_dependencies": [],
            "forbidden_dependencies": ["apps", "backend"],
        },
    }
    
    return repo, policy


def test_legacy_reverse_import_violation(legacy_reverse_import_fixture):
    """Test that canonical -> legacy import is detected."""
    repo, policy = legacy_reverse_import_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] in ("legacy_backend_import", "canonical_to_legacy_import") 
               for v in report["violations"])


# =============================================================================
# Fixture: Core framework import
# =============================================================================

@pytest.fixture
def core_framework_import_fixture(fixture_repo):
    """Fixture: core imports fastapi."""
    repo = fixture_repo
    
    # Create core package
    core_ns = repo.create_package("core", "windagent_core")
    
    # Create framework import
    (core_ns / "domain").mkdir(parents=True, exist_ok=True)
    (core_ns / "domain" / "__init__.py").write_text("")
    (core_ns / "domain" / "models.py").write_text("from fastapi import FastAPI\n")
    
    # Create pyproject
    repo.create_pyproject("core")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core"]
    policy["packages"] = {
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
            "allowed_dependencies": [],
            "forbidden_dependencies": ["fastapi"],
        },
    }
    
    return repo, policy


def test_core_framework_import_violation(core_framework_import_fixture):
    """Test that framework import in core is detected."""
    repo, policy = core_framework_import_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "core_framework_import" for v in report["violations"])


# =============================================================================
# Fixture: Dynamic legacy import
# =============================================================================

@pytest.fixture
def dynamic_legacy_import_fixture(fixture_repo):
    """Fixture: dynamic import of legacy module."""
    repo = fixture_repo
    
    # Create packages
    core_ns = repo.create_package("core", "windagent_core")
    repo.create_package("apps/backend", "backend")
    
    # Create dynamic import
    (core_ns / "loader.py").write_text("""
import importlib
module = importlib.import_module("backend.legacy")
""")
    
    # Create pyproject files
    repo.create_pyproject("core")
    repo.create_pyproject("apps/backend")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core", "apps/backend"]
    policy["global_rules"]["forbid_dynamic_imports"] = True
    policy["packages"] = {
        "backend": {
            "layer": "legacy",
            "namespace": "backend",
            "path": "apps/backend",
            "quarantine": True,
        },
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
        },
    }
    
    return repo, policy


def test_dynamic_legacy_import_violation(dynamic_legacy_import_fixture):
    """Test that dynamic legacy import is detected."""
    repo, policy = dynamic_legacy_import_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "dynamic_external_import" for v in report["violations"])


# =============================================================================
# Fixture: Private API import
# =============================================================================

@pytest.fixture
def private_api_import_fixture(fixture_repo):
    """Fixture: cross-package private module import."""
    repo = fixture_repo
    
    # Create packages
    api_ns = repo.create_package("apps/api", "windagent_api")
    core_ns = repo.create_package("core", "windagent_core")
    
    # Create private module in core
    (core_ns / "_internal").mkdir(parents=True, exist_ok=True)
    (core_ns / "_internal" / "__init__.py").write_text("")
    
    # Import private module from api
    (api_ns / "module.py").write_text("from windagent_core._internal import hidden\n")
    
    # Create pyproject files
    repo.create_pyproject("apps/api", ["windagent-core"])
    repo.create_pyproject("core")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/api", "core"]
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
            "allowed_dependencies": ["windagent_core"],
        },
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
        },
    }
    
    return repo, policy


def test_private_api_import_violation(private_api_import_fixture):
    """Test that private cross-package import is detected."""
    repo, policy = private_api_import_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] in ("public_api_leakage", "private_cross_package_import") 
               for v in report["violations"])


# =============================================================================
# Fixture: Missing declared dependency
# =============================================================================

@pytest.fixture
def missing_declared_dep_fixture(fixture_repo):
    """Fixture: workspace dependency not declared in pyproject.toml."""
    repo = fixture_repo
    
    # Create packages
    api_ns = repo.create_package("apps/api", "windagent_api")
    repo.create_package("core", "windagent_core")
    
    # Import core from api but don't declare dependency
    (api_ns / "module.py").write_text("from windagent_core import Model\n")
    
    # Create pyproject without dependency
    repo.create_pyproject("apps/api", dependencies=[])
    repo.create_pyproject("core")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/api", "core"]
    policy["global_rules"]["require_declared_workspace_dependencies"] = True
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
            "allowed_dependencies": ["windagent_core"],
        },
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
        },
    }
    
    return repo, policy


def test_missing_declared_dep_violation(missing_declared_dep_fixture):
    """Test that missing declared dependency is detected."""
    repo, policy = missing_declared_dep_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "undeclared_workspace_dependency" for v in report["violations"])


# =============================================================================
# Fixture: Package cycle
# =============================================================================

@pytest.fixture
def package_cycle_fixture(fixture_repo):
    """Fixture: circular dependency between packages."""
    repo = fixture_repo
    
    # Create packages
    pkg_a_ns = repo.create_package("pkg_a", "windagent_pkga")
    pkg_b_ns = repo.create_package("pkg_b", "windagent_pkgb")
    
    # Create circular imports
    (pkg_a_ns / "module.py").write_text("from windagent_pkgb import B\n")
    (pkg_b_ns / "module.py").write_text("from windagent_pkga import A\n")
    
    # Create pyproject files
    repo.create_pyproject("pkg_a", ["windagent-pkgb"])
    repo.create_pyproject("pkg_b", ["windagent-pkga"])
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["pkg_a", "pkg_b"]
    policy["global_rules"]["forbid_dependency_cycles"] = True
    policy["packages"] = {
        "pkg_a": {
            "layer": "application",
            "namespace": "windagent_pkga",
            "path": "pkg_a",
            "allowed_dependencies": ["windagent_pkgb"],
        },
        "pkg_b": {
            "layer": "application",
            "namespace": "windagent_pkgb",
            "path": "pkg_b",
            "allowed_dependencies": ["windagent_pkga"],
        },
    }
    
    return repo, policy


def test_package_cycle_violation(package_cycle_fixture):
    """Test that package cycle is detected."""
    repo, policy = package_cycle_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "dependency_cycle" for v in report["violations"])


# =============================================================================
# Fixture: Duplicate canonical model
# =============================================================================

@pytest.fixture
def duplicate_canonical_model_fixture(fixture_repo):
    """Fixture: duplicate canonical model definition."""
    repo = fixture_repo
    
    # Create packages
    core_ns = repo.create_package("core", "windagent_core")
    orchestration_ns = repo.create_package("orchestration", "windagent_orchestration")
    
    # Define same canonical model in two places
    (core_ns / "domain.py").write_text("""
class TaskState:
    status: str
    result: dict
""")
    (orchestration_ns / "models.py").write_text("""
class TaskState:
    status: str
    result: dict
    retry_count: int
""")
    
    # Create pyproject files
    repo.create_pyproject("core")
    repo.create_pyproject("orchestration", ["windagent-core"])
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core", "orchestration"]
    policy["canonical_models"] = ["TaskState"]
    policy["packages"] = {
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
        },
        "orchestration": {
            "layer": "application",
            "namespace": "windagent_orchestration",
            "path": "orchestration",
            "allowed_dependencies": ["windagent_core"],
        },
    }
    
    return repo, policy


def test_duplicate_canonical_model_violation(duplicate_canonical_model_fixture):
    """Test that duplicate canonical model is detected."""
    repo, policy = duplicate_canonical_model_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "duplicate_canonical_model" for v in report["violations"])


# =============================================================================
# Fixture: Production test fallback
# =============================================================================

@pytest.fixture
def production_fake_runtime_fixture(fixture_repo):
    """Fixture: production code uses test fallback symbol."""
    repo = fixture_repo
    
    # Create api package with _fallback_ symbol
    api_ns = repo.create_package("apps/api", "windagent_api")
    (api_ns / "service.py").write_text("from _fallback_fake_runtime import FakeRuntime\n")
    
    # Create pyproject
    repo.create_pyproject("apps/api")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/api"]
    policy["global_rules"]["forbid_production_test_fallbacks"] = True
    policy["forbidden_patterns"]["production_fallback_regex"] = r"\b_fallback_[A-Za-z_][A-Za-z0-9_]*\b"
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
        },
    }
    
    return repo, policy


def test_production_fake_runtime_violation(production_fake_runtime_fixture):
    """Test that production test fallback is detected."""
    repo, policy = production_fake_runtime_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "production_fallback_reference" for v in report["violations"])


# =============================================================================
# Fixture: Domain importing config
# =============================================================================

@pytest.fixture
def domain_importing_config_fixture(fixture_repo):
    """Fixture: domain imports config."""
    repo = fixture_repo
    
    # Create core package with domain and config
    core_ns = repo.create_package("core", "windagent_core")
    (core_ns / "domain").mkdir(parents=True, exist_ok=True)
    (core_ns / "config").mkdir(parents=True, exist_ok=True)
    (core_ns / "domain" / "__init__.py").write_text("")
    (core_ns / "config" / "__init__.py").write_text("")
    
    # Domain imports config
    (core_ns / "domain" / "models.py").write_text("from windagent_core.config import Settings\n")
    
    # Create pyproject
    repo.create_pyproject("core")
    
    # Create policy with internal boundaries
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["core"]
    policy["packages"] = {
        "core": {
            "layer": "domain",
            "namespace": "windagent_core",
            "path": "core",
            "internal_boundaries": {
                "domain": {
                    "path": "core/windagent_core/domain",
                    "forbidden_dependencies": ["core/windagent_core/config"],
                    "allowed_dependencies": ["core/windagent_core/contracts"],
                },
                "config": {
                    "path": "core/windagent_core/config",
                },
            },
        },
    }
    
    return repo, policy


def test_domain_importing_config_violation(domain_importing_config_fixture):
    """Test that domain importing config is detected."""
    repo, policy = domain_importing_config_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "core_internal_boundary_violation" for v in report["violations"])


# =============================================================================
# Fixture: App constructing SQL adapter
# =============================================================================

@pytest.fixture
def app_constructing_sql_adapter_fixture(fixture_repo):
    """Fixture: app layer constructs SQL adapter directly."""
    repo = fixture_repo
    
    # Create api package
    api_ns = repo.create_package("apps/api", "windagent_api")
    (api_ns / "module.py").write_text("from sqlalchemy import create_engine\nengine = create_engine('sqlite:///test.db')\n")
    
    # Create pyproject
    repo.create_pyproject("apps/api")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/api"]
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
        },
    }
    
    return repo, policy


def test_app_constructing_sql_adapter_violation(app_constructing_sql_adapter_fixture):
    """Test that app layer constructing SQL adapter is detected."""
    repo, policy = app_constructing_sql_adapter_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] == "orm_in_application_layer" for v in report["violations"])


# =============================================================================
# Fixture: Legacy main delegation
# =============================================================================

@pytest.fixture
def legacy_main_delegation_fixture(fixture_repo):
    """Fixture: apps/backend/main.py delegates to windagent_api."""
    repo = fixture_repo
    
    # Create backend package with main.py
    backend_ns = repo.create_package("apps/backend", "backend")
    (backend_ns / "main.py").write_text("from windagent_api.main import app\n")
    
    # Create pyproject
    repo.create_pyproject("apps/backend")
    
    # Create policy
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = ["apps/backend"]
    policy["packages"] = {
        "backend": {
            "layer": "legacy",
            "namespace": "backend",
            "path": "apps/backend",
            "quarantine": True,
        },
    }
    
    return repo, policy


def test_legacy_main_delegation_violation(legacy_main_delegation_fixture):
    """Test that recreating the retired legacy entrypoint is detected."""
    repo, policy = legacy_main_delegation_fixture
    report, _ = check(repo.root, policy)
    
    assert report["status"] == "FAIL"
    assert any(v["rule"] in ("legacy_backend_source_present", "legacy_backend_import", "canonical_to_legacy_import")
               for v in report["violations"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
