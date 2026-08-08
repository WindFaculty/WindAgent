"""
VP3D Phase 7 — Asset normalization domain tests (Stage C Phase 7).

Covers the canonical domain contracts:
- canonical metadata profile (meters, Z-up) and scale factors;
- hard-limit config bounds (texture resolution, polygons, VRAM) fail closed;
- VRAM estimate + BLOCKED decision semantics;
- LOD entries carry their own hash/metrics (source never overwritten);
- immutable bundle hash determinism;
- statuses/errors serialize without engine leaks.
"""

from __future__ import annotations

import pytest

from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    LodPolicy,
    NormalizationStatus,
    UnitSystem,
    UpAxis,
    VramDecision,
)
from windagent_core.domain.video_production.asset_normalization.errors import (
    AssetNormalizationError,
    VramBudgetExceededError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    AssetBundle,
    BundleFile,
    CanonicalMetadata,
    LodEntry,
    MeshValidationReport,
    NormalizationConfig,
    NormalizationRequest,
    NormalizationStage,
    NormalizedAsset,
    PreviewProfile,
    TextureInfo,
    VramEstimate,
)


class TestUnitSystems:
    def test_meters_per_unit_scale_factors(self):
        assert UnitSystem.METERS.meters_per_unit == 1.0
        assert UnitSystem.CENTIMETERS.meters_per_unit == 0.01
        assert UnitSystem.FEET.meters_per_unit == 0.3048
        assert UnitSystem.INCHES.meters_per_unit == 0.0254

    def test_canonical_metadata_detects_and_converts(self):
        meta = CanonicalMetadata(
            detected_unit=UnitSystem.CENTIMETERS,
            detected_up_axis=UpAxis.Y_UP,
        )
        assert meta.unit is UnitSystem.METERS
        assert meta.up_axis is UpAxis.Z_UP
        assert meta.scale_factor == 0.01
        assert meta.unit_converted is True
        assert meta.axis_converted is True


class TestNormalizationConfig:
    def test_defaults_match_canonical_profile(self):
        config = NormalizationConfig()
        assert config.target_unit is UnitSystem.METERS
        assert config.target_up_axis is UpAxis.Z_UP
        assert config.lod_policy is LodPolicy.SINGLE
        assert 64 <= config.max_texture_resolution <= 16384
        assert config.max_polygons >= 1
        assert config.max_vram_bytes >= 1

    def test_preview_profile_is_locked_deterministic(self):
        profile = PreviewProfile()
        assert profile.engine == "CYCLES"
        assert profile.device == "CPU"
        assert profile.samples >= 1
        assert profile.resolution == [profile.width, profile.height]

    def test_out_of_bounds_resolution_rejected(self):
        with pytest.raises(Exception):
            NormalizationConfig(max_texture_resolution=32768)


class TestVramEstimate:
    def test_within_budget_decision(self):
        vram = VramEstimate(
            geometry_bytes=1000,
            texture_bytes=2000,
            total_bytes=3000,
            hard_limit_bytes=4096,
        )
        assert vram.decision is VramDecision.WITHIN_BUDGET

    def test_blocked_decision(self):
        vram = VramEstimate(
            geometry_bytes=5000,
            texture_bytes=2000,
            total_bytes=7000,
            hard_limit_bytes=4096,
        )
        assert vram.decision is VramDecision.BLOCKED

    def test_texture_bytes_estimate(self):
        texture = TextureInfo(
            name="albedo",
            content_hash="0" * 64,
            width=1024,
            height=1024,
            bit_depth=8,
        )
        assert texture.bytes_estimate == 1024 * 1024 * 4 * 1


class TestLodEntries:
    def test_each_lod_carries_hash_and_metrics(self):
        lod = LodEntry(
            level=1,
            triangle_count=500,
            vertex_count=300,
            ratio=0.5,
            quality_score=0.9,
            content_hash="a" * 64,
            generated_by="fake",
        )
        assert lod.content_hash == "a" * 64
        assert 0.0 <= lod.quality_score <= 1.0

    def test_lod0_is_source_never_overwritten(self):
        lod0 = LodEntry(
            level=0, triangle_count=1000, vertex_count=600, ratio=1.0,
            content_hash="s" * 64, generated_by="source",
        )
        assert lod0.generated_by == "source"
        assert lod0.file_name == ""


class TestAssetBundleHash:
    def test_bundle_hash_deterministic_over_sorted_entries(self):
        a = BundleFile(path="b.txt", sha256="2" * 64, size_bytes=1)
        b = BundleFile(path="a.txt", sha256="1" * 64, size_bytes=1)
        h1 = AssetBundle.compute_hash([a, b])
        h2 = AssetBundle.compute_hash([b, a])
        assert h1 == h2  # order-independent

    def test_bundle_hash_changes_on_content_change(self):
        a = BundleFile(path="a.txt", sha256="1" * 64, size_bytes=1)
        h1 = AssetBundle.compute_hash([a])
        changed = BundleFile(path="a.txt", sha256="9" * 64, size_bytes=1)
        assert AssetBundle.compute_hash([changed]) != h1


class TestNormalizationStatuses:
    def test_blocked_asset_is_not_ready(self):
        result = NormalizedAsset(
            run_id="norm_1",
            source_content_hash="c" * 64,
            format=AssetFormat.GLTF,
            status=NormalizationStatus.BLOCKED,
        )
        assert result.ready is False
        assert result.bundle is None

    def test_ready_asset_is_ready(self):
        result = NormalizedAsset(
            run_id="norm_2",
            source_content_hash="d" * 64,
            format=AssetFormat.GLTF,
            status=NormalizationStatus.READY,
        )
        assert result.ready is True

    def test_errors_are_typed_and_carry_details(self):
        error = VramBudgetExceededError("vram over budget", details={"bytes": 999})
        assert isinstance(error, AssetNormalizationError)
        assert error.details == {"bytes": 999}


class TestSerialization:
    def test_mesh_report_round_trip(self):
        report = MeshValidationReport(
            ok=False,
            triangle_count=12,
            degenerate_faces=2,
            blocking_issues=["2 degenerate faces"],
        )
        data = report.model_dump(mode="json")
        restored = MeshValidationReport.model_validate(data)
        assert restored.triangle_count == 12
        assert restored.blocking_issues == ["2 degenerate faces"]

    def test_models_are_frozen(self):
        assert NormalizationRequest.model_config.get("frozen") is True
        assert NormalizedAsset.model_config.get("frozen") is True
        assert NormalizationStage.MESH.value == "MESH"
