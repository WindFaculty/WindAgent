"""VP3D Phase 20 - VRAM budget manager acceptance tests.

Covers the five Phase 20 components (SceneResourceEstimator, VramBudgetPolicy,
TextureBudgetPolicy, GeometryBudgetPolicy, VramMitigationPlanner) plus the
adapter gate: estimate with recorded uncertainty, calibration against measured
peak memory, ordered mitigation with derived revisions and quality-impact
reports (no silent mutation), and block-before-launch with a recommendation.
"""

from __future__ import annotations

import asyncio

import pytest

from windagent_core.domain.video_production.production_ir.enums import EngineJobStatus
from windagent_tools.production_engines.blender import (
    MITIGATION_HIDDEN_GEOMETRY_REMOVAL,
    MITIGATION_INSTANCING,
    MITIGATION_LOD,
    MITIGATION_ORDER,
    MITIGATION_SPLIT_SHOT,
    MITIGATION_TEXTURE_DOWNSCALE,
    VRAM_BLOCK,
    VRAM_SAFE,
    VRAM_WARNING,
    BlenderCapabilityProbe,
    BlenderEngineAdapter,
    BlenderEngineConfig,
    BlenderGpuProbe,
    GeometryBudgetPolicy,
    MeshResource,
    RenderBufferSettings,
    SceneResourceEstimator,
    SceneResourceManifest,
    TextureBudgetPolicy,
    TextureResource,
    VramBudgetPolicy,
    VramMitigationPlanner,
    VolumeResource,
    ModifierResource,
)
from tests.unit.tools.test_phase3_blender_adapter import (
    FakeBlenderProcess,
    make_detector,
)
from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir

MI = 1024 * 1024


def _textures(count: int, size: int = 1024, visible: bool = True) -> tuple:
    return tuple(
        TextureResource(name=f"tex_{i}", width=size, height=size, visible=visible)
        for i in range(count)
    )


def _mesh(
    name: str,
    vertices: int = 1000,
    triangles: int = 2000,
    instances: int = 1,
    instanced: bool = False,
    visible: bool = True,
) -> MeshResource:
    return MeshResource(
        name=name,
        vertex_count=vertices,
        triangle_count=triangles,
        instance_count=instances,
        instanced=instanced,
        visible=visible,
    )


def _manifest(**kwargs) -> SceneResourceManifest:
    defaults = {
        "textures": _textures(2, 1024),
        "meshes": (_mesh("hero"),),
        "render_buffers": RenderBufferSettings(1920, 1080, pass_count=6, bytes_per_pixel=4),
    }
    defaults.update(kwargs)
    return SceneResourceManifest(**defaults)


class TestSceneResourceEstimator:
    def test_texture_footprint_with_mipmap_chain(self):
        manifest = _manifest(textures=_textures(1, 1024), meshes=(), volumes=(), modifiers=())
        estimate = SceneResourceEstimator().estimate(manifest)
        # 1024*1024 px * 4 ch * 1 B * 4/3 mip chain = 5.33 MB
        item = next(i for i in estimate.items if i.category == "textures")
        assert item.estimated_mb == pytest.approx(5.33, abs=0.01)
        assert item.method == "computed"

    def test_geometry_and_acceleration_structures(self):
        manifest = _manifest(
            meshes=(_mesh("hero", 1_000_000, 2_000_000),), textures=(), volumes=(), modifiers=()
        )
        estimate = SceneResourceEstimator().estimate(manifest)
        geometry = next(i for i in estimate.items if i.category == "geometry")
        accel = next(i for i in estimate.items if i.category == "acceleration_structures")
        # 1M verts * 32 B / MiB = 30.52 MB; 2M tris * 64 B / MiB = 122.07 MB
        assert geometry.estimated_mb == pytest.approx(30.52, abs=0.01)
        assert accel.estimated_mb == pytest.approx(122.07, abs=0.01)

    def test_instancing_removes_duplicate_geometry(self):
        duplicated = _manifest(meshes=(_mesh("crowd", instances=100),), textures=(), volumes=(), modifiers=())
        instanced = _manifest(
            meshes=(_mesh("crowd", instances=100, instanced=True),), textures=(), volumes=(), modifiers=()
        )
        dup_estimate = SceneResourceEstimator().estimate(duplicated)
        inst_estimate = SceneResourceEstimator().estimate(instanced)
        dup_geometry = next(i for i in dup_estimate.items if i.category == "geometry").estimated_mb
        inst_geometry = next(i for i in inst_estimate.items if i.category == "geometry").estimated_mb
        assert inst_geometry < dup_geometry
        # 100 copies -> 100 * 32 KB = 3.05 MB; instanced -> 32 KB + 100 * 64 B
        assert dup_geometry == pytest.approx(3.05, abs=0.01)
        assert inst_geometry == pytest.approx(0.0366, abs=0.01)

    def test_volumes_render_buffers_and_modifiers(self):
        manifest = _manifest(
            textures=(),
            meshes=(),
            volumes=(VolumeResource(name="smoke", grid_resolution=64),),
            modifiers=(ModifierResource(name="hair", kind="PARTICLES", estimated_extra_mb=256.0),),
        )
        estimate = SceneResourceEstimator().estimate(manifest)
        volumes = next(i for i in estimate.items if i.category == "volumes")
        buffers = next(i for i in estimate.items if i.category == "render_buffers")
        modifiers = next(i for i in estimate.items if i.category == "modifiers")
        assert volumes.estimated_mb == pytest.approx(1.0, abs=0.01)
        assert buffers.estimated_mb == pytest.approx(1920 * 1080 * 6 * 4 / MI, abs=0.01)
        assert modifiers.estimated_mb == 256.0
        assert modifiers.method == "explicit"

    def test_every_category_records_uncertainty(self):
        estimate = SceneResourceEstimator().estimate(_manifest())
        assert len(estimate.items) == 6
        for item in estimate.items:
            # Uncertainty is recorded whenever there is an estimate at all;
            # a category with zero footprint has zero uncertainty.
            if item.estimated_mb > 0.0:
                assert item.uncertainty_mb > 0.0
        assert estimate.total_mb > 0.0
        assert estimate.uncertainty_mb > 0.0

    def test_manifest_round_trip_keeps_revision_hash(self):
        manifest = _manifest()
        restored = SceneResourceManifest.from_dict(manifest.to_dict())
        assert restored == manifest
        assert restored.revision_hash() == manifest.revision_hash()


