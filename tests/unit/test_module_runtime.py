"""Phase 4 tests: modules are declarative and bootstrap without app edits."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from windagent.platform.modules import (
    CommandRegistration,
    EventHandlerRegistration,
    InMemoryModuleRegistry,
    JobRegistration,
    ModuleConflictError,
    ModuleDiscoveryError,
    ModuleLoader,
    ModuleManifest,
    ModuleRuntime,
    PackageModuleDiscovery,
    QueryRegistration,
    StaticModuleDiscovery,
)


class CreateExample:
    pass


class FindExample:
    pass


class ExampleHandler:
    async def handle(self, value: object) -> object:
        return value


@dataclass
class RecordingRuntime:
    calls: list[str] = field(default_factory=list)

    def register_command(self, registration: CommandRegistration) -> None:
        self.calls.append(f"command:{registration.key}")

    def register_query(self, registration: QueryRegistration) -> None:
        self.calls.append(f"query:{registration.key}")

    def register_job(self, registration: JobRegistration) -> None:
        self.calls.append(f"job:{registration.job_type}")

    def register_event_handler(self, registration: EventHandlerRegistration) -> None:
        self.calls.append(f"event:{registration.event_type}")

    def register_router(self, module_id: str, router: object) -> None:
        self.calls.append(f"router:{module_id}:{router}")

    def register_migration(self, module_id: str, migration: object) -> None:
        self.calls.append(f"migration:{module_id}:{migration}")


def _manifest(module_id: str = "examples.sample") -> ModuleManifest:
    handler = ExampleHandler()
    return ModuleManifest(
        id=module_id,
        version="1.0.0",
        commands=(CommandRegistration(CreateExample, handler),),
        queries=(QueryRegistration(FindExample, handler),),
        jobs=(JobRegistration("examples.refresh", handler),),
        event_handlers=(EventHandlerRegistration("examples.created", handler),),
        routers=("example-router",),
        migrations=("0002_examples",),
        capabilities=("examples.read", "examples.write"),
    )


def test_manifest_normalizes_identity_and_exposes_only_a_stable_descriptor() -> None:
    manifest = _manifest(" examples.sample ")

    assert manifest.id == "examples.sample"
    assert manifest.descriptor.module_id == "examples.sample"
    assert manifest.descriptor.capabilities == ("examples.read", "examples.write")

    with pytest.raises(ValueError, match="duplicates"):
        ModuleManifest("examples.bad", "1.0.0", capabilities=("examples.read", "examples.read"))
    with pytest.raises(TypeError, match="commands must be a tuple"):
        ModuleManifest("examples.bad", "1.0.0", commands=[])  # type: ignore[arg-type]


def test_loader_registers_every_surface_in_the_canonical_bootstrap_order() -> None:
    runtime = RecordingRuntime()
    registry = InMemoryModuleRegistry()
    loader = ModuleLoader(registry, runtime)

    assert isinstance(runtime, ModuleRuntime)
    loaded = loader.bootstrap((StaticModuleDiscovery((_manifest(),)),))

    assert loaded[0].id == "examples.sample"
    assert runtime.calls == [
        "command:test_module_runtime.CreateExample",
        "query:test_module_runtime.FindExample",
        "job:examples.refresh",
        "event:examples.created",
        "router:examples.sample:example-router",
        "migration:examples.sample:0002_examples",
    ]
    assert registry.get("examples.sample") == loaded[0].descriptor
    assert registry.all() == (loaded[0].descriptor,)


def test_loader_validates_the_full_set_before_mutating_the_runtime() -> None:
    runtime = RecordingRuntime()
    registry = InMemoryModuleRegistry()
    loader = ModuleLoader(registry, runtime)
    duplicate = ModuleManifest(
        id="examples.conflict",
        version="1.0.0",
        commands=(CommandRegistration(CreateExample, ExampleHandler()),),
    )

    with pytest.raises(ModuleConflictError, match="command .*claimed"):
        loader.bootstrap((StaticModuleDiscovery((_manifest(), duplicate)),))

    assert runtime.calls == []
    assert registry.all() == ()


def test_package_discovery_finds_new_module_manifests_without_bootstrap_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "temporary_modules"
    feature_dir = package_root / "youtube_analytics"
    feature_dir.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (feature_dir / "__init__.py").write_text("", encoding="utf-8")
    (feature_dir / "manifest.py").write_text(
        "from windagent.platform.modules import ModuleManifest\n"
        "manifest = ModuleManifest('youtube.analytics', '1.0.0', capabilities=('youtube.read',))\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    discovered = PackageModuleDiscovery("temporary_modules").discover()

    assert tuple(manifest.id for manifest in discovered) == ("youtube.analytics",)
    sys.modules.pop("temporary_modules.youtube_analytics.manifest", None)
    sys.modules.pop("temporary_modules.youtube_analytics", None)
    sys.modules.pop("temporary_modules", None)


def test_package_discovery_rejects_a_manifest_module_without_a_manifest_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "bad_modules"
    feature_dir = package_root / "broken"
    feature_dir.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (feature_dir / "__init__.py").write_text("", encoding="utf-8")
    (feature_dir / "manifest.py").write_text("manifest = 'not-a-manifest'\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    with pytest.raises(ModuleDiscoveryError, match="must expose a ModuleManifest"):
        PackageModuleDiscovery("bad_modules").discover()

    sys.modules.pop("bad_modules.broken.manifest", None)
    sys.modules.pop("bad_modules.broken", None)
    sys.modules.pop("bad_modules", None)
