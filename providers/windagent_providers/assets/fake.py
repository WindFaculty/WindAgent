"""
Fake adapters for CI and shared contract tests (VP3D Phase 5, backlog item 7).

Every fake implements the exact semantics real adapters must provide:

- capability matching BEFORE the call (fake capability reflects declared
  support);
- discover returns DISCOVERED candidates only;
- acquire builds a content-addressed ``ReferenceAsset`` with provenance and
  NEVER stores credentials;
- failures are typed (``GenerationNotEnabledError``, ``ProviderTimeoutError``
  via configured latency, etc.);
- deterministic output for the same requirement hash (same seed -> same hashes)
  so contract tests are stable.

Fakes are also usable as the injected backends for the real adapters
(``InternetAssetAdapter``, ``MeshApiAdapter``, ``FutureGeneratorAdapter``) in
integration tests.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional

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
    GenerationNotEnabledError,
    LicenseConstraint,
    ProviderAvailability,
)
from windagent_core.domain.video_production.enums import AssetSourceType, LicenseState, MediaType
from windagent_core.domain.video_production.ids import (
    AssetCandidateId,
    ReferenceAssetId,
)

from windagent_providers.assets.adapter import AcquiredAsset, AssetAdapter
from windagent_providers.assets.generator import GeneratorBackendPort


def _seed_key(*parts: str) -> str:
    raw = "::".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fake_candidate(
    provider_id: str,
    adapter_version: str,
    requirement_hash: str,
    *,
    title: str,
    license_state: LicenseState = LicenseState.UNKNOWN,
    extra: Optional[dict] = None,
) -> AssetCandidate:
    seed = _seed_key(provider_id, title)
    return AssetCandidate(
        candidate_id=AssetCandidateId(seed[:24]),
        requirement_hash=requirement_hash,
        provider_id=provider_id,
        adapter_version=adapter_version,
        title=title,
        description=f"fake {title} (deterministic)",
        license_state=license_state,
        poly_count=10_000,
        texture_resolutions=[1024],
        metadata=dict(extra or {}),
    )


class FakeLocalAssetAdapter(AssetAdapter):
    """Deterministic local-library fake: 1 candidate per supported kind."""

    adapter_id = "fake.local.library"
    adapter_version = "1.0.0"

    def capability(self) -> AssetProviderCapability:
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.LOCAL,
            adapter_version=self.adapter_version,
            availability=ProviderAvailability.READY,
            supported_kinds=[AssetKind.CHARACTER, AssetKind.PROP, AssetKind.ENVIRONMENT],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=4096,
            license_constraints=[
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.NO_ATTRIBUTION,
            ],
            max_polygons=None,
            max_file_bytes=None,
            description="Fake local library for CI (deterministic).",
        )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        return [
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"fake_local_{request.requirement.kind.value.lower()}",
                license_state=LicenseState.LICENSED,
            )
        ]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        content = f"fake-local:{candidate.title}".encode("utf-8")
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=hashlib.sha256(content).hexdigest(),
            media_type=MediaType.UNKNOWN,
            mime_type="model/gltf-binary",
            size_bytes=len(content),
            source_type=AssetSourceType.LOCAL_LIBRARY,
            license_state=candidate.license_state,
            metadata={"provider_id": self.adapter_id},
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.LOCAL_LIBRARY,
            license_state=candidate.license_state,
            notes="fake local acquisition",
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition)


class FakeInternetAssetAdapter(AssetAdapter):
    """Deterministic Internet fake; optional latency raises typed timeout."""

    adapter_id = "fake.internet.search"
    adapter_version = "1.0.0"

    def __init__(self, *, latency_seconds: float = 0.0) -> None:
        self._latency_seconds = latency_seconds

    def capability(self) -> AssetProviderCapability:
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.INTERNET,
            adapter_version=self.adapter_version,
            availability=ProviderAvailability.READY,
            supported_kinds=[kind for kind in AssetKind],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=8192,
            license_constraints=[
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ATTRIBUTION_REQUIRED,
                LicenseConstraint.NO_ATTRIBUTION,
            ],
            max_polygons=None,
            max_file_bytes=None,
            description="Fake Internet search for CI (deterministic).",
        )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        if self._latency_seconds > 0:
            import asyncio

            await asyncio.sleep(self._latency_seconds)
        return [
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"web_{request.requirement.kind.value.lower()}_a",
                license_state=LicenseState.LICENSED,
            ),
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"web_{request.requirement.kind.value.lower()}_b",
                license_state=LicenseState.UNKNOWN,
            ),
        ]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        if self._latency_seconds > 0:
            import asyncio

            await asyncio.sleep(self._latency_seconds)
        content = f"fake-internet:{candidate.title}".encode("utf-8")
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=hashlib.sha256(content).hexdigest(),
            media_type=MediaType.UNKNOWN,
            mime_type="model/gltf-binary",
            size_bytes=len(content),
            source_type=AssetSourceType.INTERNET,
            source_url=candidate.source_url,
            license_state=candidate.license_state,
            metadata={"provider_id": self.adapter_id},
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.INTERNET,
            source_url=candidate.source_url,
            license_state=candidate.license_state,
            notes="fake internet acquisition",
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition)


class FakeMeshApiAdapter(AssetAdapter):
    """Deterministic Mesh API fake: one LICENSED candidate per kind."""

    adapter_id = "fake.mesh.api.v1"
    adapter_version = "1.0.0"

    def capability(self) -> AssetProviderCapability:
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.MESH_API,
            adapter_version=self.adapter_version,
            availability=ProviderAvailability.READY,
            supported_kinds=[
                AssetKind.CHARACTER,
                AssetKind.PROP,
                AssetKind.ENVIRONMENT,
                AssetKind.VEHICLE,
                AssetKind.CREATURE,
                AssetKind.TEXTURE,
            ],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=8192,
            license_constraints=[
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ANY_PERMISSIVE,
            ],
            max_polygons=5_000_000,
            max_file_bytes=1024 * 1024 * 1024,
            description="Fake Mesh API for CI (deterministic).",
        )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        return [
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"mesh_api_{request.requirement.kind.value.lower()}",
                license_state=LicenseState.LICENSED,
                extra={"poly_count": 25_000},
            )
        ]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        content = f"fake-mesh-api:{candidate.title}".encode("utf-8")
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=hashlib.sha256(content).hexdigest(),
            media_type=MediaType.UNKNOWN,
            mime_type="model/gltf-binary",
            size_bytes=len(content),
            source_type=AssetSourceType.PROVIDER,
            license_state=candidate.license_state,
            metadata={"provider_id": self.adapter_id},
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.PROVIDER,
            license_state=candidate.license_state,
            notes="fake mesh api acquisition",
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition)


class FakeMeshMcpAdapter(AssetAdapter):
    """Deterministic Mesh MCP fake (same semantics as the API fake)."""

    adapter_id = "fake.mesh.mcp.v1"
    adapter_version = "1.0.0"

    def capability(self) -> AssetProviderCapability:
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.MESH_MCP,
            adapter_version=self.adapter_version,
            availability=ProviderAvailability.READY,
            supported_kinds=[kind for kind in AssetKind],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=8192,
            license_constraints=[
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.ATTRIBUTION_REQUIRED,
            ],
            max_polygons=5_000_000,
            max_file_bytes=1024 * 1024 * 1024,
            description="Fake Mesh MCP for CI (deterministic).",
        )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        return [
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"mesh_mcp_{request.requirement.kind.value.lower()}",
                license_state=LicenseState.LICENSED,
            )
        ]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        content = f"fake-mesh-mcp:{candidate.title}".encode("utf-8")
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=hashlib.sha256(content).hexdigest(),
            media_type=MediaType.UNKNOWN,
            mime_type="model/gltf-binary",
            size_bytes=len(content),
            source_type=AssetSourceType.PROVIDER,
            license_state=candidate.license_state,
            metadata={"provider_id": self.adapter_id},
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.PROVIDER,
            license_state=candidate.license_state,
            notes="fake mesh mcp acquisition",
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition)


class FakeGeneratorAdapter(AssetAdapter):
    """Deterministic generator fake; generation can be disabled (typed)."""

    adapter_id = "fake.generator.future"
    adapter_version = "1.0.0"

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled

    def capability(self) -> AssetProviderCapability:
        return AssetProviderCapability(
            provider_id=self.adapter_id,
            provider_kind=AdapterKind.GENERATOR,
            adapter_version=self.adapter_version,
            availability=(
                ProviderAvailability.READY
                if self._enabled
                else ProviderAvailability.REQUIRES_CONFIG
            ),
            supported_kinds=[
                AssetKind.CHARACTER,
                AssetKind.PROP,
                AssetKind.ENVIRONMENT,
                AssetKind.VEHICLE,
                AssetKind.CREATURE,
                AssetKind.TEXTURE,
                AssetKind.MATERIAL,
            ],
            supported_styles=[style for style in AssetStyle],
            rig_supported=True,
            max_texture_resolution=4096,
            license_constraints=[
                LicenseConstraint.ANY_PERMISSIVE,
                LicenseConstraint.COMMERCIAL_ALLOWED,
                LicenseConstraint.NO_ATTRIBUTION,
            ],
            max_polygons=3_000_000,
            max_file_bytes=512 * 1024 * 1024,
            supports_generation=True,
            description="Fake 3D generator for CI (deterministic).",
        )

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise GenerationNotEnabledError(
                f"Provider {self.adapter_id}: generation not enabled.",
                details={"provider_id": self.adapter_id},
            )

    async def discover(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        self._require_enabled()
        return [
            _fake_candidate(
                self.adapter_id,
                self.adapter_version,
                request.requirement.canonical_hash,
                title=f"generated_{request.requirement.kind.value.lower()}",
                license_state=LicenseState.LICENSED,
                extra={
                    "provider": "windagent-fake",
                    "model": "fake-3d-gen-1",
                    "seed": 42,
                },
            )
        ]

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        self._require_enabled()
        content = f"fake-generated:{candidate.title}".encode("utf-8")
        prompt_hash = hashlib.sha256(request.requirement.canonical.encode("utf-8")).hexdigest()
        asset = ReferenceAsset(
            asset_id=ReferenceAssetId.generate("ast_ref"),
            content_hash=hashlib.sha256(content).hexdigest(),
            media_type=MediaType.UNKNOWN,
            mime_type="model/gltf-binary",
            size_bytes=len(content),
            source_type=AssetSourceType.GENERATED,
            license_state=candidate.license_state,
            metadata={
                "provider_id": self.adapter_id,
                "provider": "windagent-fake",
                "model": "fake-3d-gen-1",
                "prompt_hash": prompt_hash,
                "seed": 42,
            },
        )
        acquisition = AssetAcquisitionRecord(
            source_type=AssetSourceType.GENERATED,
            license_state=candidate.license_state,
            notes="fake generation acquisition",
        )
        return AcquiredAsset(asset=asset, acquisition=acquisition)


class FakeInternetSearchBackend:
    """Search backend injectable into InternetAssetAdapter (deterministic).

    Candidates are tagged with the OUTER adapter identity (``internet.search``)
    so the gateway can route acquire back to the adapter that discovered them.
    """

    def __init__(self) -> None:
        self._inner = FakeInternetAssetAdapter()

    async def search(self, request: AssetResolutionRequest) -> List[AssetCandidate]:
        candidates = await self._inner.discover(request)
        return [
            candidate.model_copy(
                update={
                    "provider_id": "internet.search",
                    "adapter_version": "1.0.0",
                }
            )
            for candidate in candidates
        ]


class FakeInternetAcquisitionBackend:
    """Acquisition backend injectable into InternetAssetAdapter."""

    def __init__(self) -> None:
        self._inner = FakeInternetAssetAdapter()

    async def acquire(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        return await self._inner.acquire(candidate, request)


class FakeGeneratorBackend(GeneratorBackendPort):
    """Generator backend injectable into FutureGeneratorAdapter.

    Candidates are tagged with the OUTER adapter identity
    (``generator.future``).
    """

    def __init__(self, *, enabled: bool = True) -> None:
        self._inner = FakeGeneratorAdapter(enabled=enabled)

    async def generate_candidates(
        self,
        request: AssetResolutionRequest,
    ) -> List[AssetCandidate]:
        candidates = await self._inner.discover(request)
        return [
            candidate.model_copy(
                update={
                    "provider_id": "generator.future",
                    "adapter_version": "1.0.0",
                }
            )
            for candidate in candidates
        ]

    async def acquire_generated(
        self,
        candidate: AssetCandidate,
        request: AssetResolutionRequest,
    ) -> AcquiredAsset:
        return await self._inner.acquire(candidate, request)


__all__ = [
    "FakeLocalAssetAdapter",
    "FakeInternetAssetAdapter",
    "FakeMeshApiAdapter",
    "FakeMeshMcpAdapter",
    "FakeGeneratorAdapter",
    "FakeInternetSearchBackend",
    "FakeInternetAcquisitionBackend",
    "FakeGeneratorBackend",
]
