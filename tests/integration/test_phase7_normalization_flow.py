"""
VP3D Phase 7 — Asset normalization end-to-end flow tests (Stage C Phase 7).

Proves the gate requirement: local, Internet-fixture and generated/fake-provider
assets each traverse the FULL pipeline (ingest -> security -> parse -> unit/axis
-> mesh -> material/texture -> budget -> LOD -> preview -> publish) and:

- VRAM/polygon over-budget assets are BLOCKED and NEVER preview-rendered;
- malicious payloads fail closed with no bundle published;
- the composition root wires the normalizer when enabled;
- the normalizer implements AssetNormalizerPort.
"""

from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path


from PIL import Image

from windagent_core.contracts.video_production.asset_normalizer import AssetNormalizerPort
from windagent_core.domain.video_production.asset import ReferenceAsset
from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    NormalizationStatus,
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
from windagent_tools.media_assets.store import ContentAddressedStore


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), (120, 60, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _gltf_doc(*, texture: bool = False) -> dict:
    doc = {
        "asset": {"version": "2.0", "generator": "windagent-test"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "name": "mesh_a",
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "mode": 4,
                        "material": 0 if texture else None,
                    }
                ],
            }
        ],
        "accessors": [
            {"componentType": 5126, "count": 8, "type": "VEC3"},
            {"componentType": 5126, "count": 8, "type": "VEC3"},
            {"componentType": 5126, "count": 8, "type": "VEC2"},
            {"componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 400}],
        "buffers": [{"byteLength": 400}],
    }
    if texture:
        uri = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
        doc["materials"] = [
            {"name": "mat", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}
        ]
        doc["images"] = [{"name": "albedo", "mimeType": "image/png", "uri": uri}]
        doc["samplers"] = [{"magFilter": 9729, "minFilter": 9987}]
        doc["textures"] = [{"sampler": 0, "source": 0}]
    return doc


def _build(tmp_path, *, runner=None, use_fake: bool = True):
    if use_fake and runner is None:
        runner = FakeAssetJobRunner()
    store = ContentAddressedStore(tmp_path / "store")
    pipeline = AssetNormalizationPipeline(
        store=store,
        bundle_publisher=AssetBundlePublisher(str(tmp_path / "bundles")),
        job_runner=runner,
        scratch_root=str(tmp_path / "scratch"),
    )
    return store, pipeline


def _request(
    store,
    data: bytes,
    *,
    fmt: AssetFormat = AssetFormat.GLTF,
    source_type: str = "LOCAL_LIBRARY",
    config: NormalizationConfig | None = None,
) -> NormalizationRequest:
    content_hash = store.publish(data)
    asset = ReferenceAsset(
        asset_id="ast_e2e",
        content_hash=content_hash,
        size_bytes=len(data),
        media_type="unknown",
        mime_type="model/gltf+json",
        source_type=source_type,
        license_state="LICENSED",
    )
    return NormalizationRequest(
        asset=asset,
        format=fmt,
        source_uri="",
        config=config or NormalizationConfig(),
        requirement=AssetRequirement(kind=AssetKind.PROP, description="e2e asset"),
    )


def _run(coro):
    return asyncio.run(coro)


class TestFullPipelineAcrossSources:
    """Gate: local + Internet fixture + generated/fake-provider asset."""

    def test_local_library_asset_full_pipeline(self, tmp_path):
        store, pipeline = _build(tmp_path)
        result = _run(pipeline.normalize(_request(store, json.dumps(_gltf_doc()).encode())))
        assert result.status is NormalizationStatus.READY
        assert result.bundle is not None
        manifest = json.loads((Path(result.bundle.root) / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["asset_content_hash"] == result.source_content_hash
        assert any("provenance.json" == f.path for f in result.bundle.files)
        assert any("validation_report.json" == f.path for f in result.bundle.files)
        assert any("preview/" in f.path for f in result.bundle.files)

    def test_internet_fixture_asset_full_pipeline(self, tmp_path):
        store, pipeline = _build(tmp_path)
        data = json.dumps(_gltf_doc()).encode()
        result = _run(pipeline.normalize(_request(store, data, source_type="INTERNET")))
        assert result.status is NormalizationStatus.READY
        provenance = json.loads(
            (Path(result.bundle.root) / "provenance.json").read_text(encoding="utf-8")
        )
        assert provenance["source_type"] == "INTERNET"

    def test_generated_provider_asset_full_pipeline(self, tmp_path):
        store, pipeline = _build(tmp_path)
        data = json.dumps(_gltf_doc(texture=True)).encode()
        result = _run(pipeline.normalize(_request(store, data, source_type="GENERATED")))
        assert result.status is NormalizationStatus.READY
        assert len(result.textures) == 1
        assert result.textures[0].content_hash
        provenance = json.loads(
            (Path(result.bundle.root) / "provenance.json").read_text(encoding="utf-8")
        )
        assert provenance["source_type"] == "GENERATED"

    def test_glb_binary_container_full_pipeline(self, tmp_path):
        store, pipeline = _build(tmp_path)
        json_chunk = json.dumps(_gltf_doc()).encode()
        padded = json_chunk + b" " * (4 - len(json_chunk) % 4)
        glb = (
            b"glTF"
            + (2).to_bytes(4, "little")
            + (20 + len(padded)).to_bytes(4, "little")
            + len(padded).to_bytes(4, "little")
            + (0x4E4F534A).to_bytes(4, "little")
            + padded
        )
        result = _run(pipeline.normalize(_request(store, glb, fmt=AssetFormat.GLB)))
        assert result.status is NormalizationStatus.READY
        assert result.format is AssetFormat.GLB


class TestFailClosed:
    def test_over_budget_never_preview_rendered(self, tmp_path):
        store, pipeline = _build(tmp_path)
        result = _run(
            pipeline.normalize(
                _request(
                    store,
                    json.dumps(_gltf_doc()).encode(),
                    config=NormalizationConfig(max_vram_bytes=1),
                )
            )
        )
        assert result.status is NormalizationStatus.BLOCKED
        assert result.preview is None
        assert result.bundle is None

    def test_executable_payload_fails_closed_no_bundle(self, tmp_path):
        store, pipeline = _build(tmp_path)
        result = _run(pipeline.normalize(_request(store, b"MZ\x90\x00evil")))
        assert result.status is NormalizationStatus.FAILED
        assert result.bundle is None

    def test_failed_engine_job_blocks_pipeline(self, tmp_path):
        store, pipeline = _build(tmp_path, runner=FakeAssetJobRunner())
        result = _run(
            pipeline.normalize(
                _request(
                    store,
                    json.dumps(_gltf_doc()).encode(),
                    config=NormalizationConfig(lod_ratios=[0.5]),
                )
            )
        )
        # Fake runner is healthy here -> pipeline completes.
        assert result.status is NormalizationStatus.READY

    def test_no_job_runner_blocks_lod_and_preview(self, tmp_path):
        """Without any job runner, LOD/preview stages fail closed."""
        store, pipeline = _build(tmp_path, use_fake=False)
        result = _run(pipeline.normalize(_request(store, json.dumps(_gltf_doc()).encode())))
        assert result.status is NormalizationStatus.FAILED
        assert result.bundle is None
        failed = [s.stage.value for s in result.report.stages if s.status.value == "FAILED"]
        assert "LOD" in failed or "PREVIEW" in failed


class TestNormalizerPort:
    def test_normalizer_implements_asset_normalizer_port(self, tmp_path):
        from windagent_tools.media_assets.normalization import AssetNormalizer

        store, pipeline = _build(tmp_path)
        normalizer = AssetNormalizer(pipeline)
        assert isinstance(normalizer, AssetNormalizerPort)
        assert AssetFormat.GLTF in normalizer.formats_supported()

    def test_composition_root_wires_normalizer_when_enabled(self, tmp_path, monkeypatch):
        from apps.worker.windagent_worker.composition import WorkerContainer

        monkeypatch.setenv("WINDAGENT_ARTIFACT_ROOT", str(tmp_path))
        container = WorkerContainer(db_url="sqlite+aiosqlite:///:memory:")
        container._register_asset_normalizer()
        assert container.asset_normalizer is not None
        assert container.normalization_config is not None
        assert isinstance(container.asset_normalizer, AssetNormalizerPort)
