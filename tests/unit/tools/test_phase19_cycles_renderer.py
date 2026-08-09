"""VP3D Phase 19 - Cycles production renderer acceptance tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from windagent_core.domain.video_production.production_ir.enums import IrAssetFormat
from windagent_tools.production_engines.blender import (
    ARTIFACT_CLASS_FINAL,
    ARTIFACT_CLASS_PREVIEW,
    CPU_FALLBACK_ALLOW,
    CPU_FALLBACK_DENY,
    DEVICE_AUTO,
    DEVICE_CPU,
    DEVICE_CUDA,
    DEVICE_OPTIX,
    DEVICE_VERDICT_CPU_FALLBACK_APPROVED,
    ENGINE_CYCLES,
    OUTPUT_EXR,
    OUTPUT_PNG,
    PROFILE_FINAL,
    PROFILE_FINAL_HIGH,
    PROFILE_PREVIEW,
    BlenderCyclesDeviceSelector,
    BlenderGpuDevice,
    BlenderCapabilityReport,
    BlenderRenderProfileCatalog,
    BlenderRenderProfileCompiler,
    ChunkRenderTelemetry,
    RenderArtifactPromotionError,
    RenderDevicePolicyError,
    RenderProfileCompileError,
    build_render_cache_key,
    ensure_artifact_promotion_allowed,
)
from tests.fixtures.video_production.ir_fixture_builder import build_valid_ir


def _intent(*, name=PROFILE_FINAL, output=IrAssetFormat.EXR, metadata=None):
    render = build_valid_ir().render_intents[0]
    profile_metadata = {"blender_profile": name, **(metadata or {})}
    profile = render.profile.model_copy(
        update={
            "engine_hint": "cycles",
            "output_format": output,
            "metadata": profile_metadata,
        }
    )
    return render.model_copy(update={"profile": profile})


def _capability(*device_types, error=""):
    return BlenderCapabilityReport(
        executable_path="blender",
        build="Blender 4.5.3" if not error else "",
        cycles_devices=[
            BlenderGpuDevice(name=f"device-{kind}", device_type=kind)
            for kind in device_types
        ],
        probe_error=error,
    )


class TestVersionedProfiles:
    def test_catalog_has_exact_profile_ladder(self):
        catalog = BlenderRenderProfileCatalog()
        assert catalog.names() == (PROFILE_PREVIEW, PROFILE_FINAL, PROFILE_FINAL_HIGH)
        assert all(catalog.get(name).settings_version == catalog.version for name in catalog.names())

    def test_final_defaults_to_cycles_with_full_settings(self):
        profile = BlenderRenderProfileCatalog().get(PROFILE_FINAL)
        assert profile.engine == ENGINE_CYCLES
        assert profile.artifact_class == ARTIFACT_CLASS_FINAL
        assert profile.adaptive_sampling and profile.denoise
        assert profile.bounce_budget.max_bounces > 0
        assert profile.resource_limits.texture_limit_px > 0
        assert profile.use_instancing
        assert profile.output_format == OUTPUT_EXR

    def test_preview_is_png_and_has_distinct_artifact_class(self):
        profile = BlenderRenderProfileCatalog().get(PROFILE_PREVIEW)
        assert profile.output_format == OUTPUT_PNG
        assert profile.artifact_class == ARTIFACT_CLASS_PREVIEW
        assert profile.profile_hash() != BlenderRenderProfileCatalog().get(PROFILE_FINAL).profile_hash()

    def test_compile_preserves_neutral_settings_and_pins_dependencies(self):
        intent = _intent(
            name=PROFILE_FINAL,
            output=IrAssetFormat.EXR,
            metadata={
                "adaptive_threshold": 0.025,
                "motion_blur": True,
                "dependency_hashes": {"camera": "cam-hash", "facial": "face-hash"},
                "seed": 99,
            },
        )
        compiled = BlenderRenderProfileCompiler().compile(intent, device=DEVICE_OPTIX)
        assert compiled.name == PROFILE_FINAL
        assert compiled.resolution == intent.profile.resolution
        assert compiled.fps == intent.profile.frame_rate
        assert compiled.samples == intent.profile.samples
        assert compiled.adaptive_threshold == 0.025
        assert compiled.output_format == OUTPUT_EXR and compiled.extension == "exr"
        assert compiled.seed == 99
        assert compiled.dependency_hashes == {"camera": "cam-hash", "facial": "face-hash"}

    def test_compile_is_deterministic(self):
        compiler = BlenderRenderProfileCompiler()
        first = compiler.compile(_intent(), device=DEVICE_CUDA)
        second = compiler.compile(_intent(), device=DEVICE_CUDA)
        assert first.to_dict() == second.to_dict()
        assert first.profile_hash() == second.profile_hash()

    def test_profile_json_contract_round_trips(self):
        compiled = BlenderRenderProfileCompiler().compile(
            _intent(name=PROFILE_FINAL_HIGH), device=DEVICE_OPTIX
        )
        restored = type(compiled).from_dict(compiled.to_dict())
        assert restored == compiled
        assert restored.profile_hash() == compiled.profile_hash()

    def test_eevee_hint_is_never_silently_accepted(self):
        intent = _intent()
        bad = intent.model_copy(
            update={"profile": intent.profile.model_copy(update={"engine_hint": "BLENDER_EEVEE_NEXT"})}
        )
        with pytest.raises(RenderProfileCompileError, match="never silently switches"):
            BlenderRenderProfileCompiler().compile(bad, device=DEVICE_CPU)

    def test_persistent_data_requires_measured_evidence(self):
        with pytest.raises(RenderProfileCompileError, match="evidence_hash"):
            BlenderRenderProfileCompiler().compile(
                _intent(metadata={"persistent_data": True}), device=DEVICE_CPU
            )
        compiled = BlenderRenderProfileCompiler().compile(
            _intent(
                metadata={
                    "persistent_data": True,
                    "persistent_data_evidence_hash": "measurement-hash",
                }
            ),
            device=DEVICE_CPU,
        )
        assert compiled.persistent_data
        assert compiled.persistent_data_evidence_hash == "measurement-hash"

    def test_invalid_adaptive_and_motion_blur_budgets_fail_closed(self):
        with pytest.raises(RenderProfileCompileError, match="adaptive_threshold"):
            BlenderRenderProfileCompiler().compile(
                _intent(metadata={"adaptive_threshold": 1.5}), device=DEVICE_CPU
            )
        with pytest.raises(RenderProfileCompileError, match="motion_blur_shutter"):
            BlenderRenderProfileCompiler().compile(
                _intent(metadata={"motion_blur_shutter": -0.1}), device=DEVICE_CPU
            )


class TestDevicePolicy:
    def test_auto_prefers_optix_then_cuda(self):
        selector = BlenderCyclesDeviceSelector()
        optix = selector.select(_capability(DEVICE_CUDA, DEVICE_OPTIX))
        assert optix.selected_device == DEVICE_OPTIX
        cuda = selector.select(_capability(DEVICE_CUDA))
        assert cuda.selected_device == DEVICE_CUDA

    def test_explicit_backend_does_not_switch_to_other_gpu(self):
        with pytest.raises(RenderDevicePolicyError, match="render blocked"):
            BlenderCyclesDeviceSelector().select(
                _capability(DEVICE_OPTIX),
                requested_device=DEVICE_CUDA,
                cpu_fallback_policy=CPU_FALLBACK_DENY,
            )

    def test_cpu_fallback_requires_explicit_allow_verdict(self):
        selector = BlenderCyclesDeviceSelector()
        with pytest.raises(RenderDevicePolicyError, match="CPU fallback"):
            selector.select(_capability(DEVICE_CPU), requested_device=DEVICE_AUTO)
        selected = selector.select(
            _capability(DEVICE_CPU),
            requested_device=DEVICE_AUTO,
            cpu_fallback_policy=CPU_FALLBACK_ALLOW,
        )
        assert selected.selected_device == DEVICE_CPU
        assert selected.fallback_used
        assert selected.verdict == DEVICE_VERDICT_CPU_FALLBACK_APPROVED

    def test_explicit_cpu_is_not_a_fallback(self):
        selected = BlenderCyclesDeviceSelector().select(
            _capability(), requested_device=DEVICE_CPU
        )
        assert selected.selected_device == DEVICE_CPU
        assert not selected.fallback_used

    def test_probe_failure_fails_closed(self):
        with pytest.raises(RenderDevicePolicyError, match="probe failed"):
            BlenderCyclesDeviceSelector().select(_capability(error="bad probe"))


class TestCacheAndPromotion:
    def _key(self, profile, **changes):
        values = {
            "scene_hash": "scene",
            "shot_hash": "shot",
            "frame_start": 1,
            "frame_end": 24,
            "profile": profile,
            "blender_version": "4.5.3",
            "device_class": profile.device,
        }
        values.update(changes)
        return build_render_cache_key(**values)

    def test_cache_key_pins_scene_shot_frame_profile_blender_device(self):
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_OPTIX)
        base = self._key(profile)
        assert self._key(profile, scene_hash="scene-2") != base
        assert self._key(profile, shot_hash="shot-2") != base
        assert self._key(profile, frame_end=25) != base
        assert self._key(profile, blender_version="4.5.4") != base
        assert self._key(profile, device_class=DEVICE_CUDA) != base

    def test_preview_and_final_never_share_a_key_or_promote(self):
        compiler = BlenderRenderProfileCompiler()
        preview = compiler.compile(
            _intent(name=PROFILE_PREVIEW, output=IrAssetFormat.PNG), device=DEVICE_OPTIX
        )
        final = compiler.compile(_intent(name=PROFILE_FINAL), device=DEVICE_OPTIX)
        assert self._key(preview) != self._key(final)
        with pytest.raises(RenderArtifactPromotionError, match="cannot be promoted"):
            ensure_artifact_promotion_allowed(preview, final)

    def test_identical_profile_identity_can_be_reused(self):
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_OPTIX)
        ensure_artifact_promotion_allowed(profile, profile)


class TestTelemetry:
    def test_chunk_telemetry_parses_frame_metrics_and_failure(self):
        telemetry = ChunkRenderTelemetry.from_dict(
            {
                "frame_start": 1,
                "frame_end": 2,
                "render_seconds": 1.25,
                "requested_device": "OPTIX",
                "actual_device": "OPTIX",
                "profile_hash": "profile",
                "cache_key": "cache",
                "peak_memory_mb": 512.0,
                "frames": [
                    {
                        "frame": 1,
                        "render_seconds": 0.5,
                        "samples": 128,
                        "peak_memory_mb": 500,
                        "device": "OPTIX",
                        "failure": "",
                    },
                    {
                        "frame": 2,
                        "render_seconds": 0.75,
                        "samples": 128,
                        "device": "OPTIX",
                        "failure": "render error",
                    },
                ],
            }
        )
        assert telemetry.actual_device == DEVICE_OPTIX
        assert telemetry.frames[0].samples == 128
        assert telemetry.frames[1].failure == "render error"
        assert telemetry.to_dict()["peak_memory_mb"] == 512.0


def _load_executor():
    path = (
        Path(__file__).resolve().parents[3]
        / "tools"
        / "windagent_tools"
        / "production_engines"
        / "blender"
        / "scripts"
        / "execute_job.py"
    )
    spec = importlib.util.spec_from_file_location("phase19_execute_job", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_bpy(*device_types):
    devices = [
        SimpleNamespace(type=kind, name=f"device-{kind}", use=False)
        for kind in device_types
    ]
    preferences = SimpleNamespace(
        compute_device_type="NONE",
        devices=devices,
        get_devices=lambda: devices,
    )
    image_settings = SimpleNamespace(
        file_format="PNG", color_depth="8", compression=0, exr_codec="NONE"
    )
    render = SimpleNamespace(
        engine="",
        resolution_x=0,
        resolution_y=0,
        resolution_percentage=0,
        fps=0,
        film_transparent=False,
        image_settings=image_settings,
        use_motion_blur=False,
        use_persistent_data=False,
        use_simplify=False,
        simplify_subdivision=0,
        simplify_texture_limit="0",
    )
    cycles = SimpleNamespace(
        device="CPU",
        samples=0,
        use_adaptive_sampling=False,
        adaptive_threshold=0.0,
        use_denoising=False,
        seed=0,
        max_bounces=0,
        diffuse_bounces=0,
        glossy_bounces=0,
        transmission_bounces=0,
        volume_bounces=0,
        transparent_max_bounces=0,
        debug_use_spatial_splits=False,
    )
    scene = SimpleNamespace(
        render=render,
        cycles=cycles,
        view_settings=SimpleNamespace(
            view_transform="Standard", look="None", exposure=0.0, gamma=1.0
        ),
    )
    return SimpleNamespace(
        context=SimpleNamespace(
            scene=scene,
            preferences=SimpleNamespace(
                addons={"cycles": SimpleNamespace(preferences=preferences)}
            ),
        ),
        ops=SimpleNamespace(
            preferences=SimpleNamespace(addon_enable=lambda module: None)
        ),
    )


class TestTrustedExecutorProfile:
    def test_applies_profile_and_records_actual_gpu(self, monkeypatch):
        executor = _load_executor()
        fake = _fake_bpy(DEVICE_CPU, DEVICE_OPTIX)
        monkeypatch.setitem(sys.modules, "bpy", fake)
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_OPTIX)
        actual = executor._configure_cycles_profile(profile.to_dict())
        assert actual == DEVICE_OPTIX
        assert fake.context.scene.render.engine == ENGINE_CYCLES
        assert fake.context.scene.cycles.device == "GPU"
        assert fake.context.scene.cycles.samples == profile.samples
        assert fake.context.scene.render.image_settings.file_format == OUTPUT_EXR
        assert [device.use for device in fake.context.preferences.addons["cycles"].preferences.devices] == [False, True]

    def test_actual_device_mismatch_fails_closed(self, monkeypatch):
        executor = _load_executor()
        fake = _fake_bpy(DEVICE_CPU)
        monkeypatch.setitem(sys.modules, "bpy", fake)
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_OPTIX)
        with pytest.raises(RuntimeError, match="actual-device mismatch"):
            executor._configure_cycles_profile(profile.to_dict())

    def test_unknown_profile_schema_fails_closed(self, monkeypatch):
        executor = _load_executor()
        monkeypatch.setitem(sys.modules, "bpy", _fake_bpy(DEVICE_CPU))
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_CPU)
        payload = profile.to_dict()
        payload["schema_version"] = "99.0"
        with pytest.raises(ValueError, match="unsupported render profile contract"):
            executor._configure_cycles_profile(payload)

    def test_manifest_identity_change_discards_reuse_entries(self, tmp_path):
        executor = _load_executor()
        (tmp_path / executor.FRAME_MANIFEST_FILENAME).write_text(
            '{"render_profile_hash":"preview","render_cache_key":"preview-key",'
            '"artifact_class":"PREVIEW","frames":[{"frame":1,"filename":"frame_0001.png"}]}',
            encoding="utf-8",
        )
        (tmp_path / "frame_0001.png").write_bytes(b"old-preview")
        executor._prepare_render_manifest(
            tmp_path,
            job_spec={
                "render_profile_hash": "final",
                "render_cache_key": "final-key",
            },
            profile={"artifact_class": "FINAL"},
            frame_start=1,
            frame_end=1,
            extension="exr",
            resolution={"width": 1920, "height": 1080},
        )
        manifest = executor._load_manifest(tmp_path)
        assert manifest["frames"] == []
        assert manifest["artifact_class"] == "FINAL"

    def test_profile_output_and_extension_conflict_fails_before_render(self, tmp_path):
        executor = _load_executor()
        profile = BlenderRenderProfileCompiler().compile(_intent(), device=DEVICE_CPU)
        rc = executor.run_render_chunk(
            tmp_path,
            "job",
            {
                "frame_start": 1,
                "frame_end": 1,
                "extension": "png",
                "render_profile": profile.to_dict(),
            },
        )
        assert rc == 1
        result = executor.read_job_spec(tmp_path)
        assert result is None
        payload = (tmp_path / executor.RESULT_FILENAME).read_text(encoding="utf-8")
        assert "conflicts with compiled render profile" in payload