class TestVramBudgetPolicy:
    def test_default_thresholds_match_plan_baseline(self):
        policy = VramBudgetPolicy()
        assert policy.safe_threshold_gb == 6.0
        assert policy.block_threshold_gb == 7.0

    def test_thresholds_must_be_sane(self):
        with pytest.raises(ValueError, match="safe < block"):
            VramBudgetPolicy(safe_threshold_gb=8.0, block_threshold_gb=7.0)

    def test_classify_boundaries(self):
        policy = VramBudgetPolicy()
        from windagent_tools.production_engines.blender import SceneResourceEstimate

        def estimate(mb: float) -> SceneResourceEstimate:
            return SceneResourceEstimate(items=(), total_mb=mb, uncertainty_mb=0.0)

        assert policy.classify(estimate(5.9 * 1024)) == VRAM_SAFE
        assert policy.classify(estimate(6.5 * 1024)) == VRAM_WARNING
        assert policy.classify(estimate(7.1 * 1024)) == VRAM_BLOCK

    def test_calibration_against_measured_peak_memory(self):
        policy = VramBudgetPolicy()
        calibrated = policy.calibrate(fixture="hero_scene", estimated_mb=5000, measured_mb=5500)
        assert calibrated.safety_factor == pytest.approx(1.1)
        assert len(calibrated.calibration_records) == 1
        # Original policy untouched (immutable).
        assert policy.safety_factor == 1.0
        # Verdict now uses the calibrated total: 5000 MB * 1.1 = 5500 MB.
        from windagent_tools.production_engines.blender import SceneResourceEstimate

        estimate = SceneResourceEstimate(items=(), total_mb=5000, uncertainty_mb=0.0)
        assert calibrated.classify(estimate) == VRAM_SAFE

    def test_multiple_calibration_records_average_the_factor(self):
        policy = VramBudgetPolicy().calibrate("a", 1000, 1100).calibrate("b", 1000, 1300)
        assert len(policy.calibration_records) == 2
        assert policy.safety_factor == pytest.approx(1.2)


