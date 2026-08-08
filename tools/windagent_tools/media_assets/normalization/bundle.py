"""
Immutable asset bundle publisher (VP3D Phase 7, Stage C item 7).

Publishes the normalized asset as an IMMUTABLE bundle:

    bundle/<bundle_id>/
    ├── manifest.json              (every file + sha256 + bundle_hash)
    ├── validation_report.json     (mesh/material/VRAM findings)
    ├── provenance.json            (source hash + derivation lineage)
    ├── asset.<ext>                (normalized interchange file)
    ├── textures/<hash>.<ext>      (content-addressed textures)
    ├── lods/lod_<N>.<ext>         (derived LODs, source never overwritten)
    └── preview/                   (thumbnail + turntable frames)

The bundle hash is deterministic over sorted (path, sha256) pairs, so the
same inputs always produce the same bundle identity.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from windagent_core.domain.video_production.asset_normalization.errors import (
    AssetNormalizationError,
)
from windagent_core.domain.video_production.asset_normalization.models import (
    AssetBundle,
    BundleFile,
    CanonicalMetadata,
    LodEntry,
    MaterialInfo,
    MeshValidationReport,
    NormalizationReport,
    NormalizationRequest,
    PreviewRenderResult,
    TextureInfo,
    VramEstimate,
)

from windagent_tools.media_assets.normalization.snapshot import MeshSnapshot


class AssetBundlePublisher:
    """Writes immutable bundles into the artifact root."""

    def __init__(self, bundle_root: str) -> None:
        self._root = Path(bundle_root).resolve()

    def publish(
        self,
        *,
        request: NormalizationRequest,
        canonical: CanonicalMetadata,
        mesh_report: MeshValidationReport,
        materials: List[MaterialInfo],
        textures: List[TextureInfo],
        texture_payloads: dict,
        vram: VramEstimate,
        lods: List[LodEntry],
        preview: PreviewRenderResult,
        report: NormalizationReport,
        snapshot: MeshSnapshot,
    ) -> AssetBundle:
        bundle_id = f"b_{request.asset.content_hash[:16]}"
        out = self._root / bundle_id
        if out.exists():
            return self._read_existing(out, bundle_id)

        out.mkdir(parents=True, exist_ok=True)
        (out / "textures").mkdir(exist_ok=True)
        (out / "lods").mkdir(exist_ok=True)
        (out / "preview").mkdir(exist_ok=True)

        files: List[BundleFile] = []

        # Normalized interchange (source copy for host-parsed formats).
        if request.source_uri:
            src = Path(request.source_uri)
            if src.is_file():
                ext = _interchange_extension(request.format.value)
                target = out / f"asset{ext}"
                self._copy_atomic(src, target)
                files.append(self._file(target, "asset" + ext))

        # Content-addressed textures.
        texture_index: dict[str, str] = {}
        for texture in textures:
            data = texture_payloads.get(texture.name)
            if data is None:
                continue
            ext = _texture_extension(texture.format)
            name = f"{texture.content_hash}{ext}"
            target = out / "textures" / name
            if not target.exists():
                target.write_bytes(data)
            rel = f"textures/{name}"
            files.append(self._file(target, rel))
            texture_index[texture.name] = rel

        # LODs (LOD0 references the source hash; derived levels have files).
        for lod in lods:
            if lod.level == 0:
                rel = f"lods/lod_{lod.level}.json"
                payload = lod.model_dump(mode="json")
                target = out / rel
                target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                files.append(self._file(target, rel))
            elif lod.local_path:
                src = Path(lod.local_path)
                if not src.is_file():
                    raise AssetNormalizationError(f"LOD {lod.level} file missing: {src}")
                name = f"lod_{lod.level}{src.suffix}"
                target = out / "lods" / name
                self._copy_atomic(src, target)
                files.append(self._file(target, f"lods/{name}"))
            else:
                rel = f"lods/lod_{lod.level}.json"
                payload = lod.model_dump(mode="json")
                target = out / rel
                target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                files.append(self._file(target, rel))

        # Preview (engine-produced files copied into the bundle).
        preview_manifest = {
            "thumbnail": preview.thumbnail_file,
            "turntable": preview.turntable_files,
            "frames_rendered": preview.frames_rendered,
            "engine": preview.engine,
            "device": preview.device,
            "content_hash": preview.content_hash,
            "generated_by": preview.generated_by,
        }
        for local in preview.local_files:
            src = Path(local)
            if not src.is_file():
                raise AssetNormalizationError(f"preview file missing: {src}")
            target = out / "preview" / src.name
            self._copy_atomic(src, target)
            files.append(self._file(target, f"preview/{src.name}"))
        rel = "preview/preview.json"
        target = out / rel
        target.write_text(json.dumps(preview_manifest, sort_keys=True), encoding="utf-8")
        files.append(self._file(target, rel))

        # Reports.
        validation = {
            "canonical_metadata": canonical.model_dump(mode="json"),
            "mesh": mesh_report.model_dump(mode="json"),
            "materials": [m.model_dump(mode="json") for m in materials],
            "textures": [t.model_dump(mode="json") for t in textures],
            "vram": vram.model_dump(mode="json"),
            "lods": [lod.model_dump(mode="json") for lod in lods],
        }
        rel = "validation_report.json"
        target = out / rel
        target.write_text(json.dumps(validation, sort_keys=True), encoding="utf-8")
        files.append(self._file(target, rel))

        provenance = {
            "source_content_hash": request.asset.content_hash,
            "source_type": request.asset.source_type.value,
            "source_url": request.asset.source_url,
            "license_state": request.asset.license_state.value,
            "format": request.format.value,
            "adapter_version": request.adapter_version,
            "normalized_at": datetime.now(timezone.utc).isoformat(),
            "derived_from_hash": request.asset.content_hash,
            "stages": [s.model_dump(mode="json") for s in report.stages],
        }
        rel = "provenance.json"
        target = out / rel
        target.write_text(json.dumps(provenance, sort_keys=True), encoding="utf-8")
        files.append(self._file(target, rel))

        # Manifest last (bundle hash covers everything including itself).
        bundle_hash = AssetBundle.compute_hash(files)
        manifest = {
            "bundle_id": bundle_id,
            "bundle_hash": bundle_hash,
            "asset_content_hash": request.asset.content_hash,
            "files": [f.model_dump(mode="json") for f in sorted(files, key=lambda f: f.path)],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rel = "manifest.json"
        target = out / rel
        target.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        manifest_hash = _sha256_file(target)
        files.append(BundleFile(path=rel, sha256=manifest_hash, size_bytes=target.stat().st_size))

        return AssetBundle(
            bundle_id=bundle_id,
            bundle_hash=bundle_hash,
            root=str(out),
            files=files,
        )

    def _read_existing(self, out: Path, bundle_id: str) -> AssetBundle:
        manifest_path = out / "manifest.json"
        if not manifest_path.is_file():
            raise AssetNormalizationError("existing bundle missing manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("bundle_id") != bundle_id:
            raise AssetNormalizationError("bundle id mismatch on existing bundle")
        files = [BundleFile.model_validate(f) for f in manifest.get("files", [])]
        return AssetBundle(
            bundle_id=bundle_id,
            bundle_hash=str(manifest.get("bundle_hash", "")),
            root=str(out),
            files=files,
        )

    def _copy_atomic(self, src: Path, target: Path) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(src.read_bytes())
        tmp.replace(target)

    @staticmethod
    def _file(path: Path, rel: str) -> BundleFile:
        return BundleFile(
            path=rel,
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _interchange_extension(fmt: str) -> str:
    return {
        "GLTF": ".gltf",
        "GLB": ".glb",
        "OBJ": ".obj",
        "FBX": ".fbx",
        "USD": ".usd",
        "BLEND": ".blend",
    }.get(fmt, ".asset")


def _texture_extension(fmt: str) -> str:
    return {
        "png": ".png",
        "jpeg": ".jpg",
        "webp": ".webp",
    }.get(fmt, ".png")


__all__ = ["AssetBundlePublisher", "_sha256_file"]
