"""
Canonical enums for the Universal Asset Gateway (VP3D Phase 5).

These normalize the vocabulary used by every provider adapter (local, Internet,
Mesh API, Mesh MCP, generator) so capability matching and typed rejection can be
performed BEFORE any provider call. Values are stable string identifiers — never
display names — and must not change once used in receipts.
"""

from __future__ import annotations

from enum import Enum


class AssetKind(str, Enum):
    """Canonical 3D asset type taxonomy (road_map.md Phase 5)."""

    CHARACTER = "CHARACTER"
    PROP = "PROP"
    ENVIRONMENT = "ENVIRONMENT"
    VEHICLE = "VEHICLE"
    CREATURE = "CREATURE"
    TEXTURE = "TEXTURE"
    MATERIAL = "MATERIAL"
    ANIMATION_CLIP = "ANIMATION_CLIP"


class AssetStyle(str, Enum):
    """Canonical visual style vocabulary for 3D assets."""

    THREE_D_CARTOON = "3D_CARTOON"
    THREE_D_REALISTIC = "3D_REALISTIC"
    STYLIZED = "STYLIZED"
    LOW_POLY = "LOW_POLY"
    PBR_MATERIAL = "PBR_MATERIAL"


class TopologyPolicy(str, Enum):
    """Mesh topology constraints a requirement may impose."""

    UNSPECIFIED = "UNSPECIFIED"
    MANIFOLD_ONLY = "MANIFOLD_ONLY"
    QUAD_DOMINANT = "QUAD_DOMINANT"
    TRIANGLE_OK = "TRIANGLE_OK"


class RigRequirement(str, Enum):
    """Rigging requirement levels for a required asset."""

    NO_RIG = "NO_RIG"
    SIMPLE_RIG = "SIMPLE_RIG"
    SKELETAL = "SKELETAL"
    FACIAL_CAPABLE = "FACIAL_CAPABLE"


class LicenseConstraint(str, Enum):
    """License constraints a requirement may impose on candidates.

    ``UNSPECIFIED`` matches any provider; all other values must be satisfied by
    the provider capability BEFORE an adapter is invoked. License state
    enforcement itself (QUARANTINED/APPROVED) is Phase 6 provenance work.
    """

    UNSPECIFIED = "UNSPECIFIED"
    ANY_PERMISSIVE = "ANY_PERMISSIVE"
    COMMERCIAL_ALLOWED = "COMMERCIAL_ALLOWED"
    ATTRIBUTION_REQUIRED = "ATTRIBUTION_REQUIRED"
    NO_ATTRIBUTION = "NO_ATTRIBUTION"


class TextureResolution(str, Enum):
    """Canonical texture resolution bands (pixel edge length)."""

    TEXTURE_512 = "512"
    TEXTURE_1024 = "1024"
    TEXTURE_2048 = "2048"
    TEXTURE_4096 = "4096"
    TEXTURE_8192 = "8192"

    @property
    def pixels(self) -> int:
        return int(self.value)


class AdapterKind(str, Enum):
    """Kind of provider behind an asset adapter."""

    LOCAL = "LOCAL"
    INTERNET = "INTERNET"
    MESH_API = "MESH_API"
    MESH_MCP = "MESH_MCP"
    GENERATOR = "GENERATOR"


class ProviderAvailability(str, Enum):
    """Runtime availability of an adapter (fail-closed by default)."""

    READY = "READY"
    REQUIRES_CONFIG = "REQUIRES_CONFIG"
    UNAVAILABLE = "UNAVAILABLE"


class AssetResolutionStatus(str, Enum):
    """Outcome of a gateway operation (discover or acquire).

    ``DISCOVERED`` means candidates were found but NOT acquired — search
    results are never usable assets. ``RESOLVED`` means the candidate was
    acquired into a content-addressed ``ReferenceAsset`` AND passed the trust
    gate (license/checksum/commercial-use evidence — Phase 6). ``QUARANTINED``
    means the asset was acquired but could not be trusted (UNKNOWN license,
    unverified checksum or unverified commercial use) — it is never usable.
    """

    DISCOVERED = "DISCOVERED"
    RESOLVED = "RESOLVED"
    QUARANTINED = "QUARANTINED"
    NOT_FOUND = "NOT_FOUND"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


__all__ = [
    "AssetKind",
    "AssetStyle",
    "TopologyPolicy",
    "RigRequirement",
    "LicenseConstraint",
    "TextureResolution",
    "AdapterKind",
    "ProviderAvailability",
    "AssetResolutionStatus",
]