class TestMitigationPolicies:
    def test_texture_downscale_halves_dimensions(self):
        manifest = _manifest(textures=_textures(2, 4096), meshes=(), volumes=(), modifiers=())
        derived, impacts = TextureBudgetPolicy().apply(manifest)
        assert derived.textures[0].width == 2048
        assert derived.textures[0].height == 2048
        assert manifest.textures[0].width == 4096  # original untouched
        assert len(impacts) == 2
        assert all(i.impact == MITIGATION_TEXTURE_DOWNSCALE for i in impacts)

    def test_lod_reduces_geometry(self):
        manifest = _manifest(meshes=(_mesh("hero", 1_000_000, 2_000_000),), textures=(), volumes=(), modifiers=())
        derived, impacts = GeometryBudgetPolicy().apply_lod(manifest)
        assert derived.meshes[0].vertex_count == 500_000
        assert derived.meshes[0].triangle_count == 1_000_000
        assert impacts[0].severity == "MEDIUM"

    def test_instancing_marks_duplicates(self):
        manifest = _manifest(
            meshes=(_mesh("crowd", instances=50), _mesh("hero")), textures=(), volumes=(), modifiers=()
        )
        derived, impacts = GeometryBudgetPolicy().apply_instancing(manifest)
        assert derived.meshes[0].instanced
        assert not derived.meshes[1].instanced
        assert len(impacts) == 1

    def test_hidden_geometry_removal_drops_invisible_resources(self):
        manifest = _manifest(
            textures=_textures(1, 1024, visible=False),
            meshes=(_mesh("hidden", visible=False), _mesh("hero")),
            volumes=(),
            modifiers=(),
        )
        derived, impacts = GeometryBudgetPolicy().apply_hidden_geometry_removal(manifest)
        assert len(derived.textures) == 0
        assert len(derived.meshes) == 1
        assert impacts[0].impact == MITIGATION_HIDDEN_GEOMETRY_REMOVAL


class TestVramMitigationPlanner:
    def test_safe_and_warning_manifests_need_no_mitigation(self):
        planner = VramMitigationPlanner()
        safe = planner.plan(_manifest(), VramBudgetPolicy())  # ~53 MB -> SAFE
        assert safe.blocked is False
        assert safe.steps == ()
        assert safe.final_verdict == VRAM_SAFE

    def test_blocked_manifest_runs_full_ordered_chain(self):
        planner = VramMitigationPlanner()
        # Modifiers are explicit estimates NO mitigation step reduces, so the
        # full chain must run and the final verdict stays BLOCK.
        manifest = _manifest(
            textures=_textures(2, 1024),
            modifiers=(ModifierResource(name="hair", kind="PARTICLES", estimated_extra_mb=8000.0),),
        )
        policy = VramBudgetPolicy()
        decision = planner.plan(manifest, policy)
        assert decision.original_verdict == VRAM_BLOCK
        names = [step.name for step in decision.steps]
        assert names == [
            MITIGATION_TEXTURE_DOWNSCALE,
            MITIGATION_LOD,
            MITIGATION_INSTANCING,
            MITIGATION_HIDDEN_GEOMETRY_REMOVAL,
            MITIGATION_SPLIT_SHOT,
        ]
        assert names == list(MITIGATION_ORDER)
        # Every step: derived revision, quality impacts, verdict recorded.
        for step in decision.steps:
            assert step.revision_hash
            assert step.verdict_after in (VRAM_SAFE, VRAM_WARNING, VRAM_BLOCK)
        assert decision.final_estimate.total_mb <= decision.original_estimate.total_mb

    def test_mitigation_stops_as_soon_as_below_block(self):
        planner = VramMitigationPlanner()
        # 96 x 2048^2 = 2.1 GB -> texture downscale 0.5 -> 512 MB < 1.0 GB SAFE.
        manifest = _manifest(textures=_textures(96, 2048))
        policy = VramBudgetPolicy(safe_threshold_gb=1.0, block_threshold_gb=1.5)
        decision = planner.plan(manifest, policy)
        assert [step.name for step in decision.steps] == [MITIGATION_TEXTURE_DOWNSCALE]
        assert decision.final_verdict == VRAM_SAFE
        assert decision.blocked is False

    def test_no_silent_mutation_original_manifest_unchanged(self):
        manifest = _manifest(
            textures=_textures(96, 2048),
            modifiers=(ModifierResource(name="hair", kind="PARTICLES", estimated_extra_mb=8000.0),),
        )
        original_hash = manifest.revision_hash()
        original_textures = manifest.textures
        decision = VramMitigationPlanner().plan(manifest, VramBudgetPolicy())
        assert manifest.revision_hash() == original_hash
        assert manifest.textures == original_textures
        assert decision.steps
        # Derived revisions differ from the original.
        for step in decision.steps:
            assert step.revision_hash != original_hash

    def test_blocked_after_full_chain_yields_recommendation(self):
        planner = VramMitigationPlanner()
        manifest = _manifest(
            textures=_textures(2, 1024),
            modifiers=(ModifierResource(name="hair", kind="PARTICLES", estimated_extra_mb=8000.0),),
        )
        policy = VramBudgetPolicy()
        decision = planner.plan(manifest, policy)
        assert decision.final_verdict == VRAM_BLOCK
        assert decision.blocked is True
        assert len(decision.steps) == 5
        assert "blocked before launch" in decision.recommendation
        assert "hard limit" in decision.recommendation

    def test_split_shot_reduces_peak_concurrent_geometry(self):
        planner = VramMitigationPlanner()
        manifest = SceneResourceManifest(
            meshes=(_mesh("crowd", vertices=5_000_000, triangles=10_000_000, instances=20),),
            textures=(),
            volumes=(),
            modifiers=(),
            render_buffers=RenderBufferSettings(0, 0),
        )
        derived, impacts = planner._split_shot(manifest)
        assert impacts[0].impact == MITIGATION_SPLIT_SHOT
        assert "2 segments" in impacts[0].detail
        assert derived.metadata.get("split_shot_segments") == 2


