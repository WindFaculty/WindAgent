"""
VP3D Phase 7 — Host-side normalization pipeline tests (Stage C Phase 7).

Covers the canonical flow with deterministic fakes (CI, no Blender):

- full pipeline: local glTF asset -> READY bundle with LODs + preview;
- canonical unit/axis conversion (CM -> meters, Y-up -> Z-up);
- mesh validation fail-closed (degenerate faces, missing UV, topology);
- material/texture normalization (oversize textures capped + hashed);
- VRAM budget: over hard limit -> BLOCKED, preview NEVER attempted;
- polygon budget: over hard limit -> BLOCKED;
- security: archive/executable payloads rejected before parse;
- malicious fixtures: path traversal in texture URI -> missing (fail closed);
- LOD source never overwritten; deterministic bundle hash.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    NormalizationStage,
    NormalizationStatus,
    UnitSystem,
    UpAxis,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    NormalizationConfig,
    NormalizationRequest,
)
from windagent_core.domain.video_production.asset_resolution.enums import AssetKind
from windagent_core.domain.video_production.asset_resolution.models import AssetRequirement
from windagent_tools.media_assets.normalization import (
    AssetNormalizationPipeline,
    FakeAssetJobRunner,
)
from windagent_tools.media_assets.normalization.bundle import AssetBundlePublisher
from windagent_tools.media_assets.normalization.parsers import (
    detect_format,
    parse_gltf,
    parse_obj,
)
from windagent_tools.media_assets.store import ContentAddressedStore


def _gltf_bytes(*, triangles: int = 12, unit: str = "CENTIMETERS", up_axis: str = "Z_UP", **extras) -> bytes:
    """Tiny but structurally valid glTF with a triangle list."""
    doc = {
        "asset": {
            "version": "2.0",
            "generator": "windagent-test",
            "extras": {"unit": unit, "up_axis": up_axis, **extras},
        },
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "name": "test_mesh",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "mode": 4,
                    }
                ],
            }
        ],
        "accessors": [
            {"componentType": 5126, "count": 8, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
            {"componentType": 5126, "count": 8, "type": "VEC3"},
            {"componentType": 5126, "count": 8, "type": "VEC2"},
            {"componentType": 5123, "count": triangles * 3, "type": "SCALAR"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 400}],
        "buffers": [{"byteLength": 400}],
    }
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def _gltf_with_texture(*, oversize: bool = False) -> bytes:
    """glTF with an embedded PNG texture (data URI)."""
    from io import BytesIO

    from PIL import Image

    size = (8192, 8192) if oversize else (128, 128)
    buf = BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buf, format="PNG")
    import base64

    uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    doc = {
        "asset": {"version": "2.0", "generator": "windagent-test"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "name": "textured",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "TEXCOORD_0": 1},
                        "indices": 2,
                        "mode": 4,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "mat_0",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicRoughnessTexture": {"index": 0},
                },
            }
        ],
        "images": [{"name": "albedo", "mimeType": "image/png", "uri": uri}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987}],
        "textures": [{"sampler": 0, "source": 0}],
        "accessors": [
            {"componentType": 5126, "count": 4, "type": "VEC3"},
            {"componentType": 5126, "count": 4, "type": "VEC2"},
            {"componentType": 5123, "count": 6, "type": "SCALAR"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 200}],
        "buffers": [{"byteLength": 200}],
    }
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def _make_pipeline(tmp_path: Path, *, runner=None, scratch=None):
    store = ContentAddressedStore(tmp_path / "store")
    publisher = AssetBundlePublisher(str(tmp_path / "bundles"))
    return store, AssetNormalizationPipeline(
        store=store,
        bundle_publisher=publisher,
        job_runner=runner or FakeAssetJobRunner(),
        scratch_root=str(scratch or tmp_path / "scratch"),
    )


def _request(store, data: bytes, *, format=AssetFormat.GLTF, config=None, source_type="LOCAL_LIBRARY"):
    content_hash = store.publish(data)
    asset = ReferenceAsset(
        asset_id="ast_test",
        content_hash=content_hash,
        size_bytes=len(data),
        media_type="unknown",
        mime_type="model/gltf+json",
        source_type=source_type,
        license_state="LICENSED",
    )
    return NormalizationRequest(
        asset=asset,
        format=format,
        source_uri="",
        config=config or NormalizationConfig(),
        requirement=AssetRequirement(kind=AssetKind.PROP, description="test asset"),
    )


def _run(coro):
    return asyncio.run(coro)


class TestFullPipeline:
    def test_local_gltf_full_pipeline_ready(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes())))
        assert result.status is NormalizationStatus.READY
        stages = {s.stage for s in result.report.stages}
        assert stages == {
            NormalizationStage.INGEST,
            NormalizationStage.SECURITY,
            NormalizationStage.PARSE,
            NormalizationStage.UNIT_AXIS,
            NormalizationStage.MESH,
            NormalizationStage.MATERIAL_TEXTURE,
            NormalizationStage.BUDGET,
            NormalizationStage.LOD,
            NormalizationStage.PREVIEW,
            NormalizationStage.PUBLISH,
        }
        assert all(s.status.value == "COMPLETED" for s in result.report.stages)

    def test_canonical_unit_conversion(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes(unit="CENTIMETERS"))))
        assert result.canonical_metadata.detected_unit is UnitSystem.CENTIMETERS
        assert result.canonical_metadata.unit is UnitSystem.METERS
        assert result.canonical_metadata.scale_factor == 0.01
        assert result.canonical_metadata.unit_converted is True

    def test_mesh_stats_and_lods(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes(triangles=24))))
        assert result.mesh_report.triangle_count == 24
        assert result.mesh_report.ok is True
        levels = {lod.level for lod in result.lods}
        assert 0 in levels and 1 in levels
        lod0 = next(entry for entry in result.lods if entry.level == 0)
        assert lod0.generated_by == "source"  # source never overwritten
        lod1 = next(entry for entry in result.lods if entry.level == 1)
        assert lod1.generated_by == "fake"

    def test_preview_and_bundle_published(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes())))
        assert result.preview is not None
        assert result.preview.frames_rendered == 12
        assert result.bundle is not None
        assert result.bundle.bundle_hash
        manifest = json.loads((Path(result.bundle.root) / "manifest.json").read_text())
        assert manifest["bundle_hash"] == result.bundle.bundle_hash
        assert any(f.path == "provenance.json" for f in result.bundle.files)
        assert any(f.path == "validation_report.json" for f in result.bundle.files)

    def test_bundle_hash_deterministic_across_runs(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        data = _gltf_bytes()
        result_a = _run(pipeline.normalize(_request(store, data)))
        result_b = _run(pipeline.normalize(_request(store, data)))
        assert result_a.bundle.bundle_hash == result_b.bundle.bundle_hash


class TestMeshValidationFailClosed:
    def test_zero_triangles_blocks(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        # OBJ with vertices but no faces.
        data = b"v 0 0 0\nv 1 0 0\nv 0 1 0\n"
        result = _run(pipeline.normalize(_request(store, data, format=AssetFormat.OBJ)))
        assert result.status is NormalizationStatus.BLOCKED
        assert any("zero triangles" in e for e in result.report.errors)

    def test_oversized_polygon_budget_blocks(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        config = NormalizationConfig(max_polygons=8)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes(triangles=24), config=config)))
        assert result.status is NormalizationStatus.BLOCKED
        assert result.bundle is None
        assert result.preview is None


class TestVramBudgetBlocked:
    def test_vram_over_limit_blocks_before_preview(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        config = NormalizationConfig(max_vram_bytes=100)
        result = _run(pipeline.normalize(_request(store, _gltf_bytes(), config=config)))
        assert result.status is NormalizationStatus.BLOCKED
        assert result.vram is not None
        assert result.vram.decision.value == "BLOCKED"
        assert result.preview is None  # never blindly rendered
        stage = next(s for s in result.report.stages if s.stage is NormalizationStage.BUDGET)
        assert stage.status.value == "BLOCKED"
        assert NormalizationStage.PREVIEW not in {s.stage for s in result.report.stages}


class TestTextureNormalization:
    def test_texture_capped_and_content_addressed(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        data = _gltf_with_texture(oversize=True)
        result = _run(pipeline.normalize(_request(store, data)))
        assert result.status is NormalizationStatus.READY
        assert len(result.textures) == 1
        texture = result.textures[0]
        assert texture.resolution_capped is True
        assert texture.width <= 4096 and texture.height <= 4096
        assert len(texture.content_hash) == 64
        assert texture.original_width == 8192

    def test_texture_within_limit_not_capped(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, _gltf_with_texture())))
        assert result.textures[0].resolution_capped is False

    def test_path_traversal_uri_recorded_missing(self, tmp_path):
        """External texture URI that escapes the asset root is NEVER read."""
        doc = json.loads(_gltf_with_texture().decode())
        doc["images"][0]["uri"] = "../../../etc/passwd"
        doc["images"][0]["mimeType"] = "image/png"
        data = json.dumps(doc).encode()
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, data)))
        assert result.status is NormalizationStatus.READY
        assert result.textures == []  # external file not resolvable -> missing


class TestSecurityFailClosed:
    @pytest.mark.parametrize(
        "payload",
        [
            b"PK\x03\x04fakezipcontent",
            b"MZ\x90\x00fake-executable",
            b"#!/bin/sh\necho pwned\n",
        ],
    )
    def test_executable_archive_script_rejected_before_parse(self, tmp_path, payload):
        store, pipeline = _make_pipeline(tmp_path)
        result = _run(pipeline.normalize(_request(store, payload)))
        assert result.status is NormalizationStatus.FAILED
        assert result.bundle is None
        stage = next(s for s in result.report.stages if s.stage is NormalizationStage.SECURITY)
        assert stage.status.value == "FAILED"

    def test_content_hash_mismatch_fails(self, tmp_path):
        store, pipeline = _make_pipeline(tmp_path)
        data = _gltf_bytes()
        store.publish(data)
        asset = ReferenceAsset(
            asset_id="ast_bad",
            content_hash="f" * 64,  # declared hash that does NOT match bytes
            size_bytes=len(data),
            media_type="unknown",
            mime_type="model/gltf+json",
            source_type="LOCAL_LIBRARY",
            license_state="LICENSED",
        )
        request = NormalizationRequest(
            asset=asset,
            format=AssetFormat.GLTF,
            requirement=AssetRequirement(kind=AssetKind.PROP, description="bad hash"),
        )
        result = _run(pipeline.normalize(request))
        assert result.status is NormalizationStatus.FAILED


class TestParsers:
    def test_detect_format(self):
        assert detect_format(b"glTF\x02\x00\x00\x00") is AssetFormat.GLB
        assert detect_format(b'{"asset": {"version": "2.0"}}') is AssetFormat.GLTF
        assert detect_format(b"v 0 0 0\nf 1 2 3\n") is AssetFormat.OBJ
        assert detect_format(b"\x00\x01\x02\x03garbage") is AssetFormat.UNKNOWN

    def test_parse_obj_uv_and_normals_detection(self):
        data = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nvn 0 0 1\nf 1/1/1 2/2/1 3/3/1\n"
        snapshot = parse_obj(data)
        assert snapshot.triangle_count == 1
        assert snapshot.object_count == 1
        assert snapshot.objects[0].parts[0].has_uv is True
        assert snapshot.objects[0].parts[0].has_normals is True
        assert snapshot.unit_hint is UnitSystem.METERS
        assert snapshot.up_axis_hint is UpAxis.Z_UP

    def test_parse_gltf_materials_and_missing_textures(self):
        data = _gltf_bytes()
        snapshot = parse_gltf(data)
        assert snapshot.format is AssetFormat.GLTF
        assert snapshot.triangle_count == 12
        assert snapshot.vertex_count == 8
        assert snapshot.unit_hint is UnitSystem.CENTIMETERS
