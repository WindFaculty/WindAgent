"""Phase 16 - Negative fixtures for the tightened composition-root policy.

The V3 policy is structural and fail-closed: every class DEFINED in an
``layer: infrastructure`` package whose name carries a mechanism suffix is an
adapter, and instantiating it anywhere outside an explicitly allowlisted
composition root / factory module is a violation.  These six fixtures pin the
exact semantics required by the Phase B hardening:

CASE 1  application instantiates a SQL repository            -> FAIL
CASE 2  application workflow instantiates a provider adapter -> FAIL
CASE 3  composition root instantiates adapters               -> PASS
CASE 4  infrastructure merely defines an adapter class       -> PASS
CASE 5  application constructs a tool adapter                -> FAIL
CASE 6  approved factory constructs its own adapter          -> PASS
"""

import shutil
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.check_architecture_imports import check


class FixtureRepository:
    """Helper to create temporary fixture repositories."""

    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="arch_croot_fixture_")
        self.root = Path(self.temp_dir)

    def cleanup(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_package(self, name, namespace=None):
        pkg_path = self.root / name
        pkg_path.mkdir(parents=True, exist_ok=True)
        ns_path = pkg_path / (namespace or name)
        ns_path.mkdir(parents=True, exist_ok=True)
        (ns_path / "__init__.py").write_text("")
        return ns_path

    def create_pyproject(self, path):
        # Map package path to distribution name matching the workspace policy
        # (e.g. storage -> windagent-storage, apps/api -> windagent-api)
        if path.startswith("apps/"):
            dist = "windagent-" + path.split("/")[-1]
        else:
            dist = "windagent-" + path.replace("/", "-")
        content = f"""[project]
name = "{dist}"
version = "0.1.0"
dependencies = []
"""
        target = self.root / path / "pyproject.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


MINIMAL_POLICY = {
    "version": "3.0",
    "workspace": {"root": ".", "members": []},
    "global_rules": {
        "forbid_cross_app_imports": True,
        "require_declared_workspace_dependencies": True,
        "enforce_composition_root_rule": True,
    },
    "forbidden_patterns": {},
    "canonical_models": [],
    "required_top_level_packages": [],
    "packages": {},
}


def _install_infrastructure_packages(repo):
    """Create three infrastructure packages, each defining one adapter."""
    storage_ns = repo.create_package("storage", "windagent_storage")
    (storage_ns / "repositories.py").write_text(
        "class SqlThingRepository:\n"
        "    def __init__(self) -> None:\n"
        "        self.rows: list = []\n"
    )
    providers_ns = repo.create_package("providers", "windagent_providers")
    (providers_ns / "ollama.py").write_text(
        "class OllamaProviderAdapter:\n"
        "    def __init__(self) -> None:\n"
        "        self.base_url = 'http://localhost'\n"
    )
    tools_ns = repo.create_package("tools", "windagent_tools")
    (tools_ns / "blender.py").write_text(
        "class BlenderEngineAdapter:\n"
        "    def __init__(self) -> None:\n"
        "        self.ready = False\n"
    )
    repo.create_pyproject("storage")
    repo.create_pyproject("providers")
    repo.create_pyproject("tools")


def _install_app_package(repo):
    api_ns = repo.create_package("apps/api", "windagent_api")
    repo.create_pyproject("apps/api")
    return api_ns


def _policy_for_fixture(repo):
    policy = deepcopy(MINIMAL_POLICY)
    policy["workspace"]["members"] = [
        "apps/api",
        "storage",
        "providers",
        "tools",
    ]
    policy["packages"] = {
        "api": {
            "layer": "app",
            "namespace": "windagent_api",
            "path": "apps/api",
            "allowed_dependencies": [
                "windagent_storage",
                "windagent_providers",
                "windagent_tools",
            ],
        },
        "storage": {
            "layer": "infrastructure",
            "namespace": "windagent_storage",
            "path": "storage",
        },
        "providers": {
            "layer": "infrastructure",
            "namespace": "windagent_providers",
            "path": "providers",
        },
        "tools": {
            "layer": "infrastructure",
            "namespace": "windagent_tools",
            "path": "tools",
        },
    }
    return policy


@pytest.fixture
def fixture_repo():
    repo = FixtureRepository()
    _install_infrastructure_packages(repo)
    _install_app_package(repo)
    yield repo
    repo.cleanup()


# =============================================================================
# CASE 1 — application instantiates a SQL repository -> FAIL
# =============================================================================

def test_case1_application_instantiates_sql_repository(fixture_repo):
    repo = fixture_repo
    (repo.root / "apps/api/windagent_api/service.py").write_text(
        "from windagent_storage.repositories import SqlThingRepository\n"
        "\n"
        "\n"
        "def build_repo():\n"
        "    return SqlThingRepository()\n"
    )
    report, _ = check(repo.root, _policy_for_fixture(repo))

    assert report["status"] == "FAIL"
    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert hits, "application constructing SqlThingRepository must be flagged"
    assert any("SqlThingRepository" in v["message"] for v in hits)


# =============================================================================
# CASE 2 — application workflow instantiates a provider adapter -> FAIL
# =============================================================================

def test_case2_workflow_instantiates_provider_adapter(fixture_repo):
    repo = fixture_repo
    (repo.root / "apps/api/windagent_api/workflow.py").write_text(
        "from windagent_providers.ollama import OllamaProviderAdapter\n"
        "\n"
        "\n"
        "def run_workflow():\n"
        "    adapter = OllamaProviderAdapter()\n"
        "    return adapter.base_url\n"
    )
    report, _ = check(repo.root, _policy_for_fixture(repo))

    assert report["status"] == "FAIL"
    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert any("OllamaProviderAdapter" in v["message"] for v in hits), (
        "workflow constructing a provider adapter must be flagged"
    )


# =============================================================================
# CASE 3 — composition root instantiates adapters -> PASS
# =============================================================================

def test_case3_composition_root_instantiation_allowed(fixture_repo):
    repo = fixture_repo
    composition_dir = repo.root / "apps/api/windagent_api/composition"
    composition_dir.mkdir(parents=True, exist_ok=True)
    (composition_dir / "__init__.py").write_text("")
    (composition_dir / "container.py").write_text(
        "from windagent_storage.repositories import SqlThingRepository\n"
        "from windagent_providers.ollama import OllamaProviderAdapter\n"
        "\n"
        "\n"
        "class Container:\n"
        "    def build(self):\n"
        "        return SqlThingRepository(), OllamaProviderAdapter()\n"
    )
    report, _ = check(repo.root, _policy_for_fixture(repo))

    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert hits == [], (
        f"composition-root wiring must be exempt, got: {hits}"
    )


# =============================================================================
# CASE 4 — infrastructure defines an adapter class (no construction) -> PASS
# =============================================================================

def test_case4_infrastructure_definition_is_not_a_violation(fixture_repo):
    repo = fixture_repo
    # Application imports the adapter ONLY as a type annotation — no Call node.
    (repo.root / "apps/api/windagent_api/consumer.py").write_text(
        "from windagent_storage.repositories import SqlThingRepository\n"
        "\n"
        "\n"
        "class Consumer:\n"
        "    def __init__(self, repo: SqlThingRepository | None = None) -> None:\n"
        "        self._repo = repo\n"
    )
    report, _ = check(repo.root, _policy_for_fixture(repo))

    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert hits == [], (
        f"defining/importing an adapter without constructing it must pass, got: {hits}"
    )


# =============================================================================
# CASE 5 — application constructs a tool adapter -> FAIL
# =============================================================================

def test_case5_application_constructs_tool_adapter(fixture_repo):
    repo = fixture_repo
    (repo.root / "apps/api/windagent_api/tools_boot.py").write_text(
        "from windagent_tools.blender import BlenderEngineAdapter\n"
        "\n"
        "\n"
        "def make_engine():\n"
        "    return BlenderEngineAdapter()\n"
    )
    report, _ = check(repo.root, _policy_for_fixture(repo))

    assert report["status"] == "FAIL"
    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert any("BlenderEngineAdapter" in v["message"] for v in hits), (
        "application constructing a tool adapter must be flagged"
    )


# =============================================================================
# CASE 6 — approved factory constructs its own adapter -> PASS
# =============================================================================

def test_case6_approved_factory_construction_allowed(fixture_repo):
    repo = fixture_repo
    (repo.root / "storage/windagent_storage/factory.py").write_text(
        "from windagent_storage.repositories import SqlThingRepository\n"
        "\n"
        "\n"
        "def create_sql_thing_repository():\n"
        "    \"\"\"Single allowlisted construction point for the storage package.\"\"\"\n"
        "    return SqlThingRepository()\n"
    )
    policy = _policy_for_fixture(repo)
    policy["global_rules"]["composition_roots"] = [
        "apps/api/windagent_api/composition/**",
        "storage/windagent_storage/factory.py",
    ]
    report, _ = check(repo.root, policy)

    hits = [v for v in report["violations"]
            if v["rule"] == "concrete_adapter_outside_composition"]
    assert hits == [], (
        f"explicitly allowlisted factory must be able to construct its own "
        f"adapter, got: {hits}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