class TestAdapterVramGate:
    def make_adapter(self, tmp_path, fake_process, policy):
        fake_exe = tmp_path / "fake_blender" / "blender.exe"
        fake_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_exe.write_bytes(b"MZ")
        config = BlenderEngineConfig(
            artifact_root=str(tmp_path / "artifacts"),
            state_dir=str(tmp_path / "state"),
            executable_path=str(fake_exe),
            vram_budget_policy=policy,
            default_timeout_seconds=30.0,
            heartbeat_seconds=0.05,
            cancel_grace_seconds=0.1,
        )
        return BlenderEngineAdapter(
            config=config,
            detector=make_detector(str(fake_exe), fake_process._version),
            capability_probe=BlenderCapabilityProbe(process_port=fake_process),
            gpu_probe=BlenderGpuProbe(),
            process_port=fake_process,
        )

    def _render_with_manifest(self, manifest: SceneResourceManifest):
        render = build_valid_ir().render_intents[0]
        return render.model_copy(
            update={"metadata": {"resource_manifest": manifest.to_dict()}}
        )

    def test_blocked_render_never_launches(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            # Hard limit 0.5 GB: 128 x 2048^2 (2.7 GB) survives downscale at
            # ~683 MB + 47 MB render buffers -> still > 512 MB -> BLOCK.
            policy = VramBudgetPolicy(safe_threshold_gb=0.2, block_threshold_gb=0.5)
            adapter = self.make_adapter(tmp_path, fake, policy)
            manifest = _manifest(textures=_textures(128, 2048))
            receipt = await adapter.submit_scene(
                build_valid_ir().scenes[0], self._render_with_manifest(manifest)
            )
            assert receipt.status == EngineJobStatus.FAILED
            assert "vram budget gate" in (receipt.error or "")
            assert "blocked before launch" in (receipt.error or "")
            assert receipt.metadata.get("gate") == "vram_budget"
            decision = receipt.metadata["vram_budget_decision"]
            assert decision["final_verdict"] == VRAM_BLOCK
            launched = [
                a for a in (fake.started or []) if "--python" in a and "--python-expr" not in a
            ]
            assert not launched, "vram gate must block BEFORE process launch"

        asyncio.run(_go())

    def test_small_scene_passes_gate_and_renders(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            policy = VramBudgetPolicy(safe_threshold_gb=0.2, block_threshold_gb=0.5)
            adapter = self.make_adapter(tmp_path, fake, policy)
            manifest = _manifest(textures=_textures(2, 256))
            receipt = await adapter.submit_scene(
                build_valid_ir().scenes[0], self._render_with_manifest(manifest)
            )
            assert receipt.status == EngineJobStatus.COMPLETED
            assert receipt.metadata.get("gate") is None
            decision = receipt.metadata["vram_budget_decision"]
            assert decision["final_verdict"] == VRAM_SAFE

        asyncio.run(_go())

    def test_no_policy_means_no_gate(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            adapter = self.make_adapter(tmp_path, fake, None)
            render = self._render_with_manifest(_manifest(textures=_textures(128, 2048)))
            receipt = await adapter.submit_scene(build_valid_ir().scenes[0], render)
            assert receipt.status == EngineJobStatus.COMPLETED
            assert receipt.metadata.get("vram_budget_decision") is None

        asyncio.run(_go())

    def test_manifest_from_scene_metadata_fallback(self, tmp_path):
        async def _go():
            fake = FakeBlenderProcess(blender_version="Blender 4.5.3")
            policy = VramBudgetPolicy(safe_threshold_gb=0.2, block_threshold_gb=0.5)
            adapter = self.make_adapter(tmp_path, fake, policy)
            scene = build_valid_ir().scenes[0]
            manifest = _manifest(textures=_textures(128, 2048))
            scene = scene.model_copy(
                update={"metadata": {"resource_manifest": manifest.to_dict()}}
            )
            receipt = await adapter.submit_scene(scene, build_valid_ir().render_intents[0])
            assert receipt.status == EngineJobStatus.FAILED
            assert receipt.metadata.get("gate") == "vram_budget"

        asyncio.run(_go())
