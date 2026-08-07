"""
Provider-neutral DTOs for the Universal Asset Gateway (VP3D Phase 5).

All DTOs are frozen and provider-agnostic: no adapter SDK type, no credential,
no network transport object ever appears here. ``AssetRequirement`` carries a
canonical hash used as the idempotency key; ``AssetCandidate`` is strictly a
DISCOVERED result; ``AssetResolutionResult`` records the typed outcome and the
redacted attempt trail for every provider touched.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from windagent_core.domain.video_production.asset_resolution.enums import (
    AdapterKind,
    AssetKind,
    AssetResolutionStatus,
    AssetStyle,
    LicenseConstraint,
    ProviderAvailability,
    RigRequirement,
    TopologyPolicy,
)
from windagent_core.domain.video_production.asset import (
    AssetAcquisitionRecord,
    ReferenceAsset,
)
from windagent_core.domain.video_production.enums import LicenseState
from windagent_core.domain.video_production.ids import (
    AssetCandidateId,
    AssetResolutionId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Default budget: baseline 1080p scene with a mid-range laptop / RTX 5060 8 GB.
DEFAULT_MAX_POLYGONS = 1_000_000
DEFAULT_MAX_TEXTURE_RESOLUTION = 4096
DEFAULT_MAX_FILE_BYTES = 512 * 1024 * 1024
DEFAULT_MAX_VRAM_ESTIMATE_BYTES = 4 * 1024 * 1024 * 1024


class AssetBudget(BaseModel):
    """Hard bounds applied to a requirement and matched against capability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_polygons: int = Field(default=DEFAULT_MAX_POLYGONS, ge=1)
    max_texture_resolution: int = Field(default=DEFAULT_MAX_TEXTURE_RESOLUTION, ge=64, le=16384)
    max_file_bytes: int = Field(default=DEFAULT_MAX_FILE_BYTES, ge=1)
    max_vram_estimate_bytes: int = Field(default=DEFAULT_MAX_VRAM_ESTIMATE_BYTES, ge=1)


class AssetRequirement(BaseModel):
    """Canonical, provider-neutral 3D asset request (road_map.md Phase 5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: AssetKind
    description: str = Field(min_length=1, max_length=500)
    style: AssetStyle = AssetStyle.THREE_D_REALISTIC
    topology: TopologyPolicy = TopologyPolicy.UNSPECIFIED
    rig_required: RigRequirement = RigRequirement.NO_RIG
    texture_resolution: int = Field(default=1024, ge=64, le=16384)
    license_constraint: LicenseConstraint = LicenseConstraint.UNSPECIFIED
    budget: AssetBudget = Field(default_factory=AssetBudget)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def canonical(self) -> str:
        """Stable canonical form of the requirement CONTENT.

        ``requirement_id`` and ``metadata`` are intentionally excluded:
        idempotency is defined over the substance of the request, so two
        requests that differ only in advisory fields share one cache key.
        """
        payload = {
            "kind": self.kind.value,
            "description": self.description,
            "style": self.style.value,
            "topology": self.topology.value,
            "rig_required": self.rig_required.value,
            "texture_resolution": self.texture_resolution,
            "license_constraint": self.license_constraint.value,
            "budget": self.budget.model_dump(mode="json"),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @property
    def canonical_hash(self) -> str:
        """SHA-256 idempotency key: requirement content + adapter/version."""
        return hashlib.sha256(self.canonical.encode("utf-8")).hexdigest()

    def cache_key(self, adapter_id: str, adapter_version: str) -> str:
        """Idempotency key scoped to ONE adapter and its version.

        A different adapter version must never reuse a stale cached outcome.
        """
        raw = f"{self.canonical_hash}::{adapter_id}::{adapter_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AssetProviderCapability(BaseModel):
    """Declared capability of one asset adapter (used for pre-call matching)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str = Field(min_length=1, max_length=100)
    provider_kind: AdapterKind
    adapter_version: str = Field(min_length=1)
    availability: ProviderAvailability = ProviderAvailability.READY
    supported_kinds: List[AssetKind] = Field(default_factory=list)
    supported_styles: List[AssetStyle] = Field(default_factory=list)
    rig_supported: bool = False
    max_texture_resolution: int = Field(default=0, ge=0)
    license_constraints: List[LicenseConstraint] = Field(default_factory=list)
    max_polygons: Optional[int] = Field(default=None, ge=0)
    max_file_bytes: Optional[int] = Field(default=None, ge=0)
    supports_generation: bool = False
    description: str = ""


class AssetCandidate(BaseModel):
    """A DISCOVERED candidate — never an approved or usable asset.

    Candidates are search/scan results only. They become usable only after
    ``acquire`` produces a content-addressed ``ReferenceAsset`` with provenance
    (license state carried through, never auto-approved).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: AssetCandidateId
    requirement_hash: str = Field(min_length=64, max_length=64)
    provider_id: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    source_url: Optional[str] = None
    license_state: LicenseState = LicenseState.UNKNOWN
    license_name: str = ""
    poly_count: int = Field(default=0, ge=0)
    texture_resolutions: List[int] = Field(default_factory=list)
    preview_uri: Optional[str] = None
    discovered_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetResolutionRequest(BaseModel):
    """One gateway invocation: requirement + routing/execution policy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement: AssetRequirement
    adapter_ids: List[str] = Field(default_factory=list)
    max_candidates: int = Field(default=5, ge=1, le=50)
    timeout_seconds: float = Field(default=30.0, gt=0)
    max_retries: int = Field(default=1, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetResolutionAttempt(BaseModel):
    """Redacted record of ONE provider attempt inside a resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    adapter_version: str
    status: AssetResolutionStatus
    error_code: Optional[str] = None
    error_message: str = ""
    started_at: datetime = Field(default_factory=utc_now)
    duration_ms: int = Field(default=0, ge=0)
    cache_hit: bool = False
    candidates_found: int = Field(default=0, ge=0)


class AssetResolutionResult(BaseModel):
    """Typed outcome of discover or acquire through the gateway."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    resolution_id: AssetResolutionId
    requirement_hash: str = Field(min_length=64, max_length=64)
    status: AssetResolutionStatus
    candidates: List[AssetCandidate] = Field(default_factory=list)
    acquired: Optional[ReferenceAsset] = None
    acquisition: Optional[AssetAcquisitionRecord] = None
    attempts: List[AssetResolutionAttempt] = Field(default_factory=list)
    provider_id: Optional[str] = None
    adapter_version: Optional[str] = None
    cache_hit: bool = False
    duration_ms: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "utc_now",
    "DEFAULT_MAX_POLYGONS",
    "DEFAULT_MAX_TEXTURE_RESOLUTION",
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_VRAM_ESTIMATE_BYTES",
    "AssetBudget",
    "AssetRequirement",
    "AssetProviderCapability",
    "AssetCandidate",
    "AssetResolutionRequest",
    "AssetResolutionAttempt",
    "AssetResolutionResult",
]
