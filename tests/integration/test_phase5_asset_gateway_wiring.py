"""
VP3D Phase 5 — AssetResolverPort wiring integration tests.

Proves (Stage C Phase 5 acceptance, audit finding "AssetResolverPort not wired"):

1. The worker composition root registers the Universal Asset Gateway with the
   Phase 6 trust gate when enabled (WINDAGENT_ASSET_GATEWAY=1).
2. The durable production workflow's RENDER_ASSETS step resolves EVERY pending
   IR asset reference through the gateway (AssetResolverPort) — never via a
   direct Internet/Mesh/Blender call.
3. A QUARANTINED/REJECTED/failed asset resolution fails the step closed: the
   engine receives nothing until every pending asset is RESOLVED (approved).
4. The Director/workflow surface never imports the provider transport modules
   (checked structurally by tests/architecture/test_phase5_asset_gateway_
   architecture.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path


from windagent_core.domain.video_production.production_ir.models import (
    ProductionIrDocument,
)
from windagent_providers.assets import (
    AssetAdapterRegistry,
    AssetResolver,
    FakeInternetAssetAdapter,
    FakeLocalAssetAdapter,
    FakeMeshApiAdapter,
    FakeMeshMcpAdapter,
)
from windagent_tools.media_assets.trust_gate import MediaAssetTrustGate


def _fake_registry() -> AssetAdapterRegistry:
    registry = AssetAdapterRegistry()
    for adapter in (
        FakeLocalAssetAdapter(),
        FakeInternetAssetAdapter(),
        FakeMeshApiAdapter(),
        FakeMeshMcpAdapter(),
    ):
        registry.register(adapter)
    return registry


def _build_gateway() -> AssetResolver:
    return AssetResolver(_fake_registry(), trust=MediaAssetTrustGate())


def _ir_with_pending_asset(pending_uri: str) -> ProductionIrDocument:
    """IR whose character mesh is a pending (not-yet-acquired) asset."""

    from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

    ir = build_valid_ir()
    scene = ir.scenes[0]
    mesh = scene.characters[0].mesh.model_copy(update={"uri": pending_uri})
    character = scene.characters[0].model_copy(update={"mesh": mesh})
    scene2 = scene.model_copy(update={"characters": [character]})
    return ir.model_copy(update={"scenes": [scene2]})


def _step_executor_with_gateway(gateway, revision_to_ir):
    import tempfile

    from windagent_orchestration.production import (
        ProductionEngineExecutor,
        ProductionStepExecutor,
    )

    from tests.integration.test_phase2_workflow_engine_cutover import (
        RecordingEnginePort,
    )

    port = RecordingEnginePort(Path(tempfile.mkdtemp()))
    executor = ProductionEngineExecutor(port=port)
    return (
        ProductionStepExecutor(
            engine=executor,
            ir_source=revision_to_ir,
            asset_gateway=gateway,
        ),
        port,
    )


class TestCompositionRootWiring:
    def test_gateway_registered_when_enabled(self, tmp_path, monkeypatch):
        from apps.worker.windagent_worker.composition import WorkerContainer

        monkeypatch.setenv("WINDAGENT_ASSET_GATEWAY", "1")
        monkeypatch.setenv("WINDAGENT_ARTIFACT_ROOT", str(tmp_path))
        container = WorkerContainer(db_url="sqlite+aiosqlite:///:memory:")
        container._register_asset_gateway()

        assert container.asset_resolver is not None
        assert container.asset_trust_gate is not None
        # Port surface: discover/acquire/capabilities callable.
        assert callable(container.asset_resolver.discover)
        assert callable(container.asset_resolver.acquire)
        assert callable(container.asset_resolver.capabilities)
        # Capabilities include the local + internet adapters.
        ids = {c.provider_id for c in container.asset_resolver.capabilities()}
        assert "local.library" in ids
        assert "internet.search" in ids

    def test_gateway_not_registered_when_disabled(self, monkeypatch):
        from apps.worker.windagent_worker.composition import WorkerContainer

        monkeypatch.delenv("WINDAGENT_ASSET_GATEWAY", raising=False)
        container = WorkerContainer(db_url="sqlite+aiosqlite:///:memory:")
        assert container.asset_resolver is None


class TestRenderStepGoesThroughGateway:
    def test_pending_asset_resolved_via_gateway_before_submit(self):
        gateway = _build_gateway()
        ir = _ir_with_pending_asset("pending:hero-mesh")
        step_executor, port = _step_executor_with_gateway(
            gateway, lambda revision_id: ir
        )

        async def run():
            from windagent_orchestration.production import ProductionRun

            run_obj = ProductionRun(run_id="r", project_id="p", revision_id="rev", revision_hash="h" * 64)
            return await step_executor.async_execute("RENDER_ASSETS", run_obj)

        result = asyncio.run(run())
        # The pending character mesh resolves through the gateway (LICENSED
        # fake-local candidate -> APPROVE -> RESOLVED) and the step proceeds.
        assert result.status == "waiting_provider"
        assert port.submitted_scenes == ["scn_01"]
        assert result.pending_external_operation is not None

    def test_quarantined_asset_fails_step_closed(self, tmp_path):
        """An asset that cannot be trusted (UNKNOWN license) MUST NOT reach
        the engine: the step fails closed with no submission."""
        from windagent_providers.assets import LocalAssetAdapter

        library = tmp_path / "library"
        library.mkdir()
        (library / "hero.glb").write_bytes(b"hero mesh bytes")
        registry = AssetAdapterRegistry()
        registry.register(LocalAssetAdapter(library))
        gateway = AssetResolver(registry, trust=MediaAssetTrustGate())

        ir = _ir_with_pending_asset("pending:untrusted")
        step_executor, port = _step_executor_with_gateway(
            gateway, lambda revision_id: ir
        )

        async def run():
            from windagent_orchestration.production import ProductionRun

            run_obj = ProductionRun(run_id="r", project_id="p", revision_id="rev", revision_hash="h" * 64)
            return await step_executor.async_execute("RENDER_ASSETS", run_obj)

        result = asyncio.run(run())
        assert result.status == "failed"
        assert "asset gateway failed closed" in result.error
        assert port.submitted_scenes == [], "nothing may reach the engine"

    def test_gateway_error_fails_closed(self):
        class ExplodingGateway:
            async def discover(self, request):
                raise RuntimeError("transport down")

            async def acquire(self, candidate, request):
                raise RuntimeError("transport down")

            def capabilities(self):
                return []

        ir = _ir_with_pending_asset("pending:hero-mesh")
        step_executor, port = _step_executor_with_gateway(
            ExplodingGateway(), lambda revision_id: ir
        )

        async def run():
            from windagent_orchestration.production import ProductionRun

            run_obj = ProductionRun(run_id="r", project_id="p", revision_id="rev", revision_hash="h" * 64)
            return await step_executor.async_execute("RENDER_ASSETS", run_obj)

        result = asyncio.run(run())
        assert result.status == "failed"
        assert port.submitted_scenes == []

    def test_no_pending_assets_skips_gateway(self):
        """An IR with fully resolved (content-addressed) assets does not
        contact the gateway at all."""
        from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

        ir = build_valid_ir()  # all URIs are file:// (already acquired)
        calls = []

        class CountingGateway:
            async def discover(self, request):
                calls.append("discover")
                return type("R", (), {"candidates": []})()

            async def acquire(self, candidate, request):
                calls.append("acquire")

            def capabilities(self):
                return []

        step_executor, port = _step_executor_with_gateway(
            CountingGateway(), lambda revision_id: ir
        )

        async def run():
            from windagent_orchestration.production import ProductionRun

            run_obj = ProductionRun(run_id="r", project_id="p", revision_id="rev", revision_hash="h" * 64)
            return await step_executor.async_execute("RENDER_ASSETS", run_obj)

        result = asyncio.run(run())
        assert result.status == "waiting_provider"
        assert calls == []
