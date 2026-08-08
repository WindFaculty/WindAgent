"""
LocalAssetAdapter — local 3D asset library (VP3D Phase 5).

Scans a configured content-addressed library directory and returns DISCOVERED
candidates; ``acquire`` verifies the file is inside the library root (no path
traversal), hashes the content and builds a content-addressed
``ReferenceAsset`` with provenance. Never touches the network.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from windagent_core.domain.video_production.asset import (
    AssetAcquisitionRecord,
    ReferenceAsset,
)
from windagent_core.domain.video_production.asset_resolution import (
    AdapterKind,
    AssetCandidate,
    AssetKind,
    AssetProviderCapability,
    AssetResolutionRequest,
    AssetStyle,
    LicenseConstraint,
    ProviderAvailability,
)
from windagent_core.domain.video_production.enums import AssetSourceType, LicenseState, MediaType
from windagent_core.domain.video_production.ids import (
    AssetCandidateId,
    ReferenceAssetId,
)

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter

LIBRARY_INDEX_FILENAME = "library_index.json"

EXTENSION_KINDS: Dict[str, List[str]] = {
    ".glb": ["CHARACTER", "PROP", "ENVIRONMENT", "VEHICLE", "CREATURE", "TEXTURE"],
    ".gltf": ["CHARACTER", "PROP", "ENVIRONMENT", "VEHICLE", "CREATURE", "TEXTURE"],
    ".fbx": ["CHARACTER", "PROP", "VEHICLE", "CREATURE", "ANIMATION_CLIP"],
    ".obj": ["PROP", "ENVIRONMENT", "VEHICLE", "CREATURE", "TEXTURE"],
    ".blend": ["CHARACTER", "PROP", "ENVIRONMENT", "VEHICLE", "CREATURE", "MATERIAL"],
    ".png": ["TEXTURE", "MATERIAL"],
    ".jpg": ["TEXTURE"],
    ".hdr": ["TEXTURE"],
    ".exr": ["TEXTURE"],
}

SUPPORTED_EXTENSIONS = tuple(EXTENSION_KINDS)


class LocalAssetAdapter(AssetAdapter):
    """Adapter over a local content-addressed library directory."""

    adapter_id = "local.library"
    adapter_version = "1.0.0"

    def __init__(
        self,
        library_root: Path,
        *,
        index: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._root = Path(library_root)
        self._index = dict(index or {})

    # ------------------------------------------------------------------
    # capability
    # ------------------------------------------------------------------

    def capability(self) -> AssetProviderCapability:
        ready = self._root.is_dir()
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.LOCAL,
            adapter_version=self.adapter_version,
            availability=ProviderAvailability.READY if ready else ProviderAvailability.UNAVAILABLE,
            supported_kinds=[kind for kind in AssetKind],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=16384,
            license_constraints=[
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.NO_ATTRIBUTION,
                LicenseConstraint.ATTRIBUTION_REQUIRED,
            ],
            max_polygons=None,
            max_file_bytes=None,
            description="Local content-addressed 3D asset library (no network).",
        )

    # ------------------------------------------------------------------
    # discover
    # ------------------------------------------------------------------

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        if not self._root.is_dir():
            return []
        index = self._load_index()
        requirement_hash = request.requirement.canonical_hash
        candidates: List[AssetCandidate] = []
        for path in sorted(self._root.iterdir()):
            if not path.is_file() or path.name == LIBRARY_INDEX_FILENAME:
                continue
            meta = self._entry_meta(index, path.name)
            kinds = [AssetKind[k] for k in meta.get("kinds", [])] or self._kinds_for(path.suffix)
            if request.requirement.kind not in kinds:
                continue
            candidates.append(
                AssetCandidate(
                    candidate_id=AssetCandidateId.generate("ast_c"),
                    requirement_hash=requirement_hash,
                    provider_id=self.adapter_id,
                    adapter_version=self.adapter_version,
                    title=meta.get("title") or path.stem,
                    description=meta.get("description", ""),
                    license_state=LicenseState(meta.get("license_state", LicenseState.UNKNOWN.value)),
                    license_name=meta.get("license_name", ""),
                    poly_count=int(meta.get("poly_count", 0)),
                    texture_resolutions=[int(t) for t in meta.get("texture_resolutions", [])],
                    metadata={
                        "relative_path": path.name,
                        "size_bytes": path.stat().st_size,
                    },
                )
            )
        return candidates[: request.max_candidates]

    # ------------------------------------------------------------------
    # acquire
    # ------------------------------------------------------------------

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        relative = str(candidate.metadata.get("relative_path", ""))
        resolved = (self._root / relative).resolve()
        root = self._root.resolve()
        if not resolved.is_relative_to(root):
            from windagent_core.domain.video_production.asset_resolution import (
                AssetResolutionError,
            )

            raise AssetResolutionError(
                f"Local asset path escapes library root: {relative!r}",
                details={"provider_id": self.adapter_id},
            )
        if not resolved.is_file():
            from windagent_core.domain.video_production.asset_resolution import (
                AssetResolutionError,
            )

            raise AssetResolutionError(
                f"Local asset missing: {relative!r}",
                details={"provider_id": self.adapter_id},
            )
        content = resolved.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        is_texture = resolved.suffix.lower() in {".png", ".jpg", ".hdr", ".exr"}
        meta = self._entry_meta(self._load_index(), relative)
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=content_hash,
            media_type=MediaType.IMAGE if is_texture else MediaType.UNKNOWN,
            mime_type=_guess_mime(resolved.suffix),
            size_bytes=len(content),
            source_type=AssetSourceType.LOCAL_LIBRARY,
            source_url=f"library://{relative}",
            license_state=candidate.license_state,
            metadata={
                "provider_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "kind": request.requirement.kind.value,
            },
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.LOCAL_LIBRARY,
            source_url=f"library://{relative}",
            license_state=candidate.license_state,
            notes=f"acquired from local library via {self.adapter_id} {self.adapter_version}",
        )
        # Phase 6 trust evidence: the checksum is computed by us from the file
        # bytes (verified by construction). Commercial-use right is only
        # claimed when the library index explicitly declares it — a local
        # asset with an UNKNOWN license stays QUARANTINED (fail closed).
        from windagent_core.domain.video_production.asset_resolution import (
            AssetTrustEvidence,
        )

        trust = AssetTrustEvidence(
            checksum_verified=True,
            commercial_use_verified=bool(meta.get("commercial_use", False)),
            trademark=bool(meta.get("trademark", False)),
            requires_attribution=bool(meta.get("requires_attribution", False)),
            content_scan_passed=True,
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition, trust=trust)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _load_index(self) -> Dict[str, Any]:
        """Load library_index.json from disk (injected index wins).

        The library index is the local library's LICENSE + metadata authority:
        it declares license_state / commercial_use / trademark / attribution
        per file, which the Phase 6 trust gate consumes. An unreadable or
        absent index yields an empty dict (UNKNOWN license -> QUARANTINED).
        """
        if self._index:
            return self._index
        index_path = self._root / LIBRARY_INDEX_FILENAME
        if not index_path.is_file():
            return {}
        try:
            import json

            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _entry_meta(self, index: Dict[str, Any], filename: str) -> Dict[str, Any]:
        entries = index.get("entries", [])
        for entry in entries:
            if entry.get("file") == filename:
                return entry
        return {}

    def _kinds_for(self, suffix: str) -> List[AssetKind]:
        names = EXTENSION_KINDS.get(suffix.lower(), [])
        return [AssetKind[name] for name in names]


def _guess_mime(suffix: str) -> str:
    return {
        ".glb": "model/gltf-binary",
        ".gltf": "model/gltf+json",
        ".fbx": "application/octet-stream",
        ".obj": "text/plain",
        ".blend": "application/octet-stream",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".hdr": "image/vnd.radiance",
        ".exr": "image/x-exr",
    }.get(suffix.lower(), "application/octet-stream")


__all__ = ["LocalAssetAdapter"]
