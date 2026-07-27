import importlib.util
from pathlib import Path
import textwrap


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scaffold_architecture_v2.py"
SPEC = importlib.util.spec_from_file_location("scaffold_architecture_v2", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pyproject_generation_does_not_read_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "ROOT_DIR", tmp_path)
    package = tmp_path / "core"
    package.mkdir()
    (package / "pyproject.toml").write_text("sentinel", encoding="utf-8")
    info = {
        "path": "core",
        "namespace": "windagent_core",
        "description": "Core",
        "version": "0.3.0",
        "allowed_dependencies": [],
        "external_dependencies": ["pydantic>=2.7"],
    }
    generated = MODULE.generate_package_pyproject("core", info)
    assert generated != "sentinel"
    assert 'name = "windagent_core"' in generated
    assert '"pydantic>=2.7"' in generated


def test_init_generation_uses_canonical_version(tmp_path, monkeypatch):
    """After Phase 7, generated __init__.py must derive __version__ from the canonical authority."""
    monkeypatch.setattr(MODULE, "ROOT_DIR", tmp_path)
    namespace = tmp_path / "core" / "windagent_core"
    namespace.mkdir(parents=True)
    (namespace / "__init__.py").write_text("sentinel", encoding="utf-8")
    generated = MODULE.generate_package_init("core", {
        "path": "core", "namespace": "windagent_core", "description": "Core", "version": "0.3.0"
    })
    assert generated != "sentinel"
    assert "from windagent_core.version import PRODUCT_VERSION" in generated
    assert "__version__ = PRODUCT_VERSION" in generated


def test_init_public_exports_block_for_app_package():
    """Config-declared required exports must appear in generated block."""
    info = {
        "path": "apps/worker",
        "namespace": "windagent_worker",
        "description": "Worker",
        "public_exports": {
            "required": {
                "TaskLease": "windagent_worker.lease",
                "TaskLeaseManager": "windagent_worker.lease",
                "ProductionWorker": "windagent_worker.runner",
            }
        },
    }
    generated = MODULE.generate_package_init("worker", info)
    assert MODULE.EXPORTS_BEGIN in generated
    assert MODULE.EXPORTS_END in generated
    assert "from windagent_worker.lease import " in generated
    assert "from windagent_worker.runner import ProductionWorker" in generated
    assert "TaskLease" in generated
    assert "TaskLeaseManager" in generated
    assert "ProductionWorker" in generated


def test_update_init_preserves_existing_exports():
    """Migrating an existing __init__.py should not discard hand-maintained re-exports."""
    current = textwrap.dedent('''\
        """Providers."""
        from windagent_providers.base import ProviderFailure
        from windagent_providers.registry import CanonicalModelRegistryService

        __version__ = "2.0.0"
        __all__ = ["ProviderFailure", "CanonicalModelRegistryService"]
    ''')
    info = {
        "path": "providers",
        "namespace": "windagent_providers",
        "description": "Providers",
        "public_exports": {"required": {}},
    }
    migrated = MODULE._update_init_contents(current, info)
    assert "from windagent_core.version import PRODUCT_VERSION" in migrated
    assert "__version__ = PRODUCT_VERSION" in migrated
    assert "from windagent_providers.base import ProviderFailure" in migrated
    assert "from windagent_providers.registry import CanonicalModelRegistryService" in migrated
    assert "__all__" in migrated


def test_update_init_injects_missing_required_exports():
    """If required exports are missing, the scaffold should inject a guarded block."""
    current = textwrap.dedent('''\
        """Worker."""
        from windagent_core.version import PRODUCT_VERSION
        __version__ = PRODUCT_VERSION
    ''')
    info = {
        "path": "apps/worker",
        "namespace": "windagent_worker",
        "description": "Worker",
        "public_exports": {
            "required": {
                "TaskLeaseManager": "windagent_worker.lease",
                "ProductionWorker": "windagent_worker.runner",
            }
        },
    }
    migrated = MODULE._update_init_contents(current, info)
    assert MODULE.EXPORTS_BEGIN in migrated
    assert "from windagent_worker.lease import TaskLeaseManager" in migrated
    assert "from windagent_worker.runner import ProductionWorker" in migrated
    assert "TaskLeaseManager" in migrated
    assert "ProductionWorker" in migrated


def test_extract_init_exports_detects_top_level_imports():
    source = textwrap.dedent('''\
        from windagent_core.version import PRODUCT_VERSION
        from windagent_worker.lease import TaskLeaseManager
        from windagent_worker.runner import ProductionWorker
        __all__ = ["TaskLeaseManager", "ProductionWorker"]
        __version__ = PRODUCT_VERSION
    ''')
    exported, version_ok = MODULE._extract_init_exports(source)
    assert version_ok
    assert "TaskLeaseManager" in exported
    assert "ProductionWorker" in exported


def test_scaffold_matches_requires_canonical_version_for_non_app_package():
    info = {"namespace": "windagent_core", "path": "core", "public_exports": {"required": {}}}
    current = textwrap.dedent('''\
        """Core."""
        __version__ = "0.3.0"
    ''')
    ok = MODULE.scaffold_matches(Path("core/windagent_core/__init__.py"), current, "", info)
    assert not ok  # 0.3.0 is no longer accepted once migration has run


def test_scaffold_matches_requires_required_exports():
    info = {
        "namespace": "windagent_worker",
        "path": "apps/worker",
        "public_exports": {
            "required": {
                "TaskLeaseManager": "windagent_worker.lease",
                "ProductionWorker": "windagent_worker.runner",
            }
        },
    }
    current = textwrap.dedent('''\
        from windagent_core.version import PRODUCT_VERSION
        __version__ = PRODUCT_VERSION
    ''')
    ok = MODULE.scaffold_matches(Path("apps/worker/__init__.py"), current, "", info)
    assert not ok
