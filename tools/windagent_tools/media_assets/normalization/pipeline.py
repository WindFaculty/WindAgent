"""
Asset normalization pipeline (VP3D Phase 7, Stage C).

Canonical flow (plan Stage C §5):

    ingest -> security -> parse -> unit/axis -> mesh -> material/texture
    -> poly/VRAM budget -> LOD -> preview render -> approval/cache

Rules enforced here (plan Stage C Phase 7):

1. Canonical metadata is METERS + Z_UP; adapters convert the real units/axis.
2. Mesh validation fails closed on non-manifold/degenerate/topology defects.
3. PBR materials are normalized; textures are content-addressed with
   resolution/bit-depth limits and color-space metadata.
4. LODs are derived artifacts per policy — the source is NEVER overwritten;
   every LOD carries its own hash and quality metrics.
5. Geometry/texture VRAM is estimated BEFORE preview; over the hard limit the
   asset is BLOCKED and never blindly rendered.
6. Preview render uses the deterministic Blender profile of Stage B.
7. The published bundle is immutable: interchange + textures + preview +
   manifest + provenance + validation report, with a deterministic hash.

The pipeline is engine-neutral on the host: every Blender-touching operation
(import validate for FBX/USD/BLEND, unit/axis conversion, LOD decimation,
preview render) goes through the injected ``AssetJobRunner`` port, which is
implemented by the Blender adapter (real) or fakes (CI).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from windagent_core.domain.video_production.asset_normalization.enums import (
    AssetFormat,
    NormalizationStage,
    NormalizationStatus,
    StageStatus,
    UnitSystem,
    UpAxis,
)
from windagent_core.domain.video_production.asset_normalization.errors import (
    AssetNormalizationError,
    UnsupportedFormatError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    CanonicalMetadata,
    MaterialInfo,
    MeshValidationReport,
    NormalizationConfig,
    NormalizationReport,
    NormalizationRequest,
    NormalizedAsset,
    StageRecord,
    TextureInfo,
    VramEstimate,
)
from windagent_core.domain.video_production.ids import NormalizationRunId

from windagent_tools.media_assets.normalization.bundle import AssetBundlePublisher
from windagent_tools.media_assets.normalization.checks import MeshValidator
from windagent_tools.media_assets.normalization.job_runner import AssetJobRunner
from windagent_tools.media_assets.normalization.lod import LodPolicyApplier
from windagent_tools.media_assets.normalization.parsers import MeshSnapshot, parse_asset
from windagent_tools.media_assets.normalization.preview import PreviewRunner
from windagent_tools.media_assets.normalization.textures import TextureNormalizer
from windagent_tools.media_assets.normalization.vram import VramEstimator
from windagent_tools.media_assets.security import classify_payload
from windagent_tools.media_assets.store import ContentAddressedStore
from windagent_tools.media_assets.trust import AssetContentScanner


class AssetNormalizationPipeline:
    """Orchestrates the canonical normalization flow for one asset."""

    def __init__(
        self,
        *,
        store: ContentAddressedStore,
        bundle_publisher: AssetBundlePublisher,
        validator: Optional[MeshValidator] = None,
        vram: Optional[VramEstimator] = None,
        textures: Optional[TextureNormalizer] = None,
        lod: Optional[LodPolicyApplier] = None,
        preview: Optional[PreviewRunner] = None,
        scanner: Optional[AssetContentScanner] = None,
        job_runner: Optional[AssetJobRunner] = None,
        scratch_root: str = "artifacts/video_production_3d/phase_07_scratch",
    ) -> None:
        self._store = store
        self._bundle = bundle_publisher
        self._validator = validator or MeshValidator()
        self._vram = vram or VramEstimator()
        self._textures = textures or TextureNormalizer(store)
        self._lod = lod or LodPolicyApplier(job_runner=job_runner)
        self._preview = preview or PreviewRunner(job_runner=job_runner)
        self._scanner = scanner or AssetContentScanner()
        self._job_runner = job_runner
        self._scratch_root = Path(scratch_root).resolve()

    # ------------------------------------------------------------------
    def formats_supported(self) -> list[AssetFormat]:
        """Formats ingestible by the HOST-side parser (engine-free)."""
        return [AssetFormat.GLTF, AssetFormat.GLB, AssetFormat.OBJ]

    # ------------------------------------------------------------------
    async def normalize(self, request: NormalizationRequest) -> NormalizedAsset:
        report = NormalizationReport()
        started = time.monotonic()
        scratch = self._scratch_root / f"run_{request.asset.content_hash[:12]}"
        scratch.mkdir(parents=True, exist_ok=True)

        # 1. INGEST — resolve bytes from the content store, verify hash.
        try:
            data = self._ingest(request)
            if not request.source_uri:
                ext = _input_extension(request.format)
                source_path = scratch / f"input{ext}"
                source_path.write_bytes(data)
                request = request.model_copy(update={"source_uri": str(source_path)})
            report.stages.append(self._stage(NormalizationStage.INGEST, True, "content verified"))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.INGEST, exc, started)

        # 2. SECURITY — static scan BEFORE any import/parse.
        try:
            try:
                self._scanner.assert_safe(data)
            except Exception as exc:  # noqa: BLE001 - scanner raises tools errors
                from windagent_core.domain.video_production.asset_normalization.errors import (
                    AssetSecurityRejectedError,
                )

                raise AssetSecurityRejectedError(f"static scan rejected payload: {exc}") from exc
            fingerprint = classify_payload(data)
            if fingerprint.is_executable or fingerprint.is_archive or fingerprint.looks_polyglot:
                raise UnsupportedFormatError(
                    "payload classified as executable/archive/polyglot (fail closed)",
                )
            report.stages.append(self._stage(NormalizationStage.SECURITY, True, "static scan clean"))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.SECURITY, exc, started)

        # 3. PARSE — host-side parse (glTF/GLB/OBJ) or Blender job (FBX/USD/BLEND).
        try:
            snapshot, parse_note = self._parse(request, data)
            report.stages.append(self._stage(NormalizationStage.PARSE, True, parse_note))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.PARSE, exc, started)

        # 4. UNIT/AXIS — canonical meters + Z-up conversion.
        try:
            canonical = self._canonical_metadata(snapshot)
            report.stages.append(
                self._stage(NormalizationStage.UNIT_AXIS, True, f"{canonical.detected_unit.value} -> meters, {canonical.detected_up_axis.value} -> Z-up")
            )
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.UNIT_AXIS, exc, started)

        # 5. MESH — structural validation (blocking issues fail closed).
        try:
            mesh_report = self._validator.validate(snapshot)
            report.stages.append(self._stage(NormalizationStage.MESH, mesh_report.ok, mesh_summary(mesh_report)))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.MESH, exc, started)
        if not mesh_report.ok:
            return self._failed(
                request, report, NormalizationStage.MESH,
                AssetNormalizationError(
                    "blocking mesh defects",
                    details={"issues": list(mesh_report.blocking_issues)},
                ),
                started, status=NormalizationStatus.BLOCKED, mesh_report=mesh_report,
            )

        # 6. MATERIAL/TEXTURE — PBR normalization + content-addressed textures.
        try:
            materials, textures, texture_payloads = self._materialize(snapshot, request.config)
            report.stages.append(self._stage(NormalizationStage.MATERIAL_TEXTURE, True, f"{len(textures)} textures, {len(materials)} materials"))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.MATERIAL_TEXTURE, exc, started)

        # 7. BUDGET — poly + VRAM estimate BEFORE any preview render.
        vram: Optional[VramEstimate] = None
        try:
            vram = self._vram.estimate(snapshot, textures, request.config)
            if mesh_report.triangle_count > request.config.max_polygons:
                raise AssetNormalizationError(
                    "polygon count exceeds hard budget",
                    details={"triangles": mesh_report.triangle_count, "limit": request.config.max_polygons},
                )
            report.stages.append(self._stage(NormalizationStage.BUDGET, vram.decision.value == "WITHIN_BUDGET", vram.detail))
        except AssetNormalizationError as exc:
            return self._failed(
                request, report, NormalizationStage.BUDGET, exc, started,
                status=NormalizationStatus.BLOCKED, vram=vram,
            )
        if vram.decision.value == "BLOCKED":
            return self._failed(
                request, report, NormalizationStage.BUDGET,
                AssetNormalizationError(vram.detail), started,
                status=NormalizationStatus.BLOCKED, vram=vram,
            )

        # 8. LOD — derived artifacts, source never overwritten.
        try:
            lods = await self._lod.generate(snapshot, request, workspace=str(scratch), started=started)
            report.stages.append(self._stage(NormalizationStage.LOD, True, f"{len(lods)} LOD levels"))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.LOD, exc, started)

        # 9. PREVIEW — deterministic profile (Blender job or fake in CI).
        try:
            preview = await self._preview.render(snapshot, request, workspace=str(scratch))
            report.stages.append(self._stage(NormalizationStage.PREVIEW, preview.ok, f"{preview.frames_rendered} frames, {preview.engine}/{preview.device}"))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.PREVIEW, exc, started)
        if not preview.ok:
            return self._failed(request, report, NormalizationStage.PREVIEW, AssetNormalizationError("preview render failed"), started)

        # 10. PUBLISH — immutable bundle + provenance.
        try:
            bundle = self._bundle.publish(
                request=request,
                canonical=canonical,
                mesh_report=mesh_report,
                materials=materials,
                textures=textures,
                texture_payloads=texture_payloads,
                vram=vram,
                lods=lods,
                preview=preview,
                report=report,
                snapshot=snapshot,
            )
            report.stages.append(self._stage(NormalizationStage.PUBLISH, True, f"bundle {bundle.bundle_hash[:12]}..."))
        except AssetNormalizationError as exc:
            return self._failed(request, report, NormalizationStage.PUBLISH, exc, started)

        return NormalizedAsset(
            run_id=self._run_id(),
            source_content_hash=request.asset.content_hash,
            format=request.format,
            status=NormalizationStatus.READY,
            canonical_metadata=canonical,
            mesh_report=mesh_report,
            materials=materials,
            textures=textures,
            vram=vram,
            lods=lods,
            preview=preview,
            bundle=bundle,
            derived_content_hash=bundle.bundle_hash,
            report=report,
        )

    # ------------------------------------------------------------------
    def _ingest(self, request: NormalizationRequest) -> bytes:
        if request.asset.content_hash:
            data = self._store.read(request.asset.content_hash)
            if data is not None:
                if ContentAddressedStore.content_hash(data) != request.asset.content_hash:
                    raise AssetNormalizationError("ingested bytes mismatch declared content hash")
                return data
        if request.source_uri:
            from pathlib import Path

            path = Path(request.source_uri)
            if path.is_file():
                data = path.read_bytes()
                if request.asset.content_hash and ContentAddressedStore.content_hash(data) != request.asset.content_hash:
                    raise AssetNormalizationError("ingested bytes mismatch declared content hash")
                return data
        raise AssetNormalizationError("asset payload not found in store or at source_uri")

    def _parse(self, request: NormalizationRequest, data: bytes) -> tuple[MeshSnapshot, str]:
        snapshot = parse_asset(data, declared_format=request.format)
        note = f"{snapshot.format.value} parsed ({snapshot.triangle_count} triangles, {len(snapshot.materials)} materials)"
        return snapshot, note

    @staticmethod
    def _canonical_metadata(snapshot: MeshSnapshot) -> CanonicalMetadata:
        unit = snapshot.unit_hint or UnitSystem.UNKNOWN
        up_axis = snapshot.up_axis_hint or UpAxis.UNKNOWN
        return CanonicalMetadata(
            unit=UnitSystem.METERS,
            up_axis=UpAxis.Z_UP,
            scale_factor=unit.meters_per_unit,
            detected_unit=unit,
            detected_up_axis=up_axis,
            unit_converted=unit is not UnitSystem.METERS,
            axis_converted=up_axis is not UpAxis.Z_UP,
        )

    def _materialize(
        self, snapshot: MeshSnapshot, config: NormalizationConfig
    ) -> tuple[list[MaterialInfo], list[TextureInfo], dict]:
        from windagent_tools.media_assets.normalization.textures import NormalizedTexture

        materials: list[MaterialInfo] = []
        textures: list[TextureInfo] = []
        payloads: dict[str, bytes] = {}
        normalized: list[NormalizedTexture] = []
        for image in snapshot.images:
            result = self._textures.normalize_image(image, config)
            if result is not None:
                normalized.append(result)
        for entry in normalized:
            textures.append(entry.info)
            payloads[entry.info.name] = entry.payload
        for material in snapshot.materials:
            materials.append(
                MaterialInfo(
                    name=material.name,
                    pbr_ok=material.pbr and not material.unsupported_extension,
                    base_color_texture=material.base_color_texture,
                    normal_texture=material.normal_texture,
                    roughness_texture=material.roughness_texture,
                    metallic_texture=material.metallic_texture,
                    unsupported_extension=material.unsupported_extension,
                    notes=list(material.notes),
                )
            )
        return materials, textures, payloads

    @staticmethod
    def _stage(stage: NormalizationStage, ok: bool, detail: str) -> StageRecord:
        return StageRecord(
            stage=stage,
            status=StageStatus.COMPLETED if ok else StageStatus.FAILED,
            duration_ms=0,
            detail=detail,
        )

    @staticmethod
    def _run_id() -> NormalizationRunId:
        return NormalizationRunId.generate("norm")

    def _failed(
        self,
        request: NormalizationRequest,
        report: NormalizationReport,
        stage: NormalizationStage,
        exc: AssetNormalizationError,
        started: float,
        *,
        status: NormalizationStatus = NormalizationStatus.FAILED,
        mesh_report: Optional[MeshValidationReport] = None,
        vram: Optional[VramEstimate] = None,
    ) -> NormalizedAsset:
        issues = (exc.details or {}).get("issues", [])
        report.errors.append(f"{stage.value}: {exc.message}" + (f" ({', '.join(str(i) for i in issues)})" if issues else ""))
        stage_status = StageStatus.FAILED if status is not NormalizationStatus.BLOCKED else StageStatus.BLOCKED
        # A failed/blocked stage already recorded via _stage() must not be
        # duplicated — replace it with the authoritative record.
        for index, record in enumerate(report.stages):
            if record.stage == stage:
                report = report.model_copy(
                    update={
                        "stages": [
                            *report.stages[:index],
                            StageRecord(
                                stage=stage,
                                status=stage_status,
                                duration_ms=int((time.monotonic() - started) * 1000),
                                detail=exc.message,
                            ),
                            *report.stages[index + 1 :],
                        ]
                    }
                )
                break
        else:
            report = report.model_copy(
                update={
                    "stages": [
                        *report.stages,
                        StageRecord(
                            stage=stage,
                            status=stage_status,
                            duration_ms=int((time.monotonic() - started) * 1000),
                            detail=exc.message,
                        ),
                    ]
                }
            )
        return NormalizedAsset(
            run_id=self._run_id(),
            source_content_hash=request.asset.content_hash,
            format=request.format,
            status=status,
            mesh_report=mesh_report or MeshValidationReport(),
            vram=vram,
            report=report,
        )


def _input_extension(fmt: AssetFormat) -> str:
    return {
        AssetFormat.GLTF: ".gltf",
        AssetFormat.GLB: ".glb",
        AssetFormat.OBJ: ".obj",
        AssetFormat.FBX: ".fbx",
        AssetFormat.USD: ".usd",
    }.get(fmt, ".asset")


def mesh_summary(report: MeshValidationReport) -> str:
    parts = [
        f"{report.object_count} objects",
        f"{report.triangle_count} triangles",
    ]
    if report.degenerate_faces:
        parts.append(f"{report.degenerate_faces} degenerate faces")
    if report.non_manifold_edges:
        parts.append(f"{report.non_manifold_edges} non-manifold edges")
    if report.missing_uv_layers:
        parts.append(f"{len(report.missing_uv_layers)} missing UVs")
    return ", ".join(parts)


class AssetNormalizer:
    """AssetNormalizerPort implementation over the normalization pipeline."""

    def __init__(self, pipeline: AssetNormalizationPipeline) -> None:
        self._pipeline = pipeline

    async def normalize(self, request: NormalizationRequest) -> NormalizedAsset:
        return await self._pipeline.normalize(request)

    def formats_supported(self) -> list[AssetFormat]:
        return self._pipeline.formats_supported()


__all__ = [
    "AssetNormalizationPipeline",
    "AssetNormalizer",
    "mesh_summary",
]