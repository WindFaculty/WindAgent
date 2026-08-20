"""Phase 8 — focused Worker composition and typed runtime settings.

Gates:
- the monolithic ``composition.py`` is replaced by an import-compatible
  package of focused composers and every
  existing import path keeps working;
- ``WorkerRuntimeSettings`` is a frozen typed snapshot with strict boolean
  parsing (unset -> default, 1/true/yes/on, 0/false/no/off, anything else
  raises a clear settings error);
- settings dependency validation runs before any DB/background-task mutation
  (provider routing requires Studio runtime; asset normalizer requires asset
  gateway);
- no environment reads exist outside ``settings.py`` in the composition
  package;
- ``capability_manifest()`` is side-effect-free, exactly shaped, JSON
  serializable and honest;
- a file-backed SQLite bootstrap returns the manifest and repeated calls are
  idempotent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER_PACKAGE = ROOT / "apps" / "worker" / "windagent_worker"
COMPOSITION_DIR = WORKER_PACKAGE / "composition"
REQUIRED_COMPOSITION_MODULES = {
    "__init__.py",
    "settings.py",
    "core.py",
    "queue.py",
    "providers.py",
    "studio.py",
    "video.py",
    "assets.py",
    "outbox.py",
    "container.py",
}

_ALL_ENV_NAMES = (
    "WINDAGENT_DATABASE_URL",
    "WINDAGENT_FAKE_RUNTIME",
    "WINDAGENT_STUDIO_RUNTIME",
    "WINDAGENT_STUDIO_MODEL_ROUTE",
    "WINDAGENT_STUDIO_CANONICAL_MODEL",
    "WINDAGENT_BLENDER_ENGINE",
    "WINDAGENT_ASSET_GATEWAY",
    "WINDAGENT_ASSET_NORMALIZER",
    "WINDAGENT_ARTIFACT_ROOT",
    "WINDAGENT_ASSET_LIBRARY_ROOT",
    "WINDAGENT_BLENDER_EXECUTABLE",
    "WINDAGENT_CERTIFICATION_MODE",
    "WIND_STUDIO_CERTIFICATION",
)


def _clear_worker_env(monkeypatch) -> None:
    for name in _ALL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _composition_source_files() -> list[Path]:
    return sorted(COMPOSITION_DIR.rglob("*.py"))


def _composition_source_text() -> str:
    parts = []
    for path in _composition_source_files():
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


# ── package / import compatibility ──────────────────────────────────────────


def test_composition_package_modules_exist():
    assert COMPOSITION_DIR.is_dir(), "composition package directory missing"
    present = {p.name for p in COMPOSITION_DIR.rglob("*.py")}
    missing = REQUIRED_COMPOSITION_MODULES - present
    assert not missing, f"required composition modules missing: {sorted(missing)}"


def test_legacy_composition_module_removed():
    assert not (WORKER_PACKAGE / "composition.py").exists(), (
        "monolithic composition.py must be replaced by the package"
    )


def test_compatibility_import_works():
    from windagent_worker.composition import (
        CertificationPreflightError,
        WorkerContainer,
        WorkerRuntimeSettings,
    )

    assert WorkerContainer.__name__ == "WorkerContainer"
    assert WorkerRuntimeSettings.__name__ == "WorkerRuntimeSettings"
    assert issubclass(CertificationPreflightError, RuntimeError)


def test_container_module_holds_implementation():
    from windagent_worker.composition import WorkerContainer
    from windagent_worker.composition.container import (
        WorkerContainer as ContainerWorkerContainer,
    )

    assert ContainerWorkerContainer is WorkerContainer


def test_container_only_orchestrates_focused_composers():
    source = (COMPOSITION_DIR / "container.py").read_text(encoding="utf-8")
    for composer in (
        "CoreComposer",
        "QueueComposer",
        "ProviderComposer",
        "StudioComposer",
        "OutboxComposer",
        "VideoComposer",
        "AssetComposer",
    ):
        assert composer in source, f"container does not orchestrate {composer}"

    for concrete in (
        "DatabaseManager",
        "ExecutionRuntimeRegistry",
        "SqlDurableTaskQueue",
        "OutboxEventPublisher",
        "CanonicalModelRegistryService",
        "EndpointExecutionCoordinator",
        "StudioRuntimeAdapter",
        "create_blender_engine_adapter",
        "AssetResolver(",
        "AssetNormalizer(",
    ):
        assert concrete not in source, f"container constructs {concrete} directly"


def test_concrete_capabilities_live_in_their_focused_modules():
    ownership = {
        "core.py": ("DatabaseManager", "ExecutionRuntimeRegistry"),
        "queue.py": ("SqlDurableTaskQueue", "DurableTaskLeaseManager"),
        "providers.py": ("CanonicalModelRegistryService", "RouteLockService"),
        "studio.py": ("EndpointExecutionCoordinator", "StudioRuntimeAdapter"),
        "video.py": ("create_blender_engine_adapter", "ProductionWorkflowEngine"),
        "assets.py": ("AssetResolver", "AssetNormalizer"),
        "outbox.py": ("OutboxEventPublisher", "SqlOutboxRepository"),
    }
    for filename, symbols in ownership.items():
        source = (COMPOSITION_DIR / filename).read_text(encoding="utf-8")
        for symbol in symbols:
            assert symbol in source, f"{symbol} missing from {filename}"


def test_worker_is_the_single_outbox_publisher_owner():
    worker_source = _composition_source_text()
    api_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "apps" / "api" / "windagent_api").rglob("*.py")
    )
    assert worker_source.count("OutboxEventPublisher(") == 1
    assert "OutboxEventPublisher" not in api_source


def test_canonical_module_path_preserved():
    """Runtime/attestation code keys on the canonical module path."""
    from windagent_worker.composition import WorkerContainer

    assert WorkerContainer.__module__ == "windagent_worker.composition"


def test_runner_and_main_imports_unchanged():
    runner_source = (WORKER_PACKAGE / "runner.py").read_text(encoding="utf-8")
    main_source = (WORKER_PACKAGE / "__main__.py").read_text(encoding="utf-8")
    assert "from windagent_worker.composition import WorkerContainer" in runner_source
    assert "from windagent_worker.composition import WorkerContainer" in main_source


# ── typed settings parsing ──────────────────────────────────────────────────


def test_settings_defaults(monkeypatch):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment(
        default_db_url="sqlite+aiosqlite:///default.db"
    )
    assert settings.database_url == "sqlite+aiosqlite:///default.db"
    assert settings.fake_runtime is False
    assert settings.studio_runtime is False
    assert settings.studio_model_route is False
    assert settings.studio_canonical_model == ""
    assert settings.blender_engine is False
    assert settings.asset_gateway is False
    assert settings.asset_normalizer is False
    assert settings.artifact_root == "artifacts"
    assert settings.asset_library_root == "data/assets/library"
    assert settings.blender_executable == ""
    assert settings.certification_enabled is False
    assert settings.certification_conflict is False
    assert settings.provider_routing is False


def test_settings_database_url_env_overrides_default(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_DATABASE_URL", "sqlite+aiosqlite:///env.db")
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment(
        default_db_url="sqlite+aiosqlite:///default.db"
    )
    assert settings.database_url == "sqlite+aiosqlite:///env.db"


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", " TRUE ", "Yes", "ON"])
def test_settings_true_parsing(monkeypatch, value):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", value)
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment()
    assert settings.studio_runtime is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " FALSE ", "No"])
def test_settings_false_parsing(monkeypatch, value):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", value)
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment()
    assert settings.studio_runtime is False


@pytest.mark.parametrize("value", ["banana", "2", "maybe", "enabled", "1.0"])
def test_settings_invalid_bool_raises(monkeypatch, value):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_FAKE_RUNTIME", value)
    from windagent_worker.composition import WorkerRuntimeSettings, WorkerSettingsError

    with pytest.raises(WorkerSettingsError, match="Invalid boolean value"):
        WorkerRuntimeSettings.from_environment()


def test_settings_empty_string_means_unset(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_FAKE_RUNTIME", "")
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment()
    assert settings.fake_runtime is False


def test_settings_are_frozen(monkeypatch):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerRuntimeSettings

    settings = WorkerRuntimeSettings.from_environment()
    with pytest.raises(Exception):
        settings.fake_runtime = True  # type: ignore[misc]


def test_certification_legacy_alias_and_conflict(monkeypatch):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerRuntimeSettings

    # Legacy alias alone enables certification.
    monkeypatch.setenv("WIND_STUDIO_CERTIFICATION", "1")
    settings = WorkerRuntimeSettings.from_environment()
    assert settings.certification_enabled is True
    assert settings.certification_conflict is False

    # Canonical flag wins over a stale legacy flag.
    monkeypatch.setenv("WINDAGENT_CERTIFICATION_MODE", "0")
    settings = WorkerRuntimeSettings.from_environment()
    assert settings.certification_enabled is False
    assert settings.certification_conflict is True


# ── dependency validation before bootstrap ──────────────────────────────────


def test_provider_routing_requires_studio_runtime(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    from windagent_worker.composition import WorkerContainer, WorkerSettingsError

    container = WorkerContainer()
    with pytest.raises(WorkerSettingsError, match="WINDAGENT_STUDIO_RUNTIME=1"):
        container.validate_settings()


def test_asset_normalizer_requires_asset_gateway(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_ASSET_NORMALIZER", "1")
    from windagent_worker.composition import WorkerContainer, WorkerSettingsError

    container = WorkerContainer()
    with pytest.raises(WorkerSettingsError, match="WINDAGENT_ASSET_GATEWAY=1"):
        container.validate_settings()


@pytest.mark.asyncio
async def test_bootstrap_validates_before_db_mutation(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_ASSET_NORMALIZER", "1")
    from windagent_worker.composition import WorkerContainer, WorkerSettingsError

    container = WorkerContainer()
    with pytest.raises(WorkerSettingsError):
        await container.bootstrap()
    assert container.db is None, "bootstrap must fail before DB creation"
    assert container.is_initialized is False


# ── no environment reads outside settings.py ────────────────────────────────


def test_only_settings_reads_environment():
    for path in _composition_source_files():
        source = path.read_text(encoding="utf-8")
        if path.name == "settings.py":
            assert "os.getenv" in source
            continue
        assert "os.getenv" not in source, f"{path.name} reads os.getenv"
        assert "os.environ" not in source, f"{path.name} reads os.environ"
        assert "environ[" not in source, f"{path.name} reads environ"


def test_container_does_not_reread_certification_environment():
    container_source = (COMPOSITION_DIR / "container.py").read_text(
        encoding="utf-8"
    )
    assert "certification_mode_enabled" not in container_source
    assert "certification_mode_conflict" not in container_source
    assert "WINDAGENT_CERTIFICATION_MODE" not in container_source
    assert "WIND_STUDIO_CERTIFICATION" not in container_source


# ── capability manifest ─────────────────────────────────────────────────────


def test_capability_manifest_exact_shape(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    monkeypatch.setenv("WINDAGENT_BLENDER_ENGINE", "1")
    monkeypatch.setenv("WINDAGENT_ASSET_GATEWAY", "1")
    from windagent_worker.composition import WorkerContainer

    container = WorkerContainer()
    manifest = container.capability_manifest()
    assert manifest == {
        "studio": True,
        "provider_routing": True,
        "blender": True,
        "asset_gateway": True,
    }
    # JSON serializable.
    json.dumps(manifest)


def test_capability_manifest_honesty(monkeypatch):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerContainer

    container = WorkerContainer()
    assert container.capability_manifest() == {
        "studio": False,
        "provider_routing": False,
        "blender": False,
        "asset_gateway": False,
    }
    # The manifest is honest about configuration even before bootstrap.
    assert container.is_initialized is False


def test_capability_manifest_is_side_effect_free(monkeypatch):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerContainer

    container = WorkerContainer()
    before = dict(container.__dict__)
    container.capability_manifest()
    assert container.__dict__ == before


def test_manifest_provider_routing_requires_studio_runtime(monkeypatch):
    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    monkeypatch.setenv("WINDAGENT_STUDIO_RUNTIME", "1")
    from windagent_worker.composition import WorkerContainer

    container = WorkerContainer()
    assert container.capability_manifest()["provider_routing"] is True

    _clear_worker_env(monkeypatch)
    monkeypatch.setenv("WINDAGENT_STUDIO_MODEL_ROUTE", "1")
    container = WorkerContainer()
    assert container.capability_manifest()["provider_routing"] is False


# ── file-backed bootstrap ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_backed_bootstrap_returns_manifest_and_is_idempotent(
    tmp_path, monkeypatch
):
    _clear_worker_env(monkeypatch)
    from windagent_worker.composition import WorkerContainer

    db_path = tmp_path / "phase8_bootstrap.db"
    container = WorkerContainer(db_url=f"sqlite+aiosqlite:///{db_path}")
    manifest = await container.bootstrap()
    assert manifest == container.capability_manifest()
    assert container.is_initialized
    assert container.db is not None
    assert container.lease_manager is not None
    assert container.execution_registry is not None

    # Repeated idempotent call returns the same manifest without re-bootstrapping.
    manifest2 = await container.bootstrap()
    assert manifest2 == manifest
    assert container.is_initialized

    await container.shutdown()
    assert container.is_initialized is False
